# Decision layer

Status: **to be designed (step D, the user with ing-lead).** The contracts the
layer produces are in `src/rmprep/contracts.py` (DRAFT until this file is done):
`Persona`, `ProductOption`, `ConstraintResult`, `ScoredOption` (`confidence`
and `stability` in 0..1), `RejectedOption`, `ClarificationQuestion`,
`DecisionWarning`, `DataQualityNote`, `DecisionResult` (`run_id`,
`config_hash`, `state` = `ready` | `needs_rm_input`, questions, assumptions,
warnings, data-quality notes, `rm_status` = pending | approved | rejected).
Input: `EvidenceSet` (from ingest) + one `Persona`.

## Facts to design against (p01–p05 checked 2026-10-10)

- Persona values are free Turkish text, not enums.
  - `risk_profili`: Muhafazakâr, Temkinli, Dengeli, Agresif.
  - `yatirim_ufku`: "1-3 yıl", "5+ yıl".
  - `likidite_ihtiyaci`, `gelir_nakit_akisi_ihtiyaci`, `anapara_koruma_tercihi`:
    Düşük / Orta / Yüksek.
  - `doviz_maruz_kalma_tercihi`: "Sınırlı", "Açık", "Çeşitlendirilmiş",
    "Mevcut döviz gelirini dikkate alarak kontrollü".
  - `oncelikler`, `acik_kisitlar`: free-text lists (each persona has one constraint).
- So the layer needs a mapping from text to levels and rules. A text it cannot
  map becomes a clarification question (`needs_rm_input`), not a guess.
- Evidence available (snapshot 20261010-001233-6b20): deposit rates (EVDS +
  28 manual rows), policy rate, CBRT funding cost, CPI, USD/TRY, gold TL/kg,
  BIST 100, TEFAS fund price/size/investors, fund returns 1m–5y, fund risk
  level 1–7. Not available: per-fund volatility, fees, redemption days.

## To decide

1. Product universe: which option kinds (deposit, fund types, gold, FX…) and
   how a TEFAS fund maps to a kind.
2. Filters: rule ids and the persona field + evidence each one reads; what is
   a hard reject.
3. Text → level mapping for every persona field above; what triggers a question.
4. Criteria and weights per persona field; `score_parts` must sum to `score`.
5. `confidence` (data quality) and `stability` (rank robustness) formulas.
6. Warnings and data-quality notes: which flags and conditions produce them.
7. `run_id` / `config_hash`; where the decision config lives (e.g. `config/decision.yaml`).
8. Worker milestones, each ending with green tests.
