import itertools
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.fiyat.kur import Kur
from app.fiyat.kurallar import TeslimYontemi
from app.hesap.servis import Adres, musteri_getir
from app.sepet.servis import ekle, sepet_bul
from app.siparis.odeme_sim import (
    BASARILI_KART,
    RET_KARTI,
    SMS_KODU,
    OdemeSonucu,
    deneme_getir,
    kart_normalize,
    odeme_baslat,
    sms_dogrula,
)
from app.siparis.servis import SiparisDurumu, siparis_getir, siparis_olustur
from tests.conftest import urun_ekle

O = OdemeSonucu
KUR = Kur(tarih=date(2026, 10, 13), eur_alis=Decimal("48.00"), eur_satis=Decimal("48.50"))
ADRES = Adres(ad_soyad="QATestUser", satir1="Demo Cad. 1", sehir="Kocaeli", ulke="TR")
_sayac = itertools.count(1)


def hazir_siparis(con, simdi):
    n = next(_sayac)
    mid = con.execute(
        "INSERT INTO musteri (tip, ad, eposta, parola_ozeti, ulke, kvkk_onay, olusturma) "
        "VALUES ('bireysel', 'QATestUser', ?, 'x', 'TR', ?, ?)",
        (f"qa.odeme{n}@example.com", simdi.isoformat(), simdi.isoformat()),
    ).lastrowid
    uid = urun_ekle(con, sku=f"OD{n}", ad="Röle", fiyat="100.00")
    sid = sepet_bul(con, None, mid, simdi)
    ekle(con, sid, uid, 1)
    return siparis_olustur(con, musteri_getir(con, mid), sid, TeslimYontemi.KARGO, ADRES, ADRES, KUR, simdi)


def tum_satirlar(con):
    metin = ""
    for tablo in ("odeme_denemesi", "siparis", "siparis_kalemi", "sepet_kalemi"):
        for r in con.execute(f"SELECT * FROM {tablo}"):
            metin += str(tuple(r))
    return metin


def deneme_sayisi(con):
    return con.execute("SELECT COUNT(*) FROM odeme_denemesi").fetchone()[0]


def sepet_adedi(con, sepet_id):
    return con.execute("SELECT COUNT(*) FROM sepet_kalemi WHERE sepet_id = ?", (sepet_id,)).fetchone()[0]


def test_kart_normalize():
    assert kart_normalize("4111 1111-1111 1111") == BASARILI_KART
    assert kart_normalize(" 4000-0000-0000-0002 ") == RET_KARTI
    assert kart_normalize("abc") == ""
    assert (BASARILI_KART, RET_KARTI, SMS_KODU) == ("4111111111111111", "4000000000000002", "000000")


def test_test_karti_disi_reddedilir_ve_saklanmaz(con, simdi):
    s = hazir_siparis(con, simdi)
    assert odeme_baslat(con, s.id, "a1", "5555 4444 3333 1111", simdi) is O.GECERSIZ_KART
    assert odeme_baslat(con, s.id, "a2", "4111 1111 1111 1112", simdi) is O.GECERSIZ_KART
    r = con.execute("SELECT * FROM odeme_denemesi WHERE islem_anahtari = 'a1'").fetchone()
    assert (r["durum"], r["kart_son4"], r["kart_sonucu"]) == ("gecersiz_kart", None, None)
    metin = tum_satirlar(con)
    assert "5555444433331111" not in metin and "5555 4444 3333 1111" not in metin
    assert "4111111111111112" not in metin
    assert siparis_getir(con, s.id, simdi).durum is SiparisDurumu.ODEME_BEKLIYOR


def test_bosluklu_tireli_kart_normalize_edilir(con, simdi):
    s = hazir_siparis(con, simdi)
    assert odeme_baslat(con, s.id, "b1", "4111-1111 1111-1111", simdi) is O.SMS_BEKLIYOR
    r = con.execute("SELECT * FROM odeme_denemesi WHERE islem_anahtari = 'b1'").fetchone()
    assert (r["durum"], r["kart_son4"], r["kart_sonucu"]) == ("sms_bekliyor", "1111", "basarili")
    assert r["olusturma"] == simdi.isoformat()
    assert BASARILI_KART not in tum_satirlar(con)


def test_deneme_getir(con, simdi):
    s = hazir_siparis(con, simdi)
    assert deneme_getir(con, "yok") is None
    odeme_baslat(con, s.id, "g1", BASARILI_KART, simdi)
    d = deneme_getir(con, "g1")
    assert (d["islem_anahtari"], d["siparis_id"], d["durum"], d["kart_son4"]) == ("g1", s.id, "sms_bekliyor", "1111")
    sms_dogrula(con, "g1", SMS_KODU, simdi)
    assert deneme_getir(con, "g1")["durum"] == "basarili"


def test_ayni_anahtar_idempotent(con, simdi):
    s = hazir_siparis(con, simdi)
    assert odeme_baslat(con, s.id, "k1", BASARILI_KART, simdi) is O.SMS_BEKLIYOR
    assert odeme_baslat(con, s.id, "k1", RET_KARTI, simdi) is O.SMS_BEKLIYOR
    assert deneme_sayisi(con) == 1
    r = con.execute("SELECT kart_sonucu FROM odeme_denemesi WHERE islem_anahtari = 'k1'").fetchone()
    assert r["kart_sonucu"] == "basarili"
    assert sms_dogrula(con, "k1", SMS_KODU, simdi) is O.BASARILI
    assert odeme_baslat(con, s.id, "k1", BASARILI_KART, simdi) is O.BASARILI
    assert sms_dogrula(con, "k1", SMS_KODU, simdi) is O.BASARILI
    assert deneme_sayisi(con) == 1
    baska = hazir_siparis(con, simdi)
    assert odeme_baslat(con, baska.id, "k1", BASARILI_KART, simdi) is O.SIPARIS_GECERSIZ
    assert sms_dogrula(con, "bilinmeyen", SMS_KODU, simdi) is O.SIPARIS_GECERSIZ


def test_sms_hatali(con, simdi):
    s = hazir_siparis(con, simdi)
    odeme_baslat(con, s.id, "h1", BASARILI_KART, simdi)
    assert sms_dogrula(con, "h1", "123456", simdi) is O.SMS_HATALI
    assert sms_dogrula(con, "h1", SMS_KODU, simdi) is O.SMS_HATALI      # deneme bitti
    assert siparis_getir(con, s.id, simdi).durum is SiparisDurumu.ODEME_BEKLIYOR
    assert odeme_baslat(con, s.id, "h2", BASARILI_KART, simdi) is O.SMS_BEKLIYOR
    assert sms_dogrula(con, "h2", f" {SMS_KODU} ", simdi) is O.BASARILI


def test_ret_sonrasi_yeni_anahtarla_basarili(con, simdi):
    s = hazir_siparis(con, simdi)
    assert odeme_baslat(con, s.id, "r1", "4000 0000 0000 0002", simdi) is O.SMS_BEKLIYOR
    assert sms_dogrula(con, "r1", SMS_KODU, simdi) is O.RET
    g = siparis_getir(con, s.id, simdi)
    assert g.durum is SiparisDurumu.ODEME_BEKLIYOR and g.kart_son4 is None
    assert sepet_adedi(con, s.sepet_id) == 1
    assert odeme_baslat(con, s.id, "r2", BASARILI_KART, simdi + timedelta(minutes=2)) is O.SMS_BEKLIYOR
    assert sms_dogrula(con, "r2", SMS_KODU, simdi + timedelta(minutes=3)) is O.BASARILI
    g = siparis_getir(con, s.id, simdi + timedelta(minutes=3))
    assert g.durum is SiparisDurumu.ODENDI and g.kart_son4 == "1111"
    assert sepet_adedi(con, s.sepet_id) == 0
    metin = tum_satirlar(con)
    assert BASARILI_KART not in metin and RET_KARTI not in metin
    assert odeme_baslat(con, s.id, "r3", BASARILI_KART, simdi + timedelta(minutes=4)) is O.ZATEN_ODENDI
    assert deneme_sayisi(con) == 2                                       # r3 kaydedilmez


def test_zaman_asimi_sonrasi_deneme(con, simdi):
    s = hazir_siparis(con, simdi)
    assert odeme_baslat(con, s.id, "t1", BASARILI_KART, simdi + timedelta(minutes=31)) is O.SIPARIS_GECERSIZ
    assert siparis_getir(con, s.id, simdi + timedelta(minutes=31)).durum is SiparisDurumu.IPTAL
    assert odeme_baslat(con, 99999, "t2", BASARILI_KART, simdi) is O.SIPARIS_GECERSIZ
    s2 = hazir_siparis(con, simdi)
    assert odeme_baslat(con, s2.id, "t3", BASARILI_KART, simdi + timedelta(minutes=25)) is O.SMS_BEKLIYOR
    assert sms_dogrula(con, "t3", SMS_KODU, simdi + timedelta(minutes=31)) is O.SIPARIS_GECERSIZ
    assert siparis_getir(con, s2.id, simdi + timedelta(minutes=31)).durum is SiparisDurumu.IPTAL


def test_ayni_siparis_iki_anahtar_tek_odeme(con, simdi):
    s = hazir_siparis(con, simdi)
    assert odeme_baslat(con, s.id, "x1", BASARILI_KART, simdi) is O.SMS_BEKLIYOR
    assert odeme_baslat(con, s.id, "x2", BASARILI_KART, simdi) is O.SMS_BEKLIYOR
    assert sms_dogrula(con, "x1", SMS_KODU, simdi) is O.BASARILI
    assert sms_dogrula(con, "x2", SMS_KODU, simdi) is O.ZATEN_ODENDI
    assert con.execute("SELECT durum FROM odeme_denemesi WHERE islem_anahtari = 'x2'").fetchone()[0] != "basarili"
    assert con.execute("SELECT durum FROM siparis WHERE id = ?", (s.id,)).fetchone()[0] == "odendi"
    assert con.execute("SELECT COUNT(*) FROM odeme_denemesi WHERE durum = 'basarili'").fetchone()[0] == 1


def test_arada_odendi_olursa_sizmaz(con, simdi):
    """Engel kontrolünden sonra, koşullu UPDATE'ten önce sipariş değişirse GecersizGecis sızmaz."""
    s = hazir_siparis(con, simdi)
    odeme_baslat(con, s.id, "y1", BASARILI_KART, simdi)

    class Araya:
        def __init__(self, c):
            self.c, self.once = c, True

        def execute(self, sql, *a):
            if sql.startswith("UPDATE siparis SET durum") and self.once:
                self.once = False
                self.c.execute("UPDATE siparis SET durum = 'odendi' WHERE id = ?", (s.id,))
            return self.c.execute(sql, *a)

    assert sms_dogrula(Araya(con), "y1", SMS_KODU, simdi) is O.ZATEN_ODENDI
    assert con.execute("SELECT durum FROM odeme_denemesi WHERE islem_anahtari = 'y1'").fetchone()[0] != "basarili"


def test_bos_anahtar(con, simdi):
    s = hazir_siparis(con, simdi)
    with pytest.raises(ValueError):
        odeme_baslat(con, s.id, "", BASARILI_KART, simdi)
    with pytest.raises(ValueError):
        sms_dogrula(con, "", SMS_KODU, simdi)
