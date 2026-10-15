# RM action log (L1) — Implementation Plan

> **For agentic workers:** one task, done by ing-lead on `main`. Steps use
> checkbox (`- [ ]`) syntax. Read the spec first.

**Goal:** Every decision and edit of the RM is written as one JSON line to
`data/logs/rm-actions/<day>.jsonl`, server side, without a web change.

**Architecture:** `src/rmprep/api/action_log.py` (`ActionLog.append`, never raises);
`create_app(..., action_log=None)` calls it in the write endpoints; `research_router`
gets an optional `log` callback; `serve.py` builds the log for the real app.

**Tech Stack:** Python 3.11+, FastAPI, pytest.

**Spec:** `docs/superpowers/specs/2026-10-15-rm-action-log-design.md`

## Global Constraints

- Actions and details exactly as spec section 5; `ts` in Europe/Istanbul; one file per Turkish day; fixed key order `ts, action, run_id, new_run_id?, persona_id, snapshot_id, lang?, details`.
- A failed write never changes the response; errors only to stderr.
- No record for a `GET` other than `card.md`; refused calls logged only for `card_downloaded` and `research_question`.
- No web change; `action_log=None` (tests, FakeBackend apps) logs nothing.
- Commit only on pytest exit code 0.

## Review Focus

1. Two requests at the same time: both lines are complete (a lock around the append) — `test_parallel_appends_stay_whole`.
2. A restore (`text: null`) of a block that was never edited: `before` = `after` = the original, action `text_block_restored` — `test_restore_of_an_unedited_block`.
3. The folder is read-only: the endpoint answers 200 as without the log — `test_write_failure_does_not_break_the_action`.
4. A refused card (open rule finding): one record with `refused: true` and the 422 unchanged — `test_refused_card_is_logged`.
5. A refused research question: one record with `refused: true` — `test_refused_research_question_is_logged`.

---

### Task 1: ActionLog and its calls (lead, main)

**Files:**
- Create: `src/rmprep/api/action_log.py`, `tests/api/test_action_log.py`
- Modify: `src/rmprep/api/app.py` (param `action_log`; calls in `new_run`, `answer`, `holdings`, `approval`, `notes`, `edit_block`, `card_md`), `src/rmprep/api/research.py` (`research_router(..., log=None)`), `src/rmprep/api/serve.py`, `docs/web-ui.md` (section "RM action log (L1)" with the KVKK note)

**Interfaces:**

```python
class ActionLog:
    def __init__(self, folder: Path | str, *, now: Callable[[], datetime] = ...): ...
    def append(self, action: str, *, run: DecisionResult | None = None, run_id: str = "",
               new_run_id: str = "", lang: str = "", details: Mapping[str, Any] | None = None) -> None
    def path_for(self, day: date) -> Path
```

- [ ] **Step 1:** write `tests/api/test_action_log.py` (each action of spec section 5 through the API with the FakeBackend and a FakeAgent; the 5 Review Focus cases; no record for a plain `GET /api/runs/{id}`).
- [ ] **Step 2:** run — FAIL (ImportError).
- [ ] **Step 3:** implement `ActionLog` (JSON line with `ensure_ascii=False`, `sort_keys=False`, the fixed key order; `threading.Lock`; `try/except OSError` → stderr) and the calls; `before` of a block = `rm_edits[block]` when present, else the joined sentences of the block in the draft before the call (`rmprep.edits._block_of`).
- [ ] **Step 4:** full pytest exit 0.
- [ ] **Step 5:** commit `L1: RM action log`; docs line; tell the user.
