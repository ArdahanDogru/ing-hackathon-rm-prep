"""Plan 2026-10-15-agent-decision Task 5: GET /api/runs/{id}/agent and the start of
the agent for a ready run (a fake AgentService; no network, no model)."""
from datetime import datetime

from fastapi.testclient import TestClient

from rmprep.api.app import create_app
from rmprep.contracts import (TR_TZ, AgentDecision, AgentNode, AgentPick, AgentReason,
                              DecisionState)

T = datetime(2026, 10, 15, 10, 0, tzinfo=TR_TZ)


class FakeAgent:
    """The interface of rmprep.agent.service.AgentService that the API uses."""

    def __init__(self, enabled=True):
        self.enabled = enabled
        self.started: list[str] = []
        self.done: dict[str, AgentDecision] = {}

    def start(self, result, evidence, lang="TR"):
        self.started.append(result.run_id)

    def status(self, run_id):
        if run_id in self.done:
            return self.done[run_id]
        if run_id in self.started:
            return AgentDecision(run_id, "running", (), (), "", (), (AgentNode("adaylar", "Adaylar", "running", T),),
                                 "claude-sonnet-5-5", "a1", 0.0, T)
        return None


def _decision(result):
    ids = [o.option.option_id for o in result.options if o.option.kind != "deposit"][:3]
    picks = tuple(AgentPick(i, (AgentReason("Neden.", ("puan:return",)),)) for i in ids)
    return AgentDecision(result.run_id, "done", picks, (), "Özet.", tuple(result.recommended),
                         (AgentNode("karar", "Karar", "done", T, T),), "claude-sonnet-5-5", "a1", 0.03, T)


def _client(backend, agent):
    return TestClient(create_app(backend, agent=agent))


def _ready(c, backend):
    for p in c.get("/api/personas").json():
        v = c.post("/api/runs", json={"persona": p}).json()
        if v["result"]["state"] == "ready":
            return v
    raise AssertionError("no ready run in the fixtures")


def test_a_ready_run_starts_the_agent_and_the_status_is_running_then_done(backend):
    agent = FakeAgent()
    c = _client(backend, agent)
    v = _ready(c, backend)
    rid = v["result"]["run_id"]
    assert rid in agent.started
    r = c.get(f"/api/runs/{rid}/agent")
    assert r.status_code == 202 and r.json()["state"] == "running" and r.json()["nodes"]
    from rmprep.contracts import DecisionResult
    agent.done[rid] = _decision(DecisionResult.from_dict(v["result"]))
    r = c.get(f"/api/runs/{rid}/agent")
    assert r.status_code == 200 and r.json()["state"] == "done" and len(r.json()["picks"]) == 3


def test_agent_status_unknown_and_not_ready(backend):
    agent = FakeAgent()
    c = _client(backend, agent)
    assert c.get("/api/runs/Rnope000000/agent").status_code == 404
    for p in c.get("/api/personas").json():
        v = c.post("/api/runs", json={"persona": p}).json()
        if v["result"]["state"] == DecisionState.NEEDS_RM_INPUT.value:
            rid = v["result"]["run_id"]
            assert rid not in agent.started
            r = c.get(f"/api/runs/{rid}/agent")
            assert r.status_code == 200 and r.json()["state"] == "off" and r.json()["fallback_reason"]
            return
    raise AssertionError("no needs_rm_input run in the fixtures")


def test_no_agent_configured_is_off(backend):
    c = TestClient(create_app(backend))
    v = _ready(c, backend)
    r = c.get(f"/api/runs/{v['result']['run_id']}/agent")
    assert r.status_code == 200 and r.json()["state"] == "off"


def test_a_disabled_agent_is_off_with_its_reason(backend):
    agent = FakeAgent(enabled=False)
    agent.off_reason = "no ANTHROPIC_API_KEY"
    c = _client(backend, agent)
    v = _ready(c, backend)
    r = c.get(f"/api/runs/{v['result']['run_id']}/agent")
    assert r.status_code == 200 and r.json()["state"] == "off" and "ANTHROPIC" in r.json()["fallback_reason"]
    assert agent.started == []
