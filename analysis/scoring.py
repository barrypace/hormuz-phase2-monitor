"""Signal scoring and alert-level logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class EnergySignals:
    score: int
    indicators: Dict[str, bool]
    details: Dict[str, float]


def _to_float_list(observations: List[Dict[str, str]]) -> List[float]:
    values: List[float] = []
    for row in observations:
        try:
            values.append(float(row["value"]))
        except (ValueError, KeyError, TypeError):
            continue
    return values


def compute_energy_stress(brent_obs: List[Dict[str, str]], thresholds: Dict) -> EnergySignals:
    values = _to_float_list(brent_obs)
    indicators = {
        "brent_price_alert": False,
        "weekly_change_alert": False,
        "sustained_uptrend": False,
    }
    details = {"latest_brent": 0.0, "weekly_change": 0.0}

    if not values:
        return EnergySignals(score=0, indicators=indicators, details=details)

    latest = values[-1]
    details["latest_brent"] = latest
    indicators["brent_price_alert"] = latest > thresholds["brent_price_alert"]

    if len(values) >= 6:
        week_back = values[-6]
        if week_back > 0:
            weekly_change = (latest - week_back) / week_back
            details["weekly_change"] = weekly_change
            indicators["weekly_change_alert"] = weekly_change > thresholds["weekly_change_alert"]

    n = thresholds["sustained_trend_days"]
    if len(values) >= n:
        window = values[-n:]
        indicators["sustained_uptrend"] = all(window[i] > window[i - 1] for i in range(1, len(window)))

    score = sum(1 for v in indicators.values() if v)
    return EnergySignals(score=score, indicators=indicators, details=details)


def compute_rss_score(match_count: int, threshold: int) -> int:
    if match_count == 0:
        return 0
    if match_count < threshold:
        return 1
    return 2


def compute_alert_level(scores: Dict[str, int], elevated_threshold: int) -> int:
    elevated = sum(1 for value in scores.values() if value >= elevated_threshold)
    if elevated >= 3:
        return 3
    if elevated >= 2:
        return 2
    if elevated >= 1:
        return 1
    return 0


def summarize(snapshot: Dict) -> str:
    level = snapshot["alert_level"]
    scores = snapshot["scores"]
    brent = snapshot["energy_details"].get("latest_brent", 0)
    wc = snapshot["energy_details"].get("weekly_change", 0) * 100
    return (
        f"Alert level {level}. Energy score={scores['energy_stress_score']} (Brent ${brent:.2f}, 1w {wc:.1f}%). "
        f"Shipping score={scores['shipping_disruption_score']} and geopolitical score={scores['geopolitical_escalation_score']}."
    )
