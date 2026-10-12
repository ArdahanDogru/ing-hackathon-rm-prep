"""Product universe and evidence lookup (docs/decision.md section 1).

Lookup: for each (quantity, entity) the row with the latest `as_of` whose
source is not excluded. If that row has `out_of_range` or `missing`, the value
counts as missing (an older row is not used instead). Entity info from an
excluded source counts as absent.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from rmprep.contracts import DataPoint, EvidenceSet, Flag, ProductOption
from rmprep.decision.config import DecisionConfig

FUND_PREFIX = "fund_"
_BAD = (Flag.OUT_OF_RANGE, Flag.MISSING)


class EvidenceIndex:
    """Latest usable row per (quantity, entity) of one EvidenceSet."""

    def __init__(self, evidence: EvidenceSet) -> None:
        excluded = evidence.excluded_sources
        self.rows = tuple(d for d in evidence.datapoints if d.source not in excluded)
        latest: dict[tuple[str, str], DataPoint] = {}
        # Same as_of from two sources: the source name decides, so the result
        # does not depend on the row order.
        for d in sorted(self.rows, key=lambda d: (d.as_of, d.source)):
            latest[(d.quantity, d.entity)] = d
        self._latest = latest

    def get(self, quantity: str, entity: str) -> DataPoint | None:
        d = self._latest.get((quantity, entity))
        if d is None or any(f in d.flags for f in _BAD):
            return None
        return d

    def quantities_of(self, entity: str) -> dict[str, DataPoint]:
        out = {}
        for (q, e) in self._latest:
            if e == entity and (d := self.get(q, e)) is not None:
                out[q] = d
        return out


def latest(evidence: EvidenceSet, quantity: str, entity: str) -> DataPoint | None:
    return EvidenceIndex(evidence).get(quantity, entity)


@dataclass(frozen=True)
class Candidate:
    option: ProductOption
    values: Mapping[str, DataPoint]     # quantity -> row used; missing quantities absent


@dataclass(frozen=True)
class Universe:
    candidates: tuple[Candidate, ...]   # deposit, time deposit (if any), funds by option_id
    removed_serbest: tuple[str, ...] = ()       # fund codes, sorted
    removed_no_entity: tuple[str, ...] = ()
    removed_unknown_kind: tuple[str, ...] = ()
    out_of_range: tuple[str, ...] = ()          # ids of out_of_range rows ignored, sorted
    market_rate: DataPoint | None = None        # EVDS deposit rate (benchmark only)
    missing_time_deposit: str | None = None     # entity of a configured time deposit w/o row
    cpi: DataPoint | None = None                # annual CPI row (real_return configured)
    stopaj: Mapping[str, DataPoint] = field(default_factory=dict)   # entity -> stopaj row
    removed_no_data: tuple[str, ...] = ()       # funds without a row the engine uses (D15)
    by_id: Mapping[str, Candidate] = field(default_factory=dict)


def _used_quantities(config: DecisionConfig):
    """Predicate: is a fund quantity one the engine scores with?"""
    fd = config.raw.get("fund_detail", {})
    fixed = {"fund_risk_level", "fund_total_value", "fund_investor_count",
             *(v for k, v in fd.items() if k.endswith("_quantity"))}
    return lambda q: q in fixed or q.startswith("fund_return_")


def stopaj_entity(option: ProductOption, config: DecisionConfig) -> str:
    """withholding_tax_rate entity of an option (real_return.stopaj)."""
    st = config.raw["real_return"]["stopaj"]
    if option.kind in ("deposit", "time_deposit"):
        return st[option.kind]
    return st.get("fund_by_kind", {}).get(option.fund_kind, st["fund_default"])


def stopaj_entities(config: DecisionConfig) -> list[str]:
    st = config.raw["real_return"]["stopaj"]
    return [st["deposit"], st["time_deposit"], st["fund_default"],
            *st.get("fund_by_kind", {}).values()]


def asset_class(kind: str, fund_kind: str, name: str, fx: bool,
                config: DecisionConfig, risk: float | None = None) -> str:
    """Asset class of an option (config asset_classes, D19): an FX fund -> fx;
    then by_name (Turkish upper case, whole words); then by_risk (D19c: the
    fund's SPK risk row, first rule with risk >= min_risk; an estimated risk
    does not count); then by_kind. "" without the section."""
    ac = config.raw.get("asset_classes")
    if ac is None:
        return ""
    if kind == "fund":
        if fx:
            return ac["fx"]
        upper = _tr_upper(name)
        for phrase, cls in ac["by_name"].items():
            if re.search(r"(?<!\w)" + re.escape(_tr_upper(phrase)) + r"(?!\w)", upper):
                return cls
        if risk is not None:
            for rule in ac.get("by_risk", {}).get(fund_kind, ()):
                if risk >= rule["min_risk"]:
                    return rule["class"]
        return ac["by_kind"][fund_kind]
    return ac["by_kind"][kind]


def _tr_upper(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def build_universe(evidence: EvidenceSet, config: DecisionConfig) -> Universe:
    c = config.raw
    idx = EvidenceIndex(evidence)
    candidates: list[Candidate] = []

    dep = c["deposit"]
    rate = idx.get(dep["quantity"], f"{dep['entity_prefix']}, {dep['tier']}")
    if rate is not None:
        option = ProductOption(option_id=dep["option_id"], kind="deposit", label=dep["label"],
                               entity=rate.entity,
                               asset_class=asset_class("deposit", "", "", False, config))
        candidates.append(Candidate(option, {dep["quantity"]: rate}))

    missing_td = None
    td = c.get("time_deposit")
    if td is not None:
        entity = f"{td['entity_prefix']}, {td['term']}, {td['tier']}"
        rate = idx.get(td["quantity"], entity)
        if rate is None:
            missing_td = entity
        else:
            option = ProductOption(option_id=td["option_id"], kind="time_deposit",
                                   label=f"{td['label']} ({td['term']})", entity=entity,
                                   asset_class=asset_class("time_deposit", "", "", False,
                                                           config))
            candidates.append(Candidate(option, {td["quantity"]: rate}))

    cpi, stopaj = None, {}
    rr = c.get("real_return")
    if rr is not None:
        cpi = idx.get(rr["cpi"]["quantity"], rr["cpi"]["entity"])
        for entity in stopaj_entities(config):
            row = idx.get(rr["stopaj"]["quantity"], entity)
            if row is not None:
                stopaj[entity] = row

    entities = {k: v for k, v in evidence.entities.items()
                if v.source not in evidence.excluded_sources}
    fund_codes = sorted({d.entity for d in idx.rows if d.quantity.startswith(FUND_PREFIX)})
    serbest, no_entity, unknown, no_data = [], [], [], []
    used = _used_quantities(config) if "short_history" in c else None
    fx_words = [_tr_upper(w) for w in c["fx_name_words"]]
    for code in fund_codes:
        info = entities.get(code)
        if info is None:
            no_entity.append(code)
            continue
        if info.category not in c["fund_kinds"]:
            unknown.append(code)
            continue
        kind = c["fund_kinds"][info.category]
        if kind is None:
            serbest.append(code)
            continue
        name = _tr_upper(info.name)
        values = {q: d for q, d in idx.quantities_of(code).items() if q.startswith(FUND_PREFIX)}
        risk_row = values.get("fund_risk_level")
        fx = any(w in name for w in fx_words)
        option = ProductOption(option_id=f"fund:{code}", kind="fund", label=info.name,
                               entity=code, fund_kind=kind, fx=fx,
                               asset_class=asset_class("fund", kind, info.name, fx, config,
                                                   risk_row.value if risk_row else None))
        if used is not None and not any(used(q) for q in values):
            no_data.append(code)        # never listed: nothing to show as evidence
            continue
        candidates.append(Candidate(option, values))

    return Universe(
        candidates=tuple(candidates),
        removed_serbest=tuple(serbest),
        removed_no_entity=tuple(no_entity),
        removed_unknown_kind=tuple(unknown),
        removed_no_data=tuple(no_data),
        out_of_range=tuple(sorted(d.id for d in idx.rows if Flag.OUT_OF_RANGE in d.flags)),
        market_rate=idx.get("deposit_rate", dep["market_entity"]),
        missing_time_deposit=missing_td,
        cpi=cpi,
        stopaj=stopaj,
        by_id={cand.option.option_id: cand for cand in candidates},
    )
