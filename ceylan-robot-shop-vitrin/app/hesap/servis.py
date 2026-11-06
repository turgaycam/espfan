"""Müşteri hesabı: kayıt kuralları, giriş, scrypt parola özeti, adresler. Commit yapmaz."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.fiyat.kurallar import MusteriTipi
from app.hesap.dogrulama import vat_id_kontrol, vergi_no_hatasi

PAROLA_MIN = 10
PAROLA_MAX = 256
ADRES_TURLERI = ("teslimat", "fatura")
_N, _R, _P, _DKLEN, _TUZ = 16384, 8, 1, 32, 16


@dataclass(frozen=True)
class Musteri:
    id: int
    tip: MusteriTipi
    ad: str
    eposta: str
    ulke: str
    vergi_kimlik_no: str | None
    vergi_dairesi: str | None
    vat_id: str | None
    iys_onay: bool


@dataclass(frozen=True)
class KayitGirdisi:
    tip: MusteriTipi
    ad: str
    eposta: str
    parola: str = field(repr=False)
    ulke: str
    kvkk_onay: bool
    iys_onay: bool = False
    vergi_kimlik_no: str | None = None
    vergi_dairesi: str | None = None
    vat_id: str | None = None


class KayitHatasi(ValueError):
    def __init__(self, alan: str, kod: str):
        super().__init__(f"{alan}:{kod}")
        self.alan = alan
        self.kod = kod


@dataclass(frozen=True)
class Adres:
    ad_soyad: str
    satir1: str
    sehir: str
    ulke: str
    satir2: str | None = None
    posta_kodu: str | None = None
    telefon: str | None = None


def _temiz(s: str | None) -> str | None:
    if s is None:
        return None
    s = s.strip()
    return s or None


def _parola_sinir(parola: str) -> None:
    if len(parola) > PAROLA_MAX:
        raise KayitHatasi("parola", "parola_uzun")
    try:
        parola.encode("utf-8")
    except UnicodeEncodeError:
        raise KayitHatasi("parola", "gecersiz") from None


def parola_ozeti(parola: str) -> str:
    _parola_sinir(parola)
    tuz = secrets.token_bytes(_TUZ)
    oz = hashlib.scrypt(parola.encode("utf-8"), salt=tuz, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${tuz.hex()}${oz.hex()}"


def parola_dogru(parola: str, ozet: str) -> bool:
    try:
        ad, n, r, p, tuz_hex, ozet_hex = ozet.split("$")
        if ad != "scrypt" or (int(n), int(r), int(p)) != (_N, _R, _P):
            return False
        tuz = bytes.fromhex(tuz_hex)
        beklenen = bytes.fromhex(ozet_hex)
        if not tuz or len(beklenen) != _DKLEN:
            return False
        hesap = hashlib.scrypt(parola.encode("utf-8"), salt=tuz, n=_N, r=_R, p=_P, dklen=_DKLEN)
    except (ValueError, TypeError, AttributeError):
        return False
    return hmac.compare_digest(hesap, beklenen)


def _musteri(r: sqlite3.Row) -> Musteri:
    return Musteri(
        id=r["id"], tip=MusteriTipi(r["tip"]), ad=r["ad"], eposta=r["eposta"], ulke=r["ulke"],
        vergi_kimlik_no=r["vergi_kimlik_no"], vergi_dairesi=r["vergi_dairesi"], vat_id=r["vat_id"],
        iys_onay=bool(r["iys_onay"]),
    )


def musteri_getir(con: sqlite3.Connection, musteri_id: int) -> Musteri | None:
    r = con.execute("SELECT * FROM musteri WHERE id = ?", (musteri_id,)).fetchone()
    return _musteri(r) if r is not None else None


def kayit_ol(con: sqlite3.Connection, g: KayitGirdisi, simdi: datetime) -> Musteri:
    ad = _temiz(g.ad)
    if ad is None:
        raise KayitHatasi("ad", "zorunlu")
    eposta = _temiz(g.eposta)
    if eposta is None:
        raise KayitHatasi("eposta", "zorunlu")
    eposta = eposta.lower()
    if "@" not in eposta:
        raise KayitHatasi("eposta", "gecersiz")
    if len(g.parola or "") < PAROLA_MIN:
        raise KayitHatasi("parola", "parola_kisa")
    _parola_sinir(g.parola)
    if not g.kvkk_onay:
        raise KayitHatasi("kvkk_onay", "kvkk_onay_yok")

    tip = MusteriTipi(g.tip)
    vkn = daire = vat = None
    iys = bool(g.iys_onay)
    if tip is MusteriTipi.KURUMSAL:
        ulke, iys = "TR", False
        vkn = "".join((g.vergi_kimlik_no or "").split())
        if not vkn:
            raise KayitHatasi("vergi_kimlik_no", "zorunlu")
        hata = vergi_no_hatasi(vkn)          # G3m madde 26: hane hatası ile doğrulama basamağı hatası ayrı
        if hata is not None:
            raise KayitHatasi("vergi_kimlik_no", hata)
        daire = _temiz(g.vergi_dairesi)
        if daire is None:
            raise KayitHatasi("vergi_dairesi", "zorunlu")
    elif tip is MusteriTipi.YURTDISI:
        ulke = (g.ulke or "").strip().upper()
        if not ulke:
            raise KayitHatasi("ulke", "zorunlu")
        if len(ulke) != 2 or not (ulke.isascii() and ulke.isalpha()) or ulke == "TR":
            raise KayitHatasi("ulke", "gecersiz")
        iys = False
        vat, kod = vat_id_kontrol(g.vat_id, ulke, zorunlu_ab=False)   # G3c madde 19: biçim (zorunluluk web'de)
        if kod is not None:
            raise KayitHatasi("vat_id", kod)
    else:
        ulke = "TR"

    if con.execute("SELECT 1 FROM musteri WHERE eposta = ?", (eposta,)).fetchone() is not None:
        raise KayitHatasi("eposta", "eposta_kayitli")
    an = simdi.isoformat()
    try:
        cur = con.execute(
            "INSERT INTO musteri (tip, ad, eposta, parola_ozeti, vergi_kimlik_no, vergi_dairesi, vat_id, "
            "ulke, kvkk_onay, iys_onay, olusturma) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tip.value, ad, eposta, parola_ozeti(g.parola), vkn, daire, vat, ulke, an, int(iys), an),
        )
    except sqlite3.IntegrityError:          # eşzamanlı aynı e-posta
        raise KayitHatasi("eposta", "eposta_kayitli") from None
    return musteri_getir(con, cur.lastrowid)


_SAHTE_OZET = parola_ozeti("sahte-parola-zamanlama")


def giris(con: sqlite3.Connection, eposta: str, parola: str) -> Musteri | None:
    e = (eposta or "").strip().lower()
    if not e:
        return None
    r = con.execute("SELECT id, parola_ozeti FROM musteri WHERE eposta = ?", (e,)).fetchone()
    if r is None:
        parola_dogru(parola or "", _SAHTE_OZET)     # zamanlama farkı: kullanıcı numaralandırmayı önle
        return None
    if not parola_dogru(parola or "", r["parola_ozeti"]):
        return None
    return musteri_getir(con, r["id"])


def adres_kaydet(
    con: sqlite3.Connection, musteri_id: int, tur: Literal["teslimat", "fatura"], a: Adres
) -> int:
    if tur not in ADRES_TURLERI:
        raise ValueError("tur")
    zorunlu: dict[str, str] = {}
    for alan in ("ad_soyad", "satir1", "sehir", "ulke"):
        deger = _temiz(getattr(a, alan))
        if deger is None:
            raise KayitHatasi(alan, "zorunlu")
        zorunlu[alan] = deger
    cur = con.execute(
        "INSERT INTO adres (musteri_id, tur, ad_soyad, satir1, satir2, sehir, posta_kodu, ulke, telefon) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            musteri_id, tur, zorunlu["ad_soyad"], zorunlu["satir1"], _temiz(a.satir2), zorunlu["sehir"],
            _temiz(a.posta_kodu), zorunlu["ulke"].upper(), _temiz(a.telefon),
        ),
    )
    return cur.lastrowid


def adres_son(con: sqlite3.Connection, musteri_id: int, tur: str) -> Adres | None:
    r = con.execute(
        "SELECT * FROM adres WHERE musteri_id = ? AND tur = ? ORDER BY id DESC LIMIT 1", (musteri_id, tur)
    ).fetchone()
    if r is None:
        return None
    return Adres(
        ad_soyad=r["ad_soyad"], satir1=r["satir1"], sehir=r["sehir"], ulke=r["ulke"],
        satir2=r["satir2"], posta_kodu=r["posta_kodu"], telefon=r["telefon"],
    )


def fatura_bilgisi_guncelle(con: sqlite3.Connection, musteri_id: int, *, ad: str,
                            vergi_dairesi: str | None) -> None:
    """G3i madde 9: "Fatura bilgilerim" — unvan (ad) ve vergi dairesi (kurumsal) güncellenir; VKN/VAT ID değişmez.
    Doğrulama çağıranda (kayıt kurallarıyla aynı: ad zorunlu, kurumsalda vergi dairesi zorunlu)."""
    ad_t = _temiz(ad)
    if ad_t is None:
        raise KayitHatasi("ad", "zorunlu")
    con.execute("UPDATE musteri SET ad = ?, vergi_dairesi = COALESCE(?, vergi_dairesi) WHERE id = ?",
                (ad_t, _temiz(vergi_dairesi), musteri_id))
