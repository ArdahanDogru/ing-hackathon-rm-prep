# Eval — design (DRAFT for the session with the user)

Status: **draft 2026-10-10 by ing-lead; the decisions marked OPEN are for the
session with the user.** Code: `src/rmprep/eval/`, tests: `tests/eval/`.

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

OPEN: an LLM judge (Claude Haiku 5.5, about $0.003 per text) for "is the text
tailored to this client" (brief section 3, "genel teklif") — or the RM's own
review only.

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

## OPEN decisions for the session

1. The scenario list (above) — add or remove.
2. The targets.
3. LLM judge: yes (Haiku 5.5) or no.
4. The frozen eval snapshot: the latest full snapshot after D12.
5. Budget per suite run (narrator texts: about 25 scenarios × 2 languages ×
   $0.05 ≈ $2.50 with Sonnet 5.5; cached after the first run).

## Milestones (worker `ing-eval`; each ends with green `pytest`)

| # | Milestone | Tests show |
|---|---|---|
| E1 | scenario format + runner on RealBackend (fake narrator in tests) | a scenario file runs; edits and exclusions apply |
| E2 | the checks and metrics of the table | each check catches a hand-made violation |
| E3 | report (Markdown + JSON), `python -m rmprep eval` (lead wires the CLI) | report from a small suite |
| E4 | the error-analysis cases as regression scenarios | each case passes after its fix |
