import re

import pytest

from app.sepet.servis import adet_toplam, ekle, sepet_bul
from app.teklif.servis import TeklifGirdisi, teklif_olustur
from tests.conftest import csrf_al, istemci_db, oturum_oku, sayfa_denetle, urun_ekle

PAROLA = "demo-parola-123"
EPOSTA = "qatestuser+bireysel@example.com"


def _kayit(istemci, dil="tr", **ek):
    csrf = csrf_al(istemci, f"/{dil}/kayit")
    veri = {"csrf": csrf, "tip": "bireysel", "ad": "QA Test Kullanıcı", "eposta": EPOSTA,
            "parola": PAROLA, "kvkk_onay": "1", "ulke": "DE"}
    veri.update(ek)
    return istemci.post(f"/{dil}/kayit", data=veri, follow_redirects=False)


def _cikis(istemci):
    csrf = csrf_al(istemci, "/tr/giris")
    return istemci.post("/tr/cikis", data={"csrf": csrf}, follow_redirects=False)


def _giris(istemci, eposta=EPOSTA, parola=PAROLA, sonraki=None):
    csrf = csrf_al(istemci, "/tr/giris")
    veri = {"csrf": csrf, "eposta": eposta, "parola": parola}
    if sonraki is not None:
        veri["sonraki"] = sonraki
    return istemci.post("/tr/giris", data=veri, follow_redirects=False)


def _musteri(istemci, eposta):
    with istemci_db(istemci) as con:
        return con.execute("SELECT * FROM musteri WHERE eposta = ?", (eposta,)).fetchone()


def test_kayit_sayfasi(istemci):
    html = sayfa_denetle(istemci.get("/tr/kayit"))
    assert 'data-e2e="kayit-gonder"' in html
    for tip in ("bireysel", "kurumsal", "yurtdisi"):
        assert f'name="tip" value="{tip}"' in html
    assert 'href="/tr/yasal/kvkk"' in html
    assert "gerçek parolanızı" in html
    assert 'data-tipler="kurumsal"' in html and "yalnız kurumsal" in html
    iys = re.search(r'<input[^>]*name="iys_onay"[^>]*>', html).group(0)
    assert "checked" not in iys
    assert 'name="vergi_kimlik_no"' in html and 'name="vat_id"' in html  # JS olmadan da tüm alanlar var


def test_kayit_tip_ve_sonraki_parametresi(istemci):
    html = istemci.get("/tr/kayit", params={"tip": "kurumsal", "sonraki": "/tr/sepet"}).text
    assert re.search(r'name="tip" value="kurumsal"[^>]*checked', html)
    assert '<input type="hidden" name="sonraki" value="/tr/sepet">' in html
    html = istemci.get("/tr/kayit", params={"sonraki": "https://evil.com"}).text
    assert '<input type="hidden" name="sonraki" value="">' in html


def test_kayit_sonrasi_sonraki_adrese_gider(istemci):
    yanit = _kayit(istemci, sonraki="/tr/sepet")
    assert yanit.status_code == 303 and yanit.headers["location"] == "/tr/sepet"
    assert "mid" in oturum_oku(istemci)  # otomatik giriş
    _cikis(istemci)
    yanit = _kayit(istemci, eposta="qatestuser+evil@example.com", sonraki="https://evil.com")
    assert yanit.headers["location"] == "/"


def test_misafir_sepeti_kayitta_birlesir(istemci, simdi):
    csrf_al(istemci, "/tr/kayit")
    oid = oturum_oku(istemci)["oid"]
    with istemci_db(istemci) as con:
        uid = urun_ekle(con, sku="KB-1", ad="KAYIT ÜRÜNÜ", stok=10)
        ekle(con, sepet_bul(con, oid, None, simdi), uid, 2)
    assert _kayit(istemci).status_code == 303
    html = istemci.get("/tr/hesabim").text
    assert "Misafir sepetinizdeki 1 kalem hesabınızın sepetiyle birleştirildi." in html
    with istemci_db(istemci) as con:
        mid = con.execute("SELECT id FROM musteri WHERE eposta = ?", (EPOSTA,)).fetchone()[0]
        uye = con.execute("SELECT id FROM sepet WHERE musteri_id = ?", (mid,)).fetchone()[0]
        assert adet_toplam(con, uye) == 2


def test_kayit_sayfasi_en(istemci):
    html = istemci.get("/en/kayit").text
    assert "Create account" in html and 'href="/en/yasal/kvkk"' in html


def test_kayit_bireysel(istemci):
    yanit = _kayit(istemci)
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/tr/hesabim"
    m = _musteri(istemci, EPOSTA)
    assert m["tip"] == "bireysel" and m["ulke"] == "TR" and m["iys_onay"] == 0
    html = sayfa_denetle(istemci.get("/tr/hesabim"))
    assert "QA Test Kullanıcı" in html and "Hesabınız oluşturuldu." in html


def test_kayit_kurumsal_gecerli_vkn(istemci):
    eposta = "qatestuser+kurumsal@example.com"
    yanit = _kayit(istemci, tip="kurumsal", ad="QA Test Makina AS", eposta=eposta,
                   vergi_kimlik_no="1234567890", vergi_dairesi="Kadıköy", iys_onay="1")
    assert yanit.status_code == 303
    m = _musteri(istemci, eposta)
    assert m["tip"] == "kurumsal" and m["vergi_kimlik_no"] == "1234567890"
    assert m["vergi_dairesi"] == "Kadıköy" and m["ulke"] == "TR" and m["iys_onay"] == 0


def test_kayit_yurtdisi(istemci):
    eposta = "qatestuser+yurtdisi@example.com"
    yanit = _kayit(istemci, tip="yurtdisi", ad="QA Test GmbH", eposta=eposta, ulke="DE",
                   vat_id="DE123456789", iys_onay="1", vergi_kimlik_no="1234567890")
    assert yanit.status_code == 303
    m = _musteri(istemci, eposta)
    assert m["tip"] == "yurtdisi" and m["ulke"] == "DE" and m["vat_id"] == "DE123456789"
    assert m["iys_onay"] == 0 and m["vergi_kimlik_no"] is None


def test_kayit_yurtdisi_turkiye_secilemez(istemci):
    yanit = _kayit(istemci, tip="yurtdisi", eposta="qatestuser+yd2@example.com", ulke="TR")
    assert yanit.status_code == 400
    assert 'id="h-ulke"' in yanit.text


def test_hatali_vkn_alaninda_gosterilir_veri_korunur(istemci):
    yanit = _kayit(istemci, tip="kurumsal", ad="QA Test Makina AS", eposta="qatestuser+vkn@example.com",
                   parola="gizli-parola-123", vergi_kimlik_no="4728136593", vergi_dairesi="Kadıköy")
    assert yanit.status_code == 400
    html = sayfa_denetle(yanit)
    assert '<p class="alan-hata" id="h-vergi_kimlik_no">Vergi kimlik numarası geçersiz' in html
    assert 'aria-invalid="true"' in html
    assert 'value="QA Test Makina AS"' in html
    assert 'value="qatestuser+vkn@example.com"' in html
    assert 'value="4728136593"' in html
    assert 'value="Kadıköy"' in html
    assert "gizli-parola-123" not in html
    assert re.search(r'name="tip" value="kurumsal"[^>]*checked', html)
    assert _musteri(istemci, "qatestuser+vkn@example.com") is None


def test_tip_secilmeden_kayit(istemci):
    yanit = _kayit(istemci, tip="")
    assert yanit.status_code == 400
    assert "Müşteri tipini seçin." in yanit.text


def test_eposta_tekrar(istemci):
    assert _kayit(istemci).status_code == 303
    _cikis(istemci)
    yanit = _kayit(istemci, ad="Başka Kişi")
    assert yanit.status_code == 400
    assert "Bu e-posta adresiyle zaten bir hesap var." in yanit.text
    assert 'value="Başka Kişi"' in yanit.text


def test_giris_cikis(istemci):
    _kayit(istemci)
    yanit = _cikis(istemci)
    assert yanit.status_code == 303 and yanit.headers["location"] == "/tr/"
    assert "mid" not in oturum_oku(istemci)
    assert istemci.get("/tr/hesabim", follow_redirects=False).status_code == 303
    yanit = _giris(istemci)
    assert yanit.status_code == 303 and yanit.headers["location"] == "/tr/hesabim"
    assert "QA Test Kullanıcı" in istemci.get("/tr/hesabim").text


def test_yanlis_parola(istemci):
    _kayit(istemci)
    _cikis(istemci)
    yanit = _giris(istemci, parola="yanlis-parola-99")
    assert yanit.status_code == 400
    html = sayfa_denetle(yanit)
    assert "E-posta veya parola hatalı." in html
    assert f'value="{EPOSTA}"' in html
    assert "yanlis-parola-99" not in html


def test_onbirinci_denemede_429(istemci):
    _kayit(istemci)
    _cikis(istemci)
    for _ in range(10):
        assert _giris(istemci, parola="yanlis-parola-99").status_code == 400
    yanit = _giris(istemci)  # doğru parola bile olsa sınır aşıldı
    assert yanit.status_code == 429
    assert "Çok fazla deneme" in yanit.text


def test_sonraki_acik_yonlendirme_engeli(istemci):
    _kayit(istemci)
    _cikis(istemci)
    yanit = _giris(istemci, sonraki="https://evil.com")
    assert yanit.status_code == 303 and yanit.headers["location"] == "/"
    _cikis(istemci)
    yanit = _giris(istemci, sonraki="/tr/sepet")
    assert yanit.headers["location"] == "/tr/sepet"


def test_giris_formu_sonraki_tasir(istemci):
    html = istemci.get("/tr/giris", params={"sonraki": "/tr/odeme"}).text
    assert 'name="sonraki" value="/tr/odeme"' in html
    html = istemci.get("/tr/giris", params={"sonraki": "//evil.com"}).text
    assert '<input type="hidden" name="sonraki" value="">' in html
    assert 'value="//evil.com"' not in html


def test_misafir_sepeti_giriste_birlesir(istemci, simdi):
    assert _kayit(istemci).status_code == 303  # kayıt aynı zamanda giriş yapar
    _cikis(istemci)
    csrf_al(istemci, "/tr/giris")  # yeni misafir oturumu (oid) oluşur
    oid = oturum_oku(istemci)["oid"]
    with istemci_db(istemci) as con:
        uid = urun_ekle(con, sku="BR-1", ad="BİRLEŞME ÜRÜNÜ", stok=10)
        mid = con.execute("SELECT id FROM musteri WHERE eposta = ?", (EPOSTA,)).fetchone()[0]
        uye = sepet_bul(con, None, mid, simdi)
        ekle(con, uye, uid, 1)
        misafir = sepet_bul(con, oid, None, simdi)
        ekle(con, misafir, uid, 2)
    assert _giris(istemci).status_code == 303
    html = istemci.get("/tr/hesabim").text
    assert "Misafir sepetinizdeki 1 kalem hesabınızın sepetiyle birleştirildi." in html
    assert '<span class="sayac"' in html and ">3</span>" in html
    with istemci_db(istemci) as con:
        assert adet_toplam(con, uye) == 3
        assert con.execute("SELECT COUNT(*) FROM sepet WHERE oturum_id = ?", (oid,)).fetchone()[0] == 0


def test_hesabim_girissiz_yonlendirir(istemci):
    yanit = istemci.get("/tr/hesabim", follow_redirects=False)
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/tr/giris?sonraki=%2Ftr%2Fhesabim"


def test_hesabim_teklifleri_ve_bos_siparisleri_listeler(istemci, simdi):
    _kayit(istemci)
    with istemci_db(istemci) as con:
        mid = con.execute("SELECT id FROM musteri WHERE eposta = ?", (EPOSTA,)).fetchone()[0]
        tk = teklif_olustur(con, TeklifGirdisi(ad="QA Test", eposta=EPOSTA, ulke="TR",
                                               mesaj="Robot için fiyat rica ederim", musteri_id=mid), simdi)
    html = sayfa_denetle(istemci.get("/tr/hesabim"))
    assert tk.no in html and "Yeni" in html
    assert "Henüz siparişiniz yok." in html


def test_cikis_csrfsiz_403(istemci):
    _kayit(istemci)
    assert istemci.post("/tr/cikis", data={}, follow_redirects=False).status_code == 403


def test_giris_oturum_sabitlemeyi_kapatir(istemci):
    _kayit(istemci)
    _cikis(istemci)
    eski = csrf_al(istemci, "/tr/giris")
    eski_oid = oturum_oku(istemci)["oid"]
    veri = {"csrf": eski, "eposta": EPOSTA, "parola": PAROLA}
    assert istemci.post("/tr/giris", data=veri, follow_redirects=False).status_code == 303
    assert oturum_oku(istemci)["oid"] != eski_oid
    assert istemci.post("/tr/cikis", data={"csrf": eski}, follow_redirects=False).status_code == 403
    assert csrf_al(istemci, "/tr/hesabim") != eski


def test_kayit_csrf_ve_oid_yenilenir(istemci):
    eski = csrf_al(istemci, "/tr/kayit")
    eski_oid = oturum_oku(istemci)["oid"]
    veri = {"csrf": eski, "tip": "bireysel", "ad": "QA", "eposta": EPOSTA, "parola": PAROLA, "kvkk_onay": "1"}
    assert istemci.post("/tr/kayit", data=veri, follow_redirects=False).status_code == 303
    assert oturum_oku(istemci)["oid"] != eski_oid
    assert istemci.post("/tr/cikis", data={"csrf": eski}, follow_redirects=False).status_code == 403


def test_cikis_sonrasi_eski_csrf_403(istemci):
    _kayit(istemci)
    eski = csrf_al(istemci, "/tr/hesabim")
    assert istemci.post("/tr/cikis", data={"csrf": eski}, follow_redirects=False).status_code == 303
    assert istemci.post("/tr/cikis", data={"csrf": eski}, follow_redirects=False).status_code == 403


def test_oturum_aciksa_kayit_post_hesap_acmaz(istemci):
    _kayit(istemci)
    yanit = _kayit(istemci, eposta="qatestuser+ikinci@example.com")
    assert yanit.status_code == 303 and yanit.headers["location"] == "/tr/hesabim"
    assert _musteri(istemci, "qatestuser+ikinci@example.com") is None
