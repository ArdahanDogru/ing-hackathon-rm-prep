import { useEffect, useRef, useState } from "react";
import type { Lang, Persona, ResetResult, SourceStatus } from "../api/types";
import { ResetButton } from "./ResetButton";
import { snapshotLabel } from "../format";
import { useT } from "../i18n";
import { UploadButton } from "./UploadButton";

export interface TopBarProps {
  personas: Persona[];
  personaId: string;
  onPersona: (id: string) => void;
  snapshots: string[];
  snapshotId: string;
  onSnapshot: (id: string) => void;
  sources: Record<string, SourceStatus>;
  excluded: string[];
  onExcluded: (excluded: string[]) => void;
  lang: Lang;
  onLang: (lang: Lang) => void;
  /** W31: the ids of the uploaded clients (marked in the dropdown) and the upload */
  uploaded?: string[];
  onUploaded?: (p: Persona) => void;
  /** W27: "Sıfırla" done; another error than 409 */
  onReset?: (r: ResetResult) => void;
  onResetError?: (e: Error) => void;
}

export function TopBar(p: TopBarProps) {
  const t = useT();
  const [dataOpen, setDataOpen] = useState(false);
  const menu = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!dataOpen) return;
    const close = (e: MouseEvent) => {
      if (menu.current && !menu.current.contains(e.target as Node)) setDataOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setDataOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [dataOpen]);

  const statusLabel = (s: SourceStatus) =>
    s.fallback_from
      ? t("sourceFallback")
      : s.status === "ok"
        ? t("sourceOk")
        : s.status === "failed"
          ? t("sourceFailed")
          : t("sourceSkipped");

  const toggleSource = (name: string) =>
    p.onExcluded(p.excluded.includes(name) ? p.excluded.filter((x) => x !== name) : [...p.excluded, name].sort());

  return (
    <header className="sticky top-0 z-30 border-b border-gray-200 bg-white">
      <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-4 px-6">
        <div className="flex items-center gap-2">
          <span className="rounded-md bg-brand px-2 py-0.5 text-sm font-extrabold tracking-wide text-white">ING</span>
          <span className="text-sm font-semibold">{t("appTitle")}</span>
        </div>

        <label className="ml-6 flex items-center gap-2 text-sm">
          <span className="text-muted">{t("persona")}</span>
          <select
            className="rounded-lg border border-gray-300 bg-white px-2 py-1 text-sm"
            value={p.personaId}
            onChange={(e) => p.onPersona(e.target.value)}
          >
            {p.personas.map((x) => (
              <option key={x.persona_id} value={x.persona_id}>
                {`${x.persona_id} · ${x.profil}${p.uploaded?.includes(x.persona_id) ? ` ${t("uploadedMark")}` : ""}`}
              </option>
            ))}
          </select>
        </label>
        {p.onUploaded && <UploadButton onUploaded={p.onUploaded} />}

        <div className="ml-auto flex items-center gap-3">
          <div className="relative" ref={menu}>
            <button
              type="button"
              className="rounded-lg border border-gray-300 px-3 py-1 text-sm"
              aria-expanded={dataOpen}
              onClick={() => setDataOpen((o) => !o)}
            >
              {t("data")} ▾
            </button>
            {dataOpen && (
              <div
                role="dialog"
                aria-label={t("data")}
                className="absolute right-0 mt-2 w-80 rounded-xl border border-gray-200 bg-white p-4 text-sm shadow-lg"
              >
                <label className="block">
                  <span className="text-xs text-muted">{t("snapshot")}</span>
                  <select
                    className="mt-1 w-full rounded-lg border border-gray-300 px-2 py-1"
                    value={p.snapshotId}
                    onChange={(e) => p.onSnapshot(e.target.value)}
                  >
                    {p.snapshots.map((s) => (
                      <option key={s} value={s}>
                        {snapshotLabel(s)}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="mt-3 text-xs text-muted">{t("sources")}</div>
                <ul className="mt-1 space-y-1">
                  {Object.entries(p.sources).map(([name, s]) => (
                    <li key={name}>
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={!p.excluded.includes(name)}
                          onChange={() => toggleSource(name)}
                        />
                        <span className="flex-1">{name}</span>
                        <span className={s.status === "ok" ? "text-xs text-muted" : "text-xs text-red-700"}>
                          {statusLabel(s)}
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {p.onReset && <ResetButton onDone={p.onReset} onError={(e) => p.onResetError?.(e)} />}

          <div role="group" aria-label={t("language")} className="flex overflow-hidden rounded-lg border border-gray-300 text-sm">
            {(["TR", "EN"] as const).map((l) => (
              <button
                key={l}
                type="button"
                aria-pressed={p.lang === l}
                className={p.lang === l ? "bg-ink px-2.5 py-1 font-semibold text-white" : "px-2.5 py-1"}
                onClick={() => p.onLang(l)}
              >
                {l}
              </button>
            ))}
          </div>
        </div>
      </div>
    </header>
  );
}
