# Test ve öğrenimler

> Teslimat 5 · Taslak (2026-10-13) · Sayılar: son tam değerlendirme
> `data/eval/20261013-004507-full` (dondurulmuş veri anlık görüntüsü
> `20261010-183835-6813`, karar yapılandırması `9279d0a6c847`, anlatıcı
> `claude-sonnet-5-5` istem `n9`, hakem `claude-haiku-5-5` istem `j3`) ve
> önceki tam değerlendirme raporları. **[VARSAYIM]** ile işaretli değerler
> ölçülmedi.

## 1. Test yaklaşımı

Çözümü üç katmanda test ettik. Her katman farklı bir soruya cevap verir.

| Katman | Ne test eder | Nasıl |
|---|---|---|
| Birim ve sözleşme testleri | Her modülün kuralı tek başına doğru mu? (veri alma, karar motoru, anlatıcı doğrulayıcısı, API) | `pytest`, 90 dosyada **1.774** test, başarısız test yok (2026-10-13); ağ erişimi yok, LLM yerine sahte model |
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
| Kanıt toplama / karar süresi (çalıştırma başına ort.) | 0,25 sn / 0,73 sn (en çok 3,31 / 1,11 sn) | yalnızca rapor | — |
| Görüşme metni süresi | ort. 27,08 sn (en çok 56,70 sn) | yalnızca rapor | — |
| Maliyet | metin başına $0,046; paket $1,164 (anlatıcı $1,155, hakem $0,009; sınır $5) | yalnızca rapor | — |
| Hakem: uyarlanmış / RM için açık / dengeli | %52 / %50 / %60 (19 metin) | yalnızca rapor | — |

Bir kontrol yalnızca ilgili senaryoda çalışır; uygulanmayanlar oranlara girmez.

## 3. Senaryo grupları

| Grup | Sayı | Neyi değiştirir | Örnek |
|---|---|---|---|
| Temel | 5 (her biri 2 kez) | Hiçbir şey; P01–P05 olduğu gibi | `base-p01` … `base-p05` |
| Hatalı / çelişkili veri | 3 | Kanıta hata enjekte eder | kaynaklar arası çelişen risk değeri, aralık dışı risk, eskimiş getiri |
| Persona değişikliği (Jüri Challenge tarzı) | 5 | Bir müşteri alanını değiştirir | P03 "Agresif" → "Muhafazakâr"; P03 vade "1 yıl"; P04 likidite "Yüksek"; P01 döviz tercihi bilinmeyen metin; P05 "Dengeli" |
| Kısıt | 4 | Açık kısıt ekler | "döviz maruziyeti istemiyor", "yüksek riskli ürün istemiyor"; bilinmeyen kısıt metni → RM'e soru |
| Veri erişimi | 4 | Bir kaynağı dışlar | TEFAS detay yok; elle girilen veri yok (mevduat oranı, TÜFE, stopaj); TEFAS web yok |
| Regresyon | 13 | Geçmiş hataları sabitler | hata analizi vakaları 1–8 (bölüm 4 ve 5) |

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

**Sonuç (ölçüldü).**

| Persona | D19 öncesi | D19 sonrası (sınıf, risk, 1 yıllık reel getiri %) |
|---|---|---|
| P01 Muhafazakâr | 3 nakit benzeri, risk 1 | değişmedi (kural uygulanmaz; doğru davranış) |
| P02 Dengeli | aynı 3 nakit benzeri, risk 1 | nakit r2 +8,0 · borçlanma r2 +8,4 · dengeli r3 +12,8 |
| P04 Dengeli | aynı 3 nakit benzeri, risk 1 | borçlanma r3 +5,9 · nakit r2 +6,7 · dengeli r3 +3,3 |
| P05 Temkinli | aynı 3 nakit benzeri, risk 1 | 3 nakit benzeri, risk 2 (kendi bandı) |
| P03 Agresif | farklı | dengeli r6 · hisse r7 · katılım fonu r5 +26,3 |

D19 sonrası **hiçbir iki temel persona aynı ilk üçü paylaşmıyor**. Raporun
satırı "1 of 5 base personas share the same recommended top 3" şunu söyler:
aynı setlerin en büyük grubu 1 personadır, yani her persona kendi setini
alır (önce: 4 / 5). Son tam çalışmanın seçimleri de bunu doğrular; bu
seçimler panoda RM'e önerilen ilk 3'tür: P01 PPN/IST/AIS, P02 BVF/NJR/IRF,
P03 GBV/YAY/OKT, P04 OKT/RPP/SUA, P05 BVF/GBL/KSK. Önceki tam raporda
(`20261012-104535-full`) P01 ile P04 ve P02 ile P05 aynı seçimi almıştı.
P03'ün seti yukarıdaki tablodan sonra değişti (son çalışmada: dengeli r6
+2,5 · hisse r7 +18,8 · borçlanma r3 +5,9); sınıf kuralı ve kuralların
hepsi geçmeye devam ediyor.

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
  küçük bir modeldir (Claude Haiku 5.5). Son çalışmada notların hemen
  hepsi "kısmen"dir; "RM için açık" için hiç "evet" yoktur.
- Hakem de değişti (j2 → j3, daha çok bağlam), bu yüzden önce / sonra
  karşılaştırması yaklaşıktır. 19 metinde bir metnin notu yaklaşık 2,6
  puanlık fark yapar.

Hakem puanını bilerek daha fazla optimize etmedik. Bir LLM hakemi için
istem ayarlamak, metni o hakemin zevkine göre ayarlamak olur; bu, RM için
daha iyi bir metin demek değildir. Sonraki adım ikinci bir hakemle uyum
kontrolü ve RM incelemesidir (bölüm 8).

## 6. Diğer bulgular ve iyileştirmeler

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
| N8 | İlk tam eval: metin başına $0,136, olgu paketi 35.000–50.000 token | Bütçe riski | Paket yalnızca metnin ihtiyacını taşır | Sonraki tam eval $0,041; son $0,046 |
| N7 | Hakem gerekçeleri: metin genel, iç değerler (bayrak adları, skorlar) metinde | Müşteriye uyarlanmamış metin | Her öneri bir müşteri ihtiyacına bağlanır; iç değer yasak | Doğrulayıcıda yeni kurallar; hakem puanı belirgin değişmedi |
| N9b | Bölüm başına şema (8 kopya) yapılandırılmış çıktı için çok büyük (HTTP 400 "compiled grammar is too large") | Metin üretilemiyordu | Tüm bölümler için tek cümle şeması | Test şemayı küçük tutar; 25 / 25 LLM metni |
| N9c | Piyasa ortalaması (%43,82) ile ING oranı (%23) pakette aynı adı taşıyordu | Piyasa oranı ING ürün adının yanına yazılabilirdi | Adlandırılmış olgular + etiket kuralı | ING adı olan cümlede yalnızca ING oranı |
| N10 | Panodaki özet canlı denemede 389 karakter (sınır 280) | Özet şablona düşüyordu | Sınır istemde kelimeyle (≈40); sığan tam cümleler tutulur | Kesik cümle yok; aşım doğrulayıcıda kalır |

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

## 7. Öğrenimler

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

## 8. Sınırlar

- **Dondurulmuş anlık görüntü:** sonuçlar 2026-10-10 verisine aittir; başka
  bir piyasa döneminde sıralama farklı olabilir.
- **RM hazırlık süresi ölçülmedi:** sistem süresini ölçtük (kanıt + karar
  ort. ≈ 1,0 sn, görüşme metni ort. ≈ 27 sn); RM'in bugünkü hazırlık süresi ve kazanç
  **[VARSAYIM]**, mentorların cevabına kadar.
- **Hakem bir LLM:** puanlar yön göstergesidir; notların hemen hepsi
  "kısmen"dir, "RM için açık" için hiç "evet" yoktur. İkinci bir hakemle uyum kontrolü sonraya
  kaldı.
- **Risk bantları ve D19 ayarları** tek anlık görüntüde ayarlandı;
  **[VARSAYIM]**, mentorlarla teyit edilecek.
- **Personalar sentetik:** gerçek müşteri verisiyle test yapılmadı.
- **Mevcut portföy yok:** personalar müşterinin varlık dağılımını vermez.
  Dağılım görünümü bantları ve sınıfın en iyi seçeneğini gösterir, bir
  boşluk analizi yapmaz; mevcut portföy girdisi gelecek iştir.
- **Kayıt örneği bir betikle onaylandı:** Teslimat 6'daki onay zamanları
  bir betikten gelir; bir RM'in uygulamada yaptığı onay değildir.
