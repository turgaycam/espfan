"""G3f — betikler.ceviri_disa (dışa aktarma) ve betikler.ceviri_yukle (doğrula + yükle)."""
from __future__ import annotations

import io
import json
import sqlite3

import pytest

from app.katalog.depo import ListeSorgusu, urun_listele
from app.katalog.urun_ceviri import ceviriler_getir, kaynak_ozeti
from betikler import ceviri_disa, ceviri_yukle
from tests.conftest import kategori_ekle, urun_ekle

AD = "KUKA 00-109-802 KRC2 GÜÇ KAYNAĞI 27V-NT"
TEKNIK = [["Giriş Voltajı (Input)", "0,72 kV"], ["Ağırlık", "3,5 kg"]]
AD_EN = "KUKA 00-109-802 KRC2 Power Supply 27V-NT"
TEKNIK_EN = [["Input Voltage (Input)", "0.72 kV"], ["Weight", "3.5 kg"]]


def _db_yolu(con):
    return con.execute("PRAGMA database_list").fetchone()["file"]


def _veri(con):
    k = kategori_ekle(con, kaynak_id="k1", ad="GÜÇ SİSTEMLERİ", yol="1", seviye=0)
    a = urun_ekle(con, sku="A1", ad=AD, kategori_id=k)
    b = urun_ekle(con, sku="B2", ad="ABB KABLO 3M", kategori_id=k)
    c = urun_ekle(con, sku="C3", ad="PASİF RÖLE", aktif=False)
    with con:
        con.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)", (a, json.dumps(
            {"ozellikler": TEKNIK, "bolumler": [["Not", "uzun metin"]]}, ensure_ascii=False)))
    return a, b, c


def _disa(con, tmp_path, *arg):
    cikis = tmp_path / "cikis"
    cikti = io.StringIO()
    assert ceviri_disa.calistir(["--db", _db_yolu(con), "--cikis", str(cikis), *arg], cikti) == 0
    satirlar = []
    for yol in sorted(cikis.glob("parti-*.jsonl")):
        satirlar += [json.loads(s) for s in yol.read_text(encoding="utf-8").splitlines()]
    return cikis, satirlar, json.loads(cikti.getvalue())


def test_disa_satir_bicimi(con, tmp_path):
    a, b, c = _veri(con)
    _, satirlar, ozet = _disa(con, tmp_path)
    assert [s["urun_id"] for s in satirlar] == [a, b]     # pasif yok
    assert satirlar[0] == {"urun_id": a, "ad": AD, "marka": "KUKA", "kategori_en": "POWER SYSTEMS", "teknik": TEKNIK}
    assert satirlar[1]["teknik"] == [] and satirlar[1]["marka"] == "ABB"
    assert ozet["urun"] == 2


def test_disa_yalniz_ad_parti_sinir(con, tmp_path):
    _veri(con)
    cikis, satirlar, _ = _disa(con, tmp_path, "--yalniz-ad", "--parti", "1")
    assert all(set(s) == {"urun_id", "ad", "marka", "kategori_en"} for s in satirlar)
    assert sorted(p.name for p in cikis.glob("parti-*.jsonl")) == ["parti-0001.jsonl", "parti-0002.jsonl"]
    cikis, satirlar, _ = _disa(con, tmp_path, "--sinir", "1")
    assert len(satirlar) == 1 and sorted(p.name for p in cikis.glob("parti-*.jsonl")) == ["parti-0001.jsonl"]


def test_disa_yalniz_eksik(con, tmp_path):
    a, b, c = _veri(con)
    d = urun_ekle(con, sku="D4", ad="SİEMENS RÖLE 24V")
    with con:
        # a: geçerli, teknikli çeviri (eksik değil); b: bayat çeviri (eksik); d: kaynak (korumalı, atlanır)
        con.execute("INSERT INTO urun_ceviri VALUES (?, 'en', ?, ?, 'llm-taslak', 'm', ?, 't')",
                    (a, AD_EN, json.dumps(TEKNIK_EN), kaynak_ozeti(AD, TEKNIK)))
        con.execute("INSERT INTO urun_ceviri VALUES (?, 'en', 'ABB Cable', NULL, 'llm-taslak', 'm', 'eski', 't')", (b,))
        con.execute("INSERT INTO urun_ceviri VALUES (?, 'en', 'Siemens Relay 24V', NULL, 'kaynak', NULL, 'eski', 't')",
                    (d,))
    _, satirlar, _ = _disa(con, tmp_path, "--yalniz-eksik")
    assert [s["urun_id"] for s in satirlar] == [b]
    with con:   # a'nın çevirisinde teknik yok: tam çeviri için eksik, yalnız ad için değil
        con.execute("UPDATE urun_ceviri SET teknik_json = NULL WHERE urun_id = ?", (a,))
    _, satirlar, _ = _disa(con, tmp_path, "--yalniz-eksik")
    assert [s["urun_id"] for s in satirlar] == [a, b]
    _, satirlar, _ = _disa(con, tmp_path, "--yalniz-eksik", "--yalniz-ad")
    assert [s["urun_id"] for s in satirlar] == [b]


def test_disa_salt_okunur(con, tmp_path):
    _veri(con)
    ro = ceviri_disa.salt_okunur_baglan(_db_yolu(con))
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("DELETE FROM urun_ceviri")
    ro.close()
    assert ceviri_disa.calistir(["--db", str(tmp_path / "yok.db"), "--cikis", str(tmp_path / "c")],
                                io.StringIO(), io.StringIO()) == 1


# ---------- yükleme ----------
def _yukle(con, tmp_path, satirlar, *arg, kod=0):
    girdi = tmp_path / "girdi"
    girdi.mkdir(exist_ok=True)
    (girdi / "cikti-0001.jsonl").write_text(
        "\n".join(s if isinstance(s, str) else json.dumps(s, ensure_ascii=False) for s in satirlar) + "\n",
        encoding="utf-8")
    ret = tmp_path / "ret"
    cikti = io.StringIO()
    assert ceviri_yukle.calistir(["--db", _db_yolu(con), "--girdi", str(girdi), "--model", "claude-haiku-5-5",
                                  "--ret", str(ret), *arg], cikti, io.StringIO()) == kod
    if kod:
        return None, None
    assert not (girdi / "reddedilen.jsonl").exists()          # girdi klasörüne yazılmaz
    reddedilen = [json.loads(s) for s in (ret / "reddedilen.jsonl").read_text(encoding="utf-8").splitlines()]
    return json.loads(cikti.getvalue()), reddedilen


def test_yukle_yazar_ozet_ve_fts(con, tmp_path):
    a, b, c = _veri(con)
    ozet, red = _yukle(con, tmp_path, [{"urun_id": a, "ad_en": AD_EN, "teknik_en": TEKNIK_EN},
                                       {"urun_id": b, "ad_en": "ABB Cable 3M", "teknik_en": None}])
    assert (ozet["okunan"], ozet["yazilan"], ozet["reddedilen"], red) == (2, 2, 0, [])
    r = con.execute("SELECT * FROM urun_ceviri WHERE urun_id = ?", (a,)).fetchone()
    assert (r["dil"], r["ad"], r["kaynak"], r["model"]) == ("en", AD_EN, "llm-taslak", "claude-haiku-5-5")
    assert json.loads(r["teknik_json"]) == TEKNIK_EN and r["kaynak_ozet"] == kaynak_ozeti(AD, TEKNIK)
    assert con.execute("SELECT teknik_json FROM urun_ceviri WHERE urun_id = ?", (b,)).fetchone()[0] is None
    assert set(ceviriler_getir(con, [a, b])) == {a, b}
    # FTS: yükleme EN adı indekse yazar
    assert [u.id for u in urun_listele(con, ListeSorgusu(arama="cable", dil="en")).urunler] == [b]


def test_yalniz_ad_yuklemesi_teknik_cevirisini_korur(con, tmp_path):
    a, *_ = _veri(con)
    _yukle(con, tmp_path, [{"urun_id": a, "ad_en": AD_EN, "teknik_en": TEKNIK_EN}])
    ozet, _ = _yukle(con, tmp_path, [{"urun_id": a, "ad_en": "KUKA 00-109-802 KRC2 Power Unit 27V-NT",
                                      "teknik_en": None}])
    assert ozet["yazilan"] == 1
    c = ceviriler_getir(con, [a])[a]
    assert c.ad == "KUKA 00-109-802 KRC2 Power Unit 27V-NT" and c.teknik == tuple(map(tuple, TEKNIK_EN))


def test_yukle_kaynak_satiri_ezilmez(con, tmp_path):
    a, *_ = _veri(con)
    with con:
        con.execute("INSERT INTO urun_ceviri VALUES (?, 'en', 'ELLE', NULL, 'kaynak', NULL, 'o', 't')", (a,))
    ozet, red = _yukle(con, tmp_path, [{"urun_id": a, "ad_en": AD_EN, "teknik_en": TEKNIK_EN}])
    assert ozet["yazilan"] == 0 and ozet["nedenler"] == {"kaynak_korumali": 1}
    assert red == [{"urun_id": a, "nedenler": ["kaynak_korumali"], "dosya": "cikti-0001.jsonl", "satir_no": 1}]
    assert tuple(con.execute("SELECT ad, kaynak FROM urun_ceviri").fetchone()) == ("ELLE", "kaynak")
    ozet, _ = _yukle(con, tmp_path, [{"urun_id": a, "ad_en": AD_EN, "teknik_en": TEKNIK_EN}], "--kuru")
    assert ozet["yazilan"] == 0 and ozet["nedenler"] == {"kaynak_korumali": 1}


def test_yukle_kuru_yazmaz(con, tmp_path):
    a, *_ = _veri(con)
    ozet, red = _yukle(con, tmp_path, [{"urun_id": a, "ad_en": AD_EN, "teknik_en": TEKNIK_EN}], "--kuru")
    assert ozet["kuru"] is True and ozet["yazilan"] == 1 and red == []
    assert con.execute("SELECT COUNT(*) FROM urun_ceviri").fetchone()[0] == 0
    assert urun_listele(con, ListeSorgusu(arama="supply", dil="en")).urunler == []


def test_yukle_reddedilenler(con, tmp_path):
    a, b, c = _veri(con)
    ozet, red = _yukle(con, tmp_path, [
        "{bozuk json",
        {"urun_id": 99999, "ad_en": "X Power", "teknik_en": None},
        {"urun_id": c, "ad_en": "Passive Relay", "teknik_en": None},          # pasif
        {"urun_id": a, "ad_en": AD_EN, "teknik_en": "metin"},                 # bozuk alan
        {"urun_id": "1", "ad_en": AD_EN},                                     # bozuk alan
        {"urun_id": b, "ad_en": "ABB Kablo 3M", "teknik_en": None},           # Türkçe kalıntı
        {"urun_id": a, "ad_en": AD_EN, "teknik_en": TEKNIK_EN},
        {"urun_id": a, "ad_en": AD_EN, "teknik_en": TEKNIK_EN},               # yinelenen
    ])
    assert (ozet["okunan"], ozet["yazilan"], ozet["reddedilen"]) == (8, 1, 7)
    assert ozet["nedenler"] == {"bozuk_json": 1, "urun_yok": 2, "bozuk_alan": 2, "turkce_kalinti": 1,
                                "yinelenen": 1}
    assert {"urun_id": 99999, "nedenler": ["urun_yok"], "dosya": "cikti-0001.jsonl", "satir_no": 2} in red
    assert con.execute("SELECT COUNT(*) FROM urun_ceviri").fetchone()[0] == 1


def test_yukle_eksik_klasor_ve_db(con, tmp_path):
    _veri(con)
    assert ceviri_yukle.calistir(["--db", _db_yolu(con), "--girdi", str(tmp_path / "yok"), "--model", "m",
                                  "--ret", str(tmp_path / "r")], io.StringIO(), io.StringIO()) == 1
    (tmp_path / "g").mkdir()
    assert ceviri_yukle.calistir(["--db", str(tmp_path / "yok.db"), "--girdi", str(tmp_path / "g"), "--model", "m",
                                  "--ret", str(tmp_path / "r")], io.StringIO(), io.StringIO()) == 1


# ---------- Düzeltme turu 1 ----------
def test_i2_asamalar_arasi_esitleme_bayat_ceviriyi_yazmaz(con, tmp_path, monkeypatch):
    a, b, _ = _veri(con)
    asil = ceviri_yukle._asama1

    def araya_esitleme(*arg, **kw):
        sonuc = asil(*arg, **kw)
        ayri = sqlite3.connect(_db_yolu(con))
        with ayri:
            ayri.execute("UPDATE urun SET ad = ? WHERE id = ?", (AD + " YENİ", a))
        ayri.close()
        return sonuc

    monkeypatch.setattr(ceviri_yukle, "_asama1", araya_esitleme)
    ozet, red = _yukle(con, tmp_path, [{"urun_id": a, "ad_en": AD_EN, "teknik_en": TEKNIK_EN},
                                       {"urun_id": b, "ad_en": "ABB Cable 3M", "teknik_en": None}])
    assert ozet["yazilan"] == 1 and ozet["nedenler"] == {"kaynak_degisti": 1}
    assert red[0]["urun_id"] == a and red[0]["nedenler"] == ["kaynak_degisti"]
    assert con.execute("SELECT COUNT(*) FROM urun_ceviri WHERE urun_id = ?", (a,)).fetchone()[0] == 0
    assert urun_listele(con, ListeSorgusu(arama="supply", dil="en")).urunler == []   # FTS'e bayat ad girmedi


def test_m4_uyari_sayilari_ozette(con, tmp_path):
    k = kategori_ekle(con, kaynak_id="k9", ad="X", yol="9", seviye=0)
    u = urun_ekle(con, sku="T1", ad="ABB MOTOR 1.500 W", kategori_id=k)
    ozet, _ = _yukle(con, tmp_path, [{"urun_id": u, "ad_en": "ABB Motor 1500 W", "teknik_en": None}])
    assert ozet["yazilan"] == 1 and ozet["uyari"] == {"binlik_ayrac": 1}
