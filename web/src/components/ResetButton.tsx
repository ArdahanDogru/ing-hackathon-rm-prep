// "Sıfırla" in the top bar (W27; docs/web-ui.md "Reset: every client back to the first state"):
// a confirmation dialog, then POST /api/reset. A 409 (the agent runs) shows the server text in
// the dialog and changes nothing; another error goes to the app's error box.
import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { ResetResult } from "../api/types";
import { useT } from "../i18n";
import { NoteDialog } from "./NoteDialog";

export function ResetButton({ onDone, onError }: { onDone: (r: ResetResult) => void; onError: (e: Error) => void }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const close = () => {
    setOpen(false);
    setRefused(null);
  };
  const confirm = () => {
    setBusy(true);
    setRefused(null);
    api.reset().then(
      (r) => {
        setBusy(false);
        close();
        onDone(r);
      },
      (e: Error) => {
        setBusy(false);
        if (e instanceof ApiError && e.status === 409) setRefused(e.detail);
        else {
          close();
          onError(e);
        }
      },
    );
  };

  return (
    <>
      <button type="button" className="rounded-lg border border-gray-300 px-3 py-1 text-sm" onClick={() => setOpen(true)}>
        {t("resetButton")}
      </button>
      {open && (
        <NoteDialog title={t("resetTitle")} onClose={close}>
          <p className="text-sm leading-relaxed text-[#344054]">{t("resetText")}</p>
          {refused && (
            <p role="alert" className="mt-3 rounded-lg border border-[#FEDF89] bg-[#FFFAEB] px-3 py-2 text-sm text-[#93370D]">
              {refused}
            </p>
          )}
          <div className="mt-4 flex justify-end gap-2 text-sm">
            <button type="button" className="rounded-lg border border-gray-300 px-3 py-1.5 font-semibold" onClick={close}>
              {t("cancel")}
            </button>
            <button
              type="button"
              disabled={busy}
              className="rounded-lg bg-[#B42318] px-3 py-1.5 font-semibold text-white disabled:opacity-50"
              onClick={confirm}
            >
              {t("resetButton")}
            </button>
          </div>
        </NoteDialog>
      )}
    </>
  );
}
