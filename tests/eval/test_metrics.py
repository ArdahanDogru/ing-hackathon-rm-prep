"""summarize: rates without n/a, targets, time, cost, judge scores."""

from rmprep.eval.checks import FAIL, PASS, CheckResult, ScenarioChecks, run_checks
from rmprep.eval.config import Targets
from rmprep.eval.judge import Grade
from rmprep.eval.metrics import summarize
from rmprep.eval.scenario import Scenario
from tests.eval.conftest import FakeNarrator
from tests.eval.test_checks import DCFG, PHRASES
from tests.eval.test_runner import runner

TARGETS = Targets(rule_checks=1.0, narrator_pass_rate=0.95, forbidden_phrases=0)


def test_summary_of_a_small_suite(root):
    runs = runner(root, narrator=FakeNarrator(cost=0.01)).run([
        Scenario(id="b1", group="base", persona="P01", repeat=2),
        Scenario(id="c", group="constraint", persona="P02", add_constraints=("kripto istemiyor",)),
    ])
    checks = run_checks(runs, DCFG, PHRASES)
    grades = [Grade("R1", "TR", "m", {"tailored": ("yes", ""), "balanced": ("no", "")},
                    cache_write_tokens=700),
              Grade("R2", "TR", "m", {"tailored": ("partly", "")}),
              Grade("R3", "TR", "m", error="refusal")]
    m = summarize(runs, checks, TARGETS, grades, judge_cost_usd=0.002)
    assert (m["scenarios"], m["runs"], m["scenario_errors"]) == (2, 3, 0)
    assert m["checks"]["consistency"] == {"pass": 1, "fail": 0, "n/a": 1, "rate": 1.0}
    assert m["checks"]["questions"]["pass"] == 1
    assert m["targets"]["rule_checks"]["met"] and m["rule_checks"]["rate"] == 1.0
    assert m["targets"]["forbidden_phrases"] == {"value": 0, "target": 0, "met": True}
    assert m["targets"]["narrator_pass_rate"]["value"] == 1.0
    assert m["cost"]["narrator_usd"] == 0.01 and m["cost"]["total_usd"] == 0.012
    assert m["texts"] == {"total": 2, "llm": 2, "template": 0}
    assert m["time"]["decide_s"]["n"] == 3 and m["time"]["narrate_s"]["n"] == 2
    assert m["judge"]["tailored"] == {"yes": 1, "partly": 1, "no": 0, "score": 0.75}
    assert m["judge"]["balanced"]["score"] == 0.0
    assert m["cost"]["judge_cache"] == {"write_tokens": 700, "read_tokens": 0, "errors": 1}
    assert set(m["groups"]) == {"base", "constraint"}


def test_a_failed_rule_check_misses_the_target(root):
    runs = runner(root).run([Scenario(id="b", group="base", persona="P01")])
    checks = run_checks(runs, DCFG, PHRASES)
    checks.append(ScenarioChecks(Scenario(id="x", group="g", persona="P01"),
                                 [[CheckResult("rule5", FAIL, ("bad",))]],
                                 [CheckResult("forbidden_phrases", FAIL, ('TR: "garanti"',))]))
    m = summarize(runs, checks, TARGETS)
    assert not m["targets"]["rule_checks"]["met"]
    assert m["targets"]["forbidden_phrases"]["value"] == 1
    assert m["checks"]["rule5"][PASS] == 1 and m["checks"]["rule5"][FAIL] == 1


def test_without_llm_texts_the_text_targets_are_not_measured(root):
    from rmprep.eval.report import to_markdown
    from rmprep.eval.suite import run_suite
    from tests.eval.conftest import CONTRACT_FIX
    res = run_suite(root, only=["base-p01"], personas_dir=CONTRACT_FIX / "personas",
                    narrator=None, judge=None, write=False)
    t = res.metrics["targets"]
    assert t["narrator_pass_rate"] == {"value": None, "target": 0.95, "met": None}
    assert t["forbidden_phrases"]["met"] is None and t["rule_checks"]["met"] is True
    md = to_markdown(res)
    assert "| Narrator validator pass rate | n/a | ≥ 95 % | n/a |" in md
    assert "| Forbidden phrases | n/a | 0 | n/a |" in md
    assert "n/a: no graded text" in md
