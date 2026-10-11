// Temporary page for W1: shows the primitives. W2 replaces it with the app shell.
import { MatchRing } from "./components/MatchRing";
import { ReturnBars } from "./components/ReturnBars";
import { RiskBar } from "./components/RiskBar";
import { Stars } from "./components/Stars";

export function Gallery() {
  return (
    <main className="mx-auto max-w-xl p-6 text-xs">
      <div className="rounded-2xl bg-white p-4 shadow-sm">
        <div className="flex items-center gap-3.5">
          <MatchRing value={8.2} />
          <h4 className="flex-1 text-[15px] font-semibold">Nurol Portföy Para Piyasası (TL)</h4>
          <div className="text-right">
            <Stars count={5} />
            <div className="text-xl font-bold">
              3. <span className="text-[13px] font-medium text-muted">/ 88</span>
            </div>
          </div>
        </div>
        <div className="my-3.5 rounded-xl bg-gray-50 p-2.5">
          <div className="text-[11px] text-muted">SPK risk değeri</div>
          <RiskBar level={1} />
        </div>
        <ReturnBars
          rows={[
            { period: "3m", fund: 11.2, category: 10.5 },
            { period: "6m", fund: 22.4, category: 20.8 },
            { period: "1y", fund: 47.6, category: 44.5 },
            { period: "real_1y", fund: 4.1, category: 1.5 },
          ]}
        />
        <div className="mt-3 text-right">
          <button className="rounded-[10px] bg-brand px-3.5 py-1.5 font-semibold text-white">Seçime ekle</button>
        </div>
      </div>
    </main>
  );
}
