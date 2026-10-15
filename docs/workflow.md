# Multi-agent workflow (set up 2026-10-10)

The project is built by fleet office sessions on laptop-a that message each
other (cross-session messaging, `SendMessage`). Not an agent team: fleet
sessions are `claude -p`, where teams cannot form. The user starts only
`ing-lead`; the lead starts and stops the workers.

| Session | Folder (git worktree) | Branch | Owns |
|---|---|---|---|
| `ing-lead` | `C:/Users/yardang/dev/ing-hackathon/prototype` | `main` | `contracts.py`, `grouping.py`, `cli.py`, `backend.py`, `__main__.py`, `pyproject.toml`, `CLAUDE.md`, `docs/`, `config/`, `.claude/`, `tests/contracts/`, `tests/cli/`, `tests/workflow/`, merges |
| `ing-ingest` | `C:/Users/yardang/dev/ing-wt/ingest` | `ingest` | `src/rmprep/ingest/`, `tests/ingest/` |
| `ing-decision` | `C:/Users/yardang/dev/ing-wt/decision` | `decision` | `src/rmprep/decision/`, `tests/decision/` |
| `ing-ui` | `C:/Users/yardang/dev/ing-wt/ui` | `ui` | `src/rmprep/ui/`, `tests/ui/` |
| `ing-narrator` | `C:/Users/yardang/dev/ing-wt/narrator` | `narrator` | `src/rmprep/narrator/`, `tests/narrator/` |
| `ing-eval` | `C:/Users/yardang/dev/ing-wt/eval` | `eval` | `src/rmprep/eval/`, `tests/eval/` |
| `ing-web` | `C:/Users/yardang/dev/ing-wt/web` | `web` | `web/` only (React app, docs/web-ui.md; added 2026-10-11) |
| `ing-lead-2` | `C:/Users/yardang/dev/ing-wt/research` | `research` | `src/rmprep/research/`, `tests/research/`, `src/rmprep/api/research.py`, `config/research.yaml`, `docs/research.md`, `web/src/components/ResearchPanel.tsx` (web research; started by the user 2026-10-14; merges go through ing-lead) |
| `ing-agent` | `C:/Users/yardang/dev/ing-wt/agent` | `agent` | `src/rmprep/agent/`, `tests/agent/` (agentic top-3 decision, docs/agent.md; added 2026-10-15) |

Design per module: ingest = `docs/ingest.md`, decision = `docs/decision.md`,
ui = `docs/ui.md`, narrator = `docs/narrator.md`, eval = `docs/eval.md`,
web = `docs/web-ui.md` (plan: `docs/superpowers/plans/2026-10-11-web-ui.md`).

## Rules for everyone

- A worker edits only its two folders. `.claude/hooks/guard_paths.py` blocks
  other edits, merges, pushes, `checkout main`, `reset --hard` and the fleet
  session tools on worker branches. Contracts, dependencies, config and docs
  change only through the lead.
- One test package per module: `tests/<module>/__init__.py`, fixtures in
  `tests/<module>/fixtures/`. Shared fixtures (personas, a small real
  EvidenceSet, illustrative DecisionResults) are in `tests/contracts/fixtures/`;
  the lead regenerates them with `python -m tests.contracts.make_fixtures`.
- All worktrees share `prototype/.venv`. pytest puts `src` first
  (`pythonpath = ["src"]`), so each worktree tests its own code. Python:
  `C:/Users/yardang/dev/ing-hackathon/prototype/.venv/Scripts/python`.
- Files keep LF line endings (`* -text`: git does not convert them);
  `tests/workflow/test_line_endings.py` fails on CRLF in `.py` files.
- Data (`data/`, `.env`) exists only in the main checkout. A live ingest from a
  worktree uses `python -m rmprep --root C:/Users/yardang/dev/ing-hackathon/prototype ...`.

## Messages (one short paragraph; no chatter)

- worker → lead: `contract request: <change> because <reason>` |
  `milestone <n> done, tests green, <branch>@<sha>` | `blocker: <what>`.
- lead → worker: `merged <branch>@<sha>, rebase` | an answer to a request or blocker.
- Workers do not message each other. The lead reports each merge, contract
  change, worker start and worker stop to the user in its own chat.

## Lead: merging

In the main checkout: `git merge --no-ff <branch>`, full `pytest`; for `web`
also `cd web; npm ci; npm test; npm run build`.
Green → keep it and tell the workers that are working now to rebase (an idle
worker rebases at the start of its next milestone; waking an idle session costs
a full context reread). Red → undo the merge and send the worker the failing
tests. Before you undo a merge, check that no worker has rebased on
it since (`git branch --contains <merge>`): a later merge of that branch brings
the undone merge back (2026-10-11: W5 came back through the narrator branch).
If a branch contains it, keep the merge and fix forward. Merge a branch only at
the sha that the worker reported (`git merge --no-ff <sha>`), not the branch
head, which can already hold the next milestone. Pushing: only the lead pushes `main`, to the private GitHub repo
`ArdahanDogru/ing-hackathon-rm-prep`, and only when the user asks (decided by the user
2026-10-11; the guard hook still blocks pushes from worker branches).

## Lead: pause, and after a restart

- "Pause" from the user (e.g. before the laptop sleeps or shuts down): ask each
  working worker to commit at the next safe point and say so; then
  `stop_session` it. Note in the chat which workers were stopped and at which
  milestone. Sleep only freezes the sessions; a shutdown ends them all.
- "Resume", or the user continued the lead after a restart/agent restart:
  `list_sessions`; `resume_session` each worker that was working (message:
  "the session restarted; check `git status`, commit or finish the open work,
  then continue your milestone"). Messages sent while a session was down are
  lost: ask each resumed worker for its state once.

## Stopped sessions (usage limits, API errors)

Added 2026-10-10 after two workers stopped silently on a usage limit.

- Hook `StopFailure` in `.claude/settings.json` (every session of the project,
  lead and workers): `.claude/hooks/notify_stop_failure.py` pushes
  "ing: <session> stopped (<error>); tell ing-lead to resume it" to the user's
  phone and appends the event to `~/.claude/ing-session-failures.jsonl`. A
  session loads hooks at start: a worker started before this change gets the
  hook only after a restart.
- The lead subscribes to an idle notice (`SendMessage` with
  `notify_when_idle: true`) for each worker it gives a milestone. An idle notice
  without a milestone or blocker message means the worker stopped: the lead
  checks `git status` / `git log main..<m>` in its worktree, sends the task again
  (a message wakes an idle session; `resume_session` only works on a stopped
  one), and pushes one line to the user.

## Lead: starting and stopping workers

At most 3 sessions work at the same time (the lead counts). Start a worker only
when its design doc is written and the contracts it uses are frozen. Fleet MCP
tools, device `laptop-a`:

1. `git worktree add -b <m> C:/Users/yardang/dev/ing-wt/<m> main` if the
   worktree is missing (else rebase it on main first).
2. `list_sessions` — no running session may already be named `ing-<m>`.
3. `start_session(device="laptop-a", cwd="C:/Users/yardang/dev/ing-wt/<m>",
   name="ing-<m>", prompt=<template below>, effort=<level below>)`.
4. When its work is merged and no milestone is left: `stop_session`. To bring a
   stopped worker back with its history: `resume_session` with a message.

Model and effort (set 2026-10-11 with the user). Every session runs on the
user's default model (Opus 5.5, 1M context); `start_session` and
`resume_session` take `effort` (and `model`, normally left out). Opus 5.5
defaults to `medium`; higher levels test more edge cases and verify more, at
more tokens and time.

| Session | Effort | Why |
|---|---|---|
| `ing-lead` | `high` | merges, red tests, contract requests, choices while the user is away |
| `ing-ingest`, `ing-decision`, `ing-eval` | `high` | parsing, scoring rules, determinism: edge cases matter |
| `ing-narrator` | `high` | output guard and claims must hold |
| `ing-ui`, `ing-web` | `medium` | clear scope; the user reviews it on screen |

Do not use `xhigh` or `max` as a worker default; for one hard task, ask the
user first or put `ultrathink` in that one message. To change a running
worker's effort: `stop_session` at a safe point, then `resume_session` with the
new `effort` (it is kept for later starts).

Worker prompt template (fill `<m>`, `<design doc>` and the first milestone):

```text
You are ing-<m>, the <m> worker for the ING hackathon prototype, in worktree
C:/Users/yardang/dev/ing-wt/<m> on branch <m>. Read docs/workflow.md ("Rules for everyone",
"Messages") and <design doc>.
You may change only src/rmprep/<m>/ and tests/<m>/ (fixtures in tests/<m>/fixtures/).
contracts.py, other modules, CLAUDE.md, docs/ and main belong to ing-lead; a hook blocks
edits there.
Python: C:/Users/yardang/dev/ing-hackathon/prototype/.venv/Scripts/python
- Need a contract change: send ing-lead "contract request: <change> because <reason>",
  then continue with other work.
- Each milestone: test-first, full test suite green, commit, then send ing-lead
  "milestone <n> done, tests green, <m>@<sha>".
- "merged X, rebase" from ing-lead: commit your work, `git rebase main`, rerun the tests, continue.
- Blocked: send ing-lead "blocker: <what>". Do not message other workers or other sessions.
Do not use the superpowers finishing-a-development-branch skill; merges belong to ing-lead.
Start with: <first milestone>.
```
