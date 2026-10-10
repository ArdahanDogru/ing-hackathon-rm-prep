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
4. Every sentence of `oneriler`, `alternatifler` and `dikkat` has at least one
   citation, and each citation exists.
5. The text says that it is a preparation for the RM, not investment advice.

Failure → one retry with the error list; second failure → a template text built
from the facts pack (always possible, no LLM) and a banner "otomatik metin
doğrulanamadı".

## Human control

- The narrator runs only for a result that the RM approved (selection known).
- The draft has its own status: `draft` → `approved` by the RM (edits kept).
- The card and the evidence record hold the approved text, the model id, the
  prompt version and the validator result.

## Determinism, cost, tests

- Cache: `data/narratives/<run_id>-<prompt_version>-<model>.json`; the same run
  gives the same text without a new call (replay, eval consistency).
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

## Milestones (worker `ing-narrator`; each ends with green `pytest`)

| # | Milestone | Tests show |
|---|---|---|
| N1 | facts pack + template text (no LLM) | facts from a fixture result; no rejected option; template valid |
| N2 | validator | each rule catches its hand-made bad text; a good text passes |
| N3 | LLM client (fake in tests), retry, fallback, cache, budget guard | fake LLM path; retry then fallback; cache hit makes no call |
| N4 | backend + UI wiring (lead / ui), card with the approved text | draft → edit → approve; test run cannot approve |
