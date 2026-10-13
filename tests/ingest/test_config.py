import copy
from pathlib import Path

import pytest

from tests.ingest.conftest import CPI_ANNUAL_ENTITY, add_cpi_annual
from rmprep.ingest.config import (
    AnnualChange,
    ConfigError,
    EvdsSource,
    ManualSource,
    TefasSource,
    load_config,
    load_raw,
    normalize_header,
    parse_config,
)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "sources.yaml"


@pytest.fixture
def raw(config_raw):
    return config_raw


def _error(raw) -> str:
    with pytest.raises(ConfigError) as exc:
        parse_config(raw)
    return str(exc.value)


# --- shipped config ---------------------------------------------------------------

def test_shipped_config_is_valid():
    cfg = load_config(CONFIG_PATH)
    assert isinstance(cfg.sources["evds"], EvdsSource)
    assert isinstance(cfg.sources["tefas"], TefasSource)
    assert isinstance(cfg.sources["manual"], ManualSource)
    assert all(s.tos_note for s in cfg.sources.values())


def test_placeholder_series_detected(raw):
    cfg = parse_config(raw)
    placeholders = {s.code for s in cfg.sources["evds"].series if s.is_placeholder}
    assert placeholders == {"VERIFY_POLICY_RATE", "VERIFY_DEPOSIT_RATE_TRY"}


def test_parse_is_deterministic(raw):
    assert parse_config(copy.deepcopy(raw)) == parse_config(copy.deepcopy(raw))


def test_tefas_source_has_no_url_to_fetch(raw):
    # No-scraping rule: the TEFAS adapter has no base_url, and the loader rejects one.
    raw["sources"]["tefas"]["base_url"] = "https://www.tefas.gov.tr/api"
    assert "unknown key(s) ['base_url']" in _error(raw)


# --- ToS and common source fields -----------------------------------------------------

def test_missing_tos_note_rejected(raw):
    del raw["sources"]["evds"]["tos_note"]
    assert "sources.evds" in _error(raw) and "tos_note" in _error(raw)


def test_blank_tos_note_rejected(raw):
    raw["sources"]["manual"]["tos_note"] = "   "
    assert "sources.manual.tos_note" in _error(raw)


def test_unknown_adapter_rejected(raw):
    raw["sources"]["evds"]["adapter"] = "scraper"
    assert "sources.evds.adapter" in _error(raw)


def test_unknown_key_rejected(raw):
    raw["sources"]["evds"]["serie"] = []
    assert "unknown key(s) ['serie']" in _error(raw)


def test_on_failure_default_is_previous(raw):
    del raw["sources"]["evds"]["on_failure"]
    assert parse_config(raw).sources["evds"].on_failure == "previous"


def test_on_failure_exclude_accepted(raw):
    raw["sources"]["tefas"]["on_failure"] = "exclude"
    assert parse_config(raw).sources["tefas"].on_failure == "exclude"


def test_bad_on_failure_rejected(raw):
    raw["sources"]["evds"]["on_failure"] = "skip"
    assert "on_failure" in _error(raw)


def test_disabled_source_not_in_enabled_list(raw):
    raw["sources"]["tefas"]["enabled"] = False
    names = [s.name for s in parse_config(raw).enabled_sources()]
    assert names == [n for n in raw["sources"] if n != "tefas"]


def test_source_name_with_separator_rejected(raw):
    raw["sources"]["ev|ds"] = raw["sources"].pop("evds")
    assert "must match" in _error(raw)


def test_wrong_version_rejected(raw):
    raw["version"] = 2
    assert "version" in _error(raw)


# --- quantities ---------------------------------------------------------------------

def test_min_greater_than_max_rejected(raw):
    raw["quantities"]["usd_try"]["min"] = 1000
    assert "quantities.usd_try" in _error(raw)


def test_negative_tolerance_rejected(raw):
    raw["quantities"]["usd_try"]["conflict_tolerance"] = -0.1
    assert "conflict_tolerance" in _error(raw)


def test_non_positive_max_age_rejected(raw):
    raw["quantities"]["usd_try"]["max_age_days"] = 0
    assert "max_age_days" in _error(raw)


# --- EVDS series ----------------------------------------------------------------------

def test_series_with_undeclared_quantity_rejected(raw):
    raw["sources"]["evds"]["series"][0]["quantity"] = "gold_price"
    assert "unknown quantity 'gold_price'" in _error(raw)


def test_series_without_verified_rejected(raw):
    del raw["sources"]["evds"]["series"][0]["verified"]
    assert "verified" in _error(raw)


def test_placeholder_cannot_be_verified(raw):
    raw["sources"]["evds"]["series"][2]["verified"] = True
    assert "cannot be verified" in _error(raw)


def test_duplicate_series_code_rejected(raw):
    series = raw["sources"]["evds"]["series"]
    series.append(dict(series[0]))
    assert "duplicate series code" in _error(raw)


# --- EVDS series options of I5 (lookback_days, annual_change) ---------------------------

def test_series_options_default_to_none(raw):
    s = parse_config(raw).sources["evds"].series[0]
    assert s.lookback_days is None and s.annual_change is None


def test_series_lookback_and_annual_change_parsed(raw):
    s = parse_config(add_cpi_annual(raw)).sources["evds"].series[-1]
    assert s.lookback_days == 400
    assert s.annual_change == AnnualChange(quantity="cpi_annual", entity=CPI_ANNUAL_ENTITY)


@pytest.mark.parametrize("bad", [0, -5, 1.5, "400", True])
def test_series_bad_lookback_rejected(raw, bad):
    add_cpi_annual(raw)["sources"]["evds"]["series"][-1]["lookback_days"] = bad
    assert "sources.evds.series[4].lookback_days: must be a positive integer" in _error(raw)


def test_annual_change_unknown_quantity_rejected(raw):
    add_cpi_annual(raw)["sources"]["evds"]["series"][-1]["annual_change"]["quantity"] = "cpi_yoy"
    assert "sources.evds.series[4].annual_change.quantity: unknown quantity 'cpi_yoy'" \
        in _error(raw)


def test_annual_change_needs_quantity_and_entity(raw):
    del add_cpi_annual(raw)["sources"]["evds"]["series"][-1]["annual_change"]["entity"]
    assert "sources.evds.series[4].annual_change: missing key(s) ['entity']" in _error(raw)


def test_annual_change_unknown_key_rejected(raw):
    add_cpi_annual(raw)["sources"]["evds"]["series"][-1]["annual_change"]["unit"] = "pct"
    assert "sources.evds.series[4].annual_change: unknown key(s) ['unit']" in _error(raw)


def test_annual_change_must_be_mapping(raw):
    add_cpi_annual(raw)["sources"]["evds"]["series"][-1]["annual_change"] = "cpi_annual"
    assert "sources.evds.series[4].annual_change: must be a mapping" in _error(raw)


def test_annual_change_only_for_monthly_series(raw):
    add_cpi_annual(raw)["sources"]["evds"]["series"][-1]["frequency"] = "daily"
    assert "sources.evds.series[4].annual_change: needs frequency monthly" in _error(raw)


# --- TEFAS columns ----------------------------------------------------------------------

def test_alias_used_by_two_columns_rejected(raw):
    raw["sources"]["tefas"]["column_aliases"]["price"].append("TARİH")
    assert "also used by 'date'" in _error(raw)


def test_value_column_without_alias_rejected(raw):
    raw["sources"]["tefas"]["value_columns"]["yield"] = "fund_price"
    assert "value_columns.yield" in _error(raw)


def test_value_column_with_unknown_quantity_rejected(raw):
    raw["sources"]["tefas"]["value_columns"]["price"] = "nav"
    assert "unknown quantity 'nav'" in _error(raw)


@pytest.mark.parametrize("header", ["Fon Adı", "FON ADI", "fon adi", "  Fon   Adı "])
def test_normalize_header_folds_turkish_and_case(header):
    assert normalize_header(header) == "fon adi"


@pytest.mark.parametrize("a,b", [("FİYAT", "Fiyat"), ("FIYAT", "fiyat"),
                                 ("KİŞİ SAYISI", "Kişi Sayısı")])
def test_normalize_header_pairs(a, b):
    assert normalize_header(a) == normalize_header(b)


# --- manual ------------------------------------------------------------------------------

def test_manual_unknown_allowed_quantity_rejected(raw):
    allowed = raw["sources"]["manual"]["allowed_quantities"]
    allowed.append("gold_price")
    assert f"allowed_quantities[{len(allowed) - 1}]" in _error(raw)
