"""Display facts for the web UI (docs/decision.md section 9, D17).

Values that are business rules (the real 1-year return after stopaj and CPI,
the "neden" lines from the persona priorities) come from here, so the API adds
no rules. Pure: reads the result, the evidence and the config only.
"""

from __future__ import annotations

import dataclasses
import string
from collections.abc import Mapping
from dataclasses import dataclass

from rmprep.contracts import DecisionResult, EvidenceSet, ProductOption
from rmprep.decision.config import DEPOSIT_KINDS, DecisionConfig
from rmprep.decision.exchange import (
    EXCHANGE_KINDS,
    STOCK,
    STOCK_VOLATILITY,
    STOCK_VOLATILITY_5Y,
    return_prefix,
    stock_risk,
)
from rmprep.decision.scoring import _net
from rmprep.decision.text import normalize
from rmprep.decision.universe import EvidenceIndex, stopaj_entity

PERIODS = ("3m", "6m", "1y")
_MINUS = "−"


@dataclass(frozen=True)
class Fact:
    value: float
    evidence_id: str            # "" when the value comes from config (time deposit term)


@dataclass(frozen=True)
class DisplayFacts:
    option_id: str
    returns: Mapping[str, Fact]          # keys among "3m", "6m", "1y" (percent); a missing period has no key
    real_1y: Fact | None                 # percent, after stopaj and CPI (4.1b, no fees); evidence id = the 1y return row
    risk: Fact | None                    # SPK risk value 1..7
    sell_valor_days: Fact | None
    lock_days: int | None                # time deposit: time_deposit.term_days; else None
    why: tuple[tuple[str, str], ...]     # (persona priority as written, text)
    kind: str = ""                       # the option kind (D26: etf and stock settle T+2)


def tr_percent(x: float) -> str:
    """Percent in Turkish format with a sign: +%8,7 / −%8,3 (one decimal)."""
    sign = _MINUS if x < 0 else "+"
    return f"{sign}%{abs(x):.1f}".replace(".", ",")


def access_text(facts: DisplayFacts, config: DecisionConfig, lang: str = "TR") -> str | None:
    """The "Paraya erişim" value (config display.access): same day, n business
    days (sell valör), or the term of a time deposit; None without data. An ETF
    or a share (D26): the exchange settlement text display.access.exchange in
    `lang` (TR or EN); the other texts are Turkish only."""
    texts = config.raw["display"]["access"]
    if facts.kind in EXCHANGE_KINDS and "exchange" in texts:
        return texts["exchange"][lang]
    if facts.lock_days is not None:
        return texts["term"].format(days=facts.lock_days)
    if facts.sell_valor_days is None:
        return None
    days = int(round(facts.sell_valor_days.value))
    return texts["same_day"] if days == 0 else texts["days"].format(days=days)


def _real(option: ProductOption, annual: float, idx: EvidenceIndex,
          config: DecisionConfig) -> float | None:
    """Real return of a nominal annual return (fraction) after the stopaj of the
    option (missing row -> 0) and CPI; None without real_return or CPI."""
    rr = config.raw.get("real_return")
    if rr is None:
        return None
    cpi = idx.get(rr["cpi"]["quantity"], rr["cpi"]["entity"])
    if cpi is None:
        return None
    st = idx.get(rr["stopaj"]["quantity"], stopaj_entity(option, config))
    net = _net(option, annual, st.value / 100 if st is not None else 0.0, config)
    return (1 + net) / (1 + cpi.value / 100) - 1


def facts_of(option: ProductOption, idx: EvidenceIndex,
             config: DecisionConfig) -> DisplayFacts:
    """Display facts of one option without the why lines."""
    c = config.raw
    returns: dict[str, Fact] = {}
    risk = valor = None
    lock_days = None
    if option.kind in DEPOSIT_KINDS:
        section = c["deposit"] if option.kind == "deposit" else c["time_deposit"]
        rate = idx.get(section["quantity"], option.entity)
        if rate is not None:            # the published annual rate
            returns["1y"] = Fact(rate.value, rate.id)
        if option.kind == "time_deposit":
            lock_days = section.get("term_days")
    else:
        prefix = return_prefix(option.kind)
        for period in PERIODS:
            row = idx.get(f"{prefix}{period}", option.entity)
            if row is not None:
                returns[period] = Fact(row.value, row.id)
        if option.kind == STOCK:        # D26: SPK band of the volatility; none without it
            v1 = idx.get(STOCK_VOLATILITY, option.entity)
            v5 = idx.get(STOCK_VOLATILITY_5Y, option.entity)      # D26c: 5 years first
            row = v5 or v1
            risk = Fact(stock_risk(v1, config, v5), row.id) if row is not None else None
        else:
            row = idx.get("fund_risk_level", option.entity)
            risk = Fact(row.value, row.id) if row is not None else None
        fd = c.get("fund_detail")
        if fd is not None and option.kind != STOCK:
            row = idx.get(fd["sell_valor_quantity"], option.entity)
            valor = Fact(row.value, row.id) if row is not None else None
    real_1y = None
    if "1y" in returns:
        real = _real(option, returns["1y"].value / 100, idx, config)
        if real is not None:
            real_1y = Fact(real * 100, returns["1y"].evidence_id)
    return DisplayFacts(option_id=option.option_id, returns=returns, real_1y=real_1y,
                        risk=risk, sell_valor_days=valor, lock_days=lock_days, why=(),
                        kind=option.kind)


def _why(facts: DisplayFacts, priorities: tuple[str, ...],
         config: DecisionConfig) -> tuple[tuple[str, str], ...]:
    """One line per persona priority (as written) that the priority table maps
    to a criterion with a display.why text; a line whose value is missing is left
    out. No score numbers."""
    c = config.raw
    texts = c["display"].get("why")
    if not texts:
        return ()
    table = {normalize(k): v for k, v in c["priorities"].items()}
    values = {
        "access": access_text(facts, config),
        "risk": f"{facts.risk.value:.0f}" if facts.risk is not None else None,
        "ret1y": tr_percent(facts.returns["1y"].value) if "1y" in facts.returns else None,
    }
    out = []
    for written in priorities:
        kind, _, crit = str(table.get(normalize(written), "")).partition(":")
        if kind != "boost" or crit not in texts:
            continue
        template = texts[crit]
        fields = {f for _, f, _, _ in string.Formatter().parse(template) if f}
        if any(values.get(f) is None for f in fields):
            continue
        out.append((written, template.format(**values)))
    return tuple(out)


def display_facts(result: DecisionResult, evidence: EvidenceSet,
                  config: DecisionConfig) -> dict[str, DisplayFacts]:
    """Display facts for every scored and rejected option of the result."""
    idx = EvidenceIndex(evidence)
    options = [o.option for o in result.options] + [x.option for x in result.rejected]
    out = {}
    for option in options:
        f = facts_of(option, idx, config)
        out[option.option_id] = dataclasses.replace(
            f, why=_why(f, result.persona.oncelikler, config))
    return out
