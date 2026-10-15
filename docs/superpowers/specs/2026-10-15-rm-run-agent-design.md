# The agent runs on the RM's request, with RM marks on the research bullets — design

Date: 2026-10-15. Status: approved in chat by the user on 2026-10-15. Changes the
agentic top-3 decision (spec `2026-10-15-agent-decision-design.md`). Milestones:
contract v1.12 and API (lead), research marks **R4** (ing-lead-2), agent **A2**
(ing-agent), web **W24** (ing-web), eval scenario (lead).

## 1. Decisions of the user (2026-10-15)

- When a run opens: only the engine's top 3 with their scores, and the web
  research of these 3 products. The agent does **not** run, and the other
  candidates are **not** researched.
- In "Ajan araştırması" the RM marks each bullet (highlight or news): ✓
  doğrulandı or ✗ yanlış / alakasız; no mark = doğrulanmamış.
- A ✗ bullet is not given to the agent. A ✓ bullet goes in with the label "RM
  doğruladı". An unmarked bullet goes in as today ("doğrulanmamış").
- The RM starts the agent with a button "Ajanı çalıştır" and a field "Aday sayısı
  (N)", default 10. The RM can run it again (e.g. after more marks).
- Prompt caching: the stable part of the agent's input first (cached), the
  research block with the marks last.

## 2. Flow

```
POST /api/runs -> engine top 3 on screen; research of the top 3 (as before the agent)
RM marks bullets  -> POST /api/research/marks {finding_id, mark: "ok"|"wrong"|null}
RM: "Ajanı çalıştır" (N)  -> POST /api/runs/{id}/agent {n}
   node 1 Adaylar (engine top 3 first, then display order, up to N)
   node 2 Ajan araştırması (the N−3 other candidates; the top 3 are cached)
   node 3–5 as today
GET /api/runs/{id}/agent -> the latest decision of the run (202 while running)
```

## 3. Marks (R4, research service)

- A mark belongs to a finding id (`F` + 8 hex; the id comes from the product, the
  date and the text), so it is a statement about a fact on that day: valid for
  every run that shows that finding. Stored in `data/research/marks/<day>.json`:
  `{finding_id: {mark, run_id, at}}`; `null` removes a mark.
- `ResearchService.marks(day) -> Mapping[str, str]`, `set_mark(finding_id, mark,
  run_id)`; the research status (`GET /api/runs/{id}/research`) adds `mark` to
  each finding.
- Each mark and each removal goes into the RM action log (L1) as
  `research_marked` (`finding_id`, `option_id`, `mark`).

## 4. The agent (A2)

- `AgentService.start(result, evidence, lang, n=None)`: `n` from 3 to
  `config.max_candidates` (20); default `config.candidates` (10).
- The pack: ✗ findings are removed; ✓ findings carry `dogrulama: "RM
  doğruladı"`; unmarked findings `dogrulama: "doğrulanmamış"`. The system prompt
  adds: "doğrulanmamış = henüz incelenmedi, yanlış değil; bir adayı yalnızca
  bulguları RM tarafından doğrulandığı için tercih etme."
- Labels by code: a reason that cites a ✓ finding gets "(web, RM doğruladı)"
  instead of "(web, doğrulanmamış)".
- **Prompt caching:** the user message has two blocks: block 1 = the stable data
  (client, portfolio, engine top 3, candidates with scores and facts, rules), with
  `cache_control`; block 2 = the research block (`arastirma`) with the marks,
  without `cache_control`. The system prompt keeps its own cache mark. A re-run
  with other marks and the same N reads block 1 from the cache.
- The decision cache key: run id + prompt version + model + Turkish date + N +
  the hash of the marks of the candidates' findings. A re-run with the same N and
  the same marks gives the stored decision without a call.
- `AgentDecision` gets `n_candidates` and `marks_hash` (contract v1.12).
- Prompt version `a3`.

## 5. API (lead)

- `_view` no longer starts the agent; research starts as today (top 3).
- `POST /api/runs/{id}/agent` with `{n}` (optional): starts the agent; 422 for n
  out of range or a run that is not ready; answers 202 with the running decision.
- `GET /api/runs/{id}/agent`: the latest decision of the run, or `state: off` with
  the reason "henüz çalıştırılmadı" (`not_started`) when the RM has not started it.
- `POST /api/research/marks` (the research router): sets or removes a mark.
- The action log gets `agent_started` (`n`, `marks`: counts of ✓ and ✗) and
  `research_marked`.

## 6. Web (W24)

- Before the agent runs, the agent box shows a short text, the field "Aday sayısı"
  (3–20, default 10) and the button "Ajanı çalıştır". While it runs: the node row
  as today. After it: the decision as today, plus "Yeniden çalıştır" (with N).
- "Ajan araştırması": each bullet has ✓ and ✗ (toggle; a second click removes the
  mark); a marked bullet shows its state; a ✗ bullet is shown dimmed with
  "ajana verilmez". After the agent has run, the bullets of the other candidates
  are shown too (grouped by product), so the RM can mark them and run again.
- The brief and pipeline step 5 follow the agent's decision only after the RM has
  run it (as today after a decision).

## 7. Eval

E11 starts the agent directly (N = 10, no marks): unchanged. One new scenario
`agent-marks`: P01 with a ✗ on a finding of the engine's #2 and a ✓ on a finding
of the engine's #1; checks that the ✗ finding is not in the pack and that the ✓
finding has the label.

## 8. Out of scope

Marks on the agent's reasons; marks that last longer than a day; a learning step
from the marks (the optimization loop).
