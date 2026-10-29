// Deliverable 7: the Turkish slide deck (pptxgenjs), 10 min presentation + 5 min Q&A.
// Numbers come from README.md and docs/teslim/01, 03-06; screenshots from docs/img/readme/
// (the running app, 17.10.2026 data). Only Arial and fixed hex colors (no theme colors), so
// the deck looks the same in PowerPoint, Keynote and Google Slides (the jury's font rule).
// Usage (NODE_PATH = a folder with pptxgenjs, react, react-dom, react-icons, sharp):
//   node scripts/deck/build_deck.js docs/teslim/sunum/07-sunum.pptx
const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");

const OUT = process.argv[2] || "07-sunum.pptx";
const ROOT = path.join(__dirname, "..", "..");
const IMG = path.join(ROOT, "docs", "img", "readme");
const FONT = "Arial";

const K = {
  ink: "1C2340", // navy text, dark backgrounds
  muted: "475569",
  tint: "F1F3F7", // card fill
  line: "D0D5DD",
  white: "FFFFFF",
  orange: "FF6200", // the RM, human decisions, highlights
  orangeTint: "FFE6D5",
  code: "34407A", // deterministic code
  codeTint: "EEF2F9",
  ai: "6941C6", // language models
  aiTint: "F4F3FF",
  green: "15803D",
  red: "B91C1C",
  redTint: "FEE4E2",
  navyTint: "DCE3F0",
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };
pres.title = "Agent 007 · RM Görüşme Hazırlığı";
pres.author = "Agent 007 (Yusuf Ardahan Doğru, Öykü Irmak Hatipoğlu)";
pres.company = "ING Agentic AI Hackathon";

// ---------- layouts ----------
pres.defineSlideMaster({
  title: "KAPAK",
  background: { color: K.white },
  objects: [],
});
pres.defineSlideMaster({
  title: "ICERIK",
  background: { color: K.white },
  objects: [
    { rect: { x: 0, y: 0, w: 13.333, h: 0.09, fill: { color: K.orange } } },
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.3, w: 12.1, h: 0.85, fontFace: FONT, fontSize: 28, bold: true, color: K.ink, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { image: { path: path.join(ROOT, "web", "public", "logo-mark.png"), x: 0.6, y: 7.0, w: 0.42, h: 0.25 } },
    { text: { text: "Agent 007 · RM görüşme hazırlığı · ING Agentic AI Hackathon", options: { x: 1.12, y: 7.0, w: 8, h: 0.25, fontFace: FONT, fontSize: 10, color: K.muted, margin: 0, valign: "middle" } } },
  ],
  slideNumber: { x: 12.2, y: 7.0, w: 0.5, h: 0.25, fontFace: FONT, fontSize: 10, color: K.muted },
});
pres.defineSlideMaster({
  title: "KOYU",
  background: { color: K.ink },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.45, w: 12.1, h: 0.9, fontFace: FONT, fontSize: 30, bold: true, color: K.white, valign: "middle", align: "left", margin: 0 }, text: "" } },
  ],
});

// ---------- helpers ----------
function icon(Comp, hex = "FFFFFF") {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { color: "#" + hex, size: 256 }));
  return sharp(Buffer.from(svg)).png().toBuffer().then((b) => "image/png;base64," + b.toString("base64"));
}

function text(slide, t, o) {
  slide.addText(t, { isTextBox: true, margin: 0, valign: "top", fontFace: FONT, fontSize: 14, color: K.ink, ...o });
}

function card(slide, x, y, w, h, fill = K.tint, line) {
  slide.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.1, fill: { color: fill }, line: line ? { color: line, width: 1 } : { type: "none" } });
}

function circleIcon(slide, data, x, y, d, fill) {
  slide.addShape(pres.ShapeType.ellipse, { x, y, w: d, h: d, fill: { color: fill }, line: { type: "none" } });
  const p = d * 0.24;
  slide.addImage({ data, x: x + p, y: y + p, w: d - 2 * p, h: d - 2 * p });
}

function num(slide, n, x, y, d, fill) {
  slide.addShape(pres.ShapeType.ellipse, { x, y, w: d, h: d, fill: { color: fill }, line: { type: "none" } });
  text(slide, String(n), { x, y, w: d, h: d, fontSize: d > 0.45 ? 15 : 12, bold: true, color: K.white, align: "center", valign: "middle" });
}

function hexBadge(slide, label, x, y, w = 0.72, h = 0.62) {
  slide.addShape(pres.ShapeType.hexagon, { x, y, w, h, fill: { color: K.orange }, line: { type: "none" } });
  text(slide, label, { x, y, w, h, fontSize: 16, bold: true, color: K.white, align: "center", valign: "middle" });
}

function bullets(items, o = {}) {
  return items.map((t, i) => {
    const parts = Array.isArray(t) ? t : [{ text: t }];
    return parts.map((p, j) => ({
      text: p.text,
      options: { ...(p.options || {}), ...(j === 0 ? { bullet: { indent: 14 } } : {}), breakLine: j === parts.length - 1 && i < items.length - 1, paraSpaceAfter: o.gap ?? 6 },
    }));
  }).flat();
}

function shot(slide, file, x, y, w, ratio, frame = true) {
  const h = w / ratio;
  if (frame) slide.addShape(pres.ShapeType.rect, { x: x - 0.03, y: y - 0.03, w: w + 0.06, h: h + 0.06, fill: { color: K.navyTint }, line: { type: "none" } });
  slide.addImage({ path: path.join(IMG, file), x, y, w, h });
  return h;
}

function caption(slide, t, x, y, w) {
  text(slide, t, { x, y, w, h: 0.3, fontSize: 11, color: K.muted, italic: true });
}

function hbar(slide, x, y, wMax, h, frac, fill) {
  slide.addShape(pres.ShapeType.rect, { x, y, w: Math.max(0.04, wMax * frac), h, fill: { color: fill }, line: { type: "none" } });
}

function arrow(slide, x, y, w = 0.3, h = 0.32, fill = K.navyTint) {
  slide.addShape(pres.ShapeType.rightArrow, { x, y, w, h, fill: { color: fill }, line: { type: "none" } });
}

function legend(slide, x, y) {
  [["Kod (deterministik)", K.code], ["Dil modeli (kod denetler)", K.ai], ["RM kararı", K.orange]].forEach(([l, col], i) => {
    const xx = x + i * 2.9;
    slide.addShape(pres.ShapeType.rect, { x: xx, y: y + 0.05, w: 0.2, h: 0.2, fill: { color: col }, line: { type: "none" } });
    text(slide, l, { x: xx + 0.3, y, w: 2.5, h: 0.3, fontSize: 12, color: K.muted, valign: "middle" });
  });
}

const hdrCell = (t, fill = K.code) => ({ text: t, options: { bold: true, color: K.white, fill: { color: fill } } });
function table(slide, rows, o) {
  const body = rows.map((r, i) => r.map((c) => (typeof c === "string" ? { text: c, options: { fill: { color: i % 2 ? K.white : K.tint } } } : c)));
  slide.addTable(body, { fontFace: FONT, fontSize: 13, color: K.ink, border: { type: "solid", pt: 0.5, color: K.line }, margin: [0.05, 0.1, 0.05, 0.1], valign: "middle", ...o });
}

// Speaker notes: who speaks, the target time, what to say.
function notes(slide, who, time, body) {
  slide.addNotes(`[${who} · ${time}]\n${body}`);
}

(async () => {
  const I = {};
  const names = ["FaDatabase", "FaCogs", "FaUserCheck", "FaPenNib", "FaFingerprint", "FaQuestionCircle", "FaShieldAlt", "FaBalanceScale",
    "FaChartLine", "FaLayerGroup", "FaExclamationTriangle", "FaLightbulb", "FaClock", "FaSearch", "FaRoad", "FaRobot", "FaLock", "FaUserFriends",
    "FaCheckCircle", "FaBolt", "FaPlay", "FaGlobe"];
  for (const n of names) I[n] = await icon(fa[n]);

  // ===== 1. Kapak =====
  pres.addSection({ title: "Giriş" });
  let s = pres.addSlide({ masterName: "KAPAK", sectionTitle: "Giriş" });
  s.addShape(pres.ShapeType.rect, { x: 0, y: 0, w: 13.333, h: 0.09, fill: { color: K.orange }, line: { type: "none" } });
  s.addImage({ path: path.join(ROOT, "logo.png"), x: 0.75, y: 2.0, w: 4.1, h: 4.1 / (1504 / 1072) });
  s.addShape(pres.ShapeType.rect, { x: 5.6, y: 1.4, w: 0.03, h: 4.9, fill: { color: K.line }, line: { type: "none" } });
  text(s, "Görüşme hazırlığı:\nkanıta dayalı yatırım\nkarar desteği", { x: 6.2, y: 1.6, w: 6.6, h: 2.4, fontSize: 38, bold: true, valign: "bottom" });
  text(s, "Private Banking RM'leri için: veriden görüşme metnine, her adımda RM kontrolü", { x: 6.2, y: 4.2, w: 6.6, h: 0.8, fontSize: 18, color: K.muted });
  s.addShape(pres.ShapeType.rect, { x: 6.2, y: 5.25, w: 1.2, h: 0.06, fill: { color: K.orange }, line: { type: "none" } });
  text(s, "Agent 007 · Yusuf Ardahan Doğru, Öykü Irmak Hatipoğlu", { x: 6.2, y: 5.5, w: 6.6, h: 0.4, fontSize: 16, bold: true });
  text(s, "ING Agentic AI Hackathon · Ekim 2026", { x: 6.2, y: 5.95, w: 6.6, h: 0.4, fontSize: 14, color: K.muted });
  notes(s, "Öykü", "0:10", "Merhaba, biz Agent 007. Private Banking RM'lerinin müşteri görüşmesi hazırlığı için bir karar destek aracı geliştirdik. 10 dakikada problemi, çözümü, canlı demoyu ve test sonuçlarımızı göstereceğiz.");

  // ===== 2. Problem ve iş etkisi =====
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Giriş" });
  s.addText("RM'in hazırlığı: yüzlerce ürün, dağınık veri, kayıt yok", { placeholder: "title" });
  text(s, "RM her görüşmeden önce yüzlerce ürünü her gün değişen kaynaklardan elle karşılaştırıyor. İş yavaş, müşteriye yeterince uyarlanmıyor, kısıt kaçabiliyor ve önerinin hangi veriye dayandığı sonradan gösterilemiyor.",
    { x: 0.6, y: 1.25, w: 12.1, h: 0.85, fontSize: 16, color: K.muted });
  const stats2 = [
    ["1.444", K.code, "seçenek (17.10.2026)", "815 fon, 37 BYF, 590 pay, 2 ING mevduatı. Muhafazakâr P01 için kurallar 1.301'ini eler; kalan 143'ü elle sıralamak bir hazırlığa sığmaz."],
    ["−%8,3", K.red, "ING Turuncu Hesap, reel", "%23 faiz, stopaj ve yıllık TÜFE (%29,73) sonrası. Aynı risk sınırındaki 37 para piyasası fonu: reel medyan +%6,6."],
    ["~26 sn", K.green, "analiz ve görüşme metni", "Karar ~1,2 sn, metin ~24,9 sn (ortalama). Bugünkü hazırlık görüşme başına ~60 dk [VARSAYIM, mentorlarla teyit]."],
  ];
  stats2.forEach(([big, col, label, desc], i) => {
    const x = 0.6 + i * 4.15;
    card(s, x, 2.25, 3.85, 2.75);
    text(s, big, { x: x + 0.3, y: 2.35, w: 3.3, h: 0.9, fontSize: 46, bold: true, color: col, valign: "middle" });
    text(s, label, { x: x + 0.3, y: 3.25, w: 3.3, h: 0.35, fontSize: 15, bold: true });
    text(s, desc, { x: x + 0.3, y: 3.65, w: 3.3, h: 1.3, fontSize: 13, color: K.muted });
  });
  text(s, "Beklenen iş etkisi (ölçüldü)", { x: 0.6, y: 5.2, w: 6, h: 0.35, fontSize: 15, bold: true });
  [["0", "kısıt ihlali", "37 / 37 çalıştırma"], ["5 / 5", "tekrar tutarlılığı", "aynı girdi, aynı sonuç"], ["5 / 5", "farklı öneri seti", "5 müşteri profilinde"], ["39 / 39", "kaynak atfı", "her sayı kanıt kimliğiyle"]].forEach(([big, l, sub], i) => {
    const x = 0.6 + i * 3.08;
    card(s, x, 5.6, 2.85, 1.15, K.codeTint);
    text(s, big, { x: x + 0.2, y: 5.68, w: 1.25, h: 0.6, fontSize: 24, bold: true, color: K.code, valign: "middle" });
    text(s, l, { x: x + 1.45, y: 5.72, w: 1.35, h: 0.5, fontSize: 12, bold: true, valign: "middle" });
    text(s, sub, { x: x + 0.2, y: 6.3, w: 2.55, h: 0.35, fontSize: 11, color: K.muted });
  });
  notes(s, "Öykü", "0:50", "RM görüşmeden önce TCMB, TEFAS, Borsa İstanbul ve banka sayfalarındaki veriyi elle birleştiriyor. Kendi verimizle ölçtük: 17 Ekim'de 1.444 seçenek var; Muhafazakâr bir müşteri için bile kurallardan sonra 143 seçenek kalıyor. İkinci içgörü: nominal getiri yanıltıcı. Turuncu Hesap %23 faiz veriyor ama stopaj ve enflasyondan sonra reel −%8,3; aynı risk seviyesindeki para piyasası fonları reel +%6,6. Bizim sistemimizde analiz yaklaşık 1 saniye, metin 25 saniye; bugünkü 60 dakikalık hazırlık süresi bir varsayım, mentorlarla teyit edeceğiz. Alttaki dört gösterge test paketimizde ölçüldü.");

  // ===== 3. Kim ne yapar =====
  pres.addSection({ title: "Çözüm" });
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Çözüm" });
  s.addText("Kararı kod hazırlar, dil modeli yazar, son söz RM'in", { placeholder: "title" });
  const lanes = [
    ["Veri", I.FaDatabase, K.code, K.codeTint, "TEFAS, TCMB EVDS, Borsa İstanbul, ING oran sayfası. Her sabah 07:30, snapshot ve kalite bayrakları."],
    ["Puanlama motoru", I.FaCogs, K.code, K.codeTint, "4 eleme kuralı, 8 ölçütlü şeffaf puan, ilk 3. Aynı girdi, aynı sonuç."],
    ["Ajan (isteğe bağlı)", I.FaRobot, K.ai, K.aiTint, "RM başlatır. Web araştırması ve karşılaştırmayla kendi ilk 3'ünü önerir; kod denetler."],
    ["RM onayı", I.FaUserCheck, K.orange, K.orangeTint, "Soruları yanıtlar, çelişkileri çözer, iki listeyi görür, onaylar."],
    ["Görüşme metni", I.FaPenNib, K.ai, K.aiTint, "Yalnızca onaylı ürünlerle yazılır; doğrulayıcı her sayıyı ve adı denetler."],
  ];
  lanes.forEach(([t, ic, circ, fill, desc], i) => {
    const x = 0.6 + i * 2.5;
    card(s, x, 1.45, 2.15, 3.3, fill);
    circleIcon(s, ic, x + 0.22, 1.65, 0.7, circ);
    text(s, t, { x: x + 0.22, y: 2.48, w: 1.8, h: 0.6, fontSize: 15, bold: true, valign: "middle" });
    text(s, desc, { x: x + 0.22, y: 3.1, w: 1.8, h: 1.6, fontSize: 12.5, color: K.muted });
    if (i < lanes.length - 1) arrow(s, x + 2.18, 2.9, 0.3, 0.32);
  });
  card(s, 0.6, 5.0, 12.1, 1.4, K.tint);
  circleIcon(s, I.FaShieldAlt, 0.85, 5.3, 0.75, K.code);
  text(s, [
    { text: "Tek ilke: ", options: { bold: true } },
    { text: "dil modeli hiçbir ürünü elemez ve hiçbir kuralı aşamaz. Ajanın, metnin, profil kontrolünün ve web araştırmasının her çıktısını kod denetler; geçmezse deterministik bir yedek gelir. RM hiçbir zaman boş ekran veya uydurma veri görmez." },
  ], { x: 1.85, y: 5.1, w: 10.6, h: 1.2, fontSize: 15, valign: "middle" });
  legend(s, 0.6, 6.55);
  notes(s, "Öykü", "0:40", "İşi dört katmana ayırdık. Mavi kutular kod: veri ve puanlama motoru. Motor aynı girdiyle her zaman aynı sonucu verir ve her adımı açıklanabilir. Mor kutular dil modeli: isteğe bağlı ajan ve görüşme metni. Turuncu RM: kararı her zaman RM verir. Tek ilkemiz: dil modeli hiçbir ürünü elemez, hiçbir kuralı aşamaz; çıktısını kod denetler, geçmezse yedek gelir.");

  // ===== 4. Veri ve kanıt =====
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Çözüm" });
  s.addText("Her sayı kaynağı, tarihi ve kanıt kimliğiyle", { placeholder: "title" });
  table(s, [
    [hdrCell("Kaynak"), hdrCell("Bize ne verir")],
    ["TCMB EVDS (resmî API)", "politika faizi, USD/TRY, fonlama maliyeti, mevduat faizi, TÜFE, BIST 100"],
    ["TEFAS getiri ve fon detayı", "1 ay–5 yıl getiri, SPK risk değeri, valör, ücret, alım durumu, portföy dağılımı"],
    ["Borsa İstanbul bültenleri", "590 pay ve 37 BYF: kapanış, getiri, oynaklık, hacim"],
    ["ING oran sayfası", "Turuncu Hesap ve e-Vadeli oranları (yedek: elle girilen dosya)"],
    ["Elle girilen dosya", "stopaj oranları ve TÜFE çapraz kontrolü; her satır kaynak bağlantılı"],
    ["Web araştırması (Exa)", "ilk 3 ve şirketleri için son 90 günün haberleri; \"doğrulanmamış\" etiketi"],
  ], { x: 0.6, y: 1.35, w: 7.4, colW: [2.5, 4.9], fontSize: 12, rowH: 0.47 });
  const hEv = shot(s, "evidence.png", 8.45, 1.4, 4.25, 448 / 314);
  caption(s, "\"K\" işareti: değer, kaynak, değer tarihi, alınma zamanı, kanıt kimliği, bayraklar", 8.45, 1.4 + hEv + 0.1, 4.25);
  [[I.FaFingerprint, "Snapshot", "Ham baytlar ve SHA-256 özeti, salt okunur. replay aynı çıktıyı ağa çıkmadan üretir."],
   [I.FaExclamationTriangle, "Kalite bayrakları", "Eksik, eski, aralık dışı, çelişen, elle girilen. Bayrak değeri değiştirmez, güveni düşürür."],
   [I.FaShieldAlt, "Dürüst kaynak kullanımı", "robots.txt ve kullanım koşullarını okuduk. KAP botları engelliyor: engeli aşmıyoruz."]].forEach(([ic, t, d], i) => {
    const x = 0.6 + i * 4.15;
    card(s, x, 4.95, 3.85, 1.8);
    circleIcon(s, ic, x + 0.2, 5.1, 0.55, K.code);
    text(s, t, { x: x + 0.9, y: 5.1, w: 2.8, h: 0.55, fontSize: 15, bold: true, valign: "middle" });
    text(s, d, { x: x + 0.2, y: 5.75, w: 3.5, h: 0.95, fontSize: 12, color: K.muted });
  });
  notes(s, "Öykü", "0:40", "Veriyi resmî ve kamuya açık kaynaklardan her sabah 07:30'da topluyoruz; RM isterse o an yeniler. Ham veri snapshot olarak SHA-256 özetiyle saklanır. Kalite kontrolleri değeri değiştirmez, bayrak ekler. Ekrandaki her sayının yanında bir K işareti var: tıklayınca değeri, kaynağı, değer tarihini, alınma zamanını ve kanıt kimliğini görürsünüz. KAP botları engelliyor; engeli aşmıyoruz, fon belgeleri için yöneticinin kendi sitesine bağlantı veriyoruz.");

  // ===== 5. Karar mantığı =====
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Çözüm" });
  s.addText("Önce katı kurallar, sonra şeffaf puan", { placeholder: "title" });
  const hPipe = shot(s, "pipeline.png", 0.6, 1.35, 8.1, 1352 / 652);
  caption(s, "P02 (Dengeli ihracatçı), 17.10.2026: 1.444 seçenek → 1.138 elendi (döviz kısıtı 15) → 306 aday → 3 öneri", 0.6, 1.35 + hPipe + 0.08, 8.1);
  [[I.FaShieldAlt, "1 · Eleme kuralları", "Alıma kapalı, risk tavanı, açık kısıtlar, kısa geçmiş. Elenen her ürün gerekçe ve kanıtla listelenir."],
   [I.FaBalanceScale, "2 · Puan", "Σ ağırlık × değer − Σ ceza; 8 ölçüt: reel getiri, risk uyumu, likidite, gelir, anapara, sadelik, kalite, portföy açığı."],
   [I.FaLayerGroup, "3 · İlk 3", "Dengeli ve Agresif müşteride sınıf başına en çok 1 ürün; RM'in önüne aynı türden üç fon gelmez."]].forEach(([ic, t, d], i) => {
    const y = 1.35 + i * 1.5;
    card(s, 9.0, y, 3.7, 1.4);
    circleIcon(s, ic, 9.15, y + 0.15, 0.48, K.code);
    text(s, t, { x: 9.75, y: y + 0.15, w: 2.85, h: 0.48, fontSize: 14, bold: true, valign: "middle" });
    text(s, d, { x: 9.15, y: y + 0.68, w: 3.45, h: 0.78, fontSize: 11.5, color: K.muted });
  });
  card(s, 0.6, 6.0, 12.1, 0.8, K.orangeTint);
  text(s, [
    { text: "Neden ML değil? ", options: { bold: true } },
    { text: "Etiketli geçmiş RM kararı yok; kural 5 (uygun olmayan ürün listeye girmez) her seferinde kesin olmalı; her puan parçası gösterilebilmeli. Ağırlıklar bizim seçimimiz [VARSAYIM] ve ekranda açık." },
  ], { x: 0.85, y: 6.05, w: 11.7, h: 0.7, fontSize: 13, valign: "middle" });
  notes(s, "Ardahan", "0:45", "Motor dört eleme kuralıyla başlar: alıma kapalı fon, risk tavanı, açık kısıtlar ve kısa geçmiş. P02 için 1.444 seçenekten 1.138'i elenir, bunların 15'i döviz kısıtı yüzünden. Kalan 306 aday 8 ölçütle puanlanır; ağırlıkları müşterinin profili belirler, P02'de getiri %34, likidite ve risk uyumu %20. İlk 3 varlık sınıflarına yayılır. Neden makine öğrenmesi değil: etiketli geçmiş veri yok ve uygunluk kuralı olasılıkla değil, kesin uygulanmalı.");

  // ===== 6. Belirsizlik =====
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Çözüm" });
  s.addText("Belirsizliği saklamıyoruz: tahmin yerine soru", { placeholder: "title" });
  const unc = [
    [I.FaChartLine, K.code, "Veri güveni (0–1)", "Kullanılan en zayıf veri satırı × katsayılar: elle girilen 0,9 · eski 0,7 · çelişen 0,6 · tahmini risk 0,7 · reel getiri hesaplanamadı 0,8."],
    [I.FaLayerGroup, K.code, "İstikrar", "Her ağırlık ve ceza sınırı ×0,8 ve ×1,2: sıralama 30–32 kez yeniden hesaplanır. Ölçü: \"öneri yine çıkıyor mu?\""],
    [I.FaQuestionCircle, K.orange, "Tahmin yerine soru", "Risk profili veya kısıt okunamazsa sıralama durur ve RM'e soru açılır. Diğer bilinmeyenlerde güvenli düzey ve \"Teyit edin\"."],
    [I.FaUserFriends, K.ai, "Profil çelişkileri", "8 sabit kural ve alıntılı AI kontrolü (Claude Opus 5.5). Çözülmemiş çelişki varken öneriler onaylanamaz."],
  ];
  unc.forEach(([ic, col, t, body], i) => {
    const x = 0.6 + (i % 2) * 6.2, y = 1.35 + Math.floor(i / 2) * 2.25;
    card(s, x, y, 5.9, 2.05);
    circleIcon(s, ic, x + 0.25, y + 0.25, 0.6, col);
    text(s, t, { x: x + 1.05, y: y + 0.25, w: 4.6, h: 0.6, fontSize: 17, bold: true, valign: "middle" });
    text(s, body, { x: x + 0.25, y: y + 1.0, w: 5.4, h: 0.95, fontSize: 13, color: K.muted });
  });
  card(s, 0.6, 5.95, 12.1, 0.85, K.tint);
  text(s, [
    { text: "Varsayımlar ekranda ve kayıtta: ", options: { bold: true } },
    { text: "geçmiş getiri tahmin değildir · TÜFE %29,73 · ING oranı için 100.000–249.999 TL dilimi · risk bantları ve ağırlıklar · mevcut portföy dağılımı tahmini (TCMB FİR); RM onaylar veya düzenler." },
  ], { x: 0.85, y: 6.0, w: 11.7, h: 0.75, fontSize: 13, valign: "middle" });
  notes(s, "Ardahan", "0:40", "Veri eksik, eski ya da çelişkili olduğunda bunu saklamıyoruz. Her öneri bir veri güveni taşır. İstikrar testi ağırlıkları %20 oynatıp sıralamayı yeniden hesaplar. Motor risk profilini veya bir kısıtı okuyamazsa tahmin etmez: sıralamayı durdurur ve RM'e soru sorar. Profil kendisiyle çelişirse, örneğin dosyada 62 yaş ama notta '45 yaşında', sabit kurallar ve yapay zekâ kontrolü bunu bulur; RM gerekçe yazmadan onay veremez.");

  // ===== 7. Ajan ve dil modelleri =====
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Çözüm" });
  s.addText("Ajan sınırlar içinde çalışır, her çıktısını kod denetler", { placeholder: "title" });
  const hAg = shot(s, "agent.png", 0.6, 1.35, 7.6, 1352 / 117);
  const hPk = shot(s, "agent-picks.png", 0.6, 1.35 + hAg + 0.2, 7.6, 1352 / 584);
  caption(s, "P01: ajan AIS'i çıkarıp ZBJ'yi aldı ve nedenini yazdı; her gerekçe bir puan parçasına veya kanıt kimliğine bağlı", 0.6, 1.35 + hAg + 0.2 + hPk + 0.08, 7.6);
  card(s, 8.55, 1.35, 4.15, 2.6, K.aiTint);
  text(s, "Ajan (Claude Sonnet 5.5)", { x: 8.75, y: 1.45, w: 3.8, h: 0.4, fontSize: 15, bold: true, color: K.ai });
  text(s, bullets([
    "RM başlatır; motorun en iyi 10 adayı (RM 20'ye kadar seçer)",
    "3 araç: karsilastir, arastir, karar_ver",
    "Web bulguları veri, talimat değil; RM'in reddettiği bulgu ajana gitmez",
  ], { gap: 5 }), { x: 8.75, y: 1.9, w: 3.8, h: 2.0, fontSize: 12.5 });
  card(s, 8.55, 4.1, 4.15, 2.7, K.codeTint);
  text(s, "Kod denetimi ve yedek", { x: 8.75, y: 4.2, w: 3.8, h: 0.4, fontSize: 15, bold: true, color: K.code });
  text(s, bullets([
    "3 farklı aday, sınıf kuralı, en çok 1 pay",
    "Her gerekçe bir kanıta, bulguya veya puan parçasına atıf yapar; her sayı o veride var",
    "Hata: 1 düzeltme hakkı; sonra, 90 sn veya günlük 3 $ aşılırsa motorun ilk 3'ü",
  ], { gap: 5 }), { x: 8.75, y: 4.65, w: 3.8, h: 2.1, fontSize: 12.5 });
  notes(s, "Ardahan", "0:45", "Ajan kendiliğinden başlamaz; RM 'Ajanı çalıştır' der. Ajan motorun en iyi adaylarını, web araştırmasını ve müşterinin dağılımını görür, üç aracı vardır ve kendi ilk 3'ünü önerir. Kararını kod denetler: her gerekçe bir kanıta ya da puan parçasına atıf yapmalı, her sayı o veride bulunmalı. Geçmezse bir düzeltme hakkı var; yine geçmezse RM motorun kendi listesini görür. Görüşme metninde de aynı düzen var: doğrulayıcı olgu dışı sayıyı, elenmiş ürünü ve yasak ifadeyi reddeder; bir tekrar, sonra şablon metin.");

  // ===== 8. İnsan onay noktaları =====
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Çözüm" });
  s.addText("RM görmeden ve onaylamadan hiçbir şey ilerlemez", { placeholder: "title" });
  const steps = [
    ["1", "Teyit edin", "soruları yanıtlar; her yanıt sıralamayı yeniden hesaplatır"],
    ["2", "Çelişkiler", "gerekçesini yazar veya profili düzeltir"],
    ["3", "Ajan", "isteğe bağlı; web bulgularını onaylar veya reddeder"],
    ["4", "Onay", "konuşulacak ürünleri seçer, not yazar, onaylar veya reddeder"],
    ["5", "Metin", "blokları düzenler veya siler; düzenlenen blok yeniden denetlenir"],
    ["6", "Kart", "PDF indirir; Sunum görünümü RM'e özel notları gizler"],
  ];
  steps.forEach(([n, t, d], i) => {
    const x = 0.6 + i * 2.05;
    card(s, x, 1.45, 1.85, 2.75, K.orangeTint);
    hexBadge(s, n, x + 0.56, 1.6);
    text(s, t, { x: x + 0.12, y: 2.35, w: 1.61, h: 0.4, fontSize: 15, bold: true, align: "center" });
    text(s, d, { x: x + 0.12, y: 2.8, w: 1.61, h: 1.35, fontSize: 12, color: K.muted, align: "center" });
  });
  [["Onay kilidi", "En az 1 ürün seçili olmalı ve çözülmemiş profil çelişkisi olmamalı."],
   ["Kart kilidi", "Denetimde açık bir kural bulgusu varsa kart indirilemez ve yazdırılamaz."]].forEach(([t, d], i) => {
    const x = 0.6 + i * 6.2;
    card(s, x, 4.45, 5.9, 1.05, K.redTint);
    circleIcon(s, I.FaLock, x + 0.2, 4.62, 0.7, K.red);
    text(s, [{ text: t + ": ", options: { bold: true } }, { text: d }], { x: x + 1.1, y: 4.5, w: 4.65, h: 0.95, fontSize: 13.5, valign: "middle" });
  });
  card(s, 0.6, 5.7, 12.1, 1.05, K.tint);
  text(s, bullets([
    "Müşteriye giden bir kanal yok: uygulama yalnızca RM'in bilgisayarında (127.0.0.1) çalışır.",
    "Her adım (onay, ret, gerekçe, bulgu işareti, düzenleme) zamanıyla kayda geçer; düzenlenmiş profil kartta işaretlenir.",
  ], { gap: 4 }), { x: 0.85, y: 5.8, w: 11.7, h: 0.9, fontSize: 13 });
  notes(s, "Öykü", "0:30", "RM'in karar verdiği altı nokta var. Hazırlık sayfasında soruları yanıtlar, çelişkileri çözer, isterse ajanı çalıştırır, sonra önerileri onaylar. Metin yalnızca onaylanan ürünlerle yazılır; RM blokları düzenler ve kartı alır. İki kilit var: çözülmemiş çelişkiyle onay yok, açık bir kural bulgusuyla kart yok. Müşteriye giden bir kanal yok ve her adım zamanıyla kayda geçer.");

  // ===== 9. Demo =====
  pres.addSection({ title: "Demo" });
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Demo" });
  s.addText("Canlı demo: P02, veriden görüşme metnine", { placeholder: "title" });
  const hD = shot(s, "dashboard.png", 0.6, 1.35, 7.7, 1584 / 905);
  caption(s, "P02 hazırlık sayfası: profil, AI'ın bulduğu sorular, piyasa notu, onay çubuğu", 0.6, 1.35 + hD + 0.08, 7.7);
  const demo = [
    ["0:00", "Hazırlık sayfası", "profil, \"Sorulacak\" kartları, K ile kanıt"],
    ["0:30", "Nasıl seçildi?", "1.444 → 306 aday; döviz kısıtı 15 ürünü eler"],
    ["1:00", "Fon kartı", "puan parçaları, geçtiği kurallar, alternatif"],
    ["1:20", "Ajan", "ajanın ve motorun ilk 3'ü yan yana"],
    ["1:50", "Onay ve metin", "beyaz alan müşteri için, sarı kutular RM için"],
    ["2:30", "Koşul değişir", "döviz kısıtı gerekçeyle kaldırılır, liste değişir"],
  ];
  demo.forEach(([t, h, d], i) => {
    const y = 1.35 + i * 0.86;
    card(s, 8.65, y, 4.05, 0.76, i === 4 ? K.orangeTint : K.tint);
    text(s, t, { x: 8.8, y, w: 0.65, h: 0.76, fontSize: 12, bold: true, color: K.code, valign: "middle" });
    text(s, h, { x: 9.5, y: y + 0.07, w: 3.1, h: 0.3, fontSize: 13.5, bold: true });
    text(s, d, { x: 9.5, y: y + 0.38, w: 3.1, h: 0.33, fontSize: 11, color: K.muted });
  });
  text(s, "Yedek: kısa demo videosu (docs/demo/agent007-demo-P01-P03.mp4)", { x: 8.65, y: 6.55, w: 4.05, h: 0.3, fontSize: 10, color: K.muted, italic: true });
  notes(s, "Ardahan ekranı kullanır, Öykü anlatır", "3:00", "Önceden hazırlanmış P02 çalıştırması açık olmalı (ajan ve metin kayıtlı, anında gelir). 0:00 Hazırlık sayfası: profil, AI'ın bulduğu iki soru, piyasa notunda bir K'ya tıkla (kaynak, tarih, alınma zamanı). 0:30 'Bu öneriler nasıl seçildi?': 1.444 seçenek, 1.138 elendi, döviz kısıtı 15; 'Elenenleri gör'. 1:00 EIL fon kartı: puan parçaları, geçtiği kurallar, en yakın alternatif. 1:20 Ajan: beş adım, ajanın ilk 3'ü ve motorun ilk 3'ü yan yana, bir bulguyu onayla. 1:50 'Onayla ve metni hazırla': görüşme metni, beyaz ve sarı alanlar, bir bloğu düzenle, Sunum görünümü. 2:30 Koşul değişikliği: döviz kısıtını gerekçeyle kaldır; sıralama yeniden hesaplanır ve döviz fonları geri gelir. Uygulama açılmazsa kısa demo videosunu oynat.");

  // ===== 10. Test =====
  pres.addSection({ title: "Sonuçlar" });
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Sonuçlar" });
  s.addText("Kesin kurallarda hedef %100: 34 senaryo, 0 ihlal", { placeholder: "title" });
  [["%100", "kural kontrolleri", "15 kontrol, 39 çalıştırma"], ["0", "kısıt ihlali", "37 / 37 öneri listesi"], ["24 / 25", "doğrulayıcı", "1 metin şablona düştü"], ["5 / 5", "tekrar tutarlılığı", "aynı girdi, aynı sonuç"]].forEach(([big, l, sub], i) => {
    const x = 0.6 + i * 3.08;
    card(s, x, 1.35, 2.85, 1.45);
    text(s, big, { x: x + 0.2, y: 1.42, w: 2.5, h: 0.7, fontSize: 34, bold: true, color: K.green, valign: "middle" });
    text(s, l, { x: x + 0.2, y: 2.1, w: 2.5, h: 0.3, fontSize: 14, bold: true });
    text(s, sub, { x: x + 0.2, y: 2.42, w: 2.5, h: 0.3, fontSize: 11.5, color: K.muted });
  });
  card(s, 0.6, 3.0, 5.9, 3.8);
  text(s, "Dört test katmanı", { x: 0.8, y: 3.1, w: 5.5, h: 0.4, fontSize: 15, bold: true });
  text(s, bullets([
    [{ text: "Birim ve sözleşme: ", options: { bold: true } }, { text: "3.082 pytest, 458 web testi; ağ yok, sahte model" }],
    [{ text: "Senaryo paketi: ", options: { bold: true } }, { text: "34 senaryo, 39 çalıştırma, dondurulmuş veri; persona ve kısıt değişikliği, erişilemeyen kaynak, hatalı veri, 13 eski hata" }],
    [{ text: "Ajan değerlendirmesi: ", options: { bold: true } }, { text: "8 karar, kör A/B hakemi" }],
    [{ text: "Canlı kontrol: ", options: { bold: true } }, { text: "ekran incelemesi, RM işlem kaydından geri bildirim raporu" }],
  ], { gap: 6 }), { x: 0.8, y: 3.55, w: 5.5, h: 2.4, fontSize: 12.5 });
  text(s, "Neden bu göstergeler? Brief'in kesin kuralları (kısıt, uydurma veri, kaynak, yasak ifade) için tek ihlal bile kabul edilmez. Metin kalitesini LLM hakemi puanlar: yalnızca yön göstergesi (%50 / %50 / %58).",
    { x: 0.8, y: 5.95, w: 5.5, h: 0.8, fontSize: 11, color: K.muted });
  card(s, 6.8, 3.0, 5.9, 3.8, K.aiTint);
  text(s, "Ajan, motordan daha iyi mi?", { x: 7.0, y: 3.1, w: 5.5, h: 0.4, fontSize: 15, bold: true, color: K.ai });
  [["8 / 8", "karar kod denetiminden geçti; yedeğe düşme 0"], ["21 / 24", "öneri, model yeniden çağrılınca korundu (5 / 8 karar aynı)"], ["4 / 5", "iki bağımsız hakem (Claude, Gemini) aynı kazananı seçti"]].forEach(([big, d], i) => {
    const y = 3.6 + i * 0.72;
    text(s, big, { x: 7.0, y, w: 1.55, h: 0.6, fontSize: 20, bold: true, color: K.ai, valign: "middle" });
    text(s, d, { x: 8.6, y, w: 3.95, h: 0.6, fontSize: 12.5, valign: "middle" });
  });
  text(s, "Kör A/B, farklı 5 soru: Haiku ajan 3, motor 1, eşit 1; Gemini ajan 4, motor 1. Az soru ve iki hakem de dil modeli: RM motorun listesini her zaman görür, ajan isteğe bağlıdır.",
    { x: 7.0, y: 5.85, w: 5.5, h: 0.85, fontSize: 12, color: K.muted });
  notes(s, "Ardahan", "0:45", "Dört katmanda test ettik. Brief'in kesin kuralları için hedefimiz %100: 34 senaryo ve 39 çalıştırmada kural kontrolleri %100, kısıt ihlali 0, aynı girdi 5'te 5 aynı sonucu verdi. Metin kalitesini bir dil modeli hakemi puanlıyor; bunu yalnızca yön göstergesi olarak okuyoruz. Ajan için dürüst olalım: 8 kararın hepsi denetimden geçti. Kör A/B'de iki farklı firmanın modelini hakem yaptık; 5 sorunun 4'ünde aynı kazananı seçtiler ve ajan çoğunlukla kazandı. Ama soru sayısı az ve hakemler de dil modeli; bu yüzden RM iki listeyi de görüyor ve ajan isteğe bağlı.");

  // ===== 11. Hata analizi =====
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Sonuçlar" });
  s.addText("Bulduğumuz hatalar ve iyileştirmeler", { placeholder: "title" });
  const cases = [
    ["Kurallar %100, ama herkes aynı öneriyi aldı", [
      ["Gördük", "5 personanın 4'üne yalnızca SPK risk 1 nakit benzeri fon önerildi."],
      ["Neden", "Geçmiş getiri baskındı; risk bütçesini ölçen bir ölçüt yoktu."],
      ["Düzeltme", "Risk uyumu bandı, varlık sınıfı, sınıf başına en çok 1 ürün."],
      ["Sonuç", "5 personada 5 farklı set; kurallar hâlâ %100."]]],
    ["Profil kendisiyle çelişebiliyordu", [
      ["Gördük", "\"Muhafazakâr\" ama büyüme önceliği; ev peşinatı ama likidite \"Düşük\"."],
      ["Nasıl", "5 personaya bilerek çelişki yerleştirip canlı kontrol yaptık."],
      ["Düzeltme", "8 sabit kural, alıntılı AI kontrolü, onaydan önce RM gerekçesi."],
      ["Sonuç", "Sabit kurallar 0 / 5, AI 5 / 5; P01, P03, P05'te yanlış alarm yok."]]],
  ];
  cases.forEach(([t, rows], i) => {
    const x = 0.6 + i * 6.2;
    card(s, x, 1.35, 5.9, 3.95);
    text(s, t, { x: x + 0.25, y: 1.45, w: 5.4, h: 0.55, fontSize: 16, bold: true, valign: "middle" });
    rows.forEach(([k, v], j) => {
      const y = 2.1 + j * 0.78;
      const col = j === 3 ? K.green : j === 2 ? K.orange : K.code;
      s.addShape(pres.ShapeType.rect, { x: x + 0.25, y: y + 0.05, w: 0.07, h: 0.6, fill: { color: col }, line: { type: "none" } });
      text(s, k, { x: x + 0.45, y, w: 1.15, h: 0.7, fontSize: 12.5, bold: true, color: col, valign: "middle" });
      text(s, v, { x: x + 1.6, y, w: 4.1, h: 0.7, fontSize: 12.5, valign: "middle" });
    });
  });
  card(s, 0.6, 5.45, 12.1, 0.62, K.codeTint);
  circleIcon(s, I.FaBolt, 0.75, 5.5, 0.5, K.code);
  text(s, [{ text: "Hız: ", options: { bold: true } }, { text: "cProfile bir sorgunun her çağrıda ~30.000 satır taradığını gösterdi; varlığa göre dizin: müşteri başına motor 6,2 → 1,4 sn, sunucu açılışı 8,7 → 2,3 sn, ilk 3 aynı." }],
    { x: 1.4, y: 5.45, w: 11.2, h: 0.62, fontSize: 12.5, valign: "middle" });
  card(s, 0.6, 6.18, 12.1, 0.62, K.orangeTint);
  circleIcon(s, I.FaLightbulb, 0.75, 6.24, 0.5, K.orange);
  text(s, [{ text: "Öğrenim: ", options: { bold: true } }, { text: "\"kurallar %100\" yeterli değil. Çıktılar arası karşılaştırma ve canlı kontrol gerekir. Tüm liste: docs/found-and-fixed.md (22 kayıt)." }],
    { x: 1.4, y: 6.18, w: 11.2, h: 0.62, fontSize: 12.5, valign: "middle" });
  notes(s, "Ardahan", "0:40", "İki hata analizi. Birincisi: tüm kurallar geçerken 5 müşterinin 4'üne yalnızca risk 1 nakit benzeri fonlar önerildi; çünkü geçmiş getiri baskındı. Risk uyumu bandı ve varlık sınıfı kuralı ekledik; şimdi 5 profilde 5 farklı set var. İkincisi: profil kendisiyle çelişebiliyordu. 5 personaya bilerek çelişki koyduk: sabit kurallar hiçbirini bulamadı, AI kontrolü 5'ini de buldu. Şimdi RM gerekçe yazmadan onay veremiyor. Hız sorununu da profil çıkararak bulduk ve çözdük.");

  // ===== 12. Sınırlar, gelecek, kapanış =====
  s = pres.addSlide({ masterName: "KOYU", sectionTitle: "Sonuçlar" });
  s.addText("Karar desteği, yatırım tavsiyesi değil", { placeholder: "title" });
  [[I.FaExclamationTriangle, K.red, "Sınırlarımız", [
      "Hazırlık süresi kazancı ölçülmedi [VARSAYIM]",
      "Ağırlıklar, risk ve dağılım bantları bizim seçimimiz [VARSAYIM]",
      "LLM hakemi yalnızca yön gösterir",
      "Personalar sentetik; tam değerlendirme 14.10 dondurulmuş verisinde",
    ]],
   [I.FaRoad, K.green, "Sonraki adımlar", [
      "Banka sistemlerinden gerçek portföy ve ürün rafı",
      "RM işlem kaydından otomatik değerlendirme döngüsü",
      "KAP için lisanslı veri; kimlik doğrulama, denetim deposu",
      "Görüşme sonrası takip adımı",
    ]]].forEach(([ic, col, t, items], i) => {
    const x = 0.6 + i * 6.2;
    s.addShape(pres.ShapeType.roundRect, { x, y: 1.55, w: 5.9, h: 3.4, rectRadius: 0.1, fill: { color: "2A3358" }, line: { type: "none" } });
    circleIcon(s, ic, x + 0.3, 1.75, 0.6, col);
    text(s, t, { x: x + 1.1, y: 1.75, w: 4.5, h: 0.6, fontSize: 19, bold: true, color: K.white, valign: "middle" });
    text(s, bullets(items, { gap: 8 }), { x: x + 0.3, y: 2.6, w: 5.35, h: 2.45, fontSize: 14, color: K.navyTint });
  });
  [["Kod karar verir", "kısıt ihlali 0, aynı girdi aynı sonuç"], ["Her sayı kanıtlı", "kaynak, tarih, alınma zamanı"], ["RM kontrolde", "6 karar noktası, 2 kilit, kanal yok"]].forEach(([t, d], i) => {
    const x = 0.6 + i * 4.15;
    text(s, t, { x, y: 5.4, w: 3.9, h: 0.4, fontSize: 17, bold: true, color: K.orange });
    text(s, d, { x, y: 5.8, w: 3.9, h: 0.35, fontSize: 13, color: K.navyTint });
  });
  text(s, "Teşekkürler. Jüri Challenge koşullarınızı bekliyoruz.", { x: 0.6, y: 6.45, w: 12.1, h: 0.45, fontSize: 18, bold: true, color: K.white });
  notes(s, "Öykü", "0:30", "Sınırlarımızı açıkça söylüyoruz: hazırlık süresi kazancını ölçmedik, ağırlıklar ve bantlar bizim seçimimiz, hakem bir dil modeli ve personalar sentetik. Sonraki adımlar: bankanın gerçek portföy verisi, RM kayıtlarından otomatik değerlendirme döngüsü ve lisanslı KAP verisi. Özetle: kararı kod verir, her sayı kanıtlıdır, son söz RM'indir. Teşekkürler; Jüri Challenge koşullarınızı canlı olarak deneyebiliriz.");

  // ===== Ek =====
  pres.addSection({ title: "Ek" });
  s = pres.addSlide({ masterName: "KOYU", sectionTitle: "Ek" });
  s.addText("Ek: soru-cevap için", { placeholder: "title" });
  text(s, bullets([
    "E1 · Jüri Challenge: koşul değişince ne olur?",
    "E2 · Mimari ve veri akışı",
    "E3 · 8 ölçüt, ağırlıklar ve cezalar",
    "E4 · P02 örneği: ilk 3 nasıl çıktı?",
    "E5 · Bir önerinin kanıt kaydı",
    "E6 · Modeller, maliyet ve yedekler",
    "E7 · Ajan değerlendirmesi ve ikinci hakem",
    "E8 · Diğer bulgular ve düzeltmeler",
    "E9 · Neden kural ve şeffaf puan?",
    "E10 · Dağılım ve geri bildirim döngüsü",
  ], { gap: 6 }), { x: 0.6, y: 1.6, w: 8, h: 5.2, fontSize: 17, color: K.navyTint });
  s.addImage({ path: path.join(ROOT, "web", "public", "logo-mark.png"), x: 9.3, y: 2.6, w: 3.0, h: 3.0 / (187 / 112) });

  // E1 Jüri Challenge
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Ek" });
  s.addText("E1 · Jüri Challenge: koşul değişince ne olur?", { placeholder: "title" });
  table(s, [
    [hdrCell("Değişiklik"), hdrCell("Sistemin davranışı")],
    ["Risk profili değişir (P03 Agresif → Muhafazakâr)", "Tavan 2'ye iner; öneriler, dağılım ve metin yeniden; kartta \"Düzenlenmiş profil ile hazırlandı\""],
    ["Yeni açık kısıt (\"döviz istemiyor\")", "Katı kural: ilgili ürünler elenir, gerekçe \"Elenenler\" listesinde"],
    ["Tanınmayan kısıt veya risk profili metni", "Sıralama durur, RM'e yanıt seçenekli soru açılır; tahmin yok"],
    ["Kısıtı RM kaldırır (P02 döviz)", "Yalnızca RM'in gerekçesiyle; varsayım ve kayıt olarak görünür"],
    ["Profil çelişkisi (yaş 62, notta \"45 yaşında\")", "Sabit kural veya AI bulgusu; RM gerekçesi olmadan onay yok"],
    ["Kaynak erişilemez veya bot engeli", "Engel aşılmaz; önceki snapshot ve tarihi kullanılır, not düşülür"],
    ["Eksik veya hatalı veri", "Bayrak, düşük güven, \"eksik veri\" notu; aralık dışı değer kullanılmaz"],
    ["Ajan hata verir veya 90 sn'yi aşar", "1 düzeltme hakkı, sonra motorun ilk 3'ü"],
    ["Mevcut portföy dağılımı girilir", "Portföy açığı ölçütü devreye girer; çalışmış ajan yeniden çalışır"],
  ], { x: 0.6, y: 1.3, w: 12.1, colW: [4.6, 7.5], fontSize: 12.5, rowH: 0.52 });

  // E2 Mimari
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Ek" });
  s.addText("E2 · Mimari ve veri akışı", { placeholder: "title" });
  const box = (x, y, w, h, t, d, fill, col) => {
    card(s, x, y, w, h, fill, col);
    text(s, t, { x: x + 0.15, y: y + 0.08, w: w - 0.3, h: 0.35, fontSize: 13, bold: true, color: col });
    if (d) text(s, d, { x: x + 0.15, y: y + 0.45, w: w - 0.3, h: h - 0.5, fontSize: 11, color: K.muted });
  };
  box(0.6, 1.4, 2.6, 2.6, "Kaynaklar", "TCMB EVDS\nTEFAS sayfaları\nBorsa İstanbul\nING oran sayfası\nElle girilen dosya", K.white, K.muted);
  box(3.6, 1.4, 2.8, 2.6, "Ingest (kod)", "Günlük 07:30 veya \"Veriyi yenile\" (kilit)\nSnapshot + SHA-256\nKalite bayrakları\nKanıt deposu: DuckDB + Parquet", K.codeTint, K.code);
  box(6.8, 1.4, 2.8, 2.6, "Puanlama motoru (kod)", "Eleme kuralları\nPuan, güven, istikrar\nİlk 3, dağılım, uyarılar, sorular", K.codeTint, K.code);
  box(10.0, 1.4, 2.7, 2.6, "API + web", "FastAPI, yalnızca 127.0.0.1\nReact uygulaması\nRM inceler, onaylar, düzenler", K.orangeTint, K.orange);
  arrow(s, 3.25, 2.55); arrow(s, 6.45, 2.55); arrow(s, 9.65, 2.55);
  [["Profil kontrolü", "8 kural + Claude Opus 5.5"], ["Web araştırması", "Exa; yedek Claude web araması"], ["Ajan", "Claude Sonnet 5.5 + kod denetimi"], ["Anlatıcı", "Sonnet 5.5 metin, Haiku 5.5 özet; doğrulayıcı"]].forEach(([t, d], i) => {
    box(0.6 + i * 3.05, 4.35, 2.85, 1.15, t, d, K.aiTint, K.ai);
  });
  box(0.6, 5.75, 5.9, 1.05, "Kayıtlar", "data/runs, narratives, agent, research, cards · logs/rm-actions", K.white, K.muted);
  box(6.8, 5.75, 5.9, 1.05, "Değerlendirme ve geri bildirim", "34 senaryo, ajan A/B, rmprep feedback (işlem kaydından)", K.codeTint, K.code);

  // E3 Ölçütler
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Ek" });
  s.addText("E3 · 8 ölçüt, ağırlıklar ve cezalar", { placeholder: "title" });
  table(s, [
    [hdrCell("Ölçüt"), hdrCell("Ne ölçer"), hdrCell("Ham ağırlık")],
    ["Getiri", "stopaj, ücret ve TÜFE sonrası reel getirinin adaylar içindeki sırası", "2 + 2 × risk iştahı (ufuk ≥ 3 yıl: +1)"],
    ["Risk uyumu", "risk değeri müşterinin bandında mı (bandın altındaki her seviye −0,5)", "2"],
    ["Likidite", "satış valörü (aynı gün 1,0 … 10 günden uzun 0,2)", "2 × likidite ihtiyacı"],
    ["Gelir", "ürün türünün düzenli gelire uygunluğu", "2 × gelir ihtiyacı"],
    ["Anapara", "anaparanın korunması (mevduat 1; fonda risk arttıkça azalır)", "2 × anapara koruma"],
    ["Sadelik", "ürün yapısının sadeliği", "yalnızca \"sade ürün\" önceliği varsa"],
    ["Kalite", "fon büyüklüğü ve yatırımcı sayısı (payda işlem hacmi)", "0,5"],
    ["Portföy açığı", "bugünkü dağılımın model banttan uzaklığı", "1 × kaynak katsayısı (RM girdiyse veya onayladıysa)"],
  ], { x: 0.6, y: 1.3, w: 12.1, colW: [1.8, 6.4, 3.9], fontSize: 12.5, rowH: 0.46 });
  text(s, "Cezalar en çok 0,3: anapara riski, geç erişim, döviz, bilinmeyen risk, reel kayıp, piyasa altı getiri · 0,2: eksik geçmiş · 0,1: küçük fon. Ceza = üst sınır × konunun müşteri için önemi × ürünün zayıflığı. Öncelikler eşleşen ölçüte +1 ekler; ağırlıklar toplamı 1. MiFID II ve SPK yerindeliğinde ağırlık yok: seçimimiz [VARSAYIM], istikrar testiyle ölçülür.",
    { x: 0.6, y: 5.85, w: 12.1, h: 1.0, fontSize: 12.5, color: K.muted });

  // E4 P02
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Ek" });
  s.addText("E4 · P02 örneği: ağırlıklar müşteriden gelir", { placeholder: "title" });
  text(s, "P02 ağırlıkları (Dengeli, 1–3 yıl, likidite / gelir / anapara Orta)", { x: 0.6, y: 1.35, w: 5.6, h: 0.6, fontSize: 14, bold: true });
  [["Reel getiri", 0.339], ["Risk uyumu", 0.203], ["Likidite", 0.203], ["Gelir", 0.102], ["Anapara", 0.102], ["Kalite", 0.051]].forEach(([l, v], i) => {
    const y = 2.05 + i * 0.58;
    text(s, l, { x: 0.6, y, w: 1.6, h: 0.4, fontSize: 13, valign: "middle" });
    hbar(s, 2.25, y + 0.05, 3.0, 0.3, v / 0.339, K.code);
    text(s, v.toFixed(3).replace(".", ","), { x: 2.25 + 3.0 * v / 0.339 + 0.1, y, w: 0.8, h: 0.4, fontSize: 12.5, bold: true, valign: "middle" });
  });
  text(s, "\"Erişilebilir likidite\" önceliği likiditeye +1 ekler; toplam 1'e normalleştirilir.", { x: 0.6, y: 5.6, w: 5.6, h: 0.6, fontSize: 12, color: K.muted });
  const neg = { color: K.red, bold: true };
  const pos = { color: K.green, bold: true };
  table(s, [
    [hdrCell("Seçenek"), hdrCell("Sınıf"), hdrCell("Reel 1 yıl"), hdrCell("Puan")],
    ["EIL · Astra Para Piyasası", "nakit benzeri", { text: "+%7,7", options: pos }, "0,783"],
    ["NJR · Nurol Borçlanma", "borçlanma", { text: "+%8,1", options: pos }, "0,743"],
    ["KDE · Kuveyt Türk Dengeli", "dengeli", { text: "+%9,5", options: pos }, "0,741"],
    ["ING e-Vadeli Mevduat", "nakit benzeri", { text: "+%2,1", options: pos }, "0,434"],
    ["ING Turuncu (karşılaştırma)", "nakit benzeri", { text: "−%8,3", options: neg }, "0,185"],
  ], { x: 6.5, y: 1.4, w: 6.2, colW: [2.7, 1.45, 1.1, 0.95], fontSize: 12.5, rowH: 0.48 });
  card(s, 6.5, 4.55, 6.2, 1.95);
  text(s, bullets([
    "RPP (0,775) KDE'den yüksek puan aldı, ama nakit benzeri sınıfın tek yeri EIL'de.",
    "\"Döviz maruziyetini gerekçesiz artırmama\" kısıtı 15 döviz ürününü eler; RM gerekçeyle kaldırabilir.",
    "Turuncu Hesap sıralamaya girmez; karşılaştırma tabanıdır.",
  ], { gap: 6 }), { x: 6.7, y: 4.7, w: 5.8, h: 1.75, fontSize: 12.5 });

  // E5 Kanıt kaydı
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Ek" });
  s.addText("E5 · Bir önerinin kanıt kaydı (Teslimat 6)", { placeholder: "title" });
  const chain = [
    ["Veri", "PPN için 10 kanıt satırı; her biri kaynak, değer tarihi ve alınma zamanıyla (18.10.2026, 13:27–13:41)"],
    ["Kural ve puan", "2 kuraldan geçti; 7 puan parçası, toplam 0,740; motorun ilk 3'ü PPN, OSD, AIS"],
    ["Ajan", "Claude Sonnet 5.5, istem a3, 0,073 $; AIS yerine ZBJ, gerekçeler atıflı"],
    ["Web bulguları", "PPN için 4 bulgu (fon belgeleri); RM 1'ini onayladı, 1'ini reddetti"],
    ["RM onayı", "22:53:18; seçim PPN, OSD, ZBJ (ajanın 3'ü); profil çelişkisi yok"],
    ["Metin ve kart", "istem n12, denetim bulgusu yok, 0,047 $; RM bir bloğu 22:54:03'te düzenledi; kart kaydedildi"],
  ];
  chain.forEach(([t, d], i) => {
    const y = 1.35 + i * 0.78;
    num(s, i + 1, 0.6, y + 0.12, 0.45, i === 4 ? K.orange : i === 2 || i === 3 ? K.ai : K.code);
    text(s, t, { x: 1.2, y, w: 2.0, h: 0.68, fontSize: 14, bold: true, valign: "middle" });
    text(s, d, { x: 3.2, y, w: 5.3, h: 0.68, fontSize: 12.5, valign: "middle" });
  });
  const hE5 = shot(s, "evidence.png", 8.9, 1.4, 3.8, 448 / 314);
  caption(s, "Kanıt penceresi: EIL 1 yıllık getiri %48,13, kanıt Edede971a", 8.9, 1.4 + hE5 + 0.08, 3.8);
  card(s, 0.6, 6.15, 12.1, 0.65, K.orangeTint);
  text(s, "Çalıştırma Rb5470b4f25 (P01), demo videosu çekilirken bir betikle onaylandı; gerçek kullanımda aynı adımları RM ekrandan yapar, kayıt yapısı aynıdır.",
    { x: 0.85, y: 6.15, w: 11.7, h: 0.65, fontSize: 12.5, valign: "middle" });

  // E6 Modeller ve maliyet
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Ek" });
  s.addText("E6 · Modeller, maliyet ve yedekler", { placeholder: "title" });
  table(s, [
    [hdrCell("Bileşen"), hdrCell("Model"), hdrCell("Güvence"), hdrCell("Maliyet")],
    ["Ajan ilk 3", "Claude Sonnet 5.5", "kod denetimi, 1 tekrar, sonra motorun ilk 3'ü", "karar başına ~0,05–0,10 $; günde en çok 3 $"],
    ["Web araştırması", "Exa (yedek: Claude Haiku 5.5)", "soru kontrolü: müşteri bilgisi dışarı gitmez; kaynaksız bulgu atılır", "ürün başına ~0,02 $; günde en çok 5 $"],
    ["Profil kontrolü", "Claude Opus 5.5", "bulgu iki tarafı kelimesi kelimesine alıntılar; sunucu doğrular", "profil başına ~0,015 $, sonuç kaydedilir"],
    ["Görüşme metni", "Claude Sonnet 5.5", "doğrulayıcı, 1 tekrar, sonra şablon metin", "metin başına 0,034 $, ort. 24,9 sn"],
    ["Pano özeti", "Claude Haiku 5.5", "doğrulayıcı; hata olursa düz cümle", "~0,003 $"],
    ["Değerlendirme hakemi", "Claude Haiku 5.5", "yalnızca kodun ölçemediği şeyler", "paket başına < 0,01 $"],
    ["İkinci A/B hakemi", "Gemini 3.8 Flash", "ilk hakemin sorusunun birebir aynısı", "ücretsiz katman (~0,002 $ / soru)"],
  ], { x: 0.6, y: 1.3, w: 12.1, colW: [2.1, 2.6, 4.4, 3.0], fontSize: 12.5, rowH: 0.58 });
  text(s, "Bir anahtar eksikse yalnızca ona bağlı parça kapanır; puanlama motoru her zaman çalışır. Piyasa notunu dil modeli değil kod yazar.",
    { x: 0.6, y: 6.25, w: 12.1, h: 0.5, fontSize: 13, color: K.muted });

  // E7 Ajan değerlendirmesi
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Ek" });
  s.addText("E7 · Ajan değerlendirmesi: ne ölçtük, ne öğrendik", { placeholder: "title" });
  text(s, bullets([
    [{ text: "Kurallara uyum: ", options: { bold: true } }, { text: "8 kararın 8'i kod denetiminden geçti; hiçbirinde yedeğe düşülmedi." }],
    [{ text: "Tutarlılık: ", options: { bold: true } }, { text: "kayıtlı karar aynı istek için geri gelir. Asıl test: sistemi sıfırlayıp modeli yeniden çağırdık; 8 kararın 5'i aynı, 3'ünde yalnızca bir ürün değişti (24 önerinin 21'i korundu)." }],
    [{ text: "Kör A/B hakemi: ", options: { bold: true } }, { text: "kimin seçtiğini bilmez; müşteri profilini ve iki ürün setinin olgularını görür: \"Hangisi müşteriye daha uygun ve neden?\". İlk tur: ajan 5, motor 0, eşit 1." }],
    [{ text: "Kendi hatamız: ", options: { bold: true } }, { text: "ajanın kazançlarının 3'ü P03'teydi ve motorun seçtiği IDY ile OKT ajanın aday listesinde yoktu. Aday listesi artık motorun ilk 3'üyle başlıyor; P03 yeniden: hakem motoru seçti." }],
    [{ text: "İkinci hakem: ", options: { bold: true } }, { text: "aynı soruları Gemini 3.8 Flash'a da sorduk; yalnızca ilk hakemin gördüğü metinle birebir aynı sorular. Bu tekrar bir sayım hatamızı buldu: iki senaryo aynı soruyu sormuştu ve yanıtı iki kez saymıştık." }],
  ], { gap: 8 }), { x: 0.6, y: 1.3, w: 7.3, h: 4.5, fontSize: 13 });
  table(s, [
    [hdrCell("Farklı 5 soru"), hdrCell("Ajan"), hdrCell("Motor"), hdrCell("Eşit")],
    ["Claude Haiku 5.5", "3", "1", "1"],
    ["Gemini 3.8 Flash", "4", "1", "0"],
  ], { x: 8.2, y: 1.4, w: 4.5, colW: [2.1, 0.8, 0.8, 0.8], fontSize: 13, rowH: 0.5 });
  text(s, "İki hakem 5 sorunun 4'ünde aynı kazananı seçti; P05'te Haiku \"eşit\", Gemini ajan dedi.",
    { x: 8.2, y: 3.15, w: 4.5, h: 0.9, fontSize: 12.5, color: K.muted });
  card(s, 0.6, 5.85, 12.1, 0.9, K.orangeTint);
  text(s, [{ text: "Karar: ", options: { bold: true } }, { text: "soru sayısı az ve iki hakem de dil modeli; sonuç ajanın daha iyi olduğunu kanıtlamaz. RM önce motorun önerilerini görür, ajanı isterse çalıştırır ve iki listeyi yan yana karşılaştırır." }],
    { x: 0.85, y: 5.85, w: 11.7, h: 0.9, fontSize: 13.5, valign: "middle" });

  // E8 Diğer bulgular
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Ek" });
  s.addText("E8 · Diğer bulgular ve düzeltmeler", { placeholder: "title" });
  table(s, [
    [hdrCell("Ne gördük"), hdrCell("Neden"), hdrCell("Düzeltme ve sonuç")],
    ["KORDS 1 ayda −%96", "Bültendeki önceki kapanış bölünmeye göre düzeltilmemişti", "±%10 limitini aşan hareket = bölünme; 111 payda 116 düzeltme; KORDS −%27,8"],
    ["5 yıllık pay geçmişi 15.02.2023'te kesiliyordu", "Depremden sonra borsa kapalıydı; boş günler bozuk dosya sayıldı", "Kapanışı 0 olan geçerli bülten = işlem olmayan gün; tam 5 yıl"],
    ["ING oranları eskimişti", "Elle kopyalanmıştı; 28 e-Vadeli oranı değişmişti", "ING oran sayfası adaptörü; %35,00 yerine güncel %34,50"],
    ["Stopaj ve TÜFE yokken güven 1,00 kalıyordu", "Eski bir bayrak açığı gizliyordu", "Reel getiri hesaplanamazsa güven × 0,8; eksik veri 5/7 → 7/7"],
    ["\"Garanti Portföy\" fon adı yasak ifade sayıldı", "Tarama kurucu adını da okuyordu; ücretli yeniden ölçüm ikinci biçimi buldu (\"Garanti GZP\")", "Kurucu adı ve fon kodu taramadan çıkarıldı; ölçüm 3/3; tek başına \"garanti\" hâlâ yakalanır"],
    ["A/B hakemi motoru tuhaf nedenlerle seçti", "Motorun seçtikleri ajanın aday listesinde yoktu", "Aday listesi motorun ilk 3'üyle başlar"],
  ], { x: 0.6, y: 1.3, w: 12.1, colW: [3.4, 4.0, 4.7], fontSize: 12, rowH: 0.62 });
  text(s, "Açık kalanlar: TEFAS bazı günlerde fon fiyatını ve büyüklüğünü 0 yayımlıyor (son snapshot'ta 45 fon); iki EVDS serisi henüz elle doğrulanmadı.",
    { x: 0.6, y: 5.95, w: 12.1, h: 0.6, fontSize: 12.5, color: K.muted });

  // E9 Neden bu yaklaşım
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Ek" });
  s.addText("E9 · Neden kural ve şeffaf puan?", { placeholder: "title" });
  const sel = (t) => ({ text: t, options: { bold: true, fill: { color: K.orangeTint } } });
  table(s, [
    [hdrCell("Ölçüt"), hdrCell("Kural + şeffaf puan (seçilen)"), hdrCell("ML sıralama"), hdrCell("Yalnızca LLM")],
    ["Veri ihtiyacı", sel("Etiket gerekmez"), "Geçmiş RM kararları gerekir; yok", "Etiket gerekmez"],
    ["Denetlenebilirlik", sel("Her puan parçası kanıta bağlı"), "Öznitelik önemi yaklaşık", "Gerekçe doğrulanamaz"],
    ["Kural 5 (uygunluk)", sel("Katı kural; ihlal mümkün değil"), "Yalnızca öğrenilmiş eğilim", "İstemle; ihlal mümkün"],
    ["Determinizm", sel("Aynı girdi, aynı sonuç ve run_id"), "Eğitim sürümüne bağlı", "Aynı istem, farklı çıktı"],
    ["Değişiklik", sel("Yapılandırma dosyası (decision.yaml)"), "Yeniden eğitim", "Öngörülemez etki"],
  ], { x: 0.6, y: 1.3, w: 12.1, colW: [2.4, 3.7, 3.0, 3.0], fontSize: 13.5, rowH: 0.62 });
  text(s, "Dil modelini güçlü olduğu yerde kullanıyoruz: metin yazmak, araştırmayı özetlemek, adayları nitel karşılaştırmak. RM onayları biriktiğinde ağırlıklar bir modelle ayarlanabilir; geri bildirim raporu bugün bunun için ölçüleri toplar.",
    { x: 0.6, y: 5.35, w: 12.1, h: 1.0, fontSize: 13.5, color: K.muted });

  // E10 Dağılım ve geri bildirim
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Ek" });
  s.addText("E10 · Dağılım görünümü ve geri bildirim döngüsü", { placeholder: "title" });
  const hAl = shot(s, "allocation.png", 0.6, 1.35, 5.95, 1352 / 1106);
  caption(s, "Model bant (Ata Yatırım, 28.04.2026), bugünkü dağılım, sınıfın en iyi seçeneği", 0.6, 1.35 + hAl + 0.06, 5.95);
  card(s, 6.95, 1.35, 5.75, 2.55);
  text(s, "Dağılım", { x: 7.15, y: 1.45, w: 5.3, h: 0.4, fontSize: 15, bold: true });
  text(s, bullets([
    "Risk profiline göre her varlık sınıfı için model bant; Temkinli bandı kaynakta yok, bizim çıkarımımız [VARSAYIM]",
    "Dosyada dağılım yoksa meslek tablosundan veya TCMB FİR ortalamasından tahmin; \"tahmini senaryo\" etiketi",
    "RM \"Tahmini onayla\" veya \"Düzenle\" demeden puanı etkilemez",
  ], { gap: 5 }), { x: 7.15, y: 1.9, w: 5.35, h: 1.95, fontSize: 12.5 });
  card(s, 6.95, 4.1, 5.75, 2.7, K.codeTint);
  text(s, "Geri bildirim döngüsü", { x: 7.15, y: 4.2, w: 5.3, h: 0.4, fontSize: 15, bold: true });
  text(s, bullets([
    "Her RM işlemi sürüm bilgileriyle bir JSON satırı: onay, ret, düzenleme, silme, bulgu işareti, dağılım, ajan",
    "rmprep feedback: 5 ölçü ve sabit eşiklerle öneriler (ör. sık silinen bölüm, ajan önerisinin kabul oranı)",
    "Rapor ayar değiştirmez; otomatik döngü gelecek iş",
  ], { gap: 5 }), { x: 7.15, y: 4.65, w: 5.35, h: 2.1, fontSize: 12.5 });

  await pres.writeFile({ fileName: OUT });
  console.log("wrote", OUT);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
