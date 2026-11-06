"""G3j: persona tur 5 — A: hatalar (1–8), B: yerleşim ve kalan UX (9–18)."""
import re
from datetime import UTC, datetime
from html import unescape
from pathlib import Path

import pytest

from app.fiyat.kurallar import MusteriTipi
from app.katalog.indeks import indeksi_yeniden_kur
from tests.conftest import csrf_al, istemci_db, oturum_oku, sayfa_denetle  # noqa: F401
from tests.test_web_g3e import _odenmis_siparis
from tests.test_web_sepet_odeme import (GECERLI_VKN, PAROLA, _adres_formu, _giris, _gizli, _kart_ode, _kur,  # noqa: F401
                                        _musteri, _odeme_gonder, _sepete_ekle, _siparis_no, _sms, _urun, db)

KOK = Path(__file__).resolve().parent.parent


def _metin(parca):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", parca))).strip()


def _satir(html, uid):
    return re.search(rf'<tr class="ut-satir[^"]*" id="urun-{uid}">.*?</tr>', html, re.S).group(0)


def _satirlar(html):
    return [unescape(re.sub(r"<[^>]+>", "", m)) for m in re.findall(r'data-e2e="urun-baglanti">(.*?)</a>', html)]


def _yonetici(istemci):
    csrf = csrf_al(istemci, "/yonetim/giris")
    r = istemci.post("/yonetim/giris", data={"kullanici": "yonetici", "parola": "yonetici-parola-123", "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 303


def _hizli(istemci, yol="/tr/teklif", **ek):
    csrf = csrf_al(istemci, yol)
    veri = {"csrf": csrf, "ad": "Teknisyen", "iletisim": "+90 532 000 00 00", "parca_kodu": "KPS-600/20"}
    veri.update(ek)
    return istemci.post("/tr/teklif/hizli", data=veri, follow_redirects=False)


def _css():
    return (KOK / "app/web/statik/site.css").read_text(encoding="utf-8")


def _ulke_ve_fiyat(istemci, ulke, fiyat, dil="tr"):
    csrf = csrf_al(istemci, f"/{dil}/urunler")
    istemci.post("/tercih", data={"csrf": csrf, "ulke": ulke, "fiyat": fiyat, "sonraki": f"/{dil}/urunler"})


def _bildirimler(html):
    m = re.search(r'<div class="bildirimler" role="status">(.*?)</div>', html, re.S)
    return _metin(m.group(1)) if m else ""


# =====================================================================================================
# A1 — hızlı talep katalog eşleşmesi
# =====================================================================================================

def test_g3j_hizli_talep_katalogda_tek_eslesme(istemci, db):
    _kur(db)
    uid = _urun(db, sku="8501010100034", ad="KUKA KRC4 ROBOT KUMANDASI", uretici_kodu="00-168-334", fiyat="100.00",
                stok=2)
    r = _hizli(istemci, parca_kodu="00 168 334", aciliyet="acil")
    assert r.status_code == 303
    t = db.execute("SELECT urun_id, mesaj FROM teklif ORDER BY id DESC").fetchone()
    assert t["urun_id"] == uid and "bulunamadı" not in t["mesaj"]
    assert "katalogda bulundu: KUKA KRC4 ROBOT KUMANDASI" in t["mesaj"]
    html = sayfa_denetle(istemci.get(r.headers["location"]))
    blok = re.search(r'<section class="katalog-eslesme"[^>]*>(.*?)</section>', html, re.S).group(1)
    assert "Katalogda bulundu: KUKA KRC4 ROBOT KUMANDASI (stokta 2)" in _metin(blok)
    assert f'href="/tr/urun/{uid}"' in blok
    assert "Doğrudan sipariş verebilirsiniz" in _metin(blok)
    assert "katalogda bulunamadı" not in _metin(html)
    # yönetim: talep satırında ürün bağlantısı
    _yonetici(istemci)
    yon = istemci.get("/yonetim/teklifler").text
    assert f'href="/tr/urun/{uid}"' in yon


def test_g3j_hizli_talep_kod_sku_ve_ad_icinde(istemci, db):
    # SKU ile tam eşleşme; addaki kod jetonu (katlanmış, kelime sınırında) ile tam eşleşme
    u1 = _urun(db, sku="KPS-600/20-ESC", ad="KUKA GÜÇ KAYNAĞI", fiyat="10.00", stok=0)
    u2 = _urun(db, sku="8503033800001", ad="KUKA ECMBP0D3004BE531 KPP-600-20 GÜÇ KAYNAĞI", fiyat="10.00", stok=1)
    r = _hizli(istemci, parca_kodu="kps600/20esc")
    html = _metin(istemci.get(r.headers["location"]).text)
    assert "Katalogda bulundu: KUKA GÜÇ KAYNAĞI (stokta yok)" in html
    assert "Doğrudan sipariş verebilirsiniz" not in html                  # stokta yok: doğrudan sipariş bağlantısı yok
    assert db.execute("SELECT urun_id FROM teklif ORDER BY id DESC").fetchone()[0] == u1
    r = _hizli(istemci, parca_kodu="KPP 600 20")
    assert db.execute("SELECT urun_id FROM teklif ORDER BY id DESC").fetchone()[0] == u2
    r = _hizli(istemci, parca_kodu="KPP-600")                              # kodun bir parçası: tam eşleşme değil
    assert db.execute("SELECT urun_id FROM teklif ORDER BY id DESC").fetchone()[0] is None


def test_g3j_hizli_talep_birden_cok_eslesme_ve_bulunamadi(istemci, db):
    a = _urun(db, sku="8503033800001", ad="KUKA ECMBP0D3004BE531 KPP-600-20 GÜÇ KAYNAĞI", uretici_kodu="00198259",
              fiyat="10.00", stok=1)
    b = _urun(db, sku="8503033800002", ad="KUKA ECMAP0D3004BE531 KPP-600-20 GÜÇ KAYNAĞI", uretici_kodu="00198259",
              fiyat="10.00", stok=3)
    r = _hizli(istemci, parca_kodu="00198259")
    t = db.execute("SELECT urun_id, mesaj FROM teklif ORDER BY id DESC").fetchone()
    assert t["urun_id"] is None and "katalogda 2 eşleşme" in t["mesaj"] and "bulunamadı" not in t["mesaj"]
    html = istemci.get(r.headers["location"]).text
    blok = re.search(r'<section class="katalog-eslesme"[^>]*>(.*?)</section>', html, re.S).group(1)
    assert "Katalogda 2 eşleşme bulundu" in _metin(blok)
    assert f'href="/tr/urun/{a}"' in blok and f'href="/tr/urun/{b}"' in blok
    assert "(stokta 1)" in _metin(blok) and "(stokta 3)" in _metin(blok)
    _yonetici(istemci)
    yon = istemci.get("/yonetim/teklifler").text
    assert f'href="/tr/urun/{a}"' in yon and f'href="/tr/urun/{b}"' in yon
    istemci.cookies.clear()
    r = _hizli(istemci, parca_kodu="XYZ-999-QQ")
    assert "katalogda bulunamadı" in db.execute("SELECT mesaj FROM teklif ORDER BY id DESC").fetchone()[0]
    html = istemci.get(r.headers["location"]).text
    assert 'class="katalog-eslesme"' not in html


# =====================================================================================================
# A2 — acil talep: telefon zorunlu, 1 saat içinde telefonla dönüş (temsili)
# =====================================================================================================

def test_g3j_acil_talep_telefon_zorunlu_ve_onay_metni(istemci, db):
    r = _hizli(istemci, aciliyet="acil", iletisim="teknisyen@ornek.test")
    assert r.status_code == 400 and 'id="hata-iletisim"' in r.text
    assert "telefon" in _metin(re.search(r'id="hata-iletisim">(.*?)</p>', r.text, re.S).group(1)).lower()
    r = _hizli(istemci, aciliyet="acil")
    assert r.status_code == 303
    onay = _metin(istemci.get(r.headers["location"]).text)
    assert "Çalışma saatlerinde 1 saat içinde telefonla dönüş (temsili)" in onay
    assert "1 iş günü" not in onay
    r = _hizli(istemci, aciliyet="planli", iletisim="teknisyen@ornek.test")       # acil değil: e-posta yeterli
    assert r.status_code == 303
    onay = _metin(istemci.get(r.headers["location"]).text)
    assert "1 iş günü" in onay and "1 saat içinde" not in onay
    en = _hizli(istemci, aciliyet="acil")
    assert "within 1 hour during business hours" in _metin(istemci.get(
        en.headers["location"].replace("/tr/", "/en/")).text)
    notlar = (KOK / "docs/hukuk-notlari.md").read_text(encoding="utf-8")
    assert "1 saat içinde telefonla dönüş" in notlar


# =====================================================================================================
# A3 — fatura bilgileri: gömülü hesap profile yazar; boş profil son siparişten ön dolar
# =====================================================================================================

def test_g3j_gomulu_hesap_fatura_bilgileri_dolu(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-GF1", ad="Gömülü Ürün", fiyat="10.00", stok=5)
    _sepete_ekle(istemci, uid)
    sayfa = istemci.get("/tr/odeme").text
    form = _adres_formu(teslimat_telefon="+90 332 111 22 33")
    form.update({"hesap_tip": "kurumsal", "hesap_eposta": "gf@ornek.test", "hesap_parola": PAROLA,
                 "hesap_kvkk_onay": "1", "hesap_firma": "Anadolu Otomasyon A.Ş.", "hesap_vkn": GECERLI_VKN,
                 "hesap_vergi_dairesi": "Meram"})
    for ad in ("csrf", "gosterilen_toplam", "gosterilen_kur"):
        form[ad] = _gizli(sayfa, ad)
    assert istemci.post("/tr/odeme", data=form, follow_redirects=False).status_code == 303
    html = istemci.get("/tr/hesabim/fatura").text
    for ad, deger in (("ad", "Anadolu Otomasyon A.Ş."), ("vergi_dairesi", "Meram"),
                      ("satir1", "Test Mah. Deneme Sk. No: 1"), ("sehir", "Konya"), ("telefon", "+90 332 111 22 33")):
        assert re.search(rf'name="{ad}" type="\w+" value="{re.escape(deger)}"', html), ad


def test_g3j_bos_profil_son_siparisten_on_dolar(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-GF2", ad="Ön Dolum Ürünü", fiyat="10.00", stok=5)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="od@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    _giris(istemci, "od@ornek.test")
    _sepete_ekle(istemci, uid)
    assert _odeme_gonder(istemci, teslimat_telefon="+90 332 444 55 66").status_code == 303
    with db:                                       # eski hesap: profilde adres kaydı yok, yalnız siparişte
        db.execute("DELETE FROM adres")
    html = istemci.get("/tr/hesabim/fatura").text
    assert re.search(r'name="satir1" type="text" value="Test Mah. Deneme Sk. No: 1"', html)
    assert re.search(r'name="sehir" type="text" value="Konya"', html)
    assert re.search(r'name="telefon" type="tel" value="\+90 332 444 55 66"', html)
    assert db.execute("SELECT COUNT(*) FROM adres").fetchone()[0] == 0          # kaydetmeden


# =====================================================================================================
# A4 — KDV oranı anomalileri
# =====================================================================================================

def test_g3j_gecersiz_kdv_orani_teklifle(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-KDV80", ad="Seksen KDVli Silindir", fiyat="100.00", stok=4, kdv="80")
    liste = sayfa_denetle(istemci.get("/tr/urunler"))
    satir = _satir(liste, uid)
    assert "Fiyat teklifle (KDV oranı teyit ediliyor)" in _metin(satir)
    assert 'action="/tr/sepet/ekle"' not in satir and f'/tr/teklif?urun_id={uid}' in satir
    urun = sayfa_denetle(istemci.get(f"/tr/urun/{uid}"))
    assert "Fiyat teklifle (KDV oranı teyit ediliyor)" in _metin(urun)
    assert 'data-e2e="sepete-ekle"' not in urun and 'data-e2e="fiyat-ana"' not in urun
    csrf = csrf_al(istemci, f"/tr/urun/{uid}")
    istemci.post("/tr/sepet/ekle", data={"csrf": csrf, "urun_id": str(uid), "adet": "1"}, follow_redirects=False)
    assert db.execute("SELECT COUNT(*) FROM sepet_kalemi").fetchone()[0] == 0
    assert db.execute("SELECT kdv_orani FROM urun WHERE id = ?", (uid,)).fetchone()[0] == "80"   # veri değişmez


@pytest.mark.parametrize("kdv,etiket", [("1", "KDV %1"), ("0", "KDV %0"), ("10", "KDV %10")])
def test_g3j_yirmi_disi_kdv_etiketi(istemci, db, kdv, etiket):
    _kur(db)
    uid = _urun(db, sku="S-KDVX", ad="Düşük KDVli Kablo", fiyat="100.00", stok=4, kdv=kdv)
    yirmi = _urun(db, sku="S-KDV20", ad="Normal Ürün", fiyat="100.00", stok=4)
    liste = istemci.get("/tr/urunler").text
    assert etiket in _metin(_satir(liste, uid)) and "KDV %" not in _metin(_satir(liste, yirmi))
    assert etiket in _metin(re.search(r'<div class="fiyat-blok">.*?</div>', istemci.get(f"/tr/urun/{uid}").text,
                                      re.S).group(0))
    _sepete_ekle(istemci, uid)
    sepet = istemci.get("/tr/sepet").text
    assert etiket in _metin(re.search(r'<tr data-e2e="sepet-kalemi">.*?</tr>', sepet, re.S).group(0))
    _ulke_ve_fiyat(istemci, "TR", "try", "en")                        # EN arayüz, Türkiye teslimi
    assert f"VAT {kdv}%" in _metin(re.search(r'<div class="fiyat-blok">.*?</div>', istemci.get(f"/en/urun/{uid}").text,
                                             re.S).group(0))


def test_g3j_veri_kalitesi_sayfasi(istemci, db):
    assert istemci.get("/yonetim/veri-kalitesi", follow_redirects=False).status_code == 303   # yetkisiz
    k80 = _urun(db, sku="S-VK80", ad="Seksenli", fiyat="10.00", kdv="80")
    k1 = _urun(db, sku="S-VK1", ad="Birli", fiyat="11.00", kdv="1")
    ayni = [_urun(db, sku=f"S-AF{i}", ad=f"Aynı Fiyat {i}", fiyat="110.41") for i in range(3)]
    iki = [_urun(db, sku=f"S-IF{i}", ad=f"İki Fiyat {i}", fiyat="50.00") for i in range(2)]
    kod = [_urun(db, sku=f"S-UK{i}", ad=f"Aynı Kod {i}", fiyat=f"{20 + i}.00", uretici_kodu="00198259")
           for i in range(2)]
    _yonetici(istemci)
    html = sayfa_denetle(istemci.get("/yonetim/veri-kalitesi"))
    assert 'href="/yonetim/veri-kalitesi"' in html                        # menüde
    kdv = re.search(r'<section[^>]*data-e2e="vk-kdv".*?</section>', html, re.S).group(0)
    assert f'href="/tr/urun/{k80}"' in kdv and f'href="/tr/urun/{k1}"' in kdv and "80" in _metin(kdv)
    assert re.search(r'<span class="yonetim-sayac">2</span>', kdv)            # inceleme M-7: sayaç (başlıkta "%20" var)
    fiyat = re.search(r'<section[^>]*data-e2e="vk-fiyat".*?</section>', html, re.S).group(0)
    assert all(f'href="/tr/urun/{i}"' in fiyat for i in ayni)
    assert not any(f'href="/tr/urun/{i}"' in fiyat for i in iki)         # 2 ürünlü grup eşik altında
    kodlar = re.search(r'<section[^>]*data-e2e="vk-kod".*?</section>', html, re.S).group(0)
    assert all(f'href="/tr/urun/{i}"' in kodlar for i in kod) and "00198259" in kodlar


# =====================================================================================================
# A5 — "Stokta" = alınabilir stok; tümü ayrılmışlar "Ayrılmış (yakında serbest)"
# =====================================================================================================

def _stok_faseti(html):
    faset = re.search(r'data-faset="stok">.*?</fieldset>', html, re.S).group(0)
    return {d: int(n) for d, n in re.findall(r'name="(\w+)" value="1"(?: checked)?> <span class="faset-ad">[^<]*</span> '
                                              r'<span class="faset-sayi">(\d+)</span>', faset)}


def test_g3j_stokta_faseti_alinabilir_stok(istemci, db):
    _kur(db)
    serbest = _urun(db, sku="S-ST1", ad="SIEMENS Serbest", fiyat="10.00", stok=2)
    ayrilmis = _urun(db, sku="S-ST2", ad="SIEMENS Ayrılmış", fiyat="10.00", stok=1)
    kismi = _urun(db, sku="S-ST3", ad="SIEMENS Kısmen", fiyat="10.00", stok=3)
    tedarik = _urun(db, sku="S-ST4", ad="SIEMENS Tedarik", fiyat="10.00", stok=0)
    _odenmis_siparis(db, ayrilmis, 1, datetime.now(UTC).isoformat())
    _odenmis_siparis(db, kismi, 2, datetime.now(UTC).isoformat(), eposta="o2@ornek.test")
    html = sayfa_denetle(istemci.get("/tr/urunler"))
    sayilar = _stok_faseti(html)
    assert sayilar == {"stokta": 2, "ayrilmis": 1, "tedarikli": 1}
    assert sum(sayilar.values()) == 4 == int(re.search(r'<p class="sonuc-sayisi">(\d+)', html).group(1))
    # G3m madde 11: etiket "Ayrılmış — en geç N iş gününde serbest"
    assert "Ayrılmış — en geç 3 iş gününde serbest" in _metin(re.search(r'data-faset="stok">.*?</fieldset>', html,
                                                                        re.S).group(0))
    stokta = istemci.get("/tr/urunler", params={"stokta": "1"}).text
    assert sorted(_satirlar(stokta)) == ["SIEMENS Kısmen", "SIEMENS Serbest"]
    assert "tümü açık siparişlerce ayrılmış" not in stokta
    hizli = re.search(r'<ul class="hizli-cipler".*?</ul>', html, re.S).group(0)
    assert re.search(r'Stokta <span class="sayi">2</span>', hizli)
    ayr = istemci.get("/tr/urunler", params={"ayrilmis": "1"}).text
    assert _satirlar(ayr) == ["SIEMENS Ayrılmış"] and "Ayrılmış — en geç 3 iş gününde serbest" in _metin(ayr)
    iki = istemci.get("/tr/urunler", params={"stokta": "1", "ayrilmis": "1"}).text
    assert len(_satirlar(iki)) == 3
    # faset toplamları marka seçiliyken de tutarlı
    html = istemci.get("/tr/urunler", params={"marka": "Siemens"}).text
    assert sum(_stok_faseti(html).values()) == int(re.search(r'<p class="sonuc-sayisi">(\d+)', html).group(1))
    assert tedarik and serbest


# =====================================================================================================
# A6 — kod biçimli sorgu
# =====================================================================================================

@pytest.fixture
def mlfb(istemci):
    with istemci_db(istemci) as con:
        from tests.conftest import urun_ekle
        urun_ekle(con, sku="S-HOH", ad="HOHNER DÖNER ENCODER PROFİNET", uretici_kodu="CM10-214X-1314.KT", stok=5)
        urun_ekle(con, sku="S-307", ad="SIEMENS SIMATIC PS 307", uretici_kodu="6ES7307-1EA01-0AA0", stok=2)
        urun_ekle(con, sku="S-361", ad="SIEMENS SIMATIC S7-300", uretici_kodu="6ES7361-3CA01-0AA0", stok=2)
        urun_ekle(con, sku="S-K214", ad="KABLO 214 MM", stok=2)
        indeksi_yeniden_kur(con)
    return istemci


def test_g3j_kod_sorgusu_bitisik_onek(mlfb):
    with istemci_db(mlfb) as con:
        from tests.conftest import urun_ekle
        urun_ekle(con, sku="S-214", ad="SIEMENS S7-1200 CPU 1214C", uretici_kodu="6ES7214-1AG40-0XB0", stok=1)
        indeksi_yeniden_kur(con)
    for q in ("6ES7 214", "6es7214"):
        html = sayfa_denetle(mlfb.get("/tr/ara", params={"q": q}))
        adlar = _satirlar(html)
        assert adlar and adlar[0] == "SIEMENS S7-1200 CPU 1214C", (q, adlar)
        assert "HOHNER DÖNER ENCODER PROFİNET" not in adlar and "KABLO 214 MM" not in adlar


def test_g3j_kod_sorgusu_sonucsuz_gevsetmez(mlfb):
    html = sayfa_denetle(mlfb.get("/tr/ara", params={"q": "6ES7 214"}))
    assert _satirlar(html) == []
    assert 'class="gevset"' not in html and "HOHNER" not in html
    blok = re.search(r'<div class="kod-yok"[^>]*>(.*?)</div>', html, re.S).group(1)
    assert "“6ES7 214” koduyla ürün yok" in _metin(blok)
    seri = re.search(r'<a href="([^"]+)"[^>]*>(Aynı seri[^<]*)</a>', blok)
    assert seri and seri.group(2) == "Aynı seri (6ES7) — 2 ürün" and "q=6ES7" in seri.group(1)
    teklif = re.search(r'<a href="([^"]+)"[^>]*>Parçayı bizim için bulun</a>', blok)
    assert teklif and unescape(teklif.group(1)) == "/tr/teklif?kod=6ES7+214"
    assert 'name="parca_kodu" value="6ES7 214"' in html                    # hızlı talep formu da dolu
    html = mlfb.get("/tr/ara", params={"q": "6es7214"}).text
    assert "Aynı seri (6ES7) — 2 ürün" in _metin(html)
    en = mlfb.get("/en/ara", params={"q": "6ES7 214"}).text
    assert "No product with the code “6ES7 214”" in _metin(en) and "Same series (6ES7) — 2 products" in _metin(en)
    # kod jetonu yoksa G3h gevşetmesi aynen
    html = mlfb.get("/tr/ara", params={"q": "simatic hohner"}).text
    assert 'class="gevset"' in html


# =====================================================================================================
# A7 — alaka katmanları
# =====================================================================================================

def test_g3j_alaka_tum_terimler_adda_once(istemci):
    with istemci_db(istemci) as con:
        from tests.conftest import urun_ekle
        a = urun_ekle(con, sku="S-GK1", ad="SIEMENS SITOP SEÇİCİLİK MODÜLÜ", stok=1)     # tip: güç kaynağı (sitop)
        b = urun_ekle(con, sku="S-GK2", ad="MEANWELL GÜÇ KAYNAĞI BAĞLANTI KABLOSU", stok=1)
        indeksi_yeniden_kur(con)
        con.execute("UPDATE urun_ara SET kategori = 'guc kaynaklari' WHERE urun_id = ?", (a,))
        assert con.execute("SELECT tip FROM urun WHERE id = ?", (a,)).fetchone()[0] == "guc_kaynagi"
        assert con.execute("SELECT tip FROM urun WHERE id = ?", (b,)).fetchone()[0] != "guc_kaynagi"
    html = istemci.get("/tr/ara", params={"q": "güç kaynağı"}).text
    assert _satirlar(html) == ["MEANWELL GÜÇ KAYNAĞI BAĞLANTI KABLOSU", "SIEMENS SITOP SEÇİCİLİK MODÜLÜ"]


def test_g3j_alaka_ve_sonucu_varsa_yalniz_onlar(istemci):
    with istemci_db(istemci) as con:
        from tests.conftest import urun_ekle
        urun_ekle(con, sku="S-RK1", ad="KUKA RESOLVER KABLOSU 10M", stok=1)
        urun_ekle(con, sku="S-RK2", ad="2.0 USB KABLOSU", stok=1)
        urun_ekle(con, sku="S-RK3", ad="KUKA RESOLVER", stok=1)
        indeksi_yeniden_kur(con)
    html = istemci.get("/tr/ara", params={"q": "resolver kablosu"}).text
    assert _satirlar(html) == ["KUKA RESOLVER KABLOSU 10M"] and 'class="gevset"' not in html
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET aktif = 0 WHERE sku = 'S-RK1'")
        indeksi_yeniden_kur(con)
    html = istemci.get("/tr/ara", params={"q": "resolver kablosu"}).text
    assert 'class="gevset"' in html and set(_satirlar(html)) == {"2.0 USB KABLOSU", "KUKA RESOLVER"}


# =====================================================================================================
# A8 — Almanca bileşik terimler
# =====================================================================================================

def test_g3j_almanca_bilesik_terimler(istemci):
    from app.katalog.depo import esanlam_sozlugu
    from app.metin import normalize
    sozluk = esanlam_sozlugu()
    for terim in ("Frequenzumrichter", "Umrichter", "Servoumrichter", "Servoverstärker", "Netzgerät",
                  "Stromversorgung", "Getriebemotor", "Getriebe", "Steuerung", "Bedienpanel", "Drehgeber",
                  "Näherungsschalter", "Schütz", "Relais", "Sicherung", "Kabel"):
        assert (normalize(terim),) in sozluk, terim
    with istemci_db(istemci) as con:
        from tests.conftest import urun_ekle
        urun_ekle(con, sku="S-FK", ad="DANFOSS FREKANS KONVERTÖRÜ", stok=1)
        urun_ekle(con, sku="S-SS", ad="KUKA SERVO SÜRÜCÜ", stok=1)
        urun_ekle(con, sku="S-RL", ad="OMRON RÖLE 24V", stok=1)
        indeksi_yeniden_kur(con)
    assert "DANFOSS FREKANS KONVERTÖRÜ" in _satirlar(istemci.get("/en/ara", params={"q": "Frequenzumrichter"}).text)
    assert "KUKA SERVO SÜRÜCÜ" in _satirlar(istemci.get("/en/ara", params={"q": "Servoumrichter"}).text)
    assert "OMRON RÖLE 24V" in _satirlar(istemci.get("/en/ara", params={"q": "Relais"}).text)


# =====================================================================================================
# B9 — filtre sütunu: gruplar <details>, Uygula yapışkan
# =====================================================================================================

def _grup(html, ad):
    return re.search(rf'<details class="faset-grup" data-grup="{ad}"( open)?>', html)


def test_g3j_filtre_gruplari_details(istemci, db):
    _kur(db)
    with db:
        db.execute("INSERT INTO kategori (kaynak_id, ad, ust_kaynak_id, yol, seviye) VALUES ('k1', 'Elektrik', NULL, '1', 1)")
    kat = db.execute("SELECT id FROM kategori").fetchone()[0]
    for i in range(12):
        _urun(db, sku=f"S-FG{i}", ad=["ABB SERVO MOTOR", "KUKA GÜÇ KAYNAĞI", "FESTO VALF", "SICK SENSÖR",
                                     "OMRON RÖLE", "SMC SİLİNDİR", "FANUC KABLO", "PILZ KONTAKTÖR", "LENZE REDÜKTÖR",
                                     "SIEMENS PLC", "BECKHOFF HMI", "YASKAWA FAN"][i], fiyat="10.00", stok=i % 2,
              kategori_id=kat)
    with db:
        db.execute("UPDATE urun SET durum_kodu = 'yeni' WHERE sku = 'S-FG0'")
        indeksi_yeniden_kur(db)
    html = sayfa_denetle(istemci.get("/tr/urunler"))
    for ad in ("tip", "stok", "marka", "fiyat", "durum"):                     # G3k madde 10: durum da açık
        assert _grup(html, ad) and _grup(html, ad).group(1), ad                 # açık
    for ad in ("kategori",):
        assert _grup(html, ad) and not _grup(html, ad).group(1), ad             # kapalı
    tip = re.search(r'data-faset="tip">.*?</fieldset>', html, re.S).group(0)
    ust = tip.split('<details class="faset-daha"')[0]
    assert len(re.findall(r'name="tip"', ust)) == 4 and "tip daha" in tip      # ilk 4 tip açık (G3k m. 10; önce 6)
    assert re.search(r'<details class="agac-kutu">', html)                     # ağaç tüm ürünlerde kapalı
    html = istemci.get("/tr/urunler", params={"durum": "yeni", "kat": str(kat)}).text
    assert _grup(html, "durum").group(1) and _grup(html, "kategori").group(1)  # seçili değer varsa açık
    # inceleme M-1/M-7: sütunun üstünde ve altında (yapışkan) aynı formun Uygula düğmeleri; yerleşim e2e'de ölçülür
    # (e2e/test_kabul.py::test_g3j_filtre_sutunu_1366_ilk_ekranda_uygula)
    form = re.search(r'<form class="filtre".*?</form>', html, re.S).group(0)
    assert re.search(r'<div class="filtre-ust">\s*<h2 class="yan-baslik">[^<]*</h2>\s*<button class="dugme dugme-kucuk '
                     r'filtre-ust-uygula" type="submit">Uygula</button>', form)
    assert form.index("filtre-ust-uygula") < form.index('data-grup="tip"') < form.index('<div class="dugmeler">')


# =====================================================================================================
# B10 — mobil liste araç çubuğu ve filtre çekmecesi
# =====================================================================================================

def test_g3j_mobil_arac_cubugu_ve_cekmece(istemci, db):
    _urun(db, sku="S-MB1", ad="Mobil Ürün", fiyat="10.00", stok=1)
    html = istemci.get("/tr/urunler").text
    siralama = re.search(r'<form class="siralama".*?</form>', html, re.S).group(0)
    assert '<label for="sira">Sırala</label>' in siralama and '<label for="adet">Sayfa başına</label>' in siralama
    en = istemci.get("/en/urunler").text
    assert '<label for="sira">Sort</label>' in en and '<label for="adet">Per page</label>' in en
    ozet = re.search(r'<details class="cekmece">\s*<summary>(.*?)</summary>', html, re.S).group(1)
    assert '<span class="cekmece-ac">Filtrele</span>' in ozet and '<span class="cekmece-kapat">Kapat</span>' in ozet
    # inceleme M-7: yerleşim (etiketler görünür, fiyat düğmeleri tek satır, çekmecede Uygula/Kapat üstte, yüzen
    # Filtrele gizli) tarayıcıda ölçülür: e2e/test_kabul.py::test_g3j_mobil_360_arac_cubugu_ve_cekmece


# =====================================================================================================
# B11 — karşılaştırma satır sırası
# =====================================================================================================

def test_g3j_karsilastirma_fiyat_once(istemci, db):
    _kur(db)
    with db:
        kat = db.execute("INSERT INTO kategori (kaynak_id, ad, ust_kaynak_id, yol, seviye) VALUES ('ks', 'Sensörler',"
                         " NULL, '9', 1)").lastrowid
    ids = [_urun(db, sku=f"S-KS{i}", ad=f"SIEMENS Karşılaştır {i}", fiyat="10.00", stok=1, uretici_kodu=f"KOD-{i}",
                 kategori_id=kat) for i in range(2)]
    for uid in ids:
        csrf = csrf_al(istemci, "/tr/urunler")
        istemci.post("/tr/karsilastir/ekle", data={"csrf": csrf, "urun_id": str(uid), "sonraki": "/tr/urunler"})
    html = istemci.get("/tr/karsilastir").text
    tbody = re.search(r"<tbody>(.*?)</tbody>", html, re.S).group(1)
    etiketler = [_metin(x) for x in re.findall(r'<th scope="row">(.*?)</th>', tbody, re.S)]
    assert etiketler[:9] == ["Fiyat (KDV hariç)", "Fiyat (KDV dahil)", "Durum", "Stok", "Teslim", "Parça no",
                             "Stok kodu", "Marka", "Kategori"], etiketler
    csv = istemci.get("/tr/karsilastir.csv").text.splitlines()
    # G3k madde 9 / G3m madde 14: CSV düz tablo; sayısal fiyat sütunları ayrı (başlık satırında)
    assert "fiyat_kdv_haric_try" in csv[0].split(";") and len(csv) == 1 + len(ids)


# =====================================================================================================
# B12 — yurt dışı € görünümünde ₺ ikincil ve TCMB kur satırı yok
# =====================================================================================================

def test_g3j_yurtdisi_eur_gorunumunde_tl_yok(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-YD1", ad="Yurt Dışı Ürünü", fiyat="100.00", stok=3)
    _ulke_ve_fiyat(istemci, "DE", "eur", "en")
    urun = istemci.get(f"/en/urun/{uid}").text
    blok = re.search(r'<div class="fiyat-blok">.*?</div>', urun, re.S).group(0)
    assert "₺" not in blok and "kur-satiri" not in blok and "€100.00" in blok
    assert "₺" not in _satir(istemci.get("/en/urunler").text, uid)
    _sepete_ekle(istemci, uid, dil="en")
    sepet = istemci.get("/en/sepet").text
    assert "₺" not in re.search(r'<table class="tablo sepet-tablo sepet-kalemleri">.*?</table>', sepet, re.S).group(0)
    assert 'class="kur-satiri' not in sepet
    # ₺ gösterimi seçilirse ya da ülke TR ise ₺ ikincil/kur yine görünür
    istemci.cookies.clear()
    _ulke_ve_fiyat(istemci, "TR", "eur")
    blok = re.search(r'<div class="fiyat-blok">.*?</div>', istemci.get(f"/tr/urun/{uid}").text, re.S).group(0)
    assert "₺" in blok and "kur-satiri" in blok


# =====================================================================================================
# B13 — ana sayfa İhracat kutusu
# =====================================================================================================

def test_g3j_ihracat_kutusu_capasi(istemci):
    for dil in ("tr", "en"):
        ana = istemci.get(f"/{dil}/").text
        kutu = re.search(r'<a href="([^"]+)"><svg[^>]*><use href="/statik/ikonlar.svg#dunya">', ana)
        assert kutu and kutu.group(1) == f"/{dil}/yasal/kullanim#ihracat-export", dil
        sayfa = istemci.get(f"/{dil}/yasal/kullanim").text
        baslik = re.search(r'<h2 id="ihracat-export">(.*?)</h2>', sayfa, re.S)
        # G3k madde 24: EN başlıkta Türkçe "İhracat /" yok
        assert baslik and ("İhracat / Export" if dil == "tr" else "B. Export:") in _metin(baslik.group(1)), dil


# =====================================================================================================
# B14 — saat dilimi
# =====================================================================================================

def test_g3j_saat_dilimi_rezervasyon_ve_son_tarih(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-TZ1", ad="Saat Dilimi Ürünü", fiyat="100.00", stok=1)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="tz@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    _giris(istemci, "tz@ornek.test")
    _sepete_ekle(istemci, uid)
    r = _odeme_gonder(istemci, odeme_yontemi="havale")
    no = r.headers["location"].rsplit("/", 1)[1]
    onay = _metin(istemci.get(r.headers["location"]).text)
    assert re.search(r"Ödeme son tarihi: \d\d\.\d\d\.\d{4} \d\d:\d\d \(TSİ\)", onay)
    assert re.search(r"\d\d:\d\d \(TSİ\)", _metin(istemci.get(f"/tr/hesabim/siparis/{no}").text))
    assert re.search(r"\d\d:\d\d \(TSİ\)", _metin(istemci.get(f"/tr/hesabim/siparis/{no}/proforma").text))
    en = _metin(istemci.get(f"/en/siparis/{no}").text)
    assert re.search(r"Payment deadline: \d{1,2} [A-Z][a-z]{2} \d{4} \d\d:\d\d TRT", en)   # G3l madde 10 biçimi
    istemci.cookies.clear()
    assert re.search(r"en geç \d\d\.\d\d\.\d{4} \d\d:\d\d \(TSİ\) serbest kalabilir",
                     _metin(istemci.get(f"/tr/urun/{uid}").text))
    assert re.search(r"by \d{1,2} [A-Z][a-z]{2} \d{4} \d\d:\d\d TRT at the latest",   # G3l madde 10
                     _metin(istemci.get(f"/en/urun/{uid}").text))


# =====================================================================================================
# B15 — kartla ödenmiş sipariş: sipariş özeti (yazdır) + fatura e-posta notu
# =====================================================================================================

def test_g3j_odenmis_kart_siparisi_belge(istemci, db):
    from app.siparis.odeme_sim import BASARILI_KART
    _kur(db)
    uid = _urun(db, sku="S-OK1", ad="Ödenmiş Ürün", fiyat="100.00", stok=3)
    _musteri(db, eposta="ok@ornek.test")
    _giris(istemci, "ok@ornek.test")
    _sepete_ekle(istemci, uid)
    no = _siparis_no(_odeme_gonder(istemci).headers["location"])
    onay = istemci.get(f"/tr/siparis/{no}").text
    assert "Fatura e-posta ile gönderilir (temsili)" not in onay            # henüz ödenmedi
    r, _ = _kart_ode(istemci, no, BASARILI_KART)
    _sms(istemci, no, r.headers["location"])
    onay = sayfa_denetle(istemci.get(f"/tr/siparis/{no}"))
    assert re.search(rf'<a href="/tr/siparis/{no}"[^>]*data-e2e="belge-ozet-onay"[^>]*>.*?Sipariş özeti \(yazdır\)', onay, re.S)
    assert "Fatura e-posta ile gönderilir (temsili)" in _metin(onay)
    ayrinti = istemci.get(f"/tr/hesabim/siparis/{no}").text
    assert "Sipariş özeti (yazdır)" in _metin(ayrinti) and "Fatura e-posta ile gönderilir (temsili)" in _metin(ayrinti)
    assert "The invoice is sent by e-mail (indicative)" in _metin(istemci.get(f"/en/siparis/{no}").text)


# =====================================================================================================
# B16 — teklif: teslim adresi / posta kodu; sepetten teklif onayında "Sepeti boşalt"
# =====================================================================================================

def test_g3j_teklif_teslim_adresi(istemci, db):
    html = istemci.get("/tr/teklif").text
    form = re.search(r'<form method="post" action="/tr/teklif".*?</form>', html, re.S).group(0)
    blok = re.search(r'<div class="alan yalniz-yd[^"]*"[^>]*>.*?</div>', form, re.S).group(0)
    assert 'name="teslim_adresi"' in blok and "Teslim adresi / posta kodu" in _metin(blok)
    assert re.search(r'\.teklif-formu:has\(select\[name="ulke"\] option\[value="TR"\]:checked\) \.yalniz-yd '
                     r'\{ display: none; \}', _css())
    csrf = _gizli(html, "csrf")
    r = istemci.post("/tr/teklif", data={"csrf": csrf, "ad": "Hans", "eposta": "h@ornek.test", "ulke": "DE",
                                         "adet": "1", "mesaj": "m", "kvkk_onay": "1",
                                         "teslim_adresi": "Hauptstr. 5, 70173 Stuttgart"}, follow_redirects=False)
    assert r.status_code == 303
    assert db.execute("SELECT teslim_adresi FROM teklif").fetchone()[0] == "Hauptstr. 5, 70173 Stuttgart"
    assert "Hauptstr. 5, 70173 Stuttgart" in _metin(istemci.get(r.headers["location"]).text)
    _yonetici(istemci)
    assert "Hauptstr. 5, 70173 Stuttgart" in istemci.get("/yonetim/teklifler").text
    r = istemci.post("/tr/teklif", data={"csrf": csrf_al(istemci, "/tr/teklif"), "ad": "Hans", "eposta": "h@ornek.test",
                                         "ulke": "DE", "adet": "1", "mesaj": "m", "kvkk_onay": "1",
                                         "teslim_adresi": "x" * 201}, follow_redirects=False)
    assert r.status_code == 400 and 'id="hata-teslim_adresi"' in r.text


def test_g3j_sepetten_teklif_sepeti_bosalt(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-SB1", ad="Sepet Teklif Ürünü", fiyat="100.00", stok=3)
    _sepete_ekle(istemci, uid)
    html = istemci.get("/tr/teklif?sepet=1").text
    r = istemci.post("/tr/teklif", data={"csrf": _gizli(html, "csrf"), "ad": "Ali", "eposta": "a@ornek.test",
                                         "telefon": "+90 532 000 00 00", "ulke": "TR", "mesaj": "m", "kvkk_onay": "1",
                                         "kaynak": "sepet", "kalem_urun": str(uid), "kalem_adet": "2"},
                     follow_redirects=False)
    assert r.status_code == 303
    onay = sayfa_denetle(istemci.get(r.headers["location"]))
    assert "Fiyatlar teklif yanıtında bildirilir" in _metin(onay)
    form = re.search(r'<form method="post" action="/tr/sepet/bosalt".*?</form>', onay, re.S).group(0)
    assert 'name="csrf"' in form and "Sepeti boşalt" in _metin(form)
    assert istemci.post("/tr/sepet/bosalt", data={}, follow_redirects=False).status_code == 403
    r = istemci.post("/tr/sepet/bosalt", data={"csrf": _gizli(form, "csrf")}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/tr/sepet"
    assert db.execute("SELECT COUNT(*) FROM sepet_kalemi").fetchone()[0] == 0
    assert "Sepet boşaltıldı" in _bildirimler(istemci.get("/tr/sepet").text)
    onay = istemci.get(f"/tr/teklif/tamam?no={db.execute('SELECT no FROM teklif').fetchone()[0]}").text
    assert "/tr/sepet/bosalt" not in onay                                       # sepet boşken düğme yok


# =====================================================================================================
# B17 — aynı parça no ile başka ürünler
# =====================================================================================================

def test_g3j_ayni_parca_no_urun_sayfasi(istemci, db):
    a = _urun(db, sku="8503033800001", ad="KUKA ECMBP0D3004BE531 KPP-600-20", uretici_kodu="00198259", stok=1)
    b = _urun(db, sku="8503033800002", ad="KUKA ECMAP0D3004BE531 KPP-600-20", uretici_kodu="00198259", stok=1)
    c = _urun(db, sku="8503033800003", ad="KUKA PASİF KPP", uretici_kodu="00198259", stok=1, aktif=False)
    tek = _urun(db, sku="S-TEK", ad="Tekil Ürün", uretici_kodu="TEK-1", stok=1)
    with db:
        db.execute("UPDATE urun SET durum_kodu = 'ikinci_el' WHERE id = ?", (b,))
    html = sayfa_denetle(istemci.get(f"/tr/urun/{a}"))
    blok = re.search(r'<p class="ayni-parca-no"[^>]*>(.*?)</p>', html, re.S).group(1)
    assert "Aynı parça no ile 1 ürün daha:" in _metin(blok)
    assert f'href="/tr/urun/{b}"' in blok and f'href="/tr/urun/{c}"' not in blok
    assert "KUKA ECMAP0D3004BE531 KPP-600-20 (2. el, stok kodu 8503033800002)" in _metin(blok)
    assert 'class="ayni-parca-no"' not in istemci.get(f"/tr/urun/{tek}").text


# =====================================================================================================
# B18 — liste rozeti "demo kaydı"
# =====================================================================================================

def test_g3j_liste_rozeti_demo_kaydi(istemci, db):
    uid = _urun(db, sku="S-DK1", ad="Demo Kayıtlı", fiyat="10.00", stok=1)
    with db:
        db.execute("UPDATE urun SET durum_kodu = 'yeni', durum_ornek = 1 WHERE id = ?", (uid,))
    for yol in ("/tr/urunler", "/tr/ara?q=demo"):
        satir = _satir(istemci.get(yol).text, uid)
        assert re.search(r'<span class="rozet rozet-ornek" title="demo için elle girilmiş durum kaydı">demo kaydı</span>',
                         satir), yol
    en = _satir(istemci.get("/en/urunler").text, uid)
    assert re.search(r'title="condition entered manually for the demo">demo record</span>', en)
    urun = istemci.get(f"/tr/urun/{uid}").text
    assert "demo için elle girilmiş durum kaydı" in urun and "örnek:" not in urun   # G3k madde 22: tekrar yok


# =====================================================================================================
# İnceleme turu 1
# =====================================================================================================

def test_g3j_f1_sepet_yurtdisi_eur_tl_toplam_ve_kur_yok(istemci, db):
    """M-2: TL tahsil edilen bireysel müşteri teslimi yurt dışı + € gösterim: /sepet özetinde ₺ toplam ve TCMB kur
    satırı yok, yalnız "ödeme TL, kur ödemede" notu; ödeme sayfası özeti değişmez."""
    _kur(db)
    uid = _urun(db, sku="S-F1S", ad="Sepet Euro Ürünü", fiyat="100.00", stok=3)
    _musteri(db, eposta="f1s@ornek.test")
    _giris(istemci, "f1s@ornek.test")
    _ulke_ve_fiyat(istemci, "DE", "eur")
    _sepete_ekle(istemci, uid)
    sepet = sayfa_denetle(istemci.get("/tr/sepet"))
    ozet = re.search(r'<aside class="siparis-ozeti".*?</aside>', sepet, re.S).group(0)
    assert "₺" not in ozet and "kur-satiri" not in ozet and "100,00 €" in ozet
    assert "Ödeme TL olarak alınır; kur ödeme adımında sabitlenir." in _metin(ozet)
    odeme = istemci.get("/tr/odeme").text
    assert "kur-satiri" in odeme and "₺" in re.search(r'<dl class="tutar-ozeti">.*?</dl>', odeme, re.S).group(0)


def test_g3j_f1_yonetim_teklifler_kodlari_tek_geciste_eslestirir(istemci, db, monkeypatch):
    """M-3: yönetim teklifler sayfası eşleşmeleri satır başına tam tarama yapmadan, tek geçişte bulur; kapanmış
    talepler için hesaplanmaz."""
    from app.katalog import depo
    from app.web.rotalar import yonetim
    a = _urun(db, sku="S-F1A", ad="KUKA KPP-600-20 GÜÇ KAYNAĞI", uretici_kodu="00198259", stok=1)
    for kod in ("00198259", "KPP 600 20", "YOK-999"):
        _hizli(istemci, parca_kodu=kod)
    with db:      # tek eşleşme ürüne bağlanır; bağlantıyı kaldırıp toplu eşleştirmeyi sına
        db.execute("UPDATE teklif SET urun_id = NULL")
        db.execute("UPDATE teklif SET durum = 'kapandi' WHERE parca_kodu = 'KPP 600 20'")
    cagri = []
    monkeypatch.setattr(yonetim, "kod_eslesmeleri", lambda *a, **k: cagri.append(a) or [], raising=False)
    gercek = depo.kod_eslesmeleri_toplu
    sayac = []
    monkeypatch.setattr(yonetim, "kod_eslesmeleri_toplu", lambda con, kodlar: sayac.append(list(kodlar)) or
                        gercek(con, kodlar))
    _yonetici(istemci)
    html = istemci.get("/yonetim/teklifler").text
    assert cagri == [] and len(sayac) == 1 and sorted(sayac[0]) == ["00198259", "YOK-999"]   # kapanmış hariç
    satirlar = re.findall(r"<tr[^>]*>(.*?)</tr>", re.search(r"<tbody>(.*?)</tbody>", html, re.S).group(1), re.S)
    acik = next(x for x in satirlar if ">00198259<" in x)
    assert f'href="/tr/urun/{a}"' in acik
    assert gercek(db, ["kpp-600-20", "00 198 259", "x"]) == {"kpp-600-20": [a], "00 198 259": [a], "x": []}


def test_g3j_f1_ad_eslesmesi_200_aday_sinirina_takilmaz(istemci, db):
    """M-4: kelime başından öneki eşleşen 200'den çok aday varken tam eşleşme 200. satırdan sonra da bulunur."""
    from app.katalog.depo import kod_eslesmeleri
    with db:
        from tests.conftest import urun_ekle
        for i in range(205):
            urun_ekle(db, sku=f"S-KRX{i:03d}", ad=f"KR16X{i:03d} PARÇA", stok=1)
        hedef = urun_ekle(db, sku="S-KR16", ad="KUKA ROBOT KR16 KOL", stok=1)
    assert [u.id for u in kod_eslesmeleri(db, "KR16")] == [hedef]
    _hizli(istemci, parca_kodu="kr-16")
    assert db.execute("SELECT urun_id FROM teklif").fetchone()[0] == hedef


def test_g3j_f1_kod_sorgusu_filtreyle_sonucsuz(mlfb):
    """M-5: kod sorgusu filtre yüzünden sonuçsuzsa "koduyla ürün yok" yerine filtreleri kaldırma bağlantısı."""
    html = sayfa_denetle(mlfb.get("/tr/ara", params={"q": "6ES7 307", "tedarikli": "1"}))
    assert _satirlar(html) == []
    blok = re.search(r'<div class="kod-yok"[^>]*>(.*?)</div>', html, re.S).group(1)
    assert "koduyla ürün yok" not in _metin(blok)
    bag = re.search(r'<a href="([^"]+)"[^>]*>(filtreleri kaldır \(1 ürün\))</a>', blok)
    assert "Filtrelerle eşleşen ürün yok" in _metin(blok) and bag and unescape(bag.group(1)) == "/tr/ara?q=6ES7+307"
    assert "No product matches the filters" in _metin(mlfb.get("/en/ara", params={"q": "6ES7 307", "tedarikli": "1"}).text)
    assert "koduyla ürün yok" in _metin(mlfb.get("/tr/ara", params={"q": "6ES7 999"}).text)      # filtresiz: aynen


@pytest.mark.parametrize("sorgu,ad", [
    ("redüktörlü motor", "REXROTH REDÜKTÖRLÜ ELEKTRİK MOTORU"),
    ("endüktif sensör", "BALLUFF ENDÜKTİF M12 SENSÖR"),
])
def test_g3j_f1_cok_kelimeli_esanlam_ifade_aramasina_cevirmez(istemci, sorgu, ad):
    """M-6: çok kelimeli eşanlam grubu, kullanıcının kelimelerini bitişik ifade aramasına çevirmez (VE biçimi de aranır)."""
    with istemci_db(istemci) as con:
        from tests.conftest import urun_ekle
        urun_ekle(con, sku="S-M6A", ad=ad, stok=1)
        urun_ekle(con, sku="S-M6B", ad="SEW REDÜKTÖRLÜ MOTOR 0,37KW", stok=1)
        urun_ekle(con, sku="S-M6C", ad="IFM YAKLAŞIM SENSÖRÜ", stok=1)
        indeksi_yeniden_kur(con)
    html = istemci.get("/tr/ara", params={"q": sorgu}).text
    assert ad in _satirlar(html) and 'class="gevset"' not in html


def test_g3j_f1_onerilen_alinabilir_stok(istemci, db):
    """M-8: "Önerilen" puanının stok puanı alınabilir stoktan (madde 5): tümü ayrılmış ürün stok puanı almaz."""
    _kur(db)
    ayr = _urun(db, sku="S-ON1", ad="AAA Ayrılmış Ürün", fiyat="10.00", stok=1)
    serbest = _urun(db, sku="S-ON2", ad="BBB Serbest Ürün", fiyat="10.00", stok=1)
    _odenmis_siparis(db, ayr, 1, datetime.now(UTC).isoformat())
    assert _satirlar(istemci.get("/tr/urunler").text) == ["BBB Serbest Ürün", "AAA Ayrılmış Ürün"]
    assert serbest
