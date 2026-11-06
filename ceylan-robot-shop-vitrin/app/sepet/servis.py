"""Sepet: misafir (oturum) ve üye sepetleri, adet sınırları, düşen ürünler, birleştirme. Commit yapmaz."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal

from app.fiyat.kurallar import Kalem, kdv_gecerli

ADET_MIN, ADET_MAX = 1, 99

_UPSERT = (
    "INSERT INTO sepet_kalemi (sepet_id, urun_id, adet) VALUES (?, ?, ?) "
    "ON CONFLICT(sepet_id, urun_id) DO UPDATE SET adet = MIN(?, sepet_kalemi.adet + excluded.adet)"
)


# G3e düzeltme 1 (M-7): adet olduğu gibi yazılır (stok sınırı çağıranda hesaplanır)
_ADET_YAZ = (
    "INSERT INTO sepet_kalemi (sepet_id, urun_id, adet) VALUES (?, ?, ?) "
    "ON CONFLICT(sepet_id, urun_id) DO UPDATE SET adet = excluded.adet"
)


class TeklifZorunlu(Exception):
    pass


class UrunYok(Exception):
    pass


def _kis(adet: int) -> int:
    return max(ADET_MIN, min(ADET_MAX, adet))


def sepet_bul(con: sqlite3.Connection, oturum_id: str | None, musteri_id: int | None, simdi: datetime) -> int:
    if musteri_id is not None:
        r = con.execute("SELECT id FROM sepet WHERE musteri_id = ?", (musteri_id,)).fetchone()
        if r is not None:
            return r["id"]
        return con.execute(
            "INSERT INTO sepet (oturum_id, musteri_id, olusturma) VALUES (NULL, ?, ?)",
            (musteri_id, simdi.isoformat()),
        ).lastrowid
    if not oturum_id:
        raise ValueError("oturum_yok")
    r = con.execute("SELECT id FROM sepet WHERE oturum_id = ?", (oturum_id,)).fetchone()
    if r is not None:
        return r["id"]
    return con.execute(
        "INSERT INTO sepet (oturum_id, musteri_id, olusturma) VALUES (?, NULL, ?)",
        (oturum_id, simdi.isoformat()),
    ).lastrowid


def _ust_sinir(stok: int, ayrilan: int = 0) -> int:
    """G3e madde 1: stok adedi bilinen (stok > 0) üründe sepet adedi ayrılabilir stoku (stok − açık siparişlerin
    ayırdığı, düzeltme 3) aşamaz (0 olabilir); stoku bilinmeyen / tedarikli (stok <= 0) üründe yalnız genel üst sınır."""
    return min(ADET_MAX, max(0, stok - ayrilan)) if stok > 0 else ADET_MAX


def ekle(con: sqlite3.Connection, sepet_id: int, urun_id: int, adet: int = 1,
         ayrilan: dict[int, int] | None = None) -> tuple[int, int | None]:
    """(sepetteki yeni adet, stok sınırı uygulandıysa ayrılabilir adet (0 olabilir) yoksa None). ayrilan: ürün ->
    açık siparişlerin ayırdığı adet (app.stok.ayrilan_adetler)."""
    r = con.execute("SELECT aktif, teklif_zorunlu, stok, kdv_orani FROM urun WHERE id = ?", (urun_id,)).fetchone()
    if r is None or not r["aktif"]:
        raise UrunYok(urun_id)
    if r["teklif_zorunlu"] or not kdv_gecerli(r["kdv_orani"]):     # G3j madde 4: geçersiz KDV oranı teklifle
        raise TeklifZorunlu(urun_id)
    mevcut = con.execute("SELECT adet FROM sepet_kalemi WHERE sepet_id = ? AND urun_id = ?",
                         (sepet_id, urun_id)).fetchone()
    istenen = (mevcut["adet"] if mevcut else 0) + _kis(adet)
    sinir = _ust_sinir(r["stok"], (ayrilan or {}).get(urun_id, 0))
    yeni = min(istenen, sinir)
    if yeni > 0:
        con.execute(_ADET_YAZ, (sepet_id, urun_id, yeni))
    else:
        kaldir(con, sepet_id, urun_id)
    net = max(0, r["stok"] - (ayrilan or {}).get(urun_id, 0))
    return yeni, (net if r["stok"] > 0 and net < istenen else None)


def adet_ayarla(con: sqlite3.Connection, sepet_id: int, urun_id: int, adet: int,
                ayrilan: dict[int, int] | None = None) -> int | None:
    """Adedi ayarlar; stok sınırı uygulandıysa ayrılabilir adedi döner (0 ise kalem çıkar), yoksa None."""
    if adet < ADET_MIN:
        kaldir(con, sepet_id, urun_id)
        return None
    r = con.execute("SELECT stok FROM urun WHERE id = ?", (urun_id,)).fetchone()
    stok = r["stok"] if r is not None else 0
    sinir = _ust_sinir(stok, (ayrilan or {}).get(urun_id, 0))
    if sinir <= 0:
        kaldir(con, sepet_id, urun_id)
    else:
        con.execute("UPDATE sepet_kalemi SET adet = ? WHERE sepet_id = ? AND urun_id = ?",
                    (min(adet, sinir), sepet_id, urun_id))
    net = max(0, stok - (ayrilan or {}).get(urun_id, 0))
    return net if stok > 0 and net < adet else None


def stok_siniri_uygula(con: sqlite3.Connection, sepet_id: int,
                       ayrilan: dict[int, int] | None = None) -> list[tuple[int, str, int, int]]:
    """G3e madde 1 + düzeltme 3: stok sepete eklendikten sonra azaldıysa ya da açık siparişlerce ayrıldıysa kalem adedi
    ayrılabilir adede indirilir (0 ise kalem çıkar); (urun_id, ad, ayrılabilir adet, önceki adet) listesi döner."""
    sonuc = []
    for r in con.execute("SELECT k.urun_id, k.adet, u.stok, u.ad FROM sepet_kalemi k JOIN urun u ON u.id = k.urun_id"
                         " WHERE k.sepet_id = ? AND u.stok > 0 ORDER BY k.rowid", (sepet_id,)).fetchall():
        sinir = max(0, r["stok"] - (ayrilan or {}).get(r["urun_id"], 0))
        if r["adet"] <= sinir:
            continue
        if sinir > 0:
            con.execute("UPDATE sepet_kalemi SET adet = ? WHERE sepet_id = ? AND urun_id = ?",
                        (sinir, sepet_id, r["urun_id"]))
        else:
            kaldir(con, sepet_id, r["urun_id"])
        sonuc.append((r["urun_id"], r["ad"], sinir, r["adet"]))
    return sonuc


def kaldir(con: sqlite3.Connection, sepet_id: int, urun_id: int) -> None:
    con.execute("DELETE FROM sepet_kalemi WHERE sepet_id = ? AND urun_id = ?", (sepet_id, urun_id))


def bosalt(con: sqlite3.Connection, sepet_id: int) -> None:
    con.execute("DELETE FROM sepet_kalemi WHERE sepet_id = ?", (sepet_id,))


def kalemler(con: sqlite3.Connection, sepet_id: int) -> tuple[list[Kalem], list[str]]:
    satirlar = con.execute(
        "SELECT k.urun_id, k.adet, u.sku, u.ad, u.temsili_fiyat_eur, u.kdv_orani, u.stok, "
        "u.tedarik_suresi_gun, u.aktif, u.teklif_zorunlu "
        "FROM sepet_kalemi k JOIN urun u ON u.id = k.urun_id WHERE k.sepet_id = ? ORDER BY k.rowid",
        (sepet_id,),
    ).fetchall()
    gecerli: list[Kalem] = []
    dusen: list[str] = []
    for r in satirlar:
        if not r["aktif"] or r["teklif_zorunlu"] or not kdv_gecerli(r["kdv_orani"]):
            kaldir(con, sepet_id, r["urun_id"])
            dusen.append(r["ad"])
            continue
        gecerli.append(
            Kalem(
                urun_id=r["urun_id"], sku=r["sku"], ad=r["ad"], adet=r["adet"],
                birim_net_eur=Decimal(r["temsili_fiyat_eur"]), kdv_orani=Decimal(r["kdv_orani"]),
                tedarik_teyit=r["stok"] == 0 and r["tedarik_suresi_gun"] is None,
            )
        )
    return gecerli, dusen


def adet_toplam(con: sqlite3.Connection, sepet_id: int) -> int:
    return con.execute(
        "SELECT COALESCE(SUM(adet), 0) FROM sepet_kalemi WHERE sepet_id = ?", (sepet_id,)
    ).fetchone()[0]


def birlestir(con: sqlite3.Connection, misafir_sepet_id: int, uye_sepet_id: int) -> int:
    if misafir_sepet_id == uye_sepet_id:
        return 0
    satirlar = con.execute(
        "SELECT urun_id, adet FROM sepet_kalemi WHERE sepet_id = ? ORDER BY rowid", (misafir_sepet_id,)
    ).fetchall()
    for r in satirlar:
        con.execute(_UPSERT, (uye_sepet_id, r["urun_id"], r["adet"], ADET_MAX))
    bosalt(con, misafir_sepet_id)
    con.execute("DELETE FROM sepet WHERE id = ?", (misafir_sepet_id,))
    return len(satirlar)
