"""Daily monitor entrypoint for Gulf energy shock early-warning signals."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from alerts.notifier import create_github_issue, send_telegram_message
from analysis.scoring import compute_alert_level, compute_energy_stress, compute_rss_score, summarize
from data.fetch_data import fetch_fred_series, fetch_rss_articles, keyword_mentions


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


def _collect_rss_matches(feed_urls: List[str], keywords: List[str]) -> List[Dict]:
    all_matches: List[Dict] = []
    for url in feed_urls:
        articles = fetch_rss_articles(url)
        matches = keyword_mentions(articles, keywords)
        for article in matches:
            all_matches.append(
                {
                    "title": article.title,
                    "link": article.link,
                    "published": article.published,
                    "source": url,
                }
            )
    return all_matches


def run() -> Dict:
    config = load_config()
    thresholds = config["thresholds"]

    fred_key = os.getenv("FRED_API_KEY", "")
    brent_obs = []
    if fred_key:
        brent_obs = fetch_fred_series(config["fred"]["base_url"], fred_key, config["fred"]["series"]["brent"], days=21)

    energy = compute_energy_stress(brent_obs, thresholds)

    shipping_matches = _collect_rss_matches(config["rss"]["shipping_feeds"], config["rss"]["shipping_keywords"])
    geopolitical_matches = _collect_rss_matches(config["rss"]["geopolitical_feeds"], config["rss"]["geopolitical_keywords"])

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

    snapshot = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scores": scores,
        "energy_flags": energy.indicators,
        "energy_details": energy.details,
        "shipping_matches": shipping_matches[:20],
        "geopolitical_matches": geopolitical_matches[:20],
        "alert_level": alert_level,
    }
    snapshot["summary"] = summarize(snapshot)

    output_cfg = config["output"]
    previous = _load_previous_snapshot(output_cfg["snapshot_path"])
    _save_json(output_cfg["previous_snapshot_path"], previous if previous else snapshot)
    _save_json(output_cfg["snapshot_path"], snapshot)

    old_level = previous.get("alert_level") if previous else None
    if old_level is not None and old_level != alert_level:
        message = f"Energy shock monitor alert changed: {old_level} -> {alert_level}. {snapshot['summary']}"

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

    print(snapshot["summary"])
    return snapshot


if __name__ == "__main__":
    run()
