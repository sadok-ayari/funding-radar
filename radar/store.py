"""Seen-list and run history in SQLite.

The seen-list is what stops the same call reappearing every week. It is keyed on
the de-duplication key, so a re-titled listing still counts as the same call.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from .dedupe import dedupe_key
from .models import Opportunity, SourceRun

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    key        TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    url        TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    total      INTEGER NOT NULL,
    new_items  INTEGER NOT NULL,
    sources    TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str = "radar.db"):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def mark_seen(self, items: List[Opportunity], now_iso: str) -> None:
        stamp = now_iso or datetime.now(timezone.utc).date().isoformat()
        for opp in items:
            self.conn.execute(
                "INSERT INTO seen(key, title, url, first_seen, last_seen) VALUES (?,?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET last_seen=excluded.last_seen",
                (dedupe_key(opp), opp.title, opp.url, stamp, stamp),
            )
        self.conn.commit()

    def is_seen(self, opp: Opportunity) -> bool:
        row = self.conn.execute("SELECT 1 FROM seen WHERE key = ?", (dedupe_key(opp),)).fetchone()
        return row is not None

    def split_new(self, items: List[Opportunity]) -> Tuple[List[Opportunity], List[Opportunity]]:
        new, seen = [], []
        for opp in items:
            (seen if self.is_seen(opp) else new).append(opp)
        return new, seen

    def record_run(self, started_at: str, total: int, new_items: int, runs: List[SourceRun]) -> None:
        import json
        self.conn.execute(
            "INSERT INTO runs(started_at, total, new_items, sources) VALUES (?,?,?,?)",
            (started_at, total, new_items, json.dumps([r.to_dict() for r in runs])),
        )
        self.conn.commit()

    def last_run(self) -> Optional[dict]:
        import json
        row = self.conn.execute(
            "SELECT started_at, total, new_items, sources FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return {"started_at": row[0], "total": row[1], "new_items": row[2], "sources": json.loads(row[3])}
