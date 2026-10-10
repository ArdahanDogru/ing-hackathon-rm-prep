# Decision layer — design

Status: **designed 2026-10-10 (step D, the user with ing-lead).** Code:
`src/rmprep/decision/`, tests: `tests/decision/`. Config:
`config/decision.yaml` (lead-owned). Contracts: `src/rmprep/contracts.py`
(lead-owned).

The layer turns one `EvidenceSet` and one `Persona` into one `DecisionResult`:
all options scored and put in a display order, the hard rejects, questions for
the RM, assumptions, warnings and data-quality notes. It prepares the RM for a
meeting; it is not advice to the client. The RM approves or rejects the result
(see `docs/ui.md`).

Every number, table, weight, penalty and text template below lives in
`config/decision.yaml`. The values here are the starting values; tuning them is
a config change, not a code change. Principle: the engine never guesses a value
that decides suitability — it asks the RM.

## Entry point

```python
def decide(evidence: EvidenceSet, persona: Persona, config: DecisionConfig,
           answers: Mapping[str, str] = {}, *, created_at: datetime) -> DecisionResult
```

Pure: no I/O, no clock (the caller gives `created_at`), no randomness. Same
inputs → identical result. `answers` maps `question_id` → chosen answer; an
answer that is not one of the question's `choices` raises `ValueError`.

## Facts the design is built on (snapshot 20261010-001233-6b20)

- Personas p01–p05: values are free Turkish text (see section 3).
- 2,028 TEFAS funds. Per fund: price, size, investors (`tefas`); returns
  1m/3m/6m/ytd/1y/3y/5y and risk level 1–7 (`tefas_web`, all rows flagged
  `needs_check`). Name and umbrella type are in the same `tefas_web` page and
  come to the layer through `EvidenceSet.entities` (milestone I1 of ingest).
- Umbrella types: Serbest 1318, Hisse Senedi 200, Değişken 189, Katılım 117,
  Fon Sepeti 101, Borçlanma Araçları 88, Para Piyasası 86, Kıymetli Madenler 29,
  Karma 8. Without Serbest, 803 funds remain.
- Deposit: ING Turuncu standard 23 % and welcome 39 % for each balance tier
  (manual, `manual_entry`); EVDS market average up to 3M 43.82 %. No FX deposit
  rate.
- Not in the evidence: redemption days (valör), fees, FX deposit rates,
  a 12-month CPI history (only 4 months), the client's amount, withholding tax
  rates (template not filled; rule 7: never hard-code them).

## 1. Product universe

| `kind` | Source | Notes |
|---|---|---|
| `deposit` | manual `deposit_rate`, entity `ING Turuncu Hesap standart, <tier>` | tier from config (`deposit.tier`, default `100.000-249.999 TL`); the persona has no amount. The welcome rate is temporary → only an assumption text. |
| `fund` | `tefas` + `tefas_web` DataPoints, `EvidenceSet.entities` | `fund_kind` from the umbrella type (table below) |

`fund_kind` table (umbrella type text → `fund_kind`):

| Umbrella type (`EntityInfo.category`) | `fund_kind` |
|---|---|
| Para Piyasası Şemsiye Fonu | `money_market` |
| Borçlanma Araçları Şemsiye Fonu | `debt` |
| Katılım Şemsiye Fonu | `participation` |
| Kıymetli Madenler Şemsiye Fonu | `precious_metals` |
| Hisse Senedi Şemsiye Fonu | `equity` |
| Değişken Şemsiye Fonu | `variable` |
| Karma Şemsiye Fonu | `mixed` |
| Fon Sepeti Şemsiye Fonu | `fund_of_funds` |
| Serbest Şemsiye Fonu | not in the universe (qualified investors only) |

- `ProductOption.option_id`: `deposit:ing_turuncu` | `fund:<code>`.
  `label`: deposit → "ING Turuncu Hesap (standart)"; fund → its name.
- `fx` tag: true if the upper-case fund name contains one of
  `fx_name_words` (start: `DÖVİZ`, `EUROBOND`, `DOLAR`).
- Removed and counted in a data-quality note: Serbest funds; funds with no
  `entities` entry; funds with an unknown umbrella type.
- No `gold` option (only a market price, no product terms, unverified series,
  120-day history) and no `fx_deposit` option (no rate). Gold exposure comes
  through `precious_metals` funds. A manual ING gold-account row can add a gold
  option later.
- Benchmarks only (never options): `gold_try_kg`, `bist100_*`, `usd_try`,
  `cpi_index`, the EVDS `deposit_rate`, `policy_rate`, `cbrt_funding_cost`.

**Evidence lookup.** For each (quantity, entity) the layer uses the row with
the latest `as_of` whose source is not in `evidence.excluded_sources`. A row with
`out_of_range` or `missing` counts as missing; an older row is then not used
(confirmed 2026-10-10, D3). `entities` whose `source` is
excluded count as absent. Each option records the ids of the rows it used
(`evidence_ids`).

## 2. Hard rule

Only one rule rejects an option:

- `risk_ceiling`: the fund's risk level is **known** and is above the persona's
  ceiling → `RejectedOption` with `ConstraintResult(rule_id="risk_ceiling",
  passed=False, reason=..., evidence_ids=(risk row,))`.

Every other rule is a penalty (section 4). A fund with no risk level is not
rejected (penalty `risk_unknown`). The deposit counts as risk level 1.
A scored option carries `ConstraintResult(rule_id="risk_ceiling", passed=True)`.

## 3. Persona text → levels

**Matching.** Normalize: Turkish lower case (`İ`→`i`, `I`→`ı`, then
`str.lower`), strip, collapse spaces, drop punctuation except `+` and `-`.
The normalized text must equal a normalized table key. No fuzzy matching.

| Field | Table (start values) |
|---|---|
| `risk_profili` | Muhafazakâr → ceiling 2, appetite 0; Temkinli → 3, ⅓; Dengeli → 5, ⅔; Agresif → 7, 1 |
| `yatirim_ufku` | pattern `N-M yıl` → M years; `N+ yıl` → N years; years ≤ 1 → period 6m, ≤ 3 → 1y, else 3y. p01–p05: "1-3 yıl" → 1y, "5+ yıl" → 3y |
| `likidite_ihtiyaci`, `gelir_nakit_akisi_ihtiyaci`, `anapara_koruma_tercihi` | Düşük 0, Orta 0.5, Yüksek 1 |
| `doviz_maruz_kalma_tercihi` | Sınırlı → FX intensity 1; Açık → 0; Çeşitlendirilmiş → 0 |
| `oncelikler` | phrase → criterion boost (below) |
| `acik_kisitlar` | phrase → constraint effect (below) |
| `profil`, `yas`, `durum`, `yatirim_amaci`, `rm_notu` | context only; not scored (the narrator uses them later) |

`oncelikler` phrases (all 15 of p01–p05):

| Phrase | Effect |
|---|---|
| düzenli gelir | +1 `income` |
| likiditeyi koruma, erişilebilir likidite, yüksek likidite | +1 `liquidity` |
| sınırlı dalgalanma, uzun vadeli dayanıklılık | +1 `low_risk` |
| sermayenin korunması | +1 `principal` |
| uzun vadeli büyüme, fırsat maliyetini azaltma | +1 `return` |
| sade ürün yapısı | +1 `simplicity` |
| çeşitlendirme | diversity cap 2 in the first 10 (section 4.5) |
| kur riskini yönetme | not scored; assumption "handled by the FX level" |
| kuşaklar arası planlama | not scored; assumption "no evidence for this priority" |

`acik_kisitlar` phrases (one per persona) and their effects:

| Phrase | Effect id | Effect |
|---|---|---|
| yüksek riskli ürünlerden kaçınma (P01) | `risk_cap` | ceiling = min(ceiling, 4) |
| döviz maruziyetini gerekçesiz artırmama (P02) | `fx_limit` | FX intensity = max(FX intensity, 0.5) |
| kısa vadeli nakit ihtiyacı varsayılmamalı (P03) | `no_liquidity_need` | liquidity weight 0 and liquidity intensity 0 |
| tek ürün veya tek varlık sınıfında yoğunlaşmama (P04) | `concentration_limit` | diversity cap 2 in the first 10 |
| uzun süre kilitli veya düşük likiditeli seçeneklerden kaçınma (P05) | `liquidity_need` | liquidity intensity = max(…, 1) |

**Unknown text → question.** Question ids: `q:<field>` or
`q:acik_kisitlar[<i>]`. Texts come from Turkish templates in the config.

| Field | `blocking` | Choices | Until answered |
|---|---|---|---|
| `risk_profili` | yes | the 4 profiles | no ranking (`needs_rm_input`) |
| `acik_kisitlar[i]` | yes | the effect ids above (as Turkish labels) + `ignore` | no ranking |
| `yatirim_ufku` | no | 6m / 1y / 3y | safe level 6m + assumption |
| `likidite_ihtiyaci` | no | Düşük / Orta / Yüksek | safe level Yüksek + assumption |
| `anapara_koruma_tercihi` | no | Düşük / Orta / Yüksek | safe level Yüksek + assumption |
| `gelir_nakit_akisi_ihtiyaci` | no | Düşük / Orta / Yüksek | safe level Orta + assumption |
| `doviz_maruz_kalma_tercihi` | no | Sınırlı / Açık / Çeşitlendirilmiş | safe level Sınırlı + assumption |
| `oncelikler[i]` | — (no question) | — | assumption "not used: <text>" |

`state` is `needs_rm_input` if a blocking question has no answer; then
`options` and `rejected` are empty. Otherwise `ready` (non-blocking questions may
still be open). With p01–p05 all results are `ready`; P02 has one open
non-blocking question (its FX text "Mevcut döviz gelirini dikkate alarak
kontrollü" is not in the table → assumed Sınırlı).

## 4. Scoring

### 4.1 Criteria (each 0..1)

| Criterion | Value | Evidence |
|---|---|---|
| `return` | percentile rank of the annualized return among all scored options | fund: `fund_return_<period>`, annualized `(1+R/100)^(1/years) − 1`; if the period is missing, the next shorter one (3y → 1y → 6m → 3m); no return in any period → value 0, the option is left out of the percentile base, reason `return_missing`. deposit: the rate. |
| `low_risk` | `1 − (risk − 1) / 6` (risk clamped to 1..7) | `fund_risk_level`; deposit 1 |
| `liquidity` | kind table | proxy (no valör in evidence) |
| `income` | kind table | proxy |
| `principal` | deposit 1; fund `max(0, 0.8 − 0.15 × (risk − 1))` | `fund_risk_level` |
| `simplicity` | kind table | — |
| `quality` | mean of the percentile ranks of size and investors among funds (a missing value gives 0 for its half); deposit 1 | `fund_total_value`, `fund_investor_count` |

Percentile rank of x among n values: `(count below + 0.5 × count equal other) /
(n − 1)`; n = 1 → 1.

Kind table:

| kind | liquidity | income | simplicity |
|---|---|---|---|
| deposit | 1.0 | 1.0 | 1.0 |
| money_market | 0.9 | 0.6 | 1.0 |
| debt | 0.7 | 0.5 | 0.7 |
| participation | 0.6 | 0.4 | 0.6 |
| precious_metals | 0.6 | 0.2 | 0.7 |
| equity | 0.5 | 0.2 | 0.6 |
| variable | 0.5 | 0.2 | 0.3 |
| mixed | 0.5 | 0.3 | 0.4 |
| fund_of_funds | 0.5 | 0.2 | 0.3 |

### 4.2 Weights

Raw weights from the levels of section 3, plus `priority_boost` (1) for each
matched priority; then divided by their sum (they add up to 1):

| Criterion | Raw weight |
|---|---|
| `return` | 1 + appetite |
| `low_risk` | 1 − appetite |
| `liquidity` | 2 × liquidity level (0 with `no_liquidity_need`) |
| `income` | 2 × income level |
| `principal` | 2 × principal level |
| `simplicity` | 0 |
| `quality` | 0.5 |

Example P01 (Muhafazakâr, likidite Orta, gelir Yüksek, anapara Yüksek; priorities
income, liquidity, low_risk): income 0.29, low_risk 0.19, liquidity 0.19,
principal 0.19, return 0.10, quality 0.05.

### 4.3 Penalties

`penalty = max (rule) × intensity (persona, 0..1) × violation (option, 0..1)`.
The best possible score is 1, so a max of 0.3 = up to 30 % of it.

| Rule | Max | Intensity | Violation |
|---|---|---|---|
| `principal` | 0.3 | principal level | `clamp((risk − 2) / 3, 0, 1)` |
| `liquidity` | 0.3 | liquidity intensity (= liquidity level, changed by constraints) | `1 − liquidity value` |
| `fx_exposure` | 0.3 | FX intensity | 1 if `fx` else 0 |
| `risk_unknown` | 0.3 (× 2 if the estimate > ceiling) | 1 | 1 if the risk level is missing |
| `track_record` | 0.2 | 1 | 1 if the horizon period return is missing |
| `fund_size` | 0.1 | 1 | `max(1 − size / 100M TL, 1 − investors / 100)` clamped 0..1; missing → 1 |

Risk estimate for a fund with no risk level: the highest known risk among the
scored funds of the same `fund_kind` in this evidence (7 if none). The estimate
is used for `low_risk`, `principal` and the `principal` penalty. It is never used
to reject: the `risk_ceiling` constraint of a fund without a risk level
passes, and its reason is the `penalty:risk_unknown` text.

### 4.4 Score, parts, reasons

`score = Σ weight × value − Σ penalty`. `score_parts` has one entry per criterion
with weight > 0 (key = criterion name) and one per penalty > 0 (key =
`penalty:<rule>`, negative value). The parts add up to the score (contract check,
tolerance 1e-9). `reasons` has the same keys: a Turkish sentence from a config
template, e.g. `penalty:fx_exposure` → "Döviz fonu; müşteri sınırlı döviz
maruziyeti istiyor."

### 4.5 Display order

`DecisionResult.options` holds **all** scored options in display order:

1. If a deposit option exists it is `options[0]`: the baseline row the UI pins
   above the list. It is not counted below.
2. Positions 1–3: by score, at most 1 option per `fund_kind`.
3. Positions 4–10: by score, at most 3 per `fund_kind` counted over positions
   1–10 (2 with `concentration_limit` or the `çeşitlendirme` priority).
4. If the caps leave places empty, fill them by score and raise
   `concentration` (section 6).
5. After position 10: by score.

Ties: higher score, then `option_id`. The UI groups the first 20 options by
`fund_kind` (docs/ui.md section 1, changed 2026-10-10); the order above stays
the order inside and between the groups.

## 5. `confidence` and `stability`

**`confidence`** = factor of the weakest DataPoint the option uses × factor of
each estimate.

| Input | Factor |
|---|---|
| no flags | 1.0 |
| `needs_check`, `manual_entry` | 0.9 |
| `unverified_series`, `fallback_snapshot` | 0.8 |
| `stale` | 0.7 |
| `conflict` | 0.6 |
| estimate: risk level from section 4.3 | × 0.7 |
| estimate: shorter return period than the horizon | × 0.8 |

A row with several flags takes its lowest factor. Today: typical fund 0.9,
fund with unknown risk 0.63, deposit 0.9.

**`stability`**: compute the display order again 26 times; each time one number
is ×0.8 or ×1.2: one of the 7 raw weights (then normalize again) or one of the 6
penalty maxima. `stability` = share of these runs in which the option is in
positions 1–20 (the deposit baseline counts as always in). Step (0.2) and size
(`stability.size`, 20 = the grouped UI pool; changed 2026-10-10 from 10, D7b)
are in the config.

## 6. Warnings and data-quality notes

The UI shows both in the side pane "Olası sorunlar" (`docs/ui.md`). Each warning
names the options it is about (`option_ids`; empty = the whole result) and the
evidence ids that caused it.

| `DecisionWarning.code` | When |
|---|---|
| `concentration` | the caps of section 4.5 could not be met in positions 1–10 |
| `fx_exposure` | an `fx` fund is in positions 1–10 and FX intensity > 0 |
| `risk_estimate` | a fund with an estimated risk above the ceiling is in positions 1–10 |
| `low_stability` | an option in positions 1–3 has stability < 0.5 |
| `deposit_vs_market` | ING standard rate < EVDS market average − 5 points |
| `no_fx_deposit_data` | an FX question exists, or the FX level is not Sınırlı, and no FX deposit rate is in the evidence |

`DataQualityNote`s:

- one per (source, flag) in the evidence the result used, with a count;
- one per excluded source ("computed without …");
- one per failed source or fallback (from `source_status`);
- `out_of_range` values ignored (with ids);
- funds removed: Serbest, no entity info, unknown umbrella type (counts).

Assumptions (always, as plain strings): fund returns are past returns and the
deposit rate is a current rate; all values are before tax (withholding rates
not filled); the deposit uses the standard rate of tier `<tier>` (the persona
has no amount; the welcome rate is temporary); no real returns (CPI history too
short); liquidity and income come from the fund kind (no valör data); plus the
assumptions of section 3.

Details fixed in D5 (2026-10-10):

- `no_fx_deposit_data` turns off when the evidence has a row with quantity
  `fx_deposit_rate` (code constant `notes.FX_DEPOSIT_QUANTITY`; no source
  gives one yet).
- A `needs_rm_input` result has the source notes (excluded, failed, fallback)
  and the assumptions, but no warnings.
- Flag-count notes count only the rows the result references (options,
  rejected, warnings).

## 7. Identity and config

- `config/decision.yaml`: all tables, weights, penalties, thresholds and Turkish
  text templates. Loaded and checked by `rmprep.decision.config` (unknown keys,
  missing kinds, weights < 0 → error).
- `config_hash` = sha256 of the parsed config as canonical JSON
  (`sort_keys=True`, no spaces), first 12 hex chars.
- `run_id` = `"R"` + sha1 of canonical JSON of `[config_hash, persona.to_dict(),
  snapshot_id, sorted(excluded_sources), sorted(answers.items())]`, first 10 hex
  chars. Same inputs → same `run_id`; an answer or a persona edit → new `run_id`.
  `created_at` is not part of it.
- `DecisionResult.persona` holds the full persona used (edited personas
  included).

## 8. Milestones (worker `ing-decision`; each ends with green `pytest`)

Before the worker starts, the lead writes `config/decision.yaml`, freezes the
contracts and adds the fixture `tests/contracts/fixtures/evidence_medium.json`
(real rows of about 40 funds of all kinds, incl. unknown risk, FX and small
funds, with `entities`).

| # | Milestone | Tests show |
|---|---|---|
| D1 | config loader + checks; persona text → levels; questions and assumptions | p01–p05 map as in section 3; unknown `acik_kisitlar` → blocking question; unknown FX text → safe level + assumption + non-blocking question; answers apply; bad answer → error |
| D2 | universe + evidence lookup | kinds and `fx` tags right; Serbest / no entity / unknown type removed and counted; latest row used; excluded source and `out_of_range` ignored |
| D3 | criteria, weights, penalties, `risk_ceiling`, `score_parts` + `reasons`, display order | parts add up to the score; hand-computed cases match; risk above ceiling → rejected; caps of section 4.5 |
| D4 | `confidence`, `stability` | exact values on small hand-made cases |
| D5 | warnings, data-quality notes, `config_hash`, `run_id`, `decide()`; `rmprep.decision.report.render(result) -> str` (text: baseline + positions 1–10 with parts) | one trigger case per warning; valid `DecisionResult` for p01–p05 on `evidence_medium`; same inputs → same `run_id`; answer → new `run_id` |
| D7 | `render` groups like the UI: baseline, then ≤ 5 `fund_kind` groups from the first 20 options (head + alternatives); rejected = count + the first 10 ids | group order and members on a hand-made result; long rejected list cut |
| D6 *(optional, after the MVO)* | Jev text mapper (below) | — |

After D5 the lead wires `python -m rmprep decide --persona P01 [--snapshot ID]
[--exclude SRC ...] [--answer QID=VALUE ...]` in `cli.py` and runs the report on
the real snapshot with the user for tuning. Wired 2026-10-10; extra option
`--personas DIR` (default: the folder above the project, `../p0*.json`).

## Later / optional

- **D6 Jev text mapper** (TypeSafe AI, decision-only model, hosted API): only
  when the exact table has no match. It never decides alone: it pre-fills the
  RM question with its choice and probability. A non-blocking field may use it
  as an assumption if p ≥ 0.8; a blocking field always needs the RM. Needs: a
  `TextMapper` protocol with a fake for tests (no network in tests); answers
  cached and treated as inputs (its probabilities vary between calls, `run_id`
  must not); a check of the 15 real Turkish phrases first; KVKK review before
  real client text leaves the bank. Decided 2026-10-10: optional, after the MVO;
  the user marked it "later" (2026-10-10, after D5).
- A trained model on RM approvals / selections (`data/runs/`) to tune weights,
  once there are enough real runs.
- A gold option from a manual ING gold-account row (spread, source URL).
