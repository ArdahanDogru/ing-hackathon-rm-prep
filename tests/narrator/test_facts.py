import json
from datetime import date

import pytest

from rmprep.narrator.facts import build_facts
from tests.narrator.conftest import approved, evidence, p02, p03, result


def test_only_an_approved_result_has_facts():
    with pytest.raises(ValueError, match="approved"):
        build_facts(result("decision_p02_ready"), evidence())


def test_persona_context_and_rm_notes():
    f = build_facts(p02(), evidence())
    assert f.run_id == "R02examp1e0"
    assert f.client["profil"] == p02().persona.profil
    assert f.client["yas"] == 48
    assert f.client["acik_kisitlar"] == ("döviz maruziyetini gerekçesiz artırmama",)
    assert set(f.client) == {"profil", "yas", "risk_profili", "durum", "yatirim_amaci",
                             "yatirim_ufku", "oncelikler", "acik_kisitlar", "rm_notu"}
    assert f.rm_note == "Şirket nakdini ayrıca konuşalım."
    assert f.selected[0].rm_note == "Vade ufkuna uygun."


def test_baseline_and_selected_in_display_order():
    f = build_facts(approved("decision_p02_ready", ("fund:AAL", "fund:BBF")), evidence())
    assert f.baseline.option_id == "deposit:ing_turuncu"
    assert [o.option_id for o in f.selected] == ["fund:BBF", "fund:AAL"]


def test_option_facts_hold_reasons_and_key_numbers():
    bbf = build_facts(p02(), evidence()).selected[0]
    assert bbf.label.startswith("PARDUS")
    assert bbf.kind == "debt"
    assert bbf.reasons[0] == ("return", 0.2, "(örnek) return")    # largest part first
    nums = {n.quantity: n for n in bbf.numbers}
    assert nums["fund_return_1y"].value == pytest.approx(52.5143)
    assert nums["fund_return_1y"].evidence_id == "Ebb80cd5d"
    assert nums["fund_return_1y"].as_of == date(2026, 10, 9)
    assert nums["fund_risk_level"].value == 2.0
    assert set(bbf.evidence_ids) == {"Ebb80cd5d", "E571475ce"}


def test_groups_name_only_the_groups_of_selected_options():
    f = build_facts(p02(), evidence())
    groups = {g.key: g for g in f.groups}
    assert set(groups) == {"debt", "money_market"}          # ABU (variable) not selected
    assert groups["debt"].selected == ("fund:BBF",)
    assert groups["debt"].alternatives == ("fund:AKE",)
    assert groups["money_market"].alternatives == ()
    assert [o.option_id for o in f.alternatives] == ["fund:AKE"]


def test_rejected_options_only_as_count_and_rule():
    r = p02()
    f = build_facts(r, evidence())
    assert f.rejected_count == 1
    assert f.rejected_rules == {"risk_ceiling": 1}
    text = json.dumps(f.to_dict(), ensure_ascii=False)
    for rej in r.rejected:
        assert rej.option.option_id not in text
        assert rej.option.label not in text


def test_warnings_only_about_named_options_or_the_whole_result():
    f = build_facts(p02(), evidence())
    assert [w.code for w in f.warnings] == ["deposit_vs_market", "fx_exposure",
                                            "no_fx_deposit_data"]
    # without BBF the debt group (and AKE) is not named, so its FX warning goes
    f = build_facts(approved("decision_p02_ready", ("fund:AAL",)), evidence())
    assert "fx_exposure" not in [w.code for w in f.warnings]
    assert "fund:AKE" not in json.dumps(f.to_dict())


def test_warnings_carry_the_numbers_of_their_evidence():
    f = build_facts(p02(), evidence())
    market = next(w for w in f.warnings if w.code == "deposit_vs_market")
    assert {n.evidence_id: n.value for n in market.numbers} == {"E42b47116": 23.0,
                                                                "E9cb9f7ad": 43.82}


def test_open_questions_assumptions_and_data_quality():
    r = p02()
    f = build_facts(r, evidence())
    assert f.open_questions == (r.questions[0].text,)
    assert f.assumptions == r.assumptions
    assert [n.message for n in f.data_quality] == [n.message for n in r.data_quality]


def test_evidence_ids_and_named_options():
    f = build_facts(p02(), evidence())
    assert set(f.named_options()) == {"deposit:ing_turuncu", "fund:BBF", "fund:AAL", "fund:AKE"}
    assert {"Ebb80cd5d", "E42b47116", "E01487022"} <= f.evidence_ids()


def test_to_dict_is_plain_json():
    d = build_facts(p03(), evidence()).to_dict()
    assert json.loads(json.dumps(d, ensure_ascii=False)) == d
    assert d["selected"][0]["option_id"] == "fund:AAV"
