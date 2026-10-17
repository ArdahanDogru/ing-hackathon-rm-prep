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

**Built 2026-10-11** (plan tasks L1-L8, D16-D18, N9-N9c, W1-W6, E8): start with
`cd web; npm ci; npm run build`, then `python -m rmprep serve` →
http://127.0.0.1:8600. Full eval `data/eval/20261011-130016-full` (prompt n6):
rule checks 100 %, narrator validator 100 %, no forbidden phrase. Waits for the
user's review on screen.

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

## Redesign v2 (approved by the user 2026-10-11, evening)

The first build was "too crowded" (the user's review, 2026-10-11). A research
pass on the pre-meeting screens of top firms and an NN/G / Carbon review gave
the new design; the user chose it with mockups. Final mockup:
`docs/web-ui/mockups/redesign-v4.html` (tab 3 "B4"; tabs 4 and 5 option "A";
tabs 1 and 2 hold the research with sources; the firm images load from the
vendors' sites, two of them only from a local copy). Local copies of all 21
research screenshots: `docs/web-ui/research-imgs/` (`sf_` Salesforce, `ms_`
Microsoft, `jump_` Jump, `zocks_` Zocks, `wb_` Wealthbox). **Where this section and
the screen sections above differ, this section wins.**

### Research behind it (sources in the mockup, tabs 1 and 2)

- Salesforce Agentforce Meeting Concierge (the user's favourite), Microsoft
  365 Copilot meeting prep, Microsoft unified customer profile, Salesforce
  FSC household, Jump, Zocks, Wealthbox; Morgan Stanley / UBS / J.P. Morgan
  by description only. Patterns: a short brief first; at most 3 highlights or
  agenda points; the system proposes, the person decides, one primary button;
  a source next to each fact; a readiness counter; the meeting lifecycle as
  navigation; counts in titles and "show all"; details behind one control.
- NN/G: about 57 % of viewing time is above the fold; a table beats cards for
  comparing a few options; at most 2 levels of disclosure. Carbon: do not cut
  long names, give the full name on hover.
- SPK suitability (yerindelik): advice only with current client information,
  so "Teyit edin" is a step before approval.

### Dashboard ("B4")

Top to bottom, one column of 1 200–1 400 px, 24 px between sections:

1. **Top bar**: ING mark, "Görüşme hazırlığı", persona pick, "Veri ▾"
   (snapshot, sources), TR / EN.
2. **Lifecycle tabs**: `1 · Hazırlık` | `2 · Görüşme metni` (the second is
   active only after approval).
3. **Brief card** (full width):
   - left: name and age (22 px); one profile line: risk profile with the fund
     risk ceiling ("Muhafazakâr (fon riski en fazla 2 / 7)"), horizon,
     liquidity, income need, the constraint in orange; **the brief**
     (17 px, 1–2 sentences, LLM; see "LLM brief" below; until it is ready and
     as its fallback: the persona's `durum` and `yatirim_amaci`); a small line
     "Veri: <snapshot date> · motor · Kaynaklar (2) · Profili düzenle"
     ("Kaynaklar" opens the persona file and the RM note; "Profili düzenle"
     opens the side panel of the test run);
   - right: **"Hazırlık n / 3"** with a thin bar and the steps "✓ Profil
     okundu · ✓ Öneriler hazır · ○ k konu teyit edilecek" (step 2 done when
     the state is `ready`; step 3 done when every "Teyit edin" item is ticked).
4. **Two columns, 1 : 2**:
   - **"Gündem · müşteriyle konuşulacaklar"**: the talking points (at most 3)
     as checkable agenda items, each: bold title with the figure, one line,
     a small source number (opens its evidence); under a line, **"Teyit edin"**
     items (checkbox; a question item also has "Yanıtla").
   - **"Öneriler · mevduatla karşılaştırma"** with a view switch
     **Tablo | Kartlar** (default **Kartlar** since 2026-10-13, the user's
     choice; before: Tablo; the browser remembers the choice):
     - *Tablo*: columns = the 3 recommendations, then the deposit as a grey
       "Karşılaştırma" column; rows: Uygunluk (match), 1 yıl getiri, Reel
       (TÜFE, stopaj), SPK risk, Paraya erişim, Kategorisinde (stars +
       rank), Neden bu müşteri (the priorities of the `why` lines). Values
       left-aligned, tabular figures; a small **"K"** mark next to each value
       with evidence opens the evidence pop-up; the column heading = short
       name (issuer small, fund type bold); the full official name and the
       fund code on hover.
     - *Kartlar*: the 3 recommendations as A-style cards side by side (match
       ring, return in green with "K", risk bar, stars + rank, the "neden"
       line), the deposit as a thin dashed "Karşılaştırma" row under them.
     - A click on a column or a card opens the **fund card** (side panel).
5. **"Detaylar"**: one line with counts — Kategoriler · Varsayımlar · Veri
   notları · Elenen · RM notu — that opens one panel (tabs or sections) with
   the categories (each opens at most 3 funds), assumptions, data notes,
   eliminated options by rule, and the RM-only warnings.
6. **Approval bar** (sticky): "Görüşmede konuşulacak" with chips (✕),
   "k konu teyit edilmedi" while items are open (a reminder, not a block),
   "Reddet", **"Onayla ve metni hazırla"** (the only filled button).

Short names (all screens): issuer = the words up to and including
"PORTFÖY", in title case; fund type = the rest, without "FONU", in title case
with Turkish rules ("PARA PİYASASI (TL)" → "Para Piyasası (TL)"); fixed
abbreviations "KISA VADELİ" → "KV", "BORÇLANMA ARAÇLARI" → "Borçlanma". The
API gives them (`issuer`, `short_label`); the full `label` stays for hover,
the fund card, the evidence pop-up and the meeting text.

### Fund card ("A", side panel)

A drawer on the right (about 520 px); the dashboard stays visible behind it.
Header: issuer, short name (22 px), the full official name and code small;
three tiles: Uygunluk, Kategoride (rank + stars), Paraya erişim; fund vs
category bars per period (3 ay, 6 ay, 1 yıl, Reel) with the delta pill;
"Bu müşteri için neden?" (the `why` lines); SPK risk bar; "Seçime ekle" /
"Seçimden çıkar" (the only filled button); "Kaynak: TEFAS, <date> · Kanıtları
göster (n)".

### Meeting text ("A", document)

One calm document column (17–18 px type, about 70 characters a line) and a
narrow right column:

- **Document**: status line ("Taslak · onayınızı bekliyor · <model> ·
  kontrol geçti" or "şablon metin"); title "Görüşme hazırlığı — <name>";
  sections with small capital headings: **Görüşmenin amacı** (`ozet`),
  **Konuşulacaklar** (`talking_points`, titles bold), **Söyleyebileceğiniz**
  (`teklif_metni` as a quote block), **Öneriler** (per selected option: short
  name, return · risk · access, need tags as chips, its sentences; the
  per-option note field), **Dikkat** (`dikkat`); collapsed lines "Diğer
  seçenekler ›", "Sorulacak sorular (n) ›", "Varsayımlar (n) ›". Each
  sentence with evidence gets a small source number.
- **Right column**: "Notlarım" (autosave), "RM notu · yalnızca sizin için"
  (RM-only warnings), "Kaynaklar" (the numbered sources: client file, TEFAS /
  EVDS rows with date), "Terimler", the card download (PDF, Markdown), and the
  button **"Metni onayla"** (at the top of the right column; editing is per
  block, see "Section-by-section editing").
- (Before 2026-10-12:) An edited text shows as formatted Markdown with "Düzenlenmiş metin" (as
  before); the cards and source numbers show for an unedited draft.

### LLM brief (approved by the user 2026-10-12)

The brief sentence of the dashboard is written by an LLM; the plain sentence
(`durum` + `yatirim_amaci`) is its fallback and shows first.

- **Content**: 1–2 sentences for the RM (not for the client): who the client
  is, what they want, what this meeting should do; built from the same facts
  pack as the meeting text (persona, `dosyadaki_not`, the decision talking
  points, the top 3, client-audience warnings only). Formal Turkish (EN with
  the language switch), at most 280 characters.
- **Model**: Claude Haiku 5.5 (`claude-haiku-5-5`, config
  `narrator.brief.model`), structured output `{text, cite}`; about $0.003
  per brief; counts against the same daily cost limit.
- **When**: the API starts it in the background when a run is made (not for
  `needs_rm_input`); `GET /api/runs/{id}/brief?lang=TR` returns the brief or
  `{"status": "running"}`; the web polls it a few times, then keeps the plain
  sentence. Cached per (run_id, lang, prompt version, model) under
  `data/narratives/`; the same run makes no second call.
- **Guard**: the narrator validator rules that apply (numbers in the facts,
  no forbidden phrase, no rejected option, the label rule of N9c, no RM-only
  fact, no pointer to a screen section). A failure or an API error → the plain
  sentence, no retry (the brief is not worth a second call).
- **Display**: the sentence with a small "AI özeti" label and the model in the
  tooltip; "Kaynaklar (n)" lists what it cites. The brief never goes into the
  card or the meeting text.
- **Contract v1.4 (additive)**: `NarrativeBrief(run_id, lang, text, source
  "llm" | "template", model, prompt_version, checks, created_at, cost_usd,
  cite)`; `Backend.brief(run_id, lang="TR") -> NarrativeBrief` (RealBackend:
  starts or waits for the background job; FakeBackend: template).
- **Milestones**: lead L11 (contract v1.4, API endpoint, background start in
  `RealBackend.decide`), narrator **N10** (prompt, brief builder, validator
  subset, cache, tests with a fake LLM, one live smoke call), web (the
  polling and the label, in the redesign milestones).

### Section-by-section editing of the meeting text (approved by the user 2026-10-12)

Replaces the "Düzenle" of the whole text as Markdown.

- **Blocks**: `ozet`, `teklif_metni`, `dikkat`, `alternatifler`, `sorular`,
  `varsayimlar` (one block each); `talking_points:<i>` (one per point);
  `oneriler:<option_id>` (one per selected option). Block ids come from the
  narrator (`narrator.blocks.block_ids(draft)`).
- **Editing**: a pencil on each block opens only that block as plain text
  ("Kaydet", "Vazgeç"); the other blocks keep their layout. An edited block
  shows "düzenlendi" and "Orijinale dön" (restores the LLM text).
- **Check**: after "Kaydet" the narrator validator checks the edited block
  alone. Findings of kind `phrase`, `option`, `internal`, `label` (forbidden
  phrase, a rejected or outside option, an RM-only fact, a wrong ING rate
  label) **block** "Metni onayla" until the RM corrects them; findings of kind
  `number` (a number not in the facts) only **warn**. Each finding shows next
  to its block.
- **Saving**: each saved block is stored on the server at once
  (`data/narratives/<run_id>-<lang>-edits.json`, restored after a restart).
  "Metni onayla" approves the text with the edits (the server composes the
  Markdown; `approve_narrative` refuses while a blocking finding is open).
  The card and the PDF use the approved text, as before.
- **Contract v1.5 (additive)**: `NarrativeDraft.rm_edits: Mapping[str, str]`
  (block id → edited text, default empty), `NarrativeDraft.edit_checks:
  Mapping[str, tuple[str, ...]]` (block id → findings, each "kind: message"),
  `BLOCKING_CHECK_KINDS = ("phrase", "option", "internal", "label")`;
  `Backend.edit_narrative(run_id, lang, block_id, text: str | None) ->
  NarrativeDraft` (None restores the original).
- **Milestones**: lead L15 (contract v1.5, RealBackend / FakeBackend
  `edit_narrative`, store and restore, approval guard, API `PUT
  /api/runs/{id}/narrative/{lang}/blocks/{block_id}` with `{text}` or
  `{text: null}`), narrator **N11** (block ids, `check_block`, `to_markdown`
  with the edits), web **W11** (pencil, editor, findings, "Orijinale dön",
  approval disabled with the reason while a blocking finding is open).

### Decision record on screen (W12, 2026-10-12)

The "Kanıt" pop-up shows the fetch time (`fetched_at`, Europe/Istanbul) next to
the date of the value (`as_of`). The meeting text view shows "Onaylandı:
<time>" from `NarrativeDraft.approved_at`; the dashboard shows the RM decision
time from `DecisionResult.rm_decided_at` (contract v1.7) in the approval bar
after approval.

### Model allocation view (W13, 2026-10-13)

"Öneriler" switch: Tablo | Kartlar | **Dağılım** (docs/decision.md section 11):
one row per asset class — band bar (low–high %), source ("*" = our inference,
tooltip), the best option (short name, real 1-year return, SPK risk; a click
opens the fund card) or the note; the holding hints above the rows. No current
shares, no amounts. The current-portfolio input with a gap analysis is future
work.

### Data freshness and refresh (W14, 2026-10-14)

Approved by the user 2026-10-14: a daily ingest (Task Scheduler, 07:30, "run
as soon as possible after a missed start"; `scripts/schedule_ingest.ps1`) and
a check when the app opens. Ingest lock: docs/ingest.md I6.

- **API (lead):** `GET /api/ingest` → `{latest_snapshot, created_at (ISO,
  Europe/Istanbul), age_hours, stale (age_hours >= 24), running, started_at,
  finished_at, error}`. `POST /api/ingest` → starts the ingest in a background
  thread (one at a time) and returns 202 with the status; 409 when an ingest
  already runs (this server or another process, e.g. the scheduled job).
- **Web (`ing-web`):** a line above the dashboard, only in these states:
  - stale, not running: "Veri {n} gün önce alındı ({date})." and the button
    **"Veriyi yenile"** with the hint "yaklaşık 15 dakika sürer";
  - running: "Veri alınıyor… (başladı {time})"; the page asks `GET
    /api/ingest` every 15 s;
  - finished, a newer snapshot exists than the one on screen: "Yeni veri hazır
    ({date})." and the button **"Yeni veriyle aç"**: it reloads the snapshot
    list and selects the newest. No automatic switch: a run on screen does not
    change under the RM;
  - error: "Veri alınamadı: {error}" and "Tekrar dene".
  Fresh data and no job: no line (the "Veri" menu shows the snapshot date).
  EN labels as well. The newest snapshot stays the default when the app opens.
- As built (2026-10-14): web `web@279eb6f` (a 404 from GET gives no line; a
  409 from POST reads GET again). API: `src/rmprep/api/ingest_job.py`
  `IngestControl`, passed to `create_app(..., ingest=)` by `serve.py`; it is not
  part of the frozen Backend protocol, so tests and the FakeBackend have no
  `/api/ingest` (404). A refresh from the web app also writes start, exit and
  error lines to `data/logs/ingest.log`.

### Source numbers, deletable blocks, market note, product kinds (W15, 2026-10-14)

Approved by the user 2026-10-14.

1. **Source numbers in the meeting text** (bug: they were `#src-n` links that
   only scrolled the page): a click opens the evidence pop-up of the
   sentence's first evidence id and gives the matching "Kaynaklar" entry a short
   highlight (2 s) without scrolling the page; keyboard: Enter/Space. The
   dashboard agenda numbers keep their behaviour.
2. **Deleting** (narrator N14): each block gets "Sil" next to the pencil; each
   section with several blocks ("Konuşulacaklar", "Öneriler") gets "Bölümü
   sil" (one `PUT` with `{text: ""}` per block). A deleted block shows as a
   thin line "Silindi · Geri al" (`{text: null}` restores it). Saving an empty
   text in the editor = delete. The approved text and the print card leave
   deleted blocks out. The disclaimer is added by the server; the screen notes
   it under the text ("Yatırım tavsiyesi değildir notu her zaman eklenir").
3. **Market note** (API, lead): `RunView.market_note` = a list of `{key,
   label, value, unit, as_of, evidence_id}` for the policy rate, USD/TRY and
   the TCMB funding cost (EVDS; missing ones left out). The dashboard shows a
   small card "Piyasa notu · TCMB EVDS" (value, date, "K" mark) under the
   brief; the meeting text has the deletable block `piyasa_notu` (N14).
4. **Product kinds** (decision D26): a small badge "BYF" or "Pay" on cards,
   table columns and the fund card for `etf` and `stock` options; "Paraya
   erişim" for both: "2 iş günü (borsa takası)". Samples for both kinds.

### Explainability: "Neden bu öneri?" (W16, 2026-10-14; PR #1)

Approved by the user 2026-10-14 (canvas "Explainability Mockup", board 2). The
fund card replaces the `why` lines with the engine's own reasoning; every value
comes from `DecisionResult` (no new decision logic):

- **Rank:** "{of} aday içinde {n}. sıra" over all scored options (score, then
  option id).
- **Chips:** stability (only for a recommended option; ≥ 0.8 kararlı, ≥ 0.5
  kısmen kararlı, else kararsız, after `warnings.low_stability_below`) and data
  confidence (≥ 0.8 yüksek, ≥ 0.6 orta, else düşük). UI thresholds only.
  How both are measured: docs/kararlilik-veri-guveni.md.
- **"Puan nasıl oluştu?":** one bar per `score_parts` criterion, highest first,
  then the penalties in red, largest first; the `reasons` text under each; the
  total. Bars are scaled to the largest absolute part. A criterion carries a
  tag for each client priority that boosts it.
- **"Geçtiği kesin kurallar":** the passed `constraints`, each with its
  evidence chips (they open the Kanıt pop-up).
- **"En yakın alternatif":** for a recommended option, the highest-scoring
  non-recommended option of the same group (`fund_kind`, else kind; as
  `grouping.group_key`), its score, and the criterion with the largest part
  difference with the alternative's reason.
- **API:** `RunView.priority_criteria` = criterion → the persona priorities (as
  written) whose `priorities` entry is `boost:<criterion>`
  (`api/views.py priority_criteria`). The samples got the key without a rerun
  (the rerun needs the narrator); the value is the same function's output.
- The `why` lines stay in the API; `FundCard` shows them when no explanation is
  given.
- The "Paraya erişim" tile text is 16 px (the 24 px of the other tiles broke
  "Vade sonunda (32 gün)" over lines).

### Explainability: decision pipeline on the dashboard (W17, 2026-10-14; PR #1)

Approved by the user 2026-10-14 (canvas "Explainability Mockup", board 1). A
section between the client card and Gündem / Öneriler, open by default (since
2026-10-15 at the lead's request; it was closed before). Its summary line
closes and reopens it: "Bu öneriler nasıl seçildi? {universe} seçenek → {rejected} elendi →
{scored} puanlandı → {picks} öneri". Open, five steps (every value from the
RunView):

1. **Müşteri profili:** `risk_ceiling`, risk profile and horizon, and the
   persona levels that set the income, principal and liquidity weights.
2. **Ürün evreni:** scored + rejected options.
3. **Kesin kurallar:** `rejected_by_rule` counts as bars (a fund can fail
   several rules).
4. **Puanlama:** the scored candidates.
5. **Öneri:** the recommended options with score, overall rank and rank in
   their group (shown when it differs); a click opens the fund card.

Each step links to the matching DetailsPanel tab (Varsayımlar, Veri notları,
Elenen, Kategoriler): `DetailsPanel` takes `request = {tab, n}` and opens on
that tab. Below the steps: the lowest stability of the recommended options
with the W16 level. Gündem, the options and the DetailsPanel are unchanged.

### Current and target split (W18, 2026-10-14)

Approved by the user 2026-10-14. Spec:
`docs/superpowers/specs/2026-10-14-portfolio-projection-design.md` sections 8–9;
plan `docs/superpowers/plans/2026-10-14-portfolio-projection.md` Task 5.

**API (lead, Task 4):**

- `RunView.allocation[i]` gets `current`, `current_low`, `current_high`,
  `current_source` ("" | `rm` | `rm_confirmed` | `persona_text` | `profile` |
  `national`), `current_ref`, `gap` (points; + under the band, − over it, 0
  inside, null for `dengeli`) and `active` (counts in the ranking).
- `RunView.holdings = {status: "estimate" | "persona_text" | "rm" |
  "rm_confirmed", sources: [{id, label, url, date}]}`.
- `RunView.effective_weights` = criterion → weight used for this client.
- `POST /api/runs/{id}/holdings` with `{"shares": {class: %} | null,
  "origin": "rm" | "rm_confirmed"}` → the new RunView (a new run id); 422 with
  `detail` on a bad input (all five classes, each 0–100, total 100 ± 0.5).

**Card "Mevcut ve hedef dağılım"** (replaces "Model dağılım"):

- One row per class: the model band as a light bar, the current value as a
  marker with its range, the gap as text ("−25 puan" / "bandın içinde").
- A badge per row: "RM", "RM onaylı", "persona metni" or "tahmini senaryo"
  (grey; the source label, URL and date in a tooltip).
- While `holdings.status` is `estimate`: the banner "Portföy dağılımı
  bilinmiyor; aşağıdaki değerler tahmini senaryodur ve sıralamayı etkilemez."
- Buttons "Tahmini onayla" (`origin: rm_confirmed`, the current points),
  "Düzenle" (five number inputs, the running total, "Kaydet" only at 100 ±
  0.5), "Sıfırla" (`shares: null`). A 422 shows the server `detail`.
- The fund card ("Neden bu öneri?", W16) shows the criterion "Portföy açığı"
  like the others.

### No "Metni onayla"; the card prints the current text (W19, 2026-10-15)

Approved by the user 2026-10-15 ("the button is just detrimental").

- The Görüşme metni screen has no "Metni onayla" button. The "Kart" box (PDF,
  .md, footer) moves to the top of the aside.
- The card prints the current text with the RM's edits and deletions (API
  `_current_text`: `to_markdown(apply_edits(draft))`); an older approved text
  is still used when it exists.
- The safety check moves to the card: while a rule finding of a kind in
  `BLOCKING_CHECK_KINDS` is open, `GET card.md` gives 422 "Kural bulgusu açık:
  kartı indirmeden önce düzeltin." and the web disables both card links with
  that reason; a card saved by the notes or the decision approval leaves the
  text out. Number findings only warn.
- The RM approval of the recommendation ("Onayla ve metni hazırla") stays, so
  the record still shows the RM's approval (brief, traceability).

### RM action log (L1, 2026-10-15)

Approved by the user 2026-10-15 (spec
`docs/superpowers/specs/2026-10-15-rm-action-log-design.md`). The API writes every
decision and edit of the RM as one JSON line to
`data/logs/rm-actions/<YYYY-MM-DD>.jsonl` (server side; no web change; nothing to
an LLM or an outside service): `run_opened`, `question_answered`, `holdings_set`,
`holdings_reset`, `decision_approved` / `decision_rejected` (the engine's top 3,
the agent's top 3 and state, the RM's choice, the note), `notes_saved`,
`text_block_edited` / `_deleted` / `_restored` (block, text before and after,
findings), `card_downloaded` (.md; also when refused), `research_question` (also
when refused). The PDF print is not logged (the server cannot tell it from a page
view). A failed write never changes the action. **KVKK:** the records can contain
the RM's notes and edited text; with the synthetic personas this is acceptable,
with real client data a KVKK review is required before the log is kept or used.

### Other banks' rates as context for the RM (W25, 2026-10-16)

Approved by the user 2026-10-16 ("these banks rates should be shown as context
for RM, not in score"). Data: ingest I14 (`ing_web`) and I15 (`isbank_web`,
`ziraat_web`), docs/ingest.md.

- **Not in the score.** Nothing changes in the engine, the top 3, the agent, the
  narrator, the meeting text or the downloaded card. On the screen only, for
  the RM (an ING text for the client must not say "the other bank pays more").
- Config `config/bank_context.yaml` (lead-owned; a separate file, so the
  decision config hash does not change): per option id, the `own` cell and the
  `banks` cells (label TR/EN, quantity, entity) and a `note` TR/EN; strict keys
  (`check_bank_context`). Now only `time_deposit:ing_e_vadeli`: own = the engine
  cell `32-45 gün / 99.999,99-250.000 TL`; İş Bankası campaign `32 - 35 Gün /
  100.001 - 250.000 TL`; Ziraat internet `32 - 45 gün / 100.000 - 499.999,99 TL`.
  Digital channels only (e-Vadeli is digital), so the Ziraat branch rate is out.
- API (lead, done): each option view has `bank_context`: `null`, or
  `{rows: [{label, cell, own, value, as_of, evidence_id, stale, diff_pp}], note}`.
  The first row is the own rate (`own: true`, `diff_pp: null`). `cell` = the
  entity after its first ", " with " / " between term and amount. A row without
  a usable value has `value: null`, `evidence_id: ""` (the web shows "veri
  yok"). `diff_pp` = the bank's rate − the own rate in percentage points (null
  when one side is missing). `stale` = the row has the ingest `stale` flag. The
  evidence ids open with the existing `GET /api/evidence/{snapshot}/{id}`.
- Web (ing-web): in the card and the drawer of the option (FundCard /
  FundDrawer; any option with a non-null `bank_context`), a small block
  "Diğer bankalar" / "Other banks", with the subtitle "bağlam — puana dahil
  değil" / "context — not in the score". One line per row: label, cell (small,
  muted), rate (`34,50 %`, Turkish format) with the K mark of the evidence,
  the date (`16.10.2026`), and for the bank rows the difference as a signed
  points value ("+2,50 puan" / "−3,50 puan", Turkish minus sign; neutral
  color, not green/red: a higher rate elsewhere is not "good" or "bad" for the
  RM). The own row is bold. A missing row shows "veri yok"; a stale row shows
  the date with the existing stale style. The note text under the block. TR
  and EN labels. Not in the options table, the compare view or the card PDF.
- Tests: API `tests/api/test_bank_context.py` (rows, differences, missing,
  stale, strict config, only the configured option, the ranking unchanged).
  Web: the block with the three rows, a missing row, the stale style, the
  signed difference format, no block when `bank_context` is null, TR and EN.
- **W25b (the user, 2026-10-16): also in the market note.** On the real data
  of 2026-10-16 the e-Vadeli option is not shown for any persona (rank 73–382:
  not in the top 3, the categories or the Dağılım view), so the drawer block is
  never seen. The RunView now has `bank_context`: a list (empty without the
  config) of `{option_id, title, rows, note}`, one entry per configured option,
  with the same rows as the option field; config `title` TR/EN (e.g. "Vadeli
  mevduat, ~32 gün, 100–250 bin TL"). Web: one line in the "Piyasa notu" panel
  (screen 1, always on screen): the title, then each row "label %rate" with its
  K mark and date ("veri yok" when missing; the own row bold; the bank rows
  with the signed points difference in a neutral color), and the note text
  small under the line ("bağlam, puana dahil değil" is in the note). The
  drawer block stays.

### Reset: every client back to the first state (W27, 2026-10-17)

Approved by the user 2026-10-17 ("everything become how it was in the first
place"; scope: all clients; the user's approved P01 record goes to the archive
too).

- API (lead, `rmprep.api.reset`): `POST /api/reset` → `{archive, moved: {runs,
  texts, cards, personas, agent, research_marks}}` (personas: the W31 uploads); 409 "Ajan çalışıyor; bitince
  sıfırlayın." while an agent job runs; 404 when the server has no reset.
  - **Moved, not deleted**, to `data/reset-archive/<YYYYMMDD-HHMMSS>/`:
    `data/runs/*.json` (approvals, rejections, notes), the approved texts and
    the text edits (`data/narratives/*-approved.json`, `*-edits.json`),
    `data/cards/*`, the agent's latest decision per run (`data/agent/<run>.json`)
    and the research marks (`data/research/marks/*.json`).
  - Memory cleared: the runs and texts of the API, the backend runs (also the
    holdings runs), approved texts and edits, the agent's live decisions.
  - **Stays:** the data (snapshots, bank rates, document links), the LLM caches
    (briefs, text drafts, research results, the agent's content cache
    `<run>.n<N>.<marks>.json`: the same start again costs nothing), the RM
    action log (one `reset` record with the counts), the browser settings
    (language, view mode).
- Web (ing-web): a "Sıfırla" / "Reset" button in the top bar (next to "Veri").
  - A click opens a confirmation dialog: "Tüm müşteriler ilk hâline döner:
    onaylar ve notlar, portföy dağılımları, ajan sonuçları, araştırma
    işaretleri, metin düzenlemeleri ve kartlar. Eski kayıtlar arşive taşınır;
    veriler ve RM eylem günlüğü kalır." with "Sıfırla" and "Vazgeç" (EN text
    in the same sense).
  - On "Sıfırla": `POST /api/reset`; then remove the browser keys of the RM
    state (`localStorage` `rmprep.agenda.*` and `rmprep.confirm.*` (the "Teyit edin" checks), `sessionStorage` `rmprep.inputs.*`;
    keep `rmprep.lang` and the view mode), close any drawer or note, go to "/",
    and load the run of the selected client again (as on the first visit). A
    short success line: "Sıfırlandı. Eski kayıtlar: <archive>".
  - 409: show the server text and keep the state. Other errors: the error box.
- Tests: API (the files moved and the ones that stay, memory cleared, the agent
  content cache kept, 409 while running, the `reset` log record, 404 without
  reset); web (the dialog, the cancel, the request, the storage keys removed and
  kept, the reload of the run, the 409 text, TR and EN).

### An edited profile can be approved (W30, 2026-10-17)

Approved by the user 2026-10-17 (option A). Before, an edited persona was a
what-if "test run" that could not be approved, so screen 2 (the meeting text)
was closed for it. Now:

- API (lead): `POST /approval` accepts a test run. The `decision_approved` /
  `_rejected` log record adds `test_run` and `persona_changes`. The card
  (`card.md`, the print card) shows, in the client section, "Düzenlenmiş profil
  ile hazırlandı: <field>: <original> → <edited>; …" (EN "Prepared with an
  edited profile: …"). The RunView keeps `test_run` and `persona_changes` as now.
- Feedback report F1: approvals with `test_run: true` are left out of R2–R4 and
  counted in one line ("Düzenlenmiş profil onayları (dışarıda): n").
- Web (ing-web): the approval works for a test run; the banner says "Düzenlenmiş
  profil: onaylanırsa metin ve kart bu profille hazırlanır; değişiklikler kartta
  gösterilir." Screen 2 and the print card show the same "Düzenlenmiş profil
  ile hazırlandı" line with the changes (from `persona_changes`).

### Client upload (W31, 2026-10-17)

Asked by the user 2026-10-17: "a place near the client dropdown … that allows us
to upload client JSONs".

- API (lead): `POST /api/personas` `{persona: {...}}` → `{persona, replaced}`;
  `GET /api/personas/uploaded` → the uploaded ids. Checks (422 with a Turkish
  text): the fields and types of `persona_schema.json` (`Persona.from_dict`:
  no missing, no unknown field), at most 64 KB, `persona_id` of letters, digits,
  `-` and `_` (1–32), not the id of a built-in client (P01–P05). The id of an
  earlier upload replaces it (`replaced: true`). Stored in
  `data/personas/<id>.json` (gitignored; the original `../p0*.json` files are
  never changed); `GET /api/personas` lists the built-in clients, then the
  uploaded ones. RM action log: `persona_uploaded {persona_id, replaced}`. The
  reset (W27) moves the uploads to the archive too.
- Web (ing-web): an "Yükle" / "Upload" button next to the client dropdown → a
  dialog with a file picker (`.json`), the KVKK warning "Gerçek müşteri verisi
  yüklemeyin. Profil bu bilgisayarda saklanır; AI özeti, metin ve ajan için
  Anthropic'e gönderilir." and "Yükle" / "Vazgeç". The web reads the file and
  posts its JSON; a parse error or a 422 shows the text in the dialog. After
  success: reload the list, select the new client, close the dialog. The
  dropdown marks uploaded clients with "(yüklendi)" / "(uploaded)".
- Tests: API (a valid upload, each refusal, replace, the list order, the log,
  the reset archive); web (the dialog, the warning, a parse error, a 422 text,
  the success path and the selection, the mark in the dropdown, TR and EN).

### The earlier research list stays while the agent runs again (W29, 2026-10-17)

Asked by the user 2026-10-17, after the fix "a new run follows the agent"
(docs/agent.md): during the agent's new run (about 30 s) the research panel
showed only the new top 3, so the research seemed gone again.

- API (lead, done): `GET /api/runs/{id}/research` has an extra key `previous:
  {run_id, products}` only while the agent runs on a run that followed an earlier
  run (`followed` in the app, filled by `_follow_agent`, cleared by the reset).
  `products` = the earlier run's shown products (its N candidates) that are not
  in this run's list, with the same shape as `products` (findings, news, marks).
  The key is absent otherwise (also when the agent is done: the new list then
  has the new N candidates).
- Web (ing-web): under the run's products, a muted section "Önceki dağılıma göre
  — ajan yeniden çalışıyor" / "From the earlier split — the agent is running
  again", with those products in the normal product form (bullets, news, marks,
  code badges), visibly muted. Poll the research while the agent runs (as now
  after an agent start), so the section goes away when the agent is done and
  the new candidates appear. Marks on these bullets work as everywhere (a mark
  belongs to the finding and the day).
- Tests: API `test_w29_previous_list_while_the_agent_runs_again`; web (the
  section with the previous products, its label, gone when `previous` is absent,
  TR and EN).

### Product codes everywhere a product is a title (W28, 2026-10-17)

Asked by the user 2026-10-17: "the abbreviations/codes of the funds, stocks and
products … should be included everywhere where the product is given as a title
or a sub-title".

- The code: for an option of kind `fund`, `etf` or `stock`, the part of the
  option id after ":" (`fund:PPN` → PPN; the TEFAS code or the BIST ticker).
  ING deposit options (`deposit`, `time_deposit`) have no code: nothing is shown.
  One helper in each layer: web `productCode(optionId)`, Python
  `rmprep.api.names.product_code(option_id)`.
- Form: in a title or a heading, a small code badge before the name (monospace,
  bold, muted border, e.g. `PPN` Para Piyasası (TL)); in running text, chips and
  short lists: "PPN · Nurol · Para Piyasası (TL)". The code is never translated.
- Where (web, ing-web; every place that shows a product name as a title or a
  sub-title): the top-3 cards and the agent's picks, the fund card and the drawer
  title (the code moves from the sub-title into the title badge), the options
  table and compare headers, the categories, the Dağılım rows, the agenda, the
  "Görüşmede konuşulacak" chips of the approval bar, the detail notes, the
  research panel product headers, the agent panel (candidates and dropped
  options), the meeting-text screen lists, the print card. Not inside the
  narrator's prose (an LLM text; a later prompt change if wanted).
- Card (lead, `rmprep.ui.card`): every product heading and list item with
  "PPN · <name>".
- Tests: web (the badge in each place above for a fund, an ETF and a stock; no
  badge for the two ING deposits; the chip text); Python (the helper, the card
  lines).

### Fund documents: links to the manager's own site (W26, 2026-10-16)

Approved by the user 2026-10-16 (step 1 of the KAP to-do). The data: ingest I16
(`rmprep.ingest.fund_docs`, on demand, links only). Not in the score, the agent,
the narrator, the meeting text or the card.

- API (lead): `GET /api/runs/{run_id}/options/{option_id}/documents` for an
  option of kind `fund` or `etf` (other kinds: 422). The fund code is the part
  of the option id after ":"; the issuer comes from `short_name(label)`.
  Sync (FastAPI runs it in the thread pool); at most 3 page GETs, 2 s apart,
  so up to about 6 s on a cold cache. Answer:
  `{status, manager_label, verdict, docs: [{kind, label, url, date}], page_url,
  checked_at, reason}` with `status` `ok` | `not_found` | `not_covered` |
  `failed` (I16). Never 500 for a site problem: that is `failed` with a reason.
  `serve.py` builds it from `config/fund_docs.yaml` (a root without the file:
  the route answers `not_covered`).
- Web (ing-web): a "Belgeler" / "Documents" block in the FundDrawer of a fund
  or ETF, loaded when the drawer opens (not on the card list):
  - while it loads: "Belgeler aranıyor…" / "Looking for the documents…";
  - `ok`: one link per document, "İzahname · 04.02.2025" and "Yatırımcı bilgi
    formu · 13.03.2026" (no date part when `date` is null), opened in a new tab
    (`target="_blank" rel="noopener noreferrer"`), with an external-link mark;
    under them, small and muted: "Kaynak: <manager site>, kontrol <dd.mm.yyyy>"
    ("Source: …, checked …"); one kind missing → only the other link;
  - `not_found`: "Kurucunun sayfasında belge bağlantısı bulunamadı." and a link
    to `page_url` when it is not empty;
  - `not_covered`: the `reason` text (e.g. "İş Portföy: robots.txt belge
    yolunu engelliyor; belgeler KAP'ta.");
  - `failed`: "Belgeler şu an alınamadı." and a "Tekrar dene" button (a new
    request);
  - no link to KAP or to any other site is made by the web.
- Tests: API (a fake `find_documents`, the 422 for other kinds, the issuer and
  code passed, the answer shape); web (the four states, the new-tab link
  attributes, the date and no-date labels, the retry, TR and EN; the samples
  of `web/src/test` or the mock).

### Not in this redesign (later, with data)

Life events and client goals (Microsoft, Salesforce): the personas have no
such data. A "Takip" (follow-up) lifecycle step: no follow-up feature yet.

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

(Superseded 2026-10-12 by "Section-by-section editing" in "Redesign v2".) "Düzenle" opens the whole text as Markdown (`narrator.template.to_markdown`)
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
  single-call by design. Built 2026-10-14 with Exa instead of Managed Agents: docs/research.md.
