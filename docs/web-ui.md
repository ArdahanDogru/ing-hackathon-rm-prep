# Web UI — design (IN PROGRESS)

Status: **2026-10-11. Screen design decided with the user (brainstorming with
mockups). Technical design: sections 1 and 2 below are PROPOSED, not yet
approved — the next session starts there, then the spec review, then the
implementation plan.** Mockups: `.superpowers/brainstorm/*/content/*.html`
(git-ignored; the final versions are named below).

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

## Technical design — PROPOSED (next session: approve or change)

### 1. Architecture

1. **JSON API** `src/rmprep/api/` (FastAPI, lead-owned), a thin layer on
   `RealBackend`: personas, snapshots, start a run, answer a question,
   approve / reject, save RM notes, get / approve the meeting text (TR/EN),
   get one evidence item (pop-ups), get the card.
2. **Web app** `web/` (React + TypeScript + Tailwind), the screens above;
   new worker **`ing-web`** in its own worktree.
3. **One command**: `python -m rmprep serve` starts the API and serves the
   built web app on one address (e.g. http://localhost:8600).
- Streamlit stays as a fallback until parity, then it is removed.
- PDF card by the browser's print-to-PDF with a print layout (no new library).

### 2. Data the screens need

| Need | Source | Contract change |
|---|---|---|
| Category rank "3. / 88", stars, category average per period | API, from the evidence (all buyable funds of the category) | no |
| Match ring 0–10 | API: the option's position among this client's options × 10 | no |
| "For the client" / "for the RM only" on warnings and notes | decision engine (D16) | yes: field `audience` |
| Client-centred talking points; need tags per recommendation | narrator (N9) | yes: new section key + per-option field (contract v1.3) |
| Card as instructions to the RM; clear note names | narrator prompt (N9) | no |
| RM notes (general, per option) | existing `annotate` | no |

Proposed order: contract v1.3 + D16 + N9 first; then the API (lead) and the
web app (ing-web) in parallel against fixed sample data.

## Open (for the next session)

- Approve or change technical sections 1 and 2.
- Then: the written spec review (this file, completed), then the
  implementation plan (milestones for ing-web, the API, D16, N9).
- From earlier, still open: eval E7 (pairwise judge + UI context for the
  judge) — not yet answered; the gold account (waits for the EVDS gold series
  verification); more Jury-Challenge scenarios (after the MVP).
