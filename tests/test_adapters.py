import os
import unittest

from radar import http
from radar.adapters import HtmlListAdapter, RSSAdapter, TEDAdapter, build

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def read(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as handle:
        return handle.read()


class RSSAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = RSSAdapter({"name": "feed", "type": "rss", "url": "https://example.org/feed", "tier": 2})

    def test_parses_items_with_amount_and_deadline(self):
        items = self.adapter.parse(read("feed.xml"))
        self.assertEqual(len(items), 3)
        first = items[0]
        self.assertIn("Coastal Resilience", first.title)
        self.assertEqual(first.published, "2026-11-10")
        self.assertEqual(first.deadline, "2026-12-15")
        self.assertEqual(first.amount, 500000.0)
        self.assertEqual(first.currency, "USD")
        self.assertEqual(first.source_tier, 2)
        self.assertIn("Climate", first.tags)

    def test_malformed_feed_raises_fetch_error(self):
        with self.assertRaises(http.FetchError):
            self.adapter.parse("<rss><channel><item>unclosed")

    def test_offset_amount_on_second_item(self):
        items = self.adapter.parse(read("feed.xml"))
        self.assertEqual(items[1].amount, 1200000.0)
        self.assertEqual(items[1].currency, "EUR")


class TEDAdapterTests(unittest.TestCase):
    def test_maps_fields_and_takes_the_largest_lot(self):
        adapter = TEDAdapter({"name": "ted", "type": "ted", "tier": 3})
        items = adapter.parse(read("ted.json"))
        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertEqual(first.raw_id, "700001-2026")
        self.assertIn("Environmental monitoring", first.title)
        self.assertEqual(first.country, "NOR")
        self.assertEqual(first.funder, "Example Environment Agency")
        self.assertEqual(first.amount, 450000.0)
        self.assertEqual(first.currency, "EUR")
        self.assertEqual(first.published, "2026-11-09")

    def test_cpv_filter_drops_unrelated_procurement(self):
        adapter = TEDAdapter({"name": "ted", "type": "ted", "tier": 3, "cpv_prefixes": ["907"]})
        items = adapter.parse(read("ted.json"))
        self.assertEqual([i.raw_id for i in items], ["700001-2026"])

    def test_error_payload_is_reported(self):
        adapter = TEDAdapter({"name": "ted", "type": "ted", "tier": 3})
        with self.assertRaises(http.FetchError):
            adapter.parse('{"message": "QUERY_INVALID_FIELD_FORMAT"}')


class HtmlListAdapterTests(unittest.TestCase):
    def test_matches_only_the_configured_pattern(self):
        adapter = HtmlListAdapter({
            "name": "list", "type": "html_list", "url": "https://example.org/calls",
            "tier": 1,
            "link_pattern": r'<a[^>]+href="(?P<href>/calls/[^"]+)"[^>]*>(?P<text>[^<]{10,200})</a>',
        })
        items = adapter.parse(read("list.html"))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].url, "https://example.org/calls/green-cities-2027")
        self.assertTrue(all("/calls/" in item.url for item in items))

    def test_missing_pattern_is_an_error(self):
        adapter = HtmlListAdapter({"name": "list", "type": "html_list", "url": "https://example.org"})
        with self.assertRaises(http.FetchError):
            adapter.parse("<html></html>")


class FactoryTests(unittest.TestCase):
    def test_unknown_type_raises(self):
        with self.assertRaises(ValueError):
            build({"name": "x", "type": "carrier-pigeon"})


if __name__ == "__main__":
    unittest.main()
