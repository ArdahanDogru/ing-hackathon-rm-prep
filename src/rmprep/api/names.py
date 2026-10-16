"""Short fund names for the screens (docs/web-ui.md "Redesign v2"; lead-owned).

TEFAS names are long and upper case ("NUROL PORTFÖY PARA PİYASASI (TL) FONU").
The screens show the issuer small ("Nurol Portföy") and the fund type bold
("Para Piyasası (TL)"); the full label stays for hover, the fund card and the
texts."""

from __future__ import annotations

import re

ABBREVIATIONS = (("KISA VADELİ", "KV"), ("BORÇLANMA ARAÇLARI", "BORÇLANMA"))
SMALL_WORDS = {"ve", "ile", "veya"}
KEEP_UPPER = {"TL", "KV", "USD", "EUR", "ING", "BIST", "ABD", "PYŞ", "TEB"}
VOWELS = set("AEIİOÖUÜ")
ISSUER_WORDS = ("PORTFÖY", "PYŞ")       # the issuer ends with one of these


CODE_KINDS = ("fund", "etf", "stock")   # W28: kinds whose option id ends with a code


def product_code(option_id: str) -> str:
    """W28: the TEFAS code or BIST ticker of a fund, ETF or share option ("fund:PPN"
    -> "PPN"); "" for the ING deposit options and any other kind."""
    kind, _, code = option_id.partition(":")
    return code if kind in CODE_KINDS else ""


def with_code(option_id: str, name: str) -> str:
    """W28: "PPN · <name>" for a product with a code, else the name."""
    code = product_code(option_id)
    return f"{code} · {name}" if code else name


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
        if core in KEEP_UPPER or (core.isalpha() and len(core) <= 5 and not set(core) & VOWELS):
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
    marks = [i for i, w in enumerate(words) if w in ISSUER_WORDS]
    if not marks:
        return "", text
    cut = marks[0] + 1
    issuer = _title(" ".join(words[:cut]))
    rest = [w for w in words[cut:] if w != "FONU"]
    if rest and rest[-1] == "FON":               # some labels end with "FON" instead of "FONU"
        rest = rest[:-1]
    if not rest:
        return issuer, text
    body = " ".join(rest)
    for long, short in ABBREVIATIONS:
        body = body.replace(long, short)
    return issuer, _title(body)
