"""G3f: aktif ürünlerin adını ve teknik özelliklerini EN çeviri (LLM taslak) için JSONL partilerine döker (salt okunur).

Kullanım: python -m betikler.ceviri_disa --db <yol> --cikis <klasör> [--parti 100] [--sinir N] [--yalniz-eksik]
                                          [--yalniz-ad]
Çıktı: <klasör>/parti-0001.jsonl, parti-0002.jsonl, ... (klasördeki eski parti-*.jsonl dosyaları silinir).
Satır: {"urun_id", "ad", "marka", "kategori_en", "teknik": [[anahtar, değer], ...]}  (--yalniz-ad: "teknik" yok).
  teknik: urun_teknik.ozellikler satırlarının TAMAMI, sırasıyla (çeviri aynı sıra ve sayıda dönmeli).
--yalniz-eksik: geçerli (kaynak özeti tutan) çevirisi olmayanlar; tam kipte teknik satırı olup çevirisinde teknik
  bulunmayanlar da. kaynak='kaynak' satırı olan ürünler atlanır (yükleme onları ezmez).
Sıra: ürün kimliği.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from app.katalog.kategori_ceviri import KategoriCeviri
from app.katalog.marka import marka_cikar
from app.katalog.urun_ceviri import ceviriler_getir, teknik_satirlari

SORGU = (
    "SELECT u.id, u.ad, u.marka, k.ad AS kategori_ad, t.veri AS teknik_veri"
    " FROM urun u LEFT JOIN kategori k ON k.id = u.kategori_id LEFT JOIN urun_teknik t ON t.urun_id = u.id"
    " WHERE u.aktif = 1"
)


def salt_okunur_baglan(yol: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(Path(yol).resolve().as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def kayit_olustur(r: sqlite3.Row, ceviri: KategoriCeviri, yalniz_ad: bool = False) -> dict[str, Any]:
    """SORGU satırından dışa aktarma satırı; yükleme doğrulayıcısı da aynı kaydı (teknik dahil) kullanır."""
    kayit: dict[str, Any] = {
        "urun_id": r["id"], "ad": r["ad"],
        "marka": r["marka"] or marka_cikar(r["ad"]),
        "kategori_en": ceviri.cevir(r["kategori_ad"], "en"),
    }
    if not yalniz_ad:
        kayit["teknik"] = [[k, v] for k, v in teknik_satirlari(r["teknik_veri"])]
    return kayit


def urunleri_oku(con: sqlite3.Connection, *, sinir: int | None = None, yalniz_eksik: bool = False,
                 yalniz_ad: bool = False) -> list[dict[str, Any]]:
    ceviri = KategoriCeviri()
    satirlar = con.execute(SORGU + " ORDER BY u.id").fetchall()
    if yalniz_eksik:
        gecerli = ceviriler_getir(con, None)
        korumali = {r[0] for r in con.execute("SELECT urun_id FROM urun_ceviri WHERE dil = 'en' AND kaynak = 'kaynak'")}

        def eksik(r: sqlite3.Row) -> bool:
            if r["id"] in korumali:
                return False
            c = gecerli.get(r["id"])
            if c is None:
                return True
            return not yalniz_ad and c.teknik is None and bool(teknik_satirlari(r["teknik_veri"]))

        satirlar = [r for r in satirlar if eksik(r)]
    kayitlar = [kayit_olustur(r, ceviri, yalniz_ad) for r in satirlar]
    return kayitlar if sinir is None else kayitlar[:max(0, sinir)]


def parti_yaz(satirlar: list[dict[str, Any]], klasor: Path, parti: int) -> list[Path]:
    klasor.mkdir(parents=True, exist_ok=True)
    for eski in klasor.glob("parti-*.jsonl"):
        eski.unlink()
    yollar = []
    for i in range(0, len(satirlar), parti):
        yol = klasor / f"parti-{i // parti + 1:04d}.jsonl"
        with yol.open("w", encoding="utf-8", newline="\n") as f:
            for s in satirlar[i:i + parti]:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        yollar.append(yol)
    return yollar


def calistir(argv: Sequence[str] | None = None, cikti: TextIO = sys.stdout, hata: TextIO = sys.stderr) -> int:
    p = argparse.ArgumentParser(prog="betikler.ceviri_disa", description=__doc__.splitlines()[0])
    p.add_argument("--db", required=True)
    p.add_argument("--cikis", required=True)
    p.add_argument("--parti", type=int, default=100)
    p.add_argument("--sinir", type=int)
    p.add_argument("--yalniz-eksik", action="store_true")
    p.add_argument("--yalniz-ad", action="store_true", help="teknik özellikleri dışa aktarma (yalnız ad çevirisi)")
    a = p.parse_args(argv)
    if a.parti < 1:
        print("HATA: --parti en az 1 olmalı.", file=hata)
        return 2
    if not Path(a.db).is_file():
        print(f"HATA: veritabanı yok: {a.db}", file=hata)
        return 1
    try:
        con = salt_okunur_baglan(a.db)
        try:
            satirlar = urunleri_oku(con, sinir=a.sinir, yalniz_eksik=a.yalniz_eksik, yalniz_ad=a.yalniz_ad)
        finally:
            con.close()
    except sqlite3.Error as e:
        print(f"HATA: veritabanı okunamadı: {e}", file=hata)
        return 1
    yollar = parti_yaz(satirlar, Path(a.cikis), a.parti)
    print(json.dumps({"urun": len(satirlar), "parti": len(yollar), "klasor": str(Path(a.cikis))}, ensure_ascii=False),
          file=cikti)
    return 0


if __name__ == "__main__":
    sys.exit(calistir())
