# Web research with Exa — design

Status: **draft 2026-10-14 by ing-lead-2, for review by the user.** Branch
`research`, worktree `C:/Users/yardang/dev/ing-wt/research`. Code:
`src/rmprep/research/`, tests: `tests/research/`.

## 1. Goal

When the engine has ranked the options of a run, the tool researches the top 3
recommended products and the companies behind them on the web, and shows the
findings in a separate panel. The RM can then ask more, or more specific,
questions in the same panel. Every finding has its source links and the label
"web kaynağı, doğrulanmamış".

The research never changes the scores, the rules, the recommendation or the
meeting text (note of the user, 2026-10-11, docs/web-ui.md "Later / optional").
It is information for the RM, next to the deterministic evidence.

## 2. Decisions (the user, 2026-10-14)

1. A separate research step; **Exa `/search` is the tool**. No Claude model in
   the loop: Exa searches, reads the pages and writes the structured, grounded
   answer.
2. **Automatic** research of the top 3 (`DecisionResult.recommended`) and their
   companies (portfolio management company, ETF issuer, listed company) when
   the ranking is computed; **RM questions** in the panel after that.
3. **Claude web search as the fallback** behind a `SearchProvider` interface.
4. Numbers in findings are allowed, with the label "web kaynağı, doğrulanmamış".
5. `kap.org.tr` stays excluded (it blocks automated access; brief rule 8).
   Publishers that republish KAP notices (Matriks, mynet, bigpara, news sites)
   are allowed: we never touch KAP.
6. Cost: the Exa free tier ($10 credit per month) covers the demo. Key
   `EXA_API_KEY` in `.env` (never logged).

## 3. Probe results (2026-10-14, throwaway script, $0.076 in total)

- Exa covers Turkish funds and their companies well: official fund pages,
  prospectus, investor information form, fund bulletins of the past days,
  annual reports, fund-data sites (fonoloji, fvt, bloomberght), news. Also for
  a small company (BV Portföy).
- `type: "deep"` with `outputSchema`: $0.012 per call, about 8 s, answers with
  `high` confidence grounded first in the company's own documents.
- Grounding is per field. With findings as **objects** in an array, every
  finding gets its own citations (`bulgular[2].metin`); with an array of
  strings, the array has one citation list. → findings are objects.
- Off-topic results occur (Panasonic "AK-..." pages for "AK Portföy"); none
  reached the answer. The URL check (section 6) removes such a citation anyway.

## 4. Flow

```
POST /api/runs -> DecisionResult (state ready)
  -> ResearchService.start(result, "TR")        background, idempotent
       for each option in result.recommended (kinds fund | etf | stock):
         product cache hit (option_id, lang, today)? -> reuse
         else ExaProvider.research_product(...)  -> findings check -> cache
  -> GET /api/runs/{id}/research?lang=TR  -> 202 while running, 200 when done
RM question in the panel
  -> POST /api/runs/{id}/research/questions {question, lang}
       question check (no client data)  -> refused: 422 with the reason
       ExaProvider.answer_question(...)  -> findings check -> cache -> 200
```

- Research is **per product, not per client**: the cache key is
  `(option_id, lang, date in Europe/Istanbul)`, so two clients with the same
  fund share one call per day, and an edited test run of the same persona is
  free.
- `deposit` and `time_deposit` (ING's own products) are not researched.
- Only the API starts research. `RealBackend`, the CLI and the eval never
  start it (no cost in eval runs, no change to `backend.py`).
- Only products and company names go to Exa. The persona never does: the
  product queries are built by code from `ProductOption.label` and `entity`,
  and the RM question passes the question check first.

## 5. Exa requests

Shapes follow Exa's `build-with-exa` skill: the query plus
`contents.highlights`; other fields only for a stated need.

**Product** (one call per product, covers the product and its company):

```json
{
  "query": "<label> (<code>) fonu ve yöneten portföy yönetim şirketi",
  "type": "deep",
  "excludeDomains": ["kap.org.tr"],
  "systemPrompt": "<language rule> Yalnızca kaynaklarda açıkça yazan bilgileri kullan; tahmin etme. Getiri vaadi veya yatırım tavsiyesi yazma.",
  "outputSchema": {
    "type": "object",
    "properties": {
      "sirket": {"type": "string", "description": "the company that manages / issues the product"},
      "ozet": {"type": "string", "description": "what the product is, 2-3 sentences"},
      "bulgular": {"type": "array", "items": {"type": "object", "properties": {
          "konu": {"type": "string", "description": "urun | sirket"},
          "metin": {"type": "string", "description": "one sourced sentence"}},
        "required": ["konu", "metin"]}}
    },
    "required": ["sirket", "ozet", "bulgular"]
  },
  "contents": {"highlights": true}
}
```

The query wording per kind (fund / ETF / stock) and the language rule (TR:
"Türkçe yaz.", EN: "Write in English.") are in `config/research.yaml`. `deep`
is used because the fields need facts from product pages and company pages.

**Question**: the same request with `"query": <the RM question>`,
`"type": "auto"`, and the schema `{ozet: string, bulgular: [{metin}]}`.

## 6. Checks (code, deterministic)

**Findings check** (every provider): a finding is kept only when at least one
of its citations is a URL that is in the `results` of the same call and not on
an excluded domain; the others are dropped and counted in `checks`. Fields with
no grounding entry are dropped too. The published date of a source comes from
`results[].publishedDate` (may be empty).

**Question check** (before any call): the question is refused when it

- is empty or longer than 300 characters;
- contains a value of the run's persona: the age, or a run of 3 or more words
  from a persona text field (`profil`, `durum`, `yatirim_amaci`, `rm_notu`,
  `oncelikler`, `acik_kisitlar`), compared after Turkish lower-casing;
- refers to the client (`müşteri`, `müşterim`, `client`, `customer`, from
  config).

A refused question gets a plain reason ("Soru müşteri bilgisi içeriyor; yalnızca
ürün veya şirket hakkında sorun.") and costs nothing.

## 7. Data types (`rmprep/research/types.py`, not in `contracts.py`)

```python
@dataclass(frozen=True)
class Source:
    url: str
    title: str
    published: str = ""            # YYYY-MM-DD or ""

@dataclass(frozen=True)
class Finding:
    text: str
    topic: str                     # "urun" | "sirket" | "soru"
    sources: tuple[Source, ...]    # at least one
    confidence: str                # low | medium | high (provider)

@dataclass(frozen=True)
class ProductResearch:
    option_id: str
    label: str
    company: str
    summary: str
    findings: tuple[Finding, ...]
    lang: str
    provider: str                  # "exa" | "claude"
    created_at: datetime           # Europe/Istanbul
    cost_usd: float
    checks: tuple[str, ...] = ()   # e.g. "2 findings without a valid source dropped"
    error: str = ""                # set when the research failed; findings empty

@dataclass(frozen=True)
class QuestionAnswer:
    question: str
    summary: str
    findings: tuple[Finding, ...]
    lang: str
    provider: str
    created_at: datetime
    cost_usd: float
    checks: tuple[str, ...] = ()
    error: str = ""
```

Each has `to_dict` / `from_dict` (cache files and API JSON).

## 8. Providers

```python
class SearchProvider(Protocol):
    name: str
    def research_product(self, option: ProductOption, lang: str) -> ProductResearch: ...
    def answer_question(self, question: str, products: Sequence[ProductOption],
                        lang: str) -> QuestionAnswer: ...
```

- `ExaProvider` (`exa.py`): `httpx`, `POST https://api.exa.ai/search`, header
  `x-api-key`; a timeout of 60 s; cost from `costDollars.total`. HTTP errors
  become `ResearchError(kind)`: `auth` (401/403), `credit` (402), `rate_limit`
  (429), `server` (5xx), `connection`, `request` (other 4xx). Tests use
  `httpx.MockTransport`; no network.
- `ClaudeSearchProvider` (`claude_search.py`, milestone R5): the Messages API
  with the server tool `web_search` (`max_uses` from config, `blocked_domains`
  = the excluded domains), the model from config (Sonnet 5.5; confirm web search
  support of the model with the Models API at build time); the answer as JSON
  with a source URL list per finding; the findings check accepts only URLs of
  `web_search_result` blocks of the same response. Cost: $10 per 1,000 searches
  plus tokens.
- **Fallback:** `config.providers` is an ordered list (default `[exa,
  claude]`). On a `ResearchError` of kind `auth`, `credit`, `server` or
  `connection`, the next provider runs; `request` and `rate_limit` do not fall
  back (the next provider would fail the same way or cost money for a
  transient error). A provider without its key is skipped. No provider left →
  the result has `error` and no findings; the panel shows the reason.

## 9. Cache, cost, limits (`service.py`, `config/research.yaml`)

```yaml
version: 1
providers: [exa, claude]
exa:
  api_key_env: EXA_API_KEY
  product_type: deep
  question_type: auto
  exclude_domains: [kap.org.tr]
  query: {fund: "{label} ({code}) fonu ve yöneten portföy yönetim şirketi",
          etf: "{label} ({code}) borsa yatırım fonu ve kurucusu",
          stock: "{label} ({code}) hissesi ve şirket"}
claude:
  model: claude-sonnet-5-5
  max_uses: 3
  price_input_per_mtok: 2.0
  price_output_per_mtok: 10.0
  price_per_search: 0.01
max_cost_usd_per_day: 2.0        # both providers together; over it -> error "günlük limit"
max_questions_per_run: 10
client_words: [müşteri, müşterim, müşterinin, client, customer]
system_prompt: {...}             # TR / EN, section 5
```

- Cache: `data/research/products/<option_id>-<lang>-<YYYYMMDD>.json`,
  `data/research/questions/<run_id>-<lang>-<sha1 of the question>.json`.
  Failed calls are not cached.
- Ledger: `data/research/costs.jsonl` (time, provider, kind, option or
  question hash, cost); the daily limit sums it for the Turkish date.
- Background: a `ThreadPoolExecutor(max_workers=3)` in `ResearchService`;
  `start` is idempotent per `(run_id, lang)`.

## 10. API (`src/rmprep/api/research.py`, an `APIRouter`)

- `GET /api/runs/{run_id}/research?lang=TR` → starts the research if needed;
  `202 {"state": "running"}` while it runs; `200 {"state": "ready",
  "products": [ProductResearch], "questions": [QuestionAnswer]}`; `200
  {"state": "off", "reason": "..."}` when no provider has a key.
- `POST /api/runs/{run_id}/research/questions` body `{question, lang}` → `200
  QuestionAnswer`; `422` with the reason for a refused question or the run
  limit.

Connection lines in lead-owned files (made on the `research` branch, merged by
ing-lead):

- `api/app.py`: `create_app(..., research=None)`; `_view` calls
  `research.start(result, "TR")` for a ready result; `app.include_router(...)`.
- `api/serve.py`: builds `ResearchService` from the root.
- `.env.example`: `EXA_API_KEY=`.
- `CLAUDE.md` and `docs/workflow.md`: one line / row for the module.

## 11. Web (`web/`)

- New component `ResearchPanel.tsx` on the dashboard below the options: one
  card per researched product (short name, company, summary, findings with
  their source links, the date of each source, a confidence mark) and the
  label "Web kaynağı, doğrulanmamış" at the top; a skeleton while `running`;
  the reason when `off` or failed.
- A question box under the cards; answers appear as cards in the same form;
  a refused question shows its reason.
- Client functions, types and the mock in `web/src/api/`; TR / EN texts in
  `i18n.ts`; one mount line in `Dashboard.tsx`.
- Tests: `vitest` for the panel (running, ready, off, refused question);
  `npm test` and `npm run build` pass.

## 12. Files

New: `src/rmprep/research/{__init__,types,config,checks,exa,claude_search,service}.py`,
`tests/research/`, `src/rmprep/api/research.py`, `config/research.yaml`,
`docs/research.md`, `web/src/components/ResearchPanel.tsx` (+ test).
Changed (small, section 10 and 11): `api/app.py`, `api/serve.py`,
`web/src/api/{client,types,mock}.ts`, `web/src/i18n.ts`,
`web/src/screens/Dashboard.tsx`, `.env.example`, `CLAUDE.md`, `docs/workflow.md`.
Not changed: `contracts.py`, `backend.py`, `narrator/`, `decision/`, `ingest/`,
`eval/`.

## 13. Milestones (each ends with green `pytest`; no test touches the network)

| # | Milestone | Tests show |
|---|---|---|
| R1 | types, config, Exa provider, findings check | request shape per kind; grounding → findings; foreign URL, excluded domain and missing grounding dropped; HTTP errors → error kinds |
| R2 | service: start, cache, ledger, daily limit, question check, fallback chain | cache hit makes no call; deposit not researched; limit stops calls; refused questions; fallback on credit error, none on request error |
| R3 | API router and connection lines | 202 then 200; off without key; 422 for a refused question; `_view` starts research |
| R4 | web panel | running / ready / off / refused; `npm test`, `npm run build` |
| R5 | Claude web search provider | fake SDK: URL check against search results; cost; blocked domains |
| R6 | docs, live smoke test (`RMPREP_LIVE_RESEARCH=1`, about $0.05), hand-off | — |

R4 runs in parallel with R1–R3 (the API shape is fixed in section 10); R5 runs
in parallel after R1.

## 14. Note for ing-lead (not part of this work)

The probe found KAP fund documents and notices on publishers that republish
them (`kapatt.matriksdata.com` for KAP attachments; mynet, bigpara, news
sites). Ingest step 10 (KAP) was dropped on 2026-10-10 because kap.org.tr
blocks automated requests. The user wants KAP data in the ingest pipeline as
evidence, not from this panel; these publishers may be a way to restart step
10, if their terms allow it (rule 8).
