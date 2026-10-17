// "Kategoriler" (W32; docs/web-ui.md "Categories by what a fund invests in"): every scored option
// by asset class, then by sub-type (from the fund name). A class opens to its sub-types; a sub-type
// shows its best 5 funds and "Tümünü göster"; a row opens the fund card. Display only: the engine's
// groups and the short-list rule do not change.
import { useMemo, useState } from "react";
import type { Category, OptionView, RunView, SubType } from "../api/types";
import { fmtPct, fmtScore } from "../format";
import { fill, useT } from "../i18n";
import { CodeBadge, ProductBadges } from "../product";

const FIRST = 5;

function FundRow({ option, score, onOpen }: { option: OptionView; score: number | undefined; onOpen: () => void }) {
  const r1 = option.returns["1y"];
  return (
    <li data-testid="fund-row" className="border-t border-gray-100">
      <button
        type="button"
        title={option.label}
        className="grid w-full grid-cols-[minmax(0,1fr)_48px_72px] items-center gap-3 py-2 text-left hover:bg-[#F7F9FC]"
        onClick={onOpen}
      >
        <span className="min-w-0 truncate text-[13px] font-medium">
          <CodeBadge optionId={option.option_id} />
          {[option.issuer.split(" ")[0], option.short_label].filter(Boolean).join(" ")}
          <ProductBadges badges={option.badges} />
        </span>
        <span className="text-right text-xs tabular-nums text-muted">{score === undefined ? "" : fmtScore(score, false)}</span>
        <span className="text-right text-sm font-semibold tabular-nums">{r1 ? fmtPct(r1.value) : "—"}</span>
      </button>
    </li>
  );
}

function SubTypeRow({
  sub,
  options,
  scores,
  onOpen,
}: {
  sub: SubType;
  options: Record<string, OptionView>;
  scores: Map<string, number>;
  onOpen: (id: string) => void;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [all, setAll] = useState(false);
  const ids = sub.option_ids.filter((id) => options[id]);
  const shown = all ? ids : ids.slice(0, FIRST);
  return (
    <li data-testid="subtype" className="border-t border-gray-100 first:border-t-0">
      <button
        type="button"
        aria-expanded={open}
        className="flex w-full items-center justify-between py-2 text-left text-sm"
        onClick={() => setOpen(!open)}
      >
        <span>{sub.label}</span>
        <span className="text-muted">
          {`${sub.count}`}
          {sub.best_return_1y !== null && ` · ${t("best")} ${fmtPct(sub.best_return_1y)}`}
          <span className="ml-2 inline-block" style={{ transform: open ? "rotate(90deg)" : "" }}>
            ›
          </span>
        </span>
      </button>
      {open && (
        <div className="pb-2 pl-3">
          <ul>
            {shown.map((id) => (
              <FundRow key={id} option={options[id]} score={scores.get(id)} onOpen={() => onOpen(id)} />
            ))}
          </ul>
          {!all && ids.length > FIRST && (
            <button type="button" className="mt-1 text-xs font-semibold text-[#355FA1] underline" onClick={() => setAll(true)}>
              {fill(t("catShowAll"), { n: ids.length })}
            </button>
          )}
        </div>
      )}
    </li>
  );
}

function ClassRow({ c, view, scores, onOpen }: { c: Category; view: RunView; scores: Map<string, number>; onOpen: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div data-testid="category" className="rounded-xl border border-gray-100 px-4">
      <button
        type="button"
        aria-expanded={open}
        className="flex w-full items-center justify-between py-3 text-left text-sm"
        onClick={() => setOpen(!open)}
      >
        <b>{c.label}</b>
        <span className="text-muted">
          {c.count}
          <span className="ml-2 inline-block" style={{ transform: open ? "rotate(90deg)" : "" }}>
            ›
          </span>
        </span>
      </button>
      {open && (
        <ul className="pb-2">
          {c.subtypes.map((s) => (
            <SubTypeRow key={s.key} sub={s} options={view.options} scores={scores} onOpen={onOpen} />
          ))}
        </ul>
      )}
    </div>
  );
}

export function CategoryList({ view, onOpen }: { view: RunView; onOpen: (id: string) => void }) {
  const t = useT();
  // one map for the scores: the rows look them up by id (every scored option is in the tree)
  const scores = useMemo(() => new Map(view.result.options.map((o) => [o.option.option_id, o.score])), [view.result.options]);
  const classes = view.categories;
  if (!classes.length) return null;
  const total = classes.reduce((n, c) => n + c.count, 0);
  return (
    <section>
      <p data-testid="categories-head" className="mb-2 text-sm text-muted">
        {fill(t("catHead"), { n: total, k: classes.length })}
      </p>
      <div className="space-y-2">
        {classes.map((c) => (
          <ClassRow key={c.key} c={c} view={view} scores={scores} onOpen={onOpen} />
        ))}
      </div>
    </section>
  );
}
