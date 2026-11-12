"""De-duplication across sources and across runs.

Two listings of the same call are common: an aggregator picks it up, then the
funder publishes it. We collapse on a normalised title plus the registrable
host, then catch near-duplicates with a similarity ratio.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Tuple
from urllib.parse import urlparse

from .models import Opportunity

STOPWORDS = {
    "a", "an", "and", "for", "of", "the", "to", "in", "on", "call", "calls",
    "grant", "grants", "funding", "opportunity", "programme", "program", "now",
    "apply", "applications", "open", "new", "2026", "2027", "proposal", "proposals",
}


def host_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def normalise_title(title: str) -> str:
    """Lower-case content tokens, sorted, so word order cannot block a match."""
    tokens = sorted({t for t in re.split(r"[^a-z0-9]+", (title or "").lower())
                     if t and t not in STOPWORDS})
    return " ".join(tokens)


def dedupe_key(opp: Opportunity) -> str:
    return f"{normalise_title(opp.title)}|{host_of(opp.url)}"


def similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def collapse(items: Iterable[Opportunity], threshold: float = 0.87) -> Tuple[List[Opportunity], List[Tuple[Opportunity, Opportunity]]]:
    """Return (kept, dropped) where dropped pairs name the survivor."""
    # Keep the richest record first: better tier, then a stated deadline.
    ordered = sorted(items, key=lambda o: (o.source_tier, 0 if o.deadline else 1, o.title or ""))
    kept: List[Opportunity] = []
    dropped: List[Tuple[Opportunity, Opportunity]] = []
    index: Dict[str, Opportunity] = {}

    for opp in ordered:
        key = dedupe_key(opp)
        if key in index:
            dropped.append((opp, index[key]))
            continue
        normalised = normalise_title(opp.title)
        twin = next((k for k in index if similarity(normalised, k) >= threshold), None)
        if twin:
            dropped.append((opp, index[twin]))
            continue
        index[normalised] = opp
        kept.append(opp)

    kept.sort(key=lambda o: (o.deadline or "9999-12-31", -(o.amount or 0), o.title or ""))
    return kept, dropped
