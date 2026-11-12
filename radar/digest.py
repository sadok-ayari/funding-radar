"""Markdown digest. Facts only: what was found, why it scored, where it came from."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .models import Opportunity, Score, SourceRun
from .textutil import days_between


def _money(opp: Opportunity) -> str:
    if opp.amount is None:
        return "not stated"
    currency = opp.currency or ""
    return f"{currency} {opp.amount:,.0f}".strip()


def _deadline(opp: Opportunity, now_iso: str) -> str:
    if not opp.deadline:
        return "not stated — verify"
    days = days_between(opp.deadline, now_iso)
    if days is None:
        return opp.deadline
    return f"{opp.deadline} ({days} days)"


def _entry(opp: Opportunity, score: Score, now_iso: str) -> str:
    lines = [f"### {opp.title}"]
    lines.append(f"- **Source:** {opp.source} (tier {opp.source_tier})")
    lines.append(f"- **Value:** {_money(opp)}")
    lines.append(f"- **Deadline:** {_deadline(opp, now_iso)}")
    if opp.funder:
        lines.append(f"- **Funder:** {opp.funder}")
    if opp.tags:
        lines.append(f"- **Tags:** {', '.join(opp.tags[:6])}")
    lines.append(f"- **Score {score.total} — {score.verdict}:** " + " · ".join(score.reasons))
    lines.append(f"- **Link:** {opp.url}")
    return "\n".join(lines)


def render(
    scored: Sequence[Tuple[Opportunity, Score]],
    sources: Sequence[SourceRun],
    now_iso: str,
    *,
    seen_count: int = 0,
    title: str = "Funding radar",
) -> str:
    pursue = [(o, s) for o, s in scored if s.verdict == "pursue"]
    watch = [(o, s) for o, s in scored if s.verdict == "watch"]
    excluded = [(o, s) for o, s in scored if s.verdict == "exclude"]
    failed = [s for s in sources if not s.ok]

    out: List[str] = []
    out.append(f"# {title} — {now_iso}")
    out.append("")
    out.append(
        f"**{len(scored)} new call(s): {len(pursue)} pursue · {len(watch)} watch · "
        f"{len(excluded)} not a fit.** {len(sources)} source(s) polled"
        + (f", {seen_count} already seen." if seen_count else ".")
    )

    if failed:
        out.append("")
        out.append("## Sources that failed")
        out.append("")
        for run in failed:
            out.append(f"- **{run.name}** — {run.error}")
        out.append("")
        out.append("*A failed source is reported, never silently dropped. The digest below is incomplete.*")

    for heading, group in (("Pursue", pursue), ("Watch", watch)):
        out.append("")
        out.append(f"## {heading} ({len(group)})")
        out.append("")
        if not group:
            out.append("_Nothing this run._")
            continue
        for opp, score in group:
            out.append(_entry(opp, score, now_iso))
            out.append("")

    if excluded:
        out.append(f"## Not a fit ({len(excluded)})")
        out.append("")
        for opp, score in excluded:
            reason = score.reasons[0] if score.reasons else "below threshold"
            out.append(f"- {opp.title} — {reason} ({opp.source})")
        out.append("")

    out.append("---")
    out.append("")
    out.append(
        "Scores are rule-based and reproducible: read the reasons line and disagree with a "
        "specific rule, not a black box. Amounts and deadlines marked *not stated* were absent "
        "from the listing and need verification at source."
    )
    return "\n".join(out).strip() + "\n"
