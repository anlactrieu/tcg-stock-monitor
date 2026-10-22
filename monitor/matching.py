"""Relevanz-Filter: Ist eine URL bzw. ein Produktname ein Pokémon-TCG-Produkt?"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from urllib.parse import unquote


def normalize(text: str) -> str:
    """Kleinschreibung, URL-Decoding, Umlaute/Akzente vereinfachen.

    "Pokémon Top-Trainer-Box" -> "pokemon top-trainer-box"
    "pok%C3%A9mon"            -> "pokemon"
    "Plüsch"                  -> "plusch"  (ü -> u; "pluesch" steht zusätzlich in der Liste)
    """
    text = unquote(text or "").lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.replace("ß", "ss")


@dataclass
class Matcher:
    required_any: list[str] = field(default_factory=list)
    product_any: list[str] = field(default_factory=list)
    exclude_any: list[str] = field(default_factory=list)

    @classmethod
    def from_config(cls, cfg: dict) -> "Matcher":
        return cls(
            required_any=[normalize(x) for x in cfg.get("required_any", [])],
            product_any=[normalize(x) for x in cfg.get("product_any", [])],
            exclude_any=[normalize(x) for x in cfg.get("exclude_any", [])],
        )

    def matches(self, text: str) -> bool:
        t = normalize(text)
        if self.required_any and not any(k in t for k in self.required_any):
            return False
        if self.product_any and not any(k in t for k in self.product_any):
            return False
        if any(k in t for k in self.exclude_any):
            return False
        return True

    def excluded(self, text: str) -> bool:
        t = normalize(text)
        return any(k in t for k in self.exclude_any)

    def has_required(self, text: str) -> bool:
        t = normalize(text)
        return not self.required_any or any(k in t for k in self.required_any)
