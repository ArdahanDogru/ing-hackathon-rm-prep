# Web Research with Exa — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a run is ranked, research its top 3 products and their companies on the web with Exa (Claude web search as the fallback), and let the RM ask more questions in a labeled "Web araştırması" panel.

**Architecture:** A new package `rmprep.research` (types, config, checks, two providers, a service with cache, cost ledger and daily limit) behind a `SearchProvider` protocol. The FastAPI app gets one router and starts the research when it returns a ready run; `RealBackend`, the CLI and the eval never start it. The React dashboard gets one new panel that polls the research endpoint and posts questions.

**Tech Stack:** Python 3.11, `httpx` (Exa REST), `anthropic` (optional extra, Claude fallback), FastAPI, pytest; React 18 + TypeScript, vitest, Tailwind.

**Spec:** `docs/superpowers/specs/2026-10-14-exa-research-design.md` (approved by the user 2026-10-14). Read it before your task.

## Global Constraints

- Python 3.11 syntax (`requires-python = ">=3.11"`); no 3.12-only features.
- No new dependencies: `httpx`, `pyyaml`, `python-dotenv` (core), `anthropic` (extra `[narrator]`, already installed). Do not use `exa-py`.
- No test touches the network. Exa tests use `httpx.MockTransport`; Claude tests use a fake SDK object. The only live test is skipped unless `RMPREP_LIVE_RESEARCH=1`.
- Timestamps are timezone-aware in `rmprep.contracts.TR_TZ` (Europe/Istanbul); the "day" of the cache and the daily limit is the Turkish date.
- Files keep LF line endings (`.gitattributes` is `* -text`; `tests/workflow/test_line_endings.py` fails on CRLF in `.py`). Write files with `newline="\n"` when writing from Python.
- API keys (`EXA_API_KEY`, `ANTHROPIC_API_KEY`) are read from the environment or `<root>/.env`, passed only to the HTTP header / SDK, never logged, never in an error text, never in a cache file.
- Excluded domain: `kap.org.tr` (brief rule 8). Every finding shown to the RM carries the label "web kaynağı, doğrulanmamış" / "web source, not verified".
- Research never changes scores, rules, `DecisionResult`, the narrator or the meeting text. Do not edit `contracts.py`, `backend.py`, `src/rmprep/narrator/`, `decision/`, `ingest/`, `eval/`.
- Daily limit `max_cost_usd_per_day: 2.0` for both providers together; no per-run question limit.
- Python: `C:/Users/yardang/dev/ing-hackathon/prototype/.venv/Scripts/python`. Run tests from the worktree root: `<python> -m pytest -q` (pytest puts `src` first).
- Commit messages end with the line `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. Never push; never touch `main`; never merge into `main`.
- Worktrees: Python tasks in `C:/Users/yardang/dev/ing-wt/research` (branch `research`); the web task in `C:/Users/yardang/dev/ing-wt/research-web` (branch `research-web`, made from `research` in Task 6 step 1).

## Review Focus

1. Exa grounding paths without the `.metin` suffix (`bulgular[1]`) and with two-digit siblings (`bulgular[10].metin` must not count for `bulgular[1]`) → each finding gets exactly its own citations. Test in Task 2.
2. A provider that keeps failing (no credit) must not keep the panel polling forever: `status` never resubmits a failed job; only `start` (a new run view) does. Test in Task 4.
3. Option ids contain `:` (`fund:PPN`), which Windows forbids in file names → cache files use `fund_PPN-TR-20261014.json`. Test in Task 4.
4. Turkish upper case in questions (`MÜŞTERİM`, `İ`/`I`) → refused like lower case. Test in Task 3.
5. An unknown run id or an unknown language on the research endpoints → 404 / 422, never 500. Test in Task 5.

## File Structure

| File | Responsibility |
|---|---|
| `config/research.yaml` | providers, Exa queries, Claude model and prices, limit, client words, system prompts |
| `src/rmprep/research/__init__.py` | package docstring |
| `src/rmprep/research/types.py` | `Source`, `Finding`, `ProductResearch`, `QuestionAnswer`, `ResearchError` |
| `src/rmprep/research/config.py` | `load_config` / `parse_config` → `ResearchConfig` |
| `src/rmprep/research/checks.py` | URL normalisation, excluded domains, `sources_for` (grounding → sources), `check_question` |
| `src/rmprep/research/exa.py` | `ExaProvider`, request shapes, `parse_product` / `parse_question` |
| `src/rmprep/research/claude_search.py` | `ClaudeSearchProvider` (Task 7) |
| `src/rmprep/research/service.py` | `ResearchService` (start, status, ask, cache, ledger, limit, fallback), `research_from_root` |
| `src/rmprep/api/research.py` | `research_router(service, get_run)` |
| `src/rmprep/api/app.py`, `api/serve.py` | connection lines (Task 5) |
| `tests/research/` | tests of the package; `conftest.py` holds `FakeProvider`, `NOW`, `ready_result()` |
| `tests/api/test_research_api.py` | router tests |
| `web/src/components/ResearchPanel.tsx` (+ `.test.tsx`) | the panel |
| `web/src/api/{types,client,mock}.ts`, `web/src/i18n.ts`, `web/src/screens/Dashboard.tsx` | web wiring |
| `docs/research.md` | module design doc (as built) |

---

### Task 1: Types and config

**Files:**
- Create: `src/rmprep/research/__init__.py`, `src/rmprep/research/types.py`, `src/rmprep/research/config.py`, `config/research.yaml`
- Test: `tests/research/__init__.py` (empty), `tests/research/test_types.py`, `tests/research/test_config.py`

**Interfaces:**
- Produces: `rmprep.research.types`: `TOPICS`, `CONFIDENCE`, `ResearchError(kind, message)` with `.kind`, `Source(url, title="", published="")`, `Finding(text, topic, sources, confidence="medium")`, `ProductResearch(option_id, label, company, summary, findings, lang, provider, created_at, cost_usd=0.0, checks=(), error="")`, `QuestionAnswer(question, summary, findings, lang, provider, created_at, cost_usd=0.0, checks=(), error="")`; each with `to_dict()` / `from_dict(d)`.
- Produces: `rmprep.research.config`: `DEFAULT_PATH`, `ConfigError(ValueError)`, `ExaConfig`, `ClaudeSearchConfig`, `ResearchConfig`, `parse_config(raw) -> ResearchConfig`, `load_config(path=DEFAULT_PATH) -> ResearchConfig`.

- [ ] **Step 1: Write the config file**

`config/research.yaml`:

```yaml
# Web research (docs/research.md; spec docs/superpowers/specs/2026-10-14-exa-research-design.md).
# Lead-owned after the merge.
version: 1
providers: [exa, claude]          # the fallback order (spec section 8)
cache_dir: data/research
max_cost_usd_per_day: 2.0         # both providers together (the user, 2026-10-14)
question_max_chars: 300
# A question with a word that starts with one of these is refused (müşteri -> müşterim, müşterinin).
client_words: [müşteri, client, customer]
system_prompt:
  TR: "Türkçe yaz. Yalnızca kaynaklarda açıkça yazan bilgileri kullan; tahmin etme. Getiri vaadi veya yatırım tavsiyesi yazma."
  EN: "Write in English. Use only facts that the sources state; do not guess. Do not promise returns or give investment advice."
exa:
  api_key_env: EXA_API_KEY
  product_type: deep              # the fields need product pages and company pages (Exa skill: deep for that)
  question_type: auto
  exclude_domains: [kap.org.tr]   # KAP blocks automated access (brief rule 8)
  query:
    fund: "{label} ({code}) fonu ve yöneten portföy yönetim şirketi"
    etf: "{label} ({code}) borsa yatırım fonu ve kurucusu"
    stock: "{label} ({code}) hissesi ve şirket"
claude:                           # fallback: the web search server tool (USD, Claude API 2026-10-14)
  model: claude-sonnet-5-5
  max_uses: 3
  max_tokens: 8000
  price_input_per_mtok: 2.0
  price_output_per_mtok: 10.0
  price_per_search: 0.01
```

- [ ] **Step 2: Write the failing tests**

`tests/research/__init__.py`: empty file.

`tests/research/test_types.py`:

```python
from datetime import datetime

import pytest

from rmprep.contracts import TR_TZ
from rmprep.research.types import Finding, ProductResearch, QuestionAnswer, ResearchError, Source

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=TR_TZ)
SRC = Source("https://www.nurolportfoy.com.tr/fon/ppn", "PPN", "2026-10-12")


def test_product_round_trip():
    p = ProductResearch("fund:PPN", "NUROL PORTFÖY PARA PİYASASI (TL) FONU", "Nurol Portföy Yönetimi A.Ş.",
                        "PPN bir para piyasası fonudur.",
                        (Finding("Yönetim ücreti %0,7'dir.", "urun", (SRC,), "high"),),
                        "TR", "exa", NOW, 0.012, ("1 findings without a valid source dropped",))
    assert ProductResearch.from_dict(p.to_dict()) == p
    assert p.to_dict()["created_at"] == "2026-10-14T10:00:00+03:00"


def test_question_round_trip_and_error():
    q = QuestionAnswer("Nurol Portföy son haberler", "", (), "TR", "", NOW, error="exa: credit")
    assert QuestionAnswer.from_dict(q.to_dict()) == q


def test_finding_needs_a_source_a_text_and_known_values():
    with pytest.raises(ValueError):
        Finding("x", "urun", ())
    with pytest.raises(ValueError):
        Finding("  ", "urun", (SRC,))
    with pytest.raises(ValueError):
        Finding("x", "haber", (SRC,))
    with pytest.raises(ValueError):
        Finding("x", "urun", (SRC,), "certain")


def test_created_at_must_be_aware_and_becomes_turkish_time():
    with pytest.raises(ValueError):
        QuestionAnswer("q", "", (), "TR", "exa", datetime(2026, 10, 14, 10, 0))
    utc = datetime.fromisoformat("2026-10-14T07:00:00+00:00")
    assert QuestionAnswer("q", "", (), "TR", "exa", utc).created_at.utcoffset().total_seconds() == 3 * 3600


def test_research_error_kind():
    e = ResearchError("credit", "HTTP 402")
    assert e.kind == "credit" and "402" in str(e)
```

`tests/research/test_config.py`:

```python
import copy

import pytest
import yaml

from rmprep.research.config import DEFAULT_PATH, ConfigError, load_config, parse_config

RAW = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))


def test_the_repo_config_loads():
    c = load_config()
    assert c.providers == ("exa", "claude")
    assert c.exa.exclude_domains == ("kap.org.tr",)
    assert c.exa.query["fund"].format(label="X", code="PPN") == "X (PPN) fonu ve yöneten portföy yönetim şirketi"
    assert c.claude is not None and c.claude.max_uses == 3
    assert c.max_cost_usd_per_day == 2.0
    assert set(c.system_prompt) == {"TR", "EN"}


def _broken(path: str, value):
    raw = copy.deepcopy(RAW)
    node = raw
    *parents, last = path.split(".")
    for p in parents:
        node = node[p]
    if value is None:
        del node[last]
    else:
        node[last] = value
    return raw


@pytest.mark.parametrize("path,value,starts", [
    ("exa.api_key_env", None, "exa.api_key_env"),
    ("providers", ["bing"], "providers"),
    ("providers", [], "providers"),
    ("max_cost_usd_per_day", 0, "max_cost_usd_per_day"),
    ("system_prompt.EN", None, "system_prompt.EN"),
    ("exa.query.etf", None, "exa.query.etf"),
    ("claude.max_uses", "three", "claude.max_uses"),
])
def test_bad_values_name_their_path(path, value, starts):
    with pytest.raises(ConfigError) as e:
        parse_config(_broken(path, value))
    assert str(e.value).startswith(starts)


def test_claude_section_only_needed_when_listed():
    raw = _broken("providers", ["exa"])
    del raw["claude"]
    assert parse_config(raw).claude is None
```

- [ ] **Step 3: Run them to see them fail**

Run: `<python> -m pytest tests/research -q`
Expected: FAIL / errors with `ModuleNotFoundError: No module named 'rmprep.research'`.

- [ ] **Step 4: Write the package**

`src/rmprep/research/__init__.py`:

```python
"""Web research of the recommended products and their companies (docs/research.md):
Exa search, Claude web search as the fallback, deterministic checks, cache and cost
limit. Information for the RM only; it never changes the decision or the meeting text."""
```

`src/rmprep/research/types.py`:

```python
"""Types of the web research (docs/research.md): sources, findings, the research
of one product and the answer to one RM question. Plain dataclasses with
to_dict / from_dict (cache files, API JSON); not part of contracts.py, because
no other module reads them."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from rmprep.contracts import TR_TZ

TOPICS = ("urun", "sirket", "soru")
CONFIDENCE = ("low", "medium", "high")


class ResearchError(Exception):
    """A provider call failed. kind: auth | credit | rate_limit | server | connection | request."""

    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message


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
    topic: str                     # urun | sirket | soru
    sources: tuple[Source, ...]    # at least one
    confidence: str = "medium"     # low | medium | high (as the provider reports it)

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
                "sources": [s.to_dict() for s in self.sources]}

    @classmethod
    def from_dict(cls, d: dict) -> Finding:
        return cls(d["text"], d["topic"], tuple(Source.from_dict(s) for s in d["sources"]),
                   d.get("confidence", "medium"))


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", _aware(self.created_at))

    def to_dict(self) -> dict:
        return {"option_id": self.option_id, "label": self.label, "company": self.company,
                "summary": self.summary, "findings": [f.to_dict() for f in self.findings],
                "lang": self.lang, "provider": self.provider,
                "created_at": self.created_at.isoformat(), "cost_usd": self.cost_usd,
                "checks": list(self.checks), "error": self.error}

    @classmethod
    def from_dict(cls, d: dict) -> ProductResearch:
        return cls(d["option_id"], d["label"], d["company"], d["summary"],
                   tuple(Finding.from_dict(f) for f in d["findings"]), d["lang"], d["provider"],
                   datetime.fromisoformat(d["created_at"]), float(d.get("cost_usd", 0.0)),
                   tuple(d.get("checks", ())), d.get("error", ""))


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", _aware(self.created_at))

    def to_dict(self) -> dict:
        return {"question": self.question, "summary": self.summary,
                "findings": [f.to_dict() for f in self.findings], "lang": self.lang,
                "provider": self.provider, "created_at": self.created_at.isoformat(),
                "cost_usd": self.cost_usd, "checks": list(self.checks), "error": self.error}

    @classmethod
    def from_dict(cls, d: dict) -> QuestionAnswer:
        return cls(d["question"], d["summary"], tuple(Finding.from_dict(f) for f in d["findings"]),
                   d["lang"], d["provider"], datetime.fromisoformat(d["created_at"]),
                   float(d.get("cost_usd", 0.0)), tuple(d.get("checks", ())), d.get("error", ""))
```

`src/rmprep/research/config.py`:

```python
"""Load and check config/research.yaml (docs/research.md)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "research.yaml"
PROVIDERS = ("exa", "claude")
LANGS = ("TR", "EN")
QUERY_KINDS = ("fund", "etf", "stock")


class ConfigError(ValueError):
    """Invalid research config. The message starts with the path of the bad key."""


@dataclass(frozen=True)
class ExaConfig:
    api_key_env: str
    product_type: str
    question_type: str
    exclude_domains: tuple[str, ...]
    query: Mapping[str, str]          # option kind -> template with {label} and {code}
    base_url: str = "https://api.exa.ai"
    timeout_s: float = 60.0


@dataclass(frozen=True)
class ClaudeSearchConfig:
    model: str
    max_uses: int
    max_tokens: int
    price_input_per_mtok: float
    price_output_per_mtok: float
    price_per_search: float
    api_key_env: str = "ANTHROPIC_API_KEY"
    workspace_id_env: str = "ANTHROPIC_WORKSPACE_ID"  # the key is org-level (as the narrator)


@dataclass(frozen=True)
class ResearchConfig:
    providers: tuple[str, ...]         # the fallback order
    exa: ExaConfig
    claude: ClaudeSearchConfig | None  # None: "claude" is not in providers
    max_cost_usd_per_day: float
    question_max_chars: int
    client_words: tuple[str, ...]
    system_prompt: Mapping[str, str]   # per language
    cache_dir: str


def _get(raw: Mapping, path: str):
    node = raw
    for part in path.split("."):
        if not isinstance(node, Mapping) or part not in node:
            raise ConfigError(f"{path}: missing")
        node = node[part]
    return node


def _num(raw: Mapping, path: str, kind=float):
    v = _get(raw, path)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
        raise ConfigError(f"{path}: must be a positive number, got {v!r}")
    return kind(v)


def _str(raw: Mapping, path: str) -> str:
    v = _get(raw, path)
    if not isinstance(v, str) or not v.strip():
        raise ConfigError(f"{path}: must be a non-empty string, got {v!r}")
    return v


def _str_list(raw: Mapping, path: str) -> tuple[str, ...]:
    v = _get(raw, path)
    if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
        raise ConfigError(f"{path}: must be a list of non-empty strings, got {v!r}")
    return tuple(v)


def parse_config(raw: Mapping) -> ResearchConfig:
    if not isinstance(raw, Mapping):
        raise ConfigError("(root): must be a mapping")
    providers = _str_list(raw, "providers")
    if not providers or any(p not in PROVIDERS for p in providers):
        raise ConfigError(f"providers: must be a non-empty list of {PROVIDERS}, got {list(providers)}")
    exa = ExaConfig(
        api_key_env=_str(raw, "exa.api_key_env"),
        product_type=_str(raw, "exa.product_type"),
        question_type=_str(raw, "exa.question_type"),
        exclude_domains=_str_list(raw, "exa.exclude_domains"),
        query={k: _str(raw, f"exa.query.{k}") for k in QUERY_KINDS})
    claude = None
    if "claude" in providers:
        claude = ClaudeSearchConfig(
            model=_str(raw, "claude.model"),
            max_uses=_num(raw, "claude.max_uses", int),
            max_tokens=_num(raw, "claude.max_tokens", int),
            price_input_per_mtok=_num(raw, "claude.price_input_per_mtok"),
            price_output_per_mtok=_num(raw, "claude.price_output_per_mtok"),
            price_per_search=_num(raw, "claude.price_per_search"))
    return ResearchConfig(
        providers=providers, exa=exa, claude=claude,
        max_cost_usd_per_day=_num(raw, "max_cost_usd_per_day"),
        question_max_chars=_num(raw, "question_max_chars", int),
        client_words=_str_list(raw, "client_words"),
        system_prompt={lang: _str(raw, f"system_prompt.{lang}") for lang in LANGS},
        cache_dir=_str(raw, "cache_dir"))


def load_config(path: Path | str = DEFAULT_PATH) -> ResearchConfig:
    return parse_config(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
```

- [ ] **Step 5: Run the tests**

Run: `<python> -m pytest tests/research -q`
Expected: all pass.

- [ ] **Step 6: Run the full suite, then commit**

Run: `<python> -m pytest -q` — expected: green (exit code 0; do not pipe the output through `grep`).

```bash
git add config/research.yaml src/rmprep/research tests/research
git commit -m "research R1a: types and config" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Exa provider and the findings check

**Files:**
- Create: `src/rmprep/research/checks.py` (URL part), `src/rmprep/research/exa.py`
- Test: `tests/research/test_checks_sources.py`, `tests/research/test_exa.py`

**Interfaces:**
- Consumes: Task 1 types and `ExaConfig`, `load_config`.
- Produces: `rmprep.research.checks`: `tr_lower(text) -> str`, `norm_url(url) -> str`, `is_excluded(url, domains) -> bool`, `sources_for(path, grounding, results, domains) -> tuple[tuple[Source, ...], str]`.
- Produces: `rmprep.research.exa`: `PRODUCT_SCHEMA`, `QUESTION_SCHEMA`, `option_code(option) -> str`, `error_kind(status) -> str`, `result_sources(body) -> dict[str, Source]`, `parse_product(body, option, lang, domains, now) -> ProductResearch`, `parse_question(body, question, lang, domains, now) -> QuestionAnswer`, `ExaProvider(config, system_prompt, api_key, *, transport=None, now=...)` with `.name == "exa"`, `.research_product(option, lang)`, `.answer_question(question, products, lang)`.

- [ ] **Step 1: Write the failing tests**

`tests/research/test_checks_sources.py`:

```python
from rmprep.research.checks import is_excluded, norm_url, sources_for, tr_lower
from rmprep.research.types import Source

RESULTS = {norm_url(u): Source(u, t, d) for u, t, d in [
    ("https://www.nurolportfoy.com.tr/fon/ppn", "PPN", "2026-10-12"),
    ("https://fonoloji.com/ppn/", "Fonoloji", ""),
    ("https://www.kap.org.tr/tr/Bildirim/1", "KAP", ""),
]}


def g(field, *urls, conf="high"):
    return {"field": field, "citations": [{"url": u, "title": "x"} for u in urls], "confidence": conf}


def test_norm_url_matches_two_forms_of_one_page():
    assert norm_url("HTTPS://WWW.Fonoloji.com/ppn/") == norm_url("https://www.fonoloji.com/ppn#top")
    assert norm_url("https://a.com/x?y=1") != norm_url("https://a.com/x")


def test_excluded_domain_and_subdomain():
    assert is_excluded("https://www.kap.org.tr/tr/x", ["kap.org.tr"])
    assert is_excluded("https://kap.org.tr/", ["kap.org.tr"])
    assert not is_excluded("https://kapatt.matriksdata.com/x", ["kap.org.tr"])


def test_tr_lower():
    assert tr_lower("MÜŞTERİM IŞIK") == "müşterim ışık"


def test_sources_of_a_field_and_its_subfields():
    grounding = [g("bulgular[0].metin", "https://www.nurolportfoy.com.tr/fon/ppn/"),
                 g("bulgular[0].konu", "https://fonoloji.com/ppn", conf="low")]
    sources, conf = sources_for("bulgular[0]", grounding, RESULTS, ["kap.org.tr"])
    assert [s.url for s in sources] == ["https://www.nurolportfoy.com.tr/fon/ppn", "https://fonoloji.com/ppn/"]
    assert conf == "high"


def test_whole_item_path_and_no_two_digit_sibling():
    grounding = [g("bulgular[1]", "https://fonoloji.com/ppn"),
                 g("bulgular[10].metin", "https://www.nurolportfoy.com.tr/fon/ppn")]
    sources, _ = sources_for("bulgular[1]", grounding, RESULTS, ["kap.org.tr"])
    assert [s.url for s in sources] == ["https://fonoloji.com/ppn/"]


def test_foreign_and_excluded_citations_do_not_count():
    grounding = [g("ozet", "https://example.org/not-a-result", "https://www.kap.org.tr/tr/Bildirim/1")]
    assert sources_for("ozet", grounding, RESULTS, ["kap.org.tr"]) == ((), "high")


def test_no_grounding_gives_medium_and_no_source():
    assert sources_for("ozet", [], RESULTS, []) == ((), "medium")
```

`tests/research/test_exa.py`:

```python
import json
from datetime import datetime

import httpx
import pytest

from rmprep.contracts import TR_TZ, ProductOption
from rmprep.research.config import load_config
from rmprep.research.exa import PRODUCT_SCHEMA, QUESTION_SCHEMA, ExaProvider
from rmprep.research.types import ResearchError

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=TR_TZ)
CONFIG = load_config()
PPN = ProductOption("fund:PPN", "fund", "NUROL PORTFÖY PARA PİYASASI (TL) FONU", entity="PPN",
                    fund_kind="money_market", asset_class="nakit_benzeri")
NUROL = "https://www.nurolportfoy.com.tr/fon/ppn"
FONOLOJI = "https://fonoloji.com/ppn/"


def cite(field, *urls, conf="high"):
    return {"field": field, "citations": [{"url": u, "title": "x"} for u in urls], "confidence": conf}


PRODUCT_BODY = {
    "requestId": "r1",
    "costDollars": {"total": 0.012},
    "results": [
        {"url": NUROL, "title": "Nurol Portföy | PPN", "publishedDate": "2026-10-12T00:00:00.000Z"},
        {"url": FONOLOJI, "title": "PPN", "publishedDate": None},
        {"url": "https://pro-av.panasonic.net/x", "title": "AK-HRP1000GJ"},
    ],
    "output": {
        "content": {
            "sirket": "Nurol Portföy Yönetimi A.Ş.",
            "ozet": "PPN bir para piyasası fonudur.",
            "bulgular": [
                {"konu": "urun", "metin": "Fonun yönetim ücreti %0,7'dir."},
                {"konu": "şirket", "metin": "Şirket Nurol Yatırım Bankası iştirakidir."},
                {"konu": "urun", "metin": "Kaynağı sonuç olmayan bulgu."},
                {"konu": "urun", "metin": "Kaynağı hiç olmayan bulgu."},
            ],
        },
        "grounding": [
            cite("sirket", NUROL + "/"),
            cite("ozet", "https://fonoloji.com/ppn", conf="medium"),
            cite("bulgular[0].metin", NUROL),
            cite("bulgular[0].konu", FONOLOJI, conf="low"),
            cite("bulgular[1]", NUROL, conf="medium"),
            cite("bulgular[2].metin", "https://example.org/not-a-result"),
        ],
    },
}


def provider(handler, key="k-123"):
    return ExaProvider(CONFIG.exa, CONFIG.system_prompt, key,
                       transport=httpx.MockTransport(handler), now=lambda: NOW)


def answering(body, seen=None, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=body)
    return handler


def test_product_request_shape():
    seen = []
    provider(answering(PRODUCT_BODY, seen)).research_product(PPN, "TR")
    req = seen[0]
    assert req.method == "POST" and req.url == "https://api.exa.ai/search"
    assert req.headers["x-api-key"] == "k-123"
    payload = json.loads(req.content)
    assert payload == {
        "query": "NUROL PORTFÖY PARA PİYASASI (TL) FONU (PPN) fonu ve yöneten portföy yönetim şirketi",
        "type": "deep",
        "excludeDomains": ["kap.org.tr"],
        "systemPrompt": CONFIG.system_prompt["TR"],
        "outputSchema": PRODUCT_SCHEMA,
        "contents": {"highlights": True},
    }


def test_product_findings_keep_only_sourced_items():
    r = provider(answering(PRODUCT_BODY)).research_product(PPN, "TR")
    assert r.provider == "exa" and r.cost_usd == 0.012 and r.created_at == NOW
    assert r.company == "Nurol Portföy Yönetimi A.Ş."
    assert r.summary == "PPN bir para piyasası fonudur."
    assert [(f.topic, f.confidence) for f in r.findings] == [("urun", "high"), ("sirket", "medium")]
    assert [s.url for s in r.findings[0].sources] == [NUROL, FONOLOJI]
    assert r.findings[0].sources[0].published == "2026-10-12"
    assert r.findings[0].sources[1].published == ""
    assert r.checks == ("2 findings without a valid source dropped",)


def test_unsourced_summary_and_company_are_left_out():
    body = json.loads(json.dumps(PRODUCT_BODY))
    body["output"]["grounding"] = [g for g in body["output"]["grounding"] if g["field"] not in ("sirket", "ozet")]
    r = provider(answering(body)).research_product(PPN, "TR")
    assert r.company == "" and r.summary == ""
    assert "sirket: no valid source, left out" in r.checks and "ozet: no valid source, left out" in r.checks


def test_kinds_use_their_query_and_deposit_has_none():
    seen = []
    stock = ProductOption("stock:THYAO", "stock", "TÜRK HAVA YOLLARI")
    provider(answering(PRODUCT_BODY, seen)).research_product(stock, "EN")
    payload = json.loads(seen[0].content)
    assert payload["query"] == "TÜRK HAVA YOLLARI (THYAO) hissesi ve şirket"
    assert payload["systemPrompt"] == CONFIG.system_prompt["EN"]
    with pytest.raises(ResearchError) as e:
        provider(answering(PRODUCT_BODY)).research_product(
            ProductOption("deposit:ing_turuncu", "deposit", "Turuncu Hesap"), "TR")
    assert e.value.kind == "request"


def test_question_request_and_answer():
    body = {"costDollars": {"total": 0.007},
            "results": [{"url": NUROL, "title": "Haber", "publishedDate": "2026-10-08"}],
            "output": {"content": {"ozet": "Nurol Portföy OSTİM payını artırdı.",
                                   "bulgular": [{"metin": "Pay oranı %5,58'e çıktı."}]},
                       "grounding": [cite("ozet", NUROL), cite("bulgular[0].metin", NUROL)]}}
    seen = []
    a = provider(answering(body, seen)).answer_question("Nurol Portföy son haberler", [PPN], "TR")
    payload = json.loads(seen[0].content)
    assert payload["query"] == "Nurol Portföy son haberler"
    assert payload["type"] == "auto" and payload["outputSchema"] == QUESTION_SCHEMA
    assert payload["systemPrompt"] == (CONFIG.system_prompt["TR"]
                                       + " İlgili ürünler: NUROL PORTFÖY PARA PİYASASI (TL) FONU (PPN).")
    assert a.summary == "Nurol Portföy OSTİM payını artırdı."
    assert [(f.topic, f.text) for f in a.findings] == [("soru", "Pay oranı %5,58'e çıktı.")]
    assert a.cost_usd == 0.007 and a.question == "Nurol Portföy son haberler"


@pytest.mark.parametrize("status,kind", [(401, "auth"), (403, "auth"), (402, "credit"),
                                         (429, "rate_limit"), (500, "server"), (400, "request")])
def test_http_errors_become_kinds(status, kind):
    with pytest.raises(ResearchError) as e:
        provider(answering({"error": "x"}, status=status)).research_product(PPN, "TR")
    assert e.value.kind == kind
    assert "k-123" not in str(e.value)


def test_connection_error_and_missing_output():
    def down(request):
        raise httpx.ConnectError("boom")
    with pytest.raises(ResearchError) as e:
        provider(down).research_product(PPN, "TR")
    assert e.value.kind == "connection"
    with pytest.raises(ResearchError) as e:
        provider(answering({"results": []})).research_product(PPN, "TR")
    assert e.value.kind == "request"
```

- [ ] **Step 2: Run them to see them fail**

Run: `<python> -m pytest tests/research/test_checks_sources.py tests/research/test_exa.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'rmprep.research.checks'`.

- [ ] **Step 3: Write `checks.py` (URL part)**

```python
"""Deterministic checks of the web research (docs/research.md section 6): which
citations count as sources of a finding, and (Task 3) which RM questions may go
to a search provider."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from urllib.parse import urlparse

from rmprep.research.types import CONFIDENCE, Source

_RANK = {c: i for i, c in enumerate(CONFIDENCE, start=1)}


def tr_lower(text: str) -> str:
    """Turkish lower-casing: İ -> i, I -> ı."""
    return text.replace("İ", "i").replace("I", "ı").lower()


def norm_url(url: str) -> str:
    """Scheme and host lower-cased, no fragment, no trailing slash: two forms of one page match."""
    p = urlparse(url.strip())
    query = f"?{p.query}" if p.query else ""
    return f"{p.scheme.lower()}://{(p.hostname or '').lower()}{p.path.rstrip('/')}{query}"


def is_excluded(url: str, domains: Iterable[str]) -> bool:
    host = (urlparse(url.strip()).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in (x.lower() for x in domains))


def sources_for(path: str, grounding: Sequence[Mapping], results: Mapping[str, Source],
                domains: Iterable[str]) -> tuple[tuple[Source, ...], str]:
    """The sources of one output field: the citations of the grounding entries of
    `path` and its sub-fields (`bulgular[0]` covers `bulgular[0].metin`, not
    `bulgular[10]`) whose URL is a result of the same call (`results`: norm_url ->
    Source) and not on an excluded domain; no repeats, in citation order. Second
    value: the highest confidence of those entries ("medium" when none is given)."""
    domains = tuple(domains)
    found: dict[str, Source] = {}
    best = ""
    for g in grounding:
        field = str(g.get("field", ""))
        if field != path and not field.startswith((path + ".", path + "[")):
            continue
        conf = str(g.get("confidence", ""))
        if _RANK.get(conf, 0) > _RANK.get(best, 0):
            best = conf
        for c in g.get("citations") or ():
            src = results.get(norm_url(str((c or {}).get("url", ""))))
            if src is None or is_excluded(src.url, domains):
                continue
            found.setdefault(norm_url(src.url), src)
    return tuple(found.values()), best or "medium"
```

- [ ] **Step 4: Write `exa.py`**

```python
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
from rmprep.research.checks import norm_url, sources_for, tr_lower
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
        if url:
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
```

- [ ] **Step 5: Run the tests**

Run: `<python> -m pytest tests/research -q` — expected: all pass.

- [ ] **Step 6: Full suite, then commit**

Run: `<python> -m pytest -q` — expected: exit code 0.

```bash
git add src/rmprep/research/checks.py src/rmprep/research/exa.py tests/research
git commit -m "research R1b: Exa provider and the findings check" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: The question check

**Files:**
- Modify: `src/rmprep/research/checks.py` (append)
- Test: `tests/research/test_checks_question.py`

**Interfaces:**
- Consumes: `tr_lower` (Task 2), `rmprep.contracts.Persona`.
- Produces: `REASONS` (`{"TR"|"EN": {"empty", "long", "client"}}`), `check_question(question, persona, lang, client_words, max_chars) -> str | None` (None = allowed; else the reason text in `lang`).

- [ ] **Step 1: Write the failing test**

```python
import json
from pathlib import Path

import pytest

from rmprep.contracts import Persona
from rmprep.research.checks import REASONS, check_question

FIX = Path(__file__).resolve().parents[1] / "contracts" / "fixtures" / "personas"
P01 = Persona.from_dict(json.loads((FIX / "p01.json").read_text(encoding="utf-8")))
WORDS = ("müşteri", "client", "customer")


def check(q, lang="TR"):
    return check_question(q, P01, lang, WORDS, 300)


@pytest.mark.parametrize("q", ["Nurol Portföy son haberler",
                               "Ak Portföy hakkında yeni bir haber var mı?",
                               "PPN fonunun yönetim ücreti ne kadar?"])
def test_product_questions_pass(q):
    assert check(q) is None


def test_empty_and_long():
    assert check("   ") == REASONS["TR"]["empty"]
    assert check("x" * 301) == "Soru 300 karakterden uzun."
    assert check("x" * 300) is None


@pytest.mark.parametrize("q", [
    "Müşterim için PPN uygun mu?",
    "MÜŞTERİM için PPN uygun mu?",                       # Turkish upper case
    "Müşterinin parası nereye gitmeli?",
    "Is PPN right for my client?",
    f"{P01.yas} yaşında biri için PPN uygun mu?",         # the persona's age
    "TL mevduat ağırlıklı portföyler için para piyasası fonu",  # 3 words of `durum`
    "Mevcut portföyün mevduat yoğunluğunu azaltacak fon",  # 3 words of `rm_notu`
])
def test_client_data_is_refused(q):
    assert check(q) == REASONS["TR"]["client"]


def test_reason_in_english():
    assert check("my client", "EN") == "The question contains client information; ask only about products or companies."
```

- [ ] **Step 2: Run it to see it fail**

Run: `<python> -m pytest tests/research/test_checks_question.py -q`
Expected: FAIL with `ImportError: cannot import name 'REASONS'`.

- [ ] **Step 3: Append to `checks.py`**

Add `import re` to the imports and `from rmprep.contracts import Persona`; then append:

```python
REASONS = {
    "TR": {"empty": "Soru boş.",
           "long": "Soru {n} karakterden uzun.",
           "client": "Soru müşteri bilgisi içeriyor; yalnızca ürün veya şirket hakkında sorun."},
    "EN": {"empty": "The question is empty.",
           "long": "The question is longer than {n} characters.",
           "client": "The question contains client information; ask only about products or companies."},
}
_WORD = re.compile(r"\w+")


def _words(text: str) -> list[str]:
    return _WORD.findall(tr_lower(text))


def _grams(words: Sequence[str], n: int = 3) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def check_question(question: str, persona: Persona, lang: str, client_words: Iterable[str],
                   max_chars: int) -> str | None:
    """None if the question may go to a search provider, else the reason (in `lang`)
    for the RM. Refused: empty; longer than max_chars; a word that starts with a
    client word (müşteri -> müşterim, müşterinin); the persona's age as a word; three
    words in a row from a persona text field (Turkish lower-casing throughout)."""
    reasons = REASONS[lang]
    q = question.strip()
    if not q:
        return reasons["empty"]
    if len(q) > max_chars:
        return reasons["long"].format(n=max_chars)
    words = _words(q)
    roots = tuple(tr_lower(w) for w in client_words)
    if str(persona.yas) in words or any(roots and w.startswith(roots) for w in words):
        return reasons["client"]
    asked = _grams(words)
    fields = (persona.profil, persona.durum, persona.yatirim_amaci, persona.rm_notu,
              *persona.oncelikler, *persona.acik_kisitlar)
    if any(asked & _grams(_words(f)) for f in fields):
        return reasons["client"]
    return None
```

- [ ] **Step 4: Run the tests** — `<python> -m pytest tests/research -q`, expected: pass.

- [ ] **Step 5: Full suite, then commit**

```bash
git add src/rmprep/research/checks.py tests/research/test_checks_question.py
git commit -m "research R2a: question check (no client data to the provider)" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: The research service

**Files:**
- Create: `src/rmprep/research/service.py`, `tests/research/conftest.py`
- Test: `tests/research/test_service.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: `rmprep.research.service`: `RESEARCHED_KINDS`, `FALLBACK_KINDS`, `LIMIT_ERROR = "daily limit"`, `SearchProvider` (Protocol), `QuestionRefused(ValueError)`, `researchable(option) -> bool`, `research_products(result) -> list[ProductOption]`, `ResearchService(config, providers, cache_root, *, now=..., off_reason="", max_workers=3)` with `.enabled`, `.start(result, lang="TR")`, `.status(result, lang) -> dict`, `.ask(result, question, lang) -> QuestionAnswer`, `.questions(run_id, lang) -> list[QuestionAnswer]`, `.spent_today() -> float`, `.wait()`; `research_from_root(root, env=None) -> ResearchService`.
- Produces (tests): `tests.research.conftest`: `NOW`, `FakeProvider(name="exa", fail=None, cost=0.01, gate=None)` with `.calls`, `ready_result()`.

- [ ] **Step 1: Write the shared test helpers**

`tests/research/conftest.py`:

```python
"""Shared helpers of the research tests: a fake provider and a ready result (no network)."""

import dataclasses
import json
import threading
from datetime import datetime
from pathlib import Path

from rmprep.contracts import TR_TZ, DecisionResult
from rmprep.research.types import Finding, ProductResearch, QuestionAnswer, ResearchError, Source

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=TR_TZ)
FIX = Path(__file__).resolve().parents[1] / "contracts" / "fixtures"
RECOMMENDED = ("fund:BBF", "fund:AAL", "fund:AKE")


def ready_result(recommended=RECOMMENDED) -> DecisionResult:
    r = DecisionResult.from_dict(json.loads((FIX / "decision_p02_ready.json").read_text(encoding="utf-8")))
    return dataclasses.replace(r, recommended=recommended)


class FakeProvider:
    """fail: a ResearchError kind to raise, or an Exception instance; gate: an Event the call waits for."""

    def __init__(self, name="exa", fail=None, cost=0.01, gate: threading.Event | None = None):
        self.name, self.fail, self.cost, self.gate = name, fail, cost, gate
        self.calls: list[tuple] = []

    def _maybe_fail(self):
        if self.gate is not None:
            self.gate.wait(5)
        if isinstance(self.fail, Exception):
            raise self.fail
        if self.fail:
            raise ResearchError(self.fail, "fake")

    def research_product(self, option, lang):
        self.calls.append(("product", option.option_id, lang))
        self._maybe_fail()
        src = Source(f"https://{self.name}.example/{option.option_id}", "x")
        return ProductResearch(option.option_id, option.label, "Şirket A.Ş.", "Özet.",
                               (Finding("Bulgu.", "urun", (src,), "high"),), lang, self.name, NOW, self.cost)

    def answer_question(self, question, products, lang):
        self.calls.append(("question", question, lang, tuple(p.option_id for p in products)))
        self._maybe_fail()
        src = Source(f"https://{self.name}.example/q", "x")
        return QuestionAnswer(question, "Yanıt.", (Finding("Bulgu.", "soru", (src,)),), lang,
                              self.name, NOW, self.cost)
```

- [ ] **Step 2: Write the failing tests**

`tests/research/test_service.py`:

```python
import dataclasses
import shutil
import threading
from pathlib import Path

import pytest

from rmprep.contracts import ProductOption
from rmprep.research.config import DEFAULT_PATH, load_config
from rmprep.research.service import (LIMIT_ERROR, QuestionRefused, ResearchService,
                                     research_from_root, research_products, researchable)
from tests.research.conftest import NOW, RECOMMENDED, FakeProvider, ready_result

CONFIG = load_config()


def service(tmp_path, *providers, config=CONFIG, workers=1):
    return ResearchService(config, providers, tmp_path, now=lambda: NOW, max_workers=workers)


def test_researchable_kinds():
    assert researchable(ProductOption("fund:PPN", "fund", "PPN", fund_kind="money_market"))
    assert researchable(ProductOption("etf:GLDTR", "etf", "Altın BYF"))
    assert researchable(ProductOption("stock:THYAO", "stock", "THY"))
    assert not researchable(ProductOption("deposit:ing_turuncu", "deposit", "Turuncu"))
    assert not researchable(ProductOption("time_deposit:ing_e_vadeli", "time_deposit", "E-Vadeli"))


def test_products_follow_the_recommended_order():
    r = ready_result(("fund:AKE", "fund:BBF"))
    assert [o.option_id for o in research_products(r)] == ["fund:AKE", "fund:BBF"]


def test_start_researches_each_recommended_product(tmp_path):
    p = FakeProvider()
    s = service(tmp_path, p)
    s.start(ready_result())
    s.wait()
    st = s.status(ready_result(), "TR")
    assert st["state"] == "ready"
    assert [x["option_id"] for x in st["products"]] == list(RECOMMENDED)
    assert st["questions"] == []
    assert [c[1] for c in p.calls] == list(RECOMMENDED)


def test_cache_file_names_and_cache_hit(tmp_path):
    s = service(tmp_path, FakeProvider())
    s.start(ready_result())
    s.wait()
    assert (tmp_path / "products" / "fund_BBF-TR-20261014.json").is_file()   # no ':' in a Windows file name
    again = FakeProvider()
    s2 = service(tmp_path, again)
    s2.start(ready_result())
    s2.wait()
    assert s2.status(ready_result(), "TR")["state"] == "ready"
    assert again.calls == []


def test_running_while_a_job_waits(tmp_path):
    gate = threading.Event()
    s = service(tmp_path, FakeProvider(gate=gate), workers=3)
    s.start(ready_result())
    assert s.status(ready_result(), "TR") == {"state": "running"}
    gate.set()
    s.wait()
    assert s.status(ready_result(), "TR")["state"] == "ready"


def test_off_without_providers(tmp_path):
    s = ResearchService(CONFIG, [], tmp_path, now=lambda: NOW, off_reason="no key in .env: EXA_API_KEY")
    assert not s.enabled
    s.start(ready_result())
    assert s.status(ready_result(), "TR") == {"state": "off", "reason": "no key in .env: EXA_API_KEY"}
    with pytest.raises(QuestionRefused):
        s.ask(ready_result(), "PPN nedir?", "TR")


def test_daily_limit_stops_calls(tmp_path):
    cfg = dataclasses.replace(CONFIG, max_cost_usd_per_day=0.015)
    p = FakeProvider(cost=0.01)
    s = service(tmp_path, p, config=cfg)
    s.start(ready_result())
    s.wait()
    products = s.status(ready_result(), "TR")["products"]
    assert [x["error"] for x in products] == ["", "", LIMIT_ERROR]
    assert len(p.calls) == 2
    assert s.spent_today() == pytest.approx(0.02)


def test_fallback_on_credit_but_not_on_request(tmp_path):
    exa, claude = FakeProvider("exa", fail="credit"), FakeProvider("claude")
    s = service(tmp_path, exa, claude)
    s.start(ready_result(("fund:BBF",)))
    s.wait()
    [x] = s.status(ready_result(("fund:BBF",)), "TR")["products"]
    assert x["provider"] == "claude" and x["error"] == ""
    exa2, claude2 = FakeProvider("exa", fail="request"), FakeProvider("claude")
    s2 = service(tmp_path / "b", exa2, claude2)
    s2.start(ready_result(("fund:BBF",)))
    s2.wait()
    [y] = s2.status(ready_result(("fund:BBF",)), "TR")["products"]
    assert y["error"] == "exa: request" and claude2.calls == []


def test_failed_product_is_not_retried_by_status_only_by_start(tmp_path):
    p = FakeProvider(fail="credit")
    s = service(tmp_path, p)
    r = ready_result(("fund:BBF",))
    s.start(r)
    s.wait()
    assert s.status(r, "TR")["products"][0]["error"] == "exa: credit"
    assert s.status(r, "TR")["state"] == "ready"           # polling ends; no new call
    assert len(p.calls) == 1
    assert not (tmp_path / "products" / "fund_BBF-TR-20261014.json").exists()
    p.fail = None
    s.start(r)                                              # a new run view retries
    s.wait()
    assert s.status(r, "TR")["products"][0]["error"] == ""
    assert len(p.calls) == 2


def test_a_provider_bug_becomes_an_error_not_a_crash(tmp_path):
    s = service(tmp_path, FakeProvider(fail=KeyError("bulgular")))
    r = ready_result(("fund:BBF",))
    s.start(r)
    s.wait()
    assert s.status(r, "TR")["products"][0]["error"].startswith("KeyError")


def test_ask_caches_and_lists_questions(tmp_path):
    p = FakeProvider()
    s = service(tmp_path, p)
    r = ready_result()
    a = s.ask(r, "  Nurol Portföy son haberler ", "TR")
    assert a.question == "Nurol Portföy son haberler" and a.summary == "Yanıt."
    assert p.calls == [("question", "Nurol Portföy son haberler", "TR", RECOMMENDED)]
    assert s.ask(r, "Nurol Portföy son haberler", "TR") == a
    assert len(p.calls) == 1
    assert [q.question for q in s.questions(r.run_id, "TR")] == ["Nurol Portföy son haberler"]
    assert s.questions(r.run_id, "EN") == []


def test_refused_question_costs_nothing(tmp_path):
    p = FakeProvider()
    s = service(tmp_path, p)
    with pytest.raises(QuestionRefused) as e:
        s.ask(ready_result(), "Müşterim için hangisi?", "TR")
    assert "müşteri bilgisi" in str(e.value)
    assert p.calls == []


def test_failed_question_is_returned_not_cached(tmp_path):
    s = service(tmp_path, FakeProvider(fail="server"))
    a = s.ask(ready_result(), "PPN nedir?", "TR")
    assert a.error == "exa: server" and a.findings == ()
    assert s.questions(ready_result().run_id, "TR") == []


def test_research_from_root_reads_keys(tmp_path):
    (tmp_path / "config").mkdir()
    shutil.copy(DEFAULT_PATH, tmp_path / "config" / "research.yaml")
    off = research_from_root(tmp_path, env={})
    assert not off.enabled
    assert off.status(ready_result(), "TR") == {"state": "off", "reason": "no key in .env: EXA_API_KEY"}
    on = research_from_root(tmp_path, env={"EXA_API_KEY": "k"})
    assert on.enabled and [p.name for p in on._providers] == ["exa"]
```

- [ ] **Step 3: Run them to see them fail**

Run: `<python> -m pytest tests/research/test_service.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'rmprep.research.service'`.

- [ ] **Step 4: Write `service.py`**

```python
"""Web research service (docs/research.md sections 4 and 9): researches a run's
recommended products in the background, answers RM questions, and keeps the
cache, the cost ledger and the daily limit. Providers run in the config order;
only auth, credit, server and connection errors fall back to the next one.

Research is per product, not per client: the cache key is (option id, language,
Turkish date). A failed product is not cached; `start` (a new run view) tries it
again, `status` (polling) never does, so a lasting error ends the polling."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import date, datetime
from pathlib import Path
from typing import Protocol, TypeVar

from rmprep.contracts import TR_TZ, DecisionResult, DecisionState, ProductOption
from rmprep.research.checks import check_question
from rmprep.research.config import ResearchConfig, load_config
from rmprep.research.types import ProductResearch, QuestionAnswer, ResearchError

RESEARCHED_KINDS = ("fund", "etf", "stock")      # deposit, time_deposit: ING's own products
FALLBACK_KINDS = ("auth", "credit", "server", "connection")
LIMIT_ERROR = "daily limit"

T = TypeVar("T", ProductResearch, QuestionAnswer)


class SearchProvider(Protocol):
    name: str

    def research_product(self, option: ProductOption, lang: str) -> ProductResearch: ...

    def answer_question(self, question: str, products: Sequence[ProductOption],
                        lang: str) -> QuestionAnswer: ...


class QuestionRefused(ValueError):
    """The question may not go to a provider; the message is the reason for the RM."""


def researchable(option: ProductOption) -> bool:
    return option.kind in RESEARCHED_KINDS


def research_products(result: DecisionResult) -> list[ProductOption]:
    """The recommended options that are researched, in the recommended order."""
    by_id = {s.option.option_id: s.option for s in result.options}
    return [by_id[i] for i in result.recommended if i in by_id and researchable(by_id[i])]


class ResearchService:
    def __init__(self, config: ResearchConfig, providers: Sequence[SearchProvider],
                 cache_root: Path | str, *,
                 now: Callable[[], datetime] = lambda: datetime.now(TR_TZ),
                 off_reason: str = "", max_workers: int = 3) -> None:
        self._config = config
        self._providers = tuple(providers)
        self._root = Path(cache_root)
        self._now = now
        self._off_reason = off_reason or "no provider key"
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="research")
        self._jobs: dict[tuple[str, str, date], Future] = {}
        self._lock = threading.Lock()
        self._ledger_lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self._providers)

    # --- products -------------------------------------------------------------

    def start(self, result: DecisionResult, lang: str = "TR") -> None:
        """Starts the research of the run's products (idempotent; retries failed ones)."""
        self._jobs_for(result, lang, self._now().date(), retry=True)

    def status(self, result: DecisionResult, lang: str) -> dict:
        """{"state": "off", "reason"} | {"state": "running"} |
        {"state": "ready", "products": [...], "questions": [...]} (JSON-ready)."""
        if not self._providers:
            return {"state": "off", "reason": self._off_reason}
        jobs = self._jobs_for(result, lang, self._now().date(), retry=False)
        if any(not j.done() for j in jobs):
            return {"state": "running"}
        return {"state": "ready", "products": [j.result().to_dict() for j in jobs],
                "questions": [q.to_dict() for q in self.questions(result.run_id, lang)]}

    def wait(self) -> None:
        """Waits for every started job (tests)."""
        with self._lock:
            jobs = list(self._jobs.values())
        wait(jobs)

    def _jobs_for(self, result: DecisionResult, lang: str, day: date, *, retry: bool) -> list[Future]:
        if not self._providers or result.state != DecisionState.READY:
            return []
        jobs = []
        with self._lock:
            for opt in research_products(result):
                key = (opt.option_id, lang, day)
                job = self._jobs.get(key)
                failed = job is not None and job.done() and job.result().error
                if job is None or (retry and failed):
                    job = self._jobs[key] = self._pool.submit(self._product, opt, lang, day)
                jobs.append(job)
        return jobs

    def _product(self, opt: ProductOption, lang: str, day: date) -> ProductResearch:
        path = self._root / "products" / f"{opt.option_id.replace(':', '_')}-{lang}-{day:%Y%m%d}.json"
        try:
            cached = _read(path, ProductResearch)
            if cached is not None:
                return cached
            out = self._call(lambda p: p.research_product(opt, lang), "product", opt.option_id)
        except Exception as e:          # a provider bug must not break the panel
            out = f"{type(e).__name__}: {e}"
        if isinstance(out, str):
            return ProductResearch(opt.option_id, opt.label, "", "", (), lang, "", self._now(),
                                   error=out)
        _write(path, out)
        return out

    # --- questions ------------------------------------------------------------

    def ask(self, result: DecisionResult, question: str, lang: str) -> QuestionAnswer:
        """The answer (cached per run, language and question), or one with `error`.
        Raises QuestionRefused when research is off or the question check refuses it."""
        if not self._providers:
            raise QuestionRefused(self._off_reason)
        reason = check_question(question, result.persona, lang, self._config.client_words,
                                self._config.question_max_chars)
        if reason:
            raise QuestionRefused(reason)
        q = question.strip()
        digest = hashlib.sha1(q.encode("utf-8")).hexdigest()[:12]
        path = self._root / "questions" / f"{result.run_id}-{lang}-{digest}.json"
        cached = _read(path, QuestionAnswer)
        if cached is not None:
            return cached
        products = research_products(result)
        try:
            out = self._call(lambda p: p.answer_question(q, products, lang), "question", path.stem)
        except Exception as e:
            out = f"{type(e).__name__}: {e}"
        if isinstance(out, str):
            return QuestionAnswer(q, "", (), lang, "", self._now(), error=out)
        _write(path, out)
        return out

    def questions(self, run_id: str, lang: str) -> list[QuestionAnswer]:
        found = (_read(p, QuestionAnswer) for p in (self._root / "questions").glob(f"{run_id}-{lang}-*.json"))
        return sorted((q for q in found if q is not None), key=lambda q: q.created_at)

    # --- providers, cost ------------------------------------------------------

    def _call(self, fn: Callable[[SearchProvider], T], kind: str, ref: str) -> T | str:
        """The first provider's result, or an error text: "daily limit" or
        "exa: credit; claude: auth" (the kinds of the failed providers)."""
        errors: list[str] = []
        for p in self._providers:
            if self.spent_today() >= self._config.max_cost_usd_per_day:
                return LIMIT_ERROR
            try:
                out = fn(p)
            except ResearchError as e:
                errors.append(f"{p.name}: {e.kind}")
                if e.kind in FALLBACK_KINDS:
                    continue
                break
            self._record(p.name, kind, ref, out.cost_usd)
            return out
        return "; ".join(errors) or "no provider"

    def spent_today(self) -> float:
        today = self._now().date().isoformat()
        try:
            lines = (self._root / "costs.jsonl").read_text(encoding="utf-8").splitlines()
        except OSError:
            return 0.0
        total = 0.0
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if str(row.get("at", ""))[:10] == today:
                total += float(row.get("cost_usd") or 0.0)
        return total

    def _record(self, provider: str, kind: str, ref: str, cost: float) -> None:
        row = {"at": self._now().isoformat(), "provider": provider, "kind": kind, "ref": ref,
               "cost_usd": round(cost, 6)}
        with self._ledger_lock:
            self._root.mkdir(parents=True, exist_ok=True)
            with (self._root / "costs.jsonl").open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read(path: Path, cls):
    try:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj.to_dict(), ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8", newline="\n")


def research_from_root(root: Path | str, env: Mapping[str, str] | None = None) -> ResearchService:
    """The service of a prototype root: config/research.yaml, keys from the
    environment or root/.env (environment wins), cache under root. A provider
    without its key is left out; none left -> research is off."""
    root = Path(root)
    config = load_config(root / "config" / "research.yaml")
    if env is None:
        from dotenv import dotenv_values
        env = {k: v for k, v in dotenv_values(root / ".env").items() if v is not None}
        env.update(os.environ)
    providers: list[SearchProvider] = []
    for name in config.providers:
        if name == "exa":
            key = env.get(config.exa.api_key_env, "").strip()
            if key:
                from rmprep.research.exa import ExaProvider
                providers.append(ExaProvider(config.exa, config.system_prompt, key))
    off = "" if providers else f"no key in .env: {config.exa.api_key_env}"
    return ResearchService(config, providers, root / config.cache_dir, off_reason=off)
```

- [ ] **Step 5: Run the tests** — `<python> -m pytest tests/research -q`, expected: pass.

- [ ] **Step 6: Full suite, then commit**

```bash
git add src/rmprep/research/service.py tests/research
git commit -m "research R2b: service (background research, cache, ledger, daily limit, fallback)" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: API router and connection lines

**Files:**
- Create: `src/rmprep/api/research.py`, `tests/api/test_research_api.py`
- Modify: `src/rmprep/api/app.py` (signature of `create_app`, `_view`, router before the static block, import of `DecisionState`), `src/rmprep/api/serve.py` (`build_app`), `.env.example`

**Interfaces:**
- Consumes: `ResearchService`, `QuestionRefused` (Task 4); `FakeProvider`, `NOW` (tests.research.conftest).
- Produces: `rmprep.api.research.research_router(service, get_run) -> APIRouter`; `create_app(..., research=None)`. HTTP: `GET /api/runs/{run_id}/research?lang=TR` → 202 `{"state": "running"}` | 200 `{"state": "ready", "products", "questions"}` | 200 `{"state": "off", "reason"}`; `POST /api/runs/{run_id}/research/questions` `{question, lang}` → 200 QuestionAnswer | 422 `{"detail": reason}`.

- [ ] **Step 1: Write the failing tests**

`tests/api/test_research_api.py`:

```python
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rmprep.api.app import create_app
from rmprep.research.config import load_config
from rmprep.research.service import ResearchService
from rmprep.ui.fake import FakeBackend
from tests.research.conftest import NOW, RECOMMENDED, FakeProvider, ready_result

FIX = Path(__file__).resolve().parents[1] / "contracts" / "fixtures"


def make(tmp_path, *providers, workers=1):
    service = ResearchService(load_config(), providers, tmp_path, now=lambda: NOW,
                              max_workers=workers, off_reason="no key in .env: EXA_API_KEY")
    client = TestClient(create_app(FakeBackend(FIX, results=[ready_result()]), research=service))
    return client, service


def new_run(client) -> str:
    persona = next(p for p in client.get("/api/personas").json() if p["persona_id"] == "P02")
    return client.post("/api/runs", json={"persona": persona}).json()["result"]["run_id"]


def test_a_new_run_starts_the_research(tmp_path):
    p = FakeProvider()
    client, service = make(tmp_path, p)
    run_id = new_run(client)
    service.wait()
    assert [c[1] for c in p.calls] == list(RECOMMENDED)
    body = client.get(f"/api/runs/{run_id}/research?lang=TR").json()
    assert body["state"] == "ready"
    assert [x["option_id"] for x in body["products"]] == list(RECOMMENDED)


def test_running_is_202(tmp_path):
    gate = threading.Event()
    client, service = make(tmp_path, FakeProvider(gate=gate), workers=3)
    run_id = new_run(client)
    r = client.get(f"/api/runs/{run_id}/research")
    assert r.status_code == 202 and r.json() == {"state": "running"}
    gate.set()
    service.wait()


def test_off_without_a_provider(tmp_path):
    client, _ = make(tmp_path)
    run_id = new_run(client)
    assert client.get(f"/api/runs/{run_id}/research").json() == {
        "state": "off", "reason": "no key in .env: EXA_API_KEY"}


def test_unknown_run_and_bad_lang(tmp_path):
    client, _ = make(tmp_path, FakeProvider())
    assert client.get("/api/runs/Rnope/research").status_code == 404
    run_id = new_run(client)
    assert client.get(f"/api/runs/{run_id}/research?lang=DE").status_code == 422
    assert client.post(f"/api/runs/{run_id}/research/questions",
                       json={"question": "PPN nedir?", "lang": "DE"}).status_code == 422


def test_question_answer_and_refusal(tmp_path):
    client, _ = make(tmp_path, FakeProvider())
    run_id = new_run(client)
    r = client.post(f"/api/runs/{run_id}/research/questions",
                    json={"question": "Nurol Portföy son haberler", "lang": "TR"})
    assert r.status_code == 200 and r.json()["summary"] == "Yanıt."
    bad = client.post(f"/api/runs/{run_id}/research/questions",
                      json={"question": "Müşterim için hangisi?", "lang": "TR"})
    assert bad.status_code == 422 and "müşteri bilgisi" in bad.json()["detail"]


def test_without_research_the_route_is_absent(tmp_path):
    client = TestClient(create_app(FakeBackend(FIX)))
    run_id = new_run(client)
    assert client.get(f"/api/runs/{run_id}/research").status_code == 404
```

- [ ] **Step 2: Run them to see them fail**

Run: `<python> -m pytest tests/api/test_research_api.py -q`
Expected: FAIL with `TypeError: create_app() got an unexpected keyword argument 'research'`.

- [ ] **Step 3: Write the router**

`src/rmprep/api/research.py`:

```python
"""Web research endpoints (docs/research.md section 10). The research is
information for the RM; nothing here changes a run."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from rmprep.contracts import NARRATIVE_LANGS, DecisionResult
from rmprep.research.service import QuestionRefused, ResearchService


class QuestionRequest(BaseModel):
    question: str
    lang: str = "TR"


def research_router(service: ResearchService, get_run: Callable[[str], DecisionResult]) -> APIRouter:
    """get_run: the app's run registry (404 for an unknown run)."""
    router = APIRouter()

    def _lang(lang: str) -> str:
        if lang not in NARRATIVE_LANGS:
            raise HTTPException(422, f"lang must be one of {NARRATIVE_LANGS}, got {lang!r}")
        return lang

    @router.get("/api/runs/{run_id}/research")
    def research(run_id: str, lang: str = "TR"):
        status = service.status(get_run(run_id), _lang(lang))
        if status["state"] == "running":
            return JSONResponse(status_code=202, content=status)
        return status

    @router.post("/api/runs/{run_id}/research/questions")
    def ask(run_id: str, req: QuestionRequest):
        result = get_run(run_id)
        try:
            return service.ask(result, req.question, _lang(req.lang)).to_dict()
        except QuestionRefused as e:
            raise HTTPException(422, str(e)) from e

    return router
```

- [ ] **Step 4: Connect it in `app.py`**

1. Add `DecisionState,` to the `from rmprep.contracts import (...)` list (alphabetical, after `DecisionResult,`).
2. Change the signature of `create_app`: after `ingest: IngestControl | None = None` add a parameter, so the end reads:

```python
               ingest: IngestControl | None = None,
               research=None) -> FastAPI:
```

and add to the docstring: `research: a rmprep.research.service.ResearchService (docs/research.md); None = no research routes.`
3. In `_view`, right after `runs[result.run_id] = result`, add:

```python
        if research is not None and result.state == DecisionState.READY:
            research.start(result, "TR")      # web research of the top 3 (docs/research.md)
```

4. Right before the line `if static_dir is not None:`, add:

```python
    if research is not None:      # before the web app's catch-all route
        from rmprep.api.research import research_router
        app.include_router(research_router(research, _run))

```

- [ ] **Step 5: Connect it in `serve.py`**

In `build_app`, add the import `from rmprep.research.service import research_from_root` next to the other imports in the function; before the `return`, add

```python
    # web research (docs/research.md); a root without its config has no research routes
    research = research_from_root(root) if (Path(root) / "config" / "research.yaml").is_file() else None
```

and change the `return create_app(...)` call so it ends with `ingest=IngestControl(Paths(Path(root).resolve())), research=research)`.

- [ ] **Step 6: `.env.example`**

Append:

```
# Web research (docs/research.md); without it the research panel is off.
EXA_API_KEY=
```

- [ ] **Step 7: Run the tests** — `<python> -m pytest tests/api tests/research tests/cli -q`, expected: pass.

- [ ] **Step 8: Full suite, then commit**

```bash
git add src/rmprep/api/research.py src/rmprep/api/app.py src/rmprep/api/serve.py .env.example tests/api/test_research_api.py
git commit -m "research R3: API router; the API starts the research of a ready run" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Web research panel (parallel track, own worktree)

**Files:**
- Create: `web/src/components/ResearchPanel.tsx`, `web/src/components/ResearchPanel.test.tsx`
- Modify: `web/src/api/types.ts` (append), `web/src/api/client.ts` (`research`, `askResearch`), `web/src/api/client.test.ts` (append), `web/src/api/mock.ts` (two routes), `web/src/api/mock.test.ts` (append), `web/src/i18n.ts` (16 keys in TR and EN), `web/src/screens/Dashboard.tsx` (import + one mount line)

**Interfaces:**
- Consumes: the HTTP contract of Task 5 (above). No Python code.
- Produces: `api.research(runId, lang): Promise<ResearchView>`, `api.askResearch(runId, question, lang): Promise<QuestionAnswer>`, `ResearchPanel({ view })`, `useResearch(runId, lang, enabled)`.

- [ ] **Step 1: Make the worktree and install**

```bash
cd C:/Users/yardang/dev/ing-hackathon/prototype
git worktree add -b research-web C:/Users/yardang/dev/ing-wt/research-web research
cd C:/Users/yardang/dev/ing-wt/research-web/web
npm ci
npm test
```

Expected: `npm test` passes before any change (baseline).

- [ ] **Step 2: Types**

Append to `web/src/api/types.ts`:

```ts
// Web research (docs/research.md section 10): information for the RM, never part of the decision.
export interface ResearchSource {
  url: string;
  title: string;
  published: string; // YYYY-MM-DD or ""
}

export interface ResearchFinding {
  text: string;
  topic: "urun" | "sirket" | "soru";
  confidence: "low" | "medium" | "high";
  sources: ResearchSource[];
}

export interface ProductResearch {
  option_id: string;
  label: string;
  company: string;
  summary: string;
  findings: ResearchFinding[];
  lang: Lang;
  provider: string;
  created_at: string;
  cost_usd: number;
  checks: string[];
  error: string; // "daily limit" | "exa: credit; claude: auth" | ""
}

export interface QuestionAnswer {
  question: string;
  summary: string;
  findings: ResearchFinding[];
  lang: Lang;
  provider: string;
  created_at: string;
  cost_usd: number;
  checks: string[];
  error: string;
}

export type ResearchView =
  | { state: "running" }
  | { state: "off"; reason: string }
  | { state: "ready"; products: ProductResearch[]; questions: QuestionAnswer[] };
```

- [ ] **Step 3: Write the failing client and mock tests**

Append to `web/src/api/client.test.ts`:

```ts
test("research: 202 is running, 404 is off, 200 is the view", async () => {
  globalThis.fetch = vi.fn().mockResolvedValueOnce(json({ state: "running" }, 202))
    .mockResolvedValueOnce(json({ detail: "Not Found" }, 404))
    .mockResolvedValueOnce(json({ state: "ready", products: [], questions: [] }, 200));
  expect(await api.research("R1", "TR")).toEqual({ state: "running" });
  expect(await api.research("R1", "TR")).toEqual({ state: "off", reason: "" });
  expect(await api.research("R1", "TR")).toEqual({ state: "ready", products: [], questions: [] });
});

test("askResearch posts the question; a refusal is an ApiError", async () => {
  const fetch = vi.fn().mockResolvedValue(json({ detail: "Soru müşteri bilgisi içeriyor" }, 422));
  globalThis.fetch = fetch;
  await expect(api.askResearch("R1", "müşterim?", "TR")).rejects.toEqual(new ApiError(422, "Soru müşteri bilgisi içeriyor"));
  expect(fetch).toHaveBeenCalledWith("/api/runs/R1/research/questions", expect.objectContaining({ method: "POST", body: JSON.stringify({ question: "müşterim?", lang: "TR" }) }));
});
```

Append to `web/src/api/mock.test.ts` (it imports `resolveMock`; use the loader the file already uses, or `() => undefined`):

```ts
test("research mock: ready view and a refused question", () => {
  const load = () => undefined;
  const view = resolveMock("GET", "/api/runs/R1/research?lang=TR", undefined, load);
  expect(view.status).toBe(200);
  expect((view.body as { state: string }).state).toBe("ready");
  expect(resolveMock("POST", "/api/runs/R1/research/questions", { question: "Müşterim için?", lang: "TR" }, load).status).toBe(422);
  const ok = resolveMock("POST", "/api/runs/R1/research/questions", { question: "PPN nedir?", lang: "TR" }, load);
  expect((ok.body as { question: string }).question).toBe("PPN nedir?");
});
```

Run: `npm test -- src/api` — expected: FAIL (`api.research is not a function`).

- [ ] **Step 4: Client and mock**

In `web/src/api/client.ts`: add `QuestionAnswer` and `ResearchView` to the type import list; add after the `brief` function:

```ts
/** GET /runs/{id}/research: "running" (202), off, or the findings; 404 (a server without research) = off. */
async function research(runId: string, lang: Lang): Promise<ResearchView> {
  const res = await fetch(`${BASE}/runs/${enc(runId)}/research?lang=${lang}`);
  if (res.status === 202) return { state: "running" };
  if (res.status === 404) return { state: "off", reason: "" };
  if (!res.ok) throw await apiError(res);
  return (await res.json()) as ResearchView;
}
```

and in `export const api = { ... }` after `brief,`:

```ts
  research,
  /** POST a question to the web research; 422 = refused (the reason is the detail). */
  askResearch: (runId: string, question: string, lang: Lang) =>
    request<QuestionAnswer>("POST", `/runs/${enc(runId)}/research/questions`, { question, lang }),
```

In `web/src/api/mock.ts`, add above `export function resolveMock`:

```ts
// Web research (docs/research.md): a small fixed sample for dev:mock.
const MOCK_FINDING = {
  text: "Fonun yönetim ücreti yıllık %0,7'dir.",
  topic: "urun",
  confidence: "high",
  sources: [{ url: "https://www.nurolportfoy.com.tr/", title: "Nurol Portföy", published: "2026-10-12" }],
};
const MOCK_RESEARCH = {
  state: "ready",
  products: [
    {
      option_id: "fund:PPN", label: "NUROL PORTFÖY PARA PİYASASI (TL) FONU", company: "Nurol Portföy Yönetimi A.Ş.",
      summary: "PPN, kısa vadeli para piyasası araçlarına yatırım yapan bir fondur.",
      findings: [MOCK_FINDING, { ...MOCK_FINDING, text: "Şirket Nurol Yatırım Bankası iştirakidir.", topic: "sirket", confidence: "medium" }],
      lang: "TR", provider: "exa", created_at: "2026-10-14T10:00:00+03:00", cost_usd: 0.012, checks: [], error: "",
    },
  ],
  questions: [],
};
```

and inside `if (a === "runs") {`, before the `narrative` routes:

```ts
    if (method === "GET" && c === "research" && !d) return { status: 200, body: MOCK_RESEARCH };
    if (method === "POST" && c === "research" && d === "questions") {
      const question = String(req.question ?? "");
      if (/müşteri|client/i.test(question)) {
        return { status: 422, body: { detail: "Soru müşteri bilgisi içeriyor; yalnızca ürün veya şirket hakkında sorun." } };
      }
      return {
        status: 200,
        body: { question, summary: "Örnek yanıt (mock).", findings: [{ ...MOCK_FINDING, topic: "soru" }], lang: "TR", provider: "exa", created_at: "2026-10-14T10:00:00+03:00", cost_usd: 0.007, checks: [], error: "" },
      };
    }
```

Run: `npm test -- src/api` — expected: pass.

- [ ] **Step 5: Labels**

In `web/src/i18n.ts`, add to the `TR` object (before its closing `};`):

```ts
  researchTitle: "Web araştırması",
  researchLabel: "Web kaynağı, doğrulanmamış",
  researchNote: "Bilgi amaçlıdır; puanları, önerileri ve görüşme metnini değiştirmez.",
  researchRunning: "Önerilen ürünler ve şirketleri web'de araştırılıyor…",
  researchOff: "Web araştırması kapalı: {reason}",
  researchFailed: "Araştırma yapılamadı: {error}",
  researchLimit: "Günlük araştırma limiti doldu.",
  researchProduct: "Ürün",
  researchCompany: "Şirket",
  researchAsk: "Ürünler veya şirketler hakkında soru sorun",
  researchAskButton: "Sor",
  researchAsking: "Aranıyor…",
  researchNoFindings: "Kaynaklı bulgu bulunamadı.",
  researchConfHigh: "güven: yüksek",
  researchConfMedium: "güven: orta",
  researchConfLow: "güven: düşük",
```

and to the `EN` object:

```ts
  researchTitle: "Web research",
  researchLabel: "Web source, not verified",
  researchNote: "For information only; it does not change the scores, the recommendations or the meeting text.",
  researchRunning: "Researching the recommended products and their companies on the web…",
  researchOff: "Web research is off: {reason}",
  researchFailed: "The research failed: {error}",
  researchLimit: "The daily research limit is reached.",
  researchProduct: "Product",
  researchCompany: "Company",
  researchAsk: "Ask about the products or companies",
  researchAskButton: "Ask",
  researchAsking: "Searching…",
  researchNoFindings: "No sourced findings.",
  researchConfHigh: "confidence: high",
  researchConfMedium: "confidence: medium",
  researchConfLow: "confidence: low",
```

- [ ] **Step 6: Write the failing panel tests**

`web/src/components/ResearchPanel.test.tsx`:

```tsx
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api, ApiError } from "../api/client";
import type { ProductResearch, QuestionAnswer, ResearchView } from "../api/types";
import { renderWith } from "../test/render";
import { sample } from "../test/samples";
import { ResearchPanel } from "./ResearchPanel";

const NUROL = "https://www.nurolportfoy.com.tr/fon/ppn";
const product = (over: Partial<ProductResearch> = {}): ProductResearch => ({
  option_id: "fund:PPN",
  label: "NUROL PORTFÖY PARA PİYASASI (TL) FONU",
  company: "Nurol Portföy Yönetimi A.Ş.",
  summary: "PPN bir para piyasası fonudur.",
  findings: [
    { text: "Fonun yönetim ücreti %0,7'dir.", topic: "urun", confidence: "high", sources: [{ url: NUROL, title: "PPN", published: "2026-10-12" }] },
    { text: "Şirket Nurol Yatırım Bankası iştirakidir.", topic: "sirket", confidence: "medium", sources: [{ url: "https://fonoloji.com/ppn", title: "PPN", published: "" }] },
  ],
  lang: "TR",
  provider: "exa",
  created_at: "2026-10-14T10:00:00+03:00",
  cost_usd: 0.012,
  checks: [],
  error: "",
  ...over,
});
const answer = (question: string): QuestionAnswer => ({
  question,
  summary: "Nurol Portföy OSTİM payını artırdı.",
  findings: [{ text: "Pay oranı %5,58'e çıktı.", topic: "soru", confidence: "high", sources: [{ url: NUROL, title: "Haber", published: "2026-10-08" }] }],
  lang: "TR",
  provider: "exa",
  created_at: "2026-10-14T10:05:00+03:00",
  cost_usd: 0.007,
  checks: [],
  error: "",
});
const ready = (products = [product()], questions: QuestionAnswer[] = []): ResearchView => ({ state: "ready", products, questions });
const panel = (lang: "TR" | "EN" = "TR") => renderWith(<ResearchPanel view={sample("run_p01_ready")} />, { lang });

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

test("shows a running line, then the findings with their sources and the label", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.spyOn(api, "research").mockResolvedValueOnce({ state: "running" }).mockResolvedValue(ready());
  panel();
  expect(await screen.findByTestId("research-running")).toBeInTheDocument();
  vi.advanceTimersByTime(3100);
  expect(await screen.findByText("Fonun yönetim ücreti %0,7'dir.")).toBeInTheDocument();
  expect(screen.getByText("Web kaynağı, doğrulanmamış")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "nurolportfoy.com.tr" })).toHaveAttribute("href", NUROL);
  expect(screen.getByText("Şirket: Nurol Portföy Yönetimi A.Ş.")).toBeInTheDocument();
  expect(screen.getByText("Şirket Nurol Yatırım Bankası iştirakidir.")).toBeInTheDocument();
});

test("hidden on a server without research", async () => {
  vi.spyOn(api, "research").mockResolvedValue({ state: "off", reason: "" });
  panel();
  await waitFor(() => expect(api.research).toHaveBeenCalled());
  expect(screen.queryByTestId("research-panel")).toBeNull();
});

test("off with a reason says so", async () => {
  vi.spyOn(api, "research").mockResolvedValue({ state: "off", reason: "no key in .env: EXA_API_KEY" });
  panel();
  expect(await screen.findByText("Web araştırması kapalı: no key in .env: EXA_API_KEY")).toBeInTheDocument();
});

test("the daily limit and other errors of a product", async () => {
  vi.spyOn(api, "research").mockResolvedValue(
    ready([product({ error: "daily limit", findings: [] }), product({ option_id: "fund:IST", label: "İSTANBUL PORTFÖY", error: "exa: credit", findings: [] })]),
  );
  panel();
  expect(await screen.findByText("Günlük araştırma limiti doldu.")).toBeInTheDocument();
  expect(screen.getByText("Araştırma yapılamadı: exa: credit")).toBeInTheDocument();
});

test("asks a question and shows the answer", async () => {
  vi.spyOn(api, "research").mockResolvedValue(ready());
  const ask = vi.spyOn(api, "askResearch").mockResolvedValue(answer("Nurol Portföy son haberler"));
  panel();
  const box = await screen.findByLabelText("Ürünler veya şirketler hakkında soru sorun");
  await userEvent.type(box, "Nurol Portföy son haberler");
  await userEvent.click(screen.getByRole("button", { name: "Sor" }));
  expect(ask).toHaveBeenCalledWith(sample("run_p01_ready").result.run_id, "Nurol Portföy son haberler", "TR");
  expect(await screen.findByText("Nurol Portföy OSTİM payını artırdı.")).toBeInTheDocument();
  expect(box).toHaveValue("");
});

test("a refused question shows its reason", async () => {
  vi.spyOn(api, "research").mockResolvedValue(ready());
  vi.spyOn(api, "askResearch").mockRejectedValue(new ApiError(422, "Soru müşteri bilgisi içeriyor; yalnızca ürün veya şirket hakkında sorun."));
  panel();
  await userEvent.type(await screen.findByLabelText("Ürünler veya şirketler hakkında soru sorun"), "Müşterim için?");
  await userEvent.click(screen.getByRole("button", { name: "Sor" }));
  expect(await screen.findByText("Soru müşteri bilgisi içeriyor; yalnızca ürün veya şirket hakkında sorun.")).toBeInTheDocument();
});

test("earlier questions of the run come from the server", async () => {
  vi.spyOn(api, "research").mockResolvedValue(ready([product()], [answer("PPN nedir?")]));
  panel();
  expect(await screen.findByText("PPN nedir?")).toBeInTheDocument();
});

test("English labels", async () => {
  vi.spyOn(api, "research").mockResolvedValue(ready());
  panel("EN");
  expect(await screen.findByText("Web source, not verified")).toBeInTheDocument();
  expect(api.research).toHaveBeenCalledWith(sample("run_p01_ready").result.run_id, "EN");
});

test("no research for a run that is not ready", () => {
  const research = vi.spyOn(api, "research");
  renderWith(<ResearchPanel view={sample("run_needs_input")} />);
  expect(research).not.toHaveBeenCalled();
  expect(screen.queryByTestId("research-panel")).toBeNull();
});
```

Run: `npm test -- src/components/ResearchPanel` — expected: FAIL (cannot resolve `./ResearchPanel`).

- [ ] **Step 7: Write the panel**

`web/src/components/ResearchPanel.tsx`:

```tsx
// Web research panel (docs/research.md section 11): the recommended products and their
// companies, researched on the web, and the RM's own questions. Information only: it
// never changes the scores, the recommendation or the meeting text.
import { useContext, useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { Lang, ProductResearch, QuestionAnswer, ResearchFinding, ResearchView, RunView } from "../api/types";
import { fill, LangContext, useT, type LabelKey } from "../i18n";

const POLL_MS = 3000;
const POLL_MAX = 40; // 2 minutes; 3 products take about 10 s
const LIMIT_ERROR = "daily limit"; // rmprep.research.service.LIMIT_ERROR
const CONFIDENCE: Record<ResearchFinding["confidence"], LabelKey> = {
  high: "researchConfHigh",
  medium: "researchConfMedium",
  low: "researchConfLow",
};

/** The research of a ready run: asked at once, then every 3 s while it runs (at most 40 calls).
 * An error, or a server without research, gives "off" with no reason (the panel stays hidden). */
export function useResearch(runId: string, lang: Lang, enabled: boolean): ResearchView | null {
  const [view, setView] = useState<ResearchView | null>(null);
  useEffect(() => {
    setView(null);
    if (!enabled) return;
    let done = false;
    let calls = 0;
    const stop = () => {
      done = true;
      clearInterval(timer);
    };
    const ask = () => {
      if (done) return;
      if (calls >= POLL_MAX) {
        setView({ state: "off", reason: "" });
        return stop();
      }
      calls += 1;
      api.research(runId, lang).then(
        (v) => {
          if (done) return;
          setView(v);
          if (v.state !== "running") stop();
        },
        () => {
          if (!done) setView({ state: "off", reason: "" });
          stop();
        },
      );
    };
    const timer = setInterval(ask, POLL_MS);
    ask();
    return stop;
  }, [runId, lang, enabled]);
  return view;
}

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function FindingList({ findings }: { findings: ResearchFinding[] }) {
  const t = useT();
  return (
    <ul className="text-sm">
      {findings.map((f) => (
        <li key={f.text} className="mb-2">
          <span>{f.text}</span>
          <span className="ml-2 text-xs text-muted">
            {f.sources.map((s, i) => (
              <span key={s.url}>
                {i > 0 && " · "}
                <a href={s.url} target="_blank" rel="noreferrer" title={s.title} className="text-[#355FA1] underline">
                  {host(s.url)}
                </a>
                {s.published && ` (${s.published})`}
              </span>
            ))}
            {` · ${t(CONFIDENCE[f.confidence])}`}
          </span>
        </li>
      ))}
    </ul>
  );
}

function ErrorLine({ error }: { error: string }) {
  const t = useT();
  return <p className="mt-2 text-sm text-[#B54708]">{error === LIMIT_ERROR ? t("researchLimit") : fill(t("researchFailed"), { error })}</p>;
}

function ProductCard({ p }: { p: ProductResearch }) {
  const t = useT();
  const product = p.findings.filter((f) => f.topic !== "sirket");
  const company = p.findings.filter((f) => f.topic === "sirket");
  return (
    <article data-testid="research-product" className="rounded-xl bg-[#F7F9FC] px-4 py-3">
      <h3 className="font-semibold">{p.label}</h3>
      {p.company && <p className="text-sm text-muted">{`${t("researchCompany")}: ${p.company}`}</p>}
      {p.error ? (
        <ErrorLine error={p.error} />
      ) : (
        <>
          {p.summary && <p className="mt-2 text-sm">{p.summary}</p>}
          {p.findings.length === 0 && <p className="mt-2 text-sm text-muted">{t("researchNoFindings")}</p>}
          {product.length > 0 && (
            <>
              <h4 className="mt-2 text-xs font-bold uppercase tracking-[0.06em] text-muted">{t("researchProduct")}</h4>
              <FindingList findings={product} />
            </>
          )}
          {company.length > 0 && (
            <>
              <h4 className="mt-2 text-xs font-bold uppercase tracking-[0.06em] text-muted">{t("researchCompany")}</h4>
              <FindingList findings={company} />
            </>
          )}
        </>
      )}
    </article>
  );
}

function AnswerCard({ a }: { a: QuestionAnswer }) {
  const t = useT();
  return (
    <article data-testid="research-answer" className="rounded-xl bg-[#F7F9FC] px-4 py-3">
      <h3 className="font-semibold">{a.question}</h3>
      {a.error ? (
        <ErrorLine error={a.error} />
      ) : (
        <>
          {a.summary && <p className="mt-1 text-sm">{a.summary}</p>}
          {a.findings.length === 0 ? <p className="mt-2 text-sm text-muted">{t("researchNoFindings")}</p> : <FindingList findings={a.findings} />}
        </>
      )}
    </article>
  );
}

export function ResearchPanel({ view }: { view: RunView }) {
  const t = useT();
  const lang = useContext(LangContext);
  const runId = view.result.run_id;
  const research = useResearch(runId, lang, view.result.state === "ready");
  const [asked, setAsked] = useState<QuestionAnswer[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  useEffect(() => {
    setAsked([]);
    setRefused(null);
  }, [runId, lang]);

  if (research === null || (research.state === "off" && !research.reason)) return null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    setRefused(null);
    api
      .askResearch(runId, q, lang)
      .then(
        (a) => {
          setAsked((xs) => [a, ...xs.filter((x) => x.question !== a.question)]);
          setQuestion("");
        },
        (err) => setRefused(err instanceof ApiError ? err.detail : String(err)),
      )
      .finally(() => setBusy(false));
  };

  const earlier = research.state === "ready" ? research.questions : [];
  const answers = [...asked, ...earlier.filter((s) => !asked.some((a) => a.question === s.question))];

  return (
    <section data-testid="research-panel" className="mb-6 rounded-2xl bg-white px-[26px] py-[22px] shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-bold">{t("researchTitle")}</h2>
        <span className="rounded-full bg-[#FEF0C7] px-2 py-0.5 text-[11px] font-semibold text-[#B54708]">{t("researchLabel")}</span>
      </div>
      <p className="mb-3 text-[13px] text-muted">{t("researchNote")}</p>
      {research.state === "off" && <p className="text-sm text-muted">{fill(t("researchOff"), { reason: research.reason })}</p>}
      {research.state === "running" && (
        <p data-testid="research-running" className="text-sm text-muted">
          {t("researchRunning")}
        </p>
      )}
      {research.state === "ready" && (
        <div className="grid gap-3 lg:grid-cols-3">
          {research.products.map((p) => (
            <ProductCard key={p.option_id} p={p} />
          ))}
        </div>
      )}
      {research.state !== "off" && (
        <form onSubmit={submit} className="mt-4 flex gap-2">
          <input
            aria-label={t("researchAsk")}
            placeholder={t("researchAsk")}
            value={question}
            maxLength={300}
            onChange={(e) => setQuestion(e.target.value)}
            className="flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
          />
          <button
            type="submit"
            disabled={busy || !question.trim()}
            className="rounded-lg bg-cobalt px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {busy ? t("researchAsking") : t("researchAskButton")}
          </button>
        </form>
      )}
      {refused && (
        <p role="status" className="mt-2 text-sm text-[#B54708]">
          {refused}
        </p>
      )}
      {answers.length > 0 && (
        <div className="mt-3 grid gap-3">
          {answers.map((a) => (
            <AnswerCard key={a.question} a={a} />
          ))}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 8: Mount it on the dashboard**

In `web/src/screens/Dashboard.tsx`: add `import { ResearchPanel } from "../components/ResearchPanel";` next to the other component imports, and right after the line `{ready && <DetailsPanel ... />}` add:

```tsx
      {ready && <ResearchPanel view={view} />}
```

- [ ] **Step 9: Run all web tests and the build**

Run: `npm test` then `npm run build` (in `web/`).
Expected: all tests pass (the existing dashboard tests stay green: without a mocked `api.research`, the request fails and the panel stays hidden); the build has no type errors. Do not commit `web/dist/` changes unless `git status` shows `web/dist` is tracked and changed by the build — then commit them too (the lead's merge rule builds `dist` again anyway).

- [ ] **Step 10: Commit on `research-web`**

```bash
git add web/src
git commit -m "research R4: web research panel (findings with sources, RM questions)" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

Report the commit sha. The lead of this feature merges `research-web` into `research` (`git merge --no-ff research-web` in the `research` worktree) after Task 5 is in.

---

### Task 7: Claude web search provider (fallback)

**Files:**
- Create: `src/rmprep/research/claude_search.py`, `tests/research/test_claude_search.py`
- Modify: `src/rmprep/research/service.py` (`research_from_root`: the `claude` branch)

**Interfaces:**
- Consumes: Tasks 1, 2 (`norm_url`, `is_excluded`, `option_code`), Task 4 (`research_from_root`).
- Produces: `ClaudeSearchProvider(config, system_prompt, exclude_domains, *, api_key=None, workspace_id=None, sdk=None, now=...)` with `.name == "claude"`, `.research_product`, `.answer_question`; `ClaudeSearchProvider.from_env(config, system_prompt, exclude_domains, env) -> ClaudeSearchProvider | None`; `parse_blocks(blocks, domains, start_topic) -> tuple[list[Finding], str, int]`.

- [ ] **Step 1: Write the failing tests**

`tests/research/test_claude_search.py`:

```python
import shutil
from datetime import datetime
from types import SimpleNamespace as NS

import pytest

from rmprep.contracts import TR_TZ, ProductOption
from rmprep.research.claude_search import ClaudeSearchProvider
from rmprep.research.config import DEFAULT_PATH, load_config
from rmprep.research.service import research_from_root
from rmprep.research.types import ResearchError

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=TR_TZ)
CONFIG = load_config()
PPN = ProductOption("fund:PPN", "fund", "NUROL PORTFÖY PARA PİYASASI (TL) FONU", fund_kind="money_market")
NUROL, FONOLOJI, KAP = "https://www.nurolportfoy.com.tr/fon/ppn", "https://fonoloji.com/ppn", "https://www.kap.org.tr/tr/Bildirim/1"


def results(*urls):
    return NS(type="web_search_tool_result", content=[NS(type="web_search_result", url=u, title=f"T {u}", page_age=None) for u in urls])


def text(t, *urls):
    cits = [NS(type="web_search_result_location", url=u, title="t", cited_text="c") for u in urls]
    return NS(type="text", text=t, citations=cits or None)


def message(blocks, stop="end_turn", searches=1):
    usage = NS(input_tokens=10000, output_tokens=500, cache_creation_input_tokens=0,
               cache_read_input_tokens=0, server_tool_use=NS(web_search_requests=searches))
    return NS(content=blocks, stop_reason=stop, model="claude-sonnet-5-5", usage=usage)


class FakeSdk:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        return self.replies.pop(0)


def provider(sdk):
    return ClaudeSearchProvider(CONFIG.claude, CONFIG.system_prompt, CONFIG.exa.exclude_domains, sdk=sdk, now=lambda: NOW)


def test_product_findings_company_and_cost():
    sdk = FakeSdk(message([
        results(NUROL, FONOLOJI, KAP),
        text("Fon kısa vadeli para piyasası araçlarına yatırım yapar.", NUROL),
        text("Bu cümlenin kaynağı arama sonucu değil.", "https://other.example/x"),
        text("ŞİRKET: Nurol Portföy Yönetimi A.Ş.\n"),
        text("Şirket Nurol Yatırım Bankası iştirakidir.", FONOLOJI + "/"),
        text("KAP bildirimine göre yeni bir fon kuruldu.", KAP),
        text("Kısa."),
    ]))
    r = provider(sdk).research_product(PPN, "TR")
    assert [(f.topic, f.text) for f in r.findings] == [
        ("urun", "Fon kısa vadeli para piyasası araçlarına yatırım yapar."),
        ("sirket", "Şirket Nurol Yatırım Bankası iştirakidir.")]
    assert r.company == "Nurol Portföy Yönetimi A.Ş." and r.summary == "" and r.provider == "claude"
    assert r.checks == ("2 findings without a valid source dropped",)
    assert r.cost_usd == pytest.approx(10000 * 2 / 1e6 + 500 * 10 / 1e6 + 0.01)
    kw = sdk.calls[0]
    assert kw["model"] == "claude-sonnet-5-5" and kw["max_tokens"] == 8000
    assert kw["tools"] == [{"type": "web_search_20260209", "name": "web_search", "max_uses": 3,
                            "blocked_domains": ["kap.org.tr"]}]
    assert "NUROL PORTFÖY PARA PİYASASI (TL) FONU (PPN)" in kw["messages"][0]["content"]
    assert kw["system"].startswith(CONFIG.system_prompt["TR"])
    assert kw["betas"] == ["server-side-fallback-2026-07-01"] and kw["fallbacks"] == "default"


def test_pause_turn_continues_and_sums_the_cost():
    first = message([results(NUROL), text("Fonun büyüklüğü 9 milyar TL'dir.", NUROL)], stop="pause_turn")
    sdk = FakeSdk(first, message([text("Fon T+0 valörlüdür, aynı gün ödenir.", NUROL)], searches=0))
    a = provider(sdk).answer_question("PPN valörü nedir?", [PPN], "TR")
    assert [f.text for f in a.findings] == ["Fonun büyüklüğü 9 milyar TL'dir.", "Fon T+0 valörlüdür, aynı gün ödenir."]
    assert all(f.topic == "soru" for f in a.findings)
    assert len(sdk.calls) == 2 and sdk.calls[1]["messages"][-1]["role"] == "assistant"
    assert a.cost_usd == pytest.approx(2 * (0.02 + 0.005) + 0.01)


def test_refusal_is_a_request_error():
    with pytest.raises(ResearchError) as e:
        provider(FakeSdk(message([], stop="refusal"))).research_product(PPN, "TR")
    assert e.value.kind == "request"


def test_from_env_needs_the_key():
    assert ClaudeSearchProvider.from_env(CONFIG.claude, CONFIG.system_prompt, (), {}) is None
    p = ClaudeSearchProvider.from_env(CONFIG.claude, CONFIG.system_prompt, (), {"ANTHROPIC_API_KEY": "k"})
    assert p is not None and p.name == "claude"


def test_research_from_root_orders_the_providers(tmp_path):
    (tmp_path / "config").mkdir()
    shutil.copy(DEFAULT_PATH, tmp_path / "config" / "research.yaml")
    only_claude = research_from_root(tmp_path, env={"ANTHROPIC_API_KEY": "k"})
    assert [p.name for p in only_claude._providers] == ["claude"]
    both = research_from_root(tmp_path, env={"ANTHROPIC_API_KEY": "k", "EXA_API_KEY": "e"})
    assert [p.name for p in both._providers] == ["exa", "claude"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `<python> -m pytest tests/research/test_claude_search.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'rmprep.research.claude_search'`.

- [ ] **Step 3: Write `claude_search.py`**

```python
"""Claude web search provider, the fallback of Exa (docs/research.md section 8):
the Messages API with the server tool web_search. Findings are the cited text
blocks of the reply; a citation counts only when its URL is a web_search_result
of the same reply and not on an excluded domain. Cost: tokens at the config
prices plus price_per_search per search. Key and workspace id go only to the SDK."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime

from rmprep.contracts import TR_TZ, ProductOption
from rmprep.research.checks import is_excluded, norm_url
from rmprep.research.config import ClaudeSearchConfig
from rmprep.research.exa import option_code
from rmprep.research.types import Finding, ProductResearch, QuestionAnswer, ResearchError, Source

FALLBACK_BETA = "server-side-fallback-2026-07-01"   # refusal fallback, as the narrator (llm.py)
WORKSPACE_HEADER = "anthropic-workspace-id"
MAX_CONTINUATIONS = 2                                # pause_turn: send the paused turn back
MIN_CHARS = 15
MARKER = re.compile(r"(?:ŞİRKET|COMPANY)\s*:\s*(.+)", re.IGNORECASE)
PRODUCT_PROMPT = {
    "TR": ("Şu yatırım ürününü ve onu yöneten veya ihraç eden şirketi web'de araştır: {label} ({code}). "
           "Önce ürün hakkında kısa, kaynaklı cümleler yaz. Sonra 'ŞİRKET: <şirket adı>' satırını yaz "
           "ve şirket hakkında kısa, kaynaklı cümleler yaz."),
    "EN": ("Research this investment product and the company that manages or issues it on the web: "
           "{label} ({code}). First write short, sourced sentences about the product. Then write the "
           "line 'COMPANY: <company name>' and short, sourced sentences about the company."),
}
QUESTION_PROMPT = {
    "TR": "{question}\n\nİlgili ürünler: {products}. Kısa, kaynaklı cümlelerle yanıtla.",
    "EN": "{question}\n\nRelated products: {products}. Answer in short, sourced sentences.",
}
FORMAT = {"TR": " Her cümle bir web kaynağına dayansın.", "EN": " Base every sentence on a web source."}


def parse_blocks(blocks: Sequence, domains: Iterable[str],
                 start_topic: str) -> tuple[list[Finding], str, int]:
    """(findings, company, dropped). Text blocks with citations become findings;
    a block that holds the company marker switches the topic from urun to sirket."""
    domains = tuple(domains)
    allowed: dict[str, Source] = {}
    for b in blocks:
        if getattr(b, "type", "") == "web_search_tool_result" and isinstance(getattr(b, "content", None), list):
            for r in b.content:
                url = getattr(r, "url", "") or ""
                if url:
                    allowed.setdefault(norm_url(url), Source(url, getattr(r, "title", "") or ""))
    topic, company, findings, dropped = start_topic, "", [], 0
    for b in blocks:
        if getattr(b, "type", "") != "text":
            continue
        text = b.text or ""
        m = MARKER.search(text)
        if m and start_topic == "urun":
            topic = "sirket"
            company = company or m.group(1).strip().strip("*").strip()
            text = text[:m.start()] + text[m.end():]
        text = " ".join(text.split())
        cits = getattr(b, "citations", None) or []
        if not cits or len(text) < MIN_CHARS:
            continue
        sources: dict[str, Source] = {}
        for c in cits:
            src = allowed.get(norm_url(getattr(c, "url", "") or ""))
            if src is not None and not is_excluded(src.url, domains):
                sources.setdefault(norm_url(src.url), src)
        if not sources:
            dropped += 1
            continue
        findings.append(Finding(text, topic, tuple(sources.values())))
    return findings, company, dropped


class ClaudeSearchProvider:
    name = "claude"

    def __init__(self, config: ClaudeSearchConfig, system_prompt: Mapping[str, str],
                 exclude_domains: Iterable[str], *, api_key: str | None = None,
                 workspace_id: str | None = None, sdk=None,
                 now: Callable[[], datetime] = lambda: datetime.now(TR_TZ)) -> None:
        if sdk is None:
            import anthropic          # optional extra [narrator]
            extra = {"default_headers": {WORKSPACE_HEADER: workspace_id}} if workspace_id else {}
            sdk = anthropic.Anthropic(api_key=api_key, **extra)
        self._sdk = sdk
        self._config = config
        self._system = system_prompt
        self._domains = tuple(exclude_domains)
        self._now = now

    @classmethod
    def from_env(cls, config: ClaudeSearchConfig, system_prompt: Mapping[str, str],
                 exclude_domains: Iterable[str], env: Mapping[str, str]) -> ClaudeSearchProvider | None:
        key = env.get(config.api_key_env, "").strip()
        if not key:
            return None
        workspace = env.get(config.workspace_id_env, "").strip() or None
        try:
            return cls(config, system_prompt, exclude_domains, api_key=key, workspace_id=workspace)
        except ImportError:           # the [narrator] extra is not installed
            return None

    def research_product(self, option: ProductOption, lang: str) -> ProductResearch:
        prompt = PRODUCT_PROMPT[lang].format(label=option.label, code=option_code(option))
        blocks, cost = self._run(prompt, lang)
        findings, company, dropped = parse_blocks(blocks, self._domains, "urun")
        checks = (f"{dropped} findings without a valid source dropped",) if dropped else ()
        return ProductResearch(option.option_id, option.label, company, "", tuple(findings), lang,
                               self.name, self._now(), cost, checks)

    def answer_question(self, question: str, products: Sequence[ProductOption],
                        lang: str) -> QuestionAnswer:
        names = "; ".join(f"{p.label} ({option_code(p)})" for p in products) or "-"
        blocks, cost = self._run(QUESTION_PROMPT[lang].format(question=question, products=names), lang)
        findings, _, dropped = parse_blocks(blocks, self._domains, "soru")
        checks = (f"{dropped} findings without a valid source dropped",) if dropped else ()
        return QuestionAnswer(question, "", tuple(findings), lang, self.name, self._now(), cost, checks)

    def _run(self, prompt: str, lang: str) -> tuple[list, float]:
        messages: list[dict] = [{"role": "user", "content": prompt}]
        blocks: list = []
        cost = 0.0
        for _ in range(MAX_CONTINUATIONS + 1):
            msg = self._create(messages, lang)
            cost += self._cost(msg.usage)
            blocks += list(msg.content)
            if msg.stop_reason == "refusal":
                raise ResearchError("request", "the model refused the request")
            if msg.stop_reason != "pause_turn":
                break
            messages = [*messages, {"role": "assistant", "content": msg.content}]
        return blocks, cost

    def _create(self, messages: list[dict], lang: str):
        import anthropic
        tool = {"type": "web_search_20260209", "name": "web_search", "max_uses": self._config.max_uses}
        if self._domains:
            tool["blocked_domains"] = list(self._domains)
        try:
            return self._sdk.beta.messages.create(
                model=self._config.model, max_tokens=self._config.max_tokens,
                system=self._system[lang] + FORMAT[lang], messages=messages, tools=[tool],
                betas=[FALLBACK_BETA], fallbacks="default")
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            raise ResearchError("auth", e.message) from e
        except anthropic.RateLimitError as e:
            raise ResearchError("rate_limit", e.message) from e
        except anthropic.APIStatusError as e:
            if "credit" in str(e.message).lower():
                raise ResearchError("credit", e.message) from e
            raise ResearchError("server" if e.status_code >= 500 else "request",
                                f"{e.status_code} {e.message}") from e
        except anthropic.APIConnectionError as e:     # includes timeouts
            raise ResearchError("connection", str(e)) from e

    def _cost(self, usage) -> float:
        c = self._config
        n = lambda name: getattr(usage, name, 0) or 0          # noqa: E731
        tokens_in = n("input_tokens") + 1.25 * n("cache_creation_input_tokens") + 0.1 * n("cache_read_input_tokens")
        searches = getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0) or 0
        return (tokens_in * c.price_input_per_mtok + n("output_tokens") * c.price_output_per_mtok) / 1e6 \
            + searches * c.price_per_search
```

- [ ] **Step 4: Add the `claude` branch to `research_from_root`**

In `src/rmprep/research/service.py`, inside the `for name in config.providers:` loop, after the `if name == "exa":` block, add:

```python
        elif name == "claude" and config.claude is not None:
            from rmprep.research.claude_search import ClaudeSearchProvider
            p = ClaudeSearchProvider.from_env(config.claude, config.system_prompt,
                                              config.exa.exclude_domains, env)
            if p is not None:
                providers.append(p)
```

Keep the off reason unchanged (`no key in .env: EXA_API_KEY`); the Task 4 and Task 5 tests assert it.

- [ ] **Step 5: Run the tests** — `<python> -m pytest tests/research -q`, expected: pass (the Task 4 test `test_research_from_root_reads_keys` uses `env={"EXA_API_KEY": "k"}`, so it still lists only `exa`).

- [ ] **Step 6: Full suite, then commit**

```bash
git add src/rmprep/research/claude_search.py src/rmprep/research/service.py tests/research/test_claude_search.py
git commit -m "research R5: Claude web search provider as the fallback" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Docs, live smoke test, merge of the web branch, hand-off

**Files:**
- Create: `docs/research.md`, `tests/research/test_live.py`
- Modify: `CLAUDE.md`, `docs/workflow.md`, `docs/web-ui.md` ("Later / optional" entry)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Live smoke test (skipped by default)**

`tests/research/test_live.py`:

```python
"""Live smoke test of the Exa provider (about $0.012): runs only with
RMPREP_LIVE_RESEARCH=1 and an EXA_API_KEY in the environment or in the .env of
RMPREP_LIVE_ROOT (default: the main checkout), so a plain pytest never calls the API."""

import os
from pathlib import Path

import pytest

from rmprep.contracts import ProductOption
from rmprep.research.config import load_config
from rmprep.research.exa import ExaProvider

ROOT = Path(os.environ.get("RMPREP_LIVE_ROOT", "C:/Users/yardang/dev/ing-hackathon/prototype"))
pytestmark = pytest.mark.skipif(os.environ.get("RMPREP_LIVE_RESEARCH") != "1",
                                reason="live test: set RMPREP_LIVE_RESEARCH=1")


def _key() -> str:
    from dotenv import dotenv_values
    return (os.environ.get("EXA_API_KEY") or dotenv_values(ROOT / ".env").get("EXA_API_KEY") or "").strip()


def test_ppn_live():
    key = _key()
    if not key:
        pytest.skip("no EXA_API_KEY")
    config = load_config()
    ppn = ProductOption("fund:PPN", "fund", "NUROL PORTFÖY PARA PİYASASI (TL) FONU", entity="PPN",
                        fund_kind="money_market", asset_class="nakit_benzeri")
    r = ExaProvider(config.exa, config.system_prompt, key).research_product(ppn, "TR")
    assert r.findings and all(f.sources for f in r.findings)
    assert not any("kap.org.tr" in s.url for f in r.findings for s in f.sources)
    assert "Nurol" in r.company
    assert 0 < r.cost_usd < 0.05
```

Run: `<python> -m pytest tests/research/test_live.py -q` — expected: `1 skipped`.
Then once, live: `RMPREP_LIVE_RESEARCH=1 <python> -m pytest tests/research/test_live.py -q` — expected: `1 passed` (cost about $0.012).
Then confirm that the fallback model accepts the web search tool (spec section 8; free): read `capabilities` of `claude-sonnet-5-5` from the Models API with the key and workspace header of `.env` (`anthropic.Anthropic(...).models.retrieve("claude-sonnet-5-5")`) and check `server_tools.web_search.supported`. If it is not supported, change `claude.model` in `config/research.yaml` to a model that supports it and record that in `docs/research.md`.

- [ ] **Step 2: `docs/research.md`**

Write the module doc (as built), in the style of `docs/narrator.md`: status line ("built 2026-10-14 by ing-lead-2; spec ...; plan ..."), why (spec section 1), the user's decisions (spec section 2), the flow (spec section 4), Exa requests (spec section 5, pointing to `exa.py` for the schemas), the checks (spec section 6), providers and fallback (section 8), cache / ledger / limit (section 9, with the real paths `data/research/products/fund_PPN-TR-20261014.json`, `data/research/questions/<run_id>-<lang>-<sha1[:12]>.json`, `data/research/costs.jsonl`), API (section 10), web panel (section 11), tests (how to run the live test), and the KAP note for ingest (section 14). Record every deviation from the spec found during the build (for example: findings from Claude have no summary; questions are cached per run).

- [ ] **Step 3: `CLAUDE.md`, `docs/workflow.md`, `docs/web-ui.md`**

- `CLAUDE.md`, the "Modules and their design docs" sentence: add `research (web research with Exa) = \`docs/research.md\``.
- `CLAUDE.md`, Layout: after the `config/glossary.yaml` line add `  config/research.yaml      web research providers, queries, limit (docs/research.md)`; after the `api/` line add `    research/               web research: Exa and Claude web search, checks, service (ing-lead-2)`; change the `.env` line to `  .env                      EVDS_API_KEY=..., ANTHROPIC_API_KEY=..., EXA_API_KEY=...   (gitignored, never logged)`.
- `docs/workflow.md`, the session table: add the row `| \`ing-lead-2\` | \`C:/Users/yardang/dev/ing-wt/research\` | \`research\` | \`src/rmprep/research/\`, \`tests/research/\`, \`src/rmprep/api/research.py\`, \`config/research.yaml\`, \`docs/research.md\`, \`web/src/components/ResearchPanel.tsx\` (web research; started by the user 2026-10-14; merges go through ing-lead) |`.
- `docs/web-ui.md`, "Later / optional", the "RM research assistant" item: add one sentence at its end: `Built 2026-10-14 with Exa instead of Managed Agents: docs/research.md.`

- [ ] **Step 4: Merge the web branch, rebase, verify**

In `C:/Users/yardang/dev/ing-wt/research`:

```bash
git merge --no-ff research-web -m "Merge research-web: web research panel" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git rebase --rebase-merges main
<python> -m pytest -q
cd web && npm ci && npm test && npm run build
```

Expected: pytest exit code 0; `npm test` and `npm run build` pass. If `main` moved and the rebase conflicts in `api/app.py` or `Dashboard.tsx`, resolve by keeping both sides (the research lines are additive).

- [ ] **Step 5: Commit the docs and hand off**

```bash
git add docs/research.md CLAUDE.md docs/workflow.md docs/web-ui.md tests/research/test_live.py
git commit -m "research R6: docs, live smoke test" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

Then send ing-lead (SendMessage, only after the user agrees): `research@<sha> ready to merge, tests green (pytest, npm test, npm run build); docs/research.md; no eval impact (only the API starts research).`
