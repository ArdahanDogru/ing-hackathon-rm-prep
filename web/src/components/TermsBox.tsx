import type { GlossaryTerm } from "../api/types";
import { useT } from "../i18n";

/** "Terimler": the glossary terms that appear in the text. */
export function TermsBox({ terms }: { terms: GlossaryTerm[] }) {
  const t = useT();
  if (!terms.length) return null;
  return (
    <section className="mb-4 rounded-[18px] bg-white px-5 py-5 shadow-sm">
      <h3 className="mb-2 text-[17px] font-semibold">{t("terms")}</h3>
      <dl>
        {terms.map((term) => (
          <div key={term.term} className="border-t border-gray-100 py-3">
            <dt className="text-base font-semibold">{term.form}</dt>
            <dd className="mt-0.5 text-[15px] leading-normal text-[#475467]">{term.explanation}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
