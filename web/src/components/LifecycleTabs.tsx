import { useNavigate } from "react-router-dom";
import { useT } from "../i18n";

/** The meeting lifecycle as navigation: 1 · Hazırlık | 2 · Görüşme metni (after approval). */
export function LifecycleTabs({ runId, approved, active }: { runId: string; approved: boolean; active: "prep" | "text" }) {
  const t = useT();
  const navigate = useNavigate();
  const tab = (key: "prep" | "text", label: string, enabled: boolean, to: string) => {
    const on = active === key;
    return (
      <button
        type="button"
        role="tab"
        aria-selected={on}
        aria-disabled={!enabled || undefined}
        className={
          on
            ? "-mb-px border-b-[3px] border-brand px-[18px] py-2.5 font-semibold text-ink"
            : enabled
              ? "-mb-px border-b-[3px] border-transparent px-[18px] py-2.5 font-semibold text-muted hover:text-ink"
              : "-mb-px cursor-not-allowed border-b-[3px] border-transparent px-[18px] py-2.5 font-semibold text-gray-300"
        }
        onClick={() => enabled && !on && navigate(to)}
      >
        {label}
      </button>
    );
  };
  return (
    <div role="tablist" className="mb-6 flex border-b border-gray-200">
      {tab("prep", t("lcPrep"), true, "/")}
      {tab("text", t("lcText"), approved, `/meeting/${encodeURIComponent(runId)}`)}
    </div>
  );
}
