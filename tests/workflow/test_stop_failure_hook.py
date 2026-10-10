"""The StopFailure hook: a session whose turn ends on an API error (e.g. a usage
limit) pushes a message to the user's phone and logs the event."""

import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "notify_stop_failure.py"


def run(payload, tmp_path):
    env = dict(os.environ, FLEET_NOTIFY_PRINT="1", ING_FAILURE_LOG=str(tmp_path / "log.jsonl"))
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), text=True,
                       capture_output=True, env=env, timeout=30)
    return p, tmp_path / "log.jsonl"


def test_worker_usage_limit_is_pushed_and_logged(tmp_path):
    payload = {"hook_event_name": "StopFailure", "session_id": "s1",
               "cwd": r"C:\Users\yardang\dev\ing-wt\eval",
               "error": {"type": "rate_limit_error", "message": "Session limit reached"}}
    p, log = run(payload, tmp_path)
    assert p.returncode == 0
    assert "ing-eval" in p.stdout and "Session limit reached" in p.stdout
    assert json.loads(log.read_text(encoding="utf-8").splitlines()[0])["payload"] == payload


def test_lead_and_unknown_shapes_never_fail(tmp_path):
    p, _ = run({"cwd": "C:/Users/yardang/dev/ing-hackathon/prototype", "reason": "overloaded"}, tmp_path)
    assert p.returncode == 0 and "ing-lead" in p.stdout and "overloaded" in p.stdout
    p, _ = run({}, tmp_path)
    assert p.returncode == 0 and "stopped" in p.stdout
