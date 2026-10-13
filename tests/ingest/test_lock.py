"""I6: one ingest at a time (lock file data/.ingest.lock)."""

import json
import logging
import os
from datetime import timedelta, timezone

import pytest

from tests.ingest.conftest import T0, FakeEvds
from tests.ingest.test_pipeline import make_project, run
from rmprep.ingest.pipeline import IngestBusy, ingest_status
from rmprep.ingest.snapshot import list_snapshots


@pytest.fixture
def paths(tmp_path, config_raw):
    return make_project(tmp_path / "proj", config_raw)


def write_lock(paths, started_at, pid=4242):
    paths.lock.parent.mkdir(parents=True, exist_ok=True)
    paths.lock.write_text(json.dumps({"pid": pid, "started_at": started_at.isoformat()}),
                          encoding="utf-8")


class LockSpy(FakeEvds):
    """Reads the lock file at the first request, i.e. while the ingest runs."""

    def __init__(self, paths):
        super().__init__()
        self.paths, self.seen = paths, None

    def __call__(self, request):
        if self.seen is None:
            self.seen = self.paths.lock.read_text(encoding="utf-8")
        return super().__call__(request)


def test_lock_file_is_in_data_folder(paths):
    assert paths.lock == paths.root / "data" / ".ingest.lock"


def test_lock_exists_during_ingest_with_pid_and_start_time(paths):
    spy = LockSpy(paths)
    run(paths, fake=spy)
    assert json.loads(spy.seen) == {"pid": os.getpid(), "started_at": "2026-10-09T15:00:00+03:00"}


def test_lock_removed_after_success(paths):
    run(paths)
    assert not paths.lock.exists()


def test_lock_removed_after_exception(paths):
    paths.config.write_text("version: 99\nquantities: {}\nsources: {}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        run(paths)
    assert not paths.lock.exists()


def test_second_ingest_while_locked_raises_busy(paths):
    write_lock(paths, T0 - timedelta(minutes=10))
    fake = FakeEvds()
    with pytest.raises(IngestBusy) as exc:
        run(paths, fake=fake)
    assert exc.value.started_at == "2026-10-09T14:50:00+03:00"
    assert "another ingest is running since 2026-10-09T14:50:00+03:00" in str(exc.value)
    assert fake.requests == []
    assert list_snapshots(paths.snapshots) == []
    assert paths.lock.exists()                     # the other ingest's lock stays


def test_stale_lock_is_replaced_and_logged(paths, caplog):
    write_lock(paths, T0 - timedelta(hours=2, minutes=1))
    with caplog.at_level(logging.WARNING, logger="rmprep.ingest.pipeline"):
        ev = run(paths)
    assert ev.snapshot_id
    assert not paths.lock.exists()
    assert "stale ingest lock" in caplog.text and "2026-10-09T12:59:00+03:00" in caplog.text


def test_lock_of_exactly_two_hours_is_not_stale(paths):
    write_lock(paths, T0 - timedelta(hours=2))
    with pytest.raises(IngestBusy):
        run(paths)


def test_unreadable_lock_uses_file_time(paths):
    paths.lock.parent.mkdir(parents=True, exist_ok=True)
    paths.lock.write_text("", encoding="utf-8")    # e.g. the other ingest has not written yet
    ts = (T0 - timedelta(minutes=1)).timestamp()
    os.utime(paths.lock, (ts, ts))
    with pytest.raises(IngestBusy) as exc:
        run(paths)
    assert exc.value.started_at == "2026-10-09T14:59:00+03:00"


def test_ingest_does_not_remove_a_lock_it_does_not_own(paths):
    class Replacer(FakeEvds):
        def __call__(self, request):
            write_lock(paths, T0, pid=999)       # another ingest took over the lock
            return super().__call__(request)

    run(paths, fake=Replacer())
    assert json.loads(paths.lock.read_text(encoding="utf-8"))["pid"] == 999


# --- ingest_status ----------------------------------------------------------------------

def test_status_without_lock(paths):
    assert ingest_status(paths) == {"running": False, "started_at": None}


def test_status_with_lock(paths):
    write_lock(paths, T0 - timedelta(minutes=5))
    assert ingest_status(paths, now=lambda: T0) == \
        {"running": True, "started_at": "2026-10-09T14:55:00+03:00"}


def test_status_with_stale_lock(paths):
    write_lock(paths, T0 - timedelta(hours=3))
    assert ingest_status(paths, now=lambda: T0) == {"running": False, "started_at": None}


def test_status_started_at_is_turkey_time(paths):
    write_lock(paths, (T0 - timedelta(minutes=5)).astimezone(timezone.utc))   # 11:55 UTC
    assert ingest_status(paths, now=lambda: T0)["started_at"] == "2026-10-09T14:55:00+03:00"
