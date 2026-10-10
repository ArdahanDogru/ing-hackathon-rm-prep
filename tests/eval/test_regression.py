"""E4: each error-analysis case of src/rmprep/eval/scenarios/regression.yaml
passes after its fix (fixture evidence plus the rows the case needs), and the
D14 case fails without its fix."""

from datetime import date

import pytest
import yaml

from rmprep import decision
from rmprep.contracts import DataPoint, Flag
from rmprep.eval.checks import FAIL, PASS, run_checks
from rmprep.eval.scenario import SCENARIO_DIR, load_scenarios, packaged_scenario_files
from rmprep.narrator.config import load_config as load_narrator_config
from tests.eval.conftest import PROJECT, SNAP, T0, FakeNarrator, fixture_evidence
from tests.eval.test_runner import runner

NCFG = load_narrator_config(PROJECT / "config" / "narrator.yaml")
SUITE = {s.id: s for s in load_scenarios(packaged_scenario_files())}
CASES = [s for s in SUITE.values() if s.group == "regression"]
FUNDS = sorted({d.entity for d in fixture_evidence().datapoints if d.source == "tefas"})


def row(quantity, entity, value, source="tefas_detail", flags=()):
    return DataPoint.create(quantity=quantity, entity=entity, value=value, unit="x",
                            as_of=date(2026, 10, 9), source=source, source_url="u",
                            fetched_at=T0, snapshot_id=SNAP, raw_ref="r", flags=flags)


def run_case(root, case_id, narrator=None):
    """The case and its compare scenario; returns (checks of the case, runs)."""
    case = SUITE[case_id]
    scenarios = [SUITE[case.compare_to]] if case.compare_to else []
    runs = runner(root, narrator=narrator or FakeNarrator()).run(scenarios + [case])
    dcfg = decision.load_config(root / "config" / "decision.yaml").raw
    checks = run_checks(runs, dcfg, NCFG.forbidden_phrases, NCFG)
    return checks[-1], runs[-1]


def assert_passes(sc):
    failed = [(c.check, c.details) for c in sc.all() if c.status == FAIL]
    assert failed == [], failed
    sens = next(c for c in sc.scenario_checks if c.check == "sensitivity")
    if sc.scenario.expect:
        assert sens.status == PASS, sens      # decided, not n/a


def test_every_case_has_a_description_with_before_and_after():
    assert {s.id for s in CASES} >= {
        "reg-d9-deposit-baseline", "reg-d12-not-buyable-p01", "reg-d13-fx-limit-p02",
        "reg-d13-liquidity-need-p05", "reg-i3-tefas-detail-source", "reg-n5-garanti-fund-name",
        "reg-d14-liquidity-proxy-confidence"}
    for s in CASES:
        assert s.needs and "fter" in s.description and (s.expect or s.compare_to), s.id
    raw = yaml.safe_load((SCENARIO_DIR / "regression.yaml").read_text(encoding="utf-8"))
    assert len(raw["scenarios"]) == len(CASES)


def d9_rows():
    """CPI and stopaj rows (manual; the fixture predates D9)."""
    stopaj = ["TL vadesiz mevduat ve günlük hesap (Turuncu Hesap türü)",
              "TL vadeli mevduat, 6 aya kadar vadeli", "Yatırım fonu, para piyasası fonu",
              "Yatırım fonu, diğer fonlar (değişken, borçlanma araçları, fon sepeti)"]
    return ([row("cpi_annual", "TÜFE yıllık değişim (TÜİK)", 29.73, "manual",
                 (Flag.MANUAL_ENTRY,))]
            + [row("withholding_tax_rate", e, 17.5, "manual", (Flag.MANUAL_ENTRY,)) for e in stopaj])


def test_d9_deposit_baseline_below_the_best_fund(root, extra_rows):
    extra_rows += d9_rows()
    sc, sr = run_case(root, "reg-d9-deposit-baseline")
    assert_passes(sc)
    assert any(k == "penalty:real_loss" for k in sr.runs[0].result.options[0].score_parts)


def test_d9_case_fails_on_nominal_returns(root):
    sc, _ = run_case(root, "reg-d9-deposit-baseline")      # no CPI row: nominal net returns
    sens = next(c for c in sc.scenario_checks if c.check == "sensitivity")
    assert sens.status == FAIL and "baseline_below_best_fund" in sens.details[0]


@pytest.mark.parametrize("case_id", ["reg-d12-not-buyable-p01", "reg-d12-not-buyable-p03"])
def test_d12_closed_funds_are_rejected(root, extra_rows, case_id):
    extra_rows += [row("fund_buyable", f, 0.0 if f == FUNDS[0] else 1.0) for f in FUNDS]
    sc, sr = run_case(root, case_id)
    assert_passes(sc)
    assert f"fund:{FUNDS[0]}" in {x.option.option_id for x in sr.runs[0].result.rejected}


def test_d13_fx_limit(root):
    assert_passes(run_case(root, "reg-d13-fx-limit-p02")[0])


def test_d13_liquidity_need(root, extra_rows):
    listed = next(o.option.entity for o in runner(root).run([SUITE["base-p05"]])[0]
                  .runs[0].result.options if o.option.kind == "fund")
    extra_rows += [row("fund_sell_valor_days", f, 5.0 if f == listed else 1.0) for f in FUNDS]
    sc, sr = run_case(root, "reg-d13-liquidity-need-p05")
    assert_passes(sc)
    assert f"fund:{listed}" in {x.option.option_id for x in sr.runs[0].result.rejected}


def test_i3_tefas_detail_rows_and_no_failed_source(root, extra_rows):
    extra_rows += [row("fund_sell_valor_days", f, 1.0) for f in FUNDS]
    assert_passes(run_case(root, "reg-i3-tefas-detail-source")[0])


class GarantiNarrator(FakeNarrator):
    """Names every selected option by its label in a sentence of its own."""

    def __init__(self):
        super().__init__(text="Öneri: {label}.")


def test_n5_a_garanti_fund_name_is_not_a_forbidden_phrase(root, renamed):
    clean = runner(root).run([SUITE["reg-n5-garanti-fund-name"]])[0].runs[0]
    head = clean.approved.rm_selected[0]
    renamed[head.removeprefix("fund:")] = "GARANTİ PORTFÖY PARA PİYASASI FONU"
    sc, sr = run_case(root, "reg-n5-garanti-fund-name", narrator=GarantiNarrator())
    sentences = sr.runs[0].narratives["TR"].sections[0].sentences
    assert any("GARANTİ PORTFÖY" in s.text for s in sentences)
    assert_passes(sc)


def _d14_rows(dropped_rows, extra_rows):
    """FUNDS[2] without tefas_web rows (its risk is estimated) and with
    needs_check tefas_detail rows, as on the real snapshot (P05: ZPO, ZND, ZTV)."""
    f = FUNDS[2]
    dropped_rows.append(lambda d: d.entity == f and d.source == "tefas_web")
    extra_rows += [row("fund_sell_valor_days", x, 0.0, flags=(Flag.NEEDS_CHECK,)) for x in FUNDS]
    return f


def test_d14_confidence_does_not_rise_without_tefas_detail(root, dropped_rows, extra_rows):
    f = _d14_rows(dropped_rows, extra_rows)
    sc, sr = run_case(root, "reg-d14-liquidity-proxy-confidence")
    assert_passes(sc)
    c = next(c for c in sc.runs[0] if c.check == "missing_data_shown")
    assert c.status == PASS
    conf = {o.option.entity: o.confidence for o in sr.runs[0].result.options}
    assert conf[f] == pytest.approx(0.7 * 0.8)


def test_d14_case_fails_without_its_fix(root, dropped_rows, extra_rows):
    _d14_rows(dropped_rows, extra_rows)
    cfg = root / "config" / "decision.yaml"
    raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    raw["confidence"].pop("liquidity_proxy")
    cfg.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    sc, _ = run_case(root, "reg-d14-liquidity-proxy-confidence")
    c = next(c for c in sc.runs[0] if c.check == "missing_data_shown")
    assert c.status == FAIL and "confidence" in c.details[0]
