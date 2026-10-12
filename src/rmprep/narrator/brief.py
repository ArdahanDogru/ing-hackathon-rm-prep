"""The dashboard brief (contract v1.4; docs/web-ui.md "LLM brief"; narrator N10):
1-2 sentences for the RM about a READY run that is not approved yet. The
facts are those of the meeting text with the engine's top 3 recommendations
(grouping.top_heads) as the selection and no deposit baseline, so an
ING-vs-market comparison (an RM-only warning) cannot pass the validator.
The plain sentence (rmprep.brief) is the fallback; there is no retry."""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass

from rmprep import grouping
from rmprep.contracts import DecisionResult, DecisionState, EvidenceSet, RmStatus
from rmprep.decision.config import DecisionConfig
from rmprep.narrator.config import NarratorConfig
from rmprep.narrator.facts import Facts, OptionFacts, build_facts
from rmprep.narrator.llm import LlmRequest
from rmprep.narrator.prompt import _LANGUAGE, _short
from rmprep.narrator.validator import validate_brief as _validate_brief

__all__ = ["BRIEF_SCHEMA", "BriefFacts", "brief_pack", "brief_request", "build_brief_facts",
           "fit_sentences", "parse_brief", "validate_brief"]

TOP = 3

BRIEF_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"},
                   "cite": {"type": "array", "items": {"type": "string"}}},
    "required": ["text", "cite"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class BriefFacts:
    facts: Facts                     # selection = the top 3; no baseline, no groups

    @property
    def options(self) -> tuple[OptionFacts, ...]:
        return self.facts.selected


def build_brief_facts(r: DecisionResult, ev: EvidenceSet,
                      decision_config: DecisionConfig | None = None) -> BriefFacts:
    """ValueError for a run that is not ready or has no recommendation."""
    if r.state != DecisionState.READY:
        raise ValueError("a brief needs a ready run")
    top = tuple(o.option.option_id for o in grouping.recommended(r, TOP))   # v1.6 (lead, 2026-10-12)
    if not top:
        raise ValueError("the run has no recommendation")
    view = dataclasses.replace(r, rm_status=RmStatus.APPROVED, rm_selected=top, rm_note="",
                               rm_option_notes={})
    f = build_facts(view, ev, decision_config)
    talked = {i for t in f.talking_points for i in t.option_ids} - set(top)
    others = [o for o in (*f.alternatives, *f.talked) if o.option_id in talked]
    named = set(top) | {o.option_id for o in others}
    f = dataclasses.replace(
        f, baseline=None, alternatives=(), groups=(), talked=tuple(others), rm_note="",
        warnings=tuple(w for w in f.warnings if set(w.option_ids) <= named))
    return BriefFacts(f)


def brief_pack(bf: BriefFacts) -> dict:
    """What the brief model reads (small: persona, file note, talking points,
    the top 3, client warnings)."""
    f = bf.facts
    return {
        "run_id": f.run_id,
        "client": {k: list(v) if isinstance(v, tuple) else v for k, v in f.client.items()
                   if k != "rm_notu"},
        "dosyadaki_not": f.client["rm_notu"],
        "talking_points": [{"title": t.title, "text": t.text, "option_ids": list(t.option_ids),
                            "evidence_ids": list(t.evidence_ids)} for t in f.talking_points],
        "top_options": [{**_short(o), "why": [list(w) for w in f.why.get(o.option_id, ())]}
                        for o in bf.options],
        "warnings": [{"code": w.code, "message": w.message, "option_ids": list(w.option_ids)}
                     for w in f.warnings],
    }


_SYSTEM = """\
You write the dashboard brief for a relationship manager (RM) of ING Turkey: \
at most two short sentences, at most {max_chars} characters in total (about \
{words} words), for the RM (not for the client), in {language}, {form}. Say who the client is, what they want, and what this \
meeting should do. You do not decide or recommend; the engine's options are \
not approved yet.

Input: the facts pack (JSON) in the first user block, the only source: \
"client" (the persona), "dosyadaki_not" (the note in the client's file), \
"talking_points" (the engine's points about the client's situation), \
"top_options" (the engine's top 3, with key numbers {{quantity: [value, unit, \
evidence_id]}} and "why" [client priority, fact] pairs) and "warnings".

Output: JSON {{"text": the brief, "cite": the option_id and evidence_id values \
it rests on}}.

Rules (a validator checks them; a text that fails is replaced by a plain sentence):
1. Every number is a number of the facts, rounded at most, written as {numbers}; \
no new numbers.
2. Name only the top options (label or fund code); no other product, no ING \
deposit and no comparison of ING with market rates.
3. Never promise a result. Do not use these phrases or their forms: {forbidden}.
4. No internal names or values: no field, flag or source names (such as \
needs_check, tefas_web), no scores, no names of screens or panes.
"""

_TASK = "Write the brief in {lang} for run {run_id} from the facts above."


def brief_request(bf: BriefFacts, lang: str, config: NarratorConfig) -> LlmRequest:
    b = config.brief
    language, form, numbers, _ = _LANGUAGE[lang]
    system = _SYSTEM.format(max_chars=b.max_chars, words=b.max_chars // 7,
                            language=language, form=form,
                            numbers=numbers,
                            forbidden=", ".join(f'"{p}"' for p in config.forbidden_phrases[lang]))
    facts = json.dumps(brief_pack(bf), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return LlmRequest(system=system,
                      user_blocks=(facts, _TASK.format(lang=lang, run_id=bf.facts.run_id)),
                      schema=BRIEF_SCHEMA, model=b.model, max_tokens=b.max_tokens,
                      effort=b.effort, fallback=False)


def validate_brief(text: str, cite, bf: BriefFacts, r: DecisionResult, config: NarratorConfig,
                   lang: str) -> tuple[str, ...]:
    """The validator rules of the brief (validator.validate_brief) on the brief facts."""
    return _validate_brief(text, tuple(cite), bf.facts, r, config, lang)


_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def fit_sentences(text: str, limit: int) -> str:
    """The whole sentences of text that fit into limit characters, never a cut
    sentence; text as it is when even the first sentence is longer (the
    validator then reports the length)."""
    if len(text) <= limit:
        return text
    out = ""
    for sentence in _SENTENCE_END.split(text.strip()):
        joined = f"{out} {sentence}".strip()
        if len(joined) > limit:
            break
        out = joined
    return out or text


def parse_brief(text: str) -> tuple[str, tuple[str, ...]]:
    """(text, cite) of the reply; ValueError on any other shape."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"not JSON: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("text"), str):
        raise ValueError("the reply needs a text string")
    cite = data.get("cite", [])
    if not isinstance(cite, list) or not all(isinstance(c, str) for c in cite):
        raise ValueError("cite: must be a list of strings")
    return data["text"].strip(), tuple(cite)
