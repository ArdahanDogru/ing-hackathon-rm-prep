"""`python -m rmprep ingest [--summary]` output (the ingest itself is faked; no network)."""

import json
from pathlib import Path

from rmprep import cli
from rmprep.contracts import EvidenceSet

FIX = Path(__file__).resolve().parents[1] / "contracts" / "fixtures"


def _evidence() -> EvidenceSet:
    """The small fixture with an ingest-style source record (it has payloads)."""
    from types import SimpleNamespace
    ev = EvidenceSet.from_dict(json.loads((FIX / "evidence_small.json").read_text(encoding="utf-8")))
    rec = SimpleNamespace(status="ok", payloads=("p1",), error=None, excluded=False,
                          fallback_from=None, rejected_rows=[])
    return EvidenceSet(**{**ev.__dict__, "source_status": {"evds": rec}})


def test_format_evidence_without_rows_keeps_sources_and_flag_counts():
    ev = _evidence()
    full = cli.format_evidence(ev)
    short = cli.format_evidence(ev, rows=False)
    assert "datapoints (" in full
    assert "datapoints (" not in short
    assert ev.datapoints[0].id not in short
    assert "sources:" in short
    assert f"{len(ev.datapoints)} datapoints" in short
    assert short.splitlines()[-1] == full.splitlines()[-1]   # the flag counts


def test_ingest_summary_prints_no_rows(monkeypatch, capsys, tmp_path):
    ev = _evidence()
    monkeypatch.setattr(cli, "ingest", lambda paths: ev)
    assert cli.main(["--root", str(tmp_path), "ingest", "--summary"]) == 0
    out = capsys.readouterr().out
    assert "sources:" in out
    assert ev.datapoints[0].id not in out
    assert cli.main(["--root", str(tmp_path), "ingest"]) == 0
    assert ev.datapoints[0].id in capsys.readouterr().out
