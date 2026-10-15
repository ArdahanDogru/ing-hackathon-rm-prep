import { resetAgentMock, resolveMock } from "./mock";

test("agent (W24): off (not started) until POST, then running 15 s (202), then done; P02 falls back; unknown run 404", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-15T10:00:00+03:00"));
  resetAgentMock();
  const run = (id: string) => ({
    result: {
      run_id: id,
      recommended: ["fund:A", "fund:B", "fund:C"],
      options: ["deposit:x", "fund:A", "fund:B", "fund:C", "fund:D", "fund:E"].map((option_id) => ({ option: { option_id, kind: "fund" } })),
    },
    options: {},
  });
  const runs: Record<string, unknown> = { run_p01_ready: run("R01"), run_p02_ready: run("R02") };
  const loadRuns = (name: string) => runs[name];
  const before = resolveMock("GET", "/api/runs/R01/agent", undefined, loadRuns);
  expect(before.status).toBe(200);
  expect(before.body).toMatchObject({ state: "off", fallback_reason: "henüz çalıştırılmadı" });
  expect(resolveMock("POST", "/api/runs/R01/agent", { n: 2 }, loadRuns).status).toBe(422);
  const started = resolveMock("POST", "/api/runs/R01/agent", { n: 5 }, loadRuns);
  expect(started.status).toBe(202);
  expect(started.body).toMatchObject({ run_id: "R01", state: "running", n_candidates: 5 });
  expect(resolveMock("GET", "/api/runs/R01/agent", undefined, loadRuns).status).toBe(202);
  vi.advanceTimersByTime(16_000);
  const done = resolveMock("GET", "/api/runs/R01/agent", undefined, loadRuns);
  expect(done.status).toBe(200);
  expect(done.body).toMatchObject({ state: "done", n_candidates: 5 });
  expect((done.body as { picks: unknown[] }).picks).toHaveLength(3);
  resolveMock("POST", "/api/runs/R02/agent", {}, loadRuns);
  expect(resolveMock("GET", "/api/runs/R02/agent", undefined, loadRuns).body).toMatchObject({ state: "fallback" });
  expect(resolveMock("GET", "/api/runs/RX/agent", undefined, loadRuns).status).toBe(404);
  vi.useRealTimers();
});

test("research marks (W24): set, read back in the research status, remove", () => {
  resetAgentMock();
  const none = (name: string) => (name === "run_p01_ready" ? undefined : undefined);
  const set = resolveMock("POST", "/api/research/marks", { finding_id: "Fa1b2c3d4", option_id: "fund:PPN", mark: "ok", run_id: "R01" }, none);
  expect(set).toMatchObject({ status: 200, body: { finding_id: "Fa1b2c3d4", mark: "ok" } });
  const research = resolveMock("GET", "/api/runs/R01/research", undefined, none).body as { products: { findings: { id?: string; mark?: string | null }[] }[] };
  const all = research.products.flatMap((p) => p.findings);
  expect(all.find((f) => f.id === "Fa1b2c3d4")?.mark).toBe("ok");
  resolveMock("POST", "/api/research/marks", { finding_id: "Fa1b2c3d4", option_id: "fund:PPN", mark: null, run_id: "R01" }, none);
  const again = resolveMock("GET", "/api/runs/R01/research", undefined, none).body as typeof research;
  expect(again.products.flatMap((p) => p.findings).find((f) => f.id === "Fa1b2c3d4")?.mark ?? null).toBeNull();
  expect(resolveMock("POST", "/api/research/marks", { finding_id: "x", mark: "maybe" }, none).status).toBe(422);
});

const files: Record<string, unknown> = {
  personas: [{ persona_id: "P01" }],
  run_p01_ready: { result: { run_id: "R01" } },
  run_p01_approved: { result: { run_id: "R01" } },
  run_p02_ready: { result: { run_id: "R02" } },
  narrative_p01_tr: { lang: "TR", status: "draft", rm_text: "" },
  narrative_p01_en: { lang: "EN", status: "draft", rm_text: "" },
};
const load = (name: string) => files[name];

test("a run of P02 uses its own sample, an unknown persona the P01 sample", () => {
  expect(resolveMock("POST", "/api/runs", { persona: { persona_id: "P02" } }, load).body).toBe(files.run_p02_ready);
  expect(resolveMock("POST", "/api/runs", { persona: { persona_id: "P05" } }, load).body).toBe(files.run_p01_ready);
});

test("GET a run finds it by run id, else 404", () => {
  expect(resolveMock("GET", "/api/runs/R02", undefined, load).body).toBe(files.run_p02_ready);
  expect(resolveMock("GET", "/api/runs/RXX", undefined, load).status).toBe(404);
});

test("approval and notes give the approved sample; narrative by lang", () => {
  expect(resolveMock("POST", "/api/runs/R01/approval", {}, load).body).toBe(files.run_p01_approved);
  expect(resolveMock("PUT", "/api/runs/R01/notes", {}, load).body).toBe(files.run_p01_approved);
  expect(resolveMock("GET", "/api/runs/R01/narrative?lang=EN", undefined, load).body).toBe(files.narrative_p01_en);
  const approved = resolveMock("POST", "/api/runs/R01/narrative/TR/approval", { text: "x" }, load).body as {
    status: string;
    rm_text: string;
  };
  expect(approved).toMatchObject({ status: "approved", rm_text: "x" });
});

test("brief: the sample of the language, else 202 running", () => {
  const brief = { text: "Kısa özet." };
  const withBrief = (name: string) => (name === "brief_p01_tr" ? brief : undefined);
  expect(resolveMock("GET", "/api/runs/R01/brief?lang=TR", undefined, withBrief)).toEqual({ status: 200, body: brief });
  expect(resolveMock("GET", "/api/runs/R01/brief?lang=EN", undefined, withBrief).status).toBe(202);
});

test("block edit: the sample with the edit; restore; a forbidden phrase gives a blocking finding; empty deletes", () => {
  const load = (name: string) => (name === "narrative_p01_tr" ? { rm_edits: {}, edit_checks: {} } : undefined);
  const put = (text: string | null) => resolveMock("PUT", "/api/runs/R01/narrative/TR/blocks/oneriler%3Afund%3APPN", { text }, load);
  expect(put("Yeni.").body).toMatchObject({ rm_edits: { "oneriler:fund:PPN": "Yeni." }, edit_checks: {} });
  expect(put(null).body).toMatchObject({ rm_edits: {} });
  expect(put("Kesin getiri var.").body).toMatchObject({ edit_checks: { "oneriler:fund:PPN": [expect.stringMatching(/^phrase:/)] } });
  expect(put("").body).toMatchObject({ rm_edits: { "oneriler:fund:PPN": "" }, edit_checks: {} });
  expect(put("  ").body).toMatchObject({ rm_edits: { "oneriler:fund:PPN": "" } });
});

test("unknown path is 404", () => {
  expect(resolveMock("GET", "/api/nothing", undefined, load).status).toBe(404);
});

test("ingest: GET is stale data on the newest snapshot, POST starts a job (202)", () => {
  const withSnapshots = (name: string) => (name === "snapshots" ? ["20261010-183835-6813"] : undefined);
  const get = resolveMock("GET", "/api/ingest", undefined, withSnapshots);
  expect(get.status).toBe(200);
  expect(get.body).toMatchObject({ latest_snapshot: "20261010-183835-6813", stale: true, running: false, error: null });
  const post = resolveMock("POST", "/api/ingest", undefined, withSnapshots);
  expect(post.status).toBe(202);
  expect(post.body).toMatchObject({ running: true });
});

test("research mock: ready view and a refused question", () => {
  const view = resolveMock("GET", "/api/runs/R1/research?lang=TR", undefined, load);
  expect(view.status).toBe(200);
  expect((view.body as { state: string }).state).toBe("ready");
  const product = (view.body as { products: { version: number; news: { date: string }[]; news_days: number; findings: unknown[]; summary: string }[] }).products[0];
  expect(product).toMatchObject({ version: 2, news_days: 90, summary: "" });
  expect(product.news).toHaveLength(1);
  expect(product.news[0].date).toBe("2026-10-12");
  expect(product.findings).toHaveLength(3); // the third is the finding that the mock agent cites (W20)
  expect(resolveMock("POST", "/api/runs/R1/research/questions", { question: "Müşterim için?", lang: "TR" }, load).status).toBe(422);
  const ok = resolveMock("POST", "/api/runs/R1/research/questions", { question: "PPN nedir?", lang: "TR" }, load);
  expect((ok.body as { question: string }).question).toBe("PPN nedir?");
  expect((ok.body as { version: number }).version).toBe(2);
});
