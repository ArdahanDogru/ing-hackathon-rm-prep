"""Readable check results for the RM (A4, 2026-10-17; docs/agent.md).

`checks.check_decision` writes its problems in English for the model (they go
back to it as "sorunlar"). The RM sees them in the "Kontrol" box: this module
turns each known form into a short TR / EN sentence with the fund code instead
of the option id. An unknown form keeps its text.
"""

from __future__ import annotations

import re

_CLASSES = {
    "nakit_benzeri": {"TR": "nakit benzeri", "EN": "cash-like"},
    "borclanma": {"TR": "borçlanma", "EN": "bonds"},
    "hisse": {"TR": "hisse", "EN": "equity"},
    "altin_doviz": {"TR": "altın / döviz", "EN": "gold / FX"},
    "dengeli": {"TR": "dengeli", "EN": "balanced"},
}


def code(option_id: str) -> str:
    """"fund:PPN" -> "PPN"; an ING deposit keeps a readable name."""
    kind, _, rest = option_id.partition(":")
    if kind == "deposit":
        return "ING Turuncu Hesap"
    if kind == "time_deposit":
        return "ING e-Vadeli"
    return rest or option_id


def _cls(c: str, lang: str) -> str:
    return _CLASSES.get(c, {}).get(lang, c)


# (pattern on the text after "<option id>: ", TR, EN); groups are named
_PER_OPTION = [
    (r"a reason needs metin and kaynaklar", "bir gerekçede metin veya kaynak eksik",
     "a reason lacks its text or its sources"),
    (r"empty reason", "bir gerekçe boş", "a reason is empty"),
    (r"reason over (?P<n>\d+) words.*", "bir gerekçe {n} kelimeden uzun", "a reason is over {n} words"),
    (r"reason without a citation.*", "bir gerekçenin kaynağı gösterilmemiş", "a reason cites no source"),
    (r"(bad citation|unknown evidence id|unknown finding id|unknown score part|unknown portfolio class).*",
     "bir kaynak gösterimi geçersiz", "a cited source is not valid"),
    (r"finding \S+ does not belong to .*", "başka bir ürünün web bulgusu gösterilmiş",
     "a web finding of another product is cited"),
    (r"date (?P<d>\S+) not in the cited data.*", "{d} tarihi gösterilen kaynaklarda yok",
     "the date {d} is not in the cited sources"),
    (r"number (?P<n>\S+) not in the cited data.*", "“{n}” sayısı gösterilen kaynaklarda yok",
     "the number “{n}” is not in the cited sources"),
    (r"forbidden phrase \"(?P<p>[^\"]+)\".*", "yasak ifade: “{p}”", "a forbidden phrase: “{p}”"),
    (r"1-3 reasons, got (?P<k>\d+)", "1–3 gerekçe olmalı, {k} verildi", "1–3 reasons needed, {k} given"),
]
_GLOBAL = [
    (r"(?P<n>\d+) shares in the picks \(at most (?P<m>\d+)\)", "seçimde {n} hisse var (en fazla {m})",
     "{n} shares in the picks (at most {m})"),
    (r"(?P<k>\d+) options of class (?P<c>\w+) \(at most (?P<m>\d+) per class.*",
     "{c} sınıfından {k} ürün seçilmiş (en fazla {m})", "{k} {c} options picked (at most {m})"),
    (r"(?P<k>\d+) (?P<c>\w+) options \(at most (?P<m>\d+);.*",
     "{c} sınıfından {k} ürün seçilmiş (en fazla {m})", "{k} {c} options picked (at most {m})"),
    (r"needs (?P<n>\d+) picks, got (?P<k>\d+)", "{n} seçim olmalı, {k} verildi", "{n} picks needed, {k} given"),
    (r"a pick needs an option_id", "bir seçimde ürün yok", "a pick has no product"),
    (r"(?P<i>\S+) is not a candidate.*", "{i} aday listesinde yok", "{i} is not a candidate"),
    (r"(?P<i>\S+) is picked twice", "{i} iki kez seçilmiş", "{i} is picked twice"),
    (r"dropped: (?P<i>\S+) of the engine's top 3 is dropped without a reason",
     "motorun ilk 3'ündeki {i} gerekçesiz çıkarılmış", "{i} of the engine's top 3 is dropped without a reason"),
    (r"dropped: (?P<i>\S+) is not an engine top-3 option.*",
     "{i} motorun ilk 3'ünden çıkarılan bir ürün değil", "{i} is not a dropped engine top-3 option"),
    (r"summary \(ozet\) is empty", "özet boş", "the summary is empty"),
    (r"summary over (?P<n>\d+) words", "özet {n} kelimeden uzun", "the summary is over {n} words"),
    (r"summary: forbidden phrase \"(?P<p>[^\"]+)\"", "özette yasak ifade: “{p}”",
     "a forbidden phrase in the summary: “{p}”"),
    (r"summary: number (?P<n>\S+) not in the data", "özetteki “{n}” sayısı verilerde yok",
     "the number “{n}” of the summary is not in the data"),
]
_OPTION_PREFIX = re.compile(r"^(?P<oid>(fund|etf|stock|deposit|time_deposit):[^:\s]+): (?P<rest>.*)$", re.S)


def _fill(match: re.Match, text: str, lang: str) -> str:
    vals = {k: (code(v) if k == "i" else _cls(v, lang) if k == "c" else v)
            for k, v in match.groupdict().items() if v is not None}
    return text.format(**vals)


def explain(problem: str, lang: str = "TR") -> str:
    """One problem of check_decision as a short sentence for the RM."""
    i = 1 if lang == "TR" else 2
    m = _OPTION_PREFIX.match(problem)
    if m:
        for pattern, *texts in _PER_OPTION:
            hit = re.fullmatch(pattern, m.group("rest"), re.S)
            if hit:
                return f"{code(m.group('oid'))}: {_fill(hit, texts[i - 1], lang)}"
        return problem
    for pattern, *texts in _GLOBAL:
        hit = re.fullmatch(pattern, problem, re.S)
        if hit:
            return _fill(hit, texts[i - 1], lang)
    return problem
