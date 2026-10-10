"""Short history and funds without data rows (the D15 row of docs/decision.md
section 8; found by the first full eval)."""

import pytest

from rmprep.contracts import DecisionResult, DecisionState
from rmprep.decision.config import ConfigError, parse_config
from rmprep.decision.engine import decide
from tests.decision.conftest import (
    D15_TEXTS,
    PERSONA_IDS,
    T0,
    d9_rows,
    dp,
    load_persona,
    make_evidence,
    market_row,
)

SHORT = D15_TEXTS["constraint"]["short_history"]
BASE = dict(size=2e8, investors=500, buyable=1, sell_valor=0)
FUNDS = {
    "MMF": dict(kind="money_market", risk=1, returns={"1y": 50.0, "3y": 200.0}, **BASE),
    "DBF": dict(kind="debt", risk=2, returns={"1y": 30.0, "3y": 100.0}, **BASE),
    # VKR/ZPO/ZTV without tefas_detail: only the 1-month return
    "SH1": dict(kind="money_market", returns={"1m": 3.0}),
    # only the 3-month return: enough history
    "SH3": dict(kind="money_market", risk=1, returns={"3m": 10.0}, **BASE),
    "NOD": dict(kind="debt"),           # no data row the engine uses (only a price row)
}


def _ev():
    return make_evidence(FUNDS, time_deposit=35.0,
                         extra=d9_rows() + [market_row(), dp("fund_price", "NOD", 1.0)])


def _row_id(quantity, code):
    return next(d.id for d in _ev().datapoints if d.quantity == quantity and d.entity == code)


def _decide(cfg, pid):
    return decide(_ev(), load_persona(pid), cfg, created_at=T0)


def _listed(r):
    return {o.option.option_id: o for o in r.options}


def _rejected(r):
    return {x.option.option_id: x for x in r.rejected}


# --- config ---------------------------------------------------------------------------------

def test_d15_config_is_valid_and_optional(d15_config, config):
    assert d15_config.raw["short_history"]["min_period"] == "3m"
    assert "short_history" not in config.raw


@pytest.mark.parametrize("edit,match", [
    (lambda r: r["short_history"].update(min_period="2m"), "short_history.min_period"),
    (lambda r: r["short_history"].update(allow_appetite=1.5), "short_history.allow_appetite"),
    (lambda r: r["short_history"].pop("allow_appetite"), "short_history"),
    (lambda r: r["texts"]["constraint"].pop("short_history"), "short_history"),
    (lambda r: r["texts"]["data_quality"].pop("removed_no_data"), "removed_no_data"),
])
def test_bad_d15_config_is_an_error(d15_raw, edit, match):
    edit(d15_raw)
    with pytest.raises(ConfigError, match=match):
        parse_config(d15_raw)


# --- the rule -------------------------------------------------------------------------------

def test_only_1m_is_rejected_with_the_1m_row_as_evidence(d15_config):
    r = _decide(d15_config, "P05")
    assert "fund:SH1" not in _listed(r)
    [c] = [c for c in _rejected(r)["fund:SH1"].failed if c.rule_id == "short_history"]
    assert not c.passed and c.reason == SHORT
    assert c.evidence_ids == (_row_id("fund_return_1m", "SH1"),)


def test_3m_return_is_enough(d15_config):
    r = _decide(d15_config, "P05")
    assert "fund:SH3" in _listed(r)


def test_agresif_keeps_it_with_the_penalty_and_the_reason(d15_config):
    r = _decide(d15_config, "P03")                     # appetite 1
    sh = _listed(r)["fund:SH1"]
    assert "fund:SH1" not in _rejected(r)
    assert sh.score_parts["penalty:track_record"] < 0
    assert sh.reasons["return"].endswith(SHORT)
    assert _row_id("fund_return_1m", "SH1") in sh.evidence_ids


@pytest.mark.parametrize("pid", ["P01", "P02", "P04", "P05"])
def test_not_agresif_rejects_it(d15_config, pid):
    r = _decide(d15_config, pid)
    assert "fund:SH1" not in _listed(r)
    assert "short_history" in [c.rule_id for c in _rejected(r)["fund:SH1"].failed]


def test_fund_without_any_data_row_is_removed_and_counted(d15_config):
    for pid in PERSONA_IDS:
        r = _decide(d15_config, pid)
        assert "fund:NOD" not in _listed(r) and "fund:NOD" not in _rejected(r)
        msg = D15_TEXTS["data_quality"]["removed_no_data"].format(count=1)
        assert msg in [n.message for n in r.data_quality]


@pytest.mark.parametrize("pid", PERSONA_IDS)
def test_no_listed_option_without_evidence_ids(d15_config, pid):
    r = _decide(d15_config, pid)
    assert r.state == DecisionState.READY
    assert all(o.evidence_ids for o in r.options)
    assert DecisionResult.from_dict(r.to_dict()) == r


def test_without_the_config_the_old_behaviour_stays(d13_config):
    r = _decide(d13_config, "P05")
    assert "fund:SH1" in _listed(r)
