// W26: the "Belgeler" block in the fund drawer (links to the manager's own site).
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "../api/client";
import type { FundDocuments as Docs, Lang } from "../api/types";
import { renderDashboard, renderWith } from "../test/render";
import { asKind, sample } from "../test/samples";
import { FundDocuments } from "./FundDocuments";

afterEach(() => vi.restoreAllMocks());

const v = sample("run_p01_ready");
const PPN = v.options["fund:PPN"];
const answer = (over: Partial<Docs> = {}): Docs => ({
  status: "ok",
  manager_label: "Nurol Portföy",
  verdict: "",
  docs: [
    { kind: "izahname", label: "İzahname", url: "https://www.nurolportfoy.com.tr/izahname-ppn.pdf", date: "2025-02-04" },
    { kind: "ybf", label: "Yatırımcı bilgi formu", url: "https://www.nurolportfoy.com.tr/ybf-ppn.pdf", date: "2026-03-13" },
  ],
  page_url: "https://www.nurolportfoy.com.tr/fonlar/ppn",
  checked_at: "2026-10-16T09:12:00+03:00",
  reason: "",
  ...over,
});
const show = (lang: Lang = "TR", option = PPN) => renderWith(<FundDocuments runId={v.result.run_id} option={option} />, { lang });

test("loading, then two links that open in a new tab with the external mark, and the source line", async () => {
  let done: (d: Docs) => void = () => {};
  const get = vi.spyOn(api, "documents").mockReturnValue(new Promise((ok) => (done = ok)));
  show();
  const block = screen.getByTestId("fund-documents");
  expect(block).toHaveTextContent("Belgeler");
  expect(block).toHaveTextContent("Belgeler aranıyor…");
  expect(get).toHaveBeenCalledWith(v.result.run_id, "fund:PPN");
  done(answer());
  const izah = await within(block).findByRole("link", { name: /İzahname · 04\.02\.2025/ });
  expect(izah).toHaveAttribute("href", "https://www.nurolportfoy.com.tr/izahname-ppn.pdf");
  expect(izah).toHaveAttribute("target", "_blank");
  expect(izah).toHaveAttribute("rel", "noopener noreferrer");
  expect(within(izah).getByTestId("external-mark")).toBeInTheDocument();
  expect(within(block).getByRole("link", { name: /Yatırımcı bilgi formu · 13\.03\.2026/ })).toHaveAttribute("target", "_blank");
  expect(block).toHaveTextContent("Kaynak: nurolportfoy.com.tr, kontrol 16.10.2026");
});

test("a document without a date has no date part; one kind missing gives only the other link", async () => {
  vi.spyOn(api, "documents").mockResolvedValue(answer({ docs: [{ kind: "ybf", label: "YBF", url: "https://www.nurolportfoy.com.tr/ybf.pdf", date: null }] }));
  show();
  const link = await screen.findByRole("link", { name: /Yatırımcı bilgi formu/ });
  expect(link.textContent?.replace("↗", "").trim()).toBe("Yatırımcı bilgi formu");
  expect(screen.queryByRole("link", { name: /İzahname/ })).toBeNull();
});

test("not_found: the text and a link to the fund page", async () => {
  vi.spyOn(api, "documents").mockResolvedValue(answer({ status: "not_found", docs: [] }));
  show();
  expect(await screen.findByText("Kurucunun sayfasında belge bağlantısı bulunamadı.")).toBeInTheDocument();
  const page = screen.getByRole("link", { name: /nurolportfoy\.com\.tr/ });
  expect(page).toHaveAttribute("href", "https://www.nurolportfoy.com.tr/fonlar/ppn");
  expect(page).toHaveAttribute("rel", "noopener noreferrer");
});

test("not_found without a page_url: only the text", async () => {
  vi.spyOn(api, "documents").mockResolvedValue(answer({ status: "not_found", docs: [], page_url: "" }));
  show();
  await screen.findByText("Kurucunun sayfasında belge bağlantısı bulunamadı.");
  expect(within(screen.getByTestId("fund-documents")).queryByRole("link")).toBeNull();
});

test("not_covered: the reason text, no link", async () => {
  const reason = "İş Portföy: robots.txt belge yolunu engelliyor; belgeler KAP'ta.";
  vi.spyOn(api, "documents").mockResolvedValue(answer({ status: "not_covered", docs: [], page_url: "", manager_label: "İş Portföy", reason }));
  show();
  expect(await screen.findByText(reason)).toBeInTheDocument();
  expect(within(screen.getByTestId("fund-documents")).queryByRole("link")).toBeNull();
});

test("failed (or a request error): the text and Tekrar dene asks again", async () => {
  const get = vi
    .spyOn(api, "documents")
    .mockResolvedValueOnce(answer({ status: "failed", docs: [], reason: "timeout" }))
    .mockRejectedValueOnce(new Error("network"))
    .mockResolvedValue(answer());
  show();
  expect(await screen.findByText("Belgeler şu an alınamadı.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Tekrar dene" }));
  expect(await screen.findByText("Belgeler şu an alınamadı.")).toBeInTheDocument(); // the error answer
  await userEvent.click(screen.getByRole("button", { name: "Tekrar dene" }));
  expect(await screen.findByRole("link", { name: /İzahname/ })).toBeInTheDocument();
  expect(get).toHaveBeenCalledTimes(3);
});

test("only for a fund or an ETF: a time deposit or a share asks nothing", () => {
  const get = vi.spyOn(api, "documents").mockResolvedValue(answer());
  const { unmount } = show("TR", v.options["time_deposit:ing_e_vadeli"]);
  expect(screen.queryByTestId("fund-documents")).toBeNull();
  unmount();
  show("TR", asKind(PPN, "stock"));
  expect(screen.queryByTestId("fund-documents")).toBeNull();
  expect(get).not.toHaveBeenCalled();
});

test("an ETF has the block", async () => {
  const get = vi.spyOn(api, "documents").mockResolvedValue(answer());
  show("TR", asKind(PPN, "etf"));
  expect(await screen.findByTestId("fund-documents")).toBeInTheDocument();
  expect(get).toHaveBeenCalledWith(v.result.run_id, "etf:PPN");
});

test("W26 EN", async () => {
  vi.spyOn(api, "documents").mockResolvedValue(answer());
  show("EN");
  const block = screen.getByTestId("fund-documents");
  expect(block).toHaveTextContent("Documents");
  expect(await within(block).findByRole("link", { name: /Prospectus · 04\.02\.2025/ })).toBeInTheDocument();
  expect(within(block).getByRole("link", { name: /Key investor information · 13\.03\.2026/ })).toBeInTheDocument();
  expect(block).toHaveTextContent("Source: nurolportfoy.com.tr, checked 16.10.2026");
});

test("the drawer loads the documents when it opens; the card list does not", async () => {
  const get = vi.spyOn(api, "documents").mockResolvedValue(answer());
  renderDashboard(v);
  expect(get).not.toHaveBeenCalled();
  expect(screen.queryByTestId("fund-documents")).toBeNull();
  await userEvent.click(screen.getAllByTestId("option-card")[0]);
  const drawer = screen.getByRole("dialog");
  expect(await within(drawer).findByTestId("fund-documents")).toBeInTheDocument();
  await waitFor(() => expect(get).toHaveBeenCalledWith(v.result.run_id, v.top[0]));
});
