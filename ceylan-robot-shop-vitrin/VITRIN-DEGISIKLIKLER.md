# Vitrin değişiklikleri

Güvenli kopya. Canlı mağaza, ödeme ve Netsis yazması yok. Kaynak sürüm `SURUM` = `eb799f1` (release 20261014-0423). Demo bandı duruyor.

## Ne değişti

- Kahraman tam genişlik: `app/web/statik/vitrin/hero.jpg` (ceylanrobot.com kahraman görseli). Beyaz başlık, turuncu tek eylem “Ürünleri keşfet” (`/tr/urunler`). İkinci arama formu yok; parça araması üst çubukta.
- Renkler ceylanrobot.com ailesi: turuncu `#fa5f0b`, lacivert `#02111e`. Zeytin ve kiremit kalktı. Turuncu üstündeki küçük yazı lacivert; beyaz üstünde turuncu küçük metin kontrastı yetmediği için.
- Kategori kartları fotoğraf kapak: `app/web/statik/vitrin/kapak-*.jpg|webp` (canlı sitedeki çözüm ve ürün görselleri). Çizgi SVG yer tutucular ürün sayfasında, görseli olmayan parça için duruyor.
- Stoktaki öne çıkanlar büyük ızgara. Görseli olmayan kart, kök kategorinin kapağını gösterir ve “Temsili görsel” yazar.
- “Temsili fiyat” tutarın üstünde (kart, liste, ürün, karşılaştırma). Öne çıkanların üstünde de bir cümle var.
- Güven şeridi: test edilmiş stok, ihracat, satış telefonu (`SHOP_TELEFON`, varsayılan `+90 (332) 239 15 75`), garanti, iade.
- Alt bilgi: künyedeki adres (`K.O.S.B. 3. Sk., No: 7, 42250 Selçuklu / Konya`), aynı telefon, çalışma saatleri. E-posta yalnız `SHOP_EPOSTA` doluysa. İkinci telefon eklenmedi.

## Yerelde çalıştırma

Önerilen port **3031** (yayındaki 3030’a dokunmamak için). Yalnız bu makine:

```bash
cd ceylan-robot-shop-vitrin
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export SHOP_DB="$PWD/veri/shop.db"
export SHOP_GIZLI_ANAHTAR="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
export SHOP_YONETICI='yonetici'
export SHOP_YONETICI_OZET="$(.venv/bin/python -c 'from app.hesap.servis import parola_ozeti; print(parola_ozeti("yerel-demo-parola"))')"
export SHOP_YAYIN_MODU='demo'
export SHOP_SITE_KOK='http://127.0.0.1:3031'
mkdir -p veri
.venv/bin/uvicorn --factory app.web.asgi:uygulama --host 127.0.0.1 --port 3031
```

İsteğe bağlı: `SHOP_TELEFON` (boş değer telefon satırını kapatır), `SHOP_EPOSTA`. Varsayılan telefon `+90 (332) 239 15 75`.

Boş veritabanında kategori ve ürün çıkmaz; şema ilk açılışta kurulur. Katalog, eşitleme betiğiyle doldurulur (`betikler/`, `SHOP_KAYNAK_API`). Eşitleme çalıştırmadan vitrin iskeleti (kahraman, renk, alt bilgi) yine görünür.

Test: `.venv/bin/python -m pytest`

## Bilerek duranlar

Gerçek tahsilat, Netsis yazması, internete açma, demo bandının kaldırılması. Liste sayfası masaüstünde tablo olarak kaldı (48 px küçük görsel liste akışının parçası); ana sayfadaki öne çıkanlar büyük ızgara.
