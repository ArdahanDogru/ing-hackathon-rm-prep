"""Blocks of the meeting text and the check of one edited block (contract v1.5;
docs/web-ui.md "Section-by-section editing"; narrator N11). rmprep.edits (lead
glue) calls block_ids and check_block.

Blocks: the whole sections ozet, teklif_metni, dikkat, alternatifler, sorular,
varsayimlar; talking_points:<i>; oneriler:<first option id of the sentence>.
The check runs the validator rules that apply to one text: phrase, option
(short names too), internal, label (these block the approval) and number (a
warning). Each finding is "<kind>: <message>" in the draft's language, for the RM."""

from __future__ import annotations

import re

from rmprep.contracts import (
    DecisionResult,
    EvidenceSet,
    NarrativeDraft,
    NarrativeSection,
    NarrativeSentence,
)
from rmprep.narrator.config import NarratorConfig, load_config
from rmprep.narrator.facts import build_facts
from rmprep.narrator.template import WHOLE_SECTIONS, block_of
from rmprep.narrator.validator import block_findings

__all__ = ["block_ids", "block_text", "check_block", "WHOLE_SECTIONS"]


def _sentences_by_block(d: NarrativeDraft) -> dict[str, list[NarrativeSentence]]:
    """Block id -> its sentences, in the order of block_ids."""
    out: dict[str, list[NarrativeSentence]] = {}
    by_key = {sec.key: sec.sentences for sec in d.sections}
    for key in WHOLE_SECTIONS:
        if by_key.get(key):
            out[key] = list(by_key[key])
    for i, s in enumerate(by_key.get("talking_points", ())):
        out[f"talking_points:{i}"] = [s]
    for i, s in enumerate(by_key.get("oneriler", ())):
        block = block_of("oneriler", i, s)
        if block is not None:
            out.setdefault(block, []).append(s)
    return out


def block_ids(d: NarrativeDraft) -> tuple[str, ...]:
    return tuple(_sentences_by_block(d))


def _sentences(d: NarrativeDraft, block_id: str) -> list[NarrativeSentence]:
    blocks = _sentences_by_block(d)
    if block_id not in blocks:
        raise ValueError(f"unknown block {block_id!r}; known: {', '.join(blocks)}")
    return blocks[block_id]


def block_text(d: NarrativeDraft, block_id: str) -> str:
    """The original plain text of a block (its sentences, one space apart)."""
    return " ".join(s.text for s in _sentences(d, block_id))


# --- messages for the RM ------------------------------------------------------------------

_MESSAGES = {   # (kind, pattern of the validator message) -> text per language
    ("number", r"date (?P<x>\S+) is not in the facts"): {
        "TR": "{x} tarihi olgularda yok", "EN": "the date {x} is not in the facts"},
    ("number", r"(?P<x>\S+) is not in the facts"): {
        "TR": "{x} olgularda yok", "EN": "{x} is not in the facts"},
    ("internal", r"(?P<x>\S+) is an internal value"): {
        "TR": "{x} iç bir değer (puan, sayı ya da veri kalitesi ayrıntısı); metinde olmamalı",
        "EN": "{x} is an internal value (a score, a count or a data-quality detail); "
              "not for the text"},
    ("internal", r'internal name "(?P<x>[^"]+)"'): {
        "TR": "'{x}' iç bir ad; metinde olmamalı", "EN": "'{x}' is an internal name; not for the text"},
    ("internal", r'the screen section "(?P<x>[^"]+)"'): {
        "TR": "'{x}' bir ekran bölümünün adı; metinde olmamalı",
        "EN": "'{x}' is the name of a screen section; not for the text"},
    ("option", r"names (?P<x>\S+), which"): {
        "TR": "{x} bu metinde anılamaz: seçilen bir seçenek, karşılaştırma ölçütü ya da grup "
              "alternatifi değil",
        "EN": "{x} may not be named here: it is not a selected option, the baseline or a group "
              "alternative"},
    ("phrase", r'forbidden phrase "(?P<x>[^"]+)"'): {
        "TR": "'{x}' kullanılmamalı", "EN": "'{x}' must not be used"},
    ("label", r"(?P<x>\S+) is not an ING rate"): {
        "TR": "{x} bir ING faizi değil; ING ürün adının yanında olmamalı",
        "EN": "{x} is not an ING rate; it must not stand next to an ING product name"},
}


def _for_rm(finding: str, lang: str, labels: dict[str, str]) -> str:
    """'<kind>: <section>: <English detail>' of the validator -> '<kind>: <message>'."""
    kind, _, rest = finding.partition(": ")
    detail = rest.partition(": ")[2] or rest
    for (k, pattern), texts in _MESSAGES.items():
        if k != kind:
            continue
        m = re.match(pattern, detail)
        if m:
            x = m.group("x")
            return f"{kind}: {texts[lang].format(x=labels.get(x, x))}"
    return f"{kind}: {detail}"


def check_block(d: NarrativeDraft, r: DecisionResult, ev: EvidenceSet | None, block_id: str,
                text: str, config: NarratorConfig | None = None) -> tuple[str, ...]:
    """Findings of one edited block: "<kind>: <message>", kinds phrase, option,
    internal, label (block the approval) and number (a warning). () = clean.
    ev None (FakeBackend): an empty evidence set; numbers then only warn."""
    original = _sentences(d, block_id)          # ValueError for an unknown block
    key = block_id.split(":", 1)[0]
    ids = tuple(dict.fromkeys(i for s in original for i in s.option_ids))
    evidence = tuple(dict.fromkeys(i for s in original for i in s.evidence_ids))
    section = NarrativeSection(key, (NarrativeSentence(text, ids, evidence),))
    if ev is None:
        ev = EvidenceSet(snapshot_id=r.snapshot_id, created_at=r.created_at,
                         excluded_sources=frozenset(), source_status={}, datapoints=())
    f = build_facts(r, ev)
    findings = block_findings([section], f, r, config or load_config())
    labels = {o.option.option_id: o.option.label for o in (*r.options, *r.rejected)}
    return tuple(dict.fromkeys(_for_rm(x, d.lang, labels) for x in findings))
