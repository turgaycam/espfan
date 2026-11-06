from datetime import UTC, datetime, timedelta

import pytest

from app.siparis.servis import GecersizGecis
from app.teklif.servis import (
    TEKLIF_GECISLERI,
    Teklif,
    TeklifGirdisi,
    TeklifHatasi,
    teklif_durum_degistir,
    teklif_olustur,
    teklifler,
)
from tests.conftest import urun_ekle


def girdi(**kw):
    alanlar = dict(ad="QATestUser", eposta="qa.teklif@example.com", ulke="TR", mesaj="KR C4 için fiyat istiyoruz.")
    alanlar.update(kw)
    return TeklifGirdisi(**alanlar)


def teklif_sayisi(con):
    return con.execute("SELECT COUNT(*) FROM teklif").fetchone()[0]


def test_teklif_no_ve_alanlar(con, simdi):
    uid = urun_ekle(
        con, sku="8301033800019", ad="KUKA KRC5 KR 140 R3200-2 PA", kok="Endüstriyel Robotlar",
        teklif=True, fiyat="20000.00",
    )
    t1 = teklif_olustur(con, girdi(urun_id=uid, adet=2, firma=" QATest Ltd ", telefon="", ulke="de"), simdi)
    t2 = teklif_olustur(con, girdi(), simdi + timedelta(hours=2))
    t3 = teklif_olustur(con, girdi(), simdi + timedelta(days=1))
    assert (t1.no, t2.no, t3.no) == ("CR-TKL-20261013-0001", "CR-TKL-20261013-0002", "CR-TKL-20261014-0001")
    assert isinstance(t1, Teklif)
    assert (t1.urun_id, t1.urun_ad, t1.adet) == (uid, "KUKA KRC5 KR 140 R3200-2 PA", 2)
    assert (t1.firma, t1.telefon, t1.ulke, t1.durum, t1.olusturma) == ("QATest Ltd", None, "DE", "yeni", simdi)
    assert (t1.ad, t1.eposta, t1.mesaj, t1.musteri_id) == ("QATestUser", "qa.teklif@example.com", "KR C4 için fiyat istiyoruz.", None)
    assert (t2.urun_id, t2.urun_ad, t2.adet) == (None, None, 1)


def test_teklif_no_tarihi_istanbul_saati(con):
    gece = datetime(2026, 10, 12, 22, 30, tzinfo=UTC)          # İstanbul'da 13.10.2026 01:30
    assert teklif_olustur(con, girdi(), gece).no == "CR-TKL-20261013-0001"


@pytest.mark.parametrize(
    "alan,deger,kod",
    [
        ("ad", "  ", "zorunlu"), ("eposta", "", "iletisim_gerekli"), ("eposta", "qa.example.com", "gecersiz"),
        ("mesaj", " \n ", "zorunlu"), ("ulke", "", "zorunlu"), ("adet", 0, "gecersiz"),
        ("adet", 10000, "gecersiz"), ("urun_id", 99999, "gecersiz"), ("musteri_id", 99999, "gecersiz"),
    ],
)
def test_teklif_hatalari(con, simdi, alan, deger, kod):
    with pytest.raises(TeklifHatasi) as e:
        teklif_olustur(con, girdi(**{alan: deger}), simdi)
    assert (e.value.alan, e.value.kod) == (alan, kod)
    assert teklif_sayisi(con) == 0


def test_mesaj_2000_siniri(con, simdi):
    assert len(teklif_olustur(con, girdi(mesaj="x" * 2000), simdi).mesaj) == 2000
    with pytest.raises(TeklifHatasi) as e:
        teklif_olustur(con, girdi(mesaj="x" * 2001), simdi)
    assert (e.value.alan, e.value.kod) == ("mesaj", "cok_uzun")
    assert teklif_sayisi(con) == 1


def test_teklifler_musteri_filtresi(con, simdi):
    mid = con.execute(
        "INSERT INTO musteri (tip, ad, eposta, parola_ozeti, ulke, kvkk_onay, olusturma) "
        "VALUES ('kurumsal', 'QATestUser Ltd', 'qa.tk@example.com', 'x', 'TR', ?, ?)",
        (simdi.isoformat(), simdi.isoformat()),
    ).lastrowid
    t1 = teklif_olustur(con, girdi(musteri_id=mid), simdi)
    t2 = teklif_olustur(con, girdi(), simdi)
    t3 = teklif_olustur(con, girdi(musteri_id=mid), simdi)
    assert [t.id for t in teklifler(con, mid)] == [t3.id, t1.id]
    assert [t.id for t in teklifler(con)] == [t3.id, t2.id, t1.id]
    assert teklifler(con, 99999) == []
    assert teklifler(con, mid)[0].musteri_id == mid


def test_teklif_gecis_tablosu():
    assert TEKLIF_GECISLERI == {
        "yeni": {"inceleniyor", "kapandi"},
        "inceleniyor": {"teklif_verildi", "kapandi"},
        "teklif_verildi": {"kapandi"},
        "kapandi": set(),
    }


IZINLI = [(a, b) for a, hedefler in TEKLIF_GECISLERI.items() for b in sorted(hedefler)]
IZINSIZ = [
    ("yeni", "teklif_verildi"), ("yeni", "yeni"), ("inceleniyor", "yeni"), ("teklif_verildi", "inceleniyor"),
    ("kapandi", "yeni"), ("kapandi", "inceleniyor"), ("yeni", "bilinmeyen"),
]


@pytest.mark.parametrize("eski,yeni", IZINLI)
def test_teklif_izinli_gecis(con, simdi, eski, yeni):
    t = teklif_olustur(con, girdi(), simdi)
    con.execute("UPDATE teklif SET durum = ? WHERE id = ?", (eski, t.id))
    assert teklif_durum_degistir(con, t.id, yeni).durum == yeni


@pytest.mark.parametrize("eski,yeni", IZINSIZ)
def test_teklif_izinsiz_gecis(con, simdi, eski, yeni):
    t = teklif_olustur(con, girdi(), simdi)
    con.execute("UPDATE teklif SET durum = ? WHERE id = ?", (eski, t.id))
    with pytest.raises(GecersizGecis):
        teklif_durum_degistir(con, t.id, yeni)
    assert con.execute("SELECT durum FROM teklif WHERE id = ?", (t.id,)).fetchone()[0] == eski


def test_teklif_yok(con):
    with pytest.raises(LookupError):
        teklif_durum_degistir(con, 99999, "inceleniyor")


class _ArayaGirenBaglanti:
    """Durum okunduktan sonra, UPDATE'ten önce başka bir işlem durumu değiştirmiş gibi davranır."""

    def __init__(self, con, teklif_id, araya):
        self._con = con
        self._id = teklif_id
        self._araya = araya
        self._tetik = True

    def execute(self, sql, params=()):
        cur = self._con.execute(sql, params)
        if self._tetik and sql.startswith("SELECT durum FROM teklif"):
            self._tetik = False
            self._con.execute("UPDATE teklif SET durum = ? WHERE id = ?", (self._araya, self._id))
        return cur


def test_teklif_durum_yaris_kosulu(con, simdi):
    t = teklif_olustur(con, girdi(), simdi)                    # durum: yeni
    vekil = _ArayaGirenBaglanti(con, t.id, "kapandi")
    with pytest.raises(GecersizGecis) as e:
        teklif_durum_degistir(vekil, t.id, "inceleniyor")      # yeni->inceleniyor geçerliydi, ama araya girdi
    assert "kapandi" in str(e.value)
    assert con.execute("SELECT durum FROM teklif WHERE id = ?", (t.id,)).fetchone()[0] == "kapandi"


def test_g3a_teklif_no_gunluk_9999_ustunde_genisler(con, simdi):
    con.execute("INSERT INTO teklif (no, ad, eposta, ulke, mesaj, olusturma) VALUES"
                " ('CR-TKL-20261013-9999', 'a', 'a@b.c', 'TR', 'm', ?)", (simdi.isoformat(),))
    t = teklif_olustur(con, girdi(), simdi)
    assert t.no == "CR-TKL-20261013-10000"
    assert teklif_olustur(con, girdi(), simdi).no == "CR-TKL-20261013-10001"
