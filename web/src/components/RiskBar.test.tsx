import { render, screen } from "@testing-library/react";
import { RiskBar, riskColor } from "./RiskBar";

test("level colors", () => {
  expect(riskColor(1)).toBe("#12B76A");
  expect(riskColor(4)).toBe("#F79009");
  expect(riskColor(7)).toBe("#D92D20");
});

test("all filled segments take the level color, with text", () => {
  render(<RiskBar level={4} />);
  const segs = screen.getAllByTestId("risk-seg");
  expect(segs).toHaveLength(7);
  expect(segs.filter((s) => s.style.backgroundColor !== "")).toHaveLength(7);
  expect(segs.slice(0, 4).every((s) => s.dataset.filled === "true")).toBe(true);
  expect(segs.slice(4).every((s) => s.dataset.filled === "false")).toBe(true);
  expect(segs[0].style.backgroundColor).toBe("rgb(247, 144, 9)");
  expect(segs[6].style.backgroundColor).toBe("rgb(228, 231, 236)");
  expect(screen.getByText("4 / 7")).toBeInTheDocument();
});
