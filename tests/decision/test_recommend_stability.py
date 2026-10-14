"""Stability of the recommended top 3 (docs/decision.md section 15, D25)."""

import copy
import dataclasses

import pytest

from rmprep.contracts import ConstraintResult, ProductOption
from rmprep.decision.config import parse_config
from rmprep.decision.confidence import stability
from rmprep.decision.engine import decide
from rmprep.decision.notes import build_warnings
from rmprep.decision.persona import read_persona
from rmprep.decision.recommend import choose
from rmprep.decision.scoring import PENALTY_RULES, Features, option_features, score_options
from rmprep.decision.universe import build_universe
from tests.decision.conftest import D19_SECTIONS, T0, load_evidence, load_persona

CRITERIA = ("return", "low_risk", "liquidity", "income", "principal", "simplicity", "quality")


@pytest.fixture
def rec_raw(raw) -> dict:
    """The pre-D9 config + the class rule (asset_classes, recommend); stability counts
    position 1 only, so a recommendation at place 2 or 3 is "far down"."""
    raw["asset_classes"] = copy.deepcopy(D19_SECTIONS["asset_classes"])
    raw["recommend"] = copy.deepcopy(D19_SECTIONS["recommend"])
    raw["display"].update(first=1, shortlist=1)
    raw["stability"]["size"] = 1
    return raw


@pytest.fixture
def rec_config(rec_raw):
    return parse_config(rec_raw)


def _levels(config, pid, **changes):
    return dataclasses.replace(read_persona(load_persona(pid), config).levels, **changes)


ZERO = dict(appetite=0.0, liquidity=0.0, income=0.0, principal=0.0, boosts={},
            liquidity_weight=None)


def _hand(oid, cls, values, factors=None, kind="debt"):
    opt = ProductOption(option_id=oid, kind="fund", label=oid, fund_kind=kind, asset_class=cls)
    vals = {c: 0.0 for c in CRITERIA}
    vals.update(values)
    fac = {r: 0.0 for r in PENALTY_RULES}
    fac.update(factors or {})
    return Features(option=opt, values=vals, factors=fac, fields={}, evidence_ids=(),
                    constraint=ConstraintResult("risk_ceiling", True, "ok"), risk=1,
                    risk_estimated=False, period="1y", shorter_period=False,
                    annual_return=0.1)


def _stability(feats, lv, cfg):
    """(top-1 shares, D25 shares with the real result's recommended)."""
    from rmprep.decision.scoring import normalize_weights, penalty_maxima, rank, raw_weights
    order = rank(feats, normalize_weights(raw_weights(lv, cfg)), penalty_maxima(cfg), lv, cfg,
                 with_reasons=False)
    rec = choose(order.rows, lv, cfg)[0]
    pick = lambda rows: choose(rows, lv, cfg)[0]          # noqa: E731
    return rec, stability(feats, lv, cfg), stability(feats, lv, cfg, rec, pick)


# --- the rule on hand-made options ------------------------------------------------------------

def test_class_pick_far_down_that_stays_its_class_best_is_stable(rec_config):
    lv = _levels(rec_config, "P04", **ZERO)                       # Dengeli: the class rule
    x = _hand("fund:X", "borclanma", {"return": 1.0})                     # 0.40
    y = _hand("fund:Y", "borclanma", {"low_risk": 1.0, "quality": 0.1})  # 0.42
    g = _hand("fund:G", "hisse", {"quality": 0.1}, kind="equity")        # 0.02, last
    a = _hand("fund:A", "altin_doviz", {"quality": 0.05}, kind="precious_metals")
    rec, top, d25 = _stability([x, y, g, a], lv, rec_config)
    assert rec == ("fund:Y", "fund:G", "fund:A")
    assert top["fund:G"] == 0.0 and top["fund:A"] == 0.0        # the old value
    assert d25["fund:G"] == 1.0 and d25["fund:A"] == 1.0
    # Y loses its class place to X in 2 of 26 runs (return x 1.2, low_risk x 0.8)
    assert d25["fund:Y"] == pytest.approx(24 / 26)
    assert d25["fund:X"] == top["fund:X"]                        # not recommended


EPS, T = 0.0005, 0.01
# Score difference rival - H1 per dimension at the base weights. Each sum is -EPS (H1
# stays first), and each part is > 5 x EPS, so a run that scales that dimension by
# x 1.2 or x 0.8 (one of the two, by the sign) puts the rival above H1.
DIMS = ("return", "low_risk", "quality", *(f"penalty:{r}" for r in PENALTY_RULES))
UP = (5 * T + EPS) / (4 * T)        # the negative parts of H2: 5 x T - 4 x UP x T = -EPS
H2_DIFF = dict(zip(DIMS, [T, -UP * T, T, -UP * T, T, -UP * T, T, -UP * T, T]))
H3_DIFF = {k: (-v * (1 + 2 * EPS / (5 * T)) if v > 0 else -v) for k, v in H2_DIFF.items()}


def _rival(oid, diff, lv, cfg):
    """An equity fund whose score differs from H1 by `diff` per dimension."""
    from rmprep.decision.scoring import penalty_maxima, raw_weights
    w, m = raw_weights(lv, cfg), penalty_maxima(cfg)
    total = sum(w.values())
    vals = {"return": 0.5, "low_risk": 0.5, "quality": 0.5}
    fac = {r: 0.5 for r in PENALTY_RULES}
    for dim, t in diff.items():
        if dim.startswith("penalty:"):
            rule = dim.removeprefix("penalty:")
            fac[rule] -= t / m[rule]
        else:
            vals[dim] += t * total / w[dim]
    return _hand(oid, "hisse", vals, fac, kind="equity")


def test_pick_that_loses_its_class_place_in_most_runs(rec_config):
    lv = _levels(rec_config, "P04", **ZERO)     # weights: return 1, low_risk 1, quality 0.5
    assert sum(H2_DIFF.values()) == pytest.approx(-EPS)
    assert sum(H3_DIFF.values()) == pytest.approx(-EPS)
    h1 = _rival("fund:H1", {}, lv, rec_config)
    h2 = _rival("fund:H2", H2_DIFF, lv, rec_config)
    h3 = _rival("fund:H3", H3_DIFF, lv, rec_config)
    b = _hand("fund:B", "borclanma", {"return": 0.1})
    a = _hand("fund:A", "altin_doviz", {"return": 0.05}, kind="precious_metals")
    rec, top, d25 = _stability([h1, h2, h3, b, a], lv, rec_config)
    assert rec == ("fund:B", "fund:A", "fund:H1")               # score order
    # H1 loses its class place in 2 runs of each of the 9 dimensions; it keeps it only
    # in the 8 runs of the 4 criteria with weight 0
    assert d25["fund:H1"] == pytest.approx(8 / 26)
    assert d25["fund:H1"] < rec_config.raw["warnings"]["low_stability_below"]
    assert d25["fund:H2"] == top["fund:H2"]     # not recommended


def test_without_the_class_rule_the_share_of_the_plain_top_3(rec_config):
    lv = _levels(rec_config, "P01", **ZERO)                       # Muhafazakâr: plain order
    x = _hand("fund:X", "borclanma", {"return": 1.0})
    y = _hand("fund:Y", "hisse", {"low_risk": 1.0, "quality": 0.1}, kind="equity")
    z = _hand("fund:Z", "dengeli", {"quality": 0.1}, kind="mixed")
    w = _hand("fund:W", "dengeli", {"quality": 0.05}, kind="mixed")
    rec, top, d25 = _stability([x, y, z, w], lv, rec_config)
    assert rec == ("fund:Y", "fund:X", "fund:Z")                  # the first three group heads
    assert top["fund:Z"] == 0.0
    assert d25["fund:Z"] == 1.0 and d25["fund:X"] == 1.0 and d25["fund:Y"] == 1.0
    assert d25["fund:W"] == top["fund:W"] == 0.0


# --- decide -----------------------------------------------------------------------------------

@pytest.mark.parametrize("pid", ["P01", "P03", "P04"])
def test_options_outside_the_top_3_keep_the_top_20_share(d19_config, pid):
    ev = load_evidence()
    r = decide(ev, load_persona(pid), d19_config, created_at=T0)
    lv = read_persona(load_persona(pid), d19_config).levels
    feats, _ = option_features(build_universe(ev, d19_config), lv, d19_config)
    old = stability(feats, lv, d19_config)
    for o in r.options:
        if o.option.option_id not in r.recommended:
            assert o.stability == old[o.option.option_id]


def test_deterministic(d19_config):
    a = decide(load_evidence(), load_persona("P03"), d19_config, created_at=T0)
    b = decide(load_evidence(), load_persona("P03"), d19_config, created_at=T0)
    assert a.to_dict() == b.to_dict()


@pytest.mark.parametrize("pid", ["P01", "P03", "P04"])
def test_no_change_to_scores_order_or_recommended(d19_config, pid):
    ev = load_evidence()
    r = decide(ev, load_persona(pid), d19_config, created_at=T0)
    lv = read_persona(load_persona(pid), d19_config).levels
    scoring = score_options(build_universe(ev, d19_config), lv, d19_config)
    assert [(o.option.option_id, o.score) for o in r.options] == \
        [(x.option.option_id, x.score) for x in scoring.scored]
    assert r.recommended == choose(scoring.scored, lv, d19_config)[0]


# --- low_stability ----------------------------------------------------------------------------

def _shaky(r, oid, value):
    return tuple(dataclasses.replace(o, stability=value) if o.option.option_id == oid else o
                 for o in r.options)


def test_low_stability_for_a_recommended_option_far_down(d19_config):
    ev = load_evidence()
    r = decide(ev, load_persona("P03"), d19_config, created_at=T0)
    lv = read_persona(load_persona("P03"), d19_config).levels
    funds = [o.option.option_id for o in r.options if o.option.kind != "deposit"]
    far = max(r.recommended, key=funds.index)
    options = _shaky(r, far, 0.3)
    ws = build_warnings(options, lv, r.questions, ev, d19_config, recommended=r.recommended)
    [w] = [w for w in ws if w.code == "low_stability"]
    assert w.option_ids == (far,)
    assert "0.30" in w.message


def test_no_low_stability_for_a_shaky_option_that_is_not_recommended(d19_config):
    ev = load_evidence()
    r = decide(ev, load_persona("P03"), d19_config, created_at=T0)
    lv = read_persona(load_persona("P03"), d19_config).levels
    other = next(o.option.option_id for o in r.options
                 if o.option.kind != "deposit" and o.option.option_id not in r.recommended)
    stable = tuple(dataclasses.replace(o, stability=1.0) for o in r.options)
    options = tuple(dataclasses.replace(o, stability=0.1) if o.option.option_id == other else o
                    for o in stable)
    ws = build_warnings(options, lv, r.questions, ev, d19_config, recommended=r.recommended)
    assert not [w for w in ws if w.code == "low_stability"]


def test_decide_warns_for_each_shaky_recommendation(d19_config):
    r = decide(load_evidence(), load_persona("P03"), d19_config, created_at=T0)
    below = d19_config.raw["warnings"]["low_stability_below"]
    by_id = {o.option.option_id: o for o in r.options}
    expected = [oid for oid in r.recommended if by_id[oid].stability < below]
    got = [w.option_ids[0] for w in r.warnings if w.code == "low_stability"]
    assert got == expected
