"""Parser für Sitemaps, Übersichtsseiten und Produktseiten.

Reine Funktionen ohne Netzwerk -> einfach mit Fixtures testbar (tests/fixtures).
"""
from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urldefrag

from defusedxml import ElementTree as ET

# ---------------------------------------------------------------- Sitemaps


@dataclass
class SitemapEntry:
    loc: str
    lastmod: str | None = None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_sitemap(xml_bytes: bytes) -> tuple[str, list[SitemapEntry]]:
    """Gibt ("index" | "urlset", Einträge) zurück."""
    root = ET.fromstring(xml_bytes)
    kind = "index" if _local(root.tag) == "sitemapindex" else "urlset"
    entries: list[SitemapEntry] = []
    for node in root:
        loc = lastmod = None
        for child in node:
            name = _local(child.tag)
            if name == "loc" and child.text:
                loc = child.text.strip()
            elif name == "lastmod" and child.text:
                lastmod = child.text.strip()
        if loc:
            entries.append(SitemapEntry(loc=loc, lastmod=lastmod))
    return kind, entries


# ---------------------------------------------------------------- Listings


def extract_links(page_html: str, base_url: str, link_pattern: str) -> list[str]:
    """Alle Links (href), die zu `link_pattern` passen, absolut und ohne Duplikate."""
    rx = re.compile(link_pattern)
    seen: dict[str, None] = {}
    for href in re.findall(r'href\s*=\s*["\']([^"\']+)["\']', page_html, flags=re.I):
        href = html_lib.unescape(href)
        if not rx.search(href):
            continue
        url, _ = urldefrag(urljoin(base_url, href))
        url = url.split("?", 1)[0]
        seen.setdefault(url, None)
    return list(seen)


# ---------------------------------------------------------------- Produktseiten

# Normalisierte Zustände
AVAILABLE = "available"
PREORDER = "preorder"
UNAVAILABLE = "unavailable"
UNKNOWN = "unknown"

_AVAIL_MAP = {
    "instock": AVAILABLE,
    "instoreonly": AVAILABLE,
    "limitedavailability": AVAILABLE,
    "onlineonly": AVAILABLE,
    "preorder": PREORDER,
    "presale": PREORDER,
    "backorder": UNAVAILABLE,
    "outofstock": UNAVAILABLE,
    "soldout": UNAVAILABLE,
    "discontinued": UNAVAILABLE,
}


@dataclass
class FeedItem:
    guid: str
    title: str
    link: str


def parse_rss(xml_bytes: bytes) -> list[FeedItem]:
    """RSS-2.0-Feed -> Einträge (Titel, Link, guid). Atom wird nicht unterstützt."""
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        guid = (it.findtext("guid") or link or title).strip()
        if title and guid:
            items.append(FeedItem(guid=guid, title=html_lib.unescape(title), link=link))
    return items


@dataclass
class ProductInfo:
    status: str = UNKNOWN
    name: str | None = None
    price: str | None = None
    currency: str | None = None
    method: str = "none"  # jsonld | meta | pattern | none


def _iter_jsonld(page_html: str):
    for raw in re.findall(
        r'<script[^>]+type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        page_html, flags=re.I | re.S,
    ):
        raw = raw.strip()
        if raw.startswith("<!--"):
            raw = raw.strip("<!->").strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            try:
                data = json.loads(html_lib.unescape(raw))
            except json.JSONDecodeError:
                continue
        yield from _walk(data)


def _walk(data):
    if isinstance(data, list):
        for item in data:
            yield from _walk(item)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from _walk(data["@graph"])


def _is_type(node: dict, name: str) -> bool:
    t = node.get("@type")
    types = t if isinstance(t, list) else [t]
    return any(isinstance(x, str) and x.lower() == name.lower() for x in types)


def _norm_availability(value) -> str:
    if not isinstance(value, str):
        return UNKNOWN
    key = value.rsplit("/", 1)[-1].replace(" ", "").lower()
    return _AVAIL_MAP.get(key, UNKNOWN)


def _offers(product: dict) -> list[dict]:
    offers = product.get("offers")
    if isinstance(offers, dict):
        if _is_type(offers, "AggregateOffer") and isinstance(offers.get("offers"), list):
            return [o for o in offers["offers"] if isinstance(o, dict)] or [offers]
        return [offers]
    if isinstance(offers, list):
        return [o for o in offers if isinstance(o, dict)]
    return []


def _best_status(statuses: list[str]) -> str:
    for s in (AVAILABLE, PREORDER, UNAVAILABLE):
        if s in statuses:
            return s
    return UNKNOWN


def parse_product(page_html: str, in_stock_patterns=(), out_of_stock_patterns=()) -> ProductInfo:
    info = ProductInfo()

    # 1) schema.org JSON-LD (bevorzugt, offizielle maschinenlesbare Angabe)
    statuses: list[str] = []
    for node in _iter_jsonld(page_html):
        if not _is_type(node, "Product") and not _is_type(node, "ProductGroup"):
            continue
        info.name = info.name or (node.get("name") if isinstance(node.get("name"), str) else None)
        for offer in _offers(node):
            statuses.append(_norm_availability(offer.get("availability")))
            if info.price is None:
                price = offer.get("price", offer.get("lowPrice"))
                if price is not None:
                    info.price = str(price)
                    info.currency = offer.get("priceCurrency")
        for variant in node.get("hasVariant", []) if isinstance(node.get("hasVariant"), list) else []:
            if isinstance(variant, dict):
                for offer in _offers(variant):
                    statuses.append(_norm_availability(offer.get("availability")))
    status = _best_status(statuses)
    if status != UNKNOWN:
        info.status, info.method = status, "jsonld"

    # 2) Meta-Tags (Open Graph / product:availability)
    if info.status == UNKNOWN:
        m = re.search(
            r'<meta[^>]+(?:property|name|itemprop)\s*=\s*["\'](?:product:availability|og:availability|availability)["\'][^>]*content\s*=\s*["\']([^"\']+)',
            page_html, flags=re.I)
        if m:
            st = _norm_availability(m.group(1).replace(" ", ""))
            if st != UNKNOWN:
                info.status, info.method = st, "meta"

    # 3) Regex-Fallbacks aus der Konfiguration
    if info.status == UNKNOWN:
        if any(re.search(p, page_html) for p in out_of_stock_patterns):
            info.status, info.method = UNAVAILABLE, "pattern"
        elif any(re.search(p, page_html) for p in in_stock_patterns):
            info.status, info.method = AVAILABLE, "pattern"

    if not info.name:
        m = re.search(r'<meta[^>]+property\s*=\s*["\']og:title["\'][^>]*content\s*=\s*["\']([^"\']+)', page_html, re.I)
        if not m:
            m = re.search(r"<title[^>]*>(.*?)</title>", page_html, re.I | re.S)
        if m:
            info.name = html_lib.unescape(m.group(1)).strip()
    if info.name:
        info.name = html_lib.unescape(info.name).strip()
    return info
