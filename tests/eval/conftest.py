"""Shared helpers of the eval tests: a RealBackend root in tmp_path on the
fixture evidence (no snapshot, no network) and a fake narrator."""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from pathlib import Path

import pytest

from rmprep import backend as be
from rmprep.contracts import (
    TR_TZ, EvidenceSet, NarrativeDraft, NarrativeSection, NarrativeSentence, SourceStatus,
)

PROJECT = Path(__file__).resolve().parents[2]
CONTRACT_FIX = PROJECT / "tests" / "contracts" / "fixtures"
FIX = Path(__file__).resolve().parent / "fixtures"
T0 = datetime(2026, 10, 10, 9, 0, tzinfo=TR_TZ)
SNAP = "20261010-001233-6b20"


def fixture_evidence() -> EvidenceSet:
    d = json.loads((CONTRACT_FIX / "evidence_medium.json").read_text(encoding="utf-8"))
    return EvidenceSet.from_dict(d)


@pytest.fixture
def builds() -> list:
    return []


@pytest.fixture
def extra_rows() -> list:
    """DataPoints a test adds to the fixture evidence (before the backend builds it)."""
    return []


@pytest.fixture
def dropped_rows() -> list:
    """Predicates on DataPoints: matching fixture rows are removed."""
    return []


@pytest.fixture
def renamed() -> dict:
    """entity -> new fund name in EvidenceSet.entities."""
    return {}


@pytest.fixture
def root(monkeypatch, tmp_path, builds, extra_rows, dropped_rows, renamed):
    """A project root with config/ copied; build_evidence serves the fixture
    evidence (minus `dropped_rows`, plus `extra_rows` - a new source gets status
    ok -, entities renamed by `renamed`) and records its calls in `builds`."""
    base = fixture_evidence()

    def fake_build(snapshots, snapshot_id, exclude=frozenset()):
        status = dict(base.source_status)
        for d in extra_rows:
            status.setdefault(d.source, SourceStatus("ok"))
        rows = tuple(d for d in base.datapoints if not any(f(d) for f in dropped_rows))
        entities = {k: dataclasses.replace(v, name=renamed.get(k, v.name))
                    for k, v in base.entities.items()}
        ev = dataclasses.replace(base, source_status=status, entities=entities,
                                 datapoints=rows + tuple(extra_rows))
        if snapshot_id != ev.snapshot_id:
            raise ValueError(f"no snapshot {snapshot_id}")
        unknown = set(exclude) - set(ev.source_status)
        if unknown:
            raise ValueError(f"unknown sources {sorted(unknown)}")
        builds.append((snapshot_id, frozenset(exclude)))
        return dataclasses.replace(ev, excluded_sources=frozenset(exclude))

    class Snap:
        snapshot_id = base.snapshot_id

    monkeypatch.setattr(be, "build_evidence", fake_build)
    monkeypatch.setattr(be, "list_snapshots", lambda snapshots: [Snap()])
    (tmp_path / "config").mkdir()
    for name in ("decision.yaml", "narrator.yaml", "eval.yaml"):
        (tmp_path / "config" / name).write_bytes((PROJECT / "config" / name).read_bytes())
    return tmp_path


class FakeNarrator:
    """Narrator.draft without an LLM: one sentence per selected option, cached
    per (run_id, lang) like the real one; each new text costs `cost`."""

    def __init__(self, cost: float = 0.0, text: str = "Seçilen ürün: {label}."):
        self.cost = cost
        self.text = text
        self.calls: list[tuple[str, str]] = []
        self.cache: dict[tuple[str, str], NarrativeDraft] = {}
        self.spent = 0.0

    def spent_today(self) -> float:
        return self.spent

    def draft(self, r, ev, lang):
        key = (r.run_id, lang)
        if key in self.cache:
            return self.cache[key]
        self.calls.append(key)
        self.spent += self.cost
        labels = {o.option.option_id: o.option.label for o in r.options}
        sentences = tuple(NarrativeSentence(self.text.format(label=labels[i]), (i,))
                          for i in r.rm_selected)
        d = NarrativeDraft(r.run_id, lang, (NarrativeSection("oneriler", sentences),),
                           "llm", "fake-model", "fake", (), T0, cost_usd=self.cost)
        self.cache[key] = d
        return d
