"""Höflicher HTTP-Client mit eingebauten rechtlichen Leitplanken.

Regeln (nicht abschwächen, siehe AGENTS.md):
- Vor JEDEM Abruf wird robots.txt geprüft. Gesperrt => kein Abruf.
- Ehrlicher User-Agent, keine Browser-Tarnung, keine Proxys.
- Mindestabstand pro Host (bzw. Crawl-delay aus robots.txt).
- 401/403/429/Captcha/Bot-Challenge => `Blocked`. Der Aufrufer pausiert die
  Quelle. Es wird NICHT erneut oder anders versucht.
"""
from __future__ import annotations

import gzip
import logging
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import requests

from .robots import RobotsTxt

log = logging.getLogger(__name__)

# Typische Kennzeichen von Bot-Schutz-Seiten. Treffer => als Blockade werten.
CHALLENGE_MARKERS = (
    "captcha",
    "cf-challenge",
    "challenge-platform",
    "_incapsula_",
    "px-captcha",
    "access denied",
    "request unsuccessful",
    "pardon our interruption",
    "bot detection",
)
BLOCK_STATUS = {401, 403, 429}
MAX_BYTES = 40 * 1024 * 1024  # Schutz gegen riesige Antworten
MAX_REDIRECTS = 5


class FetchError(Exception):
    """Temporärer Fehler (Timeout, 5xx, 404 ...)."""


class Blocked(Exception):
    """Der Shop hat uns erkennbar blockiert. Quelle pausieren, nicht umgehen."""


class Disallowed(Exception):
    """robots.txt verbietet den Abruf. Nicht abrufen."""


@dataclass
class Response:
    url: str
    status: int
    text: str
    content: bytes = b""


class PoliteClient:
    def __init__(self, user_agent: str, robots_agent: str, timeout: float = 20,
                 min_delay: float = 3.0, session: requests.Session | None = None,
                 sleep=time.sleep, clock=time.monotonic):
        self.user_agent = user_agent
        self.robots_agent = robots_agent
        self.timeout = timeout
        self.min_delay = min_delay
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept-Language": "de-DE,de;q=0.9",
        })
        self._robots: dict[str, RobotsTxt] = {}
        self._last_hit: dict[str, float] = {}
        self._sleep = sleep
        self._clock = clock
        self.request_count = 0

    # ---------------- robots.txt ----------------
    def _robots_for(self, url: str) -> RobotsTxt:
        """robots.txt je Host laden (einmal pro Lauf, auch Fehlschläge werden gemerkt).

        rp.problem: None = ok | "blocked" (401/403) | "temporary" (5xx, Netzwerk)
        """
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        robots_url = origin + "/robots.txt"
        problem = None
        try:
            self._throttle(parts.netloc, self.min_delay)
            r = self.session.get(robots_url, timeout=self.timeout)
            self.request_count += 1
            if r.status_code in BLOCK_STATUS:
                # RFC 9309 würde hier alles erlauben; wir sind bewusst vorsichtiger:
                # wer uns schon robots.txt verweigert, will uns nicht.
                rp, problem = RobotsTxt.disallow_all(), "blocked"
            elif 400 <= r.status_code < 500:
                rp = RobotsTxt.allow_all()  # keine robots.txt => alles erlaubt (RFC 9309)
            elif r.status_code >= 500:
                rp, problem = RobotsTxt.disallow_all(), "temporary"
            else:
                rp = RobotsTxt(r.content.decode("utf-8-sig", errors="replace"))
        except requests.RequestException as exc:
            log.warning("robots.txt nicht lesbar (%s): %s -> kein Abruf in diesem Lauf", robots_url, exc)
            rp, problem = RobotsTxt.disallow_all(), "temporary"
        rp.problem = problem
        self._robots[origin] = rp  # gilt für den Rest dieses Laufs
        return rp

    def _check_allowed(self, url: str) -> None:
        rp = self._robots_for(url)
        if rp.problem == "blocked":
            raise Blocked(f"robots.txt verweigert (401/403): {url}")
        if rp.problem == "temporary":
            raise FetchError(f"robots.txt vorübergehend nicht verfügbar, kein Abruf: {url}")
        if not rp.can_fetch(self.robots_agent, url):
            raise Disallowed(f"robots.txt verbietet: {url}")

    def allowed(self, url: str) -> bool:
        return self._robots_for(url).can_fetch(self.robots_agent, url)

    def _delay_for(self, url: str) -> float:
        rp = self._robots_for(url)
        crawl_delay = rp.crawl_delay(self.robots_agent) or 0.0
        return max(self.min_delay, min(crawl_delay, 60.0))

    # ---------------- Drosselung ----------------
    def _throttle(self, host: str, delay: float) -> None:
        last = self._last_hit.get(host)
        if last is not None:
            wait = delay - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_hit[host] = self._clock()

    # ---------------- Abruf ----------------
    def get(self, url: str) -> Response:
        # Weiterleitungen manuell folgen, damit auch jedes Ziel gegen robots.txt
        # geprüft wird.
        for _ in range(MAX_REDIRECTS + 1):
            self._check_allowed(url)
            host = urlsplit(url).netloc
            self._throttle(host, self._delay_for(url))
            try:
                r = self.session.get(url, timeout=self.timeout, allow_redirects=False)
                content = r.content
            except requests.RequestException as exc:
                raise FetchError(f"{url}: {exc}") from exc
            finally:
                self.request_count += 1
            location = getattr(r, "headers", {}).get("Location") if 300 <= r.status_code < 400 else None
            if not location:
                break
            url = urljoin(url, location)
        else:
            raise FetchError(f"{url}: zu viele Weiterleitungen")
        if len(content) > MAX_BYTES:
            raise FetchError(f"{url}: Antwort zu groß")
        if url.endswith(".gz") or content[:2] == b"\x1f\x8b":
            try:
                content = gzip.decompress(content)
            except OSError:
                pass
        encoding = r.encoding
        if not encoding or encoding.lower() == "iso-8859-1":
            # requests rät bei text/* ohne charset ISO-8859-1; Shops liefern UTF-8
            encoding = "utf-8"
        text = content.decode(encoding, errors="replace")

        if r.status_code in BLOCK_STATUS:
            raise Blocked(f"{url}: HTTP {r.status_code}")
        if r.status_code == 503 and looks_like_challenge(text):
            raise Blocked(f"{url}: HTTP 503 Bot-Challenge")
        if r.status_code >= 400:
            raise FetchError(f"{url}: HTTP {r.status_code}")
        if looks_like_challenge(text) and len(text) < 20000:
            # kurze Seite mit Captcha-Hinweis = Challenge-Seite statt Inhalt
            raise Blocked(f"{url}: Bot-Challenge-Seite erkannt")
        return Response(url=url, status=r.status_code, text=text, content=content)


def looks_like_challenge(text: str) -> bool:
    low = text[:20000].lower()
    return any(m in low for m in CHALLENGE_MARKERS)
