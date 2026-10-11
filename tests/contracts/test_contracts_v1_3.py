"""Contract v1.3 (docs/web-ui.md section 3): warning audience, talking points,
to_confirm; narrator talking_points, title, need_tags. All additive."""

import dataclasses
import json
from pathlib import Path

import pytest

from rmprep.contracts import (
    NARRATIVE_SECTIONS,
    NARRATIVE_SECTIONS_V13,
    WARNING_AUDIENCES,
    DecisionResult,
    DecisionWarning,
    NarrativeDraft,
    NarrativeSection,
    NarrativeSentence,
    TalkingPoint,
)

FIX = Path(__file__).resolve().parent / "fixtures"


def _ready() -> DecisionResult:
    return DecisionResult.from_dict(
        json.loads((FIX / "decision_p02_ready.json").read_text(encoding="utf-8")))


def _strip(d):
    """The JSON of a v1.2 object: without the v1.3 keys, at any depth."""
    if isinstance(d, dict):
        return {k: _strip(v) for k, v in d.items()
                if k not in ("audience", "talking_points", "to_confirm")}
    if isinstance(d, list):
        return [_strip(x) for x in d]
    return d


def test_v12_json_loads_with_defaults():
    r = DecisionResult.from_dict(_strip(_ready().to_dict()))
    assert r.talking_points == () and r.to_confirm == ()
    assert {w.audience for w in r.warnings} == {"rm"}


def test_warning_audience_default_and_check():
    assert WARNING_AUDIENCES == ("client", "rm")
    assert DecisionWarning(code="x", message="m").audience == "rm"
    assert DecisionWarning(code="x", message="m", audience="client").audience == "client"
    with pytest.raises(ValueError):
        DecisionWarning(code="x", message="m", audience="everyone")


@pytest.mark.parametrize("field", ["code", "label", "figure", "text"])
def test_talking_point_needs_its_texts(field):
    kw = dict(code="access", label="Paraya erişim", figure="Aynı gün", text="T")
    kw[field] = " "
    with pytest.raises(ValueError):
        TalkingPoint(**kw)


def test_talking_points_round_trip_limit_and_known_options():
    r = _ready()
    oid = r.options[-1].option.option_id
    tp = TalkingPoint(code="access", label="L", figure="Aynı gün", text="T",
                      evidence_ids=("e1",), option_ids=(oid,))
    ok = dataclasses.replace(r, talking_points=(tp, tp, tp), to_confirm=("Tutarı sorun.",))
    assert DecisionResult.from_dict(json.loads(json.dumps(ok.to_dict()))) == ok
    with pytest.raises(ValueError, match="at most 3"):
        dataclasses.replace(r, talking_points=(tp,) * 4)
    with pytest.raises(ValueError, match="not scored"):
        dataclasses.replace(r, talking_points=(dataclasses.replace(tp, option_ids=("fund:NOPE",)),))


def test_narrative_v13_fields():
    assert NARRATIVE_SECTIONS_V13 == NARRATIVE_SECTIONS + ("talking_points",)
    assert "talking_points" not in NARRATIVE_SECTIONS       # a v1.2 narrator stays valid
    assert NarrativeSection("talking_points", ()).key == "talking_points"
    assert NarrativeSentence(text="t").title == ""
    fields = {f.name: f for f in dataclasses.fields(NarrativeDraft)}
    assert "need_tags" in fields


def test_narrative_round_trip_and_v12_json():
    from tests.contracts.test_contracts_v1_2 import draft
    tp = NarrativeSentence(text="Mevduat aşınıyor.", title="Enflasyon ve mevduat")
    d = draft(need_tags={"fund:A": ("likiditeyi koruma",)})
    assert NarrativeDraft.from_dict(json.loads(json.dumps(d.to_dict()))) == d
    assert tp.title == "Enflasyon ve mevduat"
    old = d.to_dict()
    old.pop("need_tags")
    assert NarrativeDraft.from_dict(old).need_tags == {}
