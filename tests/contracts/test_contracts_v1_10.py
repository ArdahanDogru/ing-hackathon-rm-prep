"""Contract v1.10 (2026-10-14): current split, RM holdings input, effective weights
(spec docs/superpowers/specs/2026-10-14-portfolio-projection-design.md, section 7)."""

import json
from pathlib import Path

import pytest

from rmprep.contracts import (ACTIVE_HOLDINGS_SOURCES, ALLOCATION_CLASSES, HOLDINGS_SOURCES,
                              AllocationBand, DecisionResult, HoldingsInput)

FIXTURES = Path(__file__).parent / "fixtures"     # as FIX in tests/api/conftest.py


def _shares(**over):
    d = {"nakit_benzeri": 40.0, "borclanma": 20.0, "hisse": 20.0, "altin_doviz": 10.0, "dengeli": 10.0}
    return d | over


def test_sources_and_classes():
    assert HOLDINGS_SOURCES == ("rm", "rm_confirmed", "persona_text", "profile", "national")
    assert ACTIVE_HOLDINGS_SOURCES == ("rm", "rm_confirmed", "persona_text")
    assert ALLOCATION_CLASSES == ("nakit_benzeri", "borclanma", "hisse", "altin_doviz", "dengeli")


def test_allocation_classes_match_the_config():
    from rmprep.decision.config import load_config
    assert tuple(load_config().raw["allocation"]["classes"]) == ALLOCATION_CLASSES


def test_holdings_input_ok():
    h = HoldingsInput(_shares(), "rm")
    assert h.origin == "rm" and sum(h.shares.values()) == 100.0
    assert list(h.shares) == list(ALLOCATION_CLASSES)
    assert HoldingsInput(_shares(dengeli=10.4), "rm_confirmed")       # within ± 0.5
    assert isinstance(HoldingsInput({**_shares(), "hisse": 20}, "rm").shares["hisse"], float)


@pytest.mark.parametrize("shares, origin, msg", [
    (_shares(dengeli=11.0), "rm", "total"),
    (_shares(dengeli=9.4), "rm", "total"),
    ({k: v for k, v in _shares().items() if k != "dengeli"} | {"hisse": 30.0}, "rm", "classes"),
    (_shares() | {"gayrimenkul": 0.0}, "rm", "classes"),
    (_shares(hisse=-1.0, nakit_benzeri=61.0), "rm", "0-100"),
    (_shares(), "profile", "origin"),
])
def test_holdings_input_rejects(shares, origin, msg):
    with pytest.raises(ValueError, match=msg):
        HoldingsInput(shares, origin)


def test_band_current_fields():
    b = AllocationBand("hisse", 70, 85, "Ata", False, None, "", current=10.0, current_low=5.0,
                       current_high=15.0, current_source="profile", current_ref="Teknoloji kurucusu",
                       gap=60.0, active=False)
    assert b.gap == 60.0 and not b.active
    old = AllocationBand("hisse", 70, 85, "Ata", False, None, "")      # v1.8 constructor
    assert old.current is None and old.current_source == "" and old.active is False
    rm = AllocationBand("dengeli", None, None, "", False, None, "", current=0.0,
                        current_source="rm", active=True)               # no band, point only
    assert rm.gap is None


def test_band_rejects_bad_current():
    with pytest.raises(ValueError, match="current"):
        AllocationBand("hisse", 70, 85, "Ata", False, None, "", current=20.0, current_low=25.0,
                       current_high=30.0, current_source="profile")
    with pytest.raises(ValueError, match="current_source"):
        AllocationBand("hisse", 70, 85, "Ata", False, None, "", current=20.0, current_source="guess")
    with pytest.raises(ValueError, match="active"):
        AllocationBand("hisse", 70, 85, "Ata", False, None, "", current=20.0, current_low=20.0,
                       current_high=20.0, current_source="national", active=True)


def test_result_round_trip_with_holdings():
    from rmprep.ui.fake import FakeBackend
    b = FakeBackend(FIXTURES)
    r = b.decide(b.list_personas()[0], b.list_snapshots()[0])
    r2 = b.set_holdings(r.run_id, _shares(), "rm")
    assert r2.holdings_input == HoldingsInput(_shares(), "rm")
    back = DecisionResult.from_dict(json.loads(json.dumps(r2.to_dict())))
    assert back.holdings_input == r2.holdings_input
    assert b.set_holdings(r2.run_id, None).holdings_input is None


def test_v19_json_loads():
    """A run record written before v1.10 (no new keys) still loads."""
    from rmprep.ui.fake import FakeBackend
    b = FakeBackend(FIXTURES)
    r = b.decide(b.list_personas()[0], b.list_snapshots()[0])
    d = r.to_dict()
    d.pop("holdings_input")
    d.pop("effective_weights")
    for band in d["allocation"]:
        for k in ("current", "current_low", "current_high", "current_source", "current_ref", "gap", "active"):
            band.pop(k)
    back = DecisionResult.from_dict(json.loads(json.dumps(d)))
    assert back.holdings_input is None and dict(back.effective_weights) == {}
