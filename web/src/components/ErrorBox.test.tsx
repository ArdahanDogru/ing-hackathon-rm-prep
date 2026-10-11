import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../api/client";
import { ErrorBox } from "./ErrorBox";

test("api error shows the detail and retries", async () => {
  const retry = vi.fn();
  render(<ErrorBox error={new ApiError(500, "boom")} onRetry={retry} />);
  await userEvent.click(screen.getByRole("button", { name: "Tekrar dene" }));
  expect(screen.getByText(/boom/)).toBeInTheDocument();
  expect(retry).toHaveBeenCalled();
});

test("a 504 says that the text is not ready yet", () => {
  render(<ErrorBox error={new ApiError(504, "the meeting text is not ready yet; try again")} onRetry={() => {}} />);
  expect(screen.getByRole("alert")).toHaveTextContent("504");
});
