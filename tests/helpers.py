"""Test-Hilfen: Fake-HTTP-Session ohne Netzwerk."""
from __future__ import annotations

import os

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name: str) -> bytes:
    with open(os.path.join(FIXTURES, name), "rb") as fh:
        return fh.read()


class FakeResponse:
    def __init__(self, url: str, status: int = 200, content: bytes = b"", encoding: str | None = "utf-8",
                 headers: dict | None = None):
        self.url = url
        self.headers = headers or {}
        self.status_code = status
        self.content = content
        self.encoding = encoding

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


class FakeSession:
    """routes: {url: (status, bytes[, headers])}. robots.txt fehlt standardmäßig (404 = alles erlaubt)."""

    def __init__(self, routes: dict | None = None):
        self.routes = dict(routes or {})
        self.headers: dict = {}
        self.calls: list[str] = []
        self.posts: list[dict] = []

    def get(self, url, timeout=None, **kw):
        self.calls.append(url)
        route = self.routes.get(url, (404, b"not found"))
        status, body = route[0], route[1]
        headers = route[2] if len(route) > 2 else None
        if isinstance(body, str):
            body = body.encode()
        return FakeResponse(url, status, body, headers=headers)

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts.append({"url": url, "json": json, "headers": headers})
        return FakeResponse(url, 200, b"{}")


def no_sleep(_seconds):
    pass
