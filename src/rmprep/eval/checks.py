"""The checks of docs/eval.md ("Checks and metrics"), in code. Each check
gives pass | fail | n/a with details; n/a when it does not apply to the run
(e.g. D13 rules before D13, consistency without a repeat).

Per run: rule5, risk_ceiling, not_buyable (D12), explicit_constraints (D13),
no_invented_data, missing_data_shown, bad_data_handled, questions,
narrator_valid, forbidden_phrases, traceability, diverse_recommendations,
allocation_projection; with the agent (E11) agent_decision. Per scenario:
consistency, sensitivity (the `expect` of the scenario)."""

from __future__ import annotations

import re
import statistics
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from rmprep.contracts import DecisionResult, DecisionState, Flag, NarrativeDraft
from rmprep.eval.oracle import Oracle
from rmprep.eval.runner import RunRecord, ScenarioRun
from rmprep.eval.scenario import Scenario
from rmprep.narrator.validator import CITED_SECTIONS, PERCENT_KEYS, dates_in, numbers_in
from rmprep.narrator.validator import _token_readings as token_readings  # the number parser

PASS, FAIL, NA = "pass", "fail", "n/a"
SHORT_LIST = 20         # docs/eval.md: "the short list (first 20)"
SENSITIVITY_TOP = 10    # sensitivity metrics: positions 1-10 (without the baseline)
MAX_DETAILS = 10


@dataclass(frozen=True)
class CheckResult:
    check: str
    status: str                     # pass | fail | n/a
    details: tuple[str, ...] = ()
    needs: str = ""                 # D12 | D13 when the check waits for that milestone

    @classmethod
    def of(cls, check: str, problems: list[str], *, na: str | None = None,
           needs: str = "") -> CheckResult:
        if na is not None:
            return cls(check, NA, (na,), needs)
        if not problems:
            return cls(check, PASS)
        extra = [f"... and {len(problems) - MAX_DETAILS} more"] if len(problems) > MAX_DETAILS else []
        return cls(check, FAIL, tuple(problems[:MAX_DETAILS] + extra), needs)


@dataclass
class Context:
    """What the checks of one run may read."""

    scenario: Scenario
    run: RunRecord
    decision_config: Mapping[str, Any]
    forbidden_phrases: Mapping[str, tuple[str, ...]]
    compare: RunRecord | None = None        # first run of scenario.compare_to
    oracle: Oracle = field(init=False)

    def __post_init__(self) -> None:
        self.oracle = Oracle(self.run.result, self.run.evidence, self.decision_config)


# --- helpers -------------------------------------------------------------------

def tr_norm(text: str) -> str:
    return " ".join(text.replace("İ", "i").replace("I", "ı").lower().split())


def short_list(r: DecisionResult, n: int = SHORT_LIST):
    """The baseline (if any) and the first n other options in display order."""
    base = [o for o in r.options[:1] if o.option.kind == "deposit"]
    rest = [o for o in r.options if o.option.kind != "deposit"][:n]
    return base + rest


def sentences(d: NarrativeDraft):
    return [(sec.key, s) for sec in d.sections for s in sec.sentences]


def named_options(d: NarrativeDraft, r: DecisionResult) -> set[str]:
    """Option ids the text names: cited ids, plus labels and fund codes found
    in the text (scored and rejected options)."""
    out: set[str] = set()
    every = [o.option for o in r.options] + [x.option for x in r.rejected]
    labels = sorted(((tr_norm(o.label), o.option_id) for o in every if o.label),
                    key=lambda x: len(x[0]), reverse=True)
    for _, s in sentences(d):
        out.update(s.option_ids)
        text, raw = tr_norm(s.text), s.text
        for label, oid in labels:
            if label in text:
                out.add(oid)
                text = text.replace(label, " ")
        for o in every:
            if o.option_id in raw or (o.kind == "fund" and o.entity and re.search(
                    rf"(?<![\w]){re.escape(o.entity)}(?![\w])", raw)):
                out.add(o.option_id)
    return out


def _walk_numbers(x, key: str, out: set[float], dates: set[date]) -> None:
    if isinstance(x, bool) or x is None:
        return
    if isinstance(x, (int, float)):
        out.add(abs(float(x)))
        if key in PERCENT_KEYS:
            out.add(abs(float(x)) * 100)
    elif isinstance(x, str):
        out.update(v for v, _ in numbers_in(x))
        dates.update(dates_in(x))
        m = re.search(r"_(\d+)[my]$", x)
        if m:
            out.add(float(m.group(1)))
    elif isinstance(x, Mapping):
        for k, v in x.items():
            _walk_numbers(v, k, out, dates)
    elif isinstance(x, (list, tuple)):
        for v in x:
            _walk_numbers(v, key, out, dates)


def allowed_numbers(r: DecisionResult, ev_by_id: Mapping) -> tuple[set[float], set[date]]:
    """Numbers and dates a text about r may use: every number of the result
    (scores, parts, reasons, notes, persona), the values and dates of the
    evidence rows it references, the percent form of confidence/stability, and
    the counts of its lists (questions, warnings, rejected per rule, ...)."""
    nums: set[float] = set()
    dates: set[date] = set()
    _walk_numbers(r.to_dict(), "", nums, dates)
    for i in r.evidence_ids():
        d = ev_by_id.get(i)
        if d is not None:
            if d.value is not None:
                nums.add(abs(d.value))
            dates.add(d.as_of)
            _walk_numbers(d.quantity, "quantity", nums, dates)
    rules = Counter(c.rule_id for x in r.rejected for c in x.failed)
    counts = [len(r.options), len(r.rejected), len(r.questions), len(r.warnings),
              len(r.data_quality), len(r.assumptions), len(r.rm_selected),
              len(r.persona.oncelikler), len(r.persona.acik_kisitlar), *rules.values(),
              len([o for o in r.options if o.option.kind != "deposit"])]
    nums.update(float(c) for c in counts)
    nums.update(float(d.year) for d in dates)
    return nums, dates


def display_numbers(r: DecisionResult, ev, decision_config: Mapping[str, Any],
                    ev_by_id: Mapping) -> tuple[set[float], set[date]]:
    """Numbers and dates of the display facts of the scored options
    (rmprep.decision.display: returns per period, real 1-year return, risk,
    valör, time deposit term, the why lines) and of the evidence rows they
    cite. The narrator pack and the screens use them (N9), so a text may too.
    Rejected options are left out: a text must not talk about them."""
    from rmprep.decision.config import DecisionConfig
    from rmprep.decision.display import display_facts

    nums: set[float] = set()
    dates: set[date] = set()
    shown = {o.option.option_id for o in r.options}
    for oid, f in display_facts(r, ev, DecisionConfig(raw=decision_config)).items():
        if oid not in shown:
            continue
        facts = [*f.returns.values(), f.real_1y, f.risk, f.sell_valor_days]
        for fact in (x for x in facts if x is not None):
            nums.add(abs(fact.value))
            row = ev_by_id.get(fact.evidence_id)
            if row is not None:
                if row.value is not None:
                    nums.add(abs(row.value))
                dates.add(row.as_of)
        if f.lock_days is not None:
            nums.add(float(f.lock_days))
        _walk_numbers([text for _, text in f.why], "", nums, dates)
    return nums, dates


def _matches(readings, allowed: set[float]) -> bool:
    return any(abs(x - a) <= 0.5 * 10 ** -d + 1e-9 for x, d in readings for a in allowed)


# --- per run ------------------------------------------------------------------

def check_rule5(c: Context) -> CheckResult:
    r, o = c.run.result, c.oracle
    if r.state != DecisionState.READY:
        return CheckResult.of("rule5", [], na="not ready: nothing is listed")
    rejected = {x.option.option_id for x in r.rejected}
    bad: dict[str, list[str]] = {}
    for x in r.options:
        v = o.violations(x.option)
        if v:
            bad[x.option.option_id] = v
    problems = [f"short list: {s.option.option_id} breaks {bad[s.option.option_id]}"
                for s in short_list(r) if s.option.option_id in bad]
    if c.run.approved is not None:
        problems += [f"selection: {i} breaks {bad[i]}" for i in c.run.approved.rm_selected if i in bad]
    for lang, d in sorted(c.run.narratives.items()):
        for i in sorted(named_options(d, r)):
            if i in rejected:
                problems.append(f"text {lang}: names the rejected option {i}")
            elif i in bad:
                problems.append(f"text {lang}: names {i}, which breaks {bad[i]}")
    return CheckResult.of("rule5", problems)


def check_risk_ceiling(c: Context) -> CheckResult:
    r, o = c.run.result, c.oracle
    if r.state != DecisionState.READY:
        return CheckResult.of("risk_ceiling", [], na="not ready")
    if o.rules.ceiling is None:
        return CheckResult.of("risk_ceiling", [], na="no risk ceiling (profile unknown)")
    return CheckResult.of("risk_ceiling", [
        f"{x.option.option_id}: risk {o.risk(x.option):g} > ceiling {o.rules.ceiling}"
        for x in r.options if "risk_ceiling" in o.violations(x.option)])


def check_not_buyable(c: Context) -> CheckResult:
    r, o = c.run.result, c.oracle
    if not o.rules.d12:
        return CheckResult.of("not_buyable", [], na="needs D12 (config fund_detail)", needs="D12")
    if r.state != DecisionState.READY:
        return CheckResult.of("not_buyable", [], na="not ready")
    return CheckResult.of("not_buyable", [
        f"{x.option.option_id}: fund_buyable = 0 but listed"
        for x in r.options if "not_buyable" in o.violations(x.option)])


def check_explicit_constraints(c: Context) -> CheckResult:
    r, o = c.run.result, c.oracle
    if not o.rules.d13:
        return CheckResult.of("explicit_constraints", [], na="needs D13 (config constraint_rules)",
                              needs="D13")
    if r.state != DecisionState.READY:
        return CheckResult.of("explicit_constraints", [], na="not ready")
    if not (o.rules.fx_hard or o.rules.liquidity_hard):
        return CheckResult.of("explicit_constraints", [],
                              na="no explicit constraint that tests a product")
    problems = []
    for x in r.options:
        for rule in o.violations(x.option):
            if rule in ("fx_limit", "liquidity_need"):
                problems.append(f"{x.option.option_id}: breaks {rule} but listed")
    return CheckResult.of("explicit_constraints", problems)


def check_no_invented_data(c: Context) -> CheckResult:
    r, ev = c.run.result, c.run.evidence
    by_id = c.oracle.view.by_id
    excluded = ev.excluded_sources
    problems = []
    for i in sorted(r.evidence_ids()):
        d = by_id.get(i)
        if d is None:
            problems.append(f"result: evidence id {i} is not in the evidence")
        elif d.source in excluded:
            problems.append(f"result: {i} comes from the excluded source {d.source}")
    nums, dates = allowed_numbers(r, by_id)
    if c.run.narratives:
        shown_nums, shown_dates = display_numbers(r, ev, c.decision_config, by_id)
        nums |= shown_nums
        dates |= shown_dates
    for lang, d in sorted(c.run.narratives.items()):
        for key, s in sentences(d):
            own_nums, own_dates = set(), set()      # the rows this sentence cites itself (N14)
            for i in s.evidence_ids:
                row = by_id.get(i)
                if row is not None and row.source in excluded:
                    problems.append(f"text {lang}: {key}: cites {i} of the excluded source {row.source}")
                elif row is not None:
                    if row.value is not None:
                        own_nums.add(abs(row.value))
                    own_dates.add(row.as_of)
                    own_nums.add(float(row.as_of.year))
            text = re.sub(r"\bE[0-9a-f]{8}\b", " ", s.text)
            for tok, readings in token_readings(text):
                if not _matches(readings, nums | own_nums):
                    problems.append(f"text {lang}: {key}: number {tok} is not in the result or "
                                    f"its evidence or display facts: \"{s.text[:80]}\"")
            for dt in sorted(dates_in(text) - dates - own_dates):
                problems.append(f"text {lang}: {key}: date {dt} is not in the result or its evidence")
    return CheckResult.of("no_invented_data", problems)


def check_missing_data_shown(c: Context) -> CheckResult:
    r, ev = c.run.result, c.run.evidence
    failed = sorted(k for k, s in ev.source_status.items()
                    if s.status == "failed" or s.fallback_from)
    missing = sorted(ev.excluded_sources) + [f for f in failed if f not in ev.excluded_sources]
    if not missing:
        return CheckResult.of("missing_data_shown", [], na="no excluded or failed source")
    problems = []
    for src in missing:
        if not any(src in n.sources or src in n.message for n in r.data_quality):
            problems.append(f"{src}: no data-quality note names it")
    if c.compare is not None and c.compare.result.state == DecisionState.READY \
            and r.state == DecisionState.READY:
        base_by_id = {d.id: d for d in c.compare.evidence.datapoints}
        base = {o.option.option_id: o for o in c.compare.result.options}
        for o in r.options:
            b = base.get(o.option.option_id)
            if b is None:
                continue
            used = {base_by_id[i].source for i in b.evidence_ids if i in base_by_id}
            if used & set(ev.excluded_sources) and o.confidence > b.confidence + 1e-9:
                problems.append(f"{o.option.option_id}: confidence {o.confidence:.2f} > "
                                f"{b.confidence:.2f} without {sorted(used & set(ev.excluded_sources))}")
    return CheckResult.of("missing_data_shown", problems)


def check_bad_data_handled(c: Context) -> CheckResult:
    edits = c.run.evidence_edits
    if not edits:
        return CheckResult.of("bad_data_handled", [], na="no bad data in this scenario")
    r = c.run.result
    if r.state != DecisionState.READY:
        return CheckResult.of("bad_data_handled", [], na="not ready")
    factors = c.decision_config["confidence"]["flags"]
    problems = []
    for e in edits:
        rows = [d for d in c.run.evidence.datapoints if d.quantity == e.quantity
                and e.entity in (None, d.entity) and e.source in (None, d.source)]
        ids = {d.id for d in rows}
        for flag in e.add_flags:
            if flag == Flag.OUT_OF_RANGE:
                for o in r.options:
                    if ids & set(o.evidence_ids):
                        problems.append(f"{o.option.option_id}: uses an out_of_range row")
                if not any(Flag.OUT_OF_RANGE.value in n.flags for n in r.data_quality):
                    problems.append("no data-quality note for the out_of_range value")
            elif flag in factors:
                if not any(ids & set(o.evidence_ids) for o in r.options):
                    problems.append(f"{e.quantity} {e.entity}: no option uses the {flag} row "
                                    f"(the scenario tests nothing)")
                for o in r.options:
                    if ids & set(o.evidence_ids) and o.confidence > factors[flag] + 1e-9:
                        problems.append(f"{o.option.option_id}: uses a {flag} row but confidence "
                                        f"{o.confidence:.2f} > {factors[flag]}")
    return CheckResult.of("bad_data_handled", problems)


def check_questions(c: Context) -> CheckResult:
    r, rules = c.run.result, c.oracle.rules
    if not rules.unknown_blocking:
        asked = [q.question_id for q in r.questions if q.blocking and q.answer is None]
        if asked:
            return CheckResult.of("questions", [f"blocking question {asked} for a known text"])
        return CheckResult.of("questions", [], na="no unknown blocking text")
    problems = []
    if r.state != DecisionState.NEEDS_RM_INPUT:
        problems.append(f"unknown text {list(rules.unknown_blocking)} but state {r.state.value}")
    if r.options or r.rejected:
        problems.append("options are ranked although a blocking question is open")
    open_ids = {q.question_id for q in r.questions if q.blocking and q.answer is None}
    problems += [f"no open question {q}" for q in rules.unknown_blocking if q not in open_ids]
    return CheckResult.of("questions", problems)


NOT_MEASURED = ("llm: no API key", "budget:")   # template without an LLM try: not a finding


def check_narrator_valid(c: Context) -> CheckResult:
    texts = {lang: d for lang, d in c.run.narratives.items()
             if not (d.source == "template" and d.checks
                     and all(x.startswith(NOT_MEASURED) for x in d.checks))}
    if not texts:
        return CheckResult.of("narrator_valid", [], na="no LLM meeting text")
    problems = []
    for lang, d in sorted(texts.items()):
        if d.source != "llm":
            problems.append(f"{lang}: template text ({'; '.join(d.checks[:3]) or 'no reason'})")
        elif d.checks:
            problems.append(f"{lang}: validator findings: {'; '.join(d.checks[:3])}")
    return CheckResult.of("narrator_valid", problems)


def forbidden_hits(d: NarrativeDraft, phrases: Mapping[str, tuple[str, ...]],
                   labels: tuple[str, ...] = ()) -> list[str]:
    """Forbidden phrases in the text; option labels are removed first (a fund
    name such as "GARANTİ PORTFÖY ..." is not a guarantee)."""
    from rmprep.api.names import short_name
    from rmprep.narrator.validator import name_forms

    every = list(dict.fromkeys(p for ps in phrases.values() for p in ps))
    text = tr_norm(" ".join(s.text for _, s in sentences(d)))
    # full labels, the short screen names (n8 texts use them) and the issuers alone
    # ("Garanti Portföy" is a company, not a guarantee); lead fix 2026-10-12
    names = {tr_norm(x) for x in labels if x}
    for label in labels:
        if label:
            names.update(tr_norm(f) for f in name_forms(label))
            issuer, _ = short_name(label)
            if issuer:
                names.add(tr_norm(issuer))
    for label in sorted(names, key=len, reverse=True):
        text = text.replace(label, " ")
    return [p for p in every if tr_norm(p) in text]


def check_forbidden_phrases(c: Context) -> CheckResult:
    if not c.run.narratives:
        return CheckResult.of("forbidden_phrases", [], na="no meeting text")
    r = c.run.result
    labels = tuple(o.option.label for o in r.options) + tuple(x.option.label for x in r.rejected)
    return CheckResult.of("forbidden_phrases", [
        f"{lang}: \"{p}\"" for lang, d in sorted(c.run.narratives.items())
        for p in forbidden_hits(d, c.forbidden_phrases, labels)])


def check_traceability(c: Context) -> CheckResult:
    r = c.run.result
    by_id = c.oracle.view.by_id
    problems = []

    def known(i: str, where: str) -> None:
        d = by_id.get(i)
        if d is None:
            problems.append(f"{where}: unknown evidence id {i}")
        elif not d.source or d.as_of is None:
            problems.append(f"{where}: {i} has no source or date")

    for o in r.options:
        if not o.evidence_ids:
            problems.append(f"{o.option.option_id}: no evidence id")
        for i in o.evidence_ids:
            known(i, o.option.option_id)
    for x in r.rejected:
        for f in x.failed:
            for i in f.evidence_ids:
                known(i, f"rejected {x.option.option_id}")
    options = {o.option.option_id for o in r.options}
    for lang, d in sorted(c.run.narratives.items()):
        for key, s in sentences(d):
            if key in CITED_SECTIONS and not (s.option_ids or s.evidence_ids):
                problems.append(f"text {lang}: {key}: sentence without citation: \"{s.text[:60]}\"")
            problems += [f"text {lang}: {key}: unknown option {i}" for i in s.option_ids
                         if i not in options]
            for i in s.evidence_ids:
                known(i, f"text {lang}: {key}")
    return CheckResult.of("traceability", problems)


def _real_1y(r: DecisionResult, ev, decision_config: Mapping[str, Any]) -> dict[str, float]:
    """option_id -> real 1-year return in percent (display facts; missing = no key)."""
    from rmprep.decision.config import DecisionConfig
    from rmprep.decision.display import display_facts

    return {oid: f.real_1y.value
            for oid, f in display_facts(r, ev, DecisionConfig(raw=decision_config)).items()
            if f.real_1y is not None}


def check_diverse_recommendations(c: Context) -> CheckResult:
    """D19 (docs/decision.md section 10): for a client of recommend.profiles
    (Dengeli, Agresif) or with diversity, `recommended` has at most
    max_cash_like cash-like options and at least two asset classes, when the
    ranked options allow it (D19b floor on the real 1-year return included);
    every recommended option is inside the risk ceiling; no pick that the class
    rule moved up (not among the first three group heads) has a real 1-year
    return below recommend.min_real_return."""
    from rmprep.grouping import top_heads

    r, o, cfg = c.run.result, c.oracle, c.decision_config
    rec = cfg.get("recommend")
    if rec is None:
        return CheckResult.of("diverse_recommendations", [], na="needs D19 (config recommend)",
                              needs="D19")
    if r.state != DecisionState.READY or not r.recommended:
        return CheckResult.of("diverse_recommendations", [], na="no recommended options")
    rules = o.rules
    if rules.profile not in rec["profiles"] and not rules.diversity:
        return CheckResult.of("diverse_recommendations", [],
                              na=f"{rules.profile}: the class rule does not apply")

    by_id = {x.option.option_id: x for x in r.options}
    picks = [by_id[i] for i in r.recommended]
    cash = rec["cash_like"]
    floor = rec.get("min_real_return")
    real = _real_1y(r, c.run.evidence, cfg)
    problems = []
    for x in picks:
        if "risk_ceiling" in o.violations(x.option):
            problems.append(f"{x.option.option_id}: risk {o.risk(x.option):g} above the risk "
                            f"ceiling {rules.ceiling}")
    plain = {x.option.option_id for x in top_heads(r.options, len(r.recommended))}
    if floor is not None:
        for x in picks:
            v = real.get(x.option.option_id)
            if x.option.option_id not in plain and v is not None and v < floor:
                problems.append(f"{x.option.option_id}: picked by the class rule with a real "
                                f"1-year return {v:.1f} % below {floor:g} %")

    def eligible(x) -> bool:
        v = real.get(x.option.option_id)
        return x.option.kind != "deposit" and not (floor is not None and v is not None and v < floor)

    pool = [x for x in r.options if eligible(x) and not o.violations(x.option)]
    non_cash = [x for x in pool if x.option.asset_class != cash]
    classes = {x.option.asset_class for x in pool}
    n_cash = sum(1 for x in picks if x.option.asset_class == cash)
    if len(non_cash) >= 2 and n_cash > rec["max_cash_like"]:
        problems.append(f"{n_cash} {cash} recommendations (at most {rec['max_cash_like']}) "
                        f"although {len(non_cash)} other options are eligible")
    picked = {x.option.asset_class for x in picks}
    if len(classes) >= 2 and len(picked) < 2:
        problems.append(f"one asset class only ({sorted(picked)}) although the result has "
                        f"{len(classes)}: {sorted(classes)}")
    return CheckResult.of("diverse_recommendations", problems)


def check_allocation_projection(c: Context) -> CheckResult:
    """D27 (docs/decision.md section 17): the current split adds up to 100 and
    each point is inside its range; only RM or persona-text rows are active (the
    brief: no made-up client information in the ranking); each gap is the distance
    to the band edge; without an active row no option has the allocation_gap
    criterion, so the ranking is the one without D27."""
    from rmprep.contracts import ACTIVE_HOLDINGS_SOURCES
    from rmprep.decision.holdings import class_gap

    r = c.run.result
    if r.state != DecisionState.READY:
        return CheckResult.of("allocation_projection", [], na="not ready")
    rows = [b for b in r.allocation if b.current is not None]
    if not rows:
        return CheckResult.of("allocation_projection", [], na="needs D27 (config holdings)",
                              needs="D27")
    problems = []
    total = sum(b.current for b in rows)
    if abs(total - 100) > 0.5:
        problems.append(f"the current split adds up to {total:g}, not 100")
    for b in rows:
        lo = b.current if b.current_low is None else b.current_low
        hi = b.current if b.current_high is None else b.current_high
        if not lo <= b.current <= hi:
            problems.append(f"{b.asset_class}: current {b.current:g} outside its range {lo:g}-{hi:g}")
        if b.active != (b.current_source in ACTIVE_HOLDINGS_SOURCES):
            problems.append(f"{b.asset_class}: active={b.active} with source {b.current_source}")
        want = class_gap(b.current, None if b.low is None else (b.low, b.high))
        if (want is None) != (b.gap is None) or (want is not None and abs(want - b.gap) > 1e-6):
            problems.append(f"{b.asset_class}: gap {b.gap} but the band gives {want}")
    if not any(b.active for b in rows):
        with_gap = [x.option.option_id for x in r.options if "allocation_gap" in x.score_parts]
        if with_gap or r.effective_weights.get("allocation_gap"):
            problems.append(f"no active class, but allocation_gap is scored ({len(with_gap)} options)")
    return CheckResult.of("allocation_projection", problems)


def agent_problems(a, result: DecisionResult, decision_config: Mapping[str, Any]) -> list[str]:
    """The rules of spec section 6 on a stored done decision: the stored picks, dropped
    options and summary go through the agent's own check (rmprep.agent.checks) against
    the eval's pack (3 different candidates, the share cap, the D19 caps when the
    candidates allow them, every cite valid and known, F ids of the right option,
    numbers in the cited data, no forbidden phrase, a reason for each dropped engine
    option); then the labels and flags that code adds must match the cites."""
    from rmprep.agent.checks import check_decision
    from rmprep.decision.config import DecisionConfig

    d = a.decision
    problems = []
    if tuple(d.engine_top3) != tuple(result.recommended):
        problems.append(f"engine_top3 {list(d.engine_top3)} is not the run's "
                        f"{list(result.recommended)}")
    if a.pack is None:
        return problems + ["no data pack to check the decision against"]

    def reason(r) -> dict:
        return {"metin": r.text, "kaynaklar": list(r.cites)}

    raw = {"secimler": [{"option_id": p.option_id, "gerekceler": [reason(r) for r in p.reasons]}
                        for p in d.picks],
           "cikanlar": [{"option_id": p.option_id, "gerekce": reason(r)}
                        for p in d.dropped for r in p.reasons[:1]],
           "ozet": d.summary}
    picks, dropped, _, found = check_decision(raw, a.pack, DecisionConfig(decision_config),
                                              a.phrases, a.lang, labels=a.labels or None,
                                              words=a.words or None)
    problems += found
    if found:
        return problems
    for stored, want in ((d.picks, picks), (d.dropped, dropped)):
        for p, q in zip(stored, want):
            for r, w in zip(p.reasons, q.reasons):
                if tuple(r.labels) != tuple(w.labels):
                    problems.append(f"{p.option_id}: labels {list(r.labels)}, the cites need "
                                    f"{list(w.labels)}: \"{r.text[:60]}\"")
            for flag in ("uses_estimate", "uses_web"):
                if getattr(p, flag) != getattr(q, flag):
                    problems.append(f"{p.option_id}: {flag}={getattr(p, flag)}, the cites give "
                                    f"{getattr(q, flag)}")
    return problems


def check_agent_decision(c: Context) -> CheckResult:
    """E11: the stored agent decision of the run keeps the rules of spec section 6.
    n/a without a decision or with the agent off; a fallback (the engine's top 3)
    passes with its reason; a decision still running at the eval's deadline fails."""
    a = c.run.agent
    d = None if a is None else a.decision
    if d is None:
        why = "no agent decision" + (f" ({a.error})" if a is not None and a.error else "")
        return CheckResult.of("agent_decision", [], na=why)
    if d.state == "off":
        return CheckResult.of("agent_decision", [], na=f"agent off: {d.fallback_reason}")
    if d.state == "running":
        return CheckResult.of("agent_decision", [a.error or "deadline: still running"])
    if d.state == "fallback":
        return CheckResult("agent_decision", PASS, (f"fallback: {d.fallback_reason}",))
    return CheckResult.of("agent_decision", agent_problems(a, c.run.result, c.decision_config))


RUN_CHECKS: tuple[Callable[[Context], CheckResult], ...] = (
    check_rule5, check_risk_ceiling, check_not_buyable, check_explicit_constraints,
    check_no_invented_data, check_missing_data_shown, check_bad_data_handled, check_questions,
    check_narrator_valid, check_forbidden_phrases, check_traceability,
    check_diverse_recommendations, check_allocation_projection,
)


# --- per scenario ---------------------------------------------------------------

def check_consistency(sr: ScenarioRun) -> CheckResult:
    if len(sr.runs) < 2:
        return CheckResult.of("consistency", [], na="one run")
    first, problems = sr.runs[0], []
    for k, run in enumerate(sr.runs[1:], start=1):
        if run.result.run_id != first.result.run_id:
            problems.append(f"run {k}: run_id {run.result.run_id} != {first.result.run_id}")
        elif run.result.to_dict() != first.result.to_dict():
            problems.append(f"run {k}: same run_id, different result")
        for lang in sorted(set(first.narratives) | set(run.narratives)):
            a, b = first.narratives.get(lang), run.narratives.get(lang)
            if a is None or b is None or _text_key(a) != _text_key(b):
                problems.append(f"run {k}: the {lang} text differs (not from the cache)")
    return CheckResult.of("consistency", problems)


def _text_key(d: NarrativeDraft) -> tuple:
    """What must be equal between repeated texts (created_at is not: a
    template text is made again each time, an LLM text comes from the cache)."""
    return (d.to_dict()["sections"], d.source, d.model, d.prompt_version, d.checks)


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def phrase_findings(run: RunRecord, narrator_config) -> int | None:
    """The phrase findings of the current narrator validator on the texts of the
    run (the template text included, so no LLM call is needed)."""
    if narrator_config is None or run.approved is None or not run.narratives:
        return None
    from rmprep.narrator.facts import build_facts
    from rmprep.narrator.validator import validate

    facts = build_facts(run.approved, run.evidence)
    return sum(1 for lang, d in run.narratives.items()
               for f in validate(d.sections, facts, run.approved, narrator_config, lang)
               if f.startswith("phrase:"))


def metric_values(run: RunRecord, decision_config: Mapping[str, Any],
                  narrator_config=None) -> dict[str, Any]:
    """The metrics `expect` can name, of one run."""
    r = run.result
    ev = run.evidence
    o = Oracle(r, run.evidence, decision_config)
    top = [x for x in r.options if x.option.kind != "deposit"][:SENSITIVITY_TOP]
    risks = [o.risk(x.option) for x in top]
    funds = [x for x in r.options if x.option.kind == "fund"]
    best_fund = max((x.score for x in funds), default=None)
    deposit = next((x.score for x in r.options if x.option.kind == "deposit"), None)
    return {
        "state": r.state.value,
        "avg_risk": _mean(risks),
        "max_risk": max((x for x in risks if x is not None), default=None),
        "fx_count": sum(o.fx(x.option) for x in top),
        "fx_in_options": sum(o.fx(x.option) for x in r.options),
        "avg_sell_valor": _mean([o.sell_valor(x.option) for x in top]),
        "shortlist": [x.option.option_id for x in top],
        "not_buyable_in_options": sum("not_buyable" in o.violations(x.option) for x in r.options),
        "rejected": dict(Counter(f.rule_id for x in r.rejected for f in x.failed)),
        "baseline_below_best_fund": (None if deposit is None or best_fund is None
                                     else deposit < best_fund),
        "options": len(r.options),
        "max_sell_valor": max((v for v in (o.sell_valor(x.option) for x in r.options)
                               if v is not None), default=None),
        "evidence_rows": dict(Counter(d.source for d in ev.datapoints
                                      if d.source not in ev.excluded_sources)),
        "failed_sources": sorted(k for k, v in ev.source_status.items() if v.status == "failed"),
        "validator_phrase_findings": phrase_findings(run, narrator_config),
        "options_without_evidence": sum(1 for x in r.options if not x.evidence_ids),
        **_recommendation_metrics(r, decision_config),
    }


def _recommendation_metrics(r: DecisionResult, decision_config: Mapping[str, Any]) -> dict:
    """D19: the recommended top 3 (or the first three group heads without it)."""
    from rmprep.grouping import recommended, top_heads

    picks = recommended(r)
    cash = decision_config.get("recommend", {}).get("cash_like", "nakit_benzeri")
    return {
        "recommended": [x.option.option_id for x in picks],
        "recommended_cash_like": sum(1 for x in picks if x.option.asset_class == cash),
        "recommended_classes": len({x.option.asset_class for x in picks}),
        "recommended_plain_order": ([x.option.option_id for x in picks]
                                    == [x.option.option_id for x in top_heads(r.options, 3)]),
    }


DIRECTIONS = ("lower", "higher", "not_higher", "not_lower", "same", "changed")
ABSOLUTE = ("at_most", "at_least", "equals")
METRICS = ("state", "avg_risk", "max_risk", "fx_count", "fx_in_options", "avg_sell_valor",
           "shortlist", "not_buyable_in_options", "baseline_below_best_fund", "options",
           "rejected", "max_sell_valor", "evidence_rows", "failed_sources",
           "validator_phrase_findings", "options_without_evidence", "recommended",
           "recommended_cash_like", "recommended_classes", "recommended_plain_order")


def expect_errors(s: Scenario) -> list[str]:
    """Problems of the `expect` mapping of a scenario (unknown metric or form)."""
    out = []
    for key, want in s.expect.items():
        if key not in METRICS:
            out.append(f"expect: unknown metric {key!r}; known: {METRICS}")
        elif isinstance(want, str) and want in DIRECTIONS:
            if s.compare_to is None:
                out.append(f"expect.{key}: {want!r} needs compare_to")
        elif isinstance(want, Mapping):
            bad = sorted(set(want) - set(ABSOLUTE))
            if bad or not want:
                out.append(f"expect.{key}: use {ABSOLUTE}, got {sorted(want)}")
        elif key not in ("state", "baseline_below_best_fund", "recommended_plain_order"):
            out.append(f"expect.{key}: use a direction {DIRECTIONS} or {{at_most|at_least|equals: x}}")
    return out


def _compare(key: str, want: str, now, base) -> str | None:
    ok = {"lower": now < base, "higher": now > base, "not_higher": now <= base,
          "not_lower": now >= base, "same": now == base, "changed": now != base}[want]
    return None if ok else f"{key}: {now} is not {want} than/as {base}"


def check_sensitivity(sr: ScenarioRun, compare: ScenarioRun | None,
                      decision_config: Mapping[str, Any], narrator_config=None) -> CheckResult:
    s = sr.scenario
    if not s.expect:
        return CheckResult.of("sensitivity", [], na="no expectation")
    if not sr.runs:
        return CheckResult.of("sensitivity", [f"the scenario did not run: {sr.error}"])
    now = metric_values(sr.runs[0], decision_config, narrator_config)
    base = None
    if compare is not None and compare.runs:
        base = metric_values(compare.runs[0], decision_config, narrator_config)
    problems = list(expect_errors(s))
    undecided: list[str] = []
    for key, want in s.expect.items():
        if key not in METRICS:
            continue
        if now[key] is None or (isinstance(want, str) and want in DIRECTIONS
                                and base is not None and base[key] is None):
            undecided.append(f"{key}: no value in the evidence")
            continue
        if isinstance(want, str) and want in DIRECTIONS:
            if base is None:
                problems.append(f"{key}: the compared scenario {s.compare_to} has no run")
                continue
            p = _compare(key, want, now[key], base[key])
            if p:
                problems.append(p)
        elif isinstance(want, Mapping):
            v = now[key]
            for op, x in want.items():
                if isinstance(v, Mapping) and isinstance(x, Mapping):
                    v2 = {k: v.get(k, 0) for k in x}
                    ok = all(_op(op, v2[k], x[k]) for k in x)
                else:
                    ok = _op(op, v, x)
                if not ok:
                    problems.append(f"{key}: {v} is not {op} {x}")
        elif now[key] != want:
            problems.append(f"{key}: {now[key]!r} != {want!r}")
    if not problems and len(undecided) == len(s.expect):
        return CheckResult.of("sensitivity", [], na="; ".join(undecided))
    return CheckResult.of("sensitivity", problems)


def _op(op: str, v, x) -> bool:
    return {"at_most": lambda: v <= x, "at_least": lambda: v >= x, "equals": lambda: v == x}[op]()


# --- all ------------------------------------------------------------------------

@dataclass
class ScenarioChecks:
    scenario: Scenario
    runs: list[list[CheckResult]]           # per run, the RUN_CHECKS results
    scenario_checks: list[CheckResult]      # consistency, sensitivity
    error: str | None = None

    def all(self) -> list[CheckResult]:
        return [c for rs in self.runs for c in rs] + self.scenario_checks


def run_checks(runs: list[ScenarioRun], decision_config: Mapping[str, Any],
               forbidden_phrases: Mapping[str, tuple[str, ...]],
               narrator_config=None, *, agent: bool = False) -> list[ScenarioChecks]:
    """All checks of all scenarios; narrator_config (NarratorConfig) enables the
    metric validator_phrase_findings; agent adds the check agent_decision (E11)."""
    by_id = {sr.scenario.id: sr for sr in runs}
    run_checks_ = RUN_CHECKS + ((check_agent_decision,) if agent else ())
    out = []
    for sr in runs:
        compare = by_id.get(sr.scenario.compare_to) if sr.scenario.compare_to else None
        base_run = compare.runs[0] if compare is not None and compare.runs else None
        per_run = [[chk(Context(sr.scenario, run, decision_config, forbidden_phrases, base_run))
                    for chk in run_checks_] for run in sr.runs]
        sc = [check_consistency(sr),
              check_sensitivity(sr, compare, decision_config, narrator_config)]
        if sr.error:
            sc.insert(0, CheckResult("scenario_runs", FAIL, (sr.error,)))
        out.append(ScenarioChecks(sr.scenario, per_run, sc, sr.error))
    return out
