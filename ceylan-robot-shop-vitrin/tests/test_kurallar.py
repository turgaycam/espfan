from decimal import Decimal

import pytest

from app.fiyat.kurallar import (
    KARGO_TR_NET_EUR,
    TEKLIF_ESIGI_EUR,
    Baglam,
    FiyatGosterim,
    KurYok,
    Kalem,
    MusteriTipi,
    TeslimYontemi,
    birim_fiyat_gosterimi,
    gosterim_kdv_dahil,
    kdv_uygulanir,
    sepet_hesapla,
    tahsilat_para_birimi,
    temsili_fiyat_eur,
    teklif_zorunlu_mu,
)

KUR = Decimal("48.2101")
D = Decimal


def kalem(birim="100.00", adet=1, kdv="20", urun_id=1, sku="S1"):
    return Kalem(urun_id=urun_id, sku=sku, ad="Ürün " + sku, adet=adet,
                 birim_net_eur=D(birim), kdv_orani=D(kdv))


# ---- bantlar ----

def test_bantlar_okunur(bantlar):
    assert bantlar.robot_kokleri == frozenset({"endustriyel robotlar", "pozisyonerler"})
    assert bantlar.bantlar["endustriyel robotlar"] == (D("8000"), D("45000"))
    assert bantlar.varsayilan == (D("50"), D("2000"))


# ---- temsili fiyat ----

def test_temsili_fiyat_deterministik(bantlar):
    a = temsili_fiyat_eur("8102030100019", "Elektrik ve Elektronik", bantlar)
    b = temsili_fiyat_eur("8102030100019", "Elektrik ve Elektronik", bantlar)
    assert a == b == D("511.00")
    assert str(a) == "511.00"


def test_temsili_fiyat_bilinen_degerler(bantlar):
    # sha256("8301033800019")[:8] / 2^64 = 0.20310475...; 8000 + 0.20310475*37000 = 15514.876 -> 15515
    assert temsili_fiyat_eur("8301033800019", "Endüstriyel Robotlar", bantlar) == D("15515.00")


@pytest.mark.parametrize("kok,alt,ust", [
    ("Endüstriyel Robotlar", 8000, 45000),
    ("ENDÜSTRİYEL ROBOTLAR", 8000, 45000),
    ("Mekanik", 15, 900),
    ("ABB REDÜKTÖR", 400, 6000),
    ("Bilinmeyen Kök", 50, 2000),
    ("", 50, 2000),
])
def test_temsili_fiyat_bant_icinde(bantlar, kok, alt, ust):
    for i in range(200):
        f = temsili_fiyat_eur(f"SKU{i:05d}", kok, bantlar)
        assert D(alt) <= f <= D(ust)
        assert f == f.quantize(D("1"))
        assert f.as_tuple().exponent == -2


# ---- teklif kuralı ----

def test_teklif_robot_koku(bantlar):
    assert teklif_zorunlu_mu("Endüstriyel Robotlar", D("10.00"), bantlar) is True
    assert teklif_zorunlu_mu("POZİSYONERLER", D("10.00"), bantlar) is True
    assert teklif_zorunlu_mu("Robotik Parçaları", D("10.00"), bantlar) is False


def test_teklif_esigi_tam_sinir(bantlar):
    assert TEKLIF_ESIGI_EUR == D("15000")
    assert teklif_zorunlu_mu("Mekanik", D("15000.00"), bantlar) is False
    assert teklif_zorunlu_mu("Mekanik", D("15000.01"), bantlar) is True


# ---- bağlam kuralları ----

def test_baglam_yardimcilari():
    tr_bir = Baglam(MusteriTipi.BIREYSEL, "TR")
    assert kdv_uygulanir(tr_bir) and gosterim_kdv_dahil(tr_bir)
    tr_kur = Baglam(MusteriTipi.KURUMSAL, "TR")
    assert kdv_uygulanir(tr_kur) and not gosterim_kdv_dahil(tr_kur)
    assert not gosterim_kdv_dahil(Baglam(MusteriTipi.BIREYSEL, "DE"))
    assert tahsilat_para_birimi(Baglam(MusteriTipi.KURUMSAL, "DE")) == "EUR"


# ---- §5.3 tahsilat tablosu: her satır ayrı test ----
# Ortak girdi: 1 kalem, birim 100.00 EUR net, KDV %20, kur 48.2101.
# TRY satır: net = 100.00*48.2101 = 4821.01 ; KDV = 964.202 -> 964.20
# TRY kargo: 15.00*48.2101 = 723.1515 -> 723.15 ; KDV = 144.63

def test_tablo_tr_bireysel_tr_teslim():
    t = sepet_hesapla([kalem()], Baglam(MusteriTipi.BIREYSEL, "TR"), TeslimYontemi.KARGO, KUR)
    assert t.para_birimi == "TRY" and t.kur == KUR and t.ihracat_istisnasi is False
    assert (t.ara_toplam, t.kargo_net, t.kargo_kdv) == (D("4821.01"), D("723.15"), D("144.63"))
    assert t.kdv == D("1108.83")          # 964.20 + 144.63
    assert t.toplam == D("6652.99")       # 4821.01 + 723.15 + 1108.83


def test_tablo_tr_bireysel_yurtdisi_teslim():
    t = sepet_hesapla([kalem()], Baglam(MusteriTipi.BIREYSEL, "DE"), TeslimYontemi.YURTDISI_DAP, KUR)
    assert t.para_birimi == "TRY" and t.ihracat_istisnasi is True
    assert t.kdv == D("0.00") and t.satirlar[0].kdv == D("0.00")
    assert t.kargo_net == D("0.00")
    assert t.toplam == D("4821.01")


def test_tablo_tr_kurumsal_tr_teslim():
    t = sepet_hesapla([kalem()], Baglam(MusteriTipi.KURUMSAL, "TR"), TeslimYontemi.KARGO, KUR)
    assert t.para_birimi == "TRY" and t.ihracat_istisnasi is False
    assert t.kdv == D("1108.83") and t.toplam == D("6652.99")


def test_tablo_tr_kurumsal_yurtdisi_teslim():
    t = sepet_hesapla([kalem()], Baglam(MusteriTipi.KURUMSAL, "DE"), TeslimYontemi.YURTDISI_DAP, KUR)
    assert t.para_birimi == "EUR" and t.kur is None and t.ihracat_istisnasi is True
    assert t.kdv == D("0.00") and t.toplam == D("100.00")


def test_tablo_yurtdisi_yurtdisi_teslim():
    t = sepet_hesapla([kalem()], Baglam(MusteriTipi.YURTDISI, "DE"), TeslimYontemi.YURTDISI_DAP, None)
    assert t.para_birimi == "EUR" and t.kur is None and t.ihracat_istisnasi is True
    assert t.kdv == D("0.00") and t.toplam == D("100.00")


def test_tablo_yurtdisi_hesap_tr_teslim():
    t = sepet_hesapla([kalem()], Baglam(MusteriTipi.YURTDISI, "TR"), TeslimYontemi.KARGO, None)
    assert t.para_birimi == "EUR" and t.kur is None and t.ihracat_istisnasi is False
    assert t.satirlar[0].kdv == D("20.00")
    assert (t.kargo_net, t.kargo_kdv) == (KARGO_TR_NET_EUR, D("3.00"))
    assert t.kdv == D("23.00") and t.toplam == D("138.00")   # 100 + 15 + 23


# ---- satır bazında yuvarlama sırası ----

def test_satir_bazinda_yuvarlama_sirasi():
    kalemler = [
        kalem("33.335", adet=3, urun_id=1, sku="A"),
        kalem("0.07", adet=1, urun_id=2, sku="B"),
        kalem("12.34", adet=1, urun_id=3, sku="C"),
    ]
    t = sepet_hesapla(kalemler, Baglam(MusteriTipi.BIREYSEL, "TR"), TeslimYontemi.KARGO, KUR)
    a, b, c = t.satirlar
    # A: 33.335*3 = 100.005 ; *48.2101 = 4821.2510505 -> 4821.25
    #    (birimi önce çevirip yuvarlasaydık: 1607.08*3 = 4821.24 olurdu)
    assert a.net == D("4821.25") and a.kdv == D("964.25") and a.brut == D("5785.50")
    # B: 0.07*48.2101 = 3.374707 -> 3.37 ; KDV 0.674 -> 0.67
    assert b.net == D("3.37") and b.kdv == D("0.67")
    # C: 12.34*48.2101 = 594.912634 -> 594.91 ; KDV 118.982 -> 118.98
    assert c.net == D("594.91") and c.kdv == D("118.98")
    assert t.ara_toplam == D("5419.53")
    # satır KDV toplamı 1083.90 ; toplam üzerinden hesaplansaydı 5419.53*0.2 = 1083.906 -> 1083.91 olurdu
    assert t.kdv == D("1228.53")          # 1083.90 + kargo KDV 144.63
    assert t.toplam == D("7371.21")       # 5419.53 + 723.15 + 1228.53


# ---- kargo ----

def test_kargo_uc_yontem():
    b = Baglam(MusteriTipi.KURUMSAL, "TR")
    kargo = sepet_hesapla([kalem()], b, TeslimYontemi.KARGO, KUR)
    assert (kargo.kargo_net, kargo.kargo_kdv) == (D("723.15"), D("144.63"))
    fabrika = sepet_hesapla([kalem()], b, TeslimYontemi.FABRIKA, KUR)
    assert (fabrika.kargo_net, fabrika.kargo_kdv) == (D("0.00"), D("0.00"))
    assert fabrika.toplam == D("5785.21")   # 4821.01 + 964.20
    dap = sepet_hesapla([kalem()], Baglam(MusteriTipi.YURTDISI, "DE"), TeslimYontemi.YURTDISI_DAP, None)
    assert (dap.kargo_net, dap.kargo_kdv) == (D("0.00"), D("0.00"))


def test_try_tahsilatta_kur_yoksa_hata():
    with pytest.raises(KurYok, match="kur_yok"):
        sepet_hesapla([kalem()], Baglam(MusteriTipi.BIREYSEL, "TR"), TeslimYontemi.KARGO, None)
    assert issubclass(KurYok, ValueError)
    with pytest.raises(KurYok, match="kur_yok"):
        sepet_hesapla([kalem()], Baglam(MusteriTipi.KURUMSAL, "TR"), TeslimYontemi.FABRIKA, None)


def test_bos_sepet_sifir():
    t = sepet_hesapla([], Baglam(MusteriTipi.YURTDISI, "DE"), TeslimYontemi.YURTDISI_DAP, None)
    assert t.satirlar == () and t.toplam == D("0.00")


# ---- birim fiyat gösterimi ----

def test_gosterim_bireysel_tr():
    g = birim_fiyat_gosterimi(D("100.00"), D("20"), Baglam(MusteriTipi.BIREYSEL, "TR"), KUR)
    # 4821.01 + 964.20 = 5785.21 TRY KDV dahil ; ikincil 100.00 EUR net
    assert g == FiyatGosterim(D("5785.21"), "TRY", True, D("100.00"), "EUR")


def test_gosterim_kurumsal_tr():
    g = birim_fiyat_gosterimi(D("100.00"), D("20"), Baglam(MusteriTipi.KURUMSAL, "TR"), KUR)
    assert g == FiyatGosterim(D("100.00"), "EUR", False, D("4821.01"), "TRY")


def test_gosterim_bireysel_yurtdisi_teslim():
    # §5.3 satır 2: TRY, KDV yok (ihracat), ikincil EUR net
    g = birim_fiyat_gosterimi(D("100.00"), D("20"), Baglam(MusteriTipi.BIREYSEL, "DE"), KUR)
    assert g == FiyatGosterim(D("4821.01"), "TRY", False, D("100.00"), "EUR")


def test_gosterim_kurumsal_yurtdisi_teslim():
    # G3j madde 12: teslim Türkiye dışındayken € gösterimde ₺ ikincil yok (önce: ₺ KDV hariç ikincil vardı)
    g = birim_fiyat_gosterimi(D("100.00"), D("20"), Baglam(MusteriTipi.KURUMSAL, "DE"), KUR)
    assert g == FiyatGosterim(D("100.00"), "EUR", False, None, None)


def test_gosterim_yurtdisi():
    g = birim_fiyat_gosterimi(D("100.00"), D("20"), Baglam(MusteriTipi.YURTDISI, "DE"), KUR)
    assert g == FiyatGosterim(D("100.00"), "EUR", False, None, None)


def test_gosterim_yurtdisi_hesap_tr_teslim():
    g = birim_fiyat_gosterimi(D("100.00"), D("20"), Baglam(MusteriTipi.YURTDISI, "TR"), KUR)
    assert g == FiyatGosterim(D("100.00"), "EUR", False, None, None)


@pytest.mark.parametrize("tip,ulke", [
    (MusteriTipi.BIREYSEL, "TR"), (MusteriTipi.BIREYSEL, "DE"),
    (MusteriTipi.KURUMSAL, "TR"), (MusteriTipi.KURUMSAL, "DE"),
])
def test_gosterim_kur_yoksa_eur_net(tip, ulke):
    g = birim_fiyat_gosterimi(D("100.00"), D("20"), Baglam(tip, ulke), None)
    assert g == FiyatGosterim(D("100.00"), "EUR", False, None, None)


# ---- K4: kargo yalnız teslimat TR iken ----

def test_kargo_yurtdisi_teslimatta_sifir():
    t = sepet_hesapla([kalem()], Baglam(MusteriTipi.BIREYSEL, "DE"), TeslimYontemi.KARGO, KUR)
    assert t.kargo_net == t.kargo_kdv == D("0.00")
    assert t.ihracat_istisnasi is True
    assert t.kdv == D("0.00")
    assert t.toplam == D("4821.01")


# ---- teslimat ülkesi büyük/küçük harfe duyarsız ----

def test_baglam_ulke_normalize():
    b = Baglam(MusteriTipi.BIREYSEL, " tr ")
    assert b.teslimat_ulkesi == "TR"
    assert kdv_uygulanir(Baglam(MusteriTipi.BIREYSEL, "tr"))
    assert tahsilat_para_birimi(Baglam(MusteriTipi.BIREYSEL, "tr")) == "TRY"
    assert tahsilat_para_birimi(Baglam(MusteriTipi.KURUMSAL, "tr")) == "TRY"
