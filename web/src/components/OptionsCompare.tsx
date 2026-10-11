// "Öneriler · mevduatla karşılaştırma" with the view switch Tablo | Kartlar (remembered).
import { useState } from "react";
import type { RunView } from "../api/types";
import { useT } from "../i18n";
import { OptionsCards } from "./OptionsCards";
import { OptionsTable } from "./OptionsTable";

const VIEW_KEY = "rmprep.view.oneriler";
type View = "table" | "cards";

function savedView(): View {
  try {
    return localStorage.getItem(VIEW_KEY) === "cards" ? "cards" : "table";
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
  const [mode, setMode] = useState<View>(savedView);
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
          {(["table", "cards"] as const).map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={mode === m}
              className={mode === m ? "bg-ink px-3 py-[5px] text-white" : "px-3 py-[5px]"}
              onClick={() => choose(m)}
            >
              {m === "table" ? t("viewTable") : t("viewCards")}
            </button>
          ))}
        </div>
      </div>
      {mode === "table" ? <OptionsTable {...props} /> : <OptionsCards {...props} />}
    </section>
  );
}
