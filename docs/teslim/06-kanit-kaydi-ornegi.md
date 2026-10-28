# Kanıt kaydı örneği

> Teslimat 6 · Güncel sürüm (2026-10-28) · Kaynak: kayıtlı P01 çalıştırması
> `Rb5470b4f25` (`data/runs/Rb5470b4f25.json`), profil kontrolü
> (`data/runs/Rb5470b4f25.resolutions.json`), ajan kararı
> (`data/agent/Rb5470b4f25.json`), web araştırması
> (`data/research/products/fund_PPN-TR-20261018-v2.json`,
> `data/research/questions/Rb5470b4f25-TR-v2-9d7706b089ca.json`,
> `data/research/marks/20261018.json`), görüşme metni
> (`data/narratives/Rb5470b4f25-TR-n12-claude-sonnet-5-5-75cd8496de.json`) ve RM
> düzenlemeleri (`data/narratives/Rb5470b4f25-TR-edits.json`), kart
> (`data/cards/Rb5470b4f25.md`), RM işlem kaydı
> (`data/logs/rm-actions/2026-10-18.jsonl`), veri anlık görüntüsü
> `20261018-132653-1991`, kanıt deposu `data/evidence.duckdb`. Tüm değerler
> kayıttan aynen kopyalanmıştır; kayıtta olmayan bilgi "kayıtta yok" olarak
> işaretlidir.
>
> **Not:** Bu kayıt, demo videosu (v2, P01–P02–P03) çekilirken bir betikle
> oluşturuldu. Depo dışındaki Playwright betiği (`demo-video/record2.mjs`)
> arayüzde RM'in yerine tıkladı ve yazdı: iki web bulgusuna ✓/✗ işareti, RM
> sorusu, "Onayla ve metni hazırla", bir metin bloğunun düzenlenmesi ve RM
> notu. Bu nedenle adımlar arasında yalnızca birkaç saniye vardır. Arayüz bu
> işlemler için gerçek kullanımdaki API çağrılarının aynısını yapar. Gerçek
> kullanımda bu adımları RM ekrandan yapar; kayıt yapısı aynıdır.

## 1. Bu kayıt neyi gösteriyor

Bu kayıt, P01 müşterisi için önerilen ilk ürünün (NUROL PORTFÖY PARA PİYASASI
(TL) FONU, `fund:PPN`) tam karar zincirini gösterir: **veri → kural → skor →
motor önerisi → ajan kararı (web bulguları ve RM'in ✓/✗ işaretleriyle) → RM
onayı (profil kontrolüyle) → görüşme metni ve RM düzenlemesi → kart**. Her veri
noktasının bir kanıt kimliği (`E…`), kaynağı, değer tarihi (`as_of`) ve alınma
zamanı (`fetched_at`) vardır. Her web bulgusunun bir bulgu kimliği (`F…`)
vardır. Kurallar, skor parçaları, ajan gerekçeleri ve metin cümleleri bu
kimlikleri taşır. RM'in her işlemi aynı `run_id` ile işlem kaydına yazılır.
Tüm zamanlar Türkiye saatidir (`Europe/Istanbul`, +03:00).

README bölüm 8'deki izlenebilirlik katmanları bu belgede şu bölümlerdedir:

| README bölüm 8 katmanı | Bu belgedeki yeri |
|---|---|
| Her değer | bölüm 4 (kanıt satırları) |
| Ham veri | bölüm 14 (`raw_ref`, SHA-256, manifest) |
| Kalite | bölüm 4 (bayraklar), bölüm 5 (veri kalitesi notları) |
| Her karar | bölüm 2, 3 ve 5 |
| Ajan kararı | bölüm 7 |
| Web bulguları | bölüm 8 |
| Onaylar | bölüm 9 (karar, seçim, notlar, profil çelişkileri) |
| Metin | bölüm 10 |
| RM işlemleri | bölüm 12 |

## 2. Çalıştırma kimliği

| Alan | Değer |
|---|---|
| `run_id` | `Rb5470b4f25` |
| `snapshot_id` | `20261018-132653-1991` (manifest `created_at` = `2026-10-18T13:26:53.203068+03:00`) |
| `config_hash` | `dda3ae095519` |
| `created_at` | `2026-10-18T22:49:56.274809+03:00` |
| Sürümler (işlem kaydındaki `versions`) | `decision_config = dda3ae095519`, `narrator_prompt = n12`, `agent_prompt = a3`, `research = 2` |
| Persona | `P01` · Emekli girişimci, 62 yaş, Muhafazakâr, "Varlığı TL mevduat ağırlıklı" |
| Yatırım amacı / ufku | "Düzenli gelir ve sermayenin korunmasını önceliklendirmek" / 1-3 yıl |
| Öncelikler / açık kısıt | düzenli gelir, likiditeyi koruma, sınırlı dalgalanma / "yüksek riskli ürünlerden kaçınma" |
| Persona RM notu | "Mevcut portföyün mevduat yoğunluğunu azaltabilecek alternatifleri anlamak istiyor." |
| Durum | `state = ready`, `excluded_sources = []`, `questions = []`; 143 puanlanan, 1302 elenen seçenek |

`config_hash`, `config/decision.yaml` dosyasının kanonik JSON'unun sha256
özetinin ilk 12 karakteridir. `run_id`; `config_hash`, persona, `snapshot_id`,
hariç tutulan kaynaklar ve RM cevaplarının sha1 özetidir (`docs/decision.md`
bölüm 7). `created_at` bu özete girmez. Aynı girdiler her zaman aynı `run_id`
değerini verir. Bu kayıt bunu gösterir: pano özeti `2026-10-18T14:45:45` ve
ajan kararı `2026-10-18T14:59:06` zamanında bu `run_id` için yazıldı. Demo
provaları arasındaki sıfırlamalar çalıştırma dosyasını arşive taşıdı
(`data/reset-archive/`). Son kayıtta çalıştırma `22:49:56` zamanında aynı
girdilerle yeniden hesaplandı ve aynı kimliği aldı.

## 3. Öneri ve gerekçe (puanlama motoru)

**Seçenek:** NUROL PORTFÖY PARA PİYASASI (TL) FONU · fon kodu `PPN` ·
`option_id = fund:PPN` · `fund_kind = money_market` · `fx = false` · varlık
sınıfı `nakit_benzeri`. Motorun önerdiği ilk üç (`recommended`): `fund:PPN`,
`fund:OSD`, `fund:AIS`.

**Skor:** `0.740384201231856` (karttaki gösterim "skor 74"). Skor, ağırlık ×
değer parçalarının toplamıdır; aşağıdaki katkıların toplamı skorla aynıdır.

| Parça | Ağırlık (`effective_weights`) | Değer | Katkı (`score_parts`) | Gerekçe metni (kayıttaki gibi) | Kanıt |
|---|---|---|---|---|---|
| `return` | 0.14678899082568808 | 0.9085 | 0.1333505620881251 | Yıllık getiri %47.4, stopaj sonrası %39.1, enflasyon sonrası reel %+7.2 (1y); adayların %91'inden iyi. | `E72d070ec`, `Ede9af545`, `Eb39e0ab5` |
| `risk_fit` | 0.22018348623853212 | 1.0 | 0.22018348623853212 | Risk değeri 1/7; müşterinin risk aralığı 1-2. | `E0ae92a1e` |
| `liquidity` | 0.14678899082568808 | 1.0 | 0.14678899082568808 | Satış valörü 0 gün; likidite 1.0. | `E178811c9` |
| `income` | 0.22018348623853212 | 0.6 | 0.13211009174311927 | Düzenli gelir uygunluğu (ürün türüne göre): 0.6. | kanıt satırı yok (ürün türü `money_market`) |
| `principal` | 0.14678899082568808 | 0.8 | 0.11743119266055047 | Anapara koruma: 0.80. | `E0ae92a1e` (fon için max(0, 0.8 − 0.15 × (risk − 1))) |
| `quality` | 0.03669724770642202 | 0.8667 | 0.03180428134556575 | Fon büyüklüğü ve yatırımcı sayısı: adayların %87'inden iyi. | `Efeb58a01`, `E8a663bdb` |
| `allocation_gap` | 0.08256880733944955 | −0.5 | −0.04128440366972477 | Nakit benzeri payı persona metnine göre %75; Muhafazakâr model bandı %10–20. | kanıt satırı yok (persona metni, bölüm 6) |

`simplicity` ağırlığı 0.0'dır. "Değer" sütunu katkı / ağırlık olarak
hesaplandı. Çalıştırma dosyası kanıt kimliklerini seçenek düzeyinde
(`evidence_ids`, 10 kimlik) ve kısıt düzeyinde tutar. Parça ile kanıt
arasındaki eşlemeyi, kanıtın büyüklüğüne (`quantity`) göre biz yaptık.

`penalty:` ile başlayan parça yoktur; seçeneğe ceza uygulanmadı. Örnek:
`underperformance` cezasının karşılaştırma değeri, stopaj sonrası piyasa
mevduat oranıdır: 43.4 × (1 − 0.175) = 35.805 (`Ef6d8c9f2`, `E0382c2e7`). PPN
net getirisi (39.098565) bu değerin üstündedir. Ayrıca Muhafazakâr profilin
getiri iştahı 0.0'dır ve ceza bu iştahla çarpılır.

**Reel getiri** (`docs/decision.md` 4.1b): net = 47.3922 × (1 − 0.175) =
39.098565; reel = (1 + 0.39098565) / (1 + 0.2973) − 1 = %7.2216 (gösterim
"+%7,2"; kanıt `E72d070ec`, `Ede9af545`, `Eb39e0ab5`). `real_1y` değeri
çalıştırma dosyasında kayıtta yok; bu belge için kanıt değerlerinden yeniden
hesaplandı.

**Geçen kısıtlar:**

| Kural | Sonuç | Gerekçe | Kanıt |
|---|---|---|---|
| `not_buyable` | geçti | TEFAS'ta alıma açık. | `Eb1001265` |
| `risk_ceiling` | geçti | Risk değeri 1, müşterinin tavanı 2 içinde. | `E0ae92a1e` |

**Güven:** `confidence = 0.9` (en zayıf veri noktası `manual_entry` bayraklı;
çarpan 0.9). **Kararlılık:** `stability = 1.0` (`docs/decision.md` bölüm
15: her ağırlık ve her ceza üst sınırı tek tek × 0.8 ve × 1.2 yapıldı; 30
denemenin hepsinde öneri kuralı PPN'i yeniden önerdi).

**Neden önerilen ilk üçte (`docs/decision.md` bölüm 10).** Müşteri
Muhafazakâr'dır ve "çeşitlendirme" önceliği yoktur. Bu nedenle sınıf kuralı
uygulanmaz (`recommend.profiles = ["Dengeli", "Agresif"]`). Motor, mevduat
dışındaki ilk 20 seçeneği ürün türüne göre gruplar ve skor sırasıyla ilk üç
grubun başını önerir. Grup başları: `money_market` `fund:PPN`
(0.740384201231856), `debt` `fund:OSD` (0.7162764114418075), `participation`
`fund:AIS` (0.6817107196355162), `fund_of_funds` `fund:NBO`
(0.634866716438625). PPN, mevduat dışındaki tüm seçenekler içinde en yüksek
skora sahiptir. Aynı gruptaki `fund:ZBJ` (0.7374438270807311) ve `fund:GO6`
(0.7370475657205209) alternatif olarak kalır. Karşılaştırma için ING mevduatı
`deposit:ing_turuncu` skoru 0.4716038450429225'tir.

**Konuşma noktaları (motor, `talking_points`), PPN ile ilgili olanlar:**

- `best_alternative` "+%7,2": "NUROL PORTFÖY PARA PİYASASI (TL) FONU son bir yılda enflasyon sonrası +%7,2 getirdi; geçmiş getiri geleceği göstermez." (kanıt `E72d070ec`, `Eb39e0ab5`, `Ede9af545`)
- `access` "1 iş günü": "İlk üç öneride paraya erişim: 1 iş günü." (kanıt `E178811c9`, `E8018cdd1`, `Ea7cf75b1`; seçenek `fund:PPN`, `fund:OSD`, `fund:AIS`)

## 4. Dayandığı veriler

Seçeneğin `evidence_ids` listesindeki 10 kimliğin tümü, `snapshot_id =
20261018-132653-1991` satırlarından okunmuştur. İki kısıtın kanıtları
(`Eb1001265`, `E0ae92a1e`) bu listededir.

| Kanıt | Büyüklük | Değer + birim | as_of | Kaynak | source_url | fetched_at | Bayrak |
|---|---|---|---|---|---|---|---|
| `E72d070ec` | fund_return_1y (PPN) | 47.3922 pct | 2026-10-16 | tefas_web | https://www.tefas.gov.tr/tr/fon-getirileri | 2026-10-18T13:27:36.891898+03:00 | yok |
| `E0ae92a1e` | fund_risk_level (PPN) | 1.0 level | 2026-10-16 | tefas_web | https://www.tefas.gov.tr/tr/fon-getirileri | 2026-10-18T13:27:36.891898+03:00 | yok |
| `Eb1001265` | fund_buyable (PPN) | 1.0 flag | 2026-10-16 | tefas_detail | https://www.tefas.gov.tr/tr/fon-detayli-analiz/PPN | 2026-10-18T13:41:59.366857+03:00 | yok |
| `E178811c9` | fund_sell_valor_days (PPN) | 0.0 days | 2026-10-16 | tefas_detail | https://www.tefas.gov.tr/tr/fon-detayli-analiz/PPN | 2026-10-18T13:41:59.366857+03:00 | yok |
| `E8a663bdb` | fund_investor_count (PPN) | 10308.0 count | 2026-10-16 | tefas_detail | https://www.tefas.gov.tr/tr/fon-detayli-analiz/PPN | 2026-10-18T13:41:59.366857+03:00 | yok |
| `Efeb58a01` | fund_total_value (PPN) | 8867430816.95 TRY | 2026-10-16 | tefas_detail | https://www.tefas.gov.tr/tr/fon-detayli-analiz/PPN | 2026-10-18T13:41:59.366857+03:00 | yok |
| `Eb39e0ab5` | cpi_annual · TÜFE yıllık değişim (TÜİK) | 29.73 pct | 2026-09-30 | manual | https://www.sbb.gov.tr/enflasyon/ | 2026-10-18T13:27:35.829845+03:00 | manual_entry |
| `Ede9af545` | withholding_tax_rate · Yatırım fonu, para piyasası fonu | 17.5 pct | 2026-03-27 | manual | https://www.ziraatportfoy.com.tr/Documents/Banner//ZFG_PORTFOY_yat%C4%B1r%C4%B1m-fonlar%C4%B1-stopaj-oranlar%C4%B1-hakk%C4%B1nda-27-03-2026-pdf_328.pdf | 2026-10-18T13:27:35.829845+03:00 | manual_entry |
| `Ef6d8c9f2` | deposit_rate · TRY savings deposit rate up to 3M, weighted average (new deposits) | 43.4 pct | 2026-10-09 | evds | https://evds3.tcmb.gov.tr/ | 2026-10-18T13:27:07.166596+03:00 | yok |
| `E0382c2e7` | withholding_tax_rate · TL vadesiz mevduat ve günlük hesap (Turuncu Hesap türü) | 17.5 pct | 2026-06-20 | manual | https://www.yontemymm.com.tr/mali-aciklamalar/2026-041-tl-mevduat-hesaplarinda-uygulanan-stopaj-oranlarinin-suresi-uzatildi | 2026-10-18T13:27:35.829845+03:00 | manual_entry |

Veri 2026-10-18 Pazar günü çekildi. TEFAS satırlarının notu "as_of assumed =
previous business day" şeklindedir (`tefas_detail` satırlarında ek olarak "the
page shows no date"). Bu nedenle `as_of` önceki iş günüdür: 2026-10-16 Cuma.
`Ef6d8c9f2` ve `E0382c2e7`, `underperformance` cezasının karşılaştırma değeri
içindir (bölüm 3).

**Stopaj oranı nereden geliyor (kural 7).** Kodda stopaj oranı yoktur.
`config/decision.yaml` yalnızca hangi satırın kullanılacağını söyler. Oran,
elle doldurulan `data/inbox/manual/withholding_tax.csv` tablosundan gelir; her
satır kendi `source_url` ve `as_of` değerini taşır. `Ede9af545` notu:
"Individuals, CK 10041 (09.07.2025). CK 11734 (04.09.2026) sets 10 % for capital
companies (not individuals, unconfirmed). Secondary source". `E0382c2e7` notu:
"Vadesiz = 6 aya kadar band (research report 2026-10-10). Secondary source".
TÜFE notu: "TÜİK CPI September 2026, annual change, published 2026-10-05 (via
SBB). Cross-check of the EVDS row (docs/ingest.md I5, 2026-10-14)."

## 5. Varsayımlar, uyarılar ve teyit edilecekler

Varsayımlar (kayıttaki gibi):

1. Fon getirileri geçmiş getirilerdir; mevduat oranı bugünkü orandır.
2. Getiriler stopaj sonrası ve yıllık TÜFE'ye (%29.73, 2026-09-30) göre reel olarak hesaplandı.
3. Mevduat için 100.000-249.999 TL diliminin standart oranı kullanıldı (tutar bilinmiyor; hoş geldin oranı geçicidir).
4. Fonlarda likidite satış valöründen (valör yoksa ürün türünden), gelir uygunluğu ürün türünden türetildi.
5. Hisse senedi yoğun fonlarda stopaj %0'dır; ihtiyatlı olmak için para piyasası dışındaki tüm fonlarda 'diğer fonlar' oranı kullanıldı.
6. 32 günlük vade her ay yenilenir; oranlar değişebilir.
7. Risk değeri olmayan fonlarda aynı varlık sınıfındaki bilinen risk değerlerinin üst çeyreği (yukarı yuvarlanmış) kullanıldı.

Uyarı (yalnızca RM için, `audience = rm`):

- `deposit_vs_market`: "ING standart mevduat oranı (%23.00) piyasa ortalamasının (%43.40) 20.4 puan altında." (kanıt `Edfb610c6`, `Ef6d8c9f2`; seçenek `deposit:ing_turuncu`). `Edfb610c6`: ING Turuncu Hesap standart, 100.000-249.999 TL, 23.0 pct, `as_of` 2026-10-18, kaynak `ing_web`, https://www.ing.com.tr/tr/bilgi-destek/mevduat/mevduat-faiz-oranlari, `fetched_at` 2026-10-18T13:27:35.024407+03:00.

Teyit edilecek (`to_confirm`): "Müşterinin mevcut portföy dağılımını alın (şu
an tahmini senaryo)." Cevap bekleyen soru yoktur (`questions = []`).

Veri kalitesi notları: "manual: 6 değer "manual_entry" işaretli."; "3 değer
aralık dışında olduğu için kullanılmadı." (`E1107f15a`, `E5be1694d`,
`Edb058537`); "3 fonun TEFAS alım durumu kanıtlarda yok; bu fonlar alıma açık
sayıldı."; "Borsa ürünlerinden varant ve sertifikalar, borsada işlem gören
gayrimenkul ve girişim sermayesi fonları, tahvil ve eurobondlar kapsam
dışıdır."; "38 pay, yakın izleme veya nitelikli yatırımcı pazarında işlem
gördüğü için çıkarıldı (pazar kodu: S, W)."; "1292 serbest fon çıkarıldı
(yalnızca nitelikli yatırımcılar)."

## 6. Mevcut dağılım girdisi ve model bantlar

P01 dosyasında varlık dağılımı yoktur. RM bu kayıtta dağılım girmedi ve
tahmini onaylamadı: `holdings_input = null`. Bu nedenle `to_confirm` maddesi
açıktır. Mevcut payların kaynağı her satırda `current_source` alanındadır:
`persona_text` satırı persona metninden ("Varlığı TL mevduat ağırlıklı")
gelir. `profile` satırları meslek tablosunun `Emekli` satırından gelen
tahminlerdir. Yalnızca `active = true` olan satır `allocation_gap` ölçütüyle
puana girer.

| Varlık sınıfı | Bant (%) | Mevcut (%) | Aralık | `current_source` / `current_ref` | Fark (`gap`) | `active` | Sınıfın en iyi seçeneği | Not |
|---|---|---|---|---|---|---|---|---|
| `nakit_benzeri` | 10–20 | 75.0 | 60–90 | `persona_text` / `mevduat_agirlikli` | −55.0 | true | `fund:PPN` | — |
| `borclanma` | 60–70 | 8.1 | 3.1–13.1 | `profile` / `Emekli` | 51.9 | false | `fund:OSD` | — |
| `hisse` | 10–20 | 3.7 | 0.0–8.7 | `profile` / `Emekli` | 6.3 | false | `fund:PGD` | — |
| `altin_doviz` | 5–10 | 9.5 | 4.5–14.5 | `profile` / `Emekli` | 0.0 | false | `fund:AGC` | `negative_real` |
| `dengeli` | — (bant yok) | 3.7 | 0.0–8.7 | `profile` / `Emekli` | yok | false | `fund:KCV` | — |

Bantların kaynağı her satırda "Ata Yatırım, 28.04.2026" (`inferred = false`).
`allocation_notes`: "Dosyaya göre varlık TL mevduat ağırlıklı: nakit benzeri
bandı aşılıyor olabilir." PPN nakit benzeri sınıfındadır ve bu sınıf bandın
üstündedir. Bu nedenle PPN'in `allocation_gap` katkısı eksidir (bölüm 3).

## 7. Ajan kararı

Kaynak: `data/agent/Rb5470b4f25.json` (aynı içerik
`data/agent/Rb5470b4f25.n10.nomarks.json` adıyla da saklıdır).

| Alan | Değer |
|---|---|
| `state` | `done` (`fallback_reason = ""`, yedek karara düşülmedi) |
| Model / istem sürümü | `claude-sonnet-5-5` / `a3` |
| Maliyet | `cost_usd = 0.073132` (maliyet defteri `data/agent/costs.jsonl`: `2026-10-18T14:59:06.331345+03:00`, 0.073132) |
| `created_at` | `2026-10-18T14:59:06.335718+03:00` |
| `n_candidates` | 10 |
| `marks_hash` | `""` (karar, RM'in ✓/✗ işaretlerinden önce verildi) |
| Motorun ilk üçü (`engine_top3`) | `fund:PPN`, `fund:OSD`, `fund:AIS` |
| Ajanın seçimi | `fund:PPN`, `fund:OSD`, `fund:ZBJ` |
| Çıkarılan | `fund:AIS` |

**Adımlar (`nodes`):**

| Adım | Başlangıç → bitiş | Maliyet | Notlar (kayıttaki gibi) |
|---|---|---|---|
| `adaylar` · Adaylar | 14:58:39.370920 → 14:58:39.371922 | 0.0 | "Motorun en iyi 10 adayı (ING mevduatları hariç): PPN, OSD, AIS, ZBJ, GO6, YBS, IST, RBT, NSP, NBO." |
| `arastirma` · Ajan araştırması | 14:58:39.371922 → 14:58:57.891738 | 0.19 | "10/10 ürün araştırıldı."; alt adım `arastirma:fund:PPN`: "4 bulgu, 0 haber." (0.019) |
| `analiz` · Ajan analizi | 14:58:58.139758 → 14:59:06.335718 | 0.073132 | alt adım `analiz:1` "Karar önerisi (1. deneme)": "Amaç: Nihai karar", "Kontrollerden geçti." |
| `kontrol` · Kontrol | 14:59:06.332187 → 14:59:06.335718 | 0.0 | "1. öneri: tüm kontroller geçti." |
| `karar` · Karar | 14:59:06.335718 | 0.0 | "Ajanın seçimi: PPN, OSD, ZBJ." ve özet |

Ajanın araç çağrılarının `amac` notu "Amaç: …" satırlarıdır. Bu kararda ajan
yalnızca bir araç çağırdı: nihai karar önerisi ("Amaç: Nihai karar").
Karşılaştırma veya ek araştırma çağrısı yoktur. Kod denetimi ilk öneride
sorun bulmadı.

**PPN için ajanın gerekçeleri ve atıfları:**

| Gerekçe (kayıttaki gibi) | Atıf | Atfın karşılığı |
|---|---|---|
| "Nurol Portföy Para Piyasası (TL) Fonu risk düzeyi 1 ile müşterinin risk aralığına uyuyor, satış valörü 0 gün; likidite ve sermayeyi koruma önceliğine uygun." | `puan:risk_fit`, `puan:liquidity` | skor parçaları 0.22018348623853212 (`E0ae92a1e`) ve 0.14678899082568808 (`E178811c9`) |
| "Yıllık getirisi %47,4; enflasyon sonrası reel getiri %7,2. Geçmiş getiri gelecek için güvence değildir." | `E72d070ec` | fund_return_1y 47.3922 pct (bölüm 4) |

PPN için `labels = []`, `uses_estimate = false`, `uses_web = false`: ajan PPN
gerekçesinde web bulgusu veya tahmini dağılım kullanmadı. Karşılaştırma için
OSD gerekçesi `portfoy:borclanma` atfını ve kodun eklediği "(tahmini dağılıma
göre)" etiketini taşır.

**Çıkarılan seçenek:** `fund:AIS` · "Ak Portföy Katılım Fonu düzenli gelir
uygunluğu daha düşük (0,4) ve getirisi %46,2 ile Ziraat Başak'ın gerisinde
kaldı; üçüncü sırayı ona bıraktı." (atıf `puan:income`, `puan:return`).

**Özet:** "Üç düşük riskli fon seçildi: Nurol para piyasası, Osmanlı özel
sektör borçlanma ve Ziraat Başak. Likidite ve sermaye koruma öncelikli;
borçlanma fonu mevduat yoğunluğunu çeşitlendirmeye yardım edebilir. Getiri
güvencesi yoktur."

**Kayıtlı kararın tekrar kullanılması.** Son kayıtta ajan
`2026-10-18T22:51:49.148207+03:00` zamanında başlatıldı (`agent_started`, `n =
10`, `marks_ok = 0`, `marks_wrong = 0`). Aynı `run_id`, aday sayısı ve işaret
özeti için kayıtlı karar vardı. Bu nedenle servis modeli yeniden çağırmadı ve
14:59:06 kararını geri verdi. Maliyet defterinde bu çalıştırma için tek satır
vardır.

## 8. Web araştırması bulguları ve RM işaretleri

**Ürün araştırması:** `data/research/products/fund_PPN-TR-20261018-v2.json` ·
sağlayıcı `exa` · `version = 2` · `created_at =
2026-10-18T13:33:24.736713+03:00` · `cost_usd = 0.019` · `news_days = 90`,
`news = []` · denetimler: "3 news items without a valid source dropped", "1
bullets dropped (known facts)". Aynı gün aynı ürün için kayıtlı sonuç
kullanılır. Maliyet defterinde (`data/research/costs.jsonl`) PPN için
2026-10-18 tarihli tek ürün satırı `13:33:29.731003` zamanlıdır (0.019).

| Bulgu | Konu | Metin (kayıttaki gibi) | Kaynak | Tarih | RM işareti |
|---|---|---|---|---|---|
| `F8c751d04` | strateji | "Fon, kısa vadeli ve likit TL para-sermaye piyasası araçlarına yatırım yapar; ağırlıklı olarak mevduat, repo ve borçlanma araçlarını kullanır." | cdn.nurolportfoy.com.tr: `310-ppn-tl--izahnamesi-04-02-2025.pdf`, `FonTanitim/PPN_TMF.pdf` | kayıtta yok | ✓ `ok`, `2026-10-18T22:52:47.427410+03:00` |
| `F38232286` | strateji | "Portföyün tamamı, vadesine en fazla 184 gün kalmış araçlara; ağırlıklı ortalama vade en fazla 45 gün olacak şekilde yatırılır." | cdn.nurolportfoy.com.tr: `310-ppn-tl--izahnamesi-04-02-2025.pdf` | kayıtta yok | ✗ `wrong`, `2026-10-18T22:52:49.932279+03:00` |
| `F564b8ff4` | yonetici_sirket | "Şirket, kolektif portföy yöneticiliği ilkeleri ve ilgili portföy sınırlamaları çerçevesinde faaliyet gösterir." | cdn.nurolportfoy.com.tr: `310-ppn-tl--izahnamesi-04-02-2025.pdf` | kayıtta yok | işaret yok |
| `F689fd35d` | dikkat | "Fonun unvanı, SPK izniyle 2022’de Nurol Portföy Para Piyasası (TL) Fonu olarak değiştirilmiştir." | cdn.nurolportfoy.com.tr: `310-ppn-tl--izahnamesi-04-02-2025.pdf` | kayıtta yok | işaret yok |

Bulguların hepsinde `confidence = high` yazar. Kaynakların `published`
alanı ve bulguların `date` alanı boştur. Ekran bu bulguları "Web kaynağı,
doğrulanmamış" etiketiyle gösterir. İşaretler `data/research/marks/20261018.json`
dosyasında `run_id` ve `option_id` ile saklanır. İşlem kaydı da her işareti
`research_marked` olarak yazar (`section = highlight`, `topic = strateji`).
Bir sonraki ajan çalıştırmasında ✗ işaretli bulgu ajana verilmez. Bu kayıttaki
ajan kararı işaretlerden önce verildiği için (`marks_hash = ""`, bölüm 7)
işaretler bu kararı değiştirmedi.

**RM sorusu:** `data/research/questions/Rb5470b4f25-TR-v2-9d7706b089ca.json` ·
soru "Nurol Portföy Para Piyasası fonunun son dönemdeki önemli gelişmeleri
neler?" · sağlayıcı `exa` · `created_at = 2026-10-18T22:32:26.259961+03:00` ·
`cost_usd = 0.007` · `checks = []`.

| Bulgu | Metin (kayıttaki gibi) | Kaynak | RM işareti |
|---|---|---|---|
| `Fae98109a` | "16 Ekim 2026 itibarıyla fonun büyüklüğü 8,9 milyar TL, yatırımcı sayısı ise 10.308’dir." | https://fonalfa.com/fon/PPN/ | işaret yok |
| `F1d9f4e53` | "Fondan son bir ayda 3,8 milyar TL net çıkış gerçekleşmiş olup, üst üste 22 işlem günü net çıkış yaşanmıştır." | https://fonalfa.com/fon/PPN/ | işaret yok |
| `Ff9788495` | "Fonun 1 yıllık getirisi %47,39 seviyesinde gerçekleşmiştir." | https://fonalfa.com/fon/PPN/ | işaret yok |
| `F937842c0` | "Fon yönetimi, portföy dağılım raporlarını düzenli olarak KAP üzerinden yayımlamaya devam etmektedir." | https://cdn.nurolportfoy.com.tr/FonBulteni/2026-10-16.pdf, https://fon.org.tr/spk-bulteni/kurum/nurol-portfoy | işaret yok |

Soru bu gün iki kez soruldu (`research_question`, 22:32:26.265537 ve
22:52:59.514644; ikisinde de `refused = false`, `findings = 4`). İkinci
soruda kayıtlı cevap geri verildi. Maliyet defterinde bu soru için tek satır
vardır (`2026-10-18T22:32:26.260962+03:00`, 0.007). Biz bu bulguları kanıtlarla
elle karşılaştırdık: `Ff9788495` (%47,39) `E72d070ec` (47.3922) ile,
`Fae98109a` (8,9 milyar TL; 10.308 yatırımcı) `Efeb58a01` (8867430816.95 TRY)
ve `E8a663bdb` (10308) ile uyumludur. Bulgular yine de işaretsizdir; ekran
onları "doğrulanmamış" gösterir.

## 9. RM onayı

| Alan | Değer |
|---|---|
| `rm_status` | `approved` |
| `rm_selected` | `fund:PPN`, `fund:OSD`, `fund:ZBJ` (ajanın üçlüsü; motorun `fund:AIS` önerisi yerine `fund:ZBJ`) |
| `rm_note` | "Düzenli gelir ve sermaye koruması odaklı üç seçenek konuşulacak.Aylık gelir ihtiyacını sor." (kayıttaki gibi) |
| `rm_option_notes` | boş (`{}`) |
| `rm_decided_at` | `2026-10-18T22:53:18.116982+03:00` |
| İşlem kaydı `decision_approved` | `2026-10-18T22:53:19.019858+03:00` · `engine_top3` PPN, OSD, AIS · `agent_top3` PPN, OSD, ZBJ · `agent_state = done` · `selected` PPN, OSD, ZBJ · `note` "Düzenli gelir ve sermaye koruması odaklı üç seçenek konuşulacak." · `test_run = false` · `persona_changes = []` · `resolutions = []` · `ai_check = done` |
| Profil çelişkileri (`Rb5470b4f25.resolutions.json`) | `resolutions = []`, `ai_check = "done"`, `at = 2026-10-18T22:53:18.116982+03:00` |
| Kim onayladı | kayıtta RM kimliği alanı yok; bu kayıtta onayı demo betiği verdi (üstteki not) |

Onay anında RM notu yalnızca ilk cümleydi. "Aylık gelir ihtiyacını sor."
cümlesi onaydan sonra eklendi (`notes_saved`,
`2026-10-18T22:54:37.793620+03:00`). Çalıştırma dosyası son notu tutar.

Profil kontrolü: onay, her profil çelişkisi için RM'in gerekçeli teyidini ister
(onay kilidi). Bu kayıtta yapay zekâ kontrolü tamamlandı (`ai_check = done`)
ve çözülecek çelişki yoktu (`resolutions = []`). Persona düzenlenmedi
(`persona_changes = []`).

## 10. Görüşme metni

| Alan | Değer |
|---|---|
| Dosya | `data/narratives/Rb5470b4f25-TR-n12-claude-sonnet-5-5-75cd8496de.json` |
| Model / kaynak | `claude-sonnet-5-5` (`source = llm`) |
| Prompt sürümü | `n12` |
| Doğrulayıcı sonucu | `checks = []` (bulgu yok; maliyet defterinde `attempt = 1`, `findings = []`) |
| Maliyet | `cost_usd = 0.0466015` (girdi 32, çıktı 2588, önbellek yazma 8263 token) |
| Taslak zamanı | `created_at = 2026-10-18T22:53:40.008562+03:00` (RM onayından 22 saniye sonra) |
| Durum | `status = draft`, `approved_at = null` |
| RM düzenlemesi | blok `teklif_metni`, `2026-10-18T22:54:03.514172+03:00` (`text_block_edited`, `findings = []`); `Rb5470b4f25-TR-edits.json`: `rm_edits = {teklif_metni: …}`, `edit_checks = {}` |
| İhtiyaç etiketleri (`need_tags`) | `fund:PPN`: "düzenli gelir", "likiditeyi koruma" |

**Metin onayı yoktur; bu tasarım gereğidir.** 2026-10-15 tarihinden beri
(`docs/web-ui.md` W19) ekranda "Metni onayla" düğmesi yoktur. RM'in onay
noktası önerinin onayıdır ("Onayla ve metni hazırla"); metin yalnızca onaylı
çalıştırma için yazılır. RM metni blok blok düzenler veya siler. Düzenlenen
blok yeniden denetlenir (`edit_checks`). Kart, RM düzenlemeleriyle metnin o
anki hâlini yazar. Engelleyici bir kural bulgusu açıksa kart metni almaz ve
kart indirilemez. Bu nedenle `approved_at` alanı boştur.

Doğrulayıcı koddur, LLM değildir (`docs/narrator.md`). Sayılar olgu paketiyle
eşleşir. Yalnızca seçilen seçenekler ve grup alternatifleri adlandırılır.
Yasak ifadeler yoktur. Öneri, alternatif ve dikkat cümlelerinin her birinde
geçerli bir atıf vardır. Metin, yatırım tavsiyesi olmadığını söyler ("Bu metin
RM'in görüşme hazırlığı içindir; yatırım tavsiyesi değildir.").

**RM düzenlemesi (`teklif_metni`):**

- Önce: "Düzenli gelir ve sermayenizin korunması sizin için önemli. Varlığınız ağırlıklı olarak TL mevduatta duruyor. Bu yoğunluğu azaltabilecek üç seçeneği birlikte değerlendirelim."
- Sonra: "Düzenli gelir ve sermayenizin korunması sizin için önemli.↵Varlığınız ağırlıklı olarak TL mevduatta duruyor.↵Bu yoğunluğu azaltabilecek üç seçeneği birlikte değerlendirelim. Görüşmede bu hedefi birlikte netleştirebiliriz." (↵ = satır sonu)

**`fund:PPN` için cümleler:**

| Bölüm | Cümle | Seçenek | Kanıt |
|---|---|---|---|
| `oneriler` | "Düzenli gelir beklentisine uygun; paraya aynı gün erişim sağlar, orta düzeydeki likidite ihtiyacını karşılar." | `fund:PPN` | `E178811c9` |
| `dikkat` | "Seçilen fonların getirisi faiz değişimine bağlıdır." | `fund:PPN`, `fund:ZBJ` | `E178811c9`, `Ed5d6ce54` |
| `dikkat` | "Mevduat gibi anapara güvencesi yoktur." | `fund:PPN`, `fund:ZBJ` | `E178811c9`, `Ed5d6ce54` |
| `dikkat` | "Geçmiş getiriler gelecekteki getirileri göstermez." | `fund:PPN`, `fund:OSD`, `fund:ZBJ` | yok (yalnızca seçenek atfı) |
| `talking_points` · Nakit ağırlığı | "Müşterinin nakit benzeri payı %75; model bandı %10-20, yani band üstünde." | `fund:PPN`, `fund:ZBJ`, `fund:OSD` | yok (sayılar dağılım satırından, bölüm 6) |
| `talking_points` · Reel getiri | "NUROL fonu son bir yılda enflasyon sonrası +%7,2 getirdi." | `fund:PPN` | `E72d070ec` |

`Ed5d6ce54` ZBJ'nin satış valörüdür: 0.0 days, `as_of` 2026-10-16,
`tefas_detail`, https://www.tefas.gov.tr/tr/fon-detayli-analiz/ZBJ,
`fetched_at` 2026-10-18T13:41:59.366857+03:00, bayrak yok. "Reel getiri"
cümlesi yalnızca getiri kanıtını atfeder. Hesap TÜFE (`Eb39e0ab5`) ve stopaj
(`Ede9af545`) satırlarını da kullanır (bölüm 3).

Pano özeti (brief, `Rb5470b4f25-TR-brief-b1-claude-haiku-5-5.json`): model
`claude-haiku-5-5`, prompt `b1`, `checks = []`, `cost_usd = 0.000449375`,
`created_at = 2026-10-18T14:45:45.814211+03:00`. Özet onaydan önce, motorun
ilk üçü için yazıldı; atıfları `fund:PPN`, `fund:OSD`, `fund:AIS`,
`E72d070ec`, `E47e314bf`, `E00c74385`, `E0ae92a1e`, `Eec53b88b`, `Eec4e10d1`.

## 11. Kart

`data/cards/Rb5470b4f25.md` yalnızca onaylı çalıştırma için yazılır. Bu kart en
son RM notu kaydedildiğinde yazıldı (dosya zamanı 2026-10-18 22:54:37). Kartın
üst satırları:

```
Çalıştırma Rb5470b4f25 · veri 20261018-132653-1991 · 2026-10-18 22:49

RM onayı: 2026-10-18 22:53
```

PPN satırları:

```
- **PPN · NUROL PORTFÖY PARA PİYASASI (TL) FONU · Para Piyasası**
  - skor 74 · güven %90 · istikrar %100
  - Risk uyumu (+22): Risk değeri 1/7; müşterinin risk aralığı 1-2.
  - Likidite (+15): Satış valörü 0 gün; likidite 1.0.
  - Getiri (+13): Yıllık getiri %47.4, stopaj sonrası %39.1, enflasyon sonrası reel %+7.2 (1y); adayların %91'inden iyi.
```

"Ajan kararı" bölümünün son satırları:

```
- RM seçimi: PPN · NUROL PORTFÖY PARA PİYASASI (TL) FONU, OSD · OSMANLI PORTFÖY ÖZEL SEKTÖR BORÇLANMA ARAÇLARI FONU, ZBJ · ZİRAAT PORTFÖY BAŞAK PARA PİYASASI (TL) FONU
- Model claude-sonnet-5-5 · istem a3 · maliyet $0.073
```

Kart ayrıca müşteri profilini, veri kalitesi notlarını, varsayımları,
kaynakları, RM notunu, ajanın gerekçelerini ve görüşme metnini RM
düzenlemesiyle birlikte taşır. "Metin onayı" satırı yoktur, çünkü ayrı bir
metin onayı yoktur (bölüm 10). **Müşteriye hiçbir şey gitmedi.** Uygulama
yalnızca RM'in bilgisayarında (`127.0.0.1`) çalışır ve API'de müşteriye
gönderim uç noktası yoktur.

## 12. RM işlem kaydı

`data/logs/rm-actions/2026-10-18.jsonl` dosyasının her satırı `ts`, `action`,
`run_id`, `persona_id`, `snapshot_id` ve `versions` alanlarını taşır. Son demo
kaydının satırları (kayıttan önce `POST /api/reset` önceki kayıtları
`data/reset-archive/20261018-224954/` altına taşıdı):

| `ts` | `action` | Ayrıntı (`details`) |
|---|---|---|
| 22:49:58.394629 | `run_opened` | `test_run = false`, `state = ready` |
| 22:51:49.148207 | `agent_started` | `n = 10`, `marks_ok = 0`, `marks_wrong = 0` |
| 22:52:47.434409 | `research_marked` | `F8c751d04`, `fund:PPN`, `mark = ok` |
| 22:52:49.941272 | `research_marked` | `F38232286`, `fund:PPN`, `mark = wrong` |
| 22:52:59.514644 | `research_question` | `refused = false`, `findings = 4` |
| 22:53:19.019858 | `decision_approved` | bölüm 9 |
| 22:54:03.514172 | `text_block_edited` | `block_id = teklif_metni`, `before`/`after` (bölüm 10), `findings = []` |
| 22:54:37.793620 | `notes_saved` | `note` = son RM notu, `option_notes = {}` |

Aynı gün bu çalıştırma için 10 `decision_approved` satırı vardır (19:50:53 ile
22:53:19 arasında). Hepsi demo provalarıdır ve aynı seçimi taşır. Bu belge son
kaydı kullanır. `python -m rmprep feedback` komutu bu dosyalardan geri bildirim
raporu üretir.

## 13. Kayıttaki boşluklar

- Onaylar ve düzenlemeler demo betiğiyle yapıldı, bir RM tarafından yapılmadı (üstteki not).
- Kayıtta RM kimliği alanı yoktur.
- Görüşme metninin `approved_at` alanı boştur. Bu durum W19 tasarımının sonucudur; RM onayı karar onayıdır (bölüm 10).
- Ajan kararı RM'in işaretlerinden önce verildi (`marks_hash = ""`). ✓/✗ işaretleri bu kararı etkilemedi.
- Skor parçaları kanıt kimliğini parça düzeyinde tutmaz. Bölüm 3'teki eşleme kanıtın büyüklüğüne göre yapıldı.
- `real_1y` çalıştırma dosyasında yoktur; bölüm 3'te yeniden hesaplandı.
- Mevcut dağılım RM tarafından girilmedi veya onaylanmadı (`holdings_input = null`); `to_confirm` maddesi açıktır.
- Web bulgularının kaynak yayım tarihi ve bulgu tarihi boştur. RM sorusunun dört bulgusu işaretsizdir.

## 14. Nasıl doğrulanır

**Uygulamada:**

1. P01 müşterisini `20261018-132653-1991` anlık görüntüsü ile açın (aynı config ile `run_id = Rb5470b4f25` olur).
2. "NUROL PORTFÖY PARA PİYASASI (TL) FONU" satırında bir sayının yanındaki "K" işaretine basın.
3. Kanıt penceresinde değeri, kaynağı, değer tarihini (`as_of`), alınma zamanını (`fetched_at`), kanıt kimliğini ve bayrakları okuyun.
4. Kaynak sayfayı görmek için "Kaynağı aç" bağlantısına basın.

**API'de** (sunucu açıkken): `GET /api/evidence/20261018-132653-1991/E72d070ec`
(tek kanıt, `fetched_at` dahil); `GET /api/runs/Rb5470b4f25` (çalıştırma);
`GET /api/runs/Rb5470b4f25/agent` (ajan kararı); `GET
/api/runs/Rb5470b4f25/research` (web bulguları ve işaretler); `GET
/api/runs/Rb5470b4f25/card.md` (kart).

**Veritabanında** (yalnızca okuma):

```python
import duckdb
con = duckdb.connect("data/evidence.duckdb", read_only=True)
con.execute(
    "select id, quantity, entity, value, unit, as_of, source, source_url,"
    " cast(fetched_at as varchar), raw_ref, flags, note from datapoints"
    " where snapshot_id = '20261018-132653-1991' and id = 'E72d070ec'"
).fetchall()
```

Aynı satırlar `data/export/20261018-132653-1991.parquet` dosyasında da vardır.

**Ham dosyada:** `raw_ref` yolundaki dosyayı açın ve sha256 özetini
`data/snapshots/20261018-132653-1991/manifest.json` ile karşılaştırın.
Örnekler:

- `E72d070ec` → `…/payloads/tefas_web/fon-getirileri.html#fonKodu=PPN;field=getiri1y` (`598fa9bd5df8551bffedea16e70baa5500a49a4f5549de315ac2c023056a1ba7`)
- `E178811c9` → `…/payloads/tefas_detail/PPN.html.gz#fonKodu=PPN;field=profilData.fonSatisValor` (`faf1edfb878857f9fc8eaf012f273843635bb873403a34a41756eb7747d07104`)
- `Ede9af545` → `…/payloads/manual/withholding_tax.csv#row=6` (`c8f30b00895554c664d38756d4129d733e5c2f8acc3a51a5079ff4fd5fc0e3dd`)
- `Eb39e0ab5` → `…/payloads/manual/cpi_annual.csv#row=2` (`7a2d2be81fe85ebbf4eba21bdf81cefb1cd799724aa131724379e9ed48af5704`)

Manifestteki kaynak durumu: bist_bulletin `ok`, evds `ok`, ing_web `ok`,
isbank_web `ok`, manual `ok`, tefas `skipped`, tefas_byf `ok`, tefas_detail
`ok`, tefas_web `ok`, ziraat_web `ok`.
