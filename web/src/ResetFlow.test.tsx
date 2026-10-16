// W27: "Sıfırla" in the top bar: every client back to the first state.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { App } from "./App";
import { api, ApiError } from "./api/client";
import { sample } from "./test/samples";

const RESULT = {
  archive: "data/reset-archive/20261017-101500",
  moved: { runs: 2, texts: 1, cards: 1, agent: 1, research_marks: 3 },
};
const TEXT_TR =
  "Tüm müşteriler ilk hâline döner: onaylar ve notlar, portföy dağılımları, ajan sonuçları, araştırma işaretleri, metin düzenlemeleri ve kartlar. Eski kayıtlar arşive taşınır; veriler ve RM eylem günlüğü kalır.";

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  vi.spyOn(api, "personas").mockResolvedValue(sample("personas"));
  vi.spyOn(api, "snapshots").mockResolvedValue(sample("snapshots"));
  vi.spyOn(api, "sources").mockResolvedValue(sample("sources"));
  vi.spyOn(api, "ingestStatus").mockRejectedValue(new Error("no ingest"));
  vi.spyOn(api, "agentStatus").mockResolvedValue(null);
});
afterEach(() => vi.restoreAllMocks());

async function open() {
  const run = vi.spyOn(api, "run").mockResolvedValue(sample("run_p01_ready"));
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  );
  await screen.findByTestId("brief-card");
  return run;
}
const resetButton = () => within(screen.getByRole("banner")).getByRole("button", { name: "Sıfırla" });

test("the button in the top bar opens the confirmation; Vazgeç closes it without a request", async () => {
  await open();
  const reset = vi.spyOn(api, "reset");
  await userEvent.click(resetButton());
  const dialog = screen.getByRole("dialog", { name: /Tüm müşterileri sıfırla/ });
  expect(dialog).toHaveTextContent(TEXT_TR);
  expect(within(dialog).getByRole("button", { name: "Sıfırla" })).toBeInTheDocument();
  await userEvent.click(within(dialog).getByRole("button", { name: "Vazgeç" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(reset).not.toHaveBeenCalled();
});

test("Sıfırla: the request, the RM keys removed (language and view mode kept), the run loaded again, the success line", async () => {
  const run = await open();
  const runId = sample("run_p01_ready").result.run_id;
  localStorage.setItem(`rmprep.agenda.${runId}`, "[0]");
  localStorage.setItem(`rmprep.confirm.${runId}`, "[1]");
  localStorage.setItem("rmprep.lang", "TR");
  localStorage.setItem("rmprep.view.oneriler", "table");
  localStorage.setItem("other.app", "x");
  sessionStorage.setItem("rmprep.inputs.R-old", "{}");
  const reset = vi.spyOn(api, "reset").mockResolvedValue(RESULT);
  const before = run.mock.calls.length;
  await userEvent.click(resetButton());
  await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Sıfırla" }));
  expect(reset).toHaveBeenCalledTimes(1);
  expect(await screen.findByText(`Sıfırlandı. Eski kayıtlar: ${RESULT.archive}`)).toBeInTheDocument();
  expect(localStorage.getItem(`rmprep.agenda.${runId}`)).toBeNull();
  expect(localStorage.getItem(`rmprep.confirm.${runId}`)).toBeNull();
  expect(localStorage.getItem("rmprep.lang")).toBe("TR");
  expect(localStorage.getItem("rmprep.view.oneriler")).toBe("table");
  expect(localStorage.getItem("other.app")).toBe("x");
  expect(sessionStorage.getItem("rmprep.inputs.R-old")).toBeNull(); // the new run writes its own inputs again
  await waitFor(() => expect(run.mock.calls.length).toBe(before + 1));
  const inputs = run.mock.calls.at(-1)![0];
  expect(inputs.persona.persona_id).toBe("P01");
  expect(inputs.exclude_sources).toEqual([]);
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("an open drawer is closed by the reset", async () => {
  await open();
  vi.spyOn(api, "reset").mockResolvedValue(RESULT);
  await userEvent.click(screen.getAllByTestId("option-card")[0]);
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  await userEvent.click(resetButton());
  await userEvent.click(within(screen.getByRole("dialog", { name: /Tüm müşterileri sıfırla/ })).getByRole("button", { name: "Sıfırla" }));
  await screen.findByText(/Sıfırlandı\./);
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

test("409 while the agent runs: the server text in the dialog, nothing reset", async () => {
  const run = await open();
  const runId = sample("run_p01_ready").result.run_id;
  localStorage.setItem(`rmprep.agenda.${runId}`, "[0]");
  vi.spyOn(api, "reset").mockRejectedValue(new ApiError(409, "Ajan çalışıyor; bitince sıfırlayın."));
  const before = run.mock.calls.length;
  await userEvent.click(resetButton());
  const dialog = screen.getByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Sıfırla" }));
  expect(await within(dialog).findByRole("alert")).toHaveTextContent("Ajan çalışıyor; bitince sıfırlayın.");
  expect(localStorage.getItem(`rmprep.agenda.${runId}`)).toBe("[0]");
  expect(run.mock.calls.length).toBe(before);
  expect(screen.queryByText(/Sıfırlandı\./)).toBeNull();
});

test("another error: the error box with the server text", async () => {
  await open();
  vi.spyOn(api, "reset").mockRejectedValue(new ApiError(500, "disk full"));
  await userEvent.click(resetButton());
  await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Sıfırla" }));
  expect(await screen.findByText(/disk full/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Tekrar dene" })).toBeInTheDocument();
});

test("W27 EN", async () => {
  localStorage.setItem("rmprep.lang", "EN");
  await open();
  vi.spyOn(api, "reset").mockResolvedValue(RESULT);
  await userEvent.click(within(screen.getByRole("banner")).getByRole("button", { name: "Reset" }));
  const dialog = screen.getByRole("dialog", { name: /Reset all clients/ });
  expect(dialog).toHaveTextContent("Every client goes back to the first state");
  expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  await userEvent.click(within(dialog).getByRole("button", { name: "Reset" }));
  expect(await screen.findByText(`Reset done. Old records: ${RESULT.archive}`)).toBeInTheDocument();
  expect(localStorage.getItem("rmprep.lang")).toBe("EN");
});
