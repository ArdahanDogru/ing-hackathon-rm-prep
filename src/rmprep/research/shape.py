"""Web araştırması v2 shaping (docs/research.md "v2"): short bullets, no facts the
RM already has, no repeats, caps; news only inside the window, newest first. The
service runs it on every provider's result, so Exa and Claude give one shape."""

from __future__ import annotations

import dataclasses
import re
import unicodedata
from collections.abc import Iterable, Sequence
from datetime import date, timedelta

from rmprep.research.checks import _words, tr_lower
from rmprep.research.config import ShapeConfig
from rmprep.research.types import SHAPE_VERSION, Finding, ProductResearch, QuestionAnswer

COMPANY_TOPICS = ("yonetici_sirket",)    # at most one bullet of these topics


def cut_words(text: str, max_words: int) -> str:
    """The text, or its first max_words words and "…"."""
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]).rstrip(",;:") + "…"


def _tokens(text: str) -> set[str]:
    return {w for w in _words(text) if len(w) >= 3}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def _fold(text: str) -> str:
    """NFC, Turkish lower-casing, ı -> i (so "ISIN" -> "ısın" still matches "isin")."""
    return tr_lower(unicodedata.normalize("NFC", text)).replace("ı", "i")


def _has_known_term(text: str, terms: Iterable[str]) -> bool:
    low = _fold(text)
    return any(re.search(r"(?<!\w)" + re.escape(_fold(t)), low) for t in terms)


def _tidy(items: Sequence[Finding], cfg: ShapeConfig, cap: int, *,
          known: bool) -> tuple[list[Finding], list[str]]:
    """Known-fact filter (highlights only), repeat filter, one company bullet (highlights
    only; it counts after the first two filters, so a known-fact company bullet does not
    block a valid one), word cut, cap; check lines."""
    kept: list[Finding] = []
    n_known = n_repeat = n_company = 0
    company_seen = False
    for f in items:
        if known and _has_known_term(f.text, cfg.known_terms):
            n_known += 1
            continue
        if any(_jaccard(_tokens(f.text), _tokens(g.text)) >= cfg.repeat_jaccard for g in kept):
            n_repeat += 1
            continue
        if known and f.topic in COMPANY_TOPICS:
            if company_seen:
                n_company += 1
                continue
            company_seen = True
        kept.append(dataclasses.replace(f, text=cut_words(f.text, cfg.bullet_max_words)))
    checks = []
    if n_known:
        checks.append(f"{n_known} bullets dropped (known facts)")
    if n_repeat:
        checks.append(f"{n_repeat} bullets dropped (repeats)")
    if n_company:
        checks.append(f"{n_company} company bullets dropped (one allowed)")
    return kept[:cap], checks + ([f"{len(kept) - cap} bullets over the cap"] if len(kept) > cap else [])


def _in_window(f: Finding, start: date, today: date) -> bool:
    try:
        d = date.fromisoformat(f.date)
    except ValueError:
        return False
    return start <= d <= today


def shape_product(p: ProductResearch, cfg: ShapeConfig, today: date) -> ProductResearch:
    if p.error:
        return dataclasses.replace(p, summary="", news_days=cfg.news_days, version=SHAPE_VERSION)
    checks = list(p.checks)
    highlights, more = _tidy(p.findings, cfg, cfg.highlights_max, known=True)
    checks += more
    start = today - timedelta(days=cfg.news_days)
    dated = [n for n in p.news if _in_window(n, start, today)]
    if len(dated) < len(p.news):
        checks.append(f"{len(p.news) - len(dated)} news items undated or outside {cfg.news_days} days dropped")
    dated.sort(key=lambda n: n.date, reverse=True)
    news, more = _tidy(dated, cfg, cfg.news_max, known=False)
    checks += [c.replace("bullets over the cap", "news items over the cap") for c in more]
    # the Claude fallback makes no news search: news_days 0 hides the news section of the panel
    news_days = 0 if p.provider == "claude" else cfg.news_days
    return dataclasses.replace(p, findings=tuple(highlights), news=tuple(news), summary="",
                               news_days=news_days, version=SHAPE_VERSION, checks=tuple(checks))


def shape_answer(a: QuestionAnswer, cfg: ShapeConfig) -> QuestionAnswer:
    if a.error:
        return dataclasses.replace(a, summary="", version=SHAPE_VERSION)
    bullets, more = _tidy(a.findings, cfg, cfg.highlights_max, known=False)
    return dataclasses.replace(a, findings=tuple(bullets), summary="", version=SHAPE_VERSION,
                               checks=a.checks + tuple(more))
