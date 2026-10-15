// Typed client of the JSON API (docs/web-ui.md section 6). Prefix /api; the
// Vite proxy (dev), the mock middleware (dev:mock) or `rmprep serve` answers.
import type {
  AgentDecision,
  FindingMark,
  EvidenceItem,
  GlossaryTerm,
  HoldingsOrigin,
  IngestStatus,
  Lang,
  NarrativeBrief,
  NarrativeView,
  Persona,
  QuestionAnswer,
  ResearchView,
  RunInputs,
  RunView,
  SourceStatus,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

const BASE = "/api";
const enc = encodeURIComponent;

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  const res = await fetch(BASE + path, init);
  if (!res.ok) throw await apiError(res);
  return (await res.json()) as T;
}

async function apiError(res: Response): Promise<ApiError> {
  let detail = res.statusText || `HTTP ${res.status}`;
  try {
    const data = await res.json();
    if (data && typeof data.detail === "string") detail = data.detail;
  } catch {
    // not JSON: keep the status text
  }
  return new ApiError(res.status, detail);
}

/** GET /runs/{id}/brief: the brief, or "running" (202) while its background job runs. */
async function brief(runId: string, lang: Lang): Promise<NarrativeBrief | "running"> {
  const res = await fetch(`${BASE}/runs/${enc(runId)}/brief?lang=${lang}`);
  if (res.status === 202) return "running";
  if (!res.ok) throw await apiError(res);
  return (await res.json()) as NarrativeBrief;
}

/** GET /runs/{id}/research: "running" (202), off, or the findings; 404 (a server without research) = off. */
async function research(runId: string, lang: Lang): Promise<ResearchView> {
  const res = await fetch(`${BASE}/runs/${enc(runId)}/research?lang=${lang}`);
  if (res.status === 202) return { state: "running" };
  if (res.status === 404) return { state: "off", reason: "" };
  if (!res.ok) throw await apiError(res);
  return (await res.json()) as ResearchView;
}

/** GET /runs/{id}/agent (W20): the decision (202 while it runs, with the nodes; 200 when done,
 * fallback or off); null for a run or a server without an agent (404). */
async function agentStatus(runId: string): Promise<AgentDecision | null> {
  const res = await fetch(`${BASE}/runs/${enc(runId)}/agent`);
  if (res.status === 404) return null;
  if (!res.ok) throw await apiError(res);
  return (await res.json()) as AgentDecision;
}

export const api = {
  personas: () => request<Persona[]>("GET", "/personas"),
  snapshots: () => request<string[]>("GET", "/snapshots"),
  sources: (snapshotId: string) => request<Record<string, SourceStatus>>("GET", `/snapshots/${enc(snapshotId)}/sources`),
  run: (inputs: RunInputs) => request<RunView>("POST", "/runs", inputs),
  getRun: (runId: string) => request<RunView>("GET", `/runs/${enc(runId)}`),
  answer: (runId: string, question_id: string, answer: string) =>
    request<RunView>("POST", `/runs/${enc(runId)}/answers`, { question_id, answer }),
  approve: (runId: string, status: "approved" | "rejected", note: string, selected: string[]) =>
    request<RunView>("POST", `/runs/${enc(runId)}/approval`, { status, note, selected }),
  notes: (runId: string, note: string, option_notes: Record<string, string>) =>
    request<RunView>("PUT", `/runs/${enc(runId)}/notes`, { note, option_notes }),
  narrative: (runId: string, lang: Lang) => request<NarrativeView>("GET", `/runs/${enc(runId)}/narrative?lang=${lang}`),
  cardUrl: (runId: string, lang: Lang = "TR") =>
    `${BASE}/runs/${enc(runId)}/card.md${lang === "TR" ? "" : `?lang=${lang}`}`,
  evidence: (snapshotId: string, evidenceId: string) =>
    request<EvidenceItem>("GET", `/evidence/${enc(snapshotId)}/${enc(evidenceId)}`),
  /** PUT one block of the meeting text: its edited text, or null to restore the original. */
  editBlock: (runId: string, lang: Lang, blockId: string, text: string | null) =>
    request<NarrativeView>("PUT", `/runs/${enc(runId)}/narrative/${lang}/blocks/${enc(blockId)}`, { text }),
  brief,
  research,
  agentStatus,
  /** POST /runs/{id}/agent {n} (W24): the RM starts the agent; 202 with the running decision; 422 for a bad n. */
  startAgent: (runId: string, n: number) => request<AgentDecision>("POST", `/runs/${enc(runId)}/agent`, { n }),
  /** POST /research/marks (W24): ✓ "ok", ✗ "wrong" or null (no mark) for one finding. */
  setMark: (m: { finding_id: string; option_id: string; mark: FindingMark; run_id: string }) =>
    request<{ finding_id: string; mark: FindingMark }>("POST", "/research/marks", m),
  /** POST a question to the web research; 422 = refused (the reason is the detail). */
  askResearch: (runId: string, question: string, lang: Lang) =>
    request<QuestionAnswer>("POST", `/runs/${enc(runId)}/research/questions`, { question, lang }),
  /** POST /runs/{id}/holdings (W18): the current split (all five classes, total 100 ± 0.5), or null to remove it; a new run. */
  setHoldings: (runId: string, shares: Record<string, number> | null, origin?: HoldingsOrigin) =>
    request<RunView>("POST", `/runs/${enc(runId)}/holdings`, shares === null ? { shares: null } : { shares, origin }),
  /** GET /ingest: the age of the newest snapshot and the ingest job (W14). */
  ingestStatus: () => request<IngestStatus>("GET", "/ingest"),
  /** POST /ingest: starts the ingest (202 with the status); 409 when one already runs. */
  startIngest: () => request<IngestStatus>("POST", "/ingest"),
  glossary: (lang: Lang, runId: string) => request<GlossaryTerm[]>("GET", `/glossary?lang=${lang}&run_id=${enc(runId)}`),
};

/** GET the run; after a server restart (404) make it again from the same inputs (same run id). */
export async function getRunOrRerun(runId: string, inputs: RunInputs): Promise<RunView> {
  try {
    return await api.getRun(runId);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return api.run(inputs);
    throw e;
  }
}

// The inputs of each run, so that a route like /meeting/:runId can make the run again.
const KEY = "rmprep.inputs.";

export function rememberInputs(runId: string, inputs: RunInputs): void {
  try {
    sessionStorage.setItem(KEY + runId, JSON.stringify(inputs));
  } catch {
    // storage full or blocked: the 404 path then shows the error
  }
}

export function recallInputs(runId: string): RunInputs | null {
  const raw = sessionStorage.getItem(KEY + runId);
  return raw ? (JSON.parse(raw) as RunInputs) : null;
}
