import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { sample } from "../test/samples";
import { PipelinePanel } from "./PipelinePanel";

const setup = () => {
  const v = sample("run_p01_ready");
  const onOpen = vi.fn();
  const onDetails = vi.fn();
  render(<PipelinePanel view={v} onOpen={onOpen} onDetails={onDetails} />);
  return { v, onOpen, onDetails };
};

test("open by default; the summary line with the counts closes it", async () => {
  const { v } = setup();
  const scored = v.result.options.length;
  const rejected = v.result.rejected.length;
  expect(screen.getByRole("button", { name: /Bu öneriler nasıl seçildi\?/ })).toHaveTextContent(
    `${scored + rejected} seçenek → ${rejected} elendi → ${scored} puanlandı → 3 öneri`,
  );
  expect(screen.getAllByTestId("pipeline-step")).toHaveLength(5);
  await userEvent.click(screen.getByRole("button", { name: /Bu öneriler nasıl seçildi\?/ }));
  expect(screen.queryAllByTestId("pipeline-step")).toHaveLength(0);
});

test("five steps, the rules with their counts, the three picks", () => {
  const { v } = setup();
  const steps = screen.getAllByTestId("pipeline-step");
  expect(steps).toHaveLength(5);
  expect(steps[0]).toHaveTextContent(`Risk ≤ ${v.risk_ceiling}`);
  expect(steps[0]).toHaveTextContent(v.result.persona.gelir_nakit_akisi_ihtiyaci);
  v.rejected_by_rule.forEach((x) => expect(steps[2]).toHaveTextContent(`${x.label}${x.count}`));
  expect(within(steps[4]).getAllByRole("button")).toHaveLength(v.result.recommended.length);
  expect(steps[4]).toHaveTextContent("genel 1. sıra");
});

test("a pick opens its fund card; a step link opens its details tab", async () => {
  const { v, onOpen, onDetails } = setup();
  const steps = screen.getAllByTestId("pipeline-step");
  await userEvent.click(within(steps[4]).getAllByRole("button")[0]);
  expect(onOpen).toHaveBeenCalledWith(v.result.recommended[0]);
  await userEvent.click(screen.getByRole("button", { name: "Elenenleri gör" }));
  expect(onDetails).toHaveBeenCalledWith("eliminated");
});

test("a pick below other options of its group is not ranked first there", () => {
  const { v } = setup();
  const picks = within(screen.getAllByTestId("pipeline-step")[4]).getAllByRole("button");
  // fund:IST is 20th overall and the best debt fund
  expect(picks[v.result.recommended.indexOf("fund:IST")]).toHaveTextContent("genel 20. sıra, kendi grubunda 1.");
});

test("no recommendation, no pipeline", () => {
  const v = sample("run_needs_input");
  const { container } = render(<PipelinePanel view={v} onOpen={vi.fn()} onDetails={vi.fn()} />);
  expect(container).toBeEmptyDOMElement();
});
