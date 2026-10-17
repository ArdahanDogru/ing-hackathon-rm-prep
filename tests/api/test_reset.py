"""W27: "Sıfırla" puts every client back to the first state. The RM records move to
data/reset-archive/<time>/; the data, the LLM caches and the RM action log stay."""

import json
import threading
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rmprep.agent.service import AgentService
from rmprep.api.action_log import ActionLog
from rmprep.api.app import create_app
from rmprep.api.reset import ResetBusy, make_reset, move_files
from rmprep.backend import RealBackend
from rmprep.contracts import TR_TZ
from rmprep.research.service import ResearchService

NOW = datetime(2026, 10, 17, 10, 30, 5, tzinfo=TR_TZ)


def touch(path: Path, text: str = "{}") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


def test_move_files(tmp_path):
    touch(tmp_path / "a" / "x.json")
    touch(tmp_path / "a" / "y.txt")
    (tmp_path / "a" / "sub").mkdir()
    assert move_files(tmp_path / "a", tmp_path / "b", lambda p: p.suffix == ".json") == 1
    assert names(tmp_path / "a") == ["sub", "y.txt"] and names(tmp_path / "b") == ["x.json"]
    assert move_files(tmp_path / "missing", tmp_path / "c", lambda p: True) == 0
    assert not (tmp_path / "c").exists()          # nothing moved: no empty folder


def test_backend_reset_moves_the_rm_records_and_keeps_the_caches(tmp_path):
    root = tmp_path / "proto"
    data = root / "data"
    touch(data / "runs" / "R1.json")
    for n in ("R1-TR-approved.json", "R1-TR-edits.json", "R1-TR-brief-b1-m.json", "R1-TR-n9-m.json"):
        touch(data / "narratives" / n)
    touch(data / "cards" / "R1.md", "card")
    (root / "config").mkdir(parents=True)
    import shutil
    shutil.copy(Path(__file__).resolve().parents[2] / "config" / "decision.yaml",
                root / "config" / "decision.yaml")
    b = RealBackend(root, personas_dir=tmp_path)
    b._runs["R1"] = ("result", "inputs")
    b._narratives[("R1", "TR")] = "text"
    b._edits[("R1", "TR")] = ({}, {})
    archive = data / "reset-archive" / "X"
    assert b.reset_state(archive) == {"runs": 1, "texts": 2, "cards": 1, "personas": 0}
    assert names(data / "runs") == [] and names(data / "cards") == []
    assert names(data / "narratives") == ["R1-TR-brief-b1-m.json", "R1-TR-n9-m.json"]
    assert names(archive / "narratives") == ["R1-TR-approved.json", "R1-TR-edits.json"]
    assert names(archive / "runs") == ["R1.json"] and names(archive / "cards") == ["R1.md"]
    assert b._runs == {} and b._narratives == {} and b._edits == {}


def _agent(cache: Path) -> AgentService:
    a = object.__new__(AgentService)          # only the state the reset uses
    a.cache_root, a._lock, a._live, a._jobs = cache, threading.Lock(), {"R1": "decision"}, {}
    return a


def test_agent_reset_keeps_the_content_cache(tmp_path):
    cache = tmp_path / "agent"
    for n in ("R1.json", "R2.json", "R1.n10.144f7d95332e.json", "R2.n5.nomarks.json"):
        touch(cache / n)
    a = _agent(cache)
    done = Future()
    done.set_result(None)
    a._jobs = {"R1": done}
    assert not a.running()
    assert a.reset_state(tmp_path / "arch") == 2
    assert names(cache) == ["R1.n10.144f7d95332e.json", "R2.n5.nomarks.json"]
    assert names(tmp_path / "arch") == ["R1.json", "R2.json"]
    assert a._live == {} and a._jobs == {}
    a._jobs = {"R3": Future()}                 # not done: running
    assert a.running()


def test_research_reset_moves_the_marks_only(tmp_path):
    root = tmp_path / "research"
    touch(root / "marks" / "20261016.json")
    touch(root / "products" / "fund_AIS-TR-20261016-v2.json")
    r = object.__new__(ResearchService)
    r._root, r._marks_lock = root, threading.Lock()
    assert r.archive_marks(tmp_path / "arch") == 1
    assert names(root / "marks") == [] and names(root / "products") == ["fund_AIS-TR-20261016-v2.json"]


class _Part:
    def __init__(self, busy=False):
        self.busy, self.calls = busy, []

    def running(self):
        return self.busy

    def reset_state(self, archive):
        self.calls.append(archive)
        return 3

    def archive_marks(self, archive):
        self.calls.append(archive)
        return 4


def test_make_reset_archive_name_and_counts(tmp_path):
    class Backend:
        def reset_state(self, archive):
            self.archive = archive
            return {"runs": 2, "texts": 1, "cards": 0}

    backend, agent, research = Backend(), _Part(), _Part()
    out = make_reset(tmp_path, backend, agent, research, now=lambda: NOW)()
    assert out == {"archive": "data/reset-archive/20261017-103005",
                   "moved": {"runs": 2, "texts": 1, "cards": 0, "agent": 3, "research_marks": 4}}
    assert backend.archive == tmp_path / "data" / "reset-archive" / "20261017-103005"
    assert agent.calls == [backend.archive / "agent"]
    assert research.calls == [backend.archive / "research-marks"]


def test_make_reset_refuses_while_the_agent_runs(tmp_path):
    class Backend:
        def reset_state(self, archive):
            raise AssertionError("not called")

    with pytest.raises(ResetBusy, match="Ajan çalışıyor"):
        make_reset(tmp_path, Backend(), _Part(busy=True), None, now=lambda: NOW)()


def test_make_reset_skips_parts_without_the_method(tmp_path):
    out = make_reset(tmp_path, object(), None, object(), now=lambda: NOW)()
    assert out["moved"] == {}


def test_route_resets_the_api_memory_and_logs(backend, persona, tmp_path):
    calls = []
    log = ActionLog(tmp_path / "log", now=lambda: NOW)

    def reset():
        calls.append(1)
        return {"archive": "data/reset-archive/20261017-103005", "moved": {"runs": 1}}

    c = TestClient(create_app(backend, reset=reset, action_log=log))
    rid = c.post("/api/runs", json={"persona": persona}).json()["result"]["run_id"]
    assert c.get(f"/api/runs/{rid}").status_code == 200
    got = c.post("/api/reset")
    assert got.status_code == 200 and got.json()["moved"] == {"runs": 1} and calls == [1]
    assert c.get(f"/api/runs/{rid}").status_code == 404     # the API memory is cleared
    rows = [json.loads(x) for x in (tmp_path / "log" / "2026-10-17.jsonl").read_text(
        encoding="utf-8").splitlines()]
    assert rows[-1]["action"] == "reset" and rows[-1]["details"]["moved"] == {"runs": 1}
    assert c.post("/api/runs", json={"persona": persona}).status_code == 200   # opens again


def test_route_409_while_busy_and_404_without_reset(backend, persona):
    def busy():
        raise ResetBusy("Ajan çalışıyor; bitince sıfırlayın.")

    c = TestClient(create_app(backend, reset=busy))
    rid = c.post("/api/runs", json={"persona": persona}).json()["result"]["run_id"]
    r = c.post("/api/reset")
    assert r.status_code == 409 and r.json()["detail"] == "Ajan çalışıyor; bitince sıfırlayın."
    assert c.get(f"/api/runs/{rid}").status_code == 200      # nothing was cleared
    assert TestClient(create_app(backend)).post("/api/reset").status_code == 404
