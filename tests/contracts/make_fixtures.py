"""Regenerate tests/contracts/fixtures/ (lead-owned; run from prototype/):

    .venv/Scripts/python -m tests.contracts.make_fixtures

- personas/: byte-exact copies of ../p0*.json (the hackathon input).
- evidence_small.json: a real EvidenceSet cut down to a few rows per quantity,
  from SNAPSHOT (data/snapshots/ must hold it; it is git-ignored).
- evidence_medium.json: real rows of about 40 funds of every fund kind, plus
  funds with an unknown risk, FX funds, small funds, Serbest funds and one fund
  without entity info (docs/decision.md section 8).
- entities: from build_evidence (ingest milestone I1).
- decision_*.json: ILLUSTRATIVE DecisionResults for the UI worker. The numbers
  are made up; their shape, ids and evidence ids are real.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
from datetime import datetime
from pathlib import Path

import yaml

from rmprep.contracts import (
    TR_TZ,
    ClarificationQuestion,
    ConstraintResult,
    DataQualityNote,
    DecisionResult,
    DecisionState,
    DecisionWarning,
    EntityInfo,
    EvidenceSet,
    Persona,
    ProductOption,
    RejectedOption,
    ScoredOption,
    TalkingPoint,
)
from rmprep.ingest.pipeline import build_evidence

PROTOTYPE = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "fixtures"
SNAPSHOT = "20261010-001233-6b20"
FUND_QUANTITIES = ("fund_price", "fund_return_1y", "fund_risk_level")
CONFIG = yaml.safe_load((PROTOTYPE / "config" / "decision.yaml").read_text(encoding="utf-8"))


def _dump(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def _latest(ev: EvidenceSet) -> dict[tuple, object]:
    latest: dict[tuple, object] = {}
    for dp in ev.datapoints:
        key = (dp.source, dp.quantity, dp.entity)
        if key not in latest or dp.as_of > latest[key].as_of:
            latest[key] = dp
    return latest


def _by_fund(latest: dict) -> dict[str, dict]:
    by_fund: dict[str, dict] = {}
    for (_src, q, ent), dp in latest.items():
        if q.startswith("fund_"):
            by_fund.setdefault(ent, {})[q] = dp
    return by_fund


def _cut(ev: EvidenceSet, latest: dict, funds: list[str], quantities, entities) -> EvidenceSet:
    keep = [dp for (_s, q, ent), dp in latest.items()
            if not q.startswith("fund_") or (ent in funds and (quantities is None or q in quantities))]
    keep += [dp for dp in ev.datapoints if any(f.value == "out_of_range" for f in dp.flags)]
    rows = tuple(sorted({dp.id: dp for dp in keep}.values(), key=lambda d: d.id))
    ents = {c: entities[c] for c in sorted(funds) if c in entities}
    return dataclasses.replace(ev, datapoints=rows, entities=ents)


def small_evidence(ev: EvidenceSet, entities: dict[str, EntityInfo]) -> EvidenceSet:
    """Latest row per (source, quantity, entity) for non-fund quantities; for
    funds, three funds (risk levels 1, 4 and 7) with all FUND_QUANTITIES; plus
    every out_of_range row."""
    latest = _latest(ev)
    by_fund = _by_fund(latest)
    funds = []
    for level in (1.0, 4.0, 7.0):
        for ent in sorted(by_fund):
            f = by_fund[ent]
            if set(FUND_QUANTITIES) <= set(f) and f["fund_risk_level"].value == level:
                funds.append(ent)
                break
    return _cut(ev, latest, funds, FUND_QUANTITIES, entities)


def _val(f: dict, q: str) -> float | None:
    dp = f.get(q)
    return None if dp is None else dp.value


def medium_evidence(ev: EvidenceSet, entities: dict[str, EntityInfo]) -> EvidenceSet:
    """All latest rows of the chosen funds; see the module docstring."""
    latest = _latest(ev)
    by_fund = _by_fund(latest)
    kinds = CONFIG["fund_kinds"]
    fx_words = CONFIG["fx_name_words"]

    def kind(c):
        return kinds.get(entities[c].category) if c in entities else None

    def fx(c):
        return c in entities and any(w in entities[c].name.upper() for w in fx_words)

    def big(c):
        return ((_val(by_fund[c], "fund_total_value") or 0) >= 1e8
                and (_val(by_fund[c], "fund_investor_count") or 0) >= 100)

    codes = sorted(by_fund)
    chosen: list[str] = []

    def take(pred, n):
        for c in codes:
            if n == 0:
                return
            if c not in chosen and pred(c):
                chosen.append(c)
                n -= 1

    for fk in sorted({v for v in kinds.values() if v}):
        seen_risk: set = set()
        for c in codes:
            f = by_fund[c]
            r = _val(f, "fund_risk_level")
            if (kind(c) == fk and r is not None and r not in seen_risk and not fx(c) and big(c)
                    and _val(f, "fund_return_3y") is not None):
                chosen.append(c)
                seen_risk.add(r)
            if len(seen_risk) == 4:
                break
    take(lambda c: kind(c) and _val(by_fund[c], "fund_risk_level") is None
         and _val(by_fund[c], "fund_total_value") is not None, 2)
    take(lambda c: kind(c) and fx(c) and _val(by_fund[c], "fund_risk_level") is not None, 2)
    take(lambda c: kind(c) and not big(c) and _val(by_fund[c], "fund_risk_level") is not None, 2)
    take(lambda c: kind(c) and big(c) and _val(by_fund[c], "fund_return_1y") is not None
         and _val(by_fund[c], "fund_return_3y") is None, 1)
    take(lambda c: c in entities and entities[c].category == "Serbest Şemsiye Fonu", 2)
    take(lambda c: c not in entities, 1)
    return _cut(ev, latest, chosen, None, entities)


# --- illustrative decisions ------------------------------------------------------

def _pick(ev: EvidenceSet, quantity: str, entity: str | None = None, source: str | None = None) -> str:
    return next(dp.id for dp in ev.datapoints
                if dp.quantity == quantity and (entity is None or dp.entity == entity)
                and (source is None or dp.source == source))


def _value(ev: EvidenceSet, quantity: str, entity: str) -> float | None:
    return next((dp.value for dp in ev.datapoints if dp.quantity == quantity and dp.entity == entity), None)


def _scored(opt, parts, ev, conf=0.9, stab=1.0, risk_ok=True):
    reasons = {k: f"(örnek) {k}" for k in parts}
    ids = []
    cons = ()
    if opt.kind == "fund":
        ids = [i for i in (_pick_opt(ev, "fund_return_1y", opt.entity),
                           _pick_opt(ev, "fund_risk_level", opt.entity)) if i]
        risk = _pick_opt(ev, "fund_risk_level", opt.entity)
        if risk_ok:
            cons = (ConstraintResult("risk_ceiling", True, "(örnek) risk tavan içinde",
                                     (risk,) if risk else ()),)
    else:
        ids = [_pick(ev, "deposit_rate", opt.entity, "manual")]
    score = sum(parts.values())
    return ScoredOption(opt, score, parts, cons, conf, stab, tuple(ids), reasons)


def _pick_opt(ev, quantity, entity):
    return next((dp.id for dp in ev.datapoints if dp.quantity == quantity and dp.entity == entity), None)


def decisions(ev: EvidenceSet, personas: dict[str, Persona]) -> dict[str, DecisionResult]:
    kinds = CONFIG["fund_kinds"]
    fx_words = CONFIG["fx_name_words"]

    def fund(code):
        e = ev.entities[code]
        return ProductOption(f"fund:{code}", "fund", e.name, code, kinds[e.category],
                             any(w in e.name.upper() for w in fx_words))

    def first(pred):
        return next(c for c in sorted(ev.entities) if kinds.get(ev.entities[c].category) and pred(c))

    risk = lambda c: _value(ev, "fund_risk_level", c)  # noqa: E731
    kind = lambda c: kinds.get(ev.entities[c].category)  # noqa: E731
    mm = first(lambda c: kind(c) == "money_market")
    debt = first(lambda c: kind(c) == "debt" and risk(c) == 2)
    var4 = first(lambda c: kind(c) == "variable" and risk(c) is not None and risk(c) <= 5)
    eq6 = first(lambda c: kind(c) == "equity" and risk(c) == 6)
    pm = first(lambda c: kind(c) == "precious_metals")
    fxf = first(lambda c: fund(c).fx and risk(c) is not None and risk(c) <= 5)
    unknown = first(lambda c: risk(c) is None)

    dep_entity = f"{CONFIG['deposit']['entity_prefix']}, {CONFIG['deposit']['tier']}"
    dep = ProductOption(CONFIG["deposit"]["option_id"], "deposit", CONFIG["deposit"]["label"], dep_entity)
    dep_id = _pick(ev, "deposit_rate", dep_entity, "manual")
    market_id = _pick(ev, "deposit_rate", CONFIG["deposit"]["market_entity"], "evds")
    t = datetime(2026, 10, 10, 9, 0, tzinfo=TR_TZ)
    common = dict(config_hash="example00000", created_at=t, snapshot_id=ev.snapshot_id,
                  excluded_sources=frozenset())
    needs_check = [dp.id for dp in ev.datapoints if any(f.value == "needs_check" for f in dp.flags)]
    quality = DataQualityNote(f"tefas_web: {len(needs_check)} değer \"needs_check\" işaretli.",
                              ("needs_check",), ("tefas_web",), tuple(sorted(needs_check)[:3]))
    removed = DataQualityNote("2 serbest fon çıkarıldı (yalnızca nitelikli yatırımcılar).")
    assumptions = (CONFIG["texts"]["assumptions"]["past_returns"],
                   CONFIG["texts"]["assumptions"]["pre_tax"])
    dep_warn = DecisionWarning("deposit_vs_market", "(örnek) ING standart oranı piyasa ortalamasının altında.",
                               (dep_id, market_id))

    p02 = DecisionResult(
        run_id="R02examp1e0", persona=personas["P02"], state=DecisionState.READY,
        options=(
            _scored(dep, {"return": 0.05, "liquidity": 0.15, "income": 0.12, "principal": 0.1}, ev),
            _scored(fund(debt), {"return": 0.2, "liquidity": 0.1, "income": 0.06, "principal": 0.06}, ev),
            _scored(fund(mm), {"return": 0.12, "liquidity": 0.14, "income": 0.07, "principal": 0.08}, ev),
            _scored(fund(fxf), {"return": 0.25, "liquidity": 0.1, "income": 0.05,
                                "penalty:fx_exposure": -0.15}, ev, stab=0.42),
            _scored(fund(var4), {"return": 0.18, "liquidity": 0.07, "income": 0.02,
                                 "principal": 0.01}, ev, stab=0.7),
        ),
        rejected=(RejectedOption(fund(eq6), (ConstraintResult(
            "risk_ceiling", False, "Risk değeri 6, müşterinin risk tavanı 5 üzerinde.",
            (_pick(ev, "fund_risk_level", eq6),)),)),),
        questions=(ClarificationQuestion(
            "q:doviz_maruz_kalma_tercihi", CONFIG["texts"]["questions"]["doviz_maruz_kalma_tercihi"],
            "\"Mevcut döviz gelirini dikkate alarak kontrollü\" metni tanımlı değerlerle eşleşmiyor.",
            "doviz_maruz_kalma_tercihi", tuple(CONFIG["fx_levels"]), blocking=False),),
        assumptions=assumptions + ("\"doviz_maruz_kalma_tercihi\" için güvenli düzey \"Sınırlı\" varsayıldı.",),
        warnings=(dep_warn,
                  DecisionWarning("fx_exposure", CONFIG["texts"]["warnings"]["fx_exposure"],
                                  (), (f"fund:{fxf}",), audience="client"),
                  DecisionWarning("no_fx_deposit_data", CONFIG["texts"]["warnings"]["no_fx_deposit_data"])),
        data_quality=(quality, removed),
        # v1.3 (illustrative): one talking point and one item to confirm
        talking_points=(TalkingPoint(
            "risk_fit", "Risk", "en fazla 4 / 7",
            "İlk üç önerinin SPK risk değeri en fazla 4 / 7; müşterinin sınırı 5 / 7.",
            (_pick(ev, "fund_risk_level", debt),)),),   # no option_ids: ui tests swap the options
        to_confirm=("Yatırım tutarını sorun: 100.000–249.999 TL dilimi varsayıldı.",),
        **common)

    p03 = DecisionResult(
        run_id="R03examp1e0", persona=personas["P03"], state=DecisionState.READY,
        options=(
            _scored(dep, {"return": 0.1, "quality": 0.11}, ev),
            _scored(fund(eq6), {"return": 0.8, "quality": 0.08}, ev),
            _scored(fund(pm), {"return": 0.75, "quality": 0.09}, ev),
            _scored(fund(unknown), {"return": 0.85, "quality": 0.05, "penalty:risk_unknown": -0.3},
                    ev, conf=0.63, stab=0.35, risk_ok=False),
            _scored(fund(var4), {"return": 0.5, "quality": 0.07}, ev),
        ),
        assumptions=assumptions,
        warnings=(dep_warn,),
        data_quality=(quality, removed), **common)

    edited = dataclasses.replace(personas["P01"], acik_kisitlar=("bilinmeyen bir kısıt",))
    test_needs = DecisionResult(
        run_id="R01examp1e1", persona=edited, state=DecisionState.NEEDS_RM_INPUT,
        questions=(ClarificationQuestion(
            "q:acik_kisitlar[0]",
            CONFIG["texts"]["questions"]["acik_kisitlar"].format(text="bilinmeyen bir kısıt"),
            "\"bilinmeyen bir kısıt\" metni tanımlı değerlerle eşleşmiyor.", "acik_kisitlar[0]",
            tuple(CONFIG["texts"]["effect_labels"].values())),),
        assumptions=assumptions, data_quality=(quality,), **common)
    return {"decision_p02_ready.json": p02, "decision_p03_ready.json": p03,
            "decision_test_needs_input.json": test_needs}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / "personas").mkdir(exist_ok=True)
    for old in OUT.glob("decision_*.json"):
        old.unlink()
    personas = {}
    for p in sorted(PROTOTYPE.parent.glob("p0*.json")):
        shutil.copyfile(p, OUT / "personas" / p.name)
        persona = Persona.from_dict(json.loads(p.read_text(encoding="utf-8")))
        personas[persona.persona_id] = persona
    full = build_evidence(PROTOTYPE / "data" / "snapshots", SNAPSHOT)
    entities = dict(full.entities)
    small = small_evidence(full, entities)
    medium = medium_evidence(full, entities)
    _dump(OUT / "evidence_small.json", small.to_dict())
    _dump(OUT / "evidence_medium.json", medium.to_dict())
    for name, d in decisions(medium, personas).items():
        _dump(OUT / name, d.to_dict())
    funds = sorted({dp.entity for dp in medium.datapoints if dp.quantity == "fund_price"})
    print(f"small: {len(small.datapoints)} rows; medium: {len(medium.datapoints)} rows, "
          f"{len(funds)} funds, {len(medium.entities)} with entity info")


if __name__ == "__main__":
    main()
