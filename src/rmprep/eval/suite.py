"""One suite run (docs/eval.md "Shape"): scenarios -> RealBackend -> checks ->
judge -> metrics -> report in <root>/<report_dir>/<time>-<suite>/.

The eval narrator and judge have their own cache and cost ledger under
<root>/<report_dir>/ (narratives/, judge/), separate from the RM's narrator
cache and daily limit; the eval limit is per suite run (config/eval.yaml
max_cost_usd_per_run), enforced by the runner for texts and grades together.
`python -m rmprep eval` (cli.py, lead) calls run_suite."""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from rmprep import decision
from rmprep.contracts import TR_TZ
from rmprep.eval.checks import ScenarioChecks, run_checks
from rmprep.eval.config import EvalConfig, load_config
from rmprep.eval.judge import CachedJudge, GradedText, grade_texts, judge_from_env
from rmprep.eval.metrics import summarize
from rmprep.eval.report import write_report
from rmprep.eval.runner import Runner, ScenarioRun
from rmprep.eval.scenario import Scenario, load_scenarios, packaged_scenario_files

AUTO = "auto"
NO_DAILY_LIMIT = 1e9     # the eval narrator: the runner enforces the per-run limit


@dataclass
class SuiteResult:
    suite: str
    snapshot_id: str | None
    snapshot_frozen: bool          # the snapshot is the frozen one of config/eval.yaml
    created_at: datetime
    scenarios: list[Scenario]
    runs: list[ScenarioRun]
    checks: list[ScenarioChecks]
    grades: list[GradedText]
    metrics: dict[str, Any]
    meta: dict[str, Any]
    report_dir: Path | None = None


def load_env(root: Path) -> dict[str, str]:
    """root/.env, then the process environment on top (as the narrator does)."""
    from dotenv import dotenv_values

    env = {k: v for k, v in dotenv_values(root / ".env").items() if v is not None}
    env.update(os.environ)
    return env


def eval_narrator(root: Path, config: EvalConfig, env: Mapping[str, str]):
    """The narrator of config/narrator.yaml with the eval's own cache and ledger."""
    from rmprep.narrator.config import load_config as load_narrator_config
    from rmprep.narrator.llm import client_from_env
    from rmprep.narrator.service import Narrator

    ncfg = dataclasses.replace(load_narrator_config(root / "config" / "narrator.yaml"),
                               max_cost_usd_per_day=NO_DAILY_LIMIT)
    return Narrator(ncfg, client_from_env(ncfg, env), root / config.report_dir / "narratives")


def eval_judge(root: Path, config: EvalConfig, env: Mapping[str, str]) -> CachedJudge | None:
    inner = judge_from_env(config.judge, env)
    return None if inner is None else CachedJudge(inner, root / config.report_dir / "judge")


def run_suite(root: Path | str, *, suite: str = "full",
              scenario_files: Iterable[Path | str] | None = None,
              only: Iterable[str] | None = None, snapshot: str | None = None,
              personas_dir: Path | str | None = None, narrator: Any = AUTO, judge: Any = AUTO,
              env: Mapping[str, str] | None = None,
              now: Callable[[], datetime] | None = None, write: bool = True) -> SuiteResult:
    """Run the suite and write its report.

    scenario_files: default the packaged files (src/rmprep/eval/scenarios/);
    only: scenario ids or groups to keep; snapshot: default the frozen snapshot
    of config/eval.yaml, else the newest; narrator/judge: AUTO builds them from
    the environment (no key: template texts, no grades), None turns them off."""
    root = Path(root)
    config = load_config(root / "config" / "eval.yaml")
    dcfg = decision.load_config(root / "config" / "decision.yaml")
    from rmprep.narrator.config import load_config as load_narrator_config
    ncfg = load_narrator_config(root / "config" / "narrator.yaml")
    created = (now or (lambda: datetime.now(TR_TZ)))()

    scenarios = load_scenarios(scenario_files if scenario_files is not None
                               else packaged_scenario_files())
    if only is not None:
        keep = set(only)
        chosen = [s for s in scenarios if s.id in keep or s.group in keep]
        need = {s.compare_to for s in chosen if s.compare_to} - {s.id for s in chosen}
        scenarios = [s for s in scenarios if s in chosen or s.id in need]

    if env is None and (narrator == AUTO or judge == AUTO):
        env = load_env(root)
    if narrator == AUTO:
        narrator = eval_narrator(root, config, env)
    if judge == AUTO:
        judge = eval_judge(root, config, env)

    runner = Runner(root, personas_dir=personas_dir, narrator=narrator,
                    snapshot=snapshot or config.snapshot, now=lambda: created,
                    max_cost_usd=config.max_cost_usd_per_run)
    runs = runner.run(scenarios)
    checks = run_checks(runs, dcfg.raw, ncfg.forbidden_phrases)
    grades = grade_texts(runs, judge, config.judge.rubric,
                         budget_left=runner.budget_left, spend=runner.add_cost)
    judge_cost = sum(g.grade.cost_usd for g in grades)
    metrics = summarize(runs, checks, config.targets, [g.grade for g in grades], judge_cost)
    metrics["cost"]["limit_usd"] = config.max_cost_usd_per_run

    client = getattr(narrator, "client", None)
    meta = {
        "suite": suite,
        "created_at": created.isoformat(),
        "snapshot_id": runner.snapshot_id,
        "snapshot_frozen": bool(config.snapshot) and runner.snapshot_id == config.snapshot,
        "config_hash": next((r.result.config_hash for sr in runs for r in sr.runs), None),
        "narrator": (None if narrator is None else
                     {"model": ncfg.model, "prompt_version": ncfg.prompt_version,
                      "llm": client is not None or not hasattr(narrator, "client")}),
        "judge": None if judge is None else {"model": getattr(judge, "model", "?")},
        "scenario_files": [str(p) for p in (scenario_files or packaged_scenario_files())],
    }
    result = SuiteResult(suite=suite, snapshot_id=runner.snapshot_id,
                         snapshot_frozen=meta["snapshot_frozen"], created_at=created,
                         scenarios=scenarios, runs=runs, checks=checks, grades=grades,
                         metrics=metrics, meta=meta)
    if write:
        out = root / config.report_dir / f"{created:%Y%m%d-%H%M%S}-{suite}"
        write_report(out, result)
        result.report_dir = out
    return result
