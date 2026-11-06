# SEO ve LLM uyum raporu (iskelet)

Durum: kod tamamlandı; **kanıt komutları staging'e dağıtımdan sonra çalıştırılacak**. "Ölçüm" hücreleri `<ölçülecek>`
olarak bırakıldı; "beklenen çıktı" sütunları koddan ve testlerden türetilmiştir.

Mockup internete çıkmaz. Bu rapor "demoda nasıl uyumlu hale getirdik; üretime geçersek uyumlu" anlatısı içindir.
İki mod tek ayarla değişir:

| Ayar | Demo (varsayılan) | Üretim |
|---|---|---|
| `SHOP_YAYIN_MODU` | `demo` | `uretim` |
| `SHOP_SITE_KOK` | `http://192.168.5.30:3030` | `https://<alan adı>` |
| `SHOP_AI_TARAYICILAR` | (kullanılmaz) | `GPTBot,ClaudeBot,PerplexityBot,Google-Extended,CCBot` (varsayılan) |
| `SHOP_SAYFA_HIZ` | 120 | 120 (CDN arkasında gerçek IP için bkz. CDN bölümü) |

Başlık/açıklama kalıpları ve terim ince ayarı tek dosyada: `app/web/seo.py` (`SABLONLAR`, `DURUM_ADLARI`).

Kanıt komutlarında `B=http://192.168.5.30:3030` varsayılmıştır.

---

## 1. robots.txt

**Demoda durum:** `User-agent: *` + `Disallow: /` (+ bal küpü `Disallow: /_iz/`). Sitemap burada ilan edilmez.
Her yanıtta `X-Robots-Tag: noindex, nofollow`, her HTML sayfada `<meta name="robots" content="noindex,nofollow">`.

**Kanıt:**
```
curl -s $B/robots.txt
curl -sI $B/tr/ | grep -i x-robots-tag
```
Beklenen: `User-agent: *`, `Disallow: /`, `Disallow: /_iz/`; başlık `noindex, nofollow`.
Ölçüm: `<ölçülecek>`

**Üretimde:** `Allow: /`; yasaklar `/sepet`, `/*/sepet`, `/*/odeme`, `/*/hesabim`, `/*/giris`, `/*/kayit`, `/yonetim`,
`/*/ara?`, `/*?*stokta=`, `/*?*fmin=`, `/*?*fmax=`, `/*?*sira=`, `/_iz/`. Sayfalama (`?sayfa=`) kasıtlı açık.
`SHOP_AI_TARAYICILAR`'daki her tarayıcı için ayrı `User-agent:` bloğu (aynı kurallar). `Sitemap: <SHOP_SITE_KOK>/sitemap.xml`.
`X-Robots-Tag: noindex` yalnız işlemsel sayfalarda (sepet, ödeme, hesap, giriş, kayıt, sipariş, yönetim, arama).
Not: robots.txt ile yasaklanan bir adreste `noindex` görülemez; işlemsel sayfalar bu yüzden çifte korumalıdır
(başka sitelerden gelen bağlantıyla indekslenmeyi robots.txt tek başına engellemez).

## 2. Sitemap

**Demoda durum:** `/sitemap.xml` (indeks) → `/sitemap-urunler-<n>.xml` (en fazla 5.000 URL/dosya),
`/sitemap-kategoriler.xml`, `/sitemap-sayfalar.xml`. Her `<url>`: `loc` (tr), `lastmod`
(`urun.kaynak_guncelleme`; yoksa son eşitleme; yoksa oluşturma tarihi), `xhtml:link` tr/en/x-default.
Yalnız aktif ürün ve (aktif ürünü olan) aktif kategoriler. `Content-Type: application/xml`. Demoda de üretilir.

**Kanıt:**
```
curl -s $B/sitemap.xml
curl -s $B/sitemap-urunler-1.xml | python3 -c "import sys,xml.etree.ElementTree as E; k=E.fromstring(sys.stdin.read()); print(len(k))"
curl -s $B/saglik
```
Beklenen: indeks üç+ `<sitemap>`; ürün dosyasındaki `<url>` sayısı = `/saglik` çıktısındaki `urun`
(dosya başına ≤ 5.000). Ölçüm: ürün sayısı `<ölçülecek>`, dosya sayısı `<ölçülecek>`.

**Üretimde:** Search Console ve Bing Webmaster'a `sitemap.xml` gönderimi; kapsam raporunun izlenmesi.

## 3. llms.txt / llms-full.txt

**Demoda durum:** `/llms.txt` (llmstxt.org biçimi: `# Ceylan Robot`, `> özet`, bölümler Ürün grupları,
Satın alma ve teklif, Teslimat ve ihracat, İletişim, Yasal, Optional) ve `/llms-full.txt` (kök kategori başlıkları altında
`ad — parça no — üretici kodu — durum — bağlantı`). `text/plain; charset=utf-8`. Demoda ilk satırın altında
"Bu bir iç demodur; veriler temsilidir." notu bulunur.
**Karar:** `llms.txt` ve sayfalara gizli talimat (prompt enjeksiyonu / token tuzağı) konmaz. Gerekçe: iyi niyetli
asistanları da yanıltır, arama motorları açısından cloaking sayılır ve güveni zedeler. Kötü niyetli tarayıcılara karşı
koruma bölüm 11'deki bal küpü ve hız sınırıdır.

**Kanıt:**
```
curl -s $B/llms.txt | head -20
curl -s $B/llms-full.txt | grep -c '^- '
curl -s $B/saglik
```
Beklenen: ilk satır `# Ceylan Robot`; `grep -c` değeri = aktif ürün sayısı. Ölçüm: `<ölçülecek>`

**Üretimde:** Demo notu kendiliğinden kalkar. Hangi yapay zekâ tarayıcılarına izin verileceği ticari karardır
(`SHOP_AI_TARAYICILAR`); `llms.txt` bu listeyle ve CDN'deki bot ayarıyla tutarlı olmalıdır.

## 4. Yapısal veri (JSON-LD)

**Demoda durum:** `<script type="application/ld+json">`, sunucuda `json.dumps` ile üretilir; `<`, `>`, `&` ve satır
ayırıcılar `\uXXXX` kaçışlıdır (ürün adında `</script>` olsa bile sayfa bozulmaz; test var). CSP değişmedi: veri bloğu
kod çalıştırmaz; satır içi diğer her `<script>` hâlâ testlerde hata.
- Ürün: `Product` (name, sku, mpn, brand, image mutlak URL, description, category, itemCondition, `offers`).
  `brand` yalnız bilinen üretici markası ürün adında geçiyorsa verilir (`app/katalog/marka.py` izin listesi); aksi halde alan yok.
- `offers` fiyatı, anonim TR ziyaretçiye sayfada birincil gösterilen fiyatla aynıdır (aynı `birim_fiyat_gosterimi` hesabı: kur varsa KDV dahil TRY,
  kur yoksa EUR net); `priceCurrency` ve `priceSpecification` (`UnitPriceSpecification`, `valueAddedTaxIncluded`) buna göre.
- **Teklif zorunlu ürünlerde `offers` hiç verilmez** (fiyatsız Offer geçersiz öğedir); `Product` yine çıkar. `shippingDetails` yalnız sepete eklenebilir
  üründe ve yalnız Türkiye için 15 EUR (+ KDV, sayfadaki metinle aynı değer); yurt dışı navlun teklifledir, işaretlenmez.
- `hasMerchantReturnPolicy`: yalnız yasal/iade sayfasında yazan 14 günlük cayma süresi (`MerchantReturnFiniteReturnWindow`, `merchantReturnDays` 14) ve sayfa bağlantısı.
  "Ücretsiz iade" iddiası yoktur. Cayma yalnız bireysel alıcılar içindir; kurumsal ve yurt dışı koşullar sözleşmeye bağlıdır; yasal onaydan sonra gözden geçirilmelidir.
- Kategori/liste: `BreadcrumbList` + `ItemList`. Ana sayfa: `Organization` (logo, telefon) + `WebSite` + `SearchAction`
  (Google sitelinks arama kutusunu Kasım 2024'te kaldırdı; işaretleme zararsızdır ama görünür etkisi beklenmez).
- Durum eşlemesi: `yeni` -> NewCondition, `ikinci_el_test_edildi` -> RefurbishedCondition, `ikinci_el_oldugu_gibi` -> UsedCondition.
- Stok: stok > 0 InStock; stok 0 ve tedarik süresi var PreOrder; aksi OutOfStock.

**Üretimde:** teklif zorunlu ürünler zengin sonuç (merchant listing) üretmez; bu bilinçli bir karardır. Gerçek fiyat gelince fiyat eşleşmesi yeniden doğrulanır.

**Kanıt:**
```
curl -s $B/tr/urun/<id> | python3 -c "import re,sys,json; [print(json.dumps(json.loads(m),ensure_ascii=False)[:300]) for m in re.findall(r'<script type=\"application/ld\+json\">(.*?)</script>', sys.stdin.read(), re.S)]"
```
Beklenen: tek `Product` nesnesi, JSON olarak ayrıştırılır. Ölçüm: Schema.org doğrulayıcı / Rich Results Test sonucu `<ölçülecek>`
(demo adresine dışarıdan erişilemez; sayfa kaynağı yapıştırılarak denenir).

## 5. Başlık ve meta açıklama

**Demoda durum:** ürün `"{ad} | {parça no} | {marka} {durum} – Ceylan Robot"` (≤ 60 kr hedef; sığmazsa önce durum, sonra marka
düşer; parça no hep kalır); kategori `"{kategori} yedek parça ve robotlar ({n} ürün) – Ceylan Robot"`;
sayfa 2+ için `– Sayfa n`. Açıklama ≤ 155 kr; ürün için kayıtlı açıklama, yoksa şablon (parça no içerir). 50 rastgele ürün sayfasında
başlık ve açıklama tekrarı yok (test). Open Graph (`og:title/description/image/type/url/locale`) ve `twitter:card summary_large_image`;
`og:image` mutlak büyük görsel (yer tutucu SVG ise logo).
Marka: ürün adının ilk kelimesi (`app/katalog/marka.py`; sayı/kısa kod/jenerik sözcük ise marka yok).

**Kanıt:** `curl -s $B/tr/urun/<id> | grep -iE '<title>|name="description"|og:'`. Ölçüm: başlık uzunluğu dağılımı `<ölçülecek>`.

**Üretimde:** Anahtar kelime araştırmasının terim listesiyle `app/web/seo.py` şablonları ince ayarlanır
(rakip marka/satıcı adı ve "yetkili satıcı" ifadesi kullanılmaz).

## 6. hreflang

**Demoda durum:** Her indekslenebilir sayfada ve sitemap'te `tr`, `en`, `x-default` (= tr), mutlak URL. `<html lang>` doğru.
**Kanıt:** `curl -s $B/tr/urun/<id> | grep hreflang`. Beklenen: üç satır. Ölçüm: `<ölçülecek>`
**Üretimde:** Search Console "Uluslararası hedefleme" hataları izlenir.

## 7. Canonical

**Demoda durum:** Mutlak (`SHOP_SITE_KOK`); `stokta`, `fmin`, `fmax`, `sira`, `q` gibi filtre/sıralama/arama parametreleri atılır,
`sayfa` > 1 korunur. İşlemsel ve hata sayfalarında canonical/hreflang/OG üretilmez.
**Kanıt:** `curl -s "$B/tr/kategori/<id>?stokta=1&sira=ad&sayfa=2" | grep canonical`
Beklenen: `.../tr/kategori/<id>?sayfa=2`. Ölçüm: `<ölçülecek>`

## 8. İçerik (anahtar kelime ve ürün açıklaması)

**Demoda durum:** Kategori sayfası üstünde şablon tabanlı 1-2 cümle giriş (kategori + kök + ürün sayısı + test/ihracat/teklif; TR/EN).
Ürün açıklamaları yeni `urun_aciklama` tablosunda (`urun_id`, `dil`, `metin`, `kaynak` `llm-taslak`|`kaynak`, `model`, `uretildi`; anahtar `(urun_id, dil)`).
Eşitleme bu tabloya yazmaz/silmez (test var). Sayfada "Ürün açıklaması" bölümü; `llm-taslak` ise "Taslak açıklama" rozeti; JSON-LD ve
meta description aynı metne bağlanır, yoksa şablon açıklama. Üretim betiği bu çalışmanın dışındadır.
Ölçüm: açıklaması olan ürün oranı `<ölçülecek>`.
**Üretimde:** Taslak açıklamalar insan onayından geçirilir (`kaynak` güncellenir); üretici görselleri kaynak etiketiyle kaldırılır ya da lisanslanır.

## 9. Hız / Core Web Vitals

**Demoda durum:** Satır içi script/stil yok; yerel `webp` görseller (`/gorsel/k|b/`) `Cache-Control: public, max-age=31536000, immutable`;
liste görselleri `loading="lazy"`, ürün detay görseli (LCP adayı) lazy değil; görsellerde `width/height` var (CLS). JSON-LD sayfaya birkaç KB ekler.
**Kanıt:** `curl -sI $B/gorsel/b/<ad>.webp | grep -i cache-control`; Lighthouse (mobil) ürün ve kategori sayfası.
Ölçüm: LCP `<ölçülecek>`, INP `<ölçülecek>`, CLS `<ölçülecek>`, TTFB `<ölçülecek>`.
**Üretimde:** CDN (aşağıda) TTFB ve görsel teslimini iyileştirir; gerçek kullanıcı verisi (CrUX) Search Console'da izlenir.

## 10. Erişilebilirlik

**Demoda durum:** Ürün detay görseli `alt = ürün adı + parça no`; liste görselleri `alt=""` (yanında metin var; mevcut karar korundu).
Bal küpü bağlantısı `aria-hidden="true"` + `tabindex="-1"`, ekran dışına alınmış; klavye ve ekran okuyucu kullanıcılarını etkilemez.
Ölçüm: Lighthouse erişilebilirlik puanı `<ölçülecek>`.

## 11. Kötü niyetli tarayıcı koruması (demoda çalışır)

- **Bal küpü:** her sayfada gizli bağlantı `/_iz/<sabit>`; `robots.txt` iki modda da yasaklar. İsabet eden IP 24 saat 403 alır
  (süreç içi tablo + SQLite `engelli_ip`; yeniden başlatmada korunur). Yönetim panosunda "Engellenen tarayıcılar" listesi ve tek tıkla
  kaldırma var; `/yonetim` ve `/robots.txt` engelden muaftır (yönetici kendi IP'si engellense de panoya girebilsin). Yerel ağ IP'leri de engellenir.
- Gizli bağlantı `nofollow` taşır ve robots.txt ile yasaklıdır; yalnız kurallara uymayan botlar izler, bu nedenle arama motorlarının "gizli bağlantı" spam politikasıyla çelişmez.
  `AdsBot-Google` gibi `*` grubuna uymayan Google botları ileride Google Ads kullanılırsa bal küpüne girebilir: o zaman robots.txt'e ayrı `User-agent: AdsBot-Google` bloğu eklenmeli.
- **Muafiyet:** `SHOP_KORUMA_MUAF_IP` (virgüllü IP/CIDR) listesindeki istemciler hız sınırına ve bal küpü engeline tabi değildir (bal küpü isabeti yalnız günlüğe yazılır). Staging'de e2e laptopu için kullanılır.
- **Hız sınırı:** ürün ve kategori sayfalarında IP başına dakikada 120 istek; aşımda `429` + `Retry-After: 60`. Statik dosyalar ve `/gorsel/` hariç.
**Kanıt:**
```
curl -s -o /dev/null -w "%{http_code}\n" $B/_iz/k7f3q9x2m4b8   # 403 (bu makinenin IP'si 24 saat engellenir; panodan kaldırılır)
# NOT: muaf olmayan bir makineden çalıştırın ya da e2e'den SONRA çalıştırıp engeli panodan kaldırın;
# aksi halde e2e'yi çalıştıran IP 24 saat 403 alır. 125 istekli döngü de e2e'den sonra çalıştırılmalıdır.
# e2e makinesi SHOP_KORUMA_MUAF_IP listesine eklenirse bal küpü ve hız sınırı bu IP için uygulanmaz (kanıt için muaf olmayan makine gerekir).
for i in $(seq 1 125); do curl -s -o /dev/null -w "%{http_code}\n" $B/tr/urun/<id>; done | sort | uniq -c
```
Beklenen: 120 adet `200`, 5 adet `429`. Ölçüm: `<ölçülecek>`
**Uyarı (CDN/ters vekil):** İstemci IP'si bağlantı adresinden alınır. Önde CDN varsa uvicorn `--proxy-headers --forwarded-allow-ips=<vekil IP'leri>`
ile çalıştırılmalıdır; aksi halde bal küpü CDN kenar IP'sini engeller ve herkes 403 alır.

---

## Üretime geçiş kontrol listesi

1. Alan adı + `SHOP_SITE_KOK=https://<alan adı>`; TLS.
2. `SHOP_YAYIN_MODU=uretim`; `robots.txt`, `X-Robots-Tag` ve meta robots değişimini bölüm 1 komutlarıyla doğrula.
3. Search Console ve Bing Webmaster doğrulaması; `sitemap.xml` gönderimi.
4. Gerçek fiyat ve stok (temsili fiyat rozeti kalkar); teklif zorunlu ürünlerde JSON-LD kararı (bölüm 4).
5. Üretici görsellerinin kaynak etiketiyle kaldırılması ya da lisanslanması.
6. Taslak ürün açıklamalarının insan onayı.
7. Yapay zekâ tarayıcı politikası kararı (`SHOP_AI_TARAYICILAR`, `llms.txt`, CDN bot ayarı tutarlı).
8. CDN arkasında gerçek istemci IP'si (`--proxy-headers`) ve hız sınırı değerinin gözden geçirilmesi.

## CDN katmanı (Cloudflare önerisi)

Önerilen konum: alan adı Cloudflare üzerinden proxy'lenir; uygulama kaynak sunucu (origin) olarak kalır.

| Konu | Öneri |
|---|---|
| TLS | Cloudflare uçta TLS; origin'e "Full (strict)" için origin sertifikası ya da tünel. Demodaki düz HTTP üretimde kalmaz. |
| Önbellek | `/statik/*` ve `/gorsel/*` kenarda önbellek (origin zaten `immutable`, 1 yıl); HTML dinamik olduğundan varsayılan olarak önbelleğe alınmaz. `sitemap*.xml`/`llms*.txt` kısa TTL ile önbelleğe alınabilir. |
| WAF ve bot yönetimi | Yönetim yolu (`/yonetim`) için ek kural (IP/ülke kısıtı ya da Access). Hız sınırı kuralı kenarda da tanımlanır; uygulamadaki 120/dk sınırı ikinci katman olarak kalır. |
| Yapay zekâ botları | "Block AI bots" seçimi ile kurallara uymayan yapay zekâ tarayıcıları engellenir; izin verilen botlar `SHOP_AI_TARAYICILAR`, `llms.txt` ve CDN ayarında aynı liste olmalıdır. Cloudflare'in yönetilen `robots.txt` özelliği açılırsa kendi AI Disallow satırlarını ekler; uygulamanın `robots.txt`'iyle çelişmemesi için tek kaynak seçilmelidir. |
| AI Labyrinth | Kurallara uymayan botu sahte bağlantı labirentinde oyalar, iyi botlara dokunmaz. Uygulamadaki bal küpünü tamamlar (labirent kenarda, bal küpü origin'de). Gizli talimat/prompt enjeksiyonu yapılmaz. |
| Core Web Vitals | TTFB düşer (kenar önbellek, HTTP/3), görseller kenardan gelir; HTML'e etkisi yalnız TLS ve ağ yolunda. Ölçüm: öncesi/sonrası Lighthouse ve CrUX `<ölçülecek>`. |
| Origin gizleme | Sunucuya yalnız Cloudflare IP aralıklarından erişim (güvenlik duvarı izin listesi) ya da Cloudflare Tunnel; origin IP'si DNS'te ve e-posta başlıklarında sızdırılmaz. |
| Gerçek IP | Vekil arkasında `CF-Connecting-IP`/`X-Forwarded-For` ile gerçek IP; uvicorn `--proxy-headers --forwarded-allow-ips`. Bal küpü ve hız sınırı bu IP'ye dayanır. |

**Maliyet notu:** Ücretsiz plan; proxy, önbellek, temel DDoS koruması, sınırlı özel WAF kuralı, "Block AI bots" ve AI Labyrinth seçeneklerini
kapsar. Pro plan (aylık ücretli) daha gelişmiş bot yönetimi ve yönetilen WAF kuralları ekler; ücretsiz planın bu site için yeterli olup
olmadığı staging deneyiyle ölçülür. Güncel plan kapsamı ve fiyat satın alma öncesi Cloudflare sayfasından doğrulanmalıdır.
