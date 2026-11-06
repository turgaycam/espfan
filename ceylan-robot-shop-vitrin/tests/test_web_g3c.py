"""G3c (Ö4 madde 17–22, Ö5 madde 23, madde 24 karşılaştırma) + ertelenen inceleme maddeleri (G3a N-1/N-1b/N-4,
G3a e-posta boş endişesi, G3b N-4)."""
import csv
import io
import re
from html import unescape
from pathlib import Path

import pytest

from app.fiyat.kurallar import MusteriTipi
from app.hesap.dogrulama import eposta_gecerli, telefon_gecerli, vat_id_kontrol
from app.katalog.kategori_ceviri import KategoriCeviri
from app.teklif.servis import TeklifGirdisi, TeklifHatasi, teklif_olustur
from tests.conftest import csrf_al, istemci_db, kategori_ekle, oturum_oku, sayfa_denetle, urun_ekle
from tests.test_web_katalog import katalog  # noqa: F401 — fixture
from tests.test_web_sepet_odeme import GECERLI_VKN, _giris, _kur, _musteri, _sepete_ekle, _urun, db  # noqa: F401

KOK = Path(__file__).resolve().parent.parent
CANLI_KATEGORILER = KOK / "tests" / "ornekler" / "kategori_adlari_canli.txt"
SITE_CSS = KOK / "app" / "web" / "statik" / "site.css"


def _post(istemci, yol, veri, csrf_yolu="/tr/"):
    veri = {**veri, "csrf": csrf_al(istemci, csrf_yolu)}
    return istemci.post(yol, data=veri, follow_redirects=False)


def _bildirimler(html):
    m = re.search(r'<div class="bildirimler" role="status">(.*?)</div>', html, re.S)
    return m.group(1) if m else ""


def _sepet_sayaci(html):
    m = re.search(r'class="nav-oge sepet-bag".*?<span class="sayac"[^>]*>(\d+)</span>', html, re.S)
    assert m, "sepet sayacı yok"
    return int(m.group(1))


# =====================================================================================================
# Madde 17 — Sepete ekle sayfada kalır
# =====================================================================================================

def test_g3c_sepete_ekle_urun_sayfasinda_kalir(istemci, katalog):
    yol = f"/tr/urun/{katalog['role']}"
    html = istemci.get(yol).text
    form = re.search(r'<form class="sepet-form".*?</form>', html, re.S).group(0)
    assert f'<input type="hidden" name="sonraki" value="{yol}">' in form
    r = _post(istemci, "/tr/sepet/ekle", {"urun_id": katalog["role"], "adet": "2", "sonraki": yol}, yol)
    assert r.status_code == 303 and r.headers["location"] == f"{yol}#urun-{katalog['role']}"   # G3e madde 18
    sayfa = sayfa_denetle(istemci.get(yol))
    bildirim = _bildirimler(sayfa)
    assert "Sepete eklendi" in bildirim and "RÖLE MODÜLÜ 24V" in bildirim
    assert '<a href="/tr/sepet" data-e2e="sepete-git">Sepete git</a>' in bildirim
    assert _sepet_sayaci(sayfa) == 2
    assert "Sepete eklendi" not in _bildirimler(istemci.get(yol).text)   # bildirim bir kez


def test_g3c_sepete_ekle_liste_filtresi_korunur(istemci, katalog):
    yol = f"/tr/kategori/{katalog['elk']}?stokta=1&sira=fiyat_artan"
    html = istemci.get(yol).text
    assert 'name="sonraki" value="/tr/kategori/{}?stokta=1&amp;sira=fiyat_artan"'.format(katalog["elk"]) in html
    r = _post(istemci, "/tr/sepet/ekle", {"urun_id": katalog["role"], "adet": "1", "sonraki": unescape(
        f"/tr/kategori/{katalog['elk']}?stokta=1&sira=fiyat_artan")}, yol)
    assert (r.status_code == 303 and r.headers["location"]
            == f"/tr/kategori/{katalog['elk']}?stokta=1&sira=fiyat_artan#urun-{katalog['role']}")
    assert _sepet_sayaci(istemci.get(r.headers["location"]).text) == 1


@pytest.mark.parametrize("sonraki", ["", "https://evil.example/x", "//evil.example", "/tr/\\evil"])
def test_g3c_sepete_ekle_guvensiz_sonraki_sepete_doner(istemci, katalog, sonraki):
    r = _post(istemci, "/tr/sepet/ekle", {"urun_id": katalog["role"], "adet": "1", "sonraki": sonraki})
    assert r.status_code == 303 and r.headers["location"] == "/tr/sepet?eklendi=1"


def test_g3c_sepete_ekle_en_bildirimi(istemci, katalog):
    yol = f"/en/urun/{katalog['role']}"
    r = _post(istemci, "/en/sepet/ekle", {"urun_id": katalog["role"], "adet": "1", "sonraki": yol}, yol)
    bildirim = _bildirimler(istemci.get(r.headers["location"]).text)
    assert "Added to cart" in bildirim and '<a href="/en/sepet" data-e2e="sepete-git">Go to cart</a>' in bildirim


# =====================================================================================================
# Madde 18 — ödemeye giriş: açıklama, kayıt -> sonraki
# =====================================================================================================

def test_g3c_giris_odeme_icin_hesap_aciklamasi_ve_kayit_baglantisi(istemci):
    html = sayfa_denetle(istemci.get("/tr/giris", params={"sonraki": "/tr/odeme"}))
    assert "Siparişi takip edebilmeniz için hesap gerekir" in html
    assert 'href="/tr/kayit?sonraki=%2Ftr%2Fodeme"' in html
    html = istemci.get("/tr/giris").text
    assert "Siparişi takip edebilmeniz için hesap gerekir" not in html
    assert 'href="/tr/kayit"' in html


def test_g3c_kayit_sayfasi_giris_baglantisi_sonraki_tasir(istemci):
    html = istemci.get("/tr/kayit", params={"sonraki": "/tr/odeme"}).text
    assert 'href="/tr/giris?sonraki=%2Ftr%2Fodeme"' in html
    assert "Siparişi takip edebilmeniz için hesap gerekir" in html


def test_g3c_odeme_misafir_giris_kayit_sonraki_odemeye_doner(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-ODM", ad="Ödeme Ürünü", fiyat="100.00")
    _sepete_ekle(istemci, uid)
    r = istemci.get("/tr/odeme", follow_redirects=False)     # G3g madde 1: yönlendirme yok, gömülü hesap
    assert r.status_code == 200 and 'href="/tr/giris?sonraki=%2Ftr%2Fodeme"' in r.text
    csrf = csrf_al(istemci, "/tr/kayit?sonraki=/tr/odeme")    # kayıt sayfası yolu aynen çalışır
    r = istemci.post("/tr/kayit", data={"csrf": csrf, "tip": "bireysel", "ad": "QATestUser", "parola": "demo-parola-123",
                                        "eposta": "qatestuser+odeme@example.com", "kvkk_onay": "1",
                                        "sonraki": "/tr/odeme"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/tr/odeme"
    assert istemci.get("/tr/odeme").status_code == 200


# =====================================================================================================
# Madde 19 — kayıt formu tipe göre alanlar, VAT ID doğrulaması
# =====================================================================================================

def test_g3c_kayit_formu_tip_alan_gruplari_ve_css_has(istemci):
    html = sayfa_denetle(istemci.get("/tr/kayit"))
    kurumsal = re.search(r'<fieldset class="tip-alanlari" data-tipler="kurumsal">.*?</fieldset>', html, re.S).group(0)
    assert 'name="vergi_kimlik_no"' in kurumsal and 'name="vergi_dairesi"' in kurumsal
    yurtdisi = re.search(r'<fieldset class="tip-alanlari" data-tipler="yurtdisi">.*?</fieldset>', html, re.S).group(0)
    assert 'name="ulke"' in yurtdisi and 'name="vat_id"' in yurtdisi
    assert re.search(r'<div class="alan" data-tipler="bireysel">.*?name="iys_onay"', html, re.S)
    assert 'class="form kayit-formu"' in html
    css = SITE_CSS.read_text(encoding="utf-8")
    for tip in ("bireysel", "kurumsal", "yurtdisi"):
        assert f'.kayit-formu:has(#a-tip-{tip}:checked) [data-tipler]:not([data-tipler~="{tip}"])' in css


@pytest.mark.parametrize(("ulke", "vat", "beklenen"), [
    ("DE", "DE123456789", ("DE123456789", None)),
    ("DE", "de 123.456-789", ("DE123456789", None)),
    ("DE", "DE12345678", (None, "gecersiz_vat")),
    ("DE", "AT123456789", (None, "vat_ulke_uyumsuz")),
    ("DE", "123456789", ("DE123456789", None)),       # önek yazılmamışsa ülke öneki eklenir
    ("AT", "ATU12345678", ("ATU12345678", None)),
    ("AT", "AT12345678", (None, "gecersiz_vat")),
    ("NL", "NL123456789B01", ("NL123456789B01", None)),
    ("FR", "FRXX123456789", ("FRXX123456789", None)),
    ("IT", "IT12345678901", ("IT12345678901", None)),
    ("PL", "PL1234567890", ("PL1234567890", None)),
    ("DE", "", (None, "zorunlu")),
    ("US", "", (None, None)),
    ("GB", "GB 123 4567 89", ("GB123456789", None)),
    ("FR", "AB123456789", ("FRAB123456789", None)),   # M-6: önek yok, harfli anahtar
    ("FR", "ab 123 456 789", ("FRAB123456789", None)),
    ("FR", "AT123456789", (None, "vat_ulke_uyumsuz")),
    ("US", "xx", (None, "gecersiz_vat")),
])
def test_g3c_vat_id_kontrol(ulke, vat, beklenen):
    assert vat_id_kontrol(vat, ulke, zorunlu_ab=True) == beklenen


def test_g3c_vat_id_kontrol_zorunsuz():
    assert vat_id_kontrol("", "DE", zorunlu_ab=False) == (None, None)
    assert vat_id_kontrol("DE1", "DE", zorunlu_ab=False) == (None, "gecersiz_vat")


@pytest.mark.parametrize(("deger", "gecerli"), [
    ("qa@example.com", True), ("a@b", False), ("a@@b.com", False), ("qa@ornek", False), ("qa example@x.com", False),
])
def test_g3c_eposta_yardimcisi(deger, gecerli):
    assert eposta_gecerli(deger) is gecerli


@pytest.mark.parametrize(("deger", "gecerli"), [
    ("+90 555 000 00 00", True), ("0332 239 15 75", True), ("12345", False), ("abc1234567", False),
])
def test_g3c_telefon_yardimcisi(deger, gecerli):
    assert telefon_gecerli(deger) is gecerli


def _kayit(istemci, **ek):
    csrf = csrf_al(istemci, "/tr/kayit")
    veri = {"csrf": csrf, "tip": "yurtdisi", "ad": "QA Test GmbH", "eposta": "qatestuser+vat@example.com",
            "parola": "demo-parola-123", "kvkk_onay": "1", "ulke": "DE"}
    veri.update(ek)
    return istemci.post("/tr/kayit", data=veri, follow_redirects=False)


def test_g3c_kayit_yurtdisi_ab_vat_zorunlu_ve_bicim(istemci):
    r = _kayit(istemci, vat_id="")
    assert r.status_code == 400 and 'id="h-vat_id"' in r.text and "AB ülkelerindeki firmalar için zorunludur" in r.text
    r = _kayit(istemci, vat_id="DE1234")
    assert r.status_code == 400 and 'id="h-vat_id"' in r.text and 'value="DE1234"' in r.text
    r = _kayit(istemci, vat_id="de 123 456 789")
    assert r.status_code == 303
    with istemci_db(istemci) as con:
        assert con.execute("SELECT vat_id FROM musteri").fetchone()[0] == "DE123456789"


def test_g3c_kayit_yurtdisi_ab_disi_vat_isteğe_bagli(istemci):
    assert _kayit(istemci, ulke="US", vat_id="").status_code == 303


def test_g3c_kayit_bireysel_vat_ve_vkn_yok_sayilir(istemci):
    r = _kayit(istemci, tip="bireysel", vat_id="xx", vergi_kimlik_no="1")
    assert r.status_code == 303


# =====================================================================================================
# Madde 20 — ödeme özetinde fatura bilgileri
# =====================================================================================================

def _odeme_html(istemci, db, tip, **ek):
    _kur(db)
    uid = _urun(db, sku="S-FAT", ad="Fatura Ürünü", fiyat="100.00")
    _musteri(db, tip=tip, eposta=f"{tip.value}@ornek.test", **ek)
    _giris(istemci, f"{tip.value}@ornek.test")
    _sepete_ekle(istemci, uid)
    r = istemci.get("/tr/odeme")
    assert r.status_code == 200
    return r.text


def test_g3c_odeme_kurumsal_fatura_bilgileri(istemci, db):
    html = _odeme_html(istemci, db, MusteriTipi.KURUMSAL, vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    blok = re.search(r'<section class="fatura-bilgisi" data-e2e="fatura-bilgisi".*?</section>', html, re.S).group(0)
    assert "QATestUser kurumsal" in blok and GECERLI_VKN in blok and "Selçuk" in blok
    assert "Unvan" in blok and "VKN/TCKN" in blok and "Vergi dairesi" in blok


def test_g3c_odeme_yurtdisi_vat_id(istemci, db):
    html = _odeme_html(istemci, db, MusteriTipi.YURTDISI, ulke="DE", vat_id="DE123456789")
    blok = re.search(r'<section class="fatura-bilgisi".*?</section>', html, re.S).group(0)
    assert "DE123456789" in blok and "VAT ID" in blok


def test_g3c_odeme_yurtdisi_ab_vat_yoksa_uyari(istemci, db):
    html = _odeme_html(istemci, db, MusteriTipi.YURTDISI, ulke="DE")   # eski (VAT'sız) AB hesabı
    blok = re.search(r'<section class="fatura-bilgisi".*?</section>', html, re.S).group(0)
    assert "VAT ID kayıtlı değil" in blok


def test_g3c_m5_ab_disi_vat_yoksa_uyari_yok(istemci, db):
    html = _odeme_html(istemci, db, MusteriTipi.YURTDISI, ulke="US")
    blok = re.search(r'<section class="fatura-bilgisi".*?</section>', html, re.S).group(0)
    assert "VAT ID kayıtlı değil" not in blok and "—" in blok


def test_g3c_odeme_bireyselde_fatura_bilgisi_blogu_yok(istemci, db):
    html = _odeme_html(istemci, db, MusteriTipi.BIREYSEL)
    assert 'class="fatura-bilgisi"' not in html


# =====================================================================================================
# Madde 21 — teklif formu; G3a e-posta/telefon, N-1, N-1b, N-4; G3b N-4
# =====================================================================================================

def _teklif(istemci, dil="tr", **ek):
    form = {"ad": "QATestUser Misafir", "firma": "", "eposta": "misafir@ornek.test", "telefon": "", "ulke": "TR",
            "adet": "1", "mesaj": "Fiyat ve teslim süresi rica ederiz.", "kvkk_onay": "1", "vat_id": ""}
    form.update(ek)
    form["csrf"] = csrf_al(istemci, f"/{dil}/teklif")
    return istemci.post(f"/{dil}/teklif", data=form, follow_redirects=False)


def test_g3c_teklif_formu_baslik_vat_kvkk(istemci):
    html = sayfa_denetle(istemci.get("/tr/teklif"))
    assert "<h1>Fiyat, teslim ve toplu alım için teklif</h1>" in html
    assert "15.000" not in re.search(r"<h1>.*?</h1>\s*<p class=\"teklif-giris\">.*?</p>", html, re.S).group(0)
    assert 'name="vat_id"' in html and 'name="kvkk_onay"' in html and 'href="/tr/yasal/kvkk"' in html
    assert "Telefon veya e-postadan en az biri" in html
    en = istemci.get("/en/teklif").text
    assert "<h1>Quote for price, delivery and volume orders</h1>" in en


def test_g3c_teklif_firma_kisi_adiyla_dolmaz(istemci, db):
    """G3e madde 17 bu kararı değiştirdi: kurumsal hesapta Firma profildeki unvandan dolar; bireyselde boş kalır."""
    _musteri(db, eposta="bireysel@ornek.test")
    _giris(istemci, "bireysel@ornek.test")
    html = istemci.get("/tr/teklif").text
    assert re.search(r'<input id="firma" name="firma" type="text" value=""', html)
    assert 'value="bireysel@ornek.test"' in html


def test_g3c_teklif_kvkk_onayi_misafirde_zorunlu(istemci):
    r = _teklif(istemci, kvkk_onay="")
    assert r.status_code == 400 and 'id="hata-kvkk_onay"' in r.text and 'value="misafir@ornek.test"' in r.text
    assert _teklif(istemci).status_code == 303
    with istemci_db(istemci) as con:
        satir = con.execute("SELECT kvkk_onay FROM teklif").fetchone()
    assert satir[0]


def test_g3c_teklif_uyede_kvkk_kutusu_istenmez(istemci, db):
    _musteri(db, eposta="bireysel@ornek.test")
    _giris(istemci, "bireysel@ornek.test")
    assert 'name="kvkk_onay"' not in istemci.get("/tr/teklif").text
    assert _teklif(istemci, kvkk_onay="", eposta="bireysel@ornek.test").status_code == 303


def test_g3c_teklif_yalniz_telefonla(istemci):
    r = _teklif(istemci, eposta="", telefon="+90 555 000 00 00")
    assert r.status_code == 303
    with istemci_db(istemci) as con:
        satir = con.execute("SELECT eposta, telefon FROM teklif").fetchone()
    assert satir[0] is None and satir[1] == "+90 555 000 00 00"


def test_g3c_teklif_iletisimsiz_reddedilir(istemci):
    r = _teklif(istemci, eposta="", telefon="")
    assert r.status_code == 400 and "Telefon veya e-postadan en az birini girin" in r.text


@pytest.mark.parametrize(("alan", "deger"), [("eposta", "a@b"), ("eposta", "qa@ornek"), ("telefon", "12")])
def test_g3c_teklif_iletisim_bicimi(istemci, alan, deger):
    r = _teklif(istemci, **{alan: deger})
    assert r.status_code == 400 and f'id="hata-{alan}"' in r.text


def test_g3c_teklif_vat_id_saklanir_ve_yonetimde_gorunur(istemci):
    r = _teklif(istemci, ulke="DE", vat_id="de123456789")
    assert r.status_code == 303
    with istemci_db(istemci) as con:
        assert con.execute("SELECT vat_id FROM teklif").fetchone()[0] == "DE123456789"
    r = _teklif(istemci, ulke="DE", vat_id="DE12")
    assert r.status_code == 400 and 'id="hata-vat_id"' in r.text


def test_g3c_teklif_servisi_eposta_ya_da_telefon(con, simdi):
    t = teklif_olustur(con, TeklifGirdisi(ad="QATestUser", eposta=None, telefon="+90 555 000 00 00", ulke="TR",
                                          mesaj="m"), simdi)
    assert t.eposta is None and t.telefon == "+90 555 000 00 00"
    with pytest.raises(TeklifHatasi) as e:
        teklif_olustur(con, TeklifGirdisi(ad="QATestUser", eposta="", telefon="", ulke="TR", mesaj="m"), simdi)
    assert (e.value.alan, e.value.kod) == ("eposta", "iletisim_gerekli")
    with pytest.raises(TeklifHatasi):
        teklif_olustur(con, TeklifGirdisi(ad="Q", eposta="a@b", ulke="TR", mesaj="m"), simdi)


def test_g3c_teklif_semasi_eposta_bos_olabilir_ama_iletisim_sart(con):
    import sqlite3
    con.execute("INSERT INTO teklif (no, ad, eposta, telefon, ulke, mesaj, olusturma) VALUES "
                "('CR-TKL-20261013-0001', 'Q', NULL, '+90 555', 'TR', 'm', '2026-10-13T09:00:00+00:00')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO teklif (no, ad, eposta, telefon, ulke, mesaj, olusturma) VALUES "
                    "('CR-TKL-20261013-0002', 'Q', NULL, NULL, 'TR', 'm', '2026-10-13T09:00:00+00:00')")


def _hizli(istemci, **ek):
    veri = {"ad": "QATestUser", "iletisim": "+90 555 000 00 00", "parca_kodu": "6ES7 307-1EA00"}
    veri.update(ek)
    veri["csrf"] = csrf_al(istemci, "/tr/teklif")
    return istemci.post("/tr/teklif/hizli", data=veri, follow_redirects=False)


def test_g3c_hizli_teklif_telefonla_eposta_null(istemci):
    assert _hizli(istemci).status_code == 303
    with istemci_db(istemci) as con:
        assert con.execute("SELECT eposta, telefon FROM teklif").fetchone()[:] == (None, "+90 555 000 00 00")


def test_g3c_n1_gecersiz_iletisim_kotayi_harcamaz(istemci):
    for _ in range(6):
        assert _hizli(istemci, iletisim="12").status_code == 400
    assert _hizli(istemci).status_code == 303


def test_g3c_n1b_hizli_teklif_429_formu_girdisiyle_gosterir(istemci):
    for _ in range(5):
        assert _hizli(istemci).status_code == 303
    r = _hizli(istemci, ad="QATestUser Beşinci", parca_kodu="KOD-429")
    assert r.status_code == 429 and r.headers["Retry-After"] == "600"
    html = sayfa_denetle(r)
    assert 'value="QATestUser Beşinci"' in html and 'value="KOD-429"' in html
    assert re.search(r'role="alert".*?10 dakika', html, re.S)
    assert "bir dakika" not in html


def test_g3c_n1b_tam_teklif_429_formu_girdisiyle_gosterir(istemci):
    for _ in range(5):
        assert _teklif(istemci).status_code == 303
    r = _teklif(istemci, mesaj="Kaybolmaması gereken mesaj")
    assert r.status_code == 429 and r.headers["Retry-After"] == "600"
    assert "Kaybolmaması gereken mesaj" in r.text and "10 dakika" in r.text
    assert 'data-e2e="teklif-gonder"' in r.text


def test_g3c_g3b_n4_teklif_ulke_varsayilani_oturum_ulkesi(istemci, db):
    _musteri(db, eposta="bireysel@ornek.test")
    _giris(istemci, "bireysel@ornek.test")
    csrf = csrf_al(istemci, "/tr/")
    istemci.post("/tercih", data={"ulke": "DE", "sonraki": "/tr/", "csrf": csrf}, follow_redirects=False)
    html = istemci.get("/tr/teklif").text
    assert '<option value="DE" selected>' in html


# =====================================================================================================
# Madde 22 — üst çubukta Teklif al, telefon etiketi
# =====================================================================================================

def test_g3c_ust_cubuk_teklif_al_ve_telefon_etiketi(tmp_path):
    from fastapi.testclient import TestClient

    from app.ayarlar import Ayarlar
    from app.hesap.servis import parola_ozeti
    from app.web.uygulama import uygulama_olustur
    from tests.conftest import TEST_GIZLI

    ayarlar = Ayarlar(db_yolu=tmp_path / "w.db", gizli_anahtar=TEST_GIZLI, yonetici_kullanici="y",
                      yonetici_parola_ozeti=parola_ozeti("yonetici-parola-123"), telefon="+90 332 239 15 75")
    with TestClient(uygulama_olustur(ayarlar)) as c:
        html = c.get("/tr/").text
    ust = re.search(r'<header class="ust">.*?</header>', html, re.S).group(0)
    assert re.search(r'<a class="nav-oge nav-teklif" href="/tr/teklif" data-e2e="ust-teklif">.*?Teklif al', ust, re.S)
    bant = re.search(r'<p class="ust-iletisim">.*?</p>', html, re.S).group(0)
    assert '<span class="ust-iletisim-kisa" aria-hidden="true">Telefon</span>' in bant
    css = SITE_CSS.read_text(encoding="utf-8")
    assert ".nav-teklif" in css and ".ust-iletisim-kisa" in css


# =====================================================================================================
# Madde 23 — kategori çevirisi ve EN arayüzde Türkçe kalıntı taraması
# =====================================================================================================

def _canli_kategoriler():
    satirlar = []
    for satir in CANLI_KATEGORILER.read_text(encoding="utf-8").splitlines():
        if satir and not satir.startswith("#"):
            seviye, sayi, ad = satir.split("|", 2)
            satirlar.append((int(seviye), None if sayi == "-" else int(sayi), ad))
    return satirlar


def test_g3c_kategori_cevirisi_kok_ve_sik_alt_kategoriler():
    ceviri = KategoriCeviri()
    satirlar = _canli_kategoriler()
    kokler = [ad for s, _, ad in satirlar if s == 0]
    assert len(kokler) >= 6
    alt = sorted(((n, ad) for s, n, ad in satirlar if s == 1), reverse=True)
    eksik = [ad for ad in kokler + [ad for _, ad in alt[:40]] if ceviri.cevir(ad, "en") is None]
    assert not eksik, eksik
    tum_eksik = [ad for _, _, ad in satirlar if ceviri.cevir(ad, "en") is None]
    assert not tum_eksik, tum_eksik          # bu turda seviye 0–2'nin tamamı çevrildi
    for ad in ("DIGER", "DİĞER", "GÖRÜNTÜ ISLEME SISTEMLERI"):     # yazım farkı aynı çeviriye
        assert ceviri.cevir(ad, "en") in ("OTHER", "MACHINE VISION SYSTEMS")
    assert ceviri.cevir("Endüstriyel Robotlar", "tr") is None and ceviri.metin("Endüstriyel Robotlar", "tr") == "Endüstriyel Robotlar"


def test_g3c_en_kategori_adlari_cevrilir_cevrilmeyen_lang_tr(istemci, katalog):
    with istemci_db(istemci) as con:
        ozel = kategori_ekle(con, kaynak_id="k1019", ad="ZZZ ÖZEL KATEGORİ", yol="10.19", seviye=1, ust_kaynak_id="k10")
        urun_ekle(con, sku="OZ-1", ad="ÖZEL ÜRÜN", kategori_id=ozel)   # G3e: boş kategori ağaçta gösterilmez
    html = sayfa_denetle(istemci.get(f"/en/kategori/{katalog['elk']}"))
    serit = re.search(r'<nav class="kategori-serit".*?</nav>', html, re.S).group(0)
    assert ">Electrical and Electronics<" in serit and ">Industrial Robots<" in serit
    assert "Elektrik ve Elektronik" not in serit
    assert re.search(r"<title>[^<]*Electrical and Electronics", html)
    assert f'<a href="/en/kategori/{ozel}"><span lang="tr">ZZZ Özel Kategori</span>' in html   # G3e: Title Case
    assert "<h1>Electrical and Electronics</h1>" in html
    tr = istemci.get(f"/tr/kategori/{katalog['elk']}").text
    assert "<h1>Elektrik ve Elektronik</h1>" in tr and 'lang="tr"' not in tr.split("<body>", 1)[1]


def test_g3c_en_urun_sayfasi_kirinti_ve_kategori_cevrili(istemci, katalog):
    html = istemci.get(f"/en/urun/{katalog['robot']}").text
    iz = re.search(r'<nav class="iz".*?</nav>', html, re.S).group(0)
    assert ">Industrial Robots<" in iz and ">KUKA<" in iz and ">KR C4<" in iz
    assert "Endüstriyel" not in html.split("<body>", 1)[1]


# EN arayüz taraması: ürün adları/kodları ve lang="tr" ile işaretli içerik hariç Türkçe karakter ve sözcük kalmamalı.
TURKCE_HARF = re.compile(r"[çğışöüÇĞİŞÖÜ]")
TURKCE_SOZCUK = re.compile(
    r"\b(?:ve|için|ile|veya|Sepet|Sepete|Sepetim|Giriş|Çıkış|Üye|Teklif|teklif|Ürün|ürün|Kategori|Fiyat|Stok|stokta|"
    r"Tümü|Ara|Ana sayfa|Hesabım|Karşılaştır|Ödeme|Kargo|Adet|Durum|Marka|Parça|KDV|dahil|hariç|Yurt dışı|"
    r"Gönder|Kaydet|Temizle|Uygula|Sırala|Filtre|Filtrele|Kaldır|Türkçe)\b")
IZINLI = ("Türkiye", "Türkçe", "Selçuklu")  # kayıtlı adres (künye ile aynı)


def _gorunen_metin(html, haric=()):
    govde = html.split("<body>", 1)[1]
    govde = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", govde, flags=re.S)
    govde = re.sub(r'<(span|td|tr|p|h3|div|table|section)[^>]*\blang="tr"[^>]*>.*?</\1>', " ", govde, flags=re.S)
    govde = re.sub(r'<option value="tr"[^>]*>[^<]*</option>', " ", govde)   # dil seçicide "Türkçe" kendi dilinde
    metin = unescape(re.sub(r"<[^>]+>", " ", govde))
    for h in haric:
        metin = metin.replace(h, " ")
    for izinli in IZINLI:
        metin = metin.replace(izinli, " ")
    return metin


def test_g3c_en_sayfalarinda_turkce_kalinti_yok(istemci, katalog, db):
    _kur(db)
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET durum_kodu = 'ikinci_el_test_edildi' WHERE id = ?", (katalog["role"],))
    haric = ["RÖLE MODÜLÜ 24V", "KUKA KRC5 KR 140 R3200-2 PA", "SİGORTA KUTUSU", "QATestUser yurtdisi"]
    _musteri(db, tip=MusteriTipi.YURTDISI, eposta="yurtdisi@ornek.test", ulke="DE", vat_id="DE123456789")
    sayfalar = ["/en/", "/en/urunler", f"/en/kategori/{katalog['elk']}", f"/en/kategori/{katalog['krc4']}",
                f"/en/urun/{katalog['role']}", f"/en/urun/{katalog['robot']}", f"/en/urun/{katalog['stoksuz']}",
                "/en/ara?q=role", "/en/ara?q=yokboyleparca", "/en/sepet", "/en/giris?sonraki=/en/odeme", "/en/kayit",
                "/en/teklif", f"/en/teklif?urun_id={katalog['robot']}", "/en/karsilastir", "/en/bulunamayan"]
    csrf = csrf_al(istemci, "/en/")
    for uid in (katalog["role"], katalog["robot"]):
        istemci.post("/en/karsilastir/ekle", data={"csrf": csrf, "urun_id": uid, "sonraki": "/en/"})
    istemci.post("/en/sepet/ekle", data={"csrf": csrf, "urun_id": katalog["role"], "adet": "1", "sonraki": "/en/"})
    # öz-denetim: tarama TR sayfada Türkçeyi gerçekten yakalar
    tr_metin = _gorunen_metin(istemci.get("/tr/urunler").text, haric)
    assert TURKCE_HARF.search(tr_metin) and TURKCE_SOZCUK.search(tr_metin)
    sorunlar = {}
    for yol in sayfalar:
        yanit = istemci.get(yol)
        assert yanit.status_code == (404 if yol == "/en/bulunamayan" else 200), (yol, yanit.status_code)
        metin = _gorunen_metin(yanit.text, haric)
        bulunan = sorted(set(TURKCE_HARF.findall(metin)) | set(TURKCE_SOZCUK.findall(metin)))
        if bulunan:
            sorunlar[yol] = bulunan
    _giris(istemci, "yurtdisi@ornek.test", dil="en")
    for yol in ("/en/hesabim", "/en/odeme", "/en/sepet"):
        metin = _gorunen_metin(istemci.get(yol).text, haric)
        bulunan = sorted(set(TURKCE_HARF.findall(metin)) | set(TURKCE_SOZCUK.findall(metin)))
        if bulunan:
            sorunlar[yol] = bulunan
    assert not sorunlar, sorunlar


def test_g3c_en_ceviri_dosyasinda_turkce_deger_yok():
    import json
    en = json.loads((KOK / "app" / "web" / "dil" / "en.json").read_text(encoding="utf-8"))
    sorunlu = {k: v for k, v in en.items()
               if TURKCE_HARF.search(v.replace("Türkiye", "").replace("Türkçe", "").replace("Selçuklu", ""))
               and not k.startswith("dil.")}
    assert not sorunlu, sorunlu


# =====================================================================================================
# Madde 24 — karşılaştırma
# =====================================================================================================

def _ekle(istemci, uid, dil="tr", sonraki=None):
    sonraki = sonraki or f"/{dil}/urun/{uid}"
    return _post(istemci, f"/{dil}/karsilastir/ekle", {"urun_id": uid, "sonraki": sonraki}, f"/{dil}/")


def _teknik(istemci, uid, ozellikler):
    import json
    with istemci_db(istemci) as con:
        con.execute("INSERT OR REPLACE INTO urun_teknik (urun_id, veri) VALUES (?, ?)",
                    (uid, json.dumps({"ozellikler": ozellikler, "bolumler": []})))


def test_g3c_karsilastir_dugmesi_detay_liste_ve_kartta(istemci, katalog):
    html = istemci.get(f"/tr/urun/{katalog['role']}").text
    form = re.search(r'<form class="karsilastir-form" method="post" action="/tr/karsilastir/ekle">.*?</form>', html, re.S)
    assert form and f'name="urun_id" value="{katalog["role"]}"' in form.group(0)
    assert 'data-e2e="karsilastir-ekle"' in form.group(0) and 'aria-pressed="false"' in form.group(0)
    liste = istemci.get(f"/tr/kategori/{katalog['elk']}").text
    assert liste.count('action="/tr/karsilastir/ekle"') == 2
    ana = istemci.get("/tr/").text
    kart = ana[ana.index('<article class="kart"'):]
    assert 'action="/tr/karsilastir/ekle"' in kart[:kart.index("</article>")]


def test_g3c_karsilastir_ekle_sayac_ve_bildirim(istemci, katalog):
    yol = f"/tr/kategori/{katalog['elk']}?sira=ad"
    r = _ekle(istemci, katalog["role"], sonraki=yol)
    assert r.status_code == 303 and r.headers["location"] == f"{yol}#urun-{katalog['role']}"   # G3e madde 18
    assert oturum_oku(istemci)["karsilastir"] == [katalog["role"]]
    html = sayfa_denetle(istemci.get(yol))
    sayac = re.search(r'<a class="nav-oge karsilastir-bag" href="/tr/karsilastir" data-e2e="karsilastir-sayac">.*?'
                      r'<span class="sayac"[^>]*>(\d)</span>', html, re.S)
    assert sayac and sayac.group(1) == "1"
    bildirim = _bildirimler(html)
    assert "Karşılaştırmaya eklendi" in bildirim and 'href="/tr/karsilastir"' in bildirim
    # liste satırında artık "çıkar" düğmesi
    assert 'action="/tr/karsilastir/kaldir"' in html and 'aria-pressed="true"' in html
    _ekle(istemci, katalog["role"])                    # aynı ürün tekrar: değişmez
    assert oturum_oku(istemci)["karsilastir"] == [katalog["role"]]


def test_g3c_karsilastir_sayac_bosken_yok(istemci, katalog):
    assert 'data-e2e="karsilastir-sayac"' not in istemci.get("/tr/").text


def test_g3c_karsilastir_en_fazla_uc_en_eski_cikar(istemci, katalog):
    # G3h madde 11: sınır 3 -> 5 (altıncı ürün en eskiyi çıkarır)
    with istemci_db(istemci) as con:
        ekler = [urun_ekle(con, sku=f"EK-{i}", ad=f"EK ÜRÜN {i}", kok="Elektrik ve Elektronik", fiyat="5.00",
                           kategori_id=katalog["kontrol"]) for i in range(3)]
    for uid in (katalog["role"], katalog["robot"], katalog["stoksuz"], ekler[0], ekler[1]):
        _ekle(istemci, uid)
    r = _ekle(istemci, ekler[2])
    assert oturum_oku(istemci)["karsilastir"] == [katalog["robot"], katalog["stoksuz"], *ekler]
    # G3l madde 17: ürün sayfasında karşılaştırma bildirimi yalnız çapada (satın alma kutusu)
    html = istemci.get(r.headers["location"]).text
    bildirim = re.sub(r"<[^>]+>", "", re.search(r'<p class="yerel-bildirim".*?</p>', html, re.S).group(0))
    assert "en fazla 5 ürün" in bildirim and "RÖLE MODÜLÜ 24V" in bildirim


def test_g3c_karsilastir_gecersiz_ve_pasif_urun(istemci, katalog):
    assert _ekle(istemci, 999999).status_code == 404
    assert _ekle(istemci, katalog["pasif"]).status_code == 404
    r = _post(istemci, "/tr/karsilastir/ekle", {"urun_id": "abc", "sonraki": "/tr/"})
    assert r.status_code == 400
    assert istemci.post("/tr/karsilastir/ekle", data={"urun_id": katalog["role"]}).status_code == 403   # csrf


def test_g3c_karsilastir_tablosu(istemci, katalog, db):
    _kur(db)
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET durum_kodu = 'ikinci_el_test_edildi' WHERE id = ?", (katalog["role"],))
    _teknik(istemci, katalog["role"], [["Gerilim", "24 V"], ["Kontak", "2 NO"]])
    _teknik(istemci, katalog["stoksuz"], [["Gerilim", "230 V"], ["Akım", "16 A"]])
    for uid in (katalog["role"], katalog["stoksuz"], katalog["robot"]):
        _ekle(istemci, uid)
    r = istemci.get("/tr/karsilastir")
    html = sayfa_denetle(r)
    assert '<meta name="robots" content="noindex,nofollow">' in html
    assert 'rel="canonical"' not in html and "application/ld+json" not in html
    tablo = re.search(r'<table class="karsilastir-tablo" data-e2e="karsilastir-tablo">.*?</table>', html, re.S).group(0)
    satirlar = {unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip(): m.group(2)
                for m in re.finditer(r'<tr[^>]*>\s*<th scope="row"[^>]*>(.*?)</th>(.*?)</tr>', tablo, re.S)}
    for etiket in ("Parça no", "Marka", "Durum", "Stok", "Teslim", "Fiyat (KDV hariç)", "Fiyat (KDV dahil)",
                   "Gerilim", "Kontak", "Akım"):
        assert etiket in satirlar, (etiket, list(satirlar))
    assert satirlar["Parça no"].count("<td") == 3 and "RL-24" in satirlar["Parça no"]
    assert "KUKA" in satirlar["Marka"]
    assert "24 V" in satirlar["Gerilim"] and "230 V" in satirlar["Gerilim"]
    # G3h madde 10: teknik verisi olmayan robotun sütunu ilk teknik satırda tek birleşik "veri yok" hücresi
    assert 'class="karsilastir-veri-yok"' in satirlar["Gerilim"]
    assert satirlar["Kontak"].count("—") == 1 and satirlar["Akım"].count("—") == 1
    assert "2. el – test edildi" in satirlar["Durum"]
    assert "Fiyat teklifle" in satirlar["Fiyat (KDV hariç)"]
    assert "₺" in satirlar["Fiyat (KDV hariç)"] and "₺" in satirlar["Fiyat (KDV dahil)"]
    eylem = satirlar.get("İşlem", "")
    assert 'action="/tr/sepet/ekle"' in eylem and f'href="/tr/teklif?urun_id={katalog["robot"]}"' in eylem
    assert eylem.count('action="/tr/karsilastir/kaldir"') == 3
    css = SITE_CSS.read_text(encoding="utf-8")
    assert ".karsilastir-sar" in css and "overflow-x: auto" in css.split(".karsilastir-sar", 1)[1][:200]
    assert re.search(r"\.karsilastir-tablo th\[scope=\"row\"\][^{]*\{[^}]*position: sticky", css)


def test_g3c_karsilastir_pasif_urun_listeden_duser(istemci, katalog):
    for uid in (katalog["role"], katalog["stoksuz"]):
        _ekle(istemci, uid)
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET aktif = 0 WHERE id = ?", (katalog["stoksuz"],))
    html = istemci.get("/tr/karsilastir").text
    ana = html.split('<main', 1)[1]          # bildirim alanında eklenme mesajı olabilir
    assert "SİGORTA KUTUSU" not in ana and "RÖLE MODÜLÜ 24V" in ana
    assert oturum_oku(istemci)["karsilastir"] == [katalog["role"]]
    sayac = re.search(r'data-e2e="karsilastir-sayac">.*?<span class="sayac"[^>]*>(\d)</span>', html, re.S)
    assert sayac.group(1) == "1"


def test_g3c_karsilastir_kaldir_ve_temizle(istemci, katalog):
    for uid in (katalog["role"], katalog["stoksuz"]):
        _ekle(istemci, uid)
    r = _post(istemci, "/tr/karsilastir/kaldir", {"urun_id": katalog["role"], "sonraki": "/tr/karsilastir"})
    assert r.status_code == 303 and r.headers["location"] == f"/tr/karsilastir#urun-{katalog['role']}"
    assert oturum_oku(istemci)["karsilastir"] == [katalog["stoksuz"]]
    r = _post(istemci, "/tr/karsilastir/temizle", {"sonraki": "/tr/karsilastir"})
    assert r.status_code == 303 and oturum_oku(istemci).get("karsilastir", []) == []
    html = sayfa_denetle(istemci.get("/tr/karsilastir"))
    assert "Karşılaştırma listeniz boş" in html and 'href="/tr/urunler"' in html


def test_g3c_karsilastir_csv(istemci, katalog, db):
    _kur(db)
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET ad = '=HYPERLINK(1)' WHERE id = ?", (katalog["stoksuz"],))
    for uid in (katalog["role"], katalog["stoksuz"]):
        _ekle(istemci, uid)
    r = istemci.get("/tr/karsilastir.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers.get("X-Robots-Tag") == "noindex, nofollow"
    satirlar = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
    # G3m madde 14: düz tablo — ürün başına satır; "ad" sütununda formül önekli metin korunur
    baslik = satirlar[0]
    adlar = [s[baslik.index("ad")] for s in satirlar[1:]]
    assert adlar == ["RÖLE MODÜLÜ 24V", "'=HYPERLINK(1)"], adlar
    # G3k madde 9: CSV'de fiyatlar sayısal ayrı sütunlarda (metin fiyat sütunu yok)
    assert "parca_no" in baslik and "fiyat_kdv_haric_try" in baslik and "Fiyat (KDV hariç)" not in baslik
    html = istemci.get("/tr/karsilastir").text
    assert 'href="/tr/karsilastir.csv"' in html


def test_g3c_karsilastir_en(istemci, katalog):
    _ekle(istemci, katalog["role"], dil="en")
    html = sayfa_denetle(istemci.get("/en/karsilastir"))
    assert "<h1>Compare products</h1>" in html and "Part no." in html


def test_g3c_karsilastir_robots_txt_ve_islemsel(istemci):
    from app.web.seo import ROBOTS_YASAK, islemsel_mi
    assert islemsel_mi("/tr/karsilastir") and islemsel_mi("/en/karsilastir.csv")
    assert "/*/karsilastir" in ROBOTS_YASAK


# =====================================================================================================
# Düzeltme turu 1 (g3c-review M-1 … M-4)
# =====================================================================================================

_OZNITELIK = re.compile(r"<[a-z]+[^>]*>", re.I)


def _yinelenen_oznitelik(html):
    sorunlu = []
    for etiket in _OZNITELIK.findall(html):
        adlar = re.findall(r'\s([a-z-]+)=', etiket)
        if len(adlar) != len(set(adlar)):
            sorunlu.append(etiket)
    return sorunlu


def test_g3c_m1_eposta_hatasi_aria_describedby_tek_oznitelik(istemci):
    r = _teklif(istemci, eposta="", telefon="")
    assert r.status_code == 400
    html = sayfa_denetle(r)
    assert not _yinelenen_oznitelik(html), _yinelenen_oznitelik(html)
    girdi = re.search(r'<input id="eposta"[^>]*>', html).group(0)
    assert re.search(r'aria-describedby="ipucu-iletisim hata-eposta"', girdi), girdi
    r = _teklif(istemci, eposta="a@b")
    girdi = re.search(r'<input id="eposta"[^>]*>', r.text).group(0)
    assert 'aria-describedby="ipucu-iletisim hata-eposta"' in girdi
    girdi = re.search(r'<input id="eposta"[^>]*>', istemci.get("/tr/teklif").text).group(0)
    assert 'aria-describedby="ipucu-iletisim"' in girdi


def test_g3c_m2_bildirim_listesi_sinirli_cerez_4kb_alti(istemci, katalog):
    csrf = csrf_al(istemci, "/tr/")
    for _ in range(60):
        r = istemci.post("/tr/karsilastir/ekle", data={"csrf": csrf, "urun_id": katalog["robot"], "sonraki": "/tr/"},
                         follow_redirects=False)
        assert r.status_code == 303
    assert len(oturum_oku(istemci)["bildirimler"]) <= 3
    cerez = next(c.value for c in istemci.cookies.jar if c.name == "cr_oturum")
    assert len(cerez) < 4096, len(cerez)


def test_g3c_m3_en_kategori_girisinde_cevrilmemis_ad_yok(istemci, katalog):
    with istemci_db(istemci) as con:
        ozel = kategori_ekle(con, kaynak_id="k1019", ad="ZZZ ÖZEL KATEGORİ", yol="10.19", seviye=1, ust_kaynak_id="k10")
    html = istemci.get(f"/en/kategori/{ozel}").text
    giris = re.search(r'<p class="kategori-giris">(.*?)</p>', html, re.S)
    assert giris is None or "ÖZEL" not in re.sub(r'<span lang="tr">.*?</span>', "", giris.group(1))
    html = istemci.get(f"/en/kategori/{katalog['elk']}").text      # çevrilmiş adda giriş kalır
    assert re.search(r'<p class="kategori-giris">[^<]*Electrical and Electronics', html)


@pytest.mark.parametrize("uc", ["kaldir", "temizle"])
def test_g3c_m4a_karsilastir_csrfsiz_403(istemci, katalog, uc):
    istemci.get("/tr/")
    assert istemci.post(f"/tr/karsilastir/{uc}", data={"urun_id": katalog["role"]}).status_code == 403


@pytest.mark.parametrize("uc", ["ekle", "kaldir", "temizle"])
@pytest.mark.parametrize("sonraki", ["//evil.example", "https://evil.example/x", "/\\evil", "\\\\evil"])
def test_g3c_m4b_karsilastir_acik_yonlendirme_yok(istemci, katalog, uc, sonraki):
    r = _post(istemci, f"/tr/karsilastir/{uc}", {"urun_id": katalog["role"], "sonraki": sonraki})
    capa = "" if uc == "temizle" else f"#urun-{katalog['role']}"     # G3e madde 18
    assert r.status_code == 303 and r.headers["location"] == "/tr/karsilastir" + capa


def test_g3c_m4c_teknik_html_kacislanir(istemci, katalog):
    _teknik(istemci, katalog["role"], [["<img src=x onerror=alert(1)>", "<script>alert(2)</script>"]])
    _ekle(istemci, katalog["role"])
    html = sayfa_denetle(istemci.get("/tr/karsilastir"))
    assert "<img src=x" not in html and "<script>alert" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html and "&lt;script&gt;alert(2)&lt;/script&gt;" in html
    satirlar = list(csv.reader(io.StringIO(istemci.get("/tr/karsilastir.csv").content.decode("utf-8-sig")),
                               delimiter=";"))
    # G3m madde 14: teknik özellik ayrı sütun (ASCII başlık), değer düz metin
    assert satirlar[0][-1] == "teknik_img_src_x_onerror_alert_1" and satirlar[1][-1] == "<script>alert(2)</script>"


def test_g3c_m4d_hizli_teklif_ulke_oturum_ulkesi(istemci, db):
    _musteri(db, eposta="bireysel@ornek.test")
    _giris(istemci, "bireysel@ornek.test")
    csrf = csrf_al(istemci, "/tr/")
    istemci.post("/tercih", data={"ulke": "DE", "sonraki": "/tr/", "csrf": csrf}, follow_redirects=False)
    assert _hizli(istemci).status_code == 303
    with istemci_db(istemci) as con:
        assert con.execute("SELECT ulke FROM teklif").fetchone()[0] == "DE"


def test_g3c_m4e_uzun_sonraki_kirpilir(istemci, katalog):
    uzun = "/tr/urunler?q=" + "a" * 600
    capa = f"#urun-{katalog['role']}"                                 # G3e madde 18
    r = _post(istemci, "/tr/sepet/ekle", {"urun_id": katalog["role"], "adet": "1", "sonraki": uzun})
    assert r.status_code == 303 and r.headers["location"] == uzun[:500] + capa
    r = _post(istemci, "/tr/karsilastir/ekle", {"urun_id": katalog["role"], "sonraki": uzun})
    assert r.status_code == 303 and r.headers["location"] == uzun[:500] + capa


def test_g3c_i1_mobil_kopyala_satiri_buyutmez():
    """I-1: ≤767 px'te Kopyala görünürde 28 px, dokunma alanı ::after ile 44 px (ölçüm: g3c-report düzeltme turu 1)."""
    css = SITE_CSS.read_text(encoding="utf-8")
    blok = css[css.index("/* g3c I-1"):]
    assert ".urun-kodlar .kopyala { min-height: 28px;" in blok and "inset: -8px" in blok
    assert ".urun-bilgi h1 { line-height: 1.25; }" in blok


# =====================================================================================================
# Düzeltme turu 2: çerez bandı JS'siz kapanır, mobilde akışta (eylemleri örtmez)
# =====================================================================================================

def test_g3c_cerez_bandi_jssiz_form(istemci, katalog):
    yol = f"/tr/urun/{katalog['role']}"
    html = sayfa_denetle(istemci.get(yol))
    bant = re.search(r'<div id="cerez-bandi".*?</div>', html, re.S).group(0)
    assert re.search(r'<form method="post" action="/cerez-onay"', bant)
    assert 'name="csrf"' in bant and f'<input type="hidden" name="sonraki" value="{yol}">' in bant
    assert re.search(r'<button type="submit" class="dugme" id="cerez-kabul"', bant)
    ana = html.split('<main id="icerik"', 1)[1].split("</main>", 1)[0]
    assert 'id="cerez-bandi"' in ana                       # akışta <main> sonunda (mobilde örtmez)


def test_g3c_cerez_onay_post_cerez_yazar_bant_kalkar(istemci, katalog):
    yol = f"/tr/urun/{katalog['role']}?x=1"
    r = _post(istemci, "/cerez-onay", {"sonraki": yol}, yol)
    assert r.status_code == 303 and r.headers["location"] == yol
    assert r.cookies.get("cerez_onay") == "1"
    assert "max-age=31536000" in r.headers["set-cookie"].lower() and "samesite=lax" in r.headers["set-cookie"].lower()
    assert 'id="cerez-bandi"' not in istemci.get(yol).text


@pytest.mark.parametrize("sonraki", ["https://evil.example/", "//evil.example", "/\\evil", ""])
def test_g3c_cerez_onay_dis_sonraki_reddedilir(istemci, sonraki):
    r = _post(istemci, "/cerez-onay", {"sonraki": sonraki})
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_g3c_cerez_onay_dis_referer_reddedilir(istemci):
    csrf = csrf_al(istemci, "/tr/")
    r = istemci.post("/cerez-onay", data={"csrf": csrf}, headers={"Referer": "https://evil.example/x"},
                     follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    r = istemci.post("/cerez-onay", data={"csrf": csrf}, headers={"Referer": "http://testserver/tr/urunler?a=1"},
                     follow_redirects=False)
    assert r.headers["location"] == "/tr/urunler?a=1"


def test_g3c_cerez_onay_csrf_zorunlu(istemci):
    istemci.get("/tr/")
    r = istemci.post("/cerez-onay", data={"sonraki": "/tr/"}, follow_redirects=False)
    assert r.status_code == 403 and "cerez_onay" not in r.headers.get("set-cookie", "")


def test_g3c_cerez_bandi_mobilde_akista():
    css = SITE_CSS.read_text(encoding="utf-8")
    blok = css[css.index("/* g3c düzeltme 2"):]
    assert re.search(r"@media \(max-width: 767px\) \{[^}]*\.cerez-bandi \{[^}]*position: static", blok)
