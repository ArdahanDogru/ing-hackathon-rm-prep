"""config/eval.yaml: loaded and checked."""

import pytest

from rmprep.eval.config import ConfigError, load_config
from tests.eval.conftest import PROJECT, eval_yaml


def test_project_config_loads():
    c = load_config(PROJECT / "config" / "eval.yaml")
    assert c.max_cost_usd_per_run == 5.0 and c.report_dir == "data/eval"
    assert c.judge.model == "claude-haiku-5-5"
    assert c.judge.workspace_id_env == "ANTHROPIC_WORKSPACE_ID"
    assert [r.id for r in c.judge.rubric] == ["tailored", "clear_for_rm", "balanced"]
    assert c.targets.rule_checks == 1.0 and c.targets.forbidden_phrases == 0


def _write(tmp_path, text):
    f = tmp_path / "eval.yaml"
    f.write_text(text, encoding="utf-8")
    return f


GOOD = eval_yaml()     # the project config with snapshot: null


@pytest.mark.parametrize("old, new, match", [
    ("version: 1", "version: 2", "version"),
    ("report_dir: data/eval", "report_dir: data/eval\ncolour: red", "unknown"),
    ("max_cost_usd_per_run: 5.0", "max_cost_usd_per_run: -1", "max_cost"),
    ("  effort: low", "  effort: low\n  colour: red", "unknown"),
    ("    - id: balanced", "    - id: tailored", "duplicate"),
])
def test_bad_configs_are_rejected(tmp_path, old, new, match):
    assert old in GOOD
    with pytest.raises(ConfigError, match=match):
        load_config(_write(tmp_path, GOOD.replace(old, new, 1)))


def test_snapshot_may_be_set(tmp_path):
    c = load_config(_write(tmp_path, eval_yaml("20261010-001233-6b20")))
    assert c.snapshot == "20261010-001233-6b20"
    assert load_config(_write(tmp_path, GOOD)).snapshot is None
