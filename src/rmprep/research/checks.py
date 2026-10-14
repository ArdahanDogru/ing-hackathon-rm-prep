"""Deterministic checks of the web research (docs/research.md section 6): which
citations count as sources of a finding, and (Task 3) which RM questions may go
to a search provider."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from urllib.parse import urlparse

from rmprep.contracts import Persona
from rmprep.research.types import CONFIDENCE, Source

_RANK = {c: i for i, c in enumerate(CONFIDENCE, start=1)}


def tr_lower(text: str) -> str:
    """Turkish lower-casing: İ -> i, I -> ı."""
    return text.replace("İ", "i").replace("I", "ı").lower()


def norm_url(url: str) -> str:
    """Scheme and host lower-cased, no fragment, no trailing slash: two forms of one page match."""
    try:
        p = urlparse(url.strip())
        host = (p.hostname or "").lower()
    except ValueError:                 # malformed URL (for example "http://[bad"): never matches a result
        return ""
    query = f"?{p.query}" if p.query else ""
    return f"{p.scheme.lower()}://{host}{p.path.rstrip('/')}{query}"


def is_excluded(url: str, domains: Iterable[str]) -> bool:
    try:
        host = (urlparse(url.strip()).hostname or "").lower()
    except ValueError:                 # malformed URL: fail safe, treat it as excluded
        return True
    return any(host == d or host.endswith("." + d) for d in (x.lower() for x in domains))


def is_web_url(url: str) -> bool:
    """Only http(s) pages can be sources (a javascript: or data: URL would become a link)."""
    try:
        p = urlparse(url.strip())
        return p.scheme.lower() in ("http", "https") and bool(p.hostname)
    except ValueError:                 # malformed URL
        return False


def sources_for(path: str, grounding: Sequence[Mapping], results: Mapping[str, Source],
                domains: Iterable[str]) -> tuple[tuple[Source, ...], str]:
    """The sources of one output field: the citations of the grounding entries of
    `path` and its sub-fields (`bulgular[0]` covers `bulgular[0].metin`, not
    `bulgular[10]`) whose URL is a result of the same call (`results`: norm_url ->
    Source) and not on an excluded domain; no repeats, in citation order. Second
    value: the highest confidence of those entries ("medium" when none is given)."""
    domains = tuple(domains)
    found: dict[str, Source] = {}
    best = ""
    for g in grounding:
        field = str(g.get("field", ""))
        if field != path and not field.startswith((path + ".", path + "[")):
            continue
        conf = str(g.get("confidence", ""))
        if _RANK.get(conf, 0) > _RANK.get(best, 0):
            best = conf
        for c in g.get("citations") or ():
            src = results.get(norm_url(str((c or {}).get("url", ""))))
            if src is None or is_excluded(src.url, domains):
                continue
            found.setdefault(norm_url(src.url), src)
    return tuple(found.values()), best or "medium"


REASONS = {
    "TR": {"empty": "Soru boş.",
           "long": "Soru {n} karakterden uzun.",
           "client": "Soru müşteri bilgisi içeriyor; yalnızca ürün veya şirket hakkında sorun."},
    "EN": {"empty": "The question is empty.",
           "long": "The question is longer than {n} characters.",
           "client": "The question contains client information; ask only about products or companies."},
}
_WORD = re.compile(r"\w+")


def _words(text: str) -> list[str]:
    """Words of the text, Unicode NFC first (a decomposed "u + U+0308" is one letter "ü")."""
    return _WORD.findall(tr_lower(unicodedata.normalize("NFC", text)))


def _grams(words: Sequence[str], n: int = 3) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def check_question(question: str, persona: Persona, lang: str, client_words: Iterable[str],
                   max_chars: int) -> str | None:
    """None if the question may go to a search provider, else the reason (in `lang`)
    for the RM. Refused: empty; longer than max_chars; a word that starts with a
    client word (müşteri -> müşterim, müşterinin); the persona's age as a word; three
    words in a row from a persona text field (Turkish lower-casing throughout)."""
    reasons = REASONS[lang]
    q = question.strip()
    if not q:
        return reasons["empty"]
    if len(q) > max_chars:
        return reasons["long"].format(n=max_chars)
    words = _words(q)
    roots = tuple(tr_lower(unicodedata.normalize("NFC", w)) for w in client_words)
    if str(persona.yas) in words or any(roots and w.startswith(roots) for w in words):
        return reasons["client"]
    asked = _grams(words)
    fields = (persona.profil, persona.durum, persona.yatirim_amaci, persona.rm_notu,
              *persona.oncelikler, *persona.acik_kisitlar)
    if any(asked & _grams(_words(f)) for f in fields):
        return reasons["client"]
    return None
