import { useT } from "../i18n";

export interface Source {
  n: number;
  label: string;
  evidenceIds: string[];
}

/** "Kaynaklar": the numbered sources of the document; each id opens its evidence. */
export function SourceList({ sources, onEvidence }: { sources: Source[]; onEvidence: (id: string) => void }) {
  const t = useT();
  if (!sources.length) return null;
  return (
    <section className="mb-4 rounded-2xl bg-white px-5 py-[18px] shadow-sm">
      <h3 className="font-bold">{t("sources")}</h3>
      <ol className="mt-2 space-y-2 text-sm leading-normal text-[#344054]">
        {sources.map((s) => (
          <li key={s.n} id={`src-${s.n}`} data-testid="source-item" className="scroll-mt-24">
            <span>{`${s.n} · ${s.label}`}</span>
            <span className="mt-0.5 flex flex-wrap gap-1">
              {s.evidenceIds.map((id) => (
                <button
                  key={id}
                  type="button"
                  className="rounded-full border border-gray-300 px-1.5 py-px font-mono text-[11px] text-muted hover:border-cobalt"
                  onClick={() => onEvidence(id)}
                >
                  {id}
                </button>
              ))}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
