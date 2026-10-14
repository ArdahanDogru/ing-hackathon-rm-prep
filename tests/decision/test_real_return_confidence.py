"""D24: an option whose real return cannot be computed (no TÜFE row, or no stopaj
row for its product type) gets a lower confidence (docs/decision.md section 14)."""

import copy

import pytest

from rmprep.decision.confidence import confidence
from rmprep.decision.config import ConfigError, parse_config
from tests.decision.test_real_return import _features


@pytest.fixture
def d24_config(d9_raw):
    raw = copy.deepcopy(d9_raw)              # d9_config uses the same d9_raw
    raw["confidence"]["real_return_missing"] = 0.8
    return parse_config(raw)


def test_no_cpi_lowers_every_option(d24_config, d9_config):
    feats = _features(d24_config, cpi=None)
    assert feats
    for f in feats.values():
        assert confidence(f, d24_config) == pytest.approx(0.8 * confidence(f, d9_config))


def test_missing_stopaj_lowers_only_the_options_that_need_it(d24_config, d9_config):
    feats = _features(d24_config, fund_default=None)
    hit = [f for f in feats.values() if f.stopaj_missing]
    rest = [f for f in feats.values() if not f.stopaj_missing]
    assert hit and rest
    for f in hit:
        assert confidence(f, d24_config) == pytest.approx(0.8 * confidence(f, d9_config))
    for f in rest:
        assert confidence(f, d24_config) == pytest.approx(confidence(f, d9_config))


def test_all_inputs_present_no_change(d24_config, d9_config):
    for f in _features(d24_config).values():
        assert confidence(f, d24_config) == pytest.approx(confidence(f, d9_config))


def test_without_real_return_config_no_factor(raw):
    raw["confidence"]["real_return_missing"] = 0.8      # raw has no real_return section
    cfg = parse_config(raw)
    plain = parse_config({**raw, "confidence": {k: v for k, v in raw["confidence"].items()
                                                if k != "real_return_missing"}})
    for f in _features(cfg, cpi=None).values():
        assert confidence(f, cfg) == pytest.approx(confidence(f, plain))


def test_the_factor_is_optional(d9_config):
    assert "real_return_missing" not in d9_config.raw["confidence"]


@pytest.mark.parametrize("value", [-0.1, 1.5, "x"])
def test_bad_factor_is_an_error(d9_raw, value):
    d9_raw["confidence"]["real_return_missing"] = value
    with pytest.raises(ConfigError):
        parse_config(d9_raw)
