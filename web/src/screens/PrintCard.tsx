// The meeting card for the browser's print-to-PDF (route /print/:runId): A4,
// no top bar, no buttons. Same content as the meeting text view.
import { useContext } from "react";
import type { NarrativeView, RunView, SectionKey } from "../api/types";
import { RiskBar } from "../components/RiskBar";
import { fmtPct } from "../format";
import { LangContext, useT } from "../i18n";
import { Markdown } from "../markdown";
import "../print.css";
import { CodeBadge, ProductBadges } from "../product";
import { profileChanges } from "../profileChanges";

function List({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <section className="print-avoid mt-5">
      <h2 className="mb-1.5 text-[15px] font-bold">{title}</h2>
      <ul className="list-disc space-y-1 pl-5">
        {items.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>
    </section>
  );
}

export function PrintCard({ view, narrative }: { view: RunView; narrative: NarrativeView }) {
  const t = useT();
  const lang = useContext(LangContext);
  const r = view.result;
  const p = r.persona;
  const sentences = (key: SectionKey) => narrative.sections.find((s) => s.key === key)?.sentences ?? [];
  // a block's texts with the RM's edits: "" = deleted (left out), else the edited text
  const edits = narrative.rm_edits ?? {};
  const blockTexts = (block: string, original: string[], list = false) => {
    const e = edits[block];
    if (e === undefined) return original;
    return list ? e.split("\n").map((l) => l.trim()).filter(Boolean) : e.trim() ? [e] : [];
  };
  const texts = (key: SectionKey) => blockTexts(key, sentences(key).map((s) => s.text), key !== "ozet" && key !== "teklif_metni");
  const tp = sentences("talking_points");
  const points = tp.length
    ? tp.flatMap((s, i) => blockTexts(`talking_points:${i}`, [s.text]).map((text) => ({ title: s.title, text })))
    : view.talking_points.map((x) => ({ title: x.label, text: x.text }));
  const optionTexts = (id: string) =>
    blockTexts(
      `oneriler:${id}`,
      sentences("oneriler")
        .filter((s) => s.option_ids[0] === id)
        .map((s) => s.text),
    );
  const shownOptions = r.rm_selected.filter((id) => view.options[id] && edits[`oneriler:${id}`] !== "");
  // the current text (W19: a draft too, no approval needed) prints as Markdown when the RM edited it;
  // `markdown` is the composed text with the edits and deletions (the approved text when approved)
  const editedText = narrative.markdown.trim() !== (narrative.draft_markdown ?? "").trim() ? narrative.markdown : null;

  return (
    <article className="print-page mx-auto max-w-[190mm] bg-white p-8 text-[13px] leading-relaxed text-ink">
      <header className="flex items-start justify-between border-b border-gray-300 pb-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-brand">ING · {t("printCard")}</div>
          <h1 className="mt-1 text-xl font-bold">{`${p.persona_id} · ${p.profil}, ${p.yas}`}</h1>
          <div className="text-muted">
            {`${p.risk_profili} · ${t("horizon")} ${p.yatirim_ufku} · ${t("liquidity")} ${p.likidite_ihtiyaci.toLocaleLowerCase("tr")}`}
          </div>
          {view.test_run && view.persona_changes.length > 0 && (
            <div data-testid="print-edited-profile" className="mt-1 text-xs">
              {`${t("editedLine")}: ${profileChanges(view.persona_changes, lang)}`}
            </div>
          )}
        </div>
        <div className="text-right text-xs text-muted">
          <div>{r.run_id}</div>
          <div>{r.snapshot_id}</div>
        </div>
      </header>

      {editedText !== null ? (
        <section className="mt-4">
          <Markdown text={editedText} />
        </section>
      ) : (
        <>
          {texts("ozet").length > 0 && (
            <p className="mt-4 text-[14px]">
              <b>{`${t("meetingAim")}: `}</b>
              {texts("ozet").join(" ")}
            </p>
          )}
          {texts("piyasa_notu").length > 0 && <p className="mt-2 text-xs text-muted">{texts("piyasa_notu").join(" ")}</p>}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {p.oncelikler.map((x) => (
              <span key={x} className="rounded-full border border-gray-300 px-2 py-0.5 text-xs">
                {x}
              </span>
            ))}
            {p.acik_kisitlar.map((k) => (
              <span key={k} className="rounded-full border border-[#F79009] px-2 py-0.5 text-xs">{`${t("constraint")}: ${k}`}</span>
            ))}
          </div>

          {points.length > 0 && (
            <section className="print-avoid mt-4 grid grid-cols-3 gap-3">
              {points.map((x, i) => (
                <div key={i} className="rounded-lg border border-gray-200 p-2.5">
                  <div className="font-bold">{x.title}</div>
                  <div className="text-xs">{x.text}</div>
                </div>
              ))}
            </section>
          )}

          {texts("teklif_metni").length > 0 && (
            <section className="print-avoid mt-4 rounded-lg bg-[#F3F6FB] p-3">
              <div className="text-xs font-bold uppercase tracking-wide text-[#355FA1]">{t("script")}</div>
              <p className="mt-1 text-[14px]">{texts("teklif_metni").join(" ")}</p>
            </section>
          )}

          {shownOptions.length > 0 && <h2 className="mb-2 mt-5 text-[15px] font-bold">{t("recommendations")}</h2>}
          {shownOptions.map((id, i) => {
            const o = view.options[id];
            const r1 = o.returns["1y"];
            const tags = narrative.need_tags[id] ?? [];
            return (
              <section key={id} className="print-avoid mb-3 rounded-lg border border-gray-200 p-3">
                <div data-testid="print-option" className="flex items-baseline gap-2">
                  <b>{`${i + 1}.`}</b>
                  <b>
                    <CodeBadge optionId={id} />
                    {o.label}
                    <ProductBadges badges={o.badges} />
                  </b>
                  <span className="text-xs text-muted">{o.category_label}</span>
                </div>
                <div className="mt-1.5 grid grid-cols-3 gap-3 text-xs">
                  <div>
                    <span className="text-muted">{`${t("return1yLong")}: `}</span>
                    <b>{r1 ? fmtPct(r1.value) : "—"}</b>
                  </div>
                  <div>{o.risk ? <RiskBar level={o.risk.level} /> : "—"}</div>
                  <div>
                    <span className="text-muted">{`${t("access")}: `}</span>
                    <b>{o.access.label ?? "—"}</b>
                  </div>
                </div>
                {tags.length > 0 && <div className="mt-1 text-xs text-[#2C4F8F]">{tags.join(" · ")}</div>}
                {optionTexts(id).map((text, k) => (
                  <p key={k} className="mt-1">
                    {text}
                  </p>
                ))}
                {r.rm_option_notes[id] && (
                  <p className="mt-1 text-xs">
                    <b>{`${t("myNote")}: `}</b>
                    {r.rm_option_notes[id]}
                  </p>
                )}
              </section>
            );
          })}

          <List title={t("attention")} items={texts("dikkat")} />
          <List title={t("otherOptions")} items={texts("alternatifler")} />
          <List title={t("questionsToAsk")} items={texts("sorular")} />
          <List title={t("assumptions")} items={texts("varsayimlar")} />
        </>
      )}

      {r.rm_note && (
        <section className="print-avoid mt-5">
          <h2 className="mb-1 text-[15px] font-bold">{t("myNotes")}</h2>
          <p>{r.rm_note}</p>
        </section>
      )}
      <section data-testid="print-rm-notes" className="print-avoid mt-5 rounded-lg border border-dashed border-gray-300 p-3">
        <h2 className="mb-1 text-[15px] font-bold">{`${t("rmNotes")} · ${t("onlyForYou")}`}</h2>
        <ul className="list-disc space-y-1 pl-5">
          {view.rm_warnings.map((w) => (
            <li key={w.code + w.message}>{w.message}</li>
          ))}
        </ul>
      </section>

      <footer data-testid="print-footer" className="mt-6 border-t border-gray-300 pt-2 text-[11px] text-muted">
        {[
          narrative.source === "template" ? t("templateText") : narrative.model,
          narrative.checks.length ? `${narrative.checks.length} ${t("checkFindings")}` : t("checkPassed"),
          `$${narrative.cost_usd.toLocaleString(lang === "TR" ? "tr-TR" : "en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
          r.created_at.slice(0, 10),
        ].join(" · ")}
      </footer>
    </article>
  );
}
