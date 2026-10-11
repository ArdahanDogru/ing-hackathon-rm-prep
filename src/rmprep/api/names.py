"""Short fund names for the screens (docs/web-ui.md "Redesign v2"; lead-owned).

TEFAS names are long and upper case ("NUROL PORTFÖY PARA PİYASASI (TL) FONU").
The screens show the issuer small ("Nurol Portföy") and the fund type bold
("Para Piyasası (TL)"); the full label stays for hover, the fund card and the
texts."""

from __future__ import annotations

import re

ABBREVIATIONS = (("KISA VADELİ", "KV"), ("BORÇLANMA ARAÇLARI", "BORÇLANMA"))
SMALL_WORDS = {"ve", "ile", "veya"}
KEEP_UPPER = {"TL", "KV", "USD", "EUR", "ING", "BIST", "ABD"}


def _tr_lower(word: str) -> str:
    return word.replace("İ", "i").replace("I", "ı").lower()


def _tr_title(word: str) -> str:
    low = _tr_lower(word)
    if not low:
        return word
    head = {"i": "İ", "ı": "I"}.get(low[0], low[0].upper())
    return head + low[1:]


def _title(text: str) -> str:
    out = []
    for i, token in enumerate(text.split(" ")):
        core = token.strip("()")
        if core in KEEP_UPPER:
            out.append(token)
        elif i > 0 and _tr_lower(core) in SMALL_WORDS:
            out.append(token.replace(core, _tr_lower(core)))
        else:
            out.append(token.replace(core, _tr_title(core)) if core else token)
    return " ".join(out)


def short_name(label: str) -> tuple[str, str]:
    """(issuer, short label); ("", label) if the label has no "PORTFÖY"."""
    text = re.sub(r"\s+", " ", label).strip()
    words = text.split(" ")
    if "PORTFÖY" not in words:
        return "", text
    cut = words.index("PORTFÖY") + 1
    issuer = _title(" ".join(words[:cut]))
    rest = [w for w in words[cut:] if w != "FONU"]
    if not rest:
        return issuer, text
    body = " ".join(rest)
    for long, short in ABBREVIATIONS:
        body = body.replace(long, short)
    return issuer, _title(body)
