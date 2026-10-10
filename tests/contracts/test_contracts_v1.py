"""Frozen v1 contracts (decision / UI) and the shared fixtures in fixtures/."""

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
    DecisionWarning,
    EntityInfo,
    EvidenceSet,
    Persona,
    ProductOption,
    RejectedOption,
    RmStatus,
    ScoredOption,
)

FIX = Path(__file__).resolve().parent / "fixtures"
SCHEMA = Path(__file__).resolve().parents[3] / "persona_schema.json"
DECISIONS = ["decision_p02_ready.json", "decision_p03_ready.json", "decision_test_needs_input.json"]


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

@pytest.mark.parametrize("name", ["evidence_small.json", "evidence_medium.json"])
def test_evidence_fixture_round_trips(name):
    d = _load(name)
    ev = EvidenceSet.from_dict(d)
    assert ev.to_dict() == d
    assert [dp.id for dp in ev.datapoints] == sorted(dp.id for dp in ev.datapoints)
    assert ev.source_status["evds"].status == "ok"
    funds = {dp.entity for dp in ev.datapoints if dp.quantity.startswith("fund_")}
    assert set(ev.entities) <= funds
    assert all(isinstance(e, EntityInfo) and e.source == "tefas_web" for e in ev.entities.values())


def test_medium_evidence_covers_the_decision_cases():
    ev = EvidenceSet.from_dict(_load("evidence_medium.json"))
    funds = {dp.entity for dp in ev.datapoints if dp.quantity.startswith("fund_")}
    risk = {dp.entity for dp in ev.datapoints if dp.quantity == "fund_risk_level"}
    cats = {e.category for e in ev.entities.values()}
    assert len(funds) >= 30
    assert len(cats) == 9                                   # 8 kinds + Serbest
    assert funds - set(ev.entities)                         # a fund without entity info
    assert {c for c in funds if c in ev.entities} - risk    # a fund without a risk level
    assert any("DÖVİZ" in e.name or "EUROBOND" in e.name for e in ev.entities.values())


def test_evidence_without_entities_still_loads():
    d = _load("evidence_small.json")
    d.pop("entities")
    assert EvidenceSet.from_dict(d).entities == {}


# --- decision fixtures -----------------------------------------------------------

@pytest.mark.parametrize("name", DECISIONS)
def test_decision_fixtures_round_trip_and_cite_real_evidence(name):
    d = _load(name)
    r = DecisionResult.from_dict(d)
    assert r.to_dict() == d
    ev = EvidenceSet.from_dict(_load("evidence_medium.json"))
    assert r.snapshot_id == ev.snapshot_id
    assert r.evidence_ids() <= {dp.id for dp in ev.datapoints}


def test_fixtures_cover_both_states_and_a_non_blocking_question():
    rs = [DecisionResult.from_dict(_load(n)) for n in DECISIONS]
    assert {r.state for r in rs} == {DecisionState.NEEDS_RM_INPUT, DecisionState.READY}
    assert any(r.state == DecisionState.READY and any(q.answer is None and not q.blocking
                                                      for q in r.questions) for r in rs)
    assert all(r.options[0].option.kind == "deposit" for r in rs if r.options)


# --- invariants ------------------------------------------------------------------

P01 = Persona.from_dict(_load("personas/p01.json"))
FUND = ProductOption("fund:X", "fund", "X", "X", "debt")
DEP = ProductOption("deposit:d", "deposit", "D")


def _opt(option=FUND, parts=None, **kw):
    parts = {"return": 0.5} if parts is None else parts
    kw.setdefault("reasons", {k: "r" for k in parts})
    return ScoredOption(option, sum(parts.values()), parts, (), 0.5, 0.5, **kw)


def _result(**kw):
    base = dict(run_id="R1", config_hash="h", created_at=datetime(2026, 10, 10, tzinfo=TR_TZ),
                persona=P01, snapshot_id="S1", excluded_sources=frozenset(),
                state=DecisionState.READY)
    base.update(kw)
    return DecisionResult(**base)


def test_question_states():
    blocking = ClarificationQuestion("q", "?", "why")
    soft = ClarificationQuestion("q2", "?", "why", blocking=False)
    with pytest.raises(ValueError, match="blocking question"):
        _result(state=DecisionState.NEEDS_RM_INPUT)
    with pytest.raises(ValueError, match="blocking question"):
        _result(state=DecisionState.NEEDS_RM_INPUT, questions=(soft,))
    with pytest.raises(ValueError, match="ready with"):
        _result(questions=(blocking,))
    assert _result(questions=(soft,)).state == "ready"
    with pytest.raises(ValueError, match="no options"):
        _result(state=DecisionState.NEEDS_RM_INPUT, questions=(blocking,), options=(_opt(),))
    with pytest.raises(ValueError, match="not one of"):
        ClarificationQuestion("q", "?", "why", choices=("a", "b"), answer="c")


def test_options_order_and_ids():
    assert _result(options=(_opt(DEP), _opt(FUND, {"return": 0.9}))).persona_id == "P01"
    with pytest.raises(ValueError, match="deposit"):
        _result(options=(_opt(FUND), _opt(DEP)))
    with pytest.raises(ValueError, match="unique"):
        _result(options=(_opt(), _opt()))
    with pytest.raises(ValueError, match="unknown options"):
        _result(options=(_opt(),), warnings=(DecisionWarning("fx_exposure", "m", (), ("fund:Y",)),))
    with pytest.raises(ValueError, match="timezone"):
        _result(created_at=datetime(2026, 10, 10))


def test_rm_approval():
    opts = (_opt(DEP), _opt(FUND))
    ok = _result(options=opts, rm_status=RmStatus.APPROVED, rm_selected=("fund:X",),
                 rm_option_notes={"fund:X": "n"})
    assert ok.rm_status == "approved"
    with pytest.raises(ValueError, match="at least one"):
        _result(options=opts, rm_status=RmStatus.APPROVED)
    with pytest.raises(ValueError, match="only on approval"):
        _result(options=opts, rm_selected=("fund:X",))
    with pytest.raises(ValueError, match="not scored"):
        _result(options=opts, rm_status=RmStatus.APPROVED, rm_selected=("fund:Z",))
    with pytest.raises(ValueError, match="selected options"):
        _result(options=opts, rm_status=RmStatus.APPROVED, rm_selected=("fund:X",),
                rm_option_notes={"deposit:d": "n"})
    with pytest.raises(ValueError, match="approved"):
        _result(state=DecisionState.NEEDS_RM_INPUT, questions=(ClarificationQuestion("q", "?", "w"),),
                rm_status=RmStatus.APPROVED)


def test_option_invariants():
    with pytest.raises(ValueError, match="confidence"):
        ScoredOption(FUND, 1.0, {"a": 1.0}, (), 1.5, 0.5, reasons={"a": "r"})
    with pytest.raises(ValueError, match="pass all"):
        ScoredOption(FUND, 1.0, {"a": 1.0}, (ConstraintResult("r", False, "no"),), 1, 1,
                     reasons={"a": "r"})
    with pytest.raises(ValueError, match="sum to score"):
        ScoredOption(FUND, 0.9, {"a": 0.5, "penalty:x": -0.1}, (), 1, 1,
                     reasons={"a": "r", "penalty:x": "r"})
    with pytest.raises(ValueError, match="reasons"):
        ScoredOption(FUND, 0.5, {"a": 0.5}, (), 1, 1)
    with pytest.raises(ValueError, match="failed"):
        RejectedOption(FUND, ())
    with pytest.raises(ValueError, match="fund_kind"):
        ProductOption("fund:X", "fund", "X")
    with pytest.raises(ValueError, match="deposit option"):
        ProductOption("deposit:d", "deposit", "D", fx=True)
    with pytest.raises(ValueError, match="kind"):
        ProductOption("gold:x", "gold", "G")


def test_backend_protocol_has_the_rm_loop():
    names = {n for n in dir(Backend) if not n.startswith("_")}
    assert {"list_personas", "list_snapshots", "evidence", "decide", "answer_question",
            "approve", "annotate", "save_card"} <= names


def test_time_deposit_kind_v1_1():
    td = ProductOption("time_deposit:ing_e_vadeli", "time_deposit", "ING e-Vadeli Mevduat (32-45 gün)")
    assert td.kind == "time_deposit"
    with pytest.raises(ValueError, match="time_deposit option"):
        ProductOption("time_deposit:x", "time_deposit", "T", fund_kind="debt")
    with pytest.raises(ValueError, match="time_deposit option"):
        ProductOption("time_deposit:x", "time_deposit", "T", fx=True)
    # a time deposit is ranked like a fund: it may stand anywhere after the baseline
    ScoredOption(td, 0.5, {"a": 0.5}, (), 1, 1, reasons={"a": "r"})
