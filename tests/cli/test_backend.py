"""RealBackend: the Backend protocol on ingest + decision (no snapshot, no network:
build_evidence and list_snapshots are replaced by the fixture evidence)."""

import dataclasses
import json
from datetime import datetime
from pathlib import Path

import pytest

from rmprep import backend as be
from rmprep.contracts import TR_TZ, DecisionState, EvidenceSet, RmStatus

FIX = Path(__file__).resolve().parents[1] / "contracts" / "fixtures"
T0 = datetime(2026, 10, 10, 9, 0, tzinfo=TR_TZ)


@pytest.fixture
def backend(monkeypatch, tmp_path):
    ev = EvidenceSet.from_dict(json.loads((FIX / "evidence_medium.json").read_text(encoding="utf-8")))

    def fake_build(root, snapshot_id, exclude=frozenset()):
        assert snapshot_id == ev.snapshot_id
        return dataclasses.replace(ev, excluded_sources=frozenset(exclude))

    class Snap:
        snapshot_id = ev.snapshot_id

    monkeypatch.setattr(be, "build_evidence", fake_build)
    monkeypatch.setattr(be, "list_snapshots", lambda root: [Snap()])
    (tmp_path / "config").mkdir()
    cfg = Path(__file__).resolve().parents[2] / "config" / "decision.yaml"
    (tmp_path / "config" / "decision.yaml").write_bytes(cfg.read_bytes())
    return be.RealBackend(tmp_path, personas_dir=FIX / "personas", now=lambda: T0)


def persona(b, pid):
    return next(p for p in b.list_personas() if p.persona_id == pid)


def test_lists(backend):
    assert [p.persona_id for p in backend.list_personas()] == ["P01", "P02", "P03", "P04", "P05"]
    assert backend.list_snapshots() == ["20261010-001233-6b20"]


def test_decide_is_a_real_run_and_same_inputs_give_the_same_run(backend):
    snap = backend.list_snapshots()[0]
    r1 = backend.decide(persona(backend, "P02"), snap)
    r2 = backend.decide(persona(backend, "P02"), snap)
    assert r1.run_id == r2.run_id and r1.persona_id == "P02"
    assert backend.decide(persona(backend, "P02"), snap, frozenset({"manual"})).run_id != r1.run_id


def _blocking(backend):
    snap = backend.list_snapshots()[0]
    for p in backend.list_personas():
        r = backend.decide(p, snap)
        for q in r.questions:
            if q.answer is None and q.choices:
                return r, q
    pytest.skip("no persona with an open question on the fixture")


def test_answer_makes_a_new_run(backend):
    r, q = _blocking(backend)
    new = backend.answer_question(r.run_id, q.question_id, q.choices[0])
    assert new.run_id != r.run_id
    assert next(x for x in new.questions if x.question_id == q.question_id).answer == q.choices[0]


def test_approve_saves_the_run_and_the_card(backend, tmp_path):
    snap = backend.list_snapshots()[0]
    r = next(x for x in (backend.decide(p, snap) for p in backend.list_personas())
             if x.state == DecisionState.READY)
    ok = backend.approve(r.run_id, RmStatus.APPROVED, "ok", (r.options[0].option.option_id,))
    saved = json.loads((tmp_path / "data" / "runs" / f"{r.run_id}.json").read_text(encoding="utf-8"))
    assert saved["rm_status"] == "approved"
    noted = backend.annotate(r.run_id, "genel", {r.options[0].option.option_id: "not"})
    assert noted.rm_option_notes == {r.options[0].option.option_id: "not"}
    where = backend.save_card(r.run_id, "# kart\n")
    assert Path(where).read_text(encoding="utf-8") == "# kart\n"
    assert backend.decide(ok.persona, snap).rm_status == RmStatus.APPROVED


def test_reject_needs_a_note_and_a_test_run_cannot_be_approved(backend):
    snap = backend.list_snapshots()[0]
    p = persona(backend, "P02")
    r = backend.decide(p, snap)
    with pytest.raises(ValueError):
        backend.approve(r.run_id, RmStatus.REJECTED, " ")
    edited = dataclasses.replace(p, yas=p.yas + 1)
    t = backend.decide(edited, snap)
    with pytest.raises(ValueError, match="test run"):
        backend.approve(t.run_id, RmStatus.REJECTED, "no")


class FakeNarrator:
    def __init__(self):
        self.calls = []

    def draft(self, r, ev, lang):
        from rmprep.contracts import NarrativeDraft, NarrativeSection, NarrativeSentence
        self.calls.append((r.run_id, lang, ev.snapshot_id))
        return NarrativeDraft(r.run_id, lang, (NarrativeSection("ozet", (NarrativeSentence("x"),)),),
                              "template", "", "fake", (), T0)


def _approved(backend):
    snap = backend.list_snapshots()[0]
    r = next(x for x in (backend.decide(p, snap) for p in backend.list_personas())
             if x.state == DecisionState.READY)
    return backend.approve(r.run_id, RmStatus.APPROVED, "ok", (r.options[0].option.option_id,))


def test_narrative_needs_an_approved_run(backend):
    backend._narrator_obj = FakeNarrator()
    snap = backend.list_snapshots()[0]
    r = backend.decide(persona(backend, "P02"), snap)
    with pytest.raises(ValueError, match="approved"):
        backend.draft_narrative(r.run_id, "TR")


def test_draft_and_approve_narrative(backend, tmp_path):
    fake = FakeNarrator()
    backend._narrator_obj = fake
    r = _approved(backend)
    d = backend.draft_narrative(r.run_id, "EN")
    assert (d.run_id, d.lang) == (r.run_id, "EN") and fake.calls[-1][1] == "EN"
    with pytest.raises(ValueError):
        backend.approve_narrative(r.run_id, "EN", "  ")
    a = backend.approve_narrative(r.run_id, "EN", "# Final\ntext")
    assert a.status.value == "approved" and a.rm_text == "# Final\ntext"
    saved = tmp_path / "data" / "narratives" / f"{r.run_id}-EN-approved.json"
    assert json.loads(saved.read_text(encoding="utf-8"))["rm_text"] == "# Final\ntext"
    calls = len(fake.calls)
    assert backend.draft_narrative(r.run_id, "EN") == a       # the approved text wins
    assert len(fake.calls) == calls                            # without a new draft


class SlowNarrator(FakeNarrator):
    def __init__(self):
        super().__init__()
        import threading
        self.release = threading.Event()

    def draft(self, r, ev, lang):
        self.release.wait(10)
        return super().draft(r, ev, lang)


def test_approval_starts_the_tr_text_and_opening_it_waits_for_that_job(backend):
    slow = SlowNarrator()
    backend._narrator_obj = slow
    r = _approved(backend)                      # returns at once; the TR draft runs in the background
    assert slow.calls == []
    slow.release.set()
    d = backend.draft_narrative(r.run_id, "TR")
    assert d.lang == "TR"
    assert [c[1] for c in slow.calls] == ["TR"]      # one call: the background job, not a second one


def test_a_failed_background_draft_is_made_again_on_request(backend):
    class Flaky(FakeNarrator):
        def draft(self, r, ev, lang):
            if not self.calls:
                self.calls.append(("boom", lang, None))
                raise RuntimeError("network")
            return super().draft(r, ev, lang)
    flaky = Flaky()
    backend._narrator_obj = flaky
    r = _approved(backend)
    assert backend.draft_narrative(r.run_id, "TR").lang == "TR"
    assert len(flaky.calls) == 2


def test_a_rejection_starts_no_text(backend):
    fake = FakeNarrator()
    backend._narrator_obj = fake
    snap = backend.list_snapshots()[0]
    r = backend.decide(persona(backend, "P02"), snap)
    backend.approve(r.run_id, RmStatus.REJECTED, "not now")
    backend.wait_for_background()
    assert fake.calls == []
