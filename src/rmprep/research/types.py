"""Types of the web research (docs/research.md): sources, findings, the research
of one product and the answer to one RM question. Plain dataclasses with
to_dict / from_dict (cache files, API JSON); not part of contracts.py, because
no other module reads them."""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass
from datetime import datetime

from rmprep.contracts import TR_TZ

TOPICS = ("urun", "sirket", "soru", "haber", "strateji", "yonetici_sirket", "dikkat", "is", "finansal", "sermaye")
SHAPE_VERSION = 2              # 2: short bullets and news (docs/research.md "v2"); 1: the long summary
CONFIDENCE = ("low", "medium", "high")


class ResearchError(Exception):
    """A provider call failed. kind: auth | credit | rate_limit | server | connection | request.
    cost_usd: what the failed call cost (a paid call whose reply was bad); 0 when it was not billed."""

    def __init__(self, kind: str, message: str, cost_usd: float = 0.0):
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message
        self.cost_usd = cost_usd


@dataclass(frozen=True)
class Source:
    url: str
    title: str = ""
    published: str = ""            # YYYY-MM-DD or ""

    def to_dict(self) -> dict:
        return {"url": self.url, "title": self.title, "published": self.published}

    @classmethod
    def from_dict(cls, d: dict) -> Source:
        return cls(d["url"], d.get("title", ""), d.get("published", ""))


@dataclass(frozen=True)
class Finding:
    text: str
    topic: str                     # one of TOPICS
    sources: tuple[Source, ...]    # at least one
    confidence: str = "medium"     # low | medium | high (as the provider reports it)
    date: str = ""                 # YYYY-MM-DD; news only
    id: str = ""                   # "F" + 8 hex; set by the container (finding_id), never by a provider

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("a finding needs a text")
        if self.topic not in TOPICS:
            raise ValueError(f"topic must be one of {TOPICS}, got {self.topic!r}")
        if self.confidence not in CONFIDENCE:
            raise ValueError(f"confidence must be one of {CONFIDENCE}, got {self.confidence!r}")
        if not self.sources:
            raise ValueError("a finding needs at least one source")

    def to_dict(self) -> dict:
        return {"text": self.text, "topic": self.topic, "confidence": self.confidence,
                "sources": [s.to_dict() for s in self.sources], "date": self.date, "id": self.id}

    @classmethod
    def from_dict(cls, d: dict) -> Finding:
        return cls(d["text"], d["topic"], tuple(Source.from_dict(s) for s in d["sources"]),
                   d.get("confidence", "medium"), d.get("date", ""), d.get("id", ""))


def finding_id(option_id: str, date: str, text: str, n: int = 0) -> str:
    """A stable id of a finding: "F" + 8 hex of sha1(option|date|text); n > 0 (a repeat in
    one container) is added to the hashed text."""
    raw = f"{option_id}|{date}|{text}" + (f"|{n}" if n else "")
    return "F" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def _with_ids(option_id: str, *groups: tuple[Finding, ...]) -> tuple[tuple[Finding, ...], ...]:
    """The groups with every id recomputed from the final text; unique over all groups
    (a repeat gets n = 1, 2, ... in the order of the groups, then of the items)."""
    used: set[str] = set()
    out = []
    for group in groups:
        items = []
        for f in group:
            n = 0
            fid = finding_id(option_id, f.date, f.text)
            while fid in used:
                n += 1
                fid = finding_id(option_id, f.date, f.text, n)
            used.add(fid)
            items.append(dataclasses.replace(f, id=fid))
        out.append(tuple(items))
    return tuple(out)


def _aware(t: datetime) -> datetime:
    if t.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")
    return t.astimezone(TR_TZ)


@dataclass(frozen=True)
class ProductResearch:
    option_id: str
    label: str
    company: str                   # "" when no source names it
    summary: str                   # "" when no source supports it
    findings: tuple[Finding, ...]
    lang: str
    provider: str                  # exa | claude | "" (no provider answered)
    created_at: datetime
    cost_usd: float = 0.0
    checks: tuple[str, ...] = ()   # e.g. "2 findings without a valid source dropped"
    error: str = ""                # the research failed; findings are empty
    news: tuple[Finding, ...] = ()  # dated, newest first (v2)
    news_days: int = 0             # the window of the news search (v2)
    version: int = SHAPE_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", _aware(self.created_at))
        news, findings = _with_ids(self.option_id, self.news, self.findings)    # news first
        object.__setattr__(self, "news", news)
        object.__setattr__(self, "findings", findings)

    def to_dict(self) -> dict:
        return {"option_id": self.option_id, "label": self.label, "company": self.company,
                "summary": self.summary, "findings": [f.to_dict() for f in self.findings],
                "lang": self.lang, "provider": self.provider,
                "created_at": self.created_at.isoformat(), "cost_usd": self.cost_usd,
                "checks": list(self.checks), "error": self.error,
                "news": [n.to_dict() for n in self.news], "news_days": self.news_days,
                "version": self.version}

    @classmethod
    def from_dict(cls, d: dict) -> ProductResearch:
        return cls(d["option_id"], d["label"], d["company"], d["summary"],
                   tuple(Finding.from_dict(f) for f in d["findings"]), d["lang"], d["provider"],
                   datetime.fromisoformat(d["created_at"]), float(d.get("cost_usd", 0.0)),
                   tuple(d.get("checks", ())), d.get("error", ""),
                   tuple(Finding.from_dict(n) for n in d.get("news", ())), int(d.get("news_days", 0)),
                   int(d.get("version", 1)))


@dataclass(frozen=True)
class QuestionAnswer:
    question: str
    summary: str
    findings: tuple[Finding, ...]
    lang: str
    provider: str
    created_at: datetime
    cost_usd: float = 0.0
    checks: tuple[str, ...] = ()
    error: str = ""
    version: int = SHAPE_VERSION
    option_id: str = ""            # the product of a product question; "" for a run question

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", _aware(self.created_at))
        object.__setattr__(self, "findings", _with_ids(self.option_id, self.findings)[0])

    def to_dict(self) -> dict:
        return {"question": self.question, "summary": self.summary,
                "findings": [f.to_dict() for f in self.findings], "lang": self.lang,
                "provider": self.provider, "created_at": self.created_at.isoformat(),
                "cost_usd": self.cost_usd, "checks": list(self.checks), "error": self.error,
                "version": self.version, "option_id": self.option_id}

    @classmethod
    def from_dict(cls, d: dict) -> QuestionAnswer:
        return cls(d["question"], d["summary"], tuple(Finding.from_dict(f) for f in d["findings"]),
                   d["lang"], d["provider"], datetime.fromisoformat(d["created_at"]),
                   float(d.get("cost_usd", 0.0)), tuple(d.get("checks", ())), d.get("error", ""),
                   int(d.get("version", 1)), d.get("option_id", ""))
