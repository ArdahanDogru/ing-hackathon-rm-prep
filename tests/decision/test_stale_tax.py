"""Stale tax and inflation inputs: warning stale_tax_input and its to_confirm item
(docs/decision.md section 12, D22)."""

import dataclasses

import pytest

from rmprep.contracts import DecisionState, Flag
from rmprep.decision.config import ConfigError, parse_config
from rmprep.decision.engine import decide
from tests.decision.conftest import (
    CPI,
    STOPAJ,
    T0,
    add_d9,
    d9_rows,
    load_persona,
    make_evidence,
)

WARNING_TEXT = ("Vergi veya enflasyon verisi güncel değil ({entities}); reel getiriler bu "
                "değerlerle hesaplandı. Güncel oranı teyit edin.")
CONFIRM = "Güncel stopaj oranını ve TÜFE'yi teyit edin."
FULL = dict(returns={"1y": 40.0, "3y": 150.0}, size=2e8, investors=500)
FUNDS = {"MM": dict(kind="money_market", risk=1, **FULL),
         "DB": dict(kind="debt", risk=2, **FULL)}


def add_d22(raw: dict) -> dict:
    """Add the D22 texts (section 12) to a raw config, in place."""
    raw["texts"]["warnings"]["stale_tax_input"] = WARNING_TEXT
    raw.setdefault("to_confirm", {})["stale_tax_input"] = CONFIRM
    return raw


@pytest.fixture
def d22_raw(raw) -> dict:
    return add_d22(add_d9(raw))


@pytest.fixture
def d22_config(d22_raw):
    return parse_config(d22_raw)


def _ev(stale=(), funds=FUNDS):
    """FUNDS + deposit + CPI/stopaj rows; stale: entities whose row is flagged stale."""
    rows = [r.with_flags(Flag.STALE) if r.entity in stale else r for r in d9_rows()]
    return make_evidence(funds, extra=rows)


def _stale(r):
    return [w for w in r.warnings if w.code == "stale_tax_input"]


def _row_id(ev, entity):
    return next(d.id for d in ev.datapoints if d.entity == entity)


def test_stale_stopaj_row_gives_warning_and_to_confirm(d22_config):
    ev = _ev(stale=(STOPAJ["deposit"],))
    r = decide(ev, load_persona("P01"), d22_config, created_at=T0)
    [w] = _stale(r)
    assert w.message == WARNING_TEXT.format(entities=STOPAJ["deposit"])
    assert w.evidence_ids == (_row_id(ev, STOPAJ["deposit"]),)
    assert w.option_ids == ()
    assert r.to_confirm.count(CONFIRM) == 1


def test_stale_cpi_row_gives_warning_and_to_confirm(d22_config):
    ev = _ev(stale=(CPI,))
    r = decide(ev, load_persona("P01"), d22_config, created_at=T0)
    [w] = _stale(r)
    assert w.message == WARNING_TEXT.format(entities=CPI)
    assert w.evidence_ids == (_row_id(ev, CPI),)
    assert r.to_confirm.count(CONFIRM) == 1


def test_several_stale_rows_give_one_warning(d22_config):
    stale = (CPI, STOPAJ["deposit"], STOPAJ["money_market"])
    ev = _ev(stale=stale)
    r = decide(ev, load_persona("P01"), d22_config, created_at=T0)
    [w] = _stale(r)
    assert w.message == WARNING_TEXT.format(entities=", ".join(sorted(stale)))
    assert w.evidence_ids == tuple(sorted(_row_id(ev, e) for e in stale))
    assert r.to_confirm.count(CONFIRM) == 1


def test_fresh_rows_give_neither(d22_config):
    r = decide(_ev(), load_persona("P01"), d22_config, created_at=T0)
    assert _stale(r) == []
    assert CONFIRM not in r.to_confirm


def test_stale_row_of_an_unused_product_type_gives_nothing(d22_config):
    # no time-deposit rate in the evidence -> no time deposit option uses that stopaj row
    r = decide(_ev(stale=(STOPAJ["time_deposit"],)), load_persona("P01"), d22_config,
               created_at=T0)
    assert all(o.option.kind != "time_deposit" for o in r.options)
    assert _stale(r) == []
    assert CONFIRM not in r.to_confirm


def test_stale_row_of_a_rejected_fund_only_gives_nothing(d22_config):
    # the only money-market fund is above P01's risk ceiling: not scored
    funds = {"MM": dict(kind="money_market", risk=7, **FULL),
             "DB": dict(kind="debt", risk=2, **FULL)}
    r = decide(_ev(stale=(STOPAJ["money_market"],), funds=funds), load_persona("P01"),
               d22_config, created_at=T0)
    assert "fund:MM" not in {o.option.option_id for o in r.options}
    assert _stale(r) == []


def test_warning_is_rm_only(d22_config):
    r = decide(_ev(stale=(CPI,)), load_persona("P01"), d22_config, created_at=T0)
    assert _stale(r)[0].audience == "rm"


def test_warning_cannot_be_for_the_client(d22_raw):
    d22_raw["warnings"]["audience"] = {"stale_tax_input": "client"}
    with pytest.raises(ConfigError, match="warnings.audience.stale_tax_input"):
        parse_config(d22_raw)


def test_scores_and_order_do_not_change(d22_config):
    fresh = decide(_ev(), load_persona("P01"), d22_config, created_at=T0)
    stale = decide(_ev(stale=(CPI, STOPAJ["deposit"])), load_persona("P01"), d22_config,
                   created_at=T0)
    assert [(o.option.option_id, o.score) for o in stale.options] == \
        [(o.option.option_id, o.score) for o in fresh.options]
    assert stale.recommended == fresh.recommended


def test_needs_rm_input_has_no_warning(d22_config):
    p = dataclasses.replace(load_persona("P01"), risk_profili="?")
    r = decide(_ev(stale=(CPI,)), p, d22_config, created_at=T0)
    assert r.state == DecisionState.NEEDS_RM_INPUT
    assert r.warnings == ()
    assert CONFIRM not in r.to_confirm


def test_without_config_nothing_changes(raw):
    raw = add_d9(raw)                       # the real config has the D22 keys since 2026-10-14
    raw["texts"]["warnings"].pop("stale_tax_input", None)
    raw.get("to_confirm", {}).pop("stale_tax_input", None)
    r = decide(_ev(stale=(CPI,)), load_persona("P01"), parse_config(raw), created_at=T0)
    assert _stale(r) == []
    assert CONFIRM not in r.to_confirm


def test_warning_without_to_confirm_entry(d22_raw):
    del d22_raw["to_confirm"]["stale_tax_input"]
    r = decide(_ev(stale=(CPI,)), load_persona("P01"), parse_config(d22_raw), created_at=T0)
    assert len(_stale(r)) == 1
    assert CONFIRM not in r.to_confirm


@pytest.mark.parametrize("edit", [
    lambda r: r["texts"]["warnings"].update(stale_tax_input="Eski veri: {rows}"),
    lambda r: r["to_confirm"].update(stale_tax_input=""),
])
def test_bad_d22_config_is_an_error(d22_raw, edit):
    edit(d22_raw)
    with pytest.raises(ConfigError, match="stale_tax_input"):
        parse_config(d22_raw)
