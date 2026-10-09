"""Regenerate tests/contracts/fixtures/ (lead-owned; run from prototype/):

    .venv/Scripts/python -m tests.contracts.make_fixtures

- personas/: byte-exact copies of ../p0*.json (the hackathon input).
- evidence_small.json: a real EvidenceSet cut down to a few rows per quantity,
  from SNAPSHOT (data/snapshots/ must hold it; it is git-ignored).
- decision_*.json: ILLUSTRATIVE DecisionResults for the UI worker. The numbers
  are made up; only their shape and evidence ids are real. They change when
  step D fixes the decision rules.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
from datetime import datetime
from pathlib import Path

from rmprep.contracts import (
    TR_TZ,
    ClarificationQuestion,
    ConstraintResult,
    DataQualityNote,
    DecisionResult,
    DecisionState,
    DecisionWarning,
    EvidenceSet,
    ProductOption,
    RejectedOption,
    ScoredOption,
)
from rmprep.ingest.pipeline import build_evidence

PROTOTYPE = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "fixtures"
SNAPSHOT = "20261010-001233-6b20"
FUND_QUANTITIES = ("fund_price", "fund_return_1y", "fund_risk_level")


def _dump(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def small_evidence(ev: EvidenceSet) -> EvidenceSet:
    """Latest row per (source, quantity, entity) for non-fund quantities; for
    funds, three funds (risk levels 1, 4 and 7) with all FUND_QUANTITIES; plus
    every out_of_range row."""
    latest: dict[tuple, object] = {}
    for dp in ev.datapoints:
        key = (dp.source, dp.quantity, dp.entity)
        if key not in latest or dp.as_of > latest[key].as_of:
            latest[key] = dp
    by_fund: dict[str, dict] = {}
    for (src, q, ent), dp in latest.items():
        if q in FUND_QUANTITIES:
            by_fund.setdefault(ent, {})[q] = dp
    funds = []
    for level in (1.0, 4.0, 7.0):
        for ent in sorted(by_fund):
            f = by_fund[ent]
            if set(f) == set(FUND_QUANTITIES) and f["fund_risk_level"].value == level:
                funds.append(ent)
                break
    keep = [dp for (src, q, ent), dp in latest.items()
            if not q.startswith("fund_") or (ent in funds and q in FUND_QUANTITIES)]
    keep += [dp for dp in ev.datapoints if any(f.value == "out_of_range" for f in dp.flags)]
    rows = tuple(sorted({dp.id: dp for dp in keep}.values(), key=lambda d: d.id))
    return dataclasses.replace(ev, datapoints=rows)


def _pick(ev: EvidenceSet, quantity: str, entity: str | None = None) -> str:
    return next(dp.id for dp in ev.datapoints
                if dp.quantity == quantity and (entity is None or dp.entity == entity))


def decisions(ev: EvidenceSet) -> dict[str, DecisionResult]:
    level = {dp.entity: dp.value for dp in ev.datapoints if dp.quantity == "fund_risk_level"}
    low, mid, high = (min(e for e, v in level.items() if v == lv) for lv in (1.0, 4.0, 7.0))
    deposit = _pick(ev, "deposit_rate")
    usd = _pick(ev, "usd_try")
    t = datetime(2026, 10, 10, 9, 0, tzinfo=TR_TZ)
    common = dict(config_hash="draft-0000", created_at=t, snapshot_id=ev.snapshot_id,
                  excluded_sources=frozenset())
    opt_dep = ProductOption("deposit:manual", "deposit", "TL vadeli mevduat", "deposit_rate")
    opt_low = ProductOption(f"fund:{low}", "fund", f"Fon {low} (risk 1)", low)
    opt_mid = ProductOption(f"fund:{mid}", "fund", f"Fon {mid} (risk 4)", mid)
    opt_high = ProductOption(f"fund:{high}", "fund", f"Fon {high} (risk 7)", high)
    risk_ok = lambda e: ConstraintResult("risk_ceiling", True, "Risk level within the ceiling",  # noqa: E731
                                         (_pick(ev, "fund_risk_level", e),))
    high_rej = RejectedOption(opt_high, (ConstraintResult(
        "risk_ceiling", False, "Risk level 7 is above the client's ceiling",
        (_pick(ev, "fund_risk_level", high),)),))
    quality = DataQualityNote("EVDS series are not verified on the EVDS site yet",
                              ("unverified_series",), ("evds",), (usd,))
    p01 = DecisionResult(
        run_id="R20261010-090000-p01a", persona_id="P01", state=DecisionState.NEEDS_RM_INPUT,
        options=(
            ScoredOption(opt_dep, 0.71, {"income": 0.4, "capital_protection": 0.31}, (), 0.9, 0.8,
                         (deposit,)),
            ScoredOption(opt_low, 0.64, {"income": 0.3, "capital_protection": 0.34},
                         (risk_ok(low),), 0.7, 0.6, (_pick(ev, "fund_return_1y", low),)),
        ),
        rejected=(high_rej,),
        questions=(ClarificationQuestion(
            "q1", "Which share of the deposits may be moved out of the bank deposit?",
            "The persona says 'deposit-heavy' but gives no amount.", "durum",
            ("up to 25%", "25-50%", "more than 50%")),),
        assumptions=("No amount given: options are compared per 100 TL.",),
        warnings=(DecisionWarning("liquidity", "Fund redemption takes T+1 or more", ()),),
        data_quality=(quality,), **common)
    p03 = DecisionResult(
        run_id="R20261010-090000-p03a", persona_id="P03", state=DecisionState.READY,
        options=(
            ScoredOption(opt_high, 0.82, {"growth": 0.62, "diversification": 0.2},
                         (ConstraintResult("risk_ceiling", True, "Aggressive profile allows level 7",
                                           (_pick(ev, "fund_risk_level", high),)),),
                         0.75, 0.55, (_pick(ev, "fund_return_1y", high),)),
            ScoredOption(opt_mid, 0.66, {"growth": 0.41, "diversification": 0.25},
                         (risk_ok(mid),), 0.75, 0.7, (_pick(ev, "fund_return_1y", mid),)),
        ),
        questions=(ClarificationQuestion(
            "q1", "Is any of the cash needed within 12 months?",
            "acik_kisitlar says short-term need must not be assumed.", "acik_kisitlar[0]",
            ("no", "yes, part of it"), answer="no"),),
        assumptions=("Horizon 5+ years taken as 5 years for returns.",),
        warnings=(DecisionWarning("concentration", "Top option is a single equity fund", ()),),
        data_quality=(quality,), **common)
    return {"decision_p01_needs_input.json": p01, "decision_p03_ready.json": p03}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / "personas").mkdir(exist_ok=True)
    for p in sorted(PROTOTYPE.parent.glob("p0*.json")):
        shutil.copyfile(p, OUT / "personas" / p.name)
    ev = small_evidence(build_evidence(PROTOTYPE / "data" / "snapshots", SNAPSHOT))
    _dump(OUT / "evidence_small.json", ev.to_dict())
    for name, d in decisions(ev).items():
        _dump(OUT / name, d.to_dict())
    print(f"{len(ev.datapoints)} datapoints, funds:",
          sorted({dp.entity for dp in ev.datapoints if dp.quantity == "fund_risk_level"}))


if __name__ == "__main__":
    main()
