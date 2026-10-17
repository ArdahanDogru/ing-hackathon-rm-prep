import { act, screen, within } from "@testing-library/react";
import { renderWith } from "../test/render";
import { sample } from "../test/samples";
import { NarrativeProgress, STEP_MS } from "./NarrativeProgress";

afterEach(() => vi.useRealTimers());

const states = () => screen.getAllByTestId("prog-step").map((s) => s.dataset.state);

test("the steps come in one by one; the writing step stays open; the check is next", async () => {
  vi.useFakeTimers();
  const v = sample("run_p01_approved");
  renderWith(<NarrativeProgress view={v} />);
  expect(states()).toEqual(["active", "next"]);
  const client = screen.getAllByTestId("prog-step")[0];
  expect(client).toHaveTextContent("Müşteri profili okunuyor");
  expect(client).toHaveTextContent(v.result.persona.yatirim_amaci);
  v.result.persona.oncelikler.forEach((x) => expect(client).toHaveTextContent(x));

  await act(() => vi.advanceTimersByTimeAsync(STEP_MS));
  expect(states()).toEqual(["done", "active", "next"]);
  const options = screen.getAllByTestId("prog-step")[1];
  expect(options).toHaveTextContent(`Onaylanan ${v.result.rm_selected.length} öneri`);
  expect(options).toHaveTextContent("Nurol Para Piyasası (TL) · %7,4 reel");

  await act(() => vi.advanceTimersByTimeAsync(STEP_MS));
  expect(screen.getAllByTestId("prog-step")[2]).toHaveTextContent("TCMB EVDS: mevduat ortalaması +%4,9");

  // each step sets its timer after it renders: advance step by step, then well past the end
  for (let i = 0; i < 6; i++) await act(() => vi.advanceTimersByTimeAsync(STEP_MS));
  expect(states()).toEqual(["done", "done", "done", "done", "active", "next"]);
  const [write, check] = screen.getAllByTestId("prog-step").slice(4);
  expect(write).toHaveTextContent("Yapay zekâ metni yazıyor");
  expect(write).toHaveTextContent("Öneriler");
  expect(within(check).getAllByTestId("prog-chip").map((x) => x.textContent)).toContain("kaynaklar var mı");
  expect(check).toHaveTextContent("bir kez daha yazılır");
});

test("the seconds count up", async () => {
  vi.useFakeTimers();
  renderWith(<NarrativeProgress view={sample("run_p01_approved")} />);
  expect(screen.getByTestId("prog-seconds")).toHaveTextContent("0 sn");
  await act(() => vi.advanceTimersByTimeAsync(3000));
  expect(screen.getByTestId("prog-seconds")).toHaveTextContent("3 sn");
});

test("EN", () => {
  renderWith(<NarrativeProgress view={sample("run_p01_approved")} />, { lang: "EN" });
  expect(screen.getByText("Reading the client profile")).toBeInTheDocument();
  expect(screen.getByText("Preparing the text…")).toBeInTheDocument();
});
