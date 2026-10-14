# Test ve öğrenimler

> Teslimat 5 · Taslak (2026-10-14) · Sayılar: son tam değerlendirme
> `data/eval/20261014-105720-full` (dondurulmuş veri anlık görüntüsü
> `20261014-102329-8fca`, karar yapılandırması `c5e83ccc4e4b`, anlatıcı
> `claude-sonnet-5-5` istem `n9`, hakem `claude-haiku-5-5` istem `j3`) ve
> önceki tam değerlendirme raporları (son önceki: `20261013-004507-full`,
> anlık görüntü `20261010-183835-6813`). **[VARSAYIM]** ile işaretli
> değerler ölçülmedi.

## 1. Test yaklaşımı

Çözümü üç katmanda test ettik. Her katman farklı bir soruya cevap verir.

| Katman | Ne test eder | Nasıl |
|---|---|---|
| Birim ve sözleşme testleri | Her modülün kuralı tek başına doğru mu? (veri alma, karar motoru, anlatıcı doğrulayıcısı, API) | `pytest`, 97 dosyada **1.918** test (2026-10-14 sayımı); ağ erişimi yok, LLM yerine sahte model |
| Senaryo değerlendirme paketi | Sistem uçtan uca, jürinin değiştirebileceği girdilerle doğru davranıyor mu? | 34 senaryo, 39 çalıştırma; dondurulmuş anlık görüntü; tek komut `python -m rmprep eval` |
| Ekranda elle inceleme | RM için kullanışlı mı? | Kullanıcı ile demo ve ekran incelemesi (2026-10-11 geri bildirimi web arayüzünün yeniden tasarımına yol açtı) |

Değerlendirme paketi her senaryoyu gerçek arka uçtan geçirir: karar, panoda
RM'e önerilen ilk 3'ün onayı, görüşme metni. Kontroller üç türdür:

1. **Deterministik kurallar (kod):** kısıt uyumu, risk tavanı, kaynak atfı,
   uydurma veri, tekrar tutarlılığı. Hedef %100.
2. **LLM metninin doğrulayıcısı (kod):** metindeki her sayı olgu paketinde mi,
   yalnızca izinli ürünler mi adlandırılıyor, yasaklı ifade var mı, her cümle
   kanıt kimliği gösteriyor mu.
3. **LLM hakemi (Claude Haiku 5.5):** yalnızca kodun ölçemediği şeyler:
   metin bu müşteriye mi uyarlanmış, RM için açık mı, dengeli mi. Kural
   kontrolleri hakeme bırakılmaz.

Veri dondurulduğu için bir sonuç değişirse kod veya yapılandırma
değişmiştir. Metinler önbellekte tutulur; aynı girdi aynı metni verir.

### Neden bu başarı göstergeleri?

Göstergeleri brifin §9.1 sorularından ve §12 kurallarından türettik:

| Brif sorusu | Göstergemiz | Neden |
|---|---|---|
| Müşteri kısıtlarına uyum | Kural 5 kontrolü, risk tavanı, açık kısıtlar sert kural (D13), alıma kapalı fon yok (D12) | Jüri her senaryoda kural 5'i kontrol ediyor; tek ihlal güveni bozar |
| Eksik / çelişkili veri | Eksik veri gösteriliyor, hatalı veri işaretleniyor, tahmin yerine soru | SPK yerindelik kuralı eksik bilgiyle tavsiyeye izin vermez |
| Kaynakların doğru kullanımı | Her seçenek ve her cümle kanıt kimliği gösteriyor (kural 2); uydurma sayı yok (kural 3) | LLM metninin en büyük riski uydurma sayı |
| Tekrar tutarlılığı | Aynı girdi → aynı `run_id`, aynı sonuç, aynı metin | RM ve denetçi aynı sonucu yeniden üretebilmeli |
| Önerilerin tutarlılığı ve uyarlama | Persona değişikliği sonucu beklenen yönde değiştiriyor; çeşitli öneri (D19); hakem "uyarlanmış" puanı | Herkese aynı ürünü öneren bir araç RM'e katkı sağlamaz |
| İşlem süresi ve maliyet | Saniye ve USD (yalnızca raporlanır) | Hazırlık süresine sığmalı; bütçe sınırı $5 / paket |

## 2. Başarı göstergeleri ve hedefler (son ölçüm)

| Gösterge | Değer | Hedef | Karşılandı |
|---|---|---|---|
| Kural kontrolleri geçme oranı | %100 (218 geçti, 0 kaldı) | %100 | evet |
| Anlatıcı doğrulayıcı geçme oranı (LLM, şablona düşmeden) | %100 (25 / 25) | ≥ %95 | evet |
| Yasaklı ifade (kural 6) | 0 | 0 | evet |
| Kural 5: reddedilen / kısıtı ihlal eden seçenek listede, seçimde veya metinde | 37 / 37 geçti | %100 | evet |
| Risk tavanının üstünde seçenek yok | 37 / 37 | %100 | evet |
| Açık kısıtlar sert kural (D13) | 12 / 12 | %100 | evet |
| Uydurma veri yok (kural 3) | 39 / 39 | %100 | evet |
| Kaynak atfı (kural 2) | 39 / 39 | %100 | evet |
| Eksik veri gösteriliyor | 7 / 7 | %100 | evet |
| Hatalı veri işaretleniyor, kullanılmıyor | 3 / 3 | %100 | evet |
| Tahmin yerine soru | 2 / 2 | %100 | evet |
| Tekrar tutarlılığı | 5 / 5 | %100 | evet |
| Persona değişikliği beklenen yönde | 21 / 21 | senaryo başına | evet |
| Çeşitli öneri (D19) | 20 / 20 | %100 | evet |
| Kanıt toplama / karar süresi (çalıştırma başına ort.) | 0,24 sn / 0,96 sn (en çok 3,04 / 1,61 sn) | yalnızca rapor | — |
| Görüşme metni süresi | ort. 25,09 sn (en çok 47,73 sn) | yalnızca rapor | — |
| Maliyet | metin başına $0,044; paket $1,098 (anlatıcı $1,089, hakem $0,009; sınır $5) | yalnızca rapor | — |
| Hakem: uyarlanmış / RM için açık / dengeli | %50 / %57 / %62 (19 metin) | yalnızca rapor | — |

Bir kontrol yalnızca ilgili senaryoda çalışır; uygulanmayanlar oranlara girmez.

Önceki tam çalışmaya (`20261013-004507-full`, eski anlık görüntü) göre tüm
kontrol sayıları aynıdır. Karar süresi 0,73 sn'den 0,96 sn'ye çıktı. Olası
nedenler (ayrı ölçülmedi): motor artık her bozulmuş sıralamada öneri
kuralını da uygular (D25, bölüm 7) ve fonların portföy dağılımı satırlarını
okur (D23). Metin maliyeti $0,046'dan $0,044'e, metin süresi 27,08 sn'den
25,09 sn'ye indi. Hakem puanları %52 / %50 / %60'tan %50 / %57 / %62'ye
değişti; her ölçüde en çok 3 not değişti (bölüm 5).

## 3. Senaryo grupları

| Grup | Sayı | Neyi değiştirir | Örnek |
|---|---|---|---|
| Temel | 5 (her biri 2 kez) | Hiçbir şey; P01–P05 olduğu gibi | `base-p01` … `base-p05` |
| Hatalı / çelişkili veri | 3 | Kanıta hata enjekte eder | kaynaklar arası çelişen risk değeri, aralık dışı risk, eskimiş getiri |
| Persona değişikliği (Jüri Challenge tarzı) | 5 | Bir müşteri alanını değiştirir | P03 "Agresif" → "Muhafazakâr"; P03 vade "1 yıl"; P04 likidite "Yüksek"; P01 döviz tercihi bilinmeyen metin; P05 "Dengeli" |
| Kısıt | 4 | Açık kısıt ekler | "döviz maruziyeti istemiyor", "yüksek riskli ürün istemiyor"; bilinmeyen kısıt metni → RM'e soru |
| Veri erişimi | 4 | Bir kaynağı dışlar | TEFAS detay yok; elle girilen veri yok (mevduat oranı, TÜFE, stopaj); TEFAS web yok |
| Regresyon | 13 | Geçmiş hataları sabitler | hata analizi vakaları 1–8 (bölüm 4 ve 7) |

Örnek: TEFAS web dışlanınca P01'de 2 seçenek kalır, fon önerilmez;
bilinmeyen kısıtta sonuç `needs_rm_input` olur.

## 4. Hata analizi: herkese aynı öneri (vaka 8, karar D19)

**Bulgu (2026-10-12).** Dondurulmuş anlık görüntüde 5 personanın 4'ü ilk
üç öneri olarak yalnızca nakit benzeri, SPK risk 1 fonlar aldı. İki çift tamamen
aynı listeyi aldı (P01 = P04: Nurol Para Piyasası, İstanbul KV Borçlanma, Ak Para
Piyasası Katılım; P02 = P05: One Portföy Para Piyasası ile aynı iki fon);
İstanbul KV Borçlanma ve Ak Para Piyasası Katılım dördünde de vardı. Bu grupta Muhafazakâr
P01'in yanında Dengeli P02 ve P04 (risk tavanı 5) ile Temkinli P05 de vardı.
Tüm kural kontrolleri bu sırada %100 geçiyordu: hiçbir kısıt ihlal
edilmemişti, ama öneri müşteriye uyarlanmamıştı. Bu, "kurallara uyum" ile
"iyi öneri" arasındaki farkı gösterdi.

**Kök nedenler.**

1. **Geçmiş getirinin baskınlığı.** Son bir yılda TL nakit benzeri fonlar en
   iyi reel getiriyi verdi (TÜFE ve stopaj sonrası +%7–9); dengeli fonlar
   +%3, hisse ≈ %0, altın −%13.
2. **Risk bütçesini kullanan bir ölçüt yoktu.** `low_risk` ölçütü Dengeli
   müşteride de düşük riski ödüllendiriyordu; anapara cezası risk 5 fonları
   ayrıca vuruyordu (P04: risk 5 karma fon 0,02 puan, para piyasası 0,91).
3. **Çeşitlilik yanlış düzeyde ölçülüyordu.** Çeşitlilik `fund_kind` üzerinden
   çalışıyordu; para piyasası, kısa vadeli borçlanma ve katılım para piyasası
   farklı tür ama aynı varlık sınıfı (kısa vadeli TL nakit).

Eksik SPK risk değerleri neden değildi (her türde fonların %3–10'u).

**Düzeltme (D19, kullanıcı onayı 2026-10-12).**

| Değişiklik | İçerik |
|---|---|
| Varlık sınıfı | Her seçeneğe `asset_class`: `nakit_benzeri`, `borclanma`, `dengeli`, `hisse`, `altin_doviz` (tür ve ad kurallarıyla) |
| Risk uyumu bandı | `low_risk` yerine `risk_fit`: Muhafazakâr [1, 2], Temkinli [2, 3], Dengeli [3, 5], Agresif [4, 7]; bandın altındaki her seviye için ceza |
| Sınıf kuralı | Dengeli / Agresif müşteride veya çeşitlendirme önceliğinde: sınıf başına en çok 1, en çok 1 nakit benzeri öneri |
| Reel getiri tabanı (D19b) | Sınıf kuralı negatif 1 yıllık reel getirili bir fonu öne çıkaramaz |

**Ayar.** İlk denemede `per_step` 0,25 idi; Dengeli personaların önerileri
risk 2'de kaldı. `per_step` 0,5 ve `risk_fit` ağırlığı 2,0 ile öneriler
bandın içine girdi. Bantlar bir **[VARSAYIM]**; mentorlarla teyit edilecek.

**Sonuç (ölçüldü).** Sağ sütun son tam çalışmanın (`20261014-105720-full`,
anlık görüntü `20261014-102329-8fca`) panoda RM'e önerilen ilk 3'üdür: fon
kodu, varlık sınıfı, SPK risk değeri (r) ve stopaj ile TÜFE sonrası yıllık
reel getiri (%). Getiri dönemi personanın vadesine bağlıdır: P01, P02 ve
P05 için 1 yıl, 5+ yıl vadeli P03 ve P04 için 3 yıl.

| Persona | D19 öncesi | Son tam çalışma (sınıf, risk, reel getiri %) |
|---|---|---|
| P01 Muhafazakâr | 3 nakit benzeri, risk 1 | PPN nakit r1 +7,3 · IST nakit r1 +7,0 · AIS nakit r1 +6,5 (sınıf kuralı uygulanmaz; doğru davranış) |
| P02 Dengeli | aynı 3 nakit benzeri, risk 1 | EIL nakit r2 +7,7 · KDE dengeli r3 +10,1 · NJR borçlanma r2 +8,2 |
| P04 Dengeli | aynı 3 nakit benzeri, risk 1 | OKT borçlanma r3 +10,1 · EIL nakit r2 +11,6 · OLE dengeli r2 +10,5 |
| P05 Temkinli | aynı 3 nakit benzeri, risk 1 | EIL nakit r2 +7,7 · GBL nakit r2 +6,1 · KSK nakit r2 +6,3 (kendi bandı) |
| P03 Agresif | farklı | GBV hisse r6 +19,8 · IDY dengeli r4 +8,5 · OKT borçlanma r3 +10,1 |

D19 sonrası **hiçbir iki temel persona aynı ilk üçü paylaşmıyor**. Raporun
satırı "1 of 5 base personas share the most common recommended top 3" şunu
söyler: aynı setlerin en büyük grubu 1 personadır, yani her persona kendi
setini alır (önce: 4 / 5). Bazı fonlar birden çok personada yer alır (EIL
P02, P04 ve P05'te; OKT P03 ve P04'te), ama hiçbir set aynı değildir. D19
anındaki ölçümler (ör. P02: nakit r2 +8,0 · borçlanma r2 +8,4 · dengeli r3
+12,8) regresyon senaryolarının açıklamasında kalır. Önceki tam çalışmada
(`20261013-004507-full`, eski anlık görüntü) seçimler P01 PPN/IST/AIS, P02
BVF/NJR/IRF, P03 GBV/YAY/OKT, P04 OKT/RPP/SUA, P05 BVF/GBL/KSK idi. Yeni
anlık görüntüde sınıflar portföy dağılımından da gelir (D23); sınıf kuralı
ve tüm kural kontrolleri geçmeye devam ediyor.

Yan etkiler: hakemin "uyarlanmış" puanı %53'ten %57'ye yükseldi (senaryo
seti 30'dan 34'e büyüdüğü için bu karşılaştırma yaklaşıktır); kural
kontrolleri %100'de kaldı. Karar süresi
ortalama 0,86 sn'den 1,16 sn'ye çıktı, çünkü motor artık yalnızca grup
başlarından değil tüm sıralı seçeneklerden seçiyor. Kalıcılık için dört
regresyon senaryosu eklendi (`reg-d19-p02-diverse`, `reg-d19-p04-diverse`,
`reg-d19-p01-unchanged`, `edit-p05-dengeli`) ve yeni kontrol
`diverse_recommendations`.

## 5. Hata analizi: metin kalitesi (N13, istem n7–n9, hakem j3)

**Bulgu (2026-10-12).** `20261012-201431-full` çalışmasında kural ve
doğrulayıcı kontrolleri %100 geçti, ama hakem puanları düşüktü (uyarlanmış
%57, RM için açık %50, dengeli %50). Hakem gerekçelerini ve metinleri
inceledik. Anlatıcıda doğrulanan nedenler:

1. Seçenek başına risk, erişim ve ücret olgusu yoktu; 19 metnin 11'inde
   dikkat bölümü yalnızca geçmiş getiri cümlesini taşıyordu.
2. Sayı alanları getiriyi öne çıkarıyordu; piyasa oranı ve TÜFE her
   seçenekte tekrar ediyordu; nominal getiri reel getiriden önce geliyordu.
3. "Geçmiş getiri" uyarısı metin başına yaklaşık 6 kez geçiyordu.
4. Öneriler cümleleri çoğu zaman fonun adını vermiyordu; karşılanmayan
   müşteri öncelikleri için talimat yoktu.

**Düzeltme.**

| Sürüm | İçerik |
|---|---|
| n7 | Olgu paketinde seçenek başına risk satırı: erişim (valör), varsa ücretler, varlık sınıfına göre sabit risk notu (`config/narrator.yaml` `risk_notes`); reel 1 yıllık getiri seçeneğin sayısıdır. Öneriler: her seçenek için fonun adıyla başlayan 3 cümle (olgular, önce reel getiri; uyum; ödünleşim), doğrulayıcı kuralı `shape`. Geçmiş getiri uyarısı yalnızca dikkat ve teklif metninde. Markdown ekran sırasında |
| n8 | Dikkat bölümü öneriler bölümünü tekrar etmez; doğrulayıcı kuralı `repeat` |
| n9 | ING mevduatı ile piyasa ortalaması karşılaştırması öneriler dışında yok (RM'e özel not); doğrulayıcı kuralı `compare` |
| j3 | Hakem ekran bağlamını (8 bölüm, kapalı bölümler, varsayımların motor metni olduğu) ve seçenek olgularını (erişim, risk) görür; "kararsızsan düşük olanı seç" kuralı kalır |
| N13d | İlk denemenin doğrulayıcı bulguları maliyet defterine yazılır ve türe göre sayılır (`findings_by_kind`) |

**Sonuç (ölçüldü).**

| Ölçü | Önce (n6, j2) | Sonra (n9, j3) |
|---|---|---|
| P01 metni, kelime (canlı çağrılar, geliştirme sırasında) | 644 | 465 |
| P01 metni, kelime (tam eval önbelleği, cümle metni) | 500 | 459 |
| P01 metninde "geçmiş" sözcüğü | 6 | 3 |
| P01 öneri cümlelerinden fonun adıyla başlayan | 3 / 6 | 9 / 9 |
| Doğrulayıcı geçiş oranı, şablona düşüş | %100, 0 | %100, 0 |
| İlk denemede kalan metin (tekrarda geçen) | — (defterde yok) | 19 metinde 3 (2 sayı, 1 boş bölüm) |
| Hakem: uyarlanmış / RM için açık / dengeli | %57 / %50 / %50 | %52 / %50 / %60 |
| Metin başına maliyet | $0,042 | $0,046 |

**Yorum.** Nesnel ölçüler iyileşti: metin kısaldı, tekrar azaldı, her öneri
cümlesi fonun adıyla başlıyor, her seçenek bir risk cümlesi taşıyor. Hakem
puanı ise belirgin değişmedi: "dengeli" yükseldi, "uyarlanmış" biraz düştü,
"RM için açık" aynı kaldı. Nedenleri:

- Hakem katıdır: istemde "kararsızsan düşük olanı seç" kuralı vardır ve
  küçük bir modeldir (Claude Haiku 5.5). Son tam çalışmada
  (`20261014-105720-full`) 60 notun 52'si "kısmen"dir; "uyarlanmış" için
  hiç "evet" yoktur (önceki tam çalışmada "RM için açık" için yoktu).
- Hakem de değişti (j2 → j3, daha çok bağlam), bu yüzden önce / sonra
  karşılaştırması yaklaşıktır. 19 metinde bir metnin notu yaklaşık 2,6
  puanlık fark yapar.

Hakem puanını bilerek daha fazla optimize etmedik. Bir LLM hakemi için
istem ayarlamak, metni o hakemin zevkine göre ayarlamak olur; bu, RM için
daha iyi bir metin demek değildir. Sonraki adım ikinci bir hakemle uyum
kontrolü ve RM incelemesidir (bölüm 9).

## 6. Hata analizi: eksik vergi ve enflasyon verisi güveni düşürmüyordu (D24)

**Bulgu (2026-10-14).** Yeni dondurulmuş anlık görüntüde
(`20261014-102329-8fca`) ücretsiz `--no-llm` geçişi
(`data/eval/20261014-104638-nollm-check`) "Eksik veri gösteriliyor"
kontrolünde iki senaryoda kaldı: `data-p01-no-manual` ve
`data-p03-no-manual`. Bu senaryolar elle girilen kaynağı (stopaj, TÜFE, ING
oranları) dışlar. Fon seçenekleri güven **1,00** ile kaldı; kontrol en çok
0,90 bekler. Kural kontrolleri %99'a düştü (218 kontrolün 216'sı geçti),
"Eksik veri gösteriliyor" 5 / 7 oldu.

**Kök neden.** 2026-10-14'e kadar her TEFAS satırı "kontrol gerekli"
(`needs_check`) bayrağı taşıyordu. Bu bayrak güveni 0,9 ile çarpıyordu ve
tüm fon güvenlerini 0,90'da tutuyordu. TEFAS verisi 12 anlık görüntü
boyunca kararlı kaldığı için bayrak yeni anlık görüntülerden kaldırıldı.
Bayrak gidince ortaya çıktı: stopaj veya TÜFE satırı yokken reel getiri
hesaplanamıyordu (bu iki senaryoda TÜFE EVDS'den gelmeye devam eder; eksik
olan stopajdır, motor onu 0 alır), ama güven bunu hiç yansıtmıyordu.
Kontrol önceki tam çalışmalarda yanlış nedenle geçiyordu.

**Düzeltme (D24, 2026-10-14).** Reel getiri yapılandırmada açık olduğu
hâlde bir seçenek için hesaplanamazsa (TÜFE satırı yok veya ürün türünün
stopaj satırı yok) güven 0,8 ile çarpılır
(`confidence.real_return_missing`; D14'teki likidite tahmini çarpanıyla
aynı değer). Skor ve sıralama değişmez. Testler:
`tests/decision/test_real_return_confidence.py`.

**Sonuç (ölçüldü).**

| Ölçü | Önce (`20261014-104638-nollm-check`) | Sonra (`20261014-105544-nollm-check2`) |
|---|---|---|
| Kural kontrolleri geçme oranı | %99 (2 kaldı) | %100 |
| Eksik veri gösteriliyor | 5 / 7 | 7 / 7 |
| `data-p01-no-manual`, `data-p03-no-manual` | fon güveni 1,00 > 0,90 | geçti |
| Önerilen ilk 3 (beş temel persona) | — | değişmedi |

Sonraki tam çalışma (`20261014-105720-full`) aynı yapılandırmayla
(`c5e83ccc4e4b`) tüm hedefleri karşıladı. Öğrenim: genel bir bayrağı
kaldırmak gizli bir açığı ortaya çıkarabilir; yanlış nedenle geçen bir
kontrol bir risktir (bölüm 8, öğrenim 8).

## 7. Diğer bulgular ve iyileştirmeler

| # | Bulgu | Etki | Düzeltme | Sonuç |
|---|---|---|---|---|
| 1 | Skor nominaldi; %23 mevduat, %29,73 TÜFE ile vergi sonrası reel −%8,3 | Mevduat referansı her fonun üstünde görünüyordu | D9: vergi sonrası reel getiri | P01 referansı 0,912 → 0,568; en iyi fon 0,837 |
| 2 | 809 fonun 189'u TEFAS'ta işlem görmüyor veya kapalı | Her personanın ilk 20'sinde 1–4 alınamaz fon | I3b + D12 `not_buyable` | Listede 0; 189 reddedildi |
| 3 | Açık kısıtlar yalnızca cezaydı | P02'de 8 döviz fonu listede kaldı; P05'te valörü 3 günden uzun fonlar | D13: sert kural | P02: listede 0, 14 reddedildi; P05: en çok valör 3 |
| 4 | TEFAS detay kaynağı ilk canlı çalıştırmada hata verdi (valör zorunlu ama boş) | Kaynak kullanılamadı | Alanlar isteğe bağlı | Kaynak çalışıyor, 5.384 satır |
| 5 | Doğrulayıcı "GARANTİ PORTFÖY" fon adını yasaklı "garanti" ifadesi saydı (N5) | Geçerli metin şablona düştü | Ürün adları taramadan önce çıkarıldı | P01 ifade bulgusu 1 → 0 |
| 6 | TEFAS detay yokken likidite tahmini tabloya düştü ama güven arttı (D14) | Eksik veri gizleniyordu (0,63 → 0,70) | Tahmin için 0,8 çarpanı | Güven 0,56; eksik veri gösteriliyor |
| 7 | İlk tam eval: P05'te VKR, ZPO, ZTV kanıt kimliksiz listelendi (D15) | Kural 2 ihlali; kural kontrolleri %99 | Kısa geçmiş kuralı | Kanıtsız seçenek yok; 57 fon `short_history` reddi |
| E8 | Eval, ekranda gösterilen olguların sayılarını tanımıyordu | 2 yanlış "uydurma veri" bulgusu; %99 | Kontrol ekran olgularını kabul eder | %100; gerçek uydurma sayı hâlâ kalır |
| N8 | İlk tam eval: metin başına $0,136, olgu paketi 35.000–50.000 token | Bütçe riski | Paket yalnızca metnin ihtiyacını taşır | Sonraki tam eval $0,041; son $0,044 |
| N7 | Hakem gerekçeleri: metin genel, iç değerler (bayrak adları, skorlar) metinde | Müşteriye uyarlanmamış metin | Her öneri bir müşteri ihtiyacına bağlanır; iç değer yasak | Doğrulayıcıda yeni kurallar; hakem puanı belirgin değişmedi |
| N9b | Bölüm başına şema (8 kopya) yapılandırılmış çıktı için çok büyük (HTTP 400 "compiled grammar is too large") | Metin üretilemiyordu | Tüm bölümler için tek cümle şeması | Test şemayı küçük tutar; 25 / 25 LLM metni |
| N9c | Piyasa ortalaması (%43,82) ile ING oranı (%23) pakette aynı adı taşıyordu | Piyasa oranı ING ürün adının yanına yazılabilirdi | Adlandırılmış olgular + etiket kuralı | ING adı olan cümlede yalnızca ING oranı |
| N10 | Panodaki özet canlı denemede 389 karakter (sınır 280) | Özet şablona düşüyordu | Sınır istemde kelimeyle (≈40); sığan tam cümleler tutulur | Kesik cümle yok; aşım doğrulayıcıda kalır |
| D23 | Çok varlıklı fonların sınıfı tür ve addan geliyordu; tüm Değişken fonlar "dengeli" sayılıyordu, %80 hisse tutsalar da | Sınıf kuralı (D19) ve Dağılım satırları yanlış sınıfı kullanıyordu | Değişken, Karma, Fon Sepeti ve Katılım fonlarında sınıfı TEFAS portföy dağılımı belirler (en az %50 pay; çoğunluk yoksa dengeli); Borçlanma fonlarında yalnızca döviz çoğunluğu sayılır | Yaklaşık 214 fonun sınıfı değişti, çoğu dengeli → hisse; ör. P03 GBV: "portföyün %85'i hisse senedi" |
| D25 | Kararlılık yalnızca ilk 20 sıradaki payı ölçüyordu; sınıf kuralı öneriyi uzak bir sıradan seçebilir (P03 IDY sıra 42, OKT sıra 57) | Bu öneriler kararlılık 0,00 aldı; `low_stability` yalnızca 1–3. sıraya bakıyordu | Önerilen seçeneğin kararlılığı = 30 bozulmuş çalıştırmada öneri kuralının onu yeniden önerme payı; uyarı tüm önerilere bakar | P03 IDY ve OKT 0,00 → 1,00; P01–P05'in tüm önerileri ≥ 0,83, `low_stability` uyarısı yok |
| I6a | Zamanlanmış ingest'in görünür konsol penceresi kullanıcı tarafından kapatıldı (2026-10-14) | Çökme (çıkış kodu 0xC000013A); kilit dosyası ve yarım bir anlık görüntü kaldı | Görev konsol penceresi olmadan çalışır (`conhost --headless`) | Kapatılabilecek bir pencere yok |
| I6b | Günlükte çalışmanın çıkış satırı yoktu: `echo ... exit 0>> log` 0 numaralı tanıtıcıyı yönlendirdi | Çalışmanın nasıl bittiği günlükten okunamıyordu | Yönlendirme satırın başına alındı | Her çalışma "exit <kod>" satırı yazar |
| I3c | İlk zamanlanmış çalışma 4 fonda yeni bir TEFAS durum metni buldu: "Fon Alımına Kapalı, Fon Bozumuna Açık" | Bilinmeyen metin alım durumu satırı vermez; bu fonlar alıma açık sayılırdı | Metin "alınamaz" (0) olarak eşlendi | Yeni anlık görüntüde 195 fon alınamaz; listede 0 |

### Değerlendirmenin kendi hatası: eski metin önbelleği (2026-10-12)

D19 sonrasında değerlendirme, görüşme metni için hâlâ eski kuralla (grup
başları) seçim yapıyordu; ekranda RM'e önerilen ilk 3 ise motorun yeni
`recommended` listesiydi. Seçim kuralı düzeltilip paket yeniden
çalıştırıldığında **anlatıcı maliyeti 0 $** çıktı: P02–P05 için seçim değiştiği
hâlde hiçbir yeni metin üretilmemişti. Neden: metin önbelleğinin anahtarı
yalnızca çalıştırma kimliği, dil, istem sürümü ve modeldi; RM seçimi ve notları
anahtarda yoktu, bu yüzden aynı çalıştırma için eski seçimin metni döndü ve
kontroller eski metni değerlendirdi. Aynı sorun uygulamada da olabilirdi: bir
çalıştırma başka bir seçimle yeniden onaylanırsa eski metin veya eski blok
düzenlemeleri görünebilirdi.

İyileştirme: (1) değerlendirme artık panodaki öneriyi seçiyor; (2) önbellek
anahtarına modelin gördüğü olgu paketinin özeti (sha256, 10 karakter) eklendi
(N12) — seçim, onay notu veya seçenek notu değişince yeni metin üretiliyor;
(3) bir çalıştırmanın yeni onayı, önceki onaylı metni, blok düzenlemelerini ve
bekleyen taslakları siliyor. Her biri testle korunuyor. Sonraki geçerli
çalıştırma (`20261012-201431-full`) 25 yeni metin üretti (1,04 $) ve tüm
hedefleri karşıladı. Öğrenim: maliyet ve süre gibi "beklenmedik derecede iyi"
ölçümler de bir hatanın işareti olabilir.

## 8. Öğrenimler

1. **Geçmiş getiri tek başına baskın olur.** Bir yıllık veri, piyasa
   koşulunu herkese uygular. Müşteri profili (risk bandı, varlık sınıfı)
   ayrı bir sinyal olmalı.
2. **Kesin kurallar cezalardan güvenilirdir.** Kısıtlar (D13) ve çeşitlilik
   (D19) ceza olarak kaldığında yüksek skor onları aştı. Sert filtre ve seçim
   kuralı sonucu öngörülebilir ve test edilebilir yaptı.
3. **"Kurallar %100" yeterli değil.** Vaka 8 tüm kontroller yeşilken
   oluştu. Çıktılar arası karşılaştırma (aynı ilk üç) ve insan incelemesi
   gerekti.
4. **LLM doğrulayıcısı değerli ama kendisi de test edilmeli.** Uydurma sayı
   ve yasaklı ifade kaçmadı; ancak N5 ve E8 iki yanlış alarm üretti.
   Doğrulayıcıya da regresyon senaryosu yazdık.
5. **Yapılandırılmış çıktının boyut sınırı var.** Şemayı küçük tutmak
   (N9b) ve olgu paketini küçültmek (N8) hem hatayı hem maliyeti düşürdü.
   Dondurulmuş veri sayesinde her değişikliğin etkisi önce / sonra ölçüldü.
6. **Bir LLM hakemine göre optimize etmek tuzaktır.** Metin nesnel ölçülerde
   iyileşti, hakem puanı yerinde kaldı. İstemi hakemin zevkine göre
   ayarlamak yerine ölçülebilir kurallar (`shape`, `repeat`, `compare`)
   ekledik ve RM incelemesini sonraya bıraktık.
7. **Yeni bir görünüm eski bir hatayı ortaya çıkarabilir.** Dağılım (D20)
   satırları her sınıfın en iyi seçeneğini gösterince, risk değeri olmayan
   bir altın fonunun Muhafazakâr tavanın içinde kaldığı görüldü. Tahmin
   artık varlık sınıfından gelir (D21).
8. **Genel bir bayrağı kaldırmak gizli bir açığı ortaya çıkarabilir.** Her
   TEFAS satırındaki "kontrol gerekli" bayrağı tüm güvenleri 0,90'da
   tutuyordu; eksik stopaj ve TÜFE güveni düşürmüyordu, ama kontrol yine de
   geçiyordu (D24). Yanlış nedenle geçen bir kontrol bir risktir. Veri veya
   bayrak değişince ücretsiz `--no-llm` geçişini önce çalıştırmak bu açığı
   tam değerlendirmeden önce buldu.

## 9. Sınırlar

- **Dondurulmuş anlık görüntü:** sonuçlar 2026-10-14 anlık görüntüsüne
  (TEFAS verisi 2026-10-13) aittir; başka bir piyasa döneminde sıralama
  farklı olabilir.
- **RM hazırlık süresi ölçülmedi:** sistem süresini ölçtük (kanıt + karar
  ort. ≈ 1,2 sn, görüşme metni ort. ≈ 25 sn); RM'in bugünkü hazırlık süresi ve kazanç
  **[VARSAYIM]**, mentorların cevabına kadar.
- **Hakem bir LLM:** puanlar yön göstergesidir; 60 notun 52'si "kısmen"dir,
  "uyarlanmış" için hiç "evet" yoktur. İkinci bir hakemle uyum kontrolü
  sonraya kaldı.
- **Portföy dağılımı tek günün verisidir:** çok varlıklı fonların sınıfı
  (D23) ingest gününün dağılımından gelir; fon yöneticisi dağılımı
  değiştirirse sınıf ertesi ingest'te değişebilir.
- **Günlük ingest bir dizüstü bilgisayarda çalışır:** bilgisayar kapalıyken
  çalışma bir sonraki açılışta yapılır; uygulama veri yaşını gösterir ve RM
  veriyi yenileyebilir.
- **Risk bantları ve D19 ayarları** tek anlık görüntüde ayarlandı;
  **[VARSAYIM]**, mentorlarla teyit edilecek.
- **Personalar sentetik:** gerçek müşteri verisiyle test yapılmadı.
- **Mevcut portföy yok:** personalar müşterinin varlık dağılımını vermez.
  Dağılım görünümü bantları ve sınıfın en iyi seçeneğini gösterir, bir
  boşluk analizi yapmaz; mevcut portföy girdisi gelecek iştir.
- **Kayıt örneği:** Teslimat 6'daki kayıt örneği ayrıca açıklanır.
