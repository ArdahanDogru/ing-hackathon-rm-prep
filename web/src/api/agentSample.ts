// Agent decisions (contract v1.11) built from a run sample, for the tests and `npm run dev:mock`
// until the lead's API (W20, Task 5) has fixtures. Pure: no browser and no Vite API.
import type { AgentDecision, AgentNode, AgentPick, AgentState } from "./types";

/** The part of a RunView that the builder reads. */
interface RunLike {
  result: { run_id: string; recommended: string[]; options: { option: { option_id: string; kind: string } }[] };
  options: Record<string, { returns: { "1y": { evidence_id: string } | null } } | undefined>;
}

export const SAMPLE_FINDING = "Fa1b2c3d4";
const T0 = "2026-10-15T10:00:00+03:00";
const at = (s: number) => new Date(Date.parse(T0) + s * 1000).toISOString().replace("Z", "+00:00");

/** The engine's best 10 inside the hard rules, without the deposit baseline (spec section 4). */
function candidates(run: RunLike): string[] {
  return run.result.options
    .map((o) => o.option.option_id)
    .filter((id) => !id.startsWith("deposit:"))
    .slice(0, 10);
}

const NODES: [string, string][] = [
  ["adaylar", "Adaylar"],
  ["arastirma", "Web araştırması"],
  ["analiz", "Ajan analizi"],
  ["kontrol", "Kontrol"],
  ["karar", "Karar"],
];

/**
 * The five nodes; `finished` of them are done, the next one runs (running), or all are done.
 * The last node fails for a fallback.
 */
function nodes(run: RunLike, finished: number, fallback: boolean): AgentNode[] {
  const cands = candidates(run);
  return NODES.map(([id, label], i) => {
    const state = i < finished ? "done" : i === finished ? "running" : "waiting";
    const failed = fallback && i === 3;
    const children: AgentNode[] =
      id === "arastirma"
        ? cands.map((c, k) => ({
            id: `arastirma:${c}`,
            label: c.split(":")[1] ?? c,
            state: i < finished || k < 6 ? "done" : state,
            started_at: at(2),
            finished_at: i < finished || k < 6 ? at(6 + k) : null,
            cost_usd: 0.004,
            notes: [],
            children: [],
          }))
        : id === "analiz"
          ? [
              { id: "analiz:1", label: `karşılaştır ${cands[1]}–${cands[6]}`, state: i < finished ? "done" : state, started_at: at(20), finished_at: i < finished ? at(24) : null, cost_usd: 0, notes: ["Borçlanma açığı için iki borçlanma fonunu karşılaştırmak."], children: [] },
              { id: "analiz:2", label: `araştır ${cands[6]}: yönetim ücreti`, state: i < finished ? "done" : "waiting", started_at: i < finished ? at(25) : null, finished_at: i < finished ? at(31) : null, cost_usd: 0.01, notes: ["Ücret farkı sıralamayı değiştirir mi, görmek."], children: [] },
            ]
          : [];
    const done = i < finished;
    return {
      id,
      label,
      state: failed ? "failed" : state,
      started_at: i <= finished ? at(i * 10) : null,
      finished_at: done || failed ? at(i * 10 + 8) : null,
      cost_usd: id === "analiz" ? 0.042 : id === "arastirma" ? 0.04 : 0,
      notes:
        id === "adaylar"
          ? [`Motorun kesin kurallar içindeki en iyi ${cands.length} seçeneği.`]
          : id === "kontrol"
            ? failed
              ? ["Bir gerekçedeki sayı kaynakla uyuşmuyor (ikinci deneme de)."]
              : done
                ? ["3 farklı seçenek, hepsi adaylar içinde.", "Her gerekçe kaynak gösteriyor."]
                : []
            : [],
      children,
    };
  });
}

/** A decision in one state; `step` (running only) = the number of finished nodes, 0–4. */
export function agentDecision(run: RunLike, state: AgentState, step = 2): AgentDecision {
  const engine = run.result.recommended.slice(0, 3);
  const cands = candidates(run);
  const base = {
    run_id: run.result.run_id,
    state,
    picks: [] as AgentPick[],
    dropped: [] as AgentPick[],
    summary: "",
    engine_top3: engine,
    nodes: [] as AgentNode[],
    model: "claude-sonnet-5-5",
    prompt_version: "a1",
    cost_usd: 0,
    created_at: T0,
    fallback_reason: "",
  };
  if (state === "off") return { ...base, fallback_reason: "ANTHROPIC_API_KEY yok" };
  if (state === "running") return { ...base, nodes: nodes(run, step, false), cost_usd: 0.03 };
  if (state === "fallback")
    return {
      ...base,
      nodes: nodes(run, 4, true),
      cost_usd: 0.09,
      fallback_reason: "Kontrol iki kez geçmedi (bir gerekçedeki sayı kaynakla uyuşmuyor).",
    };
  // done: keep the 1st and 3rd engine picks, replace the 2nd with the 7th candidate (a debt fund in P01)
  const swap = cands.find((c, i) => i >= 3 && !engine.includes(c) && c.startsWith("fund:")) ?? cands[3];
  const ev = (id: string) => run.options[id]?.returns["1y"]?.evidence_id ?? "E00000000";
  const picks: AgentPick[] = [
    {
      option_id: engine[0],
      reasons: [{ text: "Aynı gün paraya erişim ve en düşük risk; düzenli gelir ihtiyacına uyuyor.", cites: [ev(engine[0]), "puan:liquidity"], labels: [] }],
      uses_estimate: false,
      uses_web: false,
    },
    {
      option_id: swap,
      reasons: [
        { text: "Borçlanma payı hedefin çok altında; bu fon açığı kapatır.", cites: ["portfoy:borclanma", "puan:allocation_gap"], labels: ["(tahmini dağılıma göre)"] },
        { text: "Yönetim ücreti benzerlerinden düşük.", cites: [SAMPLE_FINDING], labels: ["(web, doğrulanmamış)"] },
      ],
      uses_estimate: true,
      uses_web: true,
    },
    {
      option_id: engine[2],
      reasons: [{ text: "Katılım ilkesine uygun, yüksek 1 yıllık getiri.", cites: [ev(engine[2]), "puan:return"], labels: [] }],
      uses_estimate: false,
      uses_web: false,
    },
  ];
  return {
    ...base,
    picks,
    dropped: [
      {
        option_id: engine[1],
        reasons: [{ text: "İkinci para piyasası benzeri seçenek; nakit payı zaten hedefin üstünde.", cites: ["portfoy:nakit_benzeri"], labels: ["(tahmini dağılıma göre)"] }],
        uses_estimate: true,
        uses_web: false,
      },
    ],
    summary: "Nakit payı yüksek; bir para piyasası fonu yerine borçlanma fonu öneriliyor.",
    nodes: nodes(run, 5, false),
    cost_usd: 0.096,
  };
}
