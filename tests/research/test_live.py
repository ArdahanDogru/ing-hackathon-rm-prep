"""Live smoke test of the Exa provider (about $0.012): runs only with
RMPREP_LIVE_RESEARCH=1 and an EXA_API_KEY in the environment or in the .env of
RMPREP_LIVE_ROOT (default: the main checkout), so a plain pytest never calls the API."""

import os
from pathlib import Path

import pytest

from rmprep.contracts import ProductOption
from rmprep.research.config import load_config
from rmprep.research.exa import ExaProvider

ROOT = Path(os.environ.get("RMPREP_LIVE_ROOT", "C:/Users/yardang/dev/ing-hackathon/prototype"))
pytestmark = pytest.mark.skipif(os.environ.get("RMPREP_LIVE_RESEARCH") != "1",
                                reason="live test: set RMPREP_LIVE_RESEARCH=1")


def _key() -> str:
    from dotenv import dotenv_values
    return (os.environ.get("EXA_API_KEY") or dotenv_values(ROOT / ".env").get("EXA_API_KEY") or "").strip()


def test_ppn_live():
    key = _key()
    if not key:
        pytest.skip("no EXA_API_KEY")
    config = load_config()
    ppn = ProductOption("fund:PPN", "fund", "NUROL PORTFÖY PARA PİYASASI (TL) FONU", entity="PPN",
                        fund_kind="money_market", asset_class="nakit_benzeri")
    r = ExaProvider(config.exa, config.system_prompt, key).research_product(ppn, "TR")
    assert r.findings and all(f.sources for f in r.findings)
    assert not any("kap.org.tr" in s.url for f in r.findings for s in f.sources)
    assert "Nurol" in r.company
    assert 0 < r.cost_usd < 0.05
