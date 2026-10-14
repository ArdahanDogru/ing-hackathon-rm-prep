# Narrator — design (DRAFT for the session with the user)

Status: **draft 2026-10-10 by ing-lead; decisions 1–5 taken by the user
2026-10-10; decision 6 (contract) proposed, waiting for the user.** Code: `src/rmprep/narrator/`, tests: `tests/narrator/`.

## Why (brief)

The brief asks for a "taslak hazırlık metni" and a "kişiselleştirilmiş
yönlendirme ve teklif metni"; deliverable 1 is a demo "veri toplamadan RM
yönlendirmesi ve teklif metnine kadar" for at least two personas. Today the
summary card lists the results; it is not a personalized text. Rules that bind
the text: 4 (no output to the client without RM approval), 5 (no option that
breaks the risk profile or an explicit constraint), 6 (no guarantee or certain
return), 9 (decision support, not advice), 2 and 10 (sources and assumptions
shown).

## Principle

The decision layer decides; the narrator only **writes**. Code builds the facts,
the LLM turns them into Turkish prose, code checks the prose, the RM approves.

```
DecisionResult (approved selection) + EvidenceSet
  -> facts pack (code, deterministic)
  -> LLM draft (one call, structured output: sections, sentences, citations)
  -> validator (code): numbers, options, phrases, citations
       fail -> one retry with the errors -> fail again -> template text + banner
  -> RM reads, edits, approves  -> card + evidence record
```

## Input: the facts pack (code)

- Persona context: `profil`, `yas`, `durum`, `yatirim_amaci`, `yatirim_ufku`,
  `oncelikler`, `acik_kisitlar`, `rm_notu` (these fields are not scored; the
  narrator is where they matter).
- The baseline and the options the RM selected (`rm_selected`), each with label,
  kind, score parts and their reason texts, confidence, the key numbers
  (nominal / net / real return, risk, valör when I3 is in) and evidence ids.
- The groups of the short list (`rmprep.grouping`), for "alternatifler".
- Warnings, data-quality notes, assumptions, open questions, the RM notes.
- The rejected options: count and rule only. They must never appear by name.

## Output (structured, Turkish)

| Section | Content |
|---|---|
| `ozet` | 3–5 sentences: the client situation and the aim of the meeting |
| `oneriler` | per selected option: what it is, why it fits this client (from the reasons), what to watch |
| `alternatifler` | 1–2 sentences per group: the other options of the same kind |
| `dikkat` | warnings, risks, data gaps, in plain words |
| `sorular` | questions for the RM to ask the client (open questions + from `acik_kisitlar`) |
| `teklif_metni` | a short draft text the RM may say or adapt in the meeting |
| `varsayimlar` | the assumptions, verbatim from the result |

Each sentence carries citations: option ids and/or evidence ids.

## Validator (code, deterministic)

1. Every number in the text matches a number in the facts pack (tolerance for
   rounding).
2. Only the baseline, the selected options and their group alternatives are
   named; no rejected option; no option outside the result.
3. Forbidden phrases (config list, rule 6): e.g. "garanti", "kesin getiri",
   "risksiz", "kaybetmezsiniz", "mutlaka kazandırır".
   The option labels of the result are removed from the text before the scan
   (N5, found by eval E2: "GARANTİ PORTFÖY ..." fund names matched "garanti").
4. Every sentence of `oneriler`, `alternatifler` and `dikkat` has at least one
   citation, and each citation exists.
5. The text says that it is a preparation for the RM, not investment advice.

Failure → one retry with the error list; second failure → a template text built
from the facts pack (always possible, no LLM) and a banner "otomatik metin
doğrulanamadı".

## Human control

- The narrator runs only for a result that the RM approved (selection known).
- Lever 1 (the user, 2026-10-10): the approval starts the TR text in the
  background (`RealBackend`, a thread pool of 2); opening the text waits for that
  job instead of making a second call; a failed background draft is made again
  on request; EN is made when first opened. Speed test 2026-10-10 (4 texts):
  effort medium 23.9 s / $0.049, low 22.1 s / $0.036, same checker and judge
  results — effort stays medium; time is mostly the output itself.
- The draft has its own status: `draft` → `approved` by the RM (edits kept).
- The card and the evidence record hold the approved text, the model id, the
  prompt version and the validator result.

## Determinism, cost, tests

- Cache: `data/narratives/<run_id>-<lang>-<prompt_version>-<model>.json` (one
  draft per language); the same run gives the same text without a new call
  (replay, eval consistency). The cache keeps LLM texts and validator
  fallbacks, not API errors or budget stops. Cost ledger:
  `data/narratives/costs.jsonl`. Approved texts:
  `data/narratives/<run_id>-<lang>-approved.json` (RealBackend).
- Budget guard: config `max_cost_usd` per day; token usage and cost recorded per
  call.
- Tests: a fake LLM (no network); the validator on hand-made texts; the
  template fallback; one optional live smoke test, skipped without a key.
- Key: `ANTHROPIC_API_KEY` in `.env` (never logged), as the EVDS key.

## LLM options (prices: Claude API, cached 2026-10-06)

| Option | Cost per text (≈8k in, ≈1.5k out + thinking) | Notes |
|---|---|---|
| **Claude Opus 5.5** (`claude-opus-5-5`, $4 / $20 per 1M) | ≈ $0.10 | best Turkish and instruction following; ≈ 900 texts per $100 |
| Claude Sonnet 5.5 (`claude-sonnet-5-5`, $2 / $10) | ≈ $0.05 | good; half the cost |
| Claude Haiku 5.5 (`claude-haiku-5-5`, $0.10 / $0.50) | ≈ $0.003 | cheap; for checks or an LLM judge in eval, weaker prose |
| Local open-weights model (e.g. via Ollama) | 0 | no external call; weaker Turkish; setup work |
| Template only (no LLM) | 0 | fully deterministic; the fallback in any case; weaker "AI" story |
| Max plan through Claude Code | — | not for app traffic; use the API credits |

Competition fit: the brief allows any approach; the personas are synthetic and
the data is public, so sending them to the API is allowed (rule 1, rule 8). The
jury looks at the split of LLM / deterministic logic / human roles (criterion
"AI / Agentic mühendislik", 20 %): this design gives the LLM only the writing.

## Decisions (the user, 2026-10-10)

1. Model: **Claude Sonnet 5.5** (`claude-sonnet-5-5`) for now; config value.
2. The narrator runs **only for a result the RM approved**.
3. Sections as above, formal "siz" form; **Turkish and English with a toggle**:
   one draft per language, made when the RM first opens that language (cached).
4. `teklif_metni` is **a script for the RM** to say or adapt in the meeting, not
   a letter to the client.
5. Daily cost limit **$5** (config `max_cost_usd_per_day`); over the limit → the
   template text and a banner.
6. Contract v1.2 (additive; proposed, see below).

## Contract v1.2 (proposed)

New types; no existing type changes.

```python
class NarrativeStatus(StrEnum): DRAFT = "draft"; APPROVED = "approved"

@dataclass(frozen=True)
class NarrativeSentence:
    text: str
    option_ids: tuple[str, ...] = ()     # options the sentence talks about
    evidence_ids: tuple[str, ...] = ()   # DataPoint ids it rests on

@dataclass(frozen=True)
class NarrativeSection:
    key: str                             # ozet | oneriler | alternatifler | dikkat | sorular | teklif_metni | varsayimlar
    sentences: tuple[NarrativeSentence, ...]

@dataclass(frozen=True)
class NarrativeDraft:
    run_id: str                          # the approved DecisionResult it is written for
    lang: str                            # "TR" | "EN"
    sections: tuple[NarrativeSection, ...]
    source: str                          # "llm" | "template"
    model: str                           # "" for the template
    prompt_version: str
    checks: tuple[str, ...]              # validator findings; () = passed
    created_at: datetime                 # timezone-aware
    cost_usd: float = 0.0
    status: NarrativeStatus = NarrativeStatus.DRAFT
    rm_text: str = ""                    # the RM's edited text (Markdown); required when approved
```

`Backend` gets two methods:

```python
def draft_narrative(self, run_id: str, lang: str = "TR") -> NarrativeDraft: ...
    # only for an approved run; cached per (run_id, lang, prompt_version, model)
def approve_narrative(self, run_id: str, lang: str, text: str) -> NarrativeDraft: ...
    # stores the RM's text; the card uses it
```

Contract checks: `lang` in TR/EN; section keys known; `approved` needs a
non-empty `rm_text`; `source == "template"` ⇔ `model == ""`. The validator rules
stay in the narrator (they need the facts pack).

## As built (N1–N3, 2026-10-10)

- Entry point: `rmprep.narrator.service.narrator_from_root(root).draft(result,
  evidence, lang) -> NarrativeDraft`; the key comes from the environment or
  `root/.env`. Without a key: the template text.
- `template.to_markdown(draft)` is the start text for the RM edit;
  `template.banner(draft)` the banner (template after failed checks).
- Refusal fallback on (server-side, `fallbacks="default"`): `draft.model` is the
  model that served the text (can be another model after a fallback).
- `prompt_version` "n1" covers the first LLM prompt; bump it on any change of
  `prompt.py`.
- Prompt caching (the user, 2026-10-10; N6): two cache marks — at the end of the
  system prompt (rules, sections, phrases, format; about 1,700 tokens, the same
  for every call in one language, so calls for different clients within 5
  minutes read it from the cache) and after the facts pack (reused on a
  validator retry). Nothing that changes per call may be in the system prompt.
- Live smoke test (about $0.05): `tests/narrator/test_live.py`, runs only with
  `RMPREP_LIVE_NARRATOR=1` and a key, so a plain `pytest` never calls the API.
- N4 (lead): `RealBackend.draft_narrative` / `approve_narrative`; ui: U9.

## Cost finding (first full eval, 2026-10-10) and N8

A real text cost $0.136 (fixture test: $0.04): the facts pack was 35,000–50,000
tokens (P01: 62,000 characters; data-quality notes with every flagged row id
21,500, alternatives with all fields 16,000), written to the cache at 1.25×;
output with thinking 3,500–4,300 tokens; 6 of 24 texts needed a retry.
N8 (approved by the user): the facts pack keeps only what the text needs —
data-quality notes as their text and counts (no id lists), alternatives as
label, kind, option id and 2–3 key numbers with their evidence ids, compact
JSON (no indentation); the validator still sees the full facts (numbers, ids).
Target: under 10,000 characters for P01; cost per text about $0.05.

## N7: lever 2 and client links (approved by the user 2026-10-10; prompt n3)

From the judge's reasons in the eval runs of 2026-10-10:
- `dikkat`: only warnings that matter for the client and the meeting; the
  data-quality notes become one short sentence that points to the "Olası
  sorunlar" pane; no internal values (flag names such as needs_check, row
  counts, rejection counts, internal scores such as "gelir uygunluğu 0,6").
- The past-return caveat once in `dikkat` and in short form in `teklif_metni`.
- `oneriler`: per selected option one sentence that links it to a named client
  need (horizon, income, liquidity, principal, constraint, RM note); the options
  must not read alike.
- `teklif_metni`: built on the client's own goal and situation, not generic.
- `varsayimlar` unchanged (verbatim from the engine; the validator requires
  them).

## Milestones (worker `ing-narrator`; each ends with green `pytest`)

| # | Milestone | Tests show |
|---|---|---|
| N1 | facts pack + template text (no LLM) | facts from a fixture result; no rejected option; template valid |
| N2 | validator | each rule catches its hand-made bad text; a good text passes |
| N3 | LLM client (fake in tests), retry, fallback, cache, budget guard | fake LLM path; retry then fallback; cache hit makes no call |
| N4 | backend + UI wiring (lead / ui), card with the approved text | draft → edit → approve; test run cannot approve |
| N9 | (web UI, 2026-10-11; docs/web-ui.md section 5) talking points, need tags, client-only warnings, prompt `n4` (below) | see "N9" below |

## N9: talking points, need tags, client-only warnings (2026-10-11, prompt n4)

Contract v1.3. The narrator switches from `NARRATIVE_SECTIONS` to
`NARRATIVE_SECTIONS_V13` (prompt schema, parser, validator, template, config
section titles; the lead adds the `talking_points` title to
`config/narrator.yaml` when N9 is merged).

- New section `talking_points`: 2–3 sentences, each with a `title` (2–4 words)
  and a citation, about the client's situation from the client's view. Input:
  `DecisionResult.talking_points`, the persona, the selection.
- `need_tags`: for each selected option 1–3 tags; each tag is one of the
  persona's `oncelikler`, compared with Turkish lower-casing
  (`validate_need_tags(tags, persona) -> list[str]` in `validator.py`); an
  unknown tag is a validator error (retry, then template). The template takes
  the tags from the `why` lines of `rmprep.decision.display.display_facts`.
- The facts pack holds only warnings with `audience == "client"`; RM-only
  warnings never reach the text (the web shows them in "RM notları").
- The card is written as instructions to the RM ("… anlatın"); only
  `teklif_metni` is quoted speech for the client.
- Note names in the facts pack: `dosyadaki_not` (the persona's `rm_notu`) and
  `rm_onay_notu` (the RM's approval note).
- `prompt_version = "n4"`. The lead runs the eval after the merge.

Tests: facts pack without rm warnings; note names; template with 2–3 titled
talking points and tags for every selected option; Turkish casing in need
tags; the parser reads titles; no rm warning text in a draft.

## N13: text quality (2026-10-12, from the judge analysis of eval 20261012-201431-full)

The judge gives "tailored" 57 %, "clear_for_rm" 50 %, "balanced" 50 %. Causes
in the narrator (verified): no per-option risk / access / fee facts (dikkat had
only the past-return line in 11 of 19 texts); the 6 number slots favour returns
and repeat market rate and CPI per option; the nominal return leads; the
past-return caveat appears about 6 times per text; oneriler sentences often do
not name their fund; unmatched priorities get no instruction.

Changes (prompt version n7):
1. Facts pack: per option a risk line — access (`access_text` of display
   facts, valör), fees if any, a fixed risk note per asset class from config
   (`narrator.yaml risk_notes.<asset_class>`, lead adds the texts), each with a
   citation; market deposit rate and CPI move to the top level; drop
   `fund_buyable` from the option numbers; the real 1-year return is a number of
   the option (not only inside a reason).
2. Prompt: oneriler = for each selected option 3 sentences that start with its
   short name: (a) facts, real return first, then nominal; (b) the fit, with a
   client fact not used for the other options; (c) the main trade-off or risk
   for this client. dikkat = the warnings plus one watch item per option.
   Priorities with no matching criterion (`unmatched_priorities` in the pack)
   are named as not covered and asked about in sorular.
3. Repetition: the past-return caveat only in dikkat and teklif_metni; ozet at
   most 3 sentences; talking_points do not repeat profile facts.
4. `to_markdown`: the screen order (ozet, talking_points, teklif_metni,
   oneriler with a `###` heading per option, dikkat, then alternatifler,
   sorular, varsayimlar under "Ek bilgiler").
Tests with the fake LLM; one live call on P01 TR allowed (about $0.05).


## N14: deletable blocks and the market note (approved by the user 2026-10-14)

**Deleting.** The RM can delete any block of the meeting text, or a whole
section (all its blocks), and an empty text is allowed.

- Contract v1.9 (meaning, no new field): `rm_edits[block] == ""` = the block
  is deleted. `edits.with_edit` (lead) stores "" without findings; `None`
  restores the original, as before.
- `apply_edits` drops the sentences of a deleted block; `to_markdown` leaves
  out a section whose blocks are all deleted (no empty heading; "Ek bilgiler"
  only when one of its sections is left).
- The disclaimer ("yatırım tavsiyesi değildir", `config/narrator.yaml`
  `disclaimer`) always stays (brief rule 9): when the composed text no longer
  contains it (for example the `ozet` block was deleted or edited without
  it), `to_markdown` adds it as the last line. The disclaimer config moves to
  where `to_markdown` can read it (an argument or the draft's language).
- Tests: delete one block; delete all blocks of `oneriler` / `talking_points`
  (no heading); delete `ozet` → the disclaimer is the last line; restore; the
  edits file keeps "".

**Market note.** A block `piyasa_notu` (code-written, not by the LLM, so the
validator has nothing to check in it) after `ozet`:
"Piyasa notu (TCMB EVDS): politika faizi %{policy_rate} ({date}); USD/TRY
{usd_try} ({date}); TCMB ağırlıklı ortalama fonlama maliyeti %{funding} ({date})."
(EN text likewise; texts in `config/narrator.yaml` `market_note`, lead.) Values
from the evidence (`EvidenceIndex`, the entities of `config/sources.yaml`), each
sentence with its evidence ids; a missing series is left out; none at all → no
block. The block is deletable like the others, so the RM can keep it out of
the client text; the dashboard shows the same values (web W15).

**N14 as built** (merged 2026-10-14, narrator@9de7b91):

- `template.apply_edits` drops "" blocks; `to_markdown(d, names=None,
  disclaimer=None)` leaves out sections with no sentence left (and "Ek
  bilgiler" when all three are gone) and adds the disclaimer (default: config
  by `d.lang`) as the last line when the text no longer has it.
  `edits.apply_edits` (lead) hands the work to `template.apply_edits`.
- `rmprep/narrator/market.py`: `market_note_sentences` / `with_market_note`
  build `piyasa_notu` right after `ozet`, one sentence per
  `market_note.series` with the template `market_note.sentence` and its
  evidence id. A missing series is left out; no series, no evidence or no
  sentence template = no block. `Narrator.draft` adds it to LLM and template
  drafts (cached with it).
- `validate()` skips `piyasa_notu`. `check_block` on an edited `piyasa_notu`
  allows the numbers and dates of the original note; a new number still warns.
- Drafts cached before N14 have no market note until the cache key changes
  (prompt_version or the facts); a new snapshot changes the facts.
- The sentence form is one sentence per series ("{label} {value} (TCMB EVDS,
  {date}).") instead of the one long sentence above.
