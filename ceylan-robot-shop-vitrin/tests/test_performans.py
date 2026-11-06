"""G3a ölçütü: 4.449 ürünlü sahte katalogda liste sayfası (sorgu + şablon) < 300 ms, HTML < 150 KB.

Süre TestClient içinden ölçülür (ASGI uygulaması + SQLite + Jinja; ağ yok) — sunucu süresine karşılık gelir.
Her adres önce bir kez ısıtılır, sonra 5 isteğin ortancası alınır. Ölçümler `-s` ile yazdırılır.
"""
import random
import statistics
import time

import pytest

from app.katalog.indeks import indeks_metni, indeksi_yeniden_kur, turetilmis_alanlar
from tests.conftest import istemci_db

URUN_SAYISI = 4449
SURE_SINIRI = 0.300
BOYUT_SINIRI = 150_000
MARKALAR = ("KUKA", "ABB", "FANUC", "SIEMENS", "OMRON", "FESTO", "SMC", "YASKAWA", "PILZ", "SICK", "SEW", "LENZE")
KELIMELER = ("SERVO MOTOR", "SÜRÜCÜ", "GÜÇ KAYNAĞI", "RÖLE", "KONTAKTÖR", "KABLO SETİ", "REDÜKTÖR", "ENKODER",
             "KONTROL KARTI", "ŞARTLANDIRICI", "VALF", "SENSÖR", "PANEL", "CPU", "GİRİŞ MODÜLÜ")
KOKLER = ("Elektrik ve Elektronik", "Endüstriyel Robotlar", "Mekanik", "Robotik Parçaları", "Robot Kontrol Üniteleri",
          "Pnömatik", "Sensörler", "Kablolar")


@pytest.fixture
def buyuk_katalog(istemci):
    rnd = random.Random(20261013)
    with istemci_db(istemci) as con:
        kategoriler: list[tuple[int, str, str]] = []   # (id, yol, kök adı)
        for i, kok in enumerate(KOKLER, 1):
            con.execute("INSERT INTO kategori (kaynak_id, ad, yol, seviye) VALUES (?, ?, ?, 0)", (f"k{i}", kok, str(i)))
            for j in range(1, 7):
                yol2 = f"{i}.{j}"
                con.execute("INSERT INTO kategori (kaynak_id, ad, ust_kaynak_id, yol, seviye) VALUES (?, ?, ?, ?, 1)",
                            (f"k{yol2}", f"{kok.upper()} ALT {j}", f"k{i}", yol2))
                for m in range(1, 5):
                    yol3 = f"{yol2}.{m}"
                    con.execute("INSERT INTO kategori (kaynak_id, ad, ust_kaynak_id, yol, seviye) VALUES (?, ?, ?, ?, 2)",
                                (f"k{yol3}", f"{rnd.choice(KELIMELER)} GRUBU {m}", f"k{yol2}", yol3))
        for kid, yol, kaynak_id in con.execute("SELECT id, yol, kaynak_id FROM kategori WHERE seviye = 2"):
            kategoriler.append((kid, yol, KOKLER[int(yol.split(".")[0]) - 1]))
        satirlar = []
        for n in range(URUN_SAYISI):
            kid, _, kok = rnd.choice(kategoriler)
            ad = f"{rnd.choice(MARKALAR)} {rnd.choice(KELIMELER)} {rnd.randint(1, 999)}{rnd.choice('ABCDEFKX')}"
            sku = f"85{n:011d}"
            uretici = f"{rnd.randint(0, 99):02d}-{rnd.randint(0, 999):03d}-{rnd.randint(0, 999):03d}" if n % 3 else (
                f"6ES7{rnd.randint(100, 999)}-{rnd.randint(1, 9)}EA{rnd.randint(0, 99):02d}-0AA0")
            teklif = kok == "Endüstriyel Robotlar"
            fiyat = f"{rnd.randint(20, 9000)}.00" if not teklif else f"{rnd.randint(16000, 90000)}.00"
            t = turetilmis_alanlar(ad, sku, uretici)
            satirlar.append((sku, ad, uretici, kid, kok, rnd.choice((0, 0, 1, 2, 5)), fiyat, int(teklif),
                             rnd.choice(("belirtilmemis",) * 12 + ("yeni", "ikinci_el_test_edildi")),
                             "2026-10-13T00:00:00+00:00", t["sira_anahtari"], t["kod_birlesik"], t["marka"]))
        con.executemany(
            "INSERT INTO urun (sku, ad, uretici_kodu, kategori_id, kok_kategori_ad, stok, temsili_fiyat_eur,"
            " teklif_zorunlu, durum_kodu, olusturma, sira_anahtari, kod_birlesik, marka)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", satirlar)
        indeksi_yeniden_kur(con)
        assert indeks_metni("A", "B", None) == "a b"
        kok_id = con.execute("SELECT id FROM kategori WHERE yol = '1'").fetchone()[0]
        alt_id = con.execute("SELECT id FROM kategori WHERE yol = '1.2'").fetchone()[0]
        bir_kod = con.execute("SELECT uretici_kodu FROM urun WHERE uretici_kodu LIKE '__-___-___' LIMIT 1").fetchone()[0]
        assert con.execute("SELECT COUNT(*) FROM urun WHERE aktif = 1").fetchone()[0] == URUN_SAYISI
    return {"kok": kok_id, "alt": alt_id, "kod": bir_kod}


def _olc(istemci, yol: str) -> tuple[float, int]:
    ilk = istemci.get(yol)
    assert ilk.status_code == 200, (yol, ilk.status_code)
    sureler = []
    for _ in range(5):
        bas = time.perf_counter()
        yanit = istemci.get(yol)
        sureler.append(time.perf_counter() - bas)
        assert yanit.status_code == 200
    return statistics.median(sureler), len(yanit.content)


def test_g3a_liste_sayfalari_300ms_ve_150kb_altinda(istemci, buyuk_katalog):
    k = buyuk_katalog
    yollar = [
        f"/tr/kategori/{k['kok']}",                                   # en büyük kök kategori (~560 ürün)
        f"/tr/kategori/{k['alt']}?marka=Siemens&marka=KUKA&stokta=1&sira=fiyat_artan",
        "/tr/urunler",                                                 # tüm 4.449 ürün
        "/tr/urunler?sayfa=50&durum=belirtilmemis&fiyatli=1",
        "/tr/ara?q=siemens+servo",
        f"/tr/ara?q={k['kod'].replace('-', '')}",                      # ayraçsız parça kodu
        "/en/urunler?tedarikli=1",
        "/tr/urunler?fmin=1000&fmax=50000&sira=fiyat_azalan",         # G3e: görünen kipte fiyat aralığı
        "/en/ara?q=power+supply",                                      # G3e: eşanlamlı genişletme
        "/tr/urunler?adet=48",                                         # G3e: sayfa başına 48
    ]
    olcumler = {yol: _olc(istemci, yol) for yol in yollar}
    for yol, (sure, boyut) in olcumler.items():
        print(f"\nPERF {sure * 1000:6.1f} ms  {boyut / 1024:6.1f} KB  {yol}")
    for yol, (sure, boyut) in olcumler.items():
        assert sure < SURE_SINIRI, (yol, sure)
        assert boyut < BOYUT_SINIRI, (yol, boyut)
