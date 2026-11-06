"""G3i: persona tur 4 — A: fiyat şeffaflığı (1–5), B: kurumsal süreç ve belgeler (6–10), C: güven ve içerik (11–18).
Ek: G3h yeniden inceleme N-1 (Parker/Eurotherm SSD sürücüleri tipi)."""
import re
from html import unescape

import pytest

from app.fiyat.kurallar import MusteriTipi
from tests.conftest import csrf_al, istemci_db, oturum_oku, sayfa_denetle  # noqa: F401
from tests.test_web_sepet_odeme import (GECERLI_VKN, PAROLA, _adres_formu, _giris, _gizli, _kur, _musteri,  # noqa: F401
                                        _odeme_gonder, _sepete_ekle, _siparis_no, _urun, db)


# =====================================================================================================
# G3h N-1 — Parker/Eurotherm "SSD" sürücüleri sürücü tipindedir; SSD disk "diğer" kalır
# =====================================================================================================

@pytest.mark.parametrize("ad,tip", [
    ("PARKER SSD 590 DC DRIVE", "surucu"),
    ("SSD DRIVES 650V INVERTER", "surucu"),
    ("EUROTHERM SSD 690+ SÜRÜCÜ", "surucu"),
    ("KUKA SSD 256GB", "diger"),
    ("ENDÜSTRİYEL PC SSD HARD DISK", "diger"),
])
def test_g3i_ssd_surucu_tipi(ad, tip):
    from app.katalog.tip import tip_bul
    assert tip_bul(ad) == tip


# =====================================================================================================
# ortak yardımcılar
# =====================================================================================================

def _ozet(html):
    return re.search(r'<dl class="tutar-ozeti">.*?</dl>', html, re.S).group(0)


def _dtler(ozet):
    return [unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<dt[^>]*>(.*?)</dt>", ozet, re.S)]


def _bildirimler(html):
    m = re.search(r'<div class="bildirimler" role="status">(.*?)</div>', html, re.S)
    return unescape(re.sub(r"<[^>]+>", "", m.group(1))) if m else ""


def _metin(parca):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", parca))).strip()


def _fiyat_sec(istemci, deger, sonraki="/tr/urunler"):
    csrf = csrf_al(istemci, "/tr/urunler")
    return istemci.post("/tercih", data={"csrf": csrf, "fiyat": deger, "sonraki": sonraki}, follow_redirects=False)


def _liste_fiyati(html):
    return _metin(re.search(r'<td class="ut-fiyat">(.*?)</td>', html, re.S).group(1))


def _kurumsal(db, eposta):
    return _musteri(db, tip=MusteriTipi.KURUMSAL, eposta=eposta, vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")


# =====================================================================================================
# A — fiyat şeffaflığı
# =====================================================================================================

def test_g3i_ara_toplam_kdv_haric_etiketi_bireysel(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-AT1", ad="Ara Toplam Ürünü", fiyat="100.00", stok=5)
    _sepete_ekle(istemci, uid)
    html = sayfa_denetle(istemci.get("/tr/sepet"))
    assert "Tutar (KDV dahil)" in html                                   # satır başlığı KDV dahil
    dtler = _dtler(_ozet(html))
    assert [d for d in dtler if d.startswith("Ara toplam")] == ["Ara toplam (KDV hariç)"]
    en = istemci.get("/en/sepet").text
    assert "Subtotal (excl. VAT)" in _dtler(_ozet(en))


def test_g3i_ara_toplam_kurumsal_tek_satir(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-AT2", ad="Kurumsal Ara Toplam", fiyat="100.00", stok=5)
    _kurumsal(db, "at2@ornek.test")
    _giris(istemci, "at2@ornek.test")
    _sepete_ekle(istemci, uid, adet="2")
    for yol in ("/tr/sepet", "/tr/odeme"):
        ozet = _ozet(istemci.get(yol).text)
        dtler = _dtler(ozet)
        assert [d for d in dtler if "Ara toplam" in d] == ["Ara toplam (KDV hariç)"], (yol, dtler)
        satir = re.search(r'data-e2e="satir-eur-ara-toplam">.*?</dt>\s*<dd[^>]*>(.*?)</dd>', ozet, re.S)
        assert _metin(satir.group(1)) == "200,00 € · ≈ 7.000,00 ₺", yol
    r = _odeme_gonder(istemci)
    html = istemci.get(f"/tr/siparis/{_siparis_no(r.headers['location'])}").text
    ozet = _ozet(html)
    assert [d for d in _dtler(ozet) if "Ara toplam" in d] == ["Ara toplam (KDV hariç)"]
    satir = re.search(r'data-e2e="satir-eur-ara-toplam">.*?</dt>\s*<dd[^>]*>(.*?)</dd>', ozet, re.S)
    assert _metin(satir.group(1)) == "200,00 € · ≈ 7.000,00 ₺"


def test_g3i_fiyat_gosterim_secici_liste_ve_sepet(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-FG1", ad="Seçici Ürünü", fiyat="100.00", stok=5)
    html = sayfa_denetle(istemci.get("/tr/urunler"))
    secici = re.search(r'<form class="fiyat-secici"[^>]*id="fiyat-gosterim".*?</form>', html, re.S)
    assert secici, "liste üstünde fiyat seçici yok"
    secici = secici.group(0)
    assert 'action="/tercih"' in secici and 'name="csrf"' in secici
    assert re.search(r'name="fiyat" value="try"[^>]*aria-pressed="true"', secici)   # misafir TR: ₺ KDV dahil
    assert re.search(r'name="fiyat" value="eur"[^>]*aria-pressed="false"', secici)
    assert "Fiyatlar:" in _metin(secici) and "₺ KDV dahil" in _metin(secici) and "€ KDV hariç" in _metin(secici)
    assert "Kurumsal hesaplar için varsayılan € KDV hariç" in _metin(html)
    assert "₺" in _liste_fiyati(html) and "€" not in _liste_fiyati(html)
    # € KDV hariç seçilir: liste, ürün, sepet, ödeme aynı gösterimde; ödeme yine TL
    r = _fiyat_sec(istemci, "eur")
    assert r.status_code == 303 and r.headers["location"] == "/tr/urunler"
    html = istemci.get("/tr/urunler").text
    liste_fiyat = _liste_fiyati(html)
    assert liste_fiyat.index("Temsili fiyat") < liste_fiyat.index("100,00 €"), liste_fiyat
    assert "100,00 € KDV hariç" in liste_fiyat
    assert re.search(r'name="fiyat" value="eur"[^>]*aria-pressed="true"', html)
    urun = istemci.get(f"/tr/urun/{uid}").text
    assert re.search(r'data-e2e="fiyat-ana" data-para="EUR" data-kdv="haric"', urun)
    _sepete_ekle(istemci, uid)
    sepet = istemci.get("/tr/sepet").text
    assert re.search(r'<form class="fiyat-secici"', sepet), "sepette fiyat seçici yok"
    assert re.search(r'data-e2e="kalem-tutar" data-para="EUR" data-kdv="haric"', sepet)
    assert "Tutar (KDV hariç)" in sepet
    assert 'data-e2e="not-tahsilat-try"' in sepet                      # ödeme her zaman TL notu
    odeme = istemci.get("/tr/odeme").text
    assert re.search(r'data-e2e="kalem-tutar" data-para="EUR" data-kdv="haric"', odeme)
    # geri ₺ KDV dahil
    _fiyat_sec(istemci, "try")
    assert re.search(r'data-e2e="fiyat-ana" data-para="TRY" data-kdv="dahil"', istemci.get(f"/tr/urun/{uid}").text)
    # geçersiz değer yok sayılır
    _fiyat_sec(istemci, "xxx")
    assert oturum_oku(istemci).get("fiyat") == "try"


def test_g3i_fiyat_gosterim_kurumsal_varsayilan_ve_bildirim(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-FG2", ad="Kurumsal Seçici", fiyat="100.00", stok=5)
    _kurumsal(db, "fg2@ornek.test")
    istemci.get("/tr/urunler")                                    # misafir: ₺ KDV dahil
    csrf = csrf_al(istemci, "/tr/giris")
    r = istemci.post("/tr/giris", data={"eposta": "fg2@ornek.test", "parola": PAROLA, "csrf": csrf,
                                        "sonraki": "/tr/urunler"}, follow_redirects=False)
    html = istemci.get(r.headers["location"]).text
    assert "Fiyatlar kurumsal hesabınız için € KDV hariç gösteriliyor" in _bildirimler(html)
    assert re.search(r'<a href="/tr/urunler#fiyat-gosterim"[^>]*>değiştir</a>', html)
    assert re.search(r'name="fiyat" value="eur"[^>]*aria-pressed="true"', html)
    assert "gösteriliyor" not in _bildirimler(istemci.get("/tr/urunler").text)     # bir kez
    # kurumsal ₺ KDV dahil seçebilir (TR teslim): ürün ve sepet ₺ KDV dahil
    _fiyat_sec(istemci, "try")
    assert re.search(r'data-e2e="fiyat-ana" data-para="TRY" data-kdv="dahil"', istemci.get(f"/tr/urun/{uid}").text)
    _sepete_ekle(istemci, uid)
    sepet = istemci.get("/tr/sepet").text
    assert re.search(r'data-e2e="kalem-tutar" data-para="TRY" data-kdv="dahil"', sepet)
    assert 'data-e2e="satir-eur-ara-toplam"' not in sepet             # gösterim = tahsilat para birimi


def test_g3i_fiyat_gosterim_aciktan_secilmisse_giriste_bildirim_yok(istemci, db):
    _kur(db)
    _kurumsal(db, "fg3@ornek.test")
    _fiyat_sec(istemci, "eur")
    csrf = csrf_al(istemci, "/tr/giris")
    r = istemci.post("/tr/giris", data={"eposta": "fg3@ornek.test", "parola": PAROLA, "csrf": csrf},
                     follow_redirects=False)
    assert "gösteriliyor" not in _bildirimler(istemci.get(r.headers["location"]).text)


def test_g3i_sepet_hucresi_karisik_degil(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-KH1", ad="Hücre Ürünü", fiyat="100.00", stok=5)
    _sepete_ekle(istemci, uid)
    html = istemci.get("/tr/sepet").text
    hucre = re.search(r'<td class="kalem-tutar sayi"[^>]*>(.*?)</td>', html, re.S).group(1)
    ana = re.search(r'<span class="kalem-ana">(.*?)</span>\s*<span class="fiyat-ikincil kalem-ikincil">', hucre, re.S)
    ikincil = re.search(r'<span class="fiyat-ikincil kalem-ikincil">(.*?)</span>', hucre, re.S)
    assert ana and ikincil
    assert "₺" in _metin(ana.group(1)) and "KDV dahil" in _metin(ana.group(1)) and "€" not in _metin(ana.group(1))
    assert "€" in _metin(ikincil.group(1)) and "KDV hariç" in _metin(ikincil.group(1))
    assert "₺" not in _metin(ikincil.group(1)) and "dahil" not in _metin(ikincil.group(1))


def test_g3i_siparis_onayi_kdv_urunler_ve_kargo(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-KD1", ad="KDV Ürünü", fiyat="100.00", stok=5)
    _musteri(db, eposta="kd1@ornek.test")
    _giris(istemci, "kd1@ornek.test")
    _sepete_ekle(istemci, uid)
    r = _odeme_gonder(istemci)
    no = _siparis_no(r.headers["location"])
    ozet = _ozet(istemci.get(f"/tr/siparis/{no}").text)
    assert "KDV (ürünler)" in _dtler(ozet) and "KDV (kargo)" in _dtler(ozet)
    urunler = re.search(r'data-e2e="satir-kdv">KDV \(ürünler\)</dt>\s*<dd[^>]*>(.*?)</dd>', ozet).group(1)
    kargo = re.search(r'data-e2e="satir-kdv-kargo">KDV \(kargo\)</dt>\s*<dd[^>]*>(.*?)</dd>', ozet).group(1)
    assert urunler == "700,00 ₺"                                       # 100 € × 35 × %20
    assert kargo == "105,00 ₺"                                         # 15 € × 35 × %20
    assert db.execute("SELECT kdv FROM siparis WHERE no = ?", (no,)).fetchone()[0] == "805.00"
    # sepet ve ödeme özeti de iki satır
    _sepete_ekle(istemci, uid)
    assert "KDV (kargo) %20" in _dtler(_ozet(istemci.get("/tr/sepet").text))   # G3l madde 6: oran satırda


def test_g3i_tedarikli_kalem_notu(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-TD1", ad="Tedarikli Kablo", fiyat="50.00", stok=0)
    _musteri(db, eposta="td1@ornek.test")
    _giris(istemci, "td1@ornek.test")
    _sepete_ekle(istemci, uid, adet="2")
    metin = ("Bu kalemin tedarik süresi siparişten sonra 1 iş günü içinde bildirilir (temsili); süreyi önce "
             "öğrenmek için teklif isteyin")
    sepet = sayfa_denetle(istemci.get("/tr/sepet"))
    not_ = re.search(r'<p class="not-tedarik"[^>]*data-e2e="not-tedarik"[^>]*>(.*?)</p>', sepet, re.S)
    assert not_ and metin in _metin(not_.group(1))
    assert f'href="/tr/teklif?urun_id={uid}&amp;adet=2"' in not_.group(1)
    odeme = istemci.get("/tr/odeme").text
    ozet = re.search(r'<aside class="siparis-ozeti".*?</aside>', odeme, re.S).group(0)
    assert metin in _metin(ozet)
    r = _odeme_gonder(istemci)                                          # sipariş engellenmez
    assert r.status_code == 303 and "/kart" in r.headers["location"]
    # tedarik süresi bilinen üründe not yok
    uid2 = _urun(db, sku="S-TD2", ad="Süreli Ürün", fiyat="50.00", stok=0, tedarik_suresi_gun=10)
    _sepete_ekle(istemci, uid2)
    sepet = istemci.get("/tr/sepet").text
    assert sepet.count('data-e2e="not-tedarik"') == 1 and f"urun_id={uid2}&amp;adet" not in sepet


# =====================================================================================================
# B — kurumsal süreç ve belgeler
# =====================================================================================================

def _yonetime_gir(istemci):
    csrf = csrf_al(istemci, "/yonetim/giris")
    istemci.post("/yonetim/giris", data={"kullanici": "yonetici", "parola": "yonetici-parola-123", "csrf": csrf})


def _havale_siparisi(istemci, db, eposta, *, tip=MusteriTipi.KURUMSAL, po="PO-4711", ulke="TR", fiyat="100.00",
                     adet="2", dil="tr"):
    _kur(db)
    uid = _urun(db, sku=f"S-{eposta[:4]}", ad="Proforma Ürünü", fiyat=fiyat, stok=10, uretici_kodu=f"6EP-{eposta[:3]}")
    if tip == MusteriTipi.KURUMSAL:
        _kurumsal(db, eposta)
    else:
        _musteri(db, tip=tip, eposta=eposta, ulke=ulke, vat_id="DE123456789")
    _giris(istemci, eposta, dil=dil)
    _sepete_ekle(istemci, uid, adet=adet, dil=dil)
    teslim = "kargo" if ulke == "TR" else "yurtdisi_dap"
    r = _odeme_gonder(istemci, dil=dil, ulke=ulke, teslim=teslim, odeme_yontemi="havale", musteri_po=po)
    assert r.status_code == 303, r.text
    no = re.search(r"/siparis/(CR-DEMO-\d{8}-\d{4})$", r.headers["location"]).group(1)
    return no, uid


def test_g3i_po_numarasi_odeme(istemci, db):
    no, _ = _havale_siparisi(istemci, db, "po1@ornek.test", po="PO-4711/A")
    assert db.execute("SELECT musteri_po FROM siparis WHERE no = ?", (no,)).fetchone()[0] == "PO-4711/A"
    for yol in (f"/tr/siparis/{no}", "/tr/hesabim", f"/tr/hesabim/siparis/{no}", f"/tr/hesabim/siparis/{no}/proforma"):
        assert "PO-4711/A" in istemci.get(yol).text, yol
    # ödeme formunda alan, etiket ve sınır
    uid = _urun(db, sku="S-PO2", ad="PO Ürünü 2", fiyat="10.00", stok=5)
    _sepete_ekle(istemci, uid)
    odeme = istemci.get("/tr/odeme").text
    assert re.search(r'<label for="musteri_po">Satın alma \(PO\) numaranız', odeme)
    # G3n madde 9: maxlength yok (tarayıcı sessizce kırpmasın); sınır sunucuda "En çok 40 karakter"
    assert re.search(r'<input id="musteri_po" name="musteri_po"', odeme) and 'maxlength="40"' not in odeme
    r = _odeme_gonder(istemci, sayfa_html=odeme, musteri_po="X" * 41)
    assert r.status_code == 400 and 'id="hata-musteri_po"' in r.text
    assert "Your PO number" in istemci.get("/en/odeme").text
    _yonetime_gir(istemci)
    assert "PO-4711/A" in istemci.get("/yonetim/siparisler").text


def test_g3i_po_numarasi_teklif(istemci, db):
    _kurumsal(db, "po3@ornek.test")
    _giris(istemci, "po3@ornek.test")
    form = istemci.get("/tr/teklif").text
    assert re.search(r'<label for="musteri_po">Satın alma \(PO\) numaranız', form)
    veri = {"csrf": _gizli(form, "csrf"), "ad": "Anadolu Makine", "eposta": "po3@ornek.test", "ulke": "TR",
            "adet": "1", "mesaj": "Fiyat rica ederiz", "musteri_po": "PO-T-99"}
    r = istemci.post("/tr/teklif", data={**veri, "musteri_po": "Y" * 41}, follow_redirects=False)
    assert r.status_code == 400 and 'id="hata-musteri_po"' in r.text
    r = istemci.post("/tr/teklif", data=veri, follow_redirects=False)
    assert r.status_code == 303
    no = db.execute("SELECT no FROM teklif").fetchone()[0]
    assert db.execute("SELECT musteri_po FROM teklif").fetchone()[0] == "PO-T-99"
    assert "PO-T-99" in istemci.get(r.headers["location"]).text
    assert "PO-T-99" in istemci.get(f"/tr/hesabim/teklif/{no}").text
    _yonetime_gir(istemci)
    assert "PO-T-99" in istemci.get("/yonetim/teklifler").text


def test_g3i_proforma_belgesi_kurumsal_tr(istemci, db):
    from datetime import datetime, timedelta
    from pathlib import Path
    no, _ = _havale_siparisi(istemci, db, "pf1@ornek.test")
    s = db.execute("SELECT odeme_son_tarih, olusturma FROM siparis WHERE no = ?", (no,)).fetchone()
    html = sayfa_denetle(istemci.get(f"/tr/hesabim/siparis/{no}/proforma"))
    belge = re.search(r'<article class="proforma-belge".*?</article>', html, re.S).group(0)
    m = _metin(belge)
    assert "<h1" in belge and "PROFORMA FATURA" in m
    assert re.search(r'<img class="pb-logo" src="/statik/marka/ceylan-robot-logo.png"', belge)
    assert "Düzenlenme tarihi" in m and "Geçerlilik" in m
    son = datetime.fromisoformat(s["odeme_son_tarih"]) + timedelta(hours=3)
    assert son.strftime("%d.%m.%Y") in m
    # satıcı: unvan, adres; VKN/vergi dairesi ayarda yoksa demo notu
    assert "MUSTAFA CEYLAN ENDÜSTRİ A.Ş." in m and "Selçuklu / Konya" in m
    assert "Demo: üretimde doldurulacak" in m
    # alıcı: firma, VKN, vergi dairesi, adres; PO
    assert "QATestUser kurumsal" in m and GECERLI_VKN in m and "Selçuk" in m and "Test Mah. Deneme Sk. No: 1" in m
    assert "PO-4711" in m
    # kalemler: parça no, ad, adet, birim, KDV, tutar
    tablo = _metin(re.search(r'<table class="pb-kalemler".*?</table>', belge, re.S).group(0))
    for metin in ("Parça no", "Ürün", "Adet", "Birim fiyat", "KDV", "Tutar", "6EP-pf1", "Proforma Ürünü",
                  "3.500,00 ₺", "%20", "7.000,00 ₺"):
        assert metin in tablo, metin
    # toplamlar TL ve sabitlenen kurla EUR: (7.000 + 525) × 1,2 = 9.030 ₺ = 258,00 €
    toplam = _metin(re.search(r'<dl class="pb-toplam".*?</dl>', belge, re.S).group(0))
    assert "Genel toplam" in toplam and "9.030,00 ₺" in toplam and "258,00 €" in toplam, toplam
    assert "1 € = 35,0000 ₺" in m
    # banka: TR müşteri yalnız TL IBAN
    assert "IBAN (TL)" in m and "IBAN (EUR)" not in m
    assert "Menşe ve GTİP (HS) kodu sevk belgelerinde bildirilir" not in m
    # yazdırma: üst bant / alt bilgi gizli, A4 (site.css)
    css = Path("app/web/statik/site.css").read_text(encoding="utf-8")
    assert re.search(r"@page proforma\s*\{[^}]*size:\s*A4", css)   # inceleme M-5: adlandırılmış sayfa
    assert re.search(r"@media print\s*\{[^@]*\.proforma-belge", css, re.S)
    # onay sayfasındaki metin belgeye bağlanır; banka bilgisi alıcının para birimine göre
    onay = istemci.get(f"/tr/siparis/{no}").text
    assert f'href="/tr/hesabim/siparis/{no}/proforma"' in onay
    assert "IBAN (EUR)" not in onay and "IBAN (TL)" in onay


def test_g3i_proforma_satici_ayarlardan(istemci, db):
    from dataclasses import replace
    istemci.app.state.ayarlar = replace(istemci.app.state.ayarlar, satici_vkn="6130012345",
                                        satici_vergi_dairesi="Selçuklu V.D.")
    no, _ = _havale_siparisi(istemci, db, "pf2@ornek.test")
    m = _metin(istemci.get(f"/tr/hesabim/siparis/{no}/proforma").text)
    assert "6130012345" in m and "Selçuklu V.D." in m and "Demo: üretimde doldurulacak" not in m


def test_g3i_proforma_yurtdisi_eur(istemci, db):
    no, _ = _havale_siparisi(istemci, db, "pf3@ornek.test", tip=MusteriTipi.YURTDISI, ulke="DE", dil="en")
    html = sayfa_denetle(istemci.get(f"/en/hesabim/siparis/{no}/proforma"))
    belge = _metin(re.search(r'<article class="proforma-belge".*?</article>', html, re.S).group(0))
    assert "PROFORMA INVOICE" in belge and "DE123456789" in belge
    assert "IBAN (EUR)" in belge and "SWIFT/BIC" in belge and "IBAN (TL)" not in belge and "₺" not in belge
    assert "€200.00" in belge
    assert "Origin and HS code are stated in the shipping documents" in belge
    tr = _metin(istemci.get(f"/tr/hesabim/siparis/{no}/proforma").text)
    assert "Menşe ve GTİP (HS) kodu sevk belgelerinde bildirilir" in tr
    r = istemci.get(f"/en/account/orders/{no}/proforma", follow_redirects=False)     # EN takma ad
    assert r.status_code == 301 and r.headers["location"] == f"/en/hesabim/siparis/{no}/proforma"


def test_g3i_proforma_erisim(istemci, db):
    no, _ = _havale_siparisi(istemci, db, "pf4@ornek.test")
    istemci.cookies.clear()
    r = istemci.get(f"/tr/hesabim/siparis/{no}/proforma", follow_redirects=False)
    assert r.status_code == 303 and "/tr/giris" in r.headers["location"]
    _kurumsal(db, "pf5@ornek.test")
    _giris(istemci, "pf5@ornek.test")
    assert istemci.get(f"/tr/hesabim/siparis/{no}/proforma").status_code == 404     # başkasının
    assert istemci.get(f"/tr/hesabim/siparis/{no}").status_code == 404
    # kart siparişinde proforma yok
    uid = _urun(db, sku="S-PF6", ad="Kart Ürünü", fiyat="10.00", stok=5)
    _sepete_ekle(istemci, uid)
    kart_no = _siparis_no(_odeme_gonder(istemci).headers["location"])
    assert istemci.get(f"/tr/hesabim/siparis/{kart_no}/proforma").status_code == 404
    assert "/proforma" not in istemci.get(f"/tr/hesabim/siparis/{kart_no}").text


def test_g3i_hesabim_siparis_detayi_ve_tekrar_ekle(istemci, db):
    no, uid = _havale_siparisi(istemci, db, "hs1@ornek.test", adet="3")
    assert f'href="/tr/hesabim/siparis/{no}"' in istemci.get("/tr/hesabim").text      # liste satırından bağlantı
    html = sayfa_denetle(istemci.get(f"/tr/hesabim/siparis/{no}"))
    m = _metin(html)
    assert no in m and "Ödeme bekliyor" in m and "PO-4711" in m and "Proforma Ürünü" in m and "6EP-hs1" in m
    belgeler = re.search(r'<section class="siparis-belgeler".*?</section>', html, re.S).group(0)
    assert f'href="/tr/hesabim/siparis/{no}/proforma"' in belgeler
    assert f'href="/tr/siparis/{no}"' in belgeler and "Sipariş özeti (yazdır)" in _metin(belgeler)
    form = re.search(rf'<form method="post" action="/tr/hesabim/siparis/{no}/tekrar".*?</form>', html, re.S).group(0)
    assert 'name="csrf"' in form and "Kalemleri tekrar sepete ekle" in _metin(form)
    assert istemci.post(f"/tr/hesabim/siparis/{no}/tekrar", data={}, follow_redirects=False).status_code == 403
    # stok kuralı: stok 10, havale siparişi 3 ayırdı -> 7 ayrılabilir; 3 eklenir
    r = istemci.post(f"/tr/hesabim/siparis/{no}/tekrar", data={"csrf": _gizli(html, "csrf")}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/tr/sepet"
    assert "1 kalem sepete eklendi" in _bildirimler(istemci.get("/tr/sepet").text)
    assert db.execute("SELECT adet FROM sepet_kalemi WHERE urun_id = ?", (uid,)).fetchone()[0] == 3
    # stok azalırsa adet ayrılabilir stoka iner ve bildirilir (stok 4 − ayrılan 3 = 1)
    with db:
        db.execute("UPDATE urun SET stok = 4 WHERE id = ?", (uid,))
        db.execute("DELETE FROM sepet_kalemi")
    istemci.post(f"/tr/hesabim/siparis/{no}/tekrar", data={"csrf": _gizli(html, "csrf")}, follow_redirects=False)
    assert "stok" in _bildirimler(istemci.get("/tr/sepet").text)
    assert db.execute("SELECT adet FROM sepet_kalemi WHERE urun_id = ?", (uid,)).fetchone()[0] == 1
    r = istemci.get(f"/en/account/orders/{no}", follow_redirects=False)                 # EN takma ad
    assert r.status_code == 301 and r.headers["location"] == f"/en/hesabim/siparis/{no}"


def test_g3i_fatura_bilgilerim(istemci, db):
    _kurumsal(db, "fb1@ornek.test")
    _giris(istemci, "fb1@ornek.test")
    assert 'href="/tr/hesabim/fatura"' in istemci.get("/tr/hesabim").text
    html = sayfa_denetle(istemci.get("/tr/hesabim/fatura"))
    form = re.search(r'<form method="post" action="/tr/hesabim/fatura".*?</form>', html, re.S).group(0)
    for ad in ("ad", "vergi_dairesi", "satir1", "satir2", "posta_kodu", "sehir", "telefon"):
        assert f'name="{ad}"' in form, ad
    assert 'name="vergi_kimlik_no"' not in html and GECERLI_VKN in _metin(html)
    assert "Değişiklik için bizimle iletişime geçin" in _metin(html)
    csrf = _gizli(html, "csrf")
    assert istemci.post("/tr/hesabim/fatura", data={"ad": "X"}, follow_redirects=False).status_code == 403
    r = istemci.post("/tr/hesabim/fatura", data={"csrf": csrf, "ad": "", "vergi_dairesi": "", "satir1": "",
                                                 "sehir": "", "telefon": "abc"}, follow_redirects=False)
    assert r.status_code == 400
    for ad in ("ad", "vergi_dairesi", "satir1", "sehir", "telefon"):
        assert f'id="hata-{ad}"' in r.text, ad
    r = istemci.post("/tr/hesabim/fatura", data={
        "csrf": csrf, "ad": "Anadolu Makine Sanayi A.Ş.", "vergi_dairesi": "Meram", "satir1": "OSB 5. Cd. No: 9",
        "satir2": "", "posta_kodu": "42300", "sehir": "Konya", "telefon": "+90 332 000 00 00"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/tr/hesabim/fatura"
    assert "Fatura bilgileriniz kaydedildi" in _bildirimler(   # G3l madde 12 metni
        istemci.get("/tr/hesabim/fatura").text)
    m = db.execute("SELECT ad, vergi_dairesi, vergi_kimlik_no FROM musteri WHERE eposta = 'fb1@ornek.test'").fetchone()
    assert tuple(m) == ("Anadolu Makine Sanayi A.Ş.", "Meram", GECERLI_VKN)
    # ödeme: fatura bilgisi ve fatura adresi yeni bilgilerle; metin bu sayfaya bağlanır
    _kur(db)
    uid = _urun(db, sku="S-FB1", ad="Fatura Ürünü", fiyat="10.00", stok=5)
    _sepete_ekle(istemci, uid)
    odeme = istemci.get("/tr/odeme").text
    blok = re.search(r'<section class="fatura-bilgisi".*?</section>', odeme, re.S).group(0)
    assert "Anadolu Makine Sanayi A.Ş." in blok and "Meram" in blok
    assert 'href="/tr/hesabim/fatura"' in blok
    assert 'value="OSB 5. Cd. No: 9"' in odeme and 'value="+90 332 000 00 00"' in odeme
    r = istemci.get("/en/account/billing", follow_redirects=False)                        # EN takma ad
    assert r.status_code == 301 and r.headers["location"] == "/en/hesabim/fatura"


def test_g3i_fatura_bilgilerim_yurtdisi_vat_salt_okunur(istemci, db):
    _musteri(db, tip=MusteriTipi.YURTDISI, eposta="fb2@ornek.test", ulke="DE", vat_id="DE123456789")
    _giris(istemci, "fb2@ornek.test", dil="en")
    html = istemci.get("/en/hesabim/fatura").text
    assert "DE123456789" in html and 'name="vat_id"' not in html and 'name="vergi_dairesi"' not in html
    assert "contact us" in _metin(html)


@pytest.mark.parametrize("deger,gecerli", [
    ("1234567890", True), ("4728136592", True), ("10000000146", True),
    ("1234567891", False), ("10000000147", False), ("01234567890", False), ("123456789", False),
])
def test_g3i_vkn_tckn_saglama_kayit_ve_teklif(istemci, deger, gecerli):
    csrf = csrf_al(istemci, "/tr/kayit")
    r = istemci.post("/tr/kayit", data={"csrf": csrf, "tip": "kurumsal", "ad": "Firma", "eposta": f"v{deger}@ornek.test",
                                        "parola": PAROLA, "vergi_kimlik_no": deger, "vergi_dairesi": "Meram",
                                        "kvkk_onay": "1"}, follow_redirects=False)
    assert (r.status_code == 303) is gecerli, r.text[:300]
    istemci.cookies.clear()
    csrf = csrf_al(istemci, "/tr/teklif")
    r = istemci.post("/tr/teklif", data={"csrf": csrf, "ad": "A", "eposta": "a@ornek.test", "ulke": "TR", "adet": "1",
                                         "mesaj": "m", "kvkk_onay": "1", "vkn": deger}, follow_redirects=False)
    assert (r.status_code == 303) is gecerli
    if not gecerli:
        assert 'id="hata-vkn"' in r.text


def test_g3i_vkn_gomulu_hesap_ve_e2e_ornegi(istemci, db):
    from pathlib import Path
    from app.hesap.dogrulama import tckn_gecerli, vkn_gecerli
    e2e = Path("e2e/test_kabul.py").read_text(encoding="utf-8")
    ornek = re.search(r'TEST_VKN = "(\d+)"', e2e).group(1)
    assert vkn_gecerli(ornek) or tckn_gecerli(ornek)                 # e2e örnek değeri algoritmaya göre geçerli
    _kur(db)
    uid = _urun(db, sku="S-VK1", ad="VKN Ürünü", fiyat="10.00", stok=5)
    _sepete_ekle(istemci, uid)
    sayfa = istemci.get("/tr/odeme").text
    form = _adres_formu()
    form.update({"hesap_tip": "kurumsal", "hesap_eposta": "gv@ornek.test", "hesap_parola": PAROLA,
                 "hesap_kvkk_onay": "1", "hesap_firma": "Firma", "hesap_vkn": "10000000147",
                 "hesap_vergi_dairesi": "Meram"})
    for ad in ("csrf", "gosterilen_toplam", "gosterilen_kur"):
        form[ad] = _gizli(sayfa, ad)
    r = istemci.post("/tr/odeme", data=form, follow_redirects=False)
    assert r.status_code == 400 and 'id="hata-hesap_vkn"' in r.text
    form["hesap_vkn"] = "10000000146"
    assert istemci.post("/tr/odeme", data=form, follow_redirects=False).status_code == 303


# =====================================================================================================
# C — güven ve içerik
# =====================================================================================================

ORNEK_TR = "demo için elle girilmiş durum kaydı"     # G3k madde 22 (önce "örnek: …")
ORNEK_EN = "condition entered manually for the demo"


def test_g3i_ornek_rozeti_aciklamasi(istemci, db):
    uid = _urun(db, sku="S-OR1", ad="Örnek Durumlu Ürün", fiyat="10.00", stok=3)
    uid2 = _urun(db, sku="S-OR2", ad="Gerçek Durumlu Ürün", fiyat="12.00", stok=3)
    with db:
        db.execute("UPDATE urun SET durum_kodu = 'yeni', durum_ornek = 1 WHERE id = ?", (uid,))
        db.execute("UPDATE urun SET durum_kodu = 'yeni', durum_ornek = 0 WHERE id = ?", (uid2,))
    urun = sayfa_denetle(istemci.get(f"/tr/urun/{uid}"))
    durum = re.search(r'<p class="urun-durum">(.*?)</p>', urun, re.S).group(1)
    assert f'<span class="rozet rozet-ornek" title="{ORNEK_TR}">demo kaydı</span>' in durum
    assert f'<span class="ornek-aciklama">{ORNEK_TR}</span>' in durum
    assert ORNEK_EN in istemci.get(f"/en/urun/{uid}").text
    assert ORNEK_TR not in istemci.get(f"/tr/urun/{uid2}").text        # gerçek durumda açıklama yok
    liste = istemci.get("/tr/urunler").text
    # G3j madde 18: listede rozet metni "demo kaydı" (ürün sayfası açıklaması aynı kalır)
    assert '<span class="rozet rozet-ornek" title="demo için elle girilmiş durum kaydı">demo kaydı</span>' in liste
    # karşılaştırma: durum hücresi açıklamayla
    for u in (uid, uid2):
        istemci.post("/tr/karsilastir/ekle", data={"csrf": csrf_al(istemci, "/tr/urunler"), "urun_id": str(u)})
    tablo = _metin(istemci.get("/tr/karsilastir").text)
    assert f"Yeni ({ORNEK_TR})" in tablo


def test_g3i_belirtilmemis_durum_guvencesi(istemci, db):
    metin = ("Durum belirtilmemiş: siparişten sonra 1 iş günü içinde fotoğraf/test raporunu e-postayla gönderiyoruz; "
             "uygun bulmazsanız siparişi ücretsiz iptal edebilirsiniz (temsili)")
    uid = _urun(db, sku="S-BD1", ad="Durumsuz Ürün", fiyat="10.00", stok=3)
    # G3m madde 7: ayrı güvence satırı yalnız bireysel görünümde (ticari / misafirde iade satırıyla tek cümle)
    _musteri(db, eposta="bd1@ornek.test")
    _giris(istemci, "bd1@ornek.test")
    html = sayfa_denetle(istemci.get(f"/tr/urun/{uid}"))
    kutu = re.search(r'<p class="durum-guvence"[^>]*data-e2e="durum-guvence"[^>]*>(.*?)</p>', html, re.S)
    assert kutu and metin in _metin(kutu.group(1))
    assert html.index('data-e2e="sepete-ekle"') < html.index('data-e2e="durum-guvence"')   # satın alma kutusunda
    en = _metin(istemci.get(f"/en/urun/{uid}").text)
    assert ("Condition not specified: within 1 business day after the order we e-mail photos/test report; if it does "
            "not suit you, you can cancel the order free of charge (indicative)") in en
    with db:
        db.execute("UPDATE urun SET durum_kodu = 'yeni' WHERE id = ?", (uid,))
    assert 'data-e2e="durum-guvence"' not in istemci.get(f"/tr/urun/{uid}").text
    from pathlib import Path
    notlar = " ".join(Path("docs/hukuk-notlari.md").read_text(encoding="utf-8").split())
    assert "uygun bulmazsanız siparişi ücretsiz iptal edebilirsiniz" in notlar


TICARI_IADE = ("Ticari alım: cayma hakkı yok; açık ayıplar teslimden itibaren 2 gün içinde yazılı bildirilir; "
               "garanti kapsamında değişim/iade")


def _garanti_satiri(html):
    return _metin(re.search(r'data-e2e="garanti-satiri">(.*?)</p>', html, re.S).group(1))


@pytest.mark.parametrize("tip,ulke,ek", [
    (MusteriTipi.KURUMSAL, "TR", {"vergi_kimlik_no": GECERLI_VKN, "vergi_dairesi": "Selçuk"}),
    (MusteriTipi.YURTDISI, "DE", {"vat_id": "DE123456789"}),
])
def test_g3i_b2b_iade_ozeti_ticari(istemci, db, tip, ulke, ek):
    uid = _urun(db, sku="S-IA1", ad="İade Ürünü", fiyat="10.00", stok=3)
    with db:   # G3m madde 7: belirtilmemiş durumun ticari satırı ayrı (test_g3m_belirtilmemis_ticari_tek_satir)
        db.execute("UPDATE urun SET durum_kodu = 'yeni' WHERE id = ?", (uid,))
    _musteri(db, tip=tip, eposta="ia@ornek.test", ulke=ulke, **ek)
    _giris(istemci, "ia@ornek.test")
    satir = _garanti_satiri(istemci.get(f"/tr/urun/{uid}").text)
    assert TICARI_IADE in satir and "14 gün" not in satir
    # sayı yasal sayfayla birebir (İade sayfası B: "Açıkça belli olan ayıpları teslimden itibaren 2 gün içinde")
    iade = _metin(istemci.get("/tr/yasal/iade").text)
    assert "Açıkça belli olan ayıpları teslimden itibaren 2 gün içinde" in iade
    from app.web.baglam import ACIK_AYIP_IHBAR_GUN
    assert ACIK_AYIP_IHBAR_GUN == 2
    en = _garanti_satiri(istemci.get(f"/en/urun/{uid}").text)
    assert ("Business purchase: no right of withdrawal; obvious defects must be notified in writing within 2 days of "
            "delivery; replacement/refund under warranty") in en


def test_g3i_b2b_iade_ozeti_misafir_ve_bireysel(istemci, db):
    uid = _urun(db, sku="S-IA2", ad="İade Ürünü 2", fiyat="10.00", stok=3)
    with db:   # G3m madde 7: belirtilmemiş durumun ticari satırı ayrı
        db.execute("UPDATE urun SET durum_kodu = 'yeni' WHERE id = ?", (uid,))
    html = istemci.get(f"/tr/urun/{uid}").text
    satirlar = re.findall(r'<span class="iade-satir">(.*?)</span>', re.search(
        r'data-e2e="garanti-satiri">(.*?)</p>', html, re.S).group(1), re.S)
    assert len(satirlar) == 2
    assert "Bireysel alım: 14 gün cayma hakkı" in _metin(satirlar[0])
    assert TICARI_IADE in _metin(satirlar[1])
    _musteri(db, eposta="ib@ornek.test")
    _giris(istemci, "ib@ornek.test")
    satir = _garanti_satiri(istemci.get(f"/tr/urun/{uid}").text)
    assert "İade 14 gün (temsili)" in satir and "Ticari alım" not in satir      # bireysel: mevcut


def _aciklama_ekle(db, uid, metin, kaynak="llm-taslak"):
    with db:
        db.execute("INSERT INTO urun_aciklama (urun_id, dil, metin, kaynak, model, uretildi) VALUES (?, 'tr', ?, ?, 'm', 'z')",
                   (uid, metin, kaynak))


def _teknik_ekle(db, uid, ozellikler=(), bolumler=()):
    import json
    with db:
        db.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)",
                   (uid, json.dumps({"ozellikler": [list(x) for x in ozellikler], "bolumler": [list(x) for x in bolumler]})))


def test_g3i_zayif_taslak_aciklama_gizlenir(istemci, db):
    sablon = "Bu ürün endüstriyel otomasyon sistemlerinde güvenilir performans sunan bir bileşendir."
    zayif = _urun(db, sku="S-ZA1", ad="ABB ZAYIF ÜRÜN", fiyat="10.00", stok=3, uretici_kodu="3HAC-ZA1")
    _aciklama_ekle(db, zayif, sablon)
    html = sayfa_denetle(istemci.get(f"/tr/urun/{zayif}"))
    assert sablon not in html                                           # sayfa, meta ve JSON-LD'de yok
    blok = re.search(r'<div class="aciklama-bilinen" data-e2e="aciklama-bilinen">(.*?)</div>', html, re.S)
    assert blok, "olgusal blok yok"
    m = _metin(blok.group(1))
    assert ("Kaynakta ayrıntılı açıklama yok. Bilinenler: marka, parça no, kategori, durum. Teknik veri sayfası "
            "(datasheet) için teklif isteyin.") in m
    assert "ABB" in m and "3HAC-ZA1" in m and "Belirtilmemiş" in m
    assert f'href="/tr/teklif?urun_id={zayif}"' in blok.group(1)
    assert db.execute("SELECT COUNT(*) FROM urun_aciklama WHERE urun_id = ?", (zayif,)).fetchone()[0] == 1   # silinmez
    # teknik veri ya da kaynak açıklama varsa taslak gösterilir
    ozellikli = _urun(db, sku="S-ZA2", ad="ABB ÖZELLİKLİ", fiyat="10.00", stok=3)
    _aciklama_ekle(db, ozellikli, sablon)
    _teknik_ekle(db, ozellikli, ozellikler=[("Gerilim", "24 V")])
    bolumlu = _urun(db, sku="S-ZA3", ad="ABB BÖLÜMLÜ", fiyat="10.00", stok=3)
    _aciklama_ekle(db, bolumlu, sablon)
    _teknik_ekle(db, bolumlu, bolumler=[("", "Kaynak açıklama satırı")])
    kaynakli = _urun(db, sku="S-ZA4", ad="ABB KAYNAKLI", fiyat="10.00", stok=3)
    _aciklama_ekle(db, kaynakli, "Kaynaktan gelen açıklama.", kaynak="kaynak")
    for u, metin in ((ozellikli, sablon), (bolumlu, sablon), (kaynakli, "Kaynaktan gelen açıklama.")):
        html = istemci.get(f"/tr/urun/{u}").text
        assert metin in html and 'data-e2e="aciklama-bilinen"' not in html, u


def test_g3i_metin_datasheet_ve_tr_vergi_basligi(istemci, db):
    uid = _urun(db, sku="S-MT1", ad="Belgesiz Ürün", fiyat="10.00", stok=3)
    html = istemci.get(f"/tr/urun/{uid}").text
    assert "Teknik veri sayfası (datasheet) talep üzerine" in html and "föy" not in html.lower()
    teklif = istemci.get("/tr/teklif").text
    blok = re.search(r'<fieldset class="yalniz-tr" data-e2e="teklif-tr-vergi">(.*?)</fieldset>', teklif, re.S)
    assert blok
    legend = re.search(r"<legend>(.*?)</legend>", blok.group(1), re.S)
    assert legend and _metin(legend.group(1)) == "Türkiye'deki firmalar için vergi bilgileri"
    assert blok.group(1).index("</legend>") < blok.group(1).index("(yalnız Türkiye)")
    assert "Tax details for companies in Turkey" in istemci.get("/en/teklif").text


def _hizli(istemci, yol="/tr/teklif", **ek):
    csrf = csrf_al(istemci, yol)
    veri = {"csrf": csrf, "ad": "Teknisyen", "iletisim": "+90 532 000 00 00", "parca_kodu": "KPS-600/20"}
    veri.update(ek)
    return istemci.post("/tr/teklif/hizli", data=veri, follow_redirects=False)


def test_g3i_hizli_talep_aciliyet_adet_model(istemci, db):
    for yol in ("/tr/teklif", "/tr/ara?q=yokboylebirkod"):
        html = istemci.get(yol).text
        form = re.search(r'<form class="hizli-teklif"[^>]*action="/tr/teklif/hizli".*?</form>', html, re.S).group(0)
        for deger, etiket in (("acil", "Hat durdu – acil"), ("bu_hafta", "Bu hafta"), ("planli", "Planlı")):
            assert re.search(rf'name="aciliyet" value="{deger}"', form) and etiket in _metin(form), (yol, deger)
        assert "checked" not in re.search(r'<fieldset class="aciliyet".*?</fieldset>', form, re.S).group(0)
        assert 'name="adet"' in form and 'name="model"' in form
    r = _hizli(istemci, aciliyet="acil", adet="3", model="KUKA KR C4")
    assert r.status_code == 303
    t = db.execute("SELECT aciliyet, adet, model FROM teklif ORDER BY id DESC").fetchone()
    assert tuple(t) == ("acil", 3, "KUKA KR C4")
    onay = _metin(istemci.get(r.headers["location"]).text)
    assert "Acil talepler öncelikle aranır (temsili)" in onay
    r = _hizli(istemci)                                                   # seçimsiz: zorunlu değil
    assert r.status_code == 303
    assert tuple(db.execute("SELECT aciliyet, adet, model FROM teklif ORDER BY id DESC").fetchone()) == (None, 1, None)
    r = _hizli(istemci, aciliyet="xx", adet="0")
    assert r.status_code == 400 and 'id="hata-aciliyet"' in r.text and 'id="hata-adet"' in r.text
    # yönetim: acil olanlar üstte ve işaretli
    _hizli(istemci, aciliyet="planli")
    csrf = csrf_al(istemci, "/yonetim/giris")
    istemci.post("/yonetim/giris", data={"kullanici": "yonetici", "parola": "yonetici-parola-123", "csrf": csrf})
    html = istemci.get("/yonetim/teklifler").text
    satirlar = re.findall(r"<tr[^>]*>(.*?)</tr>", re.search(r"<tbody>(.*?)</tbody>", html, re.S).group(1), re.S)
    assert 'data-e2e="teklif-acil"' in satirlar[0] and "KUKA KR C4" in satirlar[0]
    assert all('data-e2e="teklif-acil"' not in s for s in satirlar[1:])
    assert "Planlı" in _metin(html)


def test_g3i_teklif_onayi_ozeti(istemci, db):
    uid = _urun(db, sku="S-TO1", ad="Özet Ürünü", fiyat="10.00", stok=3, uretici_kodu="KPS-600/20-ESC")
    csrf = csrf_al(istemci, f"/tr/teklif?urun_id={uid}")
    mesaj = "A" * 190 + "BBBBBBBBBB" + "CCCCC"
    r = istemci.post("/tr/teklif", data={
        "csrf": csrf, "ad": "Hans Muster", "firma": "Muster GmbH", "eposta": "hans@muster.test", "telefon": "+49 30 1234567",
        "ulke": "DE", "vat_id": "DE123456789", "urun_id": str(uid), "adet": "2", "mesaj": mesaj, "kvkk_onay": "1",
        "musteri_po": "PO-77"}, follow_redirects=False)
    assert r.status_code == 303
    html = sayfa_denetle(istemci.get(r.headers["location"]))
    ozet = _metin(re.search(r'<dl class="teklif-ozet-iletisim"[^>]*>(.*?)</dl>', html, re.S).group(1))
    for metin in ("hans@muster.test", "+49 30 1234567", "Muster GmbH", "DE123456789", "PO-77"):
        assert metin in ozet, metin
    assert "A" * 190 + "BBBBBBBBBB" in ozet and "CCCCC" not in ozet       # mesajın ilk 200 karakteri
    assert "2 × Özet Ürünü" in _metin(html)
    # TR alıcıda VKN
    istemci.cookies.clear()
    csrf = csrf_al(istemci, "/tr/teklif")
    r = istemci.post("/tr/teklif", data={"csrf": csrf, "ad": "A", "eposta": "a@ornek.test", "ulke": "TR", "adet": "1",
                                         "mesaj": "m", "kvkk_onay": "1", "vkn": GECERLI_VKN}, follow_redirects=False)
    assert GECERLI_VKN in _metin(istemci.get(r.headers["location"]).text)


def test_g3i_en_iletisim_saatleri_ve_eposta(istemci, db):
    saat = "Mon–Fri 08:30–18:00 (TRT, UTC+3)"
    en = sayfa_denetle(istemci.get("/en/"))
    alt = _metin(re.search(r'<footer class="alt">(.*?)</footer>', en, re.S).group(1))
    assert saat in alt and "mailto:" not in en                         # e-posta ayarı yoksa gizli
    assert saat in _metin(istemci.get("/en/yasal/kunye").text)
    tr_alt = _metin(re.search(r'<footer class="alt">(.*?)</footer>', istemci.get("/tr/").text, re.S).group(1))
    assert "Hafta içi 08:30–18:00 (TSİ, UTC+3)" in tr_alt
    from dataclasses import replace
    istemci.app.state.ayarlar = replace(istemci.app.state.ayarlar, eposta="sales@ceylanrobot.test")
    en = istemci.get("/en/").text
    alt = re.search(r'<footer class="alt">(.*?)</footer>', en, re.S).group(1)
    assert 'href="mailto:sales@ceylanrobot.test"' in alt
    assert 'href="mailto:sales@ceylanrobot.test"' in istemci.get("/en/yasal/kunye").text


# =====================================================================================================
# İnceleme turu 1
# =====================================================================================================

def _fatura_degistir(istemci, **ek):
    html = istemci.get("/tr/hesabim/fatura").text
    veri = {"csrf": _gizli(html, "csrf"), "ad": "YENI UNVAN LTD", "vergi_dairesi": "YeniVD",
            "satir1": "Yeni Cd. 1", "sehir": "Ankara", "telefon": ""}
    veri.update(ek)
    return istemci.post("/tr/hesabim/fatura", data=veri, follow_redirects=False)


def test_g3i_f1_alici_anlik_goruntu_proforma_ve_onay(istemci, db):
    # I-1: alıcı unvan/tip/VKN/vergi dairesi/VAT ID sipariş anında yazılır; fatura bilgileri sonradan değişse de eski
    # siparişin proforması, onayı ve Hesabım ayrıntısı değişmez
    no, _ = _havale_siparisi(istemci, db, "an1@ornek.test")
    s = db.execute("SELECT alici_unvan, alici_tip, alici_vkn, alici_vergi_dairesi, alici_vat_id FROM siparis WHERE no = ?",
                   (no,)).fetchone()
    assert tuple(s) == ("QATestUser kurumsal", "kurumsal", GECERLI_VKN, "Selçuk", None)
    assert _fatura_degistir(istemci).status_code == 303
    for yol in (f"/tr/hesabim/siparis/{no}/proforma", f"/tr/siparis/{no}", f"/tr/hesabim/siparis/{no}"):
        m = _metin(istemci.get(yol).text.split("<main", 1)[1])
        assert "QATestUser kurumsal" in m and "Selçuk" in m, yol
        assert "YENI UNVAN LTD" not in m and "YeniVD" not in m, yol


def test_g3i_f1_alici_anlik_goruntu_gomulu_hesap_ve_yurtdisi(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-AN2", ad="Gömülü Ürün", fiyat="10.00", stok=5)
    _sepete_ekle(istemci, uid)
    sayfa = istemci.get("/tr/odeme").text
    form = _adres_formu(odeme_yontemi="havale")
    form.update({"hesap_tip": "kurumsal", "hesap_eposta": "an2@ornek.test", "hesap_parola": PAROLA,
                 "hesap_kvkk_onay": "1", "hesap_firma": "Gömülü Firma A.Ş.", "hesap_vkn": "4728136592",
                 "hesap_vergi_dairesi": "Meram"})
    for ad in ("csrf", "gosterilen_toplam", "gosterilen_kur"):
        form[ad] = _gizli(sayfa, ad)
    assert istemci.post("/tr/odeme", data=form, follow_redirects=False).status_code == 303
    s = db.execute("SELECT alici_unvan, alici_tip, alici_vkn, alici_vergi_dairesi FROM siparis").fetchone()
    assert tuple(s) == ("Gömülü Firma A.Ş.", "kurumsal", "4728136592", "Meram")
    istemci.cookies.clear()
    no, _ = _havale_siparisi(istemci, db, "an3@ornek.test", tip=MusteriTipi.YURTDISI, ulke="DE", dil="en")
    s = db.execute("SELECT alici_tip, alici_vkn, alici_vat_id FROM siparis WHERE no = ?", (no,)).fetchone()
    assert tuple(s) == ("yurtdisi", None, "DE123456789")


def test_g3i_f1_eski_siparis_yedegi(istemci, db):
    # anlık görüntü NULL (G3i öncesi sipariş): ad fatura adresindeki ad, vergi bilgileri hesaptan
    no, _ = _havale_siparisi(istemci, db, "an4@ornek.test")
    with db:
        db.execute("UPDATE siparis SET alici_unvan = NULL, alici_tip = NULL, alici_vkn = NULL, alici_vergi_dairesi = NULL"
                   " WHERE no = ?", (no,))
    m = _metin(istemci.get(f"/tr/hesabim/siparis/{no}/proforma").text)
    assert "QATestUser Alıcı" in m and GECERLI_VKN in m and "Selçuk" in m


def test_g3i_f1_fatura_sahte_post_vergi_no_degismez(istemci, db):
    _kurumsal(db, "an5@ornek.test")
    _giris(istemci, "an5@ornek.test")
    assert _fatura_degistir(istemci, vergi_kimlik_no="4728136592", vat_id="DE999999999", tip="bireysel",
                            eposta="baska@ornek.test").status_code == 303
    m = db.execute("SELECT tip, vergi_kimlik_no, vat_id, eposta FROM musteri WHERE eposta = 'an5@ornek.test'").fetchone()
    assert tuple(m) == ("kurumsal", GECERLI_VKN, None, "an5@ornek.test")


def test_g3i_f1_baskasinin_siparisine_tekrar_post_404(istemci, db):
    no, _ = _havale_siparisi(istemci, db, "an6@ornek.test")
    istemci.cookies.clear()
    _kurumsal(db, "an7@ornek.test")
    _giris(istemci, "an7@ornek.test")
    csrf = csrf_al(istemci, "/tr/hesabim")
    assert istemci.post(f"/tr/hesabim/siparis/{no}/tekrar", data={"csrf": csrf}).status_code == 404


def test_g3i_f1_tekrar_ekle_ust_sinir_bildirimi(istemci, db):
    # M-2: stoku bilinmeyen üründe 99 üst sınırı "stok" değil genel üst sınır bildirimiyle
    no, uid = _havale_siparisi(istemci, db, "an8@ornek.test", adet="3")
    with db:
        db.execute("UPDATE urun SET stok = 0 WHERE id = ?", (uid,))
        db.execute("INSERT INTO sepet_kalemi (sepet_id, urun_id, adet) SELECT id, ?, 98 FROM sepet", (uid,))
    html = istemci.get(f"/tr/hesabim/siparis/{no}").text
    istemci.post(f"/tr/hesabim/siparis/{no}/tekrar", data={"csrf": _gizli(html, "csrf")}, follow_redirects=False)
    bildirim = _bildirimler(istemci.get("/tr/sepet").text)
    assert "en fazla 99 adet" in bildirim and "stok sınırı" not in bildirim


def test_g3i_f1_proforma_birim_notu_ve_durum(istemci, db):
    no, _ = _havale_siparisi(istemci, db, "an9@ornek.test")
    m = _metin(istemci.get(f"/tr/hesabim/siparis/{no}/proforma").text)
    assert "Birim fiyat yuvarlanmıştır" in m                            # M-3
    with db:
        db.execute("UPDATE siparis SET durum = 'odendi' WHERE no = ?", (no,))
    html = istemci.get(f"/tr/hesabim/siparis/{no}/proforma").text
    assert 'data-e2e="pb-durum"' in html and "ÖDENDİ" in _metin(html)    # M-4
    with db:
        db.execute("UPDATE siparis SET durum = 'iptal' WHERE no = ?", (no,))
    assert istemci.get(f"/tr/hesabim/siparis/{no}/proforma").status_code == 404
    assert "/proforma" not in istemci.get(f"/tr/hesabim/siparis/{no}").text


def test_g3i_f1_sayfa_a4_yalniz_proforma(istemci):
    # M-5: A4 kenar boşluğu adlandırılmış sayfada; diğer sayfaların yazdırması etkilenmez
    from pathlib import Path
    css = Path("app/web/statik/site.css").read_text(encoding="utf-8")
    assert re.search(r"@page proforma\s*\{[^}]*size:\s*A4", css)
    assert not re.search(r"@page\s*\{", css)
    assert ".proforma-belge * { break-inside" not in css


def test_g3i_f1_kapanmis_acil_isaretsiz(istemci, db):
    # M-6
    _hizli(istemci, aciliyet="acil")
    with db:
        db.execute("UPDATE teklif SET durum = 'kapandi'")
    csrf = csrf_al(istemci, "/yonetim/giris")
    istemci.post("/yonetim/giris", data={"kullanici": "yonetici", "parola": "yonetici-parola-123", "csrf": csrf})
    assert 'data-e2e="teklif-acil"' not in istemci.get("/yonetim/teklifler").text


def test_g3i_f1_onay_eur_sipariste_try_secimi(istemci, db):
    # M-1 (kural): EUR tahsilatlı siparişte kur sabitlenmez; onay, seçilen ₺ gösterimine rağmen € gösterir
    no, _ = _havale_siparisi(istemci, db, "an10@ornek.test", tip=MusteriTipi.YURTDISI, ulke="DE", dil="en")
    _fiyat_sec(istemci, "try")
    ozet = _ozet(istemci.get(f"/tr/siparis/{no}").text)
    assert "₺" not in ozet and "€" in ozet


def test_g3i_f1_hesabim_toplam_kdv_bazi(istemci, db):
    # M-9
    no, _ = _havale_siparisi(istemci, db, "an11@ornek.test")
    # G3k madde 15: tek toplam satırı yerine tutar özeti (KDV satırları ayrı): KDV bazı satırlardan okunur
    metin = _metin(istemci.get(f"/tr/hesabim/siparis/{no}").text)
    assert "Genel toplam" in metin and "KDV (ürünler)" in metin and "Ara toplam (KDV hariç)" in metin
