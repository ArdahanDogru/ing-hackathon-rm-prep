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
  const fetch = vi.fn().mockResolvedValue(json({}));
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
