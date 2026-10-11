import { useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { EvidenceItem } from "../api/types";
import { fmtNum } from "../format";
import { useT } from "../i18n";

/** "Kanıt" pop-up: value, source, date, evidence id, flags of one DataPoint. */
export function EvidencePopup({
  snapshotId,
  evidenceId,
  open,
  onClose,
}: {
  snapshotId: string;
  evidenceId: string;
  open: boolean;
  onClose: () => void;
}) {
  const t = useT();
  const [item, setItem] = useState<EvidenceItem | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let live = true;
    setItem(null);
    setError(null);
    api.evidence(snapshotId, evidenceId).then(
      (x) => live && setItem(x),
      (e: Error) => live && setError(e.message),
    );
    return () => {
      live = false;
    };
  }, [open, snapshotId, evidenceId]);

  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [open, onClose]);

  if (!open) return null;
  const row = (label: string, value: ReactNode) => (
    <>
      <dt className="text-muted">{label}</dt>
      <dd className="break-all">{value}</dd>
    </>
  );
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("evidenceTitle")}
        className="w-full max-w-md rounded-2xl bg-white p-5 text-sm shadow-xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">{t("evidenceTitle")}</h2>
          <button type="button" autoFocus className="text-sm underline" onClick={onClose}>
            {t("close")}
          </button>
        </div>
        {error && (
          <p role="alert" className="text-red-700">
            {error}
          </p>
        )}
        {!item && !error && <p className="text-muted">{t("loading")}</p>}
        {item && (
          <>
            {item.entity_name && <p className="mb-2 font-medium">{item.entity_name}</p>}
            <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-1.5">
              {row(t("value"), item.value === null ? "—" : `${fmtNum(item.value)} ${item.unit}`)}
              {row(t("source"), <span>{item.source}</span>)}
              {row(t("asOf"), <span>{item.as_of}</span>)}
              {row(t("evidenceId"), <code>{item.id}</code>)}
              {row(t("flags"), item.flags.length ? item.flags.join(", ") : t("noFlags"))}
            </dl>
            {item.note && <p className="mt-2 text-xs text-muted">{item.note}</p>}
            {item.source_url && (
              <a className="mt-3 inline-block text-xs text-[#355FA1] underline" href={item.source_url} target="_blank" rel="noreferrer">
                {t("openSource")}
              </a>
            )}
          </>
        )}
      </div>
    </div>
  );
}
