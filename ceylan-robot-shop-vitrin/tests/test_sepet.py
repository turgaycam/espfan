from decimal import Decimal

import pytest

from app.fiyat.kurallar import Kalem
from app.sepet.servis import (
    ADET_MAX,
    ADET_MIN,
    TeklifZorunlu,
    UrunYok,
    adet_ayarla,
    adet_toplam,
    birlestir,
    bosalt,
    ekle,
    kaldir,
    kalemler,
    sepet_bul,
)
from tests.conftest import urun_ekle


def musteri_ekle(con, simdi, eposta="qa.sepet@example.com"):
    return con.execute(
        "INSERT INTO musteri (tip, ad, eposta, parola_ozeti, ulke, kvkk_onay, olusturma) "
        "VALUES ('bireysel', 'QATestUser', ?, 'x', 'TR', ?, ?)",
        (eposta, simdi.isoformat(), simdi.isoformat()),
    ).lastrowid


def adetler(con, sepet_id):
    return {
        r["urun_id"]: r["adet"]
        for r in con.execute("SELECT urun_id, adet FROM sepet_kalemi WHERE sepet_id = ?", (sepet_id,))
    }


def test_sabitler():
    assert (ADET_MIN, ADET_MAX) == (1, 99)


def test_sepet_bul_misafir_ve_uye(con, simdi):
    s1 = sepet_bul(con, "oid-1", None, simdi)
    assert sepet_bul(con, "oid-1", None, simdi) == s1
    assert sepet_bul(con, "oid-2", None, simdi) != s1
    mid = musteri_ekle(con, simdi)
    s3 = sepet_bul(con, "oid-1", mid, simdi)
    assert s3 != s1
    assert sepet_bul(con, None, mid, simdi) == s3
    r = con.execute("SELECT oturum_id, musteri_id, olusturma FROM sepet WHERE id = ?", (s3,)).fetchone()
    assert (r["oturum_id"], r["musteri_id"], r["olusturma"]) == (None, mid, simdi.isoformat())
    with pytest.raises(ValueError):
        sepet_bul(con, None, None, simdi)


def test_ekle_toplar_ve_99_siniri(con, simdi):
    s = sepet_bul(con, "oid", None, simdi)
    a = urun_ekle(con, sku="A", stok=500)
    ekle(con, s, a)
    assert adetler(con, s) == {a: 1}
    ekle(con, s, a, 3)
    assert adetler(con, s) == {a: 4}
    ekle(con, s, a, 98)
    assert adetler(con, s) == {a: 99}
    assert adet_toplam(con, s) == 99


def test_teklif_zorunlu_eklenemez(con, simdi):
    s = sepet_bul(con, "oid", None, simdi)
    t = urun_ekle(con, sku="ROBOT", kok="Endüstriyel Robotlar", teklif=True, fiyat="20000.00")
    with pytest.raises(TeklifZorunlu):
        ekle(con, s, t)
    assert adetler(con, s) == {}


def test_urun_yok_ve_pasif(con, simdi):
    s = sepet_bul(con, "oid", None, simdi)
    p = urun_ekle(con, sku="P", aktif=False)
    with pytest.raises(UrunYok):
        ekle(con, s, 99999)
    with pytest.raises(UrunYok):
        ekle(con, s, p)
    assert adetler(con, s) == {}


def test_adet_sinirlari(con, simdi):
    s = sepet_bul(con, "oid", None, simdi)
    a, b, c = (urun_ekle(con, sku=x, stok=500) for x in ("A", "B", "C"))
    ekle(con, s, a, 0)
    ekle(con, s, b, -3)
    ekle(con, s, c, 1000)
    assert adetler(con, s) == {a: 1, b: 1, c: 99}
    adet_ayarla(con, s, a, 1000)
    assert adetler(con, s)[a] == 99
    adet_ayarla(con, s, a, 5)
    assert adetler(con, s)[a] == 5
    adet_ayarla(con, s, a, 0)
    adet_ayarla(con, s, b, -3)
    assert adetler(con, s) == {c: 99}
    d = urun_ekle(con, sku="D", stok=500)
    adet_ayarla(con, s, d, 5)                      # sepette olmayan ürün eklenmez
    assert adetler(con, s) == {c: 99}


def test_kaldir_bosalt_adet_toplam(con, simdi):
    s = sepet_bul(con, "oid", None, simdi)
    a, b = urun_ekle(con, sku="A", stok=500), urun_ekle(con, sku="B", stok=500)
    ekle(con, s, a, 2)
    ekle(con, s, b, 3)
    assert adet_toplam(con, s) == 5
    kaldir(con, s, a)
    assert adetler(con, s) == {b: 3}
    bosalt(con, s)
    assert adetler(con, s) == {} and adet_toplam(con, s) == 0


def test_kalemler_fiyat_kalemi_doner(con, simdi):
    s = sepet_bul(con, "oid", None, simdi)
    a = urun_ekle(con, sku="A1", ad="Röle", fiyat="123.45", kdv="20", stok=0)
    b = urun_ekle(con, sku="B1", ad="Kablo", fiyat="10.00", kdv="10", stok=0, tedarik_suresi_gun=14)
    c = urun_ekle(con, sku="C1", ad="Sigorta", fiyat="5.00", stok=7)
    ekle(con, s, a, 2)
    ekle(con, s, b)
    ekle(con, s, c, 3)
    gecerli, dusen = kalemler(con, s)
    assert dusen == []
    assert gecerli == [
        Kalem(urun_id=a, sku="A1", ad="Röle", adet=2, birim_net_eur=Decimal("123.45"),
              kdv_orani=Decimal("20"), tedarik_teyit=True),
        Kalem(urun_id=b, sku="B1", ad="Kablo", adet=1, birim_net_eur=Decimal("10.00"),
              kdv_orani=Decimal("10"), tedarik_teyit=False),
        Kalem(urun_id=c, sku="C1", ad="Sigorta", adet=3, birim_net_eur=Decimal("5.00"),
              kdv_orani=Decimal("20"), tedarik_teyit=False),
    ]


def test_pasif_urun_sepetten_duser(con, simdi):
    s = sepet_bul(con, "oid", None, simdi)
    a = urun_ekle(con, sku="A", ad="Pasifleşen Röle")
    b = urun_ekle(con, sku="B", ad="Pahalanan Sürücü")
    c = urun_ekle(con, sku="C", ad="Kalan Kablo")
    for x in (a, b, c):
        ekle(con, s, x)
    con.execute("UPDATE urun SET aktif = 0 WHERE id = ?", (a,))
    con.execute("UPDATE urun SET teklif_zorunlu = 1 WHERE id = ?", (b,))
    gecerli, dusen = kalemler(con, s)
    assert [k.urun_id for k in gecerli] == [c]
    assert dusen == ["Pasifleşen Röle", "Pahalanan Sürücü"]
    assert adetler(con, s) == {c: 1}
    assert kalemler(con, s)[1] == []                  # ikinci çağrıda bildirilecek bir şey kalmaz


def test_birlestir(con, simdi):
    misafir = sepet_bul(con, "oid", None, simdi)
    uye = sepet_bul(con, None, musteri_ekle(con, simdi), simdi)
    a, b, c = (urun_ekle(con, sku=x, stok=500) for x in ("A", "B", "C"))
    ekle(con, misafir, a, 60)
    ekle(con, misafir, b, 2)
    ekle(con, uye, a, 50)
    ekle(con, uye, c, 1)
    assert birlestir(con, misafir, uye) == 2
    assert adetler(con, uye) == {a: 99, b: 2, c: 1}
    assert adetler(con, misafir) == {}
    assert con.execute("SELECT COUNT(*) FROM sepet WHERE id = ?", (misafir,)).fetchone()[0] == 0
    assert birlestir(con, uye, uye) == 0
    assert adetler(con, uye) == {a: 99, b: 2, c: 1}
