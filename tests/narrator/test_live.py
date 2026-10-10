"""Live smoke test: one real draft (costs about $0.05). Never part of a normal
run: it needs RMPREP_LIVE_NARRATOR=1 and an API key (environment or the .env of
the root). ing-lead runs it:

    set RMPREP_LIVE_NARRATOR=1
    python -m pytest tests/narrator/test_live.py -s
"""

import os
from pathlib import Path

import pytest

from rmprep.narrator.service import narrator_from_root
from tests.narrator.conftest import evidence, p02

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(os.environ.get("RMPREP_LIVE_NARRATOR") != "1",
                    reason="live LLM call: set RMPREP_LIVE_NARRATOR=1")
def test_live_draft(tmp_path):
    n = narrator_from_root(ROOT)
    if n.client is None:
        pytest.skip("no ANTHROPIC_API_KEY")
    n.cache_dir = tmp_path
    d = n.draft(p02(), evidence(), "TR")
    print(f"\nsource={d.source} model={d.model} cost=${d.cost_usd:.4f} checks={d.checks}")
    for s in d.sections:
        print(f"[{s.key}]", *(x.text for x in s.sentences), sep="\n  ")
    assert d.cost_usd > 0
    assert d.source == "llm", d.checks
