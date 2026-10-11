import { render, screen } from "@testing-library/react";
import { ReturnBars } from "./ReturnBars";

test("fund cobalt, category grey, delta pill", () => {
  render(<ReturnBars rows={[{ period: "1y", fund: 47.6, category: 44.5 }]} />);
  expect(screen.getByTestId("bar-fund-1y").style.backgroundColor).toBe("rgb(70, 118, 191)");
  expect(screen.getByTestId("bar-cat-1y").style.backgroundColor).toBe("rgb(208, 213, 221)");
  expect(screen.getByText("+3,1 puan")).toBeInTheDocument();
});

test("a missing value gives no bar and no pill", () => {
  render(<ReturnBars rows={[{ period: "3m", fund: null, category: 10 }]} />);
  expect(screen.queryByTestId("bar-fund-3m")).toBeNull();
  expect(screen.queryByText(/puan/)).toBeNull();
});
