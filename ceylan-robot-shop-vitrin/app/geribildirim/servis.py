"""Site içi geri bildirim kaydı ve yönetici durum takibi. Commit yapmaz."""
from __future__ import annotations

import sqlite3
from datetime import datetime

DURUMLAR = ("yeni", "okundu", "yapildi")
METIN_MAX = 2000
SAYFA_MAX = 500
ISIM_MAX = 100


def kaydet(con: sqlite3.Connection, sayfa: str, metin: str, isim: str | None, simdi: datetime) -> int:
    metin = (metin or "").strip()
    if not 1 <= len(metin) <= METIN_MAX:
        raise ValueError("metin")
    sayfa = (sayfa or "").strip()
    if not 1 <= len(sayfa) <= SAYFA_MAX:
        raise ValueError("sayfa")
    isim = (isim or "").strip() or None
    if isim is not None and len(isim) > ISIM_MAX:
        raise ValueError("isim")
    return con.execute(
        "INSERT INTO geri_bildirim (sayfa, metin, isim, durum, olusturma) VALUES (?, ?, ?, 'yeni', ?)",
        (sayfa, metin, isim, simdi.isoformat()),
    ).lastrowid


def listele(con: sqlite3.Connection, durum: str | None = None) -> list[sqlite3.Row]:
    if durum is None:
        return con.execute("SELECT * FROM geri_bildirim ORDER BY id DESC").fetchall()
    if durum not in DURUMLAR:
        raise ValueError("durum")
    return con.execute("SELECT * FROM geri_bildirim WHERE durum = ? ORDER BY id DESC", (durum,)).fetchall()


def durum_degistir(con: sqlite3.Connection, gb_id: int, durum: str) -> None:
    if durum not in DURUMLAR:
        raise ValueError("durum")
    if con.execute("UPDATE geri_bildirim SET durum = ? WHERE id = ?", (durum, gb_id)).rowcount == 0:
        raise LookupError(gb_id)
