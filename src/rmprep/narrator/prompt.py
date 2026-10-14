"""The LLM request of the narrator: system prompt, facts block, task, output
schema, and the parser of the reply (docs/narrator.md, "Output").

Bump prompt_version in config/narrator.yaml on any change of the texts here:
it is part of the cache key."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from rmprep.contracts import NARRATIVE_SECTIONS_V13, NarrativeSection, NarrativeSentence
from rmprep.narrator.config import NarratorConfig
from rmprep.narrator.facts import (
    INTERNAL_PARTS,
    MARKET_NAMES,
    Facts,
    OptionFacts,
    RiskFacts,
    number_rank,
)
from rmprep.narrator.llm import LlmRequest
from rmprep.narrator.template import is_quotable

SECTIONS = NARRATIVE_SECTIONS_V13          # N9: talking_points added

# N9b: ONE sentence schema for all sections. A schema per section (8 copies) was
# a grammar too large for structured outputs (HTTP 400 "The compiled grammar is
# too large"); tests/narrator/test_prompt.py keeps the schema small.
_SENTENCE = {
    "type": "object",
    "properties": {
        "section": {"type": "string", "enum": list(SECTIONS)},
        "text": {"type": "string"},
        "title": {"type": "string"},
        "cite": {"type": "array", "items": {"type": "string"}},   # option ids and evidence ids
    },
    "required": ["section", "text", "title", "cite"],
    "additionalProperties": False,
}

_NEED_TAGS = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "option_id": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["option_id", "tags"],
        "additionalProperties": False,
    },
}

SCHEMA = {
    "type": "object",
    "properties": {"sentences": {"type": "array", "items": _SENTENCE}, "need_tags": _NEED_TAGS},
    "required": ["sentences", "need_tags"],
    "additionalProperties": False,
}

_LANGUAGE = {
    "TR": ("Turkish", "formal \"siz\" form", "%52,51 and 1.054,64", "09.10.2026"),
    "EN": ("English", "polite, plain form", "52.51% and 1,054.64", "2026-10-09"),
}

_SYSTEM = """\
You write the meeting preparation card for a relationship manager (RM) of ING \
Turkey. The decision engine has already chosen and ranked the options and the RM \
has approved a selection; you only write. You do not decide, rank, or recommend \
anything that is not in the facts.

Language: write in {language}, {form}. Persona fields, option labels and engine \
texts in the facts are Turkish; quote them as they are. Write the card as \
instructions to the RM (in Turkish as commands such as "... anlatın", "... sorun", \
"... teyit edin"; in English "Explain ...", "Ask ..."). Only teklif_metni is \
speech that the RM says to the client.

Input: the facts pack (JSON) in the first user block. It is the only source. \
"baseline" is the comparison deposit, "selected" are the options the RM chose, \
"alternatives" are the other options of the same groups, "groups" says which is \
which. Key numbers are "numbers": {{quantity: [value, unit, evidence_id]}}, with \
the date in "as_of" (a fourth item when a number has its own date); unit "pct" \
is a percent, "level" a risk level. "real_return_1y" is the real 1-year return \
after stopaj and CPI; it comes first, the nominal "fund_return_1y" after it. \
"market" holds, once for the whole text, "piyasa_mevduat_faizi" and \
"tufe_yillik" (annual CPI). Each selected option has "name" (its short name, \
as the RM's screen shows it) and "risk": "access" (when the money is \
available), "fees" and "note" (the main risk of its asset class), with "cite". \
"unmatched_priorities" are client priorities that no option criterion covers. \
"piyasa_mevduat_faizi" is the market average \
deposit rate (TCMB EVDS, weighted average of new TL deposits up to 3 months), \
not an ING rate; "ing_mevduat_faizi" (ING Turuncu Hesap) and \
"ing_vadeli_mevduat_faizi" (ING e-Vadeli Mevduat) are ING's rates: write an ING \
product name only with its own ING rate. "reasons" are the engine's reasons for an \
option; "fits" names the needs the engine found the option strong on (liquidity, \
income, principal, simplicity), without values; "why" lists [client priority, \
fact] pairs. "talking_points" are the engine's points about the client's \
situation (title, figure, text) and "talking_point_options" the options they \
name. "dosyadaki_not" is the note in the client's file; "rm_onay_notu" is the \
RM's note from the approval. "allocation" is the model split per asset class \
("band_low"-"band_high", % of the portfolio) and the client's current share: \
"current" (%) and "gap" (points to the band: positive = below it, negative = above \
it, 0 = inside) are given only for a row with "active": true (the RM or the \
client's file gave the share). A row with "active": false is only an estimate.

Output: JSON with "sentences" (all sentences of the card, in reading order) and \
"need_tags". Each sentence has "section" (one of the section keys below), \
"text", "title" ("" except in talking_points) and "cite": the option_id and \
evidence_id values of the facts that the sentence rests on.
- ozet: at most 3 sentences: the client situation and the aim of the meeting; \
then the sentence "{disclaimer}" exactly.
- talking_points: 2-3 sentences about the client's situation from the client's \
view, each with a title of 2-4 words and a citation. Start from the engine's \
talking_points (their title and figure); add from the client's priorities or \
constraints when there are fewer than 2. Do not repeat profile facts (age, \
situation, goal) that ozet gives.
- oneriler: for each selected option exactly 3 sentences, and each sentence \
must start with the option's name (its "name" or label): (a) its facts, the \
real return first, then the nominal return and the risk level; (b) why it fits \
this client, with a client fact (horizon, liquidity, income, principal \
protection, a constraint or a note, in the client's own words) that you do not \
use for the other options; (c) the main trade-off or risk for this client, \
from its "risk" line. The options must not read alike.
- alternatifler: 1-2 sentences per group: the other options of the same kind.
- dikkat: the warnings in the facts, in plain words; then at most one sentence per \
selected option, starting with its name and only with what oneriler does not say: \
its access when "access_slow" is true, and its fees if any (nothing for an option \
without these); each unmatched priority, named as not covered by the options; and \
once, that past returns do not show future returns. In dikkat do not repeat a \
sentence or a risk note of oneriler. The client can see this section: no notes \
about data quality and no names of screens or panes.
- sorular: questions for the RM to ask the client: the open questions, the \
explicit constraints (acik_kisitlar) to confirm, and one question per \
unmatched priority. When an "allocation" row with a "source" has "active": false, \
the client's current split is unknown: ask for it with the sentence "{split_unknown}"
- teklif_metni: a short script the RM may say or adapt in the meeting, spoken \
to the client and built on the client's own goal and situation (yatirim_amaci, \
durum). It is not a letter. At most one short past-return reminder.
- varsayimlar: each assumption of the facts as its own sentence, verbatim.
- need_tags: one entry for each selected option: 1-3 tags, each copied exactly \
from the client's priorities (oncelikler) that the option serves (use its \
"why" pairs); no other words.

Rules (a validator checks each one; a text that fails is replaced):
1. Every number and date you write is a number or date of the facts, rounded \
at most. Write numbers as {numbers} and dates as {date}. Do not compute new \
numbers (no differences, sums, or averages) and do not write ids in the text.
2. Name only the baseline, the selected options, the alternatives and the \
talking_point_options, by their label or fund code. Never name or hint at a \
rejected option or any other product.
3. Never promise a result. Do not use these phrases or their forms: {forbidden}. \
Write the past-return caveat only in dikkat and teklif_metni.
4. Every sentence of talking_points, oneriler, alternatifler and dikkat has at \
least one id in "cite"; cite only ids that exist in the facts.
5. No internal values outside varsayimlar: no field, flag or source names \
(such as needs_check, tefas_web, penalty:...), no score or fit values, no row \
counts, no counts of rejected options, no names of screens or panes. Write \
sources as TEFAS or TCMB EVDS.
6. Include the sentence "{disclaimer}" verbatim.
8. Do not compare the ING deposit with the market deposit rate (or the market \
average) in any section but oneriler: that comparison is an RM-only note. Name the \
ING deposit in oneriler only if the RM selected it, and never with the market rate. \
The market deposit rate alone (as in a talking point) is fine.
7. need_tags: only words of oncelikler, at most 3 per option, every selected option.
9. Write a current share or a gap only for an "allocation" row with "active": true \
(in talking_points or dikkat, citing the selected options); never for a row with \
"active": false, not even as an estimate.
Length: aim for about 450 words in total for 3 selected options (fewer for fewer \
options); ozet at most 3 sentences plus the disclaimer; teklif_metni at most 4 sentences.
This is decision support for the RM, not investment advice.
"""

# N15: the question about an unknown split when the config has no allocation texts
_SPLIT_UNKNOWN = {"TR": "Mevcut portföy dağılımı bilinmiyor; müşteriden alınmalı.",
                  "EN": "The client's current portfolio split is unknown; ask the client for it."}

_TASK = "Write the meeting text in {lang} for run {run_id} from the facts above."

_RETRY = """\
Your previous answer failed the validator. Previous answer:
{previous}

Findings:
{findings}

Return the full corrected JSON. Change only what the findings need."""


def system_prompt(lang: str, config: NarratorConfig) -> str:
    language, form, numbers, day = _LANGUAGE[lang]
    forbidden = ", ".join(f'"{p}"' for p in config.forbidden_phrases[lang])
    unknown = (config.allocation.split_unknown[lang] if config.allocation is not None
               else _SPLIT_UNKNOWN[lang])
    return _SYSTEM.format(language=language, form=form, numbers=numbers, date=day,
                          forbidden=forbidden, disclaimer=config.disclaimer[lang],
                          split_unknown=unknown)


ALTERNATIVE_NUMBERS = 3     # key numbers per alternative in the prompt pack
SELECTED_NUMBERS = 6        # key numbers per selected option and the baseline
MAIN_REASONS = 3            # reason texts per selected option (internal parts excluded)
# N13: not option numbers: the market facts (top level), buyability, and the rows of
# the risk line (sell valör, fees)
_NOT_OPTION_NUMBERS = {"fund_buyable", "fund_sell_valor_days", "fund_entry_fee", "fund_exit_fee"}


def _numbers(o: OptionFacts, limit: int) -> dict:
    """{"as_of": date, "numbers": {quantity: [value, unit, evidence_id(, as_of)]}};
    a number gets its own date only if it differs from the option's. The real
    return first (N13); market facts and risk-line rows are not option numbers."""
    own = [n for n in o.numbers if n.name not in MARKET_NAMES
           and n.quantity not in _NOT_OPTION_NUMBERS]
    chosen = sorted(own, key=number_rank)[:limit]
    if not chosen:
        return {"numbers": {}}
    day = chosen[0].as_of
    return {"as_of": day.isoformat(),
            "numbers": {n.key: [n.value, n.unit, n.evidence_id]
                        + ([n.as_of.isoformat()] if n.as_of != day else []) for n in chosen}}


def _option(o: OptionFacts) -> dict:
    """A selected option or the baseline: what the text says about it."""
    out = {"option_id": o.option_id, "label": o.label, "name": o.name, "kind": o.kind,
           "fx": o.fx,
           "reasons": [x[2] for x in o.reasons if is_quotable(x)][:MAIN_REASONS],
           "fits": [k for k, v, _ in o.reasons if k in INTERNAL_PARTS and v > 0],
           **_numbers(o, SELECTED_NUMBERS)}
    if o.warnings:
        out["warnings"] = list(o.warnings)
    if o.rm_note:
        out["rm_onay_notu"] = o.rm_note
    return out


def _short(o: OptionFacts) -> dict:
    """An alternative or a talking-point option: id, label, kind and a few numbers."""
    return {"option_id": o.option_id, "label": o.label, "kind": o.kind, "fx": o.fx,
            **_numbers(o, ALTERNATIVE_NUMBERS)}


def _risk(risk: RiskFacts | None, lang: str) -> dict:
    """N13: the risk line of a selected option for the prompt."""
    if risk is None:
        return {}
    return {"risk": {"access": risk.access,
                     "access_slow": bool(risk.access_days and risk.access_days > 0),
                     "fees": {n.quantity: n.value for n in risk.fees},
                     "note": risk.note.get(lang, ""), "cite": list(risk.evidence_ids)}}


def prompt_facts(f: Facts, lang: str = "TR") -> dict:
    """The facts pack as the LLM sees it (N8, N7): only what the text needs.
    Alternatives with label, kind, id and ALTERNATIVE_NUMBERS key numbers; no
    internal values (scores, confidence, internal-part reason texts, data-quality
    details, rejected counts). Every number and id in it is in the full Facts,
    which the validator checks against."""
    return {
        "run_id": f.run_id,
        "client": {k: list(v) if isinstance(v, tuple) else v for k, v in f.client.items()
                   if k != "rm_notu"},
        "dosyadaki_not": f.client["rm_notu"],
        "rm_onay_notu": f.rm_note,
        "talking_points": [{"title": t.title, "figure": t.figure, "text": t.text,
                            "option_ids": list(t.option_ids),
                            "evidence_ids": list(t.evidence_ids)} for t in f.talking_points],
        "talking_point_options": [_short(o) for o in f.talked],
        "baseline": _option(f.baseline) if f.baseline else None,
        "selected": [{**_option(o), "why": [list(w) for w in f.why.get(o.option_id, ())],
                      **_risk(f.risks.get(o.option_id), lang)} for o in f.selected],
        "market": {n.name: [n.value, n.unit, n.evidence_id, n.as_of.isoformat()]
                   for n in f.market},
        "unmatched_priorities": list(f.unmatched_priorities),
        "allocation": [{"class": a.asset_class, "band_low": a.band_low, "band_high": a.band_high,
                        "current": a.current, "source": a.source, "gap": a.gap,
                        "active": a.active} for a in f.allocation],         # N15
        "alternatives": [_short(o) for o in f.alternatives],
        "groups": [{"key": g.key, "selected": list(g.selected),
                    "alternatives": list(g.alternatives)} for g in f.groups],
        "warnings": [{"code": w.code, "message": w.message, "option_ids": list(w.option_ids),
                      "numbers": {n.key: [n.value, n.unit, n.evidence_id, n.as_of.isoformat()]
                                  for n in w.numbers[:ALTERNATIVE_NUMBERS]}}
                     for w in f.warnings],
        "assumptions": list(f.assumptions),
        "open_questions": list(f.open_questions),
    }


def facts_block(f: Facts, lang: str = "TR") -> str:
    """The prompt pack as stable, compact JSON bytes (same facts -> same prompt
    cache prefix)."""
    return json.dumps(prompt_facts(f, lang), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def build_request(f: Facts, lang: str, config: NarratorConfig, *, previous: str | None = None,
                  findings: Sequence[str] = ()) -> LlmRequest:
    blocks = [facts_block(f, lang), _TASK.format(lang=lang, run_id=f.run_id)]
    if previous is not None:
        blocks.append(_RETRY.format(previous=previous,
                                    findings="\n".join(f"- {x}" for x in findings)))
    return LlmRequest(system=system_prompt(lang, config), user_blocks=tuple(blocks),
                      schema=SCHEMA)


def sections_json(sections: Sequence[NarrativeSection],
                  need_tags: Mapping[str, Sequence[str]] | None = None) -> str:
    """Sections and need tags in the shape of SCHEMA (the reply format; used for
    tests and the template)."""
    data = {"sentences": [{"section": s.key, "text": x.text, "title": x.title,
                           "cite": [*x.option_ids, *x.evidence_ids]}
                          for s in sections for x in s.sentences],
            "need_tags": [{"option_id": k, "tags": list(v)} for k, v in (need_tags or {}).items()]}
    return json.dumps(data, ensure_ascii=False)


def _ids(v, where: str) -> tuple[str, ...]:
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ValueError(f"{where}: must be a list of strings")
    return tuple(v)


def parse_sections(text: str) -> tuple[NarrativeSection, ...]:
    """The reply JSON as sections, in the contract order (sentences keep their
    order within a section); a missing section is empty (the validator reports
    it). "cite" splits into option ids (with a ":") and evidence ids.
    ValueError on any other shape."""
    items = _load(text).get("sentences", [])
    if not isinstance(items, list):
        raise ValueError("sentences: must be a list")
    by_key: dict[str, list[NarrativeSentence]] = {k: [] for k in SECTIONS}
    for i, s in enumerate(items):
        where = f"sentences[{i}]"
        if not isinstance(s, dict) or not isinstance(s.get("text"), str):
            raise ValueError(f"{where}: needs a text string")
        if s.get("section") not in by_key:
            raise ValueError(f"{where}: unknown section {s.get('section')!r}")
        title = s.get("title", "")
        if not isinstance(title, str):
            raise ValueError(f"{where}: title must be a string")
        cite = _ids(s.get("cite", []), where)
        by_key[s["section"]].append(NarrativeSentence(
            s["text"], tuple(c for c in cite if ":" in c), tuple(c for c in cite if ":" not in c),
            title.strip()))
    return tuple(NarrativeSection(k, tuple(v)) for k, v in by_key.items())


def parse_need_tags(text: str) -> dict[str, tuple[str, ...]]:
    """The need tags of the reply: option_id -> tags as written by the LLM
    (the validator checks them against the persona). ValueError on a bad shape."""
    items = _load(text).get("need_tags", [])
    if not isinstance(items, list):
        raise ValueError("need_tags: must be a list")
    out: dict[str, tuple[str, ...]] = {}
    for i, item in enumerate(items):
        where = f"need_tags[{i}]"
        if not isinstance(item, dict) or not isinstance(item.get("option_id"), str):
            raise ValueError(f"{where}: needs an option_id string")
        out[item["option_id"]] = _ids(item.get("tags", []), where)
    return out


def _load(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"not JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("the reply must be a JSON object")
    return data
