// W20b: step 5 "Öneri" of the pipeline panel with the agent decision (the status the dashboard polls).
import { render, screen, waitFor, within } from "@testing-library/react";
import { api } from "../api/client";
import { agentDecision } from "../api/agentSample";
import type { AgentDecision, Lang, RunView } from "../api/types";
import { LangContext } from "../i18n";
import { renderDashboard } from "../test/render";
import { sample } from "../test/samples";
import { PipelinePanel } from "./PipelinePanel";

afterEach(() => vi.restoreAllMocks());

const view = () => sample("run_p01_ready");
const ranked = (v: RunView) =>
  [...v.result.options].sort((a, b) => b.score - a.score || a.option.option_id.localeCompare(b.option.option_id)).map((o) => o.option.option_id);
const name = (v: RunView, id: string) => [v.options[id].issuer, v.options[id].short_label].filter(Boolean).join(" ");

function step5(v: RunView, agent: AgentDecision | null, lang: Lang = "TR") {
  render(
    <LangContext.Provider value={lang}>
      <PipelinePanel view={v} onOpen={vi.fn()} onDetails={vi.fn()} agent={agent} />
    </LangContext.Provider>,
  );
  return screen.getAllByTestId("pipeline-step")[4];
}
/** The pick names without the W28 code badge and the W32 product badges. */
const pickNames = (step: HTMLElement) =>
  within(step)
    .getAllByTestId("pipe-pick")
    .map((p) => {
      const b = p.querySelector("b")!.cloneNode(true) as HTMLElement;
      b.querySelectorAll("[data-testid=code-badge], [data-testid=product-badge]").forEach((x) => x.remove());
      return b.textContent;
    });

test("running: the engine's picks and the line Ajan değerlendiriyor…", () => {
  const v = view();
  const step = step5(v, agentDecision(v, "running"));
  expect(pickNames(step)).toEqual(v.result.recommended.map((id) => name(v, id)));
  expect(within(step).getByTestId("pipe-agent")).toHaveTextContent("Ajan değerlendiriyor…");
  expect(step).not.toHaveTextContent("Ajan önerisi");
});

test("done: the agent's picks with the badge, the engine place of a new pick, the engine's line", () => {
  const v = view();
  const d = agentDecision(v, "done");
  const step = step5(v, d);
  expect(pickNames(step)).toEqual(d.picks.map((p) => name(v, p.option_id)));
  expect(within(step).getByText("Ajan önerisi")).toBeInTheDocument();
  const fresh = d.picks.findIndex((p) => !d.engine_top3.includes(p.option_id));
  const place = ranked(v).indexOf(d.picks[fresh].option_id) + 1;
  const picks = within(step).getAllByTestId("pipe-pick");
  expect(picks[fresh]).toHaveTextContent(`motor: puana göre ${place}.`);
  expect(picks[0]).not.toHaveTextContent("motor:");
  expect(within(step).getByTestId("pipe-agent")).toHaveTextContent(
    `Motorun önerisi: ${d.engine_top3.map((id) => name(v, id)).join(", ")}`,
  );
});

test("done: a pick that the engine did not rank says motorun ilk 3'ünde değil", () => {
  const v = view();
  const d = agentDecision(v, "done");
  // a pick outside the scored options (the engine has no place for it)
  v.result.options = v.result.options.filter((o) => o.option.option_id !== d.picks[1].option_id);
  const step = step5(v, d);
  expect(within(step).getAllByTestId("pipe-pick")[1]).toHaveTextContent("motorun ilk 3'ünde değil");
});

test("fallback: the engine's picks with the reason", () => {
  const v = view();
  const d = agentDecision(v, "fallback");
  const step = step5(v, d);
  expect(pickNames(step)).toEqual(v.result.recommended.map((id) => name(v, id)));
  expect(within(step).getByTestId("pipe-agent")).toHaveTextContent(`Ajan: motor önerisi kullanıldı (${d.fallback_reason})`);
});

test("off or no agent: unchanged", () => {
  const v = view();
  const step = step5(v, agentDecision(v, "off"));
  expect(within(step).queryByTestId("pipe-agent")).toBeNull();
  expect(pickNames(step)).toEqual(v.result.recommended.map((id) => name(v, id)));
});

test("W20b EN", () => {
  const v = view();
  const d = agentDecision(v, "done");
  const step = step5(v, d, "EN");
  expect(within(step).getByText("Agent recommendation")).toBeInTheDocument();
  const fresh = d.picks.findIndex((p) => !d.engine_top3.includes(p.option_id));
  const n = ranked(v).indexOf(d.picks[fresh].option_id) + 1;
  const ord = n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  expect(within(step).getAllByTestId("pipe-pick")[fresh]).toHaveTextContent(`engine: ${n}${ord} by score`);
  expect(within(step).getByTestId("pipe-agent")).toHaveTextContent("The engine's recommendation:");
});

test("the dashboard passes its one agent status to the pipeline (no second poll)", async () => {
  const v = view();
  const get = vi.spyOn(api, "agentStatus").mockResolvedValue(agentDecision(v, "done"));
  renderDashboard(v);
  const step = (await screen.findAllByTestId("pipeline-step"))[4];
  await waitFor(() => expect(within(step).getByText("Ajan önerisi")).toBeInTheDocument());
  expect(get).toHaveBeenCalledTimes(1);
});
