"""confidence and stability (docs/decision.md section 5)."""

import dataclasses

import pytest

from rmprep.contracts import ConstraintResult, ProductOption
from rmprep.decision.config import parse_config
from rmprep.decision.confidence import confidence, stability
from rmprep.decision.persona import read_persona
from rmprep.decision.scoring import (
    PENALTY_RULES,
    Features,
    normalize_weights,
    option_features,
    penalty_maxima,
    rank,
    raw_weights,
)
from rmprep.decision.universe import build_universe
from tests.decision.conftest import load_evidence, load_persona, make_evidence


def _levels(config, pid="P04", **changes):
    return dataclasses.replace(read_persona(load_persona(pid), config).levels, **changes)


def _features(config, funds, levels=None, **kw):
    u = build_universe(make_evidence(funds, **kw), config)
    feats, _ = option_features(u, levels or _levels(config), config)
    return {f.option.option_id: f for f in feats}


FULL = dict(risk=3, returns={"3y": 100.0}, size=2e8, investors=500)


# --- confidence -----------------------------------------------------------------------

@pytest.mark.parametrize("flags,expected", [
    ((), 1.0),
    (("needs_check",), 0.9),
    (("unverified_series",), 0.8),
    (("stale",), 0.7),
    (("needs_check", "conflict"), 0.6),     # a row takes its lowest factor
])
def test_confidence_of_the_weakest_row(config, flags, expected):
    f = _features(config, {"F": dict(kind="debt", flags=flags, **FULL)})["fund:F"]
    assert confidence(f, config) == pytest.approx(expected)


def test_weakest_row_decides(config):
    ev = make_evidence({"F": dict(kind="debt", flags=("needs_check",), **FULL)})
    rows = [d if d.quantity != "fund_total_value" else d.with_flags("stale")
            for d in ev.datapoints]
    ev = dataclasses.replace(ev, datapoints=tuple(rows))
    feats, _ = option_features(build_universe(ev, config), _levels(config), config)
    f = next(x for x in feats if x.option.entity == "F")
    assert confidence(f, config) == pytest.approx(0.7)


def test_deposit_confidence(config):
    f = _features(config, {})["deposit:ing_turuncu"]
    assert confidence(f, config) == pytest.approx(0.9)


def test_risk_estimate_factor(config):
    f = _features(config, {"F": dict(kind="debt", flags=("needs_check",), returns={"3y": 1.0},
                                     size=2e8, investors=500)})["fund:F"]
    assert confidence(f, config) == pytest.approx(0.9 * 0.7)


def test_shorter_period_factor(config):
    f = _features(config, {"F": dict(kind="debt", risk=3, returns={"1y": 10.0}, size=2e8,
                                     investors=500)})["fund:F"]
    assert confidence(f, config) == pytest.approx(0.8)


def test_both_estimates(config):
    f = _features(config, {"F": dict(kind="debt", flags=("needs_check",),
                                     returns={"6m": 10.0})})["fund:F"]
    assert confidence(f, config) == pytest.approx(0.9 * 0.7 * 0.8)


def test_typical_values_on_real_rows(config):
    lv = read_persona(load_persona("P04"), config).levels
    feats, _ = option_features(build_universe(load_evidence(), config), lv, config)
    by = {f.option.option_id: f for f in feats}
    assert confidence(by["fund:AAL"], config) == pytest.approx(0.9)
    assert confidence(by["fund:ADP"], config) == pytest.approx(0.63)     # no risk level
    assert confidence(by["deposit:ing_turuncu"], config) == pytest.approx(0.9)


# --- stability --------------------------------------------------------------------------

def _hand(oid, kind, values, factors=None):
    if kind == "deposit":
        opt = ProductOption(option_id=oid, kind="deposit", label=oid)
    else:
        opt = ProductOption(option_id=oid, kind="fund", label=oid, fund_kind=kind)
    vals = {c: 0.0 for c in ("return", "low_risk", "liquidity", "income", "principal",
                             "simplicity", "quality")}
    vals.update(values)
    fac = {r: 0.0 for r in PENALTY_RULES}
    fac.update(factors or {})
    return Features(option=opt, values=vals, factors=fac, fields={}, evidence_ids=(),
                    constraint=ConstraintResult("risk_ceiling", True, "ok"), risk=1,
                    risk_estimated=False, period="1y", shorter_period=False,
                    annual_return=0.1)


@pytest.fixture
def top1(raw):
    raw["display"].update(first=1, shortlist=1)
    return parse_config(raw)


def test_stability_by_hand(top1):
    # raw weights: return 1, low_risk 1, quality 0.5, the rest 0 (sum 2.5).
    lv = _levels(top1, appetite=0.0, liquidity=0.0, income=0.0, principal=0.0, boosts={},
                 liquidity_weight=None)
    x = _hand("fund:X", "debt", {"return": 1.0})                       # 1 / 2.5 = 0.40
    y = _hand("fund:Y", "equity", {"low_risk": 1.0, "quality": 0.1})   # 1.05 / 2.5 = 0.42
    d = _hand("deposit:d", "deposit", {})
    s = stability([x, y, d], lv, top1)
    # X is first only with return x 1.2 and low_risk x 0.8: 2 of 26 runs.
    assert s["fund:X"] == pytest.approx(2 / 26)
    assert s["fund:Y"] == pytest.approx(24 / 26)
    assert s["deposit:d"] == 1.0


def test_penalty_maxima_are_perturbed(top1):
    lv = _levels(top1, appetite=0.0, liquidity=0.0, income=0.0, principal=0.0, boosts={},
                 liquidity_weight=None)
    # X = (1 + 0.5 x 0.4) / 2.5 - 0.1 x 0.7 = 0.41; Y = 1.05 / 2.5 = 0.42 -> Y first.
    # X first: return x 1.2 (0.4485 > 0.3889), low_risk x 0.8 (0.4517 > 0.3696) and
    # fund_size max x 0.8 (0.48 - 0.056 = 0.424 > 0.42). quality x 1.2: 0.4069 < 0.4077.
    x = _hand("fund:X", "debt", {"return": 1.0, "quality": 0.4}, {"fund_size": 0.7})
    y = _hand("fund:Y", "equity", {"low_risk": 1.0, "quality": 0.1})
    s = stability([x, y], lv, top1)
    assert s["fund:X"] == pytest.approx(3 / 26)
    assert s["fund:Y"] == pytest.approx(23 / 26)


def test_all_options_in_a_short_universe_are_stable(config):
    feats = list(_features(config, {"A": dict(kind="debt", **FULL),
                                    "B": dict(kind="equity", **FULL)}).values())
    s = stability(feats, _levels(config), config)
    assert set(s.values()) == {1.0}


def _xy(cfg):
    lv = _levels(cfg, appetite=0.0, liquidity=0.0, income=0.0, principal=0.0, boosts={},
                 liquidity_weight=None)
    x = _hand("fund:X", "debt", {"return": 1.0})
    y = _hand("fund:Y", "equity", {"low_risk": 1.0, "quality": 0.1})
    z = _hand("fund:Z", "mixed", {"quality": 0.1})
    return stability([x, y, z], lv, cfg)


def test_stability_size_defaults_to_the_shortlist(raw):
    raw["display"].update(first=1, shortlist=1)
    raw["stability"].pop("size", None)
    s = _xy(parse_config(raw))
    assert s["fund:X"] == pytest.approx(2 / 26) and s["fund:Z"] == 0.0


def test_stability_size_counts_more_positions_than_the_shortlist(raw):
    raw["display"].update(first=1, shortlist=1)
    raw["stability"]["size"] = 2
    s = _xy(parse_config(raw))
    # X and Y always fill positions 1-2; Z (0.02) never does
    assert s["fund:X"] == 1.0 and s["fund:Y"] == 1.0 and s["fund:Z"] == 0.0


def test_stability_size_20_on_real_rows(raw):
    cfg = parse_config(raw)
    lv = read_persona(load_persona("P03"), cfg).levels
    feats, _ = option_features(build_universe(load_evidence(), cfg), lv, cfg)
    order = rank(feats, normalize_weights(raw_weights(lv, cfg)), penalty_maxima(cfg), lv, cfg)
    funds = [r.option.option_id for r in order.rows if r.option.kind != "deposit"]
    raw["stability"].pop("size", None)
    default = stability(feats, lv, parse_config(raw))
    raw["stability"]["size"] = 20
    wide = stability(feats, lv, parse_config(raw))
    assert any(default[oid] == 0.0 for oid in funds[10:20])
    assert all(wide[oid] > 0.0 for oid in funds[10:20])
    assert all(wide[oid] >= default[oid] for oid in funds)
