"""The runner: scenarios through RealBackend (fixture evidence, fake narrator)."""

from pathlib import Path

from rmprep.backend import RealBackend
from rmprep.contracts import DecisionState, RmStatus
from rmprep.eval.runner import Runner
from rmprep.eval.scenario import EvidenceEdit, Scenario, load_scenario_file
from rmprep.grouping import groups, recommended
from tests.eval.conftest import CONTRACT_FIX, SNAP, T0, FakeNarrator


def runner(root, **kw) -> Runner:
    kw.setdefault("narrator", FakeNarrator())
    return Runner(root, personas_dir=CONTRACT_FIX / "personas", now=lambda: T0, **kw)


def one(root, s: Scenario, **kw):
    [sr] = runner(root, **kw).run([s])
    return sr


def test_a_scenario_file_runs(root, tmp_path):
    f = tmp_path / "suite.yaml"
    f.write_text("""
scenarios:
  - {id: base-p02, group: base, persona: P02}
  - {id: base-p03, group: base, persona: P03, langs: [TR, EN]}
""", encoding="utf-8")
    r = runner(root)
    out = r.run(load_scenario_file(f))
    assert r.snapshot_id == SNAP
    assert [x.scenario.id for x in out] == ["base-p02", "base-p03"]
    for sr in out:
        assert sr.error is None
        [run] = sr.runs
        assert run.result.state == DecisionState.READY and run.result.snapshot_id == SNAP
        assert run.result.persona_id == sr.scenario.persona and run.errors == []
        heads = tuple(o.option.option_id for o in recommended(run.result))   # D19: what the RM sees
        assert run.approved.rm_status == RmStatus.APPROVED and run.approved.rm_selected == heads
        assert run.approved.run_id == run.result.run_id
        assert set(run.narratives) == set(sr.scenario.langs)
        assert run.seconds_decide >= 0 and run.seconds_evidence >= 0
        assert set(run.seconds_narrate) == set(sr.scenario.langs)
    assert not (root / "data" / "runs").exists()      # the eval never saves an RM run


def test_persona_edits_apply(root):
    s = Scenario(id="e", group="persona_edit", persona="P02",
                 edit={"risk_profili": "Muhafazakâr", "yatirim_ufku": "1 yıl"})
    run = one(root, s).runs[0]
    assert run.result.persona.risk_profili == "Muhafazakâr"
    assert run.result.persona.yatirim_ufku == "1 yıl"
    base = one(root, Scenario(id="b", group="base", persona="P02")).runs[0]
    assert run.result.run_id != base.result.run_id


def test_an_edited_persona_can_still_be_narrated(root):
    s = Scenario(id="e", group="persona_edit", persona="P02", edit={"yas": 30})
    run = one(root, s).runs[0]
    assert run.approved is not None and "TR" in run.narratives


def test_exclusions_apply(root, builds):
    run = one(root, Scenario(id="x", group="data_access", persona="P01",
                             exclude_sources=frozenset({"manual"}))).runs[0]
    assert run.result.excluded_sources == frozenset({"manual"})
    assert run.evidence.excluded_sources == frozenset({"manual"})
    assert ("20261010-001233-6b20", frozenset({"manual"})) in builds


def test_unknown_constraint_asks_and_the_answer_applies(root):
    text = "kripto istemiyor"
    asked = one(root, Scenario(id="c", group="constraint", persona="P01",
                               add_constraints=(text,))).runs[0]
    assert asked.result.state == DecisionState.NEEDS_RM_INPUT
    assert asked.approved is None and asked.narratives == {} and asked.errors == []
    q = next(q for q in asked.result.questions if q.answer is None and q.blocking)
    answered = one(root, Scenario(id="c2", group="constraint", persona="P01",
                                  add_constraints=(text,),
                                  answers=((q.question_id, q.choices[0]),))).runs[0]
    assert answered.result.state == DecisionState.READY
    got = next(x for x in answered.result.questions if x.question_id == q.question_id)
    assert got.answer == q.choices[0]


def test_an_answer_to_an_unknown_question_is_an_error(root):
    run = one(root, Scenario(id="a", group="g", persona="P01",
                             answers=(("q:nope", "x"),))).runs[0]
    assert any("q:nope" in e for e in run.errors)


def test_unknown_persona_and_bad_source_are_scenario_errors(root):
    out = runner(root).run([
        Scenario(id="p", group="g", persona="P99"),
        Scenario(id="s", group="g", persona="P01", exclude_sources=frozenset({"nope"})),
        Scenario(id="ok", group="g", persona="P01"),
    ])
    assert "P99" in out[0].error and out[0].runs == []
    assert "nope" in out[1].error
    assert out[2].error is None and out[2].runs


def test_repeat_runs_on_a_fresh_backend_and_the_text_comes_from_the_cache(root):
    fake = FakeNarrator()
    r = runner(root, narrator=fake)
    sr = r.run([Scenario(id="b", group="base", persona="P02", repeat=2)])[0]
    a, b = sr.runs
    assert (a.repeat, b.repeat) == (0, 1)
    assert a.backend is not b.backend and isinstance(b.backend, RealBackend)
    assert a.result.to_dict() == b.result.to_dict()
    assert a.narratives == b.narratives and len(fake.calls) == 1


def test_evidence_edits_make_their_own_snapshot_id(root):
    from rmprep.contracts import Flag
    from tests.eval.conftest import fixture_evidence
    risk = next(d for d in fixture_evidence().datapoints if d.quantity == "fund_risk_level")
    s = Scenario(id="bad", group="bad_data", persona="P04",
                 evidence_edits=(EvidenceEdit(quantity="fund_risk_level", entity=risk.entity,
                                              value=9.0, add_flags=("out_of_range",)),))
    run = one(root, s).runs[0]
    assert run.result.snapshot_id == f"{SNAP}~bad"
    assert run.evidence.snapshot_id == f"{SNAP}~bad"
    row = next(d for d in run.evidence.datapoints if d.id == risk.id)
    assert row.value == 9.0 and Flag.OUT_OF_RANGE in row.flags
    plain = one(root, Scenario(id="p", group="base", persona="P04")).runs[0]
    assert plain.result.run_id != run.result.run_id


def test_explicit_selection_and_a_bad_selection(root):
    base = one(root, Scenario(id="b", group="base", persona="P03")).runs[0]
    pick = base.result.options[-1].option.option_id
    run = one(root, Scenario(id="s", group="g", persona="P03", select=(pick,))).runs[0]
    assert run.approved.rm_selected == (pick,)
    bad = one(root, Scenario(id="s2", group="g", persona="P03", select=("fund:NOPE",))).runs[0]
    assert bad.approved is None and any("fund:NOPE" in e for e in bad.errors)


def test_no_narrator_means_no_text_and_narrate_false_skips(root):
    run = one(root, Scenario(id="b", group="base", persona="P02"), narrator=None).runs[0]
    assert run.approved is not None and run.narratives == {} and run.errors == []
    fake = FakeNarrator()
    run = one(root, Scenario(id="b", group="base", persona="P02", narrate=False),
              narrator=fake).runs[0]
    assert run.narratives == {} and fake.calls == []


def test_the_budget_stops_new_texts(root):
    fake = FakeNarrator(cost=0.04)
    r = runner(root, narrator=fake, max_cost_usd=0.05)
    out = r.run([Scenario(id=f"b{i}", group="base", persona=p)
                 for i, p in enumerate(["P01", "P02", "P03"])])
    assert [len(x.runs[0].narratives) for x in out] == [1, 1, 0]
    assert any("budget" in e for e in out[2].runs[0].errors)
    assert round(r.spent_usd, 6) == 0.08
    assert [round(x.runs[0].narrator_cost_usd, 6) for x in out] == [0.04, 0.04, 0.0]


def test_scenario_snapshot_overrides_the_suite_snapshot(root):
    sr = one(root, Scenario(id="s", group="g", persona="P01", snapshot="other"))
    assert "other" in sr.error


def test_the_suite_snapshot_is_used(root):
    r = runner(root, snapshot=SNAP)
    assert r.snapshot_id == SNAP
    assert r.run([Scenario(id="s", group="g", persona="P01")])[0].error is None


def test_the_runner_writes_nothing_under_root(root):
    # the runner reads only through RealBackend: no file under root/data is written
    runner(root).run([Scenario(id="b", group="base", persona="P01")])
    assert not (Path(root) / "data").exists()


def test_top_placeholder_edits_the_first_fund_of_the_clean_run(root):
    from rmprep.contracts import Flag
    clean = one(root, Scenario(id="c", group="base", persona="P04")).runs[0]
    top1 = next(o.option.entity for o in clean.result.options if o.option.kind == "fund")
    s = Scenario(id="stale", group="bad_data", persona="P04",
                 evidence_edits=(EvidenceEdit(quantity="fund_price", entity="@top1",
                                              add_flags=("stale",)),))
    run = one(root, s).runs[0]
    rows = [d for d in run.evidence.datapoints if d.quantity == "fund_price"]
    assert [d.entity for d in rows if Flag.STALE in d.flags] == [top1]


def test_a_top_placeholder_past_the_end_is_an_error(root):
    s = Scenario(id="x", group="bad_data", persona="P04",
                 evidence_edits=(EvidenceEdit(quantity="fund_price", entity="@top999",
                                              drop=True),))
    assert "999" in one(root, s).error


def test_the_packaged_suite_runs_on_the_fixture(root):
    from rmprep.eval.scenario import load_scenarios, packaged_scenario_files
    out = runner(root).run(load_scenarios(packaged_scenario_files()))
    for sr in out:
        if "tefas_detail" in sr.scenario.exclude_sources:   # not in the fixture snapshot
            assert "tefas_detail" in sr.error
            continue
        assert sr.error is None, (sr.scenario.id, sr.error)
        assert len(sr.runs) == sr.scenario.repeat
        assert all(run.errors == [] for run in sr.runs), (sr.scenario.id, sr.runs[0].errors)
    by_id = {sr.scenario.id: sr for sr in out}
    for sid in ("con-p03-no-fx-asks", "con-p02-unknown-asks"):
        assert by_id[sid].runs[0].result.state == DecisionState.NEEDS_RM_INPUT
    for sid in ("con-p03-no-fx-answered", "con-p03-no-high-risk-answered"):
        assert by_id[sid].runs[0].result.state == DecisionState.READY


def test_budget_left_counts_texts_and_other_costs(root):
    r = runner(root, narrator=FakeNarrator(cost=0.5), max_cost_usd=5.0)
    r.run([Scenario(id="b", group="base", persona="P01")])
    r.add_cost(0.25)
    assert r.budget_left() == 4.25
    assert runner(root).budget_left() == float("inf")


def test_the_default_selection_is_the_engine_recommendation(root):
    """The eval approves what the dashboard proposes: grouping.recommended (D19)."""
    import dataclasses

    from rmprep.grouping import recommended
    base = one(root, Scenario(id="b", group="base", persona="P03")).runs[0]
    r = base.result
    assert base.approved.rm_selected == tuple(o.option.option_id for o in recommended(r))[:3]
    # a result whose engine choice differs from the group heads: the choice wins
    alt = tuple(o.option.option_id for o in r.options if o.option.kind != "deposit")[-2:]
    chosen = dataclasses.replace(r, recommended=alt)
    rec = runner(root)._approve(Scenario(id="c", group="g", persona="P03"), chosen, [])
    assert rec.rm_selected == alt
