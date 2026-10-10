"""StopFailure hook (all sessions of this project: lead and worker worktrees).

A turn that ends on an API error (a usage or session limit, an overload) used to
stop a worker silently. This hook logs the event and pushes one line to the
user's phone through the fleet notify script. It never fails: a broken hook
must not break the session.

Env: FLEET_NOTIFY_PRINT=1 prints instead of pushing (tests);
ING_FAILURE_LOG overrides the log file (default ~/.claude/ing-session-failures.jsonl).
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

NOTIFY = "C:/Users/yardang/fleet/hooks/notify.sh"
# Git Bash, not the WSL bash.exe of Windows (which a bare "bash" finds first).
BASH_CANDIDATES = ("C:/Users/yardang/PortableGit/usr/bin/bash.exe",
                   "C:/Users/yardang/PortableGit/bin/bash.exe",
                   "C:/Program Files/Git/bin/bash.exe")


def git_bash() -> str:
    return os.environ.get("FLEET_BASH") or next(
        (b for b in BASH_CANDIDATES if Path(b).exists()), "bash")


def session_name(cwd: str) -> str:
    m = re.search(r"ing-wt[\\/]+([A-Za-z0-9_-]+)", cwd or "")
    return f"ing-{m.group(1)}" if m else "ing-lead"


def error_text(d: dict) -> str:
    for key in ("error", "error_message", "message", "reason", "stop_reason", "error_type"):
        v = d.get(key)
        if isinstance(v, dict):
            v = v.get("message") or v.get("type") or json.dumps(v, ensure_ascii=False)
        if v:
            return str(v)[:120]
    return "unknown API error"


def main() -> int:
    try:
        raw = sys.stdin.read()
        d = json.loads(raw) if raw.strip() else {}
        if not isinstance(d, dict):
            d = {}
    except Exception:
        d = {}
    name = session_name(str(d.get("cwd", "")))
    msg = f"ing: {name} stopped ({error_text(d)}); tell ing-lead to resume it"
    try:
        log = Path(os.environ.get("ING_FAILURE_LOG") or Path.home() / ".claude" / "ing-session-failures.jsonl")
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "session": name,
                                "payload": d}, ensure_ascii=False) + "\n")
    except Exception:
        pass
    try:
        p = subprocess.run([git_bash(), NOTIFY, msg], capture_output=True, text=True, timeout=20)
        if p.stdout:
            sys.stdout.write(p.stdout)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
