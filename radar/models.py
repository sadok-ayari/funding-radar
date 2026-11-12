"""Models shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class Opportunity:
    """One funding call, normalised out of a source."""

    source: str
    source_tier: int
    title: str
    url: str
    published: Optional[str] = None      # ISO date, UTC
    deadline: Optional[str] = None       # ISO date, UTC
    amount: Optional[float] = None       # headline grant value, in `currency`
    currency: Optional[str] = None
    summary: str = ""
    tags: List[str] = field(default_factory=list)
    funder: Optional[str] = None
    country: Optional[str] = None
    raw_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SourceRun:
    """What happened when one source was polled."""

    name: str
    ok: bool
    count: int = 0
    error: Optional[str] = None
    fetched_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Score:
    """A deterministic, auditable screen result."""

    total: int = 0
    verdict: str = "exclude"                       # pursue | watch | exclude
    reasons: List[str] = field(default_factory=list)
    components: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
