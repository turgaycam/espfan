from datetime import timedelta

import pytest

from app.geribildirim.servis import DURUMLAR, durum_degistir, kaydet, listele


def test_kaydet_ve_listele(con, simdi):
    i1 = kaydet(con, "/tr/urun/5", "  Fiyat görünmüyor  ", " QATestUser ", simdi)
    i2 = kaydet(con, "/tr/", "Arama yavaş", "", simdi + timedelta(minutes=1))
    satirlar = listele(con)
    assert [r["id"] for r in satirlar] == [i2, i1]
    eski = satirlar[1]
    assert (eski["sayfa"], eski["metin"], eski["isim"], eski["durum"], eski["olusturma"]) == (
        "/tr/urun/5", "Fiyat görünmüyor", "QATestUser", "yeni", simdi.isoformat(),
    )
    assert satirlar[0]["isim"] is None
    assert DURUMLAR == ("yeni", "okundu", "yapildi")


@pytest.mark.parametrize("metin", ["", "   ", "\n\t", None])
def test_bos_metin(con, simdi, metin):
    with pytest.raises(ValueError):
        kaydet(con, "/tr/", metin, None, simdi)


def test_metin_2000_siniri(con, simdi):
    kaydet(con, "/tr/", "x" * 2000, None, simdi)
    with pytest.raises(ValueError):
        kaydet(con, "/tr/", "x" * 2001, None, simdi)
    assert len(listele(con)) == 1


def test_sayfa_500_siniri(con, simdi):
    kaydet(con, "/" + "a" * 499, "metin", None, simdi)
    for sayfa in ["/" + "a" * 500, "", "   ", None]:
        with pytest.raises(ValueError):
            kaydet(con, sayfa, "metin", None, simdi)
    assert len(listele(con)) == 1


def test_isim_100_siniri(con, simdi):
    kaydet(con, "/tr/", "metin", "i" * 100, simdi)
    with pytest.raises(ValueError):
        kaydet(con, "/tr/", "metin", "i" * 101, simdi)


def test_listele_durum_filtresi(con, simdi):
    i1 = kaydet(con, "/tr/", "bir", None, simdi)
    i2 = kaydet(con, "/tr/", "iki", None, simdi)
    durum_degistir(con, i1, "okundu")
    assert [r["id"] for r in listele(con, "okundu")] == [i1]
    assert [r["id"] for r in listele(con, "yeni")] == [i2]
    assert listele(con, "yapildi") == []
    with pytest.raises(ValueError):
        listele(con, "gecersiz")


@pytest.mark.parametrize("durum", ["silindi", "", "YENI"])
def test_durum_degistir_gecersiz(con, simdi, durum):
    i = kaydet(con, "/tr/", "metin", None, simdi)
    with pytest.raises(ValueError):
        durum_degistir(con, i, durum)
    assert listele(con)[0]["durum"] == "yeni"


def test_durum_degistir_olmayan_kayit(con):
    with pytest.raises(LookupError):
        durum_degistir(con, 99999, "okundu")
