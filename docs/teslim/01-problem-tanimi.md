# Problem tanımı

> Teslimat 2 · Taslak (2026-10-14) · Sayılar: dondurulmuş veri anlık görüntüsü
> `20261014-102329-8fca` (TEFAS, TCMB EVDS, ING kamuya açık oranlar) ve
> değerlendirme `20261014-105720-full`.
> **[VARSAYIM]** ile işaretli değerler mentorlarla teyit edilecek.

## Problem cümlesi

Private Banking RM'i her müşteri görüşmesinden önce yüzlerce yatırım ürününü
dağınık kaynaklardan elle karşılaştırıyor; bu iş yavaş, müşteriye yeterince
uyarlanmıyor, müşteri kısıtlarını kaçırma riski taşıyor ve önerinin hangi
veriye dayandığı sonradan gösterilemiyor.

## RM bugün ne yapıyor, nerede zorlanıyor?

| Hazırlık adımı | Bugünkü zorluk |
|---|---|
| Veri toplama | Faiz (TCMB), fon getirisi ve riski (TEFAS), mevduat oranları (banka sayfaları) ayrı yerlerde; RM bunları elle birleştiriyor. |
| Karşılaştırma | Getiri, risk, likidite (valör), vergi (stopaj) ve enflasyon aynı anda değerlendirilmeli; nominal getiri tek başına yanıltıcı. |
| Uygunluk | Müşterinin risk profili ve açık kısıtları (ör. "yüksek riskli ürünlerden kaçınma") her ürün için kontrol edilmeli; SPK yerindelik kuralı eksik bilgiyle tavsiyeye izin vermiyor. |
| Görüşme metni | Metin çoğu zaman genel kalıyor; müşterinin hedefine, vadesine ve likidite ihtiyacına göre uyarlanmıyor. |
| Kayıt | Önerinin dayandığı veri, tarih, varsayım ve gerekçe geriye dönük gösterilemiyor. |

## Verimizden içgörüler

1. **Elle karşılaştırma ölçeği aşıyor.** P01 (emekli girişimci, Muhafazakâr)
   için evren 818 seçenek; kurallar 679'unu eliyor (573 risk tavanı, 195 alıma
   kapalı, 69 yeterli geçmiş yok — 130 fon birden fazla kurala takılıyor).
   Kalan 139 seçeneği elle sıralamak bir hazırlık süresine sığmaz.
2. **Nominal getiri yanıltıcı.** ING Turuncu Hesap'ın %23 faizi, stopaj ve
   yıllık TÜFE (%29,73; TÜİK, TCMB EVDS ile aynı) sonrası **reel −%8,3**; aynı müşteri için
   aynı gün erişilebilen para piyasası fonları son bir yılda reel **+%6,6**
   (medyan), en iyisi **+%9,7** getirdi. Reel karşılaştırma yapılmazsa müşteri
   değer kaybettiğini görmeyebilir.
3. **Yalnızca getiriye bakan bir sıralama herkese aynı ürünü önerir.** TL nakit
   benzeri fonlar reel olarak hisse ve altın/döviz fonlarını geride bıraktı:
   uzun vadeli dönemde (çoğunlukla 3 yıl, yıllık) reel getiri medyanı nakit
   benzeri fonlarda +%7,3, hisse fonlarında −%5,4, altın/döviz fonlarında
   −%2,9. İlk sürümümüzde 5 personanın 4'ü yalnızca SPK risk
   değeri 1 olan nakit benzeri fonlar aldı (iki çift tamamen aynı listeyi aldı) —
   Dengeli bir ihracatçı da, Muhafazakâr bir emekli de. Risk bütçesi ve
   çeşitlendirme ayrı sinyaller olarak eklenince her personanın öneri seti
   farklılaştı; bu anlık görüntüde 5 personada 5 farklı set var (bkz. Test ve
   öğrenimler).
4. **Sektör bu adıma yatırım yapıyor.** UBS her görüşme öncesi otomatik
   "cheat sheet", Salesforce "Meeting Prep", Morgan Stanley "Next Best Action"
   (danışmanların %90'ından fazlası kullanıyor) sunuyor; ING Türkiye'nin RM ve
   yatırım ekipleri için geliştirdiği "Genel Yatırım Öneri Platformu" 2026'da
   Stevie ödülü aldı. Görüşme hazırlığı, bankaların önem verdiği gerçek bir
   ihtiyaç.

## Beklenen iş etkisi

| Gösterge | Bugün | Çözümle | Nasıl ölçtük |
|---|---|---|---|
| Hazırlık süresi | **[VARSAYIM]** görüşme başına ~60 dk | analiz ortalama 1 sn (en çok 1,6 sn), görüşme metni ortalama 25 sn (en çok 48 sn); RM'in okuma ve onayı | sistem zamanı (ölçüldü: analiz 39, metin 25 çalışma) |
| Kısıt ihlali | elle kontrol | 34 test senaryosunda (39 çalışma) **0** | değerlendirme paketi |
| Tutarlılık | kişiye bağlı | aynı girdi → aynı sonuç ve aynı metin (%100) | tekrar testleri |
| İzlenebilirlik | yok / dağınık | her sayı kaynak, tarih ve kanıt kimliğiyle | kanıt kaydı |
| Veri güncelliği | elle, düzensiz | her gün 07:30'da otomatik veri alımı ve "Veriyi yenile" düğmesi; süresi geçen stopaj veya eski TÜFE RM'e uyarı verir | zamanlanmış görev, karar kuralı |
| Uyarlama | genel metin | 5 personada 5 farklı öneri seti (önce: 4'ü yalnızca nakit benzeri, risk 1); müşteri önceliklerine bağlı gerekçe | değerlendirme paketi |

Daha az hazırlık süresi RM'e müşteri başına daha fazla zaman bırakır; reel ve
vergi sonrası karşılaştırma müşteriye daha doğru bir tablo sunar; kayıt ise
uyum denetimini kolaylaştırır.

## Kapsam

Çözüm RM'in **görüşme öncesi** hazırlığını destekler: önerir, gerekçelendirir,
belirsizliği gösterir ve teyit sorularını üretir. Kararı ve müşteri iletişimini
RM yapar; RM onayı olmadan hiçbir çıktı müşteriye iletilecek biçimde sunulmaz.
Getiri tahmini, otomatik işlem ve müşteriyle doğrudan etkileşim kapsam dışıdır.
