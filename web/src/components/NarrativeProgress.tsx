// W41: the wait for the meeting text as the steps the narrator goes through, each with the
// inputs it uses (docs/narrator.md "draft"): the client, the approved options, the market
// data, the rules, then the model writes and the validator checks. The server reports no
// progress: the first four steps come in on a timer (they take well under a second on the
// server), the writing step stays open until the text is there; the check runs inside that
// wait and is shown as next. Every input shown comes from the RunView.
import { useEffect, useState } from "react";
import type { RunView } from "../api/types";
import { snapshotDate } from "./BriefCard";
import { fmtPct } from "../format";
import { fill, useT, type LabelKey as Key } from "../i18n";

/** Time per step of the first four (ms); the chips of a step come in STAGGER_MS apart. */
export const STEP_MS = 1100;
const STAGGER_MS = 120;
const WRITE = 4;

const SECTIONS: Key[] = ["meetingAim", "tpDoc", "scriptShort", "recommendations", "attention", "questionsToAsk", "assumptions"];
const RULES: Key[] = ["progRule1", "progRule2", "progRule3", "progRule4"];
const CHECKS: Key[] = ["progCheck1", "progCheck2", "progCheck3"];

function Dot({ state }: { state: "done" | "active" | "next" }) {
  if (state === "done")
    return (
      <span aria-hidden="true" className="flex h-5 w-5 items-center justify-center rounded-full bg-[#E3F4EA] text-[12px] font-bold text-[#1F7A4D]">
        ✓
      </span>
    );
  if (state === "active")
    return (
      <span aria-hidden="true" className="relative flex h-5 w-5 items-center justify-center">
        <span className="absolute inline-flex h-3 w-3 rounded-full bg-cobalt opacity-60 motion-safe:animate-ping" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-cobalt" />
      </span>
    );
  return <span aria-hidden="true" className="h-5 w-5 rounded-full border-2 border-gray-200" />;
}

function Chips({ items }: { items: string[] }) {
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      {items.map((x, i) => (
        <span
          key={x + i}
          data-testid="prog-chip"
          className="rounded-md bg-[#F2F4F7] px-2 py-0.5 text-[13px] text-[#344054] motion-safe:animate-rise"
          style={{ animationDelay: `${i * STAGGER_MS}ms` }}
        >
          {x}
        </span>
      ))}
    </div>
  );
}

export function NarrativeProgress({ view }: { view: RunView }) {
  const t = useT();
  const r = view.result;
  const p = r.persona;
  const [step, setStep] = useState(0);
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (step >= WRITE) return;
    const timer = setTimeout(() => setStep((s) => s + 1), STEP_MS);
    return () => clearTimeout(timer);
  }, [step]);

  const options = r.rm_selected.map((id) => view.options[id]).filter(Boolean);
  const deposit = view.talking_points.find((x) => x.code === "deposit_real");
  const steps: { title: string; chips: string[] }[] = [
    {
      title: t("progClient"),
      chips: [`${p.profil}, ${p.yas}`, p.risk_profili, p.yatirim_amaci, p.yatirim_ufku, ...p.oncelikler, ...p.acik_kisitlar].filter(Boolean),
    },
    {
      title: fill(t("progOptions"), { n: options.length }),
      chips: options.map((o) => {
        // "Nurol Para Piyasası (TL)": the issuer's first word tells two money market funds apart
        const name = [o.issuer.split(" ")[0], o.short_label || o.label].filter(Boolean).join(" ");
        const real = o.returns.real_1y?.value;
        return real !== undefined ? `${name} · ${fmtPct(real)} ${t("presReal")}` : name;
      }),
    },
    {
      title: t("progData"),
      chips: [
        t("progTefas"),
        t("progTufe"),
        deposit ? fill(t("progDeposit"), { figure: deposit.figure ?? "" }) : t("progDepositPlain"),
        fill(t("progDate"), { date: snapshotDate(r.snapshot_id) }),
      ],
    },
    { title: t("progRules"), chips: RULES.map((k) => t(k)) },
    { title: t("progWrite"), chips: SECTIONS.map((k) => t(k)) },
    { title: t("progCheck"), chips: CHECKS.map((k) => t(k)) },
  ];

  return (
    <section data-testid="narrative-progress" aria-live="polite" className="rounded-2xl bg-white px-6 py-5 shadow-sm">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <b className="text-[17px]">{t("textPreparing")}</b>
        <span data-testid="prog-seconds" className="text-[13px] tabular-nums text-muted">
          {fill(t("nodeSeconds"), { n: seconds })}
        </span>
      </div>
      <ol className="flex flex-col gap-3">
        {steps.map((s, i) => {
          if (i > step + 1) return null;
          const state = i < step ? "done" : i === step ? "active" : "next";
          return (
            <li key={i} data-testid="prog-step" data-state={state} className="flex gap-3 motion-safe:animate-rise">
              <Dot state={state} />
              <div className="min-w-0 flex-1">
                <div className={`text-[15px] ${state === "next" ? "text-muted" : "font-semibold text-ink"}`}>{s.title}</div>
                {(state !== "next" || i === WRITE + 1) && <Chips items={s.chips} />}
                {i === WRITE && state === "active" && <p className="m-0 mt-1.5 text-[13px] text-muted">{t("progWriteNote")}</p>}
                {i === WRITE + 1 && <p className="m-0 mt-0.5 text-[13px] text-muted">{t("progCheckNote")}</p>}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
