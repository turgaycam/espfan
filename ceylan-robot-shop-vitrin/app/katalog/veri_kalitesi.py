"""G3j madde 4: yönetim "Veri kalitesi" raporu — kaynak verideki göze çarpan tutarsızlıklar (yalnız okur, yazmaz).

- KDV oranı %20 olmayan aktif ürünler (geçersiz oranlar ayrıca işaretli: sitede teklifle satılır),
- en az AYNI_FIYAT_ESIGI farklı aktif üründe birebir aynı temsili fiyat (yer tutucu fiyat izlenimi),
- aynı üretici koduna sahip birden çok aktif ürün (büyük/küçük harf ve baş/son boşluk farkı yok sayılır).
- G3k fix 1 (I-3): teknik satır değeri küçük harfle başlıyor (kesik sözcük izlenimi: "ğır yük robot kollarının…"),
- G3k fix 1 (I-3): "Tork" satırının Nm değeri ürün adındaki kW değerine sayıca eşit (kW değerinin kopyalanması izlenimi).
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from app.fiyat.kurallar import kdv_gecerli
from app.metin import normalize

AYNI_FIYAT_ESIGI = 3
GRUP_UST = 200          # sayfada en çok grup (her bölüm); toplam sayı yine verilir


@dataclass(frozen=True)
class VkUrun:
    id: int
    sku: str
    ad: str
    uretici_kodu: str | None


@dataclass(frozen=True)
class VkGrup:
    anahtar: str              # fiyat (€) ya da üretici kodu
    urunler: tuple[VkUrun, ...]


@dataclass(frozen=True)
class VeriKalitesi:
    kdv: tuple[tuple[VkUrun, str, bool], ...]     # (ürün, oran, geçerli mi)
    ayni_fiyat: tuple[VkGrup, ...]
    ayni_fiyat_toplam: int
    ayni_kod: tuple[VkGrup, ...]
    ayni_kod_toplam: int
    kesik_teknik: tuple[tuple[VkUrun, str, str], ...] = ()     # (ürün, etiket, değer)
    kesik_teknik_toplam: int = 0
    tork_kw: tuple[tuple[VkUrun, str, str], ...] = ()
    tork_kw_toplam: int = 0


def _vk(r) -> VkUrun:
    return VkUrun(id=r["id"], sku=r["sku"], ad=r["ad"], uretici_kodu=r["uretici_kodu"])


def _gruplar(con: sqlite3.Connection, anahtar_sql: str, esik: int, ek_kosul: str = "") -> tuple[list[VkGrup], int]:
    anahtarlar = [r[0] for r in con.execute(
        f"SELECT {anahtar_sql} AS a FROM urun WHERE aktif = 1 {ek_kosul} GROUP BY a HAVING COUNT(*) >= ?"
        " ORDER BY COUNT(*) DESC, a", (esik,))]
    gruplar = []
    for a in anahtarlar[:GRUP_UST]:
        urunler = tuple(_vk(r) for r in con.execute(
            f"SELECT id, sku, ad, uretici_kodu FROM urun WHERE aktif = 1 {ek_kosul} AND {anahtar_sql} = ? ORDER BY id",
            (a,)))
        gruplar.append(VkGrup(anahtar=str(a), urunler=urunler))
    return gruplar, len(anahtarlar)


_NM = re.compile(r"(\d+(?:[.,]\d+)?)\s*nm\b", re.I)
_KW = re.compile(r"(\d+(?:[.,]\d+)?)\s*kw\b", re.I)


def _sayilar(desen: re.Pattern, metin: str) -> set[Decimal]:
    return {Decimal(x.replace(",", ".")) for x in desen.findall(metin or "")}


def kesik_deger_mi(deger: str) -> bool:
    """Değer küçük harfle başlıyor mu (kaynakta kesilmiş sözcük izlenimi). Yalnız işaretler; veri değişmez."""
    bas = (deger or "").strip()[:1]
    return bas.isalpha() and bas.islower()


def tork_kw_esit_mi(ad: str, etiket: str, deger: str) -> bool:
    """"Tork" satırındaki Nm değeri ürün adındaki bir kW değerine sayıca eşit mi ("8.5KW" ↔ "8.5 Nm")."""
    return "tork" in normalize(etiket) and bool(_sayilar(_NM, deger) & _sayilar(_KW, ad))


def _teknik_denetimleri(con: sqlite3.Connection):
    kesik, tork = [], []
    for r in con.execute("SELECT u.id, u.sku, u.ad, u.uretici_kodu, t.veri FROM urun u JOIN urun_teknik t"
                         " ON t.urun_id = u.id WHERE u.aktif = 1 ORDER BY u.id"):
        try:
            veri = json.loads(r["veri"])
        except (ValueError, TypeError):
            continue
        for cift in (veri.get("ozellikler") or []) if isinstance(veri, dict) else []:
            if not (isinstance(cift, list) and len(cift) == 2 and all(isinstance(x, str) for x in cift)):
                continue
            etiket, deger = cift
            if kesik_deger_mi(deger):
                kesik.append((_vk(r), etiket, deger))
            if tork_kw_esit_mi(r["ad"], etiket, deger):
                tork.append((_vk(r), etiket, deger))
    return kesik, tork


def veri_kalitesi_raporu(con: sqlite3.Connection) -> VeriKalitesi:
    kdv = []
    for r in con.execute("SELECT id, sku, ad, uretici_kodu, kdv_orani FROM urun WHERE aktif = 1"
                         " AND CAST(kdv_orani AS REAL) != 20 ORDER BY CAST(kdv_orani AS REAL) DESC, id"):
        oran = Decimal(str(r["kdv_orani"]))
        kdv.append((_vk(r), f"{oran.normalize():f}", kdv_gecerli(oran)))
    fiyat, fiyat_toplam = _gruplar(con, "temsili_fiyat_eur", AYNI_FIYAT_ESIGI)
    kod, kod_toplam = _gruplar(con, "upper(trim(uretici_kodu))", 2,
                               "AND uretici_kodu IS NOT NULL AND trim(uretici_kodu) != ''")
    kesik, tork = _teknik_denetimleri(con)
    return VeriKalitesi(kdv=tuple(kdv), ayni_fiyat=tuple(fiyat), ayni_fiyat_toplam=fiyat_toplam,
                        ayni_kod=tuple(kod), ayni_kod_toplam=kod_toplam,
                        kesik_teknik=tuple(kesik[:GRUP_UST]), kesik_teknik_toplam=len(kesik),
                        tork_kw=tuple(tork[:GRUP_UST]), tork_kw_toplam=len(tork))
