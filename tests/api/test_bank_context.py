"""W25: other banks' rates as context for the RM (config/bank_context.yaml), on
the option view only: not in the score."""

import dataclasses
from datetime import date, datetime
from pathlib import Path

import pytest
import yaml

from rmprep.api.views import ViewBuilder, bank_context, check_bank_context
from rmprep.contracts import TR_TZ, DataPoint, Persona
from rmprep.decision import load_config

ROOT = Path(__file__).resolve().parents[2]
OWN = "ING e-Vadeli Mevduat, 32-45 gün, 99.999,99-250.000 TL"
ISB = "İş Bankası kampanyalı vadeli TL, 32 - 35 Gün, 100.001 - 250.000 TL"
ZIR = "Ziraat Bankası vadeli TL (internet), 32 - 45 gün, 100.000 - 499.999,99 TL"


def real_config() -> dict:
    return check_bank_context(yaml.safe_load((ROOT / "config" / "bank_context.yaml")
                                             .read_text(encoding="utf-8")))


def dp(entity, value, source, as_of=date(2026, 10, 16), flags=()):
    return DataPoint.create(quantity="deposit_rate", entity=entity, value=value, unit="pct",
                            as_of=as_of, source=source, source_url="https://example.test/",
                            fetched_at=datetime(2026, 10, 16, 11, 35, tzinfo=TR_TZ),
                            snapshot_id="S1", raw_ref=f"S1/payloads/{source}/page.html",
                            flags=flags)


class Idx:
    def __init__(self, *rows):
        self.rows = {r.entity: r for r in rows}

    def get(self, quantity, entity):
        return self.rows.get(entity)


SPEC = real_config()["time_deposit:ing_e_vadeli"]


def test_the_real_config_names_the_engine_cell():
    """The own row is the cell the engine ranks (decision.yaml time_deposit)."""
    td = load_config(ROOT / "config" / "decision.yaml").raw["time_deposit"]
    assert SPEC["own"]["entity"] == f"{td['entity_prefix']}, {td['term']}, {td['tier']}"
    assert [b["entity"] for b in SPEC["banks"]] == [ISB, ZIR]


def test_rows_values_and_differences():
    got = bank_context(SPEC, Idx(dp(OWN, 34.5, "ing_web"), dp(ISB, 37.0, "isbank_web"),
                                 dp(ZIR, 31.0, "ziraat_web")), "TR")
    own, isb, zir = got["rows"]
    assert own["own"] and own["label"] == "ING e-Vadeli" and own["value"] == 34.5
    assert own["cell"] == "32-45 gün / 99.999,99-250.000 TL" and own["diff_pp"] is None
    assert isb["cell"] == "32 - 35 Gün / 100.001 - 250.000 TL" and isb["diff_pp"] == 2.5
    assert zir["label"] == "Ziraat (internet)" and zir["diff_pp"] == -3.5
    assert all(r["as_of"] == "2026-10-16" and r["evidence_id"] and not r["stale"]
               for r in got["rows"])
    assert got["note"].startswith("Bağlam: puana dahil değil.")
    assert bank_context(SPEC, Idx(), "EN")["note"].startswith("Context: not in the score.")


def test_missing_and_stale_rows():
    got = bank_context(SPEC, Idx(dp(OWN, 34.5, "ing_web"),
                                 dp(ZIR, 31.0, "ziraat_web", as_of=date(2026, 9, 1),
                                    flags=("stale",))), "TR")
    _, isb, zir = got["rows"]
    assert isb["value"] is None and isb["evidence_id"] == "" and isb["diff_pp"] is None
    assert zir["stale"] and zir["as_of"] == "2026-09-01" and zir["diff_pp"] == -3.5
    no_own = bank_context(SPEC, Idx(dp(ISB, 37.0, "isbank_web")), "TR")
    assert no_own["rows"][0]["value"] is None and no_own["rows"][1]["diff_pp"] is None


def test_no_spec_no_context():
    assert bank_context(None, Idx(), "TR") is None


@pytest.mark.parametrize("bad", [
    {"version": 1},
    {"version": 1, "options": {"x": {"own": {}, "banks": [], "note": {}}}},
    {"version": 1, "options": {"x": {"title": {"TR": "t", "EN": "t"},
        "own": {"label": {"TR": "a", "EN": "a"}, "quantity": "q", "entity": "no comma"},
        "banks": [{"label": {"TR": "b", "EN": "b"}, "quantity": "q", "entity": "B, c"}],
        "note": {"TR": "", "EN": ""}}}},
    {"version": 1, "options": {"x": {"title": {"TR": "t", "EN": "t"},
        "own": {"label": {"TR": "a", "EN": "a"}, "quantity": "q", "entity": "A, c"},
        "banks": [], "note": {"TR": "", "EN": ""}}}},
    {"version": 1, "options": {"x": {"title": {"TR": "t", "EN": "t"},
        "own": {"label": {"TR": "a", "EN": "a"}, "quantity": "q", "entity": "A, c", "extra": 1},
        "banks": [{"label": {"TR": "b", "EN": "b"}, "quantity": "q", "entity": "B, c"}],
        "note": {"TR": "", "EN": ""}}}},
])
def test_strict_config(bad):
    with pytest.raises(ValueError):
        check_bank_context(bad)


def test_option_view_has_the_context_only_on_the_configured_option(backend, persona):
    """The view of the run: only the configured option gets bank_context; the
    ranking (options, top) is the same with and without it. The fake runs have
    no e-Vadeli option, so the spec is put on the Turuncu option here."""
    r = backend.decide(Persona.from_dict(persona), backend.list_snapshots()[0])
    oid = "deposit:ing_turuncu"
    orig = backend.evidence

    def evidence(snapshot_id, exclude_sources=frozenset()):
        ev = orig(snapshot_id, exclude_sources)
        extra = (dp(OWN, 34.5, "ing_web"), dp(ISB, 37.0, "isbank_web"))
        return dataclasses.replace(ev, datapoints=ev.datapoints + extra)

    backend.evidence = evidence
    plain = ViewBuilder(backend, load_config())(r)
    with_ctx = ViewBuilder(backend, load_config(), bank_context={oid: SPEC})(r)
    assert plain["top"] == with_ctx["top"] and list(plain["options"]) == list(with_ctx["options"])
    assert oid in with_ctx["options"]
    for k, o in with_ctx["options"].items():
        assert plain["options"][k]["bank_context"] is None
        if k == oid:
            rows = o["bank_context"]["rows"]
            assert [x["value"] for x in rows] == [34.5, 37.0, None]
            assert rows[1]["evidence_id"] in {d.id for d in backend.evidence(r.snapshot_id).datapoints}
        else:
            assert o["bank_context"] is None


def test_strict_config_needs_the_title():
    raw = yaml.safe_load((ROOT / "config" / "bank_context.yaml").read_text(encoding="utf-8"))
    del raw["options"]["time_deposit:ing_e_vadeli"]["title"]
    with pytest.raises(ValueError):
        check_bank_context(raw)


def test_run_level_list_for_the_market_note(backend, persona):
    """W25b: the same rows once per run (the market note), also when the option is
    not shown; an empty list without the config."""
    r = backend.decide(Persona.from_dict(persona), backend.list_snapshots()[0])
    orig = backend.evidence

    def evidence(snapshot_id, exclude_sources=frozenset()):
        ev = orig(snapshot_id, exclude_sources)
        return dataclasses.replace(ev, datapoints=ev.datapoints + (dp(OWN, 34.5, "ing_web"),
                                                                   dp(ZIR, 31.0, "ziraat_web")))

    backend.evidence = evidence
    assert ViewBuilder(backend, load_config())(r)["bank_context"] == []
    v = ViewBuilder(backend, load_config(), bank_context=real_config())(r)
    assert "time_deposit:ing_e_vadeli" not in v["options"]
    [line] = v["bank_context"]
    assert line["option_id"] == "time_deposit:ing_e_vadeli"
    assert line["title"].startswith("Vadeli mevduat") and line["note"].startswith("Bağlam")
    assert [x["value"] for x in line["rows"]] == [34.5, None, 31.0]
    assert line["rows"][2]["diff_pp"] == -3.5
    en = ViewBuilder(backend, load_config(), lang="EN", bank_context=real_config())(r)
    assert en["bank_context"][0]["title"].startswith("Time deposit")
