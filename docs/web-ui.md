# Web UI — design (spec)

Status: **2026-10-11. Screen design decided with the user (brainstorming with
mockups). Technical sections 1 and 2 approved by the user 2026-10-11;
sections 3–9 approved by the user 2026-10-11 (spec review). Plan:
`docs/superpowers/plans/2026-10-11-web-ui.md`.** The final
mockups are in git: `docs/web-ui/mockups/` (`layout.html`, `detail-v5.html`,
`dikkat-v3.html`, `meeting-text-v9.html`); the earlier versions stay in the
git-ignored `.superpowers/brainstorm/`.

Replaces the Streamlit UI (`src/rmprep/ui/`, docs/ui.md), which stays as a
fallback until the web app can do everything.

## Why (the user's demo feedback, 2026-10-11)

The Streamlit page was hard to use and did not look good: the approval area
was too long and did not offer the best 3 options; an evidence table that
belongs next to each value; the short list started with the eliminated funds;
"Olası sorunlar" was not grouped; the option detail had weak visuals and raw
score numbers; categories showed too many options; the meeting text (the main
output) was hidden until approval and was missed in the demo.

## Decisions (the user)

- **Technology: a custom web app** (approach B), not styled Streamlit: the
  best visual quality. "A sleek, professional banking app (J.P. Morgan, Bank of
  America style) that an RM can understand easily."
- **Theme:** ING orange **#FF6200** (from ing.com.tr's own stylesheet; the
  site also uses #FF6600 and the font INGMe, which we cannot use → Inter)
  **only for the brand and the main buttons**. Surfaces white / soft grey,
  text navy-slate (#1D2440). Chart color **cobalt blue #4676BF** (the first
  data-visualization color of J.P. Morgan's public design system Salt,
  `@salt-ds/theme`); category comparisons in light grey (#D0D5DD). Green →
  red for risk and match. No orange in charts.

### Main screen (dashboard, layout A — mockup `layout.html`)

1. **Client card** on top: profile, horizon, liquidity, priorities as tags,
   the constraint in its own color; **"Düzenle"** opens a side panel with all
   persona fields → an edited persona is a **test run** (banner; cannot be
   approved).
2. **"Müşteriyle konuşulacaklar"**: a row of 2–3 cards right under the client
   card, each with a short label, a large number and one sentence
   (`dikkat-v3.html`, A). **Only client-relevant points, from the client's
   view.** Corrected 2026-10-11: ING's own rate vs the market is NOT a client
   talking point (it is an internal RM note), and the Turuncu Hesap real
   return is not a fact about the client; a deposit point appears only for a
   client with a deposit focus (P01), without ING numbers.
3. **Top 3 recommendations as cards** (the group heads), next to the deposit
   baseline as a "Karşılaştırma" card (a reference for the RM).
4. **Categories, closed** (e.g. "Para Piyasası · 3 fon · en iyi %47,6 ›");
   a click opens **at most 3 funds**; each fund is itself expandable.
5. **Right panel** (`dikkat-v2.html` / `dikkat-v3.html`): plain text, no
   colored boxes (enterprise patterns: IBM Carbon, Atlassian, GitHub Primer,
   Shopify Polaris, Microsoft Fluent, J.P. Morgan Salt):
   - **"Teyit edin"**: a checklist with real checkboxes, written as commands;
     the only part with a signal (small amber dot, "1 açık" → "Tamam");
   - then collapsed lines, in this order: **Varsayımlar · N → Veri notları ·
     N → "N seçenek elendi"** (opens one row per rule with its count; a row
     opens the funds and reasons; "a fund can fail more than one rule").
   - A data note about one fund shows on that fund's card.
6. **Approval bar** at the bottom: "Görüşmede konuşulacak" with the top 3 as
   chips (selected at the start; ✕ removes; "Seçime ekle" in a fund adds),
   an optional note, "Reddet", **"Onayla ve metni hazırla"** (also starts the
   meeting text in the background — lever 1).
7. **No evidence table.** Evidence only on demand: a "Kanıt" link next to a
   value opens a pop-up (value, source, date, evidence id, flags).

### Fund card (opened fund — mockup `detail-v5.html`)

- **Match ring 0–10** ("uygunluk") with a **red → green** color by value.
- **Stars 1–5** inside the category (Morningstar-style split: top 10 % = 5,
  next 22.5 % = 4, middle 35 % = 3, next 22.5 % = 2, bottom 10 % = 1) and
  under them the **rank as a fraction, large: "3. / 88"**, with "kategori
  sırası · 1 yıl getiri · Kanıt". Always show the number of funds.
- **SPK risk value**: a thin bar of 7 segments; **all filled segments take
  the color of the fund's level** (1 green #12B76A, 2 #66C61C, 3 #A6C612,
  4 orange #F79009, 5 #EF6820, 6 #E04F16, 7 red #D92D20); e.g. risk 4 = four
  orange segments.
- Tiles: risk, "Paraya erişim" (from the sell valör, e.g. "Aynı gün").
- **Returns: fund vs category average** as paired bars per period (3 months,
  6 months, 1 year, real), fund in cobalt blue, category in grey, with a
  green / red delta pill ("+3,1 puan").
- **"Bu müşteri için neden?"** box; "Seçime ekle" (orange main button).
- No raw score numbers; words instead ("Kategorisinin ilk %4'ü").

Research behind these choices (2026-10-11): banks show a fund against its
category with Morningstar stars, the category rank with the fund count, and
fund vs category average per period; Fidelity adds words (High … Low);
Turkish apps (TEFAS, Midas, İş Portföy) show the SPK risk 1–7 as boxes and
return tables. Distribution / spread charts were rejected as unintuitive.

### Meeting text ("Görüşme hazırlığı" view — mockup `meeting-text-v9.html`)

- Opens by itself after approval; the dashboard stays one click away. Bar:
  status ("Taslak · onayınızı bekliyor"), TR / EN, "Düzenle", "Metni onayla".
- **Readable type**: body 17 px, script 19 px, headings 22–26 px, line width
  about 70 characters; not "plain text": cards, icons, key figures.
- **Header card (navy gradient), only the client**: profile, aim, priorities
  and constraint as tags, **three talking points from the client's view**,
  and on **one row**: **"Görüşmede söyleyebileceğiniz"** (the speaking script,
  about two thirds) and **"Notlarım"** (a white rounded box the RM types
  into, about one third; saved automatically; goes into the card).
- **"Öneriler"**: one rich card per selected option: rank badge, name, three
  tiles (1-year return, risk bar, access), **client-need tags**, one or two
  sentences, "Kanıtları göster (n) ›", and **a note field for that option**.
- **"Dikkat"**: short items with round icons.
- **"RM notları · yalnızca sizin için"**: internal notes (e.g. ING's rate vs
  the market), never in the client-facing parts.
- Right column: **"Terimler"** (glossary terms that appear in the text) and
  the card download (PDF, Markdown) with model, check result and cost.

### Logic changes the screens need (decided in principle)

- The card is written as **instructions to the RM** ("… anlatın"), except
  the speaking script (quoted speech for the client) — narrator.
- The engine marks every warning / note as **for the client** or **for the
  RM only** — decision.
- The narrator writes **client-centred talking points** (new section) and
  **need tags per recommendation** — narrator.
- Clear names for the two notes: the persona's note (from the file) and the
  RM's approval note (typed at run time, empty at first) — narrator.

## Technical design (spec)

### 1. Architecture (approved by the user 2026-10-11)

```
browser ──JSON──> FastAPI (src/rmprep/api/) ──> RealBackend (backend.py) ──> decision / narrator / evidence
   ^                   │
   └── static files ───┘   web/dist (built React app), same address
```

1. **JSON API** `src/rmprep/api/` (FastAPI, **lead-owned**), a thin layer on
   `RealBackend`. It adds no business rules; it only puts the engine's values
   into view models and calculates display values (rank, stars, category
   average, match ring; section 6). Endpoints: section 6.
2. **Web app** `web/` (React + TypeScript + Tailwind, built with Vite), the
   screens above; new worker **`ing-web`** (effort `medium`) in its own
   worktree `C:/Users/yardang/dev/ing-wt/web`, branch `web`.
3. **One command**: `python -m rmprep serve [--port 8600]` starts the API on
   `http://127.0.0.1:8600` (local only, no login) and serves `web/dist`. Node
   (v24 on the laptop) is needed only to build: `cd web; npm ci; npm run build`.
   `web/dist/` and `web/node_modules/` are not in git.
4. New optional extra `web = ["fastapi", "uvicorn"]`. No PDF library: the
   browser prints the card from a print layout.
5. Streamlit (`src/rmprep/ui/`) stays as a fallback until the web app can do
   everything; then it is removed. Until then the API reuses
   `rmprep.ui.card` (card Markdown), `rmprep.ui.glossary` (terms) and, in
   tests, `rmprep.ui.fake.FakeBackend` (none of them imports Streamlit).
6. Tests: section 9.

### 2. Data the screens need (approved 2026-10-11; ➕ = added in the spec)

| Need | Source | Contract change |
|---|---|---|
| Category rank "3. / 88", stars, category average per period | API (section 6), from the display facts of D17 | no |
| Match ring 0–10 | API: `10 × (n − position) / (n − 1)` over the run's ranked options (deposit baseline not counted), one decimal; n = 1 → 10 | no |
| "Paraya erişim" | display facts (D17): `fund_sell_valor_days`, 0 → "Aynı gün", n → "n iş günü"; time deposit → "Vade sonunda (32 gün)" from config | no |
| "For the client" / "for the RM only" on warnings | decision **D16**: `DecisionWarning.audience` | yes (v1.3) |
| ➕ "Teyit edin" items | decision **D16**: `DecisionResult.to_confirm` (commands from config for assumptions that need the client, e.g. the amount tier) + the open non-blocking questions | yes (v1.3) |
| ➕ Display facts for every fund of a run (returns per period, real 1-year return, risk, sell valör, "neden" lines) | decision **D17**: a pure function in the decision module | no |
| ➕ Dashboard row "Müşteriyle konuşulacaklar" | decision **D18**, deterministic, texts in config | yes (v1.3): `TalkingPoint`, `DecisionResult.talking_points` |
| Talking points of the meeting text; need tags per recommendation | narrator **N9** | yes (v1.3) |
| Card as instructions to the RM; clear names for the two notes | narrator prompt (N9) | no |
| RM notes (general, per option) | existing `annotate` | no |
| "Teyit edin" check marks | browser only (local storage per run), not in the card; a question item also has "Yanıtla" (its choices) → `POST /runs/{id}/answers` → a new run | no |

Why the additions: the dashboard row shows **before** approval, but the
narrator runs only after approval (docs/narrator.md, decision 2), so the row
must come from the decision engine. The real return (stopaj, CPI) and the
"neden" lines (priority → criterion) are business rules, and the API adds no
rules; so they come from decision too.

### 3. Contract v1.3 (additive; lead)

All new fields have defaults: saved runs, fixtures and narratives of v1.2 still
load.

```python
WARNING_AUDIENCES = ("client", "rm")

@dataclass(frozen=True)
class DecisionWarning:                   # existing fields unchanged
    ...
    audience: str = "rm"                 # "client": may go into client-facing text

@dataclass(frozen=True)
class TalkingPoint:
    code: str                            # deposit_real | best_alternative | access | risk_fit
    label: str                           # short, e.g. "Mevduatta reel getiri"
    figure: str                          # the large number as text, e.g. "−%8,3", "Aynı gün"
    text: str                            # one sentence, from the client's view
    evidence_ids: tuple[str, ...] = ()
    option_ids: tuple[str, ...] = ()

# DecisionResult, new fields:
    talking_points: tuple[TalkingPoint, ...] = ()   # 0..3, display order
    to_confirm: tuple[str, ...] = ()                # commands for the RM, e.g.
                                                    # "Yatırım tutarını sorun: 100.000–249.999 TL dilimi varsayıldı."

# narrator:
NARRATIVE_SECTIONS_V13 = NARRATIVE_SECTIONS + ("talking_points",)
# NARRATIVE_SECTIONS stays the v1.2 list (a v1.2 narrator stays valid);
# NarrativeSection accepts every key of NARRATIVE_SECTIONS_V13; N9 switches the
# narrator to NARRATIVE_SECTIONS_V13.
# NarrativeSentence, new field:
    title: str = ""                      # talking_points only: 2–4 word heading
# NarrativeDraft, new field:
    need_tags: Mapping[str, tuple[str, ...]] = {}   # option_id -> client priorities
```

Checks in `__post_init__`: `audience` in `WARNING_AUDIENCES`; a talking point
has a non-empty label, figure and text; at most 3 talking points; their
`option_ids` are scored options of the result. The narrator validator (not
the contract) checks the need tags against the persona.

### 4. Decision changes (worker `ing-decision`; details go to docs/decision.md)

- **D16 audience and to_confirm.** Config `warnings.audience: {<code>:
  client|rm}`: `concentration`, `fx_exposure` → client; `deposit_vs_market`,
  `risk_estimate`, `low_stability`, `no_fx_deposit_data` → rm; a code not in
  the table → rm. Config `to_confirm: {<assumption key>: <command template>}`
  (first entry: the deposit tier, "Yatırım tutarını sorun: {tier} dilimi
  varsayıldı."). The lead also rewrites the texts of the non-blocking
  questions in config as commands ("… sorun"), because "Teyit edin" shows
  them.
- **D17 display facts.** `rmprep.decision.display.display_facts(result,
  evidence, config) -> dict[str, DisplayFacts]` for every option in
  `result.options` and `result.rejected` (named so because the narrator
  already has an `OptionFacts`). `DisplayFacts` (a decision type, not a
  contract type; stable for the API; docs/decision.md section 9): nominal returns 3 months, 6 months, 1 year (each value
  + evidence id, or none); the real 1-year return after stopaj and CPI (the
  D9 rule; none without CPI); SPK risk value 1–7 (+ evidence id, or none);
  sell valör days (+ evidence id, or none); `why`: one line per persona
  priority that maps to a criterion of the option, in words, no score
  numbers (e.g. `("likiditeyi koruma", "Paraya aynı gün erişim")`).
- **D18 talking points.** At most 3, in the config order `[deposit_real,
  best_alternative, access, risk_fit]`, each only if its condition holds:
  - `deposit_real`: the persona's `durum` contains a config keyword
    ("mevduat"); figure = the real 1-year return of the **EVDS market**
    deposit rate after the deposit stopaj and CPI. No ING numbers.
  - `best_alternative`: the real 1-year return of the first
    recommendation; the text says that it is a past return.
  - `access`: `likidite_ihtiyaci` is not low, or a priority maps to
    liquidity: the slowest sell valör of the top 3.
  - `risk_fit`: the highest SPK risk value of the top 3 against the client's
    ceiling ("en fazla 2 / 7").

  Numbers in Turkish format ("−%8,3"). "Top 3" = the heads of the first three
  groups, `rmprep.grouping.top_heads(options, 3)` (new, lead), the same
  function that the dashboard uses.

### 5. Narrator changes (worker `ing-narrator`, N9; details go to docs/narrator.md)

- New section `talking_points`: 2–3 sentences, each with a `title`, about the
  client's situation from the client's view. Input: the decision talking
  points, the persona and the selection. Each sentence has a citation.
- `need_tags`: for each selected option, 1–3 tags; each tag is one of the
  persona's `oncelikler`, exactly (compared with Turkish lower-casing). An
  unknown tag is a validator error (retry, then template). The template takes
  the tags from the `why` lines of D17.
- The facts pack holds only warnings with audience `client`. RM-only
  warnings never reach the narrator; the web shows them in "RM notları"
  directly from the `DecisionResult`.
- The card is written as instructions to the RM ("… anlatın"); only
  `teklif_metni` is quoted speech for the client.
- Note names in the facts pack: `dosyadaki_not` (the persona's `rm_notu`)
  and `rm_onay_notu` (the RM's note from the approval).
- Prompt version `n4`. The eval runs again after N9 and must pass.

Where each section shows in the meeting text view:

| Section | Place |
|---|---|
| `ozet` | header card, "Görüşmenin amacı" line |
| `talking_points` | header card, three cards |
| `teklif_metni` | "Görüşmede söyleyebileceğiniz" |
| `oneriler` | one card per selected option (its sentences by `option_ids`) + need tags |
| `dikkat` | "Dikkat" |
| `alternatifler`, `sorular`, `varsayimlar` | collapsed lines under "Dikkat": "Diğer seçenekler", "Sorulacak sorular", "Varsayımlar" |
| (RM-only warnings, not narrator) | "RM notları · yalnızca sizin için" |

"Düzenle" opens the whole text as Markdown (`narrator.template.to_markdown`)
in an editor. "Metni onayla" approves the shown text (`approve_narrative`).
After an edit, the view shows the edited Markdown, formatted, with the label
"Düzenlenmiş metin"; the cards show again only for an unedited draft.

### 6. API (lead): endpoints and view models

All bodies JSON; contract objects as their `to_dict()`. Prefix `/api`.

| Method, path | Does | Backend call |
|---|---|---|
| `GET /personas` | the personas | `list_personas` |
| `GET /snapshots` | snapshot ids, newest first | `list_snapshots` |
| `GET /snapshots/{id}/sources` | the sources of one snapshot and their status ("Veri" menu) | `evidence(...).source_status` |
| `POST /runs` `{persona, snapshot_id?, exclude_sources?}` | a run (persona = full dict; edited → test run) | `decide` |
| `GET /runs/{run_id}` | the `RunView` again | — |
| `POST /runs/{run_id}/answers` `{question_id, answer}` | a new run | `answer_question` |
| `POST /runs/{run_id}/approval` `{status, note, selected}` | approve or reject; approval starts the TR text | `approve` |
| `PUT /runs/{run_id}/notes` `{note, option_notes}` | RM notes ("Notlarım", per option); saves the card again | `annotate`, `save_card` |
| `GET /runs/{run_id}/narrative?lang=TR` | the meeting text (waits for the job, at most 120 s) | `draft_narrative` |
| `POST /runs/{run_id}/narrative/{lang}/approval` `{text}` | approve the text | `approve_narrative` |
| `GET /runs/{run_id}/card.md` | the card as Markdown (download) | `rmprep.ui.card` |
| `GET /evidence/{snapshot_id}/{evidence_id}` | one DataPoint + the fund name (pop-up) | `evidence` |
| `GET /glossary?lang=TR&run_id=…` | the terms that appear in the run's text | `rmprep.ui.glossary` |

**`RunView`** (`GET/POST /runs…`):

- `result`: the `DecisionResult`; `test_run`: bool; `persona_changes`: the
  changed fields of an edited persona (`[{field, original, edited}]`).
- `baseline`: the deposit option view, or null.
- `top`: the option ids of the top 3 (`grouping.top_heads`).
- `categories`: one per group of `rmprep.grouping`: `{key, label, count,
  best_return_1y, option_ids}`, at most 3 option ids (the head first); no
  "more" button.
- `options`: `{option_id: OptionView}` for every option in `baseline`, `top`
  and `categories`.
- `talking_points`, `to_confirm` + the open non-blocking questions,
  `assumptions`, `data_notes`, `client_warnings`, `rm_warnings` (by
  `audience`).
- `rejected_by_rule`: `[{rule_id, label, count, options: [{label, reasons}]}]`.

The API keeps a registry `run_id → DecisionResult` of every result it
returned; `GET /runs/{id}` reads it (the `Backend` protocol has no "get run").
There is no narrative status in the `RunView` (the protocol cannot report
it): the web shows "Metin hazırlanıyor…" while `GET narrative` waits.

**`OptionView`**: `option_id, label, kind, category_key, category_label, fx`;
`returns`: `{3m, 6m, 1y, real_1y}` each `{value, evidence_id}` or null;
`category_avg`: the same periods, the mean over the category; `rank`:
`{position, of}` by the 1-year return; `stars` 1–5 (top 10 % = 5, next
22.5 % = 4, middle 35 % = 3, next 22.5 % = 2, bottom 10 % = 1; by position
`p` of `n`: the share `(p − 1) / n`); `better_than_pct` (share of the
category with a lower 1-year return, whole percent); `risk`: `{level,
evidence_id}` or null; `access`: `{days, label, evidence_id}`; `match` 0–10;
`why`: the D17 lines; `warnings` and `data_notes` that name this option;
`selected` (after approval) and `rm_note`.

The category of rank, stars and averages = the `group_key`, over **all**
funds of the run in that group (ranked and eliminated) that have the value.
So the rank does not depend on the client. A fund without a 1-year return has
no rank and no stars ("sıralama yok"). Rank, stars, `better_than_pct` and
`category_avg` are for funds only; they are null for a deposit and a time
deposit.

Sample responses: the lead writes `tests/contracts/fixtures/api/*.json` (P01
ready and approved, P02, a `needs_rm_input` run, a test run, a narrative TR
and EN, glossary, one evidence item) with `python -m rmprep.api.samples`, from
`RealBackend` on the frozen eval snapshot, so the web shows real funds (needs
`data/`, main checkout only). A test checks that the samples have the keys of
the live API output (FakeBackend). They are the contract between the API and
the web app.

### 7. Web app (worker `ing-web`)

- `web/`: Vite + React + TypeScript + Tailwind; font Inter (`@fontsource/inter`,
  no network at run time); no other UI library unless the lead agrees.
- `web/src/api/`: a typed client and the types of section 6 (hand-written
  from the samples). `npm run dev:mock` serves the samples from
  `../tests/contracts/fixtures/api/` (no Python needed); `npm run dev` uses the
  API through the Vite proxy.
- Screens: `Dashboard` (client card, talking points, top 3 + "Karşılaştırma",
  categories, right panel, approval bar), `FundCard`, `PersonaPanel` (side
  panel "Düzenle"), `MeetingText`, `EvidencePopup`, `PrintCard` (route
  `/print/:runId`, print CSS).
- Top bar: ING mark, persona pick, "Veri" menu (snapshot pick, one check box
  per source; a change makes a new run), TR / EN (labels and meeting text).
- Labels in one dictionary, every key in TR and EN; engine texts stay Turkish
  (as in docs/ui.md section 4); citations as in docs/ui.md section 4.
- States: loading (skeletons); `needs_rm_input` (the questions take the place
  of the options); test run (banner; approval disabled with the reason);
  meeting text running ("Metin hazırlanıyor…"); template text (banner
  "otomatik metin doğrulanamadı"); API error (a message with the API's text,
  and "Tekrar dene").
- Colors and visual rules: "Decisions" above. Color is never the only
  signal: the risk bar has the text "1 / 7", the match ring has its number.
- The worker edits only `web/`; the guard hook gets module `web` with that
  one folder (lead).

### 8. Error handling

- API: a `ValueError` from the backend → 422 `{"detail": <message>}`; an
  unknown run or evidence id → 404; anything else → 500 with a short message
  (no keys, no stack trace in the response).
- Runs live in memory (RealBackend). After a server restart a run id gives
  404; the web app then makes the run again with the same inputs. The engine
  is deterministic, so the run id is the same. Approved runs, cards and
  narratives are on disk already.
- The narrator never fails to the screen: an API error, a validator failure
  or the cost limit gives the template text and its banner (existing
  behavior). `GET narrative` waits at most 120 s, then answers 504; the web
  shows "Tekrar dene".
- The server binds `127.0.0.1` only.

### 9. Tests

- Contract (lead): v1.3 round trip; v1.2 JSON without the new fields loads;
  the new checks reject bad values.
- API (lead, `tests/api/`): FastAPI `TestClient` on the FakeBackend fixtures,
  no network, no `data/`: every endpoint, the 404 / 422 paths, the view-model
  math (rank, the star split, match ring, access labels, category average),
  the samples equal the output. One smoke test on RealBackend, skipped
  without `data/evidence.duckdb`.
- Decision D16–D18 and narrator N9: in their modules, test-first as before.
- Web (ing-web): Vitest + Testing Library on the samples: top 3 and
  categories (at most 3 funds); stars and the risk bar colors; approval sends
  the selected chips; a test run cannot be approved; the meeting text puts
  each section in its place; every label in TR and EN. `npm test` and
  `npm run build` pass; the lead runs both at each merge (pytest does not run
  npm).
- The user reviews the screens; the eval runs again after N9.

## Open (for later)

- Eval E7 (pairwise judge + UI context for the judge): not yet answered.
- The gold account (waits for the EVDS gold series verification).
- More Jury-Challenge scenarios (after the MVP).
- Remove Streamlit after parity (move `card` and `glossary` out of `ui/`).

## Later / optional (after the MVP)

- **RM research assistant with Claude Managed Agents** (Anthropic beta API:
  a hosted agent loop in a cloud or self-hosted sandbox with web search,
  sessions and scheduled runs). Noted by the user 2026-10-11 as an optional
  feature for later. Idea: the RM asks, e.g., "what is new about this fund
  company?", the agent searches and answers with citations. Conditions: a
  clearly separate, labeled panel; every claim cited; it never changes the
  scores, the rules or the meeting text; no automated access to sources that
  forbid it (KAP blocks bots, rule 8); unverifiable web content marked as such
  (rule 3); its own cost limit; tested before any demo (beta product). Not
  used for ingest, the narrator or the eval: those stay deterministic or
  single-call by design.
