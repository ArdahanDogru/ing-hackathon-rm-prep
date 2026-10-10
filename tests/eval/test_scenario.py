"""Scenario files: format, strict loading, persona edits, evidence edits."""

import json
from pathlib import Path

import pytest

from rmprep.contracts import Flag, Persona
from rmprep.eval.scenario import (
    EvidenceEdit, Scenario, ScenarioError, apply_evidence_edits, edit_persona,
    load_scenario_file, load_scenarios, packaged_scenario_files,
)
from tests.eval.conftest import CONTRACT_FIX, fixture_evidence


def _p01() -> Persona:
    return Persona.from_dict(json.loads((CONTRACT_FIX / "personas" / "p01.json").read_text(encoding="utf-8")))


def write(tmp_path: Path, text: str, name: str = "s.yaml") -> Path:
    f = tmp_path / name
    f.write_text(text, encoding="utf-8")
    return f


def test_a_file_loads_with_defaults(tmp_path):
    f = write(tmp_path, """
scenarios:
  - id: base-p01
    group: base
    persona: P01
""")
    [s] = load_scenario_file(f)
    assert s == Scenario(id="base-p01", group="base", persona="P01")
    assert s.repeat == 1 and s.langs == ("TR",) and s.narrate and s.select_top == 3
    assert s.exclude_sources == frozenset() and s.answers == () and s.expect == {}


def test_all_fields_load(tmp_path):
    f = write(tmp_path, """
scenarios:
  - id: edit-p01
    group: persona_edit
    description: "risk up"
    persona: P01
    edit: {risk_profili: Agresif, yas: 40}
    add_constraints: ["döviz maruziyeti istemiyor"]
    exclude_sources: [manual]
    answers: {"q:acik_kisitlar[1]": "Döviz maruziyetini sınırla"}
    snapshot: S1
    evidence_edits:
      - {quantity: fund_risk_level, entity: AFT, value: 9, add_flags: [out_of_range]}
      - {quantity: fund_price, drop: true}
    repeat: 2
    select: ["fund:AFT"]
    langs: [TR, EN]
    narrate: false
    rm_note: "not"
    needs: [D12]
    compare_to: base-p01
    expect: {avg_risk: lower}
""")
    [s] = load_scenario_file(f)
    assert s.edit == {"risk_profili": "Agresif", "yas": 40}
    assert s.add_constraints == ("döviz maruziyeti istemiyor",)
    assert s.exclude_sources == frozenset({"manual"})
    assert s.answers == (("q:acik_kisitlar[1]", "Döviz maruziyetini sınırla"),)
    assert s.evidence_edits == (
        EvidenceEdit(quantity="fund_risk_level", entity="AFT", value=9.0, add_flags=("out_of_range",)),
        EvidenceEdit(quantity="fund_price", drop=True))
    assert (s.snapshot, s.repeat, s.select, s.langs, s.narrate, s.rm_note) == (
        "S1", 2, ("fund:AFT",), ("TR", "EN"), False, "not")
    assert (s.needs, s.compare_to, s.expect) == (("D12",), "base-p01", {"avg_risk": "lower"})


@pytest.mark.parametrize("body, match", [
    ("  - {id: a, group: g, persona: P01, colour: red}", "unknown"),
    ("  - {id: a, group: g}", "persona"),
    ("  - {id: a, group: g, persona: P01, repeat: 0}", "repeat"),
    ("  - {id: a, group: g, persona: P01, langs: [DE]}", "lang"),
    ("  - {id: a, group: g, persona: P01, edit: {persona_id: P02}}", "persona_id"),
    ("  - {id: a, group: g, persona: P01, edit: {hobby: x}}", "hobby"),
    ("  - {id: a, group: g, persona: P01, evidence_edits: [{entity: AFT}]}", "quantity"),
    ("  - {id: a, group: g, persona: P01, evidence_edits: [{quantity: q}]}", "change"),
    ("  - {id: a, group: g, persona: P01, evidence_edits: [{quantity: q, add_flags: [bad]}]}", "flag"),
    ("  - {id: a, group: g, persona: P01, needs: [D99]}", "needs"),
    ("  - {id: a, group: g, persona: P01}\n  - {id: a, group: g, persona: P02}", "duplicate"),
    ("  - {id: 'a b', group: g, persona: P01}", "id"),
])
def test_bad_files_are_rejected(tmp_path, body, match):
    with pytest.raises(ScenarioError, match=match):
        load_scenario_file(write(tmp_path, "scenarios:\n" + body + "\n"))


def test_compare_to_must_exist_in_the_suite(tmp_path):
    a = write(tmp_path, "scenarios:\n  - {id: a, group: g, persona: P01, compare_to: b}\n")
    with pytest.raises(ScenarioError, match="compare_to"):
        load_scenarios([a])
    b = write(tmp_path, "scenarios:\n  - {id: b, group: g, persona: P01}\n", "b.yaml")
    assert [s.id for s in load_scenarios([a, b])] == ["a", "b"]


def test_ids_are_unique_across_files(tmp_path):
    a = write(tmp_path, "scenarios:\n  - {id: a, group: g, persona: P01}\n")
    b = write(tmp_path, "scenarios:\n  - {id: a, group: g, persona: P02}\n", "b.yaml")
    with pytest.raises(ScenarioError, match="duplicate"):
        load_scenarios([a, b])


def test_edit_persona_changes_fields_and_adds_constraints():
    p = _p01()
    s = Scenario(id="x", group="g", persona="P01", edit={"risk_profili": "Agresif"},
                 add_constraints=("yeni kısıt",))
    q = edit_persona(p, s)
    assert q.risk_profili == "Agresif"
    assert q.acik_kisitlar == p.acik_kisitlar + ("yeni kısıt",)
    assert q.persona_id == p.persona_id and q.yas == p.yas
    assert edit_persona(p, Scenario(id="y", group="g", persona="P01")) == p


def test_edit_persona_with_a_bad_value_raises():
    with pytest.raises(ScenarioError, match="yas"):
        edit_persona(_p01(), Scenario(id="x", group="g", persona="P01", edit={"yas": "old"}))


def test_evidence_edits_change_value_and_flags_and_drop_rows():
    ev = fixture_evidence()
    risk = next(d for d in ev.datapoints if d.quantity == "fund_risk_level")
    edits = (EvidenceEdit(quantity="fund_risk_level", entity=risk.entity, value=9.0,
                          add_flags=("out_of_range",)),
             EvidenceEdit(quantity="fund_price", drop=True))
    new = apply_evidence_edits(ev, edits, snapshot_id="S~x")
    assert new.snapshot_id == "S~x" and new.entities == ev.entities
    changed = next(d for d in new.datapoints if d.id == risk.id)
    assert changed.value == 9.0 and Flag.OUT_OF_RANGE in changed.flags
    assert not any(d.quantity == "fund_price" for d in new.datapoints)
    others = [d for d in ev.datapoints if d.quantity not in ("fund_price",) and d.id != risk.id]
    assert all(d in new.datapoints for d in others)


def test_an_evidence_edit_that_matches_nothing_raises():
    with pytest.raises(ScenarioError, match="matches no row"):
        apply_evidence_edits(fixture_evidence(),
                             (EvidenceEdit(quantity="fund_price", entity="NOPE", drop=True),), "S~x")


def test_setting_a_value_on_a_missing_row_clears_the_missing_flag():
    ev = fixture_evidence()
    dp = ev.datapoints[0]
    missing = type(dp)(**{**dp.__dict__, "value": None, "flags": frozenset({Flag.MISSING})})
    ev2 = type(ev)(**{**ev.__dict__, "datapoints": (missing,) + ev.datapoints[1:]})
    new = apply_evidence_edits(ev2, (EvidenceEdit(quantity=dp.quantity, entity=dp.entity,
                                                  source=dp.source, value=1.0),), "S~y")
    got = next(d for d in new.datapoints if d.id == dp.id)
    assert got.value == 1.0 and Flag.MISSING not in got.flags


def test_packaged_scenarios_load():
    files = packaged_scenario_files()
    assert files, "no scenario files in src/rmprep/eval/scenarios"
    suite = load_scenarios(files)
    groups = {s.group for s in suite}
    assert {"base", "persona_edit", "constraint", "data_access", "bad_data"} <= groups
    base = [s for s in suite if s.group == "base"]
    assert sorted(s.persona for s in base) == ["P01", "P02", "P03", "P04", "P05"]
    assert all(s.repeat == 2 for s in base)


def test_top_placeholders_resolve_and_bad_placeholders_are_rejected(tmp_path):
    from rmprep.eval.scenario import resolve_top
    e = (EvidenceEdit(quantity="q", entity="@top2", drop=True), EvidenceEdit(quantity="q", drop=True))
    assert resolve_top(e, ["A", "B"])[0].entity == "B" and resolve_top(e, ["A", "B"])[1] == e[1]
    with pytest.raises(ScenarioError, match="only 1"):
        resolve_top(e, ["A"])
    with pytest.raises(ScenarioError, match="placeholder"):
        load_scenario_file(write(tmp_path, "scenarios:\n  - {id: a, group: g, persona: P01, "
                                           "evidence_edits: [{quantity: q, entity: '@best', drop: true}]}\n"))
