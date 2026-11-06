"""Sipariş: sepetten anlık görüntü, sipariş numarası, durum makinesi, 30 dk zaman aşımı. Commit yapmaz."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from app.fiyat.kur import Kur
from app.fiyat.kurallar import Baglam, TeslimYontemi, sepet_hesapla
from app.hesap.servis import Adres, Musteri
from app.para import yuvarla
from app.sepet import servis as sepet_servis


class SiparisDurumu(StrEnum):
    ODEME_BEKLIYOR = "odeme_bekliyor"
    ODENDI = "odendi"
    HAZIRLANIYOR = "hazirlaniyor"
    KARGODA = "kargoda"
    TESLIM = "teslim"
    IPTAL = "iptal"
    # G3g madde 4: ödeme son tarihi geçmiş havale siparişi. Veritabanında durum 'odeme_bekliyor' kalır (son tarih
    # odeme_son_tarih sütununda); okunurken bu duruma çevrilir. Yönetim yeniden açabilir (yeni son tarih), geç gelen
    # ödemeyi "ödendi" yapabilir ya da iptal edebilir.
    SURESI_DOLDU = "suresi_doldu"


_D = SiparisDurumu
IZINLI_GECISLER: dict[SiparisDurumu, frozenset[SiparisDurumu]] = {
    _D.ODEME_BEKLIYOR: frozenset({_D.ODENDI, _D.IPTAL}),
    _D.ODENDI: frozenset({_D.HAZIRLANIYOR, _D.IPTAL}),
    _D.HAZIRLANIYOR: frozenset({_D.KARGODA}),
    _D.KARGODA: frozenset({_D.TESLIM}),
    _D.TESLIM: frozenset(),
    _D.IPTAL: frozenset(),
    _D.SURESI_DOLDU: frozenset({_D.ODEME_BEKLIYOR, _D.ODENDI, _D.IPTAL}),
}
from app.stok import HAVALE_GUN, ODEME_SURESI, ayrilan_adetler, havale_son_tarih  # noqa: E402  (ayırma tek yerde)
ODEME_YONTEMLERI = ("kart", "havale")   # G3e madde 15: havale yalnız kurumsal / yurt dışı (web katmanı denetler)
ISTANBUL = ZoneInfo("Europe/Istanbul")


class GecersizGecis(Exception):
    pass


class SepetBos(Exception):
    pass


class StokYetersiz(Exception):
    """G3e madde 1: sipariş anında (işlem içinde) bir kalemin adedi bilinen stoku aşıyor."""

    def __init__(self, kalemler: list[tuple[int, str, int]]):
        super().__init__(kalemler)
        self.kalemler = kalemler     # (urun_id, ad, stok)


@dataclass(frozen=True)
class SiparisKalemi:
    urun_id: int
    sku: str
    ad: str
    adet: int
    birim_net_eur: Decimal
    net: Decimal
    kdv: Decimal
    brut: Decimal
    tedarik_teyit: bool


@dataclass(frozen=True)
class Siparis:
    id: int
    no: str
    musteri_id: int
    durum: SiparisDurumu
    para_birimi: str
    ara_toplam: Decimal
    kdv: Decimal
    kargo: Decimal
    toplam: Decimal
    kur: Decimal | None
    kur_tarihi: date | None
    ihracat_istisnasi: bool
    teslim_yontemi: TeslimYontemi
    teslimat_ulkesi: str
    teslimat_adresi: Adres
    fatura_adresi: Adres
    kart_son4: str | None
    sepet_id: int
    olusturma: datetime
    kalemler: tuple[SiparisKalemi, ...]
    odeme_yontemi: str = "kart"          # G3e madde 15: 'kart' | 'havale'
    odeme_son_tarih: datetime | None = None   # G3g madde 4: havale ödeme son tarihi (UTC); kartta None
    musteri_po: str | None = None             # G3i madde 6: müşterinin satın alma (PO) numarası
    # G3i inceleme I-1: alıcının sipariş anındaki unvan, tip ve vergi bilgileri (G3i öncesi siparişte None)
    alici_unvan: str | None = None
    alici_tip: str | None = None
    alici_vkn: str | None = None
    alici_vergi_dairesi: str | None = None
    alici_vat_id: str | None = None
    odeme_zamani: datetime | None = None      # G3m inceleme m5: ödenmiş siparişte tahmini varışın bazı


def _para(x: Decimal) -> str:
    return str(yuvarla(x))


def _yeni_no(con: sqlite3.Connection, simdi: datetime) -> str:
    onek = f"CR-DEMO-{simdi.astimezone(ISTANBUL):%Y%m%d}-"      # K15: gün İstanbul saatine göre
    son = con.execute(
        "SELECT MAX(CAST(substr(no, ?) AS INTEGER)) FROM siparis WHERE no LIKE ?",
        (len(onek) + 1, onek + "%"),
    ).fetchone()[0]
    return f"{onek}{(son or 0) + 1:04d}"


def _adres(metin: str) -> Adres:
    return Adres(**json.loads(metin))


def _zaman(metin: str | None) -> datetime | None:
    if not metin:
        return None
    z = datetime.fromisoformat(metin)
    return z if z.tzinfo is not None else z.replace(tzinfo=UTC)


def _suresi_doldu(r: sqlite3.Row, simdi: datetime | None) -> bool:
    son = _zaman(r["odeme_son_tarih"])
    return (simdi is not None and r["durum"] == _D.ODEME_BEKLIYOR and r["odeme_yontemi"] == "havale"
            and son is not None and son <= simdi)


def _siparis(con: sqlite3.Connection, r: sqlite3.Row, simdi: datetime | None = None) -> Siparis:
    kalemler = tuple(
        SiparisKalemi(
            urun_id=k["urun_id"], sku=k["sku"], ad=k["ad"], adet=k["adet"],
            birim_net_eur=Decimal(k["birim_net_eur"]), net=Decimal(k["net"]), kdv=Decimal(k["kdv"]),
            brut=Decimal(k["brut"]), tedarik_teyit=bool(k["tedarik_teyit"]),
        )
        for k in con.execute("SELECT * FROM siparis_kalemi WHERE siparis_id = ? ORDER BY rowid", (r["id"],))
    )
    return Siparis(
        id=r["id"], no=r["no"], musteri_id=r["musteri_id"],
        durum=_D.SURESI_DOLDU if _suresi_doldu(r, simdi) else SiparisDurumu(r["durum"]),
        para_birimi=r["para_birimi"], ara_toplam=Decimal(r["ara_toplam"]), kdv=Decimal(r["kdv"]),
        kargo=Decimal(r["kargo"]), toplam=Decimal(r["toplam"]),
        kur=Decimal(r["kur"]) if r["kur"] is not None else None,
        kur_tarihi=date.fromisoformat(r["kur_tarihi"]) if r["kur_tarihi"] is not None else None,
        ihracat_istisnasi=bool(r["ihracat_istisnasi"]), teslim_yontemi=TeslimYontemi(r["teslim_yontemi"]),
        teslimat_ulkesi=r["teslimat_ulkesi"], teslimat_adresi=_adres(r["teslimat_adresi"]),
        fatura_adresi=_adres(r["fatura_adresi"]), kart_son4=r["kart_son4"], sepet_id=r["sepet_id"],
        olusturma=datetime.fromisoformat(r["olusturma"]), kalemler=kalemler, odeme_yontemi=r["odeme_yontemi"],
        odeme_son_tarih=_zaman(r["odeme_son_tarih"]), musteri_po=r["musteri_po"],
        alici_unvan=r["alici_unvan"], alici_tip=r["alici_tip"], alici_vkn=r["alici_vkn"],
        alici_vergi_dairesi=r["alici_vergi_dairesi"], alici_vat_id=r["alici_vat_id"],
        odeme_zamani=_zaman(r["odeme_zamani"]),
    )


def zaman_asimi_uygula(con: sqlite3.Connection, siparis_id: int, simdi: datetime) -> None:
    r = con.execute("SELECT durum, olusturma, odeme_yontemi FROM siparis WHERE id = ?", (siparis_id,)).fetchone()
    if r is None or r["durum"] != _D.ODEME_BEKLIYOR or r["odeme_yontemi"] == "havale":
        return   # havale/EFT siparişi ödeme gelene kadar bekler (yönetim "ödendi" ya da "iptal" yapar)
    if datetime.fromisoformat(r["olusturma"]) + ODEME_SURESI < simdi:
        con.execute(
            "UPDATE siparis SET durum = ?, guncelleme = ? WHERE id = ? AND durum = ?",
            (_D.IPTAL.value, simdi.isoformat(), siparis_id, _D.ODEME_BEKLIYOR.value),
        )


def siparis_getir(con: sqlite3.Connection, siparis_id: int, simdi: datetime) -> Siparis | None:
    zaman_asimi_uygula(con, siparis_id, simdi)
    r = con.execute("SELECT * FROM siparis WHERE id = ?", (siparis_id,)).fetchone()
    return _siparis(con, r, simdi) if r is not None else None


def siparis_no_ile(con: sqlite3.Connection, no: str, simdi: datetime) -> Siparis | None:
    r = con.execute("SELECT id FROM siparis WHERE no = ?", (no,)).fetchone()
    return siparis_getir(con, r["id"], simdi) if r is not None else None


def musteri_siparisleri(con: sqlite3.Connection, musteri_id: int, simdi: datetime) -> list[Siparis]:
    idler = [r["id"] for r in con.execute(
        "SELECT id FROM siparis WHERE musteri_id = ? ORDER BY id DESC", (musteri_id,)
    )]
    return [siparis_getir(con, i, simdi) for i in idler]


def son_siparis_adresleri(con: sqlite3.Connection, musteri_id: int) -> tuple[Adres, Adres] | None:
    """G3m madde 21: müşterinin son siparişindeki alıcı anlık görüntüsü (teslimat, fatura adresi) ya da None."""
    r = con.execute("SELECT teslimat_adresi, fatura_adresi FROM siparis WHERE musteri_id = ? ORDER BY id DESC LIMIT 1",
                    (musteri_id,)).fetchone()
    return (_adres(r["teslimat_adresi"]), _adres(r["fatura_adresi"])) if r is not None else None


def tum_siparisler(con: sqlite3.Connection, simdi: datetime) -> list[Siparis]:
    idler = [r["id"] for r in con.execute("SELECT id FROM siparis ORDER BY id DESC")]
    return [siparis_getir(con, i, simdi) for i in idler]


def siparis_olustur(
    con: sqlite3.Connection, musteri: Musteri, sepet_id: int, teslim: TeslimYontemi,
    teslimat: Adres, fatura: Adres, kur: Kur | None, simdi: datetime, odeme_yontemi: str = "kart",
    havale_gun: int = HAVALE_GUN, musteri_po: str | None = None,
) -> Siparis:
    if odeme_yontemi not in ODEME_YONTEMLERI:
        raise ValueError(odeme_yontemi)
    if not con.in_transaction:
        # G3e düzeltme 1 (I-3): stok denetimi ile sipariş yazımı arasında başka sipariş giremesin: yazma kilidi en başta
        con.execute("BEGIN IMMEDIATE")
    kalem_listesi, _dusen = sepet_servis.kalemler(con, sepet_id)
    if not kalem_listesi:
        raise SepetBos(sepet_id)
    # aynı işlemde: stok sepetten sonra azalmış ya da açık siparişlerce ayrılmış olabilir (G3e madde 1, düzeltme 1)
    ayrilan = ayrilan_adetler(con, simdi)
    asanlar = []
    for r in con.execute("SELECT k.urun_id, k.adet, u.stok, u.ad FROM sepet_kalemi k JOIN urun u ON u.id = k.urun_id"
                         " WHERE k.sepet_id = ? AND u.stok > 0", (sepet_id,)):
        kalan = r["stok"] - ayrilan.get(r["urun_id"], 0)
        if r["adet"] > kalan:
            asanlar.append((r["urun_id"], r["ad"], max(0, kalan)))
    if asanlar:
        raise StokYetersiz(asanlar)
    ulke = teslimat.ulke.strip().upper()
    teslim = TeslimYontemi(teslim)
    tutar = sepet_hesapla(
        kalem_listesi, Baglam(musteri_tipi=musteri.tip, teslimat_ulkesi=ulke), teslim,
        kur.eur_satis if kur is not None else None,
    )
    kur_kullanildi = tutar.kur is not None and kur is not None
    an = simdi.isoformat()
    cur = con.execute(
        "INSERT INTO siparis (no, musteri_id, durum, para_birimi, ara_toplam, kdv, kargo, toplam, kur, "
        "kur_tarihi, ihracat_istisnasi, teslim_yontemi, teslimat_ulkesi, teslimat_adresi, fatura_adresi, "
        "kart_son4, sepet_id, olusturma, guncelleme, odeme_yontemi, odeme_son_tarih, musteri_po, "
        "alici_unvan, alici_tip, alici_vkn, alici_vergi_dairesi, alici_vat_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            _yeni_no(con, simdi), musteri.id, _D.ODEME_BEKLIYOR.value, tutar.para_birimi,
            _para(tutar.ara_toplam), _para(tutar.kdv), _para(tutar.kargo_net), _para(tutar.toplam),
            str(tutar.kur) if kur_kullanildi else None, kur.tarih.isoformat() if kur_kullanildi else None,
            int(tutar.ihracat_istisnasi), teslim.value, ulke,
            json.dumps(asdict(teslimat), ensure_ascii=False), json.dumps(asdict(fatura), ensure_ascii=False),
            sepet_id, an, an, odeme_yontemi,
            havale_son_tarih(simdi, havale_gun).isoformat() if odeme_yontemi == "havale" else None,
            (musteri_po or "").strip() or None,
            musteri.ad, str(musteri.tip), musteri.vergi_kimlik_no, musteri.vergi_dairesi, musteri.vat_id,
        ),
    )
    siparis_id = cur.lastrowid
    for satir in tutar.satirlar:
        k = satir.kalem
        con.execute(
            "INSERT INTO siparis_kalemi (siparis_id, urun_id, sku, ad, adet, birim_net_eur, net, kdv, brut, "
            "tedarik_teyit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                siparis_id, k.urun_id, k.sku, k.ad, k.adet, str(k.birim_net_eur),
                _para(satir.net), _para(satir.kdv), _para(satir.brut), int(k.tedarik_teyit),
            ),
        )
    return siparis_getir(con, siparis_id, simdi)


def durum_degistir(con: sqlite3.Connection, siparis_id: int, yeni: SiparisDurumu, simdi: datetime,
                   havale_gun: int = HAVALE_GUN) -> Siparis:
    zaman_asimi_uygula(con, siparis_id, simdi)
    r = con.execute("SELECT durum FROM siparis WHERE id = ?", (siparis_id,)).fetchone()
    if r is None:
        raise LookupError(siparis_id)
    odeme = con.execute("SELECT odeme_yontemi, odeme_son_tarih FROM siparis WHERE id = ?", (siparis_id,)).fetchone()
    r = {"durum": r["durum"], "odeme_yontemi": odeme["odeme_yontemi"], "odeme_son_tarih": odeme["odeme_son_tarih"]}
    kayitli = SiparisDurumu(r["durum"])
    eski = _D.SURESI_DOLDU if _suresi_doldu(r, simdi) else kayitli
    try:
        hedef = SiparisDurumu(yeni)
    except ValueError:
        raise GecersizGecis(f"{eski}->{yeni}") from None
    if hedef not in IZINLI_GECISLER[eski]:
        raise GecersizGecis(f"{eski}->{hedef}")
    if hedef == _D.SURESI_DOLDU:            # yalnız okunurken türetilir; yazılmaz
        raise GecersizGecis(f"{eski}->{hedef}")
    if eski == _D.SURESI_DOLDU and hedef in (_D.ODEME_BEKLIYOR, _D.ODENDI):
        # G3g inceleme I-1: süresi dolan havalenin ayırması kalkmıştı; yeniden açma ya da geç "ödendi" stoku yeniden
        # ayırır. Aynı işlem içinde (BEGIN IMMEDIATE) ayrılabilir stoka karşı denetlenir; yetmezse StokYetersiz.
        if not con.in_transaction:
            con.execute("BEGIN IMMEDIATE")
        ayrilan = ayrilan_adetler(con, simdi, haric_siparis_id=siparis_id)
        asanlar = []
        for k in con.execute("SELECT k.urun_id, SUM(k.adet) AS adet, u.stok, u.ad FROM siparis_kalemi k"
                             " JOIN urun u ON u.id = k.urun_id WHERE k.siparis_id = ? AND u.stok > 0"
                             " GROUP BY k.urun_id", (siparis_id,)).fetchall():
            kalan = k["stok"] - ayrilan.get(k["urun_id"], 0)
            if k["adet"] > kalan:
                asanlar.append((k["urun_id"], k["ad"], max(0, kalan)))
        if asanlar:
            raise StokYetersiz(asanlar)
    if eski == _D.SURESI_DOLDU and hedef == _D.ODEME_BEKLIYOR:
        # G3g madde 4: yönetim yeniden açar: şimdiden itibaren yeni ödeme süresi (stok yeniden ayrılır)
        cur = con.execute(
            "UPDATE siparis SET odeme_son_tarih = ?, guncelleme = ? WHERE id = ? AND durum = ? AND odeme_son_tarih = ?",
            (havale_son_tarih(simdi, havale_gun).isoformat(), simdi.isoformat(), siparis_id, kayitli.value,
             r["odeme_son_tarih"]))
        if cur.rowcount == 0:
            raise GecersizGecis(f"{eski}->{hedef} (eşzamanlı değişiklik)")
        return siparis_getir(con, siparis_id, simdi)
    cur = con.execute(
        "UPDATE siparis SET durum = ?, guncelleme = ?,"
        " odeme_zamani = CASE WHEN ? = 'odendi' THEN ? ELSE odeme_zamani END WHERE id = ? AND durum = ?",
        (hedef.value, simdi.isoformat(), hedef.value, simdi.isoformat(), siparis_id, kayitli.value),
    )
    if cur.rowcount == 0:                       # başka işlem araya girdi: güncel durumu oku
        r = con.execute("SELECT durum FROM siparis WHERE id = ?", (siparis_id,)).fetchone()
        raise GecersizGecis(f"{eski}->{hedef} (güncel: {r['durum'] if r else None})")
    return siparis_getir(con, siparis_id, simdi)
