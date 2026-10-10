"""Normalization of persona text for exact table matching (docs/decision.md section 3)."""

from __future__ import annotations

import unicodedata

_KEEP = "+-"


def normalize(text: str) -> str:
    """Turkish lower case (İ->i, I->ı), punctuation dropped except + and -,
    spaces stripped and collapsed. No fuzzy matching."""
    s = text.replace("İ", "i").replace("I", "ı").lower()
    s = "".join(" " if unicodedata.category(ch).startswith("P") and ch not in _KEEP else ch
                for ch in s)
    return " ".join(s.split())
