"""TCMB günlük EUR kuru: indirme, ayrıştırma, saklama."""
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import httpx

TCMB_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"


@dataclass(frozen=True)
class Kur:
    tarih: date
    eur_alis: Decimal
    eur_satis: Decimal


def tcmb_ayristir(xml: bytes) -> Kur:
    try:
        kok = ET.fromstring(xml)
    except ET.ParseError as e:
        raise ValueError(f"tcmb_xml_bozuk: {e}") from e
    tarih_metni = kok.get("Tarih")
    if kok.tag != "Tarih_Date" or not tarih_metni:
        raise ValueError("tcmb_tarih_yok")
    tarih = datetime.strptime(tarih_metni, "%d.%m.%Y").date()
    for doviz in kok.iter("Currency"):
        if doviz.get("Kod") != "EUR":
            continue
        try:
            alis = Decimal((doviz.findtext("ForexBuying") or "").strip())
            satis = Decimal((doviz.findtext("ForexSelling") or "").strip())
        except InvalidOperation as e:
            raise ValueError("tcmb_eur_degeri_bozuk") from e
        if alis <= 0 or satis <= 0:
            raise ValueError("tcmb_eur_degeri_bozuk")
        return Kur(tarih=tarih, eur_alis=alis, eur_satis=satis)
    raise ValueError("tcmb_eur_yok")


def kur_kaydet(con: sqlite3.Connection, kur: Kur, simdi: datetime) -> None:
    con.execute(
        "INSERT OR REPLACE INTO kur (tarih, eur_alis, eur_satis, alindi) VALUES (?, ?, ?, ?)",
        (kur.tarih.isoformat(), str(kur.eur_alis), str(kur.eur_satis), simdi.isoformat()),
    )


def son_kur(con: sqlite3.Connection) -> Kur | None:
    satir = con.execute(
        "SELECT tarih, eur_alis, eur_satis FROM kur ORDER BY tarih DESC LIMIT 1"
    ).fetchone()
    if satir is None:
        return None
    return Kur(
        tarih=date.fromisoformat(satir[0]),
        eur_alis=Decimal(satir[1]),
        eur_satis=Decimal(satir[2]),
    )


def kur_bayat_mi(kur: Kur, bugun: date) -> bool:
    return (bugun - kur.tarih).days > 3


def kur_al(con: sqlite3.Connection, http: httpx.Client, simdi: datetime) -> Kur:
    yanit = http.get(TCMB_URL, timeout=30.0)
    yanit.raise_for_status()
    kur = tcmb_ayristir(yanit.content)
    kur_kaydet(con, kur, simdi)
    return kur
