# Manual feedback report (the manual form of the eval loop) — design

Date: 2026-10-16. Status: approved in chat by the user on 2026-10-15/16 ("go ahead
and start the implementation for the manual feedback report"). Milestones: **L1b**
(lead: more fields in the RM action log) and **F1** (ing-eval: the report). The
automatic loop (variants, replay, schedule) is future work.

## 1. Purpose

Measure the RM action log (L1) and give recommendations by **fixed rules**: each
recommendation names its measure, its numbers, its rule and the log records behind
it. Nothing changes automatically; a person reads and decides. Fully explainable
(brief: "Belirsizlik ve veri eksikleri güven düzeyi veya açık uyarılarla ifade
edilmelidir").

## 2. L1b — more fields in the log (lead)

- Every record gets `versions`: `{decision_config, narrator_prompt, agent_prompt,
  research}` (the hash of config/decision.yaml as in the run, the prompt versions
  of config/narrator.yaml and config/agent.yaml, the research shape version);
  missing parts are "".
- `research_marked` details add `section` ("news" | "highlight"), `topic`,
  `option_kind`, `asset_class` (from the run's option and the research status).
- `holdings_set` details add `estimate`: per class `{current, source}` of the run
  before the RM's split (the D27 estimate).

## 3. The report (F1, ing-eval)

- Command `rmprep feedback [--since YYYY-MM-DD] [--until YYYY-MM-DD]`: reads
  `data/logs/rm-actions/*.jsonl` in the period (default: all), writes
  `data/feedback/<YYYYMMDD-HHMMSS>/report.md` and `report.json`, prints the Markdown.
  No LLM, no network, no cost; deterministic for the same log.
- Rules in `config/feedback.yaml` (strict keys). Every rule: `min_n` (the least
  data), `threshold`, a TR/EN recommendation text with named fields.
- Below `min_n` the report says "Yeterli veri yok ({n}/{min_n})" and gives no
  recommendation.

| Id | Measure | Group | Rule (start values) | Recommendation (example) |
|---|---|---|---|---|
| R1 | ✗ share of the research marks: wrong / (ok + wrong) | asset class × section (news, highlight) | min_n 10, share > 0.30 | "Para piyasası fonlarında haber maddelerinin %42'si (12/29) ✗ işaretlendi → haber istemi yalnızca fona özgü olayları sorsun." |
| R2 | Deletion share of a meeting-text section: runs with a `text_block_deleted` of that section / approved runs | section key | min_n 5, share > 0.50 | "'Piyasa notu' 7 onaylı metnin 5'inde silindi → bölüm varsayılan olarak kapalı olsun." |
| R3 | Edit share of a section: runs with a `text_block_edited` of that section / approved runs, with up to 3 examples (before → after) | section key | min_n 5, share > 0.50 | "'Özet' 6 metnin 4'ünde değiştirildi → örnek düzenlemelere göre metin istemini gözden geçirin." |
| R4 | Acceptance: of the RM's selected options, the share in the engine's top 3, and (runs with an agent decision) in the agent's top 3 | engine, agent | min_n 5 approvals; the agent's share lower than the engine's by > 0.10 | "Ajan önerileri RM seçiminde %50, motor önerileri %75 kabul gördü (6 onay) → ajan istemini gözden geçirin." |
| R5 | Error of the D27 estimate: mean absolute difference between the RM's split and the estimate, per estimate source and class | source (profile row or national) × class | min_n 3 splits, error > 15 points | "Emekli meslek satırında borçlanma tahmini RM değerlerinden ortalama 22 puan sapıyor (4 bölünme) → meslek tablosunu güncelleyin." |

- Report sections: the period, the number of records per action, then R1–R5, each
  with: the measure per group (n, value), the rule, the result (recommendation /
  no recommendation / yeterli veri yok), and the evidence (`<file>:<line>` of the
  records used, at most 10 per group, then "+ k more"). A last section lists the
  research questions of the period (text and count), without a rule.
- Versions: each measure is computed per `versions` value when more than one
  version is in the period; the report shows them side by side, so the effect of a
  change is visible.

## 4. Tests

Fixed log fixtures: every rule above and below its threshold, below `min_n`, the
evidence lines, more than one version, an empty period, a record with a missing
field (skipped and counted), determinism.

## 5. Out of scope

Any automatic change; variants and replay (the automatic loop, future work); an
LLM summary; a web page for the report.
