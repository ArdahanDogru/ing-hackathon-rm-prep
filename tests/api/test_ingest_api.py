"""GET / POST /api/ingest (docs/web-ui.md W14): data age, refresh in the background,
one ingest at a time (docs/ingest.md I6). The ingest itself is faked."""

import json
import os
import threading
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from rmprep.api.app import create_app
from rmprep.api.ingest_job import IngestControl
from rmprep.contracts import TR_TZ
from rmprep.ingest.pipeline import Paths

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=TR_TZ)


def make(backend, tmp_path, *, created=NOW - timedelta(hours=3), run=None):
    calls = []

    def fake_run(paths):
        calls.append(paths)

    latest = (lambda: ("S1", created)) if created else (lambda: None)
    ctl = IngestControl(Paths(tmp_path), run=run or fake_run, now=lambda: NOW, latest=latest)
    return TestClient(create_app(backend, ingest=ctl)), ctl, calls


def test_no_controller_no_endpoints(client):
    assert client.get("/api/ingest").status_code == 404
    assert client.post("/api/ingest").status_code == 404


def test_fresh_data(backend, tmp_path):
    c, _, _ = make(backend, tmp_path)
    s = c.get("/api/ingest").json()
    assert s == {"latest_snapshot": "S1", "created_at": "2026-10-14T06:00:00+03:00", "age_hours": 3.0,
                 "stale": False, "running": False, "started_at": None, "finished_at": None, "error": None}


def test_stale_after_24_hours(backend, tmp_path):
    c, _, _ = make(backend, tmp_path, created=NOW - timedelta(hours=24))
    s = c.get("/api/ingest").json()
    assert s["stale"] is True and s["age_hours"] == 24.0


def test_no_snapshot_is_stale(backend, tmp_path):
    c, _, _ = make(backend, tmp_path, created=None)
    s = c.get("/api/ingest").json()
    assert s["latest_snapshot"] is None and s["created_at"] is None and s["age_hours"] is None
    assert s["stale"] is True


def test_refresh_runs_once_in_the_background(backend, tmp_path):
    gate = threading.Event()
    calls = []

    def slow_run(paths):
        calls.append(paths)
        gate.wait(5)

    c, ctl, _ = make(backend, tmp_path, run=slow_run)
    r = c.post("/api/ingest")
    assert r.status_code == 202
    assert r.json()["running"] is True and r.json()["started_at"] == NOW.isoformat()
    assert c.post("/api/ingest").status_code == 409          # one at a time
    gate.set()
    ctl.wait(5)
    s = c.get("/api/ingest").json()
    assert s["running"] is False and s["finished_at"] == NOW.isoformat() and s["error"] is None
    assert len(calls) == 1 and calls[0] == Paths(tmp_path)


def test_a_failed_refresh_reports_the_error(backend, tmp_path):
    def broken(paths):
        raise RuntimeError("TEFAS down")

    c, ctl, _ = make(backend, tmp_path, run=broken)
    assert c.post("/api/ingest").status_code == 202
    ctl.wait(5)
    s = c.get("/api/ingest").json()
    assert s["running"] is False and s["error"] == "TEFAS down"


def test_an_ingest_of_another_process_blocks_the_refresh(backend, tmp_path):
    started = (datetime.now(TR_TZ) - timedelta(minutes=5)).replace(microsecond=0)   # the lock uses the real clock
    lock = Paths(tmp_path).lock
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": os.getpid(), "started_at": started.isoformat()}), encoding="utf-8")
    c, _, calls = make(backend, tmp_path)
    s = c.get("/api/ingest").json()
    assert s["running"] is True and s["started_at"] == started.isoformat()
    assert c.post("/api/ingest").status_code == 409
    assert calls == []
