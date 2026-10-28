import unittest

from monitor import parsing
from monitor.config import Source, load_settings, load_sources, validate
from monitor.fetcher import Blocked, Disallowed, PoliteClient
from monitor.matching import Matcher
from monitor.notify import AVAILABLE, NEW_LISTING, Event, Notifier

from tests.helpers import FakeSession, fixture, no_sleep


def matcher():
    return Matcher.from_config(load_settings()["matching"])


class MatchingTest(unittest.TestCase):
    def test_relevant(self):
        m = matcher()
        self.assertTrue(m.matches("https://www.rossmann.de/de/spielzeug-pokemon-karmesin-purpur-top-trainer-box/p/123"))
        self.assertTrue(m.matches("Pokémon Sammelkartenspiel Booster Display"))
        self.assertTrue(m.matches("https://x.de/p/pok%C3%A9mon-tcg-blister-PPN1/"))

    def test_irrelevant(self):
        m = matcher()
        self.assertFalse(m.matches("https://www.mueller.de/p/polaroid-go-color-film-pokemon-edition-PPN3199875/"))
        self.assertFalse(m.matches("https://www.mueller.de/p/pokemon-vorlesebuch-5-minuten-PPN3232598/"))
        self.assertFalse(m.matches("Pokémon Plüsch Pikachu"))
        self.assertFalse(m.matches("Magic the Gathering Booster Display"))


class ParsingTest(unittest.TestCase):
    def test_sitemap_index(self):
        kind, entries = parsing.parse_sitemap(fixture("sitemap_index.xml"))
        self.assertEqual(kind, "index")
        self.assertEqual(entries[0].lastmod, "2026-10-20")
        self.assertIsNone(entries[1].lastmod)

    def test_sitemap_urlset(self):
        kind, entries = parsing.parse_sitemap(fixture("sitemap_products.xml"))
        self.assertEqual(kind, "urlset")
        self.assertEqual(len(entries), 3)

    def test_jsonld_instock_graph(self):
        info = parsing.parse_product(fixture("product_jsonld_instock.html").decode())
        self.assertEqual(info.status, parsing.AVAILABLE)
        self.assertEqual(info.method, "jsonld")
        self.assertEqual(info.price, "49.99")
        self.assertEqual(info.name, "Pokémon Karmesin & Purpur Top-Trainer-Box")

    def test_jsonld_oos_list(self):
        info = parsing.parse_product(fixture("product_jsonld_oos.html").decode())
        self.assertEqual(info.status, parsing.UNAVAILABLE)
        self.assertEqual(info.price, "159.9")

    def test_aggregate_preorder(self):
        info = parsing.parse_product(fixture("product_aggregate_preorder.html").decode())
        self.assertEqual(info.status, parsing.PREORDER)

    def test_meta(self):
        info = parsing.parse_product(fixture("product_meta.html").decode())
        self.assertEqual((info.status, info.method, info.name), (parsing.UNAVAILABLE, "meta", "Pokémon Tin Box"))

    def test_pattern(self):
        html = fixture("product_pattern.html").decode()
        self.assertEqual(parsing.parse_product(html).status, parsing.UNKNOWN)
        info = parsing.parse_product(html, out_of_stock_patterns=["(?i)online nicht verf(ü|ue)gbar"])
        self.assertEqual((info.status, info.method), (parsing.UNAVAILABLE, "pattern"))

    def test_listing_links(self):
        links = parsing.extract_links(fixture("listing.html").decode(), "https://www.thalia.test/kategorie/x/",
                                      r"/shop/home/artikeldetails/A\d+")
        self.assertEqual(links, ["https://www.thalia.test/shop/home/artikeldetails/A1070021854",
                                 "https://www.thalia.test/shop/home/artikeldetails/A1070021855"])


class FetcherTest(unittest.TestCase):
    def client(self, routes):
        return PoliteClient("tcg-stock-monitor/1.0 (test)", "tcg-stock-monitor", min_delay=0,
                            session=FakeSession(routes), sleep=no_sleep)

    def test_robots_disallow(self):
        c = self.client({"https://a.test/robots.txt": (200, "User-agent: *\nDisallow: /de/search/\n")})
        self.assertFalse(c.allowed("https://a.test/de/search/pokemon"))
        self.assertTrue(c.allowed("https://a.test/de/p/1"))
        with self.assertRaises(Disallowed):
            c.get("https://a.test/de/search/pokemon")
        self.assertNotIn("https://a.test/de/search/pokemon", c.session.calls)

    def test_robots_blocks_our_agent(self):
        c = self.client({"https://a.test/robots.txt": (200, "User-agent: tcg-stock-monitor\nDisallow: /\n")})
        self.assertFalse(c.allowed("https://a.test/x"))

    def test_robots_unreachable_is_conservative(self):
        c = self.client({"https://a.test/robots.txt": (500, "")})
        self.assertFalse(c.allowed("https://a.test/x"))

    def test_403_is_blocked(self):
        c = self.client({"https://a.test/p": (403, "Forbidden")})
        with self.assertRaises(Blocked):
            c.get("https://a.test/p")

    def test_challenge_is_blocked(self):
        c = self.client({"https://a.test/p": (200, fixture("challenge.html"))})
        with self.assertRaises(Blocked):
            c.get("https://a.test/p")

    def test_js_client_challenge_is_blocked(self):
        html = '<html><head><title>Client Challenge</title><link href="/_fs-ch-x/a.css"></head><body>JavaScript</body></html>'
        c = self.client({"https://a.test/p": (200, html)})
        with self.assertRaises(Blocked):
            c.get("https://a.test/p")

    def test_throttle(self):
        slept = []
        t = [0.0]
        c = PoliteClient("ua", "tcg-stock-monitor", min_delay=3, session=FakeSession({"https://a.test/p": (200, "ok")}),
                         sleep=lambda s: slept.append(s), clock=lambda: t[0])
        c.get("https://a.test/p")
        c.get("https://a.test/p")
        self.assertTrue(slept and all(s > 0 for s in slept))

    def test_crawl_delay_respected(self):
        slept = []
        t = [0.0]
        routes = {"https://a.test/robots.txt": (200, "User-agent: *\nCrawl-delay: 10\n"), "https://a.test/p": (200, "ok")}
        c = PoliteClient("ua", "tcg-stock-monitor", min_delay=1, session=FakeSession(routes),
                         sleep=lambda s: slept.append(s), clock=lambda: t[0])
        c.get("https://a.test/p")
        c.get("https://a.test/p")
        self.assertEqual(max(slept), 10)


class NotifyTest(unittest.TestCase):
    def test_single_and_summary(self):
        s = FakeSession()
        n = Notifier("https://ntfy.test", "geheim", max_single=2, session=s)
        n.send([Event(AVAILABLE, "Rossmann", "ETB", url="https://x/1", price="49.99", currency="EUR")])
        self.assertEqual(s.posts[0]["json"]["priority"], 5)
        self.assertIn("49,99 €", s.posts[0]["json"]["message"])
        self.assertEqual(s.posts[0]["json"]["click"], "https://x/1")
        n.send([Event(NEW_LISTING, "A", f"P{i}") for i in range(5)])
        self.assertEqual(len(s.posts), 2)
        self.assertIn("5 Pokémon-TCG-Meldungen", s.posts[1]["json"]["title"])

    def test_every_event_kind_can_be_sent(self):
        from monitor import notify
        kinds = [v for k, v in vars(notify).items() if k.isupper() and isinstance(v, str) and v in notify._STYLE]
        self.assertGreaterEqual(len(kinds), 6)
        s = FakeSession()
        n = Notifier("https://ntfy.test", "geheim", max_single=20, session=s)
        n.send([Event(k, "Q", "T") for k in kinds])
        self.assertEqual(len(s.posts), len(kinds))
        self.assertEqual(s.posts[0]["json"]["priority"], 5)

    def test_no_topic_no_network(self):
        s = FakeSession()
        n = Notifier("https://ntfy.test", None, session=s)
        n.send([Event(AVAILABLE, "A", "x")])
        self.assertEqual(s.posts, [])


class ConfigTest(unittest.TestCase):
    def test_shipped_config_valid(self):
        self.assertEqual(validate(load_sources()), [])

    def test_validation_catches_problems(self):
        bad = [
            Source("x", "X", "sitemap", {"id": "x", "type": "sitemap", "enabled": True, "every_minutes": 1}),
            Source("y", "Y", "listing", {"id": "y", "type": "listing", "enabled": True,
                                         "urls": ["https://t/kategorie/HIER-EINTRAGEN/"], "link_pattern": "("}),
        ]
        errors = "\n".join(validate(bad))
        self.assertIn("index_url", errors)
        self.assertIn("zu aggressiv", errors)
        self.assertIn("Platzhalter", errors)
        self.assertIn("ungültig", errors)


if __name__ == "__main__":
    unittest.main()
