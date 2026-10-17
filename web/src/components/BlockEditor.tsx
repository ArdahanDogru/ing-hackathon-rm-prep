import { useState } from "react";
import { useT } from "../i18n";

/** One block of the meeting text as plain text, with "Kaydet" and "Vazgeç". Its own dark
 * text: a block on a dark section (05, white text) would else be white on the white editor. */
export function BlockEditor({
  label,
  initial,
  error,
  busy,
  onSave,
  onCancel,
}: {
  label: string;
  initial: string;
  error: string | null;
  busy: boolean;
  onSave: (text: string) => void;
  onCancel: () => void;
}) {
  const t = useT();
  const [text, setText] = useState(initial);
  return (
    <div className="my-2 rounded-xl border border-cobalt bg-[#F7F9FC] p-3 text-ink">
      <textarea
        aria-label={label}
        autoFocus
        rows={Math.min(12, Math.max(3, Math.ceil(text.length / 70) + text.split("\n").length))}
        className="w-full resize-y rounded-lg border border-gray-300 bg-white p-3 text-base leading-relaxed text-ink"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Escape" && onCancel()}
      />
      {error && (
        <p role="alert" className="mt-1 text-sm text-[#B42318]">
          {error}
        </p>
      )}
      <div className="mt-2 flex justify-end gap-2 text-sm">
        <button type="button" className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 font-semibold" onClick={onCancel}>
          {t("cancel")}
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded-lg bg-ink px-3 py-1.5 font-semibold text-white disabled:opacity-50"
          onClick={() => onSave(text)}
        >
          {t("save")}
        </button>
      </div>
    </div>
  );
}
