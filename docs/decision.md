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

D12 as built (2026-10-10): a buyable fund carries
`ConstraintResult("not_buyable", passed=True, "TEFAS'ta alıma açık.", (status row,))`
before `risk_ceiling`; a fund that fails both has both failed results. Fees:
`N -= (entry + exit) / 100 / horizon years`, only where N exists; the fee text is
added to the return reason. With `fund_detail` the assumption `kind_proxy` is
replaced by `kind_proxy_valor`. The status, valör and fee rows are in the
option's `evidence_ids`. Valör check on the real snapshot: money market sell
valör 0, equity 2, foreign equity 3.

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

D13 as built (2026-10-10): the question `q:override:fx_limit` (non-blocking,
`about` = the constraint text) comes from `read_persona`, so its answer is
checked like any answer; no answer or "uygula" → the rule applies. An answered
unknown constraint with effect `fx_limit` or `liquidity_need` is enforced the
same way. Failed rules in the order `not_buyable`, `risk_ceiling`, then the
constraint rules in the order of `acik_kisitlar`. Scored options carry passed
entries only for `not_buyable` and `risk_ceiling`. `fx_limit` has no evidence
ids (the tag comes from the fund name); `liquidity_need` cites the valör row or
the time deposit rate row. The valör note counts only listed funds. Real
snapshot: P02 14 FX funds rejected (override question open); P05 2 funds
rejected by `liquidity_need`, the 32-day e-Vadeli kept.

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
| estimate: liquidity from the kind table because the sell valör is missing (with `fund_detail`; D14) | × 0.8 |

A row with several flags takes its lowest factor. Today: typical fund 0.9,
fund with unknown risk 0.63, deposit 0.9.

**`stability`**: compute the display order again 30 times (26 before D9, 28
before D10 added the underperformance penalty); each
time one number is ×0.8 or ×1.2: one of the 7 raw weights (then normalize again)
or one of the 8 penalty maxima. `stability` = share of these runs in which the option is in
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
| D14 | (found by eval E2, 2026-10-10) a fund whose liquidity falls back to the kind table because its sell valör row is missing gets the estimate factor `confidence.liquidity_proxy` (0.8; optional config); before, excluding `tefas_detail` raised the confidence (ZPO 0.63 → 0.70) | with the valör row → no factor; without it → × 0.8; excluding `tefas_detail` never raises a confidence |
| D15 | (found by the first full eval, 2026-10-10; rule decided by the user) **short history**: a fund without a usable return of 3 months or longer (only `fund_return_1m`) is graded but rejected with rule `short_history`, reason "Yeterli geçmiş yok (yalnızca 1 aylık getiri)" / "Not enough history"; exception: appetite 1 (Agresif) keeps it in the list with the `track_record` penalty and the reason text; the 1-month row is its evidence. A fund with **no data row at all** is never listed (removed and counted in a data-quality note). Config `short_history: {min_period: 3m, allow_appetite: 1.0}` OPTIONAL | P05 without `tefas_detail`: VKR/ZPO/ZTV rejected with the reason; for an Agresif persona listed with the penalty; no listed option without evidence ids |
| D16 | (web UI, 2026-10-11; docs/web-ui.md section 4) **warning audience and `to_confirm`** (contract v1.3): config `warnings.audience: {concentration: client, fx_exposure: client}` (a code not in the table → `rm`); config `to_confirm: {<assumption key>: <command template>}`, first entry `deposit_tier: "Yatırım tutarını sorun: {tier} dilimi varsayıldı."`; `DecisionResult.to_confirm` = the templates of the assumption keys that the run emitted, in emit order. Both config sections OPTIONAL until the lead adds them (without them: all `rm`, `to_confirm` empty) | audience from config; `deposit_vs_market` always rm; P01 gets the tier command; without config nothing changes (same `run_id` as before) |
| D17 | (web UI) **display facts** (section 9): `rmprep.decision.display.display_facts(result, evidence, config) -> dict[str, DisplayFacts]` for every scored and rejected option; config `display.why: {<criterion>: <text with {access} {risk} {ret1y}>}` OPTIONAL | facts for every option; returns cite their rows; real 1-year = net of stopaj, then CPI (no fees); no CPI → none; time deposit `lock_days` = `term_days`; `why` uses the persona's own wording, no score numbers |
| D18 | (web UI) **talking points** (contract v1.3, section 9): config `talking_points: {order, deposit_keywords, texts}` OPTIONAL (without it: none) | P01 gets `deposit_real` first, without ING numbers; no deposit point without the keyword; figures in Turkish format with a sign; each point cites evidence and only scored options; `needs_rm_input` → none |
| D19 | (2026-10-12, error analysis) **diverse recommendations** (section 10): `asset_class` per option, criterion `risk_fit` with profile bands instead of `low_risk`, `DecisionResult.recommended` with the class rule; config sections OPTIONAL until the lead adds them (without them: the old behaviour, `recommended` = the first three group heads) | P01 top 3 unchanged; P02 and P04 at most one `nakit_benzeri` in `recommended` and at least two classes; a fund inside the band beats an equal fund below it; Muhafazakâr unchanged by the class rule; `recommended` ⊆ scored options, ≤ 3; the reason text names the class rule; talking points use `recommended` |
| D20 | (2026-10-13) **model allocation bands** (section 11): `DecisionResult.allocation` (AllocationBand per class: band, source, inferred, best option, note) and `allocation_notes` (holding hints) + the to_confirm item; config `allocation` OPTIONAL until the lead adds it | bands per profile from config; dengeli without band; best option per class in score order within the hard rules; note `ceiling` for P01 hisse; `negative_real` for gold; P01 gets the deposit hint and the to_confirm item; P02 none; without config allocation = () |
| D21 | (2026-10-13, found in D20) **risk estimate by asset class**: a fund without an SPK risk row gets the estimate of its D19 asset class, not of its TEFAS umbrella kind (a gold participation fund was estimated at risk 1–2 from the Katılım umbrella and passed a ceiling of 2). The estimate is data-based: the upper quartile (configurable `risk_estimate.by_class_quantile`, default 0.75) of the known SPK risk values of the same class in the snapshot, rounded up; fallback to the old kind table when the class has fewer than 5 known values; the assumption text names the rule | KZL (gold participation, no risk row) is estimated from altin_doviz and no longer passes P01's ceiling; funds with a risk row unchanged; the estimate is deterministic for a snapshot |
| D6 *(optional, after the MVO)* | Jev text mapper (below) | — |

After D5 the lead wires `python -m rmprep decide --persona P01 [--snapshot ID]
[--exclude SRC ...] [--answer QID=VALUE ...]` in `cli.py` and runs the report on
the real snapshot with the user for tuning. Wired 2026-10-10; extra option
`--personas DIR` (default: the folder above the project, `../p0*.json`).

## 9. Display data for the web UI (D16–D18, 2026-10-11)

The web UI (docs/web-ui.md) needs values that are business rules, so they come
from this module and not from the API.

```python
@dataclass(frozen=True)
class Fact:
    value: float
    evidence_id: str            # "" when the value comes from config (time deposit term)

@dataclass(frozen=True)
class DisplayFacts:
    option_id: str
    returns: Mapping[str, Fact]          # keys among "3m", "6m", "1y" (percent); a missing period has no key
    real_1y: Fact | None                 # percent, after stopaj and CPI (4.1b, no fees); evidence id = the 1y return row
    risk: Fact | None                    # SPK risk value 1..7
    sell_valor_days: Fact | None
    lock_days: int | None                # time deposit: time_deposit.term_days; else None
    why: tuple[tuple[str, str], ...]     # (persona priority as written, text)
```

`real_1y` is a fact of the fund, not of the client: the 1-year return after
the stopaj of its kind, then CPI; fees and the client's horizon are not used.
`why`: one line per persona priority that the priority table (section 3) maps
to a criterion of the option, with the text of `display.why.<criterion>`; no
score numbers.

**Talking points (D18).** At most 3, in `talking_points.order`, each only if
its condition holds; "top 3" = `rmprep.grouping.top_heads(options, 3)`:

| Code | Condition | Figure |
|---|---|---|
| `deposit_real` | `durum` contains a `deposit_keywords` entry (Turkish lower-casing) | real 1-year return of the **EVDS market** deposit rate (`deposit.market_entity`) after the deposit stopaj and CPI; never an ING row |
| `best_alternative` | a first recommendation with a real 1-year return | its real 1-year return; the text says that it is a past return |
| `access` | `likidite_ihtiyaci` is not low, or a priority maps to liquidity | the slowest sell valör of the top 3: "Aynı gün" / "n iş günü" |
| `risk_fit` | always (top 3 not empty) | "en fazla <max> / 7"; the text names the client's ceiling |

Percent figures: sign and comma, the minus is U+2212 ("−%8,3", "+%8,7").

**As built (D16–D18, 2026-10-11, ing-decision).**

- Helpers: `display.access_text(facts, config)` ("Aynı gün" / "n iş günü" /
  "Vade sonunda (32 gün)" / None, config `display.access`) and
  `display.tr_percent(x)`; the API and D18 use them (one rule).
  `display.facts_of` is public (used by `talking.py`).
- Deposit and time deposit facts: `returns = {"1y": the published annual rate}`,
  `real_1y` from it (time deposit with the 32-day renewal of `_net`), risk and
  sell valör none; time deposit `lock_days = time_deposit.term_days`.
- `real_1y` needs `real_return` and CPI; a missing stopaj row counts 0 (as
  D9); no fees; no stopaj on a loss. `sell_valor_days` needs `fund_detail`.
  Facts respect excluded sources.
- `why`: persona priorities in persona order, matched with Turkish
  normalization, shown as written; a criterion without a text, or a line
  whose value is missing, gives no line; two priorities with the same
  criterion give two lines. `display.why` needs `display.access`.
- `to_confirm`: the templates of the assumption keys that the run emitted, in
  emit order (standard assumptions first, then the persona ones), each once;
  a `needs_rm_input` result has them too. Config checks: audience codes from
  the known list, values `client | rm`; `to_confirm` keys are keys of
  `texts.assumptions`, only the field `{tier}`.
- Talking points: `deposit_real` cites the market, CPI and stopaj rows, no
  option ids; skipped without `real_return`, the market row or CPI.
  `best_alternative` cites the 1y row, CPI and stopaj of the first head;
  skipped without its `real_1y`. `access`: the condition is a liquidity level
  above 0 or a priority that boosts liquidity; skipped if one of the top 3 has
  no valör / term. `risk_fit`: deposit kinds count as risk 1 (cited by their
  rate row); skipped if a listed fund has no risk row; needs `figure` in its
  texts. Adding the sections changes `config_hash`, so the run ids change.
- Real check (snapshot 20261010-183835-6813): P01 `deposit_real` +%4,9,
  `best_alternative` PPN +%7,4, access "Aynı gün"; P02/P05 GO6 +%8,7, access,
  "en fazla 1 / 7"; P03 GBV +%2,5, "en fazla 7 / 7".
- The non-blocking question texts are commands now ("… müşteriyle
  netleştirin"), because "Teyit edin" shows them.
Texts: `talking_points.texts.<code>: {label, text}` with `{figure}`, `{label}`,
`{max}`, `{ceiling}`.

## 10. Diverse recommendations: asset classes and risk fit (D19, approved by the user 2026-10-12)

**Finding (error analysis, 2026-10-12).** On the frozen eval snapshot, four of
five personas got only cash-like funds at SPK risk 1 as their top 3: P01
Muhafazakâr, but also P02 and P04 (Dengeli, ceiling 5) and P05 (Temkinli).
Two pairs had identical sets (P01 = P04: Nurol Para Piyasası, İstanbul KV
Borçlanma, Ak Para Piyasası Katılım; P02 = P05: One Portföy Para Piyasası,
İstanbul KV Borçlanma, Ak Para Piyasası Katılım); İstanbul KV Borçlanma and Ak
Para Piyasası Katılım were in all four. (Corrected 2026-10-12: an earlier text
said "the same top 3" for all four.) Causes:

1. The market of the last year: TL cash-like funds had the best real returns
   (+7–9 %); balanced funds +3 %, equity about 0 %, gold −13 % (TÜFE and stopaj
   applied).
2. No criterion rewards the use of the client's risk budget: `low_risk` has a
   positive weight for Dengeli too, and the `principal` penalty hits risk-5
   funds (P04: a risk-5 mixed fund scores 0.02, money market 0.91).
3. Diversity works on `fund_kind`, but money market, short-term debt and
   participation money market are one asset class (short-term TL cash).

Missing SPK risk values are not a cause (3–10 % of the funds of each kind).

**Rules (D19).**

- **Asset class of each option** (`ProductOption.asset_class`, contract v1.6):
  config `asset_classes`:
  - `by_kind`: deposit, time_deposit, money_market → `nakit_benzeri`; debt →
    `borclanma`; participation → `borclanma`; variable, mixed, fund_of_funds →
    `dengeli`; equity → `hisse`; precious_metals → `altin_doviz`;
  - `by_name` (checked first, Turkish upper case, whole words): "PARA
    PİYASASI" → `nakit_benzeri`, "KISA VADELİ" → `nakit_benzeri`; an FX fund
    (`fx = true`) → `altin_doviz`.
- **Risk fit** (criterion `risk_fit`, replaces `low_risk`): config
  `risk_fit.bands` per risk profile — Muhafazakâr [1, 2], Temkinli [2, 3],
  Dengeli [3, 5], Agresif [4, 7]; value 1.0 inside the band, minus
  `risk_fit.per_step` (0.25) for each level below the band (above the ceiling
  the fund is rejected anyway), at least 0; unknown risk → the existing
  `risk_unknown` rules. The weight of `risk_fit` = the old `low_risk` weight
  at appetite 0 (base 1.0, no appetite term). The priority boosts that pointed
  at `low_risk` ("sınırlı dalgalanma", "uzun vadeli dayanıklılık") point at
  `risk_fit`. The bands are an **assumption** (config comment), to be checked
  with the mentors.
- **Recommended top 3** (`DecisionResult.recommended`, contract v1.6): the
  engine chooses them, in score order, from the group heads; when the client
  is Dengeli or Agresif, or has the diversity priority, at most
  `recommend.max_per_class` (1) option per asset class, and at most
  `recommend.max_cash_like` (1) `nakit_benzeri` option; if fewer than 3
  classes have an option, the rule relaxes in that order. Muhafazakâr and
  Temkinli clients without the diversity priority keep the plain score order.
  The dashboard, the brief, the talking points (D18) and the meeting text use
  `recommended` (via `grouping.recommended(result)`; `top_heads` stays the
  fallback for results without it).
- **Explanation**: the reason of a recommendation that the class rule moved
  up says so ("Çeşitlendirme: farklı varlık sınıfından en iyi seçenek"); the
  assumptions list the class rule when it applied.

**As built (D19, D19b, 2026-10-12).** With the class rule the engine picks
from **all** ranked options in score order, not only the group heads (a head
can hide another class: a long-term debt fund behind a short-term debt head,
both kind `debt`); so a recommended option can be a group alternative.
`recommend.min_real_return` (0.0) blocks class-rule picks with a negative real
1-year return (the last relax step fills by plain score order without it).
Tuning on 20261010-183835-6813: `per_step` 0.5 and `risk_fit` weight 2.0 (with
0.25 the Dengeli picks stayed at risk 2); by_name "BORÇLANMA ARACI" →
borclanma. Measured: P01 unchanged (3× nakit, risk 1); P02 nakit r2 +8,0 ·
borclanma r2 +8,4 · dengeli r3 +12,8; P04 borclanma r3 +5,9 · nakit r2 +6,7 ·
dengeli r3 +3,3; P05 3× nakit at risk 2 (its band); P03 dengeli r6 · hisse r7
· a participation fund r5 +26,3.

**Expected effect** (to be measured): P01 unchanged; P02 and P04 get one
cash-like option plus options from two other classes inside their band; P03
unchanged or more varied; P05 at most one cash-like option only if it has the
diversity priority (it has not, so unchanged unless its band moves the
order). The eval gets regression scenarios for these (E9).

## 11. Model allocation bands (D20, approved by the user 2026-10-13)

The RM sees, for the client's risk profile, a **strategic model allocation as
bands** (min–max % per asset class of D19) and the best option of each class
for this client. **No current shares and no amounts**: the personas do not give
the client's holdings (only P01 has a sentence, "Varlığı TL mevduat
ağırlıklı"), and the brief forbids collecting more client data. A current-
portfolio input with a gap analysis is **future work** (it needs the bank's
holdings data).

**Bands (config `allocation.bands`, % per class):**

| Class | Muhafazakâr | Temkinli * | Dengeli | Agresif |
|---|---|---|---|---|
| nakit_benzeri | 10–20 | 5–20 | 5–10 | 0–5 |
| borclanma | 60–70 | 40–60 | 30–40 | 5–10 |
| hisse | 10–20 | 20–40 | 40–50 | 70–85 |
| altin_doviz | 5–10 | 5–15 | 10–15 | 5–10 |
| dengeli | — | — | — | — |

Source: Ata Yatırım, "Yatırım Portföyü Oluşturma Stratejileri ve Rehberi",
28.04.2026, table "Risk Profillerine Göre Örnek Portföy Yapıları"
(https://atayatirim.com.tr/blog/yatirim-portfoyu-olusturma-stratejileri-ve-rehberi);
its gold/commodity column is our altin_doviz (no public FX band). Cross-checks:
Schwab risk profiles, Vanguard LifeStrategy, SPK BES Standart Fon limits.
\* Temkinli has no source: our inference between Muhafazakâr and Dengeli,
marked `inferred: true`. `dengeli` (multi-asset funds) has no band: these funds
are a fund type, not an asset class; they are listed without a target. The bands
are strategic; tactical house views (e.g. more cash at high TL rates) can be
outside them. To be confirmed with the mentors (question 6).

**Engine output (contract v1.8):** `DecisionResult.allocation:
tuple[AllocationBand, ...]` in class order, each with `asset_class`, `low`,
`high` (None for dengeli), `source` (short text), `inferred`, `option_id` (the
best scored option of the class for this client, in score order, None if
none), and `note` (config texts, first that applies): `ceiling` — the class has
funds but none within the client's risk ceiling ("risk tavanı nedeniyle uygun
fon yok"); `none` — no scored option; `negative_real` — the best option has a
negative real 1-year return ("son 1 yıl reel −%13: önerilmiyor" with the
figure). `DecisionResult.allocation_notes: tuple[str, ...]` holds qualitative
holding hints from the persona text (config `allocation.holding_hints`:
keyword in `durum` → text, e.g. "mevduat ağırlıklı" → "Dosyaya göre varlık TL
mevduat ağırlıklı: nakit benzeri bandı aşılıyor olabilir."); when a hint
applies, `to_confirm` gets "Mevcut portföy dağılımını sorun." Without the config
section: `allocation` = () (no change).

**Screen (W13):** the "Öneriler" switch gets a third view **Dağılım**: one row
per class with the band as a bar, the source (a "*" for an inferred band with
its tooltip), the best option (short name, real 1-year return, risk) or the
note, and the holding hints above the rows. A click on an option opens the fund
card. The meeting text does not change in this step.

## 12. Stale tax and inflation inputs (D22, approved by the user 2026-10-14)

The real return (4.1b) uses one stopaj row per product type and the annual
TÜFE row. These inputs are manual or monthly; a stopaj row gets the flag
`stale` after its end date (docs/ingest.md I7) or when it is older than the
quantity's `max_age_days`. Until now a stale input only lowered the confidence
(× 0.7) and gave a generic data-quality note.

- New `DecisionWarning` code `stale_tax_input`, audience RM only (it never
  goes into the client text). One warning per result when any stopaj row or
  the TÜFE row that the result used for a real return is flagged `stale`;
  `evidence_ids` = those rows; `option_ids` empty (the whole result).
- Text from config (`texts.warnings.stale_tax_input`, lead): "Vergi veya
  enflasyon verisi güncel değil ({entities}); reel getiriler bu değerlerle
  hesaplandı. Güncel oranı teyit edin." `{entities}` = the entity names of
  the stale rows, joined with ", ".
- `to_confirm` gets "Güncel stopaj oranını ve TÜFE'yi teyit edin." (config
  `to_confirm.stale_tax_input`) once per result, with the same condition.
- No change to scores or ranking; the confidence factor stays.
- A `needs_rm_input` result has no warnings (section 6), so no change there.
- Tests: a stale stopaj row gives the warning and the to_confirm item; a
  stale TÜFE row too; fresh rows give neither; a stale row of a product type
  that no scored option uses gives nothing; the warning is RM-only.

## 13. Asset class from the holdings (D23, approved by the user 2026-10-14, option A)

The D19 asset class comes from the umbrella type and the fund name. For
multi-asset funds this is a guess: all "Değişken" funds are `dengeli`, even
when they hold 80 % equities. The holdings (docs/ingest.md I8, quantity
`fund_holding_share`, entity `<code>/<kiymetTip>`) give the real split.
Analysis of snapshot `20261014-005625-c76a` (775 funds with holdings): option
A changes about 210 funds, 163 of them Değişken `dengeli` → `hisse`.

Option A: the holdings decide only where the umbrella type does not fix the
contents. Para Piyasası, Hisse Senedi, Kıymetli Madenler and TL Borçlanma
funds keep the class of their umbrella type and name (regulation fixes what
they hold; a single day's holdings can be odd, e.g. an equity fund at 100 %
cash).

- Config `asset_classes.by_holdings` (lead):
  - `kinds`: [variable, mixed, fund_of_funds, participation] — the holdings
    decide for these fund kinds;
  - `fx_debt_kinds`: [debt] — for these kinds only an `altin_doviz` majority
    counts (FX bonds such as "Yabancı Borçlanma Araçları");
  - `min_share`: 50 (%);
  - `labels`: class → list of `kiymetTip` texts, plus the groups `fon`
    (fund shares: no look-through) and `ignore` ("Diğer", futures margin
    cash). The 40 texts of 2026-10-14 and their classes are in the analysis
    script `scripts/analysis/varlik_impact.py` (lead).
- Matching: lower case, then keep only `a-z0-9` (simple and robust to
  spelling variants; the pages themselves have correct Turkish letters); two
  labels with the same folded key are a config error. An
  unknown text → `ignore` for this fund and one data-quality note per text
  (`unknown_holding_type`, with the count).
- Shares: the sum per class of the positive shares, without `ignore`, as %
  of their total. The class with ≥ `min_share` wins; a `fon` majority or no
  holdings rows → the old rules; no class reaches `min_share` → `dengeli`.
- Order in `asset_class()`: (1) FX name words → `altin_doviz`; (2)
  `fx_debt_kinds` with an `altin_doviz` majority → `altin_doviz`; (3)
  `by_name`; (4) `by_holdings` for `kinds`; (5) `by_risk`; (6) `by_kind`.
  The `by_name` entry "ÇOKLU VARLIK" → `dengeli` is removed from the config,
  so that the holdings decide for those funds.
- Explanation: an option whose class comes from the holdings gets the reason
  "Varlık sınıfı: portföyün %{share:.0f}'i {label} (TEFAS portföy dağılımı)."
  (config `texts.reasons.holdings_class`, lead) with the evidence ids of the
  holdings rows of that class; `{label}` = the class label (hisse senedi,
  borçlanma araçları, nakit benzeri, altın ve döviz).
- Everything that uses the class follows: the D19 class rule, the D20
  allocation rows, the D21 risk estimate (quantile per class).
- Tests: a Değişken fund with 80 % equities → `hisse`; 45/40/15 → `dengeli`;
  a `fon` majority → old rule; a Para Piyasası fund with 90 % bonds stays
  `nakit_benzeri`; a Borçlanma fund with 90 % FX debt → `altin_doviz`, with
  TL bonds stays `borclanma`; a name rule wins over the holdings ("ALTIN"); an
  unknown text gives the note; folding of broken letters; the reason with
  evidence ids; no holdings rows → today's result (the fixtures do not
  change).
- As built (merged 2026-10-14, `decision@4f1b096`; config `by_holdings` and
  texts added by the lead):
  - new key `class_labels` (class → text for `{label}`; every class of
    `labels` except `fon`/`ignore` needs one); new text
    `texts.data_quality.unknown_holding_type` ({text}, {count}); both texts
    are required when `by_holdings` is present;
  - the quantity is a code constant (`universe.HOLDINGS_QUANTITY =
    fund_holding_share`); only the latest `as_of` day of a fund counts;
  - a `dengeli` result from the holdings gets no reason text and no extra
    evidence ids (the template needs one class share); the reason is added
    to the return reason (like the class-rule text); the holdings rows go into
    `ScoredOption.evidence_ids`, not into the confidence rows;
  - the unknown-text note counts only listed funds of `kinds` and
    `fx_debt_kinds`; `fold()` is in `decision/text.py`;
  - bug fixed with it: since I8, `build_universe` read each `<code>/<type>`
    entity as a fund code (a wrong `removed_no_entity` note on new
    snapshots); an entity with "/" is not a fund code now.
  - Check on `20261014-005625-c76a` (holdings rows rebuilt from the stored
    pages): 214 funds change class (122 variable, 33 fund_of_funds, 7 mixed,
    3 participation `dengeli` → `hisse`; 2 debt → `altin_doviz`), 0 unknown
    texts.

## 14. Confidence without tax or inflation data (D24, 2026-10-14)

Found by the eval on the new frozen snapshot `20261014-102329-8fca` (free
`--no-llm` pass): with the manual source excluded (no stopaj, no TÜFE), the
fund options kept confidence 1.00, and the check "missing data is shown"
failed in `data-p01-no-manual` and `data-p03-no-manual`. Before 2026-10-14
every TEFAS row had `needs_check` (0.9), which held all confidences at 0.90
and hid the gap.

- New optional factor `confidence.real_return_missing` (0..1; config 0.8,
  like the D14 proxy): applied when the real return is configured but cannot
  be computed for the option: no TÜFE row, or no stopaj row for its product
  type (the stopaj is then taken as 0).
- Without `real_return` in the config, or without the key: no change.
- Built by the lead (small change; `ing-decision` was stopped): code in
  `decision/confidence.py` and `decision/config.py`, tests in
  `tests/decision/test_real_return_confidence.py`.

## 15. Stability of the recommended top 3 (D25, approved by the user 2026-10-14)

Stability (section 5) = the share of the 30 perturbed rankings (each raw weight
and each penalty maximum × 0.8 and × 1.2, one at a time) in which an option is
in the first `stability.size` places (20). The D19 class rule picks from the
whole order, so a recommendation can come from far down (new frozen snapshot
`20261014-102329-8fca`: P03 IDY at place 42 and OKT at place 57). Such an
option always got 0.00, and `low_stability` (positions 1–3 only) did not see
it — the stability was not meaningful for the top 3.

- For each perturbed run, the engine also applies the recommendation rule
  (`recommend.py`, the same function and config as the real result: the class
  rule when it applies, else the plain order) to that run's order.
- An option in the result's `recommended` gets the stability = the share of
  runs in which that rule recommends it again ("does this recommendation
  hold?"). All other options keep the top-20 share.
- `low_stability` fires for any recommended option with stability below
  `warnings.low_stability_below` (0.5), not only for display positions 1–3;
  its `option_ids` = those options. The text stays.
- No config change; no change to scores, order or the recommended set.
- Tests: a class-rule pick far down the order that stays its class's best in
  every run → stability 1.0; a pick that loses its place to another option of
  its class in half the runs → ≤ 0.5 and the warning; a client without the
  class rule (P01-like) → recommended stability = share of runs in the plain
  top 3; options outside the top 3 unchanged; deterministic.
- As built (merged 2026-10-14, `decision@5e0b07e`): `confidence.stability(...,
  recommended=(), pick=None)`; the engine passes `recommend.choose` on the
  rows of each perturbed order (memoized), and now runs `choose()` on the
  scored rows before the options are built (same result). `low_stability`
  gives one warning per shaky recommendation (the text has one
  `{stability}`), in recommended order; display places 1–3 that are not
  recommended no longer warn. Check on `20261014-102329-8fca`: P03 IDY (fund
  place 41) and OKT (56) 0.00 → 1.00; every recommendation of P01–P05 is
  ≥ 0.83, so no `low_stability`; 5 personas in 6.5 s.

## 16. Exchange-traded funds and shares (D26, approved by the user 2026-10-14)

The universe gets the Borsa İstanbul products: the 37 ETFs (BYF, data from
TEFAS, docs/ingest.md I10) and the 628 shares (data from the Borsa İstanbul
end-of-day bulletins, I11). Not included, with the reason in the data-quality
notes: warrants and certificates (complex, leveraged products that need a
separate appropriateness test), exchange-traded real-estate and venture capital
funds, bonds and eurobonds (a later phase).

- **Contract v1.9:** option kinds `etf` (`etf:<TEFAS code>`) and `stock`
  (`stock:<code>`); neither has a `fund_kind`; `etf` may carry the FX tag.
- **ETFs:** the fund rules and criteria apply (returns, SPK risk value,
  holdings → class D23, size), with these differences: `not_buyable` does not
  apply (bought on the exchange, not on TEFAS); liquidity from the kind table
  (T+2 settlement: 0.8); quality and the small-fund penalty use the fund size
  only (TEFAS gives no investor count for ETFs); stopaj row of the fund type
  (config `real_return.stopaj.etf`, lead fills it from the source).
- **Shares, risk value:** the SPK method of the fund guide (Yatırım Fonlarına
  İlişkin Rehber 9.3.2.1, table changed 12.10.2023), from `stock_volatility_1y`:
  annual volatility % [0, 2) → 1, [2, 5) → 2, [5, 10) → 3, [10, 15) → 4,
  [15, 20) → 5, [20, 30) → 6, ≥ 30 → 7; then at least `stock.risk_floor` 6
  (one company's risk is concentrated; volatility does not show it)
  **[VARSAYIM]**. One year of data instead of five: the value is marked as an
  estimate (confidence × 0.7, as `risk_estimate`) and the reason names it. No
  volatility row → risk 7 (estimate).
- **Shares, other criteria:** return from `stock_return_*` (period as for
  funds; no 3y/5y → the 1-year return with the shorter-period factor);
  liquidity from the kind table (T+2: 0.8); income 0.2, simplicity 0.4 (kind
  table); principal by risk as for funds; quality = the percentile of
  `stock_turnover_3m` among the shares (BIST 100 members get it ≥ 0.5); the
  small-fund penalty applies when the 3-month mean turnover is below
  `stock.min_turnover_try` (config, start 10 million TRY); stopaj row
  `real_return.stopaj.stock` (lead fills it from the tax source; rule 7).
- **Classes:** shares → `hisse`; ETFs → D23 holdings, else by name ("ALTIN",
  "GÜMÜŞ" → `altin_doviz`; "DOLAR", "EUROBOND" → FX tag; "TLREF" → `nakit_benzeri`),
  else `hisse`.
- **Short list and top 3:** the caps per kind of section 4.5 count `etf` and
  `stock` as kinds of their own; at most `stock.max_in_top3` (1) share in the
  recommended top 3. A share in the top 3 gives the RM warning
  `single_stock` ("Tek bir şirketin payı: şirkete özgü risk; çeşitlendirmeyi
  RM değerlendirsin."); text in config.
- **Narrator:** the facts carry the kind; risk notes per kind in
  `config/narrator.yaml` (lead).
- Tests: an ETF with TEFAS status "Platformda İşlem Görmüyor" stays in; the
  volatility bands (each edge); the floor; no volatility row → 7, estimate;
  a share above the ceiling is rejected; the share cap in the top 3 and the
  warning; turnover quality; ETF class by name and holdings; the excluded
  groups note; without the new sources the results are unchanged.

Details fixed in D26 (merged 2026-10-14, decision@4f90384; config by the lead):

- **Kind detection:** an ETF is a fund code whose `EntityInfo.source` =
  `etf.source` (checked before the fund_kinds table, so no Serbest or umbrella
  rule). A share is an entity with `stock_*` rows and `EntityInfo.source` =
  `stock.source` (another source → `removed_unknown_kind`; no entity →
  `removed_no_entity`).
- **ETFs:** `not_buyable`, the entry and exit fees and the sell valör are
  fund-only (an ETF is bought on the exchange); no `liquidity_proxy` factor.
  Quality = the size percentile among the scored ETFs; size penalty = 1 −
  size / `fund_size_min.total_value_try` (no investor part; no size row → 1).
  ETFs count in the D21 class quantiles. Class order: FX tag → holdings
  majority (D23; a fund majority or no counted rows: go on; no class ≥
  `min_share` → `dengeli`) → `etf.by_name` → `etf.default_class`.
- **Shares:** the risk is "known" for the ceiling (a share above the ceiling
  is rejected; evidence = the volatility row, none without it), but the
  confidence is × `confidence.risk_estimate` and there is no `risk_unknown`
  penalty. The reason of `risk_ceiling` is `texts.constraint.stock_risk` /
  `stock_risk_missing`. Returns from `stock_return_*` with the horizon
  fallback; the shorter-period factor and the track_record penalty as for
  funds (3y client: the 1-year return). `short_history` (D15) and
  `removed_no_data` apply to ETFs and shares too. Quality: the turnover
  percentile among the scored shares; `stock_bist100` = 1 → at least 0.5; no
  turnover row → 0 (BIST 100 still 0.5). Size penalty = 1 − turnover /
  `stock.min_turnover_try`, no row → 1. Principal by risk as for funds.
- **Top 3:** `stock.max_in_top3` holds in the plain path (group heads; a share
  head over the cap is skipped and the next group head comes in) and in every
  stage of the class rule, also the last fill stage (so `recommended` can have
  fewer than 3). D25 stability uses the same rule. `single_stock`: one
  warning, `option_ids` = the recommended shares, no evidence ids.
- `excluded_exchange_groups`: one data-quality note when the universe has an
  ETF or a share.
- The access talking point is skipped when a top-3 option is an ETF or a
  share (no evidence row for T+2). The access label is
  `display.access.exchange` (TR/EN); `access_text(facts, config, lang)`.
- Kind table: `etf` liquidity 0.8, income 0.2, simplicity 0.6; `stock` 0.8,
  0.2, 0.4 (income and simplicity: the worker's proposal, accepted by the
  lead).

Details fixed in D26b (merged 2026-10-14, decision@00f5ad4):

- `stock.exclude_markets`: a share whose market code (the part of
  `EntityInfo.category` after the last "·") is in the list is removed before
  scoring. It is not in the options or in the rejected list; it is counted
  per market in `Universe.removed_stock_market`. One data-quality note
  `texts.data_quality.removed_stock_market` with `{count}` (all removed
  shares) and `{markets}` (the codes, sorted). A missing key = no exclusion.
  **[VARSAYIM, lead 2026-10-14]:** `[W, S]`; W = Yakın İzleme Pazarı, S =
  Nitelikli Yatırımcı İşlem Pazarı or the pre-market platform (the code is not
  confirmed). On snapshot 20261014-164524-42c2: 590 shares kept, W 20 and
  S 18 removed.
- D20 allocation: a share is never the example option of a class band (one
  company is not an example of a class); an ETF or a fund can be. Shares are
  left out of the band computation, also for the ceiling note; a class with
  only shares gets no example and the note "none".

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
