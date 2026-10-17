// "Yükle" next to the client dropdown (W31; docs/web-ui.md "Client upload"): a dialog with a
// .json file picker and the KVKK warning. The browser reads the file and posts its JSON; a parse
// error or the server's 422 text shows in the dialog.
import { useId, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Persona } from "../api/types";
import { useT } from "../i18n";
import { NoteDialog } from "./NoteDialog";

export function UploadButton({ onUploaded }: { onUploaded: (p: Persona) => void }) {
  const t = useT();
  const inputId = useId();
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    setOpen(false);
    setChosen(null);
    setError(null);
  };
  const send = async () => {
    if (!chosen) return;
    setBusy(true);
    setError(null);
    let persona: Persona;
    try {
      persona = JSON.parse(await chosen.text()) as Persona;
    } catch {
      setBusy(false);
      setError(t("uploadBadJson"));
      return;
    }
    try {
      const r = await api.uploadPersona(persona);
      close();
      onUploaded(r.persona);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button type="button" className="rounded-lg border border-gray-300 px-2.5 py-1 text-sm" onClick={() => setOpen(true)}>
        {t("uploadButton")}
      </button>
      {open && (
        <NoteDialog title={t("uploadTitle")} onClose={close}>
          <p className="rounded-lg border border-[#FEDF89] bg-[#FFFAEB] px-3 py-2 text-sm text-[#93370D]">{t("uploadWarning")}</p>
          <label htmlFor={inputId} className="mt-3 block text-xs text-muted">
            {t("uploadFile")}
          </label>
          <input
            id={inputId}
            type="file"
            accept=".json,application/json"
            className="mt-1 block w-full text-sm"
            onChange={(e) => {
              setChosen(e.target.files?.[0] ?? null);
              setError(null);
            }}
          />
          {error && (
            <p role="alert" className="mt-3 text-sm text-[#B42318]">
              {error}
            </p>
          )}
          <div className="mt-4 flex justify-end gap-2 text-sm">
            <button type="button" className="rounded-lg border border-gray-300 px-3 py-1.5 font-semibold" onClick={close}>
              {t("cancel")}
            </button>
            <button
              type="button"
              disabled={!chosen || busy}
              className="rounded-lg bg-ink px-3 py-1.5 font-semibold text-white disabled:opacity-50"
              onClick={send}
            >
              {t("uploadButton")}
            </button>
          </div>
        </NoteDialog>
      )}
    </>
  );
}
