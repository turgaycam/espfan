"""SQLite bağlantısı ve numaralı SQL geçişleri."""
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

GECIS_KLASORU = Path(__file__).parent / "gecisler"


def _gecis_004_doldur(con: sqlite3.Connection) -> None:
    """004'e özgü, DONDURULMUŞ doldurma: yalnız 004 anındaki sütunları kullanır (ileride indeksi_yeniden_kur yeni
    sütunlara dayansa da boş veritabanında 004 kırılmaz). Değer üreten saf fonksiyonlar paylaşılır."""
    from app.katalog.indeks import indeks_metni, turetilmis_alanlar  # geç içe aktarma: db katalogdan bağımsız

    satirlar = con.execute("SELECT id, ad, sku, uretici_kodu, aktif FROM urun").fetchall()
    turetilmis = {r[0]: turetilmis_alanlar(r[1], r[2], r[3]) for r in satirlar}
    con.executemany("UPDATE urun SET sira_anahtari = ?, kod_birlesik = ?, marka = ? WHERE id = ?",
                    [(t["sira_anahtari"], t["kod_birlesik"], t["marka"], i) for i, t in turetilmis.items()])
    con.execute("DELETE FROM urun_ara")
    con.executemany("INSERT INTO urun_ara (metin, kod_birlesik, urun_id) VALUES (?, ?, ?)",
                    [(indeks_metni(r[1], r[2], r[3]), turetilmis[r[0]]["kod_birlesik"], r[0])
                     for r in satirlar if r[4]])


def _gecis_013_doldur(con: sqlite3.Connection) -> None:
    """013: katli_metin/tip ve yeni sütunlu urun_ara. Şu anki indeksi_yeniden_kur'u kullanır; ileride urun_ara ya da
    türetilmiş alanlar yeni bir geçişte değişirse bu adım 004'teki gibi o anki sütunlarla dondurulmalıdır."""
    from app.katalog.indeks import indeksi_yeniden_kur  # geç içe aktarma: db katalogdan bağımsız

    indeksi_yeniden_kur(con)


# Geçişin SQL'inden hemen sonra, aynı transaction'da çalışan Python adımı: mevcut veriyi doldurur.
GECIS_SONRASI = {"004_arama_faset.sql": _gecis_004_doldur, "013_katli_tip.sql": _gecis_013_doldur}


def baglan(yol: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(yol), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    return con


def _uygulananlar(con: sqlite3.Connection) -> set[str]:
    tablo = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sema_surumu'"
    ).fetchone()
    if tablo is None:
        return set()
    return {r[0] for r in con.execute("SELECT dosya FROM sema_surumu")}


def bekleyen_gecisler(con: sqlite3.Connection) -> list[str]:
    """Henüz uygulanmamış geçiş dosyalarının adları (uygulamaz)."""
    uygulanan = _uygulananlar(con)
    return [d.name for d in sorted(GECIS_KLASORU.glob("[0-9][0-9][0-9]_*.sql")) if d.name not in uygulanan]


def gecisleri_uygula(con: sqlite3.Connection) -> list[str]:
    """Henüz uygulanmamış app/gecisler/NNN_*.sql dosyalarını sırayla, her birini
    kendi transaction'ında uygular; yeni uygulananların adlarını döner."""
    uygulanan = _uygulananlar(con)
    yeni: list[str] = []
    for dosya in sorted(GECIS_KLASORU.glob("[0-9][0-9][0-9]_*.sql")):
        if dosya.name in uygulanan:
            continue
        sql = dosya.read_text(encoding="utf-8")
        zaman = datetime.now(UTC).isoformat()
        # SQL, varsa Python adımı ve sema_surumu kaydı tek transaction'da: biri düşerse hepsi geri alınır
        try:
            con.executescript("BEGIN;\n" + sql + "\n;\n")
            sonrasi = GECIS_SONRASI.get(dosya.name)
            if sonrasi is not None:
                sonrasi(con)
            con.execute("INSERT INTO sema_surumu (dosya, uygulandi) VALUES (?, ?)", (dosya.name, zaman))
            con.commit()
        except BaseException:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        yeni.append(dosya.name)
    return yeni
