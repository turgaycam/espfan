"""G3f — urun_ceviri tablosu (geçiş 010), kaynak özeti, geçerli çeviri okuma ve FTS ad_en sütunu."""
from __future__ import annotations

import json
import sqlite3

import pytest

from app.katalog.depo import ListeSorgusu, urun_listele
from app.katalog.indeks import indeksi_yeniden_kur
from app.katalog.urun_ceviri import ceviriler_getir, kaynak_ozeti, teknik_satirlari
from tests.conftest import urun_ekle

AD = "KUKA 00-109-802 KRC2 GÜÇ KAYNAĞI 27V-NT"
TEKNIK = [["Giriş Voltajı (Input)", "0,72 kV"], ["Ağırlık", "3,5 kg"]]
TEKNIK_EN = [["Input Voltage (Input)", "0.72 kV"], ["Weight", "3.5 kg"]]


def ceviri_yaz(con, urun_id, ad_en, teknik_en=None, *, kaynak="llm-taslak", ozet=None, ad=AD, teknik=TEKNIK):
    with con:
        con.execute(
            "INSERT OR REPLACE INTO urun_ceviri (urun_id, dil, ad, teknik_json, kaynak, model, kaynak_ozet, uretildi)"
            " VALUES (?, 'en', ?, ?, ?, 'm', ?, '2026-10-13T00:00:00+00:00')",
            (urun_id, ad_en, json.dumps(teknik_en) if teknik_en is not None else None, kaynak,
             ozet or kaynak_ozeti(ad, teknik)))


def teknik_yaz(con, urun_id, ozellikler, bolumler=()):
    with con:
        con.execute("INSERT OR REPLACE INTO urun_teknik (urun_id, veri) VALUES (?, ?)",
                    (urun_id, json.dumps({"ozellikler": ozellikler, "bolumler": list(bolumler)}, ensure_ascii=False)))


def test_gecis_010_tablo_ve_kisitlar(con):
    u = urun_ekle(con, ad=AD)
    ceviri_yaz(con, u, "KUKA Power Supply")
    for alanlar in (("tr", "llm-taslak"), ("en", "insan")):
        with pytest.raises(sqlite3.IntegrityError):
            with con:
                con.execute("INSERT INTO urun_ceviri (urun_id, dil, ad, kaynak, kaynak_ozet, uretildi)"
                            " VALUES (?, ?, 'x', ?, 'o', 'z')", (u, *alanlar))
    with pytest.raises(sqlite3.IntegrityError):   # (urun_id, dil) birincil anahtar
        with con:
            con.execute("INSERT INTO urun_ceviri (urun_id, dil, ad, kaynak, kaynak_ozet, uretildi)"
                        " VALUES (?, 'en', 'x', 'kaynak', 'o', 'z')", (u,))
    with pytest.raises(sqlite3.IntegrityError):   # bilinmeyen ürün
        with con:
            con.execute("INSERT INTO urun_ceviri (urun_id, dil, ad, kaynak, kaynak_ozet, uretildi)"
                        " VALUES (999, 'en', 'x', 'kaynak', 'o', 'z')")
    sutunlar = [r[1] for r in con.execute("PRAGMA table_info(urun_ara)")]
    assert sutunlar == ["metin", "kod_birlesik", "ad_en", "kategori", "aciklama", "urun_id"]   # G3h: 013


def test_gecis_010_mevcut_arama_indeksini_korur(tmp_path, monkeypatch):
    import shutil

    from app import db as db_modulu
    from app.db import baglan, gecisleri_uygula

    eski = tmp_path / "gecisler"
    eski.mkdir()
    for dosya in sorted(db_modulu.GECIS_KLASORU.glob("00[0-9]_*.sql")):
        shutil.copy(dosya, eski / dosya.name)
    monkeypatch.setattr(db_modulu, "GECIS_KLASORU", eski)
    c = baglan(tmp_path / "eski.db")
    gecisleri_uygula(c)
    with c:
        c.execute("INSERT INTO urun (sku, ad, temsili_fiyat_eur, olusturma, kod_birlesik) "
                  "VALUES ('S1', 'RÖLE', '1.00', 'x', 's1')")
        c.execute("INSERT INTO urun_ara (metin, kod_birlesik, urun_id) VALUES ('role s1', 's1', 1)")
    monkeypatch.undo()
    assert gecisleri_uygula(c) == ["010_urun_ceviri.sql", "011_urun_sira_en.sql", "012_teklif_kalem_havale_suresi.sql",
                                   "013_katli_tip.sql", "014_po_aciliyet.sql",
                                   "015_teklif_teslim_adresi.sql", "016_indeksler.sql"]
    assert [r[0] for r in c.execute("SELECT urun_id FROM urun_ara WHERE urun_ara MATCH 'role'")] == [1]
    assert [r[0] for r in c.execute("SELECT urun_id FROM urun_ara WHERE urun_ara MATCH 'kod_birlesik : s1'")] == [1]
    c.close()


def test_kaynak_ozeti():
    o = kaynak_ozeti(AD, TEKNIK)
    assert len(o) == 16 and all(c in "0123456789abcdef" for c in o)
    assert o == kaynak_ozeti(AD, [tuple(x) for x in TEKNIK])
    assert o != kaynak_ozeti(AD + " ", TEKNIK)
    assert o != kaynak_ozeti(AD, TEKNIK[:1])
    assert o != kaynak_ozeti(AD, [["Giriş Voltajı (Input)", "0,73 kV"], TEKNIK[1]])
    assert kaynak_ozeti(AD, []) != kaynak_ozeti(AD, TEKNIK)


def test_teknik_satirlari():
    assert teknik_satirlari(None) == []
    assert teknik_satirlari("{bozuk") == []
    assert teknik_satirlari(json.dumps({"ozellikler": [["a", "b"], ["c"], [1, 2]], "bolumler": [["x", "y"]]})) \
        == [("a", "b")]


def test_gecerli_ceviri_okunur(con):
    u = urun_ekle(con, ad=AD)
    teknik_yaz(con, u, TEKNIK, [["Not", "metin"]])
    ceviri_yaz(con, u, "KUKA 00-109-802 KRC2 Power Supply 27V-NT", TEKNIK_EN)
    c = ceviriler_getir(con, [u])[u]
    assert c.ad == "KUKA 00-109-802 KRC2 Power Supply 27V-NT"
    assert c.teknik == (("Input Voltage (Input)", "0.72 kV"), ("Weight", "3.5 kg"))
    assert c.taslak


def test_bayat_ceviri_gosterilmez(con):
    a = urun_ekle(con, sku="A", ad=AD)
    b = urun_ekle(con, sku="B", ad=AD)
    teknik_yaz(con, a, TEKNIK)
    teknik_yaz(con, b, TEKNIK)
    ceviri_yaz(con, a, "KUKA Power Supply", TEKNIK_EN)
    ceviri_yaz(con, b, "KUKA Power Supply", TEKNIK_EN)
    with con:   # eşitleme adı ya da teknik veriyi değiştirdi
        con.execute("UPDATE urun SET ad = ? WHERE id = ?", (AD + " YENİ", a))
    teknik_yaz(con, b, [TEKNIK[0], ["Ağırlık", "4 kg"]])
    assert ceviriler_getir(con, [a, b]) == {}
    assert con.execute("SELECT COUNT(*) FROM urun_ceviri").fetchone()[0] == 2   # tablo silinmez


def test_teknik_satir_sayisi_tutmazsa_yalniz_ad(con):
    u = urun_ekle(con, ad=AD)
    teknik_yaz(con, u, TEKNIK)
    ceviri_yaz(con, u, "KUKA Power Supply", TEKNIK_EN[:1])
    c = ceviriler_getir(con, [u])[u]
    assert c.ad == "KUKA Power Supply" and c.teknik is None


def test_teknigi_olmayan_urun(con):
    u = urun_ekle(con, ad="ABB KABLO 3M")
    ceviri_yaz(con, u, "ABB Cable 3M", None, ad="ABB KABLO 3M", teknik=[])
    c = ceviriler_getir(con, [u])[u]
    assert (c.ad, c.teknik) == ("ABB Cable 3M", None)


def test_indeks_yeniden_kurulumu_gecerli_en_adi_ekler(con):
    a = urun_ekle(con, sku="A", ad=AD)
    b = urun_ekle(con, sku="B", ad="ABB SÜRÜCÜ ACS800")
    ceviri_yaz(con, a, "KUKA Power Supply Zeta", None, teknik=[])
    ceviri_yaz(con, b, "ABB Drive ACS800 Omega", None, ad="ESKİ AD", teknik=[])   # bayat
    with con:
        indeksi_yeniden_kur(con)
    bul = [r[0] for r in con.execute("SELECT urun_id FROM urun_ara WHERE urun_ara MATCH 'zeta'")]
    assert bul == [a]
    assert not con.execute("SELECT 1 FROM urun_ara WHERE urun_ara MATCH 'omega'").fetchall()


def test_arama_en_adla_yalniz_en_arayuzde(con):
    u = urun_ekle(con, ad=AD)
    ceviri_yaz(con, u, "KUKA 00-109-802 KRC2 Widget 27V-NT", None, teknik=[])
    with con:
        indeksi_yeniden_kur(con)
    assert [x.id for x in urun_listele(con, ListeSorgusu(arama="widget", dil="en")).urunler] == [u]
    assert urun_listele(con, ListeSorgusu(arama="widget")).urunler == []          # TR arayüz değişmez
    assert [x.id for x in urun_listele(con, ListeSorgusu(arama="guc kaynagi", dil="en")).urunler] == [u]
    assert [x.id for x in urun_listele(con, ListeSorgusu(arama="kuka krc2")).urunler] == [u]


def test_m3_teknik_gerekmezse_teknik_json_ayristirilmaz(con, monkeypatch):
    u = urun_ekle(con, ad=AD)
    teknik_yaz(con, u, TEKNIK)
    ceviri_yaz(con, u, "KUKA 00-109-802 KRC2 Power Supply 27V-NT", TEKNIK_EN)
    import app.katalog.urun_ceviri as uc
    cagri = []
    asil = uc._ciftler
    monkeypatch.setattr(uc, "_ciftler", lambda x: cagri.append(1) or asil(x))
    c = ceviriler_getir(con, None, teknik=False)[u]
    assert c.ad.endswith("27V-NT") and c.teknik is None
    assert len(cagri) == 1          # yalnız urun_teknik.veri (özet için); teknik_json ayrıştırılmadı


def test_m2_en_ada_gore_siralama(con):
    a = urun_ekle(con, sku="A", ad="AAA GÜÇ KAYNAĞI")       # EN: Zeta ...
    b = urun_ekle(con, sku="B", ad="BBB SERVO MOTOR")       # çevirisiz: TR anahtarı
    c = urun_ekle(con, sku="C", ad="CCC RÖLE")              # EN: Alpha ...
    ceviri_yaz(con, a, "Zeta Power Supply", None, ad="AAA GÜÇ KAYNAĞI", teknik=[])
    ceviri_yaz(con, c, "Alpha Relay", None, ad="CCC RÖLE", teknik=[])
    with con:
        indeksi_yeniden_kur(con)
    assert [u.id for u in urun_listele(con, ListeSorgusu(siralama="ad", dil="en")).urunler] == [c, b, a]
    assert [u.id for u in urun_listele(con, ListeSorgusu(siralama="ad")).urunler] == [a, b, c]
