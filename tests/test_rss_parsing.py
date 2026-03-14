import unittest

from data.fetch_data import _parse_rss_or_atom, keyword_mentions


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


if __name__ == "__main__":
    unittest.main()
