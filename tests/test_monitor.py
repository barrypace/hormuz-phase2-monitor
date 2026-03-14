import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import monitor
from data.fetch_data import Article


class FeedStatus:
    def __init__(self, feed_url, success, article_count, error):
        self.feed_url = feed_url
        self.success = success
        self.article_count = article_count
        self.error = error


class MonitorBehaviorTest(unittest.TestCase):
    def _base_config(self, tmpdir: str) -> dict:
        return {
            "fred": {"base_url": "https://fred.example", "series": {"brent": "DCOILBRENTEU", "treasury_2y": "DGS2"}},
            "rss": {
                "shipping_feeds": ["https://shipping.example/feed"],
                "geopolitical_feeds": ["https://geo.example/feed"],
                "shipping_keywords": ["hormuz"],
                "geopolitical_keywords": ["iran"],
            },
            "thresholds": {
                "brent_price_alert": 120,
                "weekly_change_alert": 0.15,
                "sustained_trend_days": 3,
                "keyword_match_alert": 1,
                "score_elevated_threshold": 2,
            },
            "operations": {
                "notification_cooldown_minutes": 60,
                "fail_on_unhealthy_sources": True,
            },
            "output": {
                "snapshot_path": str(Path(tmpdir) / "latest_snapshot.json"),
                "previous_snapshot_path": str(Path(tmpdir) / "previous_snapshot.json"),
            },
        }

    def test_snapshot_has_confidence_and_critical_checks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._base_config(tmpdir)
            with patch("monitor.load_config", return_value=cfg), patch(
                "monitor.fetch_rss_feed_status"
            ) as mock_feed_status:
                mock_feed_status.side_effect = [
                    ([], FeedStatus("https://shipping.example/feed", True, 0, "")),
                    ([], FeedStatus("https://geo.example/feed", False, 0, "timeout")),
                ]

                os.environ.pop("FRED_API_KEY", None)
                snapshot = monitor.run()

                self.assertEqual(snapshot["confidence"], "LOW")
                self.assertFalse(snapshot["data_health"]["critical_sources_healthy"])
                self.assertFalse(snapshot["data_health"]["critical_checks"]["fred_energy_available"])
                self.assertFalse(snapshot["data_health"]["critical_checks"]["geopolitical_source_available"])

    def test_healthy_critical_sources_yield_high_confidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._base_config(tmpdir)
            with patch("monitor.load_config", return_value=cfg), patch(
                "monitor.fetch_rss_feed_status"
            ) as mock_feed_status, patch("monitor.fetch_fred_series", side_effect=[[{"value": "130"}], [{"value": "4.5"}]]):
                mock_feed_status.side_effect = [
                    ([], FeedStatus("https://shipping.example/feed", True, 2, "")),
                    ([], FeedStatus("https://geo.example/feed", True, 3, "")),
                ]
                os.environ["FRED_API_KEY"] = "dummy"
                snapshot = monitor.run()

                self.assertEqual(snapshot["confidence"], "HIGH")
                self.assertTrue(snapshot["data_health"]["critical_sources_healthy"])
                self.assertTrue(snapshot["data_health"]["critical_checks"]["fred_energy_available"])
                self.assertTrue(snapshot["data_health"]["critical_checks"]["shipping_source_available"])
                self.assertTrue(snapshot["data_health"]["critical_checks"]["geopolitical_source_available"])

    def test_notifies_on_alert_level_change_when_cooldown_elapsed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._base_config(tmpdir)
            previous_snapshot_path = Path(cfg["output"]["snapshot_path"])
            previous_snapshot_path.write_text(
                json.dumps({"alert_level": 0, "timestamp_utc": "2026-01-01T00:00:00+00:00"}),
                encoding="utf-8",
            )

            shipping_article = Article(
                title="Tanker warning near Hormuz",
                link="https://example.com/1",
                published="today",
                summary="hormuz disruption",
            )

            with patch("monitor.load_config", return_value=cfg), patch(
                "monitor.fetch_rss_feed_status"
            ) as mock_feed_status, patch("monitor._notify_if_configured") as mock_notify:
                mock_feed_status.side_effect = [
                    ([shipping_article], FeedStatus("https://shipping.example/feed", True, 1, "")),
                    ([], FeedStatus("https://geo.example/feed", True, 0, "")),
                ]
                os.environ.pop("FRED_API_KEY", None)
                snapshot = monitor.run()

                self.assertTrue(mock_notify.called)
                self.assertTrue(snapshot["operations"]["notification_sent"])
                self.assertEqual(snapshot["operations"]["notification_reason"], "alert_level_changed")

    def test_cooldown_suppresses_notification(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._base_config(tmpdir)
            recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
            previous_snapshot_path = Path(cfg["output"]["snapshot_path"])
            previous_snapshot_path.write_text(
                json.dumps(
                    {
                        "alert_level": 0,
                        "timestamp_utc": recent,
                        "last_notification_utc": recent,
                    }
                ),
                encoding="utf-8",
            )

            shipping_article = Article(
                title="Tanker warning near Hormuz",
                link="https://example.com/1",
                published="today",
                summary="hormuz disruption",
            )

            with patch("monitor.load_config", return_value=cfg), patch(
                "monitor.fetch_rss_feed_status"
            ) as mock_feed_status, patch("monitor._notify_if_configured") as mock_notify:
                mock_feed_status.side_effect = [
                    ([shipping_article], FeedStatus("https://shipping.example/feed", True, 1, "")),
                    ([], FeedStatus("https://geo.example/feed", True, 0, "")),
                ]
                os.environ.pop("FRED_API_KEY", None)
                snapshot = monitor.run()

                self.assertFalse(mock_notify.called)
                self.assertFalse(snapshot["operations"]["notification_sent"])
                self.assertEqual(snapshot["operations"]["notification_reason"], "cooldown_active")


if __name__ == "__main__":
    unittest.main()
