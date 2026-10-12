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
