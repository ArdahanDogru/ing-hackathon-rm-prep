"""`python -m rmprep.api.samples`: real API responses for the web app
(docs/web-ui.md section 6; lead-owned).

Runs the API on RealBackend and the frozen eval snapshot (config/eval.yaml) and
writes one JSON file per response to tests/contracts/fixtures/api/. Needs
data/ (main checkout only). The P01 approval makes the meeting text (TR, EN):
two narrator calls, cached afterwards.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from rmprep.api.serve import build_app

UNKNOWN_CONSTRAINT = "bilinmeyen bir kısıt"     # makes a blocking question (needs_rm_input)


def _get(c: TestClient, method: str, url: str, **kw):
    r = c.request(method, url, **kw)
    if r.status_code != 200:
        raise SystemExit(f"{method} {url}: {r.status_code} {r.text[:300]}")
    return r.json()


def _forget_p01(root: Path, snapshot: str) -> None:
    """RealBackend restores saved runs after a restart; the samples need a fresh
    (pending) P01 run, so the saved P01 run and its approved texts are removed."""
    c = TestClient(build_app(root))
    p01 = next(p for p in _get(c, "GET", "/api/personas") if p["persona_id"] == "P01")
    rid = _get(c, "POST", "/api/runs", json={"persona": p01, "snapshot_id": snapshot})["result"]["run_id"]
    for path in [root / "data" / "runs" / f"{rid}.json", root / "data" / "cards" / f"{rid}.md",
                 *(root / "data" / "narratives").glob(f"{rid}-*-approved.json")]:
        path.unlink(missing_ok=True)


def write_samples(root: Path, out: Path, snapshot: str | None = None) -> list[Path]:
    snapshot = snapshot or yaml.safe_load((root / "config" / "eval.yaml").read_text(encoding="utf-8"))["snapshot"]
    _forget_p01(root, snapshot)
    c = TestClient(build_app(root))
    samples: dict[str, object] = {}

    personas = _get(c, "GET", "/api/personas")
    by_id = {p["persona_id"]: p for p in personas}
    samples["personas"] = personas
    samples["snapshots"] = _get(c, "GET", "/api/snapshots")
    samples["sources"] = _get(c, "GET", f"/api/snapshots/{snapshot}/sources")

    def run(persona: dict) -> dict:
        return _get(c, "POST", "/api/runs", json={"persona": persona, "snapshot_id": snapshot})

    p01 = run(by_id["P01"])
    samples["run_p01_ready"] = p01
    samples["run_p02_ready"] = run(by_id["P02"])
    samples["run_test"] = run(dict(by_id["P01"], yas=45))
    samples["run_needs_input"] = run(dict(by_id["P01"], acik_kisitlar=[UNKNOWN_CONSTRAINT]))

    rid = p01["result"]["run_id"]
    samples["run_p01_approved"] = _get(c, "POST", f"/api/runs/{rid}/approval", json={
        "status": "approved", "note": "Müşteri aylık nakit akışını sordu.", "selected": p01["top"]})
    samples["narrative_p01_tr"] = _get(c, "GET", f"/api/runs/{rid}/narrative", params={"lang": "TR"})
    samples["narrative_p01_en"] = _get(c, "GET", f"/api/runs/{rid}/narrative", params={"lang": "EN"})
    samples["glossary"] = _get(c, "GET", "/api/glossary", params={"lang": "TR", "run_id": rid})
    head = p01["options"][p01["top"][0]]
    samples["evidence_item"] = _get(c, "GET", f"/api/evidence/{snapshot}/{head['returns']['1y']['evidence_id']}")

    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, data in samples.items():
        path = out / f"{name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rmprep.api.samples")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path)
    parser.add_argument("--snapshot")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    out = args.out or root / "tests" / "contracts" / "fixtures" / "api"
    for path in write_samples(root, out, args.snapshot):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
