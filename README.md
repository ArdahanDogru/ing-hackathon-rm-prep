# RM Görüşme Hazırlığı: kanıta dayalı yatırım karar desteği

Agent 007 grubu (Yusuf Ardahan Doğru, Öykü Irmak Hatipoğlu) olarak sunduğumuz bu ürün, Private Banking'deki RM'ler (Relationship Manager) için tasarlanmış bir yatırım karar destek çözümüdür.

Agentic mühendislik ve data science tabanlı ürünümüz, RM'lerin müşteri görüşmesi hazırlığına yardım eder.

Sistemimizde TEFAS, Borsa İstanbul, EVDS gibi kaynaklardan topladığımız ve işlediğimiz toplam 1.444 yatırım seçeneği var. Bu yatırım seçenekleri öncelikle müşterinin profiline ve kısıtlarına göre incelenir, uygunsuz opsiyonlar elenir ve geriye kalan uygun ürünler müşteriye özel puanlama sistemimizle sıralanır. Bu sıralama sonucunda puanlama motorumuz RM'in önüne en yüksek puanlı 3 ürünü öneri olarak sunar. RM, isterse bu önerilerin üzerine tıklayarak detaylarını inceleyebilir, motorun hangi kategorilere göre, neden bu yatırım seçeneğini önerdiğini görebilir. RM, bu üç opsiyon hakkında tereddüt ederse ya da yüksek puanlı opsiyonlar hakkında daha detaylı bir karşılaştırma yapmak isterse Ajan Araştırması bölümünü kullanabilir. 

Ajan araştırması, puanlama motorunun sıraladığı en üst seçenekler hakkında detaylı bir şirket ve ürün araştırması yapar, bununla birlikte müşterinin portföy bilgisi, istek ve kısıtlarını göz önünde bulundurarak motorun yaptığı tercihleri değiştirebilir, RM'e yeni bir ürün sıralaması önerebilir. RM, ajan araştırması bölümünde istediği miktarda ürünü, ürüne sahip olan şirketle beraber araştırabilir; kendisi istediği soruları araştırma motoruna yönlendirebilir.

RM, aynı zamanda süreç boyunca müşteri profilini düzenleyebilir; müşterinin portföy detaylarını değiştirebilir, yatırım seçenekleri hakkında detaylı web araştırması yaptırabilir. Web araştırması sonucunda çıkan bulguları onaylayabilir veya reddedebilir. Reddedilen bilgiler ajana girdi olarak verilmez, onaylanan bilgiler ajana daha güçlü bir şekilde önerilir.

RM hazırlık sayfasındaki önerilerden ve haberlerden, değiştirdiği bilgilerden memnun olduğu takdirde müşteri görüşme metnini hazırlatabilir. Metin; sayfada yer alan bilgiler ve RM'in verdiği kararlara göre hazırlanır. Bu süreçte ekrandaki her sayının kaynağı, tarihi ve kanıt kimliği vardır. Araç yatırım tavsiyesi vermez; kararı ve müşteri iletişimini RM yapar.

![P02 panosu: profil, AI ile bulunan teyit soruları, piyasa notu ve onay çubuğu](docs/img/readme/dashboard.png)
*Yukarıda ING Hubs tarafından sağlanan yapay P02 (ihracatçı şirket sahibi, Dengeli profil) müşterisinin hazırlık sayfasını görüyorsunuz; veriler 17.10.2026 tarihli. Sayfanın üstünde müşteri profili ve yapay zekânın profilde bulduğu, RM'in müşteriye sorması gereken noktalar yer alır. Ortada kodun yazdığı piyasa notu vardır ve her değerin yanındaki "K" işareti o değerin kanıtını açar. En altta ise RM'in önerileri onayladığı çubuk durur.*

## 0. Hızlı başlangıç ve README rehberi

### Sistemi çalıştırmak

Sistemi kendi bilgisayarınızda çalıştırmak için Powershell'de aşağıdaki komutları sırayla girebilirsiniz (Windows, Python 3.11+, Node yalnızca web derlemesi için):

```powershell
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -e ".[dev,web,narrator]"
cd web; npm ci; npm run build; cd ..
python -m rmprep ingest          # veriyi çeker (yaklaşık 16 dk), yeni snapshot
python -m rmprep serve           # http://127.0.0.1:8600
pytest -q                        # 150 dosyada 3.053 test, ağ erişimi yok
python -m rmprep eval --no-llm   # değerlendirme paketi, ücretsiz geçiş
python -m rmprep feedback        # RM işlem kaydından geri bildirim raporu
```

Bunun için environment dosyanızda (.env) üç API key bilgisi gerekir: TCMB verisi için EVDS_API_KEY, görüşme metni, ajan ve profil kontrolü için ANTHROPIC_API_KEY, web araştırması için EXA_API_KEY. Anahtarlardan biri eksikse uygulama çalışmaya devam eder; EXA_API_KEY eksikse web search claude üzerinden gerçekleştirilir. Diğer iki anahtar eksikse yalnızca bu anahtarlara bağlı parçalar kapanır; puanlama motorumuz yine çalışır.

### Bu README nasıl okunur?

Bu bölümden sonra README'miz sekiz bölümden oluşur. Aşağıdaki tablo README'deki bölümlerin yarışma brief'inin 8. maddesindeki hangi teslimata karşılık geldiğini ve ayrıntılarının repo içerisindeki hangi belgede olduğunu gösterir. Çalışan demomuz repoyu lokale klonladıktan sonra (teslimat 1) yukarıdaki Powershell komutlarla açılır ve kullanılabilir.

| README bölümü | Brief'teki teslimat | Ayrıntılı belge |
|---|---|---|
| 1 · Problem tanımı ve çözüm yaklaşımı | 2 · Problem tanımı | [`docs/teslim/01-problem-tanimi.md`](docs/teslim/01-problem-tanimi.md) |
| 2 · Veri kaynakları ve temel sinyaller | 3 · Analitik çözüm | [`docs/ingest.md`](docs/ingest.md), [`docs/research.md`](docs/research.md) |
| 3 · Karşılaştırma, sıralama ve karar mantığı | 3 · Analitik çözüm | [`docs/decision.md`](docs/decision.md), [`config/decision.yaml`](config/decision.yaml) |
| 4 · Çözüm mimarisi ve veri akışı | 4 · Çözüm tasarımı | [`docs/ingest.md`](docs/ingest.md), [`docs/web-ui.md`](docs/web-ui.md) |
| 5 · AI/Agentic bileşenler | 4 · Çözüm tasarımı | [`docs/agent.md`](docs/agent.md), [`docs/narrator.md`](docs/narrator.md), [`docs/research.md`](docs/research.md) |
| 6 · Varsayımlar, belirsizlikler ve insan onay noktaları | 3 · Analitik çözüm, 4 · Çözüm tasarımı | [`docs/kararlilik-veri-guveni.md`](docs/kararlilik-veri-guveni.md), [`docs/web-ui.md`](docs/web-ui.md) |
| 7 · Test, sonuçlar, hata analizi ve iyileştirmeler | 5 · Test ve öğrenimler | [`docs/eval.md`](docs/eval.md), [`docs/found-and-fixed.md`](docs/found-and-fixed.md) |
| 8 · İzlenebilirlik | 6 · Kanıt kaydı örneği | [`docs/teslim/06-kanit-kaydi-ornegi.md`](docs/teslim/06-kanit-kaydi-ornegi.md) |

## 1. Problem tanımı ve çözüm yaklaşımı

Relationship Manager (RM), ilgilendiği her müşteri için görüşmelerden önce yüzlerce yatırım ürününü farklı kaynaklardan toplayıp karşılaştırmak durumunda. Faiz oranları TCMB'de, fon getirileri TEFAS'ta, mevduat oranları bankaların sayfalarında duruyor ve RM bunları kendisi bir araya getiriyor. Ayrıca bu veriler dinamik; RM her toplantıdan önce elindeki verileri güncel verilerle değiştirmekle uğraşıyor. Bu iş uzun sürdüğü için de görüşme metni çoğu zaman müşteriye yeterince uyarlanamayabiliyor, müşterinin açık bir kısıtı gözden kaçabiliyor, yatırım kararını etkileyen veriler tamamen güncel olmayabiliyor ve önerilerin hangi veriye, varsayıma ve gerekçeye dayandığı o sırada gösterilemeyebiliyor.


Problemin büyüklüğünü kendi verimizle ölçtük (snapshot: `20261017-110343-d12a`, 17.10.2026):

| Gözlem | Sayı |
|---|---|
| Muhafazakâr bir müşteri (P01) için evren | 1.444 seçenek (815 fon, 37 BYF, 590 pay, 2 ING mevduatı); kurallar 1.301'ini eler, 143'ü kalır |
| P01'in risk sınırı içindeki 37 para piyasası fonu, son 1 yıl reel | medyan +%6,6, en iyisi +%9,6 |

Tablonun ikinci satırı bize şunu gösterdi: faizler kâğıt üzerinde iyi görünse de stopaj ve enflasyondan sonra müşteri mevduatta değer kaybediyor, aynı risk seviyesindeki para piyasası fonları ise enflasyonun üstünde kalıyor. RM'in bunu görebilmesi için 143 seçeneği reel getiriye, vergiye ve risk uyumuna göre sıralaması gerekir ve bu iş bir görüşme hazırlığının süresine sığmaz.

### Neden Agent007? -> İş etkisi

| Gösterge | Bugün | Agent 007 ile |
|---|---|---|
| Hazırlık süresi | **[VARSAYIM]** görüşme başına ~60 dk, daha fazla da olabilir | analiz ~1,18 sn, görüşme metni ~24,9 sn; geri kalan RM'in okuması ve onayı |
| Müşteri kısıtı/isteği ihlali | elle kontrol edilir | Testlerimizdeki 34 senaryo ve 39 çalıştırmada, öneri listesi çıkan 37 çalıştırmanın hiçbirinde kısıt ihlali gözlemlemedik |
| Tutarlılık | kişiye bağlı | deterministik; aynı girdi → aynı sonuç ve aynı metin (yaptığımız 5 testte 5/5 aynı sonuçları aldık) |
| Müşteriye özel uyarlama | Zaman kısıtına göre bazen genel metin | 5 müşteri profilinde 5 farklı öneri seti; gerekçeler ve öneriler müşterinin önceliklerine ve kısıtlarına bağlı olarak hazırlanır |
| İzlenebilirlik | dağınık; önerinin hangi veriye, varsayıma ve gerekçeye dayandığı geriye dönük gösterilemeyebilir | ekrandaki her sayının kaynağı, tarihi, alınma zamanı ve kanıt kimliği sunulur |

### Yaklaşımımız

Çözümümüzde işleri dört katmana ayırdık. Ürünleri eleyen ve sıralayan kısım, puanlama motoru, koddur; aynı girdiyle her seferinde aynı sonucu verir ve her adımı açıklanabilir. Müşteri istek ve kısıtlarına göre yatırım seçeneklerini puanlar. Ajan puanlama motorunun çizdiği sınırlar içinde çalışır: motorun önerilerini araştırıp yeni bir sıralama önerebilir. Görüşme metnini ise ayrı bir yapay zekâ adımı olan anlatıcı yazar. Ajanın ve anlatıcının yazdığı her şey yeniden denetlenir. Son karar ise her zaman RM'indir. RM hemen hemen her hazırlanan çıktıyı gözden geçirip geri bildirim verebilir.


```mermaid
flowchart TB
    P["👤 Müşteri profili<br/>persona + RM düzeltmeleri"] --> ENG
    M["📊 Piyasa ve ürün verisi<br/>TEFAS · TCMB EVDS · Borsa İstanbul · ING"] --> ENG
    K["⚙️ Kurallar ve ağırlıklar<br/>decision.yaml"] --> ENG
    subgraph ENG["Puanlama motoru · kod · aynı girdi = aynı sonuç"]
        direction LR
        E1["1 · Katı kurallar<br/>uygun olmayanı eler"] --> E2["2 · Şeffaf puan<br/>8 ölçüt − 8 ceza"] --> E3["3 · İlk 3<br/>varlık sınıflarına yayılır"]
    end
    ENG --> O1["Sıralı liste<br/>puan parçaları + kaynak"]
    ENG --> O2["Elenenler<br/>her biri nedeniyle"]
    ENG --> O3["İlk 3 öneri"]
    O3 -. "RM isterse" .-> AG["Ajan<br/>web araştırması, karşılaştırma;<br/>kod denetler"]
    O3 --> RM1{{"RM onaylar"}}
    AG -. "yeni ilk 3 önerisi" .-> RM1
    RM1 --> N["Görüşme metni<br/>dil modeli yazar, kod doğrular"]
    N --> RM2{{"RM düzenler, kartı indirir"}}
    classDef io fill:#fff,stroke:#98A2B3,color:#101828
    classDef code fill:#EEF2F9,stroke:#525199,color:#101828
    classDef ai fill:#F4F3FF,stroke:#6941C6,color:#101828
    classDef human fill:#FF6200,stroke:#B34400,color:#fff
    class P,M,K,O1,O2 io
    class E1,E2,E3,O3 code
    class AG,N ai
    class RM1,RM2 human
    style ENG fill:#F8F9FC,stroke:#525199,stroke-width:2px
```

*Şemadaki renkler işi kimin yaptığını gösterir: mavi kutular kodu (puanlama motoru), mor kutular yapay zekâyı, turuncu altıgenler RM'in karar verdiği yerleri gösterir. Kesik çizgi isteğe bağlı bir adımdır.*

Ürünümüz yalnızca görüşmeden önceki hazırlığı kapsar. Getiri tahmini, otomatik alım satım, müşteriyle doğrudan iletişim ve müşteriye açık bir sohbet botu kapsamımızın dışındadır.

## 2. Kullanılan veri kaynakları ve temel sinyaller

Önerilerimizde kullandığımız verileri resmi ve kamuya açık kaynaklardan, her gün yeniden topluyoruz. Sistemimiz otomatik olarak her sabah 07:30'da kendiliğinden çalışır. RM isterse ekrandaki *Veri* menüsünden "Veriyi yenile" tuşuna basarak veriyi o an da güncelleyebilir. Kullandığımız kaynakları seçerken kullanım koşullarını ve robots.txt dosyasını okuduk. Bir kaynak botları engelliyorsa bu engeli aşmaya çalışmıyoruz, o gün bir önceki günün verisiyle devam ediyoruz ve verinin hangi tarihten olduğunu belirtiyoruz.

| Kaynak | Bize ne verir | Nasıl okuyoruz |
|---|---|---|
| TCMB EVDS (resmî API) | politika faizi, USD/TRY, TCMB fonlama maliyeti, 3 aya kadar mevduat faizi, TÜFE endeksi (→ yıllık TÜFE), BIST 100 | API anahtarıyla, 900 günden uzun dönemleri parça parça çekiyoruz |
| TEFAS fon getirileri sayfası | ~2.100 fon ve BYF için 1 ay-5 yıl getiri ve SPK risk değeri (1-7) | kamuya açık HTML sayfası; robots.txt'nin yasakladığı `/api/` adresini çağırmıyoruz |
| TEFAS fon detayları | fiyat, büyüklük, yatırımcı sayısı, alış/satış valörü, ücretler, alım durumu, portföy dağılımı | her fon için bir sayfa |
| Borsa İstanbul gün sonu bültenleri | 628 pay için kapanış, 1 ay-5 yıl getiri, 1 ve 5 yıllık oynaklık, işlem hacmi, BIST 100 üyeliği | günlük ZIP dosyaları |
| ING oran sayfası | Turuncu Hesap ve e-Vadeli Mevduat oranları | ING'nin kamuya açık oran formu; sayfa açılmazsa önceki gün, o da yoksa elle girilen backup CSV |
| Elle girilen CSV | stopaj oranları (31.12.2026'ya kadar geçerli), yıllık TÜFE (çapraz kontrol için), ING oranları (yedek) | her satırın bir kaynak bağlantısı ve tarihi var |
| Fon yöneticisi belgeleri | izahname ve yatırımcı bilgi formu bağlantıları | RM bir fon kartını açtığında, yöneticinin kendi sitesinden; yalnızca bağlantıyı gösteriyoruz |
| Web araştırması (Exa) | önerilen ürünler ve şirketleri hakkında son 90 günün haberleri ve öne çıkanları | dışarıya yalnızca ürün ve şirket adı gider; her bulgu "web kaynağı, doğrulanmamış" etiketi taşır |

### KAP'ı neden kullanmıyoruz?

Brief KAP'ı önerilen kaynaklar arasında sayıyor, ancak kap.org.tr botları engelliyor. KAP verisini yayınlayan ayna siteler de kendi kullanım koşullarında otomatik okumayı yasaklıyor. Bu yüzden KAP yerine iki yol kullandık: fon belgeleri için fon yöneticisinin kendi sitesindeki izahnameye ve yatırımcı bilgi formuna bağlantı veriyoruz, şirket haberlerini ise web araştırmasıyla topluyoruz.

Bu kaynaklardan sonra yatırım evrenimiz 815 TEFAS fonu, 37 BYF, 590 hisse senedi ve 2 ING mevduatından oluşur. ING Turuncu Hesap sıralamaya girmez; önerileri karşılaştırdığımız taban olarak durur, böylece RM her öneriyi müşterinin bugün mevduatta alacağı getiriyle kıyaslayabilir. Yalnızca nitelikli yatırımcıya açık "Serbest" fonları, Borsa İstanbul'un W ve S pazarlarındaki payları, varant ve sertifikaları evrene almadık.

### Ürün ve müşteri sinyalleri

Puanlama motorumuz bir ürünü değerlendirirken stopaj ve enflasyon sonrası reel getirisine, SPK risk değerine, müşterinin parasına kaç günde ulaşacağına, fon büyüklüğüne ve yatırımcı sayısına, alım durumuna, giriş ve çıkış ücretine bakar. Çok varlıklı bir fonun hangi varlık sınıfına girdiğine fonun adına göre değil, gerçek portföy dağılımına göre karar verir. Hisse senetlerinde SPK risk değeri olmadığı için riski fiyat oynaklığından, büyüklüğü de işlem hacminden hesaplar. Bir ürünün risk değeri hiç yoksa bunu aynı sınıftaki ürünlerden tahmin eder ve tahmin ettiğini ekranda yazar.

Müşteri tarafında ise persona dosyasındaki her alanın kararda bir karşılığı vardır. RM bir alanı değiştirdiğinde sıralamanın neden değiştiğini bu tablodan izleyebilir:

| Müşteri dosyasındaki alan | Motor bu alanı nasıl kullanır |
|---|---|
| Risk profili | risk tavanı (bu tavanın üstündeki ürün elenir), risk bandı ve risk iştahı (puan) |
| Yatırım ufku | hangi dönemin getirisine bakılacağı, ufuk 3+ yılsa getirinin ağırlığı artar |
| Likidite, gelir, anapara koruma | Düşük 0 · Orta 0,5 · Yüksek 1 → ilgili ölçütün ağırlığı ve cezanın şiddeti |
| Döviz maruziyeti | döviz cezasının şiddeti (açık bir kısıtsa döviz ürünleri elenir) |
| Öncelikler | eşleşen her öncelik ilgili ölçütün ağırlığına +1 ekler |
| Açık kısıtlar | eleme kuralı (ör. döviz sınırı, parayı uzun süre kilitleyen ürün) |
| Durum, amaç, RM notu | müşterinin mevcut portföy dağılımının tahmini ve görüşme metnindeki uyarlama |
| Yaş | puana girmez, görüşme metninde ve profil tutarlılık kontrolünde kullanılır |

Brief'in 6. maddesinde sayılan müşteri ve ürün özelliklerinin her birini bir ölçüte, cezaya veya eleme kuralına bağladık. Getiriyi reel ve stopaj sonrası ölçüyoruz, çünkü %30 civarındaki bir enflasyonda nominal getiriye göre yapılan bir sıralama müşteriyi yanıltır.

Yaşı ise puana katmadık. Müşterinin hangi ürünlere uygun olduğunu risk profili belirliyor. Yaşı görüşme metninde ve profil kontrolünde kullanıyoruz: örneğin dosyada `yas` 62 yazarken RM notunda "45 yaşında" geçiyorsa sistem bu çelişkiyi RM'e gösteriyor.

## 3. Sıralama veya karar mantığı

Sıralama kriterlerine puanlama motorumuz karar veriyor. Motor, kurallar ve puanlardan oluşan deterministik hesaplamalar yapar, aynı müşteri ve aynı veriyle her çalıştırıldığında aynı sonucu ve aynı çalıştırma kimliğini (`run_id`) verir. Motorun bütün tabloları ve ağırlıkları [`config/decision.yaml`](config/decision.yaml) dosyasında, tasarım kararlarımız da [`docs/decision.md`](docs/decision.md) belgesindedir.

### Neden kural ve deterministik puan?

Bu yaklaşımı seçmemizin üç nedeni var. Birincisi, elimizde hangi müşteriye hangi ürünün önerildiğini gösteren ya da ürünlere önceden belirlenmiş puanlar veren etiketli bir geçmiş veri yok. Bu yüzden denetimli bir machine learning modeli eğitmemiz mümkün değildi. İkincisi, brief'in 5. kuralı (müşteriye uygun olmayan ürün öneri listesine girmez) her seferinde kesin olarak uygulanmalı. Olasılıkla çalışan bir model bunu garanti edemez. Üçüncüsü, kural ve puan yaklaşımında puanın her parçasını gösterebiliyoruz ve aynı sonucu istediğimiz zaman yeniden üretebiliyoruz. Bu algoritmamızı açıklanabilirlik açısından güçlendiriyor. Dil modelini ise metin yazmak, araştırmayı özetlemek ve adayları nitel olarak karşılaştırmak gibi kendi güçlü olduğu işlerde kullanıyoruz (bölüm 5).

```mermaid
flowchart TB
    U["Evren: 1.444 seçenek"] --> R1["1 · Alıma kapalı fon"]
    R1 --> R2["2 · Risk tavanı<br/>Muhafazakâr 2 · Temkinli 3 · Dengeli 5 · Agresif 7"]
    R2 --> R3["3 · Açık kısıtlar<br/>döviz sınırı, uzun kilit / düşük likidite"]
    R3 --> R4["4 · Kısa geçmiş<br/>yalnızca 1 aylık getiri"]
    R4 --> S["Puan = Σ ağırlık × değer − Σ ceza"]
    S --> T["Motorun ilk 3'ü<br/>Dengeli/Agresif: sınıf başına en çok 1"]
    R1 -. "her eleme gerekçe ve kanıt kimliğiyle" .-> X["Elenenler listesi"]
    R2 -.-> X
    R3 -.-> X
    R4 -.-> X
    classDef code fill:#EEF2F9,stroke:#525199,color:#101828
    classDef io fill:#fff,stroke:#98A2B3,color:#101828
    class R1,R2,R3,R4,S,T code
    class U,X io
```

Motor işe dört eleme kuralıyla başlar ve bunları sırayla uygular: alıma kapalı fonları, müşterinin risk tavanını aşan ürünleri, müşterinin açık kısıtlarına uymayan ürünleri ve yeterli getiri geçmişi olmayan ürünleri eler. Elenen her ürün, hangi kurala takıldığı ve bu kararın dayandığı kanıtla birlikte *Elenenler* listesine yazılır. Kalan ürünler puanlanır. RM bu süreci hazırlık sayfasındaki *Bu öneriler nasıl seçildi?* bölümünde adım adım izler. Müşterinin ölçüt ağırlıkları, her kuralın kaç ürünü elediği ve önerilerin ne kadar kararlı olduğu burada yazar.

![Bu öneriler nasıl seçildi: profil ve ağırlıklar, 1.444 seçenek, 1.138 elendi, 306 aday, 3 öneri](docs/img/readme/pipeline.png)

### Puan nasıl hesaplanır?

Elemeden geçen her ürün sekiz ölçütün her birinden 0 ile 1 arasında bir değer alır. Motor bu değerleri müşterinin ağırlıklarıyla çarpıp toplar, sonra ürünün zayıf yönleri için cezaları çıkarır. Ağırlıkları müşterinin profili belirler ve toplamları 1'dir. Örneğin likidite ihtiyacı yüksek bir müşteride likidite ölçütünün ağırlığı büyür; likidite ihtiyacı "Düşük" olan bir müşteride ise bu ölçütün ağırlığı sıfırdır ve fon kartında hiç görünmez. Bu yüzden aynı ürünün puan parçaları müşteriden müşteriye değişir.

| Ölçüt | Ne ölçer | Ham ağırlık |
|---|---|---|
| Getiri | stopaj, ücret ve TÜFE sonrası reel getirinin adaylar içindeki sırası | 2 + 2 × risk iştahı (ufuk 3 yıl veya daha uzunsa +1) |
| Risk uyumu | ürünün risk değeri müşterinin bandında mı (bandın altındaki her seviye −0,5) | 2 |
| Likidite | satış valörü (aynı gün 1,0 … 10 günden uzun 0,2) | 2 × likidite ihtiyacı |
| Gelir | ürün türünün düzenli gelire uygunluğu | 2 × gelir ihtiyacı |
| Anapara | anaparanın korunması (mevduat 1; fonda risk arttıkça azalır) | 2 × anapara koruma tercihi |
| Sadelik | ürün yapısının sadeliği | yalnızca "sade ürün yapısı" önceliği varsa |
| Kalite | fon büyüklüğü ve yatırımcı sayısı (payda işlem hacmi) | 0,5 |
| Portföy açığı | müşterinin bugünkü dağılımının model banttan ne kadar uzak olduğu | 1 × kaynak katsayısı; yalnızca dağılımı RM girdiyse, onayladıysa veya müşteri dosyasında varsa |

Cezalar ürünün müşteriye uymayan yanlarını puandan düşer. Anapara riski, paraya geç erişim, döviz maruziyeti, bilinmeyen risk, reel kayıp ve piyasanın altında kalan getiri için ceza en çok 0,3; eksik getiri geçmişi için 0,2; küçük fon için 0,1 olabilir. Bir cezanın büyüklüğünü belirleyen çarpımı, cezanın üst sınırı, o konunun müşteri için ne kadar önemli olduğu ve ürünün o konuda ne kadar zayıf kaldığı oluşturur.

### Bu ağırlıkları neden seçtik?

MiFID II ve SPK'nın yerindelik kurallarında kriterlerin ağırlıkları yoktur. Bu yüzden ağırlıkları kendimiz seçtik ve ekranda açıkça gösteriyoruz **[VARSAYIM]**. Seçimimizin sonucu ne kadar etkilediğini de iki yolla ölçüyoruz: istikrar testimiz her ağırlığı %20 artırıp azaltarak sıralamayı yeniden hesaplar (bölüm 6), değerlendirme adımı da persona değiştiğinde sonucun beklenen yönde değişip değişmediğine bakar (bölüm 7).

### İlk 3 öneri nasıl seçilir?

Muhafazakâr ve Temkinli müşterilerde ilk 3 öneri doğrudan puan sırasının ilk üç ürünüdür. Dengeli ve Agresif müşterilerde ya da çeşitlendirme isteyen her müşteride ise motor listeyi puan sırasıyla dolaşır ve her varlık sınıfından en çok bir ürün alır, böylece RM'in önüne aynı türden üç fon gelmez. Nakit benzeri ürünler ve paylar için de en fazla bir ürün seçilir ve son bir yılda enflasyonun altında kalmış bir ürün bu yöntemle seçilmez. Çok varlıklı bir fonun sınıfını fonun gerçek portföy dağılımı belirler: portföyün %50 veya daha fazlasını oluşturan sınıf seçilir. Böyle bir sınıf yoksa fon "dengeli" sayılır.

Bunu bir örnekle gösterelim. P02, döviz geliri olan ve 1-3 yıllık ufku bulunan Dengeli profilli bir ihracatçı, önceliklerinden biri erişilebilir likidite. Motorumuz bu müşteri için ağırlıkları getiri 0,339, risk uyumu 0,203, likidite 0,203, gelir 0,102, anapara 0,102 ve kalite 0,051 olarak hesapladı (17.10.2026):

| Seçenek | Sınıf | Reel getiri (1 yıl) | Puan | Neden |
|---|---|---|---|---|
| EIL Astra Para Piyasası | nakit benzeri | +%7,7 | 0,783 | en iyi nakit benzeri, aynı gün erişim |
| NJR Nurol Borçlanma Araçları | borçlanma | +%8,1 | 0,743 | en iyi borçlanma fonu |
| KDE Kuveyt Türk Dengeli Katılım | dengeli | +%9,5 | 0,741 | en iyi dengeli, risk bandın içinde |
| ING e-Vadeli Mevduat | nakit benzeri | +%2,1 | 0,434 | sıralanır, ama nakit benzeri yeri EIL'de |
| ING Turuncu Hesap (karşılaştırma) | nakit benzeri | −%8,3 | 0,185 | reel kayıp ve piyasa altı cezaları |

RPP adlı para piyasası fonu 0,775 puanla KDE'den yüksek puan aldı, ama nakit benzeri sınıfın tek yerini EIL doldurduğu için ilk 3'e girmedi. P02'nin "döviz maruziyetini gerekçesiz artırmama" kısıtı da 15 döviz fonunu eledi (RM isterse bu kısıtı gerekçe yazarak kaldırabilir).

RM bir önerinin üzerine tıkladığında fon kartı açılır. Kartın *Neden bu öneri?* bölümü puanın her parçasını gerekçesiyle, fonun geçtiği eleme kurallarını kanıt kimlikleriyle ve en yakın alternatifle arasındaki farkı gösterir. Ekranda puanlar 100 ile çarpılmış olarak yazar:

<img src="docs/img/readme/fundcard.png" alt="EIL fon kartı: uygunluk, benzerleri arasında sıra, kategoriye göre getiri, belgeler, puan parçaları, geçtiği kurallar, en yakın alternatif" width="420">

Aynı gün beş personamız için motorun önerdiği ilk 3 opsiyon aşağıdaki gibidir:

| Persona | Kalan / evren | Motorun ilk 3'ü |
|---|---|---|
| P01 Emekli girişimci, Muhafazakâr | 143 / 1.444 | PPN · OSD · AIS |
| P02 İhracatçı, Dengeli | 306 / 1.444 | EIL · NJR · KDE |
| P03 Teknoloji kurucusu, Agresif | 1.250 / 1.444 | ASELS (pay) · TE3 · OKT |
| P04 Aile ofisi, Dengeli | 312 / 1.444 | OKT · RPP · TCF |
| P05 Hekim, Temkinli | 180 / 1.444 | EIL · GBL · KSK |

Önerilerin yanında bir de *Dağılım* görünümü var. Bu görünüm müşterinin risk profiline göre her varlık sınıfı için model bir bandı (Ata Yatırım, 28.04.2026), müşterinin bugünkü dağılımını ve her sınıfın en iyi seçeneğini yan yana koyar. P02'nin dosyasında mevcut portföy dağılımı olmadığı için ekrandaki değerler "tahmini senaryo" olarak işaretlidir ve RM "Tahmini onayla" ya da "Düzenle" diyene kadar puan sıralamasını etkilemez.

![Dağılım görünümü: tahmini mevcut portföy, varlık sınıfı başına model bant ve sınıfın en iyi seçeneği](docs/img/readme/allocation.png)

## 4. Genel çözüm mimarisi ve veri akışı

Aşağıdaki şema verinin kaynaktan RM'in ekranına kadar izlediği yolu gösterir. Güncel veri önce bir snapshot'a kaydedilir, kontrollerden geçer ve kanıtlara yazılır. Puanlama motoru bu kanıtları okur. Web uygulaması, ajan, web araştırması ve görüşme metni de motorun sonucunu kullanır. RM'in yaptığı her işlem kayda geçer ve değerlendirme adımı bu kayıtları daha sonra yeniden okuyabilir.

```mermaid
flowchart TB
    JOB["Günlük görev 07:30 veya Veriyi yenile<br/>kilit: aynı anda tek ingest"]
    subgraph SRC["Kaynaklar"]
        direction LR
        EVDS[("TCMB EVDS API")]
        TW[("TEFAS sayfaları")]
        BIST[("Borsa İstanbul bültenleri")]
        INGW[("ING oran sayfası")]
        MAN[/"Elle girilen CSV"/]
    end
    subgraph ING["Ingest · deterministik · src/rmprep/ingest"]
        SNAP["Dondurulmuş snapshot<br/>ham baytlar + SHA-256, salt okunur"]
        QC["Kalite kontrolleri<br/>bayrak ekler, değeri değiştirmez"]
        DB[("Kanıt deposu<br/>DuckDB + Parquet")]
        SNAP --> QC --> DB
    end
    subgraph DEC["Puanlama motoru · deterministik · src/rmprep/decision"]
        RULES["Eleme kuralları"] --> SCORE["Puan, güven, istikrar"] --> TOP["İlk 3, dağılım, uyarılar, sorular"]
    end
    API["FastAPI + arka uç · src/rmprep/api<br/>yalnızca 127.0.0.1"]
    PROF["Profil kontrolü<br/>sabit kurallar + Claude Opus 5.5"]
    RES["Web araştırması · src/rmprep/research<br/>Exa; yedek Claude web araması"]
    AGT["Ajan · src/rmprep/agent<br/>Claude Sonnet 5.5 + kod denetimi"]
    subgraph NAR["Anlatıcı · src/rmprep/narrator"]
        BRIEF["Pano özeti<br/>Claude Haiku 5.5"]
        TEXT["Görüşme metni<br/>Claude Sonnet 5.5 + doğrulayıcı"]
    end
    WEB["Web uygulaması · web/ (React)<br/>RM inceler, onaylar, düzenler"]
    REC[("Kayıtlar<br/>data/runs · narratives · agent · research<br/>logs/rm-actions")]
    EVAL["Değerlendirme ve geri bildirim<br/>src/rmprep/eval · 34 senaryo · geri bildirim raporu"]
    JOB --> SRC --> SNAP
    DB --> RULES
    TOP --> API
    API <--> WEB
    API --> PROF
    API --> RES
    API -- "RM isterse" --> AGT
    RES --> AGT
    API --> BRIEF
    API -- "yalnızca onaylı seçim" --> TEXT
    API --> REC
    EVAL -.-> DEC
    EVAL -.-> NAR
    EVAL -.-> AGT
    REC -.-> EVAL
    classDef code fill:#EEF2F9,stroke:#525199,color:#101828
    classDef ai fill:#F4F3FF,stroke:#6941C6,color:#101828
    classDef human fill:#FF6200,stroke:#B34400,color:#fff
    class SNAP,QC,RULES,SCORE,TOP,API,EVAL code
    class PROF,RES,AGT,BRIEF,TEXT ai
    class WEB human
```

*Renkler ilk şemadaki gibidir: mavi kod, mor yapay zekâ, turuncu RM'in çalıştığı ekran.*

Sistemi, her biri ayrı bir şekilde test edilebilen modüllere böldük. Böylece bir modülü değiştirdiğimizde diğerlerinin bozulup bozulmadığını kendi testleriyle hemen görebiliyoruz:

| Modül | Ne iş yapar | Klasör |
|---|---|---|
| Ingest | kaynak adaptörleri, snapshot, kalite kontrolleri, kanıt deposu, günlük güncelleme ve kilitleme | `src/rmprep/ingest/`, `config/sources.yaml` |
| Puanlama motoru | opsiyon evreni, eleme kuralları, puan, güven, istikrar, ilk 3, dağılım bantları, mevcut dağılım, uyarılar | `src/rmprep/decision/`, `config/decision.yaml` |
| Ajan | adaylar, veri paketi, araçlar, kod denetimi, yedek | `src/rmprep/agent/`, `config/agent.yaml` |
| Web araştırması | Exa ve Claude sağlayıcıları, soru kontrolü, biçimlendirme, sonuçların kaydı, günlük sınır | `src/rmprep/research/`, `config/research.yaml` |
| Narrator | olgu paketi, dil modeli çağrısı, doğrulayıcı, tekrar, şablon metin, piyasa notu, maliyet defteri | `src/rmprep/narrator/`, `config/narrator.yaml` |
| API ve arka uç | çalıştırma, profil kontrolü, onay, kayıt, işlem kaydı, veri güncelliği | `src/rmprep/api/`, `src/rmprep/backend.py` |
| Web uygulaması | pano, öneriler, ajan kutusu, araştırma paneli, fon kartı, kanıt penceresi, görüşme metni, sunum görünümü | `web/` |
| Değerlendirme | senaryolar, kural kontrolleri, LLM hakemi, ajan A/B, geri bildirim raporu | `src/rmprep/eval/`, `config/eval.yaml` |

Modüller birbirleriyle `src/rmprep/contracts.py` dosyasındaki ortak veri tipleri (sözleşmeler) üzerinden konuşur. Her modülün tasarım belgesi ayrıdır: [`docs/ingest.md`](docs/ingest.md), [`docs/decision.md`](docs/decision.md), [`docs/agent.md`](docs/agent.md), [`docs/research.md`](docs/research.md), [`docs/narrator.md`](docs/narrator.md), [`docs/web-ui.md`](docs/web-ui.md), [`docs/eval.md`](docs/eval.md).

## 5. AI/Agentic bileşenler ve görev/karar akışı

Yapay zekâyı kullandığımız her yerde aynı ilkeye uyduk: kullanılan dil modeli hiçbir ürünü elemez ve hiçbir eleme kuralını aşamaz, çünkü eleme ve puan kod ile belirlenir. Dil modelini metin yazmak, web araştırması yapmak ve adayları nitel olarak karşılaştırmak için kullanıyoruz. Modelin her çıktısını kod denetler ve denetimden geçmeyen bir çıktının yerine her zaman deterministik bir yedek gelir. Böylece model hata yapsa da RM boş bir ekranla veya uydurulmuş verilerle karşılaşmaz.

| Bileşen | Model | Ne yapar | Nasıl güvence altına aldık | Maliyet |
|---|---|---|---|---|
| Ajan ilk 3 | Claude Sonnet 5.5 | motorun en iyi 10 adayı (RM 20'ye kadar seçebilir) arasından kendi ilk 3'ünü seçer | kod denetimi (1 tekrar), sonra motorun ilk 3'ü | karar başına ~0,05-0,10 $ (günde en çok 3 $ ile sınırlandırıldı) |
| Web araştırması | Exa (yedek: Claude Haiku 5.5 web araması) | ilk 3 ve şirketleri için haberleri ve öne çıkanları toplar, RM'in sorularını yanıtlar | soru kontrolü (müşteri bilgisi dışarı gitmez), kaynağı olmayan bulgu atılır, "doğrulanmamış" etiketi eklenir | ürün başına ~0,02 $ (günde en çok 5 $ ile sınırlandırıldı) |
| Profil kontrolü | Claude Opus 5.5 | müşteri profilinin tamamında çelişki arar | her bulgu çelişen iki tarafı kelimesi kelimesine alıntılar; sunucu alıntıyı ilgili alanda arar | profil başına ~0,015 $; sonuç kaydedilir, aynı profil için model yeniden çağrılmaz |
| Görüşme metni | Claude Sonnet 5.5 | onaylanan seçimi bölümlü bir Türkçe metne çevirir | doğrulayıcı; 1 tekrar; sonra şablon metin | metin başına 0,034 $, ortalama 24,9 sn |
| Pano özeti | Claude Haiku 5.5 | RM'e 1-2 cümlelik bir özet yazar | doğrulayıcı; hata olursa düz bir cümle | ~0,003 $ |
| Değerlendirme hakemi | Claude Haiku 5.5 | metnin müşteriye uyarlanmış, açık ve dengeli olup olmadığını notlar; ajan ile motoru kör A/B ile karşılaştırır | yalnızca kodun ölçemediği şeyler için | paket başına < 0,01 $ |

### Ajan nasıl çalışır?

Ajan kendiliğinden başlamaz. RM hazırlık sayfasındaki *Ajan değerlendirmesi* kutusunda aday sayısını seçip "Ajanı çalıştır" dediğinde çalışır. Ajana tek bir veri paketi veririz: müşterinin profili ve mevcut dağılımı, motorun en iyi adaylarının puan parçaları, olguları ve uyarıları, bir de bu adaylar hakkındaki web araştırması bulguları. Sistem isteminde araştırma bulgularının talimat değil veri olduğunu açıkça yazıyoruz; böylece bir web sayfasındaki yazının ajana talimat gibi etki etme riskini azaltıyoruz. Ajanın kullanabileceği üç araç vardır:

- `karsilastir(a, b, amac)`: iki adayı kodla karşılaştırır (en çok 4 kez).
- `arastir(option_id, soru, amac)`: bir aday için tek bir web sorusu sorar (en çok 2 kez).
- `karar_ver(secimler, cikanlar, ozet)`: kararını önerir.

Ajan kararını verdiğinde kodumuz bu kararı şu sorularla denetler:

- 3 farklı aday seçilmiş mi; en çok 1 pay var mı; varlık sınıfı kuralı tutuyor mu?
- Her gerekçe bir kanıt kimliğine, bir web bulgusu kimliğine, bir puan parçasına veya bir portföy satırına atıf yapıyor mu?
- Gerekçedeki her sayı ve tarih atıf yapılan veride gerçekten var mı; yasak bir ifade var mı?
- Motorun listesinden çıkarılan her seçenek için bir gerekçe yazılmış mı?

Karar denetimden geçmezse ajan bulunan sorunların listesini alır ve kararını bir kez düzeltir. İkinci kez de hata yaparsa, 90 saniyeyi aşarsa veya günlük bütçe dolarsa RM'in önüne motorun kendi ilk 3'ü gelir. RM ajanın beş adımını (Adaylar, Ajan araştırması, Ajan analizi, Kontrol, Karar) süresi, maliyeti ve notlarıyla izleyebilir ve her adımın üzerine tıklayarak o adımda ne yapıldığını okuyabilir. Modelin ham düşüncesini ise saklamıyor ve göstermiyoruz.

![Ajanın beş adımı: Adaylar, Ajan araştırması, Ajan analizi, Kontrol, Karar; süre ve maliyetle](docs/img/readme/agent.png)

![Ajan önerisi (P01): seçilen 3 fon atıflı gerekçeleriyle, çıkarılan AIS ve nedeni, motor sıralamasına bağlantı](docs/img/readme/agent-picks.png)
*P01 için ajan, motorun önerdiği AIS fonunu çıkarıp yerine ZBJ'yi aldı ve nedenini yazdı. Her gerekçe bir puan parçasına veya kanıt kimliğine bağlı. Tahmini portföy dağılımına dayanan bir cümleye "(tahmini dağılıma göre)" etiketini kod ekler.*

Ajanın kullandığı web araştırması *Ajan araştırması* bölümünde RM'in önünde de durur. RM burada ürünler veya şirketler hakkında kendi sorusunu da sorabilir. Her bulgunun yanındaki ✓ ve ✗ işaretleriyle bulguyu onaylayabilir ya da reddedebilir: reddedilen bulgu ajana hiç verilmez, onaylanan bulgu ise ajana "(web, RM doğruladı)" etiketiyle gider.

![Ajan araştırması: her öneri için tarihli haberler ve öne çıkanlar, kaynak numaraları, ✓/✗ işaretleri](docs/img/readme/research.png)

Aşağıdaki şema bir hazırlığın baştan sona akışını gösterir. RM müşteriyi seçtiğinde motor sonucu hazırlar; RM isterse ajan devreye girer; RM onay verdikten sonra anlatıcı görüşme metnini yazar ve doğrulayıcı bu metni kontrol eder.

```mermaid
sequenceDiagram
    actor RM
    participant UI as Web uygulaması
    participant E as Puanlama motoru
    participant A as Ajan (LLM)
    participant C as Kod denetimi
    participant N as Anlatıcı (LLM)
    participant V as Doğrulayıcı (kod)
    RM->>UI: müşteriyi seçer
    UI->>E: karar (aynı girdi → aynı run_id)
    E-->>UI: ilk 3, gerekçeler, uyarılar, sorular, profil bulguları
    RM->>UI: soruları yanıtlar, çelişkileri çözer
    opt RM ajanı çalıştırır
        UI->>A: N aday + araştırma (✗ işaretli bulgular hariç)
        A->>C: karar_ver
        alt denetim başarısız
            C-->>A: sorunlar, 1 tekrar
            A->>C: yeni karar
        end
        C-->>UI: ajanın ilk 3'ü veya motorun ilk 3'ü (yedek)
    end
    RM->>UI: seçimi onaylar
    UI->>N: yalnızca onaylı seçimin olgu paketi
    N->>V: yapılandırılmış JSON metin
    alt bulgu var
        V-->>N: bulgularla 1 tekrar
        N->>V: yeni metin
    end
    V-->>UI: geçen metin veya şablon metin + uyarı bandı
    RM->>UI: blokları düzenler, kartı indirir
```

### Görüşme metni nasıl yazılır ve nasıl denetlenir?

RM önerileri onayladığında anlatıcımız yalnızca onaylanan ürünlerin verilerinden bir olgu paketi hazırlar ve görüşme metnini bu paketten yazdırır. Metin arka planda hemen başlar, bu yüzden RM görüşme metni sekmesini açtığında metin çoğu zaman hazırdır. Metin hâlâ yazılıyorsa RM ekranda anlatıcının adımlarını ve her adımda hangi bilginin kullanıldığını görür:

![Metin hazırlanıyor: profil, onaylanan öneriler, piyasa verileri, yazım kuralları, yapay zekâ yazıyor, kontrol](docs/img/readme/text-wait.png)

Metin RM'e ulaşmadan önce doğrulayıcımızdan geçer. Doğrulayıcı şu durumlardan birini bulursa metni reddeder: olgu paketinde olmayan bir sayı veya tarih, elenmiş ya da listede olmayan bir ürünün adı, "garanti", "risksiz", "kesin getiri" gibi yasak bir ifade, kaynağı gösterilmemiş bir öneri cümlesi, ING ürün adının yanında ING'ye ait olmayan bir oran veya tahmini dağılımdan alınmış bir sayı. Eksik bir bölüm ya da eksik "yatırım tavsiyesi değildir" cümlesi de ret sebebidir. Reddedilen metin, bulunan sorunlarla birlikte bir kez yeniden yazdırılır; yine geçmezse RM'in önüne kurallı bir şablon metin ve bir uyarı bandı gelir. Piyasa notunu (politika faizi, USD/TRY, fonlama maliyeti) ise dil modeline hiç yazdırmıyoruz; bu bölümü kod yazar ve her değerin yanına kanıt kimliğini koyar.

Hazırlanan görüşme metni tek bir sayfadır. Sayfanın beyaz kısmı müşteriye gösterilecek sunumdur, sarı kutular ise yalnızca RM içindir ve *Sunum görünümü*nde ve çıktıda yer almaz. RM bir bloğu düzenleyebilir veya bir bölümü tamamen silebilir. Metindeki her kaynak numarası sağdaki *Kaynaklar* listesinde bir kanıt kimliğine bağlanır:

![Görüşme metni (P01): müşterinin hedefi, RM'e özel kutular, piyasa notu, temel sayılar, reel getiri grafiği ve kaynaklar](docs/img/readme/text.png)

### Ajanı ve metni neden ayrı tuttuk?

Ajan, tek bir puanın gösteremediği şeyleri tartmak için var: güncel haberler, iki adayın nitel farkı ve müşterinin mevcut dağılımı gibi. Yine de kararını kodun çizdiği sınırlar içinde verir ve RM motorun ilk 3'ünü her zaman ajanın önerisiyle yan yana görür. Görüşme metni ise tek bir model çağrısıyla (en çok bir tekrarla) yazılır; böylece maliyeti ve süresi her seferinde öngörülebilir kalır.

Ürünü geliştirirken de çoklu ajanla çalıştık. Bir lider Claude Code oturumu ve her modül için bir işçi oturumu ayrı git çalışma ağaçlarında çalıştı; modüller arasındaki sözleşmeleri dondurduk ve her adımı yeşil testlerle bitirdik ([`docs/workflow.md`](docs/workflow.md)).

## 6. Varsayımlar, belirsizlikler ve insan onay noktaları

### Varsayımlarımız

Bazı konularda veri olmadığı için varsayım yapmak zorunda kaldık. Bu varsayımların hepsi ekranda ve kayıtta görünür; `[VARSAYIM]` ile işaretlediklerimizi mentorlarla teyit edeceğiz.

- Fon getirileri geçmiş getirilerdir, bir tahmin değildir. 1 yıldan kısa dönemlerin getirilerini yıllığa çevirmiyoruz.
- Getirileri stopaj sonrası ve yıllık TÜFE'ye (%29,73) göre reel olarak hesaplıyoruz.
- Müşterinin yatırım tutarını bilmiyoruz; mevduatta 100.000-249.999 TL diliminin standart oranını kullanıyoruz.
- Risk bantları (Muhafazakâr 1-2, Temkinli 2-3, Dengeli 3-5, Agresif 4-7) ve ağırlıklar bizim yargımızdır **[VARSAYIM]**.
- Payların risk değerini oynaklık bandından hesaplıyoruz ve en az 6 alıyoruz; BYF stopajını %17,5 kabul ediyoruz **[VARSAYIM]**.
- Dağılım bantları tek bir kamuya açık kaynaktan geliyor; Temkinli bandını o kaynaktan biz çıkardık **[VARSAYIM]**.
- Müşteri dosyasında mevcut dağılım yoksa onu meslek tablosundan veya ulusal ortalamadan (TCMB FİR 2026-I) tahmin ediyoruz. Bu tahmin sıralamayı değiştirmez; RM onaylarsa değiştirir **[VARSAYIM]**.

### Belirsizliği nasıl yönetiyoruz?

Veri eksik, eski veya çelişkili olduğunda sistemimiz bunu saklamaz; RM'e gösterir. Bunun için beş araç kullanıyoruz:

| Araç | Ne yapar |
|---|---|
| Veri güveni (0-1) | kullanılan en zayıf veri satırı × tahmin katsayıları (elle girilen 0,9 · doğrulanmamış seri 0,8 · eski 0,7 · çelişen 0,6 · tahmini risk × 0,7 · kısa geçmiş × 0,8 · reel getiri hesaplanamadı × 0,8) |
| İstikrar (0-1) | her ağırlığı ve cezanın üst sınırını ×0,8 ve ×1,2 ile değiştirip sıralamayı 30-32 kez yeniden hesaplar; önerilen seçenek için "öneri yine çıkıyor mu" oranını verir ([ayrıntı](docs/kararlilik-veri-guveni.md)) |
| Tahmin yerine soru | risk profili veya kısıt tanınmazsa sıralama durur ve RM'e soru açılır; diğer bilinmeyenlerde güvenli bir düzey seçilir ve "Teyit edin" maddesi açılır |
| Profil çelişkileri | 8 sabit kural ve AI kontrolü (ör. "Muhafazakâr" profil ile büyüme önceliği; `durum`'da gelecek yıl ev peşinatı ile likidite "Düşük") |
| Uyarılar (yalnızca RM) | düşük istikrar, tahmini risk, döviz fonu, tek pay, payda sert düşüş, ING oranı piyasanın altında, süresi geçmiş stopaj veya eski TÜFE |

RM bu belirsizlikleri hazırlık sayfasında *Teyit edin* listesi olarak görür. Motor bir alanı okuyamadığında tahmin yürütmez; güvenli bir düzeyle devam eder ve RM'e yanıt seçenekleri olan bir soru açar. RM soruyu yanıtladığında sıralama yeniden hesaplanır:

![Gündem ve Teyit edin (P02): konuşulacak üç nokta, mevcut dağılım, döviz düzeyi, döviz kısıtı ve kur riski soruları](docs/img/readme/agenda.png)

### İnsan onay noktaları

Sistemimiz öneriyi hazırlar, ama müşteriye gidecek hiçbir şey RM görmeden ve onaylamadan çıkmaz. Aşağıdaki akış, bir RM'in bir müşteri için ekranda sırayla geçtiği adımları gösterir:

- Turuncu altıgenler RM'in karar verdiği yerlerdir.
- Gri kutular sistemin kendi başına yaptığı işlerdir.
- Kırmızı kutular kilitlerdir: RM bir şeyi tamamlamazsa sistem o noktadan ilerlemez.

```mermaid
flowchart TB
    S1["Sistem hazırlar<br/>müşteri profilini okur, 1.444 ürünü eler ve puanlar,<br/>ilk 3'ü, uyarıları ve RM'e soruları çıkarır,<br/>profildeki çelişkileri arar"]
    H1{{"1 · Profili gözden geçir<br/>RM 'Teyit edin' sorularını yanıtlar,<br/>tahmini portföy dağılımını onaylar veya düzeltir"}}
    H2{{"2 · Çelişkileri çöz<br/>ör. profil 'Muhafazakâr' ama öncelik büyüme;<br/>RM müşteriyle neyin geçerli olduğunu yazar"}}
    H3{{"3 · İsteğe bağlı: ajanı çalıştır<br/>RM aday sayısını seçer, web bulgularını<br/>✓ doğru veya ✗ yanlış diye işaretler"}}
    H4{{"4 · Önerileri onayla<br/>RM görüşmede konuşulacak ürünleri seçer,<br/>not yazar, Onayla veya Reddet der"}}
    L1(["Kilit: çözülmemiş bir çelişki varsa<br/>onay düğmesi çalışmaz"])
    S2["Sistem yazar<br/>yalnızca onaylanan ürünlerle görüşme metnini yazar,<br/>her sayıyı ve kaynağı kodla denetler"]
    H5{{"5 · Metni gözden geçir<br/>RM blokları okur, düzenler veya siler;<br/>her düzenleme yeniden denetlenir"}}
    H6{{"6 · Kartı al ve sun<br/>RM kartı PDF olarak indirir veya yazdırır,<br/>müşteriye Sunum görünümünü gösterir"}}
    L2(["Kilit: denetimde açık bir kural bulgusu varsa<br/>kart indirilemez ve yazdırılamaz"])
    S3["Sistem kaydeder<br/>onay zamanı, seçilen ürünler, notlar,<br/>çelişki gerekçeleri, düzenlemeler, her RM işlemi"]
    S1 --> H1 --> H2 --> H3 --> H4 --> S2 --> H5 --> H6 --> S3
    H1 -. "her yanıt veya düzeltme<br/>sıralamayı yeniden hesaplatır" .-> S1
    L1 -.- H4
    L2 -.- H6
    classDef human fill:#FF6200,color:#fff,stroke:#B34400
    classDef sys fill:#F2F4F7,color:#101828,stroke:#98A2B3
    classDef lock fill:#FEE4E2,color:#7A271A,stroke:#D92D20
    class H1,H2,H3,H4,H5,H6 human
    class S1,S2,S3 sys
    class L1,L2 lock
```

| Adım | RM ekranda ne görür | RM ne yapar | Bu adım neden var |
|---|---|---|---|
| 1 · Profili gözden geçir | "Teyit edin" listesi: motorun okuyamadığı alanlar, eksik bilgiler, tahmini portföy dağılımı | soruyu bir seçenekle yanıtlar; dağılımı "Tahmini onayla" ile kabul eder veya "Düzenle" ile kendisi girer | motor eksik bilgiyi tahmin etmez, RM'e sorar; her yanıt yeni bir hesaplama başlatır |
| 2 · Çelişkileri çöz | "Profilde çelişki" kartları; her kart çelişen alanları adlandırır, AI bulgusu iki tarafı da kelimesi kelimesine alıntılar | müşteriyle teyit ettiği durumu kısa bir gerekçe olarak yazar ("Müşteriyle teyit edildi: …") veya profili düzeltir | çelişkili bir profil yanlış bir öneriye götürür; RM'in gerekçesi kayda ve karta girer |
| 3 · Ajanı çalıştır (isteğe bağlı) | ajanın beş adımı, ajanın ilk 3'ü ve motorun ilk 3'ü yan yana, web bulguları | aday sayısını seçer (3-20); her web bulgusunu ✓ veya ✗ ile işaretler | ajan kendiliğinden başlamaz; ✗ işaretli bulgu ajana verilmez, ✓ işaretli bulgu "(web, RM doğruladı)" etiketini alır |
| 4 · Önerileri onayla | alttaki onay çubuğu: seçili ürünler, not alanı, "Reddet" ve "Onayla ve metni hazırla" | konuşulacak ürünleri seçer, isterse not yazar, onaylar veya reddeder | görüşme metni yalnızca RM'in onayladığı ürünlerle yazılır |
| 5 · Metni gözden geçir | tek sayfalık görüşme metni; beyaz alan müşteri için, sarı kutular yalnızca RM için | blokları ✎ ile düzenler veya siler; "Riskler" bölümü silinemez, "yatırım tavsiyesi değildir" cümlesi her zaman kalır | RM metnin her cümlesinden sorumludur; düzenlenen blok yeniden denetlenir |
| 6 · Kartı al ve sun | "Kart" kutusu (PDF veya Markdown), "Sunum görünümü" düğmesi | kartı indirir veya yazdırır; müşteriye sunum görünümünü gösterir | sunum görünümü sarı kutuları, notları ve kaynak numaralarını gizler; RM'e özel bilgi müşteriye gitmez |

Bu akışta birkaç kural daha geçerlidir. RM bir çelişkiyi çözmeden önerileri onaylayamaz; sistem onay isteğini "Çözülmemiş çelişki var" diye geri çevirir, ama henüz bitmemiş bir AI kontrolü onayı engellemez. "Sorulacak" etiketli kartlar yalnızca birer öneridir ve onayı engellemez; önerileri reddetmek için de gerekçe gerekmez. Denetimde açık bir kural bulgusu varken kart indirilemez ve yazdırılamaz. RM ajanı bir kez çalıştırdıysa, sonradan girdiği bir dağılım veya verdiği bir yanıt sıralamayı yeniden hesaplattığında ajan da aynı aday sayısıyla kendiliğinden yeniden çalışır.

Sistemimizin müşteriye bir şey gönderebileceği bir kanal yoktur; uygulama yalnızca RM'in bilgisayarında (`127.0.0.1`) çalışır. RM bir profili düzenlediyse veya yeni bir profil yüklediyse bu durum ekranda açıkça işaretlenir ve kartta "Düzenlenmiş profil ile hazırlandı" yazar.

## 7. Test yaklaşımı, sonuçlar, hata analizi ve yapılan iyileştirmeler

Çözümümüzü dört farklı açıdan test ettik. Her açı farklı bir soruya yanıt arar:

| Açı | Yanıtladığı Soru | Kapsam |
|---|---|---|
| Birim ve sözleşme testleri | Her kural tek başına doğru çalışıyor mu? | `pytest`: 150 dosyada 3.053 test; web: 455 test; ağ erişimi yok ise dil modeli yerine sahte model |
| Senaryo değerlendirmesi | Sistem uçtan uca, jürinin değiştirebileceği girdilerle doğru çalışıyor mu? | 34 senaryo, 39 çalıştırma, dondurulmuş veri: temel personalar, persona değişiklikleri, kısıtlar, erişilemeyen kaynak, hatalı veri, eski hataların tekrarı |
| Ajan değerlendirmesi | Ajan kurallara uyuyor mu, motordan daha iyi mi? | 8 karar: kod denetimi, yedeğe düşme oranı, tekrar, kör A/B hakemi, RM işaretleri |
| Canlı kontrol ve geri bildirim | Sistem RM için gerçekten kullanışlı mı? | ekran incelemesi, ücretli canlı kontroller, RM işlem kaydından geri bildirim raporu (`rmprep feedback`) |

### Hangi göstergelere bakıyoruz ve neden?

Brief'in kesin kurallarında, yani kısıt ihlali olmaması, uydurma veri olmaması, her bilginin kaynağının gösterilmesi ve yasak ifade kullanılmaması konularında hedefimiz %100'dür; bu kurallarda tek bir ihlali bile kabul etmiyoruz. Metin kalitesini ise yalnızca yön gösterici olarak okuyoruz, çünkü metni puanlayan hakem de bir dil modeli ve verdiği not kod kontrolleri kadar güvenilir değil.

Son tam değerlendirmemizin sonuçları (`data/eval/20261017-160939-n12-client-page`, dondurulmuş snapshot: `20261014-233110-1565`, istem n12):

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

Kısıt ihlali satırında 39 değil 37 çalıştırma var, çünkü iki çalıştırmada motor sıralamayı durdurup RM'e soru sordu ve ortada bir öneri listesi yoktu. LLM hakemi her soruya "evet" (1), "kısmen" (0,5) veya "hayır" (0) der ve tabloda bu notların ortalaması yazar. Uyarlanmış ve açık için %50, hakemin her metne "kısmen" dediği anlamına gelir; hakem hiçbir metne "hayır" demedi.

### Ajan motordan daha iyi mi?

Ajan değerlendirmemizde (`20261015-182316`, 8 karar) ajanın kararları kod denetiminden 8/8 geçti ve hiçbir kararda yedeğe düşülmedi. Ajanın kararları kaydedilir ve aynı istek tekrar geldiğinde model yeniden çağrılmadan kayıtlı karar geri getirilir; bu yüzden aynı istekler 8/8 aynı kararı verdi. Asıl tutarlılık testinde aynı girdiyle modeli yeniden çağırdık: 8 kararın 5'inde ilk 3 aynı kaldı, diğer 3'ünde yalnızca bir ürün değişti. Ajanın önerisini motorunkiyle karşılaştırmak için kör bir A/B hakemi kullandık (Claude Haiku, "Hangisi müşteriye daha uygun ve neden?"). İlk turda hakem 5 kez ajanı, hiç motoru seçmedi ve 1 kez eşit dedi. Ancak ajanın 3 kazancı P03'teydi ve orada motorun seçtiği IDY ile OKT ajanın aday listesinde yoktu; yani hakem bu iki fonun verisini göremiyordu. Aday listesini motorun ilk 3'üyle başlayacak şekilde düzelttik ve P03'ü yeniden çalıştırdık; bu kez hakem iki kez de motoru seçti. Adil karşılaştırmaların toplamı ajan 3 (P01, olumsuz haber senaryosu, RM işaretleri), motor 2, eşit 1. Bu sayılar ajanın daha iyi olduğunu göstermiyor. Bu yüzden RM iki listeyi her zaman yan yana görür ve kararı kendisi verir.

### Bulduğumuz hatalar ve yaptığımız iyileştirmeler

Geliştirme boyunca bulduğumuz her hatayı, nedenini nasıl bulduğumuzu ve düzeltmenin sonucunu kaydettik. Tam liste [`docs/found-and-fixed.md`](docs/found-and-fixed.md) belgesinde; en önemlileri şunlar:

| Ne gördük | Nasıl bulduk, neden oluyordu | Ne yaptık | Ölçülen sonuç |
|---|---|---|---|
| Kurallar %100 geçerken 5 personanın 4'ü yalnızca risk değeri 1 olan nakit benzeri fon aldı | değerlendirme paketi gösterdi; geçmiş getiri baskındı, risk bütçesini ölçen bir ölçüt yoktu | risk uyumu bandı, varlık sınıfı ve sınıf başına bir ürün kuralı | 5 personada 5 farklı set |
| Profil kendisiyle çelişebiliyordu ve hiçbir şey bunu göstermiyordu | 5 personaya bilerek çelişki yerleştirip canlı kontrol yaptık; motor yalnızca sabit değerleri okuyordu | sabit kurallar + alıntılı AI kontrolü + onaydan önce RM gerekçesi | sabit kurallar 0/5, AI kontrolü 5/5; P01, P03, P05'te yanlış alarm yok |
| İlk sayfa ~33 sn, her müşteri geçişi ~6 sn sürüyordu | adım adım zamanlama ve cProfile; bir sorgu her çağrıda ~30.000 satırı tarıyordu | varlığa göre dizin, yapay zekâ kütüphanesini ilk kullanımda yükleme, veriyi arka planda hazırlama | karar 2,86 sn → 1,18 sn; sunucu açılışı 8,7 sn → 2,3 sn; ilk 3 aynı kaldı |
| Stopaj ve TÜFE yokken fonun veri güveni 1,00 kalıyordu | "eksik veri" senaryosu; eski bir bayrak bu açığı gizliyordu | reel getiri hesaplanamazsa güven × 0,8 | eksik veri gösteriliyor 5/7 → 7/7 |
| ING oranları elle kopyalanmıştı ve eskimişti | ING sayfasını elle girilen dosyayla karşılaştırdık: 28 e-Vadeli oranı değişmişti | ING'nin kamuya açık oran sayfası için adaptör; elle girilen dosya yedek | motor %35,00 yerine güncel %34,50'yi kullanıyor |
| Pay geçmişinde ani sıçramalar vardı | bilinen bölünmelerin çevresindeki fiyatlara baktık; bültendeki önceki kapanış düzeltilmemişti | sıçrama tespiti ve günlük fiyat limitine kırpma | 5 yıllık düzeltilmiş pay getirileri |
| 5 yıllık geçmiş 15.02.2023'te kesiliyordu | 8-14.02.2023 "okunamaz" işaretlenmişti: depremden sonra borsa kapalıydı | kapanışı 0 olan geçerli bülten = işlem olmayan gün | tam 5 yıllık geçmiş |
| Bir metin şablona düştü ("Garanti Portföy GZP" → yasak ifade "garanti") | değerlendirmenin hata listesi cümleyi ve bulguyu verdi | doğrulayıcı, adı geçen fonun kurucu adını yasak ifade taramasından önce çıkarır; başka yerde "garanti" hâlâ bulgudur | testler iki yönde geçiyor; canlı yeniden çalıştırmada kayıtlı eski metin geri geldi; yeni bir metinle kontrol açık iş |

Henüz çözmediğimiz konular da var. TEFAS bazı günlerde bir fonun fiyatını ve büyüklüğünü 0 olarak yayımlıyor (son snapshot'ta 45 fon) ve bu sıfırları henüz işaretlemiyoruz. İki EVDS serisini (BIST 100 getiri endeksi ve altın) doğrulamadık; bu seriler "doğrulanmamış seri" bayrağı taşıyor. Metinleri puanlayan LLM hakemi de neredeyse her metne "kısmen" diyor, çünkü rubriğini müşteri sayfası için değil RM notu için yazmıştık.

### Geri bildirim döngüsü

Sistemde RM'in ürün üzerinde yaptığı her işlem (onay, ret, düzenleme, silme, ✓/✗ işareti, dağılım girişi, ajan başlatma) sürüm bilgileriyle birlikte `data/logs/rm-actions/` dosyasının altında bir JSON satırı olarak yazılır. `rmprep feedback` komutu bu kayıtlardan beş ölçü hesaplar ve belirlenmiş aksiyon eşiklerine göre (mesela web search'te 5 tane ✗ işareti koymuş olmak) öneriler çıkarır. Örneğin, RM'lerin hangi metin bölümünü sık sildiğini, ajanın önerisinin ne sıklıkla kabul edildiğini ve dağılım tahminimizin ne kadar yanıldığını gösterir. Rapor hiçbir ayarı kendiliğinden değiştirmez ve dil modeli kullanmaz; değişiklik kararını yine biz veririz. Şu anda sistemimizi olduğu kadar insan-destekli tutmaya çalıştık; gelecekte bu geri bildirim döngüsü, belirlediği geliştirmeleri/optimizasyonları otomatik olarak yapabilir. Böylece agentic mühendislikteki eval loops (Değerlendirme Döngüsü) efekte girmiş olur. Şu anda bilerek daha manuel gitmeyi tercih ettik, ne de olsa 5 müşteri örneğimiz var ve RM aksiyonları kendi tarafımızdan yaptığımız test işlemlerinden ibaret.

## 8. Veri kaynağı, zaman damgası ve karar gerekçesi gibi izlenebilirlik yaklaşımları

Sistemdeki her öneriyi, dayandığı verinin kaynağına, değer tarihine ve verinin hangi saatte çekildiğine kadar geriye doğru izleyebiliyoruz. Tüm zamanları Türkiye saatiyle (`Europe/Istanbul`) tutuyoruz. Aşağıdaki şema bir sayının ham indirmeden görüşme metnindeki cümleye kadar izlediği yolu gösteriyor:

```mermaid
flowchart TB
    subgraph L1["1 · Veri"]
        direction LR
        P["📥 Ham indirme<br/>snapshot + SHA-256"] --> D["🔢 Değer<br/>kanıt kimliği<br/>ör. Edede971a<br/>kaynak, değer tarihi, alınma zamanı"]
        W["🌐 Web bulgusu<br/>bulgu kimliği<br/>ör. F5737d1fc<br/>kaynak alanı, tarih<br/>RM işareti ✓ / ✗"]
    end
    subgraph L2["2 · Karar"]
        direction LR
        O["⚖️ Puan parçası ve gerekçe<br/>kanıt kimlikleriyle"] --> R["🗂️ Karar kaydı<br/>run_id + yapılandırma özeti"]
        AG["🤖 Ajan gerekçesi<br/>kanıt, bulgu, puan<br/>ve portföy atıflarıyla"]
    end
    M["📝 Görüşme metni<br/>her cümle kanıt kimliklerini taşır"]
    A{{"✅ RM onayı ve düzenlemeleri<br/>Türkiye saatiyle kayıtta"}}
    D --> O
    D --> AG
    W --> AG
    R --> M
    AG --> M
    M --> A
    classDef code fill:#EEF2F9,stroke:#525199,color:#101828
    classDef ai fill:#F4F3FF,stroke:#6941C6,color:#101828
    classDef human fill:#FF6200,stroke:#B34400,color:#fff
    class P,D,O,R code
    class W,AG,M ai
    class A human
    style L1 fill:#FCFCFD,stroke:#98A2B3
    style L2 fill:#FCFCFD,stroke:#98A2B3
```

Hangi katmanda neyi nasıl izlediğimiz:

| Ne | Nasıl izliyoruz |
|---|---|
| Her değer | kanıt kimliği (kaynak, ölçü, varlık ve tarihin özeti), kaynak, kaynak adresi, değer tarihi (`as_of`), alınma zamanı (`fetched_at`), kalite bayrakları |
| Ham veri | snapshot'ta bayt bayt; her dosyanın SHA-256 özeti; kullanılan yapılandırmanın kopyası; salt okunur. `rmprep replay` aynı çıktıyı ağa çıkmadan yeniden üretir |
| Kalite | kontroller değeri değiştirmez, yalnızca bayrak ekler: eksik, eski, aralık dışı, çelişen, yedek snapshot, doğrulanmamış seri, elle girilen. Kaynaklar arası çapraz kontrol de yaparız (ör. TÜFE: EVDS 29,7315, elle 29,73) |
| Her karar | `run_id` (müşteri + snapshot + yapılandırma özeti; aynı girdi → aynı kimlik), her puan parçası ve gerekçesi kanıt kimlikleriyle, elenenler gerekçeleriyle, varsayımlar, uyarılar |
| Ajan kararı | `data/agent/<run_id>.json`: adaylar, araçların `amac` notları, denetim sonuçları, her gerekçenin atıfları, istem sürümü, model, maliyet |
| Web bulguları | bulgu kimliği, kaynak alanı, tarih, "doğrulanmamış" etiketi, RM'in ✓/✗ işareti; aynı gün aynı ürün için kayıtlı sonuç ve maliyet defteri |
| Onaylar | RM'in karar zamanı, seçim, notlar, profil çelişkilerinin çözümleri; `data/runs/`, `data/narratives/`, `data/cards/` |
| Metin | her cümle seçenek ve kanıt kimliği taşır; model, istem sürümü, doğrulayıcı sonucu, RM düzenlemeleri ve maliyet kayda girer |
| RM işlemleri | `data/logs/rm-actions/<gün>.jsonl`: her işlem zamanı, çalıştırması, personası, snapshot'ı ve yapılandırma/istem sürümleriyle |

RM ekranda bir sayının yanındaki "K" işaretine tıkladığında o sayının kanıt penceresi açılır:

<img src="docs/img/readme/evidence.png" alt="Kanıt penceresi: değer, kaynak, değer tarihi, alınma zamanı, kanıt kimliği ve bayraklar" width="448">

*Bu örnekte EIL fonunun 1 yıllık getirisi %48,13. Değer TEFAS getiri sayfasından (`tefas_web`) geliyor, değer tarihi 16.10.2026 (bir önceki iş günü), veri 17.10.2026 saat 11:04'te çekilmiş, kanıt kimliği `Edede971a` ve değerin üzerinde hiçbir kalite bayrağı yok. En alttaki "Kaynağı aç" linkine tıklayarak da verinin alındığı web sayfasını görüntüleyebiliyorsunuz.* Bir önerinin tam karar kaydını [Teslimat 6](docs/teslim/06-kanit-kaydi-ornegi.md) belgesinde görebilirsiniz.

`.env` ve `data/` klasörü depoya girmez. Bu prototipi ING Agentic AI Hackathon için geliştirdik.
