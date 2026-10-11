"""Validator of a narrative text against its facts pack (docs/narrator.md,
"Validator"). Deterministic. Each finding is one string "<rule>: <section>:
<what>", given to the LLM for its retry and kept in NarrativeDraft.checks.

Rules: number (every number and date comes from the facts), option (only the
named options), phrase (no forbidden phrase), citation (cited sentences, known
ids), disclaimer, section (all sections, in order, none empty), assumption
(the assumptions verbatim); N7: internal (no internal names or values outside
varsayimlar), coverage (an oneriler sentence per selected option), pointer
(the N7 pointer to the "Olası sorunlar" pane is gone in N9c: the text names no
screen); N9: talking (talking_points has 2-3 sentences, each with a title), tag (need
tags: every selected option, at most 3, each one of the persona's oncelikler);
N9c: label (a clause that names an ING deposit carries only ING rates as
percents), internal also catches the names of UI sections."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date

from rmprep.contracts import (
    BRIEF_MAX_CHARS,
    NARRATIVE_SECTIONS_V13,
    DecisionResult,
    NarrativeSection,
    NarrativeSentence,
    Persona,
)
from rmprep.narrator.config import NarratorConfig
from rmprep.narrator.facts import ING_RATES, INTERNAL_PARTS, Facts
from rmprep.narrator.template import INTERNAL_NAME, tr_lower

SECTIONS = NARRATIVE_SECTIONS_V13
CITED_SECTIONS = ("talking_points", "oneriler", "alternatifler", "dikkat")
TALKING_POINTS = (2, 3)                         # sentences of talking_points (N9)
MAX_TAGS = 3                                    # need tags per selected option
PERCENT_KEYS = ("confidence", "stability")     # 0..1 values that could be written as a percent
# facts that are internal values (N7): never in the text
INTERNAL_KEYS = ("score", "confidence", "stability", "data_quality", "rejected_count",
                 "rejected_rules")
VERBATIM_SECTIONS = ("varsayimlar",)            # engine text kept as it is
# N9c: names of screens / panes of the app; the text never points to them
UI_NAMES = ("Olası sorunlar", "Possible issues", "RM notları", "RM notes")
_CLAUSE = re.compile(r"[;:]|[.,](?!\d)")        # clause ends; a decimal mark is not one
_PERCENT = re.compile(r"%\s?\d+(?:[.,]\d+)*|\d+(?:[.,]\d+)*\s?%")

_IDS = re.compile(r"\bE[0-9a-f]{8}\b|\b(?:deposit|time_deposit|fund):\S+")
_DATE_TR = re.compile(r"(?<![\w.])(\d{1,2})\.(\d{1,2})\.(\d{4})(?![\w])")
_DATE_ISO = re.compile(r"(?<![\w-])(\d{4})-(\d{2})-(\d{2})(?![\w])")
_NUMBER = re.compile(r"(?<![\w])\d+(?:[.,]\d+)*(?![\w])")
_TR_FORMS = (re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?"), re.compile(r"\d+(?:,\d+)?"))
_EN_FORMS = (re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?"), re.compile(r"\d+(?:\.\d+)?"))
_PERIOD = re.compile(r"_(\d+)[my]$")


def _dates(text: str) -> tuple[set[date], str]:
    """Dates of the text (dd.mm.yyyy, yyyy-mm-dd) and the text without them."""
    found: set[date] = set()

    def take(d: int, m: int, y: int) -> str:
        try:
            found.add(date(y, m, d))
        except ValueError:
            return f"{d}.{m}.{y}"      # not a date: leave its numbers in
        return " "

    text = _DATE_ISO.sub(lambda g: take(int(g[3]), int(g[2]), int(g[1])), text)
    text = _DATE_TR.sub(lambda g: take(int(g[1]), int(g[2]), int(g[3])), text)
    return found, text


def dates_in(text: str) -> set[date]:
    return _dates(_IDS.sub(" ", text))[0]


def _readings(token: str) -> set[tuple[float, int]]:
    """(value, decimals) of a number token, read as Turkish and as English."""
    out = set()
    for forms, thousands, decimal in ((_TR_FORMS, ".", ","), (_EN_FORMS, ",", ".")):
        if any(f.fullmatch(token) for f in forms):
            plain = token.replace(thousands, "")
            whole, _, frac = plain.partition(decimal)
            out.add((float(f"{whole}.{frac}" if frac else whole), len(frac)))
    return out


def numbers_in(text: str) -> set[tuple[float, int]]:
    """Every reading (value, decimals) of every number of the text; ids and
    dates are not numbers. Signs are dropped (a range 1-3 is 1 and 3)."""
    text = _dates(_IDS.sub(" ", text))[1]
    return {r for tok in _NUMBER.findall(text) for r in _readings(tok)}


def _token_readings(text: str) -> list[tuple[str, set[tuple[float, int]]]]:
    text = _dates(_IDS.sub(" ", text))[1]
    return [(tok, _readings(tok)) for tok in _NUMBER.findall(text)]


def _allowed(f: Facts) -> tuple[set[float], set[float], set[date]]:
    """(public, internal, dates). Public: the numbers the text may use (every
    number of the facts and its texts, a few counts). Internal (N7): scores,
    confidence, stability, the values in reason texts of INTERNAL_PARTS,
    data-quality notes and their row counts, rejected counts."""
    public: set[float] = set()
    internal: set[float] = set()
    dates: set[date] = set()

    def walk(x, key: str, sink: set[float]) -> None:
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            sink.add(abs(float(x)))
            if key in PERCENT_KEYS:
                sink.add(abs(float(x)) * 100)
        elif isinstance(x, str):
            sink.update(v for v, _ in numbers_in(x))
            dates.update(dates_in(x))
            m = _PERIOD.search(x) if key == "quantity" else None
            if m:
                sink.add(float(m.group(1)))
        elif isinstance(x, Mapping):
            for k, v in x.items():
                if k == "reasons":                      # [[part, value, text], ...]
                    for part, value, text in v:
                        internal.add(abs(float(value)))
                        walk(text, k, internal if part in INTERNAL_PARTS else public)
                else:
                    walk(v, k, internal if k in INTERNAL_KEYS else sink)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v, key, sink)

    walk(f.to_dict(), "", public)
    c = f.client
    public.update(float(n) for n in (
        len(f.selected), len(f.alternatives), len(f.groups), len(f.warnings),
        len(f.open_questions), len(f.assumptions), len(f.named_options()),
        len(c["oncelikler"]), len(c["acik_kisitlar"])))
    internal.update(float(n) for n in (len(f.data_quality),
                                       *(len(n.evidence_ids) for n in f.data_quality)))
    public.update(float(d.year) for d in dates)
    return public, internal, dates


def _matches(readings: Iterable[tuple[float, int]], allowed: set[float]) -> bool:
    """A written number matches a fact if it is the fact rounded to its decimals."""
    return any(abs(x - a) <= 0.5 * 10 ** -d + 1e-9 for x, d in readings for a in allowed)


def _norm(text: str) -> str:
    return " ".join(tr_lower(text).split())


def _short(text: str, n: int = 80) -> str:
    return text if len(text) <= n else text[:n - 1] + "…"


def _check_sections(sections: Sequence[NarrativeSection]) -> list[str]:
    keys = [s.key for s in sections]
    out = [f"section: {k}: missing" for k in SECTIONS if k not in keys]
    out += [f"section: {k}: more than once" for k in SECTIONS if keys.count(k) > 1]
    if not out and tuple(keys) != SECTIONS:
        out.append(f"section: order must be {', '.join(SECTIONS)}")
    out += [f"section: {s.key}: empty" for s in sections
            if not any(x.text.strip() for x in s.sentences)]
    return out


def _check_numbers(sections, f: Facts) -> list[str]:
    public, internal, dates = _allowed(f)
    out = []
    for sec in sections:
        for s in sec.sentences:
            for tok, readings in _token_readings(s.text):
                if _matches(readings, public):
                    continue
                if _matches(readings, internal):
                    out.append(f"internal: {sec.key}: {tok} is an internal value (a score, "
                               f"a count or a data-quality detail): \"{_short(s.text)}\"")
                else:
                    out.append(f"number: {sec.key}: {tok} is not in the facts: "
                               f"\"{_short(s.text)}\"")
            for d in sorted(dates_in(s.text) - dates):
                out.append(f"number: {sec.key}: date {d.isoformat()} is not in the facts: "
                           f"\"{_short(s.text)}\"")
    return out


def _named_labels(f: Facts) -> list[str]:
    """Normalized labels of the named options, longest first."""
    return sorted({_norm(o.label) for o in f.named_options().values()}, key=len, reverse=True)


def _without_labels(text: str, labels: Sequence[str]) -> str:
    """Normalized text with the named labels taken out (a label may hold another
    label's words, or a word such as "garanti" in GARANTİ PORTFÖY ...)."""
    text = _norm(text)
    for lbl in labels:
        text = text.replace(lbl, " ")
    return text


def _check_options(sections, f: Facts, r: DecisionResult) -> list[str]:
    named = f.named_options()
    named_labels = _named_labels(f)
    others = [o.option for o in r.options if o.option.option_id not in named]
    others += [x.option for x in r.rejected]
    out = []
    for sec in sections:
        for s in sec.sentences:
            text = _without_labels(s.text, named_labels)
            raw = s.text
            for o in named.values():
                raw = raw.replace(o.label, " ")
            for o in others:
                if (_norm(o.label) in text or o.option_id in raw
                        or (o.kind == "fund" and o.entity
                            and re.search(rf"(?<![\w]){re.escape(o.entity)}(?![\w])", raw))):
                    out.append(f"option: {sec.key}: names {o.option_id}, which is not a selected "
                               f"option, the baseline or a group alternative: "
                               f"\"{_short(s.text)}\"")
    return out


def _check_phrases(sections, f: Facts, config: NarratorConfig) -> list[str]:
    """Forbidden phrases outside the option labels (a fund of Garanti Portföy is
    not a guarantee)."""
    phrases = list(dict.fromkeys(p for ps in config.forbidden_phrases.values() for p in ps))
    labels = _named_labels(f)
    out = []
    for sec in sections:
        for s in sec.sentences:
            text = _without_labels(s.text, labels)
            out += [f"phrase: {sec.key}: forbidden phrase \"{p}\": \"{_short(s.text)}\""
                    for p in phrases if _norm(p) in text]
    return out


def _check_citations(sections, f: Facts) -> list[str]:
    options, evidence = f.named_options(), f.evidence_ids()
    out = []
    for sec in sections:
        for s in sec.sentences:
            if sec.key in CITED_SECTIONS and not (s.option_ids or s.evidence_ids):
                out.append(f"citation: {sec.key}: sentence without citation: "
                           f"\"{_short(s.text)}\"")
            out += [f"citation: {sec.key}: unknown option id {i}" for i in s.option_ids
                    if i not in options]
            out += [f"citation: {sec.key}: unknown evidence id {i}" for i in s.evidence_ids
                    if i not in evidence]
    return out


def _check_internal_names(sections) -> list[str]:
    out = [f"internal: {sec.key}: internal name \"{m}\": \"{_short(s.text)}\""
           for sec in sections if sec.key not in VERBATIM_SECTIONS
           for s in sec.sentences for m in INTERNAL_NAME.findall(s.text)]
    ui = [(u, _norm(u)) for u in UI_NAMES]
    out += [f"internal: {sec.key}: the text names the screen section \"{u}\": "
            f"\"{_short(s.text)}\""
            for sec in sections for s in sec.sentences for u, nu in ui if nu in _norm(s.text)]
    return out


def _ing_names(f: Facts) -> list[str]:
    """Normalized names of the ING deposit options: the label, the label without
    its bracket, and both without the leading "ING"."""
    out: set[str] = set()
    for o in f.named_options().values():
        if o.kind not in ("deposit", "time_deposit"):
            continue
        for name in (o.label, re.sub(r"\s*\(.*?\)", "", o.label)):
            n = _norm(name)
            out.add(n)
            prefix = _norm("ING ") + " "            # Turkish lower case: "ıng "
            if n.startswith(prefix):
                out.add(n[len(prefix):])
    return sorted((n for n in out if n), key=len, reverse=True)


def _check_ing_labels(sections, f: Facts) -> list[str]:
    """N9c: in a clause that names an ING deposit, every percent must be an ING
    rate of the facts (a market rate next to the ING name is a wrong label).
    Clause = the text between ; , : and full stops. A contrast in another clause
    ("ING %23, piyasa ise %43,82") passes; a false finding costs one retry."""
    names = _ing_names(f)
    if not names:
        return []
    rates = {n.value for o in f.named_options().values() for n in o.numbers
             if n.name in ING_RATES}
    out = []
    for sec in sections:
        if sec.key in VERBATIM_SECTIONS:
            continue
        for s in sec.sentences:
            for clause in _CLAUSE.split(s.text):
                if not any(n in _norm(clause) for n in names):
                    continue
                for tok in _PERCENT.findall(clause):
                    readings = _token_readings(tok)
                    if not readings or not _matches(readings[0][1], rates):
                        out.append(f"label: {sec.key}: {tok.strip()} is not an ING rate but "
                                   f"stands next to an ING product name: \"{_short(s.text)}\"")
    return out


def _check_coverage(sections, f: Facts) -> list[str]:
    cited = {i for sec in sections if sec.key == "oneriler" for s in sec.sentences
             for i in s.option_ids}
    return [f"coverage: oneriler: no sentence for the selected option {o.option_id} "
            f"({o.label})" for o in f.selected if o.option_id not in cited]


def _check_talking_points(sections) -> list[str]:
    tp = [s for sec in sections if sec.key == "talking_points" for s in sec.sentences]
    low, high = TALKING_POINTS
    out = []
    if tp and not low <= len(tp) <= high:
        out.append(f"talking: talking_points: {low}-{high} sentences, not {len(tp)}")
    out += [f"talking: talking_points: a sentence without a title: \"{_short(s.text)}\""
            for s in tp if not s.title.strip()]
    return out


def validate_need_tags(tags: Mapping[str, Sequence[str]], persona: Persona) -> list[str]:
    """Findings for tags that are not one of the persona's oncelikler (compared
    with Turkish lower-casing)."""
    known = {_norm(p) for p in persona.oncelikler}
    return [f"tag: {oid}: \"{t}\" is not one of the client's priorities"
            for oid, ts in tags.items() for t in ts if _norm(t) not in known]


def _check_need_tags(tags: Mapping[str, Sequence[str]], f: Facts,
                     r: DecisionResult) -> list[str]:
    selected = [o.option_id for o in f.selected]
    out = validate_need_tags(tags, r.persona)
    out += [f"tag: {oid}: not a selected option" for oid in tags if oid not in selected]
    out += [f"tag: {oid}: no need_tags entry" for oid in selected if oid not in tags]
    out += [f"tag: {oid}: at most {MAX_TAGS} tags, not {len(ts)}"
            for oid, ts in tags.items() if len(ts) > MAX_TAGS]
    return out


def persona_wording(tags: Mapping[str, Sequence[str]], persona: Persona) -> dict[str, tuple[str, ...]]:
    """Tags as the persona writes them (validated tags; others dropped)."""
    written = {_norm(p): p for p in persona.oncelikler}
    return {oid: tuple(dict.fromkeys(written[_norm(t)] for t in ts if _norm(t) in written))
            for oid, ts in tags.items()}


def validate_brief(text: str, cite: Sequence[str], f: Facts, r: DecisionResult,
                   config: NarratorConfig, lang: str) -> tuple[str, ...]:
    """N10: the rules that apply to the dashboard brief (one short text): length,
    numbers, options, forbidden phrases, citations, internal names and values,
    the ING label rule. f: the brief facts (the top 3 as the selection, no baseline)."""
    limit = min(config.brief.max_chars if config.brief else BRIEF_MAX_CHARS, BRIEF_MAX_CHARS)
    out = []
    if not text.strip():
        out.append("length: brief: the text is empty")
    if len(text) > limit:
        out.append(f"length: brief: {len(text)} characters, at most {limit}")
    sentence = NarrativeSentence(text, tuple(c for c in cite if ":" in c),
                                 tuple(c for c in cite if ":" not in c))
    sections = [NarrativeSection("ozet", (sentence,))]
    out += _check_numbers(sections, f)
    out += _check_options(sections, f, r)
    out += _check_phrases(sections, f, config)
    out += _check_citations(sections, f)
    out += _check_internal_names(sections)
    out += _check_ing_labels(sections, f)
    return tuple(x.replace(": ozet:", ": brief:", 1) for x in out)


def validate(sections: Sequence[NarrativeSection], f: Facts, r: DecisionResult,
             config: NarratorConfig, lang: str,
             need_tags: Mapping[str, Sequence[str]] | None = None) -> tuple[str, ...]:
    """All findings of the text; () means it passed. r is the result the facts
    were built from (the validator needs the names the facts leave out). With
    need_tags (N9), the tags are checked too."""
    out = _check_sections(sections)
    out += _check_numbers(sections, f)
    out += _check_options(sections, f, r)
    out += _check_phrases(sections, f, config)
    out += _check_citations(sections, f)
    out += _check_internal_names(sections)
    out += _check_coverage(sections, f)
    out += _check_ing_labels(sections, f)
    out += _check_talking_points(sections)
    if need_tags is not None:
        out += _check_need_tags(need_tags, f, r)
    everything = _norm(" ".join(s.text for sec in sections for s in sec.sentences))
    if _norm(config.disclaimer[lang]) not in everything:
        out.append(f"disclaimer: the text must contain \"{config.disclaimer[lang]}\"")
    varsayimlar = _norm(" ".join(s.text for sec in sections if sec.key == "varsayimlar"
                                 for s in sec.sentences))
    out += [f"assumption: varsayimlar: missing \"{a}\"" for a in f.assumptions
            if _norm(a) not in varsayimlar]
    return tuple(out)
