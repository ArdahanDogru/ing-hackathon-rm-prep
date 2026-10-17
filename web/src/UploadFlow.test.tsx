// W31: "Yükle" next to the client dropdown: upload a client JSON.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { App } from "./App";
import { api, ApiError } from "./api/client";
import type { Persona } from "./api/types";
import { sample } from "./test/samples";

const WARNING = "Gerçek müşteri verisi yüklemeyin. Profil bu bilgisayarda saklanır; AI özeti, metin ve ajan için Anthropic'e gönderilir.";
const upload = (): Persona => ({ ...sample("personas")[0], persona_id: "DEMO1", profil: "Demo müşteri" });
const file = (text: string, name = "demo.json") => new File([text], name, { type: "application/json" });

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(api, "personas").mockResolvedValue(sample("personas"));
  vi.spyOn(api, "uploadedPersonas").mockResolvedValue([]);
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
const uploadButton = () => within(screen.getByRole("banner")).getByRole("button", { name: "Yükle" });

async function openDialog() {
  await userEvent.click(uploadButton());
  return screen.getByRole("dialog", { name: /Müşteri yükle/ });
}

test("the button next to the dropdown opens the dialog with the file picker and the KVKK warning; Vazgeç closes it", async () => {
  await open();
  const post = vi.spyOn(api, "uploadPersona");
  const dialog = await openDialog();
  expect(dialog).toHaveTextContent(WARNING);
  const input = within(dialog).getByLabelText("JSON dosyası") as HTMLInputElement;
  expect(input.type).toBe("file");
  expect(input.accept).toBe(".json,application/json");
  expect(within(dialog).getByRole("button", { name: "Yükle" })).toBeDisabled();
  await userEvent.click(within(dialog).getByRole("button", { name: "Vazgeç" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(post).not.toHaveBeenCalled();
});

test("a file that is not JSON: the text in the dialog, no request", async () => {
  await open();
  const post = vi.spyOn(api, "uploadPersona");
  const dialog = await openDialog();
  await userEvent.upload(within(dialog).getByLabelText("JSON dosyası"), file("{ not json"));
  await userEvent.click(within(dialog).getByRole("button", { name: "Yükle" }));
  expect(await within(dialog).findByRole("alert")).toHaveTextContent("Dosya okunamadı: geçerli bir JSON değil.");
  expect(post).not.toHaveBeenCalled();
});

test("a 422 shows the server text in the dialog; the dialog stays", async () => {
  await open();
  vi.spyOn(api, "uploadPersona").mockRejectedValue(new ApiError(422, "Eksik alan: risk_profili"));
  const dialog = await openDialog();
  await userEvent.upload(within(dialog).getByLabelText("JSON dosyası"), file(JSON.stringify({ persona_id: "X" })));
  await userEvent.click(within(dialog).getByRole("button", { name: "Yükle" }));
  expect(await within(dialog).findByRole("alert")).toHaveTextContent("Eksik alan: risk_profili");
  expect(screen.getByRole("dialog")).toBe(dialog);
});

test("success: the JSON is posted, the list is loaded again, the new client is selected and its run made", async () => {
  const run = await open();
  const p = upload();
  const post = vi.spyOn(api, "uploadPersona").mockResolvedValue({ persona: p, replaced: false });
  const dialog = await openDialog();
  vi.spyOn(api, "personas").mockResolvedValue([...sample("personas"), p]);
  vi.spyOn(api, "uploadedPersonas").mockResolvedValue(["DEMO1"]);
  await userEvent.upload(within(dialog).getByLabelText("JSON dosyası"), file(JSON.stringify(p)));
  await userEvent.click(within(dialog).getByRole("button", { name: "Yükle" }));
  expect(post).toHaveBeenCalledWith(p);
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  const select = screen.getByRole("combobox", { name: /Müşteri/ }) as HTMLSelectElement;
  await waitFor(() => expect(select.value).toBe("DEMO1"));
  await waitFor(() => expect(run.mock.calls.at(-1)![0].persona.persona_id).toBe("DEMO1"));
  expect(within(select).getByRole("option", { name: /DEMO1 · Demo müşteri \(yüklendi\)/ })).toBeInTheDocument();
});

test("the dropdown marks uploaded clients", async () => {
  vi.spyOn(api, "personas").mockResolvedValue([...sample("personas"), upload()]);
  vi.spyOn(api, "uploadedPersonas").mockResolvedValue(["DEMO1"]);
  await open();
  const select = screen.getByRole("combobox", { name: /Müşteri/ });
  expect(within(select).getByRole("option", { name: "DEMO1 · Demo müşteri (yüklendi)" })).toBeInTheDocument();
  expect(within(select).getByRole("option", { name: /^P01 · / }).textContent).not.toContain("yüklendi");
});

test("a server without uploads: the list still loads, no mark", async () => {
  vi.spyOn(api, "uploadedPersonas").mockRejectedValue(new ApiError(404, "Not Found"));
  await open();
  expect(screen.queryByText(/yüklendi/)).toBeNull();
});

test("W31 EN", async () => {
  localStorage.setItem("rmprep.lang", "EN");
  vi.spyOn(api, "personas").mockResolvedValue([...sample("personas"), upload()]);
  vi.spyOn(api, "uploadedPersonas").mockResolvedValue(["DEMO1"]);
  await open();
  expect(within(screen.getByRole("combobox", { name: /Client/ })).getByRole("option", { name: "DEMO1 · Demo müşteri (uploaded)" })).toBeInTheDocument();
  await userEvent.click(within(screen.getByRole("banner")).getByRole("button", { name: "Upload" }));
  const dialog = screen.getByRole("dialog", { name: /Upload a client/ });
  expect(dialog).toHaveTextContent("Do not upload real client data.");
  expect(within(dialog).getByLabelText("JSON file")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeInTheDocument();
});
