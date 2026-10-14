"""Exa search provider (docs/research.md sections 5 and 8): one POST /search per
product or question, with structured output and field-level grounding. A finding
is kept only with a citation that is a result of the same call (checks.sources_for).
Request shapes follow Exa's build-with-exa skill (query + highlights; other fields
only for a stated need). The key goes only into the x-api-key header."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime

import httpx

from rmprep.contracts import TR_TZ, ProductOption
from rmprep.research.checks import is_web_url, norm_url, sources_for, tr_lower
from rmprep.research.config import ExaConfig
from rmprep.research.types import Finding, ProductResearch, QuestionAnswer, ResearchError, Source

# Findings are objects, so that Exa grounds each one (bulgular[i].metin); an array of
# strings gets one citation list for the whole array (probe 2026-10-14).
PRODUCT_SCHEMA = {
    "type": "object",
    "properties": {
        "sirket": {"type": "string", "description": "the company that manages or issues the product"},
        "ozet": {"type": "string", "description": "what the product is, 2-3 sentences"},
        "bulgular": {"type": "array", "items": {"type": "object", "properties": {
            "konu": {"type": "string", "description": "urun | sirket"},
            "metin": {"type": "string", "description": "one sourced sentence"}},
            "required": ["konu", "metin"]}},
    },
    "required": ["sirket", "ozet", "bulgular"],
}
QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "ozet": {"type": "string", "description": "a short answer, 1-3 sentences"},
        "bulgular": {"type": "array", "items": {"type": "object", "properties": {
            "metin": {"type": "string", "description": "one sourced sentence"}},
            "required": ["metin"]}},
    },
    "required": ["ozet", "bulgular"],
}
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
        raise ResearchError("request", "the reply has no structured output")
    return content, list(out.get("grounding") or ())


def _topic(item: Mapping) -> str:
    konu = tr_lower(str(item.get("konu") or "")).replace("ş", "s")
    return "sirket" if konu.startswith("sirket") else "urun"


def _findings(content: Mapping, grounding: list, results: Mapping[str, Source],
              domains: Iterable[str], topic_of: Callable[[Mapping], str]) -> tuple[list[Finding], int]:
    findings, dropped = [], 0
    for i, item in enumerate(content.get("bulgular") or ()):
        if not isinstance(item, Mapping):
            continue
        text = str(item.get("metin") or "").strip()
        if not text:
            continue
        sources, conf = sources_for(f"bulgular[{i}]", grounding, results, domains)
        if not sources:
            dropped += 1
            continue
        findings.append(Finding(text, topic_of(item), sources, conf))
    return findings, dropped


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


def parse_product(body: Mapping, option: ProductOption, lang: str, domains: Iterable[str],
                  now: datetime) -> ProductResearch:
    domains = tuple(domains)
    content, grounding = _output(body)
    results = result_sources(body)
    findings, dropped = _findings(content, grounding, results, domains, _topic)
    checks = [f"{dropped} findings without a valid source dropped"] if dropped else []
    company = _grounded_text("sirket", content, grounding, results, domains, checks)
    summary = _grounded_text("ozet", content, grounding, results, domains, checks)
    return ProductResearch(option.option_id, option.label, company, summary, tuple(findings),
                           lang, "exa", now, _cost(body), tuple(checks))


def parse_question(body: Mapping, question: str, lang: str, domains: Iterable[str],
                   now: datetime) -> QuestionAnswer:
    domains = tuple(domains)
    content, grounding = _output(body)
    results = result_sources(body)
    findings, dropped = _findings(content, grounding, results, domains, lambda _: "soru")
    checks = [f"{dropped} findings without a valid source dropped"] if dropped else []
    summary = _grounded_text("ozet", content, grounding, results, domains, checks)
    return QuestionAnswer(question, summary, tuple(findings), lang, "exa", now, _cost(body),
                          tuple(checks))


class ExaProvider:
    name = "exa"

    def __init__(self, config: ExaConfig, system_prompt: Mapping[str, str], api_key: str, *,
                 transport: httpx.BaseTransport | None = None,
                 now: Callable[[], datetime] = lambda: datetime.now(TR_TZ)) -> None:
        self._config = config
        self._system = system_prompt
        self._now = now
        self._http = httpx.Client(base_url=config.base_url, timeout=config.timeout_s,
                                  headers={"x-api-key": api_key}, transport=transport)

    def research_product(self, option: ProductOption, lang: str) -> ProductResearch:
        template = self._config.query.get(option.kind)
        if template is None:
            raise ResearchError("request", f"no query for option kind {option.kind}")
        body = self._post({
            "query": template.format(label=option.label, code=option_code(option)),
            "type": self._config.product_type,
            "excludeDomains": list(self._config.exclude_domains),
            "systemPrompt": self._system[lang],
            "outputSchema": PRODUCT_SCHEMA,
            "contents": {"highlights": True},
        })
        return parse_product(body, option, lang, self._config.exclude_domains, self._now())

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
            raise ResearchError(error_kind(r.status_code), f"HTTP {r.status_code}: {r.text[:200]}")
        try:
            body = r.json()
        except ValueError as e:
            raise ResearchError("server", "the reply is not JSON") from e
        if not isinstance(body, dict):
            raise ResearchError("server", "the reply is not a JSON object")
        return body
