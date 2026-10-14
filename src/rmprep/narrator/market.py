"""N14: the market note, the code-written block piyasa_notu after ozet (docs/narrator.md).

One sentence per series of config market_note.series (TCMB EVDS: policy rate,
USD/TRY, funding cost), each with the evidence id of its value; a missing
series is left out, none at all -> no block. The LLM does not write it, so the
validator has nothing to check in it; the RM can edit or delete it like any
block."""

from __future__ import annotations

import dataclasses

from rmprep.contracts import EvidenceSet, NarrativeDraft, NarrativeSection, NarrativeSentence
from rmprep.decision.universe import EvidenceIndex
from rmprep.narrator.config import NarratorConfig
from rmprep.narrator.template import MARKET_NOTE, fmt_date, fmt_number


def market_note_sentences(ev: EvidenceSet | None, config: NarratorConfig,
                          lang: str) -> tuple[NarrativeSentence, ...]:
    """The sentences of the block: the latest usable value of each series."""
    note = config.market_note
    if note is None or ev is None:
        return ()
    idx, out = EvidenceIndex(ev), []
    for s in note.series:
        d = idx.get(s.quantity, s.entity)
        if d is None or d.value is None:
            continue
        text = note.sentence[lang].format(label=s.label[lang],
                                          value=fmt_number(d.value, s.unit, lang),
                                          date=fmt_date(d.as_of, lang))
        out.append(NarrativeSentence(text, (), (d.id,)))
    return tuple(out)


def with_market_note(d: NarrativeDraft, ev: EvidenceSet | None,
                     config: NarratorConfig) -> NarrativeDraft:
    """d with the block piyasa_notu right after ozet (an old one replaced); no
    value -> no block."""
    rest = tuple(s for s in d.sections if s.key != MARKET_NOTE)
    sentences = market_note_sentences(ev, config, d.lang)
    if not sentences:
        return dataclasses.replace(d, sections=rest)
    at = next((i + 1 for i, s in enumerate(rest) if s.key == "ozet"), 0)
    section = NarrativeSection(MARKET_NOTE, sentences)
    return dataclasses.replace(d, sections=(*rest[:at], section, *rest[at:]))
