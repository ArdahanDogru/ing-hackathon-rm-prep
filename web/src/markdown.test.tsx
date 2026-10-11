import { render, screen } from "@testing-library/react";
import { Markdown } from "./markdown";

test("headings, paragraphs, lists, bold; HTML stays text", () => {
  const md = "# Başlık\n\n## Alt\n\nBir **kalın** söz.\nDevam.\n\n- bir\n- iki\n\n<script>x</script>";
  const { container } = render(<Markdown text={md} />);
  expect(screen.getByRole("heading", { level: 1, name: "Başlık" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 2, name: "Alt" })).toBeInTheDocument();
  expect(screen.getByText("kalın").tagName).toBe("STRONG");
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
  expect(container.querySelector("script")).toBeNull();
  expect(screen.getByText("<script>x</script>")).toBeInTheDocument();
});
