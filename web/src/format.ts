// Numbers in Turkish format: "3,1", "−8,3", "%47,6".
const nf = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 1 });

const MINUS = "−";

/** One decimal at most, Turkish separators, a true minus sign. */
export function fmtNum(value: number): string {
  const text = nf.format(Math.abs(value));
  return value < 0 && text !== "0" ? MINUS + text : text;
}

/** "+3,1" for a positive value, "−3,1" for a negative one, "0" for zero. */
export function fmtSigned(value: number): string {
  const text = fmtNum(value);
  return value > 0 && text !== "0" ? "+" + text : text;
}

/** Turkish percent: "%47,6", "−%8,3". */
export function fmtPct(value: number): string {
  const text = nf.format(Math.abs(value));
  return value < 0 && text !== "0" ? `${MINUS}%${text}` : `%${text}`;
}

const dtf = new Intl.DateTimeFormat("tr-TR", {
  timeZone: "Europe/Istanbul",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** A plain date "2026-10-09" → "09.10.2026". */
export function fmtDate(isoDate: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : isoDate;
}

/** An ISO time with an offset → "12.10.2026 20:47" in Turkey time; other text unchanged. */
export function fmtDateTime(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const p = Object.fromEntries(dtf.formatToParts(new Date(t)).map((x) => [x.type, x.value]));
  return `${p.day}.${p.month}.${p.year} ${p.hour}:${p.minute}`;
}

/** An ISO time → its day "14.10.2026" in Turkey time; other text unchanged. */
export function fmtDay(iso: string): string {
  const text = fmtDateTime(iso);
  return text === iso ? iso : text.split(" ")[0];
}

/** An ISO time → "07:30" in Turkey time; other text unchanged. */
export function fmtTime(iso: string): string {
  const text = fmtDateTime(iso);
  return text === iso ? iso : text.split(" ")[1];
}

/** A snapshot id "20261010-183835-6813" (Turkey time) → "10.10.2026 18:38 · 6813"; other ids unchanged. */
export function snapshotLabel(id: string): string {
  const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})\d{2}-(\w+)$/.exec(id);
  return m ? `${m[3]}.${m[2]}.${m[1]} ${m[4]}:${m[5]} · ${m[6]}` : id;
}

/**
 * A score or a score part ×100 without decimals (W21; before: "0,85", W16): "85", "+24", "−10", "0".
 * Half away from zero; the small epsilon keeps 0.245 × 100 = 24.4999… at 25. Display only.
 */
export function fmtScore(value: number, signed = true): string {
  const n = Math.round(Math.abs(value) * 100 + 1e-9);
  if (n === 0) return "0";
  return value < 0 ? `${MINUS}${n}` : signed ? `+${n}` : String(n);
}
