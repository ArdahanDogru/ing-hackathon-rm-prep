"""The eval report: report.json (everything, for the next tools) and report.md
(for the user, the jury and deliverable 5 "Test ve öğrenimler")."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from rmprep.eval.checks import FAIL

RULE_LABELS = {
    "rule5": "Rule 5: no rejected / constraint-breaking option in list, selection or text",
    "risk_ceiling": "No option above the risk ceiling",
    "not_buyable": "No fund that cannot be bought (D12)",
    "explicit_constraints": "Explicit constraints as hard rules (D13)",
    "no_invented_data": "No invented data (rule 3)",
    "missing_data_shown": "Missing data is shown",
    "bad_data_handled": "Bad data is flagged, not used",
    "questions": "Questions instead of guesses",
    "consistency": "Same inputs, same result and text",
    "sensitivity": "Persona edits move the result as expected",
    "narrator_valid": "Meeting text passes the validator (LLM, no fallback)",
    "forbidden_phrases": "No forbidden phrase (rule 6)",
    "traceability": "Every option and text sentence cites evidence (rule 2)",
    "scenario_runs": "The scenario runs",
}


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:.0f} %"


def _usd(x: float | None) -> str:
    return "-" if x is None else f"${x:.3f}"


def _sec(s: dict | None) -> str:
    return "-" if not s else f"{s['mean']:.2f} s (max {s['max']:.2f} s, n={s['n']})"


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def run_dict(run) -> dict[str, Any]:
    r = run.result
    return {
        "repeat": run.repeat,
        "run_id": r.run_id,
        "snapshot_id": r.snapshot_id,
        "state": r.state.value,
        "persona": r.persona.to_dict(),
        "excluded_sources": sorted(r.excluded_sources),
        "options": len(r.options),
        "rejected": dict(Counter(f.rule_id for x in r.rejected for f in x.failed)),
        "short_list": [o.option.option_id for o in r.options[:11]],
        "questions": [{"id": q.question_id, "blocking": q.blocking, "answer": q.answer}
                      for q in r.questions],
        "warnings": [w.code for w in r.warnings],
        "data_quality": [n.message for n in r.data_quality],
        "selected": list(run.approved.rm_selected) if run.approved else [],
        "evidence_edits": [e.__dict__ for e in run.evidence_edits],
        "narratives": {lang: {"source": d.source, "model": d.model, "checks": list(d.checks),
                              "cost_usd": d.cost_usd, "prompt_version": d.prompt_version}
                       for lang, d in sorted(run.narratives.items())},
        "seconds": {"evidence": run.seconds_evidence, "decide": run.seconds_decide,
                    "narrate": run.seconds_narrate},
        "narrator_cost_usd": run.narrator_cost_usd,
        "errors": list(run.errors),
    }


def to_json(result) -> dict[str, Any]:
    checks = {sc.scenario.id: sc for sc in result.checks}
    grades: dict[str, list] = {}
    for g in result.grades:
        grades.setdefault(g.scenario_id, []).append(g.grade.to_dict())
    scenarios = []
    for sr in result.runs:
        s = sr.scenario
        sc = checks[s.id]
        scenarios.append({
            "id": s.id, "group": s.group, "description": s.description, "persona": s.persona,
            "edit": dict(s.edit), "add_constraints": list(s.add_constraints),
            "exclude_sources": sorted(s.exclude_sources), "answers": dict(s.answers),
            "compare_to": s.compare_to, "expect": dict(s.expect), "needs": list(s.needs),
            "error": sr.error,
            "runs": [run_dict(r) for r in sr.runs],
            "checks": [[c.__dict__ | {"details": list(c.details)} for c in rs] for rs in sc.runs],
            "scenario_checks": [c.__dict__ | {"details": list(c.details)}
                                for c in sc.scenario_checks],
            "grades": grades.get(s.id, []),
        })
    return {"meta": result.meta, "metrics": result.metrics, "scenarios": scenarios}


def to_markdown(result) -> str:
    m, meta = result.metrics, result.meta
    L: list[str] = [f"# Eval report: {meta['suite']}", ""]
    frozen = "frozen eval snapshot" if meta["snapshot_frozen"] else \
        "NOT the frozen eval snapshot (config/eval.yaml snapshot is not set or differs)"
    nar = meta.get("narrator")
    L += [f"- Time: {meta['created_at']}",
          f"- Snapshot: `{meta['snapshot_id']}` ({frozen})",
          f"- Decision config: `{meta['config_hash']}`",
          f"- Narrator: " + ("off" if nar is None else
                             f"{nar['model']}, prompt {nar['prompt_version']}"
                             + ("" if nar["llm"] else " (no API key: template texts)")),
          f"- Judge: " + ("off (no API key or turned off)" if meta.get("judge") is None
                          else meta["judge"]["model"]),
          f"- Scenarios: {m['scenarios']}, runs: {m['runs']}, scenario errors: "
          f"{m['scenario_errors']}", ""]

    L += ["## Targets", "", "| Metric | Value | Target | Met |", "|---|---|---|---|"]
    t = m["targets"]
    L.append(f"| Rule checks pass rate | {_pct(t['rule_checks']['value'])} | "
             f"{_pct(t['rule_checks']['target'])} | {'yes' if t['rule_checks']['met'] else 'NO'} |")
    L.append(f"| Narrator validator pass rate | {_pct(t['narrator_pass_rate']['value'])} | "
             f"≥ {_pct(t['narrator_pass_rate']['target'])} | "
             f"{'yes' if t['narrator_pass_rate']['met'] else 'NO'} |")
    L.append(f"| Forbidden phrases | {t['forbidden_phrases']['value']} | "
             f"{t['forbidden_phrases']['target']} | {'yes' if t['forbidden_phrases']['met'] else 'NO'} |")
    L.append("")

    L += ["## Checks", "", "| Check | Pass | Fail | n/a | Pass rate |", "|---|---|---|---|---|"]
    for name, c in m["checks"].items():
        L.append(f"| {RULE_LABELS.get(name, name)} | {c['pass']} | {c['fail']} | {c['n/a']} | "
                 f"{_pct(c['rate'])} |")
    L += ["", "n/a: the check does not apply to the run (e.g. no repeat, no excluded source).", ""]

    L += ["## Scenario groups", "", "| Group | Pass | Fail | n/a | Pass rate |",
          "|---|---|---|---|---|"]
    for name, c in m["groups"].items():
        L.append(f"| {name} | {c['pass']} | {c['fail']} | {c['n/a']} | {_pct(c['rate'])} |")
    L.append("")

    L += ["## Time and cost", "",
          f"- Evidence per run: {_sec(m['time']['evidence_s'])}",
          f"- Decide per run: {_sec(m['time']['decide_s'])}",
          f"- Meeting text per run: {_sec(m['time']['narrate_s'])}",
          f"- Texts: {m['texts']['total']} ({m['texts']['llm']} LLM, "
          f"{m['texts']['template']} template)",
          f"- Cost: narrator {_usd(m['cost']['narrator_usd'])}, judge {_usd(m['cost']['judge_usd'])}, "
          f"total {_usd(m['cost']['total_usd'])} of the {_usd(m['cost'].get('limit_usd'))} limit; "
          f"per new text {_usd(m['cost']['per_text_usd'])}",
          f"- Judge prompt cache: {m['cost']['judge_cache']['write_tokens']} tokens written, "
          f"{m['cost']['judge_cache']['read_tokens']} read; judge errors: "
          f"{m['cost']['judge_cache']['errors']}", ""]

    if m["judge"]:
        L += ["## Judge (LLM, only what code cannot check)", "",
              "| Rubric item | yes | partly | no | Score |", "|---|---|---|---|---|"]
        for item, j in m["judge"].items():
            L.append(f"| {item} | {j['yes']} | {j['partly']} | {j['no']} | {_pct(j['score'])} |")
        L += ["", "Score: yes = 1, partly = 0.5, no = 0.", ""]

    L += ["## Failures", ""]
    failures = 0
    for sc in result.checks:
        for k, rs in enumerate(sc.runs):
            for c in rs:
                if c.status == FAIL:
                    failures += 1
                    L.append(f"- **{sc.scenario.id}** (run {k}) `{c.check}`: "
                             + "; ".join(_cell(d) for d in c.details))
        for c in sc.scenario_checks:
            if c.status == FAIL:
                failures += 1
                L.append(f"- **{sc.scenario.id}** `{c.check}`: "
                         + "; ".join(_cell(d) for d in c.details))
    if not failures:
        L.append("No failed check.")
    L.append("")

    L += ["## Scenarios", "", "| Scenario | Group | State | Options | Rejected | Selected | "
          "Failed checks |", "|---|---|---|---|---|---|---|"]
    by_id = {sc.scenario.id: sc for sc in result.checks}
    for sr in result.runs:
        sc = by_id[sr.scenario.id]
        failed = sorted({c.check for c in sc.all() if c.status == FAIL})
        if sr.error or not sr.runs:
            L.append(f"| {sr.scenario.id} | {sr.scenario.group} | error | - | - | - | "
                     f"{_cell(sr.error or '')} |")
            continue
        r = sr.runs[0]
        rej = sum(1 for _ in r.result.rejected)
        sel = ", ".join(r.approved.rm_selected) if r.approved else "-"
        L.append(f"| {sr.scenario.id} | {sr.scenario.group} | {r.result.state.value} | "
                 f"{len(r.result.options)} | {rej} | {_cell(sel)} | {', '.join(failed) or '-'} |")
    L.append("")

    regressions = [sr for sr in result.runs if sr.scenario.group == "regression"]
    if regressions:
        L += ["## Error analysis cases (regression scenarios)", ""]
        for sr in regressions:
            sc = by_id[sr.scenario.id]
            failed = sorted({c.check for c in sc.all() if c.status == FAIL})
            L.append(f"- **{sr.scenario.id}**: {sr.scenario.description} — "
                     + ("passes" if not failed else f"FAILS: {', '.join(failed)}"))
        L.append("")
    return "\n".join(L)


def write_report(out_dir: Path | str, result) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(
        json.dumps(to_json(result), ensure_ascii=False, indent=1, default=str) + "\n",
        encoding="utf-8", newline="\n")
    (out / "report.md").write_text(to_markdown(result), encoding="utf-8", newline="\n")
    return out
