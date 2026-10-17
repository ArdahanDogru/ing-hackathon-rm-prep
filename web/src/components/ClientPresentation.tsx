// The meeting text (W27, W28): one page the RM shows or prints for the client, with the RM's
// own help in yellow boxes next to the part it belongs to. Numbers and charts come from the
// RunView (code, not the narrator; locked); the text blocks are the narrator's blocks with
// their editing and checks. The yellow boxes and the comments (rm_note, rm_option_notes) are
// never in the client view or the print.
import { useState, type ReactNode } from "react";
import type { NarrativeView, OptionView, RunView } from "../api/types";
import { fmtDate, fmtPct } from "../format";
import { fill, useT } from "../i18n";

export interface BlockOpts {
  /** true: the block can be edited but not deleted (the risks) */
  noDelete?: boolean;
}

/** The RM's help next to a part of the page: the slots MeetingText fills. */
export interface RmNotes {
  /** under the cover: the aim of the meeting, the market note */
  cover?: ReactNode;
  /** under the key figures: the talking points */
  figures?: ReactNode;
  /** under the fund cards: the other options */
  funds?: ReactNode;
  /** under the risks: the assumptions */
  risks?: ReactNode;
}

const ACCENT = "#C2410C";
/** The chart's scale ends at this real return (%) or at the largest value. */
const SCALE_MIN = 8;
/** The access timeline shows at least this many days (a 32-day term deposit). */
const DAYS_MIN = 32;

/** "+%4,9" / "−%1,2" (a talking point figure) → 4.9 / −1.2; null when it is no percent. */
export function parseFigure(figure: string | undefined): number | null {
  if (!figure || !figure.includes("%")) return null;
  const n = Number(figure.replace("−", "-").replace(/[+%\s]/g, "").replace(/\./g, "").replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

/**
 * The job of each fund on the page: the first of its need tags (the client's own priorities)
 * that no fund before it has, else its first tag, else its category.
 */
export function fundRoles(funds: OptionView[], needTags: Record<string, string[]>): Record<string, string> {
  const used = new Set<string>();
  const out: Record<string, string> = {};
  for (const o of funds) {
    const tags = needTags[o.option_id] ?? [];
    const role = tags.find((x) => !used.has(x)) ?? tags[0] ?? o.category_label;
    used.add(role);
    out[o.option_id] = role;
  }
  return out;
}

/** What may join the fund's name to the rest of a sentence: ":", ",", "için", "de", or a space. */
const NAME_JOIN = /^(\s*[:,–-]\s*|\s+(için|de|da|ise)\s+|\s+)/i;

/**
 * A fund card's sentence without the fund's name in front (W30): the card's title is the name.
 * "Nurol Portföy Para Piyasası (TL) için getirisi …" → "Getirisi …". Unchanged when no name
 * of the fund starts it, or when nothing would be left.
 */
export function withoutName(text: string, o: OptionView, lang: "TR" | "EN"): string {
  const loc = lang === "TR" ? "tr" : "en";
  const names = [`${o.issuer} ${o.short_label}`, o.label, o.short_label].filter(Boolean).sort((a, b) => b.length - a.length);
  const lower = text.toLocaleLowerCase(loc);
  for (const name of names) {
    if (!lower.startsWith(name.toLocaleLowerCase(loc))) continue;
    const rest = text.slice(name.length).replace(NAME_JOIN, "");
    if (!rest || rest.length === text.length - name.length) continue;
    return rest.charAt(0).toLocaleUpperCase(loc) + rest.slice(1);
  }
  return text;
}

/**
 * A fund sentence that only restates the card's labels (W31): it gives both the real and the
 * nominal 1-year return ("reel getirisi %7,36, nominal getirisi %47,60, risk düzeyi 1/7").
 */
export function restatesFacts(text: string, o: OptionView): boolean {
  // the numbers of the text, each with its own rounding ("%9,7", "%7,36", "%35,0", "7.36%")
  const nums = [...text.matchAll(/\d+(?:[.,]\d+)?/g)].map((m) => {
    const [whole, frac = ""] = m[0].split(/[.,]/);
    return { value: Number(`${whole}.${frac || "0"}`), places: frac.length };
  });
  const said = (v: number | undefined) =>
    v !== undefined && nums.some((n) => Math.abs(Math.round(v * 10 ** n.places) / 10 ** n.places - n.value) < 1e-9);
  return said(o.returns.real_1y?.value) && said(o.returns["1y"]?.value);
}

/** "1.000.000" → 1000000; anything without digits → 0. */
export const parseAmount = (s: string) => Number(s.replace(/\D/g, "")) || 0;
const tl = (n: number) => `${Math.round(n).toLocaleString("tr-TR")} TL`;

/** "Nurol Para Piyasası (TL)" → the short name and the issuer apart. */
const fundName = (o: OptionView) => o.short_label || o.label;
/** "Allbatross Portföy Birinci Para Piyasası (TL)"; a deposit has no issuer. */
const fullName = (o: OptionView) => [o.issuer, fundName(o)].filter(Boolean).join(" ");

interface Figure {
  label: string;
  value: string;
  /** the option the figure belongs to, or "all of them" */
  who: string;
  sub: string;
  accent: boolean;
}

function Heading({ n, children }: { n: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline gap-3">
      <span className="text-sm font-bold" style={{ color: ACCENT }}>
        {n}
      </span>
      <h2 className="m-0 font-serif text-[26px] font-semibold leading-tight">{children}</h2>
    </div>
  );
}

/** A yellow box for the RM only: a small heading, "only you", an optional action and the body. */
export function RmNote({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  const t = useT();
  return (
    <section data-testid="rm-note" className="rounded-xl border border-dashed border-[#E3C766] bg-[#FFFBEA] px-5 py-4 text-[15px] leading-relaxed text-[#2C2924] print:hidden">
      <div className="mb-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 data-testid="doc-heading" className="m-0 text-xs font-bold uppercase tracking-[0.06em] text-[#8A6100]">
          {title}
        </h3>
        <span className="text-xs text-[#8A6100]">{t("presRmOnly")}</span>
        {action}
      </div>
      {children}
    </section>
  );
}

function Comment({ label, value, placeholder, onChange }: { label: string; value: string; placeholder: string; onChange: (v: string) => void }) {
  return (
    <label data-testid="pres-comment" className="flex flex-col gap-1 rounded-xl border border-[#F0DC8A] bg-[#FFF8D6] px-3 py-2 text-[13px] text-[#6B4E00] print:hidden">
      <span className="font-semibold">{label}</span>
      <textarea
        rows={2}
        aria-label={label}
        placeholder={placeholder}
        className="resize-y rounded-lg border border-[#F0DC8A] bg-white/70 px-2.5 py-1.5 text-[14px] leading-normal text-ink"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

export function ClientPresentation({
  view,
  draft,
  rm,
  editable,
  block,
  notes,
  optionNotes,
  onOptionNote,
}: {
  view: RunView;
  draft: NarrativeView;
  /** true: the RM's view with the yellow boxes and comments; false: what the client sees */
  rm: boolean;
  editable: boolean;
  /** One narrator block (teklif_metni, oneriler:<id>, dikkat, sorular) with its editing. */
  block: (id: string, title: string, opts?: BlockOpts) => ReactNode;
  notes: RmNotes;
  optionNotes: Record<string, string>;
  onOptionNote: (id: string, v: string) => void;
}) {
  const t = useT();
  const r = view.result;
  const [amountText, setAmountText] = useState("1.000.000");
  const amount = parseAmount(amountText);

  const funds = r.rm_selected.map((id) => view.options[id]).filter((o): o is OptionView => !!o);
  const roles = fundRoles(funds, draft.need_tags);
  const real = (o: OptionView) => o.returns.real_1y?.value ?? null;
  const deposit = view.talking_points.find((p) => p.code === "deposit_real");
  const depositReal = parseFigure(deposit?.figure);
  const best = funds.reduce<OptionView | null>((b, o) => (real(o) !== null && (b === null || real(o)! > real(b)!) ? o : b), null);

  // 01: the deposit market average and each fund, real 1-year return
  const rows = [
    ...(depositReal !== null ? [{ id: "deposit", name: t("presDeposit"), sub: t("presDepositSub"), value: depositReal, fund: false }] : []),
    ...funds.filter((o) => real(o) !== null).map((o) => ({ id: o.option_id, name: fundName(o), sub: o.issuer, value: real(o)!, fund: true })),
  ];
  const scale = Math.max(SCALE_MIN, ...rows.map((x) => Math.abs(x.value)));

  // 03: when the money is there
  const days = (o: OptionView) => o.access.days ?? o.access.lock_days;
  const dayScale = Math.max(DAYS_MIN, ...funds.map((o) => days(o) ?? 0));
  // only the options with a known access count (a fund may have none in the snapshot)
  const known = funds.filter((o) => o.access.label);
  const sameAccess = new Set(known.map((o) => `${o.access.label}|${days(o)}`)).size === 1;
  // W31: the access labels only when the options differ (or only some have one); one value
  // for all is in the key figures. W32: the timeline needs at least two known, different values
  const accessDiffers = known.length > 0 && !(sameAccess && known.length === funds.length);
  const showTimeline = known.length > 1 && !sameAccess;
  const riskDiffers = new Set(funds.filter((o) => o.risk).map((o) => o.risk!.level)).size > 1;

  // 04: the risk scale
  const levels = [...new Set(funds.map((o) => o.risk?.level).filter((x): x is number => x != null))].sort();
  const maxLevel = levels.length ? levels[levels.length - 1] : null;
  const ceiling = view.risk_ceiling;

  const snapshot = /^(\d{4})(\d{2})(\d{2})/.exec(r.snapshot_id);
  const dataDate = snapshot ? fmtDate(`${snapshot[1]}-${snapshot[2]}-${snapshot[3]}`) : "";

  // W32: each key figure names the option it belongs to (or says it holds for all)
  const fastest = known.reduce<OptionView | null>((b, o) => (b === null || (days(o) ?? Infinity) < (days(b) ?? Infinity) ? o : b), null);
  const riskiest = funds.find((o) => o.risk?.level === maxLevel) ?? null;
  const withRisk = funds.filter((o) => o.risk);
  const figures: Figure[] = [
    best && {
      label: t("presFigReal"),
      value: fmtPct(real(best)!).replace(/^%/, "+%"),
      who: fullName(best),
      sub: deposit ? fill(t("presFigDeposit"), { figure: deposit.figure }) : "",
      accent: true,
    },
    fastest && {
      label: t("presFigAccess"),
      value: fastest.access.label!,
      who: sameAccess && known.length === funds.length && funds.length > 1 ? t("presFigAll") : fullName(fastest),
      sub: sameAccess || known.length === 1 ? "" : t("presFigFastest"),
      accent: false,
    },
    maxLevel !== null && riskiest && {
      label: t("presFigRisk"),
      value: `${maxLevel} / 7`,
      who:
        riskDiffers || withRisk.length === 1
          ? fullName(riskiest)
          : withRisk.length === funds.length
            ? t("presFigAll")
            : t("presFigFunds"),
      sub: ceiling !== null ? fill(t("presFigRiskSub"), { ceiling }) : "",
      accent: false,
    },
  ].filter((x): x is Figure => !!x);

  const card = "rounded-xl border border-[#ECE9E3] bg-[#FBFAF8] p-6";

  return (
    <div data-testid="presentation" className="flex min-w-0 flex-col gap-4">
      {rm && (
        <p data-testid="pres-hint" className="m-0 px-1 text-[13px] text-[#4A463F] print:hidden">
          {t("presHint")}
        </p>
      )}

      <article className="flex flex-col gap-11 rounded-2xl bg-white px-6 py-10 text-[#1D1B18] shadow-sm sm:px-14 print:shadow-none">
        {/* cover */}
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap justify-between gap-2 text-sm text-[#5E5950]">
            <span>{t("presFor")}</span>
            <span>{dataDate}</span>
          </div>
          <div className="text-sm font-semibold uppercase tracking-[0.06em]" style={{ color: ACCENT }}>
            {t("presGoal")}
          </div>
          <h1 data-testid="pres-goal" className="m-0 max-w-[760px] font-serif text-[38px] font-semibold leading-tight">
            {r.persona.yatirim_amaci}
          </h1>
          <div className="max-w-[760px] text-[18px] leading-relaxed text-[#3A362F]">{block("teklif_metni", t("scriptShort"))}</div>
          {rm && notes.cover}
        </div>

        {/* key figures */}
        {figures.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-3">
            {figures.map((f) => (
              <div key={f.label} data-testid="pres-figure" className="flex flex-col gap-1.5 rounded-xl bg-[#F7F5F1] p-5">
                <span className="text-[13px] text-[#5E5950]">{f.label}</span>
                <span className="font-serif text-[34px] font-bold leading-tight" style={f.accent ? { color: ACCENT } : undefined}>
                  {f.value}
                </span>
                <span data-testid="pres-figure-who" className="text-sm font-semibold text-[#1D1B18]">
                  {f.who}
                </span>
                {f.sub && <span className="text-sm text-[#3A362F]">{f.sub}</span>}
              </div>
            ))}
          </div>
        )}
        {rm && notes.figures}

        {/* 01 real return */}
        {rows.length > 0 && (
          <section className="flex flex-col gap-4">
            <Heading n="01">{t("pres1Title")}</Heading>
            <p className="m-0 max-w-[760px] text-base leading-relaxed text-[#3A362F]">{t("pres1Lead")}</p>
            <div className={`${card} flex flex-col gap-4`}>
              <div className="font-serif text-[22px] font-semibold leading-snug">{t("pres1Message")}</div>
              <div className="flex flex-wrap items-center justify-between gap-2 text-[13px] text-[#5E5950]">
                <span>{t("pres1Chart")}</span>
                <label className="flex items-center gap-2 print:hidden">
                  {t("presAmount")}
                  <input
                    type="text"
                    inputMode="numeric"
                    aria-label={t("presAmount")}
                    className="w-32 rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 text-right text-[14px] text-ink"
                    value={amountText}
                    onChange={(e) => setAmountText(e.target.value)}
                  />
                  TL
                </label>
              </div>
              {rows.map((x) => (
                <div key={x.id} data-testid="pres-bar" className="grid grid-cols-[minmax(0,150px)_minmax(0,1fr)_auto] items-center gap-3 sm:grid-cols-[200px_minmax(0,1fr)_130px] sm:gap-4">
                  <div className="text-sm leading-tight">
                    <div className="font-semibold">{x.name}</div>
                    <div className="text-xs text-[#5E5950]">{x.sub}</div>
                  </div>
                  <div className="relative h-8 rounded-md bg-[#EFECE6]">
                    <div
                      className="absolute inset-y-0 left-0 rounded-md"
                      style={{ width: `${(Math.max(0, x.value) / scale) * 100}%`, background: x.fund ? ACCENT : "#B9B3A8" }}
                    />
                    <span className={`absolute left-2.5 top-1.5 text-sm font-bold ${x.fund ? "text-white" : "text-ink"}`}>
                      {fmtPct(x.value).replace(/^%/, "+%")}
                    </span>
                  </div>
                  <div className="text-right text-[15px] font-bold tabular-nums">
                    {amount > 0 ? `${x.value >= 0 ? "+" : "−"}${tl(Math.abs((amount * x.value) / 100))}` : ""}
                  </div>
                </div>
              ))}
              <div className="border-t border-[#ECE9E3] pt-3 text-xs text-[#5E5950]">
                {[amount > 0 ? fill(t("pres1Tl"), { amount: tl(amount) }) : null, fill(t("pres1Note"), { date: dataDate })].filter(Boolean).join(" ")}
              </div>
            </div>
          </section>
        )}

        {/* 02 the funds */}
        <section className="flex flex-col gap-4">
          <Heading n="02">{t("pres2Title")}</Heading>
          <div className="grid gap-4 md:grid-cols-3">
            {funds.map((o) => {
              const id = `oneriler:${o.option_id}`;
              const role = roles[o.option_id];
              const content = block(id, fundName(o));
              return (
                <div key={o.option_id} data-testid="pres-fund" className="flex flex-col gap-3 rounded-xl border border-[#ECE9E3] p-5">
                  <span className="self-start rounded-full bg-[#FBE3D3] px-2.5 py-1 text-xs font-bold tracking-[0.02em] text-[#8A3307]">
                    {role.toLocaleUpperCase("tr")}
                  </span>
                  <div>
                    <div className="font-serif text-[19px] font-semibold leading-snug">{fundName(o)}</div>
                    <div className="text-[13px] text-[#5E5950]">{o.issuer}</div>
                  </div>
                  <div className="flex flex-wrap gap-2 text-[13px]">
                    {real(o) !== null && (
                      <span className="rounded-md bg-[#F7F5F1] px-2 py-1">
                        <b>{fmtPct(real(o)!).replace(/^%/, "+%")}</b> {t("presReal")}
                      </span>
                    )}
                    {o.returns["1y"] && (
                      <span className="rounded-md bg-[#F7F5F1] px-2 py-1">
                        <b>{fmtPct(o.returns["1y"].value).replace(/^%/, "+%")}</b> {t("presNominal")}
                      </span>
                    )}
                    {riskDiffers && o.risk && <span className="rounded-md bg-[#F7F5F1] px-2 py-1">{`${t("riskShort")} ${o.risk.level}/7`}</span>}
                    {accessDiffers && o.access.label && <span className="rounded-md bg-[#F7F5F1] px-2 py-1">{o.access.label}</span>}
                  </div>
                  {content !== null && <div className="border-t border-[#ECE9E3] pt-3 text-[15px] leading-relaxed text-[#2C2924]">{content}</div>}
                  {rm && (
                    <Comment
                      label={t("presComment")}
                      placeholder={t("optionNote")}
                      value={optionNotes[o.option_id] ?? ""}
                      onChange={(v) => onOptionNote(o.option_id, v)}
                    />
                  )}
                </div>
              );
            })}
          </div>
          {rm && notes.funds}
        </section>

        {/* 03 access */}
        {showTimeline && (
          <section className="flex flex-col gap-4">
            <Heading n="03">{t("pres3Title")}</Heading>
            <div className={`${card} flex flex-col gap-3`}>
              {known.map((o) => {
                const d = days(o);
                return (
                  <div key={o.option_id} data-testid="pres-access" className="grid grid-cols-[minmax(0,150px)_minmax(0,1fr)] items-center gap-3 sm:grid-cols-[200px_minmax(0,1fr)] sm:gap-4">
                    <span className="text-sm font-semibold">{fundName(o)}</span>
                    <div className="relative h-7 rounded-md bg-[#EFECE6]">
                      {d !== null && (
                        <div className="absolute inset-y-0 left-0 rounded-md" style={{ width: `max(12px, ${(d / dayScale) * 100}%)`, background: ACCENT }} />
                      )}
                      <span className="absolute top-1 text-[13px] font-semibold" style={{ left: d !== null ? `calc(max(12px, ${(d / dayScale) * 100}%) + 10px)` : "10px" }}>
                        {o.access.label ?? "—"}
                      </span>
                    </div>
                  </div>
                );
              })}
              <div className="flex justify-between pl-[calc(150px+12px)] text-xs text-[#5E5950] sm:pl-[calc(200px+16px)]">
                <span>{t("pres3Day0")}</span>
                <span>{fill(t("pres3DayN"), { n: dayScale })}</span>
              </div>
            </div>
          </section>
        )}

        {/* 04 risks */}
        <section className="flex flex-col gap-4">
          <Heading n="04">{t("pres4Title")}</Heading>
          <div className="grid items-start gap-6 md:grid-cols-2">
            <div className={`${card} flex flex-col gap-3`}>
              <span className="text-[13px] text-[#5E5950]">{t("pres4Scale")}</span>
              <div data-testid="pres-risk" className="grid grid-cols-7 gap-1">
                {[1, 2, 3, 4, 5, 6, 7].map((n) => {
                  const own = levels.includes(n);
                  const allowed = ceiling !== null && n <= ceiling;
                  return (
                    <div
                      key={n}
                      data-level={n}
                      data-own={own || undefined}
                      className="flex h-10 items-center justify-center rounded-md text-sm font-bold"
                      style={own ? { background: ACCENT, color: "#FFFFFF" } : allowed ? { background: "#F7D9C4", color: "#8A3307" } : { background: "#EFECE6", color: "#6B655B" }}
                    >
                      {n}
                    </div>
                  );
                })}
              </div>
              <div className="flex flex-wrap justify-between gap-2 text-xs text-[#5E5950]">
                <span>{fill(t("pres4Funds"), { levels: levels.join(", ") || "—" })}</span>
                {ceiling !== null && <span>{fill(t("pres4Limit"), { ceiling })}</span>}
              </div>
            </div>
            <div className="text-[15px] leading-relaxed text-[#2C2924]">{block("dikkat", t("attention"), { noDelete: true })}</div>
          </div>
          {rm && editable && <p className="m-0 text-[13px] text-[#5E5950] print:hidden">{t("pres4Locked")}</p>}
          {rm && notes.risks}
        </section>

        {/* 05 next step */}
        <section data-testid="pres-next" className="flex flex-col gap-3 rounded-2xl bg-[#1D1B18] p-7 text-[#F4F2EE]">
          <div className="flex items-baseline gap-3">
            <span className="text-sm font-bold text-[#F59E5B]">05</span>
            <h2 className="m-0 font-serif text-[24px] font-semibold">{t("pres5Title")}</h2>
          </div>
          <div className="text-base leading-relaxed">{block("sorular", t("questionsToAsk"))}</div>
        </section>

        <p className="m-0 border-t border-[#ECE9E3] pt-4 text-xs leading-normal text-[#5E5950]">
          {fill(t("presDisclaimer"), { date: dataDate })}
        </p>
      </article>
    </div>
  );
}
