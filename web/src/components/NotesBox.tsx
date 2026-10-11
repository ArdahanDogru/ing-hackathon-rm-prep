import { useT } from "../i18n";

export type SaveState = "idle" | "saving" | "saved" | { error: string };

export function SaveStatus({ state }: { state: SaveState }) {
  const t = useT();
  if (state === "idle") return null;
  if (state === "saving") return <div className="mt-1.5 text-xs text-muted">{t("saving")}</div>;
  if (state === "saved") return <div className="mt-1.5 text-xs text-[#067647]">{`✓ ${t("saved")}`}</div>;
  return (
    <div role="alert" className="mt-1.5 text-xs text-[#B42318]">
      {state.error}
    </div>
  );
}

/** "Notlarım": the RM's general note, saved automatically. */
export function NotesBox({ value, onChange, state }: { value: string; onChange: (v: string) => void; state: SaveState }) {
  const t = useT();
  return (
    <label className="flex flex-col rounded-2xl bg-white px-5 py-4 text-ink">
      <span className="text-[13px] font-bold uppercase tracking-[0.06em] text-[#355FA1]">{t("myNotes")}</span>
      <textarea
        aria-label={t("myNotes")}
        className="mt-2 min-h-[150px] flex-1 resize-y rounded-xl border border-gray-300 bg-[#FBFCFE] p-3 text-[15px] leading-normal"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <SaveStatus state={state} />
    </label>
  );
}
