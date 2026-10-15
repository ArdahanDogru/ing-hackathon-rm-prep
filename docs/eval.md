# Eval — design (DRAFT for the session with the user)

Status: **designed 2026-10-10 (the user with ing-lead); scope: the prototype
(MVP).** Code: `src/rmprep/eval/`, tests: `tests/eval/`.

## Why (brief)

- Deliverable 5 "Test ve öğrenimler": test scenarios, chosen success metrics,
  observed results, at least one error analysis, at least one improvement based
  on it.
- Section 9.1: "Çözümümüzün iyi çalıştığını nasıl gösterdik?" Possible
  dimensions: consistency of the recommendations, compliance with the client
  constraints, behaviour with missing or conflicting data, correct use of the
  sources, consistency over repeated runs, processing time, contribution to the
  RM's preparation.
- Section 9.3 "Jüri Challenge": the jury changes a client field, a constraint,
  the data access or the scenario and watches the reaction.
- Section 12 rule 5 (checked per scenario by the jury): a product that breaks
  the risk profile or an explicit constraint must not enter the recommendation
  list or the offer text. Rules 2, 3, 6, 7 are also checkable.

The eval is the improvement loop of the whole system (ingest, decision,
narrator, UI backend), not only of the narrator.

## Shape

```
scenarios (YAML: persona + edits + source exclusions + answers + snapshot)
  -> run each through RealBackend (decide, approve a fixed selection, narrate)
  -> checks per run (code; an LLM judge only where code cannot judge)
  -> metrics per scenario and in total -> report (Markdown + JSON) in data/eval/
```

Deterministic by default: a fixed snapshot, the narrator cache, no clock in the
checks. One run of the full suite is a command: `python -m rmprep eval`.

## Scenarios

| Group | Examples |
|---|---|
| Base | P01–P05 as given, on the frozen eval snapshot |
| Jury-style persona edits | risk "Agresif" → "Muhafazakâr"; horizon "5+ yıl" → "1 yıl"; liquidity "Düşük" → "Yüksek"; FX text unknown → question |
| Jury-style constraints | add "döviz maruziyeti istemiyor", "yüksek riskli ürün istemiyor", an unknown constraint text → blocking question |
| Data access | exclude `tefas_detail`; exclude `manual` (no deposit rates, no CPI, no stopaj); exclude `tefas_web` (no returns, no risk) |
| Conflicting / bad data | a fixture snapshot with a conflicting price, an out-of-range risk, a stale row |
| Repeat | each base scenario twice |

## Checks and metrics

| Metric | Check (code) | Target |
|---|---|---|
| Rule 5 compliance | no rejected or constraint-breaking option in the short list (first 20), in the selection or named in the text | 100 % |
| Risk ceiling | no option above the ceiling anywhere in `options` | 100 % |
| Not buyable | no `fund_buyable = 0` fund in `options` (after D12) | 100 % |
| No invented data (rule 3) | with a source excluded, every number in the result and the text exists in the evidence | 100 % |
| Missing data is shown | the excluded or failed source appears in the notes; the affected options lose confidence | 100 % |
| Questions instead of guesses | an unknown blocking text → `needs_rm_input`, nothing ranked | 100 % |
| Consistency | the same inputs → the same `run_id` and identical result; the narrator text from the cache | 100 % |
| Sensitivity | a persona edit changes the short list in the expected direction (e.g. lower average risk after "Muhafazakâr") | per scenario |
| Narrator quality | validator pass rate of LLM texts; forbidden phrases 0; citations present | ≥ 95 % pass, 0 phrases |
| Source traceability (rule 2) | every option and every text sentence cites existing evidence ids with source and time | 100 % |
| Time | seconds per decide; seconds per narrator text | report only |
| Cost | USD per narrator text and per suite run | report only |

LLM judge (decided; the rubric and instructions in a cached system block, the user
2026-10-10): Claude Haiku 5.5 (`claude-haiku-5-5`, about $0.003 per
text) grades only what code cannot: is the text tailored to this client (brief
section 3, "genel teklif"), is it clear for the RM. Fixed choices per rubric item
(e.g. yes / partly / no) and a one-line reason, through structured output. The
rule checks stay in code. The judge sits behind a small `Judge` protocol, so Jev
(TypeSafe AI, decision-only, independent of Claude) can replace it or grade the
same texts later for an agreement check (later; Jev is marked "later").

## Error analysis and improvements (for deliverable 5)

Recorded cases with cause, fix and measured effect (the eval keeps them as
regression scenarios):

1. **Deposit baseline above every fund** (2026-10-10): the score was nominal;
   23 % with 29.73 % CPI is −8.3 % real after tax. Fix D9 (real return after
   tax, `real_loss`). Effect: P01 baseline 0.912 → 0.569, below the best fund.
2. **Funds that cannot be bought** (2026-10-10): 189 of 809 funds do not trade
   on TEFAS or are closed; 1–4 of them were in each persona's top 20. Fix I3b +
   D12 (`not_buyable`). Effect: measured after D12.
3. **Explicit constraints only as penalties** (2026-10-10): `fx_limit` (P02) and
   `liquidity_need` (P05) only lower the score; FX funds stay in the full list
   (P02: 8). Fix: proposed D13 (hard filters). Effect: measured after D13.
4. **TEFAS detail source failed on its first live run** (2026-10-10): valör was
   required but null for funds not on TEFAS. Fix: optional fields. Effect: 815
   pages ok, 9 rejected rows.

## Decisions (the user, 2026-10-10)

1. Scenarios as above. TODO (after the MVP): more Jury-Challenge-style
   scenarios that the user expects from the jury.
2. Targets as in the table.
3. LLM judge: yes, Claude Haiku 5.5 (Jev possible later, see above).
4. A frozen eval snapshot: the first full snapshot after D12 and D13
   (`config/eval.yaml`, set by the lead).
5. Budget: the eval has its own limit, $5 per suite run, separate from the RM's
   daily narrator limit (about $2.50 for texts + $0.15 for the judge on the
   first run; cached after that).

Config: `config/eval.yaml` (lead-owned). Scenario files:
`src/rmprep/eval/scenarios/*.yaml` (eval-owned). Reports: `data/eval/<date>-<suite>/`
(git-ignored).

## Milestones (worker `ing-eval`; each ends with green `pytest`)

| # | Milestone | Tests show |
|---|---|---|
| E1 | scenario format + runner on RealBackend (fake narrator in tests) | a scenario file runs; edits and exclusions apply |
| E2 | the checks and metrics of the table | each check catches a hand-made violation |
| E3 | report (Markdown + JSON), `python -m rmprep eval` (lead wires the CLI) | report from a small suite |
| E4 | the error-analysis cases as regression scenarios | each case passes after its fix |
| E8 | (web UI, 2026-10-11; found by the full eval of prompt n6) `no_invented_data` also accepts the numbers of the run's display facts (`rmprep.decision.display.display_facts`: returns per period, real 1-year return, risk, valör) and the evidence rows they cite, because the narrator pack and the screens use them (N9). Before: 2 false findings (P03 edits: NJR 1-year return 49,2 used, only the 3-year row cited) | a text with a display-facts number passes; a number in neither the result, its evidence nor the display facts still fails; the two P03 edit scenarios pass |
| E9 | (2026-10-12, decision D19; docs/decision.md section 10) regression scenarios for diverse recommendations: a new check `diverse_recommendations` — for a Dengeli or Agresif persona, or one with the diversity priority, `recommended` has at most one `nakit_benzeri` option and at least two asset classes when the result has them; for Muhafazakâr / Temkinli without that priority the check does not apply; every recommended fund is inside the risk ceiling; no class-rule pick has a negative real 1-year return. Scenarios: `reg-d19-p02-diverse`, `reg-d19-p04-diverse`, `reg-d19-p01-unchanged` (P01 keeps its plain score order), plus a Jury-Challenge style edit `edit-p05-dengeli` (P05 with risk_profili Dengeli gets the class rule). The report names the error case: before D19, 4 of 5 personas had the same top 3 | each scenario passes on the frozen snapshot with the main config; the check catches a hand-made result with 2 cash-like recommendations |
| E10 | (2026-10-12, judge analysis) judge version j3: the judge prompt names all 8 sections (with talking_points), says which sections the RM sees collapsed (alternatifler, sorular, varsayimlar) and that varsayimlar is engine text, and gets the per-option facts it may expect (access, risk level) so it can see what was left out; the rubric definitions and "when in doubt choose the lower one" stay; an optional `judge_repeats` (default 1) grades a text n times with a seed in the cache key and reports the mean | the prompt holds the new context; repeats change the cache key; old cached verdicts do not match j3 |

## Eval of 2026-10-15 (lead): ETFs, shares, 5-year history, D26–D27

- Frozen snapshot `20261014-233110-1565` (36 ETFs, 590 shares after D26b, 5 years
  of BIST bulletins, BIST 100 indices for 5 years). Reports: first full run
  `data/eval/20261014-235326-20261014-full` ($0.96), final run with the new check
  `data/eval/20261015-013525-20261015-final` (cached texts, $0).
- **E10 `allocation_projection`** (lead, 2026-10-15): for every ready run with a
  D27 current split: the points add up to 100 (± 0.5) and lie in their ranges;
  only rows from `rm`, `rm_confirmed` or `persona_text` are active; each gap is the
  distance to the band edge; without an active row no option has the
  `allocation_gap` criterion (so the ranking is the one without D27). 37 pass,
  2 n/a (runs that wait for an RM answer).
- **Error found by the first full run (case 9):** all 25 LLM texts failed rule 3
  on the code-written market note `piyasa_notu` (USD/TRY "49,28", the BIS policy
  rate date "2026-08-31"): the check allowed only values of the rows the decision
  result references, but the market note cites its own EVDS rows. Fix in
  `check_no_invented_data`: a sentence may use the value and date of the rows it
  cites itself; the same figure without the citation still fails (test
  `test_a_sentence_may_use_the_rows_it_cites_itself`). After the fix: 100 %.
- Final targets: rule checks 100 % (15 checks, 39 runs), narrator validator 100 %
  (25 LLM texts, prompt n10), forbidden phrases 0. Judge (Haiku): tailored 55 %,
  clear for the RM 52 %, balanced 62 % (14.10 morning, prompt n9: 50 / 57 / 62 %).
- Top 3: P01 PPN, OSD, AIS; P02 EIL, KDE, NJR; P03 ASELS (share), IDY, OKT; P04 RPP,
  OKT, TCF; P05 EIL, GBL, KSK.

## E11: eval of the agentic top-3 decision (2026-10-15, ing-eval; eval@073ac4b)

- `rmprep eval --agent` turns it on (about $2; without the flag the eval is
  unchanged: no files, no check, no calls). With `--no-llm` too, the agent part
  runs without model calls.
- Check `agent_decision` (rule checks): `rmprep.agent.checks.check_decision` on the
  stored picks against a pack the eval builds again, plus `engine_top3` and the
  estimate / web labels and flags; n/a without a decision or with the agent off; a
  fallback passes and its reason is counted; a decision still running at the
  deadline fails.
- `agent_eval.py`: one AgentService per scenario run with its own cache
  (`data/eval/agent/<scenario>/`); the eval's limit of $5 applies (the agent's daily
  limit is off); `RecordingResearch` adds injected news and records the research;
  the pack is stored next to the decision. Scenarios
  `src/rmprep/eval/scenarios/agent/agent.yaml`: agent-negative-news (P01, a negative
  event for the engine's #1), agent-rm-split (P03, RM split 80/5/10/5/0),
  agent-crash (P03, watch stock:KTLEV); keys `holdings`, `holdings_origin`,
  `agent_news`, `agent_watch`.
- Repeatability: a second decision in a fresh cache dir; the share of identical
  top 3 (report only); the cache gives the same decision again.
- A/B judge (Haiku, blind, order seeded by the run id, cached in
  `data/eval/judge-ab/`): agent, engine or equal; a top 3 that did not change is not
  sent. Report section "Agent (E11)".

## E12: RM marks on research findings (2026-10-15, ing-eval; eval@567309e)

- Scenario key `agent_marks` ({product: engine1|engine2|engine3, finding: index or
  "news:<i>", mark: ok|wrong}), resolved to finding ids on the research of the run
  (`RecordingResearch.marks()`; only the scenario marks, so the eval stays
  deterministic). Scenario `agent-marks`: P01, ✗ on highlight 0 of the engine's #2,
  ✓ on highlight 0 of the engine's #1.
- Check `agent_marks` (rule checks): the ✗ finding is not in the stored pack; the ✓
  finding has `dogrulama` "RM doğruladı"; a reason that cites it has "(web, RM
  doğruladı)"; `marks_hash` equals the hash of the marks.
- Live run 2026-10-15 (`data/eval/20261015-235705-20261015-marks`, $0.14): all
  rule checks 100 %; ✗ OSD `Fa4f2a072` removed, ✓ PPN `Fdb2a3e1e` confirmed (not
  cited); agent top 3 PPN, OSD, ZBJ (engine PPN, OSD, AIS).
