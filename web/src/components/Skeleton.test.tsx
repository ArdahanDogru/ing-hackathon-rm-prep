import { render, screen } from "@testing-library/react";
import { DashboardSkeleton } from "./Skeleton";

test("the skeleton is marked busy for screen readers", () => {
  render(<DashboardSkeleton />);
  expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
  expect(screen.getByText("Yükleniyor…")).toBeInTheDocument();
});
