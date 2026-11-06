# Ceylan Robot satış sitesi: tıklanabilir mockup (staging) tasarımı

Tarih: 12.10.2026 · Durum: tasarım onaylandı, spesifikasyon kullanıcı incelemesinde (bağımsız değerlendirme 8,7/10)
Sahip: BT birimi (CTO)

## 1. Amaç ve başarı ölçütü

**Amaç:** Netsis'te zaten bulunan ürünlerle, yurt içi ve yurt dışına online ödemeli satış yapan bir e-ticaret sitesinin **tıklanabilir prototipini** kurmak. Satış ekibi ve yönetim prototipi kullanıp geri bildirim verecek. Onaylanırsa aynı kod tabanı gerçek sitenin ilk sürümü olacak; siteyi biz geliştireceğiz.

**Başarı ölçütü:**
- Satış ekibinden en az 3 kişi, uçtan uca dört senaryoyu yardımsız tamamlayabilmeli (bkz. §11):
  - bireysel TR siparişi,
  - kurumsal TR siparişi,
  - yurt dışı siparişi,
  - robot için teklif isteme.
- Geri bildirimler site içindeki düğmeyle toplanmalı.
- Bağımsız değerlendirme puanı **en az 8,5/10** olmalı.

**Kullanıcının belirlediği kısıtlar:**
- Ürünler gerçek olmalı (Netsis kaynaklı).
- Ödeme online olmalı; mockup'ta simülasyon.
- Müşteri tipleri: bireysel, kurumsal ve yurt dışı.
- Fiyatlar hibrit (§5.3).
- Staging, Gen10'daki `cr-web-demo` VM'inde, mustafaceylan.com demosunun yanında **yalnız farklı bir portta** çalışmalı.
- Laptopa site kurulmayacak; laptopta yalnız git deposu ve dokümanlar olacak.

**Varsayımlar (kullanıcı belirtmedi):**
- Arayüz dilleri TR ve EN.
- Para birimleri EUR ve TRY.
- Kurumsal Ceylan Robot teması kullanılacak; CM-Tema yalnız saha ekranları içindir.
- Süre esnek. Tahmin: 5–6 çalışma oturumu (altyapı 1, veri ve kurallar 1, ekranlar 2, test ve düzeltme 1–2).

## 2. Kapsam

**Kapsam içi:**
- Ana sayfa, kategori ağacı, filtreli ürün listesi, arama (ad, SKU, üretici kodu), ürün detayı.
- Sepet.
- Üyelik ve giriş: bireysel, kurumsal, yurt dışı.
- Ödeme akışı: adres, fatura tipi, kargo/teslim, **sahte** 3D Secure, sipariş onayı.
- Hesabım ekranı: siparişlerim ve tekliflerim.
- Teklif isteme formu.
- TR/EN dil ve TRY/EUR para birimi geçişi.
- Yasal sayfa taslakları.
- Geri bildirim düğmesi.
- Basit yönetim paneli: siparişler, teklifler, geri bildirimler, katalog eşitleme durumu.
- Gece çalışan katalog eşitlemesi.

**Kapsam dışı (bu aşamada YAPILMAYACAK):**
- Gerçek ödeme, gerçek ödeme kuruluşu sözleşmesi ve gerçek 3D Secure.
- Netsis'e herhangi bir yazma işlemi; Netsis veritabanına doğrudan bağlantı dahil.
- E-posta ve SMS gönderimi.
- e-Fatura/e-Arşiv entegrasyonu.
- Kargo firması entegrasyonu.
- İnternete açılma; mockup yalnız iç ağdan erişilebilir olacak.
- Ürün içeriğinin (görsel, açıklama) zenginleştirilmesi.
- SEO ve analitik.

## 3. Mevcut durum (12.10.2026'da doğrulandı)

- **Mevcut ceylanrobot.com:** Ajansın (Anssoft/MXEN) yaptığı React/Vite SPA. Herkese açık `GET /api/public/products?page=&limit=` uç noktası var.
  - Toplam 4.449 ürün var. API sayfa başına en fazla ~20 kayıt döndürüyor; büyük sayfalarda zaman aşımı oluşuyor.
  - `GET /api/public/categories` ERP kategori ağacını veriyor (`path`, `level`, `parentId`, `erpId`).
- **Ürün alanları:**
  - `sku`, `name`
  - `attributes.manufacturerCode`, `attributes.vatRate`, `attributes.weight` (çoğunlukla 0)
  - `price.amount` (örneklerde 0 EUR), `stock`
  - `images` (çoğu ürün için boş), `categoryId{name,path}`
  - `descriptionSections`, `techSpecs` (örneklerde boş)
- **Netsis'e doğrudan erişim yok.** SRV2'de Windows yöneticisi SQL'e bağlanamıyor (12.10'da denendi, 18456). Mockup bu yüzden yalnız public API'yi kullanır. Gerçek site için §13'teki açık soruya bakın.
- **Hedef VM `cr-web-demo` (192.168.5.30):**
  - Ubuntu, Python 3.12.3; `pip` ve `venv` kurulu değil.
  - 2 vCPU, 1,9 GB RAM, disk 12 GB boş.
  - Port 80 `web-demo.service`, port 3027 `aic-demo.service` tarafından kullanılıyor.
  - Kullanıcı `crwebdemo` sudo grubunda; parolası kimlik Excel'inde.
  - VM'den internete (PyPI ve ceylanrobot.com) erişim var.

## 4. Mimari

**Seçilen yaklaşım:** Python **FastAPI** ile sunucu tarafında üretilen HTML (Jinja2) ve **SQLite**.
- Ekibin standart yığını (cr-barkod, cr-meet); Node gerektirmiyor.
- 2 GB RAM'de rahat çalışıyor.
- Sayfaları sunucu ürettiği için arama motoru uyumu ileride hazır olacak.
- **Reddedilenler:** Next.js (VM'e Node kurulması ve yüksek RAM ihtiyacı) ve hazır e-ticaret yazılımları (Netsis uyumu ve özelleştirme zorluğu).

```
[Tarayıcı] ──HTTP :3030──> uvicorn (FastAPI, 1 worker)
                              ├─ web/   (Jinja2 şablonları, CSS, az JS)
                              ├─ servis katmanı (katalog, fiyat, sepet, sipariş, teklif, hesap, geri bildirim)
                              └─ SQLite  /opt/cr-shop-demo/veri/shop.db  (WAL)
[systemd timer 02:30] ──> katalog_esitle.py ──HTTPS──> ceylanrobot.com/api/public/*  (salt okuma)
[systemd timer 06:00] ──> kur_al.py ──HTTPS──> TCMB today.xml (EUR alış/satış)
```

**Modüller:** Her biri tek sorumluluklu ve ayrı test edilebilir.

| Modül | Sorumluluk | Bağımlılık |
|---|---|---|
| `katalog/` | Ürün ve kategori okuma, arama, filtre | db |
| `esitleme/` | Public API'den çekme, normalleştirme, upsert, eşitleme günlüğü | httpx, db |
| `fiyat/` | Temsili fiyat üretimi, para birimi, KDV, "teklif mi sepet mi" kuralı | kur tablosu |
| `hesap/` | Kayıt, giriş, oturum, müşteri tipi | db, scrypt (stdlib) |
| `sepet/` | Oturuma bağlı sepet, tutar hesabı | fiyat |
| `siparis/` | Ödeme simülasyonu, sipariş kaydı, durumlar | sepet, hesap |
| `teklif/` | Teklif isteği kaydı | hesap (opsiyonel) |
| `geribildirim/` | Sayfa adresi + metin + isim kaydı | db |
| `yonetim/` | Listeleme ekranları (salt okuma + durum değiştirme) | tümü |
| `web/` | Rotalar, şablonlar, i18n | servisler |

**Bağımlılıklar:**
- `fastapi`, `uvicorn`, `jinja2`, `httpx`, `python-multipart`, `itsdangerous`.
- Test için: `pytest`, `playwright`.
- **CDN kullanılmaz;** az miktardaki JS (sepet adedi, para birimi ve dil geçişi) elle yazılır ve sunucudan verilir.

## 5. Veri ve iş kuralları

### 5.1 Veri modeli (SQLite)
- `kategori(id, erp_id, ad, ust_id, yol, seviye, aktif)`
- `urun(id, sku UNIQUE, ad, uretici_kodu, kategori_id, kdv_orani, stok, tedarik_suresi_gun NULL, gorsel_url, kaynak_guncelleme, aktif, temsili_fiyat_eur, teklif_zorunlu, durum_kodu)`
  - `durum_kodu`: `yeni | ikinci_el_test_edildi | ikinci_el_oldugu_gibi | belirtilmemis`. Kaynakta bu alan yok, varsayılan `belirtilmemis`. Gösterim için 10–20 üründe örnek değer seed ile atanır ve "örnek" diye işaretlenir. Ürün detayında **rozet olarak** gösterilir; değerlerin neredeyse hepsi `belirtilmemis` olacağı için listede **filtre olarak sunulmaz**.
  - `tedarik_suresi_gun`: kaynakta yok, `NULL` = bilinmiyor.
- `musteri(id, tip[bireysel|kurumsal|yurtdisi], ad, eposta UNIQUE, parola_ozeti, vergi_kimlik_no, vergi_dairesi, vat_id, ulke, kvkk_onay_ts, iys_onay, olusturma)`
  - `vergi_kimlik_no`: kurumsalda 10 haneli VKN **veya** şahıs şirketi için 11 haneli TCKN. İkisi de kontrol algoritmasıyla doğrulanır.
- `adres(id, musteri_id, tur[teslimat|fatura], …)`
- `sepet(id, oturum_id, musteri_id NULL)`, `sepet_kalemi(sepet_id, urun_id, adet)`
- `siparis(id, no, musteri_id, para_birimi, ara_toplam, kdv, kargo, toplam, kur, durum, olusturma)`, `siparis_kalemi(…)`
- `teklif(id, no, musteri_id NULL, ad, firma, eposta, telefon, ulke, urun_id NULL, mesaj, durum, olusturma)`
- `geri_bildirim(id, sayfa, metin, isim, olusturma, durum)`
- `kur(tarih, eur_alis, eur_satis)`, `esitleme_gunlugu(id, basla, bitis, cekilen, eklenen, guncellenen, hata)`

### 5.2 Katalog eşitleme
- Sayfa başına 20 kayıt çekilir, istekler arasında 1 sn beklenir. Zaman aşımı 30 sn, en fazla 3 deneme (ilk istek + 2 yeniden deneme; 2 ve 4 sn bekleme).
- Tam tur yaklaşık 4–5 dakika sürer ve **02:30'da** çalışır; canlı site yorulmaz.
- **Tur bütünlüğü:** Çekilen kayıtlar önce bir ara tabloya yazılır. Tur sonunda çekilen benzersiz SKU sayısı ile atlanan bozuk kayıt sayısının toplamı, ilk ve son sayfadaki API `total` değeriyle karşılaştırılır. Kategoriler veya ilk sayfa alınamazsa tur `hata` olur; sonraki bir sayfa alınamazsa tur `eksik` sayılır.
  - Sayılar tutarsa tur **tam** sayılır. Ara tablo tek transaction'da ana tabloya upsert edilir, kaynakta artık görünmeyen ürünler `aktif=0` yapılır ve FTS5 arama indeksi aynı transaction'da yeniden kurulur.
  - Sayılar tutmazsa (sayfalama sırasında kayıt eklendiyse ya da bir sayfa alınamadıysa) tur **eksik** sayılır. Bu durumda yalnız upsert yapılır, hiçbir ürün pasife alınmaz ve günlüğe `eksik` yazılır.
- **Hata durumunda:** Mevcut veri asla silinmez; eşitleme günlüğüne `hata` yazılır.
- **Sessiz başarısızlık önlemi:** Yönetim panelinde "son başarılı eşitleme" zamanı gösterilir. 36 saati geçerse sitenin üstünde yalnız yöneticinin gördüğü bir uyarı çıkar.
- **Görseller:** `https://www.ceylanrobot.com` üzerinden doğrudan bağlantı verilir. Görsel yoksa kategoriye göre yer tutucu çizim (SVG) gösterilir; görseller VM'de saklanmaz.

### 5.3 Fiyat (hibrit)
- **Kaynak fiyat > 0 ise** o kullanılır.
  - Bugün ürünlerin hepsinde 0 görünüyor. Bu yüzden şimdilik tüm fiyatlar temsili.
- **Kaynak fiyat 0 ise temsili fiyat üretilir.**
  - Fiyat SKU'dan deterministik olarak hesaplanır: her eşitlemede aynı kalır.
  - Kategori köküne göre bir fiyat bandı kullanılır, bantlar `fiyat/bantlar.yaml` dosyasındadır.
  - Arayüzde her fiyatın yanında **"Temsili fiyat"** rozeti bulunur.
- **Fiyat tabanı:** Temsili fiyat, kaynak fiyat ve 15.000 € eşiği her zaman **EUR ve KDV hariç** tutulur.
- **"Teklif iste" kuralı:** Aşağıdakilerden biri doğruysa ürün sepete eklenemez, yalnız teklif istenebilir:
  - kategori kökü `fiyat/bantlar.yaml` içindeki `robot_kokleri` listesinde (şu an "Endüstriyel Robotlar" ve "Pozisyonerler"; "Robot Kontrol Üniteleri" ve "Robotik Parçaları" yedek parça olarak sepete eklenebilir),
  - KDV hariç fiyat 15.000 €'nun üzerinde.
- **Stoğu 0 olan ürünler** teklife düşmez. Sepete eklenebilir; ürün sayfasında ve siparişte "Tedarik süresi sipariş sonrası teyit edilecek" notu görünür (`tedarik_suresi_gun` boşsa).
- **Vergi rejimini teslimat ülkesi belirler, müşteri tipi yalnız gösterimi belirler:**
  - **Teslimat TR:** KDV uygulanır (ürünün `kdv_orani` değeri, örneklerde %20). Bu kural yurt dışı hesabın TR adresine teslim istemesi durumunda da geçerli.
  - **Teslimat TR dışı:** "İhracat – KDV istisnası" satırı gösterilir. Gümrük ve ithalat vergilerinin alıcıya ait olduğu (DAP) notu düşülür. TR kurumsal müşterinin yurt dışı teslimatı da bu kapsamda.
  - Ödeme adımında teslimat ülkesi seçildiği anda sepet yeniden hesaplanır ve değişiklik kullanıcıya gösterilir.
- **Gösterim ve tahsilat para birimi:**

  | Müşteri | Fiyat gösterimi | Tahsilat |
  |---|---|---|
  | TR bireysel | TRY, KDV dahil (Fiyat Etiketi Yönetmeliği); EUR karşılığı küçük yazıyla bilgi | TRY |
  | TR bireysel, yurt dışı teslim | TRY, KDV yerine ihracat istisnası satırı | TRY |
  | TR kurumsal | EUR, KDV hariç; TRY karşılığı yanında; KDV sepette ayrı satır | TRY (TR teslim) / EUR (yurt dışı teslim) |
  | Yurt dışı | EUR | EUR |
  | Yurt dışı hesap, TR teslim | EUR, KDV ayrı satır | EUR (KDV dahil toplam) |
  | Ziyaretçi | Üst çubuktaki **ülke seçicisine** göre (varsayılan Türkiye). Ülke dilden bağımsızdır: EN arayüz kullanan Türkiye'deki ziyaretçi yine TRY ve KDV dahil fiyat görür | — |

- **Kur:**
  - TCMB günlük EUR satış kuru kullanılır, değeri ve tarihi fiyatın altında görünür. Kur alınamazsa son kur kullanılır ve kur tarihi kırmızıyla gösterilir.
  - **Kur ödeme anında sabitlenir** ve siparişe yazılır. Sepette gösterilen kur ödeme ekranında yenilenir; fark çıkarsa yeni tutar onaylatılır.
- **Tutar ve yuvarlama:**
  - Tüm hesap `Decimal` ile yapılır, float kullanılmaz; yuvarlama `ROUND_HALF_UP`, 2 hane.
  - **Satır bazında sıra:** EUR net birim fiyat × adet → (TRY tahsilatta) kurla çevir ve yuvarla → KDV'yi satır için hesapla ve yuvarla.
  - Ara toplam, KDV ve genel toplam satırların toplamıdır; toplam üzerinden yeniden KDV hesaplanmaz.
- **Kargo (temsili):**
  - TR teslimat: sabit 15 € + KDV (TRY tahsilatta kurla çevrilir).
  - Fabrikadan teslim: 0.
  - Yurt dışı: 0, "Navlun ayrıca teklif edilecektir" notuyla.
  - Ağırlık verisi çoğunlukla 0 olduğundan ağırlığa göre hesap **yapılmaz**.

### 5.4 Ödeme simülasyonu
- **Ödeme ekranı:** Kart formu ve sahte "3D Secure" sayfası gösterilir.
- **Kabul edilen kartlar yalnız test kartlarıdır:**
  - `4111 1111 1111 1111`: başarılı.
  - `4000 0000 0000 0002`: banka reddi.
  - **Bunların dışındaki her numara sunucuda reddedilir** ("Demo: yalnız test kartları kabul edilir"). Böylece satış ekibi yanlışlıkla gerçek kart girse bile kart işlenmez ve saklanmaz.
  - SMS kodu `000000` dışında bir değer girilirse doğrulama hatası verilir.
- **Kart bilgisi saklanmaz.** Kart numarasının yalnız son 4 hanesi siparişe yazılır; tam numara loglara düşmez, istek gövdesi de loglanmaz.
- **Sipariş kaydı ve ret sonrası:**
  - Sipariş, kullanıcı ödeme adımında "Ödemeye geç" dediği anda `odeme_bekliyor` durumunda oluşturulur. Tutar, kur ve kalemler bu anda sabitlenir.
  - Ödeme reddedilirse aynı sipariş `odeme_bekliyor` olarak kalır ve kullanıcı aynı sipariş için yeniden dener; yeni sipariş açılmaz.
  - 30 dakika içinde ödenmeyen sipariş `iptal` olur, sepet korunur. Ayrı bir zamanlayıcı yoktur: kontrol, sipariş her okunduğunda (hesabım, ödeme, yönetim paneli) yapılır.
  - Ödeme başarılı olunca (`odendi`) sepet boşaltılır.
- **Çift gönderim:** İşlem anahtarı **ödeme denemesi başına** üretilir. Aynı anahtarla gelen ikinci istek yeni deneme başlatmaz, ilk denemenin sonucu döner. Ödenmiş bir sipariş için yeni deneme kabul edilmez.
- **Misafir ödemesi yok:** Misafir sepeti kullanılabilir, ama ödeme adımına geçerken giriş veya kayıt zorunludur. Müşteri tipi ve fatura bilgisi zaten kayıtta alınıyor. Teklif formu ise misafire de açıktır.
- **Sipariş numarası:** `CR-DEMO-YYYYMMDD-NNNN` biçiminde.
- **İzinli durum geçişleri** (diğerleri 409 döner):

  | Durumdan | Duruma | Kim |
  |---|---|---|
  | `odeme_bekliyor` | `odendi`, `iptal` | ödeme sim. / yönetici |
  | `odendi` | `hazirlaniyor`, `iptal` | yönetici |
  | `hazirlaniyor` | `kargoda` | yönetici |
  | `kargoda` | `teslim` | yönetici |

- **Demo bandı:** **Her sayfanın** üstünde "DEMO – gerçek satış ve ödeme yapılmaz" bandı bulunur (tek kural).

### 5.5 Hesap ve güvenlik
- **Parola:** `hashlib.scrypt` ile, kullanıcıya özel tuz kullanılarak saklanır.
- **Oturum çerezi:** `HttpOnly`, `SameSite=Lax`. TLS olmadığından `Secure` yalnız gerçek sitede eklenir.
- **CSRF:** Tüm formlarda CSRF jetonu kullanılır.
- **Giriş denemesi:** Müşteri ve yönetim girişinde IP başına dakikada 10 deneme sınırı.
- **Yönlendirme:** Girişten sonra `sonraki=` parametresi yalnız site içi göreli yol kabul eder (açık yönlendirme engeli).
- **Yönetim paneli:** `/yonetim` tek yönetici hesabıyla korunur.
- **Gizli bilgiler:** Yönetici kimliği ve oturum imza anahtarı `/opt/cr-shop-demo/ortam` dosyasında durur (izin 600); depoya ve loglara girmez.
- **Bilinen risk:** Staging'de TLS yok, parolalar iç ağda şifresiz gider. Bu yüzden demo hesaplarında gerçek parola kullanılmaması kayıt ekranında hatırlatılır. Gerçek sitede TLS zorunlu.
- **Yanıt başlıkları:**
  - Her yanıtta `X-Robots-Tag: noindex, nofollow`.
  - CSP `default-src 'self'; img-src 'self' https://www.ceylanrobot.com data:`.
  - `X-Frame-Options: DENY`, `Referrer-Policy`.
- **Kişisel veri:** Mockup verisi sahte kişilerle doldurulur (Faker; ekibin `QATestUser` standardı). Satış ekibine gerçek müşteri bilgisi girmemeleri ekranda hatırlatılır.

## 6. Ekranlar ve akışlar

1. **Ana sayfa:**
   - Arama kutusu.
   - Kök kategoriler (kart görünümünde).
   - "Robotlar için teklif alın" alanı.
   - Güven unsurları: test edilmiş 2. el, ihracat, teknik destek.
2. **Kategori / liste:**
   - Sol tarafta kategori ağacı.
   - Filtreler: stokta, fiyat aralığı.
   - Sıralama ve sayfalama (24'lük).
   - Boş sonuçta öneri gösterilir.
3. **Arama:** Ad, SKU ve üretici kodunda arar. SQLite FTS5 kullanılır, Türkçe karakterler normalize edilir.
4. **Ürün detayı:**
   - Görsel veya yer tutucu.
   - SKU, üretici kodu, kategori yolu, durum rozeti, stok bilgisi.
   - Fiyat bloğu (§5.3).
   - "Sepete ekle" ya da "Teklif iste".
   - Teslim ve iade özeti.
5. **Sepet:**
   - Adet değiştirme ve kaldırma.
   - Para birimi ve KDV dökümü.
   - Teklif zorunlu ürünler sepete eklenemez, gerekirse uyarı verilir.
   - Misafir sepeti kullanılabilir. Giriş yapılınca misafir sepeti üye sepetiyle birleşir: aynı ürünün adetleri toplanır, birleşme kullanıcıya bildirilir.
6. **Kayıt / giriş:**
   - Önce müşteri tipi seçilir.
   - Tipe özel alanlar: kurumsalda VKN (10 hane) veya şahıs şirketi için TCKN (11 hane), ikisi de kontrol algoritmasıyla; vergi dairesi. Yurt dışında ülke ve VAT ID (isteğe bağlı).
   - KVKK aydınlatma bağlantısı.
   - İYS onay kutusu: yalnız bireysel için, işaretsiz başlar.
7. **Ödeme:**
   - Adımlar: adres → fatura → teslim yöntemi (kargo / fabrikadan teslim / yurt dışı DAP) → kart → 3D → onay.
   - Bireysel kullanıcılar için ön bilgilendirme formu ve mesafeli satış sözleşmesi onay kutuları gösterilir.
8. **Sipariş onayı ve Hesabım:** Siparişler ve teklifler listelenir, durumları gösterilir.
9. **Teklif iste:**
   - Ürün sayfasından açılırsa ürün önceden seçilidir; genel form da vardır.
   - Kayıtlı müşterinin bilgileri otomatik doldurulur.
   - Teklif durumları: `yeni → inceleniyor → teklif_verildi → kapandi`. Durumu yönetici değiştirir.
   - **Kapsam dışı (mockup):** Teklifin müşteriye fiyatla geri dönmesi ve siparişe dönüşmesi. Gerçek sitede en kritik B2B akışı olduğu için ilk geliştirme turuna alınacak.
10. **Yasal sayfalar (TR/EN):**
    - Ön bilgilendirme formu, mesafeli satış sözleşmesi.
    - İade/cayma politikası (B2C 14 gün cayma; B2B'de cayma yok, sözleşmesel iade).
    - Garanti (2. el için "test edildi / olduğu gibi" ayrımı).
    - KVKK aydınlatma, açık rıza, çerez politikası ve çerez bandı.
    - Gizlilik (GDPR), kullanım koşulları.
    - Künye: unvan, MERSİS, vergi no, adres, KEP, ETBİS. Gerçek değerler yerine "[doldurulacak]" yazılır.
    - Her sayfanın başında **"TASLAK – hukuki onay bekliyor"** bandı bulunur.
11. **Geri bildirim:**
    - Sağ altta sabit düğme.
    - Formda isim, metin ve otomatik eklenen sayfa adresi var.
    - Gönderince "kaydedildi" mesajı çıkar.
12. **Yönetim paneli:**
    - Siparişler (durum değiştirme), teklifler, geri bildirimler (durum: yeni/okundu/yapıldı).
    - Eşitleme günlüğü ve kur bilgisi.
    - CSV dışa aktarma ikinci tura bırakıldı.

**Tema ve erişilebilirlik:**
- Kurumsal palet: koyu yeşil `#303a32`, yeşil `#687860`, kiremit vurgu `#a83c29`, mavi bağlantı `#267593`, açık zemin `#f4f1e9`.
- Fontlar: başlıkta Georgia, gövdede Segoe UI/Arial.
- Ekran boyutları: 360 px mobil, tablet ve masaüstü.
- WCAG AA: kontrast, klavye ile gezinme, form etiketleri.
- Kaynak: Vault `04-Raporlar/Sunum-Temasi/Sunum-Temasi-ve-Renk-Paleti.html`.

## 7. Dil

- **Dil seçimi:** URL'nin başında `/tr/` veya `/en/` olur. Dil, ziyaretçinin seçimine göre ayarlanır ve çerezde saklanır.
- **Çeviri dosyaları:** Arayüz metinleri `web/dil/tr.json` ve `en.json` içinde.
- **Ürün adları:** ERP'deki Türkçe adlar EN arayüzde de değişmeden gösterilir; marka ve üretici kodu zaten evrensel.
- **Eksik çeviri:** Anahtarın kendisi değil TR metin gösterilir. Test, eksik anahtarları listeler.

## 8. Kurulum (staging)

- **Konum:** `cr-web-demo` VM, port **3030**.
- **Klasör yapısı:** `/opt/cr-shop-demo/`
  - `releases/<YYYYMMDD-HHMM>/` ve buna işaret eden `current` bağlantısı. **Her release kendi `venv/` klasörünü** içerir; geri dönüşte kod ve bağımlılıklar birlikte döner. Son 3 release tutulur (~150 MB).
  - `veri/shop.db`
  - `ortam` (izin 600)
  - `yedek/`
- **Ön koşul:** `sudo apt install python3-venv`. Bunun için `crwebdemo` sudo parolası gerekir; Excel'de kayıtlı.
  - **Yedek yol:** sudo kullanılamazsa paketler başka bir makinede `pip download` ile indirilir, VM'e kopyalanır ve `PYTHONPATH` ile kullanılır.
- **Servis kullanıcısı:** `crshop` (sistem kullanıcısı, giriş kabuğu yok).
- **`cr-shop-demo.service`:**
  - `uvicorn --factory app.web.asgi:uygulama --host 0.0.0.0 --port 3030 --workers 1`
  - Sertleştirme: `NoNewPrivileges`, `ProtectSystem=strict` (yazma yalnız `ReadWritePaths=/opt/cr-shop-demo/veri /opt/cr-shop-demo/yedek`), `ProtectHome`, `PrivateTmp`.
  - `Restart=always` (AIC servisindeki kalıp).
- **Zamanlayıcılar** (hepsi `crshop` kullanıcısıyla, web servisiyle aynı sertleştirme ve `ReadWritePaths` ile çalışır):
  - `cr-shop-esitle.timer` (02:30): `MemoryMax=400M`, `TimeoutStartSec=30min`.
  - `cr-shop-yedek.timer` (03:00): `sqlite3 .backup` ile `yedek/shop-YYYYMMDD.db`; 7 günden eski yedekler silinir.
  - `cr-shop-kur.timer` (06:00).
- **Güvenlik duvarı (ufw):** 3030/tcp yalnız 192.168.2.0/24, 5.0/24, 11.0/24, 12.0/24 ağlarından erişilebilir; AIC'deki kuralla aynı.
- **Sabit kalanlar:** Port 80 ve 3027 servislerine **dokunulmaz.**
- **Laptopun rolü:** Laptopta yalnız git deposu ve `deploy.sh` bulunur; Python bağımlılıkları kurulmaz. Birim ve entegrasyon testleri **VM'de**, yeni release'in kendi venv'inde çalışır. Playwright uçtan uca testleri laptopta zaten kurulu Playwright ile staging adresine karşı çalışır.
- **Dağıtım:** Laptopta `deploy.sh` çalıştırılır:
  1. Git arşivi alınır ve `scp` ile yeni release klasörüne kopyalanır.
  2. Release içinde venv kurulur, `pip install -r requirements.txt` çalıştırılır.
  3. `pytest` çalıştırılır. Testler geçmezse dağıtım durur ve `current` değişmez.
  4. **Geçişten önce zorunlu yedek:** `sqlite3 .backup` alınır.
  5. Veritabanı geçişi yapılır. Geçişler `gecisler/NNN_ad.sql` biçiminde numaralı SQL dosyalarıdır, uygulananlar `sema_surumu` tablosunda tutulur.
     - Mockup boyunca **yalnız geriye uyumlu** geçiş yazılır: tablo veya kolon eklenir, silinmez ve yeniden adlandırılmaz. Böylece önceki release yeni şemayla çalışabilir.
  6. `current` bağlantısı yeni release'e çevrilir ve servis yeniden başlatılır.
  7. Sağlık kontrolü (`/saglik`) başarısız olursa `current` önceki release'e döner. Gerekirse 4. adımdaki yedek elle geri yüklenir.
- **Yedek:** Her gece 03:00'te `cr-shop-yedek.timer` ile alınır, son 7 gün `yedek/` altında tutulur.
- **Kaynak sınırı:** Servis için `MemoryMax=600M`; diğer iki demo etkilenmez.
- **Kayıt:** Kurulum sonunda adres, servis ve kural bilgileri hive `hosts/machines.md` dosyasına ve Vault `08-Website/` altına işlenir.

## 9. Hata durumları

| Durum | Davranış |
|---|---|
| Public API erişilemiyor / zaman aşımı | Son başarılı veriyle devam edilir; eşitleme günlüğünde hata, yönetim panelinde uyarı |
| Kur alınamadı | Son kur kullanılır, fiyatın altında kur tarihi kırmızı gösterilir |
| Görsel 404 | Kategori yer tutucusu |
| Teklif zorunlu ürün sepete eklenmek istendi | 409 + teklif formuna yönlendirme |
| Stok 0 ürün sepette | Ödemede uyarı; sipariş alınır, "tedarik süresi sipariş sonrası teyit edilecek" notu düşer |
| Ödeme formu iki kez gönderildi | İşlem anahtarı aynı → ilk denemenin sonucu döner, yeni deneme başlamaz |
| İzinsiz durum geçişi | 409, durum değişmez |
| Ödeme reddi (test kartı) | Kullanıcıya anlaşılır mesaj; sepet korunur, sipariş `odeme_bekliyor` kalır |
| CSRF / oturum süresi doldu | 403 hata sayfası: "Oturum süresi doldu, sayfayı yenileyip tekrar deneyin" |
| Beklenmeyen hata | 500 sayfası (Türkçe/İngilizce) + hata kimliği; ayrıntı sadece sunucu loglarında |

## 10. Test

- **Test veritabanı:** `pytest` her testte geçici bir SQLite dosyası kullanır (`tmp_path`). Canlı `shop.db`'ye ve ağa dokunmaz; public API ve TCMB yanıtları kayıtlı örnek dosyalardan okunur.
- **Birim testleri (pytest):**
  - Fiyat ve para birimi kuralları: §5.3 tablosundaki her satır (müşteri tipi × teslimat ülkesi) ayrı bir test.
  - Teklif kuralı: robot kökü ve 15.000 € eşiği; eşiğin tam sınırı dahil.
  - Satır bazında yuvarlama sırası: bilinen bir örnekte beklenen kuruşa kadar sonuç.
  - Ödeme anında kur sabitleme ve kur değiştiğinde fark onayının istenmesi.
  - VKN ve TCKN doğrulaması: geçerli ve geçersiz örnekler.
  - Temsili fiyatın deterministik olması.
  - Eşitleme:
    - Normalleştirme ve upsert.
    - Tam turda kaybolan ürünün `aktif=0` olması.
    - **Eksik turda hiçbir ürünün pasife alınmaması.**
  - Kur yedeği (kur alınamazsa son kur).
  - İzinli ve izinsiz sipariş durum geçişleri (izinsizde 409).
  - Çift gönderim: aynı işlem anahtarıyla ikinci istekte yeni deneme başlamaması.
  - Ret sonrası aynı siparişle yeniden deneme; 30 dakika sonra `iptal`.
  - Misafir sepetinin girişte birleşmesi.
  - Açık yönlendirme engeli (`sonraki=https://…` reddedilir).
  - Giriş deneme sınırı (11. denemede 429).
  - Test kartı dışındaki kartın reddedilmesi.
  - Kontrol testleri: **başarısız olması gereken** vakalar da eklenir (ör. teklif zorunlu ürünün sepete girememesi) ve gerçekten başarısız oldukları görülür.
- **Entegrasyon:** FastAPI TestClient ile tüm rotalar; CSRF ve oturum dahil.
- **Uçtan uca (Playwright, staging'e karşı):** §11'deki 4 senaryo, TR/EN geçişi, 360 px mobil ekran görüntüleri ve JS konsolunda hata olmaması.
- **Duman testi:** Kurulumdan sonra `/saglik`, ana sayfa, bir ürün ve sepet 200 dönmeli.

## 11. Kabul ölçütleri

**"Yardımsız" tanımı:** Bir gözlemci yanında olur ama ipucu vermez. Her senaryo için süre sınırı 10 dakikadır. Kullanıcı takılırsa bu bir bulgu olarak kaydedilir.

1. **Bireysel TR siparişi:** Ürün aranır, sepete eklenir, fiyat TRY ve KDV dahil görünür. Kayıt olunur, sözleşmeler onaylanır, test kartıyla ödeme yapılır, "Hesabım"da sipariş görülür.
2. **Kurumsal TR siparişi:** Geçerli bir VKN ile kayıt olunur. Fiyat EUR ve KDV hariç, TRY karşılığıyla görünür. Ödeme ret kartıyla reddedilir, ardından başarılı kartla tamamlanır.
3. **Yurt dışı siparişi:** EN arayüz kullanılır. Fiyat EUR olur, KDV yerine ihracat istisnası satırı ve DAP notu görünür.
4. **Teklif:** SKU `8301033800019` (KUKA KRC5 KR 140 R3200-2 PA) ürününde sepet düğmesi yerine "Teklif iste" görünür. Form gönderilir, teklif yönetim panelinde listelenir.
5. **Katalog ve kayıt:**
   - Son **tam** eşitlemede `aktif=1` ürün sayısı, API'nin bildirdiği `total` değerinden atlanan bozuk kayıt sayısı çıkarılarak bulunan değere eşit olmalı (`aktif = api_toplam − bozuk`).
   - Yönetim panelinde son başarılı eşitlemenin zamanı görünmeli.
   - Geri bildirim gönderilince yönetim panelinde görünmeli.
6. **Sunucu ve diğer demolar:**
   - Port 80 ve 3027'deki demolar kurulumdan önce ve sonra 200 dönmeli.
   - Tepe bellek değerleri sınırın altında kalmalı (`MemoryPeak` özelliği VM'deki systemd 255'te var, 12.10'da doğrulandı):
     - `cr-shop-esitle.service`: tam bir eşitleme turundan sonra `MemoryPeak` < 400 MB.
     - `cr-shop-demo.service`: uçtan uca testlerden sonra `MemoryPeak` < 600 MB.
     - Eşitleme sürerken `free -m` ile ölçülen kullanılan bellek < 1.500 MB.
7. **Güvenlik:**
   - Yanıtlarda CSP başlığı bulunmalı.
   - Sayfalarda satır içi `<script>` olmamalı; Playwright testi bunu doğrular.
   - Test kartları dışındaki bir kart numarası reddedilmeli.
8. **Bağımsız değerlendirme:** Ağırlıklı ortalama ≥ 8,5/10 olmalı. Rubrik:

   | Eksen | Ağırlık |
   |---|---|
   | Kabul senaryoları (1–4) eksiksiz çalışıyor | %25 |
   | İş kuralları doğru (fiyat/KDV/kur/teklif; birim testleri dahil) | %20 |
   | Görsel kalite ve tutarlılık (kurumsal tema, mobil 360 px) | %15 |
   | Kullanılabilirlik (gezinme, hata mesajları, TR/EN) | %15 |
   | Güvenlik ve sağlamlık (§5.5, §9) | %15 |
   | İşletme (dağıtım, geri dönüş, yedek, eşitleme günlüğü) | %10 |

## 12. Orkestrasyon (uygulama nasıl yürütülecek)

- **Faz 0 (yönetici, seri):**
  - Depo iskeleti, modül arayüzleri (fonksiyon imzaları ve veri modeli) ve tasarım tokenları.
  - VM ön koşulları: venv, kullanıcı, servis, ufw. Bunlar sudo gerektirir; uygulamadan önce kullanıcıya gösterilir.
- **Faz 1 (paralel ajanlar):**
  - (a) Eşitleme ve katalog veri katmanı.
  - (b) Fiyat, para birimi ve kur.
  - (c) Şablon iskeleti ve tema.
  - (d) TR/EN yasal metin taslakları.
- **Faz 2 (paralel ajanlar):**
  - (e) Katalog ekranları ve arama.
  - (f) Hesap, sepet ve ödeme simülasyonu.
  - (g) Teklif, geri bildirim ve yönetim paneli.
- **Faz 3:**
  - Entegrasyon ve dağıtım.
  - Playwright uçtan uca testleri.
  - Bağımsız değerlendirme. Puan 8,5'in altındaysa düzeltme turu yapılır ve tekrar değerlendirilir.
- **Kurallar:**
  - Her ajan yalnız kendi modül klasörüne yazar; ortak arayüzü değiştirmek yöneticinin onayına bağlıdır.
  - Her ajanın çıktısı yönetici tarafından test çalıştırılarak doğrulanır.
  - Ajanlar Vault'a dokunmaz. VM'e yalnız `dagitim/test-vm.sh` üzerinden (çalışma ağacı başına ayrı test klasörü) erişirler; kurulum adımları yöneticidedir.
  - Ortak dosyalara (dil JSON'ları, site.css, makrolar, conftest) dokunan görevler seri çalışır; ayrıntı planın "Yürütme sırası" bölümünde.

## 13. Riskler ve açık sorular

**Riskler:**
- **Katalog içeriği zayıf:** Görsel, açıklama ve fiyat çoğunlukla yok. Bu yüzden mockup "boş" görünebilir. Önlem: yer tutucu çizimler, temsili fiyat ve gösterim için 10–20 üründe örnek içerik (açıkça "örnek" etiketli).
- **Public API yavaş veya değişebilir:** API ajansın kontrolünde. Önlem: yerel kopya; gerçek sitede kaynak Netsis olacak.
- **Satış ekibi demoyu gerçek sanabilir:** Önlem: her sayfada "DEMO" bandı ve temsili fiyat rozeti.
- **sudo parolası Excel'deki ile tutmazsa** kurulum gecikir. Önlem: §8'deki yedek yol.

**Açık sorular (mockup'ı engellemez, gerçek site öncesi kapanmalı):**
1. **Netsis'ten fiyat, stok ve durum okuma:** Salt okunur bir SQL kullanıcısı ve `mx_b2b_urunler_vw` benzeri bir görünüm gerekiyor. Fiyat listesinin hangisi olacağına muhasebe karar vermeli.
2. **Ödeme kuruluşu:** iyzico, PayTR, Sipay ve banka döviz POS'undan yazılı teklif alınmalı (EUR tahsilat ve komisyon).
3. **Hukuk:** Yasal metinler SY Hukuk'a onaylatılmalı. B2B garanti sınırlaması ve "olduğu gibi" satış maddeleri de bunun içinde.
4. **Muhasebe ve mali müşavir:** e-Arşiv/e-Fatura akışı, ihracat faturası, ETBİS kaydı, VERBİS durumu.
5. **İçerik:** 2. el ürünlerde durum ve test bilgisini kim girecek? Görselleri kim çekecek?
