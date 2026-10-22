"""Persistenter Zustand (eine JSON-Datei).

In GitHub Actions liegt die Datei auf dem Branch `state` (siehe Workflow).
Lokal standardmäßig unter state/state.json.

Aufbau:
{
  "version": 1,
  "sources": {"<source_id>": {"seeded": bool, "last_discovery": iso, "blocked_until": iso,
                               "fail_count": int, "children_lastmod": {url: lastmod}}},
  "products": {"<url>": {"source": id, "name": str, "status": str, "price": str,
                         "first_seen": iso, "last_checked": iso, "last_change": iso,
                         "lastmod": str, "pending_new": bool, "ignored": bool,
                         "disallowed": bool, "force_check": bool}}
}
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

VERSION = 1


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def is_due(last: str | None, every_minutes: float, now: datetime) -> bool:
    last_dt = parse_iso(last)
    # 1 Minute Toleranz, weil GitHub-Cron-Läufe leicht schwanken
    return last_dt is None or now - last_dt >= timedelta(minutes=every_minutes) - timedelta(minutes=1)


class State:
    def __init__(self, data: dict | None = None):
        data = data or {}
        self.data = {
            "version": VERSION,
            "sources": data.get("sources", {}),
            "products": data.get("products", {}),
        }

    @classmethod
    def load(cls, path: str) -> "State":
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return cls()
        with open(path, encoding="utf-8") as fh:
            return cls(json.load(fh))

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=1, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)

    def source(self, source_id: str) -> dict:
        return self.data["sources"].setdefault(source_id, {})

    @property
    def products(self) -> dict:
        return self.data["products"]

    def products_of(self, source_id: str) -> dict:
        return {u: p for u, p in self.products.items() if p.get("source") == source_id}
