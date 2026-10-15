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
    "allocation_projection": "Current split adds up, only RM / client-file rows rank (D27)",
    "scenario_runs": "The scenario runs",
    "agent_decision": "Agent top 3 keeps the rules (spec section 6; a fallback passes) (E11)",
}


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.0f} %"


def _met(x: bool | None) -> str:
    return "n/a" if x is None else ("yes" if x else "NO")


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
        "agent": None if run.agent is None else run.agent.to_dict(),
    }


def to_json(result) -> dict[str, Any]:
    checks = {sc.scenario.id: sc for sc in result.checks}
    grades: dict[str, list] = {}
    for g in result.grades:
        grades.setdefault(g.scenario_id, []).append(g.grade.to_dict())
    ab = {g.scenario_id: g.to_dict() for g in getattr(result, "ab", ())}
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
            "ab": ab.get(s.id),
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
    fp = t["forbidden_phrases"]
    L.append(f"| Rule checks pass rate | {_pct(t['rule_checks']['value'])} | "
             f"{_pct(t['rule_checks']['target'])} | {_met(t['rule_checks']['met'])} |")
    L.append(f"| Narrator validator pass rate | {_pct(t['narrator_pass_rate']['value'])} | "
             f"≥ {_pct(t['narrator_pass_rate']['target'])} | "
             f"{_met(t['narrator_pass_rate']['met'])} |")
    L.append(f"| Forbidden phrases | {'n/a' if fp['value'] is None else fp['value']} | "
             f"{fp['target']} | {_met(fp['met'])} |")
    L += ["", "n/a: not measured in this run (e.g. no LLM text without an API key or with "
          "--no-llm).", ""]

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
          + ("" if "agent_usd" not in m["cost"] else
             f"agent {_usd(m['cost']['agent_usd'])}, agent research "
             f"{_usd(m['cost']['agent_research_usd'])}, A/B judge "
             f"{_usd(m['cost']['ab_judge_usd'])}, ")
          + f"total {_usd(m['cost']['total_usd'])} of the {_usd(m['cost'].get('limit_usd'))} limit; "
          f"per new text {_usd(m['cost']['per_text_usd'])}",
          f"- Judge prompt cache: {m['cost']['judge_cache']['write_tokens']} tokens written, "
          f"{m['cost']['judge_cache']['read_tokens']} read; judge errors: "
          f"{m['cost']['judge_cache']['errors']}", ""]

    if m.get("agent"):
        L += agent_section(result)

    L += ["## Judge (LLM, only what code cannot check)", ""]
    if m["judge"]:
        L += ["| Rubric item | yes | partly | no | Score (mean) | Spread | Texts that differ |",
              "|---|---|---|---|---|---|---|"]
        for item, j in m["judge"].items():
            spread = "n/a" if j.get("spread") is None else f"{j['spread']:.2f}"
            L.append(f"| {item} | {j['yes']} | {j['partly']} | {j['no']} | {_pct(j['score'])} | "
                     f"{spread} | {j.get('disagree', 0)} of {j.get('texts', 0)} |")
        L += ["", "Score: yes = 1, partly = 0.5, no = 0, mean over all grades. Spread: "
              "max - min of the score of one text over its repeated grades (judge_repeats), "
              "mean over the texts; n/a with one grade per text.", ""]
    else:
        L += ["n/a: no graded text (the judge is off, has no API key, or there is no LLM "
              "text).", ""]

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
        same = m.get("same_top3")
        if same is not None:
            L += [f"Diverse recommendations (D19): {same['count']} of {same['personas']} base "
                  f"personas share the most common recommended top 3 in this run (before D19: 2 "
                  f"— P01 = P04 and P02 = P05; 4 of 5 had only cash-like funds at SPK risk 1).",
                  ""]
        for sr in regressions:
            sc = by_id[sr.scenario.id]
            failed = sorted({c.check for c in sc.all() if c.status == FAIL})
            L.append(f"- **{sr.scenario.id}**: {sr.scenario.description} — "
                     + ("passes" if not failed else f"FAILS: {', '.join(failed)}"))
        L.append("")
    return "\n".join(L)


def _top(ids) -> str:
    return ", ".join(i.split(":", 1)[-1] for i in ids) if ids else "-"


def agent_section(result) -> list[str]:
    """E11: the agent's top 3 per scenario, the rule check, fallbacks, repeatability,
    the A/B judge, cost and time."""
    from rmprep.eval.agent_eval import top3

    m, meta = result.metrics["agent"], result.meta.get("agent") or {}
    states = ", ".join(f"{k} {v}" for k, v in m["states"].items()) or "-"
    L = ["## Agent (E11)", "",
         f"- Agent: {meta.get('model', '?')}, prompt {meta.get('prompt_version', '?')}, "
         f"{meta.get('candidates', '?')} candidates"
         + ("" if meta.get("llm", True) else " (no API key: the agent is off)")
         + f"; A/B judge: {meta.get('ab_judge') or 'off'}",
         f"- Decisions: {m['decisions']} ({states}); from the cache of an earlier suite run: "
         f"{m['cached']}"]
    rule = result.metrics["checks"].get("agent_decision")
    if rule:
        L.append(f"- Rule check `agent_decision` (spec section 6): {rule['pass']} pass, "
                 f"{rule['fail']} fail, {rule['n/a']} n/a ({_pct(rule['rate'])})")
    cs = m["cache_same"]
    L.append(f"- Same run, same decision (cache): {cs['same']} of {cs['runs']}")
    L += [f"- Error: {sid}: {_cell(e)}" for sid, e in m["errors"].items()]
    L.append("")

    by_ab = {g.scenario_id: g for g in getattr(result, "ab", ())}
    L += ["| Scenario | Engine top 3 | Agent top 3 | Changed | State | Repeat (no cache) | "
          "A/B | Seconds | Cost |", "|---|---|---|---|---|---|---|---|---|"]
    for sr in result.runs:
        a = sr.runs[0].agent if sr.runs else None
        if a is None:
            continue
        d = a.decision
        state = "-" if d is None else d.state + (" (cached)" if a.cached else "")
        changed = m["changed"].get(sr.scenario.id, "-")
        rep = "-" if a.repeat is None else (
            ("same" if top3(a.repeat) == top3(d) else _top(top3(a.repeat)))
            + f" ({a.repeat.state})")
        g = by_ab.get(sr.scenario.id)
        ab = "-" if g is None else (g.winner or f"error: {g.choice.error}")
        L.append(f"| {sr.scenario.id} | {_top(() if d is None else d.engine_top3)} | "
                 f"{_top(top3(d))} | {changed} | {state} | {_cell(rep)} | {_cell(ab)} | "
                 f"{a.seconds:.1f} | {_usd(a.cost_usd)} |")
    L.append("")

    L += ["### Fallbacks", ""]
    if m["fallbacks"]:
        L += [f"- {n} × {_cell(reason)}" for reason, n in m["fallbacks"].items()]
    else:
        L.append("No fallback.")
    L.append("")

    r = m["repeat"]
    L += ["### Repeatability (a second decision without the cache; report only)", "",
          f"Identical top 3 (same order): {r['identical']} of {r['runs']} "
          f"({_pct(r['share_identical'])}); the same three products: {r['same_set']} of "
          f"{r['runs']}.", ""]

    ab = m["ab"]
    L += ['### A/B judge (blind, random order: "Hangisi müşteriye daha uygun ve neden?")', "",
          f"Graded: {ab['graded']} (agent {ab['agent']}, engine {ab['engine']}, equal "
          f"{ab['equal']}); not asked (same top 3): {ab['same']}; errors: {ab['errors']}. "
          f"The judge prefers the agent in {_pct(ab['share_agent'])} of the answers that "
          f"choose a side.", ""]
    for g in getattr(result, "ab", ()):
        if g.winner in ("", "same"):
            continue
        L.append(f"- **{g.scenario_id}**: {g.winner} — {_cell(g.choice.reason)}")

    for sr in result.runs:
        a = sr.runs[0].agent if sr.runs else None
        if a is None:
            continue
        for w in a.watch:
            place = f" (place {w['engine_place']})" if w["candidate"] else ""
            L.append(f"- **{sr.scenario.id}** watch {w['option_id']}: candidate "
                     f"{'yes' if w['candidate'] else 'no'}{place}, warnings "
                     f"{', '.join(w['warnings']) or '-'}, engine top 3 "
                     f"{'yes' if w['engine_top3'] else 'no'}, agent top 3 "
                     f"{'yes' if w['agent_top3'] else 'no'}")
        if a.news:
            shown = top3(a.decision) or ()
            kept = ", ".join(f"{o.split(':', 1)[-1]} {'kept' if o in shown else 'dropped'}"
                             for o in a.news)
            L.append(f"- **{sr.scenario.id}** injected negative news on {_top(a.news)}: {kept}")

    c, t = m["cost"], m["time"]
    L += ["", "### Agent cost and time", "",
          f"- Agent model {_usd(c['model_usd'])} (with the repeats), research "
          f"{_usd(c['research_usd'])}, A/B judge {_usd(c['ab_judge_usd'])}; total "
          f"{_usd(c['total_usd'])}",
          f"- Decision per run (new): {_sec(t['decision_s'])}; repeat: {_sec(t['repeat_s'])}",
          ""]
    return L


def write_report(out_dir: Path | str, result) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(
        json.dumps(to_json(result), ensure_ascii=False, indent=1, default=str) + "\n",
        encoding="utf-8", newline="\n")
    (out / "report.md").write_text(to_markdown(result), encoding="utf-8", newline="\n")
    return out
