import { render, screen } from "@testing-library/react";
import { Stars } from "./Stars";

test("count stars on, the rest off, with a text label", () => {
  render(<Stars count={3} />);
  expect(screen.getAllByTestId("star-on")).toHaveLength(3);
  expect(screen.getAllByTestId("star-off")).toHaveLength(2);
  expect(screen.getByLabelText("5 üzerinden 3 yıldız")).toBeInTheDocument();
});
