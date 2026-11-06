"""G3g: persona tur 3 bulguları (A: akış ve doğruluk 1–10, B: dil ve ihracat 11–17, C: mobil/yerleşim 18–22,
D: metin 23–26)."""
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from html import unescape

import pytest

from app.fiyat.kurallar import MusteriTipi, TeslimYontemi
from app.hesap.servis import Adres
from app.katalog.depo import ListeSorgusu, faset_sayilari, urun_listele
from app.sepet import servis as sepet_servis
from app.siparis.servis import SiparisDurumu, durum_degistir, siparis_getir, siparis_olustur
from app.stok import ayrilan_adetler
from tests.conftest import csrf_al, istemci_db, oturum_oku, sayfa_denetle
from tests.test_web_katalog import katalog  # noqa: F401 — fixture
from tests.test_web_sepet_odeme import (GECERLI_VKN, PAROLA, _adres_formu, _giris, _gizli, _kur, _musteri,  # noqa: F401
                                        _odeme_gonder, _sepete_ekle, _siparis_no, _urun, db)

TR_SAAT = timedelta(hours=3)


def _post(istemci, yol, veri, csrf_yolu="/tr/"):
    veri = {**veri, "csrf": csrf_al(istemci, csrf_yolu)}
    return istemci.post(yol, data=veri, follow_redirects=False)


def _bildirimler(html):
    m = re.search(r'<div class="bildirimler" role="status">(.*?)</div>', html, re.S)
    return m.group(1) if m else ""


def _say(db, sql, *p):
    return db.execute(sql, p).fetchone()[0]


def _tr(z: datetime) -> str:
    return (z.astimezone(UTC) + TR_SAAT).strftime("%d.%m.%Y %H:%M")


# =====================================================================================================
# A1 — ödemede gömülü hesap (misafir ödeme değil: hesap siparişle aynı işlemde açılır)
# =====================================================================================================

def _misafir_odeme_formu(sayfa_html, **ek):
    form = _adres_formu(**{k: v for k, v in ek.items() if not k.startswith("hesap_")})
    form.update({"hesap_tip": "bireysel", "hesap_eposta": "yeni@ornek.test", "hesap_parola": PAROLA,
                 "hesap_kvkk_onay": "1"})
    form.update({k: v for k, v in ek.items() if k.startswith("hesap_")})
    for ad in ("csrf", "gosterilen_toplam", "gosterilen_kur"):
        form[ad] = _gizli(sayfa_html, ad)
    return form


def test_g3g_misafir_odeme_sayfasi_hesap_bolumu(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-GH1", ad="Misafir Ürünü", fiyat="100.00", stok=3)
    assert _sepete_ekle(istemci, uid).status_code == 303
    r = istemci.get("/tr/odeme", follow_redirects=False)
    assert r.status_code == 200                                   # giriş sayfasına atılmaz
    html = sayfa_denetle(r)
    hesap = re.search(r'<fieldset class="bolum odeme-hesap"[^>]*data-e2e="odeme-hesap".*?(?=<fieldset class="bolum">)',
                      html, re.S)
    assert hesap, "Hesabınız bölümü yok"
    hesap = hesap.group(0)
    assert "Hesabınız" in hesap
    for ad in ("hesap_eposta", "hesap_parola", "hesap_kvkk_onay"):
        assert f'name="{ad}"' in hesap, ad
    for tip in ("bireysel", "kurumsal", "yurtdisi"):
        assert re.search(rf'name="hesap_tip" value="{tip}"', hesap), tip
    for ad in ("hesap_vkn", "hesap_vergi_dairesi", "hesap_ulke", "hesap_vat_id", "hesap_firma"):
        assert f'name="{ad}"' in hesap, ad
    assert re.search(r'Zaten hesabım var <a href="/tr/giris\?sonraki=%2Ftr%2Fodeme"', hesap)
    # Hesabınız bölümü formun üstünde (teslimat adresinden önce), aynı formun içinde
    form = re.search(r'<form method="post" action="/tr/odeme".*?</form>', html, re.S).group(0)
    assert form.index('data-e2e="odeme-hesap"') < form.index('name="teslimat_ad_soyad"')
    # kayıt ve giriş sayfaları aynen çalışır
    assert istemci.get("/tr/kayit").status_code == 200 and istemci.get("/tr/giris").status_code == 200


def test_g3g_misafir_odeme_tek_islemde_hesap_oturum_siparis(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-GH2", ad="Misafir Ürünü 2", fiyat="100.00", stok=3)
    _sepete_ekle(istemci, uid, adet="2")
    sayfa = istemci.get("/tr/odeme").text
    r = istemci.post("/tr/odeme", data=_misafir_odeme_formu(sayfa), follow_redirects=False)
    assert r.status_code == 303, r.text
    no = _siparis_no(r.headers["location"])
    m = db.execute("SELECT id, tip, ad FROM musteri WHERE eposta = 'yeni@ornek.test'").fetchone()
    assert m is not None and m["tip"] == "bireysel" and m["ad"] == "QATestUser Alıcı"
    s = db.execute("SELECT musteri_id, sepet_id FROM siparis WHERE no = ?", (no,)).fetchone()
    assert s["musteri_id"] == m["id"]
    assert _say(db, "SELECT musteri_id FROM sepet WHERE id = ?", s["sepet_id"]) == m["id"]   # sepet hesaba geçti
    assert _say(db, "SELECT COUNT(*) FROM adres WHERE musteri_id = ?", m["id"]) == 2
    assert oturum_oku(istemci).get("mid") == m["id"]                                       # oturum açık
    kart = istemci.get(r.headers["location"])
    assert kart.status_code == 200 and 'data-e2e="cikis"' in kart.text
    # yeni hesap girişte de çalışır (parola kaydedildi)
    istemci.cookies.clear()
    _giris(istemci, "yeni@ornek.test")


def test_g3g_misafir_odeme_kayitli_eposta_sepet_korunur(istemci, db):
    _kur(db)
    _musteri(db, eposta="var@ornek.test")
    uid = _urun(db, sku="S-GH3", ad="Misafir Ürünü 3", fiyat="100.00", stok=3)
    _sepete_ekle(istemci, uid)
    sayfa = istemci.get("/tr/odeme").text
    r = istemci.post("/tr/odeme", data=_misafir_odeme_formu(sayfa, hesap_eposta="VAR@ornek.test"),
                     follow_redirects=False)
    assert r.status_code == 400
    html = sayfa_denetle(r)
    assert "Bu e-posta kayıtlı, giriş yapın" in html and 'id="hata-hesap_eposta"' in html
    assert 'href="#hesap_eposta"' in html                                          # hata özetinde bağlantı
    assert _say(db, "SELECT COUNT(*) FROM musteri") == 1 and _say(db, "SELECT COUNT(*) FROM siparis") == 0
    assert _say(db, "SELECT COUNT(*) FROM sepet_kalemi WHERE urun_id = ?", uid) == 1   # sepet korunur
    assert "mid" not in oturum_oku(istemci)
    assert 'value="VAR@ornek.test"' in html                                        # girilen değer geri basılır
    assert 'href="/tr/giris?sonraki=%2Ftr%2Fodeme"' in html


def test_g3g_misafir_odeme_hesap_alanlari_dogrulanir(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-GH4", ad="Misafir Ürünü 4", fiyat="100.00", stok=3)
    _sepete_ekle(istemci, uid)
    sayfa = istemci.get("/tr/odeme").text
    r = istemci.post("/tr/odeme", data=_misafir_odeme_formu(sayfa, hesap_parola="kisa", hesap_kvkk_onay=""),
                     follow_redirects=False)
    assert r.status_code == 400
    for ad in ("hesap_parola", "hesap_kvkk_onay"):
        assert f'id="hata-{ad}"' in r.text, ad
    # kurumsal: mevcut kayıt doğrulaması (VKN sağlama, vergi dairesi, unvan)
    sayfa = istemci.get("/tr/odeme?tip=kurumsal").text
    form = _misafir_odeme_formu(sayfa, hesap_tip="kurumsal", hesap_vkn="1234567891", hesap_vergi_dairesi="",
                                hesap_firma="")
    r = istemci.post("/tr/odeme", data=form, follow_redirects=False)
    assert r.status_code == 400
    for ad in ("hesap_vkn", "hesap_vergi_dairesi", "hesap_firma"):
        assert f'id="hata-{ad}"' in r.text, ad
    # yurt dışı: AB ülkesinde VAT ID zorunlu
    r = istemci.post("/tr/odeme", data=_misafir_odeme_formu(sayfa, hesap_tip="yurtdisi", hesap_ulke="DE",
                                                            hesap_firma="QATest GmbH", hesap_vat_id=""),
                     follow_redirects=False)
    assert r.status_code == 400 and 'id="hata-hesap_vat_id"' in r.text
    assert _say(db, "SELECT COUNT(*) FROM musteri") == 0 and _say(db, "SELECT COUNT(*) FROM siparis") == 0


def test_g3g_misafir_kurumsal_hesap_ve_havale(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-GH5", ad="Misafir Ürünü 5", fiyat="100.00", stok=3)
    _sepete_ekle(istemci, uid)
    sayfa = istemci.get("/tr/odeme?tip=kurumsal").text
    assert re.search(r'name="hesap_tip" value="kurumsal" checked', sayfa)
    assert 'id="odeme-havale"' in sayfa
    form = _misafir_odeme_formu(sayfa, hesap_tip="kurumsal", hesap_vkn=GECERLI_VKN, hesap_vergi_dairesi="Selçuk",
                                hesap_firma="QATest Otomasyon A.Ş.", odeme_yontemi="havale")
    form["odeme_yontemi"] = "havale"
    r = istemci.post("/tr/odeme", data=form, follow_redirects=False)
    assert r.status_code == 303, r.text
    assert re.fullmatch(r"/tr/siparis/CR-DEMO-\d{8}-\d{4}", r.headers["location"])
    m = db.execute("SELECT tip, ad, vergi_kimlik_no FROM musteri").fetchone()
    assert tuple(m) == ("kurumsal", "QATest Otomasyon A.Ş.", GECERLI_VKN)


def test_g3g_misafir_tip_degisince_tutar_yeniden_hesaplanir(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-GH6", ad="Misafir Ürünü 6", fiyat="100.00", stok=3)
    _sepete_ekle(istemci, uid)
    sayfa = istemci.get("/tr/odeme").text                        # bireysel varsayılan (TR): KDV dahil toplam
    form = _misafir_odeme_formu(sayfa, hesap_tip="kurumsal", hesap_vkn=GECERLI_VKN, hesap_vergi_dairesi="Selçuk",
                                hesap_firma="QATest A.Ş.")
    form["gosterilen_toplam"] = "1"
    r = istemci.post("/tr/odeme", data=form, follow_redirects=False)
    assert r.status_code == 409 and _say(db, "SELECT COUNT(*) FROM musteri") == 0
    assert re.search(r'name="hesap_tip" value="kurumsal" checked', r.text)


def test_g3g_girisli_odemede_hesap_bolumu_yok(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-GH7", ad="Üye Ürünü", fiyat="100.00", stok=3)
    _musteri(db, eposta="uye@ornek.test")
    _giris(istemci, "uye@ornek.test")
    _sepete_ekle(istemci, uid)
    html = istemci.get("/tr/odeme").text
    assert 'data-e2e="odeme-hesap"' not in html and 'name="hesap_eposta"' not in html
    assert _odeme_gonder(istemci).status_code == 303


# =====================================================================================================
# A2 — sepeti teklif olarak gönder (çok kalemli)
# =====================================================================================================

def _sepet_teklif_formu(istemci, kalemler, **ek):
    form = {"kaynak": "sepet", "ad": "QATestUser", "eposta": "qatest@example.com", "telefon": "+90 555 000 00 00",
            "ulke": "TR", "mesaj": "Sepetimdeki ürünler için teklif rica ederim.", "kvkk_onay": "1"}
    form.update(ek)
    form["csrf"] = csrf_al(istemci, "/tr/teklif")
    form["kalem_urun"] = [str(u) for u, _ in kalemler]
    form["kalem_adet"] = [str(a) for _, a in kalemler]
    return istemci.post("/tr/teklif", data=form, follow_redirects=False)


def test_g3g_sepet_teklif_dugmesi_herkese(istemci, db):
    uid = _urun(db, sku="S-GT1", ad="Teklif Sepeti", fiyat="100.00", stok=5)
    _sepete_ekle(istemci, uid)
    dugme = re.compile(r'<a class="dugme ikincil" href="/tr/teklif\?sepet=1" data-e2e="sepet-teklif">'
                       r'Sepeti teklif olarak gönder</a>')
    assert dugme.search(istemci.get("/tr/sepet").text)
    _musteri(db, eposta="tg@ornek.test")
    _giris(istemci, "tg@ornek.test")
    assert dugme.search(istemci.get("/tr/sepet").text)                 # girişli kullanıcıda da


def test_g3g_sepet_teklif_formu_kalem_satirlari(istemci, db):
    a = _urun(db, sku="S-GT2", ad="Birinci Ürün", fiyat="100.00", stok=5, uretici_kodu="ABC-1")
    b = _urun(db, sku="S-GT3", ad="İkinci Ürün", fiyat="50.00", stok=5)
    _sepete_ekle(istemci, a, adet="2")
    _sepete_ekle(istemci, b, adet="1")
    html = sayfa_denetle(istemci.get("/tr/teklif?sepet=1"))
    satirlar = re.findall(r'<tr data-e2e="teklif-kalem">(.*?)</tr>', html, re.S)
    assert len(satirlar) == 2
    assert f'name="kalem_urun" value="{a}"' in satirlar[0] and 'name="kalem_adet"' in satirlar[0]
    assert re.search(r'name="kalem_adet"[^>]*value="2"', satirlar[0]) and "Birinci Ürün" in satirlar[0]
    assert "ABC-1" in satirlar[0] and re.search(r'name="kalem_adet"[^>]*value="1"', satirlar[1])
    assert 'id="adet" name="adet"' not in html                         # tek ürün adet alanı yerine satırlar
    # tek kalemli sepet de satırla gelir
    istemci.cookies.clear()
    _sepete_ekle(istemci, a, adet="3")
    html = istemci.get("/tr/teklif?sepet=1").text
    assert len(re.findall(r'data-e2e="teklif-kalem"', html)) == 1 and re.search(r'name="kalem_adet"[^>]*value="3"', html)


def test_g3g_sepet_teklif_kalemleri_kaydedilir(istemci, db):
    from tests.test_web_teklif_yonetim import _yonetici_giris
    a = _urun(db, sku="S-GT4", ad="Birinci Kalem", fiyat="100.00", stok=5)
    b = _urun(db, sku="S-GT5", ad="İkinci Kalem", fiyat="50.00", stok=5)
    c = _urun(db, sku="S-GT6", ad="Üçüncü Kalem", fiyat="50.00", stok=5)
    r = _sepet_teklif_formu(istemci, [(a, 5), (b, 0), (c, 12)])
    assert r.status_code == 303, r.text
    tk = db.execute("SELECT id, urun_id, adet FROM teklif").fetchone()
    assert tk["urun_id"] is None and tk["adet"] == 17
    kalemler = db.execute("SELECT urun_id, adet FROM teklif_kalem WHERE teklif_id = ? ORDER BY rowid",
                          (tk["id"],)).fetchall()
    assert [tuple(k) for k in kalemler] == [(a, 5), (c, 12)]           # 0 adetli satır gönderilmez
    _yonetici_giris(istemci)
    yonetim = istemci.get("/yonetim/teklifler").text
    assert "Birinci Kalem" in yonetim and "× 5" in yonetim and "Üçüncü Kalem" in yonetim and "× 12" in yonetim


def test_g3g_sepet_teklif_cok_kalem_ve_hata_satirlari_korur(istemci, db):
    # inceleme I-2: 20'den fazla kalem sessizce düşmez (üst sınır 100)
    urunler = [_urun(db, sku=f"S-GK{i}", ad=f"Kalem {i}", fiyat="10.00", stok=5) for i in range(25)]
    r = _sepet_teklif_formu(istemci, [(u, 1) for u in urunler])
    assert r.status_code == 303
    assert _say(db, "SELECT COUNT(*) FROM teklif_kalem") == 25
    # hatalı gönderimde satırlar ve adetleri korunur
    r = _sepet_teklif_formu(istemci, [(urunler[0], 4), (urunler[1], 7)], ad="")
    assert r.status_code == 400
    assert re.search(rf'name="kalem_urun" value="{urunler[0]}"', r.text)
    assert re.search(r'name="kalem_adet"[^>]*value="7"', r.text)
    # geçersiz adet
    r = _sepet_teklif_formu(istemci, [(urunler[0], 99999)])
    assert r.status_code == 400 and 'id="hata-kalemler"' in r.text


def test_g3g_tek_urun_teklif_akisi_aynen(istemci, db):
    uid = _urun(db, sku="S-GT7", ad="Tek Ürün", fiyat="100.00", stok=1)
    html = istemci.get(f"/tr/teklif?urun_id={uid}&adet=4").text
    assert re.search(r'id="adet" name="adet" type="number" value="4"', html) and 'data-e2e="teklif-kalem"' not in html
    r = _post(istemci, "/tr/teklif", {"urun_id": uid, "adet": "4", "ad": "QATestUser", "eposta": "q@example.com",
                                      "ulke": "TR", "mesaj": "Fiyat rica", "kvkk_onay": "1"}, "/tr/teklif")
    assert r.status_code == 303
    assert tuple(db.execute("SELECT urun_id, adet FROM teklif").fetchone()) == (uid, 4)
    assert _say(db, "SELECT COUNT(*) FROM teklif_kalem") == 0


# =====================================================================================================
# A3 — "fazlası için teklif" bağlantısı İSTENEN adetle
# =====================================================================================================

def test_g3g_stok_tavaninda_teklif_istenen_adetle(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-GA3", ad="Tavan Ürünü", fiyat="100.00", stok=1)
    yol = f"/tr/urun/{uid}"
    _post(istemci, "/tr/sepet/ekle", {"urun_id": uid, "adet": "1", "sonraki": yol}, yol)
    istemci.get(yol)                                                    # bildirimi tüket
    r = _post(istemci, "/tr/sepet/ekle", {"urun_id": uid, "adet": "10", "sonraki": yol}, yol)
    bildirim = _bildirimler(istemci.get(r.headers["location"].split("#")[0]).text)
    assert f'href="/tr/teklif?urun_id={uid}&amp;adet=10"' in bildirim and "adet=11" not in bildirim


# =====================================================================================================
# A4 — havale rezervasyonu süreli (SHOP_HAVALE_GUN iş günü), süresi doldu, son tarih
# =====================================================================================================

def _havale_siparisi(con, simdi, stok=1, adet=1, havale_gun=3):
    from app.hesap.servis import KayitGirdisi, kayit_ol
    from tests.conftest import urun_ekle
    uid = urun_ekle(con, sku=f"S-HV{simdi.timestamp():.0f}", stok=stok)
    with con:
        m = kayit_ol(con, KayitGirdisi(tip=MusteriTipi.KURUMSAL, ad="QATest A.Ş.", eposta=f"h{uid}@ornek.test",
                                       parola=PAROLA, ulke="TR", kvkk_onay=True, vergi_kimlik_no=GECERLI_VKN,
                                       vergi_dairesi="Selçuk"), simdi)
        sid = sepet_servis.sepet_bul(con, None, m.id, simdi)
        con.execute("INSERT INTO sepet_kalemi (sepet_id, urun_id, adet) VALUES (?, ?, ?)", (sid, uid, adet))
    from datetime import date
    from app.fiyat.kur import Kur
    kur = Kur(tarih=date(2026, 10, 12), eur_alis=Decimal("34.90"), eur_satis=Decimal("35.00"))
    adres = Adres(ad_soyad="QATest", satir1="Adres 1", sehir="Konya", ulke="TR")
    with con:
        s = siparis_olustur(con, m, sid, TeslimYontemi.KARGO, adres, adres, kur, simdi, "havale",
                            havale_gun=havale_gun)
    return s, uid, m


def test_g3g_havale_son_tarihi_resmi_tatil_atlanir(con):
    # inceleme M-1: sabit tarihli resmî tatiller (29 Ekim) iş günü sayılmaz
    from app.stok import havale_son_tarih
    assert havale_son_tarih(datetime(2026, 10, 27, 9, 0, tzinfo=UTC), 3) == datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
    assert havale_son_tarih(datetime(2026, 12, 30, 9, 0, tzinfo=UTC), 2) == datetime(2027, 1, 4, 9, 0, tzinfo=UTC)


def test_g3g_havale_son_tarihi_is_gunu_ve_suresi_dolar(con):
    simdi = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)                    # Perşembe 12:00 TSİ
    s, uid, _ = _havale_siparisi(con, simdi)
    assert s.odeme_son_tarih == datetime(2026, 10, 20, 9, 0, tzinfo=UTC)   # +3 iş günü: Salı (hafta sonu atlanır)
    assert ayrilan_adetler(con, datetime(2026, 10, 20, 8, 59, tzinfo=UTC)) == {uid: 1}
    sonra = datetime(2026, 10, 20, 9, 1, tzinfo=UTC)
    assert ayrilan_adetler(con, sonra) == {}                            # rezervasyon bırakılır
    with con:
        s2 = siparis_getir(con, s.id, sonra)
    assert s2.durum == SiparisDurumu.SURESI_DOLDU
    # yönetim yeniden açar: yeni son tarih, yeniden ayırır
    with con:
        s3 = durum_degistir(con, s.id, SiparisDurumu.ODEME_BEKLIYOR, sonra, havale_gun=3)
    assert s3.durum == SiparisDurumu.ODEME_BEKLIYOR and s3.odeme_son_tarih == datetime(2026, 10, 23, 9, 1, tzinfo=UTC)
    assert ayrilan_adetler(con, sonra) == {uid: 1}
    # geç gelen ödeme: süresi dolmuş sipariş "ödendi" yapılabilir
    with con:
        s4 = siparis_getir(con, s.id, datetime(2026, 10, 24, tzinfo=UTC))
        assert s4.durum == SiparisDurumu.SURESI_DOLDU
        assert durum_degistir(con, s.id, SiparisDurumu.ODENDI, datetime(2026, 10, 24, tzinfo=UTC)).durum == "odendi"


def test_g3g_havale_gun_ayari(con):
    from app.ayarlar import ayarlari_oku
    taban = {"SHOP_DB": "/tmp/x.db", "SHOP_GIZLI_ANAHTAR": "x" * 32, "SHOP_YONETICI": "y", "SHOP_YONETICI_OZET": "z"}
    assert ayarlari_oku(taban).havale_gun == 3
    assert ayarlari_oku({**taban, "SHOP_HAVALE_GUN": "5"}).havale_gun == 5
    with pytest.raises(RuntimeError):
        ayarlari_oku({**taban, "SHOP_HAVALE_GUN": "0"})
    simdi = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)                    # Salı
    s, _, _ = _havale_siparisi(con, simdi, havale_gun=5)
    assert s.odeme_son_tarih == datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
    # inceleme M-6c: kart siparişinde son tarih yok (30 dk kuralı)
    from app.siparis.servis import siparis_getir as _getir
    with con:
        con.execute("UPDATE siparis SET odeme_yontemi = 'kart', odeme_son_tarih = NULL WHERE id = ?", (s.id,))
    assert _getir(con, s.id, simdi).odeme_son_tarih is None
    s2, _, _ = _havale_siparisi(con, simdi + timedelta(seconds=1))
    assert s2.odeme_yontemi == "havale" and s2.odeme_son_tarih is not None


def test_g3g_gecis_012_eski_havale_son_tarihi(tmp_path, monkeypatch):
    import shutil
    from app import db as db_modulu
    from app.db import baglan, gecisleri_uygula
    eski = tmp_path / "gecisler"
    eski.mkdir()
    for dosya in sorted(db_modulu.GECIS_KLASORU.glob("0[01][0-9]_*.sql")):
        if dosya.name < "012":
            shutil.copy(dosya, eski / dosya.name)
    monkeypatch.setattr(db_modulu, "GECIS_KLASORU", eski)
    c = baglan(tmp_path / "eski.db")
    gecisleri_uygula(c)
    adres = '{"ad_soyad": "A", "satir1": "B", "sehir": "C", "ulke": "TR"}'
    with c:
        c.execute("INSERT INTO musteri (tip, ad, eposta, parola_ozeti, ulke, kvkk_onay, olusturma) "
                  "VALUES ('kurumsal', 'A', 'a@b.test', 'x', 'TR', 'x', 'x')")
        for no, yontem in (("CR-DEMO-20261013-0001", "havale"), ("CR-DEMO-20261013-0002", "kart")):
            c.execute("INSERT INTO siparis (no, musteri_id, durum, para_birimi, ara_toplam, kdv, kargo, toplam, "
                      "ihracat_istisnasi, teslim_yontemi, teslimat_ulkesi, teslimat_adresi, fatura_adresi, sepet_id, "
                      "olusturma, guncelleme, odeme_yontemi) VALUES (?, 1, 'odeme_bekliyor', 'TRY', '1', '0', '0', "
                      "'1', 0, 'kargo', 'TR', ?, ?, 1, '2026-10-13T09:00:00.123456+00:00', 'x', ?)",
                      (no, adres, adres, yontem))
    monkeypatch.undo()
    assert gecisleri_uygula(c) == ["012_teklif_kalem_havale_suresi.sql",
                                   "013_katli_tip.sql", "014_po_aciliyet.sql",
                                   "015_teklif_teslim_adresi.sql", "016_indeksler.sql"]
    son = dict(c.execute("SELECT odeme_yontemi, odeme_son_tarih FROM siparis").fetchall())
    assert son == {"havale": "2026-10-16T09:00:00+00:00", "kart": None}
    assert datetime.fromisoformat(son["havale"]) == datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
    assert c.execute("SELECT COUNT(*) FROM teklif_kalem").fetchone()[0] == 0
    c.close()


def test_g3g_havale_onay_son_tarih_ve_kendi_kalemleri(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-GHV", ad="Havale Ürünü", fiyat="100.00", stok=1)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="hv@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    _giris(istemci, "hv@ornek.test")
    _sepete_ekle(istemci, uid)
    r = _odeme_gonder(istemci, odeme_yontemi="havale")
    assert r.status_code == 303, r.text
    no = r.headers["location"].rsplit("/", 1)[1]
    son = datetime.fromisoformat(_say(db, "SELECT odeme_son_tarih FROM siparis WHERE no = ?", no))
    html = sayfa_denetle(istemci.get(r.headers["location"]))
    proforma = re.search(r'<section class="proforma".*?</section>', html, re.S).group(0)
    assert f"Ödeme son tarihi: {_tr(son)}" in proforma
    assert f"Ödeme son tarihi: {_tr(son)}" in html.replace(proforma, "")   # onay sayfasında proforma dışında da
    kalemler = re.search(r'<table class="tablo sepet-tablo siparis-kalemleri">.*?</table>', html, re.S).group(0)
    # kendi rezervasyonu düşülür; G3m madde 2-3: "Sizin için ayrıldı" + ödeme sonrası iş günü (tarih aralığı yok)
    assert "alınabilir stok yok" not in kalemler and "Sizin için ayrıldı" in kalemler
    # başka ziyaretçi için ürün tümü ayrılmış
    istemci.cookies.clear()
    assert "Şu an alınabilir stok yok" in istemci.get(f"/tr/urun/{uid}").text


def test_g3g_havale_suresi_dolan_siparis_sayfasi(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-GHD", ad="Süresi Dolan", fiyat="100.00", stok=1)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="hd@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    _giris(istemci, "hd@ornek.test")
    _sepete_ekle(istemci, uid)
    r = _odeme_gonder(istemci, odeme_yontemi="havale")
    with db:
        db.execute("UPDATE siparis SET odeme_son_tarih = ?", ((datetime.now(UTC) - timedelta(hours=1)).isoformat(),))
    html = istemci.get(r.headers["location"]).text
    assert 'data-durum="suresi_doldu"' in html and "Süresi doldu" in html and 'data-e2e="proforma"' not in html
    assert "Stokta: 1 adet" in istemci.get(f"/tr/urun/{uid}").text      # rezervasyon bırakıldı


# =====================================================================================================
# A5 — "tümü ayrılmış" metni: en erken bitecek rezervasyonun zamanı
# =====================================================================================================

def test_g3g_tumu_ayrilmis_metni_kart_havale_odenmis(istemci, db):
    from app.siparis.odeme_sim import odeme_baslat, sms_dogrula  # noqa: F401
    _kur(db)
    uid = _urun(db, sku="S-GTA", ad="Ayrılmış Ürün", fiyat="100.00", stok=1)
    _musteri(db, eposta="ta@ornek.test")
    _giris(istemci, "ta@ornek.test")
    _sepete_ekle(istemci, uid)
    r = _odeme_gonder(istemci)                                          # kart: 30 dk ayırır
    olusturma = datetime.fromisoformat(_say(db, "SELECT olusturma FROM siparis"))
    istemci.cookies.clear()
    html = istemci.get(f"/tr/urun/{uid}").text
    beklenen = (f"Şu an alınabilir stok yok · en geç {_tr(olusturma + timedelta(minutes=30))} "
                "(TSİ) serbest kalabilir · teklif isteyin")              # G3j madde 14: saat dilimi
    assert beklenen in html
    assert beklenen in istemci.get("/tr/urunler").text                  # listede de aynı metin
    # ödenmiş sipariş: bir sonraki tam eşitleme (02:30 TSİ)
    with db:
        db.execute("UPDATE siparis SET durum = 'odendi', odeme_zamani = ?", (datetime.now(UTC).isoformat(),))
    simdi_tr = datetime.now(UTC) + TR_SAAT
    esitleme = simdi_tr.replace(hour=2, minute=30, second=0, microsecond=0)
    if esitleme <= simdi_tr:
        esitleme += timedelta(days=1)
    assert (f"en geç {esitleme.strftime('%d.%m.%Y %H:%M')} (TSİ) serbest kalabilir"
            in istemci.get(f"/tr/urun/{uid}").text)
    assert r.status_code == 303


def test_g3g_tumu_ayrilmis_en_metni(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-GTE", ad="Reserved Item", fiyat="100.00", stok=1)
    _musteri(db, eposta="te@ornek.test")
    _giris(istemci, "te@ornek.test")
    _sepete_ekle(istemci, uid)
    _odeme_gonder(istemci)
    istemci.cookies.clear()
    html = istemci.get(f"/en/urun/{uid}").text
    assert "No stock available right now · may be released by " in html and "request a quote" in html


# =====================================================================================================
# A6 — görünür onay: bildirim kullanıcının indiği çapada (ürün kartı / satın alma kutusu içinde)
# =====================================================================================================

def _yerel(html, uid):
    m = re.search(rf'id="urun-{uid}".*?(<[^>]*class="yerel-bildirim"[^>]*role="status".*?</p>)', html, re.S)
    return m.group(1) if m else ""


def test_g3g_sepete_ekle_onayi_capada(istemci, katalog, db):
    _kur(db)
    uid = katalog["role"]
    for sonraki in ("/tr/urunler", f"/tr/urun/{uid}", f"/tr/kategori/{katalog['elk']}"):
        r = _post(istemci, "/tr/sepet/ekle", {"urun_id": uid, "adet": "1", "sonraki": sonraki}, sonraki)
        assert r.headers["location"].endswith(f"#urun-{uid}")
        html = sayfa_denetle(istemci.get(r.headers["location"].split("#")[0]))
        yerel = _yerel(html, uid)
        assert "Sepete eklendi" in yerel and 'href="/tr/sepet"' in yerel, sonraki
        assert "Sepete eklendi" in _bildirimler(html)                    # üstteki genel bildirim de kalır
        assert _yerel(istemci.get(sonraki).text, uid) == ""             # bir kez gösterilir


def test_g3g_karsilastir_onayi_capada(istemci, katalog, db):
    uid = katalog["role"]
    r = _post(istemci, "/tr/karsilastir/ekle", {"urun_id": uid, "sonraki": "/tr/urunler"}, "/tr/urunler")
    html = istemci.get(r.headers["location"].split("#")[0]).text
    assert "Karşılaştırmaya eklendi" in _yerel(html, uid)


# =====================================================================================================
# A7 — kurumsal fiyat tutarlılığı (ana para birimi ve KDV bazı her yerde aynı)
# =====================================================================================================

def _ana_paralar(html, e2e):
    return re.findall(rf'data-e2e="{e2e}" data-para="([A-Z]+)" data-kdv="(dahil|haric)"', html)


def test_g3g_kurumsal_sepet_odeme_onay_ana_para_eur(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-GK7", ad="Kurumsal Ürün", fiyat="28.00", stok=5)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="k7@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    _giris(istemci, "k7@ornek.test")
    _sepete_ekle(istemci, uid, adet="2")
    sepet = sayfa_denetle(istemci.get("/tr/sepet"))
    assert _ana_paralar(sepet, "fiyat-ana") == [("EUR", "haric")]
    assert _ana_paralar(sepet, "kalem-tutar") == [("EUR", "haric")]
    satir = re.search(r'<tr data-e2e="sepet-kalemi">.*?</tr>', sepet, re.S).group(0)
    assert "56,00 €" in satir and "1.960,00 ₺" in satir               # tutar € ana, ₺ ikincil
    odeme = istemci.get("/tr/odeme").text
    assert _ana_paralar(odeme, "kalem-tutar") == [("EUR", "haric")]
    assert "56,00 €" in re.search(r'<ul class="ozet-kalemleri">.*?</ul>', odeme, re.S).group(0)
    r = _odeme_gonder(istemci)
    no = _siparis_no(r.headers["location"])
    onay = istemci.get(f"/tr/siparis/{no}").text
    assert _ana_paralar(onay, "kalem-tutar") == [("EUR", "haric")]
    assert "56,00 €" in re.search(r'<table class="tablo sepet-tablo siparis-kalemleri">.*?</table>', onay, re.S).group(0)


def test_g3g_bireysel_her_yerde_try_kdv_dahil(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-GB7", ad="Bireysel Ürün", fiyat="28.00", stok=5)
    _musteri(db, eposta="b7@ornek.test")
    _giris(istemci, "b7@ornek.test")
    _sepete_ekle(istemci, uid, adet="2")
    sepet = istemci.get("/tr/sepet").text
    assert _ana_paralar(sepet, "fiyat-ana") == [("TRY", "dahil")]
    assert _ana_paralar(sepet, "kalem-tutar") == [("TRY", "dahil")]
    assert _ana_paralar(istemci.get("/tr/odeme").text, "kalem-tutar") == [("TRY", "dahil")]


# =====================================================================================================
# A8 — ödeme düğmesi nötr + seçili yönteme göre açıklama
# =====================================================================================================

def test_g3g_odeme_dugmesi_notr_ve_yontem_aciklamasi(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-GD8", ad="Düğme Ürünü", fiyat="100.00", stok=5)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="d8@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    _giris(istemci, "d8@ornek.test")
    _sepete_ekle(istemci, uid)
    html = istemci.get("/tr/odeme").text
    dugme = re.search(r'<button type="submit" name="islem" value="odeme"[^>]*data-e2e="odeme-gonder">(.*?)</button>',
                      html, re.S).group(1)
    assert "Siparişi oluştur" in dugme and "karta" not in dugme
    assert 'class="odeme-aciklama odeme-aciklama-kart"' in html and 'class="odeme-aciklama odeme-aciklama-havale"' in html
    from pathlib import Path
    css = (Path(__file__).resolve().parent.parent / "app/web/statik/site.css").read_text(encoding="utf-8")
    assert ".odeme-formu:has(#odeme-havale:checked) .odeme-aciklama-kart" in css
    assert ".odeme-formu:has(#odeme-kart:checked) .odeme-aciklama-havale" in css


# =====================================================================================================
# A9 — ters fiyat aralığı uyarısı
# =====================================================================================================

def test_g3g_fiyat_araligi_ters_uyari(istemci, katalog):
    html = sayfa_denetle(istemci.get(f"/tr/kategori/{katalog['elk']}?fmin=5000&fmax=1000"))
    kutu = re.search(r'<p class="bilgi-kutu fiyat-ters" role="status">(.*?)</p>', html, re.S)
    assert kutu and unescape(kutu.group(1)) == "En az > en çok: değerler yer değiştirildi"
    html = istemci.get(f"/en/kategori/{katalog['elk']}?fmin=5000&fmax=1000").text
    assert "Min &gt; max: the values were swapped" in html


# =====================================================================================================
# A10 — faset sayıları diğer seçili fasetlerle; kategori ağacı filtre etkinken sayı göstermez
# =====================================================================================================

def test_g3g_faset_sayisi_diger_fasetler_uygulanmis(con):
    from tests.conftest import urun_ekle
    with con:
        for i, (ad, durum) in enumerate([("KUKA A", "ikinci_el"), ("KUKA B", "ikinci_el"), ("ABB C", "yeni"),
                                         ("ABB D", "yeni"), ("KUKA E", "belirtilmemis"), ("SIEMENS F", "yeni")]):
            k = urun_ekle(con, sku=f"F{i}", ad=f"{ad} PARÇA")
            con.execute("UPDATE urun SET durum_kodu = ? WHERE id = ?", (durum, k))
    f = faset_sayilari(con, ListeSorgusu(markalar=("KUKA",)), [])
    sayilar = {x.deger: x.sayi for x in f.durum}
    assert sayilar.get("yeni", 0) == 0 and sayilar["ikinci_el"] == 2     # KUKA ∩ Yeni = 0
    f = faset_sayilari(con, ListeSorgusu(markalar=("KUKA",), durumlar=("ikinci_el",)), [])
    assert {x.deger: x.sayi for x in f.marka} == {"KUKA": 2}             # 2. el seçiliyken ABB/SIEMENS (yalnız yeni) yok
    assert urun_listele(con, ListeSorgusu(markalar=("KUKA",), durumlar=("yeni",))).toplam == 0


def test_g3g_kategori_agaci_filtre_etkinken_sayisiz(istemci, katalog):
    # G3h madde 4: filtre etkinken ağaç artık süzülmüş sayıları gösterir (0 olan kategori gizli); bağlantı filtreyi taşır
    filtresiz = istemci.get("/tr/urunler").text
    agac = re.search(r'<details class="agac-kutu".*?</details>', filtresiz, re.S).group(0)
    assert re.search(r'<span class="sayi">\(\d+\)</span>', agac)
    for yol, elk in (("/tr/urunler?stokta=1", 1), ("/tr/urunler?marka=KUKA", 0), ("/tr/urunler?fmin=1", 2)):
        html = istemci.get(yol).text
        agac = re.search(r'<details class="agac-kutu".*?</details>', html, re.S).group(0)
        if elk:
            assert f'Elektrik ve Elektronik <span class="sayi">({elk})</span>' in agac, yol
            assert f'href="/tr/kategori/{katalog["elk"]}?{yol.split("?")[1]}"' in agac, yol
        else:
            assert "Elektrik ve Elektronik" not in agac, yol


# =====================================================================================================
# B11 — karşılaştırma /en: EN ad ve geçerli EN teknik çeviri; çevrilmemiş satır lang="tr" + tablo altı not
# B12 — ürün sayfası teknik not tutarlılığı; kaynak açıklama satırları lang="tr" + "(original Turkish note)"
# =====================================================================================================

def _ceviri_verisi(con, bolumler=()):
    import json
    from app.katalog.indeks import indeksi_yeniden_kur
    from app.katalog.urun_ceviri import kaynak_ozeti
    from tests.conftest import kategori_ekle, urun_ekle
    ad, ad_en = "KUKA 00-109-802 KRC2 GÜÇ KAYNAĞI 27V-NT", "KUKA 00-109-802 KRC2 Power Supply 27V-NT"
    teknik = [["Giriş Voltajı (Input)", "0,72 kV"], ["Ağırlık", "3,5 kg"]]
    teknik_en = [["Input Voltage (Input)", "0.72 kV"], ["Weight", "3.5 kg"]]
    k = kategori_ekle(con, kaynak_id="k1", ad="GÜÇ SİSTEMLERİ", yol="1", seviye=0)
    a = urun_ekle(con, sku="A1", ad=ad, kategori_id=k, fiyat="100.00")
    b = urun_ekle(con, sku="B2", ad="SİEMENS RÖLE MODÜLÜ 24V", kategori_id=k, fiyat="50.00")
    con.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)",
                (a, json.dumps({"ozellikler": teknik, "bolumler": [list(x) for x in bolumler]}, ensure_ascii=False)))
    con.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)",
                (b, json.dumps({"ozellikler": [["Bobin Gerilimi", "24 V"]], "bolumler": []}, ensure_ascii=False)))
    con.execute("INSERT INTO urun_ceviri VALUES (?, 'en', ?, ?, 'llm-taslak', 'claude-haiku-5-5', ?, 't')",
                (a, ad_en, json.dumps(teknik_en), kaynak_ozeti(ad, teknik)))
    indeksi_yeniden_kur(con)
    return a, b, ad_en


def test_g3g_karsilastirma_en_ceviri_ve_tr_satirlar(istemci):
    with istemci_db(istemci) as con:
        a, b, ad_en = _ceviri_verisi(con)
    for u in (a, b):
        _post(istemci, "/en/karsilastir/ekle", {"urun_id": u, "sonraki": "/en/karsilastir"}, "/en/karsilastir")
    html = sayfa_denetle(istemci.get("/en/karsilastir"))
    tablo = re.search(r'<table class="karsilastir-tablo".*?</table>', html, re.S).group(0)
    assert ad_en in tablo
    weight = re.search(r'<tr[^>]*>\s*<th scope="row">Weight</th>.*?</tr>', tablo, re.S).group(0)
    assert 'lang="tr"' not in weight and "3.5 kg" in weight
    bobin = re.search(r'<tr[^>]*>\s*<th scope="row">Bobin Gerilimi</th>', tablo, re.S).group(0)
    assert 'lang="tr"' in bobin                                         # çevrilmemiş satır işaretli
    assert "Ağırlık" not in tablo                                       # çevrilmiş ürünün TR satırı yok
    assert 'data-e2e="karsilastir-tr-notu"' in html and "Machine-translated from Turkish" in html
    tr = istemci.get("/tr/karsilastir").text
    assert "Ağırlık" in tr and 'data-e2e="karsilastir-tr-notu"' not in tr and "Weight" not in tr


def test_g3g_urun_sayfasi_teknik_not_tutarliligi(istemci):
    with istemci_db(istemci) as con:
        a, b, _ = _ceviri_verisi(con, bolumler=[["", "*Görseldeki ürün ikinci eldir."]])
    html = sayfa_denetle(istemci.get(f"/en/urun/{a}"))
    assert "Technical data is shown as supplied (in Turkish)." not in html     # geçerli çeviri varken
    assert "Machine-translated from Turkish" in html
    # G3k madde 20: çevrilmemiş kaynak not kapalı <details> içinde, lang="tr" (önce "(original Turkish note)" etiketi)
    bolum = re.search(r'<details class="kaynak-not".*?</details>', html, re.S).group(0)
    assert '<div lang="tr">' in bolum and "*Görseldeki ürün ikinci eldir." in bolum
    assert "Original supplier note (Turkish, not translated)" in bolum
    # çevirisi olmayan üründe tek not: tablonun üstünde başlık (G3l madde 19; önce tablonun altında "(in Turkish)")
    assert "Technical data — original Turkish (not translated)" in istemci.get(f"/en/urun/{b}").text
    assert "(original Turkish note)" not in istemci.get(f"/tr/urun/{a}").text


# =====================================================================================================
# B13 — navlun ve ithalat metni (yurt dışı DAP): sepet, ödeme, kart, proforma
# B17 — havale bilgisi: SWIFT/BIC ve EUR IBAN "(temsili)", alıcı künyeden
# =====================================================================================================

NAVLUN_EN = ("Freight is not included. We e-mail a DAP freight quote to your delivery address within 1 business day "
             "(indicative); it is invoiced separately.")
ITHALAT_EN = ("Import VAT and duties are paid by the buyer at customs in the destination country; deductibility "
              "depends on your local rules.")
NAVLUN_TR = ("Navlun dahil değildir. Teslimat adresinize göre DAP navlun teklifini 1 iş günü içinde e-postayla "
             "iletiriz (temsili); ayrıca faturalandırılır.")
ITHALAT_TR = ("İthalat KDV'si ve gümrük vergileri varış ülkesinde gümrükte alıcı tarafından ödenir; indirilebilirliği "
              "yerel mevzuatınıza bağlıdır.")


def test_g3g_navlun_ithalat_metni_yurtdisi(istemci, db):
    uid = _urun(db, sku="S-GN1", ad="Export Item", fiyat="100.00", stok=5)
    _musteri(db, tip=MusteriTipi.YURTDISI, eposta="de@ornek.test", ulke="DE", vat_id="DE123456789")
    _giris(istemci, "de@ornek.test", dil="en")
    _sepete_ekle(istemci, uid, dil="en")
    for yol in ("/en/sepet", "/en/odeme"):
        html = unescape(istemci.get(yol).text)
        assert NAVLUN_EN in html and ITHALAT_EN in html, yol
    r = _odeme_gonder(istemci, dil="en", ulke="DE", teslim="yurtdisi_dap")
    kart = unescape(istemci.get(r.headers["location"]).text)
    assert NAVLUN_EN in kart and ITHALAT_EN in kart
    html = unescape(istemci.get("/tr/sepet").text)                       # TR karşılıkları
    assert NAVLUN_TR in html and ITHALAT_TR in html


def test_g3g_proforma_navlun_swift_eur_iban(istemci, db):
    uid = _urun(db, sku="S-GN2", ad="Export Item 2", fiyat="100.00", stok=5)
    _musteri(db, tip=MusteriTipi.YURTDISI, eposta="de2@ornek.test", ulke="DE", vat_id="DE123456789")
    _giris(istemci, "de2@ornek.test", dil="en")
    _sepete_ekle(istemci, uid, dil="en")
    r = _odeme_gonder(istemci, dil="en", ulke="DE", teslim="yurtdisi_dap", odeme_yontemi="havale")
    assert r.status_code == 303
    html = istemci.get(r.headers["location"]).text
    proforma = unescape(re.search(r'<section class="proforma".*?</section>', html, re.S).group(0))
    assert re.search(r"<dt>Freight</dt><dd>on quotation</dd>", proforma)
    assert re.search(r"<dt>SWIFT/BIC</dt><dd[^>]*>[^<]*\(indicative\)</dd>", proforma)
    assert re.search(r"<dt>IBAN \(EUR\)</dt><dd[^>]*>[^<]*\(indicative\)</dd>", proforma)
    assert "MUSTAFA CEYLAN ENDÜSTRİ A.Ş." in proforma
    # G3m madde 24: navlun / ithalat KDV notları sayfada bir kez (sipariş özetinde), proforma bölümünde tekrar yok
    assert NAVLUN_EN not in proforma and ITHALAT_EN not in proforma
    assert unescape(html).count(NAVLUN_EN) == 1 and unescape(html).count(ITHALAT_EN) == 1
    tr = unescape(istemci.get(r.headers["location"].replace("/en/", "/tr/")).text)
    proforma = re.search(r'<section class="proforma".*?</section>', tr, re.S).group(0)
    assert re.search(r"<dt>Navlun</dt><dd>teklifle</dd>", proforma)
    assert re.search(r"<dt>SWIFT/BIC</dt><dd[^>]*>[^<]*\(temsili\)</dd>", proforma)
    assert re.search(r"<dt>IBAN \(EUR\)</dt><dd[^>]*>[^<]*\(temsili\)</dd>", proforma)


# =====================================================================================================
# B14 — garanti: "2. el (genel)" tanımı; ürün sayfasında duruma göre tek satır garanti özeti
# =====================================================================================================

def test_g3g_garanti_sayfasi_ikinci_el_genel(istemci):
    tr = sayfa_denetle(istemci.get("/tr/yasal/garanti"))
    tanim = re.search(r'<dt id="durum-ikinci_el">.*?</dd>', tr, re.S).group(0)
    assert "2. el (genel)" in tanim and "fotoğraf/test raporu" in tanim
    assert "garanti süresi teklif ve faturada belirtilir" in tanim and "temsili" in tanim
    en = istemci.get("/en/yasal/garanti").text
    assert re.search(r'<dt id="durum-ikinci_el"><strong>Used \(general\)</strong>', en)
    for kod in ("yeni", "ikinci_el_test_edildi", "ikinci_el_oldugu_gibi", "belirtilmemis"):
        assert f'id="durum-{kod}"' in tr and f'id="durum-{kod}"' in en, kod


@pytest.mark.parametrize("kod,metin", [
    ("ikinci_el", "Garanti: süre teklif ve faturada belirtilir (temsili)"),
    ("yeni", "Garanti: üretici garantisi"),
    ("ikinci_el_oldugu_gibi", "Garanti: olduğu gibi satılır"),
    ("belirtilmemis", "Garanti: durum teyidiyle birlikte bildirilir"),
])
def test_g3g_urun_sayfasi_garanti_ozeti(istemci, db, kod, metin):
    uid = _urun(db, sku=f"S-GG-{kod}", ad="Garanti Ürünü", fiyat="100.00", stok=1)
    with db:
        db.execute("UPDATE urun SET durum_kodu = ? WHERE id = ?", (kod, uid))
    html = sayfa_denetle(istemci.get(f"/tr/urun/{uid}"))
    ozet = re.search(r'<p class="garanti-ozeti" data-e2e="garanti-ozeti">.*?</p>', html, re.S).group(0)
    assert metin in ozet and f'href="/tr/yasal/garanti#durum-{kod}"' in ozet
    # durum satırının hemen ardından (ilk ekranda)
    assert html.index('class="urun-durum"') < html.index('data-e2e="garanti-ozeti"') < html.index('class="fiyat-blok')


# =====================================================================================================
# B15 — yabancı kurumsal formlar: VKN/vergi dairesi yalnız TR; İYS yalnız TR; EN etiket
# =====================================================================================================

def test_g3g_teklif_formu_vkn_yalniz_turkiye(istemci, db):
    html = sayfa_denetle(istemci.get("/en/teklif"))
    # G3i madde 15: blok bir başlık (legend) altında fieldset
    blok = re.search(r'<fieldset class="yalniz-tr" data-e2e="teklif-tr-vergi">.*?</fieldset>', html, re.S).group(0)
    assert 'name="vkn"' in blok and 'name="vergi_dairesi"' in blok and "(Türkiye only)" in blok
    assert "required" not in blok
    assert "(yalnız Türkiye)" in istemci.get("/tr/teklif").text
    from pathlib import Path
    css = (Path(__file__).resolve().parent.parent / "app/web/statik/site.css").read_text(encoding="utf-8")
    assert '.teklif-formu:not(:has(select[name="ulke"] option[value="TR"]:checked)) .yalniz-tr' in css
    # yurt dışında VKN değerlendirilmez (geçersiz değer hata vermez, kaydedilmez)
    r = _post(istemci, "/en/teklif", {"ad": "QATest GmbH", "eposta": "q@example.com", "ulke": "DE", "adet": "1",
                                      "mesaj": "Quote please", "kvkk_onay": "1", "vkn": "123",
                                      "vergi_dairesi": "X"}, "/en/teklif")
    assert r.status_code == 303
    assert tuple(db.execute("SELECT vkn, vergi_dairesi FROM teklif").fetchone()) == (None, None)
    r = _post(istemci, "/tr/teklif", {"ad": "QATest", "eposta": "q@example.com", "ulke": "TR", "adet": "1",
                                      "mesaj": "Teklif", "kvkk_onay": "1", "vkn": "123"}, "/tr/teklif")
    assert r.status_code == 400 and 'id="hata-vkn"' in r.text                 # TR'de doğrulama aynen


def test_g3g_kayit_formu_iys_yalniz_tr_ve_en_etiket(istemci):
    # inceleme M-4 / kısmi 15: İYS ülkeye (Türkiye = bireysel tip) bağlı, arayüz diline değil
    tr = sayfa_denetle(istemci.get("/tr/kayit"))
    assert re.search(r'<div class="alan" data-tipler="bireysel">\s*<label class="secim"><input[^>]*name="iys_onay"', tr)
    en = sayfa_denetle(istemci.get("/en/kayit"))
    assert re.search(r'<div class="alan" data-tipler="bireysel">\s*<label class="secim"><input[^>]*name="iys_onay"', en)
    assert not re.search(r'data-tipler="(kurumsal|yurtdisi)"[^>]*>[^<]*<label[^>]*><input[^>]*iys_onay', en)
    assert "Company outside Türkiye (EU: VAT ID required)" in unescape(en)
    assert "Türkiye dışındaki firma (AB: VAT ID zorunlu)" in unescape(tr)


# =====================================================================================================
# B16 — EN yol takma adları (301, sorgu korunur)
# =====================================================================================================

@pytest.mark.parametrize("takma,hedef", [
    ("/en/search?q=abb", "/en/ara?q=abb"),
    ("/en/products?marka=KUKA&marka=ABB&sayfa=2", "/en/urunler?marka=KUKA&marka=ABB&sayfa=2"),
    ("/en/cart", "/en/sepet"),
    ("/en/checkout", "/en/odeme"),
    ("/en/compare?fark=1", "/en/karsilastir?fark=1"),
    ("/en/quote?urun_id=5&adet=3", "/en/teklif?urun_id=5&adet=3"),
])
def test_g3g_en_yol_takma_adlari(istemci, takma, hedef):
    r = istemci.get(takma, follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == hedef


def test_g3g_takma_adlar_yalniz_en_ve_eski_yollar_aynen(istemci, katalog):
    assert istemci.get("/tr/search?q=abb", follow_redirects=False).status_code == 404
    assert istemci.get("/en/ara?q=RÖLE").status_code == 200
    assert istemci.get("/en/urunler").status_code == 200


# =====================================================================================================
# C18–C21 — mobil ve yerleşim (ölçümler Playwright ile rapora; burada işaretleme ve CSS kuralları sabitlenir)
# =====================================================================================================

def _css():
    from pathlib import Path
    return (Path(__file__).resolve().parent.parent / "app/web/statik/site.css").read_text(encoding="utf-8")


def _medya_blogu(css, isaret):
    """CSS'te `isaret` yorumunu içeren @media bloğunun gövdesi."""
    i = css.index(isaret)
    bas = css.index("@media", i)
    derinlik, j = 0, css.index("{", bas)
    while True:
        if css[j] == "{":
            derinlik += 1
        elif css[j] == "}":
            derinlik -= 1
            if derinlik == 0:
                return css[bas:j + 1]
        j += 1


def test_g3g_karsilastirma_360_iki_sutun_kurallari(istemci, katalog, db):
    from tests.conftest import urun_ekle
    with db:
        ek = urun_ekle(db, sku="S-K3", ad="ÜÇÜNCÜ ÜRÜN", fiyat="10.00", kategori_id=katalog["kontrol"])
    for u in (katalog["role"], katalog["stoksuz"]):
        _post(istemci, "/tr/karsilastir/ekle", {"urun_id": u, "sonraki": "/tr/karsilastir"}, "/tr/karsilastir")
    html = sayfa_denetle(istemci.get("/tr/karsilastir"))
    assert 'class="karsilastir-kaydir"' not in html                        # iki ürün yan yana sığar: ipucu yok
    _post(istemci, "/tr/karsilastir/ekle", {"urun_id": ek, "sonraki": "/tr/karsilastir"}, "/tr/karsilastir")
    html = istemci.get("/tr/karsilastir").text
    assert 'class="karsilastir-kaydir"' in html                            # 3. ürün kaydırmayla
    blok = _medya_blogu(_css(), "G3g madde 18")
    assert "max-width: 767px" in blok
    for kural in (".karsilastir-urun img { width: 64px;", "font-size: var(--fs-13)", "min-width: 0;",
                  ".karsilastir-tablo th[scope=\"row\"], .karsilastir-kose { width: 5.5rem;"):
        assert kural in blok, kural


def test_g3g_liste_1366_tablo_tasmaz_kurallari(istemci, katalog):
    blok = _medya_blogu(_css(), "G3g madde 19")
    assert "min-width: 1024px" in blok
    assert ".ut-durum, .ut-stok { white-space: normal;" in blok
    html = istemci.get("/tr/urunler").text
    assert 'class="urun-tablo"' in html


def test_g3g_geri_bildirim_dugmesi_odeme_akisinda_yok_altbilgide_akista(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-GB20", ad="Geri Bildirim Ürünü", fiyat="100.00", stok=5)
    for yol in ("/tr/", f"/tr/urun/{uid}", "/tr/urunler", "/tr/teklif"):
        html = istemci.get(yol).text
        alt = re.search(r'<footer class="alt">.*?</footer>', html, re.S).group(0)
        assert 'id="gb-dugme"' in alt and 'id="gb-pencere"' in html, yol         # alt bilgide, akışta
    _musteri(db, eposta="gb@ornek.test")
    _giris(istemci, "gb@ornek.test")
    _sepete_ekle(istemci, uid)
    r = _odeme_gonder(istemci)
    for yol in ("/tr/sepet", "/tr/odeme", r.headers["location"]):
        html = istemci.get(yol).text
        assert 'id="gb-dugme"' not in html and 'id="gb-pencere"' not in html, yol
    blok = _css()
    assert "#gb-dugme { position: static;" in blok


def test_g3g_urun_sayfasi_mobil_kucuk_gorsel(istemci, katalog):
    html = sayfa_denetle(istemci.get(f"/tr/urun/{katalog['role']}"))
    baslik = re.search(r'<div class="urun-baslik">(.*?)</div>', html, re.S).group(1)
    assert re.search(r'<img class="urun-kucuk-gorsel" src="[^"]+"[^>]*width="96"', baslik)
    assert baslik.index("urun-kucuk-gorsel") < baslik.index("<h1>")
    blok = _medya_blogu(_css(), "G3g madde 21")
    assert "max-width: 767px" in blok and ".urun-kucuk-gorsel { display: block; width: 96px;" in blok
    assert ".urun-kucuk-gorsel { display: none; }" in _css()


# =====================================================================================================
# C22 — arama: kod öneki eşleşmesi rozeti + "tam kod" ipucu
# =====================================================================================================

def test_g3g_arama_kod_oneki_rozeti(istemci, db):
    uid = _urun(db, sku="8503053800777", ad="SIEMENS S7-300 PS307 GÜÇ KAYNAĞI", fiyat="28.00", stok=2,
                uretici_kodu="6ES7307-1EA00-0AA0")
    html = sayfa_denetle(istemci.get("/tr/ara", params={"q": "6ES7 307-1EA00"}))
    satir = re.search(rf'<tr class="ut-satir[^"]*" id="urun-{uid}">.*?</tr>', html, re.S).group(0)
    # G3k madde 7: rozet metni "Parça no ile eşleşti" (önce "Kod öneki eşleşmesi")
    assert '<span class="rozet rozet-onek" data-e2e="onek-eslesme">Parça no ile eşleşti</span>' in satir
    # G3h madde 15: parça no satırda zaten tam kodu gösteriyor: "tam kod" ipucu tekrarlanmaz
    assert "tam kod:" not in satir and satir.count("6ES7307-1EA00-0AA0") == 1
    assert 'data-e2e="tam-eslesme"' not in satir
    tam = istemci.get("/tr/ara", params={"q": "6es7307-1ea00-0aa0"}).text
    assert 'data-e2e="tam-eslesme"' in tam and 'data-e2e="onek-eslesme"' not in tam
    assert 'data-e2e="onek-eslesme"' not in istemci.get("/tr/ara", params={"q": "siemens"}).text
    en = istemci.get("/en/ara", params={"q": "6ES7 307-1EA00"}).text
    assert "Matched by part no." in en and "full code:" not in en


# =====================================================================================================
# D23 — ödeme adım göstergesi adları sayfa başlıklarıyla aynı (Sepet · Bilgiler · Ödeme · Onay)
# =====================================================================================================

def _adim(html):
    adimlar = re.findall(r'<span class="adim-ad">(.*?)</span>', html)
    gecerli = re.search(r'aria-current="step">.*?<span class="adim-ad">(.*?)</span>', html, re.S).group(1)
    h1 = re.sub(r"<[^>]+>", "", re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S).group(1)).strip()
    return adimlar, gecerli, h1


def test_g3g_adim_adlari_sayfa_basliklari(istemci, db):
    from tests.test_web_sepet_odeme import _kart_ode, _sms
    _kur(db)
    uid = _urun(db, sku="S-AD23", ad="Adım Ürünü", fiyat="100.00", stok=5)
    _sepete_ekle(istemci, uid)
    beklenen = ["Sepet", "Bilgiler", "Ödeme", "Onay"]
    for yol, ad in (("/tr/sepet", "Sepet"), ("/tr/odeme", "Bilgiler")):           # misafir
        adimlar, gecerli, h1 = _adim(istemci.get(yol).text)
        assert adimlar == beklenen and gecerli == ad and h1.startswith(ad), (yol, adimlar, gecerli, h1)
    _musteri(db, eposta="ad@ornek.test")
    _giris(istemci, "ad@ornek.test")
    adimlar, gecerli, h1 = _adim(istemci.get("/tr/odeme").text)
    assert gecerli == "Bilgiler" and h1 == "Bilgiler"
    r = _odeme_gonder(istemci)
    no = _siparis_no(r.headers["location"])
    adimlar, gecerli, h1 = _adim(istemci.get(r.headers["location"]).text)
    assert gecerli == "Ödeme" and h1.startswith("Ödeme")
    r, _ = _kart_ode(istemci, no, "4111 1111 1111 1111")
    adimlar, gecerli, h1 = _adim(istemci.get(r.headers["location"]).text)       # 3D Secure
    assert gecerli == "Ödeme" and h1.startswith("Ödeme")
    r, _ = _sms(istemci, no, r.headers["location"])
    adimlar, gecerli, h1 = _adim(istemci.get(r.headers["location"]).text)
    assert gecerli == "Onay" and h1.startswith("Onay") and no in h1
    en = istemci.get("/en/sepet").text
    assert re.findall(r'<span class="adim-ad">(.*?)</span>', en) == ["Cart", "Details", "Payment", "Confirmation"]


# =====================================================================================================
# D24 — teklif sayfası giriş cümlesi; D25 — ödeme formunda zorunlu adres alanlarında HTML required
# =====================================================================================================

def test_g3g_teklif_giris_cumlesi_ve_hizli_talep(istemci):
    html = sayfa_denetle(istemci.get("/tr/teklif"))
    giris = re.search(r'<p class="teklif-giris">(.*?)</p>', html, re.S).group(1)
    assert unescape(re.sub(r"<[^>]+>", "", giris)) == (
        "Robotlar ve teklifle satılan ürünler, toplu alım, teslim yeri/tarihi ya da bulamadığınız bir parça için bu "
        "formu kullanın. Acil durumda: Hızlı talep (telefonla dönüş).")
    assert 'href="#hizli-talep"' in giris
    form = html.index('<form method="post" action="/tr/teklif"')
    hizli = html.index('id="hizli-talep"')
    assert hizli > form                                      # ana formun alan adları önce gelir (e2e/erişilebilirlik)
    assert re.search(r'id="hizli-talep".*?<form class="hizli-teklif" method="post" action="/tr/teklif/hizli"', html, re.S)
    en = istemci.get("/en/teklif").text
    assert "Urgent:" in en and 'href="#hizli-talep"' in en


def test_g3g_odeme_zorunlu_adres_required(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-RQ25", ad="Zorunlu Ürün", fiyat="100.00", stok=5)
    _sepete_ekle(istemci, uid)
    html = istemci.get("/tr/odeme").text
    form = re.search(r'<form method="post" action="/tr/odeme"[^>]*>', html).group(0)
    assert "novalidate" not in form
    for ad in ("teslimat_ad_soyad", "teslimat_satir1", "teslimat_sehir", "hesap_eposta", "hesap_parola"):
        assert re.search(rf'<input id="{ad}"[^>]*\srequired', html), ad
    for ad in ("teslimat_satir2", "teslimat_posta_kodu", "fatura_ad_soyad", "fatura_satir1", "hesap_vkn",
               "hesap_firma"):
        assert not re.search(rf'<input id="{ad}"[^>]*\srequired', html), ad
    assert re.search(r'name="islem" value="hesapla"[^>]*formnovalidate', html)
    # sunucu doğrulaması kalır
    sayfa = istemci.get("/tr/odeme").text
    r = istemci.post("/tr/odeme", data=_misafir_odeme_formu(sayfa, teslimat_satir1=""), follow_redirects=False)
    assert r.status_code == 400 and 'id="hata-teslimat_satir1"' in r.text


# =====================================================================================================
# D26 — teklif onayında kalem özeti; Hesabım > Tekliflerim'den detay (yalnız sahibi)
# =====================================================================================================

def test_g3g_teklif_onay_ozeti_ve_hesabim_detay(istemci, db):
    from fastapi.testclient import TestClient
    a = _urun(db, sku="S-TD1", ad="Detay Kalem A", fiyat="10.00", stok=5)
    b = _urun(db, sku="S-TD2", ad="Detay Kalem B", fiyat="10.00", stok=5)
    _musteri(db, eposta="td@ornek.test")
    _giris(istemci, "td@ornek.test")
    r = _sepet_teklif_formu(istemci, [(a, 3), (b, 2)])
    assert r.status_code == 303
    no = db.execute("SELECT no FROM teklif").fetchone()[0]
    tamam = sayfa_denetle(istemci.get(r.headers["location"]))
    ozet = re.sub(r"<[^>]+>", "", re.search(r'<section class="teklif-ozet".*?</section>', tamam, re.S).group(0))
    assert "3 × Detay Kalem A" in ozet and "2 × Detay Kalem B" in ozet
    with TestClient(istemci.app) as baska:                       # numarayı bilen başkası özeti göremez
        assert 'class="teklif-ozet"' not in baska.get(r.headers["location"]).text
    hesabim = istemci.get("/tr/hesabim").text
    assert f'<a href="/tr/hesabim/teklif/{no}">{no}</a>' in hesabim
    detay = sayfa_denetle(istemci.get(f"/tr/hesabim/teklif/{no}"))
    assert "3 × Detay Kalem A" in re.sub(r"<[^>]+>", "", detay) and no in detay
    # tek ürünlü teklif de onayda özetlenir
    r = _post(istemci, "/tr/teklif", {"urun_id": a, "adet": "7", "ad": "QATest", "eposta": "q@example.com",
                                      "ulke": "TR", "mesaj": "Fiyat"}, "/tr/teklif")
    assert "7 × Detay Kalem A" in re.sub(r"<[^>]+>", "", istemci.get(r.headers["location"]).text)
    with TestClient(istemci.app) as baska:
        _musteri(db, eposta="td2@ornek.test")
        _giris(baska, "td2@ornek.test")
        assert baska.get(f"/tr/hesabim/teklif/{no}").status_code == 404
    with TestClient(istemci.app) as misafir:
        r = misafir.get(f"/tr/hesabim/teklif/{no}", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/tr/giris?sonraki=")
    assert istemci.get("/tr/hesabim/teklif/CR-TKL-20990101-0001").status_code == 404


# =====================================================================================================
# İnceleme turu 1
# =====================================================================================================

def _yeniden_acma_senaryosu(con):
    """Stok 1: A'nın havalesi süresi doldu, ayırma kalktı; B aynı adedi kartla aldı ve ödedi."""
    from app.fiyat.kur import Kur
    from app.hesap.servis import KayitGirdisi, kayit_ol
    from datetime import date
    simdi = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
    s, uid, _ = _havale_siparisi(con, simdi, stok=1)
    sonra = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
    kur = Kur(tarih=date(2026, 10, 12), eur_alis=Decimal("34.90"), eur_satis=Decimal("35.00"))
    with con:
        m = kayit_ol(con, KayitGirdisi(tip=MusteriTipi.BIREYSEL, ad="QATest B", eposta="b-yeniden@ornek.test",
                                       parola=PAROLA, ulke="TR", kvkk_onay=True), sonra)
        sid = sepet_servis.sepet_bul(con, None, m.id, sonra)
        con.execute("INSERT INTO sepet_kalemi (sepet_id, urun_id, adet) VALUES (?, ?, 1)", (sid, uid))
    adres = Adres(ad_soyad="QATest", satir1="Adres 1", sehir="Konya", ulke="TR")
    with con:
        b = siparis_olustur(con, m, sid, TeslimYontemi.KARGO, adres, adres, kur, sonra)
        durum_degistir(con, b.id, SiparisDurumu.ODENDI, sonra)
    return s, uid, sonra


@pytest.mark.parametrize("hedef", [SiparisDurumu.ODEME_BEKLIYOR, SiparisDurumu.ODENDI])
def test_duz1_suresi_dolan_havale_stok_yoksa_yeniden_acilmaz(con, hedef):
    from app.siparis.servis import StokYetersiz
    s, uid, sonra = _yeniden_acma_senaryosu(con)
    with pytest.raises(StokYetersiz):
        with con:
            durum_degistir(con, s.id, hedef, sonra)
    with con:
        assert siparis_getir(con, s.id, sonra).durum == SiparisDurumu.SURESI_DOLDU
    assert ayrilan_adetler(con, sonra) == {uid: 1}                       # çift satış yok


def test_duz1_suresi_dolan_havale_stok_varsa_yeniden_acilir(con):
    simdi = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
    s, uid, _ = _havale_siparisi(con, simdi, stok=2)
    sonra = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
    with con:
        assert durum_degistir(con, s.id, SiparisDurumu.ODEME_BEKLIYOR, sonra).durum == SiparisDurumu.ODEME_BEKLIYOR


def test_duz1_yonetimde_stok_hatasi_gorunur(istemci, db):
    from tests.test_web_teklif_yonetim import _yonetici_giris
    s, uid, _ = _yeniden_acma_senaryosu(db)
    gecmis = (datetime.now(UTC) - timedelta(hours=1)).isoformat()      # yönetim gerçek saatle çalışır
    with db:
        db.execute("UPDATE siparis SET odeme_son_tarih = ? WHERE id = ?", (gecmis, s.id))
    _yonetici_giris(istemci)
    r = _post(istemci, f"/yonetim/siparis/{s.id}/durum", {"durum": "odeme_bekliyor"}, "/yonetim/siparisler")
    assert r.status_code == 409
    assert 'data-e2e="stok-hatasi"' in r.text and s.no in r.text and "stok" in r.text.lower()
    assert _say(db, "SELECT odeme_son_tarih FROM siparis WHERE id = ?", s.id) == gecmis       # değişmedi


def test_duz1_cok_kalemli_sepet_teklife_eksiksiz(istemci, db):
    urunler = [_urun(db, sku=f"S-CK{i}", ad=f"Çok Kalem {i}", fiyat="10.00", stok=5) for i in range(25)]
    with istemci_db(istemci) as con:
        pass
    for u in urunler:
        _sepete_ekle(istemci, u)
    html = istemci.get("/tr/teklif?sepet=1").text
    assert len(re.findall(r'data-e2e="teklif-kalem"', html)) == 25
    assert 'data-e2e="kalem-atlandi"' not in html


def test_duz1_100_ustu_kalem_acik_uyari_ve_red(istemci, db, monkeypatch):
    from app.teklif import servis as teklif_servis
    from app.web.rotalar import teklif_gb
    monkeypatch.setattr(teklif_gb, "KALEM_MAX", 3)
    monkeypatch.setattr(teklif_servis, "KALEM_MAX", 3)
    urunler = [_urun(db, sku=f"S-UK{i}", ad=f"Uyarı Kalem {i}", fiyat="10.00", stok=5) for i in range(5)]
    for u in urunler:
        _sepete_ekle(istemci, u)
    html = istemci.get("/tr/teklif?sepet=1").text
    uyari = re.search(r'<p class="uyari" role="alert" data-e2e="kalem-atlandi">(.*?)</p>', html, re.S).group(1)
    assert "2" in uyari and "Uyarı Kalem 3" in uyari and "Uyarı Kalem 4" in uyari
    mesaj = unescape(re.search(r'<textarea id="mesaj"[^>]*>(.*?)</textarea>', html, re.S).group(1))
    assert "Uyarı Kalem 3" in mesaj and "Uyarı Kalem 4" in mesaj           # kayıt formda görünenle aynı
    r = _sepet_teklif_formu(istemci, [(u, 1) for u in urunler])         # sınırı aşan gönderim sessizce kırpılmaz
    assert r.status_code == 400 and 'id="hata-kalemler"' in r.text
    assert _say(db, "SELECT COUNT(*) FROM teklif") == 0


def test_duz1_sepet_teklif_get_sepeti_degistirmez(istemci, db):
    # inceleme M-3: tümü ayrılmış kalem teklif yolunda kalır; GET yan etkisiz
    uid = _urun(db, sku="S-GY1", ad="Ayrılmış Kalem", fiyat="10.00", stok=3)
    _sepete_ekle(istemci, uid, adet="3")
    with db:
        db.execute("UPDATE urun SET stok = 1 WHERE id = ?", (uid,))
    html = istemci.get("/tr/teklif?sepet=1").text
    assert re.search(r'name="kalem_adet"[^>]*value="3"', html)
    assert _say(db, "SELECT adet FROM sepet_kalemi WHERE urun_id = ?", uid) == 3


def test_duz1_onay_sayfasi_kurumsal_eur_ana(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-OK7", ad="Kurumsal Onay", fiyat="28.00", stok=5)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="ok7@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    _giris(istemci, "ok7@ornek.test")
    _sepete_ekle(istemci, uid, adet="2")
    r = _odeme_gonder(istemci)
    html = istemci.get(f"/tr/siparis/{_siparis_no(r.headers['location'])}").text
    tablo = re.search(r'<table class="tablo sepet-tablo siparis-kalemleri">.*?</table>', html, re.S).group(0)
    hucreler = re.findall(r'<td class="sayi" data-etiket="(Net|KDV|Tutar)[^"]*">(.*?)</td>', tablo, re.S)
    ana = {ad: re.search(r'<span class="tutar"[^>]*>(.*?)</span>', h).group(1) for ad, h in hucreler}
    assert ana == {"Net": "56,00 €", "KDV": "11,20 €", "Tutar": "67,20 €"}
    assert "1.960,00 ₺" in tablo                                          # ₺ ikincil
    ozet = re.search(r'<dl class="tutar-ozeti">.*?</dl>', html, re.S).group(0)
    assert 'data-e2e="satir-eur-ara-toplam"' in ozet and "56,00 €" in ozet
    assert 'data-e2e="not-tahsilat-try"' in html
    # bireysel onay: ₺ KDV dahil ana (değişmez)
    _musteri(db, eposta="ob7@ornek.test")
    istemci.cookies.clear()
    _giris(istemci, "ob7@ornek.test")
    _sepete_ekle(istemci, uid)
    r = _odeme_gonder(istemci)
    html = istemci.get(f"/tr/siparis/{_siparis_no(r.headers['location'])}").text
    assert 'data-e2e="satir-eur-ara-toplam"' not in html


def test_duz1_guven_satiri_12_ay_yok_duruma_gore_ozet(istemci, katalog):
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET durum_kodu = 'ikinci_el_test_edildi' WHERE id = ?", (katalog["role"],))
    for yol in (f"/tr/urun/{katalog['role']}", "/tr/"):
        html = istemci.get(yol).text
        assert "12 ay garanti" not in html and "12-month" not in html, yol
    kart = istemci.get("/tr/").text
    kart = kart[kart.index('<article class="kart"'):]
    kart = kart[:kart.index("</article>")]
    assert "Test edilmiş ürün garantisi" in kart          # G3l madde 18 metni
    assert 'href="/tr/yasal/garanti#durum-ikinci_el_test_edildi"' in kart
    en = istemci.get(f"/en/urun/{katalog['role']}").text
    assert "12-month" not in en
    # yenilenmiş: test edilmiş tanımına bağlanır (M-5)
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET durum_kodu = 'yenilenmis' WHERE id = ?", (katalog["role"],))
    html = istemci.get(f"/tr/urun/{katalog['role']}").text
    assert 'href="/tr/yasal/garanti#durum-ikinci_el_test_edildi"' in html


def test_duz1_parola_yeniden_girin_ipucu(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-PY1", ad="Parola Ürünü", fiyat="100.00", stok=3)
    _sepete_ekle(istemci, uid)
    sayfa = istemci.get("/tr/odeme").text
    assert "Güvenlik gereği parolayı yeniden girin" not in sayfa
    form = _misafir_odeme_formu(sayfa, hesap_tip="kurumsal", islem="hesapla")
    form["islem"] = "hesapla"
    r = istemci.post("/tr/odeme", data=form, follow_redirects=False)
    assert r.status_code == 200
    ipucu = re.search(r'<p class="alan-ipucu parola-yeniden" id="parola-yeniden"[^>]*>(.*?)</p>', r.text, re.S)
    assert ipucu and "Güvenlik gereği parolayı yeniden girin" in ipucu.group(1)
    assert re.search(r'id="hesap_parola" name="hesap_parola" type="password" value=""', r.text)
    assert PAROLA not in r.text
    r = istemci.post("/en/odeme", data={**form, "csrf": _gizli(r.text, "csrf")}, follow_redirects=False)
    assert "For security, please re-enter your password" in r.text


def test_duz1_bireysel_havale_alan_hatasi(istemci, db):
    # inceleme M-7: :has'siz tarayıcıda görünen havale seçeneği bireyselde sessizce karta çevrilmez
    _kur(db)
    uid = _urun(db, sku="S-BH1", ad="Bireysel Havale", fiyat="100.00", stok=3)
    _sepete_ekle(istemci, uid)
    sayfa = istemci.get("/tr/odeme").text
    form = _misafir_odeme_formu(sayfa)
    form["odeme_yontemi"] = "havale"
    r = istemci.post("/tr/odeme", data=form, follow_redirects=False)
    assert r.status_code == 400 and 'id="hata-odeme_yontemi"' in r.text and 'href="#odeme-havale"' in r.text
    assert _say(db, "SELECT COUNT(*) FROM musteri") == 0


def test_duz1_gomulu_hesap_stok_yetersizde_geri_alinir(istemci, db, monkeypatch):
    # inceleme M-6a: hesap açıldıktan sonra sipariş düşerse hesap da yazılmaz
    from app.siparis.servis import StokYetersiz
    from app.web.rotalar import sepet_odeme
    _kur(db)
    uid = _urun(db, sku="S-AT1", ad="Atomik Ürün", fiyat="100.00", stok=3)
    _sepete_ekle(istemci, uid)
    sayfa = istemci.get("/tr/odeme").text

    def dus(*a, **k):
        raise StokYetersiz([(uid, "Atomik Ürün", 0)])
    monkeypatch.setattr(sepet_odeme, "siparis_olustur", dus)
    r = istemci.post("/tr/odeme", data=_misafir_odeme_formu(sayfa), follow_redirects=False)
    assert r.status_code == 409
    assert _say(db, "SELECT COUNT(*) FROM musteri") == 0 and _say(db, "SELECT COUNT(*) FROM adres") == 0
    assert "mid" not in oturum_oku(istemci)


def test_duz1_gomulu_hesap_islem_ici_eposta_yarisi(istemci, db, monkeypatch):
    # inceleme M-6b: ön denetimi geçen ama işlem içinde kayıtlı çıkan e-posta
    from app.web.rotalar import sepet_odeme
    _kur(db)
    uid = _urun(db, sku="S-YR1", ad="Yarış Ürünü", fiyat="100.00", stok=3)
    _sepete_ekle(istemci, uid)
    sayfa = istemci.get("/tr/odeme").text
    _musteri(db, eposta="yaris@ornek.test")
    monkeypatch.setattr(sepet_odeme, "_hesap_dogrula", lambda con, hesap: {})
    r = istemci.post("/tr/odeme", data=_misafir_odeme_formu(sayfa, hesap_eposta="yaris@ornek.test"),
                     follow_redirects=False)
    assert r.status_code == 400 and "Bu e-posta kayıtlı, giriş yapın" in r.text
    assert _say(db, "SELECT COUNT(*) FROM siparis") == 0
    assert _say(db, "SELECT COUNT(*) FROM sepet_kalemi WHERE urun_id = ?", uid) == 1


def test_duz1_ayirma_bitisi_null_son_tarih_atlanir(con):
    # inceleme M-8
    from app.stok import ayirma_bitisleri
    simdi = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
    s, uid, _ = _havale_siparisi(con, simdi)
    with con:
        con.execute("UPDATE siparis SET odeme_son_tarih = NULL WHERE id = ?", (s.id,))
    assert ayirma_bitisleri(con, simdi, [uid]) == {}
