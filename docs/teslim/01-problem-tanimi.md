# Problem tanımı

> Teslimat 2 · Agent 007 (Yusuf Ardahan Doğru, Öykü Irmak Hatipoğlu) · 2026-10-28.
> Problemin ölçüsü: snapshot `20261017-110343-d12a` (17.10.2026). Test sonuçları:
> değerlendirme `20261017-160939-n12-client-page` (dondurulmuş snapshot
> `20261014-233110-1565`). **[VARSAYIM]** ile işaretli değerler ölçülmedi.

## Problem cümlesi

Private Banking RM'i her müşteri görüşmesinden önce yüzlerce yatırım ürününü
dağınık ve her gün değişen kaynaklardan elle karşılaştırıyor; bu iş yavaş,
müşteriye yeterince uyarlanmıyor, müşteri kısıtlarını kaçırma riski taşıyor ve
önerinin hangi veriye, varsayıma ve gerekçeye dayandığı sonradan gösterilemiyor.

## RM bugün nerede zorlanıyor?

- **Veri toplama:** faiz (TCMB), fon getirisi ve riski (TEFAS), pay verisi
  (Borsa İstanbul) ve mevduat oranları (banka sayfaları) ayrı yerlerde ve her
  gün değişiyor.
- **Karşılaştırma:** getiri, risk, likidite (valör), stopaj ve enflasyon aynı
  anda değerlendirilmeli; nominal getiri tek başına yanıltıcı.
- **Uygunluk:** risk profili ve açık kısıtlar (ör. "döviz maruziyetini
  gerekçesiz artırmama") her ürün için kontrol edilmeli; SPK yerindelik kuralı
  eksik bilgiyle tavsiyeye izin vermiyor.
- **Metin ve kayıt:** görüşme metni çoğu zaman genel kalıyor; önerinin dayandığı
  veri, tarih ve gerekçe geriye dönük gösterilemiyor.

Sektör de bu adıma yatırım yapıyor: UBS, Salesforce ve Morgan Stanley
danışmanlarına görüşme hazırlığı araçları sunuyor.

## Verimizden içgörüler

1. **Elle karşılaştırma ölçeği aşıyor.** P01 (emekli girişimci, Muhafazakâr)
   için evren 1.444 seçenek (815 fon, 37 BYF, 590 pay, 2 ING mevduatı);
   kurallar 1.301'ini eliyor. Kalan 143 seçeneği reel getiriye, vergiye ve risk
   uyumuna göre elle sıralamak bir hazırlık süresine sığmaz.
2. **Nominal getiri yanıltıcı.** ING Turuncu Hesap'ın %23 faizi, stopaj ve
   yıllık TÜFE (%29,73) sonrası **reel −%8,3**. Aynı gün P01'in risk sınırı
   içindeki 37 para piyasası fonu son bir yılda reel **+%6,6** (medyan), en
   iyisi **+%9,6** getirdi.
3. **Yalnızca getiriye bakan bir sıralama herkese aynı ürünü önerir.** İlk
   sürümümüzde kurallar %100 çalışırken 5 personanın 4'ü yalnızca SPK risk
   değeri 1 olan nakit benzeri fonlar aldı. Risk uyumu ve varlık sınıfı
   kuralıyla 5 personada 5 farklı öneri seti çıktı (Teslimat 5).

## Beklenen iş etkisi

| Gösterge | Bugün | Agent 007 ile (ölçüm) |
|---|---|---|
| Hazırlık süresi | **[VARSAYIM]** ~60 dk / görüşme | analiz ~1,18 sn, metin ~24,9 sn (ortalama, 39 analiz, 25 metin); kalan süre RM'in okuması ve onayı |
| Kısıt ihlali | elle kontrol | 34 senaryo, öneri listesi çıkan 37 çalıştırmada **0** (2 çalıştırmada motor durup RM'e soru sordu) |
| Tutarlılık | kişiye bağlı | aynı girdi → aynı sonuç ve aynı metin (5/5 tekrar) |
| Uyarlama | genel metin | 5 personada 5 farklı öneri seti; gerekçe müşterinin önceliklerine bağlı |
| İzlenebilirlik | dağınık | her sayı kaynak, değer tarihi, alınma zamanı ve kanıt kimliğiyle |
| Veri güncelliği | elle, düzensiz | her sabah 07:30'da otomatik veri alımı ve "Veriyi yenile" |

**Kapsam:** çözüm yalnızca görüşme öncesi hazırlığı destekler: önerir,
gerekçelendirir, belirsizliği gösterir ve teyit sorularını üretir. Kararı RM verir;
RM onayı olmadan hiçbir çıktı müşteriye iletilecek biçimde sunulmaz.

<!-- pdf: compact -->
