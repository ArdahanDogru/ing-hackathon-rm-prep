"""Plan 2026-10-15-agent-decision Task 5: the card section "Ajan kararı" (the engine's
top 3, the agent's top 3 with reasons and labels, the RM's choice; spec section 8)."""
from datetime import datetime

from rmprep.contracts import TR_TZ, AgentDecision, AgentPick, AgentReason
from rmprep.ui import card
from tests.ui.conftest import SNAPSHOT
from tests.ui.test_card_i18n import _approved

T = datetime(2026, 10, 15, 10, 0, tzinfo=TR_TZ)


def _done(r):
    ids = [o.option.option_id for o in r.options if o.option.kind != "deposit"]
    picks = (AgentPick(ids[2], (AgentReason("Borçlanma açığı büyük.", ("portfoy:borclanma",),
                                            ("(tahmini dağılıma göre)",)),), uses_estimate=True),
             AgentPick(ids[0], (AgentReason("Getiri yüksek.", ("puan:return",)),)),
             AgentPick(ids[1], (AgentReason("Yeni sözleşme haberi.", ("F0123abcd",), ("(web, doğrulanmamış)",)),),
                       uses_web=True))
    return AgentDecision(r.run_id, "done", picks, (), "Ajan özeti.", (ids[0], ids[1], ids[3]), (),
                         "claude-sonnet-5-5", "a1", 0.04, T)


def _label(r, oid):
    return next(o.option.label for o in r.options if o.option.option_id == oid)


def test_the_card_has_the_agent_section(fake):
    r = _approved(fake)
    d = _done(r)
    md = card.render_markdown(r, fake.evidence(SNAPSHOT), agent=d)
    assert "## Ajan kararı" in md
    section = md.split("## Ajan kararı", 1)[1]
    assert "Motor önerisi:" in section and "Ajan önerisi:" in section and "RM seçimi:" in section
    assert _label(r, d.picks[0].option_id) in section
    assert "Borçlanma açığı büyük. (tahmini dağılıma göre)" in section
    assert "Yeni sözleşme haberi. (web, doğrulanmamış)" in section
    assert "Ajan özeti." in section and "claude-sonnet-5-5" in section
    html = card.render_html(r, fake.evidence(SNAPSHOT), agent=d)
    assert "Ajan kararı" in html and "Borçlanma açığı büyük." in html


def test_a_fallback_shows_its_reason_and_no_agent_section_without_a_decision(fake):
    r = _approved(fake)
    fb = AgentDecision(r.run_id, "fallback", (), (), "", tuple(r.recommended), (), "claude-sonnet-5-5",
                       "a1", 0.01, T, fallback_reason="süre doldu")
    md = card.render_markdown(r, fake.evidence(SNAPSHOT), agent=fb)
    assert "Motor önerisi kullanıldı: süre doldu" in md
    assert "Ajan kararı" not in card.render_markdown(r, fake.evidence(SNAPSHOT))


def test_english_card(fake):
    r = _approved(fake)
    md = card.render_markdown(r, fake.evidence(SNAPSHOT), lang="EN", agent=_done(r))
    assert "## Agent decision" in md and "Engine recommendation:" in md and "RM choice:" in md
