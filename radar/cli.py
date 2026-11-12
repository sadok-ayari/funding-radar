"""Command line entry point.

    funding-radar run --now 2026-11-12
    funding-radar run --offline --cache .cache      # replay the last payloads
    funding-radar run --include-seen               # ignore the seen-list
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence

from . import __version__, pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="funding-radar",
        description="Poll funding sources, screen them against a profile, write a digest.",
    )
    parser.add_argument("--version", action="version", version=f"funding-radar {__version__}")
    sub = parser.add_subparsers(dest="command")

    run_cmd = sub.add_parser("run", help="poll sources and write a digest")
    run_cmd.add_argument("--config", default="config", help="directory holding sources.json and profile.json")
    run_cmd.add_argument("--out", default="out", help="output directory")
    run_cmd.add_argument("--now", default=None, help="YYYY-MM-DD; fixes the clock for reproducible runs")
    run_cmd.add_argument("--offline", action="store_true", help="use cached payloads only")
    run_cmd.add_argument("--cache", default=".cache", help="cache directory for payloads")
    run_cmd.add_argument("--db", default="radar.db", help="SQLite file holding the seen-list")
    run_cmd.add_argument("--include-seen", action="store_true", help="report calls already seen")
    run_cmd.add_argument("--dry-run", action="store_true", help="do not write to the seen-list")
    run_cmd.add_argument("--json", action="store_true", help="print the run summary as JSON")

    collect_cmd = sub.add_parser("collect", help="poll sources and cache payloads, no screening")
    collect_cmd.add_argument("--config", default="config")
    collect_cmd.add_argument("--cache", default=".cache")
    collect_cmd.add_argument("--json", action="store_true")

    sub.add_parser("sources", help="list configured sources")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "run"

    if command == "sources":
        cfg = pipeline.load_json(f"{getattr(args, 'config', 'config')}/sources.json")
        for source in cfg.get("sources", []):
            state = "on " if source.get("enabled", True) else "off"
            print(f"[{state}] {source.get('name'):<24} {source.get('type', 'rss'):<10} "
                  f"tier {source.get('tier', 3)}  {source.get('url', '')}")
        return 0

    if command == "collect":
        cfg = pipeline.load_json(f"{args.config}/sources.json").get("sources", [])
        items, runs = pipeline.collect(cfg, offline=False, cache_dir=args.cache)
        payload = {"items": len(items), "sources": [r.to_dict() for r in runs]}
        print(json.dumps(payload, indent=2) if args.json else
              "\n".join(f"{'ok  ' if r.ok else 'FAIL'} {r.name}: {r.count} item(s)"
                        + (f" — {r.error}" if r.error else "") for r in runs))
        return 0 if any(r.ok for r in runs) else 2

    summary = pipeline.run(
        config_dir=args.config,
        out_dir=args.out,
        now=args.now,
        offline=args.offline,
        cache_dir=args.cache,
        db_path=args.db,
        include_seen=args.include_seen,
        mark_seen=not args.dry_run,
    )
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"{summary['now']}: {summary['new']} new of {summary['scored']} scored "
              f"({summary['pursue']} pursue, {summary['watch']} watch)")
        if summary["failed_sources"]:
            print("failed sources: " + ", ".join(summary["failed_sources"]))
        print(f"digest: {summary['digest']}")
    return 0 if summary["failed_sources"] != summary["sources_polled"] or not summary["sources_polled"] else 2
