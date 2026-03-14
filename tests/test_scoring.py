import unittest

from analysis.scoring import compute_alert_level, compute_energy_stress


class ScoringTest(unittest.TestCase):
    def test_energy_threshold_detection(self):
        observations = [
            {"value": "90"},
            {"value": "95"},
            {"value": "100"},
            {"value": "105"},
            {"value": "130"},
            {"value": "140"},
        ]
        thresholds = {
            "brent_price_alert": 120,
            "weekly_change_alert": 0.15,
            "sustained_trend_days": 3,
        }
        signals = compute_energy_stress(observations, thresholds)
        self.assertTrue(signals.indicators["brent_price_alert"])
        self.assertTrue(signals.indicators["weekly_change_alert"])
        self.assertTrue(signals.indicators["sustained_uptrend"])
        self.assertEqual(signals.score, 3)

    def test_alert_level_changes(self):
        scores = {
            "energy_stress_score": 2,
            "shipping_disruption_score": 2,
            "geopolitical_escalation_score": 1,
        }
        self.assertEqual(compute_alert_level(scores, elevated_threshold=2), 2)

        scores["geopolitical_escalation_score"] = 2
        self.assertEqual(compute_alert_level(scores, elevated_threshold=2), 3)


if __name__ == "__main__":
    unittest.main()
