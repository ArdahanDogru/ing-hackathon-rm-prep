"""Warnings and data-quality notes of a result (docs/decision.md section 6)."""

from __future__ import annotations

import dataclasses
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence

from rmprep.contracts import (
    ClarificationQuestion,
    DataPoint,
    DataQualityNote,
    DecisionWarning,
    EvidenceSet,
    Flag,
    ScoredOption,
)
from rmprep.decision.config import RM_ONLY_WARNINGS, DecisionConfig
from rmprep.decision.persona import Levels
from rmprep.decision.universe import EvidenceIndex, Universe
from rmprep.grouping import group_key

# No source gives an FX deposit rate yet; a row of this quantity would.
FX_DEPOSIT_QUANTITY = "fx_deposit_rate"
_FX_FIELD = "doviz_maruz_kalma_tercihi"
_FX_SAFE_LEVEL = "Sınırlı"
_NOT_USED = (Flag.OUT_OF_RANGE, Flag.MISSING)


def build_warnings(options: Sequence[ScoredOption], levels: Levels,
                   questions: Sequence[ClarificationQuestion], evidence: EvidenceSet,
                   config: DecisionConfig, risk_estimates: Mapping[str, int] = {},
                   real_inputs: Sequence[DataPoint] = (),
                   recommended: Sequence[str] = (),
                   ) -> tuple[DecisionWarning, ...]:
    """risk_estimates: option_id -> estimated risk, for funds without a risk level;
    real_inputs: the stopaj and CPI rows the scored options used for a real return (D22);
    recommended: the result's recommended option ids (low_stability, D25)."""
    c = config.raw
    tpl = c["texts"]["warnings"]
    d = c["display"]
    funds = [o for o in options if o.option.kind != "deposit"]     # ranked options
    short = funds[:d["shortlist"]]
    first = funds[:d["first"]]
    out: list[DecisionWarning] = []

    # concentration: with the greedy order a cap is broken only when it could not be met
    cap = d["diversity_cap"] if levels.diversity else d["cap"]
    checks = [(d["shortlist"], short, cap)]
    if levels.diversity and "pool" in d:
        checks.append((d["pool"], funds[:d["pool"]], d["diversity_pool_cap"]))
    checks.append((d["first"], first, d["first_cap"]))
    for n, rows, limit in checks:
        counts = Counter(group_key(o) for o in rows)
        over = sorted((k, v) for k, v in counts.items() if v > limit)
        for kind, count in over:
            out.append(DecisionWarning(
                code="concentration",
                message=tpl["concentration"].format(n=n, kind=kind, count=count),
                option_ids=tuple(o.option.option_id for o in rows
                                 if group_key(o) == kind)))
        if over:
            break

    fx = [o for o in short if o.option.fx]
    if fx and levels.fx_intensity > 0:
        out.append(DecisionWarning(code="fx_exposure", message=tpl["fx_exposure"],
                                   option_ids=tuple(o.option.option_id for o in fx)))

    estimated = [o for o in short
                 if risk_estimates.get(o.option.option_id, 0) > levels.ceiling]
    if estimated:
        out.append(DecisionWarning(code="risk_estimate", message=tpl["risk_estimate"],
                                   option_ids=tuple(o.option.option_id for o in estimated)))

    # D25: every recommended option, wherever it is in the display order
    below = c["warnings"]["low_stability_below"]
    by_id = {o.option.option_id: o for o in options}
    for o in (by_id[oid] for oid in recommended):
        if o.stability < below:
            out.append(DecisionWarning(
                code="low_stability", message=tpl["low_stability"].format(stability=o.stability),
                option_ids=(o.option.option_id,)))

    idx = EvidenceIndex(evidence)
    dep = c["deposit"]
    ing = idx.get(dep["quantity"], f"{dep['entity_prefix']}, {dep['tier']}")
    market = idx.get(dep["quantity"], dep["market_entity"])
    if ing is not None and market is not None:
        diff = market.value - ing.value
        if diff > c["warnings"]["deposit_vs_market_points"]:
            on = tuple(o.option.option_id for o in options if o.option.kind == "deposit")
            out.append(DecisionWarning(
                code="deposit_vs_market",
                message=tpl["deposit_vs_market"].format(ing=ing.value, market=market.value,
                                                        diff=diff),
                evidence_ids=tuple(sorted((ing.id, market.id))), option_ids=on))

    fx_question = any(q.about == _FX_FIELD for q in questions)
    has_fx_rate = any(r.quantity == FX_DEPOSIT_QUANTITY and not (r.flags & set(_NOT_USED))
                      for r in idx.rows)
    if (fx_question or levels.fx_level != _FX_SAFE_LEVEL) and not has_fx_rate:
        out.append(DecisionWarning(code="no_fx_deposit_data", message=tpl["no_fx_deposit_data"]))

    shares = [oid for oid in recommended if by_id[oid].option.kind == "stock"]
    if shares and "single_stock" in tpl:            # D26: one company in the top 3
        out.append(DecisionWarning(code="single_stock", message=tpl["single_stock"],
                                   option_ids=tuple(shares)))

    stale = sorted({r.id: r for r in real_inputs if Flag.STALE in r.flags}.values(),
                   key=lambda r: r.id)
    if stale and "stale_tax_input" in tpl:
        out.append(DecisionWarning(
            code="stale_tax_input",
            message=tpl["stale_tax_input"].format(
                entities=", ".join(sorted({r.entity for r in stale}))),
            evidence_ids=tuple(r.id for r in stale)))
    # audience (D16): config warnings.audience; a code not in the table is for the RM
    audience = c["warnings"].get("audience", {})
    return tuple(dataclasses.replace(
        w, audience="rm" if w.code in RM_ONLY_WARNINGS else audience.get(w.code, "rm"))
        for w in out)


def source_notes(evidence: EvidenceSet, config: DecisionConfig) -> list[DataQualityNote]:
    tpl = config.raw["texts"]["data_quality"]
    out = [DataQualityNote(message=tpl["excluded"].format(source=s), sources=(s,))
           for s in sorted(evidence.excluded_sources)]
    for name, st in sorted(evidence.source_status.items()):
        if st.status == "failed":
            out.append(DataQualityNote(
                message=tpl["failed"].format(source=name, error=st.error or ""), sources=(name,)))
        if st.fallback_from:
            out.append(DataQualityNote(
                message=tpl["fallback"].format(source=name, snapshot=st.fallback_from),
                flags=(Flag.FALLBACK_SNAPSHOT.value,), sources=(name,)))
    return out


def build_notes(used_ids: frozenset[str], universe: Universe, evidence: EvidenceSet,
                config: DecisionConfig, stopaj_missing: Mapping[str, int] = {},
                valor_missing: int = 0) -> tuple[DataQualityNote, ...]:
    """stopaj_missing: stopaj entity -> count of options scored with stopaj 0;
    valor_missing: scored funds the liquidity_need rule could not test (D13)."""
    tpl = config.raw["texts"]["data_quality"]
    by_flag: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in evidence.datapoints:
        if row.id in used_ids:
            for flag in row.sorted_flags():
                by_flag[(row.source, flag)].append(row.id)
    out = [DataQualityNote(message=tpl["flag_count"].format(source=s, count=len(ids), flag=f),
                           flags=(f,), sources=(s,), evidence_ids=tuple(sorted(ids)))
           for (s, f), ids in sorted(by_flag.items())]
    out += source_notes(evidence, config)
    if universe.out_of_range:
        out.append(DataQualityNote(
            message=tpl["out_of_range"].format(count=len(universe.out_of_range)),
            flags=(Flag.OUT_OF_RANGE.value,), evidence_ids=universe.out_of_range))
    rr = config.raw.get("real_return")
    if rr is not None and universe.cpi is None:
        out.append(DataQualityNote(
            message=tpl["cpi_missing"].format(entity=rr["cpi"]["entity"]),
            sources=(rr["cpi"]["source"],)))
    for entity, count in sorted(stopaj_missing.items()):
        out.append(DataQualityNote(
            message=tpl["stopaj_missing"].format(entity=entity, count=count),
            sources=(rr["stopaj"]["source"],)))
    if "underperformance" in config.raw["penalties"] and universe.market_rate is None:
        out.append(DataQualityNote(message=tpl["benchmark_missing"].format(
            entity=config.raw["deposit"]["market_entity"])))
    fd = config.raw.get("fund_detail")
    if fd is not None:
        missing = sum(1 for cand in universe.candidates if cand.option.kind == "fund"
                      and fd["buyable_quantity"] not in cand.values)
        if missing:
            out.append(DataQualityNote(message=tpl["buyable_missing"].format(count=missing)))
    if universe.removed_no_data:
        out.append(DataQualityNote(message=tpl["removed_no_data"].format(
            count=len(universe.removed_no_data))))
    if valor_missing:
        out.append(DataQualityNote(message=tpl["valor_missing"].format(count=valor_missing)))
    if universe.missing_time_deposit is not None:
        td = config.raw["time_deposit"]
        out.append(DataQualityNote(
            message=tpl["time_deposit_missing"].format(entity=universe.missing_time_deposit),
            sources=(td["source"],)))
    if "excluded_exchange_groups" in tpl and any(
            cand.option.kind in ("etf", "stock") for cand in universe.candidates):
        out.append(DataQualityNote(message=tpl["excluded_exchange_groups"]))   # D26
    removed = universe.removed_stock_market
    if removed:                                                     # D26b
        out.append(DataQualityNote(message=tpl["removed_stock_market"].format(
            count=sum(len(v) for v in removed.values()), markets=", ".join(removed))))
    for text, ids in universe.unknown_holding_types.items():     # D23, sorted by text
        out.append(DataQualityNote(
            message=tpl["unknown_holding_type"].format(text=text, count=len(ids)),
            evidence_ids=ids))
    for key, codes in (("removed_serbest", universe.removed_serbest),
                       ("removed_no_entity", universe.removed_no_entity),
                       ("removed_unknown_kind", universe.removed_unknown_kind)):
        if codes:
            out.append(DataQualityNote(message=tpl[key].format(count=len(codes))))
    return tuple(out)
