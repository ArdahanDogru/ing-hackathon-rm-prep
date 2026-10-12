"""Metrics of a suite run (docs/eval.md "Checks and metrics"): pass rate per
check (pass / (pass + fail); n/a is not counted), per group, time and cost,
the judge scores, and each target of config/eval.yaml met or not."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

from rmprep.eval.checks import FAIL, NA, PASS, ScenarioChecks
from rmprep.eval.config import Targets
from rmprep.eval.runner import ScenarioRun

SCORE = {"yes": 1.0, "partly": 0.5, "no": 0.0}     # judge choice -> score

RULE_CHECKS = ("rule5", "risk_ceiling", "not_buyable", "explicit_constraints",
               "no_invented_data", "missing_data_shown", "bad_data_handled", "questions",
               "consistency", "traceability", "scenario_runs")


def _rate(c: dict[str, int]) -> float | None:
    n = c[PASS] + c[FAIL]
    return None if n == 0 else c[PASS] / n


def _stats(xs: list[float]) -> dict[str, float] | None:
    if not xs:
        return None
    return {"n": len(xs), "mean": statistics.fmean(xs), "max": max(xs),
            "median": statistics.median(xs)}


def same_top3(runs: list[ScenarioRun]) -> dict[str, Any] | None:
    """D19 error case: how many base personas share the most common recommended
    top 3 (before D19: 2 — P01 = P04 and P02 = P05; 4 of 5 had only cash-like
    funds at SPK risk 1). None without a ready base run."""
    from rmprep.grouping import recommended

    tops = [tuple(x.option.option_id for x in recommended(sr.runs[0].result))
            for sr in runs if sr.scenario.group == "base" and sr.runs
            and sr.runs[0].result.state.value == "ready"]
    if not tops:
        return None
    top, n = Counter(tops).most_common(1)[0]
    return {"count": n, "personas": len(tops), "top3": list(top)}


def summarize(runs: list[ScenarioRun], checks: list[ScenarioChecks], targets: Targets,
              grades: Iterable[Any] = (), judge_cost_usd: float = 0.0) -> dict[str, Any]:
    by_check: dict[str, dict[str, int]] = defaultdict(lambda: {PASS: 0, FAIL: 0, NA: 0})
    by_group: dict[str, dict[str, int]] = defaultdict(lambda: {PASS: 0, FAIL: 0, NA: 0})
    for sc in checks:
        for c in sc.all():
            by_check[c.check][c.status] += 1
            by_group[sc.scenario.group][c.status] += 1

    every = [r for sr in runs for r in sr.runs]
    narratives = [d for r in every for d in r.narratives.values()]
    narrator_cost = sum(r.narrator_cost_usd for r in every)

    rule = {PASS: 0, FAIL: 0, NA: 0}
    for name in RULE_CHECKS:
        for k, v in by_check.get(name, {}).items():
            rule[k] += v
    phrase_hits = sum(len(c.details) for sc in checks for c in sc.all()
                      if c.check == "forbidden_phrases" and c.status == FAIL)
    narrator_rate = _rate(by_check["narrator_valid"]) if "narrator_valid" in by_check else None
    narratives = [d for r in (r for sr in runs for r in sr.runs) for d in r.narratives.values()]

    grades = list(grades)
    judge_cache = {"write_tokens": sum(g.cache_write_tokens for g in grades),
                   "read_tokens": sum(g.cache_read_tokens for g in grades),
                   "errors": sum(1 for g in grades if g.error)}
    judge: dict[str, dict[str, Any]] = {}
    for g in grades:
        for item, (choice, _) in g.items.items():
            j = judge.setdefault(item, {"yes": 0, "partly": 0, "no": 0})
            j[choice] += 1
    # E10: repeated grades of one text (same run_id and lang): the spread of the
    # score per text (max - min), its mean over texts with 2+ grades, and the
    # number of texts whose grades differ
    per_text: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for g in grades:
        for item, (choice, _) in g.items.items():
            per_text[(item, g.run_id, g.lang)].append(SCORE[choice])
    for item, j in judge.items():
        n = j["yes"] + j["partly"] + j["no"]
        j["score"] = (j["yes"] + 0.5 * j["partly"]) / n if n else None
        texts = [v for (i, _, _), v in per_text.items() if i == item]
        spreads = [max(v) - min(v) for v in texts if len(v) >= 2]
        j["texts"] = len(texts)
        j["spread"] = statistics.fmean(spreads) if spreads else None
        j["disagree"] = sum(1 for s in spreads if s > 0)

    target_rows = {
        # met None: not measured (no run of that kind), shown as n/a
        "rule_checks": {"value": _rate(rule), "target": targets.rule_checks,
                        "met": None if _rate(rule) is None else _rate(rule) >= targets.rule_checks},
        "narrator_pass_rate": {"value": narrator_rate, "target": targets.narrator_pass_rate,
                               "met": (None if narrator_rate is None
                                       else narrator_rate >= targets.narrator_pass_rate)},
        "forbidden_phrases": {"value": None if not narratives else phrase_hits,
                              "target": targets.forbidden_phrases,
                              "met": None if not narratives
                              else phrase_hits <= targets.forbidden_phrases},
    }
    return {
        "scenarios": len(runs),
        "runs": len(every),
        "scenario_errors": sum(1 for sr in runs if sr.error),
        "checks": {k: {**v, "rate": _rate(v)} for k, v in sorted(by_check.items())},
        "groups": {k: {**v, "rate": _rate(v)} for k, v in sorted(by_group.items())},
        "rule_checks": {**rule, "rate": _rate(rule)},
        "targets": target_rows,
        "time": {
            "evidence_s": _stats([r.seconds_evidence for r in every]),
            "decide_s": _stats([r.seconds_decide for r in every]),
            "narrate_s": _stats([t for r in every for t in r.seconds_narrate.values()]),
        },
        "cost": {
            "narrator_usd": narrator_cost,
            "judge_usd": judge_cost_usd,
            "judge_cache": judge_cache,
            "total_usd": narrator_cost + judge_cost_usd,
            "per_text_usd": narrator_cost / len(narratives) if narratives else None,
        },
        "texts": {"total": len(narratives),
                  "llm": sum(1 for d in narratives if d.source == "llm"),
                  "template": sum(1 for d in narratives if d.source == "template")},
        "judge": judge,
        "same_top3": same_top3(runs),
    }
