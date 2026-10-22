import unittest

from monitor.robots import RobotsTxt

# Echte Regeln von rossmann.de (Stand 21.10.2026)
ROSSMANN = """
User-agent: *
Disallow: /de/cart
Disallow: /de/checkout
Disallow: /de/search/*
Disallow: /*?*
Allow: /*?q=%3Arelevance%3A&page=*&pageSize=*
Allow: /*?pageIndex=*

User-agent: ClaudeBot
Disallow: /
"""
AGENT = "tcg-stock-monitor"


class RobotsTest(unittest.TestCase):
    def setUp(self):
        self.r = RobotsTxt(ROSSMANN)

    def test_wildcards(self):
        self.assertFalse(self.r.can_fetch(AGENT, "https://www.rossmann.de/de/search/pokemon"))
        self.assertFalse(self.r.can_fetch(AGENT, "https://www.rossmann.de/de/spielzeug-x/p/1?foo=bar"))
        self.assertTrue(self.r.can_fetch(AGENT, "https://www.rossmann.de/de/spielzeug-x/p/1"))
        self.assertTrue(self.r.can_fetch(AGENT, "https://www.rossmann.de/de/sitemap_index.xml"))
        self.assertFalse(self.r.can_fetch(AGENT, "https://www.rossmann.de/de/cart"))

    def test_longest_match_allow(self):
        self.assertTrue(self.r.can_fetch(AGENT, "https://www.rossmann.de/de/x/c/1?pageIndex=2"))

    def test_specific_agent_group(self):
        self.assertFalse(self.r.can_fetch("ClaudeBot/1.0", "https://www.rossmann.de/de/p/1"))
        r = RobotsTxt("User-agent: tcg-stock-monitor\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
        self.assertFalse(r.can_fetch(AGENT, "https://a.test/x"))

    def test_dollar_and_empty(self):
        r = RobotsTxt("User-agent: *\nDisallow: /*.pdf$\nDisallow:\n")
        self.assertFalse(r.can_fetch(AGENT, "https://a.test/a.pdf"))
        self.assertTrue(r.can_fetch(AGENT, "https://a.test/a.pdf.html"))

    def test_crawl_delay(self):
        self.assertEqual(RobotsTxt("User-agent: *\nCrawl-delay: 7\n").crawl_delay(AGENT), 7)

    def test_multiple_agents_one_group(self):
        r = RobotsTxt("User-agent: a\nUser-agent: *\nDisallow: /x\n")
        self.assertFalse(r.can_fetch(AGENT, "https://a.test/x"))


if __name__ == "__main__":
    unittest.main()
