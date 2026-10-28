# Test ve öğrenimler

> Teslimat 5 · 2026-10-28 · Kaynaklar: README bölüm 7 (takım onaylı) ve
> `docs/found-and-fixed.md` (tüm düzeltme kaydı). Sayılar: son tam
> değerlendirme `data/eval/20261017-160939-n12-client-page` (dondurulmuş
> snapshot `20261014-233110-1565`, karar yapılandırması `dda3ae095519`,
> anlatıcı `claude-sonnet-5-5` istem `n12`, hakem `claude-haiku-5-5`); ajan
> değerlendirmesi `data/eval/20261015-182316-20261015-agent` (P03 yeniden
> çalıştırması `20261015-183949-20261015-agent-p03`, RM işaretleri
> `20261015-235705-20261015-marks`); 2 senaryoluk yeniden kontrol
> `data/eval/20261017-170013-garanti-fix` (bölüm 5.6). **[VARSAYIM]** ile
> işaretli değerler ölçülmedi.

## 1. Test yaklaşımı

Çözümü dört açıdan test ettik. Her açı farklı bir soruya cevap verir.

| Açı | Ne test eder | Kapsam |
|---|---|---|
| Birim ve sözleşme testleri | Her kural tek başına doğru çalışıyor mu? (veri alma, karar motoru, anlatıcı doğrulayıcısı, ajan, API) | `pytest`: 150 dosyada **3.056** test; web: 51 dosyada **458** test (2026-10-28); ağ erişimi yok, dil modeli yerine sahte model |
| Senaryo değerlendirmesi | Sistem uçtan uca, jürinin değiştirebileceği girdilerle doğru çalışıyor mu? | 34 senaryo, 39 çalıştırma; dondurulmuş snapshot; tek komut `python -m rmprep eval` |
| Ajan değerlendirmesi | Ajan kurallara uyuyor mu, motordan daha iyi mi? | 8 karar: kod denetimi, yedeğe düşme oranı, tekrar, kör A/B hakemi, RM işaretleri (`rmprep eval --agent`) |
| Canlı kontrol ve geri bildirim | Sistem RM için gerçekten kullanışlı mı? | Ekran incelemesi, ücretli canlı kontroller (ör. profil çelişkileri, istem n11/n12), RM işlem kaydından geri bildirim raporu (`rmprep feedback`) |

Senaryo değerlendirmesi her senaryoyu gerçek arka uçtan geçirir: karar,
panoda RM'e önerilen ilk 3'ün onayı, görüşme metni. Kontroller üç türdür:

1. **Deterministik kurallar (kod):** kısıt uyumu, risk tavanı, alıma kapalı
   fon, kaynak atfı, uydurma veri, tekrar tutarlılığı ve diğerleri (15
   kontrol). Hedef %100.
2. **Dil modeli metninin doğrulayıcısı (kod):** metindeki her sayı olgu
   paketinde mi, yalnızca izinli ürünler mi adlandırılıyor, yasak ifade var
   mı, her cümle kanıt kimliği gösteriyor mu. Bir bulgu varsa model bir kez
   daha dener; yine bulgu varsa metin düz şablona düşer.
3. **LLM hakemi (Claude Haiku 5.5):** yalnızca kodun ölçemediği şeyler:
   metin bu müşteriye mi uyarlanmış, RM için açık mı, dengeli mi. Kural
   kontrolleri hakeme bırakılmaz.

Veri dondurulduğu için bir sonuç değişirse kod veya yapılandırma
değişmiştir. Metinler önbellekte tutulur; aynı girdi aynı metni verir. Bu
önbelleğin bir yan etkisi de vardır (bölüm 5.6).

### Senaryo grupları

| Grup | Sayı | Neyi değiştirir | Örnek |
|---|---|---|---|
| Temel | 5 (her biri 2 kez) | Hiçbir şey; P01–P05 olduğu gibi | `base-p01` … `base-p05` |
| Hatalı / çelişkili veri | 3 | Kanıta hata enjekte eder | kaynaklar arası çelişen risk değeri, aralık dışı risk, eskimiş getiri |
| Persona değişikliği (Jüri Challenge tarzı) | 5 | Bir müşteri alanını değiştirir | P03 "Agresif" → "Muhafazakâr"; P03 vade "1 yıl"; P04 likidite "Yüksek"; P01 bilinmeyen döviz tercihi metni; P05 "Dengeli" |
| Kısıt | 4 | Açık kısıt ekler | "döviz maruziyeti istemiyor", "yüksek riskli ürün istemiyor"; bilinmeyen kısıt metni → RM'e soru |
| Veri erişimi | 4 | Bir kaynağı dışlar | TEFAS detay yok; elle girilen veri yok (mevduat oranı, TÜFE, stopaj); TEFAS web yok |
| Regresyon | 13 | Geçmiş hataları sabitler | bölüm 5 ve 6'daki vakalar |
| Ajan (yalnızca `--agent`) | 3 + 5 temel | Ajanın davranışını zorlar | motorun 1. fonu için olumsuz haber (P01); RM'in girdiği dağılım (P03); çöken bir hisseyi izleme (P03) |

Örnek: TEFAS web dışlanınca P01'de 6 seçenek kalır; önerilenler e-Vadeli
mevduat ve bir borsa yatırım fonudur (BTL). Bilinmeyen kısıtta sonuç `needs_rm_input` olur ve motor
hiçbir şeyi sıralamaz.

## 2. Neden bu başarı göstergeleri?

Brif tek bir zorunlu metrik vermez (§9.1). Göstergeleri brifin §9.1'deki
boyutlarından ve kesin kurallarından türettik. İlke basittir: brifin kesin
kurallarında (kısıt, uydurma veri, kaynak, yasak ifade) hedef %100'dür, tek
bir ihlali bile kabul etmiyoruz. Metin kalitesini yalnızca yön göstergesi
olarak okuyoruz, çünkü metni puanlayan hakem de bir dil modelidir ve notu
kod kontrolleri kadar güvenilir değildir.

| Brif boyutu (§9.1) | Göstergemiz | Neden bu gösterge |
|---|---|---|
| Müşteri kısıtlarına uyum | Kural 5 kontrolü; risk tavanı; açık kısıtlar sert kural (D13); alıma kapalı fon yok (D12) | Tek bir ihlal RM'in güvenini bozar; kısıt bir ceza değil, bir filtre olmalı |
| Eksik / çelişkili veri | Eksik veri gösteriliyor; hatalı veri işaretleniyor ve kullanılmıyor; tahmin yerine soru | SPK yerindelik kuralı eksik bilgiyle tavsiyeye izin vermez |
| Kaynak kullanımının doğruluğu | Her seçenek ve her cümle kanıt kimliği gösteriyor (kural 2); uydurma sayı yok (kural 3); doğrulayıcı geçme oranı | Dil modeli metninin en büyük riski uydurma sayıdır |
| Tekrar eden çalışmalarda tutarlılık | Aynı girdi → aynı `run_id`, aynı sonuç, aynı metin; ajan için önbelleksiz tekrar | RM ve denetçi aynı sonucu yeniden üretebilmeli |
| Önerilerin tutarlılığı | Persona değişikliği sonucu beklenen yönde değiştiriyor; çeşitli öneri (D19); hakemin "uyarlanmış" notu | Herkese aynı ürünü öneren bir araç RM'e bir şey katmaz (bölüm 5.1) |
| İşlem süresi | Kanıt, karar ve metin süresi (saniye; yalnızca rapor) | Araç RM'in görüşme hazırlığına sığmalı |
| RM hazırlık sürecine katkı | Geri bildirim raporu: RM'in sildiği bölümler, ajan önerisinin kabul payı, dağılım tahmininin hatası | Gerçek RM kullanımı olmadan katkıyı ancak RM işlemlerinden ölçebiliriz; RM'in bugünkü hazırlık süresi **[VARSAYIM]** |
| Maliyet | Paket başına ve yeni metin başına USD | Değerlendirmenin kendi sınırı 5 $ / paket |

## 3. Sonuçlar (son tam değerlendirme)

`data/eval/20261017-160939-n12-client-page`, snapshot
`20261014-233110-1565`, istem n12:

| Gösterge | Sonuç | Hedef |
|---|---|---|
| Kural kontrolleri (15 kontrol) | %100 | %100 |
| Kısıt ihlali (kural 5) · risk tavanı aşımı | 0 (37/37) · 0 (37/37) | 0 |
| Uydurma veri yok · kaynak atfı | 39/39 · 39/39 | %100 |
| Tahmin yerine soru · eksik veri gösteriliyor | 2/2 · 7/7 | %100 |
| Persona değişikliği sonucu beklenen yönde değiştiriyor | 21/21 | %100 |
| Doğrulayıcı (dil modeli metni, şablona düşmeden) | 24/25 (%96) | ≥ %95 |
| Yasak ifade | 0 | 0 |
| Tekrar tutarlılığı | 5/5 | %100 |
| Süre: karar · görüşme metni | 1,18 sn · 24,9 sn (ortalama) | rapor |
| Değerlendirme maliyeti | tam paket 0,866 $ · yeni görüşme metni başına 0,034 $ | ≤ 5 $ |
| LLM hakemi: uyarlanmış / açık / dengeli | %50 / %50 / %58 | yön göstergesi |

Aynı rapordaki diğer kural kontrolleri de %100 geçti: alıma kapalı fon yok
(D12) 37/37, açık kısıtlar sert kural (D13) 12/12, çeşitli öneri (D19)
20/20, hatalı veri işaretleniyor 3/3, mevcut dağılım toplamı doğru (D27)
37/37. Kanıt toplama ortalama 0,95 sn sürdü (en çok 16,00 sn); karar en çok
2,54 sn, görüşme metni en çok 54,13 sn sürdü.

Kısıt ihlali satırında 39 değil 37 çalıştırma var, çünkü iki çalıştırmada
motor sıralamayı durdurup RM'e soru sordu ve ortada bir öneri listesi yoktu.
Bir kontrol yalnızca ilgili senaryoda çalışır; uygulanmayanlar oranlara
girmez. Hakem her soruya "evet" (1), "kısmen" (0,5) veya "hayır" (0) der;
tabloda bu notların ortalaması yazar. Uyarlanmış ve açık için %50, hakemin
19 metnin hepsine "kısmen" dediği anlamına gelir; hakem hiçbir metne "hayır"
demedi.

Tek kalan hata, 25 metinden birinin şablona düşmesidir
(`bad-p04-risk-out-of-range`). Neden yanlış bir alarmdı; düzeltme ve
düzeltmenin nasıl ölçülmediği bölüm 5.6'dadır.

## 4. Ajan motordan daha iyi mi?

Ajan değerlendirmesinde (`20261015-182316`, 8 karar; ajan
`claude-sonnet-5-5`, istem a2, 10 aday) ajanın tüm kararları (8/8) kod
denetiminden geçti ve hiçbir kararda yedek karara (fallback) düşülmedi.
Sistem ajanın kararlarını kaydeder; aynı istek tekrar gelince model yeniden
çağrılmaz ve kayıtlı karar döner. Bu yüzden aynı istekler aynı kararı verdi
(8/8). Bu bir tutarlılık kanıtı değildir.

Asıl tutarlılık testinde önbelleği boşaltıp aynı girdiyle modeli yeniden
çağırdık. 8 kararın 5'inde ilk 3 aynı kaldı; diğer 3'ünde yalnızca bir ürün
değişti (24 önerinin 21'i korundu). Ajan bir karar için ortalama 28,92 sn
kullandı (en çok 53,83 sn). Davranış senaryoları beklendiği gibi geçti:
motorun 1. fonu PPN için olumsuz haber enjekte edilince ajan PPN'yi listeden
çıkardı; çöken KTLEV hissesi ne motorun ne ajanın ilk 3'üne girdi.

Ajanın önerisini motorunkiyle kıyaslamak için kör bir A/B hakemi kullandık
(Claude Haiku 5.5, rastgele sıra, soru: "Hangisi müşteriye daha uygun ve
neden?"). Hakem sistemi bilmez; yalnızca iki seti ve olgularını görür.

| Tur | Ajan | Motor | Eşit | Not |
|---|---|---|---|---|
| İlk tur (`20261015-182316`) | 5 | 0 | 1 | 2 kararda ilk 3 aynıydı, soru sorulmadı |
| P03 yeniden (`20261015-183949`, aday listesi düzeltildikten sonra) | 0 | 2 | 0 | `agent-rm-split`'te ilk 3 aynı kaldı |
| RM işaretleri (`20261015-235705`) | 1 | 0 | 0 | ✗ işaretli bulgu pakette yok, ✓ işaretli bulgu "RM doğruladı" |
| **Adil karşılaştırmaların toplamı** | **3** | **2** | **1** | ajan: P01, olumsuz haber, RM işaretleri |

İlk turda ajanın 5 kazancının 3'ü P03 senaryolarındaydı ve orada motorun
seçtiği IDY ile OKT ajanın aday listesinde yoktu. Hakem bu iki fonun
verisini göremiyordu; gerekçesi "Set B's two funds lack data" idi. Bu hata
ve düzeltmesi bölüm 5.6'dadır. Düzeltmeden sonra hakem P03'te iki kez de
motoru seçti.

**Sonuç.** Bu sayılar ajanın motordan daha iyi olduğunu göstermez: örnek
küçüktür ve hakem de bir dil modelidir. Bu yüzden RM önce puanlama motorunun
önerilerini görür; isterse ajan araştırmasını ve ajanın önerisini sonradan
başlatır. RM iki listeyi de görür ve kararı kendisi verir.

## 5. Hata analizleri

Geliştirme boyunca bulduğumuz her hatayı ve her yanlış varsayımı, nedenini,
nedeni nasıl bulduğumuzu, düzeltmeyi ve ölçülen sonucu kaydettik (tam liste:
`docs/found-and-fixed.md`). Bu bölüm en öğretici vakaları anlatır.

### 5.1 Herkese aynı öneri (vaka 8, karar D19)

**Ne gördük (2026-10-12).** Dondurulmuş snapshot'ta 5 personanın 4'ü ilk üç
öneri olarak yalnızca nakit benzeri, SPK risk 1 fonlar aldı. İki çift
tamamen aynı listeyi aldı (P01 = P04: Nurol Para Piyasası, İstanbul KV
Borçlanma, Ak Para Piyasası Katılım; P02 = P05: One Portföy Para Piyasası ile
aynı iki fon); İstanbul KV Borçlanma ve Ak Para Piyasası Katılım dördünde de
vardı. Bu grupta Muhafazakâr P01'in yanında Dengeli P02 ve P04 ile Temkinli
P05 de vardı. Tüm kural kontrolleri bu sırada %100 geçiyordu: hiçbir kısıt
ihlal edilmemişti, ama öneri müşteriye uyarlanmamıştı. Bu vaka "kurallara
uyum" ile "iyi öneri" arasındaki farkı gösterdi.

**Nedeni nasıl bulduk.** Değerlendirme paketinin çıktılarını personalar
arasında karşılaştırdık ve skorun bileşenlerini fon fon okuduk:

1. **Geçmiş getiri baskındı.** Son bir yılda TL nakit benzeri fonlar en iyi
   reel getiriyi verdi (TÜFE ve stopaj sonrası +%7–9); dengeli fonlar +%3,
   hisse ≈ %0, altın −%13.
2. **Risk bütçesini kullanan bir ölçüt yoktu.** `low_risk` ölçütü Dengeli
   müşteride de düşük riski ödüllendiriyordu; anapara cezası risk 5 fonları
   ayrıca vuruyordu (P04: risk 5 karma fon 0,02 puan, para piyasası 0,91).
3. **Çeşitlilik yanlış düzeyde ölçülüyordu.** Çeşitlilik `fund_kind`
   üzerinden çalışıyordu; para piyasası, kısa vadeli borçlanma ve katılım
   para piyasası farklı tür ama aynı varlık sınıfıdır (kısa vadeli TL nakit).

Eksik SPK risk değerleri neden değildi (her türde fonların %3–10'u).

**Düzeltme (D19, kullanıcı onayı 2026-10-12).**

| Değişiklik | İçerik |
|---|---|
| Varlık sınıfı | Her seçeneğe `asset_class`: `nakit_benzeri`, `borclanma`, `dengeli`, `hisse`, `altin_doviz` (tür ve ad kurallarıyla; D23'ten sonra çok varlıklı fonlarda TEFAS portföy dağılımıyla) |
| Risk uyumu bandı | `low_risk` yerine `risk_fit`: Muhafazakâr [1, 2], Temkinli [2, 3], Dengeli [3, 5], Agresif [4, 7]; bandın altındaki her seviye için ceza |
| Sınıf kuralı | Dengeli / Agresif müşteride veya çeşitlendirme önceliğinde: sınıf başına en çok 1, en çok 1 nakit benzeri öneri |
| Reel getiri tabanı (D19b) | Sınıf kuralı negatif 1 yıllık reel getirili bir fonu öne çıkaramaz |

İlk denemede `per_step` 0,25 idi; Dengeli personaların önerileri risk 2'de
kaldı. `per_step` 0,5 ve `risk_fit` ağırlığı 2,0 ile öneriler bandın içine
girdi. Bantlar bir **[VARSAYIM]**; mentorlarla teyit edilecek.

**Ölçülen sonuç.** D19 anındaki ölçüm (snapshot `20261010-183835-6813`;
sınıf, SPK risk değeri r, 1 yıllık reel getiri %) ve son tam değerlendirmenin
önerdiği ilk 3:

| Persona | D19 öncesi | D19 anında | Son tam değerlendirme (n12) |
|---|---|---|---|
| P01 Muhafazakâr | 3 nakit benzeri, risk 1 | değişmedi (sınıf kuralı uygulanmaz; doğru davranış) | PPN · OSD · AIS |
| P02 Dengeli | aynı 3 nakit benzeri, risk 1 | nakit r2 +8,0 · borçlanma r2 +8,4 · dengeli r3 +12,8 | EIL · KDE · NJR |
| P04 Dengeli | aynı 3 nakit benzeri, risk 1 | borçlanma r3 +5,9 · nakit r2 +6,7 · dengeli r3 +3,3 | RPP · OKT · TCF |
| P05 Temkinli | aynı 3 nakit benzeri, risk 1 | 3 nakit benzeri, risk 2 (kendi bandı) | EIL · GBL · KSK |
| P03 Agresif | farklı | dengeli r6 · hisse r7 · katılım r5 +26,3 | ASELS (pay) · IDY · OKT |

D19'dan sonra **hiçbir iki temel persona aynı ilk üçü paylaşmıyor**. Raporun
satırı "1 of 5 base personas share the most common recommended top 3" şunu
söyler: aynı setlerin en büyük grubu 1 personadır (önce: 4 personada yalnızca
nakit benzeri fonlar). Bazı fonlar birden çok personada yer alır (EIL P02 ve
P05'te, OKT P03 ve P04'te), ama hiçbir set aynı değildir. Kalıcılık için dört
regresyon senaryosu (`reg-d19-p02-diverse`, `reg-d19-p04-diverse`,
`reg-d19-p01-unchanged`, `edit-p05-dengeli`) ve yeni kontrol
`diverse_recommendations` eklendi; son tam değerlendirmede bu kontrol 20/20
geçti.

### 5.2 Profil kendisiyle çelişiyordu ve hiçbir şey bunu göstermiyordu (W42–W44)

**Ne gördük (2026-10-17).** Bir müşteri profili kendisiyle çelişebilir:
"Muhafazakâr" risk profili ile büyüme önceliği; `durum` alanında "gelecek yıl
ev peşinatı" ile likidite ihtiyacı "Düşük"; RM notunda "45 yaşında" ile `yas`
62. Yüklenen bir dosya motorun okuyamadığı değerler de taşıyabilir. Hiçbir
şey bunu işaretlemiyordu ve RM'in bu konuda ne yaptığı kaydedilmiyordu.

**Nedeni nasıl bulduk.** Beş personaya bilerek çelişki yerleştirip canlı
kontrol yaptık. Motor yalnızca sabit değerleri okuyordu (risk seviyesi,
likidite seviyesi, eşleşen öncelikler); serbest metin ve bilinmeyen değerler
sessizce geçiyordu. "Teyit edin" onay kutuları da yalnızca tarayıcıda
duruyordu.

**Düzeltme: üç katman.**

| Katman | İçerik |
|---|---|
| Sabit kurallar (W42) | Motorun kendi okuması üzerinde kurallar: risk ile büyüme önceliği, Agresif ile anapara koruma, likidite seviyesi ile likidite öncelikleri, döviz "Açık" ile döviz sınırı (çelişki); 5+ yıl vade ile yüksek likidite ihtiyacı (sorulacak) |
| AI kontrolü (W43) | Tüm profilin tek bir Claude Opus 5.5 kontrolü. Her bulgu iki tarafı kelimesi kelimesine alıntılamalı; **sunucu bir bulguyu yalnızca her alıntı adı verilen alanda varsa tutar.** Profil başına ≈ 0,015 $, önbellekli |
| RM gerekçesi (W44) | Bir çelişki, onaydan önce RM'in kısa bir gerekçesini ister ("Müşteriyle teyit edildi: …"); gerekçe çalıştırmayla, RM işlem kaydında ve kartta tutulur. Bitmemiş bir AI kontrolü onayı engellemez |

**Ölçülen sonuç (canlı kontrol, 7 profil, 0,10 $, profil başına 2–13 sn).**

| Ölçü | Sabit kurallar | AI kontrolü |
|---|---|---|
| Yerleştirilmiş 5 çelişkiden bulunan | 0 / 5 | 5 / 5 |
| Atılan alıntı (alanında olmayan) | — | 0 |
| P01, P03, P05'te yanlış alarm | 0 | 0 |

AI kontrolü P02 ve P04'te iki gerçek nokta da buldu: motor P02'nin döviz
metnini okuyamamış ve güvenli seviye "Sınırlı"yı kullanmıştı; P04'ün
"kuşaklar arası planlama" önceliğinin sıralamaya hiçbir etkisi yoktu. İkisi
de "sorulacak" türündedir ve onayı engellemez.

Öğrenim: sabit kurallar yalnızca motorun okuduğunu görür. Serbest metni bir
dil modeli okuyabilir; ama modelin her bulgusunu kod doğrulamalıdır (burada:
alıntılar). Bu örnek küçüktür (tek canlı deneme, 5 yerleştirilmiş çelişki).

### 5.3 İlk sayfa ~33 sn, her müşteri geçişi ~6 sn sürüyordu (hız)

**Ne gördük (2026-10-17).** Uygulamada ilk sayfa yaklaşık 33 sn, her müşteri
geçişi yaklaşık 6 sn sürüyordu.

**Nedeni nasıl bulduk.** Her adımı yeni bir süreçte zamanladık, sonra
cProfile ile profilledik. Üç ayrı neden çıktı; hiçbiri tahmin ettiğimiz yerde
değildi:

1. Claude web araması **yedeği**, sunucu açılışında Anthropic SDK'sını
   yüklüyordu (9,6 sn).
2. Motorun `EvidenceIndex.quantities_of` sorgusu, 1.442 çağrının her birinde
   yaklaşık 30.000 satırı tarıyordu (profilleyicide 13,3 sn'nin 10,9 sn'si).
3. En yeni snapshot (32.662 satır) ilk istekte okunuyordu (18 sn).

**Düzeltme.** (1) SDK ilk kullanımda yüklenir (ajan ve araştırma
istemcileri). (2) Varlığa göre bir dizin bir kez kurulur. Aynı satırlar, aynı
sıra: 276 varlık karşılaştırıldı, 0 fark; ilk 3 aynı kaldı. (3) Sunucu
açılışta snapshot'ı ve SDK'yı arka planda yükler; bir kilit, ikinci bir okuma
yerine isteği bu okumayı beklemeye alır.

**Ölçülen sonuç.**

| Ölçü | Önce | Sonra |
|---|---|---|
| Sunucu açılışı | 8,7 sn | 2,3 sn |
| Motor, müşteri başına | 6,2 sn | 1,4 sn |
| Değerlendirmede karar, çalıştırma başına (aynı 34 senaryo) | 2,86 sn (15.10, `20261015-013525-20261015-final`) | 1,18 sn (17.10, n12) |
| Önerilen ilk 3 | — | değişmedi |

Not: değerlendirmedeki karar süresi çalıştırmadan çalıştırmaya oynar. Aynı
34 senaryonun 14–15.10'daki iki tam çalıştırması 1,67 sn ve 1,94 sn verdi.
Bu yüzden asıl ölçü, geliştirme sırasındaki adım zamanlamasıdır (6,2 → 1,4
sn).

### 5.4 Pay fiyat geçmişinde ani düşüşler (bölünme düzeltmesi, I11b–I11e)

**Ne gördük (2026-10-14).** BIST pay geçmişinde ani sıçramalar vardı;
KORDS'un 1 aylık getirisi −%96 görünüyordu.

**Nedeni nasıl bulduk.** Bilinen şirket işlemlerinin (bölünme, bedelsiz)
çevresindeki fiyatlara baktık. Bültendeki "önceki kapanış" sütunu (`ONCEKI
KAPANIS FIYATI`) bölünmeye göre düzeltilmemişti ve `REFERANS FIYAT` 0'dı.
Bu yüzden düzeltme kuralımız hiç çalışmamıştı.

**Düzeltme.** Günlük fiyat limiti ±%10'dur. Bir kapanışın önceki kapanışa
oranı ±%10,5'in dışındaysa bunu şirket işlemi sayarız ve önceki tüm
kapanışları o oranla düzeltiriz (I11b). O günün taban fiyatını günlük limitle
uyumlu bir aralığa sıkıştırırız (I11c). Nakit temettüler limitin altında
kalır ve düzeltilmez; getiriler fiyat getirisidir. Açılış fiyatının taban
fiyatı temsil etmesi bir **[VARSAYIM]**'dır.

**Ölçülen sonuç (snapshot `20261014-164524-42c2`, 276 bülten dosyası).** 111 payda 116 düzeltme. KORDS 1 ay:
−%96 → −%27,8. Açılış 116 günün 99'unda aralığın içindeydi, 17 günde
sıkıştırıldı; HRKET 1 ay +%93,2 → +%75,9. Bazı paylar düzeltmeden sonra da
1 ayda yaklaşık −%90 gösterir (ANELE, GUNDG, TEHOL): art arda yaklaşık 20
taban günü gerçektir, şirket işlemi değildir.

**İlgili bir hata (I11e).** 5 yıllık geçmiş 15.02.2023'te kesiliyordu. İlk
5 yıllık veri alımı 8–14.02.2023 bültenlerini "okunamaz" işaretlemişti
("kapanışı olan 0 pay"). Neden: 6 Şubat 2023 depreminden sonra borsa
kapalıydı ve bir koruma kuralı boş günleri bozuk dosya sayıyordu. Düzeltme:
kapanışı 0 olan geçerli bir bülten = işlem olmayan gün. Sonuç: tam 5 yıllık
geçmiş.

### 5.5 ING'nin kendi oranları eskimişti (I14)

**Ne gördük (2026-10-16).** ING mevduat oranları 10.10'da elle bir dosyaya
kopyalanmıştı. Motor e-Vadeli seçeneği için %35,00 kullanıyordu.

**Nedeni nasıl bulduk.** ING'nin kamuya açık oran sayfasını (3 adımlı form
geri gönderimi) okuduk ve elle girilen dosyayla karşılaştırdık: 28 e-Vadeli
oranı değişmişti. Elle girilen bir dosya zamanla eskir.

**Düzeltme.** ING'nin oran sayfası için bir adaptör ekledik (robots.txt ve
kullanım şartları kontrol edildi). Elle girilen dosyalar yedek olarak kalır.
Sayfa veya tablo değişirse kaynak hata verir ve önceki iyi snapshot
kullanılır; hiçbir zaman yarım satır yazılmaz.

**Ölçülen sonuç.** Motor, kullandığı hücrede (32–45 gün, 99.999,99–250.000
TL) %35,00 yerine 16.10 sayfasının güncel %34,50'sini kullanır; 7–15 gün
hücresi %33,00 → %32,00. Not: değerlendirmenin dondurulmuş snapshot'ı
(14.10) bu adaptörden öncedir; değerlendirmedeki ING oranları elle girilen
dosyadan gelir.

### 5.6 Değerlendirmenin kendi hataları

Değerlendirme de bir koddur ve hata yapar. Dört vaka bulduk. Ortak öğrenim:
bir ölçüm "beklenmedik derecede iyi" veya "değişmemiş" görünürse önce
ölçümün kendisini kontrol et.

**(a) A/B hakemi adil olmayan bir karşılaştırma görüyordu (2026-10-15).**

- *Ne gördük:* ilk turda A/B hakemi 5 kez ajanı, 0 kez motoru seçti. P03'teki
  gerekçeleri tuhaftı: "Set B's two funds lack data".
- *Nedeni nasıl bulduk:* hakemin girdilerini okuduk. P03'te D19 sınıf kuralı
  motorun IDY ve OKT seçimlerini 10. sıranın altından almıştı. Ajan yalnızca
  ilk 10 adayı görüyordu. Bu yüzden ajan bu iki fonu tutamadı (2
  değişiklik zorunluydu) ve hakem onların olgularını göremedi. Ajanın 5
  "kazancının" 3'ü adil değildi.
- *Düzeltme:* aday listesi (`candidates()`) artık motorun ilk 3'üyle başlar
  ve 10'a kadar ekran sırasıyla dolar. Üç P03 senaryosu yeniden çalıştırıldı.
- *Ölçülen sonuç:* yeniden çalıştırmada hakem iki kez de motoru seçti. Adil
  toplam: ajan 3, motor 2, eşit 1 (bölüm 4). Düzeltmeden önceki "%100 ajan"
  sonucu bir ölçüm hatasıydı.

**(b) Eski metin önbelleği (2026-10-12).** D19'dan sonra seçim kuralı
düzeltilip paket yeniden çalıştırıldığında **anlatıcı maliyeti 0 $** çıktı:
P02–P05 için seçim değiştiği hâlde yeni metin üretilmemişti. Metin
önbelleğinin anahtarı yalnızca çalıştırma kimliği, dil, istem sürümü ve
modeldi; RM seçimi anahtarda yoktu, bu yüzden kontroller eski metni
değerlendirdi. Düzeltme (N12): önbellek anahtarına modelin gördüğü olgu
paketinin özeti (sha256, 10 karakter) eklendi; bir çalıştırmanın yeni onayı
önceki metni ve düzenlemeleri siler. Sonraki çalıştırma
(`20261012-201431-full`) 25 yeni metin üretti (1,04 $) ve tüm hedefleri
karşıladı.

**(c) "Garanti Portföy" yasak ifade sayıldı ve yeniden kontrol bunu ölçmedi
(2026-10-17).**

- *Ne gördük:* n12 tam değerlendirmesinde 25 metnin 1'i şablona düştü
  (doğrulayıcı %96). Hata listesi cümleyi ve bulguyu verdi: "Fon sepeti
  grubunda Osmanlı OLE, Garanti Portföy GZP ve İstanbul IRF bulunur." →
  yasak ifade "garanti".
- *Neden:* doğrulayıcı yasak ifade taramasından önce fonların tam adlarını
  ve kısa adlarını çıkarıyordu, ama "ihraççı + fon kodu" biçimini
  çıkarmıyordu. Kısa n12 metinleri bu biçimi daha sık yazar. (Aynı ailenin
  ilk vakası N5 idi: "GARANTİ PORTFÖY" tam fon adı.)
- *Düzeltme:* doğrulayıcı adı geçen her fonun ihraççısını ihraççı
  sözcüğüyle birlikte ("garanti portföy") da çıkarır. Başka bir yerdeki
  "garanti" hâlâ bir bulgudur. İki yönlü birim testi:
  `test_the_issuer_with_its_code_passes` ve
  `test_a_real_garanti_next_to_the_issuer_still_fails`.
- *Yeniden kontrol ne ölçtü:* düzeltmeden sonra 2 senaryoluk bir kontrol
  çalıştırdık (`20261017-170013-garanti-fix`: `bad-p04-risk-out-of-range` ve
  `base-p04`, 3 çalıştırma). Rapor doğrulayıcıyı **%67 (2/3)** gösterir ve
  aynı hatayı aynı cümleyle yeniden listeler. Neden: anlatıcı önbelleği
  şablona düşen metni de, son denemenin bulgularıyla birlikte kaydeder.
  Yeniden kontrol üç metni de önbellekten okudu (anlatıcı maliyeti 0,000 $,
  metin süresi ortalama 0,97 sn). Model çağrılmadı ve yeni doğrulayıcı bu
  metin üzerinde hiç çalışmadı. Yani bu rapor düzeltmeyi **ölçmedi**; eski
  sonucu tekrarladı. Kural kontrolleri bu raporda da %100'dür.
- *Bugünkü durum:* düzeltmeyi yalnızca birim testleri gösterir. Tam
  değerlendirme yeniden çalıştırılmadı; son ölçüm hâlâ %96'dır. Ölçmek için
  bu metnin önbellek dosyası yeni bir model çağrısıyla yeniden üretilmelidir
  (bölüm 9).

**(d) Piyasa notunda yanlış "uydurma veri" alarmı (vaka 9, 2026-10-14).**
Snapshot `20261014-233110-1565` ile ilk tam çalıştırmada 25 metnin hepsi
kural 3'te kaldı. Neden: kod tarafından yazılan piyasa notu kendi EVDS
satırlarını (ör. USD/TRY "49,28") gösteriyordu, ama kontrol yalnızca karar
sonucunun satırlarına izin veriyordu. Düzeltme: bir cümle, kendi gösterdiği
satırların değerini ve tarihini kullanabilir; aynı sayı kaynak göstermeden
yine kalır. Sonuç: %100.

### 5.7 Metin kalitesi ve hakem (N13, N16)

**Ne gördük (2026-10-12).** `20261012-201431-full` çalışmasında kural ve
doğrulayıcı kontrolleri %100 geçti, ama hakem notları düşüktü (uyarlanmış
%57, RM için açık %50, dengeli %50). Hakem gerekçelerini ve metinleri
okuduk. Anlatıcıda doğrulanan nedenler: seçenek başına risk, erişim ve ücret
olgusu yoktu (19 metnin 11'inde dikkat bölümünde yalnızca geçmiş getiri
cümlesi vardı); nominal getiri reel getiriden önce geliyordu; "geçmiş
getiri" uyarısı metin başına yaklaşık 6 kez geçiyordu.

**Düzeltme.** İstemler n7–n9: olgu paketinde seçenek başına risk satırı,
önce reel getiri, uyarı yalnızca dikkat bölümünde; doğrulayıcıya ölçülebilir
yeni kurallar (`repeat`: dikkat bölümü öneriyi tekrar etmez; `compare`: ING
mevduatı ile piyasa ortalaması yalnızca RM'e özel notta). 2026-10-17'de bir
takım üyesi müşteri sayfasını inceledi; bu inceleme istemi bir kez daha
değiştirdi (N16, n11–n12: fon başına 1–2 cümle, ortak risk bir kez, fon adı
cümlenin başında değil, iki fikir ";" ile birleşmez). Canlı kontrolde 10
metnin hepsi doğrulayıcıdan geçti; teklif metninde 100 karakteri aşan cümle
2/16'dan 0/17'ye indi.

**Hakem notlarının seyri.**

| Değerlendirme | İstem | Kural kontrolleri | Hakem: uyarlanmış / açık / dengeli |
|---|---|---|---|
| `20261012-201431-full` | n6 | %100 | %57 / %50 / %50 |
| `20261013-004507-full` | n9 | %100 | %52 / %50 / %60 |
| `20261015-013525-20261015-final` | n10 | %100 | %55 / %52 / %62 |
| `20261017-160939-n12-client-page` | n12 | %100 | %50 / %50 / %58 |

**Yorum.** Nesnel ölçüler iyileşti, hakem notu ise yerinde kaldı. Hakem
katıdır ("kararsızsan düşük olanı seç" kuralı) ve küçük bir modeldir; son
çalışmada 57 notun 54'ü "kısmen"dir. Hakemin ölçütü RM notu için yazıldı,
müşteri sayfası için değil. Hakem de değişti (j2 → j3, daha çok bağlam);
bu yüzden önce / sonra karşılaştırması yaklaşıktır.

**Hakem notunu bilerek optimize etmedik.** Bir LLM hakemi için istem
ayarlamak, metni o hakemin zevkine göre ayarlamak olur; bu, RM için daha iyi
bir metin demek değildir. Bunun yerine ölçülebilir kurallar ekledik ve RM
incelemesine güvendik. Sonraki adım ikinci bir hakemle uyum kontrolüdür
(bölüm 9).

## 6. Diğer bulgular ve iyileştirmeler

Tümü `docs/found-and-fixed.md`'de veya regresyon senaryosu olarak
değerlendirme raporundadır.

| # | Ne gördük | Etki | Düzeltme | Ölçülen sonuç |
|---|---|---|---|---|
| D24 | Stopaj ve TÜFE yokken fonun veri güveni 1,00 kalıyordu | Eksik veri gizleniyordu; "eksik veri gösteriliyor" 5/7 | Reel getiri hesaplanamazsa güven × 0,8. Eski bir "kontrol gerekli" bayrağı bu açığı gizliyordu ve kontrol yanlış nedenle geçiyordu | 5/7 → 7/7 (`20261014-104638-nollm-check` → `20261014-105544-nollm-check2`) |
| D9 | Skor nominaldi; %23 mevduat, %29,73 TÜFE ile vergi sonrası reel −%8,3 | Mevduat referansı her fonun üstünde görünüyordu | Vergi sonrası reel getiri | P01 referansı 0,912 → 0,568; en iyi fon 0,837 |
| D12 | 809 fonun 189'u TEFAS'ta işlem görmüyor veya kapalı | Her personanın ilk 20'sinde 1–4 alınamaz fon | `not_buyable` reddi | Listede 0; 189 reddedildi |
| D13 | Açık kısıtlar yalnızca cezaydı | P02'de 8 döviz fonu listede kaldı | Sert kural | P02: listede 0, 14 reddedildi; P05: en çok valör 3 |
| D15 | P05'te VKR, ZPO, ZTV kanıt kimliksiz listelendi | Kural 2 ihlali | Kısa geçmiş kuralı | Kanıtsız seçenek yok; 57 fon `short_history` reddi |
| D25 | Sınıf kuralının uzak sıradan seçtiği öneriler kararlılık 0,00 aldı (snapshot `20261014-102329-8fca`: P03 IDY sıra 42, OKT sıra 57) | İlk 3'ün kararlılığı anlamlı değildi; `low_stability` uyarısı yalnızca 1–3. sıraya bakıyordu | Kararlılık = 30 bozulmuş çalıştırmada öneri kuralının onu yeniden önerme payı; uyarı tüm önerilere bakar | P03 IDY ve OKT 0,00 → 1,00; P01–P05'in tüm önerileri ≥ 0,83 |
| #1 | Araştırma panelinde bir haber maddesi ham JSON ile bitiyordu | Demo kaydında görüldü | Bozuk JSON parçası kesilir; kayıtlı sonuçlar okunurken onarılır | Madde düzgün biter; 3 yeni test |
| #2 | Düzenlenmiş profil onaylanamıyordu, oysa kural buna izin veriyordu | Demo kaydı durdu | Kural API'de kaldırılmıştı ama gerçek arka uçta ve bir testte kalmıştı; ikisi de düzeltildi | Düzenlenmiş P03 onaylanır |
| #6 | Dağılım onayından sonra ajan araştırması "silindi" | RM işi kayboldu | Yeni dağılım yeni bir çalıştırmadır; API ajanı yeni çalıştırmada aynı aday sayısıyla başlatır | Araştırma kaybolmaz; tekrar maliyetsiz (önbellek) |
| #7 | "Kategorileri gör" 20 fon gösterirken adım 141 aday diyordu | Sayılar tutmuyordu | Kategoriler fonun neye yatırım yaptığına göre, tüm puanlı seçenekler üzerinden | Sayılar adım sayısına eşit (P01: 143 = 143) |
| #11 | Diğer bankaların oran bloğu hiç görülmüyordu | Blok, gerçek bir çalıştırmanın hiç açmadığı bir çekmecedeydi (gerçek veride e-Vadeli seçeneği sıra 73–382) | Oranlar her zaman görünen "Piyasa notu"na da girer | Her müşteride görünür; ilk kontrol örnek veriyle yapılmıştı |
| N8 | İlk tam değerlendirmede metin başına 0,136 $ | Bütçe riski | Olgu paketi yalnızca metnin ihtiyacını taşır | Son tam değerlendirmede yeni metin başına 0,034 $ |

## 7. Öğrenimler

1. **"Kurallar %100" yeterli değildir.** Herkese aynı öneri (5.1) tüm
   kontroller yeşilken oluştu. Çıktılar arası karşılaştırma ve insan
   incelemesi gerekti.
2. **Geçmiş getiri tek başına baskın olur.** Bir yıllık veri, piyasa
   koşulunu herkese uygular. Müşteri profili (risk bandı, varlık sınıfı)
   ayrı bir sinyal olmalıdır.
3. **Kesin kurallar cezalardan güvenilirdir.** Kısıtlar (D13) ve çeşitlilik
   (D19) ceza olarak kaldığında yüksek skor onları aştı. Sert filtre ve seçim
   kuralı sonucu öngörülebilir ve test edilebilir yaptı.
4. **Dil modelinin bulgusunu kod doğrulamalıdır.** Profil kontrolünde (5.2)
   model serbest metindeki çelişkileri buldu; sunucu her alıntıyı alanında
   aradı. Ajanın her önerisi de kod denetiminden geçer (8/8).
5. **Önce ölç, sonra düzelt.** Yavaşlığın üç nedeni de tahmin ettiğimiz
   yerde değildi (5.3); cProfile onları buldu. Düzeltme ilk 3'ü
   değiştirmedi, çünkü aynı satırları aynı sırayla karşılaştırdık.
6. **Veriyi bilinen olaylarla sına.** Bölünme düzeltmesi (5.4) ve deprem
   günleri, bilinen şirket işlemlerine ve tarihlere bakınca ortaya çıktı.
7. **Elle girilen veri eskir.** ING oranları (5.5) 10.10 ile 16.10
   arasında değişti. Otomatik kaynak birincil, elle girilen dosya yedek olmalıdır.
8. **Bir karşılaştırma ancak iki taraf aynı bilgiyi görürse adildir.**
   A/B hakemi (5.6 a) motorun fonlarını göremediği için ajanı seçiyordu.
9. **Önbellek bir değişikliği gizleyebilir.** İki kez oldu: 2026-10-12'de
   eski metin döndü (5.6 b); 2026-10-17'de yeniden kontrol, şablona düşmüş
   eski metni okudu ve doğrulayıcı düzeltmesini ölçmedi (5.6 c). Maliyet 0 $
   ve çok kısa metin süresi bunun işaretiydi.
10. **Bir kural değişikliği her katmanda aranmalıdır.** Düzenlenmiş profil
    kuralı API'de değişti, gerçek arka uçta ve bir testte eski hâliyle kaldı
    (bölüm 6, #2).
11. **Bir ekran değişikliğini gerçek veriyle kontrol et.** Diğer bankaların
    oran bloğu örnek veride görünüyordu, gerçek veride hiç görünmüyordu
    (bölüm 6, #11).
12. **Bir LLM hakemine göre optimize etmek bir tuzaktır.** Metin nesnel
    ölçülerde iyileşti, hakem notu yerinde kaldı (5.7). Hakemin zevkine göre
    ayar yerine ölçülebilir kurallar ekledik.

## 8. Sınırlar

- **Dondurulmuş snapshot:** değerlendirme sonuçları
  `20261014-233110-1565` snapshot'ına (2026-10-14 akşamı) aittir; başka bir
  piyasa döneminde sıralama farklı olabilir. Bu snapshot ING oran
  adaptöründen (16.10) öncedir.
- **RM hazırlık süresi ölçülmedi:** sistem süresini ölçtük (karar ort. 1,18
  sn, görüşme metni ort. 24,9 sn); RM'in bugünkü hazırlık süresi ve kazanç
  **[VARSAYIM]**.
- **Hakem bir LLM:** notlar yön göstergesidir; son tam değerlendirmede 57
  notun 54'ü "kısmen"dir. İkinci bir hakemle uyum kontrolü yapılmadı.
- **Ajan karşılaştırması küçük:** adil A/B karşılaştırmaları 6 karardır
  (ajan 3, motor 2, eşit 1); önbelleksiz tekrarda 8 kararın 5'i aynı kaldı.
- **Profil kontrolü tek canlı deneme:** 5 yerleştirilmiş çelişki ve 7
  profil; daha geniş bir çelişki seti test edilmedi.
- **Risk bantları ve D19 ayarları** tek snapshot'ta ayarlandı;
  **[VARSAYIM]**, mentorlarla teyit edilecek.
- **Personalar sentetik:** gerçek müşteri verisiyle test yapılmadı.
- **Geri bildirim raporu gerçek RM kullanımı görmedi:** RM işlem kaydı
  yalnızca kendi test işlemlerimizi içerir; rapor hiçbir ayarı kendiliğinden
  değiştirmez. Otomatik değerlendirme döngüsü gelecek iştir.
- **Pay getirileri fiyat getirisidir:** nakit temettüler düzeltilmez.

## 9. Hâlâ açık konular

- **TEFAS sıfırları:** TEFAS bazı günlerde bir fonun fiyatını ve
  büyüklüğünü 0 olarak yayımlar (son snapshot'ta 45 fon); bu sıfırları
  henüz işaretlemiyoruz (I9, planlı).
- **Doğrulanmamış EVDS serileri:** bazı EVDS serileri (BIST 100 getiri
  endeksi, altın, …) elle doğrulanmadı; bu seriler hâlâ "doğrulanmamış
  seri" bayrağı taşır.
- **Garanti düzeltmesinin ölçümü:** düzeltme birim testleriyle
  korunuyor, ama tam değerlendirmede ölçülmedi (5.6 c). Bir sonraki
  ücretli tam değerlendirmede bu metin yeniden üretilmelidir.
- **Hakemin ölçütü:** hakem (Claude Haiku) neredeyse her metne "kısmen"
  der ve ölçütü müşteri sayfası için değil, RM notu için yazılmıştır (n10 →
  n12: uyarlanmış %55 → %50, açık %52 → %50, dengeli %62 → %58; kural
  kontrolleri %100'de kaldı).
- **İkinci hakem ve RM incelemesi:** yapılmadı; mentorlarla ve gerçek
  RM'lerle yapılmalıdır.
