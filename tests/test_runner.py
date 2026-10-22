"""End-to-End-Tests eines Laufs mit Fake-Shop (kein Netzwerk)."""
import unittest
from datetime import timedelta

from monitor.config import Source, load_settings
from monitor.fetcher import PoliteClient
from monitor.matching import Matcher
from monitor.notify import AVAILABLE, BLOCKED, NEW_LISTING
from monitor.runner import Runner
from monitor.state import State, utcnow

from tests.helpers import FakeSession, fixture, no_sleep

BASE = "https://shop.test"
INDEX = BASE + "/de/sitemap_index.xml"
CHILD = BASE + "/de/sitemap/Product-0.xml"
TTB = BASE + "/de/spielzeug-pokemon-karmesin-purpur-top-trainer-box/p/0196214100001"
NEW = BASE + "/de/spielzeug-pokemon-mega-entwicklung-booster-display/p/0196214100009"

SRC = Source("shop", "Testshop", "sitemap", {
    "id": "shop", "type": "sitemap", "enabled": True, "index_url": INDEX,
    "child_include": r"/Product-\d+\.xml", "every_minutes": 30,
    "product_every_minutes": 15, "max_product_checks": 10, "region_hint": "HH-Hinweis",
})

OOS = fixture("product_jsonld_oos.html").decode().replace("Pokémon Booster Display", "Pokémon Top-Trainer-Box")
INSTOCK = fixture("product_jsonld_instock.html")


def sitemap_with(*urls, lastmod="2026-10-20"):
    body = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    index = (f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>{CHILD}</loc>'
             f"<lastmod>{lastmod}</lastmod></sitemap></sitemapindex>")
    return index, f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'


class _Base:
    def setUp(self):
        self.state = State()
        self.now = utcnow()
        self.settings = load_settings()

    def run_once(self, routes, minutes_later=0):
        session = FakeSession(routes)
        client = PoliteClient("ua", "tcg-stock-monitor", min_delay=0, session=session, sleep=no_sleep)
        runner = Runner(self.settings, [SRC], self.state, client,
                        Matcher.from_config(self.settings["matching"]), self.now + timedelta(minutes=minutes_later))
        return runner.run(), session


class RunnerTest(_Base, unittest.TestCase):
    def test_full_flow(self):
        index, child = sitemap_with(TTB, BASE + "/de/spielzeug-pokemon-pluesch-pikachu/p/2")
        # 1) Erster Lauf = Baseline: keine Meldungen, Produkt wird erfasst
        events, _ = self.run_once({INDEX: (200, index), CHILD: (200, child), TTB: (200, OOS)})
        self.assertEqual(events, [])
        self.assertEqual(self.state.products[TTB]["status"], "unavailable")
        self.assertEqual(len(self.state.products), 1, "Plüsch darf nicht erfasst werden")

        # 2) 20 Min später: Produkt wieder lieferbar -> AVAILABLE; Sitemap unverändert -> nicht neu geladen
        events, session = self.run_once({INDEX: (200, index), CHILD: (200, child), TTB: (200, INSTOCK)}, 20)
        self.assertEqual(session.calls.count(INDEX), 0, "Discovery erst nach 30 Min fällig")
        self.assertEqual([e.kind for e in events], [AVAILABLE])
        self.assertEqual(events[0].hint, "HH-Hinweis")

        # 3) 40 Min: neue Sitemap mit neuem Display -> Meldung (neu + Status)
        index2, child2 = sitemap_with(TTB, NEW, lastmod="2026-10-21")
        events, _ = self.run_once({INDEX: (200, index2), CHILD: (200, child2), TTB: (200, INSTOCK),
                                   NEW: (200, fixture("product_jsonld_oos.html"))}, 40)
        self.assertEqual([e.kind for e in events], [NEW_LISTING])
        self.assertEqual(events[0].url, NEW)

        # 4) unverändert -> keine Meldung
        events, _ = self.run_once({INDEX: (200, index2), CHILD: (200, child2), TTB: (200, INSTOCK),
                                   NEW: (200, fixture("product_jsonld_oos.html"))}, 80)
        self.assertEqual(events, [])

    def test_unchanged_child_sitemap_skipped(self):
        index, child = sitemap_with(TTB)
        self.run_once({INDEX: (200, index), CHILD: (200, child), TTB: (200, OOS)})
        _, session = self.run_once({INDEX: (200, index), CHILD: (200, child), TTB: (200, OOS)}, 31)
        self.assertIn(INDEX, session.calls)
        self.assertNotIn(CHILD, session.calls)

    def test_block_pauses_source(self):
        events, _ = self.run_once({INDEX: (403, "Forbidden")})
        self.assertEqual([e.kind for e in events], [BLOCKED])
        self.assertIn("blocked_until", self.state.source("shop"))
        events, session = self.run_once({INDEX: (200, "")}, 60)
        self.assertEqual(events, [])
        self.assertEqual(session.calls, [], "Während der Pause keinerlei Abrufe")

    def test_robots_disallowed_product_skipped(self):
        index, child = sitemap_with(TTB)
        robots = "User-agent: *\nDisallow: /de/spielzeug-\n"
        events, session = self.run_once({BASE + "/robots.txt": (200, robots), INDEX: (200, index), CHILD: (200, child)})
        self.assertNotIn(TTB, session.calls)
        self.assertTrue(self.state.products[TTB]["disallowed"], "als gesperrt markiert, nie abgerufen")

    def test_errors_alert_once(self):
        for i in range(4):
            events, _ = self.run_once({INDEX: (500, "boom")}, i * 31)
            kinds = [e.kind for e in events]
            self.assertEqual(kinds, ["error"] if i == 2 else [])


if __name__ == "__main__":
    unittest.main()


class RobustnessTest(_Base, unittest.TestCase):
    def test_discovery_failure_still_checks_products(self):
        index, child = sitemap_with(TTB)
        self.run_once({INDEX: (200, index), CHILD: (200, child), TTB: (200, OOS)})
        events, session = self.run_once({INDEX: (500, "kaputt"), TTB: (200, INSTOCK)}, 31)
        self.assertIn(TTB, session.calls)
        self.assertEqual([e.kind for e in events], [AVAILABLE])

    def test_404_does_not_cause_false_restock(self):
        index, child = sitemap_with(TTB)
        self.run_once({INDEX: (200, index), CHILD: (200, child), TTB: (200, INSTOCK)})
        self.run_once({INDEX: (200, index), CHILD: (200, child), TTB: (404, "weg")}, 16)
        self.assertEqual(self.state.products[TTB]["status"], "available")
        events, _ = self.run_once({INDEX: (200, index), CHILD: (200, child), TTB: (200, INSTOCK)}, 32)
        self.assertEqual(events, [])

    def test_deadline_stops_work(self):
        index, child = sitemap_with(TTB)
        session = FakeSession({INDEX: (200, index), CHILD: (200, child), TTB: (200, OOS)})
        client = PoliteClient("ua", "tcg-stock-monitor", min_delay=0, session=session, sleep=no_sleep)
        settings = dict(self.settings, run={"max_seconds": 1})
        t = [0.0]
        runner = Runner(settings, [SRC], self.state, client, Matcher.from_config(settings["matching"]),
                        self.now, clock=lambda: t[0])
        t[0] = 5.0  # Budget schon vorbei
        runner.run()
        self.assertEqual(session.calls, [])


class FetcherSafetyTest(unittest.TestCase):
    def test_redirect_into_disallowed_path_not_followed(self):
        routes = {
            "https://a.test/robots.txt": (200, "User-agent: *\nDisallow: /de/search/*\n"),
            "https://a.test/p/1": (301, "", {"Location": "/de/search/x?q=1"}),
        }
        session = FakeSession(routes)
        c = PoliteClient("ua", "tcg-stock-monitor", min_delay=0, session=session, sleep=no_sleep)
        from monitor.fetcher import Disallowed
        with self.assertRaises(Disallowed):
            c.get("https://a.test/p/1")
        self.assertNotIn("https://a.test/de/search/x?q=1", session.calls)

    def test_redirect_followed_when_allowed(self):
        routes = {"https://a.test/p/1": (302, "", {"Location": "https://a.test/p/2"}), "https://a.test/p/2": (200, "ok")}
        c = PoliteClient("ua", "tcg-stock-monitor", min_delay=0, session=FakeSession(routes), sleep=no_sleep)
        r = c.get("https://a.test/p/1")
        self.assertEqual((r.url, r.text), ("https://a.test/p/2", "ok"))

    def test_bom_robots(self):
        routes = {"https://a.test/robots.txt": (200, "﻿User-agent: *\nDisallow: /x\n")}
        c = PoliteClient("ua", "tcg-stock-monitor", min_delay=0, session=FakeSession(routes), sleep=no_sleep)
        self.assertFalse(c.allowed("https://a.test/x"))

    def test_robots_fetched_once_per_run_even_on_error(self):
        session = FakeSession({"https://a.test/robots.txt": (503, "")})
        c = PoliteClient("ua", "tcg-stock-monitor", min_delay=0, session=session, sleep=no_sleep)
        from monitor.fetcher import FetchError
        for i in range(3):
            with self.assertRaises(FetchError):
                c.get(f"https://a.test/p/{i}")
        self.assertEqual(session.calls, ["https://a.test/robots.txt"])


class DiscoveryOnlyTest(_Base, unittest.TestCase):
    def test_new_listing_without_product_fetch(self):
        src = Source("shop", "Testshop", "sitemap", dict(SRC.raw, discovery_only=True))
        def run(routes, minutes_later):
            session = FakeSession(routes)
            client = PoliteClient("ua", "tcg-stock-monitor", min_delay=0, session=session, sleep=no_sleep)
            runner = Runner(self.settings, [src], self.state, client,
                            Matcher.from_config(self.settings["matching"]), self.now + timedelta(minutes=minutes_later))
            return runner.run(), session
        index, child = sitemap_with(TTB)
        events, session = run({INDEX: (200, index), CHILD: (200, child)}, 0)
        self.assertEqual(events, [], "Baseline meldet nichts")
        index2, child2 = sitemap_with(TTB, NEW, lastmod="2026-10-21")
        events, session = run({INDEX: (200, index2), CHILD: (200, child2)}, 40)
        self.assertEqual([e.kind for e in events], [NEW_LISTING])
        self.assertEqual(events[0].url, NEW)
        self.assertNotIn(NEW, session.calls, "Produktseite darf nicht abgerufen werden")
        events, _ = run({INDEX: (200, index2), CHILD: (200, child2)}, 80)
        self.assertEqual(events, [], "keine doppelte Meldung")


class RssTest(_Base, unittest.TestCase):
    FEED = "https://feed.test/rss"

    def _feed(self, *titles):
        items = "".join(f"<item><title>{t}</title><link>https://deal.test/{i}</link><guid>g-{t}</guid></item>"
                        for i, t in enumerate(titles))
        return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{items}</channel></rss>'

    def test_rss_new_matching_items_only(self):
        src = Source("feed", "Feed", "rss", {"id": "feed", "type": "rss", "urls": [self.FEED], "every_minutes": 10})
        def run(body, minutes_later):
            session = FakeSession({self.FEED: (200, body)})
            client = PoliteClient("ua", "tcg-stock-monitor", min_delay=0, session=session, sleep=no_sleep)
            return Runner(self.settings, [src], self.state, client, Matcher.from_config(self.settings["matching"]),
                          self.now + timedelta(minutes=minutes_later)).run()
        ev = run(self._feed("Pokemon Center Top Trainer Box"), 0)
        self.assertEqual(ev, [], "Baseline")
        ev = run(self._feed("Pokémon Booster Display neu", "Pokemon Center Top Trainer Box", "Pokémon Plüsch Pikachu"), 20)
        self.assertEqual([e.title for e in ev], ["Pokémon Booster Display neu"])
        self.assertEqual(ev[0].kind, "deal")
        self.assertEqual(run(self._feed("Pokémon Booster Display neu"), 40), [])
