// Mock API for `npm run dev:mock`: answers /api/* from the sample JSON files
// (../tests/contracts/fixtures/api/). Pure: the Vite
// middleware in vite.config.ts gives it a loader by sample name.

import { agentDecision, notStarted, SAMPLE_FINDING } from "./agentSample";

export type Loader = (name: string) => unknown | undefined;
export type MockAnswer = { status: number; body: unknown; type?: string };

// approved first: after an approval the server holds the approved run under the same id
const RUN_SAMPLES = ["run_p01_approved", "run_p01_ready", "run_p02_ready", "run_needs_input", "run_test"];

const notFound = (detail: string): MockAnswer => ({ status: 404, body: { detail } });

function sample(load: Loader, name: string, fallback?: string): MockAnswer {
  const body = load(name) ?? (fallback ? load(fallback) : undefined);
  return body === undefined ? notFound(`no sample ${name}`) : { status: 200, body };
}

// Web research (docs/research.md): a small fixed sample for dev:mock.
const MOCK_SOURCE = { url: "https://www.nurolportfoy.com.tr/", title: "Nurol Portföy", published: "2026-10-12" };
const MOCK_FINDING = {
  text: "Fon, kısa vadeli para piyasası araçlarına yatırım yapar.",
  topic: "strateji",
  confidence: "high",
  sources: [MOCK_SOURCE],
  date: "",
};
const MOCK_RESEARCH = {
  state: "ready",
  products: [
    {
      option_id: "fund:PPN", label: "NUROL PORTFÖY PARA PİYASASI (TL) FONU", company: "Nurol Portföy Yönetimi A.Ş.",
      summary: "",
      news: [{ ...MOCK_FINDING, id: "Fa0000003", text: "Nurol Portföy yeni bir fon başlattı.", topic: "haber", date: "2026-10-12" }],
      news_days: 90,
      findings: [
        { ...MOCK_FINDING, id: "Fa0000001" },
        { ...MOCK_FINDING, id: "Fa0000002", text: "Getiri faiz oranlarına duyarlıdır.", topic: "dikkat", confidence: "medium" },
        // the finding that the mock agent cites (W20)
        { ...MOCK_FINDING, id: SAMPLE_FINDING, text: "Yönetim ücreti benzer fonlardan düşük.", topic: "is", confidence: "medium" },
      ],
      lang: "TR", provider: "exa", created_at: "2026-10-14T10:00:00+03:00", cost_usd: 0.025, checks: [], error: "", version: 2,
    },
  ],
  questions: [],
};

// Agent (W24): off ("henüz çalıştırılmadı") until the RM starts it (POST {n}); then running for
// AGENT_RUN_MS, then done; P02 falls back. The research marks are kept in memory.
const AGENT_RUN_MS = 15_000;
const agentStarted = new Map<string, { at: number; n: number }>();
const marks = new Map<string, "ok" | "wrong">();

/** Forget the starts of the mock agent and the marks (tests). */
export function resetAgentMock(): void {
  agentStarted.clear();
  marks.clear();
  uploads.clear();
}

// Client upload (W31): kept in memory; the checks of the API in short (the required fields,
// the id form, not a built-in id); the reset forgets the uploads too.
const uploads = new Map<string, Record<string, unknown>>();
const REQUIRED = ["persona_id", "profil", "yas", "risk_profili", "durum", "yatirim_amaci", "yatirim_ufku", "likidite_ihtiyaci",
  "doviz_maruz_kalma_tercihi", "gelir_nakit_akisi_ihtiyaci", "anapara_koruma_tercihi", "oncelikler", "acik_kisitlar"];

function uploadPersona(req: Record<string, unknown>): MockAnswer {
  const p = req.persona as Record<string, unknown> | undefined;
  if (!p || typeof p !== "object") return { status: 422, body: { detail: "Dosyada persona yok." } };
  const missing = REQUIRED.find((k) => !(k in p));
  if (missing) return { status: 422, body: { detail: `Eksik alan: ${missing}` } };
  const id = String(p.persona_id);
  if (!/^[A-Za-z0-9_-]{1,32}$/.test(id)) return { status: 422, body: { detail: "persona_id yalnızca harf, rakam, - ve _ içerebilir (1–32)." } };
  if (/^P0[1-5]$/.test(id)) return { status: 422, body: { detail: `${id} hazır bir müşterinin kimliği; başka bir kimlik seçin.` } };
  const replaced = uploads.has(id);
  uploads.set(id, p);
  return { status: 200, body: { persona: p, replaced } };
}

type MockRun = Parameters<typeof agentDecision>[0];

function runOf(load: Loader, runId: string): { name: string; run: MockRun } | null {
  const name = RUN_SAMPLES.find((n) => (load(n) as { result?: { run_id?: string } } | undefined)?.result?.run_id === runId);
  return name ? { name, run: load(name) as MockRun } : null;
}

function agentAnswer(load: Loader, runId: string): MockAnswer {
  const found = runOf(load, runId);
  if (!found) return notFound(`unknown run ${runId}`);
  const started = agentStarted.get(runId);
  if (!started) return { status: 200, body: notStarted(found.run) };
  if (found.name === "run_p02_ready") return { status: 200, body: { ...agentDecision(found.run, "fallback"), n_candidates: started.n } };
  const elapsed = Date.now() - started.at;
  if (elapsed >= AGENT_RUN_MS) return { status: 200, body: { ...agentDecision(found.run, "done"), n_candidates: started.n } };
  const step = Math.min(4, Math.floor((elapsed / AGENT_RUN_MS) * 5));
  return { status: 202, body: { ...agentDecision(found.run, "running", step), n_candidates: started.n } };
}

function startAgent(load: Loader, runId: string, req: Record<string, unknown>): MockAnswer {
  if (!runOf(load, runId)) return notFound(`unknown run ${runId}`);
  const n = req.n === undefined ? 10 : Number(req.n);
  if (!Number.isInteger(n) || n < 3 || n > 20) return { status: 422, body: { detail: `n must be 3–20, got ${String(req.n)}` } };
  agentStarted.set(runId, { at: Date.now(), n });
  return agentAnswer(load, runId);
}

type MockFinding = { id?: string; mark?: string | null };
const withMarks = <F extends MockFinding>(f: F): F => (f.id ? { ...f, mark: marks.get(f.id) ?? null } : f);

/** The research status with the marks; after a done agent run, one more candidate (W24). */
function researchAnswer(load: Loader, runId: string): MockAnswer {
  const products: (typeof MOCK_RESEARCH.products[number] | Record<string, unknown>)[] = [...MOCK_RESEARCH.products];
  const found = runOf(load, runId);
  const started = agentStarted.get(runId);
  if (found && started && Date.now() - started.at >= AGENT_RUN_MS && found.name !== "run_p02_ready") {
    const other = agentDecision(found.run, "done").picks.find((p) => !found.run.result.recommended.includes(p.option_id));
    if (other?.option_id) // a run with fewer than 3 engine picks has no such candidate
      products.push({
        ...MOCK_RESEARCH.products[0],
        option_id: other.option_id,
        label: other.option_id.split(":")[1] ?? other.option_id,
        company: "",
        news: [],
        findings: [{ ...MOCK_FINDING, id: "Fb0c0de01", text: "Fon büyük ölçüde özel sektör tahvili tutar." }],
      });
  }
  const mark = (p: typeof products[number]) => {
    const q = p as { findings?: MockFinding[]; news?: MockFinding[] };
    return { ...p, findings: (q.findings ?? []).map(withMarks), news: (q.news ?? []).map(withMarks) };
  };
  // W29: while the run's agent runs, an earlier run's candidate that is not in this list
  // (the mock has no "followed" runs: any running agent shows it)
  const running = !!started && Date.now() - started.at < AGENT_RUN_MS;
  const previous = running
    ? {
        run_id: "R-earlier",
        products: [
          mark({
            ...MOCK_RESEARCH.products[0],
            option_id: "fund:GO6",
            label: "ONE PORTFÖY PARA PİYASASI (TL) FONU",
            company: "One Portföy Yönetimi A.Ş.",
            news: [],
            findings: [{ ...MOCK_FINDING, id: "Fb0c0de02", text: "Fon kısa vadeli mevduat ve repo tutar." }],
          }),
        ],
      }
    : undefined;
  return { status: 200, body: { ...MOCK_RESEARCH, products: products.map(mark), ...(previous ? { previous } : {}) } };
}

// Fund documents (W26): Nurol funds ok (two links), AIS not_found, IST failed, the rest
// not_covered (the İş Portföy text for an İş Portföy fund); other kinds 422.
const IS_REASON = "İş Portföy: robots.txt belge yolunu engelliyor; belgeler KAP'ta.";

function documentsAnswer(load: Loader, runId: string, optionId: string): MockAnswer {
  const found = runOf(load, runId);
  if (!found) return notFound(`unknown run ${runId}`);
  const o = (found.run as unknown as { options: Record<string, { issuer?: string; kind?: string } | undefined> }).options[optionId];
  if (!o) return notFound(`unknown option ${optionId}`);
  if (o.kind !== "fund" && o.kind !== "etf") return { status: 422, body: { detail: `documents only for funds and ETFs, not ${o.kind}` } };
  const code = (optionId.split(":")[1] ?? optionId).toLowerCase();
  const issuer = o.issuer ?? "";
  const base = { manager_label: issuer, verdict: "", docs: [], page_url: "", checked_at: new Date().toISOString(), reason: "" };
  if (issuer.startsWith("Nurol")) {
    const site = "https://www.nurolportfoy.com.tr";
    return {
      status: 200,
      body: {
        ...base,
        status: "ok",
        verdict: "izahname and ybf found",
        page_url: `${site}/fonlar/${code}`,
        docs: [
          { kind: "izahname", label: "İzahname", url: `${site}/belgeler/${code}-izahname.pdf`, date: "2025-02-04" },
          { kind: "ybf", label: "Yatırımcı Bilgi Formu", url: `${site}/belgeler/${code}-ybf.pdf`, date: "2026-03-13" },
        ],
      },
    };
  }
  if (code === "ais") return { status: 200, body: { ...base, status: "not_found", page_url: "https://www.akportfoy.com.tr/fonlar/ais" } };
  if (code === "ist") return { status: 200, body: { ...base, status: "failed", reason: "timeout" } };
  const reason = issuer.startsWith("İş Portföy") ? IS_REASON : `${issuer || "Kurucu"}: belge bağlantıları bu kurucu için tanımlı değil.`;
  return { status: 200, body: { ...base, status: "not_covered", reason } };
}

// Reset (W27): 409 while a mock agent runs; else forget the agent starts and the marks.
function resetAnswer(): MockAnswer {
  const now = Date.now();
  if ([...agentStarted.values()].some((s) => now - s.at < AGENT_RUN_MS))
    return { status: 409, body: { detail: "Ajan çalışıyor; bitince sıfırlayın." } };
  const p = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Istanbul", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    })
      .formatToParts(new Date(now))
      .map((x) => [x.type, x.value]),
  );
  const moved = { runs: 0, texts: 0, cards: 0, agent: agentStarted.size, research_marks: marks.size };
  agentStarted.clear();
  marks.clear();
  uploads.clear();
  return { status: 200, body: { archive: `data/reset-archive/${p.year}${p.month}${p.day}-${p.hour}${p.minute}${p.second}`, moved } };
}

function setMark(req: Record<string, unknown>): MockAnswer {
  const id = req.finding_id;
  const mark = req.mark ?? null;
  if (typeof id !== "string" || !id || !(mark === null || mark === "ok" || mark === "wrong"))
    return { status: 422, body: { detail: "finding_id and a mark ok | wrong | null are needed" } };
  if (mark === null) marks.delete(id);
  else marks.set(id, mark);
  return { status: 200, body: { finding_id: id, mark } };
}

export function resolveMock(method: string, url: string, body: unknown, load: Loader): MockAnswer {
  const [path, query = ""] = url.split("?");
  const params = new URLSearchParams(query);
  const p = path.split("/").filter(Boolean).map(decodeURIComponent); // ["api", ...]
  if (p[0] !== "api") return notFound(url);
  const [, a, b, c, d, e] = p;
  const req = (body ?? {}) as Record<string, unknown>;

  if (method === "GET" && a === "personas" && !b) {
    const builtIn = (load("personas") as unknown[] | undefined) ?? [];
    return { status: 200, body: [...builtIn, ...uploads.values()] };
  }
  if (method === "GET" && a === "personas" && b === "uploaded") return { status: 200, body: [...uploads.keys()] };
  if (method === "POST" && a === "personas" && !b) return uploadPersona(req);
  if (method === "GET" && a === "snapshots" && !b) return sample(load, "snapshots");
  if (method === "GET" && a === "snapshots" && c === "sources") return sample(load, "sources");
  if (method === "GET" && a === "evidence") return sample(load, "evidence_item");
  if (method === "GET" && a === "glossary") return sample(load, "glossary");
  if (a === "ingest" && !b) {
    // stateless: stale data on the newest snapshot; a POST answers a started job
    const latest = (load("snapshots") as string[] | undefined)?.[0] ?? null;
    const m = latest && /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})/.exec(latest);
    const created_at = m ? `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}+03:00` : null;
    const age_hours = created_at ? (Date.now() - Date.parse(created_at)) / 3_600_000 : null;
    const status = { latest_snapshot: latest, created_at, age_hours, stale: true, running: false, started_at: null, finished_at: null, error: null };
    if (method === "GET") return { status: 200, body: status };
    if (method === "POST") return { status: 202, body: { ...status, running: true, started_at: new Date().toISOString() } };
  }

  if (method === "POST" && a === "research" && b === "marks") return setMark(req);
  if (method === "POST" && a === "reset" && !b) return resetAnswer();

  if (a === "runs") {
    if (method === "POST" && !b) {
      const persona = (req.persona ?? {}) as { persona_id?: string };
      const id = (persona.persona_id ?? "P01").toLowerCase();
      return sample(load, `run_${id}_ready`, "run_p01_ready");
    }
    if (method === "GET" && b && !c) {
      for (const name of RUN_SAMPLES) {
        const run = load(name) as { result?: { run_id?: string } } | undefined;
        if (run?.result?.run_id === b) return { status: 200, body: run };
      }
      return notFound(`unknown run ${b} (the server may have restarted)`);
    }
    if (method === "POST" && c === "answers") return sample(load, "run_p01_ready");
    if (method === "POST" && c === "approval") return sample(load, "run_p01_approved");
    if (method === "PUT" && c === "notes") return sample(load, "run_p01_approved");
    if (method === "GET" && c === "research" && !d) return researchAnswer(load, b ?? "");
    if (method === "GET" && c === "agent" && !d) return agentAnswer(load, b ?? "");
    if (method === "POST" && c === "agent" && !d) return startAgent(load, b ?? "", req);
    if (method === "GET" && c === "options" && d && e === "documents") return documentsAnswer(load, b ?? "", d);
    if (method === "POST" && c === "research" && d === "questions") {
      const question = String(req.question ?? "");
      if (/müşteri|client/i.test(question)) {
        return { status: 422, body: { detail: "Soru müşteri bilgisi içeriyor; yalnızca ürün veya şirket hakkında sorun." } };
      }
      return {
        status: 200,
        body: { question, summary: "", findings: [{ ...MOCK_FINDING, text: "Örnek madde (mock).", topic: "soru" }], lang: "TR", provider: "exa", created_at: "2026-10-14T10:00:00+03:00", cost_usd: 0.007, checks: [], error: "", version: 2 },
      };
    }
    if (method === "GET" && c === "narrative" && !d) {
      return sample(load, `narrative_p01_${(params.get("lang") ?? "TR").toLowerCase()}`);
    }
    if (method === "POST" && c === "narrative" && e === "approval") {
      const draft = load(`narrative_p01_${(d ?? "TR").toLowerCase()}`) as Record<string, unknown> | undefined;
      if (!draft) return notFound("no narrative sample");
      const text = String(req.text ?? "");
      return { status: 200, body: { ...draft, status: "approved", rm_text: text, markdown: text } };
    }
    if (method === "PUT" && c === "narrative" && e === "blocks") {
      // stateless: the sample with this one edit; "kesin getiri" gives a blocking finding to try the guard;
      // an empty text deletes the block
      const block = p[6] ?? "";
      const draft = load(`narrative_p01_${(d ?? "TR").toLowerCase()}`) as Record<string, unknown> | undefined;
      if (!draft) return notFound("no narrative sample");
      const raw = req.text as string | null;
      const text = raw === null ? null : String(raw).trim() ? String(raw) : ""; // "" = the block is deleted (v1.9)
      const edits = text === null ? {} : { [block]: text };
      const checks = text && /kesin getiri/i.test(text) ? { [block]: ["phrase: 'kesin getiri' kullanılmamalı"] } : {};
      return { status: 200, body: { ...draft, rm_edits: edits, edit_checks: checks } };
    }
    if (method === "GET" && c === "brief") {
      const brief = load(`brief_p01_${(params.get("lang") ?? "TR").toLowerCase()}`);
      return brief === undefined ? { status: 202, body: { status: "running" } } : { status: 200, body: brief };
    }
    if (method === "GET" && c === "card.md") {
      return { status: 200, body: "# Görüşme kartı (mock)\n", type: "text/markdown; charset=utf-8" };
    }
  }
  return notFound(`no mock for ${method} ${path}`);
}
