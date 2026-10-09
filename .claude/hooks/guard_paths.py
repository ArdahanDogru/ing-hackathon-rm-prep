"""PreToolUse guard for the multi-agent workflow (CLAUDE.md "Multi-agent workflow").

A session on branch main (the lead) may do anything. A session on a worker
branch (ingest, decision, ui, narrator, eval; also "<module>-..." or
"<module>/...") may edit only src/rmprep/<module>/ and tests/<module>/ of its
own worktree, never the main checkout or another worktree, and may not merge,
push, check out main or reset --hard. Files outside the repository (temp files)
are not checked.

Blocking = exit code 2 with the reason on stderr (Claude Code shows it to Claude).
Standard library only: the hook runs with the plain `python` on PATH.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

MODULES = ("ingest", "decision", "ui", "narrator", "eval")
EDIT_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path",
              "NotebookEdit": "notebook_path"}
SHELL_TOOLS = ("Bash", "PowerShell")
FORBIDDEN_GIT = [
    (re.compile(r"\bgit\b[^;&|\n]*\b(merge|push)\b"), "merging and pushing belong to ing-lead"),
    (re.compile(r"\bgit\b[^;&|\n]*\b(checkout|switch)\s+(-\S+\s+)*main\b"), "workers never check out main"),
    (re.compile(r"\bgit\b[^;&|\n]*\breset\b[^;&|\n]*--hard"), "no reset --hard; ask ing-lead"),
]


def _git(cwd: str, *args: str) -> str:
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def module_of(branch: str) -> str | None:
    for m in MODULES:
        if branch == m or branch.startswith((f"{m}-", f"{m}/")):
            return m
    return None


def _norm(p: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(p))).replace("\\", "/")


def check(event: dict, branch: str, top: str, worktrees: list[str]) -> str | None:
    """Reason to block, or None."""
    module = module_of(branch)
    if module is None:
        return None
    tool = event.get("tool_name", "")
    inp = event.get("tool_input") or {}
    if tool in SHELL_TOOLS:
        cmd = str(inp.get("command") or "")
        for pattern, why in FORBIDDEN_GIT:
            if pattern.search(cmd):
                return f"Blocked for the {module} worker: {why}."
        return None
    key = EDIT_TOOLS.get(tool)
    if not key or not inp.get(key):
        return None
    cwd = event.get("cwd") or top
    target = _norm(Path(cwd) / inp[key])
    own = _norm(top)
    others = [_norm(w) for w in worktrees if _norm(w) != own]
    if any(target == o or target.startswith(o + "/") for o in others):
        return (f"Blocked: {inp[key]} is in another checkout. The {module} worker edits only its "
                f"own worktree ({top}).")
    if not (target == own or target.startswith(own + "/")):
        return None  # outside the repository: scratch files are fine
    rel = target[len(own) + 1:]
    allowed = (f"src/rmprep/{module}/", f"tests/{module}/")
    if rel.startswith(allowed):
        return None
    return (f"Blocked: the {module} worker may edit only {allowed[0]} and {allowed[1]}; "
            f"{rel} belongs to ing-lead or another worker. For a contract change, send ing-lead "
            f"'contract request: <change> because <reason>'.")


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    cwd = event.get("cwd") or os.getcwd()
    top = _git(cwd, "rev-parse", "--show-toplevel")
    if not top:
        return 0
    branch = _git(cwd, "branch", "--show-current")  # works before the first commit too
    worktrees = [line[len("worktree "):] for line in _git(cwd, "worktree", "list", "--porcelain").splitlines()
                 if line.startswith("worktree ")]
    reason = check(event, branch, top, worktrees)
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
