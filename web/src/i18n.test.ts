import { labels } from "./i18n";

test("every key in TR and EN", () => {
  expect(Object.keys(labels.TR).sort()).toEqual(Object.keys(labels.EN).sort());
});

test("no empty label", () => {
  for (const lang of ["TR", "EN"] as const) {
    for (const [k, v] of Object.entries(labels[lang])) expect(v.trim(), `${lang}.${k}`).not.toBe("");
  }
});

test("fill puts the values into the placeholders", async () => {
  const { fill } = await import("./i18n");
  expect(fill("Veri {n} gün önce alındı ({date}).", { n: 3, date: "10.10.2026" })).toBe("Veri 3 gün önce alındı (10.10.2026).");
  expect(fill("{x} {x}", { x: "a" })).toBe("a a");
});
