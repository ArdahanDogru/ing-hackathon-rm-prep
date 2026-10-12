// Typed client of the JSON API (docs/web-ui.md section 6). Prefix /api; the
// Vite proxy (dev), the mock middleware (dev:mock) or `rmprep serve` answers.
import type {
  EvidenceItem,
  GlossaryTerm,
  Lang,
  NarrativeBrief,
  NarrativeView,
  Persona,
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
  approveNarrative: (runId: string, lang: Lang, text: string) =>
    request<NarrativeView>("POST", `/runs/${enc(runId)}/narrative/${lang}/approval`, { text }),
  cardUrl: (runId: string, lang: Lang = "TR") =>
    `${BASE}/runs/${enc(runId)}/card.md${lang === "TR" ? "" : `?lang=${lang}`}`,
  evidence: (snapshotId: string, evidenceId: string) =>
    request<EvidenceItem>("GET", `/evidence/${enc(snapshotId)}/${enc(evidenceId)}`),
  /** PUT one block of the meeting text: its edited text, or null to restore the original. */
  editBlock: (runId: string, lang: Lang, blockId: string, text: string | null) =>
    request<NarrativeView>("PUT", `/runs/${enc(runId)}/narrative/${lang}/blocks/${enc(blockId)}`, { text }),
  brief,
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
