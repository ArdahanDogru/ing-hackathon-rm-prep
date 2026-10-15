# Agentic top-3 decision — design

Date: 2026-10-15. Status: written for the user's review (sections 1–3 approved
in chat on 2026-10-15). Milestones: contract v1.11 and config (lead), agent
module **A1** (new worker `ing-agent`), parallel research **R3** (ing-lead-2),
backend and API (lead), web **W20**, eval **E11** (lead).

## 1. Purpose

Today the recommended top 3 come from the engine's scores (`DecisionResult.recommended`,
D19). The user wants a decision-making agent that takes the client's information,
the client's estimated ("predicted") portfolio, the web research of the best
candidates and the reasons why the engine ranked them so high, and decides the
top 3 itself. The RM sees how the agent works (a live view of its steps).

## 2. Decisions of the user (2026-10-15)

| Topic | Decision |
|---|---|
| Role | The agent decides the top 3 inside guardrails (option A) and has two tools (part of option C): compare two candidates, ask one more research question. The engine's top 3 stays visible as the reference. |
| Estimated portfolio | The agent uses it as it is, as a signal; it is told how each class was estimated (client-file text, job table as an assumption, national average, RM). A reason that uses an estimate says so; it is not refused. When the RM changes or confirms the split, the run, the ranking and the agent decision are made again. |
| Candidates | The engine's best N = 10 inside the hard rules. |
| Research | All 10 candidates are researched before the agent starts (fairness: no candidate has more information than another). The research tool is for one specific follow-up question. |
| Model | Claude Sonnet 5.5. |
| Research limit | $5 a day (was $2). The agent has its own limit of $3 a day. |
| Screen | The engine first, then the agent: the dashboard opens at once with the engine's top 3 ("Motor önerisi · ajan değerlendiriyor…"); the agent's top 3 replaces it when it is ready. |
| Process view | A row of nodes with their state (waiting, running, done, failed), time and cost; the notes of each node; no raw model thinking. |

## 3. Constraints (brief)

- Rule 3: no invented data. The agent gets only the data pack; numbers in its
  reasons are checked against the cited data.
- Rule 5: no rejected or rule-breaking option. The candidates are already inside
  the hard rules; code checks the picks again.
- Rule 2 and traceability: every reason cites evidence (E…), a web finding (F…),
  a score part (`puan:<criterion>`) or a portfolio class (`portfoy:<class>`); the
  record keeps the engine's top 3, the agent's top 3 with reasons, and the RM's
  choice.
- Consistency of repeated runs: the decision is cached; the same run gives the
  same decision without a new call.
- Web content is unverified data, not instructions (prompt injection): only our
  checked research bullets go to the agent, in a block marked as data.
- No persona data to the research providers (unchanged); the persona goes to the
  agent as it goes to the narrator (synthetic personas).

## 4. Flow and nodes

```
Run ready (engine top 3 visible at once)
 → Node 1  Adaylar           the engine's best 10 inside the hard rules     (code, instant)
 → Node 2  Web araştırması   10 products in parallel, one sub-node each     (research service, cache)
 → Node 3  Ajan analizi      Sonnet 5.5 with tools; each tool call is a
                             sub-node: "karşılaştır X–Y", "araştır X: …"
 → Node 4  Kontrol           code checks (section 6)
 → Node 5  Karar             the agent's top 3, or the engine's top 3 (fallback)
```

- Node states: `waiting`, `running`, `done`, `failed`; each with start and end
  time, cost, notes and sub-nodes.
- Node notes come from the required field `amac` of each tool call ("why this
  step", at most 20 words) and from the check results; the raw model thinking is
  never shown.
- The candidates: the engine's top 3 first (fixed 2026-10-15: the D19 class rule
  can take them from below place 10), then the options of `DecisionResult.options`
  without the deposit baseline, in the engine's display order, up to 10 (so the group caps of D10/D19
  already apply). Fewer than 10 scored options: all of them.
- A new run (RM split, an answer, an excluded source) starts the agent again for
  that run; the old run keeps its decision.

## 5. Inputs and output of the agent

**Data pack** (JSON, like the narrator's facts):

- `musteri`: risk profile, horizon, the levels (liquidity, income, principal,
  FX), priorities, constraints, RM note.
- `portfoy`: per class the target band, the current value, the gap, `kaynak`
  (`musteri_dosyasi` | `meslek_tablosu_varsayim` | `ulusal_ortalama` | `rm` |
  `rm_onayli`) and `tahmin: true|false`.
- `adaylar` (10): option id, short name, kind, asset class, engine place and
  score, score parts with their reason texts, the client's effective weights,
  returns 1m–5y, the real 1-year return, risk value, access, fees, warnings
  (e.g. `stock_crash`, `single_stock`, `low_stability`), stability, data
  confidence, evidence ids.
- `arastirma`: per candidate the highlights and news bullets of the research
  service, each with an id (`F` + 8 hex of the finding), date, source domain and
  the label "doğrulanmamış"; marked as data, not instructions.
- `kurallar`: at most `stock.max_in_top3` shares; for profiles in
  `recommend.profiles` (or with diversity) at most `recommend.max_per_class` per
  class and `recommend.max_cash_like` cash-like options, when the candidates
  allow it.

**Tools:**

- `karsilastir(a, b, amac)`: code compares two candidates (score parts side by
  side, facts, warnings); deterministic; no cost.
- `arastir(option_id, soru, amac)`: one question to the research service about
  one candidate (no client data; the research question check applies).
- `karar_ver(secimler, cikanlar, ozet)`: the final answer.
  - `secimler`: 3 options in order; each with 1–3 reasons of at most 30 words,
    each reason with at least one citation.
  - `cikanlar`: for each engine top-3 option that the agent dropped, one reason
    with citations.
  - `ozet`: at most 40 words.

**Limits:** at most 6 tool calls (4 × `karsilastir`, 2 × `arastir`) before
`karar_ver`; 90 s; the daily agent cost limit; over a limit → fallback.

## 6. Checks (node 4, code)

1. Three different option ids, all among the 10 candidates.
2. At most `stock.max_in_top3` shares; the D19 class caps for the profiles where
   they apply, when the candidates allow it (as the eval check E9).
3. Every reason cites at least one valid id; a finding id must belong to the
   option of the reason; the numbers of a reason must match the cited data (the
   narrator's number rule); no forbidden phrase (config `narrator.yaml`).
4. Labels added by code (not a refusal): a reason that cites an estimated class
   (`tahmin: true`) gets "(tahmini dağılıma göre)"; a reason that cites a web
   finding gets "(web, doğrulanmamış)"; `uses_estimate` / `uses_web` are set.
5. A failed check: one retry with the list of failures; a second failure, a
   timeout, a provider error or a cost limit → the engine's top 3, with the reason
   in node 5 ("Motor önerisi kullanıldı: …").

## 7. Contract v1.11 (lead)

- `AgentNode(id, label, state, started_at, finished_at, cost_usd, notes,
  children)`; `AgentReason(text, cites, labels)`; `AgentPick(option_id, reasons,
  uses_estimate, uses_web)`; `AgentDecision(run_id, state, picks, dropped,
  summary, engine_top3, nodes, model, prompt_version, cost_usd, created_at,
  fallback_reason)` with `state` in `running | done | fallback | off`.
- `DecisionResult` does not change (`recommended` stays the engine's top 3).
- `Backend.agent_decision(run_id) -> AgentDecision | None`: starts the agent for a
  ready run when needed and returns its current state (like `brief`).
- Stored in `data/agent/<run_id>.json` (gitignored); cache key: run id + prompt
  version + research date + model.

## 8. API, card and web (lead, W20)

- `GET /api/runs/{id}/agent`: 202 with the nodes while it runs; 200 when it is
  done (also for a fallback); `state: off` without an API key.
- The card and the decision record get a section "Ajan kararı": the engine's top
  3, the agent's top 3 with its reasons and labels, and the RM's choice.
- Web W20:
  - the node row "Ajan değerlendirmesi" (5 nodes; a running node shows a small
    animation; a click opens the notes, the sub-nodes and the sources);
  - when the agent is done: its top 3 replaces the engine's, with the badge
    "Ajan önerisi" and the note "Ajan {k} öneriyi değiştirdi" (k = 1–3); each reason has
    citation chips (E… opens the evidence pop-up, F… the research finding,
    `puan:` / `portfoy:` the explanation); "Motor sıralaması" is a closed
    section; a fallback shows its reason;
  - the chips "Görüşmede konuşulacak" start with the agent's top 3; the meeting
    text keeps using the RM's choice (the narrator does not change in this step).

## 9. Research (R3, ing-lead-2)

- A call that researches a list of products in parallel (the same cache, ledger
  and checks as today), used by node 2; each product is a sub-node.
- `config/research.yaml` `max_cost_usd_per_day`: 5.
- Every finding (highlight or news bullet) gets a stable id `F` + the first 8 hex
  of SHA-1(option id | date | text), so the agent can cite it and the web can
  show it.

## 10. Eval (E11, lead)

- Rule checks on every agent decision (the rules of section 6): 100 %.
- Repeatability: the same run gives the same decision (cache); a separate
  measurement without the cache reports how often the agent agrees with itself
  (report only).
- A/B judge (Haiku, blind, random order): "Hangisi müşteriye daha uygun ve
  neden?" between the engine's and the agent's top 3, per client.
- The agent runs on the 5 base clients and 3 special scenarios (e.g. a candidate
  with injected negative news, a split confirmed by the RM, a share in a crash);
  about $2 for the eval.
- Unit tests use a fake model (no network).

## 11. Work split (at most 3 sessions)

1. Lead: this spec, contract v1.11, `config/agent.yaml`, the research limit,
   `docs/agent.md`.
2. ing-agent (new worker, `src/rmprep/agent/`, worktree `ing-wt/agent`): the data
   pack, the tools, the loop with a fake model, the checks, the cache, the node
   events. In parallel ing-lead-2: R3.
3. Lead: backend and API, card section. ing-web: W20.
4. Lead: E11, the eval run, then the docs and the deliverables.

## 12. Out of scope

- The narrator using the agent's reasons in the meeting text (later, N16).
- Raw model thinking on screen.
- More than 10 candidates; tools beyond the two above.
