# Kanıt kaydı örneği

> Teslimat 6 · Taslak (2026-10-13) · Kaynak: kayıtlı P02 çalıştırması
> `R2b9ee9ca01` (`data/runs/R2b9ee9ca01.json`), onaylı görüşme metni
> (`data/narratives/R2b9ee9ca01-TR-approved.json`), kart
> (`data/cards/R2b9ee9ca01.md`), veri anlık görüntüsü `20261010-183835-6813`,
> kanıt deposu `data/evidence.duckdb`. Tüm değerler kayıttan aynen
> kopyalanmıştır; kayıtta olmayan bilgi "kayıtta yok" olarak işaretlidir.
>
> **Not:** Bu örnek kayıt, uçtan uca akışı göstermek için bir betikle
> oluşturuldu; RM onayı ve metin onayı arayüzdeki aynı API çağrılarıyla, ancak
> otomatik verildi (onay zamanları birkaç saniye aralıklıdır). Gerçek kullanımda
> ve demoda onayı RM ekrandan verir; kayıt yapısı aynıdır.

## 1. Bu kayıt neyi gösteriyor

Bu kayıt, P02 müşterisi için önerilen ilk ürünün (BV PORTFÖY PARA PİYASASI
(TL) FON, `fund:BVF`) tam karar zincirini gösterir: **veri → kural → skor →
öneri → model dağılım → görüşme metni → RM onayı → metin onayı**. Her veri
noktasının bir kanıt kimliği (`E…`), kaynağı, değer tarihi (`as_of`) ve alınma
zamanı (`fetched_at`) vardır. Kurallar, skor parçaları ve metin cümleleri bu
kimlikleri taşır. RM onayı ve metin onayı aynı `run_id` altında saklanır.

## 2. Çalıştırma kimliği

| Alan | Değer |
|---|---|
| `run_id` | `R2b9ee9ca01` |
| `snapshot_id` | `20261010-183835-6813` |
| `config_hash` | `9279d0a6c847` |
| `created_at` (Europe/Istanbul) | `2026-10-13T01:03:39.784910+03:00` |
| Persona | `P02` · İhracatçı şirket sahibi, 48 yaş, Dengeli, "Döviz geliri bulunuyor" |
| Öncelikler / açık kısıt | kur riskini yönetme, çeşitlendirme, erişilebilir likidite / "döviz maruziyetini gerekçesiz artırmama" |
| Durum | `state = ready`, `excluded_sources = []`; 307 puanlanan, 509 elenen seçenek |

`config_hash`, `config/decision.yaml` dosyasının kanonik JSON'unun sha256
özetinin ilk 12 karakteridir. `run_id`; `config_hash`, persona, `snapshot_id`,
hariç tutulan kaynaklar ve RM cevaplarının sha1 özetidir (`docs/decision.md`
bölüm 7). `created_at` bu özete girmez. Aynı girdiler her zaman aynı `run_id`
değerini verir. Örnek: brief dosyası `2026-10-13T00:48:12.463226+03:00`
zamanında aynı `run_id` için yazıldı; çalıştırma daha sonra aynı girdilerle
tekrar kaydedildi ve aynı kimliği aldı.

## 3. Öneri ve gerekçe

**Seçenek:** kısa ad "Para Piyasası (TL)", ihraççı "BV Portföy" · tam ad BV
PORTFÖY PARA PİYASASI (TL) FON · fon kodu `BVF` · `option_id = fund:BVF` ·
`fund_kind = money_market` · `fx = false` · varlık sınıfı `nakit_benzeri`.
Önerilen ilk üç (`recommended`): `fund:BVF`, `fund:NJR`, `fund:IRF`.

**Skor:** `0.7751011131443154` (ağırlık × değer parçalarının toplamı; fark 0.0).

| Parça | Değer | Gerekçe metni (kayıttaki gibi) |
|---|---|---|
| `return` | 0.3146117203985317 | Yıllık getiri %48.6, stopaj sonrası %40.1, enflasyon sonrası reel %+8.0 (1y); adayların %93'inden iyi. |
| `risk_fit` | 0.10169491525354785 | Risk değeri 2/7; müşterinin risk aralığı 3-5. |
| `liquidity` | 0.2033898305070957 | Satış valörü 0 gün; likidite 1.0. |
| `income` | 0.061016949152128706 | Düzenli gelir uygunluğu (ürün türüne göre): 0.6. |
| `principal` | 0.06610169491480611 | Anapara koruma: 0.65. |
| `quality` | 0.02828600291820536 | Fon büyüklüğü ve yatırımcı sayısı: adayların %56'inden iyi. |

`penalty:` ile başlayan parça yoktur; seçeneğe ceza uygulanmadı.

**Reel getiri** (`docs/decision.md` 4.1b): net = 48.5786 × (1 − 0.175) =
40.077345; reel = (1 + 0.40077345) / (1 + 0.2973) − 1. `real_1y` çalıştırma
dosyasında kayıtta yok; `rmprep.decision.display.facts_of` ile salt okunur
yeniden hesaplandı: `7.976061820704539` (gösterim "+%8,0"; kanıt `Eb8143c0e`,
`Ede9af545`, `Eb39e0ab5`).

**Geçen kısıtlar:**

| Kural | Sonuç | Gerekçe | Kanıt |
|---|---|---|---|
| `not_buyable` | geçti | TEFAS'ta alıma açık. | `E0dcd47b0` |
| `risk_ceiling` | geçti | Risk değeri 2, müşterinin tavanı 5 içinde. | `Ea80b47f6` |

**Güven:** `confidence = 0.9` (en zayıf veri noktası `needs_check` veya
`manual_entry`; çarpan 0.9). **Kararlılık:** `stability = 1.0` (ağırlıklar ve
ceza üst sınırları ±%20 değiştirildiğinde seçenek her denemede ilk 20 içinde
kaldı).

**Neden önerilen ilk üçte (D19, `docs/decision.md` bölüm 10).** Müşteri
Dengeli'dir ve "çeşitlendirme" önceliği vardır. Bu nedenle sınıf kuralı
uygulanır: her varlık sınıfından en fazla 1, `nakit_benzeri` sınıfından en
fazla 1 seçenek, skor sırasıyla. `fund:BVF`, mevduat dışındaki tüm seçenekler
içinde en yüksek skora sahiptir (sonraki `fund:EIL` 0.7743740815825517, o da
nakit benzeri). Bu nedenle ilk seçimdir ve nakit benzeri payını kullanır;
reel getirisi pozitif olduğu için `recommend.min_real_return` (0.0) koşulunu
geçer. Sonraki seçimler başka sınıflardandır: `fund:NJR` (`borclanma`,
0.7368726748391465) ve `fund:IRF` (`dengeli`, 0.7177267791927738; gerekçesinde
"Çeşitlendirme: farklı varlık sınıfından en iyi seçenek." yazar). BVF
gerekçesinde bu ifade yoktur, çünkü düz skor sırasında da birinci olur.

## 4. Dayandığı veriler

Seçeneğin `evidence_ids` listesindeki 10 kimliğin tümü, `snapshot_id =
20261010-183835-6813` satırlarından okunmuştur. İki kısıtın kanıtları
(`E0dcd47b0`, `Ea80b47f6`) bu listededir.

| Kanıt | Büyüklük | Değer + birim | as_of | Kaynak | source_url | fetched_at | Bayrak |
|---|---|---|---|---|---|---|---|
| `Eb8143c0e` | fund_return_1y (BVF) | 48.5786 pct | 2026-10-09 | tefas_web | https://www.tefas.gov.tr/tr/fon-getirileri | 2026-10-10T18:38:37.587166+03:00 | needs_check |
| `Ea80b47f6` | fund_risk_level (BVF) | 2.0 level | 2026-10-09 | tefas_web | https://www.tefas.gov.tr/tr/fon-getirileri | 2026-10-10T18:38:37.587166+03:00 | needs_check |
| `E0dcd47b0` | fund_buyable (BVF) | 1.0 flag | 2026-10-09 | tefas_detail | https://www.tefas.gov.tr/tr/fon-detayli-analiz/BVF | 2026-10-10T18:52:15.632710+03:00 | needs_check |
| `Ee9dc76cc` | fund_sell_valor_days (BVF) | 0.0 days | 2026-10-09 | tefas_detail | https://www.tefas.gov.tr/tr/fon-detayli-analiz/BVF | 2026-10-10T18:52:15.632710+03:00 | needs_check |
| `E4cd2b07b` | fund_investor_count (BVF) | 647.0 count | 2026-10-09 | tefas_detail | https://www.tefas.gov.tr/tr/fon-detayli-analiz/BVF | 2026-10-10T18:52:15.632710+03:00 | needs_check |
| `E2f06fc68` | fund_total_value (BVF) | 1667959437.87 TRY | 2026-10-09 | tefas_detail | https://www.tefas.gov.tr/tr/fon-detayli-analiz/BVF | 2026-10-10T18:52:15.632710+03:00 | needs_check |
| `Eb39e0ab5` | cpi_annual · TÜFE yıllık değişim (TÜİK) | 29.73 pct | 2026-09-30 | manual | https://www.sbb.gov.tr/enflasyon/ | 2026-10-10T18:38:36.881130+03:00 | manual_entry |
| `Ede9af545` | withholding_tax_rate · Yatırım fonu, para piyasası fonu | 17.5 pct | 2026-03-27 | manual | https://www.ziraatportfoy.com.tr/Documents/Banner//ZFG_PORTFOY_yat%C4%B1r%C4%B1m-fonlar%C4%B1-stopaj-oranlar%C4%B1-hakk%C4%B1nda-27-03-2026-pdf_328.pdf | 2026-10-10T18:38:36.881130+03:00 | manual_entry |
| `E9cb9f7ad` | deposit_rate · TRY savings deposit rate up to 3M, weighted average (new deposits) | 43.82 pct | 2026-10-02 | evds | https://evds3.tcmb.gov.tr/ | 2026-10-10T18:38:36.865736+03:00 | yok |
| `E0382c2e7` | withholding_tax_rate · TL vadesiz mevduat ve günlük hesap (Turuncu Hesap türü) | 17.5 pct | 2026-06-20 | manual | https://www.yontemymm.com.tr/mali-aciklamalar/2026-041-tl-mevduat-hesaplarinda-uygulanan-stopaj-oranlarinin-suresi-uzatildi | 2026-10-10T18:38:36.881130+03:00 | manual_entry |

TEFAS satırlarının notu: "as_of assumed = previous business day". `E9cb9f7ad`
ve `E0382c2e7`, `underperformance` cezasının karşılaştırma değeri içindir; BVF
net getirisi bu değerin üstünde olduğu için ceza sıfırdır.

**Stopaj oranı nereden geliyor (kural 7).** Kodda stopaj oranı yoktur.
`config/decision.yaml` yalnızca hangi satırın kullanılacağını söyler
(`fund_by_kind: {money_market: "Yatırım fonu, para piyasası fonu"}`). Oran,
elle doldurulan `data/inbox/manual/withholding_tax.csv` tablosundan gelir; her
satır kendi `source_url` ve `as_of` değerini taşır. `Ede9af545` notu:
"Individuals, CK 10041 (09.07.2025). CK 11734 (04.09.2026) sets 10 % for capital
companies (not individuals, unconfirmed). Secondary source". TÜFE notu: "TÜİK
CPI September 2026, annual change, published 2026-10-05 (via SBB). EVDS has
only 4 months of the index (2025=100), not enough for a 12-month change."

## 5. Varsayımlar, uyarılar ve teyit edilecekler

Varsayımlar (kayıttaki gibi):

1. Fon getirileri geçmiş getirilerdir; mevduat oranı bugünkü orandır.
2. Getiriler stopaj sonrası ve yıllık TÜFE'ye (%29.73, 2026-09-30) göre reel olarak hesaplandı.
3. Mevduat için 100.000-249.999 TL diliminin standart oranı kullanıldı (tutar bilinmiyor; hoş geldin oranı geçicidir).
4. Fonlarda likidite satış valöründen (valör yoksa ürün türünden), gelir uygunluğu ürün türünden türetildi.
5. Hisse senedi yoğun fonlarda stopaj %0'dır; ihtiyatlı olmak için para piyasası dışındaki tüm fonlarda 'diğer fonlar' oranı kullanıldı.
6. 32 günlük vade her ay yenilenir; oranlar değişebilir.
7. "doviz_maruz_kalma_tercihi" için "Mevcut döviz gelirini dikkate alarak kontrollü" anlaşılamadı; güvenli düzey "Sınırlı" varsayıldı.
8. "kur riskini yönetme" önceliği döviz düzeyi ile ele alındı.
9. Risk değeri olmayan fonlarda aynı varlık sınıfındaki bilinen risk değerlerinin üst çeyreği (yukarı yuvarlanmış) kullanıldı.
10. Öneriler varlık sınıflarına yayıldı: her sınıftan en fazla bir, nakit benzeri en fazla bir seçenek.

Uyarılar (ikisi de yalnızca RM için, `audience = rm`):

- `deposit_vs_market`: "ING standart mevduat oranı (%23.00) piyasa ortalamasının (%43.82) 20.8 puan altında." (kanıt `E42b47116`, `E9cb9f7ad`)
- `no_fx_deposit_data`: "Döviz mevduatı oranı kanıtlarda yok; döviz mevduatı karşılaştırılamadı." (kanıt yok)

Teyit edilecek (`to_confirm`): "Yatırım tutarını sorun: 100.000-249.999 TL
dilimi varsayıldı." Engelleyici olmayan iki soru cevapsızdır (`answer = null`):
`q:doviz_maruz_kalma_tercihi` ve `q:override:fx_limit`.

Veri kalitesi notları: "manual: 7 değer "manual_entry" işaretli."; "tefas_detail:
1398 değer "needs_check" işaretli."; "tefas_web: 962 değer "needs_check"
işaretli."; "1 değer aralık dışında olduğu için kullanılmadı."; "6 fonun TEFAS
alım durumu kanıtlarda yok; bu fonlar alıma açık sayıldı."; "1292 serbest fon
çıkarıldı (yalnızca nitelikli yatırımcılar)."

## 6. Model dağılım (D20, stratejik bantlar)

Dengeli profilin stratejik bantlarıdır (`docs/decision.md` bölüm 11). Tutar ve
mevcut pay yoktur, çünkü personalar müşterinin varlık dağılımını vermez.

| Varlık sınıfı | Bant (%) | Kaynak (`inferred`) | Sınıfın en iyi seçeneği veya not |
|---|---|---|---|
| `nakit_benzeri` | 5–10 | Ata Yatırım, 28.04.2026 (false) | `fund:BVF` · BV PORTFÖY PARA PİYASASI (TL) FON |
| `borclanma` | 30–40 | Ata Yatırım, 28.04.2026 (false) | `fund:NJR` · NUROL PORTFÖY BİRİNCİ BORÇLANMA ARAÇLARI FONU |
| `hisse` | 40–50 | Ata Yatırım, 28.04.2026 (false) | `fund:CPU` · AKTİF PORTFÖY TEKNOLOJİ KATILIM FONU |
| `altin_doviz` | 10–15 | Ata Yatırım, 28.04.2026 (false) | yok · not `ceiling`: "Risk tavanı nedeniyle uygun fon yok." |
| `dengeli` | — (bant yok) | Ata Yatırım, 28.04.2026 (false) | `fund:IRF` · İSTANBUL PORTFÖY BİRİNCİ FON SEPETİ FONU |

`allocation_notes = []`: persona metninde varlık ipucu yoktur.

## 7. Görüşme metni

| Alan | Değer |
|---|---|
| Model | `claude-sonnet-5-5` (`source = llm`) |
| Prompt sürümü | `n9` |
| Doğrulayıcı sonucu | `checks = []` (bulgu yok) |
| Maliyet | `cost_usd = 0.073411` |
| Taslak zamanı | `2026-10-13T01:04:21.833514+03:00` (`R2b9ee9ca01-TR-n9-claude-sonnet-5-5-dbef3f0b33.json`) |
| Onay zamanı | `approved_at = 2026-10-13T01:04:22.065722+03:00` (`status = approved`) |
| RM düzeltmeleri | `rm_edits = {}`; onaylı cümleler taslakla aynıdır |

Doğrulayıcı koddur, LLM değildir (`docs/narrator.md`): sayılar olgu paketiyle
eşleşir; yalnızca seçilen seçenekler ve grup alternatifleri adlandırılır; yasak
ifadeler yoktur; öneri, alternatif ve dikkat cümlelerinin her birinde geçerli
bir kanıt atfı vardır; metin yatırım tavsiyesi olmadığını söyler.

`fund:BVF` için cümleler:

| Cümle | Kanıt |
|---|---|
| "BV Portföy Para Piyasası (TL) için enflasyon sonrası reel getiri %7,98, nominal getiri %48,58 ve risk düzeyi 2'dir." | `Eb8143c0e`, `Ea80b47f6` |
| "BV Portföy Para Piyasası (TL), aynı gün erişim sağladığı için müşterinin erişilebilir likidite önceliğine ve döviz gelirinin bir kısmını TL'de değerlendirme isteğine uyar." | `Ee9dc76cc` |
| "BV Portföy Para Piyasası (TL)'nin getirisi faiz değişimine bağlıdır; mevduat gibi anapara güvencesi yoktur." | `Ee9dc76cc` |

Pano özeti (brief): model `claude-haiku-5-5`, prompt `b1`, `checks = []`,
`cost_usd = 0.000964355`; atıflar `fund:BVF`, `fund:NJR`, `fund:IRF`,
`Ec7827ecf`, `Ee9dc76cc`, `Ef1ea9bbf`.

## 8. RM onayı

| Alan | Değer |
|---|---|
| `rm_status` | `approved` |
| `rm_selected` | `fund:BVF`, `fund:NJR`, `fund:IRF` (önerilen üçlü, değişiklik yok) |
| `rm_note` | "Müşteri döviz gelirinin bir kısmını TL fonlarda değerlendirmek istiyor." |
| `rm_option_notes` | boş (`{}`) |
| `rm_decided_at` | `2026-10-13T01:03:40.801286+03:00` |
| Metin onayı | `2026-10-13T01:04:22.065722+03:00` |

Kart satırları (`data/cards/R2b9ee9ca01.md`):

```
RM onayı: 2026-10-13 01:03
Metin onayı: 2026-10-13 01:04 · model claude-sonnet-5-5 · kontrol bulgusu 0
```

Sistem şu kuralları uygular: onaylanmamış bir çalıştırma için görüşme metni
yazılmaz; kart yalnızca onaylı çalıştırma için oluşturulur; metin onayı boş
olmayan bir RM metni ister ve engelleyici bulgu varsa reddedilir. **Müşteriye
hiçbir şey gitmedi.** Kart ve metin RM'in hazırlığı içindir ("Bu metin RM'in
görüşme hazırlığı içindir; yatırım tavsiyesi değildir."). API'de müşteriye
gönderim uç noktası yoktur.

## 9. Nasıl doğrulanır

**Uygulamada:**

1. P02 müşterisini `20261010-183835-6813` anlık görüntüsü ile açın (aynı config ile `run_id = R2b9ee9ca01` olur).
2. "Para Piyasası (TL)" (BV Portföy) kartında "Kanıtları göster" düğmesine basın.
3. Bir kimliğe (ör. `Eb8143c0e`) basın. "Kanıt" penceresi değeri, kaynağı, "Tarih" (`as_of`) ve altında "Alındı" (`fetched_at`) satırını, kanıt numarasını, işaretleri ve notu gösterir.
4. Kaynak sayfayı görmek için "Kaynağı aç" bağlantısına basın.

**API'de:** `GET /api/evidence/20261010-183835-6813/Eb8143c0e` (tek kanıt,
`fetched_at` dahil); `GET /api/runs/R2b9ee9ca01` (çalıştırma);
`GET /api/runs/R2b9ee9ca01/card.md` (kart).

**Veritabanında** (yalnızca okuma):

```python
import duckdb
con = duckdb.connect("data/evidence.duckdb", read_only=True)
con.execute(
    "select id, quantity, entity, value, unit, as_of, source, source_url,"
    " cast(fetched_at as varchar), raw_ref, flags, note from datapoints"
    " where snapshot_id = '20261010-183835-6813' and id = 'Eb8143c0e'"
).fetchall()
```

**Ham dosyada:** `raw_ref` yolundaki dosyayı açın ve sha256 özetini
`manifest.json` ile karşılaştırın. Örnekler: `Eb8143c0e` →
`…/payloads/tefas_web/fon-getirileri.html#fonKodu=BVF;field=getiri1y`
(`75af158a680cf6ec4f39dc5847d396043f8682175e040ac2782d44e5077b71d4`);
`Ee9dc76cc` → `…/payloads/tefas_detail/BVF.html.gz#fonKodu=BVF;field=profilData.fonSatisValor`
(`35b7e1c4b34efc4fd23f116977c65fc083e47dc6e57ad866d255d1a25c012372`);
`Ede9af545` → `…/payloads/manual/withholding_tax.csv#row=6`
(`6757068d2fb8c9d7205b73cf3b578af8eed62c22943fa89628f6564c4fabe76a`). Manifestteki
kaynak durumu: evds `ok`, manual `ok`, tefas_web `ok`, tefas_detail `ok`,
tefas `skipped`.
