"""robots.txt-Parser nach RFC 9309 (inkl. Wildcards `*` und `$`).

Pythons urllib.robotparser versteht keine Wildcards (z. B. `Disallow: /de/search/*`
oder `Disallow: /*?*`) und würde solche Pfade fälschlich erlauben. Deshalb eigener Parser.

Regeln:
- Es gilt die Gruppe, deren User-agent-Token im Namen unseres Agents vorkommt
  (längster Treffer); sonst die Gruppe `*`; sonst alles erlaubt.
- Innerhalb der Gruppe gewinnt die längste passende Regel; bei Gleichstand `Allow`.
- `Crawl-delay` wird zusätzlich ausgewertet (nicht im RFC, aber höflich).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote, unquote, urlsplit


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[tuple[bool, str]] = field(default_factory=list)  # (allow, pattern)
    crawl_delay: float | None = None


def _normalize_path(path: str) -> str:
    # Prozent-Kodierung vereinheitlichen, damit /pok%C3%A9mon und /pokémon gleich sind
    return quote(unquote(path), safe="/?=&*$%:@!,;+-._~")


def _pattern_to_regex(pattern: str) -> re.Pattern:
    anchored = pattern.endswith("$")
    if anchored:
        pattern = pattern[:-1]
    rx = "".join(".*" if ch == "*" else re.escape(ch) for ch in _normalize_path(pattern))
    return re.compile(rx + ("$" if anchored else ""))


class RobotsTxt:
    def __init__(self, text: str = ""):
        self.groups: list[_Group] = []
        self._parse(text)

    @classmethod
    def allow_all(cls) -> "RobotsTxt":
        return cls("")

    @classmethod
    def disallow_all(cls) -> "RobotsTxt":
        return cls("User-agent: *\nDisallow: /\n")

    def _parse(self, text: str) -> None:
        current: _Group | None = None
        last_was_agent = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key, value = key.strip().lower(), value.strip()
            if key == "user-agent":
                if current is None or not last_was_agent:
                    current = _Group()
                    self.groups.append(current)
                current.agents.append(value.lower())
                last_was_agent = True
                continue
            last_was_agent = False
            if current is None:
                continue
            if key in ("allow", "disallow"):
                if value == "" and key == "disallow":
                    continue  # leeres Disallow = alles erlaubt
                current.rules.append((key == "allow", value))
            elif key == "crawl-delay":
                try:
                    current.crawl_delay = float(value)
                except ValueError:
                    pass

    def _groups_for(self, agent: str) -> list[_Group]:
        # Produkt-Token = Teil vor "/" (z. B. "tcg-stock-monitor/1.0" -> "tcg-stock-monitor"),
        # Vergleich exakt und ohne Groß-/Kleinschreibung (RFC 9309).
        token = agent.split("/", 1)[0].strip().lower()
        exact = [g for g in self.groups if token in g.agents]
        if exact:
            return exact
        return [g for g in self.groups if "*" in g.agents]

    def can_fetch(self, agent: str, url: str) -> bool:
        parts = urlsplit(url)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        if path == "/robots.txt":
            return True
        path = _normalize_path(path)
        best: tuple[int, bool] | None = None  # (Länge, allow)
        for g in self._groups_for(agent):
            for allow, pattern in g.rules:
                if _pattern_to_regex(pattern).match(path):
                    length = len(pattern)
                    if best is None or length > best[0] or (length == best[0] and allow):
                        best = (length, allow)
        return True if best is None else best[1]

    def crawl_delay(self, agent: str) -> float | None:
        delays = [g.crawl_delay for g in self._groups_for(agent) if g.crawl_delay is not None]
        return max(delays) if delays else None
