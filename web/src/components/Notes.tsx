import { useState } from "react";
import type { DataNote, Warning } from "../api/types";
import { useT } from "../i18n";

/** The data notes about one option, on its card: one closed line, opens on click. */
export function OptionNotes({ notes }: { notes: DataNote[] }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  if (!notes.length) return null;
  return (
    <div className="mt-2 text-[11px] leading-snug text-muted">
      <button type="button" aria-expanded={open} className="underline" onClick={() => setOpen(!open)}>
        {`${t("dataNotes")} · ${notes.length}`}
      </button>
      {open && (
        <ul className="mt-1 space-y-1">
          {notes.map((n) => (
            <li key={n.message}>{n.message}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Warnings as plain lines; RM-only ones are marked (never client-facing). */
export function WarningList({ warnings }: { warnings: Warning[] }) {
  const t = useT();
  return (
    <ul className="space-y-2 text-[13px] leading-snug text-[#475467]">
      {warnings.map((w) => (
        <li key={w.code + w.message} data-audience={w.audience}>
          {w.audience === "rm" && <span className="mr-1 font-semibold text-[#B54708]">{`${t("rmOnly")}:`}</span>}
          <span>{w.message}</span>
        </li>
      ))}
    </ul>
  );
}
