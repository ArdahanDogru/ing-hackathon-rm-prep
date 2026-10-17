// W30: the changes of an edited profile in one line, with the field labels of the profile panel:
// "yaş: 62 → 45; öncelikler: düzenli gelir, likidite → büyüme".
import type { Lang } from "./api/types";
import { labels, type LabelKey } from "./i18n";

type Change = { field: string; original: unknown; edited: unknown };

const show = (v: unknown) => (Array.isArray(v) ? v.join(", ") : String(v));

export function profileChanges(changes: Change[], lang: Lang): string {
  const label = (f: string) => labels[lang][`f_${f}` as LabelKey] ?? f;
  return changes.map((c) => `${label(c.field)}: ${show(c.original)} → ${show(c.edited)}`).join("; ");
}
