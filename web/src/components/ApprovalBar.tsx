import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { OptionView, Resolution, RunView } from "../api/types";
import { fmtDateTime } from "../format";
import { fill, useT } from "../i18n";
import { withCode } from "../product";

/** "PPN · Nurol · Para Piyasası (TL)": the code (W28), the issuer's first word and the short name. */
export function chipName(o: OptionView | undefined, id: string): string {
  if (!o) return withCode(id, id.split(":")[1] ?? id);
  const who = o.issuer.split(" ")[0];
  return withCode(id, who ? `${who} · ${o.short_label}` : o.short_label);
}

/** Bottom bar: the selection as chips, an optional note, the open "Teyit edin" reminder,
 * "Reddet", "Onayla ve metni hazırla" (the only filled button). */
export function ApprovalBar({
  view,
  selected,
  openConfirms = 0,
  unresolved = 0,
  resolutions = [],
  onRemove,
  onView,
}: {
  view: RunView;
  selected: string[];
  openConfirms?: number;
  /** W44: the profile conflicts without a reason; the approval waits for them */
  unresolved?: number;
  /** W44: the RM's reasons, sent with an approval */
  resolutions?: Resolution[];
  onRemove: (id: string) => void;
  onView: (v: RunView) => void;
}) {
  const t = useT();
  const navigate = useNavigate();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const runId = view.result.run_id;
  const status = view.result.rm_status;

  const send = async (decision: "approved" | "rejected") => {
    setBusy(true);
    setError(null);
    try {
      const approved = decision === "approved";
      const next = await api.approve(runId, decision, note, approved ? selected : [], approved ? resolutions : []);
      onView(next);
      if (decision === "approved") navigate(`/meeting/${encodeURIComponent(next.result.run_id)}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  // W30: an edited profile (a test run) can be approved too
  const reason = selected.length === 0 ? t("needOne") : null;

  return (
    <div className="sticky bottom-0 z-20 mt-6 border-t border-gray-200 bg-ink text-white">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-3 px-6 py-3 text-sm">
        {status === "pending" ? (
          <>
            <span className="font-semibold">{t("discussInMeeting")}</span>
            <ul className="flex flex-wrap gap-1.5">
              {selected.map((id) => {
                const label = view.options[id]?.label ?? id;
                const name = chipName(view.options[id], id);
                return (
                  <li
                    key={id}
                    data-testid="chip"
                    className="flex max-w-[260px] items-center gap-1 rounded-full bg-white/15 py-0.5 pl-3 pr-1 text-xs"
                  >
                    <span className="truncate" title={label}>
                      {name}
                    </span>
                    <button
                      type="button"
                      aria-label={`${label} ${t("removeFromSelection")}`}
                      className="rounded-full px-1.5 hover:bg-white/20"
                      onClick={() => onRemove(id)}
                    >
                      ✕
                    </button>
                  </li>
                );
              })}
            </ul>
            <div className="ml-auto flex flex-wrap items-center justify-end gap-3">
              <input
                aria-label={t("note")}
                placeholder={t("note")}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className="w-56 rounded-lg bg-white/10 px-3 py-1.5 text-sm placeholder:text-white/60"
              />
              {openConfirms > 0 && <span className="text-[13px] opacity-80">{`${openConfirms} ${t("notConfirmed")}`}</span>}
              {unresolved > 0 && (
                <span data-testid="unresolved" title={t("unresolvedHint")} className="cursor-help text-[13px] font-semibold text-[#FEC84B]">
                  {`⚠ ${fill(t("unresolved"), { n: unresolved })}`}
                </span>
              )}
              {(reason || error) && (
                <span role={error ? "alert" : undefined} className="text-xs text-[#FEC84B]">
                  {error ?? reason}
                </span>
              )}
              <button
                type="button"
                disabled={busy}
                className="rounded-[10px] border border-white/70 px-3 py-1.5 font-semibold disabled:opacity-50"
                onClick={() => send("rejected")}
              >
                {t("reject")}
              </button>
              <button
                type="button"
                disabled={busy || reason !== null || unresolved > 0}
                title={unresolved > 0 ? t("unresolvedHint") : undefined}
                className="rounded-[10px] bg-brand px-4 py-1.5 font-semibold text-white disabled:opacity-50"
                onClick={() => send("approved")}
              >
                {t("approve")}
              </button>
            </div>
          </>
        ) : (
          <>
            <span data-testid="decided-at" className="font-semibold">
              {`${status === "approved" ? t("approved") : t("rejected")}${
                view.result.rm_decided_at ? `: ${fmtDateTime(view.result.rm_decided_at)}` : ""
              }`}
            </span>
            {view.result.rm_note && <span className="text-white/80">{view.result.rm_note}</span>}
            {status === "approved" && (
              <Link
                to={`/meeting/${encodeURIComponent(runId)}`}
                className="ml-auto rounded-[10px] bg-brand px-4 py-1.5 font-semibold text-white"
              >
                {t("openMeeting")}
              </Link>
            )}
          </>
        )}
      </div>
    </div>
  );
}
