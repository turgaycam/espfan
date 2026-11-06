# Ceylan Robot — site boşluk analizi (:3030 prototip ↔ ceylanrobot.com)

Tarih: 6 Kasım 2026  
Hazırlayan: ürün / UX analizi (kod değişikliği yok)  
İlgili: Turgay — “:3030 görsel olarak fazla sade; ceylanrobot.com daha iyi duruyor”

## English executive summary

The :3030 demo is a real B2B parts desk (part-number search, representative price with VAT, cart, fake checkout, quote, accounts) dressed in an intentional “workshop paper” theme: beige page, olive bar, Georgia headline, five icon tiles. ceylanrobot.com is a photography-led corporate site — navy and orange `#fa5f0b`, full-bleed robot film, services, about, repair workshop — whose public catalog does not show a price because the API amount is 0 EUR. The prototype feels basic because the first screen is a form, not a brand. Keep the shop’s transaction rules. Borrow the live brand surface, proof, and solution paths. Do not copy hidden prices, the carousel stack, the two different phone numbers, or the JavaScript-only page shell. This review did not open `http://192.168.5.30:3030/` live; the prototype side is the saved homepage, the UI pack, and DEVIR.md.

---

## Kaynak ve yöntem

| Taraf | Ne kullanıldı | Ne kullanılmadı |
|---|---|---|
| `:3030` prototip | Kayıtlı ana sayfa görüntüsü (`shop-3030.png`), kayıtlı ana sayfa HTML’i, `shop-ui-pack.zip` içindeki şablonlar (`app/web/sablonlar`), `site.css`, tasarım notu “Atölye” (13 Ekim 2026), satış sitesi tasarım spec’i (12 Ekim 2026), `DEVIR.md` | LAN adresi açılmadı. Liste, ürün, sepet ve ödeme ekranlarının canlı görüntüsü yok; o akışlar şablon ve spec ile anlatılır. |
| ceylanrobot.com | 6 Kasım 2026’da çekilen kabuk HTML, `robots.txt`, `sitemap.xml`, `GET /api/public/products` ve `/api/public/categories`, tema CSS’i; ekteki tam sayfa görüntüleri ve işlenmiş DOM (`www-full`, `www-products`, `www-category-1`, `www-about`, `www-dom-box.html`) | Canlı sitede sepet ve ödeme adımları tıklanarak gezilmedi. Ana sayfa kahramanı tarayıcıda oynatılmadı; slayt metni ekteki DOM ve görüntüden okundu. |

Katalog sayıları bugün örtüşüyor: kayıtlı prototip ana sayfası **4.451 ürün / 5 ana kategori**; public API aynı gün `total: 4451`. Ürün sayfasındaki fiyat alanı örneklerde `amount: 0`, `currency: EUR`.

Şablon paketi 13 Ekim tarihli. Kayıtlı ana sayfa HTML’i paketteki `ana.html` / `urun_karti` makrosundan ileride: logo dosyası, üstte “Teklif al”, karşılaştırma düğmesi ve kartın içinde uzun garanti metni var. Turgay’ın gördüğü ekran bu kayıtlı sayfadır. Paket, niyet belgesidir.

---

## 1. Özet yargı

`:3030` bitmemiş bir Bootstrap sayfası değildir. 13 Ekim “Atölye” notu bunu bilinçli seçmiş: bej zemin `#f4f1e9`, zeytin başlık `#303a32`, kiremit düğme `#a83c29`, Georgia yalnız ana başlıkta, karusel yok, gölge yok, kartta 1 px çizgi. Amaç parça numarasıyla arayan satış ekibine sakin bir tezgâh vermek. Bu tezgâh, şirketin yayındaki yüzüyle aynı marka değil.

ceylanrobot.com ilk bakışta **yetki** satıyor: turuncu robot fotoğrafı veya videosu tüm ekranı kaplıyor, başlık büyük ve beyaz, turuncu “Ürünleri Keşfet” tek eylem, altta hizmet, çözüm ailesi, tamir atölyesi, blog ve koyu iletişim şeridi var. Ürün ızgarası büyük fotoğraf, turuncu “Sepete Ekle” ve “Detay” ile vitrin gibi duruyor.

Prototip ilk bakışta **form** satıyor. Kayıtlı görüntüde kahraman, çerçeveli beyaz bir kart: serif başlık “Test edilmiş robot ve otomasyon parçaları”, ince kırmızı çizgi, ikinci arama kutusu, sağda “4.451 ürün / 5 ana kategori”. Altında beş beyaz kutu ve çizgi ikon. Fotoğraf, video, tesis, referans marka ve adres bu katmanda yok. Üst bant “DEMO – gerçek satış ve ödeme yapılmaz” yazdığı için ekran iç araç gibi okunuyor. Bu bant demo için doğru; görsel sadelikle birleşince “henüz tasarlanmamış” hissini büyütüyor.

Kısa yargı: prototip işlem olarak canlı siteden önde, sahne olarak geride. İyileştirme, tezgâhı atmak değil. Aynı arama, fiyat ve teklif kurallarını canlı markanın lacivert–turuncu yüzeyine ve kısa kurumsal kanıta oturtmak.

---

## 2. Görsel / marka karşılaştırması

### Renk ve başlık

| | Prototip (kayıtlı sayfa + `site.css`) | Canlı site |
|---|---|---|
| Zemin | Sıcak bej sayfa, beyaz kart, 1 px `#c9c4b4` çerçeve | Fotoğrafın üstüne binen açık başlık; iç sayfalarda koyu lacivert blok. Tema CSS’inde tekrar eden lacivertler `#02111e`, `#071320`, `#020e1d` |
| Eylem rengi | Kiremit `#a83c29` (arama düğmesi, teklif bandı) | Turuncu `#fa5f0b` (`style.css` içinde yüzlerce kez; düğme, bağlantı, vurgu) |
| Logo | Kayıtlı sayfada gerçek logo dosyası, siyah yuvarlatılmış kutuda. Paketteki `taban.html` hâlâ düz metin “CEYLAN ROBOT” | Aynı oranlı logo (`width="1294" height="233"`), başlığın içinde, siyah kutu yok |
| Yazı | Gövde sistem fontu; ana başlık Georgia, 36 px, kalın değil | Paket CSS’i Roboto ve Poppins yüklüyor. İşlenmiş kahraman başlığı 3.5 rem, ağırlık 800, beyaz gradyan |
| Hareket | Tasarım notu: 120–160 ms, karusel yok | Kahraman slaytı, oklar, noktalar, kategori kaydırması, referans logosu şeridi, odometer sayaç |

Logo dosyasının içindeki turuncu, prototip kromuyla çatışıyor. Ziyaretçi logodaki turuncuyu, sayfadaki kiremit ve zeytinle aynı sistem sanmıyor.

### İlk ekran

Kayıtlı prototip görüntüsü tek, sabit bir metin kartı. İki sayı var; ikisi de katalog sayımı. Tesis, teslimat vaadi veya müşteri işi görünmüyor.

Canlı ana sayfa bir slayt. Ekler aynı anda iki metin gösteriyor; ikisini de “bugün ilk slayt budur” diye kilitlemiyorum, çünkü LAN dışı sayfa tarayıcıda oynatılmadı:

- Kayıtlı görüntü: “İşletmenize Özel Mühendislik ve Otomasyon Çözümleri” ve “Ürünleri Keşfet”.
- Kayıtlı DOM’daki aktif kahraman: “Türkiye’nin En Büyük İkinci El Robot Stoğu ile Anında Teslim”; alt metin KUKA, ABB ve Yaskawa stoğu. Düğme yine “Ürünleri Keşfet”.

İkisi de aynı desenin parçası: tam ekran sanayi görüntüsü, tek cümle, tek turuncu düğme. Prototipte bu desen yok. Arama ise prototipte daha doğru yerde: kahramanın içindeki kutu “Parça no veya ürün adı” diyor. Canlı arama yer tutucusu “Aradığınız ürünü yazın...”; parça numarası vaadi başlıkta değil, kutunun içinde de yok.

### Kart ve kategori

Canlı ürün sayfası (`www-products.png`): solda filtre kartı, sağda büyük görsel, yürek ikonu, turuncu kategori etiketi (MOTORLAR, YEDEK PARÇALAR, KABLOLAR), ad, üretici kodu, stok kodu, turuncu “Sepete Ekle”, çerçeveli “Detay”. Kartta fiyat yok. Görseller karışık: vidalı mil ve şaft gibi gerçek parça fotoğrafı ile, beyaz zemine basılmış Ceylan logosu yan yana.

Prototip ana sayfasının görünen katı beş ikon kutusu (Elektrik 2202, Endüstriyel Robotlar 69, Mekanik 1931, Robot Kontrol Üniteleri 11, Robotik Parçaları 238). İkonlar `yer-tutucu/*.svg` çizimleri. “Stoktaki öne çıkanlar” görüntüde yeni başlıyor; kart gövdesi görüntüde yok. Kayıtlı HTML’de her kart şunları taşıyor: parça no, stok kodu, uzun ad, KDV dahil tutar, “Temsili fiyat”, KDV hariç satırı, “Stokta”, “Kargoya veriliş: 1–2 iş günü · varış: 10–12 Kasım (temsili)”, iki üç satır garanti ve cayma metni, “Karşılaştır”. “Sepete ekle” bu kartta yok. Paketteki `urun_karti` makrosu çok daha kısa: görsel, kod, ad, fiyat, stok. Yayındaki sayfa makrodan şişmiş.

Sonuç: katlamanın üstü boş ve düz, katlamanın altı hukuk metni. Canlı kart ise fotoğraf ve tek eylem. İkisi de aşırı; hedef ikisinin ortası.

### Güven ve alt bilgi

Prototipte güven şeridi var ama yasal sayfalara giden beş kısa madde (test, garanti, iade, ihracat, teknik destek) ve altta yalnız yasal bağlantı listesi. Kayıtlı sayfada mesai satırı var: “Hafta içi 08:30–18:00”. Adres, e-posta ve sosyal hesap yok.

Canlı alt bilgi dört kolon: kısa firma cümlesi ve sosyal ikonlar, hizmetler, faydalı linkler, iletişim. Görüntü ve DOM aynı adresi yazıyor: Konya OSB, Büyükkayacık OSB, 3. Sk. No: 7, 42250 Selçuklu/Konya. E-posta `info@ceylanrobot.com`. Sağ altta WhatsApp balonu (`wa.me` DOM’da var). Referans şeridinde Bosch Rexroth, Siemens, ABB, FANUC, KUKA, Yaskawa logoları dönüyor.

Telefon tutarlı değil; bunu kopyalamayın. Prototip üst bant ve JSON-LD tek numara kullanıyor: +90 (332) 239 15 75. Canlı DOM’da JSON-LD `+90-332-239-15-75`, alt bilgi ve kategori görüntüsü `+90 539 518 97 71`. İki hat varsa rolü yazılmalı (santral / satış); tek satırda ikisi birden durmamalı.

---

## 3. Bilgi mimarisi ve içerik

### İki farklı ağaç

Canlı üst menü çözüm ve kurum satıyor: Robotik Otomasyon, Ürünler, Kurumsal, İletişim. Ayrı URL’ler sitemap ve DOM’da duruyor: `/`, `/products`, `/category`, `/category/1`…`/8`, `/service`, `/service/1`…`/6`, `/about`, `/contact`, `/blog`, `/cart`, `/login`. Sitemap ayrıca `/team`, `/references`, `/faq` listeliyor; bu üçü görüntülenmedi.

Çözüm ailesi, ERP ağacı değil. DOM başlıkları: İşleme, Kaynak, Paketleme ve Paletleme, Taşıma, CNC ve Pres Besleme, Montaj, Boyama, Müşteriye Özel Sistemler. Kategori görüntüsü (`/category/1` başlığı “İşleme Robotları”) ürün ızgarası değil: solda YouTube tanıtım filmi, sağda uzun metin ve madde işaretleri, altta “Projeniz İçin Teklif Almaya Hazır mısınız?”. Bu, parça arayan ile hat kurmak isteyeni ayıran bir katman.

Prototip menüsü beş ERP kökü ve “Tüm ürünler”. Arama `/tr/ara`, teklif `/tr/teklif`, hesap, sepet, yasal sayfalar. Hakkımızda, hizmet, blog, iletişim sayfası, çözüm inişi yok. `DEVIR.md` rota listesi de bunu doğruluyor: katalog, hesap, sepet/ödeme, teklif, yasal, yönetim, karşılaştırma.

Public API 6 Kasım’da **501 aktif kategori**, seviye dağılımı 9 / 50 / 252 / 190. Seviye 0 adları: Elektrik ve Elektronik, Endüstriyel Robotlar, Mekanik, Pozisyonerler, Robot Kontrol Üniteleri, Robotik Parçaları, Slider, ABB REDÜKTÖR, GÜÇ KAYNAĞI. Prototip şeridi beş kök gösteriyor ve bu beşin adetleri 4.451’e tamamlanıyor. Pozisyonerler ve Slider ana şeritte yok. Canlı ana sayfa ayrıca seviye 1 adlarını vitrinliyor (şartlandırıcı, valf, pnömatik, sensör, güç, kontrol, motor, görüntü işleme, kablo). Ziyaretçi 501 düğümlü ağacı değil, yirmi kadar tanıdık başlığı görüyor.

### Kurumsal metin

Hakkımızda görüntüsü dolu bir şirket sayfası: “Robot Teknolojilerinin Sadece Tedarikçisi Değil, Teknik Otoritesiyiz!”, Mustafa Ceylan Endüstri A.Ş., 1974, Konya OSB’de 65.000 m² alan ve 20.000 m² kapalı alan, Robot Teknolojileri ve Yenileme Merkezi, KUKA / ABB / FANUC / YASKAWA, “Güçlü Tedarikçi” ve “Mühendislik Partneri”, misyon ve vizyon. Sol menüde Kalite Politikası ve Değerler de var; o iki panel görüntünün dışında, metinleri bu rapora yazılmadı.

DOM’da ayrı bir tamir bloğu var: “Elektronik Kart Tamir Atölyesi”, KUKA sürücü ve pendant, “%70 Maliyet Tasarrufu”. Bu iddia prototipte hiç yok. Satış vaadi olarak kullanılacaksa hukuk ve satış onayından geçmeli; analiz onu doğru kabul etmiyor, sadece yayında durduğunu kaydediyor.

Blog başlıkları DOM’da dört adet (S7-1200/1500, endüstriyel robot yazısı, üniversite-sanayi, savunma sanayii tedarikçi buluşması). Prototipte içerik yok.

Hizmet listesi alt bilgide: yenilenmiş robot satışı, robotik otomasyon, elektronik kart tamir ve satış, endüstriyel yedek parça, teknik servis, eğitim ve danışmanlık. Prototipin güven şeridi bunların ancak bir kısmını (test, garanti, ihracat, destek) yasal sayfaya linkleyerek söylüyor.

### Eksik olan prototip içeriği, fazla olan prototip içeriği

Eksik: tesis, marka hikâyesi, çözüm aileleri, tamir atölyesi, tek adres, tek e-posta, sosyal kanıt.

Fazla, yanlış yerde: ana sayfa kartında cayma hakkı, “olduğu gibi satılır” ve tarihli teslim cümlesi. Bunlar ürün sayfasına ait. Kayıtlı kartlarda garanti cümleleri ürünler arasında değişiyor (üretici garantisi / test edilmiş / olduğu gibi). Ayrım doğru bir B2B kuralı; vitrin kartının gövdesi değil.

Yasal sayfalar prototipte var, canlı sitede bu incelemenin gördüğü sayfalarda yok. `hukuk-notlari.md` taslak olduklarını ve künye boşluklarını (MERSİS, sicil, vergi, KEP) yazıyor. Yayına hazır içerik değiller. Canlı hakkımızda metnini olduğu gibi taşımak da hukuki inceleme yerine geçmez.

---

## 4. E-ticaret ve B2B akış

İki sitenin işi aynı değil. Canlı site ajans vitrini (spec’in deyişiyle Anssoft/MXEN, React/Vite). Prototip, Netsis’ten okunan katalogla yurt içi ve yurt dışı sipariş ile teklifi deneyen iç ağ demosu. Demo bandı, sahte kart ve `noindex` bu yüzden duruyor. Görsel eleştiri bu sınırı silmemeli.

### Prototipte olup canlı vitrinde görünmeyenler

Kanıt şablon, spec ve `DEVIR.md`. Ana sayfa HTML’i bunları göstermez.

- Parça numarası, SKU ve üretici kodunda sunucu tarafı arama (FTS5). Ülke seçici dilden ayrı: TR ziyaretçi TRY ve KDV dahil görür; teslimat yurt dışıysa ihracat satırı.
- Fiyat. API tutarı 0 olduğu için spec temsili bant ve “Temsili fiyat” rozeti şart koşmuş. Kayıtlı kartlarda rozet duruyor (örnek: 30.308,80 ₺ KDV dahil, yanında KDV hariç). Canlı ürün görüntüsünde fiyat satırı yok. 20 ürünlük API örneğinin 20’sinde de `price.amount` 0. Canlı “Sepete Ekle”, fiyatı olmayan bir katalog düğmesi. Prototipin fiyatı göstermesi bir boşluk değil; rozetin küçük kalması bir risk.
- 15.000 € üstü ve robot köklerinde sepet yerine teklif. Ana sayfada “Robotlar için teklif alın” bandı var. Teklif formu şablonda misafire açık: ad, firma, e-posta, telefon, ülke, adet, mesaj; ürün seçiliyse özet kartı.
- Sepet, üyelik (bireysel / kurumsal / yurt dışı), adres, sahte kart ve sahte 3D, havale süresi, sipariş durumu, hesabım, karşılaştırma, geri bildirim, yönetim panosu. Ödeme gerçek değil; sipariş numarası spec’te `CR-DEMO-…`.
- Liste şablonu masaüstünde yoğun tablo: 48 px görsel, mono parça no, durum, stok, fiyat, sepete veya teklif. Filtre: stokta, fiyat aralığı, sıralama ad / fiyat. Uygulanan filtreler çip.
- Ürün şablonu karar sırasını yazıyor: ad, kopyalanabilir parça no, fiyat, stok, adet, sepete veya teklif, kargo satırı (TR 15 € + KDV temsili; yurt dışı navlun teklifle), 2. elde “durum bilgisi”.

### Canlı sitede olup prototipte olmayanlar

- Çözüm sayfasından teklife giden anlatı (video, madde, “Bize Ulaşın”). Prototip teklifi form olarak açıyor, hikâye olarak değil.
- Ürün ızgarasında büyük fotoğraf, yürek, kategori etiketi, “Detay”, ızgara/liste anahtarı, “Ada göre” sıralama, “4451 ürün bulundu”.
- Filtre alanları: ürün adı, üretici kodu, stok kodu, kategori açılır listesi. Prototip bunları ayrı kutu yapmıyor; arama kutusu aynı alanlara bakacak şekilde spec’te tanımlı. Keşif yine de zayıf, çünkü filtre etiketleri canlıdaki kadar görünür değil.
- WhatsApp, çok dilli menü (TR / EN / AR). Prototip TR ve EN yol öneki (`/tr/`, `/en/`) ve 12 ülke seçicisi kullanıyor. Arapça yok.
- Kurumsal güven: tesis ölçüleri, marka listesi, tamir, blog. Bunlar dönüşüm içeriği; sepet kuralı değil.

### Sepete ekle farkı

Canlı kart fiyat göstermeden sepete atıyor. Prototip ana sayfa kartı fiyat gösterip sepete atmıyor; karşılaştırıyor ve detaya link veriyor. Liste şablonunda sepete ekle var. İlk ekranda eylem, canlı sitede daha net.

Stok: API örneğinde 20 üründen 19’unun stoğu 0’dan büyük; ilki 0. Prototip “öne çıkanlar” hepsi “Stokta”. Spec, stoğu 0 olanı da sepete bırakıp “tedarik teyit” diyor. Bu kural korunmalı. Canlı kart görüntüsünde stok adedi yok.

### Bilinçli olarak kopyalanmayacaklar

- Sıfır fiyatı gizlemek. Tezgâhın işi fiyat ve teklif eşiğini göstermek. Rozet “Temsili fiyat” kartta tutarın yanında küçük bir hap; 87.281,22 ₺ gibi rakamlar gerçek liste fiyatı gibi okunuyor. Düzeltme fiyatı silmek değil, temsili olduğunu fiyatın üstünde bir cümle yapmak.
- Canlı sitedeki iki telefonu yan yana taşımak.
- “%70 tasarruf” ve “Türkiye’nin en büyük stok” cümlelerini kanıtsız taşımak.
- Karusel, otomatik sayaç, jQuery + Owl + React yığınını “daha zengin görünsün” diye eklemek. Atölye notu bunu kapsam dışı yazmış; ilk ekran fotoğrafı için karusel gerekmez.
- Demo bandını kaldırmak. İç ağda sahte tahsilat durduğu sürece bant kalır (`DEVIR.md` riski).

---

## 5. Teknik ve SEO gözlemleri

Lighthouse veya benzeri skor üretilmedi. Aşağıdakiler kaynak kod, başlık ve HTTP yanıtından.

### Prototip

Kayıtlı ana sayfa sunucunun bastığı HTML. Gövde boş değil; ürün adları, fiyat ve kategori kaynakta duruyor. `robots` meta `noindex,nofollow`. Canonical `http://192.168.5.30:3030/tr/`. hreflang `/tr/` ve `/en/` yol önekli. JSON-LD Organization ve WebSite var; Organization logosu `/statik/marka/ceylan-robot-logo.png`, telefon +90 (332) 239 15 75, SearchAction `/tr/ara?q=`. Başlık ve description parça aramasını anlatıyor. Atla bağlantısı var. CSS tek dosya (`site.css`, pakette yaklaşık 72 KB), JS tek dosya (yaklaşık 10 KB), CDN yok. Bu, spec’in kararı.

Bunlar demo için doğru, halka açık site için yanlış adres. Spec SEO’yu ve internete açılmayı bu aşamanın dışında bırakmış. `uretim` modu indeks açar; `DEVIR.md` künye boşken bunu yasaklıyor. Skor hedefi yok: önce host, TLS ve hukuk.

Kategori URL’si sayısal (`/tr/kategori/197`). İnsan okurluğu ve ilerideki indeks için zayıf. Ürün URL’si `/tr/urun/1`.

### Canlı site

`https://www.ceylanrobot.com/` ve `https://ceylanrobot.com/` ikisi de HTTP 200. Biri diğerine 301 ile inmıyor. İşlenmiş DOM canonical’ı apekse koyuyor: `https://ceylanrobot.com/`. www ve apeks aynı içeriği iki hostta sunuyor.

İlk HTML bir kabuk: `<div id="root"></div>`, noscript “You need to enable JavaScript to run this app.” Kabuk başlığı “Ceylan Robot”, description genel cümle, `og:image` `/favicon.ico`. İşlenmiş DOM başlığı uzuyor (“…/İkinci El Robot | Ceylan Robot”) ve ikinci bir description basıyor; JSON-LD logo hâlâ `favicon.ico`, `sameAs` boş. Helmet (`data-rh`) JS sonrası çalışıyor. JS çalıştırmayan bir okuyucu vitrini görmez.

hreflang `?lang=tr|en|ar`. Yol öneki değil. Sitemap 12 adres: ana sayfa, about, products, service, blog, contact, team, references, faq, category. Ürün URL’si yok. 4.451 ürün ve 501 kategori indekse bu dosyadan bağlı değil.

`robots.txt` Cloudflare content signal: `search=yes`, `ai-train=no`, genel `Allow: /`. Demo’daki gibi siteyi kapatmıyor.

Yük: Bootstrap, Boxicons, jQuery, Owl Carousel, odometer, Magnific Popup, meanmenu, `dark.css`, bir de Vite paketi (`index-*.js` / `index-*.css`). Google Fonts (Roboto, Poppins) ve flagcdn. Prototip bu yığının yanında sade; sadelik burada performans lehine. Sayaç etiketleri DOM’da “Endüstriyel Tecrübe, Başarılı Proje, Robot Stoğu, Yedek Parça Stoğu”; rakam düğümleri statik kopyada `0+`. Odometer doldurmadan sayı okunmuyor. Bu rapor o rakamları yazmaz.

API örneği (20 ürün): hepsinde bir görsel yolu var, hiçbirinde `descriptionSections` veya `techSpecs` yok, hepsinde fiyat 0. Spec’in 12 Ekim tespiti (boş açıklama, boş teknik, sıfır fiyat) 6 Kasım örneğinde duruyor. Canlı karttaki logo görseli ile “görsel yolu dolu” çelişmiyor: yol, marka yerleştirmesine de gidebilir. Asıl boşluk metin ve fiyat verisi.

Güvenlik başlıkları canlı yanıtta görüldü: HSTS, `nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy`. Prototip spec’i `DENY` ve sıkı bir CSP yazıyor; kayıtlı HTML başlıklarını taşımıyor, doğrulanmadı.

---

## 6. Öncelikli backlog

Çaba: **S** bir iki günlük arayüz işi, **M** birkaç şablon ve içerik turu, **L** yeni bilgi yapısı veya veri işi. P0, Turgay’ın “basit duruyor” cümlesini ve güven riskini hedefler. Demo bandı, sahte ödeme ve `noindex` P0 ile kalkmaz.

| Öncelik | Boşluk | Neden | Somut iş | Çaba |
|---|---|---|---|---|
| P0 | Ana sayfa marka yüzeyi canlı siteyle aynı ailede değil | Bej kart, Georgia, zeytin bant ve kiremit düğme; yayındaki lacivert–turuncu ve fotoğraf yok. Logo turuncusu sayfada karşılıksız | `site.css` tokenları: sayfa beyaz, başlık bandı `#02111e`, birincil eylem `#fa5f0b`. Kahraman tam genişlik, tek sanayi fotoğrafı, beyaz başlık, arama kutusu bandın içinde kalsın. Karusel eklenmez | S |
| P0 | Ana sayfa kartı hukuk metni; sepete ekle yok | Kayıtlı HTML’de her kartta garanti, cayma ve “10–12 Kasım” var. Paket makrosu kısa. Canlı kart tek eylem gösteriyor | Kartı makroya döndür: görsel, parça no, ad, fiyat, stok, turuncu “Sepete ekle” veya “Teklif iste”. Tarihli teslim cümlesini karttan çıkar. Garanti ürün sayfasında kalsın | S |
| P0 | Temsili fiyat gerçek raf fiyatı gibi duruyor | API tutarı 0. Rozet tutarın yanında küçük. 30–87 bin ₺ vitrinde bağlayıcı okunur | Fiyatın üstüne tek satır: “Gösterilen tutar temsili banttır, sipariş öncesi teyit edilir.” Rozet kalsın. Fiyatı canlı site gibi silmeyin | S |
| P0 | Alt bilgi yalnız yasal liste | Adres, e-posta ve tesis yok. Canlı alt bilgi şirketi yerleştiriyor. Telefonda iki numara var | Dört kolon: katalog, hizmet, iletişim, yasal. İletişimde tek doğrulanmış telefon, `info@ceylanrobot.com`, OSB adresi, mevcut mesai. İkinci hat rolü yazılmadan eklenmez | S |
| P1 | Çözüm katmanı yok | Canlı menü hat tipiyle (kaynak, işleme, besleme) konuşuyor. Prototip beş ERP kökü gösteriyor. API’de 9 seviye-0 ve 501 düğüm var | Ana sayfaya sekiz statik çözüm kartı. Her kart ilgili köke veya hazır bir arama sorgusuna gitsin. Pozisyonerler ve Slider, ürünü varsa şeride eklensin. 501’lik menü bu turda açılmasın | M |
| P1 | Kurumsal ve tamir hikâyesi yok | Hakkımızda görüntüsü tesis, marka ve iki kimlik anlatıyor. Tamir bloğu ayrı bir teklif kapısı | `/tr/kurumsal` : görüntüdeki hakkımızda metninin kısaltılmış, satışın onayladığı hâli. Ayrı kısa “Kart tamir” sayfası; “%70” ancak belge varsa | M |
| P1 | Ürün listesi iç tablo gibi tasarlanmış | Şablon 48 px görsel ve sütun. Canlı ızgara büyük fotoğraf. Liste ekranının görüntüsü bu incelemede yok; hükmü şablon veriyor | Masaüstünde varsayılanı mevcut `urun_karti` ızgarası yapın. Tablo ikinci görünüm kalsın. Filtreye üretici kodu ve stok kodu kutusu ekleyin; FTS zaten arıyor | M |
| P1 | Kategori inişi yok | `/category/1` film ve madde ile anlatıyor, sonra teklif istiyor. Prototip kategori şablonu doğrudan liste | Beş kök için şablonun üstüne tek görsel, üç cümle, bir teklif düğmesi. Video ancak şirket kanalındaki mevcut film gömülürse | M |
| P1 | Katalog metni boş | 20 ürünlük örnekte açıklama ve teknik föy yok. Her iki sitede kart görseli zaman zaman logo | Eşitleme metni uydurmasın. Öne çıkan 30 SKU için gerçek fotoğraf ve üç satır teknik, elde seçilsin. Geri kalan yer tutucu, logo filigranı ile işaretlensin (“Temsili görsel” zaten şablonda gizli düğüm) | L |
| P2 | Canlı sitemap ve kabuk zayıf | Ürün URL’si sitemap’te yok, og görseli favicon, www ve apeks ikisi de 200, içerik JS sonrası | Demo yayına çıkmayacak. Çıkış kararı olursa: tek host 301, ürün ve kategori sitemap’i, og’da logo dosyası, slug’lı yol. Prototipin sunucu HTML’i bu konuda canlı kabuktan önde; SPA’ya dönülmez | L |
| P2 | Blog, ekip, SSS, referans, AR | Sitemap’te duruyor; prototipte yok. TR/EN satış senaryosu için şart değiller | Referans logoları statik bir satır olarak P0 footer’a girebilir. Blog ve AR ayrı içerik işi; bu görsel turda yok | L |
| P2 | Yasal künye boş | Hukuk notu MERSİS, KEP, VERBİS/ETBİS bekliyor | `uretim` moduna alınmaz. Taslak bandı kalır | L |

---

## 7. Hızlı kazançlar

Aşağıdaki sekiz iş birlikte yaklaşık bir iki günlük ön yüz işidir. Yeni sayfa sistemi, video prodüksiyonu ve hukuk onayı yoktur. Hepsi kayıtlı ana sayfa ile paketteki `taban.html`, `ana.html`, `_makrolar.html` ve `site.css` üzerindedir.

1. **Token değişimi.** Sayfa zemini `#ffffff`, üst bant ve kategori şeridi `#02111e`, birincil düğme `#fa5f0b`, metin koyu lacivert. Georgia ana başlıktan çıksın; gövde fontu kalsın. Bej “kâğıt form” hissi bu kadarlık bir değişiklikle kırılır.
2. **Kahramanı bant yapın.** Tek fotoğraf (canlı sitedeki mevcut robot karesi, kullanım hakkı şirket içinde netleştirilerek) tam genişlik, koyu perde, beyaz başlık. Mevcut cümle kalsın: “Test edilmiş robot ve otomasyon parçaları.” Alt satır canlı siteden bir cümle olabilir, slayt olmaz. Büyük arama kutusu ve 4.451 / 5 sayısı bandın içinde kalır.
3. **Kartı kısaltın ve sepete bağlayın.** Ana sayfa kartından garanti, iade ve tarihli teslim paragraflarını çıkarın. Liste şablonundaki sepete ekle formunu karta koyun. Teklif zorunlu üründe düğme “Teklif iste” olsun.
4. **Temsili fiyat cümlesi.** Öne çıkanlar başlığının altında bir satır: tutarlar temsili banttır. Rozet kartta da kalsın.
5. **Kategori kutusu.** Çizgi SVG’yi kutunun sol şeridi ve turuncu adet yapacak kadar büyütün. Kutunun tamamı tıklanır kalsın. Beş kök yetiyor; bu turda 501’i dökmeyin.
6. **Sekiz çözüm kısayolu.** Kaynak, işleme, CNC besleme, paletleme, montaj, boyama, taşıma, kart tamir. Statik kart, mevcut kategori veya `/tr/teklif` linki. Metin birer satır.
7. **Alt bilgi.** Adres, e-posta, mesai, doğrulanmış telefon, KUKA ABB FANUC Yaskawa Siemens satırı (dönen şerit değil, beş logo). Yasal linkler dördüncü kolonda kalsın. “CEYLAN ROBOT” düz metin logosu yerine header’daki logo dosyası.
8. **Sabit ara düğmesi.** Sağ altta telefon linki, demo bandıyla çelişmeyen kısa etiket: “Satış hattı”. WhatsApp ancak şirket hattı ve hazır mesaj metni belliyse. Yeşil balon tek başına marka işi sayılmasın.

Bu sekiz madde bitince ana sayfa hâlâ sade bir tezgâhtır; fotoğrafı, turuncusu, adresi ve net düğmesi olduğu için canlı sitenin akrabası gibi okunur. Hakkımızda sayfası, liste ızgarası ve öne çıkan 30 fotoğraf bir sonraki tura (P1) kalır.

---

## Ek: korunanlar

Bunlar boşluk değildir.

- DEMO bandı, sahte kart, Netsis’e yazmama, e-posta yok.
- Ülkeye göre KDV ve ihracat satırı, TCMB kur satırı, 15.000 € teklif eşiği.
- Parça numarasıyla arama ve mono kod.
- Sunucunun bastığı HTML, atla bağlantısı, `noindex` (iç ağdayken).
- TR/EN yol öneki. Canlı sitedeki `?lang=` bunu geçmez.
- Yasal taslakların durması. Onaysız metin yayına çıkmaz.
