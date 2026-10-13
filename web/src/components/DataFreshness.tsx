// The data freshness line above the dashboard (docs/web-ui.md W14): stale data
// and "Veriyi yenile", a running ingest, newer data and "Yeni veriyle aç", an
// error and "Tekrar dene". Fresh data and no job: no line.
import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import type { IngestStatus } from "../api/types";
import { fmtDay, fmtTime } from "../format";
import { fill, useT } from "../i18n";

const POLL_MS = 15_000;

export interface DataFreshnessProps {
  /** the snapshot list the app has: a newer latest snapshot is not on it */
  known: string[];
  /** reload the snapshot list and select the newest */
  onOpenNewest: () => void;
}

export function DataFreshness({ known, onOpenNewest }: DataFreshnessProps) {
  const t = useT();
  const [status, setStatus] = useState<IngestStatus | null>(null);
  const [startError, setStartError] = useState<string | null>(null);

  // a failed poll keeps the old status (a new object, so that the poll goes on)
  const refresh = useCallback(() => {
    api.ingestStatus().then(setStatus, () => setStatus((s) => (s ? { ...s } : null)));
  }, []);
  useEffect(refresh, [refresh]);

  useEffect(() => {
    if (!status?.running) return;
    const timer = setTimeout(refresh, POLL_MS);
    return () => clearTimeout(timer);
  }, [status, refresh]);

  const start = () => {
    setStartError(null);
    api.startIngest().then(setStatus, (e: Error) => {
      if (e instanceof ApiError && e.status === 409) refresh(); // another process runs it
      else setStartError(e.message);
    });
  };

  if (!status) return null;
  const latest = status.latest_snapshot;
  const error = status.running ? null : (startError ?? status.error);

  let text: string;
  let button: { label: string; onClick: () => void } | null = null;
  let hint: string | null = null;
  let tone = "border-gray-200";
  if (status.running) {
    text = fill(t("ingestRunning"), { time: status.started_at ? fmtTime(status.started_at) : "" });
  } else if (error) {
    text = fill(t("ingestError"), { error });
    button = { label: t("retry"), onClick: start };
    tone = "border-red-200";
  } else if (latest && known.length && !known.includes(latest)) {
    text = fill(t("ingestNewer"), { date: status.created_at ? fmtDay(status.created_at) : latest });
    button = { label: t("ingestOpenNewer"), onClick: onOpenNewest };
    tone = "border-brand";
  } else if (status.stale) {
    const days = Math.max(1, Math.floor((status.age_hours ?? 24) / 24));
    const date = status.created_at ? fmtDay(status.created_at) : (latest ?? "");
    text = fill(t(days === 1 ? "ingestStaleOne" : "ingestStale"), { n: days, date });
    button = { label: t("ingestRefresh"), onClick: start };
    hint = t("ingestHint");
  } else {
    return null;
  }

  return (
    <div
      role="status"
      data-testid="data-freshness"
      className={`mb-4 flex flex-wrap items-center gap-3 rounded-xl border bg-white px-4 py-2 text-sm ${tone}`}
    >
      <span className={status.running ? "animate-pulse" : undefined}>{text}</span>
      {button && (
        <span className="ml-auto flex items-center gap-2">
          {hint && <span className="text-xs text-muted">{hint}</span>}
          <button type="button" className="rounded-[10px] border border-gray-300 px-3 py-1 font-semibold" onClick={button.onClick}>
            {button.label}
          </button>
        </span>
      )}
    </div>
  );
}
