"""Daily monitor entrypoint for Gulf energy shock early-warning signals."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from alerts.notifier import create_github_issue, send_email_alert, send_telegram_message
from analysis.scoring import compute_alert_level, compute_energy_stress, compute_rss_score, summarize
from data.fetch_data import fetch_fred_series, fetch_rss_feed_status, keyword_mentions


def load_config(path: str = "config.json") -> Dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_previous_snapshot(path: str) -> Dict:
    if not Path(path).exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _save_json(path: str, payload: Dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _collect_rss_matches(feed_urls: List[str], keywords: List[str]) -> Tuple[List[Dict], List[Dict]]:
    all_matches: List[Dict] = []
    health: List[Dict] = []
    for url in feed_urls:
        articles, feed_status = fetch_rss_feed_status(url)
        matches = keyword_mentions(articles, keywords)

        health.append(
            {
                "feed_url": feed_status.feed_url,
                "success": feed_status.success,
                "article_count": feed_status.article_count,
                "keyword_match_count": len(matches),
                "error": feed_status.error,
            }
        )

        for article in matches:
            all_matches.append(
                {
                    "title": article.title,
                    "link": article.link,
                    "published": article.published,
                    "source": url,
                }
            )
    return all_matches, health


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc_iso(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _cooldown_elapsed(previous_snapshot: Dict, cooldown_minutes: int, now: datetime) -> bool:
    if cooldown_minutes <= 0:
        return True

    marker = previous_snapshot.get("last_notification_utc") or previous_snapshot.get("timestamp_utc")
    if not marker:
        return True

    previous_time = _parse_utc_iso(marker)
    if previous_time is None:
        return True

    return (now - previous_time) >= timedelta(minutes=cooldown_minutes)


def _latest_value(observations: List[Dict[str, str]]) -> float | None:
    if not observations:
        return None
    try:
        return float(observations[-1]["value"])
    except Exception:
        return None


def _compute_data_quality(fred_status: Dict, shipping_feed_health: List[Dict], geopolitical_feed_health: List[Dict]) -> Dict:
    shipping_success_count = sum(1 for row in shipping_feed_health if row.get("success"))
    geopolitical_success_count = sum(1 for row in geopolitical_feed_health if row.get("success"))

    critical_checks = {
        "fred_energy_available": bool(fred_status.get("success")),
        "shipping_source_available": shipping_success_count >= 1,
        "geopolitical_source_available": geopolitical_success_count >= 1,
    }
    critical_available_count = sum(1 for ok in critical_checks.values() if ok)

    if critical_available_count == 3:
        confidence = "HIGH"
    elif critical_available_count == 2:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return {
        "confidence": confidence,
        "critical_checks": critical_checks,
        "critical_sources_healthy": critical_available_count == 3,
        "shipping_success_count": shipping_success_count,
        "geopolitical_success_count": geopolitical_success_count,
    }


def _notify_if_configured(message: str, alert_level: int) -> None:
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID")
    if tg_token and tg_chat:
        try:
            send_telegram_message(tg_token, tg_chat, message)
        except Exception:
            pass

    gh_repo = os.getenv("GITHUB_REPOSITORY")
    gh_token = os.getenv("GITHUB_TOKEN")
    if gh_repo and gh_token:
        try:
            create_github_issue(
                gh_repo,
                gh_token,
                title=f"Energy shock monitor alert changed to L{alert_level}",
                body=message,
            )
        except Exception:
            pass

    smtp_host = os.getenv("EMAIL_SMTP_HOST")
    smtp_port = os.getenv("EMAIL_SMTP_PORT")
    smtp_username = os.getenv("EMAIL_SMTP_USERNAME")
    smtp_password = os.getenv("EMAIL_SMTP_PASSWORD")
    sender_email = os.getenv("EMAIL_FROM")
    recipient_email = os.getenv("EMAIL_TO")
    starttls_env = os.getenv("EMAIL_SMTP_STARTTLS", "true").lower()
    use_starttls = starttls_env in ("1", "true", "yes")

    if smtp_host and smtp_port and smtp_username and smtp_password and sender_email and recipient_email:
        try:
            send_email_alert(
                smtp_host=smtp_host,
                smtp_port=int(smtp_port),
                smtp_username=smtp_username,
                smtp_password=smtp_password,
                sender_email=sender_email,
                recipient_email=recipient_email,
                subject=f"Energy shock alert changed to Level {alert_level}",
                body=message,
                use_starttls=use_starttls,
            )
        except Exception:
            pass


def run() -> Dict:
    config = load_config()
    thresholds = config["thresholds"]
    operations = config.get("operations", {})
    cooldown_minutes = int(operations.get("notification_cooldown_minutes", 60))

    fred_key = os.getenv("FRED_API_KEY", "")
    brent_obs: List[Dict[str, str]] = []
    treasury_obs: List[Dict[str, str]] = []

    fred_status = {
        "attempted": bool(fred_key),
        "success": False,
        "error": "",
        "series": {
            "brent": {
                "series_id": config["fred"]["series"]["brent"],
                "success": False,
                "observation_count": 0,
                "latest": None,
                "error": "",
            },
            "treasury_2y": {
                "series_id": config["fred"]["series"]["treasury_2y"],
                "success": False,
                "observation_count": 0,
                "latest": None,
                "error": "",
            },
        },
    }

    if not fred_key:
        fred_status["error"] = "FRED_API_KEY is missing"
    else:
        for key, series_id in [
            ("brent", config["fred"]["series"]["brent"]),
            ("treasury_2y", config["fred"]["series"]["treasury_2y"]),
        ]:
            try:
                observations = fetch_fred_series(config["fred"]["base_url"], fred_key, series_id, days=21)
                fred_status["series"][key]["observation_count"] = len(observations)
                fred_status["series"][key]["latest"] = _latest_value(observations)
                fred_status["series"][key]["success"] = len(observations) > 0
                if key == "brent":
                    brent_obs = observations
                else:
                    treasury_obs = observations
            except Exception as exc:
                fred_status["series"][key]["error"] = str(exc)

        brent_ok = fred_status["series"]["brent"]["success"]
        treasury_ok = fred_status["series"]["treasury_2y"]["success"]
        fred_status["success"] = bool(brent_ok and treasury_ok)
        if not fred_status["success"]:
            fred_status["error"] = "One or more required FRED series returned no valid observations"

    energy = compute_energy_stress(brent_obs, thresholds)

    shipping_matches, shipping_feed_health = _collect_rss_matches(
        config["rss"]["shipping_feeds"], config["rss"]["shipping_keywords"]
    )
    geopolitical_matches, geopolitical_feed_health = _collect_rss_matches(
        config["rss"]["geopolitical_feeds"], config["rss"]["geopolitical_keywords"]
    )

    scores = {
        "energy_stress_score": energy.score,
        "shipping_disruption_score": compute_rss_score(
            len(shipping_matches), thresholds["keyword_match_alert"]
        ),
        "geopolitical_escalation_score": compute_rss_score(
            len(geopolitical_matches), thresholds["keyword_match_alert"]
        ),
    }

    alert_level = compute_alert_level(scores, thresholds["score_elevated_threshold"])
    now_utc = _now_utc()
    quality = _compute_data_quality(fred_status, shipping_feed_health, geopolitical_feed_health)

    snapshot = {
        "timestamp_utc": now_utc.isoformat(),
        "confidence": quality["confidence"],
        "scores": scores,
        "energy_flags": energy.indicators,
        "energy_details": {
            **energy.details,
            "latest_treasury_2y": fred_status["series"]["treasury_2y"]["latest"],
            "treasury_2y_observation_count": fred_status["series"]["treasury_2y"]["observation_count"],
        },
        "shipping_matches": shipping_matches[:20],
        "geopolitical_matches": geopolitical_matches[:20],
        "data_health": {
            "fred": fred_status,
            "shipping_feeds": shipping_feed_health,
            "geopolitical_feeds": geopolitical_feed_health,
            "critical_checks": quality["critical_checks"],
            "critical_sources_healthy": quality["critical_sources_healthy"],
            "shipping_success_count": quality["shipping_success_count"],
            "geopolitical_success_count": quality["geopolitical_success_count"],
        },
        "operations": {
            "notification_cooldown_minutes": cooldown_minutes,
            "notification_sent": False,
            "notification_reason": "",
            "last_notification_utc": "",
        },
        "alert_level": alert_level,
    }
    snapshot["summary"] = summarize(snapshot)

    output_cfg = config["output"]
    previous = _load_previous_snapshot(output_cfg["snapshot_path"])

    old_level = previous.get("alert_level") if previous else None
    level_changed = old_level is not None and old_level != alert_level
    cooldown_ok = _cooldown_elapsed(previous, cooldown_minutes, now_utc)

    if level_changed and cooldown_ok:
        message = f"Energy shock monitor alert changed: {old_level} -> {alert_level}. {snapshot['summary']}"
        _notify_if_configured(message, alert_level)
        snapshot["operations"]["notification_sent"] = True
        snapshot["operations"]["notification_reason"] = "alert_level_changed"
        snapshot["operations"]["last_notification_utc"] = now_utc.isoformat()
        snapshot["last_notification_utc"] = now_utc.isoformat()
    elif level_changed and not cooldown_ok:
        snapshot["operations"]["notification_reason"] = "cooldown_active"
        if previous.get("last_notification_utc"):
            snapshot["operations"]["last_notification_utc"] = previous["last_notification_utc"]
            snapshot["last_notification_utc"] = previous["last_notification_utc"]
    else:
        snapshot["operations"]["notification_reason"] = "no_alert_level_change"
        if previous.get("last_notification_utc"):
            snapshot["operations"]["last_notification_utc"] = previous["last_notification_utc"]
            snapshot["last_notification_utc"] = previous["last_notification_utc"]

    _save_json(output_cfg["previous_snapshot_path"], previous if previous else snapshot)
    _save_json(output_cfg["snapshot_path"], snapshot)

    print(snapshot["summary"])
    return snapshot


if __name__ == "__main__":
    result = run()
    fail_on_unhealthy = bool(load_config().get("operations", {}).get("fail_on_unhealthy_sources", True))
    if fail_on_unhealthy and not result["data_health"]["critical_sources_healthy"]:
        raise SystemExit("Critical data sources unavailable; failing run for trustworthiness")
    if not result["data_health"]["fred"]["attempted"]:
        raise SystemExit("FRED_API_KEY missing; failing run")
    if not result["data_health"]["fred"]["success"]:
        raise SystemExit("FRED returned no valid observations for required series; failing run")
