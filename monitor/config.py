"""Laden und Prüfen der Konfiguration (config/settings.yaml, config/sources.yaml)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT, "config")

TYPES = {"sitemap", "listing", "products", "rss"}
DEFAULTS = {
    "enabled": True,
    "every_minutes": 30,
    "product_every_minutes": 15,
    "max_product_checks": 20,
    "region_hint": "",
    "in_stock_patterns": [],
    "out_of_stock_patterns": [],
    "assume_relevant": False,
    "discovery_only": False,
    "urls": [],
}
REQUIRED = {
    "sitemap": ["index_url"],
    "listing": ["urls", "link_pattern"],
    "products": ["urls"],
    "rss": ["urls"],
}


@dataclass
class Source:
    id: str
    name: str
    type: str
    raw: dict = field(default_factory=dict)

    def __getattr__(self, item):
        # erlaubt src.every_minutes etc. mit Defaults
        raw = self.__dict__.get("raw", {})
        if item in raw:
            return raw[item]
        if item in DEFAULTS:
            return DEFAULTS[item]
        if item in ("index_url", "child_include", "link_pattern"):
            return None
        raise AttributeError(item)


def load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_settings(path: str | None = None) -> dict:
    settings = load_yaml(path or os.path.join(CONFIG_DIR, "settings.yaml"))
    contact = os.environ.get("CONTACT") or (
        "https://github.com/" + os.environ["GITHUB_REPOSITORY"] if os.environ.get("GITHUB_REPOSITORY") else "lokal"
    )
    settings["user_agent"] = settings.get("user_agent", "tcg-stock-monitor/1.0 ({contact})").format(contact=contact)
    return settings


def load_sources(path: str | None = None) -> list[Source]:
    data = load_yaml(path or os.path.join(CONFIG_DIR, "sources.yaml"))
    return [Source(id=s["id"], name=s.get("name", s["id"]), type=s["type"], raw=s)
            for s in data.get("sources", [])]


def validate(sources: list[Source]) -> list[str]:
    """Gibt eine Liste von Fehlermeldungen zurück (leer = alles ok)."""
    errors: list[str] = []
    seen: set[str] = set()
    for s in sources:
        where = f"Quelle '{s.id}'"
        if not re.fullmatch(r"[a-z0-9_-]+", s.id or ""):
            errors.append(f"{where}: id nur a-z, 0-9, _ und - erlaubt")
        if s.id in seen:
            errors.append(f"{where}: id doppelt")
        seen.add(s.id)
        if s.type not in TYPES:
            errors.append(f"{where}: type muss eins von {sorted(TYPES)} sein")
            continue
        if not s.enabled:
            continue
        for key in REQUIRED[s.type]:
            if not s.raw.get(key):
                errors.append(f"{where}: Pflichtfeld '{key}' fehlt")
        for key in ("child_include", "link_pattern"):
            if s.raw.get(key):
                try:
                    re.compile(s.raw[key])
                except re.error as exc:
                    errors.append(f"{where}: Regex '{key}' ungültig: {exc}")
        for key in ("in_stock_patterns", "out_of_stock_patterns"):
            for p in s.raw.get(key, []) or []:
                try:
                    re.compile(p)
                except re.error as exc:
                    errors.append(f"{where}: Regex in '{key}' ungültig: {p} ({exc})")
        for u in list(s.raw.get("urls", []) or []) + ([s.raw["index_url"]] if s.raw.get("index_url") else []):
            if not str(u).startswith("https://"):
                errors.append(f"{where}: URL muss mit https:// beginnen: {u}")
            if "HIER-" in str(u):
                errors.append(f"{where}: Platzhalter-URL noch nicht ersetzt: {u}")
        for key in ("every_minutes", "product_every_minutes"):
            if float(getattr(s, key)) < 5:
                errors.append(f"{where}: {key} < 5 Minuten ist zu aggressiv (Server-Last)")
        if int(s.max_product_checks) > 60:
            errors.append(f"{where}: max_product_checks > 60 pro Lauf ist zu viel")
        if "pokemoncenter.com" in str(s.raw):
            errors.append(f"{where}: Pokémon Center wird bewusst nicht automatisiert (siehe AGENTS.md)")
    return errors
