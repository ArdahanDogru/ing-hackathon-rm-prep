"""F1: the manual feedback report (spec docs/superpowers/specs/2026-10-16-feedback-report-
design.md). Fixed JSONL logs in a tmp root; no LLM, no network."""

import json
import shutil
from datetime import date, datetime
from pathlib import Path

import pytest

from rmprep.contracts import TR_TZ
from rmprep.eval.feedback import (
    FeedbackConfigError, load_feedback_config, parse_feedback_config, run_feedback, section_of,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "feedback"
NOW = datetime(2026, 10, 16, 18, 30, 0, tzinfo=TR_TZ)
V1 = {"decision_config": "cfg1", "narrator_prompt": "n10", "agent_prompt": "a3", "research": "2"}
V2 = dict(V1, narrator_prompt="n11", agent_prompt="a4", research="3")


class Log:
    """Writes records into <root>/data/logs/rm-actions/<day>.jsonl in call order."""

    def __init__(self, root: Path):
        self.dir = root / "data" / "logs" / "rm-actions"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.n = 0

    def add(self, action, details=None, *, run="R1", day="2026-10-16", versions=V1, **extra):
        self.n += 1
        rec = {"ts": f"{day}T10:{self.n // 60:02d}:{self.n % 60:02d}+03:00", "action": action,
               "run_id": run, "persona_id": "P01", "snapshot_id": "S1", **extra,
               "details": details or {}}
        if versions is not None:
            rec["versions"] = versions
        with (self.dir / f"{day}.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def mark(self, i, mark, *, section="news", cls="nakit_benzeri", **kw):
        self.add("research_marked", {"finding_id": f"F{i:08x}", "option_id": "fund:AAA",
                                     "mark": mark, "section": section, "topic": "haber",
                                     "option_kind": "fund", "asset_class": cls}, **kw)

    def approve(self, run, *, engine=("fund:A", "fund:B", "fund:C"), agent=(), selected=(),
                **kw):
        self.add("decision_approved", {"engine_top3": list(engine), "agent_top3": list(agent),
                                       "agent_state": "done" if agent else "none",
                                       "selected": list(selected or engine[:2]), "note": ""},
                 run=run, **kw)

    def block(self, run, block_id, after, before="Eski metin.", **kw):
        action = "text_block_deleted" if after == "" else "text_block_edited"
        self.add(action, {"block_id": block_id, "before": before, "after": after,
                          "findings": []}, run=run, lang="TR", **kw)

    def split(self, shares, estimate, **kw):
        self.add("holdings_set", {"shares": shares, "origin": "rm", "estimate": estimate},
                 run="R9", new_run_id="R10", **kw)


@pytest.fixture
def root(tmp_path):
    (tmp_path / "config").mkdir()
    shutil.copy(FIX / "feedback.yaml", tmp_path / "config" / "feedback.yaml")
    return tmp_path


def run(root, **kw):
    kw.setdefault("now", lambda: NOW)
    return run_feedback(root, **kw)


def rule(res, rid):
    return res.measures["rules"][rid]


def groups(res, rid, **match):
    return [g for g in rule(res, rid)["groups"]
            if all(g["group"].get(k) == v for k, v in match.items())]


# --- config -------------------------------------------------------------------------------

def test_the_config_loads():
    cfg = load_feedback_config(FIX / "feedback.yaml")
    assert cfg.evidence_max == 3 and cfg.rules["R1"].min_n == 10
    assert cfg.rules["R3"].examples == 2 and cfg.rules["R5"].threshold == 15
    assert cfg.rules["R1"].actions["news"]["TR"].startswith("haber istemi")
    assert cfg.label("ozet") == "Özet" and cfg.label("dikkat") == "dikkat"


def _raw():
    import yaml
    return yaml.safe_load((FIX / "feedback.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("change, msg", [
    (lambda r: r.update(extra=1), "unknown keys"),
    (lambda r: r.pop("evidence_max"), "missing keys"),
    (lambda r: r.update(version=2), "version"),
    (lambda r: r["rules"].pop("R5"), "rules"),
    (lambda r: r["rules"]["R2"].update(min_n=0), "min_n"),
    (lambda r: r["rules"]["R2"].update(threshold=-1), "threshold"),
    (lambda r: r["rules"]["R2"]["text"].pop("EN"), "text"),
    (lambda r: r["rules"]["R2"]["text"].update(TR="{nope}"), "unknown field"),
    (lambda r: r["rules"]["R1"]["actions"].pop("news"), "actions"),
    (lambda r: r["rules"]["R2"].update(examples=2), "unknown keys"),
    (lambda r: r["rules"]["R3"].update(examples=-1), "examples"),
    (lambda r: r.update(labels={"ozet": 3}), "labels"),
])
def test_bad_configs_are_refused(change, msg):
    raw = _raw()
    change(raw)
    with pytest.raises(FeedbackConfigError, match=msg):
        parse_feedback_config(raw)


def test_section_of_a_block():
    assert section_of("ozet") == "ozet"
    assert section_of("talking_points:2") == "talking_points"
    assert section_of("oneriler:fund:AAA") == "oneriler"


# --- empty, period, files -----------------------------------------------------------------------

def test_an_empty_period(root):
    res = run(root)
    assert res.measures["meta"]["records"] == 0
    for rid in ("R1", "R2", "R3", "R4", "R5"):
        r = rule(res, rid)
        assert r["groups"] == [] and r["status"] == "insufficient"
    md = res.markdown
    assert "Bu dönemde kayıt yok." in md
    assert md.count("Yeterli veri yok (0/") == 5
    assert res.report_md == root / "data" / "feedback" / "20261016-183000" / "report.md"
    assert res.report_md.read_text(encoding="utf-8") == md
    assert json.loads(res.report_json.read_text(encoding="utf-8")) == res.measures


def test_the_period_filters_by_the_record_day(root):
    log = Log(root)
    log.add("run_opened", day="2026-10-14")
    log.add("run_opened", day="2026-10-15")
    log.add("notes_saved", day="2026-10-16")
    res = run(root, since="2026-10-15", until=date(2026, 10, 15))
    assert res.measures["meta"]["records"] == 1
    assert res.measures["actions"] == {"run_opened": 1}
    assert run(root).measures["actions"] == {"run_opened": 2, "notes_saved": 1}


def test_a_broken_line_is_counted_and_skipped(root):
    log = Log(root)
    log.add("run_opened")
    with (log.dir / "2026-10-16.jsonl").open("a", encoding="utf-8") as f:
        f.write("{not json\n")
    res = run(root)
    assert res.measures["meta"]["records"] == 1 and res.measures["meta"]["broken_lines"] == [
        "2026-10-16.jsonl:2"]


# --- R1 research marks ------------------------------------------------------------------------

def test_r1_above_the_threshold(root):
    log = Log(root)
    for i in range(12):
        log.mark(i, "wrong" if i < 5 else "ok")         # 5/12 = 42 %
    res = run(root)
    [g] = groups(res, "R1", asset_class="nakit_benzeri", section="news")
    assert g["n"] == 12 and g["wrong"] == 5 and g["value"] == pytest.approx(5 / 12)
    assert g["status"] == "recommendation"
    assert g["recommendation"]["TR"] == ("Para piyasası fonları: haber maddeleri %42 oranında "
                                         "(5/12) ✗ işaretlendi → haber istemi yalnızca fona "
                                         "özgü olayları sorsun.")
    assert g["recommendation"]["EN"].startswith("Para piyasası fonları: 42% of the")
    assert g["evidence"] == ["2026-10-16.jsonl:1", "2026-10-16.jsonl:2", "2026-10-16.jsonl:3"]
    assert g["evidence_more"] == 9
    assert "2026-10-16.jsonl:1, 2026-10-16.jsonl:2, 2026-10-16.jsonl:3 + 9 more" in res.markdown


def test_r1_below_the_threshold_and_below_min_n(root):
    log = Log(root)
    for i in range(10):
        log.mark(i, "wrong" if i < 3 else "ok")         # 30 %: not above 0.30
    for i in range(4):
        log.mark(100 + i, "wrong", section="highlight")
    res = run(root)
    [news] = groups(res, "R1", section="news")
    [high] = groups(res, "R1", section="highlight")
    assert news["status"] == "no_recommendation" and news["recommendation"] is None
    assert high["status"] == "insufficient" and high["n"] == 4
    assert "Yeterli veri yok (4/10)" in res.markdown


def test_r1_counts_the_last_mark_of_a_finding(root):
    log = Log(root)
    log.mark(1, "wrong")
    log.mark(1, "ok")
    log.mark(2, "ok")
    log.mark(2, None)                                   # the mark is removed
    [g] = groups(run(root), "R1")
    assert g["n"] == 1 and g["wrong"] == 0
    assert g["evidence"] == ["2026-10-16.jsonl:2"]


def test_r1_skips_a_record_without_the_l1b_fields(root):
    log = Log(root)
    log.add("research_marked", {"finding_id": "F1", "option_id": "fund:AAA", "mark": "wrong"},
            versions=None)
    log.mark(2, "ok")
    res = run(root)
    r = rule(res, "R1")
    assert r["missing_fields"] == 1 and r["missing_evidence"] == ["2026-10-16.jsonl:1"]
    [g] = r["groups"]
    assert g["n"] == 1
    assert "Eksik alan: 1 kayıt" in res.markdown


# --- R2 / R3 meeting-text sections ----------------------------------------------------------------

def test_r2_deletions_above_and_below(root):
    log = Log(root)
    for k in range(7):
        log.approve(f"R{k}")
    for k in range(5):
        log.block(f"R{k}", "piyasa_notu", "")
    log.block("R0", "piyasa_notu", "")                  # a second delete of the same run
    log.block("R0", "ozet", "")
    log.block("RX", "ozet", "")                         # not an approved run: not counted
    res = run(root)
    [pn] = groups(res, "R2", section="piyasa_notu")
    assert (pn["n"], pn["deleted"], pn["status"]) == (7, 5, "recommendation")
    assert pn["recommendation"]["TR"] == ("'Piyasa notu' 7 onaylı metnin 5 tanesinde silindi "
                                          "(%71) → bölüm varsayılan olarak kapalı olsun.")
    [oz] = groups(res, "R2", section="ozet")
    assert (oz["deleted"], oz["status"]) == (1, "no_recommendation")


def test_r2_below_min_n(root):
    log = Log(root)
    for k in range(4):
        log.approve(f"R{k}")
        log.block(f"R{k}", "piyasa_notu", "")
    [g] = groups(run(root), "R2", section="piyasa_notu")
    assert g["status"] == "insufficient" and g["n"] == 4


def test_r3_edits_with_examples(root):
    log = Log(root)
    for k in range(6):
        log.approve(f"R{k}")
    for k in range(4):
        log.block(f"R{k}", "talking_points:1", f"Yeni nokta {k}.", before=f"Eski nokta {k}.")
    log.block("R5", "oneriler:fund:AAA", "Kısa.")
    res = run(root)
    [tp] = groups(res, "R3", section="talking_points")
    assert (tp["n"], tp["edited"], tp["status"]) == (6, 4, "recommendation")
    assert tp["examples"] == [{"before": "Eski nokta 0.", "after": "Yeni nokta 0.",
                               "at": "2026-10-16.jsonl:7"},
                              {"before": "Eski nokta 1.", "after": "Yeni nokta 1.",
                               "at": "2026-10-16.jsonl:8"}]
    assert "Eski nokta 0. → Yeni nokta 0." in res.markdown
    [on] = groups(res, "R3", section="oneriler")
    assert on["status"] == "no_recommendation"
    assert "'Konuşma noktaları' 6 metnin 4 tanesinde değiştirildi (%67)" in res.markdown


# --- R4 acceptance ----------------------------------------------------------------------------

def test_r4_agent_below_the_engine(root):
    log = Log(root)
    eng, ag = ("fund:A", "fund:B", "fund:C"), ("fund:A", "fund:X", "fund:Y")
    for k in range(6):          # selected A, B: engine 2/2, agent 1/2
        log.approve(f"R{k}", engine=eng, agent=ag, selected=("fund:A", "fund:B"))
    log.approve("R9", engine=eng, selected=("fund:Z",))     # no agent decision
    res = run(root)
    [g] = rule(res, "R4")["groups"]
    assert g["n"] == 6 and g["engine_share"] == 1.0 and g["agent_share"] == 0.5
    assert g["engine_share_all"] == pytest.approx(12 / 13) and g["approvals"] == 7
    assert g["status"] == "recommendation"
    assert g["recommendation"]["TR"].startswith("Ajan önerileri RM seçiminde %50, motor "
                                                "önerileri %100 kabul gördü (6 onay)")


def test_r4_no_recommendation_and_insufficient(root):
    log = Log(root)
    eng = ("fund:A", "fund:B", "fund:C")
    for k in range(5):
        log.approve(f"R{k}", engine=eng, agent=("fund:A", "fund:B", "fund:X"),
                    selected=("fund:A", "fund:B"))
    [g] = rule(run(root), "R4")["groups"]
    assert g["status"] == "no_recommendation"
    other = Log(root / "x")
    other.approve("R1", engine=eng, agent=eng)
    (root / "x" / "config").mkdir()
    shutil.copy(FIX / "feedback.yaml", root / "x" / "config" / "feedback.yaml")
    [g] = rule(run(root / "x"), "R4")["groups"]
    assert g["status"] == "insufficient" and g["n"] == 1


# --- R5 D27 estimate ------------------------------------------------------------------------

SHARES = {"nakit_benzeri": 50, "borclanma": 30, "hisse": 10, "altin_doviz": 10, "dengeli": 0}


def test_r5_estimate_error(root):
    log = Log(root)
    est = {"nakit_benzeri": {"current": 40, "source": "profile", "ref": "Emekli"},
           "borclanma": {"current": 8, "source": "profile", "ref": "Emekli"},
           "hisse": {"current": 9, "source": "national"},
           "altin_doviz": {"current": None, "source": "national"}}
    for _ in range(3):
        log.split(SHARES, est)
    log.add("holdings_set", {"shares": SHARES, "origin": "rm"}, versions=None)  # before L1b
    res = run(root)
    [b] = groups(res, "R5", source="profile", ref="Emekli", asset_class="borclanma")
    assert (b["n"], b["value"], b["status"]) == (3, 22.0, "recommendation")
    assert b["recommendation"]["TR"] == ("Meslek satırı (Emekli): borclanma tahmini RM "
                                         "değerlerinden ortalama 22 puan sapıyor (3 bölünme) → "
                                         "meslek tablosunu güncelleyin.")
    [n] = groups(res, "R5", source="profile", asset_class="nakit_benzeri")
    assert n["value"] == 10 and n["status"] == "no_recommendation"
    [h] = groups(res, "R5", source="national", asset_class="hisse")
    assert h["group"]["ref"] == "" and h["value"] == 1
    assert not groups(res, "R5", asset_class="altin_doviz")
    assert rule(res, "R5")["missing_fields"] == 1


def test_r5_below_min_n(root):
    log = Log(root)
    log.split(SHARES, {"borclanma": {"current": 0, "source": "national"}})
    [g] = groups(run(root), "R5")
    assert g["status"] == "insufficient" and "Yeterli veri yok (1/3)" in run(root).markdown


# --- versions, questions, determinism ------------------------------------------------------------

def test_two_versions_side_by_side(root):
    log = Log(root)
    for k in range(6):
        log.approve(f"A{k}", versions=V1)
        log.block(f"A{k}", "ozet", "")
    for k in range(5):
        log.approve(f"B{k}", versions=V2)
    log.block("B0", "ozet", "", versions=V2)
    res = run(root)
    r = rule(res, "R2")
    assert r["versions"] == ["narrator_prompt=n10", "narrator_prompt=n11"]
    old, new = groups(res, "R2", section="ozet")
    assert (old["version"], old["deleted"], old["status"]) == ("narrator_prompt=n10", 6,
                                                               "recommendation")
    assert (new["version"], new["deleted"], new["status"]) == ("narrator_prompt=n11", 1,
                                                               "no_recommendation")
    md = res.markdown
    assert "| Grup | narrator_prompt=n10 | narrator_prompt=n11 |" in md
    assert "| Özet | %100 (6/6) | %20 (1/5) |" in md


def test_records_without_versions_are_their_own_column(root):
    log = Log(root)
    for k in range(5):
        log.approve(f"R{k}", versions=None)
    log.approve("R9")
    r = rule(run(root), "R4")
    assert r["versions"] == ["agent_prompt=a3, decision_config=cfg1", "sürüm yok"]


def test_research_questions_are_listed(root):
    log = Log(root)
    log.add("research_question", {"question": "Fonun yöneticisi kim?", "refused": False,
                                  "findings": 2})
    log.add("research_question", {"question": " fonun yöneticisi kim? ", "refused": False,
                                  "findings": 1})
    log.add("research_question", {"question": "Müşteri X ne almalı?", "refused": True,
                                  "findings": 0})
    qs = run(root).measures["research_questions"]
    assert qs == [{"question": "Fonun yöneticisi kim?", "count": 2, "refused": 0},
                  {"question": "Müşteri X ne almalı?", "count": 1, "refused": 1}]


def test_the_committed_fixture_log_is_deterministic(root):
    shutil.copytree(FIX / "logs", root / "data" / "logs" / "rm-actions")
    a = run(root, now=lambda: NOW)
    b = run(root, now=lambda: datetime(2026, 10, 17, 9, 0, tzinfo=TR_TZ))
    strip = lambda m: {k: v for k, v in m.items() if k != "meta"}   # noqa: E731
    assert strip(a.measures) == strip(b.measures)
    assert a.markdown.split("\n", 3)[3] == b.markdown.split("\n", 3)[3]
    meta = a.measures["meta"]
    assert meta["files"] == ["2026-10-15.jsonl", "2026-10-16.jsonl"] and meta["records"] == 9
    [g] = groups(a, "R2", section="piyasa_notu")
    assert g["evidence"] == ["2026-10-15.jsonl:4", "2026-10-16.jsonl:3"]


def test_w30_approvals_of_an_edited_profile_are_left_out(root):
    """W30: an approval with details.test_run is not counted in R2-R4; the report
    gives their number."""
    log = Log(root)
    for k in range(5):
        log.approve(f"R{k}")
        log.block(f"R{k}", "piyasa_notu", "")
    log.add("decision_approved", {"engine_top3": ["fund:A"], "agent_top3": [], "agent_state": "none",
                                  "selected": ["fund:A"], "note": "", "test_run": True,
                                  "persona_changes": [{"field": "yas", "original": 62, "edited": 63}]},
            run="RT")
    log.block("RT", "piyasa_notu", "")
    res = run(root)
    [pn] = groups(res, "R2", section="piyasa_notu")
    assert (pn["n"], pn["deleted"]) == (5, 5)
    assert rule(res, "R2")["test_runs_skipped"] == 1 and rule(res, "R4")["test_runs_skipped"] == 1
    assert "Düzenlenmiş profil onayları (dışarıda): 1" in res.markdown
