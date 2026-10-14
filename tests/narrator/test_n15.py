"""N15 (docs/narrator.md; spec 2026-10-14-portfolio-projection-design.md section
10): the client's current split. The facts pack has the allocation rows; a
current share or gap is a fact only for an active row (rm, rm_confirmed,
persona_text); the validator rejects the figures of an estimate row (kind
number); the template states an active gap and asks for an unknown split.
The tests use their own config copies (narrator texts and the D27 decision keys)."""

import dataclasses
import json

import pytest
import yaml

from rmprep.contracts import NarrativeSection, NarrativeSentence
from rmprep.narrator.blocks import check_block
from rmprep.narrator.config import DEFAULT_PATH, ConfigError, parse_config
from rmprep.narrator.facts import build_facts
from rmprep.narrator.prompt import prompt_facts, system_prompt
from rmprep.narrator.template import template_draft, template_need_tags, template_sections
from rmprep.narrator.validator import validate
from tests.narrator.conftest import CREATED, evidence

UNKNOWN = {"TR": "Mevcut portföy dağılımı bilinmiyor; müşteriden alınmalı.",
           "EN": "The client's current portfolio split is unknown; ask the client for it."}
TEXTS = {
    "gap_under": {"TR": "{class_label} payı {source_label} {current}; model bandı {low}–{high}, "
                        "bandın {gap} puan altında.",
                  "EN": "{class_label} share {source_label}: {current}; model band "
                        "{low}–{high}, {gap} points below the band."},
    "gap_over": {"TR": "{class_label} payı {source_label} {current}; model bandı {low}–{high}, "
                       "bandın {gap} puan üstünde.",
                 "EN": "{class_label} share {source_label}: {current}; model band "
                       "{low}–{high}, {gap} points above the band."},
    "split_unknown": UNKNOWN,
    "class_labels": {
        "nakit_benzeri": {"TR": "Nakit benzeri", "EN": "Cash-like"},
        "borclanma": {"TR": "Borçlanma araçları", "EN": "Debt instruments"},
        "hisse": {"TR": "Hisse senedi", "EN": "Equities"},
        "altin_doviz": {"TR": "Altın ve döviz", "EN": "Gold and FX"},
        "dengeli": {"TR": "Dengeli fon", "EN": "Balanced funds"}},
    "source_labels": {
        "rm": {"TR": "RM'e göre", "EN": "according to the RM"},
        "rm_confirmed": {"TR": "RM onaylı tahmine göre",
                         "EN": "according to the estimate the RM confirmed"},
        "persona_text": {"TR": "müşteri dosyasına göre", "EN": "according to the client file"}},
}


def _raw(**allocation):
    raw = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))
    raw["allocation"] = allocation
    return raw


@pytest.fixture(scope="module")
def acfg():
    return parse_config(_raw(**TEXTS))


# P01 bands (config/decision.yaml, D20): nakit 10-20, borclanma 60-70, hisse 10-20,
# altin_doviz 5-10, dengeli none. Active: nakit 75 from the client file (gap -55).
# Estimates (national): borclanma 6.3 (gap 53.7), hisse 4.9 (gap 5.1), altin 7.4, dengeli 6.4.
ROWS = {
    "nakit_benzeri": dict(current=75.0, current_low=60.0, current_high=90.0,
                          current_source="persona_text", current_ref="mevduat_agirlikli",
                          gap=-55.0, active=True),
    "borclanma": dict(current=6.3, current_low=1.3, current_high=11.3, current_source="national",
                      current_ref="Türkiye hanehalkı ortalaması", gap=53.7),
    "hisse": dict(current=4.9, current_low=0.0, current_high=9.9, current_source="national",
                  current_ref="Türkiye hanehalkı ortalaması", gap=5.1),
    "altin_doviz": dict(current=7.4, current_low=2.4, current_high=12.4,
                        current_source="national", current_ref="Türkiye hanehalkı ortalaması",
                        gap=0.0),
    "dengeli": dict(current=6.4, current_low=1.4, current_high=11.4, current_source="national",
                    current_ref="Türkiye hanehalkı ortalaması"),
}


def _with_rows(r, rows):
    return dataclasses.replace(r, allocation=tuple(
        dataclasses.replace(a, **rows.get(a.asset_class, {})) for a in r.allocation))


@pytest.fixture(scope="module")
def r_partly(approved_p01):
    """P01 with the nakit share from the client file; the rest an estimate."""
    return _with_rows(approved_p01, ROWS)


@pytest.fixture(scope="module")
def r_estimate(approved_p01):
    """P01 with an estimate only (no active row)."""
    rows = {k: {**v, "current_source": "national", "active": False} for k, v in ROWS.items()}
    return _with_rows(approved_p01, rows)


@pytest.fixture(scope="module")
def r_rm(approved_p01):
    """P01 with the split from the RM (every row active)."""
    rows = {k: {**v, "current_source": "rm", "active": True,
                "current_low": v["current"], "current_high": v["current"]}
            for k, v in ROWS.items()}
    return _with_rows(approved_p01, rows)


def _rows(f):
    return {a.asset_class: a for a in f.allocation}


def _number_findings(findings):
    return [x for x in findings if x.startswith("number:")]


# --- facts pack -------------------------------------------------------------------------------

def test_facts_have_the_allocation_rows(r_partly):
    rows = _rows(build_facts(r_partly, evidence()))
    assert list(rows) == ["nakit_benzeri", "borclanma", "hisse", "altin_doviz", "dengeli"]
    n = rows["nakit_benzeri"]
    assert (n.band_low, n.band_high, n.current, n.source, n.gap, n.active) == (
        10, 20, 75.0, "persona_text", -55.0, True)


def test_an_estimate_row_has_no_current_or_gap(r_partly):
    b = _rows(build_facts(r_partly, evidence()))["borclanma"]
    assert (b.band_low, b.band_high, b.source, b.active) == (60, 70, "national", False)
    assert b.current is None and b.gap is None


def test_split_unknown(r_partly, r_estimate, r_rm, approved_p01):
    assert build_facts(r_partly, evidence()).split_unknown
    assert build_facts(r_estimate, evidence()).split_unknown
    assert not build_facts(r_rm, evidence()).split_unknown
    plain = dataclasses.replace(approved_p01, allocation=tuple(       # no D27 data
        dataclasses.replace(b, current=None, current_low=None, current_high=None,
                            current_source="", current_ref="", gap=None, active=False)
        for b in approved_p01.allocation))
    assert not build_facts(plain, evidence()).split_unknown


def test_prompt_pack_allocation(r_partly):
    pack = prompt_facts(build_facts(r_partly, evidence()))
    rows = {x["class"]: x for x in pack["allocation"]}
    assert rows["nakit_benzeri"] == {"class": "nakit_benzeri", "band_low": 10, "band_high": 20,
                                     "current": 75.0, "source": "persona_text", "gap": -55.0,
                                     "active": True}
    assert rows["borclanma"]["current"] is None and rows["borclanma"]["gap"] is None
    blob = json.dumps(pack)
    assert "53.7" not in blob and "6.3" not in blob


@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_system_prompt_rules(lang, acfg):
    text = system_prompt(lang, acfg)
    assert '"allocation"' in text and '"active": true' in text
    assert UNKNOWN[lang] in text


# --- validator --------------------------------------------------------------------------------

def _validate_with(r, cfg, key, text, lang="TR"):
    """The template text of r with one more sentence in section key."""
    f = build_facts(r, evidence())
    sections = list(template_sections(f, lang, cfg.disclaimer[lang]))
    whole = tuple(o.option_id for o in f.selected)
    for i, s in enumerate(sections):
        if s.key == key:
            sections[i] = NarrativeSection(key, (*s.sentences, NarrativeSentence(text, whole)))
    return validate(sections, f, r, cfg, lang, need_tags=template_need_tags(f))


@pytest.mark.parametrize("text", [
    "Borçlanma araçlarının payı bandın 53,7 puan altında.",          # the gap of an estimate
    "Borçlanma araçlarının payı %6,3.",                               # the current of an estimate
])
def test_figure_of_an_estimate_row_is_rejected(r_partly, acfg, text):
    found = _number_findings(_validate_with(r_partly, acfg, "dikkat", text))
    assert found and "estimate" in found[0], found


def test_figure_of_an_active_row_is_fine(r_partly, acfg):
    text = "Nakit benzeri payı %75; model bandının 55 puan üstünde."
    assert _validate_with(r_partly, acfg, "dikkat", text) == ()


def test_figures_from_the_rm_are_fine(r_rm, acfg):
    text = "Borçlanma araçlarının payı %6,3; bandın 53,7 puan altında."
    assert _validate_with(r_rm, acfg, "dikkat", text) == ()


def test_split_unknown_sentence_is_valid(r_estimate, acfg):
    assert _validate_with(r_estimate, acfg, "sorular", UNKNOWN["TR"]) == ()


def test_edited_block_with_an_estimate_figure_warns(r_partly, acfg):
    d = template_draft(build_facts(r_partly, evidence()), "TR", acfg, created_at=CREATED)
    found = check_block(d, r_partly, evidence(), "dikkat", "Borçlanma payı %6,3.", acfg)
    assert [x.split(":", 1)[0] for x in found] == ["number"]


# --- template ---------------------------------------------------------------------------------

def _texts(d, key):
    return [s.text for sec in d.sections if sec.key == key for s in sec.sentences]


@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_template_states_an_active_gap(r_partly, acfg, lang):
    f = build_facts(r_partly, evidence())
    d = template_draft(f, lang, acfg, created_at=CREATED)
    want = {"TR": "Nakit benzeri payı müşteri dosyasına göre %75; model bandı %10–%20, bandın "
                  "55 puan üstünde.",
            "EN": "Cash-like share according to the client file: 75%; model band 10%–20%, "
                  "55 points above the band."}[lang]
    assert want in _texts(d, "dikkat")
    assert UNKNOWN[lang] in _texts(d, "sorular")              # the rest is an estimate
    estimates = [TEXTS["class_labels"][k][lang] for k in ("borclanma", "hisse", "altin_doviz")]
    assert not any(t.startswith(tuple(estimates)) for t in _texts(d, "dikkat"))
    assert validate(d.sections, f, r_partly, acfg, lang, need_tags=template_need_tags(f)) == ()


def test_template_with_the_rm_split(r_rm, acfg):
    f = build_facts(r_rm, evidence())
    d = template_draft(f, "TR", acfg, created_at=CREATED)
    dikkat = _texts(d, "dikkat")
    assert any(t.startswith("Borçlanma araçları payı RM'e göre %6,3") and "53,7 puan altında" in t
               for t in dikkat)
    assert not any(t.startswith("Altın ve döviz") for t in dikkat)         # inside the band
    assert not any(t.startswith("Dengeli fon") for t in dikkat)            # no band
    assert UNKNOWN["TR"] not in _texts(d, "sorular")
    assert validate(d.sections, f, r_rm, acfg, "TR", need_tags=template_need_tags(f)) == ()


def test_template_estimate_only(r_estimate, acfg):
    f = build_facts(r_estimate, evidence())
    d = template_draft(f, "TR", acfg, created_at=CREATED)
    assert not any("payı" in t for t in _texts(d, "dikkat"))
    assert UNKNOWN["TR"] in _texts(d, "sorular")


def test_template_without_d27_data_is_unchanged(approved_p01, acfg, config):
    f = build_facts(approved_p01, evidence())
    assert template_draft(f, "TR", acfg, created_at=CREATED).sections == \
        template_draft(f, "TR", config, created_at=CREATED).sections


def test_template_without_the_config_texts(r_partly, acfg):
    cfg = dataclasses.replace(acfg, allocation=None)
    d = template_draft(build_facts(r_partly, evidence()), "TR", cfg, created_at=CREATED)
    assert not any("payı" in t for t in _texts(d, "dikkat"))
    assert UNKNOWN["TR"] not in _texts(d, "sorular")


# --- config -----------------------------------------------------------------------------------

def test_config_allocation(acfg):
    a = acfg.allocation
    assert a.split_unknown == UNKNOWN
    assert a.class_labels["hisse"]["EN"] == "Equities"
    assert a.source_labels["rm"]["TR"] == "RM'e göre"


def test_config_without_allocation():
    raw = _raw()
    raw.pop("allocation")
    assert parse_config(raw).allocation is None


@pytest.mark.parametrize("change, where", [
    (lambda t: t.pop("gap_over"), "allocation.gap_over"),
    (lambda t: t["gap_under"].update(TR="{nope}"), "allocation.gap_under.TR"),
    (lambda t: t["class_labels"].pop("hisse"), "allocation.class_labels"),
    (lambda t: t["source_labels"]["rm"].pop("EN"), "allocation.source_labels.rm"),
])
def test_config_allocation_errors(change, where):
    texts = json.loads(json.dumps(TEXTS))
    change(texts)
    with pytest.raises(ConfigError, match=f"^{where}"):
        parse_config(_raw(**texts))


# --- with the D27 engine (the lead's test config copy) ------------------------------------------

@pytest.fixture(scope="module")
def d27_config():
    from rmprep.decision.config import DEFAULT_PATH as DECISION_PATH
    from rmprep.decision.config import parse_config as parse_decision_config
    from tests.decision.test_holdings import add_d27, strip_d27

    raw = yaml.safe_load(DECISION_PATH.read_text(encoding="utf-8"))
    return parse_decision_config(add_d27(strip_d27(raw)))


@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_d27_engine_p01(d27_config, acfg, lang):
    """P01 "mevduat ağırlıklı": the nakit share is active (client file), the rest
    an estimate; the template passes the validator."""
    from rmprep.contracts import RmStatus
    from rmprep.decision.engine import decide
    from tests.narrator.conftest import persona

    r = decide(evidence(), persona("p01"), d27_config, created_at=CREATED)
    chosen = tuple(o.option.option_id for o in r.options if o.option.kind != "deposit")[:2]
    r = dataclasses.replace(r, rm_status=RmStatus.APPROVED, rm_selected=chosen)
    f = build_facts(r, evidence(), decision_config=d27_config)
    active = [a.asset_class for a in f.allocation if a.active]
    assert active == ["nakit_benzeri"] and f.split_unknown
    d = template_draft(f, lang, acfg, created_at=CREATED)
    label = TEXTS["class_labels"]["nakit_benzeri"][lang]
    assert any(t.startswith(label) for t in _texts(d, "dikkat"))
    assert UNKNOWN[lang] in _texts(d, "sorular")
    assert validate(d.sections, f, r, acfg, lang, need_tags=template_need_tags(f)) == ()
