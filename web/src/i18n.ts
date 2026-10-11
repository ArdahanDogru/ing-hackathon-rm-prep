// Screen labels, every key in TR and EN (docs/web-ui.md section 7). Engine
// texts (reasons, warnings, questions) stay Turkish and do not come from here.
import { createContext, useContext } from "react";
import type { Lang } from "./api/types";

const TR = {
  appTitle: "Görüşme hazırlığı",
  persona: "Müşteri",
  data: "Veri",
  snapshot: "Veri anlık görüntüsü",
  sources: "Kaynaklar",
  sourceOk: "tamam",
  sourceFailed: "hata",
  sourceSkipped: "atlandı",
  sourceFallback: "önceki veri",
  language: "Dil",
  loading: "Yükleniyor…",
  retry: "Tekrar dene",
  errorTitle: "Bir sorun oluştu",
  noRun: "Bir müşteri seçin.",
  dashboard: "Panel",
  meetingText: "Görüşme hazırlığı",
  printCard: "Görüşme kartı",
  backToDashboard: "Panele dön",
  runId: "Çalıştırma",
} as const;

export type LabelKey = keyof typeof TR;

const EN: Record<LabelKey, string> = {
  appTitle: "Meeting preparation",
  persona: "Client",
  data: "Data",
  snapshot: "Data snapshot",
  sources: "Sources",
  sourceOk: "ok",
  sourceFailed: "failed",
  sourceSkipped: "skipped",
  sourceFallback: "earlier data",
  language: "Language",
  loading: "Loading…",
  retry: "Try again",
  errorTitle: "Something went wrong",
  noRun: "Select a client.",
  dashboard: "Dashboard",
  meetingText: "Meeting preparation",
  printCard: "Meeting card",
  backToDashboard: "Back to the dashboard",
  runId: "Run",
};

export const labels: Record<Lang, Record<LabelKey, string>> = { TR, EN };

export const LangContext = createContext<Lang>("TR");

/** The label function of the current language. */
export function useT(): (key: LabelKey) => string {
  const lang = useContext(LangContext);
  return (key) => labels[lang][key];
}
