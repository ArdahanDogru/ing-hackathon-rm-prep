// "Öneriler · mevduatla karşılaştırma" with the view switch Tablo | Kartlar | Dağılım (remembered).
import { useState } from "react";
import type { RunView } from "../api/types";
import { useT } from "../i18n";
import { OptionsAllocation } from "./OptionsAllocation";
import { OptionsCards } from "./OptionsCards";
import { OptionsTable } from "./OptionsTable";

const VIEW_KEY = "rmprep.view.oneriler";
type View = "table" | "cards" | "allocation";

function savedView(): View {
  try {
    const v = localStorage.getItem(VIEW_KEY);
    return v === "cards" || v === "allocation" ? v : "table";
  } catch {
    return "table";
  }
}

export function OptionsCompare({
  view,
  onOpen,
  onEvidence,
}: {
  view: RunView;
  onOpen: (id: string) => void;
  onEvidence: (id: string) => void;
}) {
  const t = useT();
  const [saved, setMode] = useState<View>(savedView);
  const hasAllocation = view.allocation.length > 0;
  const mode: View = saved === "allocation" && !hasAllocation ? "table" : saved; // no bands: the table
  const choose = (m: View) => {
    setMode(m);
    try {
      localStorage.setItem(VIEW_KEY, m);
    } catch {
      // storage blocked: the choice holds for this page only
    }
  };
  const options = view.top.map((id) => view.options[id]).filter(Boolean);
  const props = { options, baseline: view.baseline, onOpen, onEvidence };

  return (
    <section data-testid="options-compare" className="min-w-0 rounded-2xl bg-white px-1.5 pb-3 pt-2 shadow-sm">
      <div className="flex items-center justify-between px-4 pb-1 pt-3">
        <h2 className="text-xs font-bold uppercase tracking-[0.06em] text-muted">{t("optionsCompare")}</h2>
        <div role="group" className="inline-flex overflow-hidden rounded-[10px] border border-catgrey text-[13px]">
          {(hasAllocation ? (["table", "cards", "allocation"] as const) : (["table", "cards"] as const)).map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={mode === m}
              className={mode === m ? "bg-ink px-3 py-[5px] text-white" : "px-3 py-[5px]"}
              onClick={() => choose(m)}
            >
              {m === "table" ? t("viewTable") : m === "cards" ? t("viewCards") : t("viewAllocation")}
            </button>
          ))}
        </div>
      </div>
      {mode === "table" ? (
        <OptionsTable {...props} />
      ) : mode === "cards" ? (
        <OptionsCards {...props} />
      ) : (
        <OptionsAllocation view={view} onOpen={onOpen} />
      )}
    </section>
  );
}
