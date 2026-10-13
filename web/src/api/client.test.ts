import { api, ApiError, getRunOrRerun, recallInputs, rememberInputs } from "./client";

afterEach(() => vi.restoreAllMocks());

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

test("422 detail becomes an ApiError", async () => {
  globalThis.fetch = vi.fn().mockResolvedValue(json({ detail: "a rejection needs a note" }, 422));
  await expect(api.approve("R1", "rejected", "", [])).rejects.toEqual(new ApiError(422, "a rejection needs a note"));
});

test("retries a 404 run", async () => {
  const view = { result: { run_id: "R1" } };
  globalThis.fetch = vi
    .fn()
    .mockResolvedValueOnce(json({ detail: "unknown run" }, 404))
    .mockResolvedValueOnce(json(view, 200));
  expect((await getRunOrRerun("R1", { persona: {} as never })).result.run_id).toBe("R1");
});

test("other errors are not retried", async () => {
  const fetch = vi.fn().mockResolvedValue(json({ detail: "boom" }, 500));
  globalThis.fetch = fetch;
  await expect(getRunOrRerun("R1", { persona: {} as never })).rejects.toEqual(new ApiError(500, "boom"));
  expect(fetch).toHaveBeenCalledTimes(1);
});

test("an error without JSON keeps the status text", async () => {
  globalThis.fetch = vi.fn().mockResolvedValue(new Response("gateway", { status: 504, statusText: "Gateway Timeout" }));
  await expect(api.narrative("R1", "TR")).rejects.toMatchObject({ status: 504 });
});

test("requests use the right method, path and body", async () => {
  const fetch = vi.fn().mockImplementation(async () => json({}));
  globalThis.fetch = fetch;
  await api.approve("R1", "approved", "not", ["fund:A", "fund:B"]);
  await api.notes("R1", "n", { "fund:A": "x" });
  await api.narrative("R1", "EN");
  await api.evidence("S 1", "E1");
  const [url, init] = fetch.mock.calls[0];
  expect(url).toBe("/api/runs/R1/approval");
  expect(init.method).toBe("POST");
  expect(JSON.parse(init.body)).toEqual({ status: "approved", note: "not", selected: ["fund:A", "fund:B"] });
  expect(fetch.mock.calls[1][0]).toBe("/api/runs/R1/notes");
  expect(fetch.mock.calls[1][1].method).toBe("PUT");
  expect(fetch.mock.calls[2][0]).toBe("/api/runs/R1/narrative?lang=EN");
  expect(fetch.mock.calls[3][0]).toBe("/api/evidence/S%201/E1");
  expect(api.cardUrl("R1")).toBe("/api/runs/R1/card.md");
});

test("run inputs are remembered per run id", () => {
  rememberInputs("R9", { persona: { persona_id: "P01" } as never, snapshot_id: "S" });
  expect(recallInputs("R9")?.snapshot_id).toBe("S");
  expect(recallInputs("R0")).toBeNull();
});

test("brief: 202 means running, 200 the brief, an error throws", async () => {
  const b = { run_id: "R1", lang: "TR", text: "Kısa özet.", source: "llm", model: "claude-haiku-5-5", prompt_version: "b1", checks: [], created_at: "", cost_usd: 0.003, cite: [] };
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(json({ status: "running" }, 202))
    .mockResolvedValueOnce(json(b, 200))
    .mockResolvedValueOnce(json({ detail: "needs_rm_input" }, 422));
  globalThis.fetch = fetch;
  expect(await api.brief("R1", "TR")).toBe("running");
  expect(await api.brief("R1", "EN")).toEqual(b);
  await expect(api.brief("R1", "TR")).rejects.toEqual(new ApiError(422, "needs_rm_input"));
  expect(fetch.mock.calls[1][0]).toBe("/api/runs/R1/brief?lang=EN");
});

test("editBlock: PUT the block with its text or null", async () => {
  const fetch = vi.fn().mockImplementation(async () => json({}));
  globalThis.fetch = fetch;
  await api.editBlock("R1", "TR", "oneriler:fund:PPN", "Yeni.");
  await api.editBlock("R1", "EN", "ozet", null);
  expect(fetch.mock.calls[0][0]).toBe("/api/runs/R1/narrative/TR/blocks/oneriler%3Afund%3APPN");
  expect(fetch.mock.calls[0][1].method).toBe("PUT");
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ text: "Yeni." });
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ text: null });
});

test("ingest: GET the status, POST starts it (202), 409 when it already runs", async () => {
  const status = { latest_snapshot: "S", running: true };
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(json(status, 200))
    .mockResolvedValueOnce(json(status, 202))
    .mockResolvedValueOnce(json({ detail: "an ingest already runs" }, 409));
  globalThis.fetch = fetch;
  expect(await api.ingestStatus()).toEqual(status);
  expect(await api.startIngest()).toEqual(status);
  await expect(api.startIngest()).rejects.toEqual(new ApiError(409, "an ingest already runs"));
  expect(fetch.mock.calls[0][0]).toBe("/api/ingest");
  expect(fetch.mock.calls[0][1].method).toBe("GET");
  expect(fetch.mock.calls[1][0]).toBe("/api/ingest");
  expect(fetch.mock.calls[1][1].method).toBe("POST");
});
