"""G3h geri doldurma: türetilmiş ürün alanlarını (katli_metin, tip vb.) ve arama indeksini yeniden kurar.

Eşitleme her turda aynı işi yapar (indeksi_yeniden_kur); bu betik eşitlemeyi beklemeden (ör. tip.yaml değişince ya da
açıklama yüklemesinden sonra) çalıştırmak içindir. Yalnız türetilmiş alanları ve urun_ara'yı yazar; urun_ceviri ve
urun_aciklama'yı yalnız okur.

Çalıştırma (release kökünden): venv/bin/python -m betikler.turetilmis_doldur [--db YOL]
(--db verilmezse ortamdaki ayarlardan). Çıktı: tek satır JSON — toplam aktif ürün, tip dağılımı, "diger" oranı.
Geçiş UYGULAMAZ (inceleme M-5): şema geride ise hata JSON'u ve çıkış 2; geçişler yedek alan
`python -m app.gecis_calistir` ile uygulanır.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from app.db import baglan, bekleyen_gecisler
from app.katalog.indeks import indeksi_yeniden_kur


def dagilim(con) -> dict:
    satirlar = con.execute("SELECT tip, COUNT(*) FROM urun WHERE aktif = 1 GROUP BY tip ORDER BY 2 DESC, 1").fetchall()
    toplam = sum(n for _, n in satirlar)
    sayilar = {t: n for t, n in satirlar}
    return {"toplam": toplam, "dagilim": sayilar,
            "diger_orani": round(sayilar.get("diger", 0) / toplam, 4) if toplam else 0.0}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, help="veritabanı yolu (verilmezse SHOP_* ortam ayarlarından)")
    arg = ap.parse_args(argv)
    if arg.db is not None:
        yol = arg.db
    else:
        from app.ayarlar import ayarlari_oku
        yol = ayarlari_oku(os.environ).db_yolu
    con = baglan(yol)
    try:
        bekleyen = bekleyen_gecisler(con)
        if bekleyen:
            print(json.dumps({"durum": "hata", "bekleyen_gecisler": bekleyen,
                              "hata": "şema geride: önce geçişleri yedekli uygulayın (python -m app.gecis_calistir)"},
                             ensure_ascii=False), flush=True)
            return 2
        with con:
            indeksi_yeniden_kur(con)
        print(json.dumps(dagilim(con), ensure_ascii=False), flush=True)
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
