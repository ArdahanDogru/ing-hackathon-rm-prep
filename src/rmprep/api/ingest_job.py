"""The data age and the "Veriyi yenile" ingest of the web app (docs/web-ui.md W14).

Not part of the Backend protocol (contracts.py is frozen): `create_app` takes an
optional IngestControl; without it the /api/ingest endpoints answer 404 and the
web app shows no line. One ingest at a time: this server runs at most one
thread, and the ingest lock (docs/ingest.md I6) also covers the daily
Task Scheduler job.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime

from rmprep.contracts import TR_TZ
from rmprep.ingest.pipeline import IngestBusy, Paths, ingest, ingest_status
from rmprep.ingest.snapshot import list_snapshots

STALE_AFTER_HOURS = 24.0
LOG = ("data", "logs", "ingest.log")   # the same log as scripts/run_ingest.cmd


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(TR_TZ).isoformat(timespec="seconds") if dt else None


class IngestControl:
    """`run`, `now` and `latest` are for tests (a fake ingest, a fixed clock and
    a fixed newest snapshot); the defaults are the real ones."""

    def __init__(self, paths: Paths, *,
                 run: Callable[[Paths], object] | None = None,
                 now: Callable[[], datetime] | None = None,
                 latest: Callable[[], tuple[str, datetime] | None] | None = None) -> None:
        self._paths = paths
        self._run = run or ingest
        self._now = now or (lambda: datetime.now(TR_TZ))
        self._latest = latest or self._latest_snapshot
        self._mutex = threading.Lock()
        self._thread: threading.Thread | None = None
        self._started_at: datetime | None = None
        self._finished_at: datetime | None = None
        self._error: str | None = None

    def _latest_snapshot(self) -> tuple[str, datetime] | None:
        snaps = list_snapshots(self._paths.snapshots)
        return (snaps[-1].snapshot_id, snaps[-1].created_at) if snaps else None

    def _mine_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status(self) -> dict:
        latest = self._latest()
        age = (self._now() - latest[1]).total_seconds() / 3600 if latest else None
        other = ingest_status(self._paths)          # the lock: this server or another process
        running = self._mine_running() or other["running"]
        started = _iso(self._started_at) if self._mine_running() else other["started_at"]
        return {
            "latest_snapshot": latest[0] if latest else None,
            "created_at": _iso(latest[1]) if latest else None,
            "age_hours": round(age, 1) if age is not None else None,
            "stale": age is None or age >= STALE_AFTER_HOURS,
            "running": running,
            "started_at": started if running else None,
            "finished_at": _iso(self._finished_at),
            "error": self._error,
        }

    def start(self) -> dict:
        """Start the ingest in a background thread; IngestBusy if one runs."""
        with self._mutex:
            other = ingest_status(self._paths)
            if self._mine_running() or other["running"]:
                raise IngestBusy(_iso(self._started_at) if self._mine_running() else other["started_at"])
            self._started_at, self._finished_at, self._error = self._now(), None, None
            self._thread = threading.Thread(target=self._work, name="ingest", daemon=True)
            self._thread.start()
        return self.status()

    def wait(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def _work(self) -> None:
        self._log(f"==== {_iso(self._now())} start (web app)")
        try:
            ev = self._run(self._paths)
            self._log(f"==== {_iso(self._now())} exit 0 {getattr(ev, 'snapshot_id', '')}")
        except Exception as e:   # shown on the web page; the next refresh can try again
            self._error = str(e) or type(e).__name__
            self._log(f"==== {_iso(self._now())} error {self._error}")
        finally:
            self._finished_at = self._now()

    def _log(self, line: str) -> None:
        try:
            path = self._paths.root.joinpath(*LOG)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass   # the log is a help, not a requirement
