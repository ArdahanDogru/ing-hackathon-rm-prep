"""Validator of a narrative text against its facts pack (docs/narrator.md,
"Validator"). Deterministic. Each finding is one string "<rule>: <section>:
<what>", given to the LLM for its retry and kept in NarrativeDraft.checks.

Rules: number (every number and date comes from the facts), option (only the
named options), phrase (no forbidden phrase), citation (cited sentences, known
ids), disclaimer, section (all sections, in order, none empty), assumption
(the assumptions verbatim)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date

from rmprep.contracts import NARRATIVE_SECTIONS, DecisionResult, NarrativeSection
from rmprep.narrator.config import NarratorConfig
from rmprep.narrator.facts import Facts
from rmprep.narrator.template import tr_lower

CITED_SECTIONS = ("oneriler", "alternatifler", "dikkat")
PERCENT_KEYS = ("confidence", "stability")     # 0..1 facts the text may write as a percent

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


def _allowed(f: Facts) -> tuple[set[float], set[date]]:
    """Numbers and dates the text may use: every number of the facts pack (and
    in its texts), a few counts, and the percent form of confidence/stability."""
    numbers: set[float] = set()
    dates: set[date] = set()

    def walk(x, key: str = "") -> None:
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            numbers.add(abs(float(x)))
            if key in PERCENT_KEYS:
                numbers.add(abs(float(x)) * 100)
        elif isinstance(x, str):
            numbers.update(v for v, _ in numbers_in(x))
            dates.update(dates_in(x))
            m = _PERIOD.search(x) if key == "quantity" else None
            if m:
                numbers.add(float(m.group(1)))
        elif isinstance(x, Mapping):
            for k, v in x.items():
                walk(v, k)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v, key)

    walk(f.to_dict())
    c = f.client
    numbers.update(float(n) for n in (
        len(f.selected), len(f.alternatives), len(f.groups), len(f.warnings),
        len(f.data_quality), len(f.open_questions), len(f.assumptions), len(f.named_options()),
        len(c["oncelikler"]), len(c["acik_kisitlar"])))
    numbers.update(float(d.year) for d in dates)
    return numbers, dates


def _matches(readings: Iterable[tuple[float, int]], allowed: set[float]) -> bool:
    """A written number matches a fact if it is the fact rounded to its decimals."""
    return any(abs(x - a) <= 0.5 * 10 ** -d + 1e-9 for x, d in readings for a in allowed)


def _norm(text: str) -> str:
    return " ".join(tr_lower(text).split())


def _short(text: str, n: int = 80) -> str:
    return text if len(text) <= n else text[:n - 1] + "…"


def _check_sections(sections: Sequence[NarrativeSection]) -> list[str]:
    keys = [s.key for s in sections]
    out = [f"section: {k}: missing" for k in NARRATIVE_SECTIONS if k not in keys]
    out += [f"section: {k}: more than once" for k in NARRATIVE_SECTIONS if keys.count(k) > 1]
    if not out and tuple(keys) != NARRATIVE_SECTIONS:
        out.append(f"section: order must be {', '.join(NARRATIVE_SECTIONS)}")
    out += [f"section: {s.key}: empty" for s in sections
            if not any(x.text.strip() for x in s.sentences)]
    return out


def _check_numbers(sections, f: Facts) -> list[str]:
    numbers, dates = _allowed(f)
    out = []
    for sec in sections:
        for s in sec.sentences:
            for tok, readings in _token_readings(s.text):
                if not _matches(readings, numbers):
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


def validate(sections: Sequence[NarrativeSection], f: Facts, r: DecisionResult,
             config: NarratorConfig, lang: str) -> tuple[str, ...]:
    """All findings of the text; () means it passed. r is the result the facts
    were built from (the validator needs the names the facts leave out)."""
    out = _check_sections(sections)
    out += _check_numbers(sections, f)
    out += _check_options(sections, f, r)
    out += _check_phrases(sections, f, config)
    out += _check_citations(sections, f)
    everything = _norm(" ".join(s.text for sec in sections for s in sec.sentences))
    if _norm(config.disclaimer[lang]) not in everything:
        out.append(f"disclaimer: the text must contain \"{config.disclaimer[lang]}\"")
    varsayimlar = _norm(" ".join(s.text for sec in sections if sec.key == "varsayimlar"
                                 for s in sec.sentences))
    out += [f"assumption: varsayimlar: missing \"{a}\"" for a in f.assumptions
            if _norm(a) not in varsayimlar]
    return tuple(out)
