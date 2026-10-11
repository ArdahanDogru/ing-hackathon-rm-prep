import { render, screen } from "@testing-library/react";
import { DeltaPill } from "./DeltaPill";

test("positive is green with a plus sign", () => {
  render(<DeltaPill points={3.14} />);
  const pill = screen.getByText("+3,1 puan");
  expect(pill.dataset.tone).toBe("good");
});

test("negative is red with a minus sign", () => {
  render(<DeltaPill points={-0.75} />);
  const pill = screen.getByText("−0,8 puan");
  expect(pill.dataset.tone).toBe("bad");
});

test("zero is neutral", () => {
  render(<DeltaPill points={0} />);
  expect(screen.getByText("0 puan").dataset.tone).toBe("neutral");
});
