"""The pipeline: poll, normalise, de-duplicate, screen, digest, record."""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any, Dict, List, Optional

from . import adapters, digest
from .dedupe import collapse
from .models import Opportunity, Score, SourceRun
from .screen import screen
from .store import Store


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def collect(
    sources_cfg: List[Dict[str, Any]],
    *,
    offline: bool = False,
    cache_dir: Optional[str] = None,
) -> tuple[List[Opportunity], List[SourceRun]]:
    items: List[Opportunity] = []
    runs: List[SourceRun] = []
    for cfg in sources_cfg:
        if not cfg.get("enabled", True):
            continue
        name = cfg.get("name", cfg.get("url", "unnamed"))
        try:
            adapter = adapters.build(cfg)
            found = adapter.fetch(offline=offline, cache_dir=cache_dir)
            items.extend(found)
            runs.append(SourceRun(name=name, ok=True, count=len(found),
                                  fetched_at=date.today().isoformat()))
        except Exception as error:  # one broken source must not kill the run
            runs.append(SourceRun(name=name, ok=False, error=str(error)))
    return items, runs


def run(
    config_dir: str = "config",
    *,
    out_dir: str = "out",
    now: Optional[str] = None,
    offline: bool = False,
    cache_dir: Optional[str] = ".cache",
    db_path: str = "radar.db",
    include_seen: bool = False,
    mark_seen: bool = True,
) -> Dict[str, Any]:
    now_iso = now or date.today().isoformat()
    sources_cfg = load_json(os.path.join(config_dir, "sources.json")).get("sources", [])
    profile = load_json(os.path.join(config_dir, "profile.json"))

    raw, runs = collect(sources_cfg, offline=offline, cache_dir=cache_dir)
    kept, duplicates = collapse(raw)
    scored: List[tuple[Opportunity, Score]] = [(opp, screen(opp, profile, now_iso)) for opp in kept]

    store = Store(db_path)
    new_items, seen_items = store.split_new([opp for opp, _ in scored])
    if include_seen:
        new_items = [opp for opp, _ in scored]
    new_keys = {id(opp) for opp in new_items}
    fresh = [(opp, score) for opp, score in scored if id(opp) in new_keys]

    os.makedirs(out_dir, exist_ok=True)
    markdown = digest.render(fresh, runs, now_iso, seen_count=len(seen_items),
                             title=profile.get("title", "Funding radar"))
    digest_path = os.path.join(out_dir, "digest.md")
    with open(digest_path, "w", encoding="utf-8") as handle:
        handle.write(markdown)

    items_path = os.path.join(out_dir, "items.json")
    with open(items_path, "w", encoding="utf-8") as handle:
        json.dump({
            "generated": now_iso,
            "sources": [r.to_dict() for r in runs],
            "items": [dict(opp.to_dict(), score=score.to_dict()) for opp, score in scored],
        }, handle, indent=2)

    if mark_seen:
        store.mark_seen([opp for opp, _ in fresh], now_iso)
    summary = {
        "now": now_iso,
        "raw": len(raw),
        "duplicates": len(duplicates),
        "scored": len(scored),
        "new": len(fresh),
        "seen": len(seen_items),
        "pursue": sum(1 for _, s in fresh if s.verdict == "pursue"),
        "watch": sum(1 for _, s in fresh if s.verdict == "watch"),
        "excluded": sum(1 for _, s in fresh if s.verdict == "exclude"),
        "failed_sources": [r.name for r in runs if not r.ok],
        "sources_polled": len(runs),
        "digest": digest_path,
        "items": items_path,
    }
    store.record_run(now_iso, len(scored), len(fresh), runs)
    store.close()
    return summary
