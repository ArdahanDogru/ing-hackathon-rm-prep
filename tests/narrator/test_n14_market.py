"""N14 (docs/narrator.md): the code-written block piyasa_notu (TCMB EVDS policy
rate, USD/TRY, funding cost) after ozet, with the evidence id of each value.
The tests use their own config copy (market_note texts of the test, not the
lead's)."""

import dataclasses
import json

import pytest
import yaml

import rmprep.edits as edits
from rmprep.contracts import NarrativeDraft
from rmprep.narrator.blocks import block_ids, block_text, check_block
from rmprep.narrator.config import DEFAULT_PATH, ConfigError, parse_config
from rmprep.narrator.facts import build_facts
from rmprep.narrator.market import market_note_sentences, with_market_note
from rmprep.narrator.service import Narrator
from rmprep.narrator.template import template_draft, template_need_tags, to_markdown
from rmprep.narrator.validator import validate
from tests.narrator.conftest import CREATED, evidence, p02
from tests.narrator.test_service import good

SENTENCE = {"TR": "{label} {value} (TCMB EVDS, {date}).",
            "EN": "{label} {value} (CBRT EVDS, {date})."}
SERIES = [
    {"key": "policy_rate", "quantity": "policy_rate", "entity": "CBRT policy rate (monthly, BIS)",
     "unit": "pct", "label": {"TR": "Politika faizi", "EN": "Policy rate"}},
    {"key": "usd_try", "quantity": "usd_try", "entity": "USD/TRY CBRT buying rate",
     "unit": "TRY", "label": {"TR": "USD/TRY (TCMB alış)", "EN": "USD/TRY (CBRT buying)"}},
    {"key": "funding_cost", "quantity": "cbrt_funding_cost",
     "entity": "CBRT weighted average funding cost", "unit": "pct",
     "label": {"TR": "TCMB ağırlıklı ortalama fonlama maliyeti",
               "EN": "CBRT weighted average funding cost"}},
]
# evidence_medium: policy rate 37.0 (2026-08-31), USD/TRY 49.1267, funding cost 37.0 (2026-10-09)
IDS = {"policy_rate": "E1970c4a6", "usd_try": "E32643a0c", "cbrt_funding_cost": "E48b4dba0"}


def _raw(**market_note):
    raw = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))
    raw["market_note"] = market_note
    return raw


@pytest.fixture(scope="module")
def mconfig():
    return parse_config(_raw(series=SERIES, sentence=SENTENCE))


def _without(ev, *quantities):
    return dataclasses.replace(ev, datapoints=tuple(d for d in ev.datapoints
                                                    if d.quantity not in quantities))


# --- config ---------------------------------------------------------------------------

def test_config_market_note(mconfig):
    note = mconfig.market_note
    assert [s.key for s in note.series] == ["policy_rate", "usd_try", "funding_cost"]
    assert note.series[1].entity == "USD/TRY CBRT buying rate"
    assert note.sentence == SENTENCE


def test_config_without_sentence_has_no_market_note():
    assert parse_config(_raw(series=SERIES)).market_note is None
    raw = _raw()
    raw.pop("market_note")
    assert parse_config(raw).market_note is None


@pytest.mark.parametrize("over, where", [
    (dict(sentence={"TR": "{label} {nope}", "EN": "{label}"}), "market_note.sentence.TR"),
    (dict(sentence={"TR": "{label}"}), "market_note.sentence"),
    (dict(series=[{**SERIES[0], "entity": ""}]), "market_note.series.0.entity"),
    (dict(series=[{**SERIES[0], "label": {"TR": "x"}}]), "market_note.series.0.label"),
])
def test_config_errors(over, where):
    with pytest.raises(ConfigError, match=f"^{where}"):
        parse_config(_raw(**{"series": SERIES, "sentence": SENTENCE, **over}))


def test_real_config_has_the_market_note():
    from rmprep.narrator.config import load_config

    note = load_config().market_note
    assert note is not None and {s.quantity for s in note.series} == set(IDS)


# --- sentences ---------------------------------------------------------------------------

def test_sentences_tr(mconfig):
    s = market_note_sentences(evidence(), mconfig, "TR")
    assert [x.text for x in s] == [
        "Politika faizi %37,00 (TCMB EVDS, 31.08.2026).",
        "USD/TRY (TCMB alış) 49,13 (TCMB EVDS, 09.10.2026).",
        "TCMB ağırlıklı ortalama fonlama maliyeti %37,00 (TCMB EVDS, 09.10.2026).",
    ]
    assert [x.evidence_ids for x in s] == [(IDS[q],) for q in IDS]
    assert all(x.option_ids == () for x in s)


def test_sentences_en(mconfig):
    s = market_note_sentences(evidence(), mconfig, "EN")
    assert s[0].text == "Policy rate 37.00% (CBRT EVDS, 2026-08-31)."
    assert s[1].text == "USD/TRY (CBRT buying) 49.13 (CBRT EVDS, 2026-10-09)."


def test_a_missing_series_is_left_out(mconfig):
    s = market_note_sentences(_without(evidence(), "usd_try"), mconfig, "TR")
    assert [x.evidence_ids for x in s] == [(IDS["policy_rate"],), (IDS["cbrt_funding_cost"],)]


def test_an_excluded_source_is_left_out(mconfig):
    ev = dataclasses.replace(evidence(), excluded_sources=frozenset({"evds"}))
    assert market_note_sentences(ev, mconfig, "TR") == ()


# --- the block in the draft ------------------------------------------------------------------

@pytest.fixture(scope="module")
def plain(mconfig):
    return template_draft(build_facts(p02(), evidence()), "TR", mconfig, created_at=CREATED)


@pytest.fixture(scope="module")
def noted(plain, mconfig):
    return with_market_note(plain, evidence(), mconfig)


def test_block_after_ozet(noted):
    keys = [s.key for s in noted.sections]
    assert keys[:2] == ["ozet", "piyasa_notu"]
    assert keys.count("piyasa_notu") == 1


def test_with_market_note_twice_keeps_one_block(noted, mconfig):
    assert with_market_note(noted, evidence(), mconfig) == noted


def test_no_value_no_block(plain, mconfig):
    ev = _without(evidence(), *IDS)
    assert with_market_note(plain, ev, mconfig) == plain
    assert with_market_note(plain, None, mconfig) == plain


def test_no_config_no_block(plain, mconfig):
    cfg = dataclasses.replace(mconfig, market_note=None)
    assert with_market_note(plain, evidence(), cfg) == plain


def test_markdown_has_the_market_note_after_ozet(noted):
    md = to_markdown(noted)
    heads = [x for x in md.splitlines() if x.startswith("## ")]
    assert heads[:2] == ["## Özet", "## Piyasa notu"]
    assert "Politika faizi %37,00 (TCMB EVDS, 31.08.2026). USD/TRY" in md


def test_validator_has_nothing_to_check_in_it(noted, mconfig):
    r = p02()
    f = build_facts(r, evidence())
    assert validate(noted.sections, f, r, mconfig, "TR", need_tags=template_need_tags(f)) == ()


def test_the_block_is_deletable(noted):
    assert "piyasa_notu" in block_ids(noted)
    assert block_text(noted, "piyasa_notu").startswith("Politika faizi %37,00")
    d = edits.with_edit(noted, "piyasa_notu", "", ())
    md = to_markdown(d)
    assert "## Piyasa notu" not in md and "Politika faizi" not in md
    assert md == to_markdown(edits.apply_edits(d))         # the API's path (app.py)
    assert edits.with_edit(d, "piyasa_notu", None, ()).rm_edits == {}


def test_editing_the_block_keeps_its_numbers_clean(noted):
    """The values of the note are not in the facts pack; an edit that keeps them
    gets no number warning; a new number still does."""
    r = p02()
    text = block_text(noted, "piyasa_notu")
    assert check_block(noted, r, evidence(), "piyasa_notu", text) == ()
    assert check_block(noted, r, evidence(), "piyasa_notu", "Politika faizi %37,00.") == ()
    found = check_block(noted, r, evidence(), "piyasa_notu", "Politika faizi %55,50.")
    assert [x.split(":", 1)[0] for x in found] == ["number"]
    found = check_block(noted, r, evidence(), "piyasa_notu", "Faiz garanti.")
    assert "phrase" in {x.split(":", 1)[0] for x in found}


def test_round_trip(noted):
    back = NarrativeDraft.from_dict(json.loads(json.dumps(noted.to_dict())))
    assert back == noted


# --- Narrator.draft ---------------------------------------------------------------------------

@pytest.mark.parametrize("client", [False, True])
def test_narrator_draft_has_the_block(tmp_path, mconfig, client):
    from tests.narrator.test_service import FakeLlm

    llm = FakeLlm(good(config=mconfig)) if client else None
    n = Narrator(mconfig, llm, tmp_path, clock=lambda: CREATED)
    d = n.draft(p02(), evidence(), "TR")
    assert d.source == ("llm" if client else "template")
    assert [s.key for s in d.sections][:2] == ["ozet", "piyasa_notu"]
    if client:          # cached with the block
        again = Narrator(mconfig, FakeLlm(), tmp_path, clock=lambda: CREATED)
        assert again.draft(p02(), evidence(), "TR") == d


def test_narrator_draft_without_market_values(tmp_path, mconfig):
    n = Narrator(mconfig, None, tmp_path, clock=lambda: CREATED)
    d = n.draft(p02(), _without(evidence(), *IDS), "TR")
    assert "piyasa_notu" not in [s.key for s in d.sections]
