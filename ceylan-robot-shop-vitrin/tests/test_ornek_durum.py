from app.esitleme.ornek import ORNEK_DURUMLAR, ornek_durumlari_ata
from tests.conftest import urun_ekle


def test_ilk_cagri_atar_ikinci_cagri_dokunmaz(con):
    for i in range(20):
        urun_ekle(con, sku=f"S{i:03d}", ad=f"Ürün {i}")
    urun_ekle(con, sku="R001", ad="Robot", kok="Endüstriyel Robotlar", teklif=True)
    urun_ekle(con, sku="P001", ad="Pasif", aktif=False)

    assert ornek_durumlari_ata(con, adet=15) == 15
    satirlar = con.execute(
        "SELECT sku, durum_kodu FROM urun WHERE durum_ornek = 1 ORDER BY sku").fetchall()
    assert [s["sku"] for s in satirlar] == [f"S{i:03d}" for i in range(15)]
    assert [s["durum_kodu"] for s in satirlar[:3]] == list(ORNEK_DURUMLAR)
    # teklif zorunlu ve pasif ürünlere atanmaz
    assert con.execute("SELECT COUNT(*) FROM urun WHERE sku IN ('R001','P001') AND durum_ornek = 1").fetchone()[0] == 0

    assert ornek_durumlari_ata(con, adet=15) == 0
    assert con.execute("SELECT COUNT(*) FROM urun WHERE durum_ornek = 1").fetchone()[0] == 15


def test_bos_katalog(con):
    assert ornek_durumlari_ata(con) == 0


def test_g3b_kaynaktan_durumu_olan_urune_ornek_atanmaz(con):
    for i in range(3):
        urun_ekle(con, sku=f"S{i:03d}", ad=f"Ürün {i}")
    with con:
        con.execute("UPDATE urun SET durum_kodu = 'yenilenmis' WHERE sku = 'S000'")
    assert ornek_durumlari_ata(con, adet=2) == 2
    assert con.execute("SELECT durum_kodu, durum_ornek FROM urun WHERE sku = 'S000'").fetchone()[:] == ("yenilenmis", 0)
