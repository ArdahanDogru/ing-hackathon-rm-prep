import type { DataNote, Warning } from "../api/types";
import { useT } from "../i18n";

/** The data notes about one option, on its card. */
export function OptionNotes({ notes }: { notes: DataNote[] }) {
  if (!notes.length) return null;
  return (
    <ul className="mt-2 space-y-1 text-[11px] leading-snug text-muted">
      {notes.map((n) => (
        <li key={n.message}>{n.message}</li>
      ))}
    </ul>
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
