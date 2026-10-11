import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OptionNotes } from "./Notes";

test("data notes on a card are one closed line that opens", async () => {
  const notes = [
    { message: "tefas_detail: 739 değer işaretli.", flags: ["needs_check"], sources: ["tefas_detail"], evidence_ids: [] },
    { message: "manual: 7 değer işaretli.", flags: ["manual_entry"], sources: ["manual"], evidence_ids: [] },
  ];
  render(<OptionNotes notes={notes} />);
  expect(screen.queryByText(notes[0].message)).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Veri notları · 2" }));
  expect(screen.getByText(notes[0].message)).toBeInTheDocument();
});
