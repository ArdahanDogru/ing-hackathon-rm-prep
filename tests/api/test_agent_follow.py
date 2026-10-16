"""Bug 2026-10-17 (the user): after the agent ran, a confirmed split (or an answer
to an RM question) made a new run without an agent result, so the agent panel and
the research of the N candidates seemed gone. The RM's rule (2026-10-15): a new
split recomputes the ranking "and of course the agent recommendation as well".
So the API starts the agent on the new run with the same N, once."""

import dataclasses
import json

from fastapi.testclient import TestClient

from rmprep.api.action_log import ActionLog
from rmprep.api.app import create_app
from tests.api.test_agent_api import T, FakeAgent, _decision, _ready

SHARES = {"nakit_benzeri": 50.0, "borclanma": 20.0, "hisse": 10.0, "altin_doviz": 10.0,
          "dengeli": 10.0}


def _client(backend, agent, tmp_path=None):
    log = ActionLog(tmp_path / "log", now=lambda: T) if tmp_path is not None else None
    return TestClient(create_app(backend, agent=agent, action_log=log))


def _done(agent, run_id, result_view, n=12):
    agent.started.append(run_id)
    agent.done[run_id] = dataclasses.replace(_decision(result_view), n_candidates=n)


def _split(c, rid, shares=SHARES):
    r = c.post(f"/api/runs/{rid}/holdings", json={"shares": shares, "origin": "rm"})
    assert r.status_code == 200, r.text
    return r.json()["result"]["run_id"]


def test_a_new_split_starts_the_agent_again_with_the_same_n(backend, tmp_path):
    agent = FakeAgent()
    c = _client(backend, agent, tmp_path)
    view = _ready(c, backend)
    rid = view["result"]["run_id"]
    _done(agent, rid, backend._runs[rid][0], n=12)
    new = _split(c, rid)
    assert new != rid
    assert agent.started[-1] == new and agent.n == 12
    assert c.get(f"/api/runs/{new}/agent").json()["state"] == "running"
    rows = [json.loads(x) for x in (tmp_path / "log" / "2026-10-15.jsonl").read_text(
        encoding="utf-8").splitlines()]
    auto = [r for r in rows if r["action"] == "agent_started"]
    assert len(auto) == 1 and auto[0]["run_id"] == new
    assert auto[0]["details"] == {"n": 12, "auto": True, "from_run": rid}


def test_no_agent_before_no_start_after(backend):
    agent = FakeAgent()
    c = _client(backend, agent)
    rid = _ready(c, backend)["result"]["run_id"]
    _split(c, rid)
    assert agent.started == []                       # v1.12: only on the RM's request


def test_a_run_with_its_own_decision_is_not_started_again(backend):
    """Back to a split that already has a result (or the reset of the split): the
    stored result is shown, no new job."""
    agent = FakeAgent()
    c = _client(backend, agent)
    rid = _ready(c, backend)["result"]["run_id"]
    _done(agent, rid, backend._runs[rid][0])
    new = _split(c, rid)
    _done(agent, new, backend._runs[new][0])
    started = list(agent.started)
    back = c.post(f"/api/runs/{new}/holdings", json={"shares": None, "origin": "rm"}).json()
    assert back["result"]["run_id"] == rid and agent.started == started


def test_a_running_agent_is_followed_too(backend):
    """The RM confirms the split while the agent still runs: the new run gets its own job."""
    agent = FakeAgent()
    c = _client(backend, agent)
    rid = _ready(c, backend)["result"]["run_id"]
    c.post(f"/api/runs/{rid}/agent", json={"n": 7})
    new = _split(c, rid)
    assert agent.started == [rid, new] and agent.n == 7


def test_the_agent_off_starts_nothing(backend):
    agent = FakeAgent(enabled=False)
    c = _client(backend, agent)
    rid = _ready(c, backend)["result"]["run_id"]
    agent.done[rid] = dataclasses.replace(_decision(backend._runs[rid][0]), n_candidates=10)
    _split(c, rid)
    assert agent.started == []


def test_an_answer_to_an_rm_question_follows_the_agent_too(backend, persona):
    """P02 is ready with an open non-blocking question; the answer makes a new run."""
    agent = FakeAgent()
    c = _client(backend, agent)
    view = c.post("/api/runs", json={"persona": persona}).json()
    rid = view["result"]["run_id"]
    q = next(q for q in view["result"]["questions"] if not q["blocking"] and q["answer"] is None)
    _done(agent, rid, backend._runs[rid][0], n=10)
    new = c.post(f"/api/runs/{rid}/answers",
                 json={"question_id": q["question_id"], "answer": q["choices"][0]}).json()
    assert new["result"]["run_id"] != rid and agent.started[-1] == new["result"]["run_id"]
    assert agent.n == 10
