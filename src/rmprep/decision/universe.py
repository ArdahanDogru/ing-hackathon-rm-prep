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
from rmprep.decision.exchange import (
    ETF,
    EXCHANGE_KINDS,
    STOCK,
    STOCK_PREFIX,
    STOCK_TURNOVER,
    STOCK_VOLATILITY,
    market_of,
    name_class,
)
from rmprep.decision.text import fold

FUND_PREFIX = "fund_"
# ingest I8: one row per holding, entity "<fund code>/<kiymetTip>", value = share %
HOLDINGS_QUANTITY = "fund_holding_share"
MIXED_CLASS = "dengeli"     # no class reaches by_holdings.min_share (D23)
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
        # Speed (2026-10-17): quantities_of scanned every key for each entity (1,442
        # calls x ~30,000 keys, ~10 s per run); the same rows, in the same order, by entity
        by_entity: dict[str, list[str]] = {}
        for (q, e) in latest:
            by_entity.setdefault(e, []).append(q)
        self._by_entity = by_entity

    def get(self, quantity: str, entity: str) -> DataPoint | None:
        d = self._latest.get((quantity, entity))
        if d is None or any(f in d.flags for f in _BAD):
            return None
        return d

    def quantities_of(self, entity: str) -> dict[str, DataPoint]:
        out = {}
        for q in self._by_entity.get(entity, ()):
            if (d := self.get(q, entity)) is not None:
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
    # D23: option_id -> the holdings that decided its class; kiymetTip text not in
    # by_holdings.labels -> ids of its rows (funds whose holdings were read)
    holdings_class: Mapping[str, HoldingsClass] = field(default_factory=dict)
    unknown_holding_types: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    # D26b: market code -> the share codes removed by stock.exclude_markets
    removed_stock_market: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class HoldingsClass:
    asset_class: str
    share: float                    # % of the counted holdings
    evidence_ids: tuple[str, ...]   # the rows of that class, sorted


@dataclass(frozen=True)
class Holdings:
    """The holdings of one fund on its latest day, by class (by_holdings.labels)."""
    shares: Mapping[str, float]                 # class -> % of the counted total
    ids: Mapping[str, tuple[str, ...]]          # class -> row ids (positive shares)
    unknown: Mapping[str, tuple[str, ...]]      # text not in the labels -> row ids

    def majority(self, min_share: float) -> str | None:
        """The class with >= min_share; MIXED_CLASS if none; None without counted rows."""
        if not self.shares:
            return None
        top, share = max(self.shares.items(), key=lambda kv: (kv[1], kv[0]))
        return top if share >= min_share else MIXED_CLASS


def holdings_of(rows: list[DataPoint], config: DecisionConfig) -> Holdings:
    """rows: the holdings rows of one fund (any days); only the latest day counts.
    Positive shares only, without the ignore group; an unknown text is ignored."""
    labels = config.raw["asset_classes"]["by_holdings"]["labels"]
    lookup = {fold(text): cls for cls, texts in labels.items() for text in texts}
    last = max((r.as_of for r in rows), default=None)
    sums: dict[str, float] = {}
    ids: dict[str, list[str]] = {}
    unknown: dict[str, list[str]] = {}
    for r in rows:
        if r.as_of != last:
            continue
        text = r.entity.split("/", 1)[1]
        cls = lookup.get(fold(text))
        if cls is None:
            unknown.setdefault(text, []).append(r.id)
        elif cls != "ignore" and r.value > 0:
            sums[cls] = sums.get(cls, 0.0) + r.value
            ids.setdefault(cls, []).append(r.id)
    total = sum(sums.values())
    return Holdings(shares={k: 100 * v / total for k, v in sums.items()} if total else {},
                    ids={k: tuple(sorted(v)) for k, v in ids.items()},
                    unknown={k: tuple(sorted(v)) for k, v in unknown.items()})


def _used_quantities(config: DecisionConfig):
    """Predicate: is a fund (or share, D26) quantity one the engine scores with?"""
    fd = config.raw.get("fund_detail", {})
    fixed = {"fund_risk_level", "fund_total_value", "fund_investor_count",
             STOCK_VOLATILITY, STOCK_TURNOVER,
             *(v for k, v in fd.items() if k.endswith("_quantity"))}
    return lambda q: (q in fixed or q.startswith("fund_return_")
                      or q.startswith("stock_return_"))


def stopaj_entity(option: ProductOption, config: DecisionConfig) -> str:
    """withholding_tax_rate entity of an option (real_return.stopaj); an ETF or a
    share without its own key (D26) uses fund_default."""
    st = config.raw["real_return"]["stopaj"]
    if option.kind in ("deposit", "time_deposit"):
        return st[option.kind]
    if option.kind in EXCHANGE_KINDS:
        return st.get(option.kind, st["fund_default"])
    return st.get("fund_by_kind", {}).get(option.fund_kind, st["fund_default"])


def stopaj_entities(config: DecisionConfig) -> list[str]:
    st = config.raw["real_return"]["stopaj"]
    return [st["deposit"], st["time_deposit"], st["fund_default"],
            *st.get("fund_by_kind", {}).values(),
            *(st[k] for k in EXCHANGE_KINDS if k in st)]


def asset_class(kind: str, fund_kind: str, name: str, fx: bool,
                config: DecisionConfig, risk: float | None = None,
                holdings: Holdings | None = None) -> str:
    """Asset class of an option (config asset_classes, D19): an FX fund -> fx;
    then (D23) an fx majority of the holdings of a by_holdings.fx_debt_kinds
    fund; then by_name (Turkish upper case, whole words); then (D23) the
    holdings majority of a by_holdings.kinds fund (a fon majority or no counted
    rows: go on); then by_risk (D19c: the fund's SPK risk row, first rule with
    risk >= min_risk; an estimated risk does not count); then by_kind. "" without
    the section."""
    return _classify(kind, fund_kind, name, fx, config, risk, holdings)[0]


def _classify(kind: str, fund_kind: str, name: str, fx: bool, config: DecisionConfig,
              risk: float | None, holdings: Holdings | None) -> tuple[str, bool]:
    """(class, whether a holdings class of >= min_share decided it)."""
    ac = config.raw.get("asset_classes")
    if ac is None:
        return "", False
    if kind != "fund":
        return ac["by_kind"][kind], False
    if fx:
        return ac["fx"], False
    bh = ac.get("by_holdings")
    top = holdings.majority(bh["min_share"]) if bh is not None and holdings else None
    if top == ac["fx"] and fund_kind in bh["fx_debt_kinds"]:
        return top, True
    upper = _tr_upper(name)
    for phrase, cls in ac["by_name"].items():
        if re.search(r"(?<!\w)" + re.escape(_tr_upper(phrase)) + r"(?!\w)", upper):
            return cls, False
    if top not in (None, "fon") and fund_kind in bh["kinds"]:
        return top, top != MIXED_CLASS
    if risk is not None:
        for rule in ac.get("by_risk", {}).get(fund_kind, ()):
            if risk >= rule["min_risk"]:
                return rule["class"], False
    return ac["by_kind"][fund_kind], False


def _etf_class(name: str, fx: bool, holdings: Holdings | None,
               config: DecisionConfig) -> tuple[str, bool]:
    """(class, decided by the holdings) of an ETF (D26): the FX tag -> fx; then the
    holdings majority (D23; a fon majority or no counted rows: go on); then
    etf.by_name; then etf.default_class. "" without asset_classes."""
    ac = config.raw.get("asset_classes")
    if ac is None:
        return "", False
    if fx:
        return ac["fx"], False
    bh = ac.get("by_holdings")
    top = holdings.majority(bh["min_share"]) if bh is not None and holdings else None
    if top not in (None, "fon"):
        return top, top != MIXED_CLASS
    et = config.raw["etf"]
    return name_class(name, et["by_name"]) or et["default_class"], False


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
    # a holdings entity "<code>/<kiymetTip>" (I8) is not a fund code
    fund_codes = sorted({d.entity for d in idx.rows
                         if d.quantity.startswith(FUND_PREFIX) and "/" not in d.entity})
    bh = c.get("asset_classes", {}).get("by_holdings")
    holding_rows: dict[str, list[DataPoint]] = {}
    if bh is not None:
        for d in idx.rows:
            if (d.quantity == HOLDINGS_QUANTITY and "/" in d.entity
                    and idx.get(d.quantity, d.entity) is d):      # latest usable row
                holding_rows.setdefault(d.entity.split("/", 1)[0], []).append(d)
    by_holdings: dict[str, HoldingsClass] = {}
    unknown_types: dict[str, list[str]] = {}
    serbest, no_entity, unknown, no_data = [], [], [], []
    used = _used_quantities(config) if "short_history" in c else None
    fx_words = [_tr_upper(w) for w in c["fx_name_words"]]
    etf_source = c.get(ETF, {}).get("source")
    for code in fund_codes:
        info = entities.get(code)
        if info is None:
            no_entity.append(code)
            continue
        if etf_source is not None and info.source == etf_source:      # D26: an ETF
            values = {q: d for q, d in idx.quantities_of(code).items()
                      if q.startswith(FUND_PREFIX)}
            fx = any(w in _tr_upper(info.name) for w in fx_words)
            holdings = holdings_of(holding_rows[code], config) if code in holding_rows else None
            cls, decided = _etf_class(info.name, fx, holdings, config)
            option = ProductOption(option_id=f"{ETF}:{code}", kind=ETF, label=info.name,
                                   entity=code, fx=fx, asset_class=cls)
            if used is not None and not any(used(q) for q in values):
                no_data.append(code)
                continue
            candidates.append(Candidate(option, values))
            if holdings is not None:
                for text, ids in holdings.unknown.items():
                    unknown_types.setdefault(text, []).extend(ids)
            if decided:
                by_holdings[option.option_id] = HoldingsClass(
                    asset_class=cls, share=holdings.shares[cls], evidence_ids=holdings.ids[cls])
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
        holdings = holdings_of(holding_rows[code], config) if code in holding_rows else None
        cls, decided = _classify("fund", kind, info.name, fx, config,
                                 risk_row.value if risk_row else None, holdings)
        option = ProductOption(option_id=f"fund:{code}", kind="fund", label=info.name,
                               entity=code, fund_kind=kind, fx=fx, asset_class=cls)
        if used is not None and not any(used(q) for q in values):
            no_data.append(code)        # never listed: nothing to show as evidence
            continue
        candidates.append(Candidate(option, values))
        if holdings is not None and kind in (*bh["kinds"], *bh["fx_debt_kinds"]):
            for text, ids in holdings.unknown.items():
                unknown_types.setdefault(text, []).extend(ids)
        if decided:
            by_holdings[option.option_id] = HoldingsClass(
                asset_class=cls, share=holdings.shares[cls], evidence_ids=holdings.ids[cls])

    removed_market: dict[str, list[str]] = {}
    st = c.get(STOCK)
    if st is not None:          # D26: Borsa İstanbul shares
        stock_codes = sorted({d.entity for d in idx.rows if d.quantity.startswith(STOCK_PREFIX)})
        cls = st["asset_class"] if "asset_classes" in c else ""
        for code in stock_codes:
            info = entities.get(code)
            if info is None:
                no_entity.append(code)
                continue
            if info.source != st["source"]:
                unknown.append(code)
                continue
            market = market_of(info.category)
            if market in st.get("exclude_markets", ()):        # D26b
                removed_market.setdefault(market, []).append(code)
                continue
            values = {q: d for q, d in idx.quantities_of(code).items()
                      if q.startswith(STOCK_PREFIX)}
            if used is not None and not any(used(q) for q in values):
                no_data.append(code)
                continue
            option = ProductOption(option_id=f"{STOCK}:{code}", kind=STOCK, label=info.name,
                                   entity=code, asset_class=cls)
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
        holdings_class=by_holdings,
        unknown_holding_types={k: tuple(sorted(v)) for k, v in sorted(unknown_types.items())},
        removed_stock_market={k: tuple(sorted(v)) for k, v in sorted(removed_market.items())},
    )
