"""Görev 15 — teklif formu, geri bildirim ve yönetim paneli (TestClient ile)."""
import re
from datetime import UTC, date, datetime, timedelta

import pytest

from app.db import baglan, gecisleri_uygula
from app.fiyat.kur import Kur, kur_kaydet, son_kur
from app.fiyat.kurallar import MusteriTipi, TeslimYontemi
from app.hesap.servis import Adres, KayitGirdisi, kayit_ol
from app.para import d
from app.sepet.servis import ekle, sepet_bul
from app.siparis.servis import siparis_olustur
from tests.conftest import csrf_al, urun_ekle

PAROLA = "demo-parola-123"
YONETICI_PAROLA = "yonetici-parola-123"
MESAJ = "KUKA robot için teslim süresi ve fiyat bilgisi rica ederim."
GB_METNI = "Teklif formunda telefon alanı daha görünür olsun."


@pytest.fixture
def db(istemci):
    con = baglan(istemci.app.state.ayarlar.db_yolu)
    gecisleri_uygula(con)
    yield con
    con.close()


def _musteri(db, tip=MusteriTipi.BIREYSEL, eposta="bireysel@ornek.test", ulke="TR", **ek):
    with db:
        return kayit_ol(db, KayitGirdisi(tip=tip, ad=f"QATestUser {tip.value}", eposta=eposta, parola=PAROLA,
                                         ulke=ulke, kvkk_onay=True, **ek), datetime.now(UTC))


def _giris(istemci, eposta, dil="tr"):
    csrf = csrf_al(istemci, f"/{dil}/giris")
    r = istemci.post(f"/{dil}/giris", data={"eposta": eposta, "parola": PAROLA, "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 303, r.text


def _yonetici_giris(istemci):
    csrf = csrf_al(istemci, "/yonetim/giris")
    r = istemci.post("/yonetim/giris", data={"kullanici": "yonetici", "parola": YONETICI_PAROLA, "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/yonetim", r.text


def _robot(db):
    with db:
        return urun_ekle(db, sku="8301033800019", ad="KUKA KRC5 KR 140 R3200-2 PA", kok="Endüstriyel Robotlar",
                         fiyat="20000.00", teklif=True)


def _teklif_gonder(istemci, dil="tr", **ek):
    form = {"ad": "QATestUser Misafir", "firma": "Deneme Otomasyon Ltd.", "eposta": "misafir@ornek.test",
            "telefon": "", "ulke": "TR", "adet": "1", "mesaj": MESAJ, "kvkk_onay": "1"}
    form.update(ek)
    form["csrf"] = csrf_al(istemci, f"/{dil}/teklif")
    return istemci.post(f"/{dil}/teklif", data=form, follow_redirects=False)


def _gb_gonder(istemci, metin=GB_METNI, csrf=True):
    veri = {"sayfa": "/tr/teklif", "metin": metin, "isim": "QATestUser"}
    if csrf:
        veri["csrf"] = csrf_al(istemci, "/tr/teklif")
    else:
        istemci.get("/tr/teklif")
    return istemci.post("/geri-bildirim", data=veri)


def _siparis(db):
    simdi = datetime.now(UTC)
    with db:
        m = kayit_ol(db, KayitGirdisi(tip=MusteriTipi.BIREYSEL, ad="QATestUser Yönetim", eposta="yonetim-test@ornek.test",
                                      parola=PAROLA, ulke="TR", kvkk_onay=True), simdi)
        uid = urun_ekle(db, sku="Y-1", ad="Yönetim Test Ürünü", fiyat="100.00")
        kur_kaydet(db, Kur(tarih=date(2026, 10, 12), eur_alis=d("34.9000"), eur_satis=d("35.0000")), simdi)
        sepet_id = sepet_bul(db, None, m.id, simdi)
        ekle(db, sepet_id, uid, 1)
        adres = Adres(ad_soyad="QATestUser Alıcı", satir1="Test Mah. Deneme Sk. No: 1", sehir="Konya", ulke="TR")
        return siparis_olustur(db, m, sepet_id, TeslimYontemi.KARGO, adres, adres, son_kur(db), simdi)


def _esitleme_kaydi(db, saat_once, durum="tam"):
    bitis = datetime.now(UTC) - timedelta(hours=saat_once)
    with db:
        db.execute("INSERT INTO esitleme_gunlugu (basla, bitis, durum, api_toplam, cekilen, eklenen, guncellenen, "
                   "pasiflenen) VALUES (?, ?, ?, 4449, 4449, 0, 4449, 0)",
                   ((bitis - timedelta(minutes=5)).isoformat(), bitis.isoformat(), durum))


def _say(db, sql, *p):
    return db.execute(sql, p).fetchone()[0]


# ---------- teklif ----------

def test_teklif_formu_urun_on_secili_misafir(istemci, db):
    uid = _robot(db)
    sayfa = istemci.get(f"/tr/teklif?urun_id={uid}")
    assert sayfa.status_code == 200
    assert f'name="urun_id" value="{uid}"' in sayfa.text
    assert "KUKA KRC5 KR 140 R3200-2 PA" in sayfa.text
    assert 'data-e2e="teklif-gonder"' in sayfa.text

    r = _teklif_gonder(istemci, urun_id=str(uid))
    assert r.status_code == 303
    assert re.fullmatch(r"/tr/teklif/tamam\?no=CR-TKL-\d{8}-\d{4}", r.headers["location"])
    no = r.headers["location"].split("no=")[1]
    tamam = istemci.get(r.headers["location"])
    assert tamam.status_code == 200
    assert re.search(rf'data-e2e="teklif-no"[^>]*>{no}<', tamam.text)
    satir = db.execute("SELECT * FROM teklif WHERE no = ?", (no,)).fetchone()
    assert satir["urun_id"] == uid
    assert satir["musteri_id"] is None
    assert satir["durum"] == "yeni"


def test_teklif_bozuk_urun_id_yok_sayilir(istemci):
    assert istemci.get("/tr/teklif?urun_id=abc").status_code == 200
    r = istemci.get("/tr/teklif?urun_id=999999")
    assert r.status_code == 200
    assert 'name="urun_id" value="999999"' not in r.text


def test_teklif_uye_otomatik_doldurma(istemci, db):
    m = _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="kurumsal@ornek.test",
                 vergi_kimlik_no="1234567890", vergi_dairesi="Selçuk")
    _giris(istemci, "kurumsal@ornek.test")
    sayfa = istemci.get("/tr/teklif")
    assert 'value="QATestUser kurumsal"' in sayfa.text
    assert 'value="kurumsal@ornek.test"' in sayfa.text
    r = _teklif_gonder(istemci, ad="QATestUser kurumsal", eposta="kurumsal@ornek.test")
    assert r.status_code == 303
    assert _say(db, "SELECT musteri_id FROM teklif") == m.id


def test_teklif_hatali_form_alan_hatasi(istemci, db):
    r = _teklif_gonder(istemci, ad="")
    assert r.status_code == 400
    assert 'id="hata-ad"' in r.text
    assert MESAJ in r.text                       # girilen veri korunur
    r = _teklif_gonder(istemci, adet="abc")
    assert r.status_code == 400 and 'id="hata-adet"' in r.text
    r = _teklif_gonder(istemci, ulke="Türkiye")
    assert r.status_code == 400 and 'id="hata-ulke"' in r.text
    assert _say(db, "SELECT COUNT(*) FROM teklif") == 0


def test_teklif_yonetimde_gorunur_ve_durum_degisir(istemci, db):
    assert _teklif_gonder(istemci).status_code == 303
    tid, no = db.execute("SELECT id, no FROM teklif").fetchone()
    _yonetici_giris(istemci)
    liste = istemci.get("/yonetim/teklifler")
    assert liste.status_code == 200
    assert no in liste.text and "QATestUser Misafir" in liste.text

    csrf = csrf_al(istemci, "/yonetim/teklifler")
    r = istemci.post(f"/yonetim/teklif/{tid}/durum", data={"durum": "inceleniyor", "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 303
    assert _say(db, "SELECT durum FROM teklif WHERE id = ?", tid) == "inceleniyor"

    r = istemci.post(f"/yonetim/teklif/{tid}/durum", data={"durum": "yeni", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 409
    assert "izin verilmiyor" in r.text
    assert _say(db, "SELECT durum FROM teklif WHERE id = ?", tid) == "inceleniyor"

    r = istemci.post(f"/yonetim/teklif/{tid}/durum", data={"durum": "uctu", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 400


# ---------- geri bildirim ----------

def test_geri_bildirim_json_tamam(istemci, db):
    r = _gb_gonder(istemci)
    assert r.status_code == 200
    assert r.json() == {"tamam": True}
    satir = db.execute("SELECT sayfa, metin, isim, durum FROM geri_bildirim").fetchone()
    assert tuple(satir) == ("/tr/teklif", GB_METNI, "QATestUser", "yeni")


def test_geri_bildirim_csrf_yok_403(istemci, db):
    r = _gb_gonder(istemci, csrf=False)
    assert r.status_code == 403
    assert _say(db, "SELECT COUNT(*) FROM geri_bildirim") == 0


def test_geri_bildirim_bos_metin_400(istemci, db):
    r = _gb_gonder(istemci, metin="   ")
    assert r.status_code == 400
    assert r.json()["tamam"] is False
    assert _say(db, "SELECT COUNT(*) FROM geri_bildirim") == 0


def test_geri_bildirim_yonetimde_gorunur_ve_durum_degisir(istemci, db):
    assert _gb_gonder(istemci).status_code == 200
    gid = _say(db, "SELECT id FROM geri_bildirim")
    _yonetici_giris(istemci)
    sayfa = istemci.get("/yonetim/geri-bildirimler")
    assert sayfa.status_code == 200 and GB_METNI in sayfa.text

    csrf = csrf_al(istemci, "/yonetim/geri-bildirimler")
    r = istemci.post(f"/yonetim/geri-bildirim/{gid}/durum", data={"durum": "okundu", "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 303
    assert _say(db, "SELECT durum FROM geri_bildirim WHERE id = ?", gid) == "okundu"
    assert GB_METNI not in istemci.get("/yonetim/geri-bildirimler?durum=yeni").text
    assert GB_METNI in istemci.get("/yonetim/geri-bildirimler?durum=okundu").text

    r = istemci.post(f"/yonetim/geri-bildirim/{gid}/durum", data={"durum": "sil", "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 400
    r = istemci.post("/yonetim/geri-bildirim/999999/durum", data={"durum": "okundu", "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 404


# ---------- yönetim girişi ----------

@pytest.mark.parametrize("yol", ["/yonetim", "/yonetim/siparisler", "/yonetim/teklifler", "/yonetim/geri-bildirimler"])
def test_yonetim_girissiz_yonlendirir(istemci, yol):
    r = istemci.get(yol, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/yonetim/giris"


def test_yonetim_girissiz_post_yonlendirir(istemci):
    csrf = csrf_al(istemci, "/yonetim/giris")
    r = istemci.post("/yonetim/siparis/1/durum", data={"durum": "odendi", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/yonetim/giris"


def test_yonetim_yanlis_parola(istemci):
    giris = istemci.get("/yonetim/giris")
    assert 'name="kullanici"' in giris.text and 'name="parola"' in giris.text
    assert 'data-e2e="yonetim-giris"' in giris.text
    csrf = csrf_al(istemci, "/yonetim/giris")
    r = istemci.post("/yonetim/giris", data={"kullanici": "yonetici", "parola": "yanlis-parola", "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 401
    assert "hatalı" in r.text
    r = istemci.post("/yonetim/giris", data={"kullanici": "baska", "parola": YONETICI_PAROLA, "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 401
    assert istemci.get("/yonetim", follow_redirects=False).status_code == 303


def test_yonetim_11_deneme_429(istemci):
    csrf = csrf_al(istemci, "/yonetim/giris")
    for _ in range(10):
        r = istemci.post("/yonetim/giris", data={"kullanici": "yonetici", "parola": "yanlis", "csrf": csrf},
                         follow_redirects=False)
        assert r.status_code == 401
    r = istemci.post("/yonetim/giris", data={"kullanici": "yonetici", "parola": YONETICI_PAROLA, "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 429
    assert "Çok fazla deneme" in r.text
    assert istemci.get("/yonetim", follow_redirects=False).status_code == 303


def test_yonetim_cikis(istemci):
    _yonetici_giris(istemci)
    assert istemci.get("/yonetim").status_code == 200
    csrf = csrf_al(istemci, "/yonetim")
    r = istemci.post("/yonetim/cikis", data={"csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303
    assert istemci.get("/yonetim", follow_redirects=False).status_code == 303


# ---------- sipariş durumu ----------

def test_siparis_durum_izinli_ve_izinsiz(istemci, db):
    s = _siparis(db)
    _yonetici_giris(istemci)
    liste = istemci.get("/yonetim/siparisler")
    assert liste.status_code == 200 and s.no in liste.text

    csrf = csrf_al(istemci, "/yonetim/siparisler")
    r = istemci.post(f"/yonetim/siparis/{s.id}/durum", data={"durum": "odendi", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/yonetim/siparisler"
    assert _say(db, "SELECT durum FROM siparis WHERE id = ?", s.id) == "odendi"

    r = istemci.post(f"/yonetim/siparis/{s.id}/durum", data={"durum": "teslim", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 409
    assert "izin verilmiyor" in r.text
    assert _say(db, "SELECT durum FROM siparis WHERE id = ?", s.id) == "odendi"

    r = istemci.post(f"/yonetim/siparis/{s.id}/durum", data={"durum": "uctu", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 400
    r = istemci.post("/yonetim/siparis/999999/durum", data={"durum": "odendi", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 404


# ---------- pano ----------

def test_pano_esitleme_uyarisi_36_saat(istemci, db):
    _esitleme_kaydi(db, 40, "tam")
    _esitleme_kaydi(db, 1, "eksik")          # sonraki eksik tur uyarıyı kaldırmaz
    _yonetici_giris(istemci)
    pano = istemci.get("/yonetim")
    assert pano.status_code == 200
    assert "uyari-esitleme" in pano.text
    assert "36 saatten eski" in pano.text
    assert 'data-e2e="son-esitleme"' in pano.text
    assert (datetime.now(UTC) - timedelta(hours=40)).strftime("%d.%m.%Y") in pano.text
    assert "Eksik" in pano.text


def test_pano_taze_esitlemede_uyari_yok(istemci, db):
    _esitleme_kaydi(db, 2, "tam")
    with db:
        kur_kaydet(db, Kur(tarih=date(2026, 10, 12), eur_alis=d("34.9000"), eur_satis=d("35.0000")),
                   datetime.now(UTC))
    _yonetici_giris(istemci)
    pano = istemci.get("/yonetim")
    assert "uyari-esitleme" not in pano.text
    assert "35.0000" in pano.text and "12.10.2026" in pano.text


def test_pano_hic_esitleme_yoksa_uyari(istemci):
    _yonetici_giris(istemci)
    pano = istemci.get("/yonetim")
    assert "uyari-esitleme" in pano.text
    assert "henüz başarılı" in pano.text
    assert "Kayıtlı kur yok" in pano.text


# ---------- Görev 15 ek testleri (kontrolcü kararları ve K22 §3) ----------

from tests.conftest import oturum_oku, sayfa_denetle  # noqa: E402


def test_teklif_formu_sinirlar_ve_ulke_secimi(istemci, db):
    html = sayfa_denetle(istemci.get("/tr/teklif"))
    for ad, sinir in (("ad", 120), ("eposta", 254), ("firma", 160), ("telefon", 40)):
        assert re.search(rf'<input id="{ad}" name="{ad}"[^>]*maxlength="{sinir}"', html), ad
    assert '<select id="ulke" name="ulke"' in html
    assert '<option value="TR" selected>Türkiye</option>' in html
    for ad, sinir in (("ad", 120), ("eposta", 254), ("firma", 160), ("telefon", 40)):
        deger = "a" * (sinir - 10) + "@ornek.test" if ad == "eposta" else "x" * (sinir + 1)
        r = _teklif_gonder(istemci, **{ad: deger})
        assert r.status_code == 400 and f'id="hata-{ad}"' in r.text, ad
        assert "Girilen metin çok uzun." in r.text
    r = _teklif_gonder(istemci, ulke="XX")
    assert r.status_code == 400 and 'id="hata-ulke"' in r.text
    assert _say(db, "SELECT COUNT(*) FROM teklif") == 0
    assert _teklif_gonder(istemci, ad="x" * 120, ulke="de").status_code == 303
    assert _say(db, "SELECT ulke FROM teklif") == "DE"


def test_teklif_hata_ozeti_ve_urun_karti(istemci, db):
    uid = _robot(db)
    html = sayfa_denetle(istemci.get(f"/tr/teklif?urun_id={uid}"))
    assert 'class="teklif-urun"' in html and "8301033800019" in html
    r = _teklif_gonder(istemci, ad="", mesaj="", urun_id=str(uid))
    assert r.status_code == 400
    assert 'role="alert"' in r.text and 'href="#ad"' in r.text and 'href="#mesaj"' in r.text
    assert f'name="urun_id" value="{uid}"' in r.text          # ürün seçimi korunur
    en = istemci.get("/en/teklif")
    assert "Quote for price, delivery and volume orders" in en.text and "Country" in en.text   # G3c madde 21 başlık


def test_yonetim_girisi_csrf_yeniler_cikis_temizler(istemci):
    eski = csrf_al(istemci, "/yonetim/giris")
    _yonetici_giris(istemci)
    oturum = oturum_oku(istemci)
    assert oturum.get("yonetici") is True and oturum.get("csrf") and oturum["csrf"] != eski
    r = istemci.post("/yonetim/cikis", data={"csrf": eski}, follow_redirects=False)
    assert r.status_code == 403                                  # girişten önceki jeton geçersiz
    yeni = csrf_al(istemci, "/yonetim")
    assert istemci.post("/yonetim/cikis", data={"csrf": yeni}, follow_redirects=False).status_code == 303
    oturum = oturum_oku(istemci)
    assert "yonetici" not in oturum and oturum.get("csrf") != yeni


def test_yonetim_sayfalari_ortak_kurallar(istemci, db):
    sayfa_denetle(istemci.get("/yonetim/giris"))
    _yonetici_giris(istemci)
    for yol in ("/yonetim", "/yonetim/siparisler", "/yonetim/teklifler", "/yonetim/geri-bildirimler"):
        html = sayfa_denetle(istemci.get(yol))
        assert 'class="yonetim-menu"' in html
        assert html.count('aria-current="page"') >= 1, yol
    pano = istemci.get("/yonetim").text
    assert len(re.findall(r'<li class="sayi-karti[" ]', pano)) == 5   # G3a Ö1: + döviz kuru kartı


def test_pano_tam_turda_bozuk_ozeti_hata_sayilmaz(istemci, db):
    bitis = datetime.now(UTC) - timedelta(hours=1)
    with db:
        db.execute("INSERT INTO esitleme_gunlugu (basla, bitis, durum, api_toplam, cekilen, eklenen, guncellenen, "
                   "pasiflenen, bozuk, hata) VALUES (?, ?, 'tam', 10, 10, 0, 7, 0, 3, ?)",
                   ((bitis - timedelta(minutes=5)).isoformat(), bitis.isoformat(), "bozuk_kayit: 3 [A, B, C]"))
    _yonetici_giris(istemci)
    pano = istemci.get("/yonetim").text
    assert "uyari-esitleme" not in pano
    assert "atlanan bozuk kayıt 3" in pano
    assert "Not: bozuk_kayit: 3" in pano and "Hata: bozuk_kayit" not in pano
    assert "esitleme-tam" in pano


def test_pano_hata_turu_hata_metni(istemci, db):
    _esitleme_kaydi(db, 2, "tam")
    with db:
        db.execute("INSERT INTO esitleme_gunlugu (basla, bitis, durum, hata) VALUES (?, ?, 'hata', 'zaman asimi')",
                   (datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat()))
    _yonetici_giris(istemci)
    pano = istemci.get("/yonetim").text
    assert "Hata: zaman asimi" in pano and "esitleme-hata" in pano
    assert "uyari-esitleme" not in pano                         # son tam tur 2 saat önce


def test_yonetim_buyuk_kimlik_404_ve_filtre_korunur(istemci, db):
    assert _gb_gonder(istemci).status_code == 200
    gid = _say(db, "SELECT id FROM geri_bildirim")
    _yonetici_giris(istemci)
    csrf = csrf_al(istemci, "/yonetim/geri-bildirimler")
    for yol in (f"/yonetim/siparis/{2**64}/durum", f"/yonetim/teklif/{2**64}/durum"):
        assert istemci.post(yol, data={"durum": "iptal", "csrf": csrf}, follow_redirects=False).status_code in (400, 404)
    r = istemci.post(f"/yonetim/geri-bildirim/{2**64}/durum", data={"durum": "okundu", "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 404
    r = istemci.post(f"/yonetim/geri-bildirim/{gid}/durum", data={"durum": "okundu", "filtre": "yeni", "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/yonetim/geri-bildirimler?durum=yeni"


# ---------- Cilalama turu (kontrolcü kararı) ----------

def test_yonetimde_magaza_basligi_yok(istemci):
    ana = sayfa_denetle(istemci.get("/tr/"))
    assert 'class="arama"' in ana and 'id="ust-arama"' in ana and 'class="nav-oge sepet-bag"' in ana
    giris = sayfa_denetle(istemci.get("/yonetim/giris"))
    assert 'id="ust-arama"' not in giris and "sepet-bag" not in giris and 'href="/tr/kayit"' not in giris
    assert "Yönetim" in giris and 'data-e2e="yonetim-cikis"' not in giris      # girişsiz: Çıkış yok
    _yonetici_giris(istemci)
    for yol in ("/yonetim", "/yonetim/siparisler", "/yonetim/teklifler", "/yonetim/geri-bildirimler"):
        html = sayfa_denetle(istemci.get(yol))
        assert 'id="ust-arama"' not in html and "sepet-bag" not in html and "kategori-serit" not in html, yol
        assert 'class="ust yonetim-ust"' in html and 'data-e2e="yonetim-cikis"' in html, yol


def test_geri_bildirim_guvensiz_sayfa_baglanti_olmaz(istemci, db):
    with db:
        for sayfa in ("/\\evil.com", "//evil.com", "javascript:alert(1)", "/tr/sepet"):
            db.execute("INSERT INTO geri_bildirim (sayfa, metin, isim, durum, olusturma) VALUES (?, 'x', NULL, 'yeni', ?)",
                       (sayfa, datetime.now(UTC).isoformat()))
    _yonetici_giris(istemci)
    html = istemci.get("/yonetim/geri-bildirimler").text
    assert 'href="/\\evil.com"' not in html and "/\\evil.com" in html
    assert 'href="//evil.com"' not in html and 'href="javascript:' not in html
    assert '<a href="/tr/sepet">/tr/sepet</a>' in html


def test_geri_bildirim_hiz_siniri_429(istemci, db):
    csrf = csrf_al(istemci, "/tr/teklif")
    veri = {"sayfa": "/tr/", "metin": "Deneme", "csrf": csrf}
    for _ in range(10):
        assert istemci.post("/geri-bildirim", data=veri).status_code == 200
    r = istemci.post("/geri-bildirim", data=veri)
    assert r.status_code == 429 and r.json() == {"tamam": False, "hata": "cok_deneme"}
    assert _say(db, "SELECT COUNT(*) FROM geri_bildirim") == 10


def test_yonetimde_saklanan_xss_kacislanir(istemci, db):
    zararli = "<script>alert(1)</script>"
    assert _gb_gonder(istemci, metin=zararli).status_code == 200
    assert _teklif_gonder(istemci, ad=zararli[:60], mesaj=zararli, firma=zararli).status_code == 303
    _yonetici_giris(istemci)
    for yol in ("/yonetim/geri-bildirimler", "/yonetim/teklifler"):
        html = istemci.get(yol).text
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html, yol
        assert "<script>alert" not in html, yol



# ---------- G3a Ö1: panoda "kur eski/yok" uyarı kartı ----------

def test_g3a_pano_kur_yok_uyari_karti(istemci):
    _yonetici_giris(istemci)
    pano = istemci.get("/yonetim").text
    kart = re.search(r'<li class="sayi-karti sayi-karti-dikkat" data-e2e="kur-karti">.*?</li>', pano, re.S)
    assert kart and "Döviz kuru" in kart.group(0) and "Yok" in kart.group(0)
    assert re.search(r'<div class="uyari uyari-kur" role="alert">.*?Kayıtlı kur yok', pano, re.S)


def test_g3a_pano_kur_eski_uyari_karti(istemci, db):
    with db:
        kur_kaydet(db, Kur(tarih=date(2026, 9, 1), eur_alis=d("34.9000"), eur_satis=d("35.0000")), datetime.now(UTC))
    _yonetici_giris(istemci)
    pano = istemci.get("/yonetim").text
    kart = re.search(r'<li class="sayi-karti sayi-karti-dikkat" data-e2e="kur-karti">.*?</li>', pano, re.S)
    assert kart and "01.09.2026" in kart.group(0)
    assert re.search(r'<div class="uyari uyari-kur" role="alert">.*?3 günden eski', pano, re.S)


def test_g3a_pano_taze_kurda_kart_dikkat_degil(istemci, db):
    with db:
        kur_kaydet(db, Kur(tarih=datetime.now(UTC).date(), eur_alis=d("34.9000"), eur_satis=d("35.0000")),
                   datetime.now(UTC))
    _yonetici_giris(istemci)
    pano = istemci.get("/yonetim").text
    assert '<li class="sayi-karti" data-e2e="kur-karti">' in pano
    assert "uyari-kur" not in pano


def test_g3a_teklif_tamam_bes_haneli_numara(istemci):
    html = istemci.get("/tr/teklif/tamam", params={"no": "CR-TKL-20261013-10000"}).text
    assert 'data-e2e="teklif-no">CR-TKL-20261013-10000<' in html
