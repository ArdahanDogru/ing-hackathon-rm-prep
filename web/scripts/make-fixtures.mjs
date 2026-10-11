// Hand-made API samples for tests and `npm run dev:mock` until the lead's real
// samples (tests/contracts/fixtures/api/*.json) are on main. Values are
// illustrative, not market data. Run: node scripts/make-fixtures.mjs
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, "..", "src", "test", "fixtures");
const personaDir = join(here, "..", "..", "tests", "contracts", "fixtures", "personas");
mkdirSync(out, { recursive: true });

const persona = (id) => JSON.parse(readFileSync(join(personaDir, `${id}.json`), "utf8"));
const write = (name, data) => writeFileSync(join(out, `${name}.json`), JSON.stringify(data, null, 1) + "\n");

const SNAP = "20261010-001233-6b20";
const fact = (value, id) => ({ value, evidence_id: id });

// --- options of P01 -----------------------------------------------------------
const funds = [
  // id, label, category key/label, kind, returns [3m,6m,1y,real], cat avg, rank, stars, better, risk, sell days, match, score
  ["fund:NJR", "Nurol Portföy Para Piyasası (TL) Fonu", "money_market", "Para Piyasası", [11.9, 23.1, 47.6, 4.1], [11.2, 21.5, 44.5, 1.5], [3, 88], 5, 96, 1, 0, 10, 0.812],
  ["fund:TPP", "Tera Portföy Para Piyasası Fonu", "money_market", "Para Piyasası", [11.7, 22.8, 46.9, 3.5], [11.2, 21.5, 44.5, 1.5], [7, 88], 5, 92, 1, 0, 9.3, 0.791],
  ["fund:AKP", "Ak Portföy Para Piyasası Fonu", "money_market", "Para Piyasası", [11.4, 22.0, 45.8, 2.6], [11.2, 21.5, 44.5, 1.5], [21, 88], 4, 76, 1, 0, 6.4, 0.744],
  ["fund:KBD", "Kuveyt Kısa Vadeli Borçlanma Araçları Fonu", "short_debt", "Kısa Vadeli Borçlanma Araçları", [11.1, 21.9, 46.2, 3.0], [10.6, 20.7, 43.1, 0.2], [4, 41], 5, 90, 2, 1, 8.6, 0.776],
  ["fund:IKB", "İş Portföy Kısa Vadeli Borçlanma Araçları Fonu", "short_debt", "Kısa Vadeli Borçlanma Araçları", [10.8, 21.0, 44.0, 1.1], [10.6, 20.7, 43.1, 0.2], [15, 41], 3, 63, 2, 1, 5.7, 0.731],
  ["fund:YBF", "Yapı Kredi Borçlanma Araçları Fonu", "debt", "Borçlanma Araçları", [9.8, 20.1, 42.3, -0.6], [9.5, 19.4, 40.2, -2.1], [9, 64], 4, 86, 3, 1, 7.9, 0.761],
  ["fund:GBF", "Garanti Borçlanma Araçları Fonu", "debt", "Borçlanma Araçları", [9.1, 18.7, 39.0, -3.0], [9.5, 19.4, 40.2, -2.1], [40, 64], 2, 37, 3, 1, 5.0, 0.702],
];
const rank = funds.map((f) => f[0]);
const timeDeposit = {
  option_id: "time_deposit:ing_e_vadeli",
  label: "ING e-Vadeli (32 gün)",
};

const why = {
  "fund:NJR": [["likiditeyi koruma", "Paraya aynı gün erişim"], ["sınırlı dalgalanma", "SPK risk değeri 1"]],
  "fund:TPP": [["likiditeyi koruma", "Paraya aynı gün erişim"], ["sınırlı dalgalanma", "SPK risk değeri 1"]],
  "fund:AKP": [["likiditeyi koruma", "Paraya aynı gün erişim"]],
  "fund:KBD": [["düzenli gelir", "Kategorisinin üzerinde 1 yıllık getiri"], ["likiditeyi koruma", "Paraya 1 iş gününde erişim"]],
  "fund:IKB": [["likiditeyi koruma", "Paraya 1 iş gününde erişim"]],
  "fund:YBF": [["düzenli gelir", "Kategorisinin üzerinde 1 yıllık getiri"]],
  "fund:GBF": [],
};

const ev = (opt, q) => `E${(opt + q).split("").reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7).toString(16).padStart(8, "0").slice(0, 8)}`;

function optionView(f) {
  const [id, label, ck, cl, r, avg, rk, stars, better, risk, days, match] = f;
  return {
    option_id: id,
    label,
    kind: "fund",
    category_key: ck,
    category_label: cl,
    fx: false,
    returns: { "3m": fact(r[0], ev(id, "3m")), "6m": fact(r[1], ev(id, "6m")), "1y": fact(r[2], ev(id, "1y")), real_1y: fact(r[3], ev(id, "real")) },
    category_avg: { "3m": avg[0], "6m": avg[1], "1y": avg[2], real_1y: avg[3] },
    rank: { position: rk[0], of: rk[1] },
    stars,
    better_than_pct: better,
    risk: { level: risk, evidence_id: ev(id, "risk") },
    access: { days, label: days === 0 ? "Aynı gün" : `${days} iş günü`, evidence_id: ev(id, "valor") },
    match,
    why: why[id],
    warnings: [],
    data_notes: [],
    selected: false,
    rm_note: "",
  };
}

const baseline = {
  option_id: "deposit:ing_turuncu",
  label: "ING Turuncu Hesap (standart)",
  kind: "deposit",
  category_key: "deposit",
  category_label: "Mevduat",
  fx: false,
  returns: { "3m": null, "6m": null, "1y": fact(38.0, ev("dep", "1y")), real_1y: fact(-6.8, ev("dep", "real")) },
  category_avg: null,
  rank: null,
  stars: null,
  better_than_pct: null,
  risk: null,
  access: { days: 0, label: "Aynı gün", evidence_id: ev("dep", "valor") },
  match: null,
  why: [["likiditeyi koruma", "Paraya aynı gün erişim"]],
  warnings: [],
  data_notes: [],
  selected: false,
  rm_note: "",
};

const tdView = {
  ...baseline,
  option_id: timeDeposit.option_id,
  label: timeDeposit.label,
  kind: "time_deposit",
  category_key: "time_deposit",
  category_label: "Vadeli Mevduat",
  returns: { "3m": null, "6m": null, "1y": fact(42.0, ev("td", "1y")), real_1y: fact(-3.9, ev("td", "real")) },
  access: { days: 32, label: "Vade sonunda (32 gün)", evidence_id: ev("td", "valor") },
  match: 7.1,
  why: [["düzenli gelir", "Vade sonunda sabit faiz"]],
};

const options = Object.fromEntries(funds.map((f) => [f[0], optionView(f)]));
options[baseline.option_id] = baseline;
options[tdView.option_id] = tdView;
options["fund:YBF"].data_notes = [{ message: "tefas_web: 6 aylık getiri bir gün eski", flags: ["stale"], sources: ["tefas_web"], evidence_ids: [ev("fund:YBF", "6m")] }];

const option = (o) => ({ option_id: o.option_id, kind: o.kind, label: o.label, entity: o.option_id.split(":")[1], fund_kind: o.kind === "fund" ? o.category_key : "", fx: false });
const scored = (o, score) => ({
  option: option(o),
  score,
  score_parts: { return: +(score * 0.4).toFixed(3), liquidity: +(score * 0.35).toFixed(3), volatility: +(score * 0.25).toFixed(3) },
  constraints: [{ rule_id: "risk_ceiling", passed: true, reason: "SPK risk değeri tavanın altında", evidence_ids: [] }],
  confidence: 0.9,
  stability: 0.95,
  evidence_ids: Object.values(o.returns).filter(Boolean).map((f) => f.evidence_id),
  reasons: { return: "1 yıllık getiri kategorinin üzerinde", liquidity: "satış valörü kısa", volatility: "düşük dalgalanma" },
});

const p01 = persona("p01");
const warnings = [
  { code: "concentration", message: "Önerilerin üçü de TL faiz getirisine bağlı; faiz düşerse getiriler birlikte düşer.", evidence_ids: [], option_ids: ["fund:NJR", "fund:KBD", "fund:YBF"], audience: "client" },
  { code: "deposit_vs_market", message: "ING Turuncu Hesap standart oranı piyasa ortalamasının 4,2 puan altında.", evidence_ids: [ev("dep", "1y")], option_ids: ["deposit:ing_turuncu"], audience: "rm" },
  { code: "low_stability", message: "Ak Portföy Para Piyasası Fonu sırası küçük veri değişimlerinde değişiyor.", evidence_ids: [], option_ids: ["fund:AKP"], audience: "rm" },
];
const dataQuality = [
  { message: "tefas_web: 6 aylık getiri bir gün eski", flags: ["stale"], sources: ["tefas_web"], evidence_ids: [ev("fund:YBF", "6m")] },
  { message: "evds: TÜFE serisi ayın 3'ünde güncellenir", flags: [], sources: ["evds"], evidence_ids: [] },
];
const talking = [
  { code: "deposit_real", label: "Mevduatta reel getiri", figure: "−%6,8", text: "Mevduattaki birikiminiz son bir yılda enflasyonun gerisinde kaldı.", evidence_ids: [ev("dep", "real")], option_ids: [] },
  { code: "best_alternative", label: "Para piyasası fonu", figure: "%4,1", text: "İlk öneri geçen yıl enflasyonun üzerinde getiri sağladı; bu geçmiş bir getiridir.", evidence_ids: [ev("fund:NJR", "real")], option_ids: ["fund:NJR"] },
  { code: "access", label: "Paraya erişim", figure: "1 iş günü", text: "Önerilen fonlarda paranıza en geç bir iş gününde ulaşırsınız.", evidence_ids: [], option_ids: ["fund:NJR", "fund:KBD", "fund:YBF"] },
];
const rejectedFunds = [
  ["fund:HSE", "Hedef Portföy Hisse Senedi Fonu", "SPK risk değeri 6, müşterinin tavanı 3"],
  ["fund:AGF", "Altın Katılım Fonu", "SPK risk değeri 5, müşterinin tavanı 3"],
  ["fund:DEU", "Eurobond Borçlanma Araçları Fonu", "SPK risk değeri 4, müşterinin tavanı 3"],
];

const result = {
  run_id: "R01a1b2c3d4",
  config_hash: "example00000",
  created_at: "2026-10-10T09:00:00+03:00",
  persona: p01,
  snapshot_id: SNAP,
  excluded_sources: [],
  state: "ready",
  options: [scored(baseline, 0.42), ...rank.map((id, i) => scored(options[id], funds[i][12])), scored(tdView, 0.755)],
  rejected: rejectedFunds.map(([id, label, reason]) => ({
    option: { option_id: id, kind: "fund", label, entity: id.split(":")[1], fund_kind: "", fx: id === "fund:DEU" },
    failed: [{ rule_id: "risk_ceiling", passed: false, reason, evidence_ids: [] }],
  })),
  questions: [
    { question_id: "q:gelir_sikligi", text: "Gelirin hangi sıklıkla gerektiğini sorun.", reason: "Düzenli gelir önceliği için ödeme sıklığı bilinmiyor.", about: "gelir_nakit_akisi_ihtiyaci", choices: ["Aylık", "Üç aylık", "Yıllık"], answer: null, blocking: false },
  ],
  assumptions: ["Mevduat için 100.000-249.999 TL diliminin standart oranı kullanıldı (tutar bilinmiyor; hoş geldin oranı geçicidir).", "Reel getiri son 12 aylık TÜFE ile hesaplandı."],
  warnings,
  data_quality: dataQuality,
  rm_status: "pending",
  rm_note: "",
  rm_selected: [],
  rm_option_notes: {},
  talking_points: talking,
  to_confirm: ["Yatırım tutarını sorun: 100.000–249.999 TL dilimi varsayıldı."],
};

const top = ["fund:NJR", "fund:KBD", "fund:YBF"];
for (const id of top) options[id].warnings = warnings.filter((w) => w.option_ids.includes(id) && w.audience === "client");

const runReady = {
  result,
  test_run: false,
  persona_changes: [],
  baseline,
  top,
  categories: [
    { key: "money_market", label: "Para Piyasası", count: 3, best_return_1y: 47.6, option_ids: ["fund:NJR", "fund:TPP", "fund:AKP"] },
    { key: "short_debt", label: "Kısa Vadeli Borçlanma Araçları", count: 2, best_return_1y: 46.2, option_ids: ["fund:KBD", "fund:IKB"] },
    { key: "debt", label: "Borçlanma Araçları", count: 2, best_return_1y: 42.3, option_ids: ["fund:YBF", "fund:GBF"] },
    { key: "time_deposit", label: "Vadeli Mevduat", count: 1, best_return_1y: 42.0, option_ids: [tdView.option_id] },
  ],
  options,
  talking_points: talking,
  to_confirm: [
    { text: "Yatırım tutarını sorun: 100.000–249.999 TL dilimi varsayıldı.", question_id: null, choices: [] },
    { text: "Gelirin hangi sıklıkla gerektiğini sorun.", question_id: "q:gelir_sikligi", choices: ["Aylık", "Üç aylık", "Yıllık"] },
  ],
  assumptions: result.assumptions,
  data_notes: dataQuality,
  client_warnings: warnings.filter((w) => w.audience === "client"),
  rm_warnings: warnings.filter((w) => w.audience === "rm"),
  rejected_by_rule: [
    { rule_id: "risk_ceiling", label: "Risk tavanının üzerinde", count: 3, options: rejectedFunds.map(([, label, reason]) => ({ label, reasons: [reason] })) },
  ],
};

const approvedOptions = structuredClone(options);
for (const id of top) approvedOptions[id].selected = true;
const runApproved = {
  ...structuredClone(runReady),
  result: { ...structuredClone(result), rm_status: "approved", rm_selected: top, rm_note: "" },
  options: approvedOptions,
};

const sentence = (text, option_ids = [], title = "") => ({ text, option_ids, evidence_ids: [], title });
const narrative = (lang) => {
  const tr = lang === "TR";
  const sections = [
    { key: "ozet", sentences: [sentence(tr ? "Müşteriye mevduata bağlı birikimini düzenli gelirle ve düşük riskle değerlendirme yollarını anlatın." : "Explain to the client how to use the deposit savings for regular income at low risk.")] },
    { key: "talking_points", sentences: [
      sentence(tr ? "Mevduat birikimi son bir yılda enflasyonun gerisinde kaldı." : "The deposit savings fell behind inflation last year.", [], tr ? "Mevduatın reel kaybı" : "Real loss on deposits"),
      sentence(tr ? "Para piyasası fonu aynı gün erişim ve düşük risk sunuyor." : "A money market fund gives same-day access at low risk.", ["fund:NJR"], tr ? "Aynı gün erişim" : "Same-day access"),
      sentence(tr ? "Üç öneri de düşük risk sınırının içinde kalıyor." : "All three recommendations stay inside the low risk limit.", [], tr ? "Risk sınırı" : "Risk limit"),
    ] },
    { key: "teklif_metni", sentences: [sentence(tr ? "“Birikiminizi mevduatta tutmaya devam edebilirsiniz; ama bir bölümünü aynı gün erişebileceğiniz düşük riskli fonlara ayırırsanız, geçen yılın verilerine göre enflasyonun üzerinde kalma şansınız daha yüksek olur.”" : "“You can keep your savings in deposits; but if you put a part into low-risk funds with same-day access, last year's data suggests a better chance to stay above inflation.”")] },
    { key: "oneriler", sentences: top.map((id) => sentence(tr ? `${options[id].label}: kategorisinin üzerinde getiri ve kısa satış valörü olduğunu anlatın.` : `${options[id].label}: explain the above-category return and the short sale settlement.`, [id])) },
    { key: "dikkat", sentences: [sentence(tr ? "Üç önerinin de TL faizine bağlı olduğunu belirtin." : "Say that all three recommendations depend on TL interest rates.", top)] },
    { key: "alternatifler", sentences: [sentence(tr ? "ING e-Vadeli 32 gün vadeyle sabit faiz sunar." : "ING e-Vadeli gives a fixed rate for 32 days.", [tdView.option_id])] },
    { key: "sorular", sentences: [sentence(tr ? "Gelirin hangi sıklıkla gerektiğini sorun." : "Ask how often the client needs the income.")] },
    { key: "varsayimlar", sentences: [sentence(tr ? "Yatırım tutarı 100.000–249.999 TL dilimi olarak varsayıldı." : "The amount was assumed in the 100,000–249,999 TL tier.")] },
  ];
  const markdown = sections.map((s) => `## ${s.key}\n\n${s.sentences.map((x) => x.text).join(" ")}`).join("\n\n") + "\n";
  return {
    run_id: result.run_id,
    lang,
    sections,
    source: "llm",
    model: "claude-sonnet-5-5",
    prompt_version: "n4",
    checks: [],
    created_at: "2026-10-10T09:05:00+03:00",
    cost_usd: 0.031,
    status: "draft",
    rm_text: "",
    need_tags: { "fund:NJR": ["likiditeyi koruma", "sınırlı dalgalanma"], "fund:KBD": ["düzenli gelir"], "fund:YBF": ["düzenli gelir"] },
    markdown,
  };
};

// needs_rm_input: a blocking question, nothing ranked.
const p03 = persona("p03");
const needsResult = {
  ...structuredClone(result),
  run_id: "R03e5f6a7b8",
  persona: p03,
  state: "needs_rm_input",
  options: [],
  rejected: [],
  questions: [
    { question_id: "q:acik_kisitlar[0]", text: "Kısıtın ne anlama geldiğini müşteriye sorun.", reason: "Kısıt bir kurala eşlenemedi.", about: "acik_kisitlar[0]", choices: ["Hisse senedi olmasın", "Döviz olmasın", "Kısıt yok"], answer: null, blocking: true },
  ],
  warnings: [],
  talking_points: [],
  to_confirm: [],
};
const runNeedsInput = {
  result: needsResult,
  test_run: false,
  persona_changes: [],
  baseline: null,
  top: [],
  categories: [],
  options: {},
  talking_points: [],
  to_confirm: [],
  assumptions: needsResult.assumptions,
  data_notes: [],
  client_warnings: [],
  rm_warnings: [],
  rejected_by_rule: [],
};

// test run: P01 with an edited age.
const edited = { ...p01, yas: 45 };
const runTest = {
  ...structuredClone(runReady),
  result: { ...structuredClone(result), run_id: "R01t0e1s2t3", persona: edited },
  test_run: true,
  persona_changes: [{ field: "yas", original: 62, edited: 45 }],
};

write("personas", ["p01", "p02", "p03", "p04", "p05"].map(persona));
write("snapshots", [SNAP, "20261009-231500-1a2b"]);
write("sources", {
  evds: { status: "ok", error: null, fallback_from: null, excluded: false },
  manual: { status: "ok", error: null, fallback_from: null, excluded: false },
  tefas_web: { status: "ok", error: null, fallback_from: null, excluded: false },
  kap: { status: "skipped", error: null, fallback_from: null, excluded: false },
});
write("run_p01_ready", runReady);
write("run_p01_approved", runApproved);
write("run_needs_input", runNeedsInput);
write("run_test", runTest);
write("narrative_p01_tr", narrative("TR"));
write("narrative_p01_en", narrative("EN"));
write("glossary", [
  { term: "valor", form: "satış valörü", explanation: "Fon satışından sonra paranın hesaba geçtiği iş günü sayısı." },
  { term: "reel_getiri", form: "reel getiri", explanation: "Enflasyondan arındırılmış getiri." },
]);
write("evidence_item", {
  id: ev("fund:NJR", "1y"),
  quantity: "fund_return_1y",
  entity: "NJR",
  value: 47.6,
  unit: "percent",
  as_of: "2026-10-09",
  source: "tefas_web",
  source_url: "https://www.tefas.gov.tr/FonKarsilastirma.aspx",
  fetched_at: "2026-10-10T00:12:33+03:00",
  snapshot_id: SNAP,
  raw_ref: "payloads/tefas_web/returns.json#NJR",
  flags: [],
  note: "",
  entity_name: "NUROL PORTFÖY PARA PİYASASI (TL) FONU",
});
console.log("fixtures written to", out);
