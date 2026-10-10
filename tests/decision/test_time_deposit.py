"""The time deposit option, ING e-Vadeli Mevduat (docs/decision.md section 1,
milestone D8; contract v1.1)."""

import math
from types import SimpleNamespace

import pytest

from rmprep.contracts import DecisionResult, DecisionState, ProductOption
from rmprep.decision.config import ConfigError, parse_config
from rmprep.decision.confidence import confidence
from rmprep.decision.engine import decide
from rmprep.decision.persona import read_persona
from rmprep import grouping
from rmprep.decision.report import render
from rmprep.decision.scoring import display_order, option_features, score_options
from rmprep.decision.universe import build_universe
from tests.decision.conftest import (
    PERSONA_IDS,
    T0,
    TD,
    TD_SECTION,
    load_persona,
    make_evidence,
)

TD_ID = "time_deposit:ing_e_vadeli"
FULL = dict(returns={"3y": 100.0, "1y": 30.0}, size=2e8, investors=500)
FUNDS = {
    "MMF": dict(kind="money_market", risk=1, **FULL),
    "DBF": dict(kind="debt", risk=2, **FULL),
    "EQF": dict(kind="equity", risk=5, **FULL),
    "MXF": dict(kind="mixed", risk=4, **FULL),
}


def _levels(config, pid="P04"):
    return read_persona(load_persona(pid), config).levels


# --- config -------------------------------------------------------------------------

def test_section_is_optional(raw):
    raw.pop("time_deposit", None)
    raw["kinds"].pop("time_deposit", None)
    raw["texts"]["data_quality"].pop("time_deposit_missing", None)
    parse_config(raw)


def test_section_is_checked(td_config):
    assert td_config.raw["time_deposit"]["term"] == "32-45 gün"


@pytest.mark.parametrize("key", list(TD_SECTION))
def test_missing_section_key_is_an_error(td_raw, key):
    del td_raw["time_deposit"][key]
    with pytest.raises(ConfigError, match="time_deposit"):
        parse_config(td_raw)


def test_unknown_section_key_is_an_error(td_raw):
    td_raw["time_deposit"]["amount"] = 1
    with pytest.raises(ConfigError, match="time_deposit"):
        parse_config(td_raw)


def test_section_needs_a_kind_row(td_raw):
    del td_raw["kinds"]["time_deposit"]
    with pytest.raises(ConfigError, match="time_deposit"):
        parse_config(td_raw)


def test_section_needs_the_missing_note_text(td_raw):
    del td_raw["texts"]["data_quality"]["time_deposit_missing"]
    with pytest.raises(ConfigError, match="time_deposit_missing"):
        parse_config(td_raw)


def test_fund_kind_cannot_be_time_deposit(td_raw):
    td_raw["fund_kinds"]["Karma Şemsiye Fonu"] = "time_deposit"
    with pytest.raises(ConfigError, match="fund_kinds"):
        parse_config(td_raw)


def test_principal_value_may_have_a_time_deposit_entry(td_raw):
    td_raw["principal_value"]["time_deposit"] = 0.9
    cfg = parse_config(td_raw)
    f = _features(cfg)[TD_ID]
    assert f.values["principal"] == 0.9


# --- universe -------------------------------------------------------------------------

def _universe(cfg, **kw):
    kw.setdefault("time_deposit", 35.0)
    return build_universe(make_evidence(FUNDS, **kw), cfg)


def test_option_from_the_row(td_config):
    u = _universe(td_config)
    assert [c.option.kind for c in u.candidates[:2]] == ["deposit", "time_deposit"]
    opt = u.by_id[TD_ID].option
    assert opt.label == "ING e-Vadeli Mevduat (32-45 gün)"
    assert opt.entity == TD
    assert opt.fund_kind == "" and not opt.fx
    assert u.by_id[TD_ID].values["deposit_rate"].value == 35.0
    assert u.missing_time_deposit is None


def test_missing_row_gives_no_option(td_config):
    u = _universe(td_config, time_deposit=None)
    assert TD_ID not in u.by_id
    assert u.missing_time_deposit == TD


def test_no_section_gives_no_option_and_no_note(raw):
    raw.pop("time_deposit", None)
    u = _universe(parse_config(raw))
    assert TD_ID not in u.by_id and u.missing_time_deposit is None


def test_missing_row_gives_a_note(td_config):
    r = decide(make_evidence(FUNDS), load_persona("P04"), td_config, created_at=T0)
    [n] = [n for n in r.data_quality if "e-Vadeli" in n.message]
    assert TD in n.message and n.sources == ("manual",)


# --- scoring -------------------------------------------------------------------------------

def _features(cfg, pid="P04", **kw):
    feats, _ = option_features(_universe(cfg, **kw), _levels(cfg, pid), cfg)
    return {f.option.option_id: f for f in feats}


def test_scored_like_a_deposit_except_the_kind_table(td_config):
    f = _features(td_config)[TD_ID]
    assert f.risk == 1 and not f.risk_estimated
    assert f.annual_return == pytest.approx(0.35) and f.period == "1y"
    assert not f.shorter_period
    v = f.values
    assert (v["low_risk"], v["principal"], v["quality"]) == (1.0, 1.0, 1.0)
    assert (v["liquidity"], v["income"], v["simplicity"]) == (0.6, 0.9, 1.0)
    # rates: deposit .23, funds 1y-annualized 3y = 2^(1/3)-1 = .26, time deposit .35
    assert v["return"] == 1.0


def test_penalties_as_for_any_option(td_config):
    f = _features(td_config, "P05")[TD_ID]          # liquidity intensity 1
    assert f.factors["liquidity"] == pytest.approx(0.4)
    assert f.factors["track_record"] == 0.0 and f.factors["fund_size"] == 0.0
    assert f.factors["principal"] == 0.0 and f.factors["risk_unknown"] == 0.0
    r = score_options(_universe(td_config), _levels(td_config, "P05"), td_config)
    row = next(s for s in r.scored if s.option.option_id == TD_ID)
    assert row.parts["penalty:liquidity"] == pytest.approx(-0.3 * 0.4)
    assert set(row.reasons) == set(row.parts)
    assert math.isclose(sum(row.parts.values()), row.score, abs_tol=1e-12)


def test_confidence_of_the_manual_row(td_config):
    assert confidence(_features(td_config)[TD_ID], td_config) == pytest.approx(0.9)


def _row(oid, kind, score):
    if kind in ("deposit", "time_deposit"):
        opt = ProductOption(option_id=oid, kind=kind, label=oid)
    else:
        opt = ProductOption(option_id=oid, kind="fund", label=oid, fund_kind=kind)
    return SimpleNamespace(option=opt, score=score)


def test_time_deposit_is_its_own_kind_for_the_caps(td_config):
    rows = [_row("deposit:d", "deposit", 0.1), _row("f:a1", "debt", 0.9),
            _row("f:a2", "debt", 0.8), _row(TD_ID, "time_deposit", 0.7),
            _row("f:b1", "equity", 0.65), _row("f:a3", "debt", 0.6)]
    o = display_order(rows, diversity=False, config=td_config)
    assert [r.option.option_id for r in o.rows] == [
        "deposit:d", "f:a1", TD_ID, "f:b1", "f:a2", "f:a3"]
    assert o.concentration == ()


def test_time_deposit_is_ranked_and_not_the_baseline(td_config):
    r = decide(make_evidence(FUNDS, time_deposit=35.0), load_persona("P04"), td_config,
               created_at=T0)
    assert r.options[0].option.kind == "deposit"
    td = next(o for o in r.options if o.option.option_id == TD_ID)
    assert r.options.index(td) > 0
    assert 0.0 <= td.stability <= 1.0


# --- report and decide --------------------------------------------------------------------

def test_report_has_a_time_deposit_group(td_config):
    r = decide(make_evidence(FUNDS, time_deposit=35.0), load_persona("P04"), td_config,
               created_at=T0)
    gs = {g.key: g for g in grouping.groups(r.options)}
    assert gs["time_deposit"].head.option.option_id == TD_ID
    assert gs["time_deposit"].alternatives == ()
    text = render(r)
    assert "time_deposit (1)" in text and "ING e-Vadeli Mevduat (32-45 gün)" in text


@pytest.mark.parametrize("pid", PERSONA_IDS)
def test_valid_results_with_the_row(td_config, pid):
    ev = make_evidence(FUNDS, time_deposit=35.0)
    r = decide(ev, load_persona(pid), td_config, created_at=T0)
    assert isinstance(r, DecisionResult) and r.state == DecisionState.READY
    assert TD_ID in {o.option.option_id for o in r.options}
    assert DecisionResult.from_dict(r.to_dict()) == r
    assert not [n for n in r.data_quality if "e-Vadeli" in n.message]
