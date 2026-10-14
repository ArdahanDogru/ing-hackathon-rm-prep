"""E4: each error-analysis case of src/rmprep/eval/scenarios/regression.yaml
passes after its fix (fixture evidence plus the rows the case needs), and the
D14 case fails without its fix."""

from datetime import date

import pytest
import yaml

from rmprep import decision
from rmprep.contracts import DataPoint, Flag
from rmprep.eval.checks import FAIL, NA, PASS, run_checks
from rmprep.eval.scenario import SCENARIO_DIR, load_scenarios, packaged_scenario_files
from rmprep.narrator.config import load_config as load_narrator_config
from tests.eval.conftest import PROJECT, SNAP, T0, FakeNarrator, fixture_evidence
from tests.eval.test_runner import runner

NCFG = load_narrator_config(PROJECT / "config" / "narrator.yaml")
SUITE = {s.id: s for s in load_scenarios(packaged_scenario_files())}
CASES = [s for s in SUITE.values() if s.group == "regression"]
FUNDS = sorted({d.entity for d in fixture_evidence().datapoints if d.source == "tefas"})
LISTABLE = [f for f in FUNDS                     # in the universe (Serbest funds are not)
            if not fixture_evidence().entities[f].category.startswith("Serbest")]


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
    """FUNDS[2] with no risk row (its risk is estimated), one unflagged 1-year
    return (a usable history, so D15 short_history keeps it) and needs_check
    tefas_detail rows: the tefas_detail rows are its weakest rows, as on the
    real snapshot (P05: ZPO, ZND, ZTV). Keeping its needs_check tefas_web
    returns would hide the D14 case (the confidence could not rise)."""
    f = FUNDS[2]
    dropped_rows.append(lambda d: d.entity == f and d.source == "tefas_web")
    extra_rows.append(row("fund_return_1y", f, 40.0, source="tefas_web"))
    extra_rows += [row("fund_sell_valor_days", x, 0.0, flags=(Flag.NEEDS_CHECK,)) for x in FUNDS]
    return f


def test_d14_confidence_does_not_rise_without_tefas_detail(root, dropped_rows, extra_rows):
    f = _d14_rows(dropped_rows, extra_rows)
    # only D14 here: the test rows have no TÜFE, so D24 (real_return_missing) would also apply
    cfg = root / "config" / "decision.yaml"
    raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    raw["confidence"].pop("real_return_missing", None)
    cfg.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
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


def set_d15(root, on: bool):
    """Turn the D15 config on or off in the test root (independent of the
    project config, which may or may not have it yet)."""
    cfg = root / "config" / "decision.yaml"
    raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    raw.pop("short_history", None)
    raw["texts"]["constraint"].pop("short_history", None)
    raw["texts"]["data_quality"].pop("removed_no_data", None)
    if on:
        raw["short_history"] = {"min_period": "3m", "allow_appetite": 1.0}
        raw["texts"]["constraint"]["short_history"] = "Yeterli geçmiş yok (yalnızca 1 aylık getiri)."
        raw["texts"]["data_quality"]["removed_no_data"] = (
            "{count} fon, kullanılabilir veri satırı olmadığı için çıkarıldı.")
    cfg.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _d15_rows(dropped_rows, extra_rows):
    """A listable fund (not the D14 one) keeps only its 1-month return (as VKR,
    ZPO, ZTV on the real snapshot without tefas_detail); the other funds get
    tefas_detail rows, so the scenarios can exclude that source."""
    f = next(x for x in LISTABLE if x != FUNDS[2])
    dropped_rows.append(lambda d: d.entity == f and d.quantity != "fund_return_1m")
    extra_rows += [row("fund_sell_valor_days", x, 1.0) for x in FUNDS if x != f]
    return f


def test_d15_p05_rejects_a_short_history_fund_and_lists_none_without_evidence(
        root, dropped_rows, extra_rows):
    f = _d15_rows(dropped_rows, extra_rows)
    set_d15(root, True)
    sc, sr = run_case(root, "reg-d15-short-history-p05")
    assert_passes(sc)
    rejected = {x.option.entity: [c.rule_id for c in x.failed] for x in sr.runs[0].result.rejected}
    assert "short_history" in rejected[f]


def test_d15_an_agresif_persona_keeps_it_with_the_penalty(root, dropped_rows, extra_rows):
    f = _d15_rows(dropped_rows, extra_rows)
    set_d15(root, True)
    sc, sr = run_case(root, "reg-d15-short-history-p03")
    assert_passes(sc)
    o = next(o for o in sr.runs[0].result.options if o.option.entity == f)
    assert "penalty:track_record" in o.score_parts and o.evidence_ids


def test_d15_case_fails_without_its_fix(root, dropped_rows, extra_rows):
    _d15_rows(dropped_rows, extra_rows)
    set_d15(root, False)
    sc, _ = run_case(root, "reg-d15-short-history-p05")
    sens = next(c for c in sc.scenario_checks if c.check == "sensitivity")
    assert sens.status == FAIL and "short_history" in " ".join(sens.details)


@pytest.mark.parametrize("case_id", ["reg-d19-p02-diverse", "reg-d19-p04-diverse",
                                     "reg-d19-p01-unchanged"])
def test_d19_diverse_recommendations(root, case_id):
    sc, sr = run_case(root, case_id)
    assert_passes(sc)
    c = next(c for c in sc.runs[0] if c.check == "diverse_recommendations")
    assert c.status == (NA if case_id.endswith("unchanged") else PASS), c


def test_d19_case_fails_with_three_cash_like_picks(root):
    import dataclasses
    _, sr = run_case(root, "reg-d19-p02-diverse")
    run = sr.runs[0]
    cash = tuple(o.option.option_id for o in run.result.options
                 if o.option.asset_class == "nakit_benzeri" and o.option.kind != "deposit")[:3]
    assert len(cash) == 3
    sr.runs[0] = dataclasses.replace(run, result=dataclasses.replace(run.result, recommended=cash))
    dcfg = decision.load_config(root / "config" / "decision.yaml").raw
    [sc] = run_checks([sr], dcfg, NCFG.forbidden_phrases, NCFG)
    failed = {c.check for c in sc.all() if c.status == FAIL}
    assert {"diverse_recommendations", "sensitivity"} <= failed
