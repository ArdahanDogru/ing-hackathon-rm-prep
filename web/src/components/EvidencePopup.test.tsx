import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api, ApiError } from "../api/client";
import { sample } from "../test/samples";
import { EvidencePopup } from "./EvidencePopup";

afterEach(() => vi.restoreAllMocks());

test("evidence pop-up shows source and date", async () => {
  const item = sample("evidence_item");
  const get = vi.spyOn(api, "evidence").mockResolvedValue(item);
  render(<EvidencePopup snapshotId="S" evidenceId={item.id} open onClose={() => {}} />);
  expect(await screen.findByText(item.source)).toBeInTheDocument();
  // the value date and the fetch time, in Turkish format (Europe/Istanbul)
  const [y, m, d] = item.as_of.split("-");
  expect(screen.getByText(`${d}.${m}.${y}`)).toBeInTheDocument();
  expect(screen.getByTestId("fetched-at")).toHaveTextContent(/^Alındı: \d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$/);
  expect(screen.getByText(item.id)).toBeInTheDocument();
  expect(screen.getByText(item.entity_name)).toBeInTheDocument();
  expect(get).toHaveBeenCalledWith("S", item.id);
});

test("closed: nothing rendered, nothing fetched", () => {
  const get = vi.spyOn(api, "evidence");
  render(<EvidencePopup snapshotId="S" evidenceId="E1" open={false} onClose={() => {}} />);
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(get).not.toHaveBeenCalled();
});

test("an unknown id shows the API detail; Kapat closes", async () => {
  vi.spyOn(api, "evidence").mockRejectedValue(new ApiError(404, "unknown evidence id E1"));
  const onClose = vi.fn();
  render(<EvidencePopup snapshotId="S" evidenceId="E1" open onClose={onClose} />);
  expect(await screen.findByText(/unknown evidence id E1/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Kapat" }));
  expect(onClose).toHaveBeenCalled();
});
