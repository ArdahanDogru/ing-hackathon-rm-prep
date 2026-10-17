// W44: a profile conflict must be resolved before the approval (docs/web-ui.md). Each conflict
// in the profile block gets "Profili düzelt" (the edit panel) and "Müşteriyle teyit edildi" (a
// required reason). The reasons go with the approval; after it, the recorded reasons show.
import { useState } from "react";
import type { ResolutionRecord } from "../api/types";
import { fill, useT } from "../i18n";

export interface ResolveProps {
  /** the RM's reasons by finding id (not yet sent) */
  notes: Record<string, string>;
  onNote: (id: string, note: string) => void;
  /** opens "Profili düzenle"; no button without it */
  onFix?: () => void;
  /** the run is decided: only the recorded reasons, no actions */
  decided: boolean;
  recorded?: ResolutionRecord | null;
}

function Resolved({ note, onChange }: { note: string; onChange?: () => void }) {
  const t = useT();
  return (
    <span data-testid="resolved" className="mt-1 flex flex-wrap items-center gap-2 text-xs font-normal text-[#344054]">
      <span className="rounded bg-[#ECFDF3] px-1.5 font-semibold text-[#067647]">{`✓ ${t("resolvedChip")}`}</span>
      <span>{fill(t("resolvedNote"), { note })}</span>
      {onChange && (
        <button type="button" className="underline" onClick={onChange}>
          {t("resolveChange")}
        </button>
      )}
    </span>
  );
}

/** The actions of one conflict, its reason field, or its reason. */
export function Resolve({ id, resolve }: { id: string; resolve?: ResolveProps }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  if (!resolve) return null;
  if (resolve.decided) {
    const r = resolve.recorded?.resolutions.find((x) => x.id === id);
    return r ? <Resolved note={r.note} /> : null;
  }
  const note = resolve.notes[id]?.trim() ?? "";
  if (open) {
    return (
      <form
        className="mt-1.5 flex flex-wrap items-center gap-2 text-xs font-normal"
        onSubmit={(e) => {
          e.preventDefault();
          if (!draft.trim()) return;
          resolve.onNote(id, draft.trim());
          setOpen(false);
        }}
      >
        <input
          aria-label={t("resolveReason")}
          placeholder={t("resolvePlaceholder")}
          value={draft}
          autoFocus
          onChange={(e) => setDraft(e.target.value)}
          className="w-[min(100%,360px)] rounded-lg border border-[#F79009] bg-white px-2 py-1 text-[13px] text-[#101828]"
        />
        <button
          type="submit"
          disabled={!draft.trim()}
          className="rounded-lg bg-ink px-2.5 py-1 font-semibold text-white disabled:opacity-40"
        >
          {t("save")}
        </button>
      </form>
    );
  }
  if (note) {
    return (
      <Resolved
        note={note}
        onChange={() => {
          setDraft(note);
          setOpen(true);
        }}
      />
    );
  }
  const action = "rounded-lg border border-[#F79009] bg-white px-2 py-0.5 font-semibold text-[#93370D] hover:bg-[#FEF0C7]";
  return (
    <span className="mt-1.5 flex flex-wrap gap-2 text-xs font-normal">
      {resolve.onFix && (
        <button type="button" className={action} onClick={resolve.onFix}>
          {t("fixProfile")}
        </button>
      )}
      <button
        type="button"
        className={action}
        onClick={() => {
          setDraft("");
          setOpen(true);
        }}
      >
        {t("confirmedWithClient")}
      </button>
    </span>
  );
}
