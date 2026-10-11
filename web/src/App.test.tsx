import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { App } from "./App";
import { api } from "./api/client";
import { sample } from "./test/samples";

beforeEach(() => {
  vi.spyOn(api, "personas").mockResolvedValue(sample("personas"));
  vi.spyOn(api, "snapshots").mockResolvedValue(sample("snapshots"));
  vi.spyOn(api, "sources").mockResolvedValue(sample("sources"));
});
afterEach(() => vi.restoreAllMocks());

test("loads the first persona and makes a run on the newest snapshot", async () => {
  const run = vi.spyOn(api, "run").mockResolvedValue(sample("run_p01_ready"));
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  );
  expect(await screen.findByTestId("client-card")).toBeInTheDocument();
  expect(run.mock.calls[0][0].persona.persona_id).toBe("P01");
  expect(run.mock.calls[0][0].snapshot_id).toBe(sample("snapshots")[0]);
  expect(screen.getByText("ING")).toBeInTheDocument();
});

test("another persona or an excluded source makes a new run", async () => {
  const run = vi.spyOn(api, "run").mockResolvedValue(sample("run_p01_ready"));
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  );
  await screen.findByTestId("client-card");
  await userEvent.selectOptions(screen.getByRole("combobox", { name: /Müşteri/ }), "P02");
  await waitFor(() => expect(run.mock.calls.at(-1)![0].persona.persona_id).toBe("P02"));
  await userEvent.click(screen.getByRole("button", { name: "Veri ▾" }));
  await userEvent.click(screen.getByRole("checkbox", { name: /evds/ }));
  await waitFor(() => expect(run.mock.calls.at(-1)![0].exclude_sources).toEqual(["evds"]));
});

test("TR / EN switches the labels", async () => {
  vi.spyOn(api, "run").mockResolvedValue(sample("run_p01_ready"));
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  );
  await screen.findByTestId("client-card");
  await userEvent.click(screen.getByRole("button", { name: "EN" }));
  expect(screen.getByText("Meeting preparation")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "EN" })).toHaveAttribute("aria-pressed", "true");
});

test("an API error shows its detail and Tekrar dene", async () => {
  vi.spyOn(api, "run").mockRejectedValue(new Error("evidence store is locked"));
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  );
  expect(await screen.findByText(/evidence store is locked/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Tekrar dene" })).toBeInTheDocument();
});
