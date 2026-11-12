import json
import os
import tempfile
import unittest
from unittest import mock

from radar import pipeline
from radar.models import Opportunity

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROFILE = {
    "title": "Test radar",
    "rules": {
        "countries": [], "themes": ["climate", "resilience", "water"],
        "exclude_keywords": ["military"], "min_amount": 50000, "max_amount": 5000000,
        "deadline_window_days": 60, "urgent_days": 14, "require_theme": True,
    },
    "weights": {"theme": 40, "tier1": 15, "tier2": 10, "tier3": 5,
                "value_in_band": 20, "value_unknown": 5,
                "deadline_in_window": 25, "deadline_far": 5, "deadline_unknown": 5},
    "thresholds": {"pursue": 60, "watch": 40},
}


def item(title, url, source="stub", tier=2, amount=None, deadline=None):
    return Opportunity(source=source, source_tier=tier, title=title, url=url,
                       amount=amount, currency="USD" if amount else None, deadline=deadline)


class StubAdapter:
    def __init__(self, items=None, error=None):
        self.items = items or []
        self.error = error

    def fetch(self, **kwargs):
        if self.error:
            raise RuntimeError(self.error)
        return self.items


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.config = os.path.join(self.dir, "config")
        os.makedirs(self.config)
        with open(os.path.join(self.config, "profile.json"), "w", encoding="utf-8") as handle:
            json.dump(PROFILE, handle)
        with open(os.path.join(self.config, "sources.json"), "w", encoding="utf-8") as handle:
            json.dump({"sources": [
                {"name": "a", "type": "rss", "url": "https://a.example/feed", "tier": 2, "enabled": True},
                {"name": "b", "type": "rss", "url": "https://b.example/feed", "tier": 3, "enabled": True},
            ]}, handle)
        self.out = os.path.join(self.dir, "out")
        self.db = os.path.join(self.dir, "radar.db")

    def tearDown(self):
        self.tmp.cleanup()

    def run_pipeline(self, adapters, **kwargs):
        with mock.patch("radar.adapters.build", side_effect=adapters):
            return pipeline.run(config_dir=self.config, out_dir=self.out, now="2026-11-12",
                                db_path=self.db, cache_dir=None, **kwargs)

    def test_end_to_end_writes_digest_and_items(self):
        summary = self.run_pipeline([
            StubAdapter([item("Climate resilience grants", "https://a.example/1", amount=250000, deadline="2026-12-10")]),
            StubAdapter([item("Hospital equipment", "https://b.example/2", amount=900000, deadline="2026-12-01")]),
        ])
        self.assertEqual(summary["scored"], 2)
        self.assertEqual(summary["new"], 2)
        self.assertEqual(summary["pursue"], 1)
        self.assertEqual(summary["excluded"], 1)
        with open(summary["digest"], encoding="utf-8") as handle:
            markdown = handle.read()
        self.assertIn("# Test radar — 2026-11-12", markdown)
        self.assertIn("Climate resilience grants", markdown)
        self.assertIn("## Not a fit (1)", markdown)
        with open(summary["items"], encoding="utf-8") as handle:
            payload = json.load(handle)
        self.assertEqual(len(payload["items"]), 2)
        self.assertIn("score", payload["items"][0])

    def test_second_run_reports_nothing_new(self):
        items = [item("Climate resilience grants", "https://a.example/1", amount=250000, deadline="2026-12-10")]
        self.run_pipeline([StubAdapter(items), StubAdapter([])])
        second = self.run_pipeline([StubAdapter(items), StubAdapter([])])
        self.assertEqual(second["new"], 0)
        self.assertEqual(second["seen"], 1)

    def test_include_seen_reports_again(self):
        items = [item("Climate resilience grants", "https://a.example/1", amount=250000, deadline="2026-12-10")]
        self.run_pipeline([StubAdapter(items), StubAdapter([])])
        second = self.run_pipeline([StubAdapter(items), StubAdapter([])], include_seen=True)
        self.assertEqual(second["new"], 1)

    def test_failed_source_is_reported_not_dropped(self):
        summary = self.run_pipeline([
            StubAdapter([item("Water reuse fund", "https://a.example/1", amount=120000, deadline="2026-12-05")]),
            StubAdapter(error="connection reset"),
        ])
        self.assertEqual(summary["failed_sources"], ["b"])
        with open(summary["digest"], encoding="utf-8") as handle:
            markdown = handle.read()
        self.assertIn("## Sources that failed", markdown)
        self.assertIn("connection reset", markdown)

    def test_cross_source_duplicates_collapse(self):
        summary = self.run_pipeline([
            StubAdapter([item("Climate resilience grants 2027", "https://a.example/1", source="a", tier=2,
                             amount=250000, deadline="2026-12-10")]),
            StubAdapter([item("Climate resilience grants 2027", "https://b.example/1", source="b", tier=3)]),
        ])
        self.assertEqual(summary["raw"], 2)
        self.assertEqual(summary["duplicates"], 1)
        self.assertEqual(summary["scored"], 1)

    def test_dry_run_does_not_write_the_seen_list(self):
        items = [item("Climate resilience grants", "https://a.example/1", amount=250000, deadline="2026-12-10")]
        self.run_pipeline([StubAdapter(items), StubAdapter([])], mark_seen=False)
        second = self.run_pipeline([StubAdapter(items), StubAdapter([])])
        self.assertEqual(second["new"], 1)


class ShippedConfigTests(unittest.TestCase):
    def test_shipped_config_is_well_formed(self):
        with open(os.path.join(REPO, "config", "sources.json"), encoding="utf-8") as handle:
            sources = json.load(handle)["sources"]
        with open(os.path.join(REPO, "config", "profile.json"), encoding="utf-8") as handle:
            profile = json.load(handle)
        self.assertTrue(sources)
        for source in sources:
            self.assertIn("type", source)
            self.assertIn("url", source)
            self.assertIn(source["type"], {"rss", "ted", "html_list"})
        for key in ("themes", "min_amount", "max_amount", "deadline_window_days"):
            self.assertIn(key, profile["rules"])
        self.assertEqual(sum(profile["weights"].values()) > 0, True)


if __name__ == "__main__":
    unittest.main()
