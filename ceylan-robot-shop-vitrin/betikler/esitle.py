"""Katalog eşitleme betiği — cr-shop-esitle.service (02:30) çalıştırır.

Çalıştırma (release kökünden): venv/bin/python -m betikler.esitle
Çıktı: stdout'a tek satır JSON (TurSonucu alanları). Durum 'hata' ise çıkış kodu 1.
'eksik' tur çıkış 0 döner: veri tutarlı kalır, günlükte ve yönetim panelinde görünür.
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import TextIO

import httpx

from app.ayarlar import ayarlari_oku
from app.db import baglan
from app.esitleme.esitle import esitle
from app.esitleme.ornek import ornek_durumlari_ata
from app.esitleme.kaynak import KaynakIstemci
from app.fiyat.kurallar import bantlari_oku

KULLANICI_AJANI = "cr-shop-demo-esitleme/1.0"
ZAMAN_ASIMI_SN = 30


def http_istemcisi(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(timeout=ZAMAN_ASIMI_SN, headers={"User-Agent": KULLANICI_AJANI}, transport=transport)


def _simdi() -> datetime:
    return datetime.now(UTC)


def calistir(
    ortam: Mapping[str, str] = os.environ,
    *,
    transport: httpx.BaseTransport | None = None,
    uyku: Callable[[float], None] = time.sleep,
    simdi: Callable[[], datetime] = _simdi,
    cikti: TextIO = sys.stdout,
) -> int:
    ayarlar = ayarlari_oku(ortam)
    bantlar = bantlari_oku(ayarlar.bantlar_yolu)
    con = baglan(ayarlar.db_yolu)
    try:
        with http_istemcisi(transport) as http:
            kaynak = KaynakIstemci(http, ayarlar.kaynak_api, uyku=uyku)
            sonuc = esitle(con, kaynak, bantlar, simdi, gorsel_dizin=ayarlar.gorsel_dizin)
        if sonuc.durum != "hata":
            with con:
                ornek_durumlari_ata(con)   # Görev 5A; idempotent
    finally:
        con.close()
    print(json.dumps(dataclasses.asdict(sonuc), ensure_ascii=False), file=cikti, flush=True)
    return 1 if sonuc.durum == "hata" else 0


if __name__ == "__main__":
    sys.exit(calistir())
