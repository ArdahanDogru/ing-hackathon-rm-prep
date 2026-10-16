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

    def start(self, result, evidence, lang="TR", n=None):
        if n is not None and not 3 <= n <= 20:
            raise ValueError(f"n must be 3-20, got {n}")
        if result.run_id in self.started and result.run_id not in self.done:
            return                                  # one job per run while it runs
        self.started.append(result.run_id)
        self.n = n

    def status(self, run_id):
        if run_id in self.done:
            return self.done[run_id]
        if run_id in self.started:
            return AgentDecision(run_id, "running", (), (), "", (), (AgentNode("adaylar", "Adaylar", "running", T),),
                                 "claude-sonnet-5-5", "a1", 0.0, T,
                                 n_candidates=getattr(self, "n", None) or 0)   # as the service: N while running
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


def test_a_ready_run_does_not_start_the_agent(backend):
    """v1.12 (the user, 2026-10-15): the agent runs only when the RM starts it."""
    agent = FakeAgent()
    c = _client(backend, agent)
    rid = _ready(c, backend)["result"]["run_id"]
    assert agent.started == []
    r = c.get(f"/api/runs/{rid}/agent")
    assert r.status_code == 200 and r.json()["state"] == "off"
    assert r.json()["fallback_reason"] == "henüz çalıştırılmadı"
    assert agent.started == []                      # a GET never starts it


def test_post_starts_the_agent_with_n(backend):
    agent = FakeAgent()
    c = _client(backend, agent)
    rid = _ready(c, backend)["result"]["run_id"]
    r = c.post(f"/api/runs/{rid}/agent", json={"n": 12})
    assert r.status_code == 202 and r.json()["state"] == "running" and agent.n == 12
    r = c.post(f"/api/runs/{rid}/agent", json={})
    assert r.status_code == 202 and agent.started == [rid]   # double start = one job


def test_agent_start_rejects_bad_n(backend):
    agent = FakeAgent()
    c = _client(backend, agent)
    rid = _ready(c, backend)["result"]["run_id"]
    for bad in (2, 21, "abc"):
        assert c.post(f"/api/runs/{rid}/agent", json={"n": bad}).status_code == 422
    assert agent.started == []


def test_a_ready_run_starts_the_agent_and_the_status_is_running_then_done(backend):
    agent = FakeAgent()
    c = _client(backend, agent)
    v = _ready(c, backend)
    rid = v["result"]["run_id"]
    c.post(f"/api/runs/{rid}/agent", json={})
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
    assert c.post("/api/runs/Rnope000000/agent", json={}).status_code == 404
    for p in c.get("/api/personas").json():
        v = c.post("/api/runs", json={"persona": p}).json()
        if v["result"]["state"] == DecisionState.NEEDS_RM_INPUT.value:
            rid = v["result"]["run_id"]
            r = c.get(f"/api/runs/{rid}/agent")
            assert r.status_code == 200 and r.json()["state"] == "off" and r.json()["fallback_reason"]
            assert c.post(f"/api/runs/{rid}/agent", json={}).status_code == 422
            assert rid not in agent.started
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


def test_the_brief_follows_the_agent_top3_when_it_changed(backend):
    """W20c: GET /brief passes the agent's picks to the backend when they differ."""
    calls = []
    orig = backend.brief

    def brief(run_id, lang="TR", top3=None):
        calls.append(top3)
        return orig(run_id, lang)

    backend.brief = brief
    agent = FakeAgent()
    c = _client(backend, agent)
    v = _ready(c, backend)
    rid = v["result"]["run_id"]
    from rmprep.contracts import DecisionResult
    r = DecisionResult.from_dict(v["result"])
    c.post(f"/api/runs/{rid}/agent", json={})
    c.get(f"/api/runs/{rid}/brief")
    assert calls[-1] is None                                          # agent still running
    ids = [o.option.option_id for o in r.options if o.option.kind != "deposit"]
    picks = tuple(AgentPick(i, (AgentReason("Neden.", ("puan:return",)),)) for i in (ids[3], ids[0], ids[1]))
    agent.done[rid] = AgentDecision(rid, "done", picks, (), "Özet.", tuple(r.recommended), (),
                                    "claude-sonnet-5-5", "a2", 0.03, T)
    c.get(f"/api/runs/{rid}/brief")
    assert calls[-1] == (ids[3], ids[0], ids[1])
    if len(r.recommended) == 3:                    # the fixture run may have a shorter top 3
        same = tuple(AgentPick(i, (AgentReason("Neden.", ("puan:return",)),)) for i in r.recommended)
        agent.done[rid] = AgentDecision(rid, "done", same, (), "Özet.", tuple(r.recommended), (),
                                        "claude-sonnet-5-5", "a2", 0.03, T)
        c.get(f"/api/runs/{rid}/brief")
        assert calls[-1] is None                                      # same picks: the engine's brief


class ResearchAll:
    """Research status with every scored product (as R4 gives: today's research of any run)."""
    enabled = True

    def __init__(self, ids):
        self.ids = ids

    def start(self, result, lang="TR"):
        pass

    def status(self, result, lang):
        return {"state": "ready", "questions": [],
                "products": [{"option_id": i, "findings": [], "news": []} for i in self.ids]}


def test_research_panel_shows_the_top3_then_the_agent_candidates(backend):
    """v1.12 live check 2026-10-15: the panel listed 25 products (today's research of other
    runs). Before an agent run: the engine's top 3; after: the run's N candidates."""
    from rmprep.agent.pack import candidates
    from rmprep.contracts import DecisionResult
    agent = FakeAgent()
    probe = TestClient(create_app(backend))
    v = _ready(probe, backend)
    r = DecisionResult.from_dict(v["result"])
    ids = [o.option.option_id for o in r.options if o.option.kind != "deposit"]
    c = TestClient(create_app(backend, agent=agent, research=ResearchAll(ids)))
    rid = c.post("/api/runs", json={"persona": v["result"]["persona"]}).json()["result"]["run_id"]
    shown = [p["option_id"] for p in c.get(f"/api/runs/{rid}/research").json()["products"]]
    assert shown == [i for i in ids if i in r.recommended] or set(shown) == set(r.recommended)
    picks = tuple(AgentPick(i, (AgentReason("Neden.", ("puan:return",)),)) for i in ids[:3])
    agent.done[rid] = AgentDecision(rid, "done", picks, (), "", tuple(r.recommended), (),
                                    "claude-sonnet-5-5", "a3", 0.0, T, n_candidates=4)
    shown = [p["option_id"] for p in c.get(f"/api/runs/{rid}/research").json()["products"]]
    assert set(shown) == {s.option.option_id for s in candidates(r, 4)}
