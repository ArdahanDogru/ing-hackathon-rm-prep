# Agentic top-3 decision (module `rmprep.agent`, worker `ing-agent`)

Approved by the user 2026-10-15. Spec:
`docs/superpowers/specs/2026-10-15-agent-decision-design.md`; plan:
`docs/superpowers/plans/2026-10-15-agent-decision.md` (Task 3 = milestone **A1**,
with the interfaces, the tests to write first and the config shape). Contract
v1.11 (`AgentNode`, `AgentReason`, `AgentPick`, `AgentDecision`) is on main.

## Summary

- A Claude Sonnet 5.5 agent decides the recommended top 3 from the engine's best
  10 candidates (`DecisionResult.options` without the deposit, display order),
  inside guardrails that code checks. The engine's `recommended` does not change;
  the agent's decision is a separate record (`data/agent/<run_id>.json`).
- Inputs (one JSON data pack): the client, the portfolio split per class with its
  source and the flag `tahmin`, the 10 candidates with their score parts and
  reasons, facts, warnings, stability and confidence, and the checked research
  of all 10 (highlights and news with finding ids `F…`, marked as data, not
  instructions).
- Tools: `karsilastir(a, b, amac)` (code, deterministic), `arastir(option_id,
  soru, amac)` (the research service, one question about one candidate),
  `karar_ver(secimler, cikanlar, ozet)`. At most 4 × `karsilastir`, 2 ×
  `arastir`; 90 s; $3 a day.
- Checks (code): 3 different ids among the candidates; at most
  `stock.max_in_top3` shares; the D19 caps where they apply; every reason cites
  E…, F…, `puan:<criterion>` or `portfoy:<class>`; numbers match the cited data;
  no forbidden phrase; labels "(tahmini dağılıma göre)" and "(web,
  doğrulanmamış)" added by code. One retry, then the engine's top 3 (fallback).
- Process view: 5 nodes (Adaylar, Web araştırması, Ajan analizi, Kontrol,
  Karar) with state, time, cost and notes (the `amac` field of each tool call;
  never the raw model thinking).
- The agent is a service next to the backend (like the research service), started
  by the API for a ready run; the eval builds it directly.
