"""Code checks of a karar_ver answer (spec section 6, node 4 "Kontrol").

1. Three different option ids, all among the candidates.
2. At most stock.max_in_top3 shares; for the profiles of the class rule (D19) at
   most recommend.max_per_class per asset class and recommend.max_cash_like
   cash-like options, when the candidates allow it (relaxed in the engine's
   order: first the class cap, then the cash cap).
3. 1-3 reasons per pick, each of at most `words.reason` words, each with at
   least one valid citation (E…, F…, puan:<part>, portfoy:<class>); a finding id
   belongs to the option of the reason; every number and date of a reason is in
   the data it cites (the narrator's number rule; a plain count or place 1-10 is
   allowed); no forbidden phrase (config/narrator.yaml).
4. One reason for each engine top-3 option that is dropped; a summary of at most
   `words.summary` words.

Labels are added by code (not a refusal): "(tahmini dağılıma göre)" for a reason
that cites an estimated class, "(web, doğrulanmamış)" for one that cites a web
finding. Problems are short English strings, given to the model for its retry."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date
from itertools import combinations
from typing import Any

from rmprep.contracts import AgentPick, AgentReason
from rmprep.decision.config import DecisionConfig
from rmprep.narrator.template import tr_lower
from rmprep.narrator.validator import _PERCENT, _matches, _token_readings, dates_in, numbers_in

N = 3
MAX_REASONS = 3
SMALL = frozenset(float(i) for i in range(1, 11))        # places and counts
DEFAULT_LABELS = {"TR": {"estimate": "(tahmini dağılıma göre)", "web": "(web, doğrulanmamış)"},
                  "EN": {"estimate": "(based on the estimated split)", "web": "(web, not verified)"}}
DEFAULT_WORDS = {"reason": 30, "summary": 40}
_CITE = re.compile(r"^(E[0-9a-f]{8}|F[0-9a-f]{8}|puan:[a-z_]+|portfoy:[a-z_]+)$")
_OPTION_IDS = re.compile(r"\b(?:deposit|time_deposit|fund|etf|stock):\S+")
_CITES_IN_TEXT = re.compile(r"\b(?:E[0-9a-f]{8}|F[0-9a-f]{8})\b|\b(?:puan|portfoy):[a-z_]+")


def _date(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def _scaled(v: float) -> set[float]:
    """A value and its thousand / million / billion forms (fund size written short)."""
    v = abs(float(v))
    out = {v}
    if v >= 1000:
        out.update(v / k for k in (1e3, 1e6, 1e9))
    return out


class _Index:
    """What each citation id allows, read from the pack."""

    def __init__(self, pack: Mapping[str, Any]):
        self.cands = {c["option_id"]: c for c in pack.get("adaylar", ())}
        self.e_nums: dict[str, set[float]] = {}
        self.e_dates: dict[str, set[date]] = {}
        self.puan: dict[tuple[str, str], set[float]] = {}
        self.f_owner: dict[str, str] = {}
        self.f_nums: dict[str, set[float]] = {}
        self.f_dates: dict[str, set[date]] = {}
        self.portfoy: dict[str, tuple[set[float], bool]] = {}
        for oid, c in self.cands.items():
            for eid, row in c.get("kanitlar", {}).items():
                self.e_nums.setdefault(eid, set()).update(_scaled(row["deger"]))
                d = _date(row.get("tarih", ""))
                if d is not None:
                    self.e_dates.setdefault(eid, set()).add(d)
            self._facts(c)
            for w in c.get("uyarilar", ()):
                values = {v for v, _ in numbers_in(w.get("metin", ""))}
                for eid in w.get("kanit", ()):
                    self.e_nums.setdefault(eid, set()).update(values)
            for p in c.get("puan_parcalari", ()):
                nums = {abs(p["puan"]), abs(p["puan"]) * 100}
                if p.get("agirlik") is not None:
                    nums |= {abs(p["agirlik"]), abs(p["agirlik"]) * 100}
                nums |= {v for v, _ in numbers_in(p.get("neden", ""))}
                self.puan[(oid, p["id"])] = nums
        for oid, block in pack.get("arastirma", {}).items():
            for f in (*block.get("bulgular", ()), *block.get("haberler", ())):
                self.f_owner[f["id"]] = oid
                self.f_nums[f["id"]] = {v for v, _ in numbers_in(f["metin"])}
                self.f_dates[f["id"]] = dates_in(f["metin"]) | (
                    {_date(f["tarih"])} if _date(f.get("tarih", "")) else set())
        for row in pack.get("portfoy", ()):
            nums = {abs(float(row[k])) for k in ("hedef_alt", "hedef_ust", "mevcut", "mevcut_alt",
                                                 "mevcut_ust", "fark") if row.get(k) is not None}
            self.portfoy[row["id"]] = (nums, bool(row.get("tahmin")))

    def all_numbers(self) -> set[float]:
        out: set[float] = set()
        for group in (self.e_nums, self.puan, self.f_nums):
            for v in group.values():
                out |= v
        for v, _ in self.portfoy.values():
            out |= v
        return out

    def _facts(self, x: Any) -> None:
        """Every {"deger": v, "kanit": E…} object of a candidate allows v for that id."""
        if isinstance(x, Mapping):
            if isinstance(x.get("kanit"), str) and isinstance(x.get("deger"), (int, float)):
                self.e_nums.setdefault(x["kanit"], set()).update(_scaled(x["deger"]))
            for v in x.values():
                self._facts(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                self._facts(v)


def _words(text: str) -> int:
    return len(text.split())


def _strip_names(text: str, idx: _Index) -> str:
    """The text without option ids, citation ids and candidate names (a name may
    hold a number or a word such as "Garanti")."""
    text = _CITES_IN_TEXT.sub(" ", _OPTION_IDS.sub(" ", text))
    low = tr_lower(text)
    for c in sorted(idx.cands.values(), key=lambda c: -len(c.get("ad", ""))):
        name = tr_lower(c.get("ad", ""))
        if name:
            low = low.replace(name, " ")
    return low


def _check_reason(oid: str, raw: Any, idx: _Index, phrases: Sequence[str],
                  labels: Mapping[str, str], max_words: int,
                  problems: list[str]) -> AgentReason | None:
    if not isinstance(raw, Mapping) or not isinstance(raw.get("metin"), str):
        problems.append(f"{oid}: a reason needs metin and kaynaklar")
        return None
    text = raw["metin"].strip()
    cites = raw.get("kaynaklar")
    cites = [c for c in cites if isinstance(c, str)] if isinstance(cites, list) else []
    n = len(problems)
    if not text:
        problems.append(f"{oid}: empty reason")
    if _words(text) > max_words:
        problems.append(f"{oid}: reason over {max_words} words: \"{text[:60]}\"")
    if not cites:
        problems.append(f"{oid}: reason without a citation: \"{text[:60]}\"")
    nums: set[float] = set()
    dates: set[date] = set()
    estimate = web = False
    for c in cites:
        if not _CITE.match(c):
            problems.append(f"{oid}: bad citation {c!r} (use E…, F…, puan:<part>, portfoy:<class>)")
        elif c.startswith("E"):
            if c not in idx.e_nums:
                problems.append(f"{oid}: unknown evidence id {c}")
            nums |= idx.e_nums.get(c, set())
            dates |= idx.e_dates.get(c, set())
        elif c.startswith("F"):
            owner = idx.f_owner.get(c)
            if owner is None:
                problems.append(f"{oid}: unknown finding id {c}")
            elif owner != oid:
                problems.append(f"{oid}: finding {c} does not belong to {oid} (it is of {owner})")
            web = True
            nums |= idx.f_nums.get(c, set())
            dates |= idx.f_dates.get(c, set())
        elif c.startswith("puan:"):
            if (oid, c) not in idx.puan:
                problems.append(f"{oid}: unknown score part {c} of {oid}")
            nums |= idx.puan.get((oid, c), set())
        else:
            if c not in idx.portfoy:
                problems.append(f"{oid}: unknown portfolio class {c}")
            more, est = idx.portfoy.get(c, (set(), False))
            nums |= more
            estimate = estimate or est
    clean = _strip_names(text, idx)
    for d in dates_in(clean):
        if d not in dates:
            problems.append(f"{oid}: date {d.isoformat()} not in the cited data: \"{text[:60]}\"")
    percents = {tok for m in _PERCENT.finditer(clean)
                for tok, _ in _token_readings(m.group(0))}
    for tok, readings in _token_readings(clean):
        if _matches(readings, nums):
            continue
        if tok not in percents and any(d == 0 and v in SMALL for v, d in readings):
            continue
        problems.append(f"{oid}: number {tok} not in the cited data: \"{text[:60]}\"")
    for p in phrases:
        if tr_lower(p) in clean:
            problems.append(f"{oid}: forbidden phrase \"{p}\": \"{text[:60]}\"")
    if len(problems) > n:
        return None
    return AgentReason(text, tuple(cites),
                       tuple(labels[k] for k, on in (("estimate", estimate), ("web", web)) if on))


def _pick(oid: str, reasons: list[AgentReason], labels: Mapping[str, str]) -> AgentPick:
    return AgentPick(oid, tuple(reasons),
                     uses_estimate=any(labels["estimate"] in r.labels for r in reasons),
                     uses_web=any(labels["web"] in r.labels for r in reasons))


def _fits(ids: Sequence[str], cands: Mapping[str, Mapping], per_class: int | None,
          cash: int | None, cash_class: str | None, stocks: int | None) -> bool:
    classes = Counter(cands[i]["varlik_sinifi"] for i in ids)
    if stocks is not None and sum(1 for i in ids if cands[i]["tur"] == "stock") > stocks:
        return False
    if per_class is not None and any(v > per_class for v in classes.values()):
        return False
    return cash is None or classes[cash_class] <= cash


def _caps(ids: list[str], pack: Mapping, decision_config: DecisionConfig,
          idx: _Index) -> list[str]:
    rules = pack.get("kurallar", {})
    stocks = rules.get("en_fazla_hisse")
    cands = idx.cands
    out = []
    n_stock = sum(1 for i in ids if cands[i]["tur"] == "stock")
    if stocks is not None and n_stock > stocks:
        out.append(f"{n_stock} shares in the picks (at most {stocks})")
    if not rules.get("sinif_kurali"):
        return out
    rec = decision_config.raw["recommend"]
    per, cash, cash_cls = rec["max_per_class"], rec["max_cash_like"], rec["cash_like"]

    def feasible(per_class: int | None, cash_cap: int | None) -> bool:
        return any(_fits(combo, cands, per_class, cash_cap, cash_cls, stocks)
                   for combo in combinations(list(cands), N))

    classes = Counter(cands[i]["varlik_sinifi"] for i in ids)
    if feasible(per, cash):
        out += [f"{k} options of class {c} (at most {per} per class; the candidates allow it)"
                for c, k in classes.items() if k > per]
    if (feasible(per, cash) or feasible(None, cash)) and classes[cash_cls] > cash:
        out.append(f"{classes[cash_cls]} {cash_cls} options (at most {cash}; the candidates "
                   f"allow it)")
    return out


def check_decision(raw: Mapping, pack: dict, decision_config: DecisionConfig,
                   phrases: Sequence[str], lang: str, *,
                   labels: Mapping[str, str] | None = None,
                   words: Mapping[str, int] | None = None,
                   ) -> tuple[list[AgentPick], list[AgentPick], str, list[str]]:
    """(picks with labels, dropped, summary, problems); problems == [] means accepted."""
    labels = labels or DEFAULT_LABELS.get(lang, DEFAULT_LABELS["TR"])
    words = {**DEFAULT_WORDS, **(words or {})}
    idx = _Index(pack)
    problems: list[str] = []
    raw = raw if isinstance(raw, Mapping) else {}

    secimler = raw.get("secimler")
    secimler = secimler if isinstance(secimler, list) else []
    ids = [s.get("option_id") if isinstance(s, Mapping) else None for s in secimler]
    if len(secimler) != N:
        problems.append(f"needs {N} picks, got {len(secimler)}")
    for i in ids:
        if not isinstance(i, str):
            problems.append("a pick needs an option_id")
        elif i not in idx.cands:
            problems.append(f"{i} is not a candidate (candidates: {', '.join(idx.cands)})")
    for i, k in Counter(x for x in ids if isinstance(x, str)).items():
        if k > 1:
            problems.append(f"{i} is picked twice")
    if not problems:
        problems += _caps(ids, pack, decision_config, idx)

    picks: list[AgentPick] = []
    for s, oid in zip(secimler, ids):
        if not isinstance(oid, str):
            continue
        rs = s.get("gerekceler")
        rs = rs if isinstance(rs, list) else []
        if not 1 <= len(rs) <= MAX_REASONS:
            problems.append(f"{oid}: 1-3 reasons, got {len(rs)}")
        checked = [_check_reason(oid, r, idx, phrases, labels, words["reason"], problems)
                   for r in rs[:MAX_REASONS]]
        good = [r for r in checked if r is not None]
        if good:
            picks.append(_pick(oid, good, labels))

    engine = [o for o in pack.get("motor_ilk3", ()) if o not in ids]
    cikanlar = raw.get("cikanlar")
    cikanlar = cikanlar if isinstance(cikanlar, list) else []
    given: dict[str, Any] = {}
    for c in cikanlar:
        if isinstance(c, Mapping) and isinstance(c.get("option_id"), str):
            given.setdefault(c["option_id"], c.get("gerekce"))
    dropped: list[AgentPick] = []
    for oid in engine:
        if oid not in given:
            problems.append(f"dropped: {oid} of the engine's top 3 is dropped without a reason")
            continue
        r = _check_reason(oid, given[oid], idx, phrases, labels, words["reason"], problems)
        if r is not None:
            dropped.append(_pick(oid, [r], labels))
    for oid in given:
        if oid not in engine:
            problems.append(f"dropped: {oid} is not an engine top-3 option that was dropped")

    summary = raw.get("ozet")
    summary = summary.strip() if isinstance(summary, str) else ""
    if not summary:
        problems.append("summary (ozet) is empty")
    elif _words(summary) > words["summary"]:
        problems.append(f"summary over {words['summary']} words")
    else:
        clean = _strip_names(summary, idx)
        problems += [f"summary: forbidden phrase \"{p}\"" for p in phrases if tr_lower(p) in clean]
        known = idx.all_numbers()
        problems += [f"summary: number {tok} not in the data" for tok, readings
                     in _token_readings(clean) if not _matches(readings, known | SMALL)]
    return picks, dropped, summary, problems
