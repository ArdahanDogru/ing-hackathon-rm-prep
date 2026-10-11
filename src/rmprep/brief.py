"""The plain dashboard brief (docs/web-ui.md "LLM brief"; lead-owned): the
persona's situation and goal, shown first and kept when the LLM brief fails."""

from __future__ import annotations

from datetime import datetime

from rmprep.contracts import BRIEF_MAX_CHARS, DecisionResult, NarrativeBrief

TEMPLATE_VERSION = "b0"


def _cut(text: str, limit: int = BRIEF_MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def plain_brief(r: DecisionResult, lang: str) -> str:
    p = r.persona
    if lang == "EN":
        return _cut(f"Situation: {_sentence(p.durum)} Goal: {_sentence(p.yatirim_amaci)}")
    return _cut(f"{_sentence(p.durum)} {_sentence(p.yatirim_amaci)}")


def template_brief(r: DecisionResult, lang: str, created_at: datetime,
                   checks: tuple[str, ...] = ()) -> NarrativeBrief:
    return NarrativeBrief(run_id=r.run_id, lang=lang, text=plain_brief(r, lang), source="template",
                          model="", prompt_version=TEMPLATE_VERSION, checks=checks,
                          created_at=created_at)
