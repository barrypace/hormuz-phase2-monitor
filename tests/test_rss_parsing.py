import unittest
from unittest.mock import patch

from data.fetch_data import _parse_rss_or_atom, fetch_rss_feed_status, keyword_mentions


RSS_SAMPLE = """<?xml version='1.0'?>
<rss version='2.0'><channel>
<item><title>Tanker rerouting near Hormuz</title><link>https://example.com/1</link><pubDate>today</pubDate><description>Shipping disruption expected</description></item>
<item><title>Unrelated</title><link>https://example.com/2</link><pubDate>today</pubDate><description>Other news</description></item>
</channel></rss>
"""


class RSSParsingTest(unittest.TestCase):
    def test_rss_parsing_and_keyword_filtering(self):
        articles = _parse_rss_or_atom(RSS_SAMPLE)
        self.assertEqual(len(articles), 2)
        matches = keyword_mentions(articles, ["hormuz", "shipping disruption"])
        self.assertEqual(len(matches), 1)
        self.assertIn("Tanker", matches[0].title)

    @patch("data.fetch_data.HTTPClient.get_text", return_value=RSS_SAMPLE)
    def test_feed_status_success(self, _mock_get_text):
        articles, status = fetch_rss_feed_status("https://example.com/rss")
        self.assertTrue(status.success)
        self.assertEqual(status.article_count, 2)
        self.assertEqual(len(articles), 2)

    @patch("data.fetch_data.HTTPClient.get_text", side_effect=RuntimeError("boom"))
    def test_feed_status_failure(self, _mock_get_text):
        articles, status = fetch_rss_feed_status("https://example.com/rss")
        self.assertFalse(status.success)
        self.assertEqual(status.article_count, 0)
        self.assertIn("boom", status.error)
        self.assertEqual(articles, [])


if __name__ == "__main__":
    unittest.main()
