"""W26: GET /api/runs/{run_id}/options/{option_id}/documents (links to the
official fund documents on the manager's own site; I16). A fake find_documents."""

from dataclasses import dataclass
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from rmprep.api.app import create_app
from rmprep.api.names import short_name
from rmprep.contracts import TR_TZ

KEYS = {"status", "manager_label", "verdict", "docs", "page_url", "checked_at", "reason"}


@dataclass(frozen=True)
class Doc:
    kind: str
    url: str
    label: str
    date: date | None


@dataclass(frozen=True)
class Docs:                     # the shape of rmprep.ingest.fund_docs.FundDocs
    code: str
    manager: str
    manager_label: str
    verdict: str
    status: str
    docs: tuple
    page_url: str
    page_sha256: str
    checked_at: datetime
    reason: str


def _client(backend, fn):
    return TestClient(create_app(backend, fund_docs=fn))


def _run_and_fund(client, persona):
    view = client.post("/api/runs", json={"persona": persona}).json()
    rid = view["result"]["run_id"]
    opts = [o["option"] for o in view["result"]["options"]]
    fund = next(o for o in opts if o["kind"] == "fund")
    dep = next(o for o in opts if o["kind"] == "deposit")
    return rid, fund, dep


def test_ok_answer_shape_and_the_code_and_issuer_passed(backend, persona):
    calls = []

    def fake(code, issuer):
        calls.append((code, issuer))
        return Docs(code, "nurol", "Nurol Portföy", "ok", "ok",
                    (Doc("izahname", "https://cdn.example.test/i.pdf", "İzahname", date(2025, 2, 4)),
                     Doc("ybf", "https://cdn.example.test/y.pdf", "YBF", None)),
                    "https://example.test/fon", "abc", datetime(2026, 10, 16, 14, 0, tzinfo=TR_TZ), "")

    c = _client(backend, fake)
    rid, fund, _ = _run_and_fund(c, persona)
    got = c.get(f"/api/runs/{rid}/options/{fund['option_id']}/documents").json()
    assert set(got) == KEYS and got["status"] == "ok" and got["verdict"] == "ok"
    assert got["docs"][0] == {"kind": "izahname", "url": "https://cdn.example.test/i.pdf",
                              "label": "İzahname", "date": "2025-02-04"}
    assert got["docs"][1]["date"] is None
    assert got["checked_at"].startswith("2026-10-16T14:00")
    assert calls == [(fund["option_id"].split(":", 1)[1], short_name(fund["label"])[0])]


def test_other_kinds_422_unknown_option_404(backend, persona):
    c = _client(backend, lambda code, issuer: pytest.fail("not called"))
    rid, _, dep = _run_and_fund(c, persona)
    assert c.get(f"/api/runs/{rid}/options/{dep['option_id']}/documents").status_code == 422
    assert c.get(f"/api/runs/{rid}/options/fund:NOPE/documents").status_code == 404
    assert c.get("/api/runs/Rnope/options/fund:X/documents").status_code == 404


def test_not_configured_is_not_covered(backend, persona):
    c = TestClient(create_app(backend))
    rid, fund, _ = _run_and_fund(c, persona)
    got = c.get(f"/api/runs/{rid}/options/{fund['option_id']}/documents").json()
    assert got["status"] == "not_covered" and got["docs"] == [] and "config/fund_docs.yaml" in got["reason"]


def test_an_error_is_failed_not_500(backend, persona):
    def boom(code, issuer):
        raise RuntimeError("site down")

    c = _client(backend, boom)
    rid, fund, _ = _run_and_fund(c, persona)
    r = c.get(f"/api/runs/{rid}/options/{fund['option_id']}/documents")
    assert r.status_code == 200 and r.json()["status"] == "failed" and "site down" in r.json()["reason"]
