"""Fiyat, KDV, para birimi, kargo ve teklif kuralları (saf fonksiyonlar)."""
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from pathlib import Path

import yaml

from app.metin import normalize
from app.para import d, yuvarla

TEKLIF_ESIGI_EUR = Decimal("15000")
KARGO_TR_NET_EUR = Decimal("15.00")
KARGO_KDV_ORANI = Decimal("20")
SIFIR = Decimal("0.00")


class KurYok(ValueError):
    """TRY tahsilat/gösterim için kur gerekiyor ama yok. Web katmanı yakalar."""


class MusteriTipi(StrEnum):
    BIREYSEL = "bireysel"
    KURUMSAL = "kurumsal"
    YURTDISI = "yurtdisi"


class TeslimYontemi(StrEnum):
    KARGO = "kargo"
    FABRIKA = "fabrika"
    YURTDISI_DAP = "yurtdisi_dap"


@dataclass(frozen=True)
class Bantlar:
    robot_kokleri: frozenset[str]
    bantlar: Mapping[str, tuple[Decimal, Decimal]]
    varsayilan: tuple[Decimal, Decimal]


def _aralik(deger: list) -> tuple[Decimal, Decimal]:
    alt, ust = (d(str(x)) for x in deger)
    if alt > ust:
        raise ValueError(f"bant alt sınırı üst sınırdan büyük: {deger}")
    return alt, ust


def bantlari_oku(yol: Path) -> Bantlar:
    ham = yaml.safe_load(Path(yol).read_text(encoding="utf-8"))
    return Bantlar(
        robot_kokleri=frozenset(normalize(k) for k in ham["robot_kokleri"]),
        bantlar={normalize(k): _aralik(v) for k, v in ham["bantlar"].items()},
        varsayilan=_aralik(ham["varsayilan"]),
    )


def temsili_fiyat_eur(sku: str, kok_kategori_ad: str, bantlar: Bantlar) -> Decimal:
    alt, ust = bantlar.bantlar.get(normalize(kok_kategori_ad), bantlar.varsayilan)
    ozet = hashlib.sha256(sku.encode("utf-8")).digest()[:8]
    oran = Decimal(int.from_bytes(ozet, "big")) / Decimal(2**64)
    ham = alt + oran * (ust - alt)
    return ham.quantize(Decimal("1"), rounding=ROUND_HALF_UP).quantize(Decimal("0.01"))


def teklif_zorunlu_mu(kok_kategori_ad: str, net_eur: Decimal, bantlar: Bantlar) -> bool:
    return normalize(kok_kategori_ad) in bantlar.robot_kokleri or net_eur > TEKLIF_ESIGI_EUR


# G3j madde 4: Türkiye'de geçerli KDV oranları. Kaynakta başka oran (ör. 80) gelen ürün doğrudan satılmaz: fiyat yerine
# "Fiyat teklifle (KDV oranı teyit ediliyor)", sepete eklenmez. Veri değiştirilmez; yönetimde "Veri kalitesi" sayfası.
GECERLI_KDV_ORANLARI = frozenset({Decimal("0"), Decimal("1"), Decimal("10"), Decimal("20")})


def kdv_gecerli(oran: object) -> bool:
    try:
        return Decimal(str(oran)) in GECERLI_KDV_ORANLARI
    except (ArithmeticError, ValueError):
        return False


def kdv_gecersiz_sql(tablo: str = "u") -> str:
    """SQL ifadesi: ürünün KDV oranı geçerli oranlardan biri değil (metin sütunu sayıya çevrilir)."""
    return f"(CAST({tablo}.kdv_orani AS REAL) NOT IN (0, 1, 10, 20))"


FIYAT_GOSTERIMLERI = ("try", "eur")   # G3i madde 2: ziyaretçinin seçtiği fiyat gösterimi (₺ KDV dahil | € KDV hariç)


@dataclass(frozen=True)
class Baglam:
    musteri_tipi: MusteriTipi
    teslimat_ulkesi: str
    # G3i madde 2: açık gösterim tercihi ("try": ₺, TR teslimde KDV dahil; "eur": € KDV hariç). None: müşteri tipinin
    # varsayılanı. Yalnız GÖSTERİMİ etkiler; tahsilat para birimi ve tutar hesabı (sepet_hesapla) değişmez.
    gosterim: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "teslimat_ulkesi", self.teslimat_ulkesi.strip().upper())


def kdv_uygulanir(b: Baglam) -> bool:
    return b.teslimat_ulkesi == "TR"


def tahsilat_para_birimi(b: Baglam) -> str:
    if b.musteri_tipi == MusteriTipi.BIREYSEL:
        return "TRY"
    if b.musteri_tipi == MusteriTipi.KURUMSAL:
        return "TRY" if b.teslimat_ulkesi == "TR" else "EUR"
    return "EUR"


def gosterim_kdv_dahil(b: Baglam) -> bool:
    if b.gosterim == "eur":
        return False
    if b.gosterim == "try":
        return kdv_uygulanir(b)
    return b.musteri_tipi == MusteriTipi.BIREYSEL and kdv_uygulanir(b)


@dataclass(frozen=True)
class Kalem:
    urun_id: int
    sku: str
    ad: str
    adet: int
    birim_net_eur: Decimal
    kdv_orani: Decimal
    tedarik_teyit: bool = False


@dataclass(frozen=True)
class SatirTutar:
    kalem: Kalem
    net: Decimal
    kdv: Decimal
    brut: Decimal


@dataclass(frozen=True)
class SepetTutari:
    para_birimi: str
    satirlar: tuple[SatirTutar, ...]
    ara_toplam: Decimal
    kdv: Decimal
    kargo_net: Decimal
    kargo_kdv: Decimal
    toplam: Decimal
    kur: Decimal | None
    ihracat_istisnasi: bool


def sepet_hesapla(kalemler: Sequence[Kalem], b: Baglam, teslim: TeslimYontemi,
                  kur_eur_try: Decimal | None) -> SepetTutari:
    para = tahsilat_para_birimi(b)
    if para == "TRY":
        if kur_eur_try is None:
            raise KurYok("kur_yok")
        return _hesapla(kalemler, b, teslim, "TRY", kur_eur_try)
    return _hesapla(kalemler, b, teslim, "EUR", None)


def sepet_hesapla_eur(kalemler: Sequence[Kalem], b: Baglam, teslim: TeslimYontemi) -> SepetTutari:
    """G3a Ö1: TRY tahsilatta kur yokken gösterim yedeği — aynı KDV/kargo kuralları, tutarlar EUR.
    Tahsilat tutarı DEĞİLDİR; sipariş bu tutarla oluşturulmaz."""
    return _hesapla(kalemler, b, teslim, "EUR", None)


def _hesapla(kalemler: Sequence[Kalem], b: Baglam, teslim: TeslimYontemi, para: str,
             kur: Decimal | None) -> SepetTutari:
    carpan = kur if kur is not None else Decimal("1")
    kdv_var = kdv_uygulanir(b)

    satirlar: list[SatirTutar] = []
    for k in kalemler:
        net = yuvarla(k.birim_net_eur * k.adet * carpan)
        kdv = yuvarla(net * k.kdv_orani / 100) if kdv_var else SIFIR
        satirlar.append(SatirTutar(kalem=k, net=net, kdv=kdv, brut=net + kdv))

    if teslim == TeslimYontemi.KARGO and b.teslimat_ulkesi == "TR":
        kargo_net = yuvarla(KARGO_TR_NET_EUR * carpan)
        kargo_kdv = yuvarla(kargo_net * KARGO_KDV_ORANI / 100)
    else:
        kargo_net = SIFIR
        kargo_kdv = SIFIR

    ara_toplam = sum((s.net for s in satirlar), SIFIR)
    kdv_toplam = sum((s.kdv for s in satirlar), SIFIR) + kargo_kdv
    return SepetTutari(
        para_birimi=para,
        satirlar=tuple(satirlar),
        ara_toplam=ara_toplam,
        kdv=kdv_toplam,
        kargo_net=kargo_net,
        kargo_kdv=kargo_kdv,
        toplam=ara_toplam + kargo_net + kdv_toplam,
        kur=kur,
        ihracat_istisnasi=not kdv_var,
    )


@dataclass(frozen=True)
class FiyatGosterim:
    ana_tutar: Decimal
    ana_para: str
    kdv_dahil: bool
    ikincil_tutar: Decimal | None
    ikincil_para: str | None


def _net_tutar(net_eur: Decimal, para: str, kur_eur_try: Decimal | None) -> Decimal:
    """Birim net tutar gösterim para biriminde (birim gösterimi ve KDV karşılığı aynı yuvarlamayı kullanır)."""
    if para == "TRY":
        if kur_eur_try is None:
            raise KurYok("kur_yok")
        return yuvarla(net_eur * kur_eur_try)
    return yuvarla(net_eur)


def _kdv_dahil(net: Decimal, kdv_orani: Decimal) -> Decimal:
    return net + yuvarla(net * kdv_orani / 100)


def birim_fiyat_gosterimi(net_eur: Decimal, kdv_orani: Decimal, b: Baglam,
                          kur_eur_try: Decimal | None) -> FiyatGosterim:
    eur_net = yuvarla(net_eur)
    yalniz_eur = FiyatGosterim(eur_net, "EUR", False, None, None)
    if b.gosterim == "eur":           # G3i madde 2: € KDV hariç ana, kur varsa ₺ KDV hariç ikincil
        if kur_eur_try is None or b.teslimat_ulkesi != "TR":   # G3j madde 12: yurt dışında ₺ ikincil yok
            return yalniz_eur
        return FiyatGosterim(eur_net, "EUR", False, yuvarla(net_eur * kur_eur_try), "TRY")
    if b.gosterim == "try":           # ₺ ana (TR teslimde KDV dahil), € KDV hariç ikincil
        if kur_eur_try is None:
            return yalniz_eur
        try_net = _net_tutar(net_eur, "TRY", kur_eur_try)
        if kdv_uygulanir(b):
            return FiyatGosterim(_kdv_dahil(try_net, kdv_orani), "TRY", True, eur_net, "EUR")
        return FiyatGosterim(try_net, "TRY", False, eur_net, "EUR")
    if b.musteri_tipi == MusteriTipi.KURUMSAL:
        # EUR net, kur varsa TRY net ikincil. G3j madde 12: teslim Türkiye dışındaysa ₺ ikincil (ve kur satırı) yok
        if kur_eur_try is None or b.teslimat_ulkesi != "TR":
            return yalniz_eur
        return FiyatGosterim(eur_net, "EUR", False, yuvarla(net_eur * kur_eur_try), "TRY")
    if tahsilat_para_birimi(b) == "EUR":
        return yalniz_eur
    if kur_eur_try is None:
        return yalniz_eur        # TRY gerekiyor ama kur yok: EUR net, kdv_dahil=False
    try_net = _net_tutar(net_eur, "TRY", kur_eur_try)
    if gosterim_kdv_dahil(b):
        return FiyatGosterim(_kdv_dahil(try_net, kdv_orani), "TRY", True, eur_net, "EUR")
    return FiyatGosterim(try_net, "TRY", False, eur_net, "EUR")   # bireysel, teslimat TR dışı


def kdv_karsiligi(net_eur: Decimal, kdv_orani: Decimal, b: Baglam, kur_eur_try: Decimal | None,
                  g: FiyatGosterim) -> tuple[Decimal, str, bool] | None:
    """G3b madde 12: ana fiyatın KDV'li/KDV'siz karşılığı, AYNI para biriminde: (tutar, para, kdv_dahil).
    Ana fiyat KDV dahilse KDV hariç tutar, değilse KDV dahil tutar döner. KDV uygulanmıyorsa (TR dışı teslim) None.
    Yuvarlama sepet ve birim gösterimiyle aynıdır: net = yuvarla(net_eur × kur), KDV = yuvarla(net × oran / 100)."""
    if not kdv_uygulanir(b):
        return None
    net = _net_tutar(net_eur, g.ana_para, kur_eur_try)
    if g.kdv_dahil:
        return net, g.ana_para, False
    return _kdv_dahil(net, kdv_orani), g.ana_para, True


def gosterim_kipi(b: Baglam, kur_eur_try: Decimal | None) -> tuple[str, Decimal, bool]:
    """G3e madde 9: ziyaretçinin listede gördüğü fiyatın kipi: (para birimi, net EUR'dan çarpan, KDV dahil mi).
    birim_fiyat_gosterimi ile aynı kural (ana tutar); fiyat aralığı filtresi bu kipte girilir."""
    g = birim_fiyat_gosterimi(Decimal("1"), Decimal("0"), b, kur_eur_try)
    carpan = kur_eur_try if g.ana_para == "TRY" and kur_eur_try is not None else Decimal("1")
    return g.ana_para, carpan, g.kdv_dahil
