"""Speed fixes of 2026-10-17 (found and fixed: the first page took ~33 s)."""

import shutil
import threading
import time
from pathlib import Path

from rmprep import backend as backend_mod
from rmprep.backend import RealBackend

PROTO = Path(__file__).resolve().parents[2]


def _backend(tmp_path) -> RealBackend:
    root = tmp_path / "proto"
    (root / "config").mkdir(parents=True)
    shutil.copy(PROTO / "config" / "decision.yaml", root / "config" / "decision.yaml")
    return RealBackend(root, personas_dir=tmp_path)


def test_one_evidence_build_for_parallel_requests(tmp_path, monkeypatch):
    """The background warm-up and a first request at the same time: one build, both get it."""
    calls = []

    def slow_build(root, snapshot_id, exclude):
        calls.append(snapshot_id)
        time.sleep(0.2)
        return object()

    monkeypatch.setattr(backend_mod, "build_evidence", slow_build)
    b = _backend(tmp_path)
    got = []
    threads = [threading.Thread(target=lambda: got.append(b.evidence("S1"))) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert calls == ["S1"] and len(got) == 3 and len({id(x) for x in got}) == 1
    b.evidence("S1", frozenset({"tefas"}))          # another key: its own build
    assert calls == ["S1", "S1"]


def test_warm_builds_the_newest_snapshot(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(backend_mod, "build_evidence", lambda root, sid, ex: calls.append(sid) or object())
    b = _backend(tmp_path)
    monkeypatch.setattr(b, "list_snapshots", lambda: ["S2", "S1"])
    b.warm()
    assert calls == ["S2"]
    monkeypatch.setattr(b, "list_snapshots", lambda: [])
    b.warm()                                        # no snapshot: nothing to do
    assert calls == ["S2"]


def test_the_sdk_clients_load_the_sdk_on_first_use():
    """The agent and the research fallback no longer import the SDK when they are made."""
    from rmprep.agent.client import AnthropicAgentClient
    from rmprep.agent.config import load_agent_config
    c = AnthropicAgentClient(load_agent_config(PROTO / "config" / "agent.yaml"), api_key="k")
    assert c._sdk_obj is None
    fake = object()
    c2 = AnthropicAgentClient(load_agent_config(PROTO / "config" / "agent.yaml"), sdk=fake)
    assert c2._sdk is fake
