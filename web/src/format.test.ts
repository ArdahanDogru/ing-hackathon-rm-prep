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
