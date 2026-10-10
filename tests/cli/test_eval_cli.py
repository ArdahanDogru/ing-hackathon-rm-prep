"""`python -m rmprep eval` passes its options to run_suite (no real run, no network)."""

from pathlib import Path
from types import SimpleNamespace

from rmprep import cli


def test_eval_passes_options_and_prints_the_report(monkeypatch, tmp_path, capsys):
    calls = []
    report = tmp_path / "r"
    report.mkdir()
    (report / "report.md").write_text("# Eval\nrule checks 100 %\n", encoding="utf-8")

    def fake_run_suite(root, **kw):
        calls.append((Path(root), kw))
        return SimpleNamespace(report_dir=report, metrics={}, meta={})

    monkeypatch.setattr(cli, "run_suite", fake_run_suite)
    code = cli.main(["--root", str(tmp_path), "eval", "--only", "base", "--only", "P01-repeat",
                     "--snapshot", "S1", "--no-llm"])
    assert code == 0
    root, kw = calls[0]
    assert root == tmp_path.resolve()
    assert kw["only"] == ["base", "P01-repeat"] and kw["snapshot"] == "S1"
    assert kw["narrator"] is None and kw["judge"] is None
    out = capsys.readouterr().out
    assert "rule checks 100 %" in out and str(report) in out


def test_eval_defaults_use_the_llm(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(cli, "run_suite", lambda root, **kw: seen.update(kw) or SimpleNamespace(
        report_dir=None, metrics={}, meta={}))
    assert cli.main(["--root", str(tmp_path), "eval"]) == 0
    assert "narrator" not in seen and "judge" not in seen and seen["only"] is None
