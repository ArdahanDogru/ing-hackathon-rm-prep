"""One suite run (docs/eval.md "Shape"): scenarios -> RealBackend -> checks ->
judge -> metrics -> report in <root>/<report_dir>/<time>-<suite>/.

The eval narrator and judge have their own cache and cost ledger under
<root>/<report_dir>/ (narratives/, judge/), separate from the RM's narrator
cache and daily limit; the eval limit is per suite run (config/eval.yaml
max_cost_usd_per_run), enforced by the runner for texts and grades together.
`python -m rmprep eval` (cli.py, lead) calls run_suite.

E11: with agent=True (`rmprep eval --agent`) the agent scenarios
(scenarios/agent/) are added, the agent decides for the base and agent scenarios
(agent_eval.py), the check agent_decision runs, the A/B judge compares the two top
3, and the report gets the section "Agent (E11)". Without it nothing changes and
nothing of the agent is called."""

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
from rmprep.eval.judge import (
    AbGrade, CachedAbJudge, CachedJudge, GradedText, ab_grades, ab_judge_from_env, grade_texts,
    judge_from_env,
)
from rmprep.eval.metrics import summarize
from rmprep.eval.report import write_report
from rmprep.eval.runner import Runner, ScenarioRun
from rmprep.eval.scenario import (
    Scenario, agent_scenario_files, load_scenarios, packaged_scenario_files,
)

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
    ab: list[AbGrade] = dataclasses.field(default_factory=list)     # E11


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
              now: Callable[[], datetime] | None = None, write: bool = True,
              agent: bool = False, agent_client: Any = AUTO, research: Any = AUTO,
              ab_judge: Any = AUTO, agent_deadline_s: float | None = None) -> SuiteResult:
    """Run the suite and write its report.

    scenario_files: default the packaged files (src/rmprep/eval/scenarios/; with
    agent also scenarios/agent/); only: scenario ids or groups to keep; snapshot:
    default the frozen snapshot of config/eval.yaml, else the newest;
    narrator/judge: AUTO builds them from the environment (no key: template texts,
    no grades), None turns them off. agent (E11): the agent part; agent_client,
    research and ab_judge as narrator (AUTO from the environment, None off)."""
    root = Path(root)
    config = load_config(root / "config" / "eval.yaml")
    dcfg = decision.load_config(root / "config" / "decision.yaml")
    from rmprep.narrator.config import load_config as load_narrator_config
    ncfg = load_narrator_config(root / "config" / "narrator.yaml")
    created = (now or (lambda: datetime.now(TR_TZ)))()

    files = (list(scenario_files) if scenario_files is not None
             else packaged_scenario_files() + (agent_scenario_files() if agent else []))
    scenarios = load_scenarios(files)
    if only is not None:
        keep = set(only)
        chosen = [s for s in scenarios if s.id in keep or s.group in keep]
        need = {s.compare_to for s in chosen if s.compare_to} - {s.id for s in chosen}
        scenarios = [s for s in scenarios if s in chosen or s.id in need]

    agent_auto = agent and AUTO in (agent_client, research, ab_judge)
    if env is None and (narrator == AUTO or judge == AUTO or agent_auto):
        env = load_env(root)
    if narrator == AUTO:
        narrator = eval_narrator(root, config, env)
    if judge == AUTO:
        judge = eval_judge(root, config, env)

    runner = Runner(root, personas_dir=personas_dir, narrator=narrator,
                    snapshot=snapshot or config.snapshot, now=lambda: created,
                    max_cost_usd=config.max_cost_usd_per_run)
    runs = runner.run(scenarios)
    if agent:
        from rmprep.eval.agent_eval import eval_agent

        agent_eval = eval_agent(root, config, env or {}, client=agent_client, research=research,
                                created=created, deadline_s=agent_deadline_s)
        agent_eval.run(runs, budget_left=runner.budget_left, spend=runner.add_cost)
    checks = run_checks(runs, dcfg.raw, ncfg.forbidden_phrases, ncfg, agent=agent)
    grades = grade_texts(runs, judge, config.judge.rubric, repeats=config.judge_repeats,
                         budget_left=runner.budget_left, spend=runner.add_cost)
    judge_cost = sum(g.grade.cost_usd for g in grades)
    metrics = summarize(runs, checks, config.targets, [g.grade for g in grades], judge_cost)
    metrics["cost"]["limit_usd"] = config.max_cost_usd_per_run
    ab: list[AbGrade] = []
    if agent:
        from rmprep.eval.agent_eval import agent_metrics

        if ab_judge == AUTO:
            inner = ab_judge_from_env(config.judge, env)
            ab_judge = (None if inner is None
                        else CachedAbJudge(inner, root / config.report_dir / "judge-ab"))
        ab = ab_grades(runs, ab_judge, budget_left=runner.budget_left, spend=runner.add_cost)
        metrics["agent"] = agent_metrics(runs, ab)
        c = metrics["cost"]
        c["agent_usd"] = metrics["agent"]["cost"]["model_usd"]
        c["agent_research_usd"] = metrics["agent"]["cost"]["research_usd"]
        c["ab_judge_usd"] = metrics["agent"]["cost"]["ab_judge_usd"]
        c["total_usd"] += metrics["agent"]["cost"]["total_usd"]

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
        "judge": None if judge is None else {"model": getattr(judge, "model", "?"),
                                             "repeats": config.judge_repeats},
        "scenario_files": [str(p) for p in files],
        "agent": None,
    }
    if agent:
        from rmprep.eval.agent_eval import agent_meta

        meta["agent"] = agent_meta(root, client_on=agent_eval.client_on)
        meta["agent"]["ab_judge"] = None if ab_judge is None else ab_judge.model
    result = SuiteResult(suite=suite, snapshot_id=runner.snapshot_id,
                         snapshot_frozen=meta["snapshot_frozen"], created_at=created,
                         scenarios=scenarios, runs=runs, checks=checks, grades=grades,
                         metrics=metrics, meta=meta, ab=ab)
    if write:
        out = root / config.report_dir / f"{created:%Y%m%d-%H%M%S}-{suite}"
        write_report(out, result)
        result.report_dir = out
    return result
