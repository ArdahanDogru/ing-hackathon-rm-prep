import type { ReactNode } from "react";

/** One section of the meeting text document: a small capital heading (with an optional action) and its body. */
export function DocumentSection({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="mb-6">
      <div className="flex items-baseline gap-3">
        <h2 data-testid="doc-heading" className="text-xs font-bold uppercase tracking-[0.06em] text-muted">
          {title}
        </h2>
        {action}
      </div>
      <div className="mt-1.5">{children}</div>
    </section>
  );
}

/** The small source number after a sentence; a click (or Enter/Space) opens its evidence. */
export function SourceMark({ n, label, onOpen }: { n: number | undefined; label: string; onOpen: () => void }) {
  if (n === undefined) return null;
  return (
    <button
      type="button"
      data-testid="src-mark"
      aria-label={`${label} ${n}`}
      className="ml-1 inline-block rounded-md bg-[#EEF2F9] px-[7px] py-px align-[2px] text-[11px] font-bold leading-normal text-cobalt hover:bg-[#DCE4F2]"
      onClick={onOpen}
    >
      {n}
    </button>
  );
}
