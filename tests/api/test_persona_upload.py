"""W31: client upload. POST /api/personas stores a client JSON in data/personas/
(the original ../p0*.json files are never changed); GET /api/personas lists the
built-in clients, then the uploaded ones; the reset (W27) archives the uploads."""

import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rmprep.api.action_log import ActionLog
from rmprep.api.app import create_app
from rmprep.backend import RealBackend
from rmprep.contracts import TR_TZ

PROTO = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=TR_TZ)


@pytest.fixture
def setup(tmp_path):
    personas = tmp_path / "personas"
    personas.mkdir()
    for n in ("p01.json", "p02.json"):
        shutil.copy(PROTO.parent / n, personas / n)
    root = tmp_path / "proto"
    (root / "config").mkdir(parents=True)
    shutil.copy(PROTO / "config" / "decision.yaml", root / "config" / "decision.yaml")
    backend = RealBackend(root, personas_dir=personas)
    log = ActionLog(tmp_path / "log", now=lambda: NOW)
    return TestClient(create_app(backend, action_log=log)), backend, root, personas, tmp_path


def client_json(pid="P06", **change):
    d = json.loads((PROTO.parent / "p01.json").read_text(encoding="utf-8"))
    return {**d, "persona_id": pid, "profil": "Yüklenen müşteri", **change}


def test_upload_lists_and_logs(setup):
    c, backend, root, personas, tmp = setup
    before = sorted(p.name for p in personas.iterdir())
    r = c.post("/api/personas", json={"persona": client_json()})
    assert r.status_code == 200 and r.json() == {"persona": client_json(), "replaced": False}
    assert [p["persona_id"] for p in c.get("/api/personas").json()] == ["P01", "P02", "P06"]
    assert c.get("/api/personas/uploaded").json() == ["P06"]
    assert json.loads((root / "data" / "personas" / "P06.json").read_text(encoding="utf-8")) == client_json()
    assert sorted(p.name for p in personas.iterdir()) == before          # the originals stay
    rows = [json.loads(x) for x in (tmp / "log" / "2026-10-17.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["action"] == "persona_uploaded"
    assert rows[-1]["details"] == {"persona_id": "P06", "replaced": False}


def test_an_uploaded_client_is_not_a_test_run(setup):
    c, *_ = setup
    c.post("/api/personas", json={"persona": client_json()})
    p = next(x for x in c.get("/api/personas").json() if x["persona_id"] == "P06")
    assert p == client_json()            # the same dict the web posts back to /api/runs


def test_the_same_id_replaces_an_upload(setup):
    c, *_ = setup
    c.post("/api/personas", json={"persona": client_json()})
    r = c.post("/api/personas", json={"persona": client_json(yas=50)})
    assert r.json()["replaced"] is True
    assert next(x for x in c.get("/api/personas").json() if x["persona_id"] == "P06")["yas"] == 50


@pytest.mark.parametrize("persona,text", [
    (client_json("P01"), "yerleşik bir müşteriye ait"),
    (client_json("P 6"), "yalnızca harf, rakam"),
    (client_json("x" * 33), "yalnızca harf, rakam"),
    (client_json("../evil"), "yalnızca harf, rakam"),
    ({k: v for k, v in client_json().items() if k != "yas"}, "Geçersiz müşteri dosyası"),
    (client_json(extra="x"), "Geçersiz müşteri dosyası"),
    (client_json(yas="62"), "Geçersiz müşteri dosyası"),
    (client_json(rm_notu="x" * 70000), "en fazla 64 KB"),
])
def test_refusals(setup, persona, text):
    c, backend, root, *_ = setup
    r = c.post("/api/personas", json={"persona": persona})
    assert r.status_code == 422 and text in r.json()["detail"]
    assert not (root / "data" / "personas").exists() or not any((root / "data" / "personas").iterdir())


def test_a_broken_upload_file_is_skipped(setup):
    c, backend, root, *_ = setup
    (root / "data" / "personas").mkdir(parents=True)
    (root / "data" / "personas" / "bad.json").write_text("{", encoding="utf-8")
    assert [p["persona_id"] for p in c.get("/api/personas").json()] == ["P01", "P02"]


def test_the_reset_archives_the_uploads(setup):
    c, backend, root, *_ = setup
    c.post("/api/personas", json={"persona": client_json()})
    out = backend.reset_state(root / "data" / "reset-archive" / "X")
    assert out["personas"] == 1
    assert c.get("/api/personas/uploaded").json() == []
    assert (root / "data" / "reset-archive" / "X" / "personas" / "P06.json").is_file()


def test_no_upload_without_the_backend_support(backend, persona):
    c = TestClient(create_app(backend))           # the FakeBackend has no uploads
    assert c.post("/api/personas", json={"persona": persona}).status_code == 404
    assert c.get("/api/personas/uploaded").json() == []
