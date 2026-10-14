"""The facts pack: everything the narrator may say about one approved run
(docs/narrator.md, "Input: the facts pack"). Deterministic; no LLM.

Named options are the baseline, the RM's selection, the other members of the
groups (rmprep.grouping) that hold a selected option, and (N9) the options of
the engine's talking points. Rejected options are in the pack only as a count
per rule; no other option is in it. Only warnings for the client (v1.3
audience "client") are in it."""

from __future__ import annotations

import dataclasses
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from rmprep import grouping
from rmprep.contracts import (
    AllocationBand,
    DecisionResult,
    EvidenceSet,
    RmStatus,
    ScoredOption,
)
from rmprep.api.names import short_name
from rmprep.decision.config import DecisionConfig
from rmprep.decision.config import load_config as load_decision_config
from rmprep.decision.display import DisplayFacts, access_text, display_facts
from rmprep.decision.text import normalize

# persona fields the text may use (not scored; the narrator is where they matter)
CLIENT_FIELDS = ("profil", "yas", "risk_profili", "durum", "yatirim_amaci", "yatirim_ufku",
                 "likidite_ihtiyaci", "doviz_maruz_kalma_tercihi", "gelir_nakit_akisi_ihtiyaci",
                 "anapara_koruma_tercihi", "oncelikler", "acik_kisitlar", "rm_notu")

# Score parts whose reason text carries an internal 0..1 value ("Düzenli gelir
# uygunluğu (ürün türüne göre): 0.6."): the text names them, never their values (N7).
INTERNAL_PARTS = ("liquidity", "income", "principal", "simplicity")


@dataclass(frozen=True)
class KeyNumber:
    evidence_id: str
    quantity: str           # DataPoint.quantity, e.g. fund_return_1y
    value: float
    unit: str
    as_of: date
    source: str
    name: str = ""          # N9c: the name in the pack (deposit rates: market vs ING); "" = quantity

    @property
    def key(self) -> str:
        return self.name or self.quantity


# N9c: deposit_rate rows by entity. The market average (EVDS) and the ING rates
# must never be mixed up in a client text.
MARKET_DEPOSIT_RATE = "piyasa_mevduat_faizi"
ING_DEPOSIT_RATE = "ing_mevduat_faizi"
ING_TIME_DEPOSIT_RATE = "ing_vadeli_mevduat_faizi"
ING_RATES = (ING_DEPOSIT_RATE, ING_TIME_DEPOSIT_RATE)
CPI_RATE = "tufe_yillik"                   # N13: the annual CPI row (real-return input)
MARKET_NAMES = (MARKET_DEPOSIT_RATE, CPI_RATE)   # N13: shown once, at the top of the pack
REAL_RETURN = "real_return_1y"             # N13: the real 1-year return (after stopaj and CPI)
# N13: number order of an option: the real return first, then the nominal one
NUMBER_ORDER = (REAL_RETURN, "fund_return_1y", ING_DEPOSIT_RATE, ING_TIME_DEPOSIT_RATE,
                "deposit_rate", "fund_risk_level", "fund_return_3y", "fund_return_5y",
                "fund_return_6m", "fund_return_3m", "fund_return_ytd", "fund_return_1m")


def number_rank(n: "KeyNumber") -> tuple[int, str]:
    k = n.key if n.key in NUMBER_ORDER else n.quantity
    return (NUMBER_ORDER.index(k) if k in NUMBER_ORDER else len(NUMBER_ORDER), k)


def deposit_rate_name(entity: str, config: DecisionConfig) -> str:
    """The pack name of a deposit_rate row (config deposit / time_deposit)."""
    c = config.raw
    if entity == c["deposit"]["market_entity"]:
        return MARKET_DEPOSIT_RATE
    if entity.startswith(c["deposit"]["entity_prefix"]):
        return ING_DEPOSIT_RATE
    td = c.get("time_deposit")
    if td and entity.startswith(td["entity_prefix"]):
        return ING_TIME_DEPOSIT_RATE
    return "deposit_rate"


@dataclass(frozen=True)
class OptionFacts:
    option_id: str
    label: str
    kind: str                                   # grouping.group_key
    fx: bool
    score: float
    confidence: float
    stability: float
    reasons: tuple[tuple[str, float, str], ...]  # (score part, value, reason), largest first
    numbers: tuple[KeyNumber, ...]
    evidence_ids: tuple[str, ...]
    warnings: tuple[str, ...] = ()              # messages of the warnings that name it
    rm_note: str = ""
    name: str = ""                              # N13: the screen's short name (issuer + type)
    asset_class: str = ""                       # N13 (v1.6): nakit_benzeri | borclanma | ...


@dataclass(frozen=True)
class AllocationFacts:
    """N15: one class of the model split and the client's current share (contract
    v1.10). current and gap only for an active row (rm, rm_confirmed,
    persona_text): an estimate (profile, national) is not a fact about the client."""
    asset_class: str
    band_low: float | None
    band_high: float | None
    current: float | None
    source: str                                 # "" | HOLDINGS_SOURCES
    gap: float | None                           # points to the band; + under, - over, 0 inside
    active: bool


def allocation_facts(a: AllocationBand) -> AllocationFacts:
    known = a.active and a.current is not None
    return AllocationFacts(a.asset_class, a.low, a.high, a.current if known else None,
                           a.current_source, a.gap if known else None, a.active)


@dataclass(frozen=True)
class RiskFacts:
    """N13: the risk line of a selected option."""
    access: str = ""                            # display access text ("Aynı gün"); "" = no data
    access_days: float | None = None            # N13b: sell valör or term days; None = no data
    fees: tuple[KeyNumber, ...] = ()            # entry / exit fee rows above 0
    note: Mapping[str, str] = dataclasses.field(default_factory=dict)   # lang -> config text
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GroupFacts:
    key: str                                    # grouping.group_key of the members
    selected: tuple[str, ...]                   # option ids the RM selected
    alternatives: tuple[str, ...]               # the other members (visible ones only)


@dataclass(frozen=True)
class WarningFacts:
    code: str
    message: str
    option_ids: tuple[str, ...] = ()            # named options only; () = the whole result
    evidence_ids: tuple[str, ...] = ()
    numbers: tuple[KeyNumber, ...] = ()         # values of its evidence


@dataclass(frozen=True)
class NoteFacts:
    message: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TalkingPointFacts:
    """A talking point of the engine (decision D18): the client's situation."""
    title: str                                  # TalkingPoint.label
    figure: str
    text: str
    option_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Facts:
    run_id: str
    persona_id: str
    snapshot_id: str
    client: Mapping[str, object]                # CLIENT_FIELDS of the persona
    baseline: OptionFacts | None                # the deposit, if the result has one
    selected: tuple[OptionFacts, ...]           # display order
    alternatives: tuple[OptionFacts, ...]       # group alternatives, display order
    groups: tuple[GroupFacts, ...]
    warnings: tuple[WarningFacts, ...]
    data_quality: tuple[NoteFacts, ...]
    assumptions: tuple[str, ...]
    open_questions: tuple[str, ...]
    rm_note: str
    rejected_count: int
    rejected_rules: Mapping[str, int]           # rule_id -> options it rejected
    talking_points: tuple[TalkingPointFacts, ...] = ()
    talked: tuple[OptionFacts, ...] = ()        # talking-point options not named otherwise
    # selected option -> (persona priority as written, why line) of decision D17
    why: Mapping[str, tuple[tuple[str, str], ...]] = dataclasses.field(default_factory=dict)
    risks: Mapping[str, RiskFacts] = dataclasses.field(default_factory=dict)   # N13, selected
    market: tuple[KeyNumber, ...] = ()          # N13: market deposit rate and CPI, once
    unmatched_priorities: tuple[str, ...] = ()  # N13: priorities with no scoring criterion
    allocation: tuple[AllocationFacts, ...] = ()  # N15: the model split and the current shares

    @property
    def split_unknown(self) -> bool:
        """N15: some class has only an estimate of the client's share."""
        return any(a.source and not a.active for a in self.allocation)

    def named_options(self) -> dict[str, OptionFacts]:
        out = {} if self.baseline is None else {self.baseline.option_id: self.baseline}
        out.update((o.option_id, o) for o in (*self.selected, *self.alternatives, *self.talked))
        return out

    def evidence_ids(self) -> frozenset[str]:
        ids = {i for o in self.named_options().values() for i in o.evidence_ids}
        ids.update(i for t in self.talking_points for i in t.evidence_ids)
        ids.update(i for w in self.warnings for i in w.evidence_ids)
        ids.update(i for n in self.data_quality for i in n.evidence_ids)
        return frozenset(ids)

    def to_dict(self) -> dict:
        return _plain(self)


def _plain(x):
    """JSON-ready copy: dataclasses and mappings -> dict, tuples -> list, dates -> ISO."""
    if dataclasses.is_dataclass(x):
        return {f.name: _plain(getattr(x, f.name)) for f in dataclasses.fields(x)}
    if isinstance(x, Mapping):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, (tuple, list)):
        return [_plain(v) for v in x]
    if isinstance(x, date):
        return x.isoformat()
    return x


def _name_of(dp, config: DecisionConfig) -> str:
    c = config.raw
    if dp.quantity == c["deposit"]["quantity"]:
        return deposit_rate_name(dp.entity, config)
    cpi = (c.get("real_return") or {}).get("cpi") or {}
    if dp.quantity == cpi.get("quantity") and dp.entity == cpi.get("entity"):
        return CPI_RATE
    return ""


def _numbers(ids, ev: EvidenceSet, config: DecisionConfig) -> tuple[KeyNumber, ...]:
    by_id = {dp.id: dp for dp in ev.datapoints}
    return tuple(KeyNumber(dp.id, dp.quantity, dp.value, dp.unit, dp.as_of, dp.source,
                           _name_of(dp, config))
                 for dp in (by_id.get(i) for i in ids) if dp is not None and dp.value is not None)


def display_name(label: str) -> str:
    """The screen's short name of an option: issuer + short label, or the label."""
    issuer, short = short_name(label)
    return f"{issuer} {short}" if issuer else label


def _option_facts(o: ScoredOption, ev: EvidenceSet, warnings: list[str], note: str,
                  config: DecisionConfig, shown: DisplayFacts | None = None) -> OptionFacts:
    ids = list(dict.fromkeys([*o.evidence_ids, *(i for c in o.constraints
                                                   for i in c.evidence_ids)]))
    numbers = _numbers(ids, ev, config)
    if shown is not None and shown.real_1y is not None:          # N13: the real return is a number
        row = next((dp for dp in ev.datapoints if dp.id == shown.real_1y.evidence_id), None)
        if row is not None:
            numbers = (KeyNumber(row.id, REAL_RETURN, shown.real_1y.value, "pct", row.as_of,
                                 row.source), *numbers)
            ids = list(dict.fromkeys([*ids, row.id]))
    reasons = sorted(((k, v, o.reasons[k]) for k, v in o.score_parts.items()),
                     key=lambda r: -abs(r[1]))
    return OptionFacts(
        option_id=o.option.option_id, label=o.option.label, kind=grouping.group_key(o),
        fx=o.option.fx, score=o.score, confidence=o.confidence, stability=o.stability,
        reasons=tuple(reasons), numbers=numbers, evidence_ids=tuple(ids),
        warnings=tuple(warnings), rm_note=note, name=display_name(o.option.label),
        asset_class=o.option.asset_class)


def _risk(o: ScoredOption, f: OptionFacts, shown: DisplayFacts, config: DecisionConfig,
          notes: Mapping) -> RiskFacts:
    """N13: access (sell valör or the term), fees above 0, the config risk note."""
    access = access_text(shown, config) or ""
    ids = []
    if shown.sell_valor_days is not None:
        ids.append(shown.sell_valor_days.evidence_id)
    elif shown.lock_days is not None and "1y" in shown.returns:
        ids.append(shown.returns["1y"].evidence_id)
    fd = config.raw.get("fund_detail") or {}
    fee_q = {fd.get("entry_fee_quantity"), fd.get("exit_fee_quantity")} - {None}
    fees = tuple(n for n in f.numbers if n.quantity in fee_q and n.value > 0)
    ids += [n.evidence_id for n in fees]
    note = (notes.get("by_class", {}).get(o.option.asset_class)
            or notes.get("by_kind", {}).get(o.option.kind) or {})
    days = (shown.sell_valor_days.value if shown.sell_valor_days is not None
            else shown.lock_days)
    return RiskFacts(access=access, access_days=days, fees=fees, note=dict(note),
                     evidence_ids=tuple(ids))


def unmatched_priorities(priorities, config: DecisionConfig) -> tuple[str, ...]:
    """N13: the persona priorities that map to no scoring criterion (the
    decision table: boost:<criterion> and diversity match; notes do not)."""
    table = {normalize(k): str(v) for k, v in config.raw["priorities"].items()}
    out = []
    for p in priorities:
        entry = table.get(normalize(p), "")
        if not (entry.startswith("boost:") or entry == "diversity"):
            out.append(p)
    return tuple(out)


@lru_cache(maxsize=1)
def _default_risk_notes() -> Mapping:
    from rmprep.narrator.config import load_config

    return load_config().risk_notes


@lru_cache(maxsize=1)
def _default_decision_config() -> DecisionConfig:
    return load_decision_config()


def build_facts(r: DecisionResult, ev: EvidenceSet,
                decision_config: DecisionConfig | None = None,
                risk_notes: Mapping | None = None) -> Facts:
    """decision_config: for the why lines (decision D17) and access texts; default
    config/decision.yaml. risk_notes: config narrator.yaml risk_notes (default)."""
    if r.rm_status != RmStatus.APPROVED:
        raise ValueError("the narrator writes only for an approved result")
    selected = set(r.rm_selected)
    dcfg = decision_config or _default_decision_config()

    groups = []
    for g in grouping.groups(r.options):
        members = (g.head, *g.alternatives)
        mine = tuple(o.option.option_id for o in members if o.option.option_id in selected)
        if mine:
            others = tuple(o.option.option_id for o in members if o.option.option_id not in selected)
            groups.append(GroupFacts(g.key, mine,
                                     others[:grouping.DEFAULT_RULE.visible_alternatives]))
    alternative_ids = {i for g in groups for i in g.alternatives}
    baseline = next((o for o in r.options if o.option.kind == "deposit"), None)
    named = selected | alternative_ids | ({baseline.option.option_id} if baseline else set())
    talked_ids = [i for t in r.talking_points for i in t.option_ids if i not in named]
    named |= set(talked_ids)

    rejected_labels = [x.option.label for x in r.rejected]
    warnings = []
    for w in r.warnings:
        if w.audience != "client":              # RM-only warnings never reach the text (N9)
            continue
        ids = tuple(i for i in w.option_ids if i in named)
        if (w.option_ids and not ids) or any(lbl in w.message for lbl in rejected_labels):
            continue
        warnings.append(WarningFacts(w.code, w.message, ids, w.evidence_ids,
                                     _numbers(w.evidence_ids, ev, dcfg)))

    shown = display_facts(r, ev, dcfg)

    def facts(o: ScoredOption) -> OptionFacts:
        oid = o.option.option_id
        return _option_facts(o, ev, [w.message for w in warnings if oid in w.option_ids],
                             r.rm_option_notes.get(oid, ""), dcfg, shown.get(oid))

    chosen = [o for o in r.options if o.option.option_id in selected]
    selected_facts = tuple(facts(o) for o in chosen)
    notes = _default_risk_notes() if risk_notes is None else risk_notes
    risks = {o.option.option_id: _risk(o, fo, shown[o.option.option_id], dcfg, notes)
             for o, fo in zip(chosen, selected_facts)}
    baseline_facts = facts(baseline) if baseline else None
    alternatives = tuple(facts(o) for o in r.options if o.option.option_id in alternative_ids)
    market = {}
    for o in (*([baseline_facts] if baseline_facts else []), *selected_facts, *alternatives):
        for n in o.numbers:
            if n.name in MARKET_NAMES:
                market.setdefault(n.name, n)
    for w in warnings:
        for n in w.numbers:
            if n.name in MARKET_NAMES:
                market.setdefault(n.name, n)
    p = r.persona
    return Facts(
        run_id=r.run_id, persona_id=p.persona_id, snapshot_id=r.snapshot_id,
        client={k: getattr(p, k) for k in CLIENT_FIELDS},
        baseline=baseline_facts,
        selected=selected_facts,
        alternatives=alternatives,
        groups=tuple(groups),
        warnings=tuple(warnings),
        data_quality=tuple(NoteFacts(n.message, n.evidence_ids) for n in r.data_quality),
        assumptions=r.assumptions,
        open_questions=tuple(q.text for q in r.questions if q.answer is None),
        rm_note=r.rm_note,
        rejected_count=len(r.rejected),
        rejected_rules=dict(sorted(Counter(c.rule_id for x in r.rejected
                                           for c in x.failed).items())),
        talking_points=tuple(TalkingPointFacts(t.label, t.figure, t.text, t.option_ids,
                                               t.evidence_ids) for t in r.talking_points),
        talked=tuple(facts(o) for o in r.options if o.option.option_id in set(talked_ids)),
        why={oid: shown[oid].why for oid in r.rm_selected},
        risks=risks,
        market=tuple(market[k] for k in sorted(market)),
        unmatched_priorities=unmatched_priorities(p.oncelikler, dcfg),
        allocation=tuple(allocation_facts(a) for a in r.allocation),
    )
