import unittest

from radar.dedupe import collapse, dedupe_key, normalise_title, similarity
from radar.models import Opportunity


def opp(title, url, source="feed", tier=2, published=None, deadline=None, amount=None):
    return Opportunity(
        source=source, source_tier=tier, title=title, url=url,
        published=published, deadline=deadline, amount=amount,
    )


class DedupeTests(unittest.TestCase):
    def test_stopwords_are_dropped_from_the_key(self):
        self.assertEqual(normalise_title("Call for Proposals: Coastal Resilience"),
                         normalise_title("Coastal Resilience Proposal"))

    def test_identical_listing_from_two_sources_collapses(self):
        items = [
            opp("Call for Proposals: Coastal Resilience", "https://example.org/a", source="feed", tier=2),
            opp("Call for Proposals: Coastal Resilience", "https://aggregator.net/b", source="agg", tier=3),
        ]
        kept, dropped = collapse(items)
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(dropped), 1)
        # The better-tier source survives.
        self.assertEqual(kept[0].source, "feed")

    def test_near_duplicates_collapse(self):
        items = [
            opp("Green Cities Challenge 2027 implementation grants", "https://example.org/gc"),
            opp("Green Cities Challenge 2027 — Implementation Grants", "https://other.net/gc"),
        ]
        kept, dropped = collapse(items)
        self.assertEqual(len(kept), 1)
        self.assertEqual(similarity(normalise_title(items[0].title), normalise_title(items[1].title)) > 0.87, True)

    def test_distinct_calls_are_kept(self):
        items = [
            opp("Water Reuse Demonstration Fund", "https://example.org/w"),
            opp("Coastal Resilience in Small Island States", "https://example.org/c"),
        ]
        kept, _ = collapse(items)
        self.assertEqual(len(kept), 2)

    def test_key_includes_the_host(self):
        self.assertNotEqual(dedupe_key(opp("Same title", "https://a.org/x")),
                            dedupe_key(opp("Same title", "https://b.org/x")))

    def test_output_is_ordered_by_deadline(self):
        items = [
            opp("B call", "https://example.org/b", deadline="2026-12-01"),
            opp("A call", "https://example.org/a", deadline="2026-11-20"),
        ]
        kept, _ = collapse(items)
        self.assertEqual([k.deadline for k in kept], ["2026-11-20", "2026-12-01"])


if __name__ == "__main__":
    unittest.main()
