"""Eligibility and fit screening.

Every point awarded here is traceable to a rule in the profile file. There is no
model in this module on purpose: a human has to be able to read the score and
disagree with a specific line.
"""

from __future__ import annotations

import re
from typing import Dict, List

from .models import Opportunity, Score
from .textutil import days_between


def _haystack(opp: Opportunity) -> str:
    return " ".join([opp.title or "", opp.summary or "", " ".join(opp.tags or []),
                     opp.funder or "", opp.country or ""]).lower()


def _keyword_hits(text: str, keywords: List[str]) -> List[str]:
    hits = []
    for kw in keywords:
        k = kw.lower().strip()
        if not k:
            continue
        if re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", text):
            hits.append(kw)
    return hits


def screen(opp: Opportunity, profile: Dict, now_iso: str) -> Score:
    """Score one opportunity against the profile. Deterministic."""
    rules = profile.get("rules", {})
    weights = profile.get("weights", {})
    text = _haystack(opp)
    score = Score()
    reasons: List[str] = []

    # --- hard gates -------------------------------------------------------
    countries = [c.lower() for c in rules.get("countries", [])]
    if countries and opp.country and opp.country.lower() not in countries:
        score.total = 0
        score.verdict = "exclude"
        score.reasons.append(f"excluded: geography {opp.country} outside the profile")
        return score

    excluded_terms = _keyword_hits(text, rules.get("exclude_keywords", []))
    if excluded_terms:
        score.total = 0
        score.verdict = "exclude"
        score.reasons.append("excluded: mentions " + ", ".join(excluded_terms))
        return score

    days = days_between(opp.deadline, now_iso)
    if days is not None and days < 0:
        score.total = 0
        score.verdict = "exclude"
        score.reasons.append(f"excluded: deadline {opp.deadline} has passed")
        return score

    # --- weighted components ---------------------------------------------
    theme_weight = int(weights.get("theme", 40))
    hits = _keyword_hits(text, rules.get("themes", []))
    theme_points = 0
    if hits:
        theme_points = min(theme_weight, 14 + 9 * (len(hits) - 1)) if len(hits) > 1 else 18
        theme_points = min(theme_points, theme_weight)
        reasons.append(f"theme: {len(hits)} match(es) — " + ", ".join(hits[:5]))
    else:
        reasons.append("theme: no profile keyword found")
        if rules.get("require_theme", True):
            score.total = 0
            score.verdict = "exclude"
            reasons.append("excluded: nothing in the profile's themes")
            score.reasons = reasons
            return score
    score.components["theme"] = theme_points

    tier = max(1, min(3, opp.source_tier))
    tier_points = {1: int(weights.get("tier1", 15)), 2: int(weights.get("tier2", 10)),
                   3: int(weights.get("tier3", 5))}.get(tier, 5)
    score.components["source_tier"] = tier_points
    reasons.append(f"source: {opp.source} (tier {tier})")

    value_points = 0
    low = rules.get("min_amount")
    high = rules.get("max_amount")
    if opp.amount is None:
        value_points = int(weights.get("value_unknown", 5))
        reasons.append("value: not stated in the listing")
    elif low is not None and opp.amount < low:
        value_points = 0
        reasons.append(f"value: {int(opp.amount):,} below floor {int(low):,}")
    elif high is not None and opp.amount > high:
        value_points = 0
        reasons.append(f"value: {int(opp.amount):,} above ceiling {int(high):,}")
    else:
        value_points = int(weights.get("value_in_band", 20))
        reasons.append(f"value: {int(opp.amount):,} inside the band")
    score.components["value"] = value_points

    deadline_points = 0
    window = int(rules.get("deadline_window_days", 60))
    urgent = int(rules.get("urgent_days", 14))
    if days is None:
        deadline_points = int(weights.get("deadline_unknown", 5))
        reasons.append("deadline: not stated, verify before planning")
    elif days > window:
        deadline_points = int(weights.get("deadline_far", 5))
        reasons.append(f"deadline: {days} days out, beyond the {window}-day window")
    else:
        deadline_points = int(weights.get("deadline_in_window", 25))
        reasons.append(f"deadline: {days} days out" + (" — closing soon" if days <= urgent else ""))
    score.components["deadline"] = deadline_points

    total = sum(score.components.values())
    score.total = max(0, min(100, total))
    pursue = int(profile.get("thresholds", {}).get("pursue", 60))
    watch = int(profile.get("thresholds", {}).get("watch", 40))
    score.verdict = "pursue" if score.total >= pursue else ("watch" if score.total >= watch else "exclude")
    if score.verdict == "exclude":
        reasons.append(f"total {score.total} below the watch floor {watch}")
    score.reasons = reasons
    return score
