# UI — design

Status: **designed 2026-10-10 (step D, the user with ing-lead).** Code:
`src/rmprep/ui/`, tests: `tests/ui/`. The worker `ing-ui` starts after decision
milestone D5, or earlier if the user asks.

Streamlit (`pip install -e ".[ui]"`), one page. The UI talks only to the
`Backend` protocol in `src/rmprep/contracts.py`. The worker builds a
`FakeBackend` on the fixtures in `tests/contracts/fixtures/`; the lead later
wires the real backend (ingest + decision) on main. Start:
`streamlit run src/rmprep/ui/app.py`.

Real backend (lead, 2026-10-10): `rmprep.backend.RealBackend(root)` (root =
the prototype folder with `config/` and `data/`; personas from `../p0*.json`).
`page.default_backend()` returns it when the environment variable `RMPREP_ROOT`
is set, else the `FakeBackend`: `$env:RMPREP_ROOT="."; streamlit run
src/rmprep/ui/app.py`. The real backend also refuses to approve a test run.

## 1. Layout

```
┌ Sidebar ─────────────┐┌ Main ─────────────────────────────────────┐┌ Olası sorunlar ─────┐
│ Persona  [P01 ▼]     ││ P01 · Emekli girişimci · Muhafazakâr      ││ ⚠ Warnings           │
│  card + [Düzenle]    ││ State READY · run R3fa… · pending         ││ ⓘ Data quality       │
│ Snapshot [newest ▼]  ││ ┌ Questions (if any) ───────────────────┐ ││ Assumptions          │
│ Sources (☑ = used)   ││ └───────────────────────────────────────┘ ││                      │
│ Language [TR|EN]     ││ [Kısa liste] [Tüm puanlananlar] [Elenenler] [Kanıt]                │
│ Çalıştırmalar (runs) ││  Karşılaştırma: ING Turuncu (pinned)      ││                      │
└──────────────────────┘│  1–3 … [Daha fazla]                       ││                      │
                        │ RM: select ☑, note, [Onayla] [Reddet]     ││                      │
                        └───────────────────────────────────────────┘└──────────────────────┘
```

Main and the right pane are `st.columns([3, 1])`.

- **Sidebar**
  - Persona pick (`list_personas`) and its card (all schema fields).
  - "Düzenle": an edit form for a test run (section 2).
  - Snapshot pick (`list_snapshots`, newest first).
  - One checkbox per source of the snapshot (from `EvidenceSet.source_status`);
    clearing one excludes that source and makes a new run.
  - Language TR | EN.
  - "Çalıştırmalar": the temporary run history (section 3).
- **Main**
  - Header: persona id, `profil`, `risk_profili`; state banner
    (`ready` / `needs_rm_input`), `run_id`, `rm_status`; test-run banner if the
    persona is edited.
  - Questions: every open question, blocking ones first (section 3).
  - Tab "Kısa liste":
    - the deposit baseline (`options[0]` if its kind is `deposit`) is pinned
      above the list as "Karşılaştırma";
    - then the options in groups by the **grouping rule, docs/decision.md
      section 4.6 (ground truth)**, from `rmprep.grouping` (`groups`,
      `visible_alternatives`); group header: the name of the key (i18n key
      `kind.<key>`, e.g. "Para Piyasası" / "Money market") and the count of
      options in the group; the head is the recommendation row (all columns
      below, expandable); "Daha fazla" per group;
    - columns: position, label, kind / `fund_kind`, FX badge, score, confidence,
      stability, ⚠ marker if a warning names the option;
    - an expanded row shows the score parts as horizontal bars (penalties
      negative) with their `reasons`, the constraints, and the evidence ids as
      links to "Kanıt".
  - Tab "Tüm puanlananlar": all options, with a `fund_kind` filter.
  - Tab "Elenenler": `rejected`, with each failed rule and reason.
  - Tab "Kanıt": the evidence view (section 5).
  - RM bar: a checkbox per shown option ("görüşmede konuşulacak"), a note,
    "Onayla" / "Reddet" (section 3).
- **Right pane "Olası sorunlar"**
  - Warnings (`code`, message, the options they name). The ⚠ marker of a row
    opens its warning here.
  - Data-quality notes.
  - Assumptions.

If `state` is `needs_rm_input`, the tabs show "Önce soruları yanıtlayın" and only
the questions, the pane and the evidence are active.

## 2. Persona edit (test run)

- "Düzenle" opens a form with all schema fields: text inputs for free text; a
  pick list for fields with known levels, with "diğer" for free text (to test
  the question path); list editors for `oncelikler` and `acik_kisitlar`; a number
  for `yas`. "Uygula" makes a new run with the edited `Persona`; "Sıfırla"
  returns to the original persona.
- An edited persona keeps its `persona_id`. The UI compares it with the original
  from `list_personas` and shows "Test: P01 değiştirildi (yaş 62 → 45)".
- A test run cannot be approved (the buttons are disabled with the reason).

## 3. The RM loop

- **Run.** One call of the engine with one set of inputs (persona, snapshot,
  excluded sources, answers) → one `DecisionResult` with its own `run_id`.
  New run on: persona pick, answer, source checkbox, persona edit, snapshot pick.
  A new run has `rm_status = pending`.
- **Answer a question.** A radio with the `choices` (text input if there are
  none) and "Uygula" → `answer_question(run_id, question_id, answer)` → a new
  result, shown at once. Answers stay while the persona stays the same (also
  across source and snapshot changes); they are cleared on a persona pick.
- **Approve / reject.** Only a `ready` result that is not a test run can be
  approved. The RM ticks the options to discuss with the client, then:
  - "Onayla" → `approve(run_id, APPROVED, note, selected_option_ids)`; at least
    one option must be selected;
  - "Reddet" → `approve(run_id, REJECTED, note)`; a note is required.
  The backend saves the result (`data/runs/<run_id>.json` in the real backend,
  in memory in the fake).
- **Summary card ("Görüşme kartı").** After approval, the card is shown and can
  be downloaded as Markdown and as HTML (print to PDF in the browser; no new
  dependency). Content: persona summary; the selected options with score,
  confidence, the main score parts and reasons; the warnings that name them;
  data-quality notes; assumptions; source citations (section 4); the RM's
  notes. The RM can add or change one general note and one note per selected
  option, also after approval → `annotate(run_id, note, option_notes)`, then the
  card is saved again (`save_card(run_id, markdown)`; real backend:
  `data/cards/<run_id>.md`). Rendering: `rmprep.ui.card.render_markdown(result,
  evidence)` and `render_html(...)`.
- **Run history ("Çalıştırmalar").** Temporary, in `st.session_state` only: the
  runs of the current persona in order, each with `run_id`, what changed from the
  previous run (e.g. "yanıt: q:doviz… = Sınırlı", "tefas hariç") and its status.
  Clicking a run shows it again. Cleared when the RM picks another persona; not
  written to disk (only approved / rejected results and cards are).

## 4. Language and citations

- UI labels in Turkish by default, English by the toggle; the labels live in one
  dictionary in `rmprep.ui.i18n` (every key in both languages).
- Engine texts (reasons, warnings, questions, assumptions) are Turkish only
  (config templates in `config/decision.yaml`); the English UI shows them as they
  are.
- In English mode the footer says the translation is not an official TCMB
  translation (EVDS terms).
- Citations, one per source the result used:
  - evds: "Kaynak: TCMB EVDS";
  - tefas / tefas_web: "Kaynak: TEFAS (Takasbank verinin doğruluğunu garanti
    etmez)";
  - manual ING rates: "ING oranları: gösterge niteliğinde, ing.com.tr, <as_of>".

## 5. Evidence view (tab "Kanıt")

One row per DataPoint: `id`, quantity, entity (+ fund name from
`EvidenceSet.entities`), value + unit, `as_of`, source, `source_url` (link),
flags as coloured badges, note. Clicking an evidence id anywhere (score part,
constraint, warning, note) opens the tab filtered to those ids; "Tümü" clears
the filter. Without a filter the tab shows the rows the result used
(`DecisionResult.evidence_ids()`), with a switch to show the whole EvidenceSet.

## 6. FakeBackend

`rmprep.ui.fake.FakeBackend(fixtures_dir)` implements `Backend`:

- `list_personas`, `list_snapshots`, `evidence` from the fixtures
  (`evidence` drops the rows of excluded sources).
- `decide(persona, snapshot_id, exclude_sources)`: the fixture result whose
  persona id matches (else the `ready` fixture), with `persona`,
  `excluded_sources` and a recomputed `run_id` put in.
- `answer_question`: copy with the answer set, `state` recomputed, new `run_id`.
- `approve`, `annotate`, `save_card`: in memory.

## 7. Milestones (worker `ing-ui`; each ends with green `pytest`)

Tests use `streamlit.testing.v1.AppTest` (no browser, no network).

| # | Milestone | Tests show |
|---|---|---|
| U1 | `FakeBackend` + page skeleton: sidebar (persona, snapshot, sources), header and state banner | the fake satisfies `Backend`; the page loads for every fixture; clearing a source makes a new run |
| U2 | "Kısa liste" (baseline, 3 → 10 → +10, parts with reasons), "Tüm puanlananlar" with filter, "Elenenler" | row counts at each step; bars add up to the score |
| U3 | "Kanıt", "Olası sorunlar", ⚠ markers, citations | an evidence id filters the right rows; every warning appears in the pane |
| U4 | RM loop: questions, approve / reject with selection, run history, persona edit | answer → new run; a test run cannot be approved; history cleared on persona pick |
| U5 | summary card (Markdown, HTML) with notes; TR / EN | the card holds the selected options, notes and citations; every label exists in TR and EN |
| U6 | "Kısa liste" grouped by `fund_kind` (section 1) | groups from the top-20 pool, ≤ 5, ordered by best score; head = best of kind; 3 alternatives then "Daha fazla"; selection and approval work on heads and alternatives; `kind.*` keys in TR and EN |
| U7 | `time_deposit` (contract v1.1): own group in "Kısa liste", kind label `kind.time_deposit` (TR "Vadeli mevduat", EN "Time deposit") in all tabs and the card | a result with a time deposit (hand-made template for the FakeBackend) shows it as a group; no fund-only field (FX badge, fund code) for it |
| U8 | use `rmprep.grouping` (docs/decision.md 4.6) in "Kısa liste" and for the kind filter; remove `views.kind_groups`, `kind_key`, `KindGroup` and the local constants | page output unchanged; tests import the shared rule |
| U10 | (after D12; the user's request 2026-10-10) above the short list, a visible line per hard rule with its count, e.g. "189 fon alıma kapalı (TEFAS'ta işlem görmüyor veya alıma kapalı)" / "189 funds not buyable", and "12 fon risk tavanının üstünde"; clicking it opens "Elenenler" filtered to that rule; each rejected row shows the reason ("Alıma kapalı" / "Not buyable") | the line shows the right count per rule; the click filters "Elenenler"; TR and EN labels |
