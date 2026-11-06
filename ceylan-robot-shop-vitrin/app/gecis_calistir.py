"""Dağıtım adımı: canlı veritabanını yedekler, sonra geçişleri uygular (crshop olarak).

dagitim/uzak-yayinla.sh, release kökünden çağırır:
    sudo -n -u crshop /opt/cr-shop-demo/releases/<release>/venv/bin/python -m app.gecis_calistir
sudo ortamı sıfırladığı için SHOP_DB ortam dosyasından okunur. Yedek adı release klasöründen türetilir:
    <SHOP_DB klasörü>/shop-onceki-<release>.db   (son 3 tutulur)
Çıktı: tek satır JSON. SHOP_DB yoksa çıkış 1.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import TextIO

from app.db import baglan, gecisleri_uygula

ORTAM_DOSYASI = Path("/opt/cr-shop-demo/ortam")
TUTULAN_YEDEK = 3


def ortam_dosyasi_oku(yol: Path) -> dict[str, str]:
    """systemd EnvironmentFile biçimi: ANAHTAR=deger, '#' yorum, değer tek/çift tırnaklı olabilir."""
    sonuc: dict[str, str] = {}
    for satir in yol.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if not satir or satir.startswith(("#", ";")) or "=" not in satir:
            continue
        anahtar, deger = satir.split("=", 1)
        deger = deger.strip()
        if len(deger) >= 2 and deger[0] == deger[-1] and deger[0] in "'\"":
            deger = deger[1:-1]
        sonuc[anahtar.strip()] = deger
    return sonuc


def release_adi() -> str:
    return Path(__file__).resolve().parents[1].name


def yedekle(db: Path, hedef: Path) -> None:
    kaynak = sqlite3.connect(db)
    try:
        hedef_con = sqlite3.connect(hedef)
        try:
            kaynak.backup(hedef_con)
        finally:
            hedef_con.close()
    finally:
        kaynak.close()


def eski_yedekleri_sil(klasor: Path, tutulan: int = TUTULAN_YEDEK) -> list[str]:
    yedekler = sorted(klasor.glob("shop-onceki-*.db"), key=lambda p: p.name)
    silinecek = yedekler[:-tutulan] if len(yedekler) > tutulan else []
    for yol in silinecek:
        yol.unlink()
    return [yol.name for yol in silinecek]


def calistir(ortam_dosyasi: Path = ORTAM_DOSYASI, release: str | None = None, cikti: TextIO = sys.stdout) -> int:
    ortam = ortam_dosyasi_oku(ortam_dosyasi)
    if not ortam.get("SHOP_DB"):
        print(json.dumps({"durum": "hata", "hata": f"SHOP_DB yok: {ortam_dosyasi}"}, ensure_ascii=False),
              file=cikti, flush=True)
        return 1
    db = Path(ortam["SHOP_DB"])
    release = release or release_adi()
    yedek: Path | None = None
    if db.exists():
        yedek = db.parent / f"shop-onceki-{release}.db"
        yedekle(db, yedek)
    con = baglan(db)
    try:
        uygulanan = gecisleri_uygula(con)
    finally:
        con.close()
    silinen = eski_yedekleri_sil(db.parent)
    print(json.dumps({"durum": "tamam", "release": release, "yedek": str(yedek) if yedek else None,
                      "uygulanan": uygulanan, "silinen_yedek": silinen}, ensure_ascii=False),
          file=cikti, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(calistir())
