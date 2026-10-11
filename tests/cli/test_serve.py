"""`python -m rmprep serve` and the static files of the web app (docs/web-ui.md section 1)."""

from pathlib import Path

from fastapi.testclient import TestClient

from rmprep import cli
from rmprep.api.app import create_app
from rmprep.ui.fake import FakeBackend

FIX = Path(__file__).resolve().parents[1] / "contracts" / "fixtures"


def _dist(tmp_path):
    (tmp_path / "index.html").write_text("<div id=root></div>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "a.js").write_text("x", encoding="utf-8")
    return tmp_path


def test_static_files_and_client_routes(tmp_path):
    c = TestClient(create_app(FakeBackend(FIX), static_dir=_dist(tmp_path)))
    assert c.get("/assets/a.js").text == "x"
    assert "root" in c.get("/").text
    assert "root" in c.get("/print/R123").text            # client-side route -> index.html
    assert c.get("/api/personas").status_code == 200
    assert c.get("/api/nope").status_code == 404          # an API path never gets index.html


def test_no_static_dir_only_api(tmp_path):
    c = TestClient(create_app(FakeBackend(FIX)))
    assert c.get("/").status_code == 404
    assert c.get("/api/personas").status_code == 200


def test_serve_args(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr("rmprep.api.serve.serve",
                        lambda root, port, personas_dir=None: seen.update(root=root, port=port))
    assert cli.main(["--root", str(tmp_path), "serve", "--port", "8601"]) == 0
    assert seen == {"root": tmp_path.resolve(), "port": 8601}
    assert cli.main(["--root", str(tmp_path), "serve"]) == 0
    assert seen["port"] == 8600
