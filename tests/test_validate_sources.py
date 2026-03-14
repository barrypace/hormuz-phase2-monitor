import unittest

from scripts.validate_sources import SourceResult, build_recommendations, markdown_summary


class ValidateSourcesTest(unittest.TestCase):
    def test_recommendations_split_sources(self):
        results = [
            SourceResult(
                source_name="fred_brent",
                source_group="energy",
                url="https://fred.example/brent",
                status_code=200,
                parse_success=True,
                suitable_for_production=True,
                reason="received valid observations",
            ),
            SourceResult(
                source_name="shipping_feed_1",
                source_group="shipping",
                url="https://bad.example/rss",
                status_code=503,
                parse_success=False,
                suitable_for_production=False,
                reason="non-success status code: 503",
            ),
        ]

        recs = build_recommendations(results)
        self.assertEqual(len(recs["keep_enabled"]), 1)
        self.assertEqual(len(recs["disable_or_fix"]), 1)

    def test_markdown_summary_has_required_columns(self):
        results = [
            SourceResult(
                source_name="geopolitical_feed_1",
                source_group="geopolitical",
                url="https://example.com/feed",
                status_code=200,
                parse_success=True,
                suitable_for_production=True,
                reason="parsed as RSS/Atom with entries",
            )
        ]
        recs = build_recommendations(results)
        md = markdown_summary(results, recs)

        self.assertIn("| Source | Group | URL | Status | Parse | Suitable | Reason |", md)
        self.assertIn("### Recommendations", md)
        self.assertIn("Keep enabled", md)


if __name__ == "__main__":
    unittest.main()
