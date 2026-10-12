# Problem tanımı

> Teslimat 2 · Taslak (2026-10-12) · Sayılar: dondurulmuş veri anlık görüntüsü
> `20261010-183835-6813` (TEFAS, TCMB EVDS, ING kamuya açık oranlar).
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
   için evren 816 seçenek; kurallar 675'ini eliyor (573 risk tavanı, 189 alıma
   kapalı, 69 yeterli geçmiş yok — bir fon birden fazla kurala takılabilir).
   Kalan 141 seçeneği elle sıralamak bir hazırlık süresine sığmaz.
2. **Nominal getiri yanıltıcı.** ING Turuncu Hesap'ın %23 faizi, stopaj ve
   yıllık TÜFE sonrası **reel −%8,3**; aynı müşteri için aynı gün erişilebilen
   para piyasası fonları reel **+%7,4**. Reel karşılaştırma yapılmazsa müşteri
   değer kaybettiğini görmeyebilir.
3. **Yalnızca getiriye bakan bir sıralama herkese aynı ürünü önerir.** Son bir
   yılda TL nakit benzeri fonlar reel olarak hisse (≈ %0) ve altın (−%13)
   fonlarını geride bıraktı. İlk sürümümüzde 5 personanın 4'ü yalnızca SPK risk
   değeri 1 olan nakit benzeri fonlar aldı (iki çift tamamen aynı listeyi aldı) —
   Dengeli bir ihracatçı da, Muhafazakâr bir emekli de. Risk bütçesi ve
   çeşitlendirme ayrı sinyaller olarak eklenince her personanın öneri seti
   farklılaştı (bkz. Test ve öğrenimler).
4. **Sektör bu adıma yatırım yapıyor.** UBS her görüşme öncesi otomatik
   "cheat sheet", Salesforce "Meeting Prep", Morgan Stanley "Next Best Action"
   (danışmanların %90'ından fazlası kullanıyor) sunuyor; ING Türkiye'nin RM ve
   yatırım ekipleri için geliştirdiği "Genel Yatırım Öneri Platformu" 2026'da
   Stevie ödülü aldı. Görüşme hazırlığı, bankaların önem verdiği gerçek bir
   ihtiyaç.

## Beklenen iş etkisi

| Gösterge | Bugün | Çözümle | Nasıl ölçtük |
|---|---|---|---|
| Hazırlık süresi | **[VARSAYIM]** görüşme başına ~60 dk | analiz 1–7 sn, görüşme metni 20–30 sn; RM'in okuma ve onayı | sistem zamanı (ölçüldü) |
| Kısıt ihlali | elle kontrol | 30 test senaryosunda **0** | değerlendirme paketi |
| Tutarlılık | kişiye bağlı | aynı girdi → aynı sonuç ve aynı metin (%100) | tekrar testleri |
| İzlenebilirlik | yok / dağınık | her sayı kaynak, tarih ve kanıt kimliğiyle | kanıt kaydı |
| Uyarlama | genel metin | 5 personada 5 farklı öneri seti (önce: 4'ü yalnızca nakit benzeri, risk 1); müşteri önceliklerine bağlı gerekçe | değerlendirme paketi |

Daha az hazırlık süresi RM'e müşteri başına daha fazla zaman bırakır; reel ve
vergi sonrası karşılaştırma müşteriye daha doğru bir tablo sunar; kayıt ise
uyum denetimini kolaylaştırır.

## Kapsam

Çözüm RM'in **görüşme öncesi** hazırlığını destekler: önerir, gerekçelendirir,
belirsizliği gösterir ve teyit sorularını üretir. Kararı ve müşteri iletişimini
RM yapar; RM onayı olmadan hiçbir çıktı müşteriye iletilecek biçimde sunulmaz.
Getiri tahmini, otomatik işlem ve müşteriyle doğrudan etkileşim kapsam dışıdır.
