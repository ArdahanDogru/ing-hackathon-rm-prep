import { render, screen } from "@testing-library/react";
import { sample } from "../test/samples";
import { DetailsPanel } from "./DetailsPanel";

test("a request opens the panel on its tab (W17 pipeline links)", () => {
  const v = sample("run_p01_ready");
  const props = { view: v, selected: [], onToggle: vi.fn(), onOpen: vi.fn() };
  const { rerender } = render(<DetailsPanel {...props} request={null} />);
  expect(screen.queryByRole("tablist")).toBeNull();
  rerender(<DetailsPanel {...props} request={{ tab: "eliminated", n: 1 }} />);
  expect(screen.getByRole("tab", { selected: true })).toHaveTextContent(/^Elenen \(/);
});
