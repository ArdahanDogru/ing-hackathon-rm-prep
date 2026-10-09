"""The PreToolUse guard that keeps each worker in its own folders."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "guard_paths.py"
spec = importlib.util.spec_from_file_location("guard_paths", HOOK)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

MAIN = "C:/repo/prototype"
WT = "C:/wt/decision"
TREES = [MAIN, WT, "C:/wt/ui"]


def edit(path, cwd=WT, tool="Edit"):
    return {"tool_name": tool, "tool_input": {"file_path": path}, "cwd": cwd}


def shell(cmd, tool="PowerShell"):
    return {"tool_name": tool, "tool_input": {"command": cmd}, "cwd": WT}


def test_worker_edits_only_its_own_folders():
    assert guard.check(edit("src/rmprep/decision/scoring.py"), "decision", WT, TREES) is None
    assert guard.check(edit(f"{WT}/tests/decision/test_x.py", tool="Write"), "decision", WT, TREES) is None
    for path in ("src/rmprep/contracts.py", "src/rmprep/ingest/store.py", "CLAUDE.md",
                 "tests/contracts/fixtures/evidence_small.json", "pyproject.toml"):
        assert "may edit only" in guard.check(edit(path), "decision", WT, TREES), path


def test_worker_never_edits_main_or_another_worktree():
    assert "another checkout" in guard.check(edit(f"{MAIN}/src/rmprep/decision/x.py"), "decision", WT, TREES)
    assert "another checkout" in guard.check(edit("C:/wt/ui/src/rmprep/ui/app.py"), "decision", WT, TREES)


def test_files_outside_the_repo_and_the_lead_are_free():
    assert guard.check(edit("C:/Temp/scratch.txt"), "decision", WT, TREES) is None
    assert guard.check(edit("src/rmprep/contracts.py", cwd=MAIN), "main", MAIN, TREES) is None
    assert guard.check(shell("git merge decision"), "main", MAIN, TREES) is None


def test_worker_git_limits():
    for cmd in ("git merge main", "git push", "git checkout main", "git switch main",
                "git -C . reset --hard HEAD~1", "git fetch; git merge x"):
        assert guard.check(shell(cmd), "decision", WT, TREES), cmd
    for cmd in ("git rebase main", "git commit -m x", "git status", "git log main..decision",
                "git diff main", "git stash"):
        assert guard.check(shell(cmd, tool="Bash"), "decision", WT, TREES) is None, cmd


def test_branch_names_map_to_modules():
    assert guard.module_of("decision") == "decision"
    assert guard.module_of("ui-fake-backend") == "ui"
    assert guard.module_of("main") is None and guard.module_of("uix") is None


def test_hook_blocks_with_exit_code_2_in_a_real_repo(tmp_path):
    repo = tmp_path / "r"
    subprocess.run(["git", "init", "-q", "-b", "decision", str(repo)], check=True)
    event = {"tool_name": "Write", "tool_input": {"file_path": "src/rmprep/contracts.py"}, "cwd": str(repo)}
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True, text=True)
    assert r.returncode == 2 and "may edit only" in r.stderr
    bom = subprocess.run([sys.executable, str(HOOK)], input=("﻿" + json.dumps(event)).encode("utf-8"),
                         capture_output=True)
    assert bom.returncode == 2  # PowerShell pipes add a BOM
    event["tool_input"]["file_path"] = "src/rmprep/decision/x.py"
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True, text=True)
    assert r.returncode == 0
