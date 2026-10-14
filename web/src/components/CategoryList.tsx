import { useState } from "react";
import type { Category, OptionView } from "../api/types";
import { fmtPct } from "../format";
import { useT } from "../i18n";
import { RiskBar } from "./RiskBar";
import { Stars } from "./Stars";

function FundRow({
  option,
  selected,
  onToggle,
  onOpen,
}: {
  option: OptionView;
  selected: boolean;
  onToggle: () => void;
  onOpen: () => void;
}) {
  const t = useT();
  const r1 = option.returns["1y"];
  return (
    <li data-testid="fund-row" className="border-t border-gray-100">
      <div className="grid grid-cols-[1fr_auto_auto_auto_auto] items-center gap-4 py-2.5">
        <div className="min-w-0">
          <div className="truncate text-[13px] font-medium">{option.label}</div>
          <div className="text-[11px] text-muted">
            {option.rank ? `${option.rank.position}. / ${option.rank.of} ${t("categoryRank")}` : t("noRank")}
            {option.access.label && ` · ${t("access")}: ${option.access.label}`}
          </div>
        </div>
        <div className="w-24 text-xs">{option.risk && <RiskBar level={option.risk.level} />}</div>
        <div className="w-28 text-right">
          <div className="text-sm font-semibold">{r1 ? fmtPct(r1.value) : "—"}</div>
          {option.stars !== null && <Stars count={option.stars} />}
        </div>
        <button
          type="button"
          aria-pressed={selected}
          onClick={onToggle}
          className="w-28 rounded-[10px] border border-gray-300 px-2 py-1 text-xs font-semibold"
        >
          {selected ? `✓ ${t("inSelection")}` : t("addToSelection")}
        </button>
        <button type="button" className="text-xs text-[#355FA1] underline" onClick={onOpen}>
          {t("details")}
        </button>
      </div>
    </li>
  );
}

/** Categories, closed; one opens at most 3 options (the API sends at most 3 ids, the head first). In "Detaylar". */
export function CategoryList({
  categories,
  options,
  selected,
  onToggle,
  onOpen,
}: {
  categories: Category[];
  options: Record<string, OptionView>;
  selected: string[];
  onToggle: (id: string) => void;
  onOpen: (id: string) => void;
}) {
  const t = useT();
  const [open, setOpen] = useState<Record<string, boolean>>({});
  if (!categories.length) return null;
  return (
    <section>
      <div className="space-y-2">
        {categories.map((c) => {
          const isOpen = !!open[c.key];
          const ids = c.option_ids.slice(0, 3).filter((id) => options[id]);
          const allFunds = ids.every((id) => options[id].kind === "fund" || options[id].kind === "etf");
          return (
            <div key={c.key} data-testid="category" className="rounded-xl border border-gray-100 px-4">
              <button
                type="button"
                aria-expanded={isOpen}
                className="flex w-full items-center justify-between py-3 text-left text-sm"
                onClick={() => setOpen((o) => ({ ...o, [c.key]: !isOpen }))}
              >
                <b>{c.label}</b>
                <span className="text-muted">
                  {`${c.count} ${allFunds ? t("funds") : t("optionsWord")}`}
                  {c.best_return_1y !== null && ` · ${t("best")} ${fmtPct(c.best_return_1y)}`}
                  <span className="ml-2 inline-block transition-transform" style={{ transform: isOpen ? "rotate(90deg)" : "" }}>
                    ›
                  </span>
                </span>
              </button>
              {isOpen && (
                <ul className="pb-2">
                  {ids.map((id) => (
                    <FundRow
                      key={id}
                      option={options[id]}
                      selected={selected.includes(id)}
                      onToggle={() => onToggle(id)}
                      onOpen={() => onOpen(id)}
                    />
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
