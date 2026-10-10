"""Glossary for "Terimler" / "Terms" (docs/ui.md U11): config/glossary.yaml
(static, lead-owned) and the terms that appear in a shown text.

Matching: case-insensitive after Turkish lower-casing, whole words or phrases
only (so "reel" does not match inside "reelleşme"). The page language's forms
are matched; an English page also matches the Turkish forms, because the engine
texts (reasons, warnings, assumptions) are Turkish only. A missing or broken
file gives no terms, never an error."""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

LANGS = ("TR", "EN")


@dataclass(frozen=True)
class Term:
    key: str
    forms: dict[str, tuple[str, ...]]    # lang -> surface forms, Turkish lower case
    text: dict[str, str]                 # lang -> plain explanation


@dataclass(frozen=True)
class Found:
    term: Term
    form: str            # the form that matched first
    explanation: str     # in the page language


def tr_lower(text: str) -> str:
    return text.replace("I", "ı").replace("İ", "i").lower()


def _term(key, d) -> Term:
    forms = d["forms"]
    if not all(isinstance(forms[lang], list) and forms[lang] for lang in LANGS):
        raise ValueError(f"{key}: forms must be non-empty lists")
    if not all(isinstance(d[lang], str) and d[lang].strip() for lang in LANGS):
        raise ValueError(f"{key}: explanations must be non-empty text")
    return Term(str(key), {lang: tuple(tr_lower(str(f)) for f in forms[lang]) for lang in LANGS},
                {lang: d[lang].strip() for lang in LANGS})


@functools.lru_cache(maxsize=4)
def load(path: Path | str) -> tuple[Term, ...]:
    """The terms of the glossary file, in file order; () if it is missing or broken."""
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        terms = raw["terms"]
        if not isinstance(terms, dict) or not terms:
            return ()
        return tuple(_term(k, v) for k, v in terms.items())
    except (OSError, yaml.YAMLError, KeyError, TypeError, ValueError, AttributeError):
        return ()


@functools.lru_cache(maxsize=256)
def _pattern(form: str) -> re.Pattern:
    return re.compile(r"(?<!\w)" + re.escape(form) + r"(?!\w)")


def find_terms(text: str, terms: tuple[Term, ...], lang: str) -> list[Found]:
    """The terms whose forms appear in text, in the order of first appearance."""
    low = tr_lower(text)
    langs = (lang, "TR") if lang != "TR" else ("TR",)
    hits = []
    for i, term in enumerate(terms):
        best = None
        for form in dict.fromkeys(f for lg in langs for f in term.forms.get(lg, ())):
            m = _pattern(form).search(low)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), form)
        if best is not None:
            hits.append((best[0], i, Found(term, best[1], term.text[lang])))
    return [f for _, _, f in sorted(hits, key=lambda h: (h[0], h[1]))]
