from dataclasses import replace

import pytest

from app.fiyat.kurallar import MusteriTipi
from app.hesap.dogrulama import tckn_gecerli, vkn_gecerli
from app.hesap.servis import (
    Adres,
    KayitGirdisi,
    KayitHatasi,
    Musteri,
    adres_kaydet,
    adres_son,
    giris,
    kayit_ol,
    musteri_getir,
    parola_dogru,
    parola_ozeti,
)

GECERLI_VKN = "1234567890"
GECERLI_TCKN = "10000000146"
PAROLA = "demo-parola-123"


def girdi(tip, **kw):
    taban = {
        MusteriTipi.BIREYSEL: dict(ad="QATestUser Bireysel", eposta="qa.bireysel@example.com", ulke="TR"),
        MusteriTipi.KURUMSAL: dict(
            ad="QATestUser Ltd", eposta="qa.kurumsal@example.com", ulke="TR",
            vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Kocaeli",
        ),
        MusteriTipi.YURTDISI: dict(
            ad="QATestUser GmbH", eposta="qa.yurtdisi@example.com", ulke="DE", vat_id="DE123456789",
        ),
    }[tip]
    alanlar = dict(tip=tip, parola=PAROLA, kvkk_onay=True, **taban)
    alanlar.update(kw)
    return KayitGirdisi(**alanlar)


def hata(con, simdi, g):
    with pytest.raises(KayitHatasi) as e:
        kayit_ol(con, g, simdi)
    return (e.value.alan, e.value.kod)


def musteri_sayisi(con):
    return con.execute("SELECT COUNT(*) FROM musteri").fetchone()[0]


def test_ornek_numaralar():
    assert vkn_gecerli(GECERLI_VKN) and vkn_gecerli("4728136592") and tckn_gecerli(GECERLI_TCKN)
    assert not vkn_gecerli("1234567891") and not vkn_gecerli("4728136593")
    assert not tckn_gecerli("10000000145")


def test_bireysel_kayit(con, simdi):
    m = kayit_ol(con, girdi(MusteriTipi.BIREYSEL, iys_onay=True, vergi_kimlik_no=GECERLI_VKN), simdi)
    assert isinstance(m, Musteri) and m.tip is MusteriTipi.BIREYSEL
    assert m.ulke == "TR" and m.iys_onay is True
    assert (m.vergi_kimlik_no, m.vergi_dairesi, m.vat_id) == (None, None, None)
    r = con.execute("SELECT kvkk_onay, olusturma, parola_ozeti FROM musteri WHERE id = ?", (m.id,)).fetchone()
    assert r["kvkk_onay"] == simdi.isoformat() and r["olusturma"] == simdi.isoformat()
    assert PAROLA not in r["parola_ozeti"] and parola_dogru(PAROLA, r["parola_ozeti"])
    assert musteri_getir(con, m.id) == m
    assert musteri_getir(con, 99999) is None


def test_bireysel_ulke_tr_zorlanir(con, simdi):
    assert kayit_ol(con, girdi(MusteriTipi.BIREYSEL, ulke="de"), simdi).ulke == "TR"


def test_kurumsal_vkn_veya_tckn(con, simdi):
    m1 = kayit_ol(con, girdi(MusteriTipi.KURUMSAL, iys_onay=True), simdi)
    assert m1.tip is MusteriTipi.KURUMSAL
    assert (m1.vergi_kimlik_no, m1.vergi_dairesi, m1.ulke, m1.iys_onay) == (GECERLI_VKN, "Kocaeli", "TR", False)
    m3 = kayit_ol(con, girdi(MusteriTipi.KURUMSAL, eposta="qa.k3@example.com", vergi_kimlik_no="4728136592"), simdi)
    assert m3.vergi_kimlik_no == "4728136592"
    m2 = kayit_ol(
        con,
        girdi(MusteriTipi.KURUMSAL, eposta="qa.sahis@example.com", vergi_kimlik_no=" 100 000 001 46 ", ulke="DE"),
        simdi,
    )
    assert (m2.vergi_kimlik_no, m2.ulke) == (GECERLI_TCKN, "TR")


@pytest.mark.parametrize("vkn,kod", [
    # G3m madde 26: hane sayısı doğru (10 / 11 rakam) ama doğrulama basamağı tutmuyor: ayrı kod
    ("1234567891", "vkn_basamak"), ("4728136593", "vkn_basamak"), ("10000000145", "vkn_basamak"),
    ("123456789", "gecersiz_vkn"), ("123456789012", "gecersiz_vkn"), ("12345abcde", "gecersiz_vkn"),
    ("01234567890", "gecersiz_vkn"),     # G3m inceleme m8: TCKN 0 ile başlamaz (biçim)
])
def test_kurumsal_gecersiz_vergi_no(con, simdi, vkn, kod):
    assert hata(con, simdi, girdi(MusteriTipi.KURUMSAL, vergi_kimlik_no=vkn)) == ("vergi_kimlik_no", kod)
    assert musteri_sayisi(con) == 0


def test_kurumsal_zorunlu_alanlar(con, simdi):
    assert hata(con, simdi, girdi(MusteriTipi.KURUMSAL, vergi_kimlik_no=None)) == ("vergi_kimlik_no", "zorunlu")
    assert hata(con, simdi, girdi(MusteriTipi.KURUMSAL, vergi_kimlik_no="   ")) == ("vergi_kimlik_no", "zorunlu")
    assert hata(con, simdi, girdi(MusteriTipi.KURUMSAL, vergi_dairesi=" ")) == ("vergi_dairesi", "zorunlu")
    assert hata(con, simdi, girdi(MusteriTipi.KURUMSAL, vergi_dairesi=None)) == ("vergi_dairesi", "zorunlu")


def test_yurtdisi_kayit_iys_zorla_false(con, simdi):
    m = kayit_ol(con, girdi(MusteriTipi.YURTDISI, ulke=" de ", iys_onay=True), simdi)
    assert (m.tip, m.ulke, m.iys_onay, m.vat_id) == (MusteriTipi.YURTDISI, "DE", False, "DE123456789")
    assert con.execute("SELECT iys_onay FROM musteri WHERE id = ?", (m.id,)).fetchone()[0] == 0
    m2 = kayit_ol(con, girdi(MusteriTipi.YURTDISI, eposta="qa.fr@example.com", ulke="FR", vat_id="  "), simdi)
    assert m2.vat_id is None


@pytest.mark.parametrize("ulke", ["TR", "tr", "DEU", "1A", "D"])
def test_yurtdisi_gecersiz_ulke(con, simdi, ulke):
    assert hata(con, simdi, girdi(MusteriTipi.YURTDISI, ulke=ulke)) == ("ulke", "gecersiz")


def test_yurtdisi_ulke_zorunlu(con, simdi):
    assert hata(con, simdi, girdi(MusteriTipi.YURTDISI, ulke="  ")) == ("ulke", "zorunlu")


def test_eposta_tekrari_buyuk_kucuk_harf_duyarsiz(con, simdi):
    kayit_ol(con, girdi(MusteriTipi.BIREYSEL), simdi)
    g = girdi(MusteriTipi.KURUMSAL, eposta="  QA.Bireysel@Example.COM ")
    assert hata(con, simdi, g) == ("eposta", "eposta_kayitli")
    assert musteri_sayisi(con) == 1


def test_eposta_bicimi(con, simdi):
    assert hata(con, simdi, girdi(MusteriTipi.BIREYSEL, eposta="   ")) == ("eposta", "zorunlu")
    assert hata(con, simdi, girdi(MusteriTipi.BIREYSEL, eposta="qa.example.com")) == ("eposta", "gecersiz")


def test_kisa_parola(con, simdi):
    assert hata(con, simdi, girdi(MusteriTipi.BIREYSEL, parola="123456789")) == ("parola", "parola_kisa")
    assert kayit_ol(con, girdi(MusteriTipi.BIREYSEL, parola="1234567890"), simdi).id > 0


def test_kvkk_onay_yok(con, simdi):
    assert hata(con, simdi, girdi(MusteriTipi.BIREYSEL, kvkk_onay=False)) == ("kvkk_onay", "kvkk_onay_yok")
    assert musteri_sayisi(con) == 0


def test_ad_zorunlu(con, simdi):
    assert hata(con, simdi, girdi(MusteriTipi.BIREYSEL, ad="  ")) == ("ad", "zorunlu")


def test_parola_ozeti_bicimi_ve_dogrulama():
    oz = parola_ozeti(PAROLA)
    parcalar = oz.split("$")
    assert len(parcalar) == 6 and parcalar[:4] == ["scrypt", "16384", "8", "1"]
    assert len(parcalar[4]) == 32 and len(parcalar[5]) == 64
    int(parcalar[4], 16)
    int(parcalar[5], 16)
    assert parola_ozeti(PAROLA) != oz                    # tuz her seferinde farklı
    assert parola_dogru(PAROLA, oz) is True
    assert parola_dogru("demo-parola-124", oz) is False


@pytest.mark.parametrize(
    "ozet",
    [
        "", "bozuk", "scrypt$16384$8$1$zz$00", "scrypt$16384$8$1$abcd", "scrypt$x$8$1$00$00",
        "md5$16384$8$1$00$00", "scrypt$16384$8$1$$", "scrypt$1048576$8$1$00112233$0011", None,
    ],
)
def test_bozuk_ozet_false_doner(ozet):
    assert parola_dogru(PAROLA, ozet) is False


def test_giris(con, simdi):
    m = kayit_ol(con, girdi(MusteriTipi.BIREYSEL, eposta="QA.Giris@Example.com"), simdi)
    assert m.eposta == "qa.giris@example.com"
    assert giris(con, "qa.giris@example.com", PAROLA) == m
    assert giris(con, "  QA.GIRIS@EXAMPLE.COM ", PAROLA) == m
    assert giris(con, "qa.giris@example.com", "yanlis-parola-1") is None
    assert giris(con, "yok@example.com", PAROLA) is None
    assert giris(con, "", "") is None


ADRES1 = Adres(ad_soyad="QATestUser Bir", satir1="Demo Cad. 1", sehir="Kocaeli", ulke="tr", posta_kodu="41400")
ADRES2 = Adres(ad_soyad="QATestUser İki", satir1="Demo Sok. 2", sehir="İstanbul", ulke="TR", telefon="+90 500 000 00 00")


def test_adres_kaydet_ve_son(con, simdi):
    m = kayit_ol(con, girdi(MusteriTipi.BIREYSEL), simdi)
    assert adres_son(con, m.id, "teslimat") is None
    i1 = adres_kaydet(con, m.id, "teslimat", ADRES1)
    i2 = adres_kaydet(con, m.id, "teslimat", ADRES2)
    assert i2 > i1
    assert adres_son(con, m.id, "teslimat") == ADRES2
    assert adres_son(con, m.id, "fatura") is None
    adres_kaydet(con, m.id, "fatura", replace(ADRES1, satir2="  ", sehir=" Kocaeli "))
    assert adres_son(con, m.id, "fatura") == replace(ADRES1, ulke="TR")


def test_adres_gecersiz(con, simdi):
    m = kayit_ol(con, girdi(MusteriTipi.BIREYSEL), simdi)
    with pytest.raises(ValueError):
        adres_kaydet(con, m.id, "ev", ADRES1)
    with pytest.raises(KayitHatasi) as e:
        adres_kaydet(con, m.id, "teslimat", replace(ADRES1, satir1="  "))
    assert (e.value.alan, e.value.kod) == ("satir1", "zorunlu")
    assert con.execute("SELECT COUNT(*) FROM adres").fetchone()[0] == 0


def test_giris_kayitsiz_eposta_yine_de_scrypt_calistirir(con, simdi, monkeypatch):
    import app.hesap.servis as s

    cagrilar = []
    gercek = s.parola_dogru
    monkeypatch.setattr(s, "parola_dogru", lambda p, o: cagrilar.append(o) or gercek(p, o))
    assert giris(con, "yok@example.com", PAROLA) is None
    assert len(cagrilar) == 1


def test_parola_repr_de_gorunmez():
    assert PAROLA not in repr(girdi(MusteriTipi.BIREYSEL))


def test_parola_ust_sinir_ve_gecersiz_karakter(con, simdi):
    assert kayit_ol(con, girdi(MusteriTipi.BIREYSEL, parola="a" * 256), simdi).id > 0
    assert hata(con, simdi, girdi(MusteriTipi.KURUMSAL, parola="a" * 257)) == ("parola", "parola_uzun")
    assert hata(con, simdi, girdi(MusteriTipi.KURUMSAL, parola="abcdefghij\ud800")) == ("parola", "gecersiz")
    assert musteri_sayisi(con) == 1
    assert parola_dogru("abcdefghij\ud800", parola_ozeti(PAROLA)) is False
    with pytest.raises(KayitHatasi):
        parola_ozeti("a" * 257)
