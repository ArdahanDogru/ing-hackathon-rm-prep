import { BLOCKING_CHECK_KINDS } from "../api/types";
import { useT } from "../i18n";

/** "phrase: 'kesin getiri' kullanılmamalı" → ["phrase", "'kesin getiri' kullanılmamalı"] */
export function splitFinding(f: string): [string, string] {
  const i = f.indexOf(":");
  return i < 0 ? ["", f.trim()] : [f.slice(0, i).trim(), f.slice(i + 1).trim()];
}

export const isBlocking = (f: string) => (BLOCKING_CHECK_KINDS as readonly string[]).includes(splitFinding(f)[0]);

/** The check findings of one edited block: blocking ones in red, number findings as warnings. */
export function FindingList({ findings }: { findings: string[] }) {
  const t = useT();
  if (!findings.length) return null;
  return (
    <ul data-testid="findings" className="mt-2 space-y-1 text-sm leading-snug">
      {findings.map((f) => {
        const [, message] = splitFinding(f);
        const hard = isBlocking(f);
        return (
          <li
            key={f}
            data-kind={splitFinding(f)[0]}
            className={hard ? "rounded-lg bg-[#FEF3F2] px-3 py-1.5 text-[#B42318]" : "rounded-lg bg-[#FFFAEB] px-3 py-1.5 text-[#B54708]"}
          >
            <b>{`${hard ? t("mustFix") : t("warnOnly")}: `}</b>
            {message}
          </li>
        );
      })}
    </ul>
  );
}
