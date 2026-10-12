"""Contract v1.8 (docs/decision.md section 11, D20): model allocation bands."""

import dataclasses
import json
from pathlib import Path

import pytest

from rmprep.contracts import AllocationBand, DecisionResult

FIX = Path(__file__).resolve().parent / "fixtures"


def _ready() -> DecisionResult:
    return DecisionResult.from_dict(
        json.loads((FIX / "decision_p02_ready.json").read_text(encoding="utf-8")))


def test_defaults_and_old_json():
    r = _ready()
    assert r.allocation == () and r.allocation_notes == ()


def test_round_trip():
    r = _ready()
    oid = r.options[1].option.option_id
    bands = (AllocationBand("borclanma", 30.0, 40.0, "Ata Yatırım 2026", False, oid, ""),
             AllocationBand("dengeli", None, None, "", False, None, "none"),
             AllocationBand("hisse", 20.0, 40.0, "çıkarım", True, None, "ceiling"))
    r2 = dataclasses.replace(r, allocation=bands, allocation_notes=("Dosyaya göre ...",))
    assert DecisionResult.from_dict(json.loads(json.dumps(r2.to_dict()))) == r2


@pytest.mark.parametrize("kw", [dict(low=50.0, high=40.0), dict(low=-1.0, high=10.0),
                                dict(low=10.0, high=101.0), dict(low=10.0, high=None),
                                dict(asset_class=" ")])
def test_band_checks(kw):
    base = dict(asset_class="hisse", low=10.0, high=20.0, source="s", inferred=False,
                option_id=None, note="")
    with pytest.raises(ValueError):
        AllocationBand(**(base | kw))


def test_band_option_must_be_scored():
    r = _ready()
    with pytest.raises(ValueError, match="not scored"):
        dataclasses.replace(r, allocation=(AllocationBand("hisse", 1.0, 2.0, "s", False, "fund:NOPE", ""),))
