# Web research — design (as built)

Status: **built 2026-10-14 by ing-lead-2; approved by the user 2026-10-14**
(daily limit $2; no limit per run). Spec:
`docs/superpowers/specs/2026-10-14-exa-research-design.md`. Plan:
`docs/superpowers/plans/2026-10-14-exa-research.md`. Code: `src/rmprep/research/`
(`types`, `config`, `checks`, `exa`, `claude_search`, `service`),
`src/rmprep/api/research.py`, `web/src/components/ResearchPanel.tsx`. Tests:
`tests/research/`, `tests/api/test_research_api.py`,
`web/src/components/ResearchPanel.test.tsx`. Config: `config/research.yaml`.

## Why

The RM wants to know more about a recommended product and the company behind it
than the bulletin data tells (note of the user, 2026-10-11, `docs/web-ui.md`
"Later / optional"). This step researches the top 3 recommended products and
their companies on the web and shows the findings in a separate panel. The RM
can then ask more questions in the same panel. Every finding has its source
links and the label "web kaynağı, doğrulanmamış".

The research never changes the scores, the rules, the recommendation or the
meeting text. It is information for the RM, next to the deterministic evidence.

## Decisions (the user, 2026-10-14)

1. A separate research step. **Exa `/search` is the tool.** No Claude model in
   the loop: Exa searches, reads the pages and writes the structured, grounded
   answer.
2. **Automatic** research of the top 3 (`DecisionResult.recommended`) and their
   companies when the ranking is computed. **RM questions** in the panel after
   that.
3. **Claude web search is the fallback**, behind a `SearchProvider` interface.
4. Numbers in findings are allowed, with the label "web kaynağı, doğrulanmamış".
5. `kap.org.tr` stays excluded (it blocks automated access; brief rule 8).
   Publishers that republish KAP notices are allowed: we never touch KAP.
6. Cost: the Exa free tier ($10 credit per month) covers the demo. The key is
   `EXA_API_KEY` in `.env` (never logged). The daily limit is $2 for both
   providers together. There is no limit per run.

## Flow

```
POST /api/runs -> DecisionResult (state ready)
  -> ResearchService.start(result, "TR")        background, idempotent
       for each option in result.recommended (kinds fund | etf | stock):
         product cache hit (option_id, lang, today)? -> reuse
         else provider.research_product(...)  -> findings check -> cache + ledger
  -> GET /api/runs/{id}/research?lang=TR  -> 202 while running, 200 when done
RM question in the panel
  -> POST /api/runs/{id}/research/questions {question, lang}
       question check (no client data)  -> refused: 422 with the reason
       provider.answer_question(...)  -> findings check -> cache + ledger -> 200
```

- Research is **per product, not per client**. The cache key is
  `(option_id, lang, Turkish date)`. Two clients with the same fund share one
  call per day.
- `deposit` and `time_deposit` (ING's own products) are not researched.
- Only the API starts research: `api/app.py` calls `research.start(...)` in
  `_view` for a ready result. `RealBackend`, the CLI and the eval never start
  it. They have no cost from research and `backend.py` did not change.
- Only products and company names go to a provider. The persona never does. Code
  builds the product queries from `ProductOption.label` and the option code. The
  RM question passes the question check first.

## Exa requests (`exa.py`)

One `POST https://api.exa.ai/search` per product or question. Header
`x-api-key`; timeout 60 s; cost from `costDollars.total`. The code uses `httpx`
(not `exa-py`).

- **Product:** `type: deep` (the fields need facts from product pages and company
  pages), `excludeDomains: [kap.org.tr]`, `systemPrompt` (the language rule and
  the grounding rule, TR or EN, from `config/research.yaml`), `outputSchema`
  `PRODUCT_SCHEMA` (`sirket`, `ozet`, `bulgular[{konu, metin}]`) and
  `contents.highlights`. The query text per kind (fund, ETF, stock) is in the
  config. A probe cost $0.012 and 8 s per call.
- **Question:** the RM question as the query, `type: auto`, `QUESTION_SCHEMA`
  (`ozet`, `bulgular[{metin}]`). The system prompt names the run's researched
  products as context.
- Findings are **objects** in an array. Exa then grounds each finding with its
  own citations (`bulgular[2].metin`). With an array of strings, the whole array
  has one citation list. The schemas are in `exa.py`.
- HTTP errors become `ResearchError(kind)`: `auth` (401, 403), `credit` (402),
  `rate_limit` (429), `server` (5xx), `connection` (transport error, timeout),
  `request` (other 4xx, or a reply with no structured output).

## Checks (`checks.py`, code, deterministic)

**Findings check** (every provider). A finding is kept only when at least one of
its citations is a URL that is in the `results` of the same call, is an http(s)
URL and is not on an excluded domain. The code compares URLs after a light
normal form (scheme and host in lower case, no fragment, no trailing slash).
Other findings are dropped and counted in `checks`. The fields `sirket` and
`ozet` with no valid source are left out and noted in `checks`. The published
date of a source comes from `results[].publishedDate` (may be empty). The
confidence of a finding is the highest one that Exa gives for it.

**Question check** (before any call; a refused question costs nothing). The
question is refused when it:

- is empty or longer than 300 characters (`question_max_chars`);
- contains the age of the persona as a word;
- has a run of 3 words or more that is also in a persona text field (`profil`,
  `durum`, `yatirim_amaci`, `rm_notu`, `oncelikler`, `acik_kisitlar`), after
  Turkish lower-casing;
- has a word that starts with a client word (`müşteri`, `client`, `customer`;
  so `müşterim` and `müşterinin` match too).

The reason is plain text in the language of the panel, for example "Soru
müşteri bilgisi içeriyor; yalnızca ürün veya şirket hakkında sorun."

## Providers and fallback (`service.py`, `claude_search.py`)

- `ExaProvider` is the first provider (`providers: [exa, claude]` in the config).
- `ClaudeSearchProvider` uses the Messages API with the server tool
  `web_search_20260209` with `allowed_callers: ["direct"]` (`max_uses` and
  `blocked_domains` from the config). The model is `claude.model` (Haiku 5.5). The
  code sends the refusal-fallback beta like the narrator and sends a `pause_turn`
  back at most twice. The reply splits a line into text blocks: only the cited
  span has citations. A finding is one sentence of the reply: a unit ends at a
  newline or at a sentence end (`.`, `!`, `?`), also inside a block. It has only
  the citations of its own blocks, so a sentence of the model's own words never
  takes the source of a cited span on the same line. An abbreviation such as
  "A.Ş. " can split a sentence; then a part without citations is lost, but no
  source is wrong. Bold marks and list marks are removed. A citation counts only when its URL is in a
  `web_search_tool_result` block of the same reply and is not on an excluded
  domain. The key and the workspace id (`ANTHROPIC_WORKSPACE_ID`) go only to the
  SDK. Cost: tokens at the config prices plus $0.01 per search.
- **Fallback:** on a `ResearchError` of kind `auth`, `credit`, `server` or
  `connection`, the next provider runs. `request` and `rate_limit` do not fall
  back (the next provider would fail the same way, or cost money for a transient
  error). A provider with no key is left out. If no provider is left, research is
  `off` with the reason "no key in .env: EXA_API_KEY".
- If every provider fails, the product has `error` ("exa: credit; claude: auth",
  the kinds only) and no findings. The panel shows the reason.
- Models API check (2026-10-15, free): `claude-sonnet-5-5` and
  `claude-haiku-5-5` have `capabilities.server_tools.web_search.supported =
  true`. The model in `config/research.yaml` is `claude-haiku-5-5` since
  2026-10-15 (see "Claude fallback: 0 findings, fixed").

## Cache, ledger, limit

- Products: `data/research/products/<option_id>-<lang>-<YYYYMMDD>.json`, with `:`
  in the option id written as `_`, for example
  `data/research/products/fund_PPN-TR-20261014.json`.
- Questions: `data/research/questions/<run_id>-<lang>-<sha1[:12]>.json` (the sha1
  is of the stripped question).
- Ledger: `data/research/costs.jsonl`, one JSON line per paid call (`at`,
  `provider`, `kind`, `ref`, `cost_usd`). The daily limit sums the lines of the
  Turkish date. The check runs before each provider call. Over the limit, the
  result has the error `daily limit` and the panel says so.
- `data/research/` is in `.gitignore`. The cache and the ledger never enter git.
- A failed call is not cached. `start` (a new view of the run) tries a failed
  product again. `status` (the polling of the panel) never does, so a lasting
  error ends the polling.
- A thread pool of 3 runs the background work. `start` is idempotent per
  `(option_id, lang, day)`.

## API (`api/research.py`)

- `GET /api/runs/{run_id}/research?lang=TR`: `202 {"state": "running"}` while
  the research runs; `200 {"state": "ready", "products": [...], "questions":
  [...]}`; `200 {"state": "off", "reason": "..."}` when no provider has a key.
  `lang` other than TR or EN gives 422. An unknown run gives 404.
- `POST /api/runs/{run_id}/research/questions` with `{question, lang}`: `200` with
  the answer (it can have `error`); `422` with the reason for a refused question
  or when research is off.
- `create_app(..., research=None)`: with `None` there are no research routes.
  `api/serve.py` builds the service with `research_from_root(root)` when
  `config/research.yaml` exists.

## Web panel (`ResearchPanel.tsx`)

The panel is below the options on the dashboard (one mount line in
`Dashboard.tsx`). It polls every 3 s while the state is `running` (at most 40
calls). It shows one card per researched product: short name, company, summary,
findings (product and company) with source links, the date of each source and
a confidence mark. A skeleton shows while the research runs. The reason shows
when the state is `off` or a product failed. Under the cards, a question box:
answers appear as cards of the same form; a refused question shows its reason.
Texts are in `i18n.ts` (TR and EN).

## Deviations from the spec (found during the build)

1. Sources must be http(s) URLs (`is_web_url`). The spec only named the check
   against the results and the excluded domains. A `javascript:` URL would become
   a link in the panel.
2. The API key is removed from error texts (`ResearchError` of Exa replaces it
   with `***`). The spec said only "never in an error text".
3. A failed cache write leaves the result uncached, but the result is returned
   and its cost is in the ledger. The cache never blocks a product or a question.
4. The Claude provider gives no summary (`summary` is empty). Its findings have
   the confidence `medium` (Claude gives none). It finds the company from a
   marker line in the text ("ŞİRKET: ..."). The tool type is
   `web_search_20260209` with `allowed_callers: ["direct"]` (no dynamic
   filtering), and the result blocks are `web_search_tool_result`.
5. Questions are cached per run: `<run_id>-<lang>-<sha1[:12]>`. The spec did not
   say how the question cache handles the run. `GET` returns the questions of the
   run that exist on disk.
6. The panel shows one label ("Web kaynağı, doğrulanmamış") at its top, not on
   each card.
7. `data/research/` is in `.gitignore`.
8. The config has more keys than the spec shows: `cache_dir`,
   `question_max_chars`, `claude.max_tokens`, the key names and the workspace id.
   `client_words` are word roots (prefix match), so it has three entries, not
   five.
9. `status` never starts a failed product again; only `start` does (see Cache).
10. Fields of the Exa answer (`sirket`, `ozet`) with no valid source are left out,
    not only the findings.
11. Live check of the Claude provider (see Tests): the first call gave no
    findings. The cause was found and fixed; see "Claude fallback: 0 findings,
    fixed".

## Tests

- `pytest` runs the research tests with no network: Exa with
  `httpx.MockTransport`, Claude with a fake SDK object.
- Live smoke test of Exa (about $0.012), skipped by default:
  `RMPREP_LIVE_RESEARCH=1 python -m pytest tests/research/test_live.py -q`. It
  needs `EXA_API_KEY` in the environment or in the `.env` of `RMPREP_LIVE_ROOT`
  (default: the main checkout). It researches the fund `PPN` and checks the
  findings, the sources, the company name and the cost.
- Result 2026-10-14: the Exa live test passed (1 passed). The Claude provider
  live call for the same fund (about $0.15) gave the company "Nurol Portföy
  Yönetimi A.Ş." and no findings. After the fix (2026-10-15): 17 findings, $0.026
  (see "Claude fallback: 0 findings, fixed").
- Web: `cd web && npm test && npm run build`.

## Claude fallback: 0 findings, fixed (2026-10-15)

- Symptom (2026-10-14): one live call for `PPN` gave 0 findings, no dropped
  finding, the company "Nurol Portföy Yönetimi A.Ş." and a cost of $0.15
  (estimate: $0.04).
- Root cause (a live call with the same request, block structure recorded):
  `web_search_20260209` runs web search from code execution by default
  (dynamic filtering, `allowed_callers` defaults to `["code_execution_20260120"]`).
  The model ran 4 `code_execution` calls; 2 `web_search` calls had a `caller`
  of type `code_execution_20260120`. The model read the results from the
  `stdout` of the code. The answer was one `text` block with `citations: null`;
  the sources were plain text ("(Kaynak: bloomberght.com/...)"). With no
  citations, the check skipped the block and counted nothing as dropped. The
  code loop sent the context again 4 times: 65,044 input tokens, $0.176 on
  Sonnet 5.5.
- Second cause (seen after the first fix): with direct search, the answer is
  many `text` blocks. Only the cited span has citations ("8 Temmuz 2021"); the
  words around it are other blocks with `citations: null`. The old check made a
  finding of each block, so the findings were fragments.
- Fix: the tool has `allowed_callers: ["direct"]`; a finding is a sentence of
  the reply with the citations of its own blocks (`_units` in `claude_search.py`);
  the model is `claude-haiku-5-5` ($0.10 / $0.50 per MTok, prompts up to 100K
  tokens). Sonnet 5.5 with direct search would cost about $0.14 for the same
  tokens (about 35,000 input tokens and 5,000 output tokens).
- Live result after the fix (`PPN`, TR): 17 findings (10 product, 7 company),
  every source http(s), none on kap.org.tr, company "Nurol Portföy Yönetimi
  A.Ş.", 2 searches, 34,499 input tokens, 5,554 output tokens, $0.026.
- Tests: `test_live_reply_shape_cited_spans_inside_lines` and
  `test_live_reply_markdown_and_period_after_a_quote_are_removed` use the block
  structure of the real replies.
  `test_an_uncited_sentence_never_takes_the_source_of_its_line` (review fix):
  an uncited sentence before or after a cited span on the same line is not in
  a finding.
- Review fix (2026-10-15): the first version ended a unit only at a newline or
  at a block end, so an uncited sentence on the line of a cited span showed that
  source. An offline replay of the recorded replies with the final parser gives
  20 findings (first experiment) and 23 findings (live call after the fix); the
  live call itself was made with the first version (17 findings).

## Open points

- Claude fallback: in some findings the model writes its own sentence and then
  the quote from the source, so the finding says the same thing twice. The
  prompt can ask for one form.
- Claude fallback cost: the config price is the Haiku 5.5 price for prompts up
  to 100K tokens. With more searches (`max_uses` 3) a prompt can go over 100K
  tokens; the price is then 5 times higher and the ledger shows too little.

## Note for ing-lead (not part of this work)

The probe found KAP fund documents and notices on publishers that republish them
(`kapatt.matriksdata.com` for KAP attachments; mynet, bigpara, news sites).
Ingest step 10 (KAP) was dropped on 2026-10-10 because kap.org.tr blocks
automated requests. The user wants KAP data in the ingest pipeline as evidence,
not from this panel. These publishers may be a way to restart step 10, if their
terms allow it (rule 8).
