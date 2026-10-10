import pytest

from rmprep.contracts import DecisionState
from tests.ui.conftest import PERSONA_IDS, SNAPSHOT, app_test, run


def test_page_loads_with_the_first_persona():
    at = run(app_test())
    assert at.selectbox(key="persona").value == "P01"
    assert at.selectbox(key="snapshot").value == SNAPSHOT
    assert at.session_state["result"].persona_id == "P01"
    assert any("P01" in h.value for h in at.subheader)


@pytest.mark.parametrize("pid", PERSONA_IDS)
def test_page_loads_for_every_persona(pid):
    at = run(app_test())
    at.selectbox(key="persona").set_value(pid)
    run(at)
    r = at.session_state["result"]
    assert r.persona_id == pid
    header = " ".join(h.value for h in at.subheader)
    assert pid in header and r.persona.risk_profili in header
    captions = " ".join(c.value for c in at.caption)
    assert r.run_id in captions and r.rm_status.value in captions
    if r.state == DecisionState.READY:
        assert at.success
    else:
        assert any("yanıtlayın" in w.value for w in at.warning)


def test_persona_card_shows_every_field():
    at = run(app_test())
    r = at.session_state["result"]
    text = " ".join(m.value for m in at.sidebar.markdown)
    for value in (r.persona.profil, r.persona.durum, r.persona.yatirim_ufku,
                  *r.persona.oncelikler):
        assert value in text


def test_sidebar_has_one_checkbox_per_source():
    at = run(app_test())
    keys = sorted(c.key for c in at.sidebar.checkbox if c.key.startswith("src:"))
    assert keys == ["src:evds", "src:manual", "src:tefas", "src:tefas_web"]
    assert all(at.checkbox(key=k).value for k in keys)


def test_clearing_a_source_makes_a_new_run():
    at = run(app_test())
    at.selectbox(key="persona").set_value("P02")
    run(at)
    first = at.session_state["result"]
    at.checkbox(key="src:tefas").uncheck()
    run(at)
    second = at.session_state["result"]
    assert second.run_id != first.run_id
    assert second.excluded_sources == frozenset({"tefas"})
    at.checkbox(key="src:tefas").check()
    run(at)
    assert at.session_state["result"].run_id == first.run_id


def test_rerun_without_change_does_not_call_decide():
    at = run(app_test())
    backend = at.session_state["backend"]
    calls = []
    orig = backend.decide
    backend.decide = lambda *a, **k: calls.append(a) or orig(*a, **k)
    run(at)
    assert calls == []


def test_default_backend_is_the_fake_without_rmprep_root(monkeypatch):
    from rmprep.ui import page
    from rmprep.ui.fake import FakeBackend

    monkeypatch.delenv("RMPREP_ROOT", raising=False)
    assert isinstance(page.default_backend(), FakeBackend)


def test_default_backend_is_the_real_one_with_rmprep_root(monkeypatch):
    from rmprep.ui import page

    made = []
    monkeypatch.setattr(page, "RealBackend", lambda root: made.append(root) or "real")
    monkeypatch.setenv("RMPREP_ROOT", "C:/somewhere/prototype")
    assert page.default_backend() == "real"
    assert made == ["C:/somewhere/prototype"]
