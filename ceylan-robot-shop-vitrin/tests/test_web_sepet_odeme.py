"""Görev 14 — sepet, ödeme, kart, 3D ve sipariş sayfası (TestClient ile)."""
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.db import baglan, gecisleri_uygula
from app.fiyat.kur import Kur, kur_kaydet
from app.fiyat.kurallar import MusteriTipi
from app.hesap.servis import KayitGirdisi, kayit_ol
from app.para import d
from tests.conftest import csrf_al, urun_ekle

PAROLA = "demo-parola-123"
GECERLI_VKN = "1234567890"   # K16


# ---------- yardımcılar ----------

@pytest.fixture
def db(istemci):
    """Uygulamanın kullandığı veritabanına ayrı bir bağlantı (test verisi kurmak ve sonucu okumak için)."""
    con = baglan(istemci.app.state.ayarlar.db_yolu)
    gecisleri_uygula(con)
    yield con
    con.close()


def _kur(db, tarih=date(2026, 10, 12), satis="35.0000"):
    with db:
        kur_kaydet(db, Kur(tarih=tarih, eur_alis=d(satis) - d("0.1000"), eur_satis=d(satis)), datetime.now(UTC))


def _urun(db, **ek):
    with db:
        return urun_ekle(db, **ek)


def _musteri(db, tip=MusteriTipi.BIREYSEL, eposta="bireysel@ornek.test", ulke="TR", **ek):
    with db:
        return kayit_ol(db, KayitGirdisi(tip=tip, ad=f"QATestUser {tip.value}", eposta=eposta, parola=PAROLA,
                                         ulke=ulke, kvkk_onay=True, **ek), datetime.now(UTC))


def _giris(istemci, eposta, dil="tr"):
    csrf = csrf_al(istemci, f"/{dil}/giris")
    r = istemci.post(f"/{dil}/giris", data={"eposta": eposta, "parola": PAROLA, "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 303, r.text


def _sepete_ekle(istemci, urun_id, dil="tr", adet="1"):
    csrf = csrf_al(istemci, f"/{dil}/sepet")
    return istemci.post(f"/{dil}/sepet/ekle", data={"urun_id": str(urun_id), "adet": adet, "csrf": csrf},
                        follow_redirects=False)


def _gizli(html, ad):
    m = re.search(rf'name="{ad}" value="([^"]*)"', html)
    assert m, f"gizli alan yok: {ad}"
    return m.group(1)


def _adres_formu(ulke="TR", teslim="kargo", **ek):
    form = {
        "teslimat_ad_soyad": "QATestUser Alıcı", "teslimat_satir1": "Test Mah. Deneme Sk. No: 1",
        "teslimat_satir2": "", "teslimat_sehir": "Konya" if ulke == "TR" else "Berlin",
        "teslimat_posta_kodu": "42250", "teslimat_ulke": ulke, "teslimat_telefon": "",
        "fatura_ayni": "1", "teslim": teslim,
        "on_bilgi_onay": "1", "mesafeli_onay": "1", "kosullar_onay": "1", "islem": "odeme",
    }
    form.update(ek)
    return form


def _odeme_gonder(istemci, dil="tr", sayfa_html=None, **form_ek):
    if sayfa_html is None:
        sayfa = istemci.get(f"/{dil}/odeme")
        assert sayfa.status_code == 200, sayfa.text
        sayfa_html = sayfa.text
    form = _adres_formu(**form_ek)
    for ad in ("csrf", "gosterilen_toplam", "gosterilen_kur"):
        form[ad] = _gizli(sayfa_html, ad)
    return istemci.post(f"/{dil}/odeme", data=form, follow_redirects=False)


def _siparis_no(konum):
    m = re.search(r"/odeme/(CR-DEMO-\d{8}-\d{4})/kart$", konum)
    assert m, konum
    return m.group(1)


def _kart_ode(istemci, no, kart, dil="tr"):
    sayfa = istemci.get(f"/{dil}/odeme/{no}/kart")
    assert sayfa.status_code == 200, sayfa.text
    form = {"csrf": _gizli(sayfa.text, "csrf"), "islem_anahtari": _gizli(sayfa.text, "islem_anahtari"),
            "kart_no": kart}
    return istemci.post(f"/{dil}/odeme/{no}/kart", data=form, follow_redirects=False), form


def _sms(istemci, no, konum, kod="000000", dil="tr"):
    anahtar = parse_qs(urlparse(konum).query)["a"][0]
    sayfa = istemci.get(konum)
    assert sayfa.status_code == 200, sayfa.text
    return istemci.post(f"/{dil}/odeme/{no}/3d",
                        data={"csrf": _gizli(sayfa.text, "csrf"), "a": anahtar, "sms_kodu": kod},
                        follow_redirects=False), sayfa


def _say(db, sql, *p):
    return db.execute(sql, p).fetchone()[0]


def _db_dokumu(db):
    parcalar = []
    for (tablo,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        for satir in db.execute(f'SELECT * FROM "{tablo}"').fetchall():
            parcalar.append("|".join(str(x) for x in satir))
    return "\n".join(parcalar)


def _siparis_hazirla(istemci, db, eposta="bireysel@ornek.test"):
    """Giriş yapmış bireysel müşteri + 100 € ürün + kur 35 -> odeme_bekliyor sipariş no'su."""
    _kur(db)
    uid = _urun(db, sku="S-HAZIR", ad="Hazır Ürün", fiyat="100.00")
    _musteri(db, eposta=eposta)
    _giris(istemci, eposta)
    assert _sepete_ekle(istemci, uid).status_code == 303
    r = _odeme_gonder(istemci)
    assert r.status_code == 303, r.text
    return _siparis_no(r.headers["location"])


# ---------- §11 senaryo 1: bireysel TR ----------

def test_senaryo1_bireysel_tr_siparis(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-ROLE", ad="Test Röle", fiyat="100.00")

    # misafir sepete ekler; fiyat TRY ve KDV dahil (100 € × 35 = 3.500 ₺ + %20 KDV = 4.200 ₺)
    assert _sepete_ekle(istemci, uid).status_code == 303
    sepet = istemci.get("/tr/sepet")
    assert sepet.status_code == 200
    assert "Test Röle" in sepet.text
    assert "4.200,00 ₺" in sepet.text
    assert "KDV dahil" in sepet.text
    assert 'data-e2e="sepet-kalemi"' in sepet.text and 'data-e2e="odemeye-gec"' in sepet.text

    # G3g madde 1: misafir giriş sayfasına atılmaz; ödeme formunun üstünde "Hesabınız" (hesap siparişle açılır)
    r = istemci.get("/tr/odeme", follow_redirects=False)
    assert r.status_code == 200 and 'data-e2e="odeme-hesap"' in r.text

    # kayıtlı müşteri girer, misafir sepeti üye sepetine geçer
    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    odeme = istemci.get("/tr/odeme")
    assert odeme.status_code == 200
    assert "Test Röle" in odeme.text
    # 3.500 + 700 KDV + 525 kargo + 105 kargo KDV = 4.830 ₺
    assert "4.830,00 ₺" in odeme.text
    assert "/tr/yasal/on-bilgilendirme" in odeme.text
    assert "/tr/yasal/mesafeli-satis" in odeme.text
    assert 'name="on_bilgi_onay"' in odeme.text and 'name="mesafeli_onay"' in odeme.text
    assert 'data-e2e="odeme-gonder"' in odeme.text and 'data-e2e="satir-kdv"' in odeme.text
    assert re.search(r'<input[^>]*name="fatura_ayni"[^>]*checked', odeme.text)

    r = _odeme_gonder(istemci, sayfa_html=odeme.text)
    assert r.status_code == 303, r.text
    no = _siparis_no(r.headers["location"])

    r, _ = _kart_ode(istemci, no, "4111 1111 1111 1111")
    assert r.status_code == 303
    assert r.headers["location"].startswith(f"/tr/odeme/{no}/3d?a=")

    r, uc_d = _sms(istemci, no, r.headers["location"])
    assert 'data-e2e="sms-gonder"' in uc_d.text
    assert r.status_code == 303
    assert r.headers["location"] == f"/tr/siparis/{no}"

    onay = istemci.get(f"/tr/siparis/{no}")
    assert onay.status_code == 200
    assert re.search(r'data-e2e="siparis-durum"[^>]*data-durum="odendi"', onay.text)
    assert "4.830,00 ₺" in onay.text
    assert "**** 1111" in onay.text
    assert 'data-e2e="odeme-hata"' not in onay.text

    satir = db.execute("SELECT * FROM siparis WHERE no = ?", (no,)).fetchone()
    assert satir["durum"] == "odendi"
    assert satir["para_birimi"] == "TRY"
    assert Decimal(satir["toplam"]) == Decimal("4830.00")
    assert Decimal(satir["kdv"]) == Decimal("805.00")
    assert satir["kart_son4"] == "1111"
    assert satir["ihracat_istisnasi"] == 0

    assert no in istemci.get("/tr/hesabim").text
    assert "Sepetiniz boş" in istemci.get("/tr/sepet").text


def test_bireysel_sozlesme_onayi_zorunlu(istemci, db):
    _kur(db)
    uid = _urun(db, fiyat="100.00")
    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    _sepete_ekle(istemci, uid)
    r = _odeme_gonder(istemci, mesafeli_onay="")
    assert r.status_code == 400
    assert 'id="hata-mesafeli_onay"' in r.text
    assert _say(db, "SELECT COUNT(*) FROM siparis") == 0


# ---------- §11 senaryo 2: kurumsal TR ----------

def test_senaryo2_kurumsal_ret_sonra_basarili(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-KONT", ad="Test Kontaktör", fiyat="100.00")
    m = _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="kurumsal@ornek.test",
                 vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    _giris(istemci, "kurumsal@ornek.test")
    assert _sepete_ekle(istemci, uid).status_code == 303

    sepet = istemci.get("/tr/sepet")
    assert "100,00 €" in sepet.text          # EUR, KDV hariç birim fiyat
    assert "3.500,00 ₺" in sepet.text        # TRY karşılığı (net)
    assert "KDV hariç" in sepet.text

    odeme = istemci.get("/tr/odeme")
    assert 'name="kosullar_onay"' in odeme.text
    assert 'name="mesafeli_onay"' not in odeme.text
    r = _odeme_gonder(istemci, sayfa_html=odeme.text, on_bilgi_onay="", mesafeli_onay="")
    assert r.status_code == 303, r.text
    no = _siparis_no(r.headers["location"])

    # ret kartı: banka reddi -> sipariş sayfası, odeme-hata[data-kod=ret] + tekrar dene bağlantısı
    r, _ = _kart_ode(istemci, no, "4000000000000002")
    assert r.status_code == 303
    r, _ = _sms(istemci, no, r.headers["location"])
    assert r.status_code == 303
    assert r.headers["location"] == f"/tr/siparis/{no}?hata=ret"
    hata = istemci.get(r.headers["location"])
    assert re.search(r'data-e2e="odeme-hata"[^>]*data-kod="ret"', hata.text)
    assert "reddedildi" in hata.text
    assert f'href="/tr/odeme/{no}/kart"' in hata.text
    assert db.execute("SELECT durum FROM siparis WHERE no = ?", (no,)).fetchone()[0] == "odeme_bekliyor"

    # aynı siparişle başarılı kart
    r, _ = _kart_ode(istemci, no, "4111111111111111")
    r, _ = _sms(istemci, no, r.headers["location"])
    assert r.headers["location"] == f"/tr/siparis/{no}"

    satir = db.execute("SELECT * FROM siparis WHERE no = ?", (no,)).fetchone()
    assert satir["durum"] == "odendi"
    assert satir["musteri_id"] == m.id
    assert satir["para_birimi"] == "TRY"
    assert Decimal(satir["toplam"]) == Decimal("4830.00")
    assert _say(db, "SELECT COUNT(*) FROM siparis") == 1
    assert _say(db, "SELECT COUNT(*) FROM odeme_denemesi WHERE siparis_id = ?", satir["id"]) == 2


# ---------- yurt dışı teslim ----------

def test_yurtdisi_musteri_dap_ve_ihracat_istisnasi(istemci, db):
    uid = _urun(db, sku="S-EXP", ad="Export Item", fiyat="100.00")
    _musteri(db, tip=MusteriTipi.YURTDISI, eposta="export@ornek.test", ulke="DE")
    _giris(istemci, "export@ornek.test", dil="en")
    assert _sepete_ekle(istemci, uid, dil="en").status_code == 303

    odeme = istemci.get("/en/odeme")
    assert odeme.status_code == 200
    assert "Export – VAT exemption" in odeme.text
    assert 'data-e2e="satir-ihracat"' in odeme.text and 'data-e2e="not-dap"' in odeme.text
    assert "borne by the buyer" in odeme.text
    assert 'value="yurtdisi_dap"' in odeme.text and 'value="fabrika"' in odeme.text   # K4
    assert 'value="kargo"' not in odeme.text

    r = _odeme_gonder(istemci, dil="en", sayfa_html=odeme.text, ulke="DE", teslim="yurtdisi_dap",
                      on_bilgi_onay="", mesafeli_onay="")
    assert r.status_code == 303, r.text
    satir = db.execute("SELECT * FROM siparis").fetchone()
    assert satir["para_birimi"] == "EUR"
    assert satir["ihracat_istisnasi"] == 1
    assert Decimal(satir["kdv"]) == Decimal("0")
    assert Decimal(satir["kargo"]) == Decimal("0")
    assert Decimal(satir["toplam"]) == Decimal("100.00")
    assert satir["teslim_yontemi"] == "yurtdisi_dap"


def test_tr_disi_teslimatta_kargo_secilemez(istemci, db):
    _kur(db)
    uid = _urun(db, fiyat="100.00")
    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    _sepete_ekle(istemci, uid)

    r = _odeme_gonder(istemci, ulke="DE", teslim="kargo")
    assert r.status_code == 400
    assert 'id="hata-teslim"' in r.text
    assert 'value="kargo"' not in r.text
    assert 'value="yurtdisi_dap"' in r.text and 'value="fabrika"' in r.text
    assert _say(db, "SELECT COUNT(*) FROM siparis") == 0

    # bireysel müşteri, yurt dışı teslim: TRY, KDV yerine ihracat istisnası satırı ve DAP notu
    hesap = _odeme_gonder(istemci, ulke="DE", teslim="yurtdisi_dap", islem="hesapla")
    assert hesap.status_code == 200
    assert "İhracat – KDV istisnası" in hesap.text
    assert "alıcıya aittir" in hesap.text
    assert "3.500,00 ₺" in hesap.text
    r = _odeme_gonder(istemci, sayfa_html=hesap.text, ulke="DE", teslim="yurtdisi_dap")
    assert r.status_code == 303, r.text
    satir = db.execute("SELECT * FROM siparis").fetchone()
    assert satir["para_birimi"] == "TRY"
    assert satir["ihracat_istisnasi"] == 1
    assert Decimal(satir["toplam"]) == Decimal("3500.00")


# ---------- sepet ----------

def test_teklif_zorunlu_urun_409(istemci, db):
    uid = _urun(db, sku="8301033800019", ad="KUKA KRC5 KR 140 R3200-2 PA", kok="Endüstriyel Robotlar",
                fiyat="20000.00", teklif=True)
    r = _sepete_ekle(istemci, uid)
    assert r.status_code == 409
    assert re.search(rf'href="/tr/teklif\?urun_id={uid}"[^>]*data-e2e="teklif-iste"', r.text)
    assert _say(db, "SELECT COUNT(*) FROM sepet_kalemi") == 0


def test_olmayan_urun_404_bozuk_adet_400(istemci, db):
    assert _sepete_ekle(istemci, 999999).status_code == 404
    uid = _urun(db, fiyat="10.00", stok=500)   # G3e: stok sınırı 99 sınırından büyük
    # son inceleme I-1: bozuk adet çıplak 400 değil; ürün çapasına 303 + bildirim, sepete bir şey eklenmez
    r = _sepete_ekle(istemci, uid, adet="abc")
    assert r.status_code == 303 and r.headers["location"] == f"/tr/urun/{uid}#urun-{uid}"
    assert _say(db, "SELECT COUNT(*) FROM sepet_kalemi WHERE urun_id = ?", uid) == 0
    assert _sepete_ekle(istemci, uid, adet="1000").status_code == 303
    assert _say(db, "SELECT adet FROM sepet_kalemi WHERE urun_id = ?", uid) == 99


def test_adet_guncelle_ve_kaldir(istemci, db):
    _kur(db)
    uid = _urun(db, fiyat="10.00", stok=5)
    _sepete_ekle(istemci, uid)
    csrf = csrf_al(istemci, "/tr/sepet")
    r = istemci.post("/tr/sepet/adet", data={"urun_id": str(uid), "adet": "3", "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 303
    assert _say(db, "SELECT adet FROM sepet_kalemi WHERE urun_id = ?", uid) == 3
    r = istemci.post("/tr/sepet/kaldir", data={"urun_id": str(uid), "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303
    assert _say(db, "SELECT COUNT(*) FROM sepet_kalemi") == 0


def test_urunlu_sepet_sayfasi_render(istemci, db):
    # _makrolar.html'deki fiyat makrosu bağlamdaki t/para/kur'a ihtiyaç duyar ("with context" olmadan UndefinedError)
    _kur(db)
    uid = _urun(db, fiyat="10.00")
    _sepete_ekle(istemci, uid)
    r = istemci.get("/tr/sepet")
    assert r.status_code == 200
    assert 'data-e2e="sepet-kalemi"' in r.text


def test_sepet_csrf_yoksa_403(istemci, db):
    uid = _urun(db, fiyat="10.00")
    istemci.get("/tr/sepet")
    r = istemci.post("/tr/sepet/ekle", data={"urun_id": str(uid), "adet": "1"}, follow_redirects=False)
    assert r.status_code == 403
    assert _say(db, "SELECT COUNT(*) FROM sepet_kalemi") == 0


# ---------- ödeme ----------

def test_girissiz_odeme_yonlendirir(istemci):
    # G3g madde 1: girişsiz ödemede giriş yönlendirmesi yok (gömülü hesap); boş sepet sepete döner
    r = istemci.get("/tr/odeme", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/tr/sepet"
    r = istemci.get("/en/odeme", follow_redirects=False)
    assert r.headers["location"] == "/en/sepet"


def test_odemede_dusen_urun_bildirilir(istemci, db):
    _kur(db)
    kalan = _urun(db, sku="S-KALAN", ad="Kalan Ürün", fiyat="10.00")
    dusen = _urun(db, sku="S-DUSEN", ad="Pasifleşen Ürün", fiyat="10.00")
    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    _sepete_ekle(istemci, kalan)
    _sepete_ekle(istemci, dusen)
    sayfa = istemci.get("/tr/odeme")                       # kullanıcı formu açtı
    with db:
        db.execute("UPDATE urun SET aktif = 0 WHERE id = ?", (dusen,))

    # K21: POST'ta siparis_olustur'dan önce kalemler() çağrılır, düşen ürün adıyla bildirilir
    r = _odeme_gonder(istemci, sayfa_html=sayfa.text)
    assert r.status_code == 409
    assert "sepetinizden çıkarıldı" in r.text and "Pasifleşen Ürün" in r.text
    assert _say(db, "SELECT COUNT(*) FROM siparis") == 0
    assert _say(db, "SELECT COUNT(*) FROM sepet_kalemi WHERE urun_id = ?", dusen) == 0

    r = _odeme_gonder(istemci, sayfa_html=r.text)          # yeni tutarla onay
    assert r.status_code == 303, r.text


def test_kur_yoksa_anlasilir_hata(istemci, db):
    uid = _urun(db, fiyat="100.00")
    _sepete_ekle(istemci, uid)
    sepet = istemci.get("/tr/sepet")
    assert sepet.status_code == 200
    assert "kuru alınamadığı" in sepet.text

    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    odeme = istemci.get("/tr/odeme")
    assert odeme.status_code == 200
    assert "kuru alınamadığı" in odeme.text
    r = _odeme_gonder(istemci, sayfa_html=odeme.text)
    assert r.status_code == 409          # G3a Ö1: iş kuralı hatası 4xx + formun üstünde özet (önceden 503)
    assert _say(db, "SELECT COUNT(*) FROM siparis") == 0


def test_kur_degisince_fark_onayi(istemci, db):
    _kur(db, satis="35.0000")
    uid = _urun(db, fiyat="100.00")
    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    _sepete_ekle(istemci, uid)
    eski = istemci.get("/tr/odeme")
    assert _gizli(eski.text, "gosterilen_toplam") == "4830.00"
    assert _gizli(eski.text, "gosterilen_kur") == "35.0000"

    _kur(db, tarih=date(2026, 10, 13), satis="36.0000")      # kullanıcı formdayken kur değişti
    r = _odeme_gonder(istemci, sayfa_html=eski.text)
    assert r.status_code == 409
    assert "Tutar güncellendi" in r.text
    assert "4.968,00 ₺" in r.text                              # 3.600 + 720 + 540 + 108
    assert _gizli(r.text, "gosterilen_toplam") == "4968.00"
    assert _say(db, "SELECT COUNT(*) FROM siparis") == 0

    r = _odeme_gonder(istemci, sayfa_html=r.text)               # yeni tutar onaylandı
    assert r.status_code == 303
    assert Decimal(db.execute("SELECT toplam FROM siparis").fetchone()[0]) == Decimal("4968.00")


# ---------- kart, 3D, güvenlik ----------

def test_kart_formu_skt_cvc_gonderilmez(istemci, db):
    no = _siparis_hazirla(istemci, db)
    sayfa = istemci.get(f"/tr/odeme/{no}/kart")
    assert sayfa.status_code == 200
    assert "DEMO: yalnız test kartları" in sayfa.text
    assert "4111 1111 1111 1111" in sayfa.text and "4000 0000 0000 0002" in sayfa.text
    for kimlik in ("kart_skt", "kart_cvc"):
        etiket = re.search(rf'<input[^>]*id="{kimlik}"[^>]*>', sayfa.text).group(0)
        assert "name=" not in etiket
    assert re.search(r'<input[^>]*name="kart_no"', sayfa.text)
    assert 'data-e2e="kart-gonder"' in sayfa.text and 'data-e2e="satir-kdv"' in sayfa.text
    assert len(_gizli(sayfa.text, "islem_anahtari")) >= 16


def test_cift_post_ayni_anahtar_tek_sonuc(istemci, db):
    no = _siparis_hazirla(istemci, db)
    r1, form = _kart_ode(istemci, no, "4111111111111111")
    r2 = istemci.post(f"/tr/odeme/{no}/kart", data=form, follow_redirects=False)
    assert r1.status_code == r2.status_code == 303
    assert r1.headers["location"] == r2.headers["location"]
    assert _say(db, "SELECT COUNT(*) FROM odeme_denemesi") == 1


def test_baska_musterinin_siparisi_404(istemci, db):
    no = _siparis_hazirla(istemci, db, eposta="a@ornek.test")
    _musteri(db, eposta="b@ornek.test")
    with TestClient(istemci.app) as baska:
        _giris(baska, "b@ornek.test")
        assert baska.get(f"/tr/siparis/{no}").status_code == 404
        assert baska.get(f"/tr/odeme/{no}/kart").status_code == 404
        assert baska.get(f"/tr/odeme/{no}/3d?a=xxxxxxxxxxxxxxxxxxxx").status_code == 404
    with TestClient(istemci.app) as misafir:
        r = misafir.get(f"/tr/siparis/{no}", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"].startswith("/tr/giris?sonraki=")


def test_gecersiz_kart_mesaji_ve_numara_saklanmaz(istemci, db):
    no = _siparis_hazirla(istemci, db)
    r, _ = _kart_ode(istemci, no, "5555 4444 3333 1111")
    assert r.status_code == 400
    assert re.search(r'data-e2e="odeme-hata"[^>]*data-kod="gecersiz_kart"', r.text)
    assert "Demo: yalnız test kartları kabul edilir" in r.text
    assert "5555444433331111" not in r.text and "5555 4444 3333 1111" not in r.text
    assert db.execute("SELECT durum FROM odeme_denemesi").fetchone()[0] == "gecersiz_kart"
    assert "5555444433331111" not in _db_dokumu(db)
    assert db.execute("SELECT durum FROM siparis WHERE no = ?", (no,)).fetchone()[0] == "odeme_bekliyor"


def test_tam_kart_numarasi_yanitta_ve_dbde_yok(istemci, db):
    no = _siparis_hazirla(istemci, db)
    r, _ = _kart_ode(istemci, no, "4111111111111111")
    r, uc_d = _sms(istemci, no, r.headers["location"])
    onay = istemci.get(r.headers["location"])
    for html in (uc_d.text, onay.text):
        assert "4111111111111111" not in html
        assert "4111 1111 1111 1111" not in html
    assert "1111" in uc_d.text
    assert "4111111111111111" not in _db_dokumu(db)


def test_hatali_sms_siparis_sayfasina_doner(istemci, db):
    no = _siparis_hazirla(istemci, db)
    r, _ = _kart_ode(istemci, no, "4111111111111111")
    r, _ = _sms(istemci, no, r.headers["location"], kod="123456")
    assert r.headers["location"] == f"/tr/siparis/{no}?hata=sms_hatali"
    sayfa = istemci.get(r.headers["location"])
    assert re.search(r'data-e2e="odeme-hata"[^>]*data-kod="sms_hatali"', sayfa.text)
    assert "SMS kodu hatalı" in sayfa.text
    assert db.execute("SELECT durum FROM siparis WHERE no = ?", (no,)).fetchone()[0] == "odeme_bekliyor"


# ---------- K22 §5: adım göstergesi ----------

def _adim(html):
    nav = re.search(r'<nav class="adimlar"[^>]*>(.*?)</nav>', html, re.S)
    assert nav, "adım göstergesi yok"
    gecerli = re.findall(r'<li[^>]*aria-current="step"[^>]*>.*?<span class="adim-no">(\d)</span>', nav.group(1), re.S)
    assert len(gecerli) == 1, gecerli
    return int(gecerli[0])


def test_odeme_sayfalarinda_adim_gostergesi(istemci, db):
    from tests.conftest import sayfa_denetle

    no = _siparis_hazirla(istemci, db)
    kart = istemci.get(f"/tr/odeme/{no}/kart")
    assert _adim(sayfa_denetle(kart)) == 3              # G3g madde 23: Sepet · Bilgiler · Ödeme · Onay
    assert 'class="bilgi-kutu test-kartlari"' in kart.text
    r, _ = _kart_ode(istemci, no, "4111111111111111")
    uc_d = istemci.get(r.headers["location"])
    assert _adim(sayfa_denetle(uc_d)) == 3
    assert 'class="bilgi-kutu test-kartlari"' in uc_d.text
    r, _ = _sms(istemci, no, r.headers["location"])
    assert _adim(sayfa_denetle(istemci.get(r.headers["location"]))) == 4

    uid = _urun(db, sku="S-ADIM", fiyat="10.00")
    _sepete_ekle(istemci, uid)
    assert _adim(sayfa_denetle(istemci.get("/tr/sepet"))) == 1
    odeme = istemci.get("/tr/odeme")
    assert _adim(sayfa_denetle(odeme)) == 2
    assert 'class="siparis-ozeti"' in odeme.text

    hatali = _odeme_gonder(istemci, sayfa_html=odeme.text, teslimat_sehir="")
    assert hatali.status_code == 400
    ozet = re.search(r'<div class="form-hata-ozet" role="alert"[^>]*>(.*?)</div>', hatali.text, re.S)
    assert ozet and 'href="#teslimat_sehir"' in ozet.group(1)
    assert 'id="hata-teslimat_sehir"' in hatali.text


def test_bos_sepette_kategori_baglantilari(istemci, db):
    from tests.conftest import kategori_ekle

    kid = kategori_ekle(db, kaynak_id="K1", ad="ELEKTRİK", yol="ELEKTRİK", seviye=0)
    _urun(db, fiyat="10.00", kategori_id=kid)
    html = istemci.get("/tr/sepet").text
    assert "Sepetiniz boş" in html
    assert re.search(r'class="bos-sepet-kategoriler".*?href="/tr/kategori/\d+"', html, re.S)


# ---------- Fix turu 1 ----------

def _bekleyen_sayisi(db):
    return _say(db, "SELECT COUNT(*) FROM siparis WHERE durum = 'odeme_bekliyor'")


def test_ayni_form_iki_kez_tek_siparis(istemci, db):
    _kur(db)
    uid = _urun(db, fiyat="100.00")
    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    _sepete_ekle(istemci, uid)
    sayfa = istemci.get("/tr/odeme").text
    r1 = _odeme_gonder(istemci, sayfa_html=sayfa)
    r2 = _odeme_gonder(istemci, sayfa_html=sayfa)
    assert r1.status_code == r2.status_code == 303
    assert r1.headers["location"] == r2.headers["location"]
    assert _say(db, "SELECT COUNT(*) FROM siparis") == 1
    assert _bekleyen_sayisi(db) == 1


def test_sepet_degisince_eski_bekleyen_iptal(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-A", fiyat="100.00")
    uid2 = _urun(db, sku="S-B", fiyat="20.00")
    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    _sepete_ekle(istemci, uid)
    eski = _siparis_no(_odeme_gonder(istemci).headers["location"])
    _sepete_ekle(istemci, uid2)
    r = _odeme_gonder(istemci)
    assert r.status_code == 303, r.text
    yeni = _siparis_no(r.headers["location"])
    assert yeni != eski
    assert db.execute("SELECT durum FROM siparis WHERE no = ?", (eski,)).fetchone()[0] == "iptal"
    assert db.execute("SELECT durum FROM siparis WHERE no = ?", (yeni,)).fetchone()[0] == "odeme_bekliyor"
    assert _bekleyen_sayisi(db) == 1


def test_adres_degisince_eski_bekleyen_iptal(istemci, db):
    _kur(db)
    uid = _urun(db, fiyat="100.00")
    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    _sepete_ekle(istemci, uid)
    eski = _siparis_no(_odeme_gonder(istemci).headers["location"])
    yeni = _siparis_no(_odeme_gonder(istemci, teslimat_sehir="Ankara").headers["location"])
    assert yeni != eski
    assert db.execute("SELECT durum FROM siparis WHERE no = ?", (eski,)).fetchone()[0] == "iptal"
    assert _bekleyen_sayisi(db) == 1


def test_ulke_secimi_ve_ust_bant(istemci, db):
    _urun(db, fiyat="100.00")
    uid = _urun(db, sku="S-UL", fiyat="100.00")
    _musteri(db, tip=MusteriTipi.YURTDISI, eposta="export@ornek.test", ulke="DE")
    _giris(istemci, "export@ornek.test", dil="en")
    _sepete_ekle(istemci, uid, dil="en")
    html = istemci.get("/en/odeme").text
    for ad in ("teslimat_ulke", "fatura_ulke"):
        secim = re.search(rf'<select[^>]*name="{ad}"[^>]*>(.*?)</select>', html, re.S)
        assert secim, ad
        assert re.search(r'<option value="DE" selected>Germany</option>', secim.group(1))
        assert '<option value="TR">Turkey</option>' in secim.group(1)
    ust = re.search(r'<select id="sec-ulke"[^>]*>(.*?)</select>', html, re.S).group(1)
    assert re.search(r'<option value="DE" selected>', ust)

    r = _odeme_gonder(istemci, dil="en", sayfa_html=html, ulke="XX", teslim="yurtdisi_dap",
                      on_bilgi_onay="", mesafeli_onay="")
    assert r.status_code == 400
    assert 'id="hata-teslimat_ulke"' in r.text
    assert _say(db, "SELECT COUNT(*) FROM siparis") == 0


def test_kart_hatasi_alana_bagli(istemci, db):
    no = _siparis_hazirla(istemci, db)
    r, _ = _kart_ode(istemci, no, "5555 4444 3333 1111")
    etiket = re.search(r'<input[^>]*id="kart_no"[^>]*>', r.text).group(0)
    assert 'aria-invalid="true"' in etiket
    hedef = re.search(r'aria-describedby="([^"]+)"', etiket).group(1)
    assert re.search(rf'id="{hedef}"[^>]*data-e2e="odeme-hata"', r.text)


def test_ret_sonrasi_tekrar_dene_dugmesi_birincil(istemci, db):
    no = _siparis_hazirla(istemci, db)
    r, _ = _kart_ode(istemci, no, "4000000000000002")
    r, _ = _sms(istemci, no, r.headers["location"])
    html = istemci.get(r.headers["location"]).text
    assert re.search(rf'<a class="dugme"[^>]*href="/tr/odeme/{no}/kart"', html)
    import pathlib
    css = (pathlib.Path(__file__).parent.parent / "app" / "web" / "statik" / "site.css").read_text(encoding="utf-8")
    assert re.search(r"\.form-hata-ozet a\.dugme[^{]*\{[^}]*color: var\(--surface\)", css)


# ---------- G3a Ö1: sessiz hata yok, toplamlar her durumda görünür ----------

def _islem_ozeti(html):
    m = re.search(r'<div class="form-hata-ozet islem-hatasi" role="alert"[^>]*>(.*?)</div>', html, re.S)
    assert m, "formun üstünde işlem hatası özeti yok"
    return m.group(1)


def test_g3a_kur_yokken_siparis_hatasi_formun_ustunde(istemci, db):
    uid = _urun(db, fiyat="100.00")
    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    _sepete_ekle(istemci, uid)
    odeme = istemci.get("/tr/odeme")
    assert "islem-hatasi" not in odeme.text            # GET'te yalnız uyarı; özet gönderimden sonra
    r = _odeme_gonder(istemci, sayfa_html=odeme.text)
    assert 400 <= r.status_code < 500
    ozet = _islem_ozeti(r.text)
    assert "Sipariş oluşturulamadı" in ozet
    assert "Döviz kuru bugün alınamadı; lütfen daha sonra deneyin ya da teklif isteyin" in ozet
    assert 'href="/tr/teklif"' in ozet
    assert r.text.index("islem-hatasi") < r.text.index('class="odeme-formu"')
    assert 'data-hata-ozet' in r.text                   # site.js odağı özete taşır


def test_g3a_tutar_degisince_ozet_formun_ustunde(istemci, db):
    _kur(db, satis="35.0000")
    uid = _urun(db, fiyat="100.00")
    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    _sepete_ekle(istemci, uid)
    eski = istemci.get("/tr/odeme")
    _kur(db, tarih=date(2026, 10, 13), satis="36.0000")
    r = _odeme_gonder(istemci, sayfa_html=eski.text)
    assert r.status_code == 409
    assert "Tutar güncellendi" in _islem_ozeti(r.text)


def test_g3a_kur_yokken_sepette_eur_toplamlar(istemci, db):
    uid = _urun(db, fiyat="100.00")
    _sepete_ekle(istemci, uid)
    html = istemci.get("/tr/sepet").text
    ozet = re.search(r'<dl class="tutar-ozeti">.*?</dl>', html, re.S)
    assert ozet, "sepette tutar özeti yok"
    # bireysel TR, kur yok: EUR ile ara toplam 100, kargo 15, KDV 23 (G3i madde 4: ürünler 20 + kargo 3), genel toplam 138
    for metin in ("Ara toplam (KDV hariç)", "100,00 €", "15,00 €", "KDV (ürünler)", "20,00 €", "KDV (kargo)", "3,00 €",
                  "Tahmini toplam", "138,00 €"):  # G3e madde 5
        assert metin in ozet.group(0), metin
    # KDV dahil satır (G3i madde 3: ana tutar kendi satırında)
    assert re.search(r'class="kalem-tutar sayi"[^>]*><span class="kalem-ana"><span class="tutar"[^>]*>120,00 €</span>', html)
    assert "data-e2e=\"not-kur-yok\"" in html and "TL tutar" in html


def test_g3a_kur_yokken_odemede_eur_toplamlar(istemci, db):
    uid = _urun(db, fiyat="100.00")
    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    _sepete_ekle(istemci, uid)
    html = istemci.get("/tr/odeme").text
    ozet = re.search(r'<dl class="tutar-ozeti">.*?</dl>', html, re.S)
    assert ozet and "138,00 €" in ozet.group(0)
    assert _gizli(html, "gosterilen_toplam") == ""      # EUR yedek tutarı TL siparişe onay sayılmaz


def test_g3a_sepet_bos_yarisi_bildirimle_doner(istemci, db, monkeypatch):
    from app.siparis.servis import SepetBos
    from app.web.rotalar import sepet_odeme

    _kur(db)
    uid = _urun(db, fiyat="100.00")
    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    _sepete_ekle(istemci, uid)

    def bos(*a, **k):
        raise SepetBos()
    monkeypatch.setattr(sepet_odeme, "siparis_olustur", bos)
    r = _odeme_gonder(istemci)
    assert r.status_code == 303 and r.headers["location"] == "/tr/sepet"
    assert "sipariş oluşturulmadı" in istemci.get("/tr/sepet").text
