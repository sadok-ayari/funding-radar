import unittest

from radar.models import Opportunity
from radar.screen import screen

NOW = "2026-11-12"

PROFILE = {
    "rules": {
        "countries": [],
        "themes": ["climate", "resilience", "biodiversity", "water"],
        "exclude_keywords": ["military"],
        "min_amount": 50000,
        "max_amount": 5000000,
        "deadline_window_days": 60,
        "urgent_days": 14,
        "require_theme": True,
    },
    "weights": {
        "theme": 40, "tier1": 15, "tier2": 10, "tier3": 5,
        "value_in_band": 20, "value_unknown": 5,
        "deadline_in_window": 25, "deadline_far": 5, "deadline_unknown": 5,
    },
    "thresholds": {"pursue": 60, "watch": 40},
}


def opp(**kwargs):
    base = dict(source="feed", source_tier=2, title="Call", url="https://example.org/x", summary="")
    base.update(kwargs)
    return Opportunity(**base)


class ScreenTests(unittest.TestCase):
    def test_strong_match_pursues(self):
        item = opp(title="Coastal resilience and climate adaptation grants",
                   amount=250000, deadline="2026-12-10")
        score = screen(item, PROFILE, NOW)
        self.assertEqual(score.verdict, "pursue")
        self.assertGreaterEqual(score.total, 60)
        self.assertTrue(any(r.startswith("theme:") for r in score.reasons))

    def test_no_theme_is_excluded_when_required(self):
        item = opp(title="Hospital equipment framework", amount=250000, deadline="2026-12-10")
        score = screen(item, PROFILE, NOW)
        self.assertEqual(score.verdict, "exclude")
        self.assertEqual(score.total, 0)
        self.assertIn("theme: no profile keyword found", score.reasons)

    def test_theme_optional_when_the_profile_says_so(self):
        profile = {"rules": dict(PROFILE["rules"], require_theme=False),
                   "weights": PROFILE["weights"], "thresholds": PROFILE["thresholds"]}
        item = opp(title="Hospital equipment framework", amount=250000, deadline="2026-12-10")
        score = screen(item, profile, NOW)
        self.assertNotEqual(score.verdict, "exclude")

    def test_expired_deadline_is_excluded(self):
        item = opp(title="Climate grants", amount=250000, deadline="2026-11-01")
        score = screen(item, PROFILE, NOW)
        self.assertEqual(score.verdict, "exclude")
        self.assertIn("has passed", " ".join(score.reasons))

    def test_geography_gate(self):
        profile = {"rules": dict(PROFILE["rules"], countries=["Kenya"]),
                   "weights": PROFILE["weights"], "thresholds": PROFILE["thresholds"]}
        item = opp(title="Climate grants", country="Peru", amount=250000, deadline="2026-12-10")
        score = screen(item, profile, NOW)
        self.assertEqual(score.verdict, "exclude")
        self.assertTrue(any("geography" in r for r in score.reasons))

    def test_excluded_keyword_gate(self):
        item = opp(title="Climate resilience for military bases", amount=250000, deadline="2026-12-10")
        score = screen(item, PROFILE, NOW)
        self.assertEqual(score.verdict, "exclude")
        self.assertIn("mentions military", " ".join(score.reasons))

    def test_value_below_floor_scores_zero_component_but_can_still_watch(self):
        item = opp(title="Climate micro-grants", amount=5000, deadline="2026-12-10")
        score = screen(item, PROFILE, NOW)
        self.assertEqual(score.components["value"], 0)
        self.assertIn("below floor", " ".join(score.reasons))

    def test_unknown_value_and_deadline_are_flagged(self):
        item = opp(title="Climate and water programme")
        score = screen(item, PROFILE, NOW)
        self.assertIn("not stated", " ".join(score.reasons))
        self.assertEqual(score.components["deadline"], 5)

    def test_scoring_is_stable(self):
        item = opp(title="Climate resilience grants", amount=250000, deadline="2026-12-10")
        self.assertEqual(screen(item, PROFILE, NOW).to_dict(), screen(item, PROFILE, NOW).to_dict())


if __name__ == "__main__":
    unittest.main()
