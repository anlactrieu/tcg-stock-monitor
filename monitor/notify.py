"""Benachrichtigungen per ntfy (https://ntfy.sh) – kostenlose Push-App für iOS/Android.

Konfiguration über Umgebungsvariablen (GitHub-Secrets):
  NTFY_TOPIC   geheimer Topic-Name (wie ein Passwort behandeln!)  – Pflicht
  NTFY_SERVER  optional, Standard aus settings.yaml (https://ntfy.sh)
  NTFY_TOKEN   optional, Access-Token falls eigener/geschützter Server
Ohne NTFY_TOPIC wird nur geloggt.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

# Ereignisarten
AVAILABLE = "available"
PREORDER = "preorder"
NEW_LISTING = "new_listing"
DEAL = "deal"
BLOCKED = "blocked"
ERROR = "error"

_STYLE = {
    # kind: (Titel-Präfix, ntfy-Priorität 1-5, ntfy-Tags)
    AVAILABLE: ("Jetzt verfügbar", 5, ["green_circle", "shopping_cart"]),
    PREORDER: ("Vorbestellbar", 4, ["large_blue_circle", "calendar"]),
    NEW_LISTING: ("Neu gelistet", 3, ["new"]),
    DEAL: ("Community-Fund", 4, ["loudspeaker"]),
    BLOCKED: ("Quelle pausiert", 2, ["warning"]),
    ERROR: ("Quelle fehlerhaft", 2, ["x"]),
}


@dataclass
class Event:
    kind: str
    source_name: str
    title: str
    url: str | None = None
    price: str | None = None
    currency: str | None = None
    hint: str | None = None

    def headline(self) -> str:
        return f"{self.source_name}: {_STYLE[self.kind][0]}"

    def body(self) -> str:
        lines = [self.title]
        if self.price:
            lines.append(f"{format_price(self.price, self.currency)}")
        if self.hint:
            lines.append(self.hint)
        return "\n".join(lines)


def format_price(price: str, currency: str | None) -> str:
    try:
        value = f"{float(price):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        value = str(price)
    return f"{value} {'€' if (currency or 'EUR') == 'EUR' else currency}"


class Notifier:
    def __init__(self, server: str, topic: str | None, token: str | None = None,
                 max_single: int = 8, session: requests.Session | None = None):
        self.server = server.rstrip("/")
        self.topic = topic
        self.token = token
        self.max_single = max_single
        self.session = session or requests.Session()
        self.sent: list[dict] = []  # für Tests/Logs

    def _post(self, payload: dict) -> None:
        payload = {"topic": self.topic, **payload}
        self.sent.append(payload)
        if not self.topic:
            log.info("[kein NTFY_TOPIC] %s | %s", payload.get("title"), payload.get("message"))
            return
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            r = self.session.post(self.server + "/", json=payload, headers=headers, timeout=15)
            if r.status_code >= 400:
                log.error("ntfy antwortet %s: %s", r.status_code, r.text[:200])
        except requests.RequestException as exc:
            log.error("ntfy nicht erreichbar: %s", exc)

    def send(self, events: list[Event]) -> None:
        if not events:
            return
        # Wichtigste zuerst
        order = [AVAILABLE, PREORDER, NEW_LISTING, BLOCKED, ERROR]
        events = sorted(events, key=lambda e: order.index(e.kind))
        if len(events) <= self.max_single:
            for e in events:
                prefix, prio, tags = _STYLE[e.kind]
                payload = {"title": e.headline(), "message": e.body(), "priority": prio, "tags": tags}
                if e.url:
                    payload["click"] = e.url
                    payload["actions"] = [{"action": "view", "label": "Zum Produkt", "url": e.url}]
                self._post(payload)
            return
        # Sammelmeldung
        top = max(_STYLE[e.kind][1] for e in events)
        lines = [f"• {e.headline()} – {e.title}" + (f" ({format_price(e.price, e.currency)})" if e.price else "")
                 for e in events[:20]]
        if len(events) > 20:
            lines.append(f"… und {len(events) - 20} weitere")
        payload = {
            "title": f"{len(events)} Pokémon-TCG-Meldungen",
            "message": "\n".join(lines),
            "priority": top,
            "tags": ["bell"],
        }
        if events[0].url:
            payload["click"] = events[0].url
        self._post(payload)

    def test(self) -> None:
        self._post({"title": "Test: TCG-Monitor", "message": "Benachrichtigungen funktionieren ✅",
                    "priority": 3, "tags": ["white_check_mark"]})
