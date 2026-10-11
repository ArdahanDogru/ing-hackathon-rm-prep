"""The API samples of the web app (tests/contracts/fixtures/api/) have the keys
of the live API output (docs/web-ui.md section 6). The samples come from real
data (python -m rmprep.api.samples); this test runs on the FakeBackend."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rmprep.api.app import create_app
from rmprep.api.views import ViewBuilder
from rmprep.decision import load_config

SAMPLES = Path(__file__).resolve().parents[1] / "contracts" / "fixtures" / "api"
NAMES = ("personas", "snapshots", "sources", "run_p01_ready", "run_p01_approved", "run_p02_ready",
         "run_needs_input", "run_test", "narrative_p01_tr", "narrative_p01_en", "glossary",
         "evidence_item")


def _sample(name):
    return json.loads((SAMPLES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def live(backend, persona):
    c = TestClient(create_app(backend, views=ViewBuilder(backend, load_config())))
    view = c.post("/api/runs", json={"persona": persona}).json()
    rid = view["result"]["run_id"]
    first = view["top"][0]
    c.post(f"/api/runs/{rid}/approval", json={"status": "approved", "note": "", "selected": [first]})
    return c, view, rid


def test_every_sample_exists():
    assert sorted(p.stem for p in SAMPLES.glob("*.json")) == sorted(NAMES)


@pytest.mark.parametrize("name", ["run_p01_ready", "run_p01_approved", "run_p02_ready", "run_test"])
def test_runview_samples_have_the_live_keys(live, name):
    _, view, _ = live
    sample = _sample(name)
    assert set(sample) == set(view)
    assert set(next(iter(sample["options"].values()))) == set(next(iter(view["options"].values())))
    assert set(sample["result"]) == set(view["result"])


def test_needs_input_sample():
    s = _sample("run_needs_input")
    assert s["result"]["state"] == "needs_rm_input" and s["top"] == [] and s["test_run"] is True


def test_narrative_samples_have_the_live_keys(live):
    c, _, rid = live
    d = c.get(f"/api/runs/{rid}/narrative").json()
    for name in ("narrative_p01_tr", "narrative_p01_en"):
        assert set(_sample(name)) == set(d)


def test_approved_sample_selects_the_top_options():
    s = _sample("run_p01_approved")
    assert s["result"]["rm_status"] == "approved" and s["result"]["rm_selected"] == s["top"]
    assert all(s["options"][i]["selected"] for i in s["top"])
