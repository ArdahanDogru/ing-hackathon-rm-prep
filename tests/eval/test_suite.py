"""run_suite + the report on a small suite (tmp root, fixture evidence, fakes)."""

import json
from datetime import datetime

from rmprep.contracts import TR_TZ
from rmprep.eval.suite import eval_narrator, run_suite
from rmprep.eval.config import load_config
from tests.eval.conftest import CONTRACT_FIX, SNAP, FakeNarrator, eval_yaml
from tests.eval.test_judge import CountingJudge

NOW = datetime(2026, 10, 10, 15, 30, 0, tzinfo=TR_TZ)


def write_suite(tmp_path):
    f = tmp_path / "small.yaml"
    f.write_text("""
scenarios:
  - {id: base-p03, group: base, persona: P03, repeat: 2}
  - id: edit-p03
    group: persona_edit
    persona: P03
    edit: {risk_profili: "Muhafazakâr"}
    compare_to: base-p03
    expect: {avg_risk: lower}
  - {id: asks, group: constraint, persona: P01, add_constraints: ["kripto istemiyor"],
     expect: {state: needs_rm_input}}
  - {id: reg-x, group: regression, description: "a case", persona: P02}
""", encoding="utf-8")
    return f


def test_run_suite_writes_markdown_and_json(root, tmp_path):
    f = write_suite(tmp_path)
    judge = CountingJudge(cost=0.001)
    res = run_suite(root, suite="small", scenario_files=[f], personas_dir=CONTRACT_FIX / "personas",
                    narrator=FakeNarrator(cost=0.01), judge=judge, now=lambda: NOW)
    assert res.report_dir == root / "data" / "eval" / "20261010-153000-small"
    data = json.loads((res.report_dir / "report.json").read_text(encoding="utf-8"))
    assert data["meta"]["snapshot_id"] == SNAP and data["meta"]["snapshot_frozen"] is False
    assert [s["id"] for s in data["scenarios"]] == ["base-p03", "edit-p03", "asks", "reg-x"]
    assert len(data["scenarios"][0]["runs"]) == 2 and data["scenarios"][0]["grades"]
    assert data["metrics"]["targets"]["rule_checks"]["met"] is True
    assert data["metrics"]["cost"]["judge_usd"] == 0.003 and judge.calls == 3
    md = (res.report_dir / "report.md").read_text(encoding="utf-8")
    for heading in ("## Targets", "## Checks", "## Time and cost", "## Judge", "## Failures",
                    "## Scenarios", "## Error analysis cases"):
        assert heading in md
    assert "NOT the frozen eval snapshot" in md and "No failed check." in md
    assert "**reg-x**: a case — passes" in md


def test_only_keeps_ids_or_groups_and_their_compare_scenarios(root, tmp_path):
    res = run_suite(root, scenario_files=[write_suite(tmp_path)], only=["edit-p03"],
                    personas_dir=CONTRACT_FIX / "personas", narrator=None, judge=None,
                    write=False, now=lambda: NOW)
    assert [s.id for s in res.scenarios] == ["base-p03", "edit-p03"]
    assert res.report_dir is None and not (root / "data").exists()


def test_frozen_snapshot_from_the_config(root, tmp_path):
    (root / "config" / "eval.yaml").write_text(eval_yaml(SNAP), encoding="utf-8")
    res = run_suite(root, scenario_files=[write_suite(tmp_path)], only=["asks"],
                    personas_dir=CONTRACT_FIX / "personas", narrator=None, judge=None,
                    write=False, now=lambda: NOW)
    assert res.snapshot_frozen and res.meta["snapshot_frozen"]


def test_auto_without_a_key_gives_template_texts_and_no_judge(root, tmp_path):
    res = run_suite(root, scenario_files=[write_suite(tmp_path)], only=["reg-x"],
                    personas_dir=CONTRACT_FIX / "personas", env={}, write=True, now=lambda: NOW)
    [sr] = res.runs
    d = sr.runs[0].narratives["TR"]
    assert d.source == "template" and res.grades == [] and res.meta["judge"] is None
    md = (res.report_dir / "report.md").read_text(encoding="utf-8")
    assert "no API key: template texts" in md


def test_eval_narrator_has_its_own_cache_and_no_daily_limit(root):
    n = eval_narrator(root, load_config(root / "config" / "eval.yaml"), {})
    assert n.cache_dir == root / "data" / "eval" / "narratives"
    assert n.client is None and n.config.max_cost_usd_per_day >= 1e6
