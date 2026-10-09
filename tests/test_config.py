import copy
from pathlib import Path

import pytest

from rmprep.config import (
    ConfigError,
    EvdsSource,
    ManualSource,
    TefasSource,
    load_config,
    load_raw,
    normalize_header,
    parse_config,
)

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "sources.yaml"


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
    assert names == ["evds", "tefas_web", "manual"]


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
    raw["sources"]["manual"]["allowed_quantities"].append("gold_price")
    assert "allowed_quantities[2]" in _error(raw)
