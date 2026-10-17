"""W42: conflicting client information (fixed rules over the engine's reading)."""

import json
from pathlib import Path

import pytest

from rmprep.api.profile_checks import RULE_IDS, check, load_texts
from rmprep.api.views import ViewBuilder
from rmprep.contracts import Persona
from rmprep.decision import load_config

PROTO = Path(__file__).resolve().parents[2]
PERSONAS = PROTO / "tests" / "contracts" / "fixtures" / "personas"
TEXTS = load_texts(PROTO / "config" / "profile_checks.yaml")
CFG = load_config(PROTO / "config" / "decision.yaml")


def persona(pid="p01", **change) -> Persona:
    d = json.loads((PERSONAS / f"{pid}.json").read_text(encoding="utf-8"))
    return Persona.from_dict({**d, **change})


def ids(p: Persona) -> list[str]:
    return [f["id"] for f in check(p, CFG, TEXTS)]


@pytest.mark.parametrize("pid", ["p01", "p02", "p03", "p04", "p05"])
def test_the_five_clients_have_no_finding(pid):
    assert ids(persona(pid)) == []


def test_risk_vs_growth():
    p = persona("p01", oncelikler=["düzenli gelir", "uzun vadeli büyüme"])
    [f] = check(p, CFG, TEXTS)
    assert f["id"] == "risk_vs_growth" and f["kind"] == "conflict"
    assert f["fields"] == ["risk_profili", "oncelikler"]
    assert "Risk profili Muhafazakâr (fon riski en fazla 2 / 7)" in f["text"] and "uzun vadeli büyüme" in f["text"]
    assert "The risk profile is Muhafazakâr" in check(p, CFG, TEXTS, "EN")[0]["text"]


def test_aggressive_vs_protection():
    p = persona("p03", anapara_koruma_tercihi="Yüksek", acik_kisitlar=["yüksek riskli ürünlerden kaçınma"])
    [f] = check(p, CFG, TEXTS)
    assert f["id"] == "aggressive_vs_protection"
    assert "anapara koruma tercihi Yüksek" in f["text"] and "yüksek riskli ürünlerden kaçınma" in f["text"]


def test_liquidity_both_ways():
    assert "liquidity_low_vs_need" in ids(persona("p05", likidite_ihtiyaci="Düşük"))
    assert "liquidity_high_vs_no_need" in ids(persona("p03", likidite_ihtiyaci="Yüksek"))


def test_income_and_fx():
    assert ids(persona("p01", gelir_nakit_akisi_ihtiyaci="Düşük")) == ["income_low_vs_priority"]
    assert ids(persona("p02", doviz_maruz_kalma_tercihi="Açık")) == ["fx_open_vs_limit"]


def test_the_confirm_kinds():
    p = persona("p04", likidite_ihtiyaci="Yüksek")             # 5+ yıl
    [f] = check(p, CFG, TEXTS)
    assert (f["id"], f["kind"]) == ("long_horizon_high_liquidity", "confirm")
    q = persona("p03", yatirim_ufku="6 ay")                     # growth in a short time
    assert "short_horizon_growth" in ids(q)


def test_the_view_has_the_findings_and_teyit_edin(backend, client):
    p = next(x for x in client.get("/api/personas").json() if x["persona_id"] == "P01")
    edited = Persona.from_dict({**p, "oncelikler": ["uzun vadeli büyüme"]})
    r = backend.decide(edited, backend.list_snapshots()[0])
    v = ViewBuilder(backend, load_config(), profile_texts=TEXTS)(r)
    assert [f["id"] for f in v["profile_checks"]] == ["risk_vs_growth"]
    assert v["profile_checks"][0]["text"] in [c["text"] for c in v["to_confirm"]]
    plain = ViewBuilder(backend, load_config())(r)
    assert plain["profile_checks"] == []


def test_strict_texts(tmp_path):
    raw = (PROTO / "config" / "profile_checks.yaml").read_text(encoding="utf-8")
    f = tmp_path / "x.yaml"
    f.write_text(raw.replace("  short_horizon_growth:", "  other_rule:"), encoding="utf-8")
    with pytest.raises(ValueError):
        load_texts(f)
    f.write_text(raw.replace("kind: confirm", "kind: maybe", 1), encoding="utf-8")
    with pytest.raises(ValueError):
        load_texts(f)
    assert set(TEXTS) == set(RULE_IDS)
