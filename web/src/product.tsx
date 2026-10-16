// Product codes (W28; docs/web-ui.md "Product codes everywhere a product is a title"): the TEFAS
// code or the BIST ticker of a fund, an ETF or a share is the part of the option id after ":".
// The two ING deposits have no code. The code is never translated.

const CODED = new Set(["fund", "etf", "stock"]);

/** "fund:PPN" → "PPN"; "" for a deposit or a time deposit. */
export function productCode(optionId: string): string {
  const i = optionId.indexOf(":");
  return i > 0 && CODED.has(optionId.slice(0, i)) ? optionId.slice(i + 1) : "";
}

/** For running text, chips and short lists: "PPN · Nurol · Para Piyasası (TL)". */
export function withCode(optionId: string, name: string): string {
  const code = productCode(optionId);
  return code ? `${code} · ${name}` : name;
}

/** In a title or a heading: a small code badge before the name; nothing without a code. */
export function CodeBadge({ optionId, className = "" }: { optionId: string; className?: string }) {
  const code = productCode(optionId);
  if (!code) return null;
  return (
    <span
      data-testid="code-badge"
      className={`mr-1.5 inline-block rounded border border-gray-300 bg-white px-1 py-px align-[1px] font-mono text-[11px] font-bold leading-tight tracking-normal text-[#475467] normal-case ${className}`}
    >
      {code}
    </span>
  );
}
