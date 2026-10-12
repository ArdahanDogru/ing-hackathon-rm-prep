"""Contract v1.6 (docs/decision.md section 10, D19): asset class per option and
the engine's recommended top 3."""

import dataclasses
import json
from pathlib import Path

import pytest

from rmprep.contracts import DecisionResult, ProductOption
from rmprep.grouping import recommended, top_heads

FIX = Path(__file__).resolve().parent / "fixtures"


def _ready() -> DecisionResult:
    return DecisionResult.from_dict(
        json.loads((FIX / "decision_p02_ready.json").read_text(encoding="utf-8")))


def test_defaults_and_old_json():
    r = _ready()
    assert r.recommended == ()
    assert all(o.option.asset_class == "" for o in r.options)
    assert ProductOption("fund:X", "fund", "X", fund_kind="debt").asset_class == ""


def test_round_trip():
    r = _ready()
    ids = tuple(o.option.option_id for o in r.options[1:3])
    opts = tuple(dataclasses.replace(o, option=dataclasses.replace(o.option, asset_class="borclanma"))
                 for o in r.options)
    r2 = dataclasses.replace(r, options=opts, recommended=ids)
    assert DecisionResult.from_dict(json.loads(json.dumps(r2.to_dict()))) == r2


def test_recommended_checks():
    r = _ready()
    ids = [o.option.option_id for o in r.options]
    with pytest.raises(ValueError, match="at most 3"):
        dataclasses.replace(r, recommended=tuple(ids[1:5]))
    with pytest.raises(ValueError, match="not scored"):
        dataclasses.replace(r, recommended=("fund:NOPE",))
    with pytest.raises(ValueError, match="twice"):
        dataclasses.replace(r, recommended=(ids[1], ids[1]))


def test_grouping_recommended_prefers_the_engine():
    r = _ready()
    assert recommended(r) == top_heads(r.options, 3)          # empty: the fallback
    chosen = (r.options[-1].option.option_id,)
    picked = recommended(dataclasses.replace(r, recommended=chosen))
    assert tuple(o.option.option_id for o in picked) == chosen
