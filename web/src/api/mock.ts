// Mock API for `npm run dev:mock`: answers /api/* from the sample JSON files
// (../tests/contracts/fixtures/api/). Pure: the Vite
// middleware in vite.config.ts gives it a loader by sample name.

export type Loader = (name: string) => unknown | undefined;
export type MockAnswer = { status: number; body: unknown; type?: string };

// approved first: after an approval the server holds the approved run under the same id
const RUN_SAMPLES = ["run_p01_approved", "run_p01_ready", "run_p02_ready", "run_needs_input", "run_test"];

const notFound = (detail: string): MockAnswer => ({ status: 404, body: { detail } });

function sample(load: Loader, name: string, fallback?: string): MockAnswer {
  const body = load(name) ?? (fallback ? load(fallback) : undefined);
  return body === undefined ? notFound(`no sample ${name}`) : { status: 200, body };
}

export function resolveMock(method: string, url: string, body: unknown, load: Loader): MockAnswer {
  const [path, query = ""] = url.split("?");
  const params = new URLSearchParams(query);
  const p = path.split("/").filter(Boolean).map(decodeURIComponent); // ["api", ...]
  if (p[0] !== "api") return notFound(url);
  const [, a, b, c, d, e] = p;
  const req = (body ?? {}) as Record<string, unknown>;

  if (method === "GET" && a === "personas" && !b) return sample(load, "personas");
  if (method === "GET" && a === "snapshots" && !b) return sample(load, "snapshots");
  if (method === "GET" && a === "snapshots" && c === "sources") return sample(load, "sources");
  if (method === "GET" && a === "evidence") return sample(load, "evidence_item");
  if (method === "GET" && a === "glossary") return sample(load, "glossary");

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
    if (method === "GET" && c === "narrative" && !d) {
      return sample(load, `narrative_p01_${(params.get("lang") ?? "TR").toLowerCase()}`);
    }
    if (method === "POST" && c === "narrative" && e === "approval") {
      const draft = load(`narrative_p01_${(d ?? "TR").toLowerCase()}`) as Record<string, unknown> | undefined;
      if (!draft) return notFound("no narrative sample");
      const text = String(req.text ?? "");
      return { status: 200, body: { ...draft, status: "approved", rm_text: text, markdown: text } };
    }
    if (method === "GET" && c === "card.md") {
      return { status: 200, body: "# Görüşme kartı (mock)\n", type: "text/markdown; charset=utf-8" };
    }
  }
  return notFound(`no mock for ${method} ${path}`);
}
