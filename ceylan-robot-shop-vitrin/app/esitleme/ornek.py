"""Gösterim amaçlı örnek ürün durumu (spec §5.1). Kaynakta durum bilgisi yok; atananlar durum_ornek=1 ile işaretlenir."""
from __future__ import annotations

import sqlite3

ORNEK_DURUMLAR = ("yeni", "ikinci_el_test_edildi", "ikinci_el_oldugu_gibi")


def ornek_durumlari_ata(con: sqlite3.Connection, adet: int = 15) -> int:
    if con.execute("SELECT 1 FROM urun WHERE durum_ornek = 1 LIMIT 1").fetchone():
        return 0
    idler = [r[0] for r in con.execute(
        "SELECT id FROM urun WHERE aktif = 1 AND teklif_zorunlu = 0 AND durum_kodu = 'belirtilmemis'"
        " ORDER BY sku LIMIT ?", (adet,))]
    for sira, urun_id in enumerate(idler):
        con.execute("UPDATE urun SET durum_kodu = ?, durum_ornek = 1 WHERE id = ?",
                    (ORNEK_DURUMLAR[sira % len(ORNEK_DURUMLAR)], urun_id))
    return len(idler)
