"""Model allocation bands (docs/decision.md section 11, D20; contract v1.8)."""

import copy
import dataclasses

import pytest

from rmprep.decision.config import ConfigError, parse_config
from rmprep.decision.display import display_facts
from rmprep.decision.engine import decide
from rmprep.decision.report import render
from tests.decision.conftest import T0, d9_rows, load_persona, make_evidence, market_row
from tests.decision.test_diverse import FUNDS

ATA = "Ata Yatırım, 28.04.2026"
ALLOCATION = {
    "classes": ["nakit_benzeri", "borclanma", "hisse", "altin_doviz", "dengeli"],
    "profiles": {
        "Muhafazakâr": {"source": ATA, "inferred": False, "bands": {
            "nakit_benzeri": [10, 20], "borclanma": [60, 70], "hisse": [10, 20],
            "altin_doviz": [5, 10]}},
        "Temkinli": {"source": "çıkarım", "inferred": True, "bands": {
            "nakit_benzeri": [5, 20], "borclanma": [40, 60], "hisse": [20, 40],
            "altin_doviz": [5, 15]}},
        "Dengeli": {"source": ATA, "inferred": False, "bands": {
            "nakit_benzeri": [5, 10], "borclanma": [30, 40], "hisse": [40, 50],
            "altin_doviz": [10, 15]}},
        "Agresif": {"source": ATA, "inferred": False, "bands": {
            "nakit_benzeri": [0, 5], "borclanma": [5, 10], "hisse": [70, 85],
            "altin_doviz": [5, 10]}},
    },
    "note_texts": {
        "ceiling": "Risk tavanı nedeniyle uygun fon yok.",
        "none": "Bu sınıfta puanlanan seçenek yok.",
        "negative_real": "Son 1 yıl reel {figure}: önerilmiyor.",
    },
    "holding_hints": {
        "mevduat ağırlıklı": "Dosyaya göre varlık TL mevduat ağırlıklı: nakit benzeri bandı "
                             "aşılıyor olabilir.",
    },
    "holding_confirm": "Mevcut portföy dağılımını sorun.",
}
HINT = ALLOCATION["holding_hints"]["mevduat ağırlıklı"]


@pytest.fixture
def al_raw(d19_raw):
    d19_raw["allocation"] = copy.deepcopy(ALLOCATION)
    return d19_raw


@pytest.fixture
def al_config(al_raw):
    return parse_config(al_raw)


def _ev(funds=FUNDS):
    return make_evidence(funds, time_deposit=35.0, extra=d9_rows() + [market_row()])


def _decide(cfg, pid, funds=FUNDS, persona=None):
    return decide(_ev(funds), persona or load_persona(pid), cfg, created_at=T0)


def _band(r, cls):
    return next(b for b in r.allocation if b.asset_class == cls)


# --- bands --------------------------------------------------------------------------------------

def test_bands_of_the_profile_in_class_order(al_config):
    r = _decide(al_config, "P01")                        # Muhafazakâr
    assert [b.asset_class for b in r.allocation] == ALLOCATION["classes"]
    b = _band(r, "borclanma")
    assert (b.low, b.high, b.source, b.inferred) == (60, 70, ATA, False)


def test_dengeli_class_has_no_band(al_config):
    b = _band(_decide(al_config, "P04"), "dengeli")
    assert b.low is None and b.high is None


def test_temkinli_band_is_inferred(al_config):
    b = _band(_decide(al_config, "P05"), "hisse")
    assert (b.low, b.high, b.source, b.inferred) == (20, 40, "çıkarım", True)


# --- best option per class ---------------------------------------------------------------------

@pytest.mark.parametrize("pid", ["P01", "P02", "P03", "P04", "P05"])
def test_best_option_is_the_first_of_its_class_in_score_order(al_config, pid):
    r = _decide(al_config, pid)
    ranked = sorted((o for o in r.options if o.option.kind != "deposit"),
                    key=lambda o: (-o.score, o.option.option_id))
    for b in r.allocation:
        first = next((o.option.option_id for o in ranked
                      if o.option.asset_class == b.asset_class), None)
        assert b.option_id == first


def test_the_deposit_baseline_is_not_a_class_pick(al_config):
    r = _decide(al_config, "P01")
    assert all(b.option_id != "deposit:ing_turuncu" for b in r.allocation)


# --- notes ---------------------------------------------------------------------------------------

def test_ceiling_note_for_p01_hisse(al_config):
    b = _band(_decide(al_config, "P01"), "hisse")          # EQF risk 5 > ceiling 2
    assert b.option_id is None and b.note == "ceiling"


def test_none_note_without_any_option(al_config):
    funds = {k: FUNDS[k] for k in ("MMF", "UVD", "MIX")}   # no equity fund at all
    b = _band(_decide(al_config, "P03", funds=funds), "hisse")
    assert b.option_id is None and b.note == "none"


def test_negative_real_keeps_the_option(al_config):
    r = _decide(al_config, "P02")                          # GLD 1y 20 % -> real < 0
    b = _band(r, "altin_doviz")
    assert b.option_id == "fund:GLD" and b.note == "negative_real"
    facts = display_facts(r, _ev(), al_config)
    assert facts["fund:GLD"].real_1y.value < 0


def test_no_note_for_a_good_best_option(al_config):
    b = _band(_decide(al_config, "P02"), "nakit_benzeri")
    assert b.option_id is not None and b.note == ""


# --- holding hints ----------------------------------------------------------------------------------

def test_p01_gets_the_deposit_hint_and_the_to_confirm_item(al_config):
    r = _decide(al_config, "P01")                          # durum "... TL mevduat ağırlıklı"
    assert r.allocation_notes == (HINT,)
    assert r.to_confirm[-1] == "Mevcut portföy dağılımını sorun."


def test_p02_gets_no_hint(al_config):
    r = _decide(al_config, "P02")
    assert r.allocation_notes == ()
    assert "Mevcut portföy dağılımını sorun." not in r.to_confirm


def test_hint_matches_turkish_case(al_config):
    p = dataclasses.replace(load_persona("P02"), durum="VARLIĞI MEVDUAT AĞIRLIKLI")
    assert _decide(al_config, "P02", persona=p).allocation_notes == (HINT,)


# --- without config, blocked, report -------------------------------------------------------------------

def test_without_config_nothing_changes(d19_config):
    r = _decide(d19_config, "P01")
    assert r.allocation == () and r.allocation_notes == ()
    assert "Mevcut portföy dağılımını sorun." not in r.to_confirm


def test_blocked_result_has_no_bands(al_config):
    p = dataclasses.replace(load_persona("P01"), risk_profili="?")
    r = _decide(al_config, "P01", persona=p)
    assert r.allocation == ()


def test_report_shows_the_bands(al_config):
    text = render(_decide(al_config, "P02"))
    assert "allocation:" in text
    assert "borclanma 30-40 %" in text and "dengeli -" in text
    assert "fund:GLD (negative_real)" in text
    assert "çıkarım" not in text                           # P02 is Dengeli: Ata source
    assert render(_decide(al_config, "P05")).count("*") >= 1   # inferred bands are marked


@pytest.mark.parametrize("edit,match", [
    (lambda a: a["profiles"].pop("Temkinli"), "allocation.profiles"),
    (lambda a: a["profiles"]["Dengeli"]["bands"].update(hisse=[50, 40]), "allocation.profiles"),
    (lambda a: a["profiles"]["Dengeli"]["bands"].update(hisse=[40, 120]), "allocation.profiles"),
    (lambda a: a["profiles"]["Dengeli"]["bands"].update(gold=[1, 2]), "allocation.profiles"),
    (lambda a: a["classes"].append("kripto"), "allocation.classes"),
    (lambda a: a["note_texts"].pop("ceiling"), "allocation.note_texts"),
    (lambda a: a.pop("holding_confirm"), "allocation"),
])
def test_bad_allocation_config_is_an_error(al_raw, edit, match):
    edit(al_raw["allocation"])
    with pytest.raises(ConfigError, match=match):
        parse_config(al_raw)


def test_allocation_needs_asset_classes(raw):
    raw["allocation"] = copy.deepcopy(ALLOCATION)
    with pytest.raises(ConfigError, match="allocation"):
        parse_config(raw)


def test_an_estimated_risk_above_the_ceiling_is_not_a_class_pick(al_config):
    # a foreign equity fund without a risk row: listed (risk_unknown penalty, estimate 7),
    # but for P01 (ceiling 2) it must not be the best hisse option
    funds = {**FUNDS, "TMG": dict(kind="equity", name="J PORTFÖY YABANCI HİSSE SENEDİ FONU",
                                  returns={"1y": 30.0, "3y": 100.0}, **{
                                      k: v for k, v in FUNDS["EQF"].items()
                                      if k not in ("risk", "returns", "name", "kind")})}
    r = _decide(al_config, "P01", funds=funds)
    assert "fund:TMG" in {o.option.option_id for o in r.options}
    b = _band(r, "hisse")
    assert b.option_id is None and b.note == "ceiling"


def test_an_estimated_risk_within_the_ceiling_can_be_a_class_pick(al_config):
    funds = {**FUNDS, "TMG": dict(kind="equity", name="J PORTFÖY YABANCI HİSSE SENEDİ FONU",
                                  returns={"1y": 90.0, "3y": 400.0}, **{
                                      k: v for k, v in FUNDS["EQF"].items()
                                      if k not in ("risk", "returns", "name", "kind")})}
    r = _decide(al_config, "P03", funds=funds)            # Agresif: ceiling 7
    assert _band(r, "hisse").option_id == "fund:TMG"
