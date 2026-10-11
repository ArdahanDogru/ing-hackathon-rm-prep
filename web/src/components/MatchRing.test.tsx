import { render, screen } from "@testing-library/react";
import { MatchRing, matchColor } from "./MatchRing";

test("number is always shown, color red to green", () => {
  render(<MatchRing value={8.2} />);
  expect(screen.getByText("8,2")).toBeInTheDocument();
  expect(matchColor(0)).not.toBe(matchColor(10));
  expect(matchColor(0)).toBe("#D92D20");
  expect(matchColor(10)).toBe("#12B76A");
});

test("whole numbers have no decimal", () => {
  render(<MatchRing value={10} />);
  expect(screen.getByText("10")).toBeInTheDocument();
});
