"""Product universe and evidence lookup (docs/decision.md section 1)."""

import dataclasses
from collections import Counter
from datetime import date

import pytest

from rmprep.contracts import EntityInfo
from rmprep.decision.universe import build_universe, latest
from tests.decision.conftest import dp, load_evidence


@pytest.fixture(scope="module")
def medium():
    return load_evidence()


def _with(ev, add=(), entities=None, excluded=None):
    return dataclasses.replace(
        ev, datapoints=tuple(ev.datapoints) + tuple(add),
        entities=dict(ev.entities if entities is None else entities),
        excluded_sources=frozenset(ev.excluded_sources if excluded is None else excluded))


# --- universe on evidence_medium ------------------------------------------------------

def test_deposit_is_the_first_candidate(medium, config):
    u = build_universe(medium, config)
    dep = u.candidates[0]
    assert dep.option.option_id == "deposit:ing_turuncu"
    assert dep.option.kind == "deposit"
    assert dep.option.label == "ING Turuncu Hesap (standart)"
    assert dep.option.entity == "ING Turuncu Hesap standart, 100.000-249.999 TL"
    assert dep.values["deposit_rate"].value == 23.0
    assert all(c.option.kind == "fund" for c in u.candidates[1:])


def test_fund_kinds(medium, config):
    u = build_universe(medium, config)
    kinds = Counter(c.option.fund_kind for c in u.candidates[1:])
    assert kinds == {"debt": 7, "equity": 5, "variable": 5, "fund_of_funds": 4,
                     "participation": 4, "money_market": 3, "mixed": 2, "precious_metals": 1}


def test_fund_options(medium, config):
    u = build_universe(medium, config)
    aal = u.by_id["fund:AAL"].option
    assert aal.kind == "fund" and aal.entity == "AAL"
    assert aal.label == "ATA PORTFÖY PARA PİYASASI (TL) FONU"
    assert aal.fund_kind == "money_market"
    ids = [c.option.option_id for c in u.candidates[1:]]
    assert ids == sorted(ids)


def test_fx_tags(medium, config):
    u = build_universe(medium, config)
    assert {c.option.entity for c in u.candidates if c.option.fx} == {"AKE", "DBH"}


def test_fx_tag_uses_turkish_upper_case(medium, config):
    ents = dict(medium.entities)
    ents["AAL"] = EntityInfo(name="Ata Portföy Döviz Fonu", category="Para Piyasası Şemsiye Fonu",
                             source="tefas_web")
    assert build_universe(_with(medium, entities=ents), config).by_id["fund:AAL"].option.fx


def test_removed_funds_are_counted(medium, config):
    u = build_universe(medium, config)
    assert u.removed_serbest == ("AAS", "ABG")
    assert u.removed_no_entity == ("IGF",)
    assert u.removed_unknown_kind == ()


def test_unknown_umbrella_type_is_removed(medium, config):
    ents = dict(medium.entities)
    ents["AAL"] = dataclasses.replace(ents["AAL"], category="Yeni Şemsiye Fonu")
    u = build_universe(_with(medium, entities=ents), config)
    assert "fund:AAL" not in u.by_id
    assert u.removed_unknown_kind == ("AAL",)


def test_entity_info_of_an_excluded_source_counts_as_absent(medium, config):
    u = build_universe(_with(medium, excluded={"tefas_web"}), config)
    assert [c.option.kind for c in u.candidates] == ["deposit"]
    tefas_funds = {d.entity for d in medium.datapoints if d.source == "tefas"}
    assert set(u.removed_no_entity) == tefas_funds and len(tefas_funds) > 30


def test_excluded_manual_source_removes_the_deposit(medium, config):
    u = build_universe(_with(medium, excluded={"manual"}), config)
    assert "deposit:ing_turuncu" not in u.by_id
    assert u.candidates[0].option.kind == "fund"


def test_market_deposit_rate_is_a_benchmark_only(medium, config):
    u = build_universe(medium, config)
    assert u.market_rate.value == 43.82 and u.market_rate.source == "evds"
    assert all(c.option.entity != u.market_rate.entity for c in u.candidates)


# --- evidence lookup ----------------------------------------------------------------

def test_latest_row_is_used(medium, config):
    old = dp("fund_total_value", "AAL", 1.0, as_of=date(2026, 10, 1))
    new = dp("fund_total_value", "AAL", 2.0, as_of=date(2026, 10, 12))
    ev = _with(medium, add=[old, new])
    assert latest(ev, "fund_total_value", "AAL") == new
    assert build_universe(ev, config).by_id["fund:AAL"].values["fund_total_value"] == new


def test_excluded_source_is_ignored(medium, config):
    ev = _with(medium, excluded={"tefas"})
    assert latest(ev, "fund_total_value", "AAL") is None
    aal = build_universe(ev, config).by_id["fund:AAL"]
    assert "fund_total_value" not in aal.values
    assert "fund_return_1y" in aal.values


def test_out_of_range_latest_row_counts_as_missing(medium, config):
    good = dp("fund_risk_level", "AAL", 1.0, as_of=date(2026, 10, 1))
    bad = dp("fund_risk_level", "AAL", 9.0, as_of=date(2026, 10, 12),
             flags=("needs_check", "out_of_range"))
    ev = _with(medium, add=[good, bad])
    assert latest(ev, "fund_risk_level", "AAL") is None
    u = build_universe(ev, config)
    assert "fund_risk_level" not in u.by_id["fund:AAL"].values
    assert bad.id in u.out_of_range


def test_missing_latest_row_counts_as_missing(medium, config):
    ev = _with(medium, add=[dp("fund_total_value", "AAL", None, as_of=date(2026, 10, 12))])
    assert latest(ev, "fund_total_value", "AAL") is None


def test_out_of_range_rows_of_the_evidence_are_listed(medium, config):
    u = build_universe(medium, config)
    assert u.out_of_range == ("Ea1b6ffd1",)     # IGF risk level 0.0
    assert build_universe(_with(medium, excluded={"tefas_web"}), config).out_of_range == ()


def test_fund_without_a_risk_level_stays_in_the_universe(medium, config):
    u = build_universe(medium, config)
    adp = u.by_id["fund:ADP"]
    assert "fund_risk_level" not in adp.values
    assert "fund_return_3y" in adp.values
