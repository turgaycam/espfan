import sqlite3
import threading
from decimal import Decimal

import pytest

from app.ayarlar import ayarlari_oku
from app.db import baglan, gecisleri_uygula
from app.katalog.indeks import indeks_metni, indeksi_yeniden_kur
from app.metin import metin_temizle, normalize
from app.para import d, yuvarla
from tests.conftest import kategori_ekle, urun_ekle

TAM_ORTAM = {
    "SHOP_DB": "/tmp/shop.db",
    "SHOP_GIZLI_ANAHTAR": "g" * 32,
    "SHOP_YONETICI": "yonetici",
    "SHOP_YONETICI_OZET": "scrypt$16384$8$1$00$00",
}


def test_gecisler_ikinci_kez_atlanir(tmp_path):
    c = baglan(tmp_path / "yeni.db")
    assert gecisleri_uygula(c) == ["001_baslangic.sql", "002_gorsel_temizlik.sql", "003_seo_koruma.sql",
                                     "004_arama_faset.sql", "005_teknik_durum.sql", "006_durum_kaynak.sql",
                                     "007_teklif_iletisim.sql", "008_odeme_teklif_alanlari.sql",
                                   "009_odeme_zamani.sql", "010_urun_ceviri.sql", "011_urun_sira_en.sql",
                                   "012_teklif_kalem_havale_suresi.sql",
                                   "013_katli_tip.sql", "014_po_aciliyet.sql",
                                   "015_teklif_teslim_adresi.sql", "016_indeksler.sql"]
    assert gecisleri_uygula(c) == []
    kayitlar = [r["dosya"] for r in c.execute("SELECT dosya FROM sema_surumu")]
    assert kayitlar == ["001_baslangic.sql", "002_gorsel_temizlik.sql", "003_seo_koruma.sql",
                                     "004_arama_faset.sql", "005_teknik_durum.sql", "006_durum_kaynak.sql",
                                     "007_teklif_iletisim.sql", "008_odeme_teklif_alanlari.sql",
                                   "009_odeme_zamani.sql", "010_urun_ceviri.sql", "011_urun_sira_en.sql",
                                   "012_teklif_kalem_havale_suresi.sql",
                                   "013_katli_tip.sql", "014_po_aciliyet.sql",
                                   "015_teklif_teslim_adresi.sql", "016_indeksler.sql"]
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    c.close()


def test_ayarlar_tam():
    a = ayarlari_oku(TAM_ORTAM)
    assert a.db_yolu.name == "shop.db"
    assert a.kaynak_api == "https://www.ceylanrobot.com"
    assert a.bantlar_yolu.name == "bantlar.yaml"


@pytest.mark.parametrize(
    "eksik", ["SHOP_DB", "SHOP_GIZLI_ANAHTAR", "SHOP_YONETICI", "SHOP_YONETICI_OZET"]
)
def test_ayarlar_eksik_anahtar(eksik):
    ortam = {k: v for k, v in TAM_ORTAM.items() if k != eksik}
    with pytest.raises(RuntimeError, match=eksik):
        ayarlari_oku(ortam)


def test_yuvarla_half_up():
    assert yuvarla(Decimal("2.675")) == Decimal("2.68")
    assert yuvarla(Decimal("2.665")) == Decimal("2.67")
    assert yuvarla(Decimal("-2.675")) == Decimal("-2.68")
    assert str(yuvarla(Decimal("5"))) == "5.00"


def test_d_float_reddeder():
    with pytest.raises(TypeError):
        d(2.675)
    assert d("2.675") == Decimal("2.675")
    assert d(3) == Decimal(3)
    assert d(Decimal("1.5")) == Decimal("1.5")


def test_normalize_turkce():
    assert normalize("İZLEME RÖLESİ") == "izleme rolesi"
    assert normalize("ışık") == "isik"
    assert normalize("  ŞALTER   ÇIKIŞ  ") == "salter cikis"
    assert normalize("Güç Kaynağı") == "guc kaynagi"


def test_metin_temizle_bozuk_kodlama():
    sonuc = metin_temizle("GÜÇ KAYNA�\udc9eI")
    assert sonuc == "GÜÇ KAYNA�I"
    sonuc.encode("utf-8")  # UnicodeEncodeError vermemeli
    assert metin_temizle("A\udc9eB") == "A�B"
    assert metin_temizle("  düz metin ") == "düz metin"
    assert metin_temizle(None) is None


def test_yardimcilar_urun_ve_kategori(con):
    kid = kategori_ekle(con, kaynak_id="k1", ad="Elektrik ve Elektronik", yol="10", seviye=0)
    uid = urun_ekle(con, sku="X1", ad="Röle", kategori_id=kid)
    satir = con.execute("SELECT * FROM urun WHERE id=?", (uid,)).fetchone()
    assert satir["sku"] == "X1" and satir["kategori_id"] == kid
    assert satir["temsili_fiyat_eur"] == "100.00"
    bulunan = con.execute("SELECT urun_id FROM urun_ara WHERE urun_ara MATCH 'role'").fetchone()
    assert bulunan[0] == uid


def test_baglanti_baska_thread_te_kullanilabilir(con):
    # FastAPI senkron bağımlılıkları thread havuzunda çalışır (K8: check_same_thread=False)
    sonuc = []
    th = threading.Thread(target=lambda: sonuc.append(con.execute("SELECT 1").fetchone()[0]))
    th.start()
    th.join()
    assert sonuc == [1]


def test_esitleme_gunlugu_bozuk_kolonu(con):
    kolonlar = [r["name"] for r in con.execute("PRAGMA table_info(esitleme_gunlugu)")]
    assert "bozuk" in kolonlar


def test_indeks_metni():
    assert indeks_metni("SIEMENS SIRIUS İZLEME RÖLESİ", "8102030100019", "3UG4512-1BR20") == (
        "siemens sirius izleme rolesi 8102030100019 3ug4512-1br20")
    assert indeks_metni("Işık Perdesi", "S9", None) == "isik perdesi s9"


def test_urun_ekle_yeni_parametreler(con):
    uid = urun_ekle(con, sku="Y1", ad="Röle", uretici_kodu="3UG4512", gorsel_url="https://x/y.webp",
                    tedarik_suresi_gun=7)
    satir = con.execute("SELECT uretici_kodu, gorsel_url, tedarik_suresi_gun FROM urun WHERE id=?",
                        (uid,)).fetchone()
    assert tuple(satir) == ("3UG4512", "https://x/y.webp", 7)
    ara = con.execute("SELECT urun_id, typeof(urun_id) FROM urun_ara WHERE urun_ara MATCH '3ug4512*'").fetchone()
    assert tuple(ara) == (uid, "integer")


def test_indeksi_yeniden_kur(con):
    a = urun_ekle(con, sku="A1", ad="İzleme Rölesi")
    b = urun_ekle(con, sku="B1", ad="Pasif Ürün", aktif=False)
    with con:
        con.execute("DELETE FROM urun_ara")
        indeksi_yeniden_kur(con)
        indeksi_yeniden_kur(con)   # iki kez çağrılınca çift satır oluşmaz
    assert con.execute("SELECT COUNT(*) FROM urun_ara").fetchone()[0] == 1
    assert [r[0] for r in con.execute("SELECT urun_id FROM urun_ara WHERE urun_ara MATCH 'izleme'")] == [a]
    assert con.execute("SELECT COUNT(*) FROM urun_ara WHERE urun_id=?", (b,)).fetchone()[0] == 0


# --- G2: SEO / yayın modu ayarları ve 003 geçişi ---
def test_ayarlar_seo_varsayilanlari():
    a = ayarlari_oku(TAM_ORTAM)
    assert a.yayin_modu == "demo"
    assert a.site_kok == "http://192.168.5.30:3030"
    assert a.ai_tarayicilar == ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "CCBot")
    assert a.sayfa_hiz_limiti == 120


def test_ayarlar_seo_ortamdan():
    a = ayarlari_oku({**TAM_ORTAM, "SHOP_YAYIN_MODU": "uretim", "SHOP_SITE_KOK": "https://shop.example.com/",
                      "SHOP_AI_TARAYICILAR": "GPTBot, ClaudeBot,,"})
    assert a.yayin_modu == "uretim"
    assert a.site_kok == "https://shop.example.com"
    assert a.ai_tarayicilar == ("GPTBot", "ClaudeBot")


def test_ayarlar_bilinmeyen_yayin_modu_hata():
    with pytest.raises(RuntimeError, match="SHOP_YAYIN_MODU"):
        ayarlari_oku({**TAM_ORTAM, "SHOP_YAYIN_MODU": "canli"})


def test_gecis_003_tablolari(con):
    tablolar = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"urun_aciklama", "engelli_ip"} <= tablolar
    con.execute("INSERT INTO urun (sku, ad, temsili_fiyat_eur, olusturma) VALUES ('S', 'A', '1', 'x')")
    with pytest.raises(sqlite3.IntegrityError):  # kaynak değeri sınırlı
        con.execute("INSERT INTO urun_aciklama (urun_id, dil, metin, kaynak, uretildi) VALUES (1, 'tr', 'm', 'bilinmeyen', 'x')")
