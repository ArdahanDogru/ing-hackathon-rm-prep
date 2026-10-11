import { ApiError } from "../api/client";
import { useT } from "../i18n";

/** An API error: its detail text and "Tekrar dene". */
export function ErrorBox({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const t = useT();
  const code = error instanceof ApiError ? ` (${error.status})` : "";
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-red-200 bg-white px-4 py-3 text-sm">
      <span>
        <b>{`${t("errorTitle")}${code}:`}</b> {error.message}
      </span>
      <button type="button" className="ml-auto rounded-[10px] border border-gray-300 px-3 py-1 font-semibold" onClick={onRetry}>
        {t("retry")}
      </button>
    </div>
  );
}
