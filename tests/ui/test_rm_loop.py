import dataclasses

from rmprep.contracts import DecisionState, RmStatus
from rmprep.ui import views
from rmprep.ui.i18n import t
from tests.ui.conftest import SNAPSHOT, app_test, run

Q01 = "q:acik_kisitlar[0]"


def _p(pid):
    at = run(app_test())
    if pid != "P01":
        at.selectbox(key="persona").set_value(pid)
        run(at)
    return at


def _answer(at, qid, value):
    at.radio(key=f"qv:{qid}").set_value(value)
    at.button(key=f"qa:{qid}").click()
    return run(at)


def _history(at):
    return at.session_state["history"]


# --- pure helpers -------------------------------------------------------------

def test_open_questions_put_blocking_ones_first(fake):
    r = fake.decide(fake.list_personas()[1], SNAPSHOT)
    q = r.questions[0]
    blocking = dataclasses.replace(q, question_id="q:x", blocking=True)
    answered = dataclasses.replace(q, question_id="q:y", answer=q.choices[0])
    r2 = dataclasses.replace(r, questions=(q, answered, blocking), state=DecisionState.NEEDS_RM_INPUT,
                             options=(), rejected=(), warnings=())
    assert [x.question_id for x in views.open_questions(r2)] == ["q:x", q.question_id]


def test_persona_diff_names_each_changed_field(fake):
    p = fake.list_personas()[0]
    e = dataclasses.replace(p, yas=45, oncelikler=("düzenli gelir",))
    assert views.persona_diff(p, e) == [
        "yaş 62 → 45", "öncelikler düzenli gelir, likiditeyi koruma, sınırlı dalgalanma → düzenli gelir"]
    assert views.persona_diff(p, p) == []


def test_describe_change(fake):
    p = fake.list_personas()[0]
    a = views.RunInputs(p, SNAPSHOT, frozenset(), ())
    assert views.describe_change(None, a) == t("ch_first")
    b = dataclasses.replace(a, excluded_sources=frozenset({"tefas"}))
    assert views.describe_change(a, b) == "tefas hariç"
    assert views.describe_change(b, a) == "tefas dahil"
    c = dataclasses.replace(a, answers=(("q:doviz_maruz_kalma_tercihi", "Sınırlı"),))
    assert views.describe_change(a, c) == "yanıt: q:doviz_maru… = Sınırlı"
    d = dataclasses.replace(a, persona=dataclasses.replace(p, yas=45))
    assert views.describe_change(a, d) == "test: yaş 62 → 45"


def test_known_levels_merge_config_and_persona_values(fake):
    raw = {"risk_profiles": {"Muhafazakâr": {}, "Agresif": {}}, "levels": {"Düşük": 0, "Orta": 0.5},
           "fx_levels": {"Sınırlı": 1}}
    lv = views.known_levels(raw, fake.list_personas())
    assert lv["risk_profili"][:2] == ["Muhafazakâr", "Agresif"]
    assert "Dengeli" in lv["risk_profili"]          # seen in a persona
    assert lv["likidite_ihtiyaci"][:2] == ["Düşük", "Orta"]
    assert lv["doviz_maruz_kalma_tercihi"][0] == "Sınırlı"
    assert "1-3 yıl" in lv["yatirim_ufku"]
    assert all(len(v) == len(set(v)) for v in lv.values())


# --- questions ----------------------------------------------------------------

def test_answer_makes_a_new_run_shown_at_once():
    at = _p("P01")
    first = at.session_state["result"]
    assert first.state == DecisionState.NEEDS_RM_INPUT
    choice = first.questions[0].choices[0]
    _answer(at, Q01, choice)
    r = at.session_state["result"]
    assert r.run_id != first.run_id
    assert r.state == DecisionState.READY and r.questions[0].answer == choice
    assert [h["run_id"] for h in _history(at)] == [first.run_id, r.run_id]
    assert _history(at)[1]["change"].startswith("yanıt: ")
    assert at.success  # banner is ready now


def test_answers_stay_across_a_source_change_and_clear_on_persona_pick():
    at = _p("P01")
    choice = at.session_state["result"].questions[0].choices[1]
    _answer(at, Q01, choice)
    at.checkbox(key="src:tefas").uncheck()
    run(at)
    r = at.session_state["result"]
    assert r.excluded_sources == frozenset({"tefas"}) and r.questions[0].answer == choice
    assert len(_history(at)) == 3 and _history(at)[2]["change"] == "tefas hariç"
    at.selectbox(key="persona").set_value("P02")
    run(at)
    assert len(_history(at)) == 1
    at.selectbox(key="persona").set_value("P01")
    run(at)
    r = at.session_state["result"]
    assert r.state == DecisionState.NEEDS_RM_INPUT and len(_history(at)) == 1


def test_non_blocking_question_is_shown_while_ready():
    at = _p("P02")
    r = at.session_state["result"]
    q = r.questions[0]
    assert not q.blocking and at.radio(key=f"qv:{q.question_id}").options == list(q.choices)
    _answer(at, q.question_id, q.choices[0])
    assert at.session_state["result"].questions[0].answer == q.choices[0]
    assert not any(b.key == f"qa:{q.question_id}" for b in at.button)


def test_clicking_a_run_in_the_history_shows_it_again():
    at = _p("P02")
    first = at.session_state["result"]
    at.checkbox(key="src:tefas").uncheck()
    run(at)
    at.button(key="hist:0").click()
    run(at)
    assert at.session_state["result"].run_id == first.run_id
    assert at.checkbox(key="src:tefas").value is True
    assert len(_history(at)) == 2


# --- approve / reject ---------------------------------------------------------

def test_approve_needs_a_selected_option():
    at = _p("P02")
    r = at.session_state["result"]
    at.button(key="approve").click()
    run(at)
    assert at.session_state["result"].rm_status == RmStatus.PENDING
    assert any(t("need_selection") in e.value for e in at.error)
    oid = r.options[1].option.option_id
    at.checkbox(key=f"sel:{r.run_id}:{oid}").check()
    at.text_area(key=f"note:{r.run_id}").input("görüşelim")
    at.button(key="approve").click()
    run(at)
    a = at.session_state["result"]
    assert (a.rm_status, a.rm_selected, a.rm_note) == (RmStatus.APPROVED, (oid,), "görüşelim")
    assert at.session_state["backend"].saved[r.run_id] == a
    assert _history(at)[-1]["status"] == RmStatus.APPROVED
    assert not any(b.key == "approve" for b in at.button)


def test_one_checkbox_per_shown_option():
    at = _p("P02")
    r = at.session_state["result"]
    keys = [c.key for c in at.checkbox if c.key.startswith("sel:")]
    shown = views.shown_options(r)
    assert keys == [f"sel:{r.run_id}:{o.option.option_id}" for o in shown]


def test_reject_needs_a_note():
    at = _p("P02")
    r = at.session_state["result"]
    at.button(key="reject").click()
    run(at)
    assert at.session_state["result"].rm_status == RmStatus.PENDING
    assert any(t("need_note") in e.value for e in at.error)
    at.text_area(key=f"note:{r.run_id}").input("uygun değil")
    at.button(key="reject").click()
    run(at)
    assert at.session_state["result"].rm_status == RmStatus.REJECTED


def test_needs_input_result_has_no_approve_buttons():
    at = _p("P01")
    assert not any(b.key in ("approve", "reject") for b in at.button)


# --- persona edit (test run) --------------------------------------------------

def test_edited_persona_is_a_test_run_that_cannot_be_approved():
    at = _p("P02")
    original = at.session_state["result"]
    at.number_input(key="edit:yas").set_value(45)
    at.button(key="edit_apply").click()
    run(at)
    r = at.session_state["result"]
    assert r.persona.yas == 45 and r.persona.persona_id == "P02" and r.run_id != original.run_id
    assert any("Test: P02" in w.value and "yaş 48 → 45" in w.value for w in at.warning)
    assert at.button(key="approve").disabled and at.button(key="reject").disabled
    assert any(t("test_no_approve") in c.value for c in at.caption)
    assert _history(at)[-1]["change"] == "test: yaş 48 → 45"
    at.button(key="edit_reset").click()
    run(at)
    assert at.session_state["result"].run_id == original.run_id
    assert at.number_input(key="edit:yas").value == 48
    assert not at.button(key="approve").disabled


def test_other_level_takes_free_text():
    at = _p("P02")
    at.selectbox(key="edit:risk_profili").set_value(views.OTHER)
    at.text_input(key="edit:risk_profili:other").input("Biraz riskli")
    at.button(key="edit_apply").click()
    run(at)
    assert at.session_state["result"].persona.risk_profili == "Biraz riskli"


def test_list_fields_are_edited_one_per_line():
    at = _p("P02")
    at.text_area(key="edit:oncelikler").input("çeşitlendirme\n\n uzun vadeli büyüme ")
    at.button(key="edit_apply").click()
    run(at)
    assert at.session_state["result"].persona.oncelikler == ("çeşitlendirme", "uzun vadeli büyüme")


def test_invalid_edit_shows_an_error_and_keeps_the_run():
    at = _p("P02")
    before = at.session_state["result"].run_id
    at.text_input(key="edit:profil").input("  ")
    at.button(key="edit_apply").click()
    run(at)
    assert at.session_state["result"].run_id == before
    assert at.sidebar.error
