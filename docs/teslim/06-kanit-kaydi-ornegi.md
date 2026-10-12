# Kanıt kaydı örneği

> Teslimat 6 · Taslak (2026-10-12) · Kaynak: kayıtlı P01 çalıştırması
> `Rc42670a01a`, veri anlık görüntüsü `20261010-183835-6813`, kanıt deposu
> `data/evidence.duckdb`. Tüm değerler kayıttan aynen kopyalanmıştır; kayıtta
> olmayan bilgi "kayıtta yok" olarak işaretlidir.

## 1. Bu kayıt neyi gösteriyor

Bu kayıt, P01 müşterisi için önerilen ilk ürünün (NUROL PORTFÖY PARA PİYASASI
(TL) FONU, `fund:PPN`) zincirini uçtan uca izler: **veri → kural → skor →
öneri → görüşme metni → RM onayı**. Her veri noktasının bir kanıt kimliği
(`E…`) vardır; kurallar ve skor parçaları bu kimlikleri taşır; görüşme
metnindeki her cümle dayandığı kimlikleri listeler; RM onayı aynı çalıştırma
kimliğine (`run_id`) yazılır. Böylece bir jüri üyesi metindeki bir sayıdan
başlayıp kaynak sayfaya ve ham dosyaya kadar geri gidebilir.

## 2. Çalıştırma kimliği

| Alan | Değer |
|---|---|
| `run_id` | `Rc42670a01a` |
| `snapshot_id` | `20261010-183835-6813` |
| `config_hash` | `2534f798cc47` |
| `created_at` (Europe/Istanbul) | `2026-10-12T18:46:20.662476+03:00` |
| Persona | `P01` · Emekli girişimci, 62 yaş, Muhafazakâr, "Varlığı TL mevduat ağırlıklı" |
| Durum | `state = ready`, `excluded_sources = []` |

`config_hash`, `config/decision.yaml` dosyasının kanonik JSON'unun sha256
özetinin ilk 12 karakteridir. `run_id` ise `config_hash`, persona, `snapshot_id`,
hariç tutulan kaynaklar ve RM cevaplarının sha1 özetidir (`docs/decision.md`
bölüm 7). `created_at` bu özete girmez. Bu nedenle aynı girdiler her zaman aynı
`run_id` değerini verir; bir persona değişikliği veya bir cevap yeni bir
`run_id` üretir.

## 3. Öneri ve gerekçe

**Seçenek:** Para Piyasası (TL) · NUROL PORTFÖY PARA PİYASASI (TL) FONU · fon
kodu `PPN` · `option_id = fund:PPN` · ihraççı Nurol Portföy · varlık sınıfı
`nakit_benzeri`. Motorun önerdiği ilk üç seçenek (`recommended`):
`fund:PPN`, `fund:IST`, `fund:AIS`.

**Skor:** `0.849747653806048`. Skor, ağırlık × değer parçalarının toplamıdır;
parçalar skora eşit olmazsa sözleşme kontrolü hata verir.

| Parça | Değer | Gerekçe metni (kayıttaki gibi) |
|---|---|---|
| `return` | 0.14285714285714288 | Yıllık getiri %47.6, stopaj sonrası %39.3, enflasyon sonrası reel %+7.4 (1y); adayların %89'inden iyi. |
| `risk_fit` | 0.24 | Risk değeri 1/7; müşterinin risk aralığı 1-2. |
| `liquidity` | 0.16 | Satış valörü 0 gün; likidite 1.0. |
| `income` | 0.144 | Düzenli gelir uygunluğu (ürün türüne göre): 0.6. |
| `principal` | 0.128 | Anapara koruma: 0.80. |
| `quality` | 0.03489051094890511 | Fon büyüklüğü ve yatırımcı sayısı: adayların %87'inden iyi. |

`score_parts` içinde `penalty:` ile başlayan bir parça yoktur, yani bu
seçeneğe ceza uygulanmadı.

**Reel getiri hesabı** (`docs/decision.md` 4.1b, kayıtlı değerlerle):
net = 47.6037 × (1 − 0.175); reel = (1 + net) / (1 + 0.2973) − 1. Sonuç,
kayıttaki `real_1y = 7.3560876435674105` değeridir (kanıt `E2075d858`,
`Ede9af545`, `Eb39e0ab5`).

**Geçen kısıtlar:**

| Kural | Sonuç | Gerekçe | Kanıt |
|---|---|---|---|
| `not_buyable` | geçti | TEFAS'ta alıma açık. | `E6b3773b2` |
| `risk_ceiling` | geçti | Risk değeri 1, müşterinin tavanı 2 içinde. | `Ea939c58c` |

**Güven:** `confidence = 0.9` (en zayıf veri noktası `needs_check` veya
`manual_entry` işaretli; çarpan 0.9). **Kararlılık:** `stability = 1.0`
(ağırlıklar ve ceza üst sınırları ±%20 değiştirildiğinde seçenek her
denemede ilk 20 içinde kaldı).

## 4. Dayandığı veriler

Seçeneğin `evidence_ids` listesindeki 10 kimliğin tümü, `snapshot_id =
20261010-183835-6813` satırlarından okunmuştur.

| Kanıt | Büyüklük | Değer + birim | as_of | Kaynak | source_url | fetched_at | Bayrak |
|---|---|---|---|---|---|---|---|
| `E2075d858` | fund_return_1y (PPN) | 47.6037 pct | 2026-10-09 | tefas_web | https://www.tefas.gov.tr/tr/fon-getirileri | 2026-10-10T18:38:37.587166+03:00 | needs_check |
| `Ea939c58c` | fund_risk_level (PPN) | 1.0 level | 2026-10-09 | tefas_web | https://www.tefas.gov.tr/tr/fon-getirileri | 2026-10-10T18:38:37.587166+03:00 | needs_check |
| `E6b3773b2` | fund_buyable (PPN) | 1.0 flag | 2026-10-09 | tefas_detail | https://www.tefas.gov.tr/tr/fon-detayli-analiz/PPN | 2026-10-10T18:52:15.632710+03:00 | needs_check |
| `E06f53164` | fund_sell_valor_days (PPN) | 0.0 days | 2026-10-09 | tefas_detail | https://www.tefas.gov.tr/tr/fon-detayli-analiz/PPN | 2026-10-10T18:52:15.632710+03:00 | needs_check |
| `E8eec2559` | fund_investor_count (PPN) | 10366.0 count | 2026-10-09 | tefas_detail | https://www.tefas.gov.tr/tr/fon-detayli-analiz/PPN | 2026-10-10T18:52:15.632710+03:00 | needs_check |
| `E9d4d5f36` | fund_total_value (PPN) | 9030023246.62 TRY | 2026-10-09 | tefas_detail | https://www.tefas.gov.tr/tr/fon-detayli-analiz/PPN | 2026-10-10T18:52:15.632710+03:00 | needs_check |
| `Eb39e0ab5` | cpi_annual · TÜFE yıllık değişim (TÜİK) | 29.73 pct | 2026-09-30 | manual | https://www.sbb.gov.tr/enflasyon/ | 2026-10-10T18:38:36.881130+03:00 | manual_entry |
| `Ede9af545` | withholding_tax_rate · Yatırım fonu, para piyasası fonu | 17.5 pct | 2026-03-27 | manual | https://www.ziraatportfoy.com.tr/Documents/Banner//ZFG_PORTFOY_yat%C4%B1r%C4%B1m-fonlar%C4%B1-stopaj-oranlar%C4%B1-hakk%C4%B1nda-27-03-2026-pdf_328.pdf | 2026-10-10T18:38:36.881130+03:00 | manual_entry |
| `E9cb9f7ad` | deposit_rate · TRY savings deposit rate up to 3M, weighted average (new deposits) | 43.82 pct | 2026-10-02 | evds | https://evds3.tcmb.gov.tr/ | 2026-10-10T18:38:36.865736+03:00 | yok |
| `E0382c2e7` | withholding_tax_rate · TL vadesiz mevduat ve günlük hesap (Turuncu Hesap türü) | 17.5 pct | 2026-06-20 | manual | https://www.yontemymm.com.tr/mali-aciklamalar/2026-041-tl-mevduat-hesaplarinda-uygulanan-stopaj-oranlarinin-suresi-uzatildi | 2026-10-10T18:38:36.881130+03:00 | manual_entry |

`E9cb9f7ad` (piyasa mevduat ortalaması) ve `E0382c2e7` (mevduat stopajı),
`underperformance` cezasının karşılaştırma değeri için listededir; bu seçenekte
ceza sıfırdır.

**Stopaj oranı nereden geliyor (kural 7).** Kodda stopaj oranı yoktur.
`config/decision.yaml` yalnızca hangi satırın kullanılacağını söyler
(`fund_by_kind: {money_market: "Yatırım fonu, para piyasası fonu"}`). Oran,
elle doldurulan `data/inbox/manual/withholding_tax.csv` tablosundan gelir; her
satır kendi `source_url` ve `as_of` değerini taşır. `Ede9af545` satırının notu:
"Individuals, CK 10041 (09.07.2025). CK 11734 (04.09.2026) sets 10 % for capital
companies (not individuals, unconfirmed). Secondary source". TÜFE satırının
notu: "TÜİK CPI September 2026, annual change, published 2026-10-05 (via SBB).
EVDS has only 4 months of the index (2025=100), not enough for a 12-month
change."

**Ham dosya izi.** Her satırın `raw_ref` alanı anlık görüntüdeki ham dosyayı
gösterir. Örnek: `E2075d858` →
`20261010-183835-6813/payloads/tefas_web/fon-getirileri.html#fonKodu=PPN;field=getiri1y`;
`Ede9af545` → `…/payloads/manual/withholding_tax.csv#row=6`. `manifest.json`
her ham dosyanın sha256 özetini saklar (ör. `PPN.html.gz`:
`d1bc6debb2368a16074e28849025cb6aec58ef2761ee40c4e87005eeac59eeac`). Manifestteki kaynak durumu: evds `ok`, manual `ok`,
tefas_web `ok`, tefas_detail `ok`, tefas `skipped`.

## 5. Varsayımlar ve uyarılar

Varsayımlar (kayıttaki gibi):

1. Fon getirileri geçmiş getirilerdir; mevduat oranı bugünkü orandır.
2. Getiriler stopaj sonrası ve yıllık TÜFE'ye (%29.73, 2026-09-30) göre reel olarak hesaplandı.
3. Mevduat için 100.000-249.999 TL diliminin standart oranı kullanıldı (tutar bilinmiyor; hoş geldin oranı geçicidir).
4. Fonlarda likidite satış valöründen (valör yoksa ürün türünden), gelir uygunluğu ürün türünden türetildi.
5. Hisse senedi yoğun fonlarda stopaj %0'dır; ihtiyatlı olmak için para piyasası dışındaki tüm fonlarda 'diğer fonlar' oranı kullanıldı.
6. 32 günlük vade her ay yenilenir; oranlar değişebilir.

Uyarı (yalnızca RM için, `audience = rm`): `deposit_vs_market` — "ING standart
mevduat oranı (%23.00) piyasa ortalamasının (%43.82) 20.8 puan altında."
(kanıt `E42b47116`, `E9cb9f7ad`).

Teyit edilecek: "Yatırım tutarını sorun: 100.000-249.999 TL dilimi varsayıldı."

Veri kalitesi notları: "manual: 7 değer "manual_entry" işaretli."; "tefas_detail:
739 değer "needs_check" işaretli."; "tefas_web: 847 değer "needs_check"
işaretli."; "1 değer aralık dışında olduğu için kullanılmadı."; "6 fonun TEFAS
alım durumu kanıtlarda yok; bu fonlar alıma açık sayıldı."; "1292 serbest fon
çıkarıldı (yalnızca nitelikli yatırımcılar)."

## 6. Görüşme metni

| Alan | Değer |
|---|---|
| Model | `claude-sonnet-5-5` (`source = llm`) |
| Prompt sürümü | `n6` |
| Doğrulayıcı sonucu | `checks = []` (bulgu yok, yani geçti) |
| Maliyet | `cost_usd = 0.0633525` |
| Oluşturma zamanı | `2026-10-12T18:47:05.808829+03:00` |
| Durum | `draft`, `rm_text = ""` |

Doğrulayıcı koddur, LLM değildir (`docs/narrator.md`). Beş kontrol yapar: her
sayı olgu paketindeki bir sayıyla eşleşir; yalnızca seçilen seçenekler ve grup
alternatifleri adlandırılır; yasak ifadeler ("garanti", "risksiz" vb.) yoktur;
öneri, alternatif ve dikkat cümlelerinin her birinde var olan bir kanıt atfı
vardır; metin yatırım tavsiyesi olmadığını söyler.

`fund:PPN` için cümleler:

| Cümle | Kanıt |
|---|---|
| "NUROL PORTFÖY PARA PİYASASI (TL) FONU bir para piyasası fonudur; son bir yılda getirisi %47,6, risk değeri 1/7 ve yatırımcı sayısı 10.366." | `E2075d858`, `Ea939c58c`, `E8eec2559` |
| "Müşterinin "düzenli gelir" önceliğine bağlayın: son bir yıllık getirisi bu başlıkta öne çıkıyor ve aynı gün erişim, aylık nakit akışı sorusuna yanıt olabilir." | `E2075d858` |
| "NUROL PORTFÖY PARA PİYASASI (TL) FONU son bir yılda enflasyon sonrası +%7,4 getirdi; geçmiş getiri geleceği göstermez." | `E2075d858`, `Eb39e0ab5` |

Motorun aynı konuşma noktası (`best_alternative`) ayrıca stopaj satırı
`Ede9af545` kimliğini de atfeder.

## 7. RM onayı

| Alan | Değer |
|---|---|
| `rm_status` | `approved` |
| `rm_selected` | `fund:PPN`, `fund:IST`, `fund:AIS` |
| `rm_note` | "Müşteri aylık nakit akışını sordu." |
| `rm_option_notes` | boş (`{}`) |
| Onay zamanı | kayıtta yok (sonuç yalnızca `created_at` saklar) |
| Görüşme metninin onayı | kayıtta yok (metin `draft` durumunda) |

RM, motorun önerdiği üç seçeneği değiştirmeden onayladı. Görüşme metni bu
onaydan sonra yazıldı ve RM notunu kullandı ("müşteri aylık nakit akışını
sordu"). Sistem şu kuralları uygular:

- Onaylanmamış bir çalıştırma için görüşme metni yazılmaz (API: "a meeting text needs an approved run").
- Kart yalnızca onaylı bir çalıştırma için oluşturulur.
- Metin onayı boş olmayan bir RM metni ister ve engelleyici bulgu varsa reddedilir.
- Onaylı metin, model, prompt sürümü ve doğrulayıcı sonucu ile birlikte `data/narratives/<run_id>-<lang>-approved.json` dosyasına ve karta yazılır.

Bu kayıtta metnin RM onayı yoktur. Bu nedenle müşteriye giden bir metin de
yoktur. `Rc42670a01a` için onaylı metin dosyası ve kart dosyası
(`data/cards/Rc42670a01a.md`) kayıtta yok.

## 8. Nasıl doğrulanır

**Uygulamada:**

1. P01 müşterisini `20261010-183835-6813` anlık görüntüsü ile açın (aynı config ile `run_id = Rc42670a01a` olur).
2. NUROL PORTFÖY PARA PİYASASI (TL) FONU kartında "Kanıtları göster" düğmesine basın.
3. Bir kimliğe (ör. `E2075d858`) basın. "Kanıt" penceresi değeri, kaynağı, tarihi, kanıt numarasını, bayrakları ve notu gösterir.
4. Kaynak sayfayı görmek için "Kaynağı aç" bağlantısına basın.

`fetched_at` değeri penceredeki alanlarda yoktur; API cevabında vardır:
`GET /api/evidence/20261010-183835-6813/E2075d858`. Bu cevabın kayıtlı örneği
`tests/contracts/fixtures/api/evidence_item.json` dosyasıdır.

**Veritabanında** (yalnızca okuma):

```python
import duckdb
con = duckdb.connect("data/evidence.duckdb", read_only=True)
con.execute(
    "select id, quantity, entity, value, unit, as_of, source, source_url,"
    " cast(fetched_at as varchar), raw_ref, flags, note from datapoints"
    " where snapshot_id = '20261010-183835-6813' and id = 'E2075d858'"
).fetchall()
```

**Ham dosyada:** `raw_ref` yolundaki dosyayı açın. Dosyanın sha256 özetini
`manifest.json` içindeki değerle karşılaştırın.
