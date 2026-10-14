"""Deterministic checks of the web research (docs/research.md section 6): which
citations count as sources of a finding, and (Task 3) which RM questions may go
to a search provider."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from urllib.parse import urlparse

from rmprep.research.types import CONFIDENCE, Source

_RANK = {c: i for i, c in enumerate(CONFIDENCE, start=1)}


def tr_lower(text: str) -> str:
    """Turkish lower-casing: İ -> i, I -> ı."""
    return text.replace("İ", "i").replace("I", "ı").lower()


def norm_url(url: str) -> str:
    """Scheme and host lower-cased, no fragment, no trailing slash: two forms of one page match."""
    p = urlparse(url.strip())
    query = f"?{p.query}" if p.query else ""
    return f"{p.scheme.lower()}://{(p.hostname or '').lower()}{p.path.rstrip('/')}{query}"


def is_excluded(url: str, domains: Iterable[str]) -> bool:
    host = (urlparse(url.strip()).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in (x.lower() for x in domains))


def is_web_url(url: str) -> bool:
    """Only http(s) pages can be sources (a javascript: or data: URL would become a link)."""
    p = urlparse(url.strip())
    return p.scheme.lower() in ("http", "https") and bool(p.hostname)


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
