import { fmtNum, fmtPct, fmtSigned } from "./format";

test("Turkish separators and a true minus sign", () => {
  expect(fmtNum(1234.56)).toBe("1.234,6");
  expect(fmtNum(-8.25)).toBe("−8,3");
  expect(fmtNum(-0.01)).toBe("0");
  expect(fmtSigned(3.1000000000000014)).toBe("+3,1");
  expect(fmtSigned(0)).toBe("0");
  expect(fmtPct(47.6)).toBe("%47,6");
  expect(fmtPct(-8.3)).toBe("−%8,3");
});

test("Turkish dates and times in Europe/Istanbul", async () => {
  const { fmtDate, fmtDateTime } = await import("./format");
  expect(fmtDate("2026-10-09")).toBe("09.10.2026");
  expect(fmtDateTime("2026-10-12T20:47:15.985540+03:00")).toBe("12.10.2026 20:47");
  expect(fmtDateTime("2026-10-12T17:47:15Z")).toBe("12.10.2026 20:47");
  expect(fmtDateTime("not a time")).toBe("not a time");
});

test("day and time of an ISO time in Turkey time", async () => {
  const { fmtDay, fmtTime } = await import("./format");
  expect(fmtDay("2026-10-13T22:30:00Z")).toBe("14.10.2026");
  expect(fmtTime("2026-10-14T04:30:04Z")).toBe("07:30");
  expect(fmtDay("not a time")).toBe("not a time");
});

test("a snapshot id shows its date and time", async () => {
  const { snapshotLabel } = await import("./format");
  expect(snapshotLabel("20261010-183835-6813")).toBe("10.10.2026 18:38 · 6813");
  expect(snapshotLabel("odd-id")).toBe("odd-id");
});
