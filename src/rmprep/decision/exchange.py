"""Exchange-traded funds and shares (docs/decision.md section 16, D26).

ETFs (source tefas_byf) have the quantities of the TEFAS funds; shares (source
bist_bulletin) have their own. Both are bought on Borsa İstanbul (T+2).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from rmprep.contracts import DataPoint
from rmprep.decision.config import DecisionConfig

ETF, STOCK = "etf", "stock"
EXCHANGE_KINDS = (ETF, STOCK)
MARKET_KINDS = ("fund", ETF, STOCK)     # ranked products with market data and an SPK risk
STOCK_PREFIX = "stock_"
STOCK_VOLATILITY = "stock_volatility_1y"
STOCK_TURNOVER = "stock_turnover_3m"
STOCK_BIST100 = "stock_bist100"
RISK_TOP = 7


def return_prefix(kind: str) -> str:
    """Quantity prefix of the period returns of a kind."""
    return "stock_return_" if kind == STOCK else "fund_return_"


def spk_risk(volatility: float, bands: Sequence[Sequence[float]]) -> int:
    """SPK risk value of an annual volatility (%): the risk of the first band
    [upper, risk] with volatility < upper; above the last band 7 (SPK guide 9.3.2.1)."""
    for upper, risk in bands:
        if volatility < upper:
            return int(risk)
    return RISK_TOP


def stock_risk(volatility: DataPoint | None, config: DecisionConfig) -> int:
    """Risk value of a share: the SPK band of its 1-year volatility, at least
    stock.risk_floor (one company's risk is concentrated); no row -> 7."""
    s = config.raw["stock"]
    if volatility is None:
        return RISK_TOP
    return max(spk_risk(volatility.value, s["spk_bands"]), s["risk_floor"])


def _tr_upper(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def name_class(name: str, table: dict[str, str]) -> str | None:
    """The class of the first phrase of the table in the name (Turkish upper
    case, whole words), else None."""
    upper = _tr_upper(name)
    for phrase, cls in table.items():
        if re.search(r"(?<!\w)" + re.escape(_tr_upper(phrase)) + r"(?!\w)", upper):
            return cls
    return None
