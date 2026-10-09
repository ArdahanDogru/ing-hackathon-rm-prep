"""Draft v0 contracts (decision / UI) and the shared fixtures in fixtures/."""

import dataclasses
import json
from datetime import datetime
from pathlib import Path

import pytest

from rmprep.contracts import (
    TR_TZ,
    Backend,
    ClarificationQuestion,
    ConstraintResult,
    DecisionResult,
    DecisionState,
    EvidenceSet,
    Persona,
    ProductOption,
    RejectedOption,
    RmStatus,
    ScoredOption,
)

FIX = Path(__file__).resolve().parent / "fixtures"
SCHEMA = Path(__file__).resolve().parents[3] / "persona_schema.json"


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


# --- persona -------------------------------------------------------------------

@pytest.mark.parametrize("name", [f"p0{i}.json" for i in range(1, 6)])
def test_every_persona_fixture_loads(name):
    p = Persona.from_dict(_load(f"personas/{name}"))
    assert p.persona_id == f"P0{name[2]}"
    assert Persona.from_dict(p.to_dict()) == p


def test_persona_fields_match_the_schema():
    if not SCHEMA.exists():
        pytest.skip("persona_schema.json is outside this checkout")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    fields = {f.name for f in dataclasses.fields(Persona)}
    assert fields == set(schema["properties"])


def test_persona_rejects_missing_and_unknown_keys():
    d = _load("personas/p01.json")
    with pytest.raises(ValueError, match="missing"):
        Persona.from_dict({k: v for k, v in d.items() if k != "risk_profili"})
    with pytest.raises(ValueError, match="unknown"):
        Persona.from_dict({**d, "risk": "x"})
    with pytest.raises(ValueError, match="yas"):
        Persona.from_dict({**d, "yas": "62"})


# --- evidence ------------------------------------------------------------------

def test_evidence_fixture_round_trips():
    d = _load("evidence_small.json")
    ev = EvidenceSet.from_dict(d)
    assert ev.to_dict() == d
    assert [dp.id for dp in ev.datapoints] == sorted(dp.id for dp in ev.datapoints)
    assert ev.source_status["evds"].status == "ok"


# --- decision ------------------------------------------------------------------

@pytest.mark.parametrize("name", ["decision_p01_needs_input.json", "decision_p03_ready.json"])
def test_decision_fixtures_round_trip_and_cite_real_evidence(name):
    d = _load(name)
    r = DecisionResult.from_dict(d)
    assert r.to_dict() == d
    ev = EvidenceSet.from_dict(_load("evidence_small.json"))
    assert r.snapshot_id == ev.snapshot_id
    assert r.evidence_ids() <= {dp.id for dp in ev.datapoints}


def test_fixtures_cover_both_states():
    states = {DecisionResult.from_dict(_load(n)).state
              for n in ("decision_p01_needs_input.json", "decision_p03_ready.json")}
    assert states == {DecisionState.NEEDS_RM_INPUT, DecisionState.READY}


def _result(**kw):
    base = dict(run_id="R1", config_hash="h", created_at=datetime(2026, 10, 10, tzinfo=TR_TZ),
                persona_id="P01", snapshot_id="S1", excluded_sources=frozenset(),
                state=DecisionState.READY)
    base.update(kw)
    return DecisionResult(**base)


def _opt(score, **kw):
    return ScoredOption(ProductOption("x", "fund", "X"), score, {"a": score}, (), 0.5, 0.5, **kw)


def test_decision_invariants():
    q_open = ClarificationQuestion("q", "?", "why")
    with pytest.raises(ValueError, match="unanswered"):
        _result(state=DecisionState.NEEDS_RM_INPUT)
    with pytest.raises(ValueError, match="ready with"):
        _result(questions=(q_open,))
    with pytest.raises(ValueError, match="approved"):
        _result(state=DecisionState.NEEDS_RM_INPUT, questions=(q_open,), rm_status=RmStatus.APPROVED)
    with pytest.raises(ValueError, match="ranked"):
        _result(options=(_opt(0.2), _opt(0.9)))
    with pytest.raises(ValueError, match="timezone"):
        _result(created_at=datetime(2026, 10, 10))
    assert _result(rm_status=RmStatus.APPROVED).rm_status == "approved"


def test_option_invariants():
    with pytest.raises(ValueError, match="confidence"):
        ScoredOption(ProductOption("x", "fund", "X"), 1.0, {}, (), 1.5, 0.5)
    with pytest.raises(ValueError, match="pass all"):
        ScoredOption(ProductOption("x", "fund", "X"), 1.0, {}, (ConstraintResult("r", False, "no"),), 1, 1)
    with pytest.raises(ValueError, match="failed"):
        RejectedOption(ProductOption("x", "fund", "X"), ())


def test_backend_protocol_has_the_rm_loop_stubs():
    names = {n for n in dir(Backend) if not n.startswith("_")}
    assert {"list_personas", "list_snapshots", "evidence", "decide", "answer_question", "approve"} <= names
