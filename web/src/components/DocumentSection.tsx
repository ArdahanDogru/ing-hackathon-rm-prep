import type { ReactNode } from "react";

/** One section of the meeting text document: a small capital heading and its body. */
export function DocumentSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-6">
      <h2 data-testid="doc-heading" className="text-xs font-bold uppercase tracking-[0.06em] text-muted">
        {title}
      </h2>
      <div className="mt-1.5">{children}</div>
    </section>
  );
}

/** The small source number after a sentence; it links to its item in "Kaynaklar". */
export function SourceMark({ n }: { n: number | undefined }) {
  if (n === undefined) return null;
  return (
    <a
      data-testid="src-mark"
      href={`#src-${n}`}
      className="ml-1 inline-block rounded-md bg-[#EEF2F9] px-[7px] py-px align-[2px] text-[11px] font-bold leading-normal text-cobalt no-underline"
    >
      {n}
    </a>
  );
}
