"""Per-block edits of the meeting text (docs/web-ui.md "Section-by-section
editing"; contract v1.5; lead-owned glue).

The narrator owns the real block rules (milestone N11: rmprep.narrator.blocks
with block_ids, check_block and an edit-aware to_markdown). Until that module
exists, this file gives a stand-in with the same names, so the backends and the
API work; the stand-in check finds only forbidden phrases.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import yaml

from rmprep.contracts import NarrativeDraft, NarrativeSection, NarrativeSentence

WHOLE_SECTIONS = ("ozet", "teklif_metni", "dikkat", "alternatifler", "sorular", "varsayimlar")
_CONFIG = Path(__file__).resolve().parents[2] / "config" / "narrator.yaml"

try:                                    # the narrator's rules, once N11 is merged
    from rmprep.narrator import blocks as _narrator_blocks
except ImportError:                     # pragma: no cover - depends on the merge state
    _narrator_blocks = None


def _sentences(d: NarrativeDraft, key: str) -> tuple[NarrativeSentence, ...]:
    return next((s.sentences for s in d.sections if s.key == key), ())


def block_ids(d: NarrativeDraft) -> tuple[str, ...]:
    if _narrator_blocks is not None:
        return tuple(_narrator_blocks.block_ids(d))
    ids = [k for k in WHOLE_SECTIONS if _sentences(d, k)]
    ids += [f"talking_points:{i}" for i, _ in enumerate(_sentences(d, "talking_points"))]
    seen = []
    for s in _sentences(d, "oneriler"):
        if s.option_ids and s.option_ids[0] not in seen:
            seen.append(s.option_ids[0])
    ids += [f"oneriler:{o}" for o in seen]
    return tuple(ids)


def _block_of(key: str, i: int, s: NarrativeSentence) -> str | None:
    if key in WHOLE_SECTIONS:
        return key
    if key == "talking_points":
        return f"talking_points:{i}"
    if key == "oneriler" and s.option_ids:
        return f"oneriler:{s.option_ids[0]}"
    return None


def apply_edits(d: NarrativeDraft) -> NarrativeDraft:
    """The draft with each edited block written as one sentence (rm_edits then
    empty), for any renderer that does not know the edits."""
    if not d.rm_edits:
        return d
    sections = []
    for sec in d.sections:
        out, done = [], set()
        for i, s in enumerate(sec.sentences):
            block = _block_of(sec.key, i, s)
            if block in d.rm_edits:
                if block not in done:
                    done.add(block)
                    out.append(NarrativeSentence(d.rm_edits[block], s.option_ids, s.evidence_ids, s.title))
                continue
            out.append(s)
        sections.append(NarrativeSection(sec.key, tuple(out)))
    return dataclasses.replace(d, sections=tuple(sections), rm_edits={})


def _phrases(lang: str) -> tuple[str, ...]:
    try:
        raw = yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))
        return tuple(raw["forbidden_phrases"][lang])
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        return ("garanti", "kesin getiri", "risksiz")


def _tr_lower(text: str) -> str:
    return text.replace("İ", "i").replace("I", "ı").lower()


def check_block(d: NarrativeDraft, result, evidence, block_id: str, text: str) -> tuple[str, ...]:
    if _narrator_blocks is not None:
        return tuple(_narrator_blocks.check_block(d, result, evidence, block_id, text))
    low = _tr_lower(text)
    return tuple(f"phrase: '{p}' kullanılmamalı" for p in _phrases(d.lang) if _tr_lower(p) in low)


def with_edit(d: NarrativeDraft, block_id: str, text: str | None,
              findings: tuple[str, ...]) -> NarrativeDraft:
    """d with one block set (text) or restored (None); its findings replaced."""
    if block_id not in block_ids(d):
        raise ValueError(f"unknown block {block_id!r}; known: {', '.join(block_ids(d))}")
    edits, checks = dict(d.rm_edits), dict(d.edit_checks)
    if text is None:
        edits.pop(block_id, None)
        checks.pop(block_id, None)
    else:
        if not text.strip():
            raise ValueError("boş metin: use null to restore the original block")
        edits[block_id] = text.strip()
        if findings:
            checks[block_id] = tuple(findings)
        else:
            checks.pop(block_id, None)
    return dataclasses.replace(d, rm_edits=edits, edit_checks=checks)
