# Tasarım yönü: "Atölye" (K22 — Görev 11–16'yı bağlar)

Kaynak: `docs/arastirma/2026-10-13-eticaret-ux-ui-arastirmasi.md` (Baymard, NN/g, sektör siteleri, forumlar). Yönetime sunulacak; hedef: **yeni nesil ama anlaşılır**. Plan metnindeki görsel değerlerle çelişirse **bu belge kazanır**; iş kuralları, rotalar, form alan adları, `data-e2e` seçicileri ve testler DEĞİŞMEZ.

## 1. Tokenlar (`site.css :root`) — plandaki eski tokenların yerine
```css
:root {
  --bg:#f4f1e9; --surface:#ffffff; --surface-2:#ebe7db;
  --ink:#1d231f; --ink-muted:#5b645d;
  --brand-900:#303a32; --brand-600:#4f5e48; --brand-500:#687860;
  --accent:#a83c29; --accent-700:#8f3222;
  --info:#267593; --info-700:#1d607c;
  --border:#c9c4b4; --border-strong:#7f857b;
  --ok:#2e6b3a; --ok-bg:#e3efe2; --warn:#7a4f00; --warn-bg:#fbefd0; --danger:#8f3222; --danger-bg:#f8e3de;
  --focus:#267593; --focus-on-dark:#f2b705;
  --font-ui: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-mono: ui-monospace, "Cascadia Mono", "SF Mono", Consolas, "Liberation Mono", monospace;
  --font-display: Georgia, "Times New Roman", serif;
  --r-sm:4px; --r-md:6px; --r-pill:999px;
  --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:24px; --s6:32px; --s7:48px;
  --shadow-pop: 0 4px 16px rgba(29,35,31,.12);
  --container:1280px;
}
```
Geriye uyum: plandaki eski token adları (`--yesil-koyu`, `--yesil`, `--kiremit`, `--mavi`, `--zemin`, `--gri`, `--cizgi`, `--yazi`) aynı dosyada yeni tokenlara takma ad olarak tanımlanır (`--yesil-koyu: var(--brand-900)` … `--yazi: var(--ink)`, `--yesil: var(--brand-600)`), böylece sonraki görevlerin CSS'i bozulmaz.

## 2. Kurallar
- **Tipografi:** Gövde ve başlıklar `--font-ui`. Georgia (`--font-display`) yalnız ana sayfanın büyük başlığında. SKU ve üretici kodu `--font-mono`. Fiyat, stok ve tablo rakamları `font-variant-numeric: tabular-nums`.
  - Ölçek: 13 / 14 / 16 / 18 / 22 / 28 / 36 px. Gövde 15 px, tablo 14 px; **13 px'in altına inilmez.** Satır yüksekliği 1,45.
- **Renk kullanımı:**
  - Metin ve bağlantıda `#687860` kullanılmaz; yerine `--brand-600` veya `--info-700`.
  - Birincil eylem (Sepete ekle, Ödemeye geç, Teklif iste) `--accent` dolgu + beyaz metin.
  - İkincil eylem: `--surface` zemin + `--border-strong` çerçeve.
  - Durum: renk + metin (ve varsa ikon) birlikte; tek başına renk kullanılmaz.
- **Odak:** Her etkileşimli öğede 2 px `--focus` halka (`outline-offset:2px`). Koyu bantta (`--brand-900`) `--focus-on-dark`.
- **Köşe ve gölge:** Input ve tablo 4 px, kart ve düğme 6 px, rozet pill. Gölge yalnız açılır panel/çekmece/dialog'da (`--shadow-pop`); kartlar 1 px `--border`.
- **Izgara:** Konteyner 1280 px, oluk 16–24 px. Kırılımlar 360 / 768 / 1024 / 1280. Mobilde 44 px dokunma hedefi.
- **Hareket:** Yalnız 120–160 ms renk/opaklık geçişi; `prefers-reduced-motion`'da kapalı. Karusel, pop-up ve otomatik dönen içerik yok.
- **İkonlar:** `app/web/statik/ikonlar.svg` sprite (24 px ızgara, 1,5 px çizgi, `currentColor`), kullanım `<svg class="ikon" aria-hidden="true"><use href="/statik/ikonlar.svg#ad"></use></svg>`. Gerekli set: arama, sepet, kullanici, telefon, kontrol, kalkan, kamyon, dunya, dosya, filtre, carpi, ok-sag, uyari, bilgi, kopyala. Görev 11 sprite'ı oluşturur.

## 3. Ekran desenleri (kapsam içi, mockup)
- **Başlık (Görev 11):**
  - Üstte koyu `--brand-900` ince bant: DEMO bandı + iletişim/telefon + dil ve ülke seçici.
  - Altında beyaz ana başlık: "CEYLAN ROBOT" sözcük markası (font-weight 700, harf aralığı .04em), **geniş arama kutusu** ("Parça no, üretici kodu veya ürün adı"), Hesap, Sepet (sayaç rozeti).
  - En altta kök kategoriler yatay gezinme şeridi (gerçek bağlantılar; mobilde yatay kaydırma).
- **Ana sayfa (Görev 12):**
  - Hero: Georgia büyük başlık ("Test edilmiş robot ve otomasyon parçaları") + büyük parça no arama formu. Karusel yok.
  - Kategori kutuları (ikon + ad + ürün sayısı).
  - "Stoktaki öne çıkanlar" yoğun kartlar.
  - **Güven şeridi:** Test edilmiş · Garanti · İade · İhracat · Teknik destek; ikon + kısa metin, yasal sayfalara bağlantı.
  - Altta "Robot mu arıyorsunuz? Teklif alın" CTA bandı.
- **Liste (Görev 12):**
  - Masaüstünde **yoğun tablo görünümü** varsayılan. Sütunlar: görsel küçük resim (48 px), parça no (mono) + ad, durum rozeti, stok/tedarik, fiyat (`tabular-nums`, KDV ibaresiyle), eylem (Sepete / Teklif iste).
  - 768 px altında aynı veri kart listesi olur (CSS ile, aynı HTML; `<table>` yerine rol uygun grid/`<ul>` kullanılabilir).
  - Filtreler masaüstünde solda **varsayılan açık**. Mobilde `<details>` ile "Filtrele" çekmecesi (JS'siz). Uygulanan filtreler çip olarak üstte gösterilir, her çipte kaldırma bağlantısı olur.
  - Sonuç sayısı ve sıralama listenin üstünde.
- **Ürün (Görev 12):**
  - İki sütun: solda görsel/yer tutucu, sağda karar bloğu.
  - Karar bloğu sırası: başlık (ad), parça no (mono) + **kopyala** düğmesi (site.js, JS yoksa düğme gizli), üretici kodu, durum rozeti, **fiyat bloğu** (ana fiyat büyük; KDV ibaresi; ikincil fiyat küçük; temsili rozeti), stok/tedarik satırı (ikonlu), adet + birincil eylem.
  - Altında **maliyet şeffaflığı** satırı: "Kargo: TR 15 € + KDV (temsili) · Yurt dışı: navlun teklifle" (giriş gerektirmez). Güven satırı: garanti · iade · ihracat (yasal sayfalara bağlantı).
  - 2. el ürünlerde (durum_kodu `ikinci_el_*`): "Durum bilgisi" `<details>` bölümü. Satırları: tarih kodu, revizyon/firmware, program/lisans dahil mi, test tarihi. Değerler mockup'ta "[örnek]"; bunun dışında `<details>` bölümleri: Teknik özellikler (boşsa "Teknik föy talep üzerine" + teklif bağlantısı), Teslimat ve iade.
- **Sepet ve ödeme (Görev 14):**
  - Üstte **adım göstergesi** (1 Sepet → 2 Bilgiler → 3 Teslimat → 4 Ödeme → 5 Onay); `aria-current="step"`.
  - Ödeme formu **tek sütun**, etiket alanın üstünde. Sağda (mobilde altta) sabit **sipariş özeti**: kalemler, kargo, KDV/ihracat satırı, toplam.
  - Hatalar: alanın altında satır içi + formun üstünde özet (`role="alert"`, alanlara bağlantılı).
  - Kart ve 3D ekranlarında "Demo – test kartları" bilgi kutusu `--info` çerçeveli.
- **Teklif ve yönetim (Görev 15):**
  - Teklif formu tek sütun; ürün seçiliyse üstte ürün özeti kartı.
  - Yönetim: solda dikey menü (Pano, Siparişler, Teklifler, Geri bildirimler). Pano üstte 4 sayı kartı (yeni sipariş, açık teklif, yeni geri bildirim, son eşitleme durumu), tablolar yoğun.
- **Yasal (Görev 16):** Okuma genişliği en fazla 72 karakter, başlık hiyerarşisi net, TASLAK bandı `--warn-bg`.
- **Boş durumlar:** Arama sonucu yoksa yazımı kontrol önerisi + kategori bağlantıları + "Parçayı bulamadınız mı? Teklif isteyin". Sepet boşsa kategori bağlantıları.

## 4. Kapsam dışı (YAGNI — mockup'ta YOK)
CSV ile liste yükleme, ürün karşılaştırma, "teklife dönüştür", otomatik tamamlama, karanlık mod, kart/tablo görünüm anahtarı (tek davranış: masaüstü tablo, mobil kart), sohbet balonu.

## 5. Doğrulama (Görev 11–16'daki testlere ek)
- Görev 11: `site.css` içinde `:root` yeni tokenları içerir; `ikonlar.svg` mevcut ve her sembol id'si var (test: dosyayı ayrıştırıp id kümesi).
- Görev 12: Liste sayfasında `table` (veya `role="table"`) ve her satırda mono parça no sınıfı; ürün sayfasında maliyet şeffaflığı satırı ve 2. el ürününde "Durum bilgisi" bölümü.
- Görev 14: Ödeme sayfalarında `aria-current="step"` olan adım göstergesi.
- Görev 18 e2e: 360 px ve 1280 px ekran görüntüleri yönetim sunumu için `e2e/ekranlar/` altına (ana, liste, ürün, sepet, ödeme, yönetim panosu).
