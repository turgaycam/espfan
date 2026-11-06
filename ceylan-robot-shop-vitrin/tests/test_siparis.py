import itertools
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.fiyat.kur import Kur
from app.fiyat.kurallar import KurYok, MusteriTipi, TeslimYontemi
from app.hesap.servis import Adres, musteri_getir
from app.sepet.servis import adet_ayarla, ekle, sepet_bul
from app.siparis.servis import (
    IZINLI_GECISLER,
    ODEME_SURESI,
    GecersizGecis,
    SepetBos,
    SiparisDurumu,
    durum_degistir,
    musteri_siparisleri,
    siparis_getir,
    siparis_no_ile,
    siparis_olustur,
    tum_siparisler,
    zaman_asimi_uygula,
)
from tests.conftest import urun_ekle

D = SiparisDurumu
KUR = Kur(tarih=date(2026, 10, 13), eur_alis=Decimal("48.00"), eur_satis=Decimal("48.50"))
ADRES_TR = Adres(ad_soyad="QATestUser", satir1="Demo Cad. 1", sehir="Kocaeli", ulke="TR", posta_kodu="41400")
ADRES_DE = Adres(ad_soyad="QATestUser GmbH", satir1="Demostr. 1", sehir="Berlin", ulke="DE", posta_kodu="10115")
_sayac = itertools.count(1)


def musteri(con, simdi, tip=MusteriTipi.BIREYSEL, ulke="TR"):
    mid = con.execute(
        "INSERT INTO musteri (tip, ad, eposta, parola_ozeti, ulke, kvkk_onay, olusturma) "
        "VALUES (?, 'QATestUser', ?, 'x', ?, ?, ?)",
        (tip.value, f"qa.siparis{next(_sayac)}@example.com", ulke, simdi.isoformat(), simdi.isoformat()),
    ).lastrowid
    return musteri_getir(con, mid)


def dolu_sepet(con, m, simdi, fiyat="100.00", adet=2):
    uid = urun_ekle(con, sku=f"S{next(_sayac)}", ad="Röle", fiyat=fiyat, kdv="20", stok=50)
    sid = sepet_bul(con, None, m.id, simdi)
    ekle(con, sid, uid, adet)
    return sid, uid


def yeni_siparis(con, simdi, m=None):
    m = m or musteri(con, simdi)
    sid, _ = dolu_sepet(con, m, simdi)
    return siparis_olustur(con, m, sid, TeslimYontemi.KARGO, ADRES_TR, ADRES_TR, KUR, simdi)


def test_siparis_olustur_anlik_goruntu(con, simdi):
    m = musteri(con, simdi)
    sid, uid = dolu_sepet(con, m, simdi)
    sku = con.execute("SELECT sku FROM urun WHERE id = ?", (uid,)).fetchone()[0]
    s = siparis_olustur(con, m, sid, TeslimYontemi.KARGO, ADRES_TR, ADRES_TR, KUR, simdi)
    assert s.durum is D.ODEME_BEKLIYOR and s.para_birimi == "TRY"
    # 100,00 € x 2 x 48,50 = 9.700,00 ₺ ; KDV 1.940,00 ; kargo 15 € x 48,50 = 727,50 + KDV 145,50
    assert (s.ara_toplam, s.kdv, s.kargo, s.toplam) == (
        Decimal("9700.00"), Decimal("2085.50"), Decimal("727.50"), Decimal("12513.00"),
    )
    assert s.kur == Decimal("48.50") and s.kur_tarihi == date(2026, 10, 13) and s.ihracat_istisnasi is False
    assert s.teslim_yontemi is TeslimYontemi.KARGO and s.teslimat_ulkesi == "TR"
    assert s.teslimat_adresi == ADRES_TR and s.fatura_adresi == ADRES_TR
    assert (s.musteri_id, s.sepet_id, s.olusturma, s.kart_son4) == (m.id, sid, simdi, None)
    assert len(s.kalemler) == 1
    k = s.kalemler[0]
    assert (k.urun_id, k.sku, k.ad, k.adet, k.birim_net_eur, k.net, k.kdv, k.brut, k.tedarik_teyit) == (
        uid, sku, "Röle", 2, Decimal("100.00"), Decimal("9700.00"), Decimal("1940.00"), Decimal("11640.00"), False,
    )
    # sepet ve ürün sonradan değişse de sipariş değişmez
    adet_ayarla(con, sid, uid, 5)
    con.execute("UPDATE urun SET temsili_fiyat_eur = '999.00', ad = 'Değişti' WHERE id = ?", (uid,))
    assert siparis_getir(con, s.id, simdi) == s


def test_yurtdisi_eur_kur_yazilmaz(con, simdi):
    m = musteri(con, simdi, MusteriTipi.YURTDISI, "DE")
    sid, _ = dolu_sepet(con, m, simdi)
    s = siparis_olustur(con, m, sid, TeslimYontemi.YURTDISI_DAP, ADRES_DE, ADRES_DE, KUR, simdi)
    assert s.para_birimi == "EUR" and s.kur is None and s.kur_tarihi is None
    assert s.ihracat_istisnasi is True and s.teslimat_ulkesi == "DE"
    assert (s.kdv, s.kargo, s.toplam) == (Decimal("0"), Decimal("0"), Decimal("200.00"))


def test_try_tahsilatta_kur_yoksa_hata(con, simdi):
    m = musteri(con, simdi)
    sid, _ = dolu_sepet(con, m, simdi)
    with pytest.raises(KurYok):                       # K5: KurYok(ValueError)
        siparis_olustur(con, m, sid, TeslimYontemi.KARGO, ADRES_TR, ADRES_TR, None, simdi)
    assert issubclass(KurYok, ValueError)
    assert con.execute("SELECT COUNT(*) FROM siparis").fetchone()[0] == 0


def test_siparis_no_ve_gun_ici_sira(con, simdi):
    m = musteri(con, simdi)
    sid, _ = dolu_sepet(con, m, simdi)
    s1 = siparis_olustur(con, m, sid, TeslimYontemi.KARGO, ADRES_TR, ADRES_TR, KUR, simdi)
    s2 = siparis_olustur(con, m, sid, TeslimYontemi.KARGO, ADRES_TR, ADRES_TR, KUR, simdi + timedelta(hours=1))
    s3 = siparis_olustur(con, m, sid, TeslimYontemi.KARGO, ADRES_TR, ADRES_TR, KUR, simdi + timedelta(days=1))
    assert (s1.no, s2.no, s3.no) == ("CR-DEMO-20261013-0001", "CR-DEMO-20261013-0002", "CR-DEMO-20261014-0001")
    assert siparis_no_ile(con, s2.no, simdi + timedelta(hours=1)) == s2
    assert siparis_no_ile(con, "CR-DEMO-YOK", simdi) is None
    baska = yeni_siparis(con, simdi)
    assert [x.no for x in musteri_siparisleri(con, m.id, simdi)] == [s3.no, s2.no, s1.no]
    assert [x.no for x in tum_siparisler(con, simdi)] == [baska.no, s3.no, s2.no, s1.no]
    assert musteri_siparisleri(con, 99999, simdi) == []


def test_siparis_no_tarihi_istanbul_saati(con):
    gece = datetime(2026, 10, 12, 22, 30, tzinfo=UTC)          # İstanbul'da 13.10.2026 01:30
    s = yeni_siparis(con, gece)
    assert s.no == "CR-DEMO-20261013-0001"
    s2 = yeni_siparis(con, datetime(2026, 10, 13, 9, 0, tzinfo=UTC))
    assert s2.no == "CR-DEMO-20261013-0002"                    # aynı İstanbul günü, sıra devam eder


def test_bos_sepet(con, simdi):
    m = musteri(con, simdi)
    sid = sepet_bul(con, None, m.id, simdi)
    with pytest.raises(SepetBos):
        siparis_olustur(con, m, sid, TeslimYontemi.KARGO, ADRES_TR, ADRES_TR, KUR, simdi)
    p = urun_ekle(con, sku="PASIF")
    ekle(con, sid, p)
    con.execute("UPDATE urun SET aktif = 0 WHERE id = ?", (p,))
    with pytest.raises(SepetBos):                     # yalnız düşen ürün varsa da boş sayılır
        siparis_olustur(con, m, sid, TeslimYontemi.KARGO, ADRES_TR, ADRES_TR, KUR, simdi)


def test_izinli_gecis_tablosu():
    assert IZINLI_GECISLER == {
        D.ODEME_BEKLIYOR: {D.ODENDI, D.IPTAL},
        D.ODENDI: {D.HAZIRLANIYOR, D.IPTAL},
        D.HAZIRLANIYOR: {D.KARGODA},
        D.KARGODA: {D.TESLIM},
        D.TESLIM: set(),
        D.IPTAL: set(),
        D.SURESI_DOLDU: {D.ODEME_BEKLIYOR, D.ODENDI, D.IPTAL},   # G3g madde 4 (türetilen durum)
    }
    assert ODEME_SURESI == timedelta(minutes=30)


# G3g: "süresi doldu" veritabanına yazılmaz (havale son tarihinden türetilir); geçişleri test_web_g3g'de
IZINLI = [(a, b) for a, hedefler in IZINLI_GECISLER.items() if a is not D.SURESI_DOLDU for b in sorted(hedefler)]
IZINSIZ = [
    (D.ODEME_BEKLIYOR, D.HAZIRLANIYOR), (D.ODEME_BEKLIYOR, D.TESLIM), (D.ODENDI, D.ODEME_BEKLIYOR),
    (D.ODENDI, D.TESLIM), (D.ODENDI, D.ODENDI), (D.HAZIRLANIYOR, D.IPTAL), (D.KARGODA, D.HAZIRLANIYOR),
    (D.TESLIM, D.IPTAL), (D.IPTAL, D.ODENDI), (D.IPTAL, D.ODEME_BEKLIYOR),
]


@pytest.mark.parametrize("eski,yeni", IZINLI, ids=[f"{a}-{b}" for a, b in IZINLI])
def test_izinli_gecis(con, simdi, eski, yeni):
    s = yeni_siparis(con, simdi)
    con.execute("UPDATE siparis SET durum = ? WHERE id = ?", (eski.value, s.id))
    sonra = simdi + timedelta(minutes=5)
    assert durum_degistir(con, s.id, yeni, sonra).durum is yeni
    assert con.execute("SELECT guncelleme FROM siparis WHERE id = ?", (s.id,)).fetchone()[0] == sonra.isoformat()


@pytest.mark.parametrize("eski,yeni", IZINSIZ, ids=[f"{a}-{b}" for a, b in IZINSIZ])
def test_izinsiz_gecis(con, simdi, eski, yeni):
    s = yeni_siparis(con, simdi)
    con.execute("UPDATE siparis SET durum = ? WHERE id = ?", (eski.value, s.id))
    with pytest.raises(GecersizGecis):
        durum_degistir(con, s.id, yeni, simdi)
    assert siparis_getir(con, s.id, simdi).durum is eski


def test_durum_degistir_olmayan_siparis(con, simdi):
    with pytest.raises(LookupError):
        durum_degistir(con, 99999, D.ODENDI, simdi)


def test_zaman_asimi(con, simdi):
    m = musteri(con, simdi)
    s = yeni_siparis(con, simdi, m)
    assert siparis_getir(con, s.id, simdi + timedelta(minutes=29)).durum is D.ODEME_BEKLIYOR
    assert siparis_getir(con, s.id, simdi + ODEME_SURESI).durum is D.ODEME_BEKLIYOR
    assert siparis_getir(con, s.id, simdi + timedelta(minutes=31)).durum is D.IPTAL
    # sepet korunur
    assert con.execute("SELECT COUNT(*) FROM sepet_kalemi WHERE sepet_id = ?", (s.sepet_id,)).fetchone()[0] == 1
    # ödenmiş sipariş zaman aşımına uğramaz
    s2 = siparis_olustur(con, m, s.sepet_id, TeslimYontemi.KARGO, ADRES_TR, ADRES_TR, KUR, simdi)
    durum_degistir(con, s2.id, D.ODENDI, simdi + timedelta(minutes=1))
    zaman_asimi_uygula(con, s2.id, simdi + timedelta(hours=2))
    assert siparis_getir(con, s2.id, simdi + timedelta(hours=2)).durum is D.ODENDI
    assert siparis_getir(con, 99999, simdi) is None


def test_durum_degistir_arada_degisirse(con, simdi):
    s = yeni_siparis(con, simdi)

    class Araya:
        def __init__(self, c):
            self.c = c

        def execute(self, sql, *a):
            r = self.c.execute(sql, *a)
            if sql.startswith("SELECT durum FROM siparis"):
                self.c.execute("UPDATE siparis SET durum = 'iptal' WHERE id = ?", (s.id,))
            return r

    with pytest.raises(GecersizGecis):
        durum_degistir(Araya(con), s.id, D.ODENDI, simdi)
    assert siparis_getir(con, s.id, simdi).durum is D.IPTAL
