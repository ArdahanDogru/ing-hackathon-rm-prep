"""Exa search provider (docs/research.md sections 5 and 8): one product research is two
POST /search calls (highlights with a topic schema per kind, then news of the last
days); a question is one call. Structured output with field-level grounding. A finding
is kept only with a citation that is a result of the same call (checks.sources_for).
Request shapes follow Exa's build-with-exa skill (query + highlights; other fields
only for a stated need: the news call states its window). The key goes only into the
x-api-key header. This module returns raw findings; the service shapes them."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta

import httpx

from rmprep.contracts import TR_TZ, ProductOption
from rmprep.research.checks import is_web_url, norm_url, sources_for, tr_lower
from rmprep.research.config import ExaConfig
from rmprep.research.types import Finding, ProductResearch, QuestionAnswer, ResearchError, Source

# Findings are objects, so that Exa grounds each one (bulgular[i].metin); an array of
# strings gets one citation list for the whole array (probe 2026-10-14).
TOPICS_BY_KIND = {"fund": ("strateji", "yonetici_sirket", "dikkat"),
                  "etf": ("strateji", "yonetici_sirket", "dikkat"),
                  "stock": ("is", "finansal", "sermaye")}
_FUND_HELP = ("strateji: what it invests in; yonetici_sirket: one fact about the managing company; "
              "dikkat: an unusual event (merger, manager change, regulatory step), only if there is one")
TOPIC_HELP = {"fund": _FUND_HELP, "etf": _FUND_HELP,
              "stock": "is: the business; finansal: the latest results; "
                       "sermaye: capital actions (dividend, capital increase, buyback)"}


def product_schema(kind: str) -> dict:
    topics = TOPICS_BY_KIND[kind]
    return {
        "type": "object",
        "properties": {
            "sirket": {"type": "string",
                       "description": "the name of the company that manages or issues the product"},
            "bulgular": {"type": "array", "items": {"type": "object", "properties": {
                "konu": {"type": "string", "description": f"one of: {' | '.join(topics)}. {TOPIC_HELP[kind]}"},
                "metin": {"type": "string", "description": "one sourced bullet of at most 20 words"}},
                "required": ["konu", "metin"]}},
        },
        "required": ["sirket", "bulgular"],
    }


def _bullets_schema(key: str, description: str) -> dict:
    return {"type": "object",
            "properties": {key: {"type": "array", "items": {"type": "object", "properties": {
                "metin": {"type": "string", "description": description}},
                "required": ["metin"]}}},
            "required": [key]}


NEWS_SCHEMA = _bullets_schema("haberler", "what happened, one sentence of at most 20 words")
QUESTION_SCHEMA = _bullets_schema("bulgular", "one sourced bullet of at most 20 words")
CONTEXT = {"TR": " İlgili ürünler: {products}.", "EN": " Related products: {products}."}


def option_code(option: ProductOption) -> str:
    """fund:PPN -> PPN"""
    return option.option_id.split(":", 1)[-1]


def error_kind(status: int) -> str:
    if status in (401, 403):
        return "auth"
    if status == 402:
        return "credit"
    if status == 429:
        return "rate_limit"
    if status >= 500:
        return "server"
    return "request"


def result_sources(body: Mapping) -> dict[str, Source]:
    out: dict[str, Source] = {}
    for r in body.get("results") or ():
        url = str((r or {}).get("url") or "")
        if url and is_web_url(url):
            out.setdefault(norm_url(url), Source(url, str(r.get("title") or ""),
                                                 str(r.get("publishedDate") or "")[:10]))
    return out


def _output(body: Mapping) -> tuple[Mapping, list]:
    out = body.get("output") or {}
    content = out.get("content") if isinstance(out, Mapping) else None
    if not isinstance(content, Mapping):
        raise ResearchError("request", "the reply has no structured output", _cost(body))   # billed
    return content, list(out.get("grounding") or ())


_ASCII = str.maketrans("şıöüçğ", "sioucg")


def _topic_for(kind: str, item: Mapping) -> str | None:
    """The allowed topic of the kind that the konu of the item equals or starts with, else None."""
    konu = tr_lower(str(item.get("konu") or "")).translate(_ASCII)
    konu = "_".join(konu.replace("-", " ").split())
    if not konu:
        return None
    for topic in TOPICS_BY_KIND.get(kind, ()):
        if konu == topic or konu.startswith(topic):
            return topic
    return None


def _iso_date(text: str) -> bool:
    """Exactly YYYY-MM-DD with digits and a real day (fromisoformat alone also takes week dates)."""
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _newest(sources: Iterable[Source]) -> str:
    """The newest valid publication date (YYYY-MM-DD) of the sources; "" when none has one."""
    return max((s.published for s in sources if _iso_date(s.published)), default="")


def _findings(content: Mapping, key: str, grounding: list, results: Mapping[str, Source],
              domains: Iterable[str], topic_of: Callable[[Mapping], str | None], *,
              dated: bool = False) -> tuple[list[Finding], int, int]:
    """Findings of content[key]. Second value: items dropped without a valid source.
    Third: sourced items whose topic topic_of does not know (dropped)."""
    findings, dropped, unknown = [], 0, 0
    for i, item in enumerate(content.get(key) or ()):
        if not isinstance(item, Mapping):
            continue
        text = str(item.get("metin") or "").strip()
        if not text:
            continue
        sources, conf = sources_for(f"{key}[{i}]", grounding, results, domains)
        if not sources:
            dropped += 1
            continue
        topic = topic_of(item)
        if topic is None:
            unknown += 1
            continue
        findings.append(Finding(text, topic, sources, conf, _newest(sources) if dated else ""))
    return findings, dropped, unknown


def _grounded_text(key: str, content: Mapping, grounding: list, results: Mapping[str, Source],
                   domains: Iterable[str], checks: list[str]) -> str:
    text = str(content.get(key) or "").strip()
    if text and not sources_for(key, grounding, results, domains)[0]:
        checks.append(f"{key}: no valid source, left out")
        return ""
    return text


def _cost(body: Mapping) -> float:
    try:
        return float((body.get("costDollars") or {}).get("total") or 0.0)
    except (TypeError, ValueError, AttributeError):
        return 0.0


def _drop_checks(dropped: int, unknown: int = 0, what: str = "findings") -> list[str]:
    checks = [f"{dropped} {what} without a valid source dropped"] if dropped else []
    if unknown:
        checks.append(f"{unknown} bullets with an unknown topic dropped")
    return checks


def parse_product(body: Mapping, option: ProductOption, lang: str, domains: Iterable[str],
                  now: datetime) -> ProductResearch:
    domains = tuple(domains)
    content, grounding = _output(body)
    results = result_sources(body)
    findings, dropped, unknown = _findings(content, "bulgular", grounding, results, domains,
                                           lambda item: _topic_for(option.kind, item))
    checks = _drop_checks(dropped, unknown)
    company = _grounded_text("sirket", content, grounding, results, domains, checks)
    return ProductResearch(option.option_id, option.label, company, "", tuple(findings),
                           lang, "exa", now, _cost(body), tuple(checks))


def parse_news(body: Mapping, domains: Iterable[str]) -> tuple[list[Finding], int]:
    """News items that have a source of the same call. The date of an item is the newest
    publishedDate of its sources ("" when none has one; the shaping drops those). Second
    value: items dropped without a valid source. Raises ResearchError like parse_product."""
    content, grounding = _output(body)
    items, dropped, _ = _findings(content, "haberler", grounding, result_sources(body),
                                  tuple(domains), lambda _: "haber", dated=True)
    return items, dropped


def parse_question(body: Mapping, question: str, lang: str, domains: Iterable[str],
                   now: datetime) -> QuestionAnswer:
    domains = tuple(domains)
    content, grounding = _output(body)
    results = result_sources(body)
    findings, dropped, _ = _findings(content, "bulgular", grounding, results, domains,
                                     lambda _: "soru")
    return QuestionAnswer(question, "", tuple(findings), lang, "exa", now, _cost(body),
                          tuple(_drop_checks(dropped)))


class ExaProvider:
    name = "exa"

    def __init__(self, config: ExaConfig, system_prompt: Mapping[str, str], api_key: str, *,
                 highlights_prompt: Mapping[str, str] | None = None, news_days: int = 90,
                 transport: httpx.BaseTransport | None = None,
                 now: Callable[[], datetime] = lambda: datetime.now(TR_TZ)) -> None:
        self._config = config
        self._system = system_prompt
        self._highlights = highlights_prompt or {}
        self._news_days = news_days
        self._now = now
        self._key = api_key
        self._http = httpx.Client(base_url=config.base_url, timeout=config.timeout_s,
                                  headers={"x-api-key": api_key}, transport=transport)

    def research_product(self, option: ProductOption, lang: str) -> ProductResearch:
        template = self._config.query.get(option.kind)
        if template is None:
            raise ResearchError("request", f"no query for option kind {option.kind}")
        system = self._system[lang]
        if self._highlights.get(lang):
            system += " " + self._highlights[lang]
        body = self._post({
            "query": template.format(label=option.label, code=option_code(option)),
            "type": self._config.product_type,
            "excludeDomains": list(self._config.exclude_domains),
            "systemPrompt": system,
            "outputSchema": product_schema(option.kind),
            "contents": {"highlights": True},
        })
        p = parse_product(body, option, lang, self._config.exclude_domains, self._now())
        news, checks, cost = self._news(option, lang, p.company or option.label)
        return dataclasses.replace(p, news=tuple(news), cost_usd=p.cost_usd + cost,
                                   checks=p.checks + tuple(checks))

    def _news(self, option: ProductOption, lang: str,
              name: str) -> tuple[list[Finding], list[str], float]:
        """The news call: items, check lines, cost. A failure never loses the highlights:
        it becomes a check line, and the cost of a billed bad reply still counts."""
        start = self._now().date() - timedelta(days=self._news_days)
        body = None
        try:
            body = self._post({
                "query": self._config.news_query.format(name=name, code=option_code(option)),
                "type": self._config.news_type,
                "category": "news",
                "startPublishedDate": f"{start.isoformat()}T00:00:00.000Z",
                "excludeDomains": list(self._config.exclude_domains),
                "systemPrompt": self._system[lang],
                "outputSchema": NEWS_SCHEMA,
                "contents": {"highlights": True},
            })
            items, dropped = parse_news(body, self._config.exclude_domains)
        except ResearchError as e:
            return [], [f"news: {e.kind}"], e.cost_usd
        except (TypeError, ValueError, AttributeError):    # a 200 reply of a wrong shape (billed)
            return [], ["news: request"], _cost(body) if body is not None else 0.0
        return items, _drop_checks(dropped, what="news items"), _cost(body)

    def answer_question(self, question: str, products: Sequence[ProductOption],
                        lang: str) -> QuestionAnswer:
        system = self._system[lang]
        if products:
            names = "; ".join(f"{p.label} ({option_code(p)})" for p in products)
            system += CONTEXT[lang].format(products=names)
        body = self._post({
            "query": question,
            "type": self._config.question_type,
            "excludeDomains": list(self._config.exclude_domains),
            "systemPrompt": system,
            "outputSchema": QUESTION_SCHEMA,
            "contents": {"highlights": True},
        })
        return parse_question(body, question, lang, self._config.exclude_domains, self._now())

    def _post(self, payload: dict) -> dict:
        try:
            r = self._http.post("/search", json=payload)
        except httpx.TransportError as e:            # includes timeouts
            raise ResearchError("connection", type(e).__name__) from e
        if r.status_code != 200:
            text = r.text.replace(self._key, "***") if self._key else r.text   # the key never enters an error
            raise ResearchError(error_kind(r.status_code), f"HTTP {r.status_code}: {text[:200]}")
        try:
            body = r.json()
        except ValueError as e:
            raise ResearchError("server", "the reply is not JSON") from e
        if not isinstance(body, dict):
            raise ResearchError("server", "the reply is not a JSON object")
        return body
