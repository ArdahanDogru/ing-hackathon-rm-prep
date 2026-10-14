# Current portfolio projection and allocation gap — design

Date: 2026-10-14. Status: written for the user's review (sections 1–3 approved
in chat on 2026-10-14; the brief rule below agreed on the same day).
Milestones: contract v1.10 and config (lead), decision **D27**, API (lead),
web **W18**, narrator **N15**, eval and docs (lead).

## 1. Purpose

The RM sees today the model bands of the client's risk profile (D20) but not
how the client's money is split now. The user wants the tool to estimate the
current split from the persona information, let the RM correct it, and use the
gap to the model band to recommend better options. Example of the user: an
Agresif client whose portfolio is very stable (mostly cash) should see equity
options higher in the list.

A later AI agent (not in this design) will read the rankings and the
coefficients that make them; every value of this design must therefore be
machine-readable in the run record and the API.

## 2. Constraints from the brief

- Section 6: "Takımlar ek müşteri verisi toplamaz ve yeni persona üretmez.
  Alanlar eksik veya birbiriyle çelişkiliyse çözüm varsayım yapmak yerine
  durumu RM'e açıkça göstermeli…"
- Rule 3: "Veri çekilemediğinde sistem oran, fiyat veya müşteri bilgisi
  uydurmaz; eksikliği açıkça belirtir."
- "Nihai değerlendirme ve müşteri iletişimi RM tarafından yapılır."

**Rule of this design (agreed with the user 2026-10-14):** only values that
come from the persona text or from the RM change the ranking. Values from the
job table or the national average are a proposal ("tahmini senaryo, müşteri
bilgisi değildir"); they change the ranking only after the RM confirms or
corrects them. Until then the RM sees the missing data first in "Teyit edin".

## 3. Asset classes

The five classes of D19/D20 (`allocation.classes`): `nakit_benzeri`,
`borclanma`, `hisse`, `altin_doviz`, `dengeli`. FX deposits and FX cash count
as `altin_doviz` (as the FX funds do). Only the financial portfolio counts;
real estate and company stakes are out of scope. `dengeli` has no model band
(D20), so it has no gap.

## 4. The estimate of the current split

### 4.1 Sources, in order of priority

| Source id | What | Changes the ranking |
|---|---|---|
| `rm` | the RM typed the split | yes |
| `rm_confirmed` | the RM accepted the estimate with one click | yes |
| `persona_text` | a config rule matched a sentence about the client's assets in the persona text | yes |
| `profile` | a config rule matched the persona's `profil` (job) | no (proposal) |
| `national` | the national average of Turkish households | no (proposal) |

### 4.2 Config `holdings` (config/decision.yaml, lead)

- `national`: the split, its source and date. Value (TCMB Finansal İstikrar
  Raporu 2026-I, Tablo III.1.2, March 2026, look-through of funds by the lead;
  FX and precious-metal deposits → `altin_doviz`): nakit_benzeri 39,
  borclanma 10, hisse 10, altin_doviz 30, dengeli 11. URL in config. Gold
  "under the pillow" is not in the data (note in the doc).
- `profiles`: a list of `{match: [words], label, shares, rule, source}`.
  `match` words are compared with the normalised `profil` (the same Turkish
  normalisation as `priorities`); the first match wins. Values (all
  **[VARSAYIM]**: no Turkish split by job or age exists; the rule text says how
  each was derived from the national default; the family office row is
  adapted from the UBS Global Family Office Report 2025, Middle East):

  | Profile (match) | nakit | borç. | hisse | altın/döviz | dengeli |
  |---|---|---|---|---|---|
  | emekli | 32 | 22 | 10 | 26 | 10 |
  | ihracatçı, şirket sahibi | 22 | 22 | 13 | 33 | 10 |
  | teknoloji kurucusu, kurucu | 45 | 12 | 20 | 15 | 8 |
  | aile ofisi | 15 | 28 | 27 | 15 | 15 |
  | hekim, doktor | 28 | 12 | 13 | 25 | 22 |

- `text_rules`: a list of `{fields: [...], match: "<phrase>", class, range:
  [low, high], note}`. A rule exists only for a sentence that states the
  client's assets (not income, not goals). Start rules:
  - `durum` "mevduat ağırlıklı" → `nakit_benzeri` 60–90 (P01).
  - `durum` "şirket satışından gelen nakdi" → `nakit_benzeri` 50–100 (P03).
  P02 "Döviz geliri bulunuyor" is income, not a holding: no text rule.
- `spread`: points around a table value for the shown range (start 5).

### 4.3 Combination (pure function, decision D27)

1. Base split = the matched `profiles` row, else `national`.
2. Text rules: each matched rule fixes its class: point = the middle of its
   range, range = the rule range, source `persona_text`.
3. The rest (100 − the text points) is spread over the other classes in the
   proportions of the base; their source is `profile` or `national`; range =
   point ± `spread`, clipped to 0–100.
4. RM input replaces everything: every class gets the RM value (range =
   point), source `rm` or `rm_confirmed`.
5. The points always add up to 100 (rounded to one decimal; the rounding rest
   goes to the largest class).

## 5. The gap and the new criterion

- **Gap of a class** with band [low, high] and current point x: low − x when
  x < low (positive = underweight), high − x when x > high (negative =
  overweight), 0 inside the band. `dengeli`: no gap.
- **Active:** a class counts only when its source is `rm`, `rm_confirmed` or
  `persona_text` (section 2).
- **Criterion `allocation_gap`** (shown as "Portföy açığı"): for an option of
  class c, value = clamp(gap_c / `allocation_gap.scale`, −1, 1); a negative
  value is × `overweight_factor` (a small penalty); 0 for an inactive class,
  for `dengeli` and for a class without a band. The option's class is its D19
  `asset_class`.
- **Weight:** `weights.allocation_gap.base` × source factor ×
  (1 + `per_signal` × number of change signals, at most `max_signals`).
  - Source factor (config `allocation_gap.source_factor`): rm 1.0,
    rm_confirmed 0.75, persona_text 0.75.
  - Change signals (config `allocation_gap.signals`, normalised phrases in
    `oncelikler`, `acik_kisitlar`, `yatirim_amaci` and `rm_notu`): start list
    "çeşitlendirme", "mevduat yoğunluğunu azalt", "tek ürün veya tek varlık
    sınıfında yoğunlaşmama", "fırsat maliyetini azaltma". This is "what the
    client wants": a client who asks for change gets a stronger effect.
  - Start values: scale 30 points, overweight_factor 0.5, base 1.0,
    per_signal 0.5, max_signals 2. Tuned in eval.
  - When no class is active, the weight is 0 (the criterion is not in
    `score_parts`), so a run without text rules and without RM input scores
    exactly as before.
- **Hard rules do not change.** The risk ceiling and the other hard rules run
  before scoring; the gap never brings back a rejected option.
- **Reason text** (config): "{class_label} payı {source_label} %{current:.0f};
  {profile} model bandı %{low:.0f}–{high:.0f}." Inactive: "{class_label} payı
  bilinmiyor (tahmini senaryo); RM onayı bekleniyor." `source_label`: "RM'e
  göre", "RM onaylı tahmine göre", "persona metnine göre".
- **Stability (D25):** the new weight is varied like the others.
- The D19 class rule and the D20 examples do not change; the gap acts through
  the scores.

## 6. The RM flow

- While no class is from `rm` or `rm_confirmed`, the first `to_confirm` item
  is "Müşterinin mevcut portföy dağılımını alın (şu an tahmini senaryo)."
- The RM can: **confirm** the estimate as it is ("Tahmini onayla"), **edit**
  the split (one number per class, total 100 ± 0.5), or **reset** (remove the
  input). Each action makes a new run (the input is part of the run inputs,
  like question answers; the run id is deterministic).
- The RM input is synthetic client data typed by the RM; it is stored with the
  run in `data/runs/` (gitignored), never sent to an LLM other than as part of
  the facts pack of that run.

## 7. Contract v1.10 (lead)

- `AllocationBand` gets optional fields (defaults keep v1.8 constructors
  working): `current: float | None`, `current_low: float | None`,
  `current_high: float | None`, `current_source: str` ("" | the source ids of
  4.1), `current_ref: str` (rule id, profile label or source short text),
  `gap: float | None`, `active: bool = False`. Checks: 0 ≤ current_low ≤
  current ≤ current_high ≤ 100 when set; `active` only with an active source
  (`rm`, `rm_confirmed`, `persona_text`).
- New `HoldingsInput(shares: Mapping[str, float], origin: str)`; origin "rm" |
  "rm_confirmed"; shares cover all `allocation.classes`, each 0–100, total 100
  ± 0.5.
- `DecisionResult` gets `holdings_input: HoldingsInput | None = None` and
  `effective_weights: Mapping[str, float] = {}` (criterion → the weight used
  for this client after levels, priorities and signals; for the explanation
  panel and the later AI agent).
- `Backend.set_holdings(run_id, shares: Mapping[str, float] | None, origin:
  str = "rm") -> DecisionResult`; None removes the input.
- The narrative contracts (`NarrativeDraft`, sections) do not change.

## 8. API (lead)

- `RunView.allocation` rows get `current`, `current_low`, `current_high`,
  `current_source`, `current_ref`, `gap`, `active`.
- `RunView.holdings` = `{status: "estimate" | "persona_text" | "rm" |
  "rm_confirmed", sources: [{id, label, url, date}]}`.
- `RunView.effective_weights`.
- `POST /api/runs/{id}/holdings` with `{shares, origin}` or `{shares: null}` →
  the new RunView. 422 on a bad total or an unknown class.

## 9. Web (W18)

The "Model dağılım" card becomes "Mevcut ve hedef dağılım":

- One row per class: the model band as a light bar, the current value as a
  marker with its range, the gap as text ("−25 puan" / "bandın içinde").
- A badge per row: "RM", "RM onaylı", "persona metni" or "tahmini senaryo"
  (grey, with the source in a tooltip).
- A banner while the status is an estimate: "Portföy dağılımı bilinmiyor;
  aşağıdaki değerler tahmini senaryodur ve sıralamayı etkilemez."
- Buttons "Tahmini onayla", "Düzenle" (number inputs, the running total, save
  disabled unless the total is 100 ± 0.5), "Sıfırla".
- The fund card ("Neden bu öneri?", W16) shows the new criterion like the
  others.

## 10. Narrator (N15)

- The facts pack gets the allocation rows (class, band, current, source,
  gap, active).
- The LLM may mention a gap only for an active row; for an estimate row it may
  only say that the split is unknown and must be asked. The validator checks
  the numbers against the facts (existing number rule) and rejects a gap
  figure of an inactive row.
- No new section.

## 11. Eval and tests

- Unit (D27): combination (text rule + base, total 100, rounding), the gap
  edges, inactive classes give 0, the weight with signals, RM input replaces
  all, reset.
- Behaviour (eval, frozen snapshot):
  1. Without RM input, P02, P04 and P05 rank the same as without the feature
     (no text rule; estimate inactive).
  2. P01 (persona text "mevduat ağırlıklı", signal "mevduat yoğunluğunu
     azalt"): nakit-like options go down, borçlanma options go up.
  3. A P03 copy with RM input hisse 10 %, nakit 80 %: equity options rise; the
     ceiling still rejects what it rejected.
  4. Stability of the top 3 stays ≥ the D25 target.
- Contract tests for v1.10; API tests; web tests; narrator validator test.

## 12. Work split and order (at most 3 sessions)

1. Lead: contract v1.10, config `holdings` and `allocation_gap` (values of
   4.2 and 5), docs (decision.md section 17, web-ui.md W18, narrator.md N15).
2. ing-decision: D27 (estimate, gap, criterion, effective weights, D25).
3. Lead: API. In parallel ing-web: W18, and ing-narrator: N15.
4. Lead: eval on a new frozen snapshot, then the deliverables, the README and
   the deck.

## 13. Out of scope

- Real bank holdings, amounts in TL, real estate, company stakes.
- A look-through of `dengeli` funds into classes.
- Tactical house views; the AI agent itself.
