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
