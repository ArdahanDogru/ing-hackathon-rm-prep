"""View models of the API (docs/web-ui.md section 6): rank, stars, category
average, match ring, access, RunView shape."""

import pytest

from rmprep.api.views import ViewBuilder, category_average, category_ranks, match, stars
from rmprep.decision import load_config
from rmprep.decision.display import DisplayFacts, Fact


def facts(oid, r1y=None, r3m=None, real=None):
    returns = {k: Fact(v, f"E{oid}{k}") for k, v in (("1y", r1y), ("3m", r3m)) if v is not None}
    return DisplayFacts(oid, returns, None if real is None else Fact(real, f"E{oid}1y"),
                        None, None, None, ())


@pytest.mark.parametrize("p,n,s", [(1, 88, 5), (9, 88, 5), (10, 88, 4), (29, 88, 4),
                                   (30, 88, 3), (60, 88, 3), (61, 88, 2), (80, 88, 2),
                                   (81, 88, 1), (88, 88, 1), (1, 1, 5), (2, 2, 3)])
def test_stars_split(p, n, s):
    assert stars(p, n) == s


def test_match_ring():
    assert match(1, 10) == 10.0 and match(10, 10) == 0.0 and match(4, 10) == 6.7
    assert match(1, 1) == 10.0


def test_category_ranks_by_1y_and_skips_funds_without_it():
    f = {"a": facts("a", 10), "b": facts("b", 30), "c": facts("c", 20), "d": facts("d"),
         "e": facts("e", 20)}
    ranks = category_ranks(f, ["a", "b", "c", "d", "e"])
    assert ranks["b"] == {"position": 1, "of": 4, "stars": 5, "better_than_pct": 75}
    assert ranks["c"]["position"] == 2 and ranks["e"]["position"] == 3    # tie: option id
    assert ranks["a"] == {"position": 4, "of": 4, "stars": 2, "better_than_pct": 0}
    assert "d" not in ranks


def test_category_average_ignores_missing_values():
    f = {"a": facts("a", 10, 1, real=-2), "b": facts("b", 30), "c": facts("c")}
    avg = category_average(f, ["a", "b", "c"])
    assert avg == {"3m": 1.0, "6m": None, "1y": 20.0, "real_1y": -2.0}


@pytest.fixture
def view(backend, persona):
    from rmprep.contracts import Persona
    r = backend.decide(Persona.from_dict(persona), backend.list_snapshots()[0])
    return r, ViewBuilder(backend, load_config())(r)


def test_runview_shape(view):
    r, v = view
    assert v["baseline"]["kind"] == "deposit" and v["baseline"]["rank"] is None
    assert 1 <= len(v["top"]) <= 3 and set(v["top"]) <= set(v["options"])
    assert all(1 <= len(c["option_ids"]) <= 3 for c in v["categories"])
    assert {i for c in v["categories"] for i in c["option_ids"]} <= set(v["options"])
    for o in v["options"].values():
        if o["kind"] == "fund":
            assert 0.0 <= o["match"] <= 10.0
        else:
            assert o["rank"] is None and o["stars"] is None and o["category_avg"] is None
    assert [w["audience"] for w in v["client_warnings"]] == ["client"]
    assert {w["audience"] for w in v["rm_warnings"]} == {"rm"}
    from rmprep.contracts import _to_json
    assert v["talking_points"] == [_to_json(tp) for tp in r.talking_points]


def test_to_confirm_has_commands_and_open_non_blocking_questions(view):
    r, v = view
    texts = [c["text"] for c in v["to_confirm"]]
    assert texts[:len(r.to_confirm)] == list(r.to_confirm)
    q = next(q for q in r.questions if not q.blocking and q.answer is None)
    item = next(c for c in v["to_confirm"] if c["question_id"] == q.question_id)
    assert item["text"] == q.text and item["choices"] == list(q.choices)


def test_rejected_by_rule_counts(view):
    r, v = view
    rows = {x["rule_id"]: x for x in v["rejected_by_rule"]}
    assert rows["risk_ceiling"]["count"] == 1 and rows["risk_ceiling"]["label"] == "Risk tavanı"
    assert rows["risk_ceiling"]["options"][0]["reasons"]


def test_option_view_values(view):
    r, v = view
    head = v["options"][v["top"][0]]
    assert head["returns"]["1y"]["evidence_id"] and head["rank"]["of"] >= 1
    assert head["category_label"]
    label = head["access"]["label"]
    assert label is None or label == "Aynı gün" or label.endswith("iş günü")
    assert head["selected"] is False and head["rm_note"] == ""


def test_views_through_the_app(backend, persona):
    from fastapi.testclient import TestClient

    from rmprep.api.app import create_app
    c = TestClient(create_app(backend, views=ViewBuilder(backend, load_config())))
    v = c.post("/api/runs", json={"persona": persona}).json()
    assert {"result", "test_run", "top", "categories", "options", "to_confirm"} <= set(v)
    assert v["top"] and all(i in v["options"] for i in v["top"])


def test_every_rule_and_kind_has_a_label():
    from rmprep.api.views import _label
    from rmprep.decision import load_config
    cfg = load_config()
    for rule in ("risk_ceiling", "not_buyable", "fx_limit", "liquidity_need", "short_history"):
        for lang in ("TR", "EN"):
            assert _label(f"rule.{rule}", lang) != rule
    for kind in {*cfg.raw["fund_kinds"].values(), "deposit", "time_deposit"} - {None}:
        assert _label(f"kind.{kind}", "TR") != kind


def test_option_data_notes_are_only_about_that_option(backend, persona):
    import dataclasses

    from rmprep.contracts import DataQualityNote, Persona
    r = backend.decide(Persona.from_dict(persona), backend.list_snapshots()[0])
    head = r.options[1]
    own = DataQualityNote("only this fund", evidence_ids=head.evidence_ids[:1])
    wide = DataQualityNote("source wide", evidence_ids=(head.evidence_ids[0], "E-other-fund"))
    r = dataclasses.replace(r, data_quality=(own, wide))
    v = ViewBuilder(backend, load_config())(r)
    notes = v["options"][head.option.option_id]["data_notes"]
    assert [n["message"] for n in notes] == ["only this fund"]
    assert [n["message"] for n in v["data_notes"]] == ["only this fund", "source wide"]


def test_runview_has_the_risk_ceiling(view):
    r, v = view
    from rmprep.decision import load_config
    from rmprep.decision.persona import read_persona
    answers = {q.question_id: q.answer for q in r.questions if q.answer is not None}
    assert v["risk_ceiling"] == read_persona(r.persona, load_config(), answers).levels.ceiling
    assert isinstance(v["risk_ceiling"], int) and 1 <= v["risk_ceiling"] <= 7


def test_allocation_options_are_in_the_view(backend, persona):
    import dataclasses

    from rmprep.contracts import AllocationBand, Persona
    r = backend.decide(Persona.from_dict(persona), backend.list_snapshots()[0])
    far = r.options[-1].option.option_id
    r = dataclasses.replace(r, allocation=(AllocationBand("hisse", 40.0, 50.0, "s", False, far, ""),))
    v = ViewBuilder(backend, load_config())(r)
    assert far in v["options"]
    assert v["result"]["allocation"][0]["option_id"] == far if "result" in v else True


def test_allocation_rows_have_texts(backend, persona):
    import dataclasses

    from rmprep.contracts import AllocationBand, Persona
    r = backend.decide(Persona.from_dict(persona), backend.list_snapshots()[0])
    oid = r.options[1].option.option_id
    r = dataclasses.replace(r, allocation=(
        AllocationBand("hisse", 40.0, 50.0, "Ata Yatırım, 28.04.2026", False, None, "ceiling"),
        AllocationBand("borclanma", 30.0, 40.0, "Ata Yatırım, 28.04.2026", False, oid, "")),
        allocation_notes=("not",))
    v = ViewBuilder(backend, load_config())(r)
    rows = v["allocation"]
    assert rows[0]["label"] == "Hisse" and rows[0]["note_text"] == "Risk tavanı nedeniyle uygun fon yok."
    assert rows[1]["option_id"] == oid and rows[1]["note_text"] == ""
    assert v["allocation_notes"] == ["not"]


SERIES = [
    {"key": "policy_rate", "quantity": "policy_rate", "entity": "CBRT policy rate (monthly, BIS)",
     "unit": "pct", "label": {"TR": "Politika faizi", "EN": "Policy rate"}},
    {"key": "usd_try", "quantity": "usd_try", "entity": "USD/TRY CBRT buying rate",
     "unit": "TRY", "label": {"TR": "USD/TRY (TCMB alış)", "EN": "USD/TRY (CBRT buying)"}},
    {"key": "nope", "quantity": "policy_rate", "entity": "no such entity",
     "unit": "pct", "label": {"TR": "Yok", "EN": "None"}},
]


def test_market_note_from_the_evidence(backend, persona):
    """W15: the EVDS market note of the dashboard; a missing series is left out."""
    from rmprep.contracts import Persona
    r = backend.decide(Persona.from_dict(persona), backend.list_snapshots()[0])
    v = ViewBuilder(backend, load_config(), market_series=SERIES)(r)
    keys = [m["key"] for m in v["market_note"]]
    assert keys == ["policy_rate", "usd_try"]
    ev = {d.id: d for d in backend.evidence(r.snapshot_id).datapoints}
    for m in v["market_note"]:
        d = ev[m["evidence_id"]]
        assert m["value"] == d.value and m["as_of"] == d.as_of.isoformat()
    assert v["market_note"][0]["label"] == "Politika faizi" and v["market_note"][0]["unit"] == "pct"


def test_no_market_series_no_note(view):
    assert view[1]["market_note"] == []


def test_priority_criteria_maps_boosts_and_skips_the_rest():
    from rmprep.api.views import priority_criteria
    got = priority_criteria(["düzenli gelir", "Likiditeyi koruma", "sınırlı dalgalanma",
                             "çeşitlendirme", "kur riskini yönetme", "bilinmeyen"], load_config())
    assert got == {"income": ["düzenli gelir"], "liquidity": ["Likiditeyi koruma"],
                   "risk_fit": ["sınırlı dalgalanma"]}


def test_market_note_last_change_only_while_the_value_is_the_same(backend, persona):
    """Policy rate (2026-10-14, the user's option A): the monthly BIS value is dated
    at the month end; the note "son değişiklik" shows the date of the last TCMB
    change, but only while the EVDS value equals the value of that change."""
    from rmprep.contracts import Persona
    r = backend.decide(Persona.from_dict(persona), backend.list_snapshots()[0])
    ev = {d.id: d for d in backend.evidence(r.snapshot_id).datapoints}
    first = ViewBuilder(backend, load_config(), market_series=SERIES[:1])(r)["market_note"][0]
    value = ev[first["evidence_id"]].value
    change = {"date": "2026-01-23", "value": value,
              "label": {"TR": "son değişiklik {date}", "EN": "last change {date}"}}
    same = [SERIES[0] | {"last_change": change}]
    v = ViewBuilder(backend, load_config(), market_series=same)(r)
    assert v["market_note"][0]["label"] == "Politika faizi (son değişiklik 23.01.2026)"
    other = [SERIES[0] | {"last_change": change | {"value": value + 1}}]
    v = ViewBuilder(backend, load_config(), market_series=other)(r)
    assert v["market_note"][0]["label"] == "Politika faizi"
