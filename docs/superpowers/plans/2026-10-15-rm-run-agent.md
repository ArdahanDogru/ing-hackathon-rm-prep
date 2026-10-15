# The agent on the RM's request, with research marks — Implementation Plan

> **For agentic workers:** multi-agent workflow (`docs/workflow.md`): ing-lead does
> Tasks 1, 4, 6 on `main`; ing-lead-2 Task 2 (R4, branch `research`); ing-agent
> Task 3 (A2, branch `agent`); ing-web Task 5 (W24, branch `web`, after W23).
> Steps use checkbox (`- [ ]`) syntax. Read the spec first.

**Goal:** The agent runs only when the RM starts it (with N), and it uses the RM's
✓/✗ marks on the research bullets; the stable part of its input is prompt-cached.

**Architecture:** Marks live in the research service (per finding id and day). The
API stops starting the agent in `_view`; a new `POST /api/runs/{id}/agent {n}`
starts it. The agent pack splits into a cached stable block and an uncached
research block with the marks.

**Tech Stack:** Python 3.11+, FastAPI, anthropic, pytest; React 18 + TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-15-rm-run-agent-design.md`

## Global Constraints

- Marks: `"ok"` (✓ doğrulandı), `"wrong"` (✗ yanlış / alakasız), `None` (no mark); per finding id per Turkish day; `data/research/marks/<day>.json`.
- ✗ findings never reach the agent; ✓ findings carry `dogrulama: "RM doğruladı"`; unmarked `"doğrulanmamış"`; reason label "(web, RM doğruladı)" for a ✓ citation.
- N: 3 ≤ n ≤ `max_candidates` (20); default `candidates` (10).
- User message block 1 (stable, `cache_control`), block 2 (research with marks, no `cache_control`).
- Decision cache key adds N and the marks hash of the candidates' findings; `AgentDecision.n_candidates`, `.marks_hash`.
- Prompt `a3`. The API never starts the agent by itself.
- Tests without network; commit only on pytest exit code 0.

## Review Focus

1. A mark on a finding that a later Exa call no longer returns (the text changed): the mark stays in the file and has no effect — R4 `test_mark_of_an_unknown_finding_is_kept_and_ignored`.
2. Two runs on the same day show the same fund: a ✓ in run 1 shows in run 2 too — R4 `test_marks_are_shared_by_runs_of_the_day`.
3. The RM presses "Ajanı çalıştır" twice quickly: one job, the second call returns the running decision — lead `test_double_start_is_one_job`.
4. N out of range (2, 21, "abc"): 422, nothing starts — lead `test_agent_start_rejects_bad_n`.
5. A re-run with new marks and the same N: a new decision (marks hash differs), block 1 identical (cache read) — A2 `test_rerun_with_new_marks_keeps_block1`.

---

### Task 1: Contract v1.12 (lead)

- [ ] `AgentDecision` gets `n_candidates: int = 0` and `marks_hash: str = ""` (defaults keep v1.11 JSON valid); test in `tests/contracts/test_contracts_v1_12.py` (round trip; old JSON without the keys loads); full pytest; commit; tell the user.

### Task 2: R4 — marks in the research service (ing-lead-2)

**Interfaces:** `ResearchService.marks(day: date | None = None) -> Mapping[str, str]` (finding id → "ok" | "wrong"); `ResearchService.set_mark(finding_id: str, mark: str | None, run_id: str, option_id: str) -> None` (ValueError for another value); `status()` adds `"mark"` to each finding dict; `research_router` gets `POST /api/research/marks {finding_id, option_id, mark, run_id}` → 200 `{finding_id, mark}` and logs `research_marked` through the router's `log`.

- [ ] Tests first (set, remove, shared by runs, unknown id kept and ignored, bad value 422, the status shows the mark, the log call); pytest exit 0; report.

### Task 3: A2 — the agent with N and marks (ing-agent)

**Interfaces:** `AgentService.start(result, evidence, lang="TR", n: int | None = None) -> None` (ValueError for n out of range); `ResearchLike` gets `marks() -> Mapping[str, str]`; the pack removes ✗ findings and sets `dogrulama`; `AgentClient.step` sends the user content as two blocks (block 1 stable with `cache_control`, block 2 research); config keys `max_candidates: 20`; prompt `a3` (the "doğrulanmamış = henüz incelenmedi" rule); labels `web_confirmed: {TR: "(web, RM doğruladı)", EN: "(web, confirmed by the RM)"}`; decision cache key with N and the marks hash.

- [ ] Tests first (✗ removed, ✓ label, N range, cache key with N and marks, block 1 identical across a re-run with new marks, the client gets two blocks with cache_control only on block 1, the prompt rule); pytest exit 0; one live call on P01 with one ✓ and one ✗ (≤ $0.15) and the cache read tokens of a second run with one more mark; report.

### Task 4: API (lead)

- [ ] Tests first in `tests/api/test_agent_api.py`: `_view` does not start the agent; `POST /api/runs/{id}/agent {n}` starts it (202), default n; 422 for a bad n or a run that is not ready; double start = one job; `GET` before a start → `state: off`, `fallback_reason` "henüz çalıştırılmadı"; the action log `agent_started` with `n` and the mark counts.
- [ ] Implement; pytest exit 0; commit.

### Task 5: W24 — the screen (ing-web, after W23)

- [ ] The agent box before a run: text, field "Aday sayısı" (3–20, default 10), button "Ajanı çalıştır" → `POST /agent {n}`, then polling as today; after a run: "Yeniden çalıştır" with N. "Ajan araştırması": ✓/✗ toggles per bullet → `POST /api/research/marks`; marked state; ✗ dimmed "ajana verilmez"; after a run, the other candidates' research grouped by product. Tests first; vitest and build green; report with screenshots (before a run, marks, after a run).

### Task 6: Eval scenario and live check (lead)

- [ ] Scenario `agent-marks` (P01; ✗ on a finding of the engine's #2, ✓ on a finding of the engine's #1); run `rmprep eval --agent --only agent-marks` (≤ $0.30); a live check in the app; docs; push when the user asks.
