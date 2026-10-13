// Deliverable 7: the Turkish slide deck (pptxgenjs). Numbers come from
// docs/teslim/01, 03, 04 and 05; screenshots from scripts/deck/shots.js.
// Usage (NODE_PATH = a folder with pptxgenjs, react, react-dom, react-icons, sharp):
//   node scripts/deck/build_deck.js <out.pptx> [apply_theme.js]
const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");

const OUT = process.argv[2] || "07-sunum.pptx";
const APPLY_THEME = process.argv[3];
const IMG = path.join(__dirname, "..", "..", "docs", "teslim", "sunum", "img");

const THEME = {
  name: "ING RM Hazirlik",
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1C2340", // navy ink
    lt1: "FFFFFF",
    dk2: "475569", // slate, muted text
    lt2: "F1F3F7", // card tint
    accent1: "FF6200", // ING orange: human approval, highlights
    accent2: "34407A", // mid navy: deterministic code
    accent3: "15803D", // green: pass
    accent4: "B91C1C", // red: negative
    accent5: "FFE6D5", // light orange tint
    accent6: "DCE3F0", // light navy tint
    hlink: "2563EB",
    folHlink: "7C3AED",
  },
};
const HEX = THEME.colors;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "RM Görüşme Hazırlığı · Teslimat 7";
pres.author = "ING Agentic AI Hackathon takımı";
const C = pres.SchemeColor;

// ---------- layouts ----------
pres.defineSlideMaster({
  title: "KAPAK",
  background: { color: C.text1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.7, w: 6.4, h: 2.2, fontSize: 40, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 4.1, w: 6.4, h: 1.4, fontSize: 20, color: C.accent6, valign: "top", align: "left", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "ICERIK",
  background: { color: C.background1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.85, fontSize: 32, bold: true, color: C.text1, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { text: { text: "ING Agentic AI Hackathon · RM görüşme hazırlığı", options: { x: 0.6, y: 7.0, w: 8, h: 0.3, fontSize: 10, color: C.text2, margin: 0 } } },
  ],
  slideNumber: { x: 12.2, y: 7.0, w: 0.5, h: 0.3, fontSize: 10, color: HEX.dk2 },
});
pres.defineSlideMaster({
  title: "KOYU",
  background: { color: C.text1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.45, w: 12.1, h: 0.9, fontSize: 34, bold: true, color: C.background1, valign: "middle", align: "left", margin: 0 }, text: "" } },
  ],
});

// ---------- helpers ----------
function icon(Comp, hex = "FFFFFF") {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { color: "#" + hex, size: 256 }));
  return sharp(Buffer.from(svg)).png().toBuffer().then((b) => "image/png;base64," + b.toString("base64"));
}

function text(slide, t, o) {
  slide.addText(t, { isTextBox: true, margin: 0, valign: "top", fontSize: 14, color: C.text1, ...o });
}

function card(slide, x, y, w, h, fill = C.background2, name) {
  slide.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { type: "none" }, objectName: name });
}

function circleIcon(slide, data, x, y, d, fill) {
  slide.addShape(pres.ShapeType.ellipse, { x, y, w: d, h: d, fill: { color: fill }, line: { type: "none" } });
  const p = d * 0.24;
  slide.addImage({ data, x: x + p, y: y + p, w: d - 2 * p, h: d - 2 * p });
}

function hexBadge(slide, label, x, y, w = 0.75, h = 0.65) {
  slide.addShape(pres.ShapeType.hexagon, { x, y, w, h, fill: { color: C.accent1 }, line: { type: "none" } });
  text(slide, label, { x, y, w, h, fontSize: 16, bold: true, color: C.background1, align: "center", valign: "middle" });
}

function bullets(items, o = {}) {
  return items.map((t, i) => ({
    text: t,
    options: { bullet: true, breakLine: i < items.length - 1, paraSpaceAfter: o.gap ?? 6 },
  }));
}

function shot(slide, file, x, y, w, ratio) {
  const h = w / ratio;
  slide.addShape(pres.ShapeType.rect, { x: x - 0.03, y: y - 0.03, w: w + 0.06, h: h + 0.06, fill: { color: C.accent6 }, line: { type: "none" } });
  slide.addImage({ path: path.join(IMG, file), x, y, w, h });
  return h;
}

function hbar(slide, x, y, wMax, h, frac, fill) {
  slide.addShape(pres.ShapeType.rect, { x, y, w: Math.max(0.04, wMax * frac), h, fill: { color: fill }, line: { type: "none" } });
}

(async () => {
  const I = {};
  const names = ["FaDatabase", "FaCogs", "FaUserCheck", "FaPenNib", "FaFileSignature", "FaFingerprint", "FaQuestionCircle", "FaShieldAlt", "FaBalanceScale", "FaChartLine", "FaLayerGroup", "FaExclamationTriangle", "FaLightbulb", "FaClock", "FaSearch", "FaRoad"];
  for (const n of names) I[n] = await icon(fa[n]);

  // ===== 1. Kapak =====
  pres.addSection({ title: "Giriş" });
  let s = pres.addSlide({ masterName: "KAPAK", sectionTitle: "Giriş" });
  s.addText("Görüşme hazırlığı: kanıta dayalı karar desteği", { placeholder: "title" });
  s.addText("Private Banking RM'leri için yatırım karar destek prototipi", { placeholder: "body" });
  text(s, "ING Agentic AI Hackathon · Ekim 2026", { x: 0.6, y: 5.9, w: 6.4, h: 0.4, fontSize: 14, color: C.accent1, bold: true });
  shot(s, "dashboard-crop.png", 7.5, 1.55, 5.25, 2880 / 1520);
  text(s, "Gerçek uygulama, P02 panosu (veri: 10.10.2026)", { x: 7.5, y: 4.45, w: 5.25, h: 0.3, fontSize: 11, color: C.accent6 });

  // ===== 2. Problem =====
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Giriş" });
  s.addText("RM'in hazırlığı yavaş, dağınık ve kayıtsız", { placeholder: "title" });
  text(s, "RM her görüşmeden önce yüzlerce ürünü dağınık kaynaklardan elle karşılaştırıyor. İş yavaş, müşteriye uyarlanmıyor, kısıt kaçabiliyor ve önerinin hangi veriye dayandığı sonradan gösterilemiyor.",
    { x: 0.6, y: 1.4, w: 12.1, h: 1.0, fontSize: 18, color: C.text2 });
  const stats2 = [
    ["816", C.accent1, "P01 için seçenek", "Kurallar 675'ini eler: risk tavanı, alıma kapalı, kısa geçmiş. Kalan 141 seçeneği elle sıralamak bir hazırlığa sığmaz."],
    ["−%8,3", C.accent4, "ING Turuncu Hesap, reel getiri", "%23 faiz, stopaj ve yıllık TÜFE (%29,73) sonrası. Aynı gün para piyasası fonları reel +%7,4."],
    ["≈ 30 sn", C.accent2, "analiz ve görüşme metni", "Karar ≈ 1 sn, metin ortalama 27 sn. Bugünkü hazırlık görüşme başına ~60 dk [VARSAYIM]."],
  ];
  stats2.forEach(([big, col, label, desc], i) => {
    const x = 0.6 + i * 4.15;
    card(s, x, 2.6, 3.85, 3.0);
    text(s, big, { x: x + 0.35, y: 2.8, w: 3.2, h: 1.0, fontSize: 54, bold: true, color: col, valign: "middle" });
    text(s, label, { x: x + 0.35, y: 3.85, w: 3.2, h: 0.4, fontSize: 16, bold: true });
    text(s, desc, { x: x + 0.35, y: 4.3, w: 3.2, h: 1.2, fontSize: 14, color: C.text2 });
  });
  card(s, 0.6, 5.85, 12.1, 0.95, C.accent5);
  circleIcon(s, I.FaRoad, 0.85, 6.0, 0.65, C.accent1);
  text(s, [
    { text: "Kapsam: ", options: { bold: true } },
    { text: "görüşme öncesi hazırlık. Çözüm önerir, gerekçelendirir, belirsizliği gösterir ve teyit sorularını üretir. Kararı ve müşteri iletişimini RM yapar." },
  ], { x: 1.7, y: 5.95, w: 10.8, h: 0.75, fontSize: 15, valign: "middle" });

  // ===== 3. Çözüm akışı =====
  pres.addSection({ title: "Çözüm" });
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Çözüm" });
  s.addText("Kararı kod verir, son sözü RM söyler", { placeholder: "title" });
  const flow = [
    ["Veri", I.FaDatabase, C.accent2, C.background2, "TEFAS, TCMB EVDS, ING oranları, stopaj, TÜFE. Anlık görüntü ve kalite bayrakları."],
    ["Karar motoru", I.FaCogs, C.accent2, C.background2, "Katı kurallar, şeffaf puan, önerilen ilk 3, dağılım bantları. Deterministik."],
    ["RM onayı", I.FaUserCheck, C.accent1, C.accent5, "Soruları yanıtlar, \"Teyit edin\" maddelerini kontrol eder, seçimi onaylar."],
    ["Görüşme metni", I.FaPenNib, C.text2, C.background2, "Claude Sonnet 5.5 yazar. Kod her sayıyı ve ürün adını doğrular."],
    ["RM metin onayı", I.FaFileSignature, C.accent1, C.accent5, "Blokları düzenler ve onaylar. Müşteriye otomatik iletim yok."],
  ];
  flow.forEach(([title, ic, circ, fill, desc], i) => {
    const x = 0.6 + i * 2.5;
    card(s, x, 1.55, 2.1, 3.15, fill);
    circleIcon(s, ic, x + 0.25, 1.8, 0.7, circ);
    text(s, title, { x: x + 0.25, y: 2.65, w: 1.7, h: 0.45, fontSize: 17, bold: true });
    text(s, desc, { x: x + 0.25, y: 3.15, w: 1.7, h: 1.5, fontSize: 14, color: C.text2 });
    if (i < flow.length - 1)
      s.addShape(pres.ShapeType.rightArrow, { x: x + 2.15, y: 2.95, w: 0.3, h: 0.35, fill: { color: C.accent6 }, line: { type: "none" } });
  });
  card(s, 0.6, 4.95, 12.1, 1.2, C.background2);
  circleIcon(s, I.FaFingerprint, 0.85, 5.2, 0.7, C.accent2);
  text(s, [
    { text: "Kanıt kaydı. ", options: { bold: true } },
    { text: "Her sayı kaynak, tarih ve kanıt kimliğiyle görünür. Kayıt; çalıştırma kimliği, yapılandırma özeti, RM kararı ve iki onay zamanını (Türkiye saati) tutar." },
  ], { x: 1.8, y: 5.05, w: 10.7, h: 1.0, fontSize: 15, valign: "middle" });
  [["Deterministik kod", C.accent2], ["LLM (yalnızca dil)", C.text2], ["İnsan onayı", C.accent1]].forEach(([l, col], i) => {
    const x = 0.6 + i * 2.6;
    s.addShape(pres.ShapeType.rect, { x, y: 6.45, w: 0.22, h: 0.22, fill: { color: col }, line: { type: "none" } });
    text(s, l, { x: x + 0.32, y: 6.4, w: 2.2, h: 0.32, fontSize: 12, color: C.text2, valign: "middle" });
  });

  // ===== 4. Karar mantığı =====
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Çözüm" });
  s.addText("Önce katı kurallar, sonra şeffaf puan", { placeholder: "title" });
  text(s, "816 seçenekten kaç tanesi kalıyor?", { x: 0.6, y: 1.4, w: 6.0, h: 0.4, fontSize: 16, bold: true });
  const elim = [["P01", "Muhafazakâr", 141], ["P02", "Dengeli", 307], ["P03", "Agresif", 627], ["P04", "Dengeli", 313], ["P05", "Temkinli", 179]];
  const BX = 2.45, BW = 4.0;
  elim.forEach(([id, prof, kept], i) => {
    const y = 1.95 + i * 0.62;
    text(s, [{ text: id + " ", options: { bold: true } }, { text: prof, options: { color: C.text2 } }], { x: 0.6, y, w: 1.8, h: 0.42, valign: "middle" });
    hbar(s, BX, y, BW, 0.42, 1, C.accent6);
    hbar(s, BX, y, BW, 0.42, kept / 816, C.accent2);
    text(s, String(kept), { x: BX + 0.08, y, w: 0.6, h: 0.42, fontSize: 14, bold: true, color: C.background1, valign: "middle" });
    text(s, (816 - kept) + " elendi", { x: BX + BW - 1.25, y, w: 1.17, h: 0.42, fontSize: 13, color: C.text2, align: "right", valign: "middle" });
  });
  [["puanlanan", C.accent2], ["elenen (gerekçe ve kanıt kimliğiyle)", C.accent6]].forEach(([l, col], i) => {
    const x = 0.6 + i * 1.9;
    s.addShape(pres.ShapeType.rect, { x, y: 5.15, w: 0.2, h: 0.2, fill: { color: col }, line: { type: "none" } });
    text(s, l, { x: x + 0.28, y: 5.1, w: i ? 3.6 : 1.5, h: 0.3, fontSize: 12, color: C.text2, valign: "middle" });
  });
  text(s, "Evren: 814 fon ve 2 ING mevduatı. Bir fon birden çok kurala takılabilir; her gerekçe \"Elenenler\" listesinde görünür.",
    { x: 0.6, y: 5.6, w: 6.0, h: 0.9, fontSize: 13, color: C.text2 });
  card(s, 7.0, 1.4, 5.7, 2.6);
  circleIcon(s, I.FaShieldAlt, 7.25, 1.6, 0.55, C.accent2);
  text(s, "Katı kurallar (sırayla)", { x: 7.95, y: 1.6, w: 4.5, h: 0.55, fontSize: 17, bold: true, valign: "middle" });
  text(s, bullets([
    "Alıma kapalı veya işlem görmüyor: 189 fon",
    "Risk tavanı: SPK risk değeri tavanın üstünde",
    "Açık kısıt: P02 döviz 14 fon, P05 valör > 3 gün 2 fon",
    "Kısa geçmiş: yalnızca 1 aylık getiri var",
  ]), { x: 7.3, y: 2.3, w: 5.2, h: 1.6, fontSize: 14 });
  card(s, 7.0, 4.2, 5.7, 2.55);
  circleIcon(s, I.FaBalanceScale, 7.25, 4.4, 0.55, C.accent2);
  text(s, "Puan = Σ ağırlık × kriter − Σ ceza", { x: 7.95, y: 4.4, w: 4.6, h: 0.55, fontSize: 17, bold: true, valign: "middle" });
  text(s, bullets([
    "Getiri: stopaj ve TÜFE sonrası reel getiri",
    "Risk uyumu, likidite, gelir, anapara, kalite",
    "Ağırlıklar müşterinin seviyelerinden gelir",
    "Dengeli / Agresif: sınıf başına en çok 1 öneri",
  ]), { x: 7.3, y: 5.1, w: 5.2, h: 1.6, fontSize: 14 });

  // ===== 5. Belirsizlik =====
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Çözüm" });
  s.addText("Belirsizlik gizlenmez: tahmin yerine soru", { placeholder: "title" });
  const unc = [
    [I.FaChartLine, "Güven (0–1)", "Seçeneğin kullandığı en zayıf veri satırı × tahmin katsayıları. P01: 141 seçeneğin 102'si 0,90; risk değeri tahmin edilen 27 seçenek 0,63."],
    [I.FaLayerGroup, "İstikrar", "Ağırlıklar ve cezalar 30 kez ±%20 değişir. Ölçü: seçeneğin ilk 20'de kalma oranı. İlk 3'te 0,5'in altı bir uyarı verir."],
    [I.FaQuestionCircle, "Tahmin yerine soru", "Risk profili veya kısıt tanınmazsa sıralama durur (needs_rm_input). Diğer alanlarda güvenli düzey ve \"Teyit edin\" sorusu."],
    [I.FaExclamationTriangle, "Eksik risk değeri (D21)", "Aynı varlık sınıfındaki bilinen değerlerin üst çeyreği. Altın fonu KZL: eski tahmin 1–2, yeni tahmin 6; Muhafazakâr listeden çıktı."],
  ];
  unc.forEach(([ic, title, body], i) => {
    const x = 0.6 + (i % 2) * 6.2, y = 1.45 + Math.floor(i / 2) * 2.5;
    card(s, x, y, 5.9, 2.3);
    circleIcon(s, ic, x + 0.3, y + 0.3, 0.6, i === 2 ? C.accent1 : C.accent2);
    text(s, title, { x: x + 1.1, y: y + 0.3, w: 4.5, h: 0.6, fontSize: 18, bold: true, valign: "middle" });
    text(s, body, { x: x + 0.3, y: y + 1.05, w: 5.3, h: 1.15, fontSize: 14, color: C.text2 });
  });
  text(s, "Varsayımlar ekranda ve kayıtta: geçmiş getiri bir tahmin değildir · TÜFE %29,73 · 100.000–249.999 TL dilimi · risk bantları [VARSAYIM]",
    { x: 0.6, y: 6.45, w: 12.1, h: 0.45, fontSize: 12, color: C.text2 });

  // ===== 6. LLM ve insan =====
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Çözüm" });
  s.addText("LLM yalnızca yazar, kod denetler, RM onaylar", { placeholder: "title" });
  text(s, "Görüşme metni nasıl üretilir?", { x: 0.6, y: 1.35, w: 6.2, h: 0.4, fontSize: 16, bold: true });
  const pipe = [
    ["Olgu paketi (kod)", "Onaylı seçim, kanıt kimlikli sayılar, varsayımlar. Elenen ürün ve RM'e özel not girmez."],
    ["Metin (Claude Sonnet 5.5)", "Yapılandırılmış JSON. Her cümle seçenek ve kanıt kimliği taşır."],
    ["Doğrulayıcı (kod)", "Olgu dışı sayı, izinsiz ürün adı, yasak ifade, kaynaksız cümle: ret."],
    ["Hata yolu", "Bulgularla 1 tekrar. Yine hata olursa şablon metin ve bir uyarı bandı."],
  ];
  pipe.forEach(([t, d], i) => {
    const y = 1.85 + i * 0.9;
    s.addShape(pres.ShapeType.ellipse, { x: 0.6, y: y + 0.05, w: 0.5, h: 0.5, fill: { color: i === 1 ? C.text2 : C.accent2 }, line: { type: "none" } });
    text(s, String(i + 1), { x: 0.6, y: y + 0.05, w: 0.5, h: 0.5, fontSize: 16, bold: true, color: C.background1, align: "center", valign: "middle" });
    text(s, t, { x: 1.3, y, w: 5.4, h: 0.32, fontSize: 15, bold: true });
    text(s, d, { x: 1.3, y: y + 0.32, w: 5.4, h: 0.55, fontSize: 13, color: C.text2 });
  });
  text(s, "İnsan onay noktaları", { x: 7.2, y: 1.35, w: 5.5, h: 0.4, fontSize: 16, bold: true });
  [["İ1", "Soruları yanıtlar, \"Teyit edin\" maddelerini kontrol eder."],
   ["İ2", "Önerilen ilk 3'ü onaylar veya not yazıp reddeder. Zaman kaydedilir."],
   ["İ3", "Metni blok blok düzenler ve onaylar. Engelleyici bulgu onayı durdurur."]].forEach(([b, d], i) => {
    const y = 1.85 + i * 0.95;
    hexBadge(s, b, 7.2, y);
    text(s, d, { x: 8.15, y, w: 4.55, h: 0.75, fontSize: 14, valign: "middle" });
  });
  text(s, "Çalışma anında ajan döngüsü yok: her metin tek çağrıdır (en çok 1 tekrar). Maliyet, süre ve davranış öngörülebilir.",
    { x: 7.2, y: 4.75, w: 5.5, h: 0.75, fontSize: 13, color: C.text2, italic: true });
  [["0,046 $", "yeni metin başına"], ["27 sn", "ortalama metin süresi"], ["25 / 25", "LLM metni doğrulayıcıdan geçti"], ["0", "yasak ifade (\"garanti\" vb.)"]].forEach(([big, l], i) => {
    const x = 0.6 + i * 3.08;
    card(s, x, 5.65, 2.85, 1.15);
    text(s, big, { x: x + 0.25, y: 5.72, w: 2.4, h: 0.6, fontSize: 28, bold: true, color: i >= 2 ? C.accent3 : C.text1, valign: "middle" });
    text(s, l, { x: x + 0.25, y: 6.32, w: 2.45, h: 0.4, fontSize: 12, color: C.text2 });
  });

  // ===== 7. Demo =====
  pres.addSection({ title: "Demo" });
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Demo" });
  s.addText("Canlı demo: P02 ve P01", { placeholder: "title" });
  const hDemo = shot(s, "dashboard-crop.png", 0.6, 1.45, 7.9, 2880 / 1520);
  text(s, "P02 panosu: önerilen ilk 3, mevduatla karşılaştırma, \"Teyit edin\" ve onay çubuğu", { x: 0.6, y: 1.45 + hDemo + 0.12, w: 7.9, h: 0.35, fontSize: 11, color: C.text2 });
  text(s, "Demoda bakılacaklar", { x: 8.9, y: 1.4, w: 3.8, h: 0.45, fontSize: 17, bold: true });
  [["P02: döviz kısıtı", "14 döviz fonu gerekçeyle elenir."],
   ["Öneriler", "Reel getiri, risk, erişim; \"K\" ile kanıt."],
   ["Dağılım", "Model bantlar ve sınıfın en iyi seçeneği."],
   ["RM onayı", "Görüşme metni, blok düzenleme, metin onayı."],
   ["P01: Muhafazakâr", "675 eleme; altın / döviz için uygun fon yok."]].forEach(([t, d], i) => {
    const y = 1.95 + i * 0.92;
    s.addShape(pres.ShapeType.ellipse, { x: 8.9, y: y + 0.02, w: 0.42, h: 0.42, fill: { color: i === 3 ? C.accent1 : C.accent2 }, line: { type: "none" } });
    text(s, String(i + 1), { x: 8.9, y: y + 0.02, w: 0.42, h: 0.42, fontSize: 14, bold: true, color: C.background1, align: "center", valign: "middle" });
    text(s, t, { x: 9.5, y, w: 3.2, h: 0.32, fontSize: 15, bold: true });
    text(s, d, { x: 9.5, y: y + 0.32, w: 3.2, h: 0.55, fontSize: 13, color: C.text2 });
  });

  // ===== 8. Test sonuçları =====
  pres.addSection({ title: "Sonuçlar" });
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Sonuçlar" });
  s.addText("34 senaryo: kurallar %100, kısıt ihlali 0", { placeholder: "title" });
  [["%100", "kural kontrolleri", "218 geçti, 0 kaldı"], ["0", "kısıt ihlali", "37 / 37 kontrol"], ["25 / 25", "LLM metni geçti", "şablona düşüş yok"], ["5 / 5", "tekrar tutarlılığı", "aynı girdi, aynı sonuç"]].forEach(([big, l, sub], i) => {
    const x = 0.6 + i * 3.08;
    card(s, x, 1.4, 2.85, 1.65);
    text(s, big, { x: x + 0.25, y: 1.5, w: 2.4, h: 0.8, fontSize: 40, bold: true, color: C.accent3, valign: "middle" });
    text(s, l, { x: x + 0.25, y: 2.3, w: 2.45, h: 0.32, fontSize: 15, bold: true });
    text(s, sub, { x: x + 0.25, y: 2.62, w: 2.45, h: 0.32, fontSize: 12, color: C.text2 });
  });
  text(s, "Senaryo grupları (39 çalıştırma, dondurulmuş veri)", { x: 0.6, y: 3.35, w: 6.8, h: 0.4, fontSize: 15, bold: true });
  [["Temel P01–P05 (her biri 2 kez)", 5], ["Hatalı / çelişkili veri", 3], ["Persona değişikliği", 5], ["Açık kısıt eklenir", 4], ["Kaynak erişilemez", 4], ["Regresyon (geçmiş hatalar)", 13]].forEach(([l, n], i) => {
    const y = 3.85 + i * 0.46;
    text(s, l, { x: 0.6, y, w: 3.2, h: 0.36, fontSize: 13, valign: "middle" });
    hbar(s, 3.9, y + 0.04, 2.9, 0.28, n / 13, C.accent2);
    text(s, String(n), { x: 3.9 + 2.9 * n / 13 + 0.1, y, w: 0.5, h: 0.36, fontSize: 13, bold: true, valign: "middle" });
  });
  card(s, 7.6, 3.35, 5.1, 3.4);
  text(s, "Dil kalitesi: LLM hakemi", { x: 7.85, y: 3.5, w: 4.6, h: 0.4, fontSize: 15, bold: true });
  [["Uyarlanmış", 52], ["RM için açık", 50], ["Dengeli", 60]].forEach(([l, v], i) => {
    const y = 4.0 + i * 0.5;
    text(s, l, { x: 7.85, y, w: 1.5, h: 0.36, fontSize: 13, valign: "middle" });
    hbar(s, 9.4, y + 0.04, 2.6, 0.28, 1, C.accent6);
    hbar(s, 9.4, y + 0.04, 2.6, 0.28, v / 100, C.text2);
    text(s, "%" + v, { x: 12.1, y, w: 0.55, h: 0.36, fontSize: 13, bold: true, valign: "middle" });
  });
  text(s, "Yön göstergesi: hakem katı ve küçük bir model (Claude Haiku 5.5). Kural kontrolleri hakeme bırakılmaz. Ek olarak 1.774 pytest testi, ağ erişimi yok.",
    { x: 7.85, y: 5.6, w: 4.6, h: 1.05, fontSize: 12, color: C.text2 });

  // ===== 9. Hata analizi =====
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Sonuçlar" });
  s.addText("Hata: kurallar geçti, herkes aynı öneriyi aldı", { placeholder: "title" });
  card(s, 0.6, 1.4, 4.6, 4.35);
  text(s, "Önce (12.10.2026)", { x: 0.85, y: 1.55, w: 4.1, h: 0.4, fontSize: 16, bold: true, color: C.accent4 });
  const before = [["P01 Muhafazakâr", "3 nakit benzeri, risk 1 (= P04)"], ["P02 Dengeli", "3 nakit benzeri, risk 1 (= P05)"], ["P04 Dengeli", "3 nakit benzeri, risk 1 (= P01)"], ["P05 Temkinli", "3 nakit benzeri, risk 1 (= P02)"], ["P03 Agresif", "farklı bir set"]];
  const after = [["P01 Muhafazakâr", "değişmedi (doğru davranış)"], ["P02 Dengeli", "nakit r2 · borçlanma r2 · dengeli r3"], ["P04 Dengeli", "borçlanma r3 · nakit r2 · dengeli r3"], ["P05 Temkinli", "3 nakit benzeri, risk 2 (kendi bandı)"], ["P03 Agresif", "dengeli r6 · hisse r7 · borçlanma r3"]];
  before.forEach(([p, v], i) => {
    const y = 2.05 + i * 0.72;
    text(s, p, { x: 0.85, y, w: 4.1, h: 0.3, fontSize: 14, bold: true });
    text(s, v, { x: 0.85, y: y + 0.3, w: 4.1, h: 0.32, fontSize: 14, color: i < 4 ? C.accent4 : C.text2 });
  });
  s.addShape(pres.ShapeType.rightArrow, { x: 5.45, y: 1.55, w: 2.4, h: 0.6, fill: { color: C.accent1 }, line: { type: "none" } });
  text(s, "Düzeltme D19", { x: 5.45, y: 1.55, w: 2.1, h: 0.6, fontSize: 14, bold: true, color: C.background1, align: "center", valign: "middle" });
  text(s, [
    { text: "Geçmiş getiri baskındı (nakit reel +%7–9, altın −%13)", options: { breakLine: true, color: C.text2 } },
    { text: "→ risk uyumu bandı", options: { bold: true, breakLine: true, paraSpaceAfter: 8 } },
    { text: "Çeşitlilik fon türünde ölçülüyordu", options: { breakLine: true, color: C.text2 } },
    { text: "→ varlık sınıfı ve sınıf kuralı", options: { bold: true, breakLine: true, paraSpaceAfter: 8 } },
    { text: "→ negatif reel getirili fon öne çıkmaz", options: { bold: true } },
  ], { x: 5.45, y: 2.35, w: 2.45, h: 3.4, fontSize: 14 });
  card(s, 8.1, 1.4, 4.6, 4.35);
  text(s, "Sonra (D19)", { x: 8.35, y: 1.55, w: 4.1, h: 0.4, fontSize: 16, bold: true, color: C.accent3 });
  after.forEach(([p, v], i) => {
    const y = 2.05 + i * 0.72;
    text(s, p, { x: 8.35, y, w: 4.1, h: 0.3, fontSize: 14, bold: true });
    text(s, v, { x: 8.35, y: y + 0.3, w: 4.1, h: 0.32, fontSize: 14, color: C.text2 });
  });
  card(s, 0.6, 5.95, 12.1, 0.85, C.accent5);
  circleIcon(s, I.FaLightbulb, 0.8, 6.05, 0.6, C.accent1);
  text(s, [
    { text: "Öğrenim: ", options: { bold: true } },
    { text: "\"kurallar %100\" yeterli değil. Çıktılar arası karşılaştırma ve insan incelemesi gerekir. Şimdi 5 persona, 5 farklı set." },
  ], { x: 1.6, y: 6.0, w: 10.9, h: 0.75, fontSize: 15, valign: "middle" });

  // ===== 10. Sınırlar ve sonraki adımlar =====
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Sonuçlar" });
  s.addText("Sınırlarımız ve sonraki adımlar", { placeholder: "title" });
  [[I.FaExclamationTriangle, C.accent4, "Sınırlar", [
      "Sonuçlar 10.10.2026 dondurulmuş verisine aittir",
      "RM'in bugünkü hazırlık süresi ölçülmedi [VARSAYIM]",
      "Risk ve dağılım bantları tek kaynaktan [VARSAYIM]",
      "Sınıf kuralıyla gelen önerilerde istikrar ölçüsü anlamlı değil (P03: OKT)",
      "LLM hakemi yalnızca yön gösterir; ikinci hakem yok",
    ]],
   [I.FaRoad, C.accent3, "Sonraki adımlar", [
      "Mevcut portföy girdisi ve bantlarla boşluk analizi",
      "Yaşam olayları, hedefler ve görüşme sonrası \"Takip\" adımı",
      "Bankanın model portföyleri, resmî oran ve stopaj akışı",
      "RM incelemesi ile hakemin kalibrasyonu",
      "KAP için lisanslı veri; kimlik doğrulama ve denetim deposu",
    ]]].forEach(([ic, col, title, items], i) => {
    const x = 0.6 + i * 6.2;
    card(s, x, 1.45, 5.9, 4.2);
    circleIcon(s, ic, x + 0.3, 1.7, 0.65, col);
    text(s, title, { x: x + 1.15, y: 1.7, w: 4.4, h: 0.65, fontSize: 20, bold: true, valign: "middle" });
    text(s, bullets(items, { gap: 10 }), { x: x + 0.35, y: 2.6, w: 5.25, h: 2.9, fontSize: 15 });
  });

  // ===== 11. Kapanış =====
  s = pres.addSlide({ masterName: "KOYU", sectionTitle: "Sonuçlar" });
  s.addText("Karar desteği, yatırım tavsiyesi değil", { placeholder: "title" });
  [[I.FaCogs, "Deterministik çekirdek", "Kısıt ihlali 0. Aynı girdi aynı sonucu ve aynı metni verir."],
   [I.FaFingerprint, "Her sayı kanıtla", "Kaynak, tarih, alınma zamanı ve kanıt kimliği. Her karar kayda geçer."],
   [I.FaUserCheck, "RM kontrolde", "Üç onay noktası. Müşteriye otomatik iletim yok."]].forEach(([ic, t, d], i) => {
    const x = 0.6 + i * 4.15;
    s.addShape(pres.ShapeType.roundRect, { x, y: 1.9, w: 3.85, h: 2.95, rectRadius: 0.12, fill: { color: C.background1, transparency: 90 }, line: { type: "none" } });
    circleIcon(s, ic, x + 0.35, 2.2, 0.8, i === 2 ? C.accent1 : C.accent2);
    text(s, t, { x: x + 0.35, y: 3.2, w: 3.2, h: 0.5, fontSize: 20, bold: true, color: C.background1 });
    text(s, d, { x: x + 0.35, y: 3.75, w: 3.2, h: 0.95, fontSize: 15, color: C.accent6 });
  });
  text(s, "Teşekkürler. Sorularınızı ve Jüri Challenge koşullarını bekliyoruz.", { x: 0.6, y: 5.35, w: 12.1, h: 0.5, fontSize: 18, color: C.accent1, bold: true });

  // ===== Ek =====
  pres.addSection({ title: "Ek" });
  s = pres.addSlide({ masterName: "KAPAK", sectionTitle: "Ek" });
  s.addText("Ek: soru-cevap için", { placeholder: "title" });
  s.addText("Jüri Challenge davranışları, P02 örneği, kanıt kaydı, dağılım bantları, onay noktaları, metin kalitesi, yöntem seçimi", { placeholder: "body" });
  circleIcon(s, I.FaQuestionCircle, 8.9, 2.0, 2.6, C.accent1);

  // A1 Jüri Challenge
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Ek" });
  s.addText("Jüri Challenge: koşul değişince ne olur?", { placeholder: "title" });
  const hdr = (t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.accent2 } } });
  const rowsA1 = [
    ["Risk profili değişir (P03 Agresif → Muhafazakâr)", "Tavan 2'ye iner; öneriler, dağılım bantları ve metin yeniden üretilir", "Persona değişikliği"],
    ["Yeni açık kısıt (\"döviz istemiyor\", \"yüksek riskli ürün istemiyor\")", "Katı kural: ilgili fonlar elenir, gerekçe listede görünür", "Kısıt"],
    ["Tanınmayan kısıt veya risk profili metni", "Sıralama durur; RM'e soru açılır (needs_rm_input)", "Kısıt"],
    ["Vade kısalır veya likidite \"Yüksek\" olur", "Getiri dönemi ve likidite ağırlığı değişir; sonuç beklenen yönde", "Persona değişikliği"],
    ["Kaynak erişilemez (TEFAS web dışlanır)", "Fon önerilmez; P01'de 2 seçenek kalır, eksik kaynak notta", "Veri erişimi"],
    ["Hatalı veya çelişkili veri", "Bayrak; aralık dışı değer kullanılmaz, güven düşer", "Hatalı veri"],
    ["Ekranda \"Profili düzenle\"", "Test çalıştırması: sonuç görünür, onaylanamaz", "Arka uç kuralı"],
  ];
  s.addTable([[hdr("Değişiklik"), hdr("Sistemin davranışı"), hdr("Eval grubu")], ...rowsA1.map((r, i) => r.map((c) => ({ text: c, options: { fill: { color: i % 2 ? C.background1 : C.background2 } } })))],
    { x: 0.6, y: 1.4, w: 12.1, colW: [4.4, 5.6, 2.1], fontSize: 13, color: C.text1, border: { type: "none" }, margin: [0.06, 0.12, 0.06, 0.12], valign: "middle", rowH: 0.62 });

  // A2 P02 örneği
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Ek" });
  s.addText("P02 örneği: ağırlıklar müşteriden gelir", { placeholder: "title" });
  text(s, "P02 ağırlıkları (Dengeli, 1–3 yıl, likidite / gelir / anapara Orta)", { x: 0.6, y: 1.4, w: 5.8, h: 0.6, fontSize: 15, bold: true });
  [["Reel getiri", 0.339], ["Risk uyumu", 0.203], ["Likidite", 0.203], ["Gelir", 0.102], ["Anapara", 0.102], ["Kalite", 0.051]].forEach(([l, v], i) => {
    const y = 2.15 + i * 0.6;
    text(s, l, { x: 0.6, y, w: 1.6, h: 0.4, fontSize: 14, valign: "middle" });
    hbar(s, 2.3, y + 0.04, 3.2, 0.32, v / 0.339, C.accent2);
    text(s, v.toFixed(3).replace(".", ","), { x: 2.3 + 3.2 * v / 0.339 + 0.1, y, w: 0.8, h: 0.4, fontSize: 13, bold: true, valign: "middle" });
  });
  text(s, "\"Erişilebilir likidite\" önceliği likiditeye +1 ekler; toplam 1'e normalleştirilir.", { x: 0.6, y: 5.9, w: 5.8, h: 0.7, fontSize: 12, color: C.text2 });
  const neg = { color: C.accent4, bold: true };
  const pos = { color: C.accent3, bold: true };
  s.addTable([
    [hdr("Seçenek"), hdr("Sınıf, risk"), hdr("Reel 1 yıl"), hdr("Puan")],
    ["BVF · BV Para Piyasası", "nakit, 2", { text: "+%8,0", options: pos }, "0,775"],
    ["NJR · Nurol Borçlanma", "borçlanma, 2", { text: "+%8,4", options: pos }, "0,737"],
    ["IRF · İstanbul Fon Sepeti", "dengeli, 3", { text: "+%12,8", options: pos }, "0,718"],
    ["Turuncu Hesap (taban)", "nakit, 1", { text: "−%8,3", options: neg }, "0,187"],
  ], { x: 6.8, y: 1.45, w: 5.9, colW: [2.6, 1.3, 1.1, 0.9], fontSize: 13, color: C.text1, border: { type: "solid", pt: 0.5, color: HEX.accent6 }, margin: [0.06, 0.1, 0.06, 0.1], valign: "middle", rowH: 0.5 });
  card(s, 6.8, 4.25, 5.9, 2.0);
  text(s, bullets([
    "EIL (0,774) BVF'ye çok yakın, ama ikinci nakit benzeri: alternatif kalır.",
    "KDE (0,736) IRF'den yüksek, ama borçlanma sınıfı NJR ile dolu.",
    "Turuncu Hesap reel −%8,3: reel zarar ve piyasa altı cezaları alır.",
  ], { gap: 8 }), { x: 7.05, y: 4.45, w: 5.4, h: 2.1, fontSize: 14 });

  // A3 Kanıt kaydı
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Ek" });
  s.addText("Her sayı kaynağı ve zamanıyla görünür", { placeholder: "title" });
  const hEv = shot(s, "evidence.png", 0.6, 1.5, 5.4, 896 / 628);
  text(s, "\"K\" işareti: değer, kaynak, tarih, alınma zamanı, kanıt kimliği, bayrak", { x: 0.6, y: 1.5 + hEv + 0.12, w: 5.4, h: 0.5, fontSize: 11, color: C.text2 });
  text(s, "Karar kaydı neyi tutar?", { x: 6.6, y: 1.45, w: 6.1, h: 0.45, fontSize: 17, bold: true });
  [["Çalıştırma", "kimlik, yapılandırma özeti, veri anlık görüntüsü, dışlanan kaynaklar"],
   ["RM kararı", "durum, seçim, notlar, karar zamanı (Türkiye saati)"],
   ["Görüşme metni", "model, istem sürümü, doğrulayıcı sonucu, maliyet, onay zamanı"],
   ["Her sayı", "kanıt kimliğiyle kaynağa bağlı; aynı girdi aynı kimliği verir"]].forEach(([t, d], i) => {
    const y = 2.05 + i * 0.95;
    card(s, 6.6, y, 6.1, 0.8);
    text(s, [{ text: t + ": ", options: { bold: true } }, { text: d, options: { color: C.text2 } }], { x: 6.85, y, w: 5.65, h: 0.8, fontSize: 14, valign: "middle" });
  });
  text(s, "Teslimat 6'daki örnek kayıt (P02) bir betikle onaylandı; demoda onayı RM ekranda verir.", { x: 6.6, y: 5.95, w: 6.1, h: 0.7, fontSize: 12, color: C.text2, italic: true });

  // A4 Dağılım
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Ek" });
  s.addText("Dağılım: risk profiline göre model bantlar", { placeholder: "title" });
  shot(s, "allocation.png", 0.6, 1.45, 7.6, 1770 / 1080);
  card(s, 8.6, 1.45, 4.1, 3.75);
  text(s, bullets([
    "Kaynak: Ata Yatırım, 28.04.2026, risk profiline göre örnek portföyler",
    "Temkinli bandı kaynakta yok: bizim çıkarımımız [VARSAYIM]",
    "Her sınıfta bu müşteriye en iyi seçenek; uygun fon yoksa nedeni yazılır",
    "Bantlar puana girmez. Mevcut pay yok; boşluk analizi gelecek iş",
  ], { gap: 10 }), { x: 8.85, y: 1.7, w: 3.6, h: 4.2, fontSize: 14 });

  // A5 Onay noktaları
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Ek" });
  s.addText("Üç onay noktası, müşteriye otomatik iletim yok", { placeholder: "title" });
  const hMt = shot(s, "meeting-crop.png", 0.6, 1.45, 7.2, 2880 / 1500);
  text(s, "Onaylı görüşme metni (P02): onay zamanı, model, kontrol sonucu; sağda \"RM notu · yalnızca sizin için\"", { x: 0.6, y: 1.45 + hMt + 0.12, w: 7.2, h: 0.5, fontSize: 11, color: C.text2 });
  [["İ1", "Engelleyici soru açıkken sıralama yapılmaz."],
   ["İ2", "Ret not ister. Metin yalnızca onaylı seçim için üretilir."],
   ["İ3", "Yasak ifade, izinsiz ürün veya iç bilgi onayı engeller."]].forEach(([b, d], i) => {
    const y = 1.5 + i * 1.0;
    hexBadge(s, b, 8.2, y);
    text(s, d, { x: 9.15, y, w: 3.55, h: 0.8, fontSize: 14, valign: "middle" });
  });
  card(s, 8.2, 4.65, 4.5, 1.5, C.accent5);
  text(s, bullets([
    "RM'e özel not müşteri metnine girmez",
    "Uygulama yalnızca 127.0.0.1 adresinde çalışır",
    "Düzenlenmiş persona onaylanamaz",
  ], { gap: 6 }), { x: 8.45, y: 4.8, w: 4.1, h: 1.25, fontSize: 14 });

  // A6 Metin kalitesi
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Ek" });
  s.addText("Metin kalitesi: hakeme göre optimize etmedik", { placeholder: "title" });
  s.addTable([
    [hdr("Ölçü"), hdr("Önce (n6, j2)"), hdr("Sonra (n9, j3)")],
    ["P01 metni, kelime", "644", "465"],
    ["P01'de \"geçmiş\" sözcüğü", "6", "3"],
    ["Fonun adıyla başlayan öneri cümlesi", "3 / 6", "9 / 9"],
    ["Doğrulayıcı geçiş, şablona düşüş", "%100, 0", "%100, 0"],
    ["Hakem: uyarlanmış / açık / dengeli", "%57 / %50 / %50", "%52 / %50 / %60"],
    ["Metin başına maliyet", "0,042 $", "0,046 $"],
  ], { x: 0.6, y: 1.45, w: 6.9, colW: [3.3, 1.8, 1.8], fontSize: 13, color: C.text1, border: { type: "solid", pt: 0.5, color: HEX.accent6 }, margin: [0.06, 0.1, 0.06, 0.1], valign: "middle", rowH: 0.52 });
  card(s, 7.9, 1.45, 4.8, 1.85);
  text(s, "Neden durduk?", { x: 8.15, y: 1.6, w: 4.3, h: 0.4, fontSize: 16, bold: true });
  text(s, "İstemi bir LLM hakeminin zevkine göre ayarlamak, RM için daha iyi metin demek değil. Ölçülebilir kurallar ekledik (shape, repeat, compare).",
    { x: 8.15, y: 2.05, w: 4.3, h: 1.15, fontSize: 14, color: C.text2 });
  card(s, 7.9, 3.5, 4.8, 2.15, C.accent5);
  text(s, "Değerlendirmenin kendi hatası", { x: 8.15, y: 3.65, w: 4.3, h: 0.4, fontSize: 16, bold: true });
  text(s, "Anlatıcı maliyeti 0 $ çıktı: önbellek anahtarında RM seçimi yoktu, eski metin döndü. Anahtara olgu paketinin özeti eklendi (N12). Beklenmedik derecede iyi bir ölçüm de bir hata işaretidir.",
    { x: 8.15, y: 4.1, w: 4.3, h: 1.45, fontSize: 14, color: C.text2 });

  // A7 Neden bu yaklaşım
  s = pres.addSlide({ masterName: "ICERIK", sectionTitle: "Ek" });
  s.addText("Neden kural ve şeffaf puan?", { placeholder: "title" });
  const sel = (t) => ({ text: t, options: { bold: true, fill: { color: C.accent5 } } });
  s.addTable([
    [hdr("Ölçüt"), hdr("Kural + şeffaf puan (seçilen)"), hdr("ML sıralama"), hdr("Yalnızca LLM")],
    ["Veri ihtiyacı", sel("Etiket gerekmez"), "Geçmiş RM kararları gerekir; yok", "Etiket gerekmez"],
    ["Denetlenebilirlik", sel("Her puan parçası kanıta bağlı"), "Öznitelik önemi yaklaşık", "Gerekçe doğrulanamaz"],
    ["Düzenleyici kurallar", sel("Katı kural; ihlal mümkün değil"), "Yalnızca öğrenilmiş eğilim", "İstemle; ihlal mümkün"],
    ["Determinizm", sel("Aynı girdi, aynı sonuç"), "Eğitim sürümüne bağlı", "Aynı istem, farklı çıktı"],
    ["Değişiklik", sel("Yapılandırma dosyası"), "Yeniden eğitim", "Öngörülemez etki"],
  ], { x: 0.6, y: 1.45, w: 12.1, colW: [2.5, 3.6, 3.0, 3.0], fontSize: 14, color: C.text1, border: { type: "solid", pt: 0.5, color: HEX.accent6 }, margin: [0.08, 0.12, 0.08, 0.12], valign: "middle", rowH: 0.62 });
  text(s, "Yerindelik önce bir kısıt problemidir (risk tavanı, alıma açıklık, açık kısıtlar), sonra çok kriterli bir ödünleşimdir. Ağırlıkları biz seçeriz ve açıkça gösteririz; RM onayları biriktiğinde bir modelle ayarlanabilir.",
    { x: 0.6, y: 5.5, w: 12.1, h: 1.0, fontSize: 14, color: C.text2 });

  await pres.writeFile({ fileName: OUT });
  if (APPLY_THEME) {
    const { applyTheme } = require(APPLY_THEME);
    await applyTheme(OUT, THEME);
  }
  console.log("wrote", OUT);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
