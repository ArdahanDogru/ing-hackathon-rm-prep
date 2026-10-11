import { labels } from "./i18n";

test("every key in TR and EN", () => {
  expect(Object.keys(labels.TR).sort()).toEqual(Object.keys(labels.EN).sort());
});

test("no empty label", () => {
  for (const lang of ["TR", "EN"] as const) {
    for (const [k, v] of Object.entries(labels[lang])) expect(v.trim(), `${lang}.${k}`).not.toBe("");
  }
});
