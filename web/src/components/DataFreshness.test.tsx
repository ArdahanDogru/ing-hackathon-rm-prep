import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError, api } from "../api/client";
import type { Lang } from "../api/types";
import { LangContext } from "../i18n";
import { ingestSample, sample } from "../test/samples";
import { DataFreshness } from "./DataFreshness";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function show(onOpenNewest = () => {}, lang: Lang = "TR") {
  return render(
    <LangContext.Provider value={lang}>
      <DataFreshness known={sample("snapshots")} onOpenNewest={onOpenNewest} />
    </LangContext.Provider>,
  );
}

test("W53: fresh data and no job: Veri güncel with its date and time, and Veriyi yenile", async () => {
  vi.spyOn(api, "ingestStatus").mockResolvedValue(ingestSample("fresh"));
  const start = vi.spyOn(api, "startIngest").mockResolvedValue(ingestSample("running"));
  show();
  expect(await screen.findByText("Veri güncel (10.10.2026 18:38).")).toBeInTheDocument();
  expect(screen.getByText("yaklaşık 15 dakika sürer")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Veriyi yenile" }));
  expect(start).toHaveBeenCalledTimes(1);
});

test("no ingest endpoint (an older API): no line", async () => {
  const get = vi.spyOn(api, "ingestStatus").mockRejectedValue(new ApiError(404, "Not Found"));
  const { container } = show();
  await waitFor(() => expect(get).toHaveBeenCalled());
  expect(container).toBeEmptyDOMElement();
});

test("stale: the age, the date and Veriyi yenile with its hint", async () => {
  vi.spyOn(api, "ingestStatus").mockResolvedValue(ingestSample("stale"));
  show();
  expect(await screen.findByText("Veri 3 gün önce alındı (10.10.2026).")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Veriyi yenile" })).toBeInTheDocument();
  expect(screen.getByText("yaklaşık 15 dakika sürer")).toBeInTheDocument();
});

test("Veriyi yenile starts the ingest and shows it running", async () => {
  vi.spyOn(api, "ingestStatus").mockResolvedValue(ingestSample("stale"));
  const start = vi.spyOn(api, "startIngest").mockResolvedValue(ingestSample("running"));
  show();
  await userEvent.click(await screen.findByRole("button", { name: "Veriyi yenile" }));
  expect(start).toHaveBeenCalledTimes(1);
  expect(await screen.findByText("Veri alınıyor… (başladı 07:30)")).toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

test("409 (another process runs it): the line shows the running job", async () => {
  const get = vi
    .spyOn(api, "ingestStatus")
    .mockResolvedValueOnce(ingestSample("stale"))
    .mockResolvedValue(ingestSample("running"));
  vi.spyOn(api, "startIngest").mockRejectedValue(new ApiError(409, "an ingest already runs"));
  show();
  await userEvent.click(await screen.findByRole("button", { name: "Veriyi yenile" }));
  expect(await screen.findByText("Veri alınıyor… (başladı 07:30)")).toBeInTheDocument();
  expect(get).toHaveBeenCalledTimes(2);
});

test("running: asks the status every 15 s, then offers the newer data", async () => {
  vi.useFakeTimers();
  const get = vi
    .spyOn(api, "ingestStatus")
    .mockResolvedValueOnce(ingestSample("running"))
    .mockResolvedValueOnce(ingestSample("running"))
    .mockResolvedValue(ingestSample("finished_newer"));
  show();
  await act(() => vi.advanceTimersByTimeAsync(0));
  expect(screen.getByText("Veri alınıyor… (başladı 07:30)")).toBeInTheDocument();
  await act(() => vi.advanceTimersByTimeAsync(14_000));
  expect(get).toHaveBeenCalledTimes(1);
  await act(() => vi.advanceTimersByTimeAsync(1_000));
  expect(get).toHaveBeenCalledTimes(2);
  await act(() => vi.advanceTimersByTimeAsync(15_000));
  expect(get).toHaveBeenCalledTimes(3);
  expect(screen.getByText("Yeni veri hazır (14.10.2026).")).toBeInTheDocument();
  await act(() => vi.advanceTimersByTimeAsync(60_000));
  expect(get).toHaveBeenCalledTimes(3); // no job: no more polling
});

test("a newer snapshot: Yeni veriyle aç asks the app to open it, no automatic switch", async () => {
  vi.spyOn(api, "ingestStatus").mockResolvedValue(ingestSample("finished_newer"));
  const open = vi.fn();
  show(open);
  const button = await screen.findByRole("button", { name: "Yeni veriyle aç" });
  expect(open).not.toHaveBeenCalled();
  await userEvent.click(button);
  expect(open).toHaveBeenCalledTimes(1);
});

test("the newest snapshot is on the list already: no Yeni veriyle aç, the fresh line with Veriyi yenile", async () => {
  vi.spyOn(api, "ingestStatus").mockResolvedValue(ingestSample("finished_newer"));
  render(<DataFreshness known={["20261014-074512-a1b2", ...sample("snapshots")]} onOpenNewest={() => {}} />);
  expect(await screen.findByText("Veri güncel (14.10.2026 07:45).")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Veriyi yenile" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Yeni veriyle aç" })).toBeNull();
});

test("error: the error text and Tekrar dene starts the ingest again", async () => {
  vi.spyOn(api, "ingestStatus").mockResolvedValue(ingestSample("error"));
  const start = vi.spyOn(api, "startIngest").mockResolvedValue(ingestSample("running"));
  show();
  expect(await screen.findByText("Veri alınamadı: EVDS: HTTP 503")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Tekrar dene" }));
  expect(start).toHaveBeenCalledTimes(1);
  expect(await screen.findByText(/Veri alınıyor/)).toBeInTheDocument();
});

test("a failed start shows its error and Tekrar dene", async () => {
  vi.spyOn(api, "ingestStatus").mockResolvedValue(ingestSample("stale"));
  vi.spyOn(api, "startIngest").mockRejectedValue(new ApiError(500, "lock file is not writable"));
  show();
  await userEvent.click(await screen.findByRole("button", { name: "Veriyi yenile" }));
  expect(await screen.findByText("Veri alınamadı: lock file is not writable")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Tekrar dene" })).toBeInTheDocument();
});

test("EN labels", async () => {
  vi.spyOn(api, "ingestStatus").mockResolvedValue(ingestSample("stale"));
  show(() => {}, "EN");
  expect(await screen.findByText("The data is 3 days old (10.10.2026).")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Refresh the data" })).toBeInTheDocument();
  expect(screen.getByText("takes about 15 minutes")).toBeInTheDocument();
});
