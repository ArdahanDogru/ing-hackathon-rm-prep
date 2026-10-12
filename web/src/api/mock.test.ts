import { resolveMock } from "./mock";

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

test("block edit: the sample with the edit; restore; a forbidden phrase gives a blocking finding; empty is 422", () => {
  const load = (name: string) => (name === "narrative_p01_tr" ? { rm_edits: {}, edit_checks: {} } : undefined);
  const put = (text: string | null) => resolveMock("PUT", "/api/runs/R01/narrative/TR/blocks/oneriler%3Afund%3APPN", { text }, load);
  expect(put("Yeni.").body).toMatchObject({ rm_edits: { "oneriler:fund:PPN": "Yeni." }, edit_checks: {} });
  expect(put(null).body).toMatchObject({ rm_edits: {} });
  expect(put("Kesin getiri var.").body).toMatchObject({ edit_checks: { "oneriler:fund:PPN": [expect.stringMatching(/^phrase:/)] } });
  expect(put("  ").status).toBe(422);
});

test("unknown path is 404", () => {
  expect(resolveMock("GET", "/api/nothing", undefined, load).status).toBe(404);
});
