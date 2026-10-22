"""Ein Monitor-Lauf: Entdecken (Sitemap/Listing) -> Produktseiten prüfen -> Ereignisse."""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta

from . import parsing
from .config import Source
from .fetcher import Blocked, Disallowed, FetchError, PoliteClient
from .matching import Matcher
from .notify import AVAILABLE, BLOCKED, ERROR, NEW_LISTING, PREORDER, Event
from .state import State, iso, is_due, parse_iso

log = logging.getLogger(__name__)

SITEMAP_REFRESH = timedelta(hours=6)
GONE_AFTER_ERRORS = 5          # so viele Fehler in Folge -> nur noch 1x täglich prüfen
GONE_RECHECK_MINUTES = 24 * 60


class Runner:
    def __init__(self, settings: dict, sources: list[Source], state: State,
                 client: PoliteClient, matcher: Matcher, now: datetime, clock=time.monotonic):
        self.settings = settings
        self.sources = sources
        self.state = state
        self.client = client
        self.matcher = matcher
        self.now = now
        self.events: list[Event] = []
        self.block_pause = timedelta(hours=float(settings.get("http", {}).get("block_pause_hours", 24)))
        self.error_alert_after = int(settings.get("notify", {}).get("error_alert_after", 3))
        # Zeitbudget: Lauf rechtzeitig vor dem Workflow-Timeout beenden
        self._clock = clock
        budget = float(settings.get("run", {}).get("max_seconds", 420))
        self.deadline = clock() + budget if budget > 0 else None

    # ------------------------------------------------------------------ Lauf
    def run(self, only: str | None = None) -> list[Event]:
        for src in self.sources:
            if only and src.id != only:
                continue
            if not src.enabled and not only:
                continue
            self.run_source(src)
        return self.events

    def run_source(self, src: Source) -> None:
        sst = self.state.source(src.id)
        blocked_until = parse_iso(sst.get("blocked_until"))
        if blocked_until and blocked_until > self.now:
            log.info("[%s] pausiert bis %s (Blockade)", src.id, sst["blocked_until"])
            return
        if self._out_of_time():
            log.warning("[%s] übersprungen: Zeitbudget des Laufs erschöpft", src.id)
            return
        failed = False
        try:
            # 1) Entdecken – Fehler hier dürfen die Produktprüfung NICHT verhindern
            try:
                if src.type in ("sitemap", "listing"):
                    if is_due(sst.get("last_discovery"), src.every_minutes, self.now):
                        if src.type == "sitemap":
                            self.discover_sitemap(src, sst)
                        else:
                            self.discover_listing(src, sst)
                        sst["last_discovery"] = iso(self.now)
                        sst["seeded"] = True
                elif src.type == "products":
                    self.sync_watchlist(src)
            except Blocked:
                raise
            except Exception as exc:  # noqa: BLE001
                failed = True
                self._record_error(src, sst, exc)
            # 2) Bekannte Produkte prüfen
            self.check_products(src)
            if not failed:
                sst["fail_count"] = 0
                sst.pop("last_error", None)
            sst.pop("blocked_until", None)
        except Blocked as exc:
            sst["blocked_until"] = iso(self.now + self.block_pause)
            sst["block_count"] = int(sst.get("block_count", 0)) + 1
            log.warning("[%s] BLOCKIERT: %s -> pausiert bis %s", src.id, exc, sst["blocked_until"])
            self.events.append(Event(BLOCKED, src.name,
                                     f"Shop blockiert automatische Abrufe ({exc}). "
                                     f"Pausiert bis {sst['blocked_until']}. Keine Umgehung.",
                                     url=None))
        except Exception as exc:  # noqa: BLE001 – ein Shop darf den Lauf nicht abbrechen
            self._record_error(src, sst, exc)

    def _record_error(self, src: Source, sst: dict, exc: Exception) -> None:
        sst["fail_count"] = int(sst.get("fail_count", 0)) + 1
        sst["last_error"] = f"{type(exc).__name__}: {exc}"[:300]
        log.error("[%s] Fehler (%s. in Folge): %s", src.id, sst["fail_count"], exc,
                  exc_info=not isinstance(exc, (FetchError, Disallowed)))
        if sst["fail_count"] == self.error_alert_after:
            self.events.append(Event(ERROR, src.name, f"{sst['fail_count']}× in Folge fehlgeschlagen: {sst['last_error']}"))

    def _out_of_time(self) -> bool:
        return self.deadline is not None and self._clock() >= self.deadline

    # ------------------------------------------------------------- Entdecken
    def _register(self, src: Source, url: str, lastmod: str | None, seeded: bool) -> None:
        products = self.state.products
        p = products.get(url)
        if p is None:
            products[url] = {
                "source": src.id,
                "first_seen": iso(self.now),
                "status": parsing.UNKNOWN,
                "lastmod": lastmod,
                # Beim allerersten Lauf (Baseline) keine "neu"-Meldungen
                "pending_new": bool(seeded),
            }
            if seeded:
                log.info("[%s] NEU: %s", src.id, url)
        elif lastmod and p.get("lastmod") != lastmod:
            p["lastmod"] = lastmod
            p["force_check"] = True  # Shop hat die Seite geändert -> bald prüfen

    def discover_sitemap(self, src: Source, sst: dict) -> None:
        seeded = bool(sst.get("seeded"))
        resp = self.client.get(src.index_url)
        kind, entries = parsing.parse_sitemap(resp.content or resp.text.encode())
        if kind == "urlset":
            self._process_urls(src, entries, seeded)
            return
        child_rx = re.compile(src.child_include) if src.child_include else None
        children = [e for e in entries if not child_rx or child_rx.search(e.loc)]
        for child in children:
            if self._out_of_time():
                log.warning("[%s] Zeitbudget erschöpft, restliche Sitemaps im nächsten Lauf", src.id)
                raise FetchError("Zeitbudget erschöpft (Sitemaps)")
            self._fetch_child_sitemap(src, sst, child, seeded, depth=0)

    def _fetch_child_sitemap(self, src: Source, sst: dict, entry, seeded: bool, depth: int) -> None:
        known = sst.setdefault("children_lastmod", {})
        fetched = sst.setdefault("children_fetched", {})
        last_fetch = parse_iso(fetched.get(entry.loc))
        fresh = last_fetch is not None and self.now - last_fetch < SITEMAP_REFRESH
        # lastmod unverändert UND vor < 6 h geladen -> überspringen
        # (die 6 h fangen Shops ab, die nur ein Datum ohne Uhrzeit liefern)
        if entry.lastmod and known.get(entry.loc) == entry.lastmod and fresh:
            return
        r = self.client.get(entry.loc)
        kind, entries = parsing.parse_sitemap(r.content or r.text.encode())
        if kind == "index":
            if depth >= 1:
                return  # nicht tiefer als eine verschachtelte Ebene
            for sub in entries:
                self._fetch_child_sitemap(src, sst, sub, seeded, depth + 1)
        else:
            self._process_urls(src, entries, seeded)
        if entry.lastmod:
            known[entry.loc] = entry.lastmod
        fetched[entry.loc] = iso(self.now)

    def _process_urls(self, src: Source, entries, seeded: bool) -> None:
        for e in entries:
            if self.matcher.matches(e.loc):
                self._register(src, e.loc, e.lastmod, seeded)

    def discover_listing(self, src: Source, sst: dict) -> None:
        seeded = bool(sst.get("seeded"))
        for page_url in src.urls:
            resp = self.client.get(page_url)
            for link in parsing.extract_links(resp.text, resp.url, src.link_pattern):
                if src.assume_relevant or self.matcher.matches(link):
                    self._register(src, link, None, seeded)

    def sync_watchlist(self, src: Source) -> None:
        for url in src.urls:
            if url not in self.state.products:
                self._register(src, url, None, seeded=False)

    # -------------------------------------------------------- Produktprüfung
    def _due_products(self, src: Source) -> list[tuple[str, dict]]:
        due = []
        for url, p in self.state.products_of(src.id).items():
            if p.get("ignored") or p.get("disallowed"):
                continue
            interval = GONE_RECHECK_MINUTES if int(p.get("errors", 0)) >= GONE_AFTER_ERRORS else src.product_every_minutes
            if p.get("pending_new") or p.get("force_check") or is_due(p.get("last_checked"), interval, self.now):
                due.append((url, p))
        due.sort(key=lambda item: (
            not item[1].get("pending_new"),
            not item[1].get("force_check"),
            item[1].get("last_checked") or "",
        ))
        return due[: int(src.max_product_checks)]

    def check_products(self, src: Source) -> None:
        for url, p in self._due_products(src):
            if self._out_of_time():
                log.warning("[%s] Zeitbudget erschöpft, restliche Produkte im nächsten Lauf", src.id)
                return
            try:
                resp = self.client.get(url)
            except Disallowed:
                p["disallowed"] = True
                log.info("[%s] robots.txt verbietet Produktseite, ignoriere: %s", src.id, url)
                continue
            except FetchError as exc:
                p["last_checked"] = iso(self.now)
                p["errors"] = int(p.get("errors", 0)) + 1
                log.warning("[%s] Produktseite fehlgeschlagen (%sx): %s", src.id, p["errors"], exc)
                # Status NICHT ändern (sonst Fehlalarm "verfügbar", wenn die Seite zurückkommt).
                # Dauerhaft fehlerhafte Produkte dürfen die Warteschlange nicht blockieren:
                if p["errors"] >= 2:
                    p.pop("pending_new", None)
                    p.pop("force_check", None)
                continue
            # Blocked wird absichtlich nicht gefangen -> ganze Quelle pausieren
            info = parsing.parse_product(resp.text, src.in_stock_patterns, src.out_of_stock_patterns)
            self._apply(src, url, p, info)

    def _apply(self, src: Source, url: str, p: dict, info: parsing.ProductInfo) -> None:
        old = p.get("status", parsing.UNKNOWN)
        was_new = bool(p.pop("pending_new", False))
        p.pop("force_check", None)
        p.pop("errors", None)
        p["last_checked"] = iso(self.now)
        p["method"] = info.method
        if info.name:
            p["name"] = info.name[:200]
        if info.price:
            p["price"], p["currency"] = info.price, info.currency
        # Name gegenprüfen (z. B. Plüsch, der nur über die URL hereinkam)
        if info.name and (self.matcher.excluded(info.name)
                          or (src.assume_relevant and not self.matcher.has_required(info.name))):
            p["ignored"] = True
            p.pop("pending_new", None)
            log.info("[%s] ignoriert (Name passt nicht): %s", src.id, info.name)
            return
        new = info.status
        if new != parsing.UNKNOWN:
            if new != old:
                p["last_change"] = iso(self.now)
            p["status"] = new
        title = p.get("name") or url
        hint = src.region_hint or None

        def event(kind):
            self.events.append(Event(kind, src.name, title, url=url, price=p.get("price"),
                                     currency=p.get("currency"), hint=hint))

        became = new if new != old else None
        if was_new:
            # Neu entdeckt: je nach Status passende Meldung
            event(AVAILABLE if new == parsing.AVAILABLE else PREORDER if new == parsing.PREORDER else NEW_LISTING)
        elif became == parsing.AVAILABLE and old in (parsing.UNAVAILABLE, parsing.PREORDER):
            event(AVAILABLE)
        elif became == parsing.PREORDER and old == parsing.UNAVAILABLE:
            event(PREORDER)
        elif became and old == parsing.UNKNOWN:
            log.info("[%s] Baseline %s: %s", src.id, new, title)
