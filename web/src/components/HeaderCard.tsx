import type { ReactNode } from "react";
import type { Persona } from "../api/types";
import { useT } from "../i18n";

export type HeaderPoint = { title: string; text: string };

/** Navy header card, only the client: profile, aim, tags, talking points, script + notes on one row. */
export function HeaderCard({
  persona,
  aim,
  points,
  script,
  notes,
}: {
  persona: Persona;
  aim: string;
  points: HeaderPoint[];
  script: string;
  notes: ReactNode;
}) {
  const t = useT();
  return (
    <section
      className="mb-6 rounded-[20px] px-7 py-7 text-white"
      style={{ background: "linear-gradient(135deg, #1D2A6B 0%, #2F4A9A 100%)" }}
    >
      <div className="flex items-center gap-4">
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-white/15 text-xl font-bold">
          {persona.persona_id}
        </div>
        <div>
          <h2 className="text-2xl font-semibold">{`${persona.profil}, ${persona.yas}`}</h2>
          <div className="text-base opacity-85">
            {`${persona.risk_profili} · ${t("horizon")} ${persona.yatirim_ufku} · ${t("liquidity")} ${persona.likidite_ihtiyaci.toLocaleLowerCase("tr")}`}
          </div>
        </div>
      </div>
      <p data-testid="header-aim" className="my-4 max-w-[62ch] text-[19px] leading-relaxed">
        <span className="opacity-80">{`${t("meetingAim")}: `}</span>
        {aim}
      </p>
      <div className="mb-5 flex flex-wrap gap-2">
        {persona.oncelikler.map((p) => (
          <span key={p} className="rounded-full bg-white/15 px-3 py-1.5 text-sm">
            {p}
          </span>
        ))}
        {persona.acik_kisitlar.map((k) => (
          <span key={k} className="rounded-full bg-[rgba(255,190,150,0.22)] px-3 py-1.5 text-sm">
            {`${t("constraint")}: ${k}`}
          </span>
        ))}
      </div>
      {points.length > 0 && (
        <div className="grid gap-3 md:grid-cols-3">
          {points.map((p, i) => (
            <div key={i} data-testid="header-point" className="rounded-[14px] px-4 py-3.5" style={{ background: "rgba(255,255,255,.12)" }}>
              {p.title && <div className="mb-1 text-base font-bold">{p.title}</div>}
              <div className="text-[15px] leading-snug opacity-90">{p.text}</div>
            </div>
          ))}
        </div>
      )}
      <div className="mt-5 grid items-stretch gap-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <div data-testid="script" className="relative rounded-2xl bg-white px-7 py-5 text-ink">
          <span aria-hidden="true" className="absolute right-5 top-1 font-serif text-[64px] leading-none text-[#C9D7EE]">
            “
          </span>
          <div className="text-[13px] font-bold uppercase tracking-[0.06em] text-[#355FA1]">{t("script")}</div>
          <p className="mt-2 max-w-[64ch] text-[19px] leading-[1.7]">{script}</p>
        </div>
        {notes}
      </div>
    </section>
  );
}
