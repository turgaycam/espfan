"""Sahte kart + 3D Secure. Yalnız test kartları kabul edilir; tam kart numarası hiçbir yere yazılmaz."""
from __future__ import annotations

import hmac
import sqlite3
from datetime import datetime
from enum import StrEnum

from app.sepet.servis import bosalt
from app.siparis.servis import SiparisDurumu, zaman_asimi_uygula

BASARILI_KART = "4111111111111111"
RET_KARTI = "4000000000000002"
SMS_KODU = "000000"


class OdemeSonucu(StrEnum):
    SMS_BEKLIYOR = "sms_bekliyor"
    BASARILI = "basarili"
    RET = "ret"
    SMS_HATALI = "sms_hatali"
    GECERSIZ_KART = "gecersiz_kart"
    ZATEN_ODENDI = "zaten_odendi"
    SIPARIS_GECERSIZ = "siparis_gecersiz"


def kart_normalize(kart_no: str) -> str:
    return "".join(ch for ch in (kart_no or "") if ch in "0123456789")


def deneme_getir(con: sqlite3.Connection, islem_anahtari: str) -> sqlite3.Row | None:
    """K13: 3D rotası deneme kaydını (siparis_id, durum, kart_son4...) buradan okur."""
    return con.execute("SELECT * FROM odeme_denemesi WHERE islem_anahtari = ?", (islem_anahtari,)).fetchone()


def _siparis_engeli(con: sqlite3.Connection, siparis_id: int, simdi: datetime) -> OdemeSonucu | None:
    zaman_asimi_uygula(con, siparis_id, simdi)
    r = con.execute("SELECT durum FROM siparis WHERE id = ?", (siparis_id,)).fetchone()
    if r is None or r["durum"] == SiparisDurumu.IPTAL:
        return OdemeSonucu.SIPARIS_GECERSIZ
    if r["durum"] != SiparisDurumu.ODEME_BEKLIYOR:
        return OdemeSonucu.ZATEN_ODENDI
    return None


def odeme_baslat(
    con: sqlite3.Connection, siparis_id: int, islem_anahtari: str, kart_no: str, simdi: datetime
) -> OdemeSonucu:
    if not islem_anahtari:
        raise ValueError("islem_anahtari")
    onceki = con.execute(
        "SELECT siparis_id, durum FROM odeme_denemesi WHERE islem_anahtari = ?", (islem_anahtari,)
    ).fetchone()
    if onceki is not None:
        if onceki["siparis_id"] != siparis_id:
            return OdemeSonucu.SIPARIS_GECERSIZ
        return OdemeSonucu(onceki["durum"])
    engel = _siparis_engeli(con, siparis_id, simdi)
    if engel is not None:
        return engel
    kart = kart_normalize(kart_no)
    kart_son4 = kart[-4:]
    kart_sonucu = {BASARILI_KART: "basarili", RET_KARTI: "ret"}.get(kart)
    del kart, kart_no                           # tam numara bundan sonra bellekte tutulmaz
    if kart_sonucu is None:
        con.execute(
            "INSERT INTO odeme_denemesi (islem_anahtari, siparis_id, kart_son4, kart_sonucu, durum, olusturma) "
            "VALUES (?, ?, NULL, NULL, ?, ?)",
            (islem_anahtari, siparis_id, OdemeSonucu.GECERSIZ_KART.value, simdi.isoformat()),
        )
        return OdemeSonucu.GECERSIZ_KART
    con.execute(
        "INSERT INTO odeme_denemesi (islem_anahtari, siparis_id, kart_son4, kart_sonucu, durum, olusturma) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (islem_anahtari, siparis_id, kart_son4, kart_sonucu, OdemeSonucu.SMS_BEKLIYOR.value, simdi.isoformat()),
    )
    return OdemeSonucu.SMS_BEKLIYOR


def _deneme_bitir(con: sqlite3.Connection, islem_anahtari: str, sonuc: OdemeSonucu) -> OdemeSonucu:
    con.execute("UPDATE odeme_denemesi SET durum = ? WHERE islem_anahtari = ?", (sonuc.value, islem_anahtari))
    return sonuc


def sms_dogrula(con: sqlite3.Connection, islem_anahtari: str, sms_kodu: str, simdi: datetime) -> OdemeSonucu:
    if not islem_anahtari:
        raise ValueError("islem_anahtari")
    d = con.execute(
        "SELECT siparis_id, durum, kart_son4, kart_sonucu FROM odeme_denemesi WHERE islem_anahtari = ?",
        (islem_anahtari,),
    ).fetchone()
    if d is None:
        return OdemeSonucu.SIPARIS_GECERSIZ
    if d["durum"] != OdemeSonucu.SMS_BEKLIYOR:
        return OdemeSonucu(d["durum"])
    engel = _siparis_engeli(con, d["siparis_id"], simdi)
    if engel is not None:
        return engel
    if not hmac.compare_digest((sms_kodu or "").strip().encode("utf-8"), SMS_KODU.encode("utf-8")):
        return _deneme_bitir(con, islem_anahtari, OdemeSonucu.SMS_HATALI)
    if d["kart_sonucu"] != "basarili":
        return _deneme_bitir(con, islem_anahtari, OdemeSonucu.RET)
    cur = con.execute(
        "UPDATE siparis SET durum = ?, kart_son4 = ?, guncelleme = ?, odeme_zamani = ? WHERE id = ? AND durum = ?",
        (SiparisDurumu.ODENDI.value, d["kart_son4"], simdi.isoformat(), simdi.isoformat(), d["siparis_id"],
         SiparisDurumu.ODEME_BEKLIYOR.value),
    )
    if cur.rowcount == 0:                       # başka işlem siparişin durumunu değiştirdi
        r = con.execute("SELECT durum FROM siparis WHERE id = ?", (d["siparis_id"],)).fetchone()
        _deneme_bitir(con, islem_anahtari, OdemeSonucu.RET)
        if r is not None and r["durum"] != SiparisDurumu.IPTAL:
            return OdemeSonucu.ZATEN_ODENDI
        return OdemeSonucu.SIPARIS_GECERSIZ
    _deneme_bitir(con, islem_anahtari, OdemeSonucu.BASARILI)
    sepet_id = con.execute("SELECT sepet_id FROM siparis WHERE id = ?", (d["siparis_id"],)).fetchone()[0]
    bosalt(con, sepet_id)
    return OdemeSonucu.BASARILI
