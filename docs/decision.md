# Decision layer — design

Status: **designed 2026-10-10 (step D, the user with ing-lead); D1–D5, D7–D10
done; tuning on snapshot 20261010-144333-f348 accepted by the user 2026-10-10
(P01/P05 stay similar: both careful, 1–3 years; accepted). D6 (Jev) later.
Stopaj rows expire 31.12.2026.** Code:
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
| `time_deposit` | manual `deposit_rate`, entity `ING e-Vadeli Mevduat, <term>, <tier>` (`data/inbox/manual/ing_e_vadeli.csv`) | added 2026-10-10 (contract v1.1, milestone D8). One option, ranked like a fund (not a baseline). Term and tier from config (`time_deposit.term`, default `32-45 gün`; `time_deposit.tier`, default `99.999,99-250.000 TL`, the column that holds 100.000–249.999 TL). Missing row → no option + a data-quality note. |
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

- `ProductOption.option_id`: `deposit:ing_turuncu` | `time_deposit:ing_e_vadeli` |
  `fund:<code>`. `label`: deposit → "ING Turuncu Hesap (standart)"; time
  deposit → "ING e-Vadeli Mevduat (<term>)"; fund → its name.
- ING clients can buy the funds of other companies through ING; the list does
  not prefer ING funds (decided by the user 2026-10-10).
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

D12 (approved by the user 2026-10-10, parts a, b, c): a second hard rule.

- `not_buyable`: the fund's latest `fund_buyable` row (ingest I3b) is 0 — the
  fund does not trade on TEFAS or is closed for purchase, so an ING client cannot
  buy it → `RejectedOption` with `ConstraintResult(rule_id="not_buyable",
  passed=False, reason=..., evidence_ids=(status row,))`. The first live run
  (279 pages) had 65 such funds. A missing row → no rejection; one data-quality
  note with the count. Checked before `risk_ceiling`; a fund can fail both.

D13 (approved by the user 2026-10-10): **explicit constraints are hard rules**
(brief section 12 rule 5: a product that breaks an explicit constraint must not
enter the recommendation list or the offer text). Each `acik_kisitlar` effect
that can be tested on a product rejects the product, with the rule id = the
effect id and the reason shown to the RM in "Elenenler":

- `fx_limit` (P02 "döviz maruziyetini gerekçesiz artırmama"): a fund with the
  `fx` tag is rejected. "gerekçesiz" lets the RM lift it: a non-blocking question
  `q:override:fx_limit` (choices: "uygula" = default, "gerekçeyle kaldır"); with
  "gerekçeyle kaldır" the FX funds come back with the old penalty, and an
  assumption records the RM's override (the RM writes the reason in the note).
- `liquidity_need` (P05 "uzun süre kilitli veya düşük likiditeli seçeneklerden
  kaçınma"): a fund with a sell valör above `max_sell_valor_days` (3) and a time
  deposit with a term above `max_lock_days` (91) are rejected. A fund without a
  valör row is not rejected (data-quality note with the count). The 32-day
  e-Vadeli stays.
- `risk_cap` was already hard (ceiling). `concentration_limit` and
  `no_liquidity_need` do not test a single product; they stay structural (caps,
  weights).
- An unknown constraint text stays a blocking question; the RM's answer picks an
  effect id, and that effect is enforced the same way.
- Order of the checks: `not_buyable`, `risk_ceiling`, then the constraint rules.
  The soft preferences (the FX level of `doviz_maruz_kalma_tercihi`, the
  liquidity level) stay penalties.

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
| `return` | percentile rank of the annualized return among all scored options | fund: `fund_return_<period>`, annualized `(1+R/100)^(1/years) − 1`; if the period is missing, the next shorter one (3y → 1y → 6m → 3m); no return in any period → value 0, the option is left out of the percentile base, reason `return_missing`. deposit and time deposit: the rate (nominal annual, as published). |
| `low_risk` | `1 − (risk − 1) / 6` (risk clamped to 1..7) | `fund_risk_level`; deposit and time deposit 1 |
| `liquidity` | kind table | proxy (no valör in evidence) |
| `income` | kind table | proxy |
| `principal` | deposit and time deposit 1; fund `max(0, 0.8 − 0.15 × (risk − 1))` | `fund_risk_level` |
| `simplicity` | kind table | — |
| `quality` | mean of the percentile ranks of size and investors among funds (a missing value gives 0 for its half); deposit and time deposit 0.5 (neutral; was 1, changed 2026-10-10, D9) | `fund_total_value`, `fund_investor_count` |

Percentile rank of x among n values: `(count below + 0.5 × count equal other) /
(n − 1)`; n = 1 → 1.

Kind table:

| kind | liquidity | income | simplicity |
|---|---|---|---|
| deposit | 1.0 | 1.0 | 1.0 |
| time_deposit | 0.6 | 0.9 | 1.0 |
| money_market | 0.9 | 0.6 | 1.0 |
| debt | 0.7 | 0.5 | 0.7 |
| participation | 0.6 | 0.4 | 0.6 |
| precious_metals | 0.6 | 0.2 | 0.7 |
| equity | 0.5 | 0.2 | 0.6 |
| variable | 0.5 | 0.2 | 0.3 |
| mixed | 0.5 | 0.3 | 0.4 |
| fund_of_funds | 0.5 | 0.2 | 0.3 |

### 4.1b Real return after tax (D9, decided by the user 2026-10-10)

Research (2026-10-10): annual CPI 29.73 % (TÜİK, Sep 2026); the Turuncu Hesap
standard rate (23 %) is −8.3 % real after the 17.5 % stopaj. Suitability rules
(MiFID II, SPK III-37.1) give no numeric weights; a low weight on a *nominal*
return is hard to defend at this inflation. Thus the `return` criterion uses
the real return after tax, and a negative real return is penalized.

- Evidence (manual CSVs in `data/inbox/manual/`, config section `real_return`):
  `cpi_annual` (entity `TÜFE yıllık değişim (TÜİK)`) and `withholding_tax_rate`
  per product: deposit → `TL vadesiz mevduat ve günlük hesap (Turuncu Hesap
  türü)`; time deposit → `TL vadeli mevduat, 6 aya kadar vadeli`; fund →
  `Yatırım fonu, para piyasası fonu` for `money_market`, else `Yatırım fonu,
  diğer fonlar (değişken, borçlanma araçları, fon sepeti)`. Equity-intensive
  TEFAS funds have 0 % stopaj; the engine uses the "diğer fonlar" rate for all
  other funds and says so in an assumption (conservative).
- Nominal annual return `R` as in 4.1 (fund: annualized past return; deposit and
  time deposit: the rate). Net `N = R × (1 − stopaj)`. Time deposit: renewed
  every `time_deposit.term_days` (32) days: `N = (1 + R(1−t) × d/365)^(365/d) − 1`.
  Deposit: no compounding (conservative). Real `r = (1 + N) / (1 + CPI) − 1`.
- `return` value = percentile rank of `r` among the scored options. The reason
  text shows R, N and r.
- Missing CPI → nominal net return, no `real_loss` penalty, a data-quality note.
  Missing stopaj for an option → stopaj 0 for it, a data-quality note.
- New penalty `real_loss` (4.3). Assumptions: the old `pre_tax` and
  `no_real_returns` texts are replaced by one text with the CPI value and date,
  plus the stopaj assumption for equity funds and "32 günlük vade her ay
  yenilenir; oranlar değişebilir".

Details fixed in D9 (2026-10-10):

- No stopaj on a loss: if R ≤ 0 then N = R.
- The CPI and stopaj rows used are in the option's `evidence_ids`; they are
  `manual_entry`, so `confidence` is at most 0.9.
- `score_parts` order of penalties: `real_loss` before `fund_size`.
- Assumptions with `real_return`: past returns, `real_return_cpi` (or
  `real_return_no_cpi`), deposit tier, kind proxy, `stopaj_equity`,
  `time_deposit_renewal` (only if `term_days` is set).
- Tests: the shared `config` fixture is the project config without the D9
  additions (`tests/decision/conftest.py`), so the hand-computed D1–D8 values
  stay; the D9 tests use `d9_config`.

### 4.2 Weights

Raw weights from the levels of section 3, plus `priority_boost` (1) for each
matched priority; then divided by their sum (they add up to 1):

| Criterion | Raw weight |
|---|---|
| `return` | 2 + 2 × appetite (was 1 + appetite; changed 2026-10-10, D9) |
| `low_risk` | 1 − appetite |
| `liquidity` | 2 × liquidity level (0 with `no_liquidity_need`) |
| `income` | 2 × income level |
| `principal` | 2 × principal level |
| `simplicity` | 0 |
| `quality` | 0.5 |

Example P01 (Muhafazakâr, likidite Orta, gelir Yüksek, anapara Yüksek; priorities
income, liquidity, low_risk): income 0.29, low_risk 0.19, liquidity 0.19,
principal 0.19, return 0.10, quality 0.05.

Long horizon (D9): if the horizon period is `3y` (horizon 3+ years), the
`liquidity` raw weight × 0.5 and the `return` raw weight + 1 (config
`long_horizon`), before the normalization.

Details fixed in D10 (2026-10-10):

- `underperformance`: N is the net return (4.1b); without `real_return`, N and B
  are nominal (B = the gross market rate). A missing deposit stopaj row gives
  B = the gross market rate. An option with no return gets no
  `underperformance` penalty (`track_record` covers it). The market row and the
  deposit stopaj row are in each option's `evidence_ids` when the penalty is
  configured and the option has a return.
- Stability: 30 runs with `real_loss` and `underperformance` (2 × (7 + 8)).
- Concentration with the pool: ranges checked in the order 1–10, 1–20 (only with
  diversity), 1–3; the first range over its cap is reported.

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
| `underperformance` (D10) | 0.3 | appetite (0, ⅓, ⅔, 1 from `risk_profili`) | `clamp((B − N) / 0.20, 0, 1)`; N = the option's net return (4.1b), B = the EVDS market deposit rate (`deposit.market_entity`, 43.82 %) net of the deposit stopaj (36.2 %). Missing B → no penalty + a data-quality note. Decided by the user 2026-10-10: a client who wants return or accepts risk must not get an option far below the deposit market. |
| `real_loss` (D9) | 0.3 | principal level | `clamp(−r / 0.10, 0, 1)` (r = real return after tax, 4.1b) |
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
4. Positions 11–20 (D10, 2026-10-10), only with `concentration_limit` or the
   `çeşitlendirme` priority: by score, at most 4 per kind counted over
   positions 1–20 (config `display.pool: 20`, `display.diversity_pool_cap: 4`).
   Without diversity: by score, as before.
5. If the caps leave places empty, fill them by score and raise
   `concentration` (section 6).
6. After position 10 (without diversity) or 20 (with it): by score.

Ties: higher score, then `option_id`. The short list shows these options in
groups (4.6); the order above stays the order inside and between the groups.

### 4.6 Grouping rule (ground truth, 2026-10-10)

This section is the only description of the rule. One implementation,
`src/rmprep/grouping.py` (lead-owned), serves the UI ("Kısa liste"), the text
report (`render`) and the kind caps of 4.5. Change the rule here first.

- Group key (`group_key`): `fund_kind` for a fund, else the option `kind`
  (`time_deposit`). The kind caps of 4.5 count by the same key.
- Pool: the first 20 non-deposit options in display order. The deposit baseline
  is not in a group; it is pinned above the list.
- One group per key in the pool; at most 5 groups, ordered by the score of
  their best option (ties: `option_id`).
- Head: the best option of the group (the recommendation row).
- Alternatives: the other pool options of the group, best first; 3 visible, the
  rest behind "Daha fazla".
- Options outside the pool or the 5 groups appear only in the full list.
- Values: `GroupingRule(pool=20, max_groups=5, visible_alternatives=3)`.

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

**`stability`**: compute the display order again 28 times (26 before D9); each
time one number is ×0.8 or ×1.2: one of the 7 raw weights (then normalize again)
or one of the 7 penalty maxima. `stability` = share of these runs in which the option is in
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

Assumptions (always, as plain strings; with D9 the before-tax and no-real-return
texts are replaced as in 4.1b): fund returns are past returns and the
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
| D8 | `time_deposit` option (section 1): config section `time_deposit` (OPTIONAL in the checks until the lead adds it: option_id, label, source, quantity, entity_prefix, term, tier); scored like a deposit except the kind table; counts as its own kind (`time_deposit`) for the caps of 4.5 and the groups of the report; penalties as for any option | option from a hand-made row; missing row → no option + note; kind caps; group in `render`; P01–P05 valid on a hand-made evidence with the row |
| D9 | real return after tax (4.1b): config section `real_return` (OPTIONAL in the checks until the lead adds it; without it the old nominal behaviour stays), `time_deposit.term_days`, penalty `real_loss`, `long_horizon`, deposit quality value from config (`quality_value.deposit`, `quality_value.time_deposit`), new texts (reason for `return` with R/N/r, `penalty:real_loss`, assumptions, data-quality notes for missing CPI / stopaj) | hand-computed N and r for deposit, time deposit (compounding), fund; Turuncu 23 % / stopaj 17.5 % / CPI 29.73 % → r = −8.3 % and penalty 0.3 × level × 0.83; missing CPI / stopaj cases; long-horizon weights; P01–P05 valid on hand-made evidence with the new rows |
| D10 | penalty `underperformance` (4.3) and the positions 11–20 cap with diversity (4.5); config OPTIONAL until the lead adds it: `penalties.underperformance` (0.3), `underperformance: {scale: 0.20}`, `display.pool` (20), `display.diversity_pool_cap` (4); texts `penalty:underperformance`, data-quality note for a missing benchmark | hand-computed penalty (fund 10 % for P03 → 0.3; P02 → 0.2; Muhafazakâr → 0); missing benchmark; with diversity no kind has more than 4 options in 1–20, without diversity the order does not change; stability counts the new penalty |
| D11 | use `rmprep.grouping` (4.6): `report.render` groups with `grouping.groups`; the kind caps of 4.5 count by `grouping.group_key`; remove `report.fund_groups` and the local constants | report output unchanged on the real snapshot; tests import the shared rule |
| D12 | (a) hard rule `not_buyable` (section 2); (b) `liquidity` of a fund from its sell valör (`fund_sell_valor_days`) through a config table (start: 0 days 1.0, 1 → 0.9, 2 → 0.8, 3 → 0.7, 4–5 → 0.6, 6–10 → 0.4, more → 0.2), the kind table only when the row is missing (reason says which); (c) entry and exit fees (`fund_entry_fee`, `fund_exit_fee`, %) reduce the net return N by (entry + exit) / horizon years (6m 0.5, 1y 1, 3y 3); reason texts for valör and fees; all config OPTIONAL until the lead adds it | rejected with the rule and the row id; missing status → note; valör table values and the kind fallback; fee effect hand-computed; P01–P05 valid |
| D13 | explicit constraints as hard rules (section 2): `fx_limit` (with the RM override question), `liquidity_need` (`max_sell_valor_days` 3, `max_lock_days` 91); config OPTIONAL until the lead adds it | FX fund rejected for P02, back with the override; P05: valör 4 rejected, 3 kept, missing kept + note; time deposit 32 days kept, a 120-day one rejected; rejected options never in `options` |
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
