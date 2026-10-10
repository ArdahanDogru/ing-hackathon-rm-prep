"""`python -m rmprep decide` on the fixture evidence (no snapshot, no network)."""

import json
from pathlib import Path

import pytest

from rmprep import cli
from rmprep.contracts import EvidenceSet

FIX = Path(__file__).resolve().parents[1] / "contracts" / "fixtures"


@pytest.fixture
def evidence(monkeypatch):
    ev = EvidenceSet.from_dict(json.loads((FIX / "evidence_medium.json").read_text(encoding="utf-8")))
    calls = []

    def fake_build(root, snapshot_id, exclude=frozenset()):
        calls.append((snapshot_id, frozenset(exclude)))
        return ev

    class Snap:
        snapshot_id = ev.snapshot_id

    monkeypatch.setattr(cli, "build_evidence", fake_build)
    monkeypatch.setattr(cli, "list_snapshots", lambda root: [Snap()])
    return calls


def run(capsys, *args):
    code = cli.main(["--root", str(Path(__file__).resolve().parents[2]), "decide",
                     "--personas", str(FIX / "personas"), *args])
    out = capsys.readouterr()
    return code, out.out, out.err


def test_decide_prints_report_for_latest_snapshot(evidence, capsys):
    code, out, err = run(capsys, "--persona", "p02")
    assert code == 0, err
    assert "persona P02" in out
    assert evidence[0][1] == frozenset()


def test_decide_passes_snapshot_and_exclusions(evidence, capsys):
    code, out, err = run(capsys, "--persona", "P03", "--snapshot", "S1", "--exclude", "manual")
    assert code == 0, err
    assert evidence == [("S1", frozenset({"manual"}))]


def test_unknown_persona_is_an_error(evidence, capsys):
    code, out, err = run(capsys, "--persona", "P99")
    assert code == 2
    assert "P99" in err


def test_bad_answer_is_an_error(evidence, capsys):
    code, out, err = run(capsys, "--persona", "P01", "--answer", "no-such-question=x")
    assert code == 2
    assert "error" in err


def test_answer_needs_equals_sign(evidence, capsys):
    code, out, err = run(capsys, "--persona", "P01", "--answer", "novalue")
    assert code == 2
