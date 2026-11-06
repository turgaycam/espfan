"""TCMB EUR kuru — cr-shop-kur.service (06:00) çalıştırır.

Çalıştırma (release kökünden): venv/bin/python -m betikler.kur_al
Başarı: {"durum":"tamam",...} ve çıkış 0. Hata: {"durum":"hata",...} ve çıkış 1.
Hata durumunda veritabanına yazılmaz; site son kuru kullanmaya devam eder (kur tarihi kırmızı).
"""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TextIO

import httpx

from app.ayarlar import ayarlari_oku
from app.db import baglan
from app.fiyat.kur import kur_al, son_kur

KULLANICI_AJANI = "cr-shop-demo-kur/1.0"
ZAMAN_ASIMI_SN = 30


def calistir(
    ortam: Mapping[str, str] = os.environ,
    *,
    transport: httpx.BaseTransport | None = None,
    simdi: datetime | None = None,
    cikti: TextIO = sys.stdout,
) -> int:
    ayarlar = ayarlari_oku(ortam)
    an = simdi or datetime.now(UTC)
    con = baglan(ayarlar.db_yolu)
    try:
        try:
            with httpx.Client(timeout=ZAMAN_ASIMI_SN, headers={"User-Agent": KULLANICI_AJANI},
                              transport=transport) as http:
                with con:
                    kur = kur_al(con, http, an)
        except Exception as hata:  # ağ, HTTP durum, ayrıştırma — hepsi aynı sonuç: son kur korunur
            son = son_kur(con)
            print(json.dumps({
                "durum": "hata",
                "hata": f"{type(hata).__name__}: {hata}",
                "son_kur_tarihi": son.tarih.isoformat() if son else None,
                "son_kur_eur_satis": str(son.eur_satis) if son else None,
            }, ensure_ascii=False), file=cikti, flush=True)
            return 1
    finally:
        con.close()
    print(json.dumps({
        "durum": "tamam",
        "tarih": kur.tarih.isoformat(),
        "eur_alis": str(kur.eur_alis),
        "eur_satis": str(kur.eur_satis),
    }, ensure_ascii=False), file=cikti, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(calistir())
