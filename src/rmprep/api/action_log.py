"""RM action log (L1; spec docs/superpowers/specs/2026-10-15-rm-action-log-design.md).

Every decision and edit of the RM is one JSON line in
<folder>/<YYYY-MM-DD>.jsonl (Turkish day): the data for a later eval /
optimization loop. Server side only; nothing goes to an LLM or an outside
service. A failed write never changes the RM's action: the error goes to stderr.
"""

from __future__ import annotations

import json
import sys
import threading
from collections.abc import Callable, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

from rmprep.contracts import TR_TZ, DecisionResult


class ActionLog:
    def __init__(self, folder: Path | str, *,
                 now: Callable[[], datetime] = lambda: datetime.now(TR_TZ)) -> None:
        self._folder = Path(folder)
        self._now = now
        self._lock = threading.Lock()

    def path_for(self, day: date) -> Path:
        return self._folder / f"{day.isoformat()}.jsonl"

    def append(self, action: str, *, run: DecisionResult | None = None, run_id: str = "",
               new_run_id: str = "", lang: str = "",
               details: Mapping[str, Any] | None = None) -> None:
        """One record; keys in the fixed order of the spec (section 4)."""
        try:
            ts = self._now().astimezone(TR_TZ)
            rec: dict[str, Any] = {"ts": ts.isoformat(), "action": action,
                                   "run_id": run_id or (run.run_id if run is not None else "")}
            if new_run_id and new_run_id != rec["run_id"]:
                rec["new_run_id"] = new_run_id
            rec["persona_id"] = run.persona.persona_id if run is not None else ""
            rec["snapshot_id"] = run.snapshot_id if run is not None else ""
            if lang:
                rec["lang"] = lang
            rec["details"] = dict(details or {})
            line = json.dumps(rec, ensure_ascii=False, default=str) + "\n"
            with self._lock:
                self._folder.mkdir(parents=True, exist_ok=True)
                with self.path_for(ts.date()).open("a", encoding="utf-8", newline="\n") as f:
                    f.write(line)
        except Exception as e:          # never breaks the RM's action
            print(f"action log: {action}: {type(e).__name__}: {e}", file=sys.stderr)
