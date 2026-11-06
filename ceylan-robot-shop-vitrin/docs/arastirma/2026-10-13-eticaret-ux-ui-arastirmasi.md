# E-ticaret UX/UI Araştırması — Endüstriyel B2B+B2C Satış Sitesi Mockup'ı

Tarih: 2026-10-13 · Kapsam: 2. el/yeni robot, PLC, sürücü, yedek parça · Kısıt: Jinja2 SSR, elle CSS, minimum vanilla JS, CDN/framework yok, satır içi script/style yasak (CSP).

**Kaynak güvenilirliği notu.** Baymard ve NN/g sayfaları doğrudan okundu; rakamlar o sayfalardan. Reddit'e erişim araçta engelli (reddit.com alan adı erişilemez) ve aramalarda r/PLC, r/ecommerce vb. başlık çıkmadı: **Reddit kaynaklı hiçbir iddia bu belgede yok, "doğrulanmadı"**. YouTube'da yalnızca başlık düzeyinde sonuç alındı (içerik izlenmedi). **2. turda (bu belgenin sonundaki "Ek" bölümü) Reddit ve YouTube yine araç düzeyinde engelli çıktı; boşluk yalnızca kısmen, Hacker News/EEVblog/control.com gibi başka topluluk forumlarıyla kapatıldı. Reddit/YouTube iddiası hâlâ yok.** RS Components, Misumi, Automation24, Radwell, Robots.com, EU Automation, Digi-Key sayfaları ya 403 verdi ya da arama kutusu/fiyat gibi dinamik kısımları getirmedi; bu sitelerde gözlem sınırlıdır ve aşağıda açıkça belirtildi.

---

## 1. Yönetici özeti

1. **Parça numarası birinci sınıf vatandaş.** Endüstriyel alıcı ürün adıyla değil, tam katalog/üretici koduyla (ve "eşdeğeri/çapraz referans" ile) arar. Arama kutusu başlığın en büyük öğesi olmalı; kod tam eşleşmesi sonuçta en üstte çıkmalı.
2. **Liste = yoğun tablo (masaüstü), kompakt liste (mobil).** Baymard, özellik ağırlıklı B2B ürünlerde kart/liste yerine "ürün tablosu" önerir (kolon sıralama, çoklu filtre). Kart ızgarası yalnızca ana sayfa/vitrin için.
3. **Fiyat, stok, teslim süresi ve durum bir arada, her yerde aynı biçimde.** B2B alıcılar fiyat ister; NN/g "gizli fiyat" yerine kesin veya en azından örnek fiyat önerir. 2. el için "durum + test + garanti" rozeti güvenin taşıyıcısıdır.
4. **Teklif (RFQ) ikinci birincil eylem, sepet birincil.** Fiyatı olmayan/tek adetlik 2. el robotlarda "Teklif iste" ana CTA; standart parçalarda "Sepete ekle".
5. **Ödeme: misafir en görünür seçenek, tek sütun, satır içi doğrulama, toplam maliyet erken.** Baymard: terk nedenlerinin başında beklenmedik ek ücret (%39) ve zorunlu üyelik (%19).
6. **Görsel yön: marka yeşil/kiremit korunur, ama modern sans yığını, nötr yüzey, yüksek yoğunluk, az gölge.** Mevcut `#687860` açık zeminde metin olarak AA'yı geçmiyor (4,19:1); metin için koyulaştırılmış tonlar gerekli.
7. **JS'siz mümkün:** arama (GET formu), filtre (form+`<details>`), mobil çekmece (CSS `:target` veya `<details>`), karşılaştırma (checkbox+form), adım göstergesi, hata mesajları. JS yalnızca otomatik tamamlama ve toplu satır ekleme için isteğe bağlı.

---

## 2. Endüstriyel B2B kullanıcı davranışı

| Davranış | Bulgu | Kaynak |
|---|---|---|
| Parça no ile arama | Alıcılar "[parça no] equivalent", "[üretici] [model] cross-reference", özellik+malzeme sınıfı ile arar. RFQ aşaması sorguları ayrı. (Ajans blogu; ikincil kaynak) | [1Digital Agency](https://1digitalagency.com/blog/b2b-ecommerce-seo-for-industrial-distributors/), [Growthspree](https://www.growthspreeofficial.com/blogs/google-ads-b2b-manufacturing-industrial-buyer-search-2026) |
| Arama kutusu içinde zengin sonuç | Arama önerilerinde görsel, kısa açıklama, parça no, hatta sepete ekle; "stokta olanlar" ve "daha önce aldıklarım" filtreleri önerilir (satıcı blogu, ikincil) | [Optimizely](https://www.optimizely.com/insights/blog/improving-b2b-ecommerce-search/) |
| Uzun filtre listeleri | Test edilen sitelerin %46'sı filtre türü içinde aramaya izin vermiyor; 15-20+ seçenekte arama gerekli; mantıklı sıralama (ohm için küçükten büyüğe, üretici alfabetik) | [Baymard, Nis 2024](https://baymard.com/blog/allow-search-for-long-filter-options-lists) |
| Teknik özellik karşılaştırma | Spec ağırlıklı B2B'de masaüstünde "Product Table" öneriliyor; kolon başına artan/azalan sıralama; test edilen neredeyse tüm üretici/distribütör siteleri tablo kullanıyor. Mobilde tablo 2-4 kolon gösterir, liste görünümü önerilir | [Baymard: Product Tables](https://baymard.com/blog/use-product-tables-for-desktop-product-listings) |
| Karşılaştırma aracı | Üst 60 sitenin yalnızca %38'inde ayrı karşılaştırma var; tutarsız saklanan özellikler karşılaştırmayı imkansız kılar; spec sayfalarının %50'si taranması zor | [Baymard: Comparison](https://baymard.com/blog/provide-comparison-features), [Spec sheet](https://baymard.com/blog/spec-sheet-scannability) |
| Stok / teslim süresi / MOQ / kademeli fiyat | Altı B2B elektronik sitesinde MOQ, hacim fiyat kademeleri, kargo süresi ve stok, tablo ile satın alma bölümü arasında tutarsız gösteriliyor | [Baymard arama özeti](https://baymard.com/research/product-page) (alt başlık numaraları 7-12; tam metin ücretli, doğrudan doğrulanmadı) |
| Fiyat beklentisi | NN/g: B2B müşteriler B2C kadar fiyat duyarlı; kesin fiyat, olmazsa örnek fiyat veya hesaplayıcı; fiyat bir "filtre" işlevi görür | [NN/g B2B vs B2C](https://www.nngroup.com/articles/b2b-vs-b2c/) |
| Uyumluluk / standart bilgisi | Uyumluluk en büyük kaygılardan; standartlar (ISO, RoHS), bağlantı ve çevre koşulları yazılmalı | aynı NN/g makalesi |
| Ekip içi onay | Sepeti/içeriği meslektaşla paylaşma araçları öneriliyor; satın alma döngüsü uzun | aynı NN/g makalesi |
| Teklif/RFQ | Alım yolu: spesifikasyon, kaynak, doğrulama, teklif, sipariş, yeniden sipariş; tek tıkla satın alma nadir (ajans, ikincil). Surplus Record ana sayfasında doğrudan teklif butonu yok; "Wanted" ilanı ve satıcı sorgusu modeli var (doğrudan gözlem) | [1Digital](https://1digitalagency.com/blog/b2b-ecommerce-seo-for-industrial-distributors/), [Surplus Record](https://www.surplusrecord.com) |
| Toplu sipariş | Digi-Key'de "Upload a List", "My Lists", "Quotes" bağlantıları var (işlevi sayfadan doğrulanmadı) | [Digi-Key](https://www.digikey.com) |
| KDV hariç fiyat | NN/g doğrudan KDV'den bahsetmiyor. Gözlem: Türk perakende (Direnc.net) fiyatları "KDV dahil" gösteriyor. B2B için KDV hariç varsayılan + anahtar öneri **bizim çıkarımımız**, kaynakla doğrulanmadı | [Direnc.net](https://www.direnc.net) |
| 2. el güveni | Sahte/kilitli işlemci, firmware uyumsuzluğu, "New" etiketinin belirsizliği, yetkisiz satıcıda üretici garantisinin geçersizliği alıcı kaygıları; test raporu ve satıcı garantisi isteniyor (satıcı kılavuzları, ikincil; forum değil) | [NJT Automation](https://njtautomation.com/guides/allen-bradley-condition-labels/), [uBuyFirst](https://app.ubuyfirst.com/guides/allen-bradley-buying-guide), [DO Supply](https://www.dosupply.com/buy/allen-bradley/810-A18A) |

---

## 3. Desen kataloğu

Her satır: **Ne / Neden / Bizde nasıl / JS durumu.**

### 3.1 Başlık + arama
- **Ne:** Üst bantta logo, geniş tek arama kutusu (placeholder: "Parça no, üretici kodu veya ürün adı"), telefon, hesap, sepet, KDV hariç/dahil anahtarı, dil/para birimi.
- **Neden:** Parça no ile arama birincil (bkz. 2). McMaster ana sayfası yüksek yoğunlukta, karusel/pop-up yok, "Browse Catalog" + iletişim bilgisi ile işi öne alıyor ([Medusa analizi](https://dev.to/medusajs/9-ux-best-practices-for-ecommerce-1oao), [IA Collaborative](https://iacollaborative.com/work/mcmaster-carr); ikincil). Direnc.net başlıkta güven skoru, ücretsiz kargo eşiği ve TR/EN anahtarı kullanıyor; RS başlıkta kargo takibi ve "Find your local branch" yer alıyor (doğrudan gözlem; arama kutusu içerik dökümünde görünmedi).
- **Bizde:** `<form method="get" action="/ara">` + `<input type="search" name="q">`. Sunucu: önce tam parça no eşleşmesi (boşluk/tire/büyük-küçük harf normalize), sonra önek, sonra metin; üretici kodu ve eski kod (çapraz referans) ayrı alan. Sonuç yoksa "Bu kod için teklif isteyin" yönlendirmesi.
- **JS:** Arama JS'siz tam çalışır. Otomatik tamamlama isteğe bağlı: ~40 satır `fetch` + `<datalist>` veya `<ul>`; Baymard önerileri: eşleşme sayısı göster, temizle düğmesi, yazılmayan kısmı vurgula ([kaynak](https://baymard.com/blog/allow-search-for-long-filter-options-lists)).

### 3.2 Mega menü yerine kategori gezinmesi
- **Ne:** Başlıkta tek "Kategoriler" düğmesi → `/kategoriler` tam sayfa (ikonlu, 2 kademe listesi, ürün sayısıyla). Ana sayfada aynı liste yoğun ızgara.
- **Neden:** McMaster ve RS kategori sayfasını/tiles'ı doğrudan açar (RS: 33 üst kategori, "800.000+ ürün", "Show N subcategories" aç-kapa); Direnc.net ~40 kategori mega menüsü kullanıyor. 8-10 üst kategorimizde mega menü gereksiz ağırlık, hover menüsü dokunmatik ve erişilebilirlikte zayıf (çıkarım).
- **Bizde:** Üst düzey: Robotlar (yeni/2. el), PLC, Sürücüler/Servo, HMI, Robot yedek parça, Sensör/Kablo, Hizmetler. Marka ve "durum" (Yeni/2. el/Revizyonlu) ikinci eksen.
- **JS:** Gerekmez; `<details><summary>` ile alt kategori açılımı.

### 3.3 Ürün listesi: kart mı, tablo mu?
- **Ne:** Varsayılan masaüstü = yoğun tablo: görsel (küçük) · parça no · tanım · 2-4 anahtar özellik · durum rozeti · stok/teslim · fiyat (KDV hariç) · "Sepete/Teklif". Tüm kolon başlıkları sıralanabilir link. Kart görünümü seçenek. Mobil = kompakt liste (parça no, fiyat, stok, 2-3 özellik).
- **Neden:** Baymard: B2B spec ağırlıklı ürünlerde tablo > liste; mobilde tablo 2-4 kolon, liste önerilir ([kaynak](https://baymard.com/blog/use-product-tables-for-desktop-product-listings)). Baymard liste araştırması: sitelerin %64'ü liste öğesi bilgisinde en az bir hata yapıyor, %86'sı çok adetli ürünlerde birim fiyatı göstermiyor, %13'ü ürün sayfasından dönünce aynı konuma döndürmüyor; spec odaklı ürünlerde hızlı bakış (quick view) önerilmiyor ([kaynak](https://baymard.com/blog/ecommerce-product-lists-report-and-benchmark)).
- **Bizde:** `<table>` semantik, `<caption>` ve `scope="col"`; sıralama `?sirala=fiyat_art`; sayfalama `?sayfa=2` (sonsuz kaydırma yok, konum korunur). Mobilde tabloyu CSS ile `display:block` kart-satıra çevir.
- **JS:** Gerekmez.

### 3.4 Filtreler (mobilde çekmece)
- **Ne:** Sol dikey filtre paneli; uygulanan filtreler üstte çip olarak, tek tıkla kaldır; filtre başına sayaç; 15+ seçenekte filtre içi arama; çoklu seçim (VEYA); önemli filtreler önde (Durum, Stok, Marka, Seri, Voltaj/Güç).
- **Neden:** Baymard: %28'i uygulanan filtrelere genel bakış göstermiyor, %61'i önemli filtreleri öne çıkarmıyor, %15'i aynı türde çoklu seçime izin vermiyor ([kaynak](https://baymard.com/blog/ecommerce-product-lists-report-and-benchmark)); filtre içi arama için yukarıdaki Nisan 2024 makalesi.
- **Bizde:** `<form method="get">` içinde checkbox grupları + "Uygula". Mobilde "Filtrele (3)" düğmesi: `<details>` veya CSS `:target` tam ekran çekmece; altta sabit "142 sonucu göster". Filtre içi arama için uzun listelerde isteğe bağlı küçük JS (liste süzme).
- **JS:** Çekirdek JS'siz; filtre içi arama için ~20 satır.

### 3.5 Ürün detayı
- **Fiyat bloğu:** Fiyat KDV hariç büyük, KDV dahil küçük; kademeli fiyat tablosu; adet girişi. Baymard: ürün sayfalarının %67'si "Buy" yanında toplam maliyet tahmini göstermiyor, %44'ü iade politikasını ürün içeriğinden bağlamıyor, %60 kullanıcı iade bilgisini ürün sayfasında arıyor ([kaynak](https://baymard.com/blog/current-state-ecommerce-product-page-ux)). → Fiyat bloğunun altında "Teslimat + kargo tahmini" ve "İade/garanti" bağlantısı.
- **Stok/teslim:** "Stokta 3 adet · Bugün 16:00'a kadar siparişte yarın kargo" ya da "Tedarik: 7-10 iş günü". Renk + metin + ikon (yalnızca renge bağımlı olma).
- **Durum rozeti (2. el güveni):** Yeni (kutulu) / Yeni (açık kutu) / Revizyonlu / 2. el-test edildi / Arızalı-yedek parça. Rozet yanında tek satırlık tanım ve "Test raporu" bağlantısı. Gerekçe: "New" etiketinin satıcıdan satıcıya anlamının değişmesi ve kilitli işlemci/firmware riski ([NJT](https://njtautomation.com/guides/allen-bradley-condition-labels/)). Ürün sayfasında: seri no fotoğrafı, test tarihi, firmware/revizyon, garanti süresi.
- **Teknik özellik tablosu:** Gruplanmış (Elektriksel / Mekanik / Haberleşme / Çevre), tutarlı etiketler. Baymard: gruplama alfabetik listeden kolay; sitelerin %50'sinde spec sayfası taranması zor ([kaynak](https://baymard.com/blog/spec-sheet-scannability)). Veri modelinde etiketlerin standartlaşması şart (Baymard B2B'de aynı özelliğin farklı adlandırılmasını sorun olarak bulmuş; alt başlık 7-21/22, tam metin doğrulanmadı).
- **"Teklif iste" CTA:** Sepete ekle ile aynı blokta, ikincil buton. Form: parça no önceden dolu, adet, ihracat/ülke, KDV durumu, firma. Başarılı gönderimde referans no + beklenen yanıt süresi.
- **JS:** Gerekmez. Sekmeler `<details>` veya sayfa içi `#bağlantılar`.

### 3.6 Sepet ve ödeme
- **Adım göstergesi:** 1 Sepet → 2 Bilgiler → 3 Teslimat/Ödeme → 4 Onay; `<ol>` + `aria-current="step"`. Baymard: doğrusal olmayan akış en ağır kullanılabilirlik ihlallerinden ([TechnologyAdvice özeti, ikincil](https://technologyadvice.com/blog/sales/checkout-optimization/)).
- **Misafir/üye:** "Misafir olarak devam et" en belirgin; hesap oluşturma siparişten sonra. Baymard: ABD'li yetişkinlerin %19'u hesap açmak istemediği için siparişi bıraktı; sitelerin %62'si misafiri en belirgin seçenek yapmıyor ([Baymard](https://baymard.com/blog/checkout-flow-ux-optimization)). Kurumsal müşteri için ayrı giriş + "vergi no ile fatura" alanı.
- **Form:** Etiketler alanın üstünde, tek sütun, yalnızca gerekli alanlar (Baymard ortalama 19,9 form öğesi; optimize akış 12'ye inebilir), plain-language hata mesajı (%98'i bunu yapmıyor), satır içi doğrulama (%31'inde yok). Adres otomatik doldurma attribute'ları (`autocomplete="street-address"` vb.) JS gerektirmez.
- **Maliyet şeffaflığı:** Sepette KDV, kargo, toplam; beklenmedik ek ücret terk nedenlerinin %39'u ([Baymard](https://baymard.com/blog/checkout-flow-ux-optimization)). Fatura bilgileri (vergi dairesi/no), "KDV hariç ihracat" seçeneği.
- **Çıkarım:** "Banka havalesi / cari hesap / kredi kartı / teklife dönüştür" ödeme seçenekleri; B2B'de kart tek seçenek olmamalı. (Kaynaklı değil; Baymard %10'u tercih ettiği ödeme yöntemi yok diye terk ediyor.)
- **JS:** Gerekmez; yalnızca satır içi doğrulama için HTML5 `required`, `pattern`, `:user-invalid` CSS.

### 3.7 Güven unsurları
- Rozet seti: "Test edilmiş", "X ay garanti", "14 gün iade (2. el koşulları)", "İhracat ve gümrük desteği", "Fatura/e-fatura", "Teknik destek (telefon)". Direnc.net güven skoru rozeti (TrustBuy) ve Robotistan "garanti, hızlı teslimat, destek, kolay iade" kullanıyor (doğrudan gözlem).
- Gerçek fotoğraf (kendi depomuz, seri no plakası). İletişim: telefon başlıkta (McMaster ve RS örnekleri). Garanti ve iade sayfaları tek tıkla.
- Yetkisiz satıcı uyarısı: üretici garantisi yerine kendi garantimizi açıkça yazmak, rakiplerin yazdığı gibi belirsiz bırakmamak ([DO Supply notu](https://www.dosupply.com/buy/allen-bradley/810-A18A)).

### 3.8 Boş durumlar ve hatalar
- **Sıfır sonuç:** "‘6ES7 …’ için sonuç yok" + yazım ipuçları (tire/boşluk), "Bu parçayı bizden isteyin" RFQ formu, benzer kategori bağlantıları. Filtre sıfır sonuç verirse hangi filtrenin kaldırılacağını öner.
- **Boş sepet:** son bakılan ürünler, "Parça no listesi yükle (CSV)" bağlantısı.
- **Hata:** Ne oldu + ne yapmalı + alan yanında; sayfa üstünde özet (`role="alert"`), hata özeti alanlara bağlantı verir.

### 3.9 Erişilebilirlik
- Avrupa Erişilebilirlik Yasası (EAA) 28 Haziran 2025'ten itibaren AB'deki tüketicilere e-ticaret hizmeti sunanları kapsıyor; referans EN 301 549 (web için WCAG 2.1 AA); EN 301 549'un yenilenmiş sürümünün 2026 3. çeyrekte yayımlanması planlanmıştı, resmi statü hukuk bürolarında tutarsız ([Taylor Wessing](https://www.taylorwessing.com/en/insights-and-events/insights/2025/09/european-accessibility-act-requirements-for-e-commerce-services), [Bird & Bird](https://www.twobirds.com/en/insights/2025/a-guide-to-navigating-the-european-accessibility-act-for-online-retailers-service-providers-and-plat)). AB'ye tüketici satışı (B2C ihracat) varsa geçerli olabilir; hukuk görüşü alınmalı (**doğrulanmadı**, mikro işletme muafiyeti ayrıca incelenmeli).
- Uygulama: gerçek `<button>/<a>`, görünür odak halkası, 44px dokunma hedefi, `label for`, tablo semantiği, `skip link`, `lang`, kontrast (bkz. 4), renk tek başına durum belirtmez, `prefers-reduced-motion`.

---

## 4. Görsel dil önerisi

### 4.1 Tipografi
**Öneri: başlık dahil modern sans (sistem yığını); Georgia yalnızca ana sayfa büyük başlığında isteğe bağlı vurgu, ürün/liste/form ekranlarında kullanılmasın.**
Gerekçe: Georgia sunum temasında kurumsal ağırlık verir ama eski nesil algısı yaratır; yoğun tablo ve fiyatlarda oldstyle rakamlar (Georgia eski stil rakam kullanır) sütun hizasını bozar. Sistem sans ile `font-variant-numeric: tabular-nums` hizalı fiyat/stok verir. Webfont CDN yok, yerel `@font-face` mümkün ama başlangıçta gereksiz.
```
--font-ui: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
--font-mono: ui-monospace, "Cascadia Mono", "SF Mono", Consolas, "Liberation Mono", monospace; /* parça no */
--font-display: Georgia, "Times New Roman", serif; /* yalnızca isteğe bağlı hero başlığı */
```
Ölçek (rem, 16px taban): 12 / 13 / 14 / 16 / 18 / 22 / 28 / 36. Gövde 14-15px (B2B yoğunluk), tablo 13-14px, satır yüksekliği 1,45. Parça numaraları mono, tablo rakamları `tabular-nums`.

### 4.2 Renk sistemi ve WCAG kontrast (hesaplandı)
WCAG 2.x oranları, göreli parlaklık formülüyle PowerShell'de hesaplandı. Eşik: normal metin 4,5:1, büyük metin ve arayüz bileşeni sınırı 3:1.

| Token | Hex | Kullanım |
|---|---|---|
| `--bg` | #f4f1e9 | Sayfa zemini (marka) |
| `--surface` | #ffffff | Kart, tablo, form |
| `--surface-2` | #ebe7db | Tablo şeridi, panel |
| `--ink` | #1d231f | Gövde metin |
| `--ink-muted` | #5b645d | İkincil metin |
| `--brand-900` | #303a32 | Başlık bandı, birincil koyu |
| `--brand-600` | #4f5e48 | Marka yeşili, metin/bağlantı güvenli ton |
| `--brand-500` | #687860 | Marka yeşili (yalnızca dekor/büyük metin/dolgu+beyaz büyük) |
| `--accent` | #a83c29 | Kiremit, birincil CTA ("Sepete ekle"/"Teklif iste") |
| `--accent-700` | #8f3222 | CTA hover, hata metni |
| `--info` | #267593 | Bağlantı/bilgi mavisi |
| `--info-700` | #1d607c | Bağlantı hover |
| `--border-strong` | #7f857b | Form alanı sınırı |
| `--border` | #c9c4b4 | Ayırıcı çizgi (dekoratif) |
| `--ok` / `--ok-bg` | #2e6b3a / #e3efe2 | Stokta |
| `--warn` / `--warn-bg` | #7a4f00 / #fbefd0 | Sınırlı stok, 2. el uyarısı |
| `--danger` / bg | #8f3222 / #f8e3de | Hata, stok yok |

Hesaplanan oranlar:

| Çift | Oran | Sonuç |
|---|---|---|
| #1d231f / #f4f1e9 | 14,18 | AA/AAA |
| #1d231f / #ffffff | 16,00 | AA/AAA |
| #303a32 / #f4f1e9 | 10,47 | AA/AAA |
| #ffffff / #303a32 | 11,82 | AA/AAA |
| **#687860 / #f4f1e9 (marka yeşili metin)** | **4,19** | **AA metinde GEÇMEZ** (büyük metinde geçer) |
| #687860 / #ffffff | 4,73 | AA geçer (sınırda) |
| #ffffff / #687860 (yeşil düğme) | 4,73 | AA geçer; zeminde geçmez, düğmede tercih #4f5e48 |
| #4f5e48 / #f4f1e9 | 6,15 | AA |
| #4f5e48 / #ffffff | 6,94 | AA |
| #a83c29 / #f4f1e9 | 5,56 | AA |
| #ffffff / #a83c29 (CTA) | 6,28 | AA |
| #ffffff / #8f3222 | 7,93 | AA/AAA |
| #267593 / #f4f1e9 | 4,60 | AA (sınırda) |
| #267593 / #ffffff | 5,19 | AA |
| #ffffff / #267593 | 5,19 | AA |
| #1d607c / #ffffff | 6,96 | AA |
| #5b645d / #f4f1e9 | 5,43 | AA |
| #5b645d / #ebe7db | 4,96 | AA |
| #2e6b3a / #e3efe2 | 5,40 | AA |
| #7a4f00 / #fbefd0 | 6,23 | AA |
| #8f3222 / #f8e3de | 6,43 | AA |
| #c9c4b4 / #f4f1e9 (çizgi) | 1,55 | Bileşen sınırı için GEÇMEZ; yalnızca dekoratif ayırıcı |
| #7f857b / #ffffff (input sınırı) | 3,79 | Bileşen sınırı için 3:1 geçer |
| #7f857b / #f4f1e9 | 3,36 | geçer |
| #687860 / #ebe7db | 3,82 | Metin için geçmez |
| #267593 / #ebe7db | 4,20 | Metin için geçmez (şerit satırda bağlantı için #1d607c kullan) |
| Odak halkası #267593 / #303a32 | 2,28 | Koyu zeminde GEÇMEZ; koyu bantta sarı #f2b705 kullan (6,50) |

**Sonuç:** Marka yeşili #687860 açık zeminde metin/ikon olarak kullanılmamalı (4,19); metin ve bağlantıda #4f5e48 / #1d607c. Kiremit #a83c29 CTA ve vurgu için güvenli. Durum renkleri ayrı metin+ikon ile.

### 4.3 Boşluk, ızgara, köşe, gölge
- Boşluk ölçeği 4 tabanlı: 4, 8, 12, 16, 24, 32, 48. Konteyner 1280px, 12 sütun, 16-24px oluk.
- Köşe: 4px (input/tablo), 6px (kart/düğme), 999px yalnızca durum rozeti. Endüstriyel/ciddi his için büyük yuvarlaklıktan kaçın.
- Gölge: neredeyse yok; 1px `--border` çizgisi + açılır menü/çekmecede tek `0 4px 16px rgba(29,35,31,.12)`.
- Çizgi: tablo satır ayırıcı `--border`, form alanı `--border-strong`.

### 4.4 İkonografi
Tek `<svg>` sprite dosyası (`/static/icons.svg`), `<svg><use href="/static/icons.svg#cart"></use></svg>`; 24px ızgara, 1,5px çizgi, `currentColor`. CSP satır içi script gerektirmez; `use` harici dosyayı aynı kökenden çağırır. Gerekli set: arama, sepet, kullanıcı, telefon, kontrol (test edildi), kalkan (garanti), kamyon (teslimat), dünya (ihracat), dosya (teknik föy), filtre, çarpı, ok, uyarı, bilgi.

### 4.5 Yoğunluk
B2B için sıkı: tablo satır yüksekliği 40-44px (dokunmatik hedef 44px için mobilde 48), form alanı 40px, gövde 14px. Rahat yoğunluk anahtarı gerekmez, ürün listesinde "Sık/Normal" seçeneği isteğe bağlı.

### 4.6 Karanlık mod
**Gerekli değil (ilk sürüm).** Gerekçe: fabrika/ofis kullanıcısı çoğunlukla masaüstü gündüz, yönetim sunumunda tek tutarlı görünüm daha önemli, tablo ve durum renkleri için ikinci palet doğrulama yükü getirir. Token yapısı (CSS özel özellikleri) ileride `@media (prefers-color-scheme: dark)` eklemeye hazır tutulur; örnek metin/yüzey çifti #e8e6dc / #1b211d (13,09:1).

---

## 5. Yapılmaması gerekenler

| Kaçın | Gerekçe / kaynak |
|---|---|
| Ana sayfa karuseli, otomatik dönen | NN/g: insanlar büyük görselleri çoğu kez doğrudan geçer, ilk kare dışı kaçırılır, mobilde otomatik ilerletme önerilmez ([NN/g](https://www.nngroup.com/articles/designing-effective-carousels/)). Baymard: üst sitelerin %33'ünde karusel var, %46'sında kullanılabilirlik sorunu; statik içerik bölümleri iyi yapılmış karusele yakın performans gösterir ve daha kolay ([Baymard](https://baymard.com/research-articles/homepage-carousel)) |
| Gizli fiyat / "fiyat için arayın" her yerde | NN/g B2B alıcıların fiyatı ilk ihtiyaç saydığını ve fiyat göstermeyen sitelerden rakibe gittiğini söyler (2013 tarihli; **birincil makale doğrulanmadı**, ikincil alıntı: [Populi](https://populiweb.com/blog/2013/12/nielsen-norman-group-show-your-pricing/)); güncel NN/g: kesin fiyat veya örnek fiyat/hesaplayıcı ([NN/g](https://www.nngroup.com/articles/b2b-vs-b2c/)) |
| Zorunlu üyelik sürprizi | Baymard: %19 terk, sitelerin %62'sinde misafir seçeneği belirgin değil ([Baymard](https://baymard.com/blog/checkout-flow-ux-optimization)) |
| Son adımda ek ücret | Terklerin %39'u ([Baymard](https://baymard.com/blog/checkout-flow-ux-optimization)) |
| Filtre listesini kaydırmaya zorlamak | Baymard: kullanıcılar uzun filtreyi tümden bırakıyor ([Baymard](https://baymard.com/blog/allow-search-for-long-filter-options-lists)) |
| Spec ağırlıklı ürünlerde hızlı bakış penceresi | Baymard: %21 site yapıyor, araştırma önermiyor ([Baymard](https://baymard.com/blog/ecommerce-product-lists-report-and-benchmark)) |
| Belirsiz "Yeni/2. el" etiketi | Kilitli işlemci, firmware uyumsuzluğu riskleri; "New" kelimesi satıcıya göre değişiyor ([NJT](https://njtautomation.com/guides/allen-bradley-condition-labels/)) |
| Çok sütunlu ödeme formu, etiketi alan içinde | Baymard form önerisi: tek sütun, etiket üstte ([özet](https://technologyadvice.com/blog/sales/checkout-optimization/), ikincil) |
| Süslü, ince, düşük kontrastlı tipografi; hover'a bağlı menü | WCAG/EAA; çıkarım |
| Aşırı animasyon, pop-up, sohbet balonunun içeriği örtmesi | McMaster'ın pop-up'sız, karusel'siz yaklaşımı (ikincil gözlem) |

---

## 6. Tasarım yönü

### 6.1 Üç alternatif
- **A. "Katalog" (McMaster esinli):** Ağır tablo, minimum görsel, tek renk vurgu. Artı: hız, otorite. Eksi: duygusuz, yönetim sunumunda "eski" görünebilir, 2. el güveni zayıf.
- **B. "Atölye" (önerilen):** Marka yeşil/kiremit, nötr sıcak zemin, yoğun tablo + net rozet sistemi + güven şeridi. Sistem sans, mono parça no. Artı: markaya bağ, modern ama ciddi, B2B+B2C ikisini taşır.
- **C. "Vitrin" (Robotistan/B2C esinli):** Büyük kart, bol görsel, kampanya bantları. Artı: ilk bakışta cazip. Eksi: parça no/teknik karşılaştırmada zayıf; Baymard B2B tablo bulgusuna ters.

**Öneri: B.** Gerekçe: ana kullanıcı bakım mühendisi/satın almacı (parça no, stok, teslim, KDV hariç fiyat), ama 2. el robotta güven ve görsel ikna da gerekiyor; B bu iki ihtiyacı tablo + rozet + güven şeridi ile birleştirir. A'dan sadelik, C'den ana sayfa vitrini ödünç alınır.

### 6.2 Ekran taslakları (ASCII)

**Ana sayfa**
```
[logo] [ Parça no, üretici kodu veya ürün adı ............ ][Ara] ☎ Hesap Sepet(0) [KDV hariç|dahil]
Robotlar · PLC · Sürücü/Servo · HMI · Yedek parça · 2. El · Teklif İste
---------------------------------------------------------------------------
| Parça numaranız var mı? [ .......................... ][Bul]  veya  [Liste yükle (CSV)] |
---------------------------------------------------------------------------
Kategoriler (8 kutu, ikon + ürün sayısı)     |  Durum: Yeni · Revizyonlu · 2. El (Test edildi)
---------------------------------------------------------------------------
Stoktaki öne çıkanlar (yoğun kart 4-6, fiyat KDV hariç, stok, durum rozeti)
---------------------------------------------------------------------------
Güven şeridi: Test edilmiş · Garanti · İade · İhracat · Teknik destek
Markalar (metin/logo sırası) · Teklif İste CTA bandı · Altbilgi
```

**Ürün listesi**
```
Ana sayfa > PLC > Siemens S7-1500        142 sonuç   Sırala: [Fiyat ↑ ▾]  Görünüm: [Tablo|Kart]
Filtreler (çipler: Stokta ×  Siemens ×)  | Görsel | Parça no     | Tanım       | Durum | Stok/Teslim | Fiyat KDV hariç | [Ekle]
 Durum  ☐ Yeni ☐ 2.El            [img]   6ES7 ...  CPU 1515-2 PN  [2.El test]  Stokta 2   12.400 TL       [Sepete]
 Stok   ☐ Stokta                  [img]   ...        ...           [Yeni]       7-10 gün   Teklif iste     [Teklif]
 Marka (aramalı) · Seri · Voltaj  ☐ Karşılaştır (maks 4)                          < 1 2 3 >
Mobil: "Filtrele(3)" düğmesi → tam ekran çekmece; kompakt liste
```

**Ürün sayfası**
```
Ana sayfa > ... > 6ES7 515-2AM01-0AB0
[galeri: ürün + seri no plakası]   | Siemens CPU 1515-2 PN             [2. El · Test edildi 12.10.2026]
                                   | Parça no: 6ES7 ... (kopyala)  Üretici kodu: ...
                                   | 12.400 TL  KDV hariç   (14.880 TL KDV dahil)
                                   | Stokta 2 adet · Yarın kargo     Toplam tahmin: kargo+KDV
                                   | Adet [1]  [Sepete ekle]  [Teklif iste]   Garanti 12 ay · İade
Sekmeler/bölümler (details): Teknik özellikler (gruplu tablo) · Test raporu · Uyumluluk · Belgeler (PDF) · Teslimat/İade
Benzer ürünler / aynı seri
```

**Sepet**
```
1 Sepet → 2 Bilgiler → 3 Teslimat/Ödeme → 4 Onay
Satır tablosu: ürün · adet [±] · birim fiyat (KDV hariç) · toplam · Kaldır
Özet: Ara toplam · Kargo · KDV · Toplam         [Ödemeye geç]   [Teklife dönüştür]
Parça no ile hızlı ekle [ ........ ] [Ekle]     Kupon (kapalı bölüm)
```

**Ödeme**
```
Adım 2/4  Bilgiler (tek sütun)           | Sipariş özeti (sabit sağ panel)
 (•) Misafir olarak devam  ( ) Giriş yap |  kalemler, kargo, KDV, toplam
 Ad, e-posta, telefon                    |  Güven: Garanti · İade
 Adres (otomatik doldur)                 |
 [ ] Kurumsal fatura: vergi dairesi/no   |
Adım 3: Teslimat (süre, ücret) + Ödeme: Kart · Havale · Cari hesap · Teklif
Satır içi hata + üstte özet; hesap oluşturma siparişten sonra
```

**Yönetim (satıcı paneli)**
```
Sol: Siparişler · Teklifler (RFQ) · Ürünler · Stok · Müşteriler · İçerik
Üst: Arama (sipariş no / parça no / müşteri)         Bugün: 12 yeni sipariş · 5 açık teklif
Teklifler tablosu: No · Müşteri · Parça · Adet · Durum [Yeni/Hazırlanıyor/Gönderildi] · Süre · [Yanıtla]
Ürün düzenleme: Parça no, üretici, durum (Yeni/Revizyonlu/2.El), test tarihi, seri no, firmware,
  spec alanları (standart etiketler), KDV hariç fiyat, stok, teslim süresi, fotoğraflar, PDF'ler
```

---

## 7. Kaynaklar

Birincil/doğrudan okunan:
- https://baymard.com/blog/allow-search-for-long-filter-options-lists (Nisan 2024)
- https://baymard.com/blog/use-product-tables-for-desktop-product-listings
- https://baymard.com/blog/ecommerce-product-lists-report-and-benchmark
- https://baymard.com/blog/current-state-ecommerce-product-page-ux (2026)
- https://baymard.com/blog/checkout-flow-ux-optimization
- https://baymard.com/research-articles/homepage-carousel
- https://baymard.com/blog/provide-comparison-features, https://baymard.com/blog/spec-sheet-scannability, https://baymard.com/research/product-page (yalnızca arama özeti; tam metin ücretli)
- https://www.nngroup.com/articles/b2b-vs-b2c/
- https://www.nngroup.com/articles/designing-effective-carousels/ (2013, 2026'da gözden geçirilmiş)
- Referans siteler (doğrudan gözlem, kısmi): https://www.mcmaster.com, https://uk.rs-online.com, https://www.digikey.com, https://www.surplusrecord.com, https://www.direnc.net, https://www.robotistan.com

İkincil (ajans/satıcı/hukuk büroları):
- https://dev.to/medusajs/9-ux-best-practices-for-ecommerce-1oao, https://iacollaborative.com/work/mcmaster-carr
- https://1digitalagency.com/blog/b2b-ecommerce-seo-for-industrial-distributors/
- https://www.optimizely.com/insights/blog/improving-b2b-ecommerce-search/
- https://www.growthspreeofficial.com/blogs/google-ads-b2b-manufacturing-industrial-buyer-search-2026
- https://technologyadvice.com/blog/sales/checkout-optimization/
- https://populiweb.com/blog/2013/12/nielsen-norman-group-show-your-pricing/
- https://njtautomation.com/guides/allen-bradley-condition-labels/, https://app.ubuyfirst.com/guides/allen-bradley-buying-guide, https://www.dosupply.com/buy/allen-bradley/810-A18A
- https://www.taylorwessing.com/en/insights-and-events/insights/2025/09/european-accessibility-act-requirements-for-e-commerce-services
- https://www.twobirds.com/en/insights/2025/a-guide-to-navigating-the-european-accessibility-act-for-online-retailers-service-providers-and-plat

**Doğrulanmadı / erişilemedi:**
- Reddit (r/userexperience, r/ecommerce, r/web_design, r/UXDesign, r/PLC, r/robotics): erişim engelli; hiçbir iddia kullanılmadı.
- YouTube: yalnızca başlıklar görüldü, içerik izlenmedi, iddia alınmadı. Örnek başlık: "B2B Websites That Convert: What Industrial Brands Get Wrong & How to Fix It" (https://www.youtube.com/watch?v=RdbllpsCP6M).
- Misumi, Automation24, Radwell, Robots.com/RobotWorx: 403; EU Automation: industrietec-automation.com'a yönlendirdi, incelenmedi. Mouser, Wiautomation, Eurobots, Hepsiburada/Trendyol incelenmedi.
- RS Components sayfasında arama kutusu, stok ve KDV anahtarı içerik dökümünde görünmedi (dinamik olabilir; yokluğu kanıtlamaz).
- NN/g'nin "B2B fiyat gizleme" bulgusunun birincil makalesi bulunamadı; yalnızca ikincil alıntı.
- Baymard'ın B2B çalışmasının tam kılavuzları ücretli.
- 2025-2026 genel UX trend yazıları ayrıca taranmadı; bu belge Baymard 2026 verisine dayanır.

---

## Ek: Reddit ve YouTube bulguları (2. tur)

### Erişim durumu (dürüst not)

Görev Reddit (en az 8 başlık) ve YouTube (en az 4 video) bulgusu istiyordu. **Bu hedef karşılanamadı.**

- **Reddit:** `reddit.com` ve `old.reddit.com` hem WebSearch (alan adı filtresi API tarafından reddedildi: "not accessible to our user agent") hem WebFetch (`.json` ve normal sayfa) tarafında engelli. `site:reddit.com` ve "reddit" anahtar sözcüklü 8 farklı sorguda tek bir Reddit başlığı dönmedi. Vekil/okuyucu servisleri talimat gereği denenmedi. **Reddit'ten doğrulanmış bulgu: 0.**
- **YouTube:** Video sayfaları WebFetch ile yalnızca başlık + site altlığı döndürdü (açıklama, bölüm, yorum yok). **Doğrulanmış video içerik bulgusu: 0.** Arama özetinde geçen tek video yorumu aşağıda "dolaylı" olarak işaretli.
- **Yerine konan kaynak:** Aynı kitlenin (mühendis, bakım, satın alma) konuştuğu açık forumlar: Hacker News (3 başlık, doğrudan okundu), EEVblog (1 başlık, doğrudan okundu), Siemens destek forumu, control.com, electrical-contractor.net (bu üçü yalnızca arama özetinden). Bunlar Reddit'in yerine **geçmez**; benzer nitelikli topluluk görüşü olarak açıkça etiketli kullanıldı. Kullanıcı adı yazılmadı; alıntılar özgün İngilizcesiyle.

### Bulgular

Kaynak türü: **[D]** sayfa doğrudan okundu · **[Ö]** yalnızca arama özeti, doğrulanmamış.

| # | Kaynak (başlık, tarih, URL) | Alıntı / özet | Mockup etkisi (ekran) |
|---|---|---|---|
| 1 | [D] HN: "Mcmaster.com is the best e-commerce site I've ever used", 25.09.2022. https://news.ycombinator.com/item?id=32976978 | "McMaster is generally not the cheapest, but they're almost always the fastest and the easiest." · "Their search is the best though, can write some half assed description of what I want" · "I also have yet to get an incorrect item." · "have it tomorrow and have a certificate telling me exactly what stuff is with a nice cad model." | **Ürün:** sevilme nedeni arayüzden çok güvenilirlik: doğru ürün, ertesi gün, sertifika/CAD/teknik föy. Ürün sayfasında belge (PDF, test raporu) bloğu öne alınmalı. **Liste/ana:** serbest metin aramada tolerans (boşluk, tire, kısmi). |
| 2 | [D] aynı başlık, aynı tarih | Aynı başlıkta eleştiri: "the website is an almost exact duplicate of it's print catalog and not all that user friendly for b2b buyers"; mobil site eleştirisi ve kargo ücretinin eskiden ödemeye kadar gizli kalması. | **Sepet/ödeme:** kargo ücreti en baştan görünür. **Mobil:** McMaster kopyası yetmez, kompakt liste şart. |
| 3 | [D] HN: "McMaster-Carr: A refreshingly fast, thoughtful, and well-organized website", 09.01.2023. https://news.ycombinator.com/item?id=34306793 | Övgü: "Blazing-fast search", "Table rows highlight on hover", "Unwavering commitment to grayscale images which make scanning easier", "Every product category and refinable search field has a useful description". Şikayet: "Everything is so tiny and I feel like I have to squint.", "McMaster broke middle-click opening of drill-down links in tabs", "Can't even estimate shipping & tax without creating an account." | **Liste:** satır hover vurgusu, tutarlı ürün görselleri, her filtre için tek satır açıklama. **Tipografi:** önceki 13-14 px tablo kararı alt sınır. **Tüm ekranlar:** gezinme gerçek `<a href>` olmalı (orta tık çalışsın; GET filtre mimarisi bunu sağlıyor). **Sepet:** hesap açmadan kargo+KDV tahmini. |
| 4 | [D] HN: "Ask HN: What are good high-information density UIs", 08-11.05.2025. https://news.ycombinator.com/item?id=43925732 | "professionals often want as much as possible accessible from a single screen" · "I think intuitiveness and density are orthogonal properties" · "Information density is not inherently a virtue." · McMaster için: "reduces an intrinsically dense catalog of parts to such a consistent and sensibly-structured interface". | **Tasarım yönü:** B ("Atölye") yoğunluğu desteklenir, ama değeri tutarlılıktan gelir: her yerde aynı satır düzeni, rozet, fiyat biçimi. "Yeni nesil" = yoğunluğu azaltmak değil, netlik ve tutarlılık. |
| 5 | [D] HN alt dalı, 08-09.05.2025. https://news.ycombinator.com/item?id=43926273 | Digi-Key/Mouser için: "The filter/apply pattern they use when trying to narrow things down is a lot quicker"; McMaster aralık seçimi "has always felt a little cumbersome"; "digikey has a better search than McMaster, but McMaster has a much better interface for filtering categories". Markasız genel listeleme "reduce the cognitive load of making decisions", pazarlama değil sert özelliklere göre seçenek sunuyor. | **Liste:** "çoklu seçim + Uygula" (form tabanlı filtre) doğrulanıyor. Sayısal aralıkta (voltaj, güç, kg) min/max alanı. Listede pazarlama metni yerine 2-4 sert özellik kolonu (önceki 3.3 ile uyumlu). |
| 6 | [D] EEVblog: "Digi-Key has changed and it is not very good", 10-11.10.2020. https://eevblog.com/forum/chat/digi-key-has-changed-and-it-is-not-very-good | "I have to click Show More EVERY SINGLE TIME I search for a part" · "the list boxes aren't list boxes as such anymore, so you can't navigate them by keyboard." · "bloated and slow AF with analytics and buggy Javascript" · "the long columns with "5mm, 5.02mm, 5.05mm, 5.07mm, 5.12mm" are just stupid to click to death on" · "sorting by quantity available is among the more useful features". | **Liste:** filtreler varsayılan açık (önemli 4-5 grup), "daha fazla" yalnızca ikincil gruplar için; benzer değerleri aralıkla grupla; stoka göre sıralama bağlantısı. Yerel form kontrolleri klavye erişimini korur (JS'siz yaklaşımın artısı). "These small "marketplace" vendors I've never heard of are surely a backdoor for counterfeit": **2. el rozetine** gerekçe, kaynağı belirsiz satıcı güveni öldürür. |
| 7 | [Ö] control.com: "Where do you buy discontinued PLCs and automation parts urgently?" (tarih alınamadı; sayfa 403). https://control.com/forums/threads/where-do-you-buy-discontinued-plcs-and-automation-parts-urgently.56040/ | Arama özetine göre: "Refurbished sold as new is very common on discontinued items."; yeni olmadığını ele verenler: tutarsız tarih kodu, kart kenarında lehim/akı kalıntısı; CPU'nun program/pil/lisansı olmadan işe yaramayabileceği; revizyon/firmware uyumsuzluğu; satıcıdan yazılı teyit önerisi. | **Ürün (2. el):** durum rozetinin yanında tarih kodu, revizyon/firmware, pil durumu, "program/lisans dahil mi" satırı ve seri no/etiket fotoğrafı. **Teklif/onay:** yazılı durum teyidi. Önceki 3.5 ve 3.7'yi genişletir. |
| 8 | [Ö] Siemens destek forumu, 15.10.2020 (sayfa okunmadı). https://support.industry.siemens.com/forum/cn/en/post/963958 | Arama özetine göre bir yanıt: fiyatlar Industry Mall'a giriş sonrası görünüyor, birçok şirket uzun giriş sürecini tamamlamamış; öneri yerel satış temsilcisine gitmek. | **Ana/liste/teklif:** kayıt duvarı arkasında fiyat alıcıyı kanal dışına iter. Fiyat veya tahmini aralık girişsiz görünsün; kayıt yalnızca cari hesap/teklif geçmişi için istensin. |
| 9 | [Ö] electrical-contractor.net forumu (tarih alınamadı). https://www.electrical-contractor.net/forums/ubbthreads.php/topics/201014.html | Arama özetine göre müşteriler teklifleri Grainger gibi katalog fiyatlarıyla kıyaslıyor. Tek anekdot, zayıf kanıt. | **Liste/ürün:** yayımlanmış fiyat pazarlıkta çıpa; "fiyat yok" rakip katalog fiyatına alan bırakır. |
| 10 | [Ö, dolaylı YouTube] "The fastest website ever?" videosu altı izleyici yorumu, arama özetinde aktarılmış. https://www.youtube.com/watch?v=fWfIf7Vfjec | Yorum (özet): McMaster'ın avantajı sitenin hızı değil, siparişin birkaç saatte kapıda olması. Anekdot, doğrulanmadı. | **Ürün/sepet:** teslim süresi ve kesim saati ("Bugün 16:00'a kadar → yarın kargo") fiyatla aynı hiyerarşide. HN #1 ile aynı sonuç. |

**Sayım:** Reddit 0, YouTube 0 (1 dolaylı yorum özeti), doğrudan okunan topluluk başlığı 4, arama özetinden gelen 5. İstenen "8 Reddit + 4 YouTube" hedefi karşılanmadı.

### Çapraz okuma

1. **McMaster sevgisinin kaynağı çoğunlukla operasyonel güven:** hız, doğru ürün, belge, CAD. Arayüz bunu bozmayan sade zemin. Bizde karşılığı: stok/teslim/belge/garanti bilgisini görsel süsten önce koymak (mevcut yönle uyumlu).
2. **Yoğunluk eleştirilmiyor; tutarsızlık, gizlenen filtre ve küçük yazı eleştiriliyor.**
3. **Kayıt/giriş duvarı tekrar eden sürtünme:** McMaster'da kargo/KDV tahmini, Siemens'te fiyat.
4. **2. el güveni = ayrıntı:** tarih kodu, revizyon, lisans/program, yazılı teyit; belirsiz "yeni" etiketi ve kaynağı belirsiz satıcı en büyük risk.

### Tasarım yönüne etkisi

**Yön değişmiyor: B ("Atölye") korunuyor.** Bulgular onu zayıflatmıyor; dört ayrıntı önceki belgeye eklenir:

- **Filtreler varsayılan açık**, "daha fazla" yalnızca ikincil gruplar için; sayısal özelliklerde min/max (#5, #6). Önceki 3.4'e ek.
- **Hesapsız kargo + KDV tahmini** sepette ve ürün sayfasında (#2, #3). Önceki 3.6 "maliyet şeffaflığı"nı somutlaştırır.
- **2. el kartına "tarih kodu / revizyon-firmware / program-lisans dahil mi / yazılı durum teyidi"** satırları (#7). Önceki 3.5 durum rozetini genişletir.
- **Tipografi alt sınırı:** tablo ve gövde 13 px altına inmesin ("çok küçük yazı" şikayeti McMaster'a bile yöneltilmiş, #3); tüm gezinme gerçek bağlantı olsun (orta tık).

Not: Kanıt tabanı 4 doğrudan okunan forum başlığı ve 5 arama özetinden ibaret. Reddit/YouTube erişimi sağlanırsa (ör. kullanıcı başlıkları kendi tarayıcısından aktarırsa) bu bölüm yeniden doğrulanmalı.
