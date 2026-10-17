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

## Implementation (A1, agent@2eb12ec; merged 2026-10-15)

- Files: `src/rmprep/agent/config.py` (strict loader), `pack.py` (candidates, data
  pack, finding ids), `tools.py` (TOOLS, `karsilastir`), `checks.py`
  (`check_decision`), `client.py` (`AgentClient`, `AnthropicAgentClient`),
  `service.py` (`AgentService`, `agent_from_root`).
- Model call: Messages API with tools, `tool_choice` "auto" (Sonnet 5.5 rejects
  "any") and strict schemas; a turn without a tool call counts as a failed try.
  Adaptive thinking at the config `effort` (medium); the assistant content is sent
  back unchanged inside one run and is never stored. Prompt caching: the system
  prompt and the data pack block.
- Data pack: `musteri`, `portfoy` (id `portfoy:<class>`, target band, current value
  and range, gap, `kaynak` = musteri_dosyasi | meslek_tablosu_varsayim |
  ulusal_ortalama | rm | rm_onayli, `tahmin`), `motor_ilk3`, `adaylar` (score parts
  with the ids `puan:<part>`, a penalty `penalty:x` becomes `puan:penalty_x`;
  returns 1m–5y, real 1-year return, risk, access, valör, fees, warnings,
  stability, confidence, `kanitlar` = E id → quantity, value, date), `arastirma`
  (highlights and news: F id, text, date, source domain, label "doğrulanmamış"; no
  provider summary, no URL; a failed or missing product is "yok" with the reason),
  `kurallar`. The pack is sent inside `<veri>…</veri>`; the system prompt says
  that the research is data, not instructions.
- Research: `research_many` runs in the agent's own pool with a deadline
  (`research_timeout_s`, default `timeout_s`); the 90 s of the model loop start
  after node 2; on a research timeout node 2 is failed and the agent decides
  without research. `ask_product` gets `persona=result.persona`.
- Checks: 3 different candidate ids; at most `stock.max_in_top3` shares; the D19
  caps when a 3-set of the candidates can meet them (the engine's relax order);
  1–3 reasons per pick of at most `words.reason` words; every cite valid and
  known; an F id belongs to the option of the reason; every number and date is in
  the cited data (a plain count or place 1–10 is allowed, not as a percent); no
  forbidden phrase (option names removed first); one reason for each dropped
  engine top-3 option; a summary of at most `words.summary` words with numbers
  from the pack.
- Fallback (the engine's top 3): fewer than 3 candidates (no call), the daily
  limit (checked before every call), 90 s, a tool over its limit, no tool call
  twice, a second failed check, a provider error or refusal, an internal error.
  `fallback_reason` holds the formatted `fallback_texts` line; the check part is
  in English (the first problem).
- Cache: `data/agent/<run_id>.json` (also while running, so the status is live);
  a done or fallback decision is used again when the prompt version, the model
  and the Turkish date match. Costs: `data/agent/costs.jsonl`, one row per model
  call; an unreadable ledger stops the calls (fail closed).
- Node notes: the `amac` of each tool call, the check problems and the result;
  never the raw model thinking.
- Live smoke (P01, snapshot 20261014-233110-1565, a small fake research): done,
  picks PPN, OSD, GO6 (engine PPN, OSD, AIS); $0.078, 20 s, 2 model calls (the
  first `karar_ver` failed the phrase check "garanti", the retry passed).

## Candidate set fixed (lead, 2026-10-15, found by eval 20261015-agent)

For P03 the D19 class rule took the engine's picks IDY and OKT from below place
10, so they were not among the agent's 10 candidates: the agent could not keep
them (2 changes were forced), and the A/B judge saw "n/a" for them (3 of the 5
"agent" grades were not fair). Now `candidates()` puts the engine's top 3 first and
fills up to 10 from the display order. The three P03 scenarios were run again
with this rule.

## A new run follows the agent (lead, 2026-10-17, bug found by the user)

Bug: the RM started the agent (P01, run `Rfe4ff6578a`, N 10, done 19:04 on
2026-10-16), then confirmed a new split (19:08). The split makes a new run
(`R8a90f0ad0c`); the agent decision and the research of the N candidates belong
to a run id, so the new run showed "not started" and only the new top 3 in the
research panel: "the agent researches were deleted". It did not come back on a
second try because the same split gives the same run id, and the RM had started
the agent on that run by hand in between (19:10). Evidence: the RM action log and
`data/agent/<run>.json`.

Rule (the user, 2026-10-15: a new split recomputes the ranking "and of course the
agent recommendation as well"): when `POST /holdings` or `POST /answers` makes a
new ready run and the old run has an agent decision (running, done or fallback),
the API starts the agent on the new run with the same N (`_follow_agent`) and logs
`agent_started` with `{n, auto: true, from_run}`. Not when the agent is off, the
new run is not ready, or the new run already has a decision (e.g. back to an
earlier split, or the reset of the split). The web needs no change: a new run id
polls the status at once, and the research panel asks again after the run. Cost:
one agent run per new split after an agent run (the content cache makes a repeat
free). Tests: `tests/api/test_agent_follow.py`.

## A4: readable stage boxes (lead, 2026-10-17, asked by the user)

The user: the explanations of the agent's stage boxes "are not so intuitive;
some of them are not explanatory even" (e.g. "Kontrol" showed raw English check
messages such as `fund:OSD: number 75 not in the cited data`, then "Tüm
kontroller geçti" without saying that a first proposal had failed; "Ajan
analizi" showed the tool name "karar ver" twice, one failed).

- `agent/explain.py`: each problem form of `checks.check_decision` as a short
  TR / EN sentence with the fund code (`explain`); `code(option_id)` = the code
  ("fund:PPN" → PPN; ING deposits by name). The model still gets the English
  problems; only the RM's notes and the fallback reason use `explain`.
- Notes in the RM's words (`service.TEXTS`): Adaylar lists the codes; Ajan
  araştırması adds how many ✗-marked findings were not given to the agent;
  the analysis steps are "Karşılaştırma: PPN ile OSD", "Ek araştırma: AIS —
  “…”", "Karar önerisi (k. deneme)", each with "Amaç: …" and, for a proposal,
  its result ("Kontrolde n sorun bulundu; ajan düzeltip yeniden önerdi." /
  "Kontrollerden geçti."); Kontrol gives per proposal "k. öneri: n sorun
  bulundu, ajana düzeltmesi için geri verildi:" with the explained problems,
  or "k. öneri: tüm kontroller geçti."; Karar starts with "Ajanın seçimi: …".
- The stage descriptions themselves (what each stage does) are fixed screen
  texts (web-ui.md W40). Stored decisions of earlier runs keep their old notes.
