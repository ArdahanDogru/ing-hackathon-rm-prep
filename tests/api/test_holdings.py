"""Plan 2026-10-14-portfolio-projection Task 4: POST /api/runs/{id}/holdings and the
RunView keys holdings / effective_weights (FakeBackend, no data/)."""

SHARES = {"nakit_benzeri": 80, "borclanma": 10, "hisse": 5, "altin_doviz": 5, "dengeli": 0}


def _run(client, persona):
    return client.post("/api/runs", json={"persona": persona}).json()


def test_holdings_post_makes_a_new_run(client, persona):
    v0 = _run(client, persona)
    r = client.post(f"/api/runs/{v0['result']['run_id']}/holdings",
                    json={"shares": SHARES, "origin": "rm_confirmed"})
    assert r.status_code == 200
    v = r.json()
    assert v["result"]["run_id"] != v0["result"]["run_id"]
    assert v["result"]["holdings_input"] == {"shares": {k: float(x) for k, x in SHARES.items()},
                                             "origin": "rm_confirmed"}
    back = client.post(f"/api/runs/{v['result']['run_id']}/holdings", json={"shares": None})
    assert back.status_code == 200 and back.json()["result"]["run_id"] == v0["result"]["run_id"]


def test_holdings_422(client, persona):
    rid = _run(client, persona)["result"]["run_id"]
    r = client.post(f"/api/runs/{rid}/holdings", json={"shares": {"hisse": 50}, "origin": "rm"})
    assert r.status_code == 422 and "classes" in r.json()["detail"]
    r = client.post(f"/api/runs/{rid}/holdings",
                    json={"shares": SHARES | {"dengeli": 2}, "origin": "rm"})
    assert r.status_code == 422 and "total" in r.json()["detail"]
    r = client.post(f"/api/runs/{rid}/holdings", json={"shares": SHARES, "origin": "profile"})
    assert r.status_code == 422 and "origin" in r.json()["detail"]


def test_holdings_unknown_run_404(client):
    r = client.post("/api/runs/Rnope000000/holdings", json={"shares": None})
    assert r.status_code == 404


def test_runview_has_holdings_and_effective_weights(backend, persona):
    from fastapi.testclient import TestClient

    from rmprep.api.app import create_app
    from rmprep.api.views import ViewBuilder
    from rmprep.decision.config import load_config
    c = TestClient(create_app(backend, views=ViewBuilder(backend, load_config())))
    v = c.post("/api/runs", json={"persona": persona}).json()
    assert "holdings" in v and "effective_weights" in v
    assert v["effective_weights"] == v["result"]["effective_weights"]
