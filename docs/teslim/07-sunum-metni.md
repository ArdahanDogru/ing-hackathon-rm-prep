# Sunum metni ve demo planı

> Teslimat 7 · Agent 007 (Yusuf Ardahan Doğru, Öykü Irmak Hatipoğlu) · 2026-10-28.
> Süre: **10 dakika sunum ve demo, 5 dakika soru-cevap.** Slaytlar:
> `docs/teslim/sunum/07-sunum.pptx` (PowerPoint, yalnızca Arial; PDF kopyası
> `docs/teslim/pdf/07-sunum.pdf`). Her slaytın konuşmacı notunda konuşmacı,
> hedef süre ve söylenecekler yazar. Sayıların kaynağı README ve Teslimat 2–6.

## 1. Akış

| # | Slayt | Konuşan | Süre | Toplam |
|---|---|---|---|---|
| 1 | Kapak | Öykü | 0:10 | 0:10 |
| 2 | Problem ve iş etkisi | Öykü | 0:50 | 1:00 |
| 3 | Kararı kod hazırlar, dil modeli yazar, son söz RM'in | Öykü | 0:40 | 1:40 |
| 4 | Her sayı kaynağı, tarihi ve kanıt kimliğiyle | Öykü | 0:40 | 2:20 |
| 5 | Önce katı kurallar, sonra şeffaf puan | Ardahan | 0:45 | 3:05 |
| 6 | Belirsizliği saklamıyoruz: tahmin yerine soru | Ardahan | 0:40 | 3:45 |
| 7 | Ajan sınırlar içinde çalışır | Ardahan | 0:45 | 4:30 |
| 8 | RM görmeden ve onaylamadan hiçbir şey ilerlemez | Öykü | 0:30 | 5:00 |
| 9 | Canlı demo (P02) | Ardahan ekranı kullanır, Öykü anlatır | 3:00 | 8:00 |
| 10 | Test sonuçları ve ajan değerlendirmesi | Ardahan | 0:45 | 8:45 |
| 11 | Bulduğumuz hatalar ve iyileştirmeler | Ardahan | 0:40 | 9:25 |
| 12 | Sınırlar, sonraki adımlar, kapanış | Öykü | 0:30 | 9:55 |

Ek slaytlar (E1–E10) yalnızca soru-cevap içindir. Konuşmacı dağılımı bir
öneridir; prova sonrası değiştirilebilir. 8:00'de demo bitmediyse 2:30 adımını
(koşul değişikliği) atlayın; jüri zaten bir koşul değiştirecek.

## 2. Demo adımları (3:00)

Hazırlıkta açık olanlar: uygulama (`http://127.0.0.1:8600`), P02 seçili,
ajan sonucu kayıtlı (bölüm 3). Tarayıcı tam ekran, yakınlaştırma %100.

| Zaman | Ekranda | Söylenecek |
|---|---|---|
| 0:00 | P02 hazırlık sayfası; "Sorulacak" kartları; piyasa notunda bir **K**'ya tıkla | "Yapay zekâ profilde iki soru buldu. Her sayının kaynağı, değer tarihi ve alınma zamanı var." |
| 0:30 | "Bu öneriler nasıl seçildi?" → "Elenenleri gör" | "1.444 seçenekten 1.138'i elendi; 15'i döviz kısıtı yüzünden. Her elemenin gerekçesi ve kanıtı burada." |
| 1:00 | EIL'e tıkla: fon kartı, "Neden bu öneri?" | "Puanın her parçası, geçtiği kurallar ve en yakın alternatif." |
| 1:20 | Ajan değerlendirmesi: beş adım, ajanın ilk 3'ü ve motorun ilk 3'ü; bir web bulgusunu onayla | "Ajan isteğe bağlı. Her gerekçesi bir kanıta atıf yapar; kod denetler." |
| 1:50 | "Onayla ve metni hazırla" → görüşme metni; bir bloğu düzenle; "Sunum görünümü" | "Beyaz alan müşteri için, sarı kutular yalnızca RM için. Sunum görünümü RM notlarını gizler." |
| 2:30 | Döviz kısıtı sorusunda kısıtı gerekçeyle kaldır | "Kısıtı yalnızca RM gerekçeyle kaldırabilir; sıralama yeniden hesaplanır ve kayda geçer." |

Uygulama açılmazsa veya ağ yoksa: kısa demo videosu
`docs/demo/agent007-demo-P01-P03.mp4` (3:50) oynatılır; ilk 3 dakika yeterli.
İnternet yoksa motor yine çalışır; dil modeli adımları şablon metne düşer ve
ekranda bir uyarı bandı çıkar. Bunu jüriye bir güvenilirlik örneği olarak
söyleyin.

## 3. Sunumdan önce kontrol listesi

1. Sunum günü sabah 07:30'dan sonra prova yapın. Çalıştırma kimliği müşteri,
   snapshot ve yapılandırmadan gelir; yeni günün verisi yeni bir kimlik verir
   ve kayıtlı sonuçlar o kimliğe uymaz.
2. `.env` dosyasında üç anahtar olsun (EVDS, Anthropic, Exa). İnterneti
   kontrol edin.
3. `python -m rmprep serve` ile uygulamayı başlatın ve sayfayı açın.
4. P02 için tam provayı yapın: ajanı çalıştırın, bir bulguyu onaylayın,
   önerileri demodaki seçimle onaylayın ve metnin geldiğini görün.
5. Üst çubuktaki **Sıfırla** ile müşterileri ilk hâline döndürün. Sıfırlama
   onayları, kartları ve işaretleri arşive taşır; metin taslakları ve ajanın
   içerik önbelleği kalır. Demoda ajan ve metin bu yüzden anında gelir.
6. Sıfırladıktan sonra "Veriyi yenile"ye basmayın.
7. Slaytları sunum bilgisayarında PowerPoint ile açın, Sunucu görünümünde
   notları kontrol edin. Yedek: `docs/teslim/pdf/07-sunum.pdf`.
8. Demo videosunu sunum bilgisayarına kopyalayın ve bir kez oynatın.

## 4. Jüri Challenge: ekranda nasıl gösterilir?

| Jürinin değişikliği | Ekranda ne yapılır | Ne görülür |
|---|---|---|
| Müşteri bilgisi (risk profili, ufuk, likidite, yaş) | "Profili düzenle" ile alanı değiştirin | Yeni sıralama; kartta "Düzenlenmiş profil ile hazırlandı" |
| Yeni müşteri kısıtı ("döviz istemiyor", "yüksek risk istemiyor") | "Profili düzenle" → açık kısıtlar | İlgili ürünler elenir; gerekçe "Elenenler" listesinde |
| Okunamayan kısıt veya risk metni | Serbest bir metin yazın | Sıralama durur; RM'e yanıt seçenekli bir soru açılır |
| Çelişkili bilgi (ör. notta farklı yaş) | "Profili düzenle" ile RM notuna yazın | "Profilde çelişki" kartı; gerekçe yazılmadan onay yok |
| Veri erişimi (bir kaynak yok) | "Veri" menüsünde kaynağın işaretini kaldırın | O kaynağa bağlı ürünler çıkar; eksik kaynak notta görünür |
| Mevcut portföy bilgisi | Dağılım görünümünde "Düzenle" | Portföy açığı ölçütü devreye girer; ajan yeniden çalışır |
| Yeni müşteri dosyası | Üst çubukta "Yükle" | Motor dosyayı okur; okuyamadığı alanı soru olarak sorar |

Anlatırken: önce **neyin değiştiğini** (ekrandaki sayı ve liste), sonra **neden
değiştiğini** (hangi kural veya ağırlık), sonra **RM'in nerede karar
verdiğini** söyleyin.

## 5. Olası sorular ve kısa yanıtlar

| Soru | Kısa yanıt | Ek slayt |
|---|---|---|
| Neden makine öğrenmesi yok? | Etiketli geçmiş RM kararı yok; uygunluk kuralı kesin uygulanmalı; her puan parçası gösterilebilmeli. RM onayları biriktiğinde ağırlıklar bir modelle ayarlanabilir. | E9 |
| Ağırlıkları nasıl seçtiniz? | MiFID II ve SPK yerindeliğinde ağırlık yok. Ağırlıklar bizim seçimimiz, ekranda açık; istikrar testi her ağırlığı ±%20 oynatır ve önerinin yine çıkıp çıkmadığını ölçer. | E3 |
| Ajan motordan iyi değilse neden var? | Puanın göremediği sinyaller için: güncel haber, iki adayın nitel farkı, mevcut dağılım. Kurallara 8/8 uydu. Farklı 5 A/B sorusunda Haiku: ajan 3, motor 1, eşit 1; ikinci hakem Gemini: ajan 4, motor 1; iki hakem 4 soruda aynı. Bu yüzden isteğe bağlı ve RM iki listeyi görür. | E7 |
| Dil modeli bir sayı uydurursa? | Doğrulayıcı olgu paketinde olmayan her sayıyı ve tarihi reddeder; bir tekrar, sonra şablon metin. Son değerlendirmede yasak ifade 0, uydurma veri 0. | E6 |
| Web sayfasındaki bir yazı ajanı yönlendirirse? | Bulgular "veri, talimat değil" olarak verilir; dışarıya yalnızca ürün ve şirket adı gider; RM'in reddettiği bulgu ajana gitmez. | 7 |
| Bir kaynak çökerse? | Engeli aşmıyoruz; önceki snapshot ve tarihi kullanılır, eksik kaynak notta görünür; uydurma yok. | E1 |
| KAP neden yok? | kap.org.tr botları engelliyor; ayna siteler otomatik okumayı yasaklıyor. Fon belgeleri için yöneticinin kendi sitesine bağlantı, haberler için web araştırması. | 4 |
| Hazırlık süresi kazancını nasıl biliyorsunuz? | Bilmiyoruz: sistem süresini ölçtük (~1,2 sn + ~25 sn), RM'in bugünkü süresi bir varsayım. Bir RM zaman çalışması sonraki adım. | 12 |
| Müşterinin portföyünü nereden biliyorsunuz? | Dosyada yoksa meslek tablosundan veya TCMB FİR ortalamasından tahmin; "tahmini senaryo" etiketi; RM onaylamadan puana girmez. | E10 |
| Bu bir yatırım tavsiyesi mi? | Hayır. Karar desteği: kararı ve müşteri iletişimini RM yapar; müşteriye giden bir kanal yok. | 8 |
| Maliyet ne kadar? | Metin başına ~0,034 $, ajan kararı ~0,05–0,10 $, ürün başına araştırma ~0,02 $; günlük sınırlar var. Motor ücretsiz ve çevrimdışı çalışır. | E6 |
| Neden ikinci bir hakem? Hakem de bir dil modeli. | Evet; bu yüzden farklı firmanın modelini (Gemini) ekledik ve aynı soruları sorduk. Uyum 5'te 4. Tekrar bir sayım hatamızı da buldu (aynı soru iki kez sayılmıştı). | E7 |
| Hata analiziniz neydi? | Kurallar %100 geçerken 5 personanın 4'ü aynı tür öneriyi aldı; risk uyumu ve sınıf kuralı ile 5 farklı set. Ayrıca profil çelişkileri: sabit kurallar 0/5, AI 5/5. | 11 |

## 6. Slaytları yeniden üretmek

```
cd prototype
# NODE_PATH: pptxgenjs, react, react-dom, react-icons, sharp olan bir klasör
node scripts/deck/build_deck.js docs/teslim/sunum/07-sunum.pptx
powershell -File scripts/deck/finalize.ps1 docs/teslim/sunum/07-sunum.pptx docs/teslim/pdf/07-sunum.pdf <png klasörü>
```

`finalize.ps1` dosyayı PowerPoint'te açıp yeniden kaydeder, PDF ve slayt
görüntülerini çıkarır ve kullanılan yazı tiplerini yazar. Beklenen çıktı
yalnızca Arial'dir: jüri her bilgisayarda aynı görünen yazı tipi istedi.
Ekran görüntüleri `docs/img/readme/` klasöründendir (17.10.2026 verisi).
