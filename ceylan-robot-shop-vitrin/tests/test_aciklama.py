"""G3d — LLM taslak açıklama doğrulayıcısı, dışa aktarma ve yükleme betikleri."""
from __future__ import annotations

import io
import json
import sqlite3

import pytest

from app.katalog.aciklama_dogrula import dogrula
from betikler import aciklama_disa, aciklama_yukle
from tests.conftest import kategori_ekle, urun_ekle

URUN = {
    "ad": "SIEMENS SIMATIC S7-300 GÜÇ KAYNAĞI", "sku": "8102030100019", "uretici_kodu": "6ES7 307-1EA00-0AA0",
    "marka": "Siemens", "durum_kodu": "ikinci_el_test_edildi",
    "teknik": [["Giriş gerilimi", "120/230 V AC"], ["Çıkış akımı", "5 A"]],
    "kaynak_aciklama": "SIEMENS SIRIUS izleme rölesi. 24 V DC besleme.",
}
TR = (
    "Siemens SIMATIC S7-300 güç kaynağı, 6ES7 307-1EA00-0AA0 üretici koduyla listelenen bir otomasyon parçasıdır. "
    "Genellikle S7-300 denetleyici sistemlerinde besleme için kullanılır ve panolarda yedek parça olarak aranır.\n\n"
    "Kayıtlı teknik özellikler arasında giriş gerilimi 120/230 V AC ve çıkış akımı 5 A bilgisi yer alır. "
    "Bunun dışında bir değer verilmemiştir; kullanım öncesinde uyumluluğu parça numarasından doğrulayın.\n\n"
    "Ürün ikinci el ve test edilmiş olarak sunulur. Fiyat ve ihracat koşulları için teklif isteyebilirsiniz."
)
EN = (
    "The Siemens SIMATIC S7-300 power supply is an automation part listed under manufacturer code "
    "6ES7307-1EA00-0AA0. It is generally used to supply S7-300 controller systems and is often sought as a spare part "
    "in control cabinets.\n\n"
    "The recorded technical data include an input voltage of 120/230 V AC and an output current of 5 A. No other "
    "values are given, so please confirm compatibility from the part number before use.\n\n"
    "The item is offered used and tested. You can request a quote for price and export terms."
)


def _kodlar(metin, dil="tr", **degisiklik):
    return dogrula(metin, dil, {**URUN, **degisiklik})


def test_gecerli_tr_ve_en():
    assert _kodlar(TR, "tr") == []
    assert _kodlar(EN, "en") == []


def test_uzunluk():
    assert "uzunluk" in _kodlar("Kısa ve bir metin için.", "tr")
    assert "uzunluk" in _kodlar(TR * 3, "tr")


def test_dil():
    assert "dil" in _kodlar(EN, "tr")
    assert "dil" in _kodlar(TR, "en")
    assert "dil" not in _kodlar(TR, "tr")


def test_uydurma_sayi_ve_parca_kodu_katlamasi():
    assert "uydurma_sayi" in _kodlar(TR.replace("5 A", "7,5 A"))
    assert "uydurma_sayi" in _kodlar(TR + " Üretim yılı 2019.")
    assert "uydurma_sayi" in _kodlar(TR.replace("6ES7 307-1EA00-0AA0", "6ES7 999-1AA00"))
    # boşluk/tire katlaması her iki yönde: metinde ayraçsız, kaynakta ayraçlı
    assert "uydurma_sayi" not in _kodlar(TR.replace("6ES7 307-1EA00-0AA0", "6ES7307-1EA00-0AA0"))
    assert "uydurma_sayi" not in _kodlar(EN, "en")
    # kaynak_aciklama'dan gelen değer geçerli
    assert "uydurma_sayi" not in _kodlar(TR + " Besleme 24 V DC olarak belirtilmiştir.")


def test_izinli_genel_sayilar_yalniz_baglaminda():
    assert "uydurma_sayi" not in _kodlar(TR + " 12 ay garanti sunulur.")
    assert "uydurma_sayi" not in _kodlar(TR + " 14 gün içinde iade edilebilir.")
    assert "uydurma_sayi" not in _kodlar(TR + " Bu 2. el bir üründür.")
    assert "uydurma_sayi" in _kodlar(TR + " 12 kg ağırlığındadır.")
    assert "uydurma_sayi" in _kodlar(TR + " 14 mm çapındadır.")


@pytest.mark.parametrize("ek", [
    "Yetkili satıcı olarak sunulur.", "Authorized dealer parts.", "Orijinal garanti kapsamındadır.",
    "En ucuz fiyat.", "%100 çalışır.", "Pazar Otomasyon gibi değil.", "Lektronix benzeri.",
    "Bize info@ornek.com adresinden yazın.", "Bkz www.ornek.com.tr", "Arayın +90 532 123 45 67.",
])
def test_yasak_ifade(ek):
    assert "yasak_ifade" in _kodlar(TR + " " + ek)


def test_yasak_ifade_gecen():
    assert "yasak_ifade" not in _kodlar(TR)


def test_durum_celiski():
    assert "durum_celiski" in _kodlar(TR + " Sıfır ürün gibidir.")
    assert "durum_celiski" in _kodlar(EN + " Practically brand new.", "en")
    assert "durum_celiski" in _kodlar(TR, durum_kodu="belirtilmemis")  # "test edilmiş" iddiası
    assert "durum_celiski" not in _kodlar(TR + " Yenilenmiş değildir.")  # yenilenmiş != yeni
    belirtilmemis = TR.replace("ikinci el ve test edilmiş olarak sunulur", "durumu belirtilmemiştir").replace(
        "test edilmiş", "kontrollü")
    assert "durum_celiski" not in _kodlar(belirtilmemis, durum_kodu="belirtilmemis")
    assert "durum_celiski" in _kodlar(TR + " Ürün yeni.", durum_kodu="belirtilmemis")
    assert "durum_celiski" not in _kodlar(TR.replace("ikinci el ve test edilmiş olarak", "olarak") + " Ürün sıfır ve yeni.", durum_kodu="yeni")


@pytest.mark.parametrize("degisim", [
    lambda t: t + " <b>kalın</b>", lambda t: t + " `kod`", lambda t: "# Başlık\n" + t,
    lambda t: t + "\n* madde", lambda t: t + "\n- madde",
    lambda t: t + "\n\nDördüncü paragraf.",
])
def test_html(degisim):
    assert "html" in _kodlar(degisim(TR))


def test_marka_uydurma():
    assert "marka_uydurma" in _kodlar(TR + " Bu parça ABB sistemleriyle de çalışır.")
    assert "marka_uydurma" not in _kodlar(TR)
    assert "marka_uydurma" in _kodlar(TR, marka="KUKA")  # metinde Siemens, ürün KUKA
    assert "marka_uydurma" not in _kodlar(TR.replace("Siemens", "genel"), marka=None)


# ---------- veritabanı yardımcıları ----------
def _db(con):
    k = kategori_ekle(con, kaynak_id="k1", ad="Endüstriyel Robotlar", yol="1", seviye=0)
    a = urun_ekle(con, sku="A1", ad="SIEMENS GÜÇ KAYNAĞI", uretici_kodu="6ES7 307", kategori_id=k, kok="Mekanik")
    b = urun_ekle(con, sku="B2", ad="KUKA KABLO", kategori_id=k, stok=0)
    c = urun_ekle(con, sku="C3", ad="PASİF", aktif=False)
    d = urun_ekle(con, sku="D4", ad="ABB MOTOR", kategori_id=k)
    with con:
        con.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)", (d, json.dumps(
            {"ozellikler": [[f"o{i}", f"{i}"] for i in range(30)],
             "bolumler": [["", "x" * 2000]]}, ensure_ascii=False)))
    return a, b, c, d


def _db_yolu(con):
    return con.execute("PRAGMA database_list").fetchone()["file"]


def _disa(con, tmp_path, *arg):
    cikis = tmp_path / "cikis"
    cikti = io.StringIO()
    assert aciklama_disa.calistir(["--db", _db_yolu(con), "--cikis", str(cikis), *arg], cikti) == 0
    satirlar = []
    for yol in sorted(cikis.glob("parti-*.jsonl")):
        satirlar += [json.loads(s) for s in yol.read_text(encoding="utf-8").splitlines()]
    return cikis, satirlar, json.loads(cikti.getvalue())


def test_disa_siralama_alanlar_ve_pasif_yok(con, tmp_path):
    a, b, c, d = _db(con)
    cikis, satirlar, ozet = _disa(con, tmp_path)
    assert [s["urun_id"] for s in satirlar] == [d, a, b]  # teknik olan önce, pasif yok
    s = satirlar[0]
    assert set(s) == {"urun_id", "ad", "sku", "uretici_kodu", "marka", "kategori", "kok_kategori", "kategori_en",
                      "kok_kategori_en", "durum_kodu", "durum_kaynak", "stok_durumu", "teknik", "kaynak_aciklama"}
    assert len(s["teknik"]) == 20 and len(s["kaynak_aciklama"]) <= 1500
    assert s["kategori_en"] == "Industrial Robots" and s["stok_durumu"] == "stokta"
    assert satirlar[2]["stok_durumu"] == "stok_yok" and satirlar[2]["kaynak_aciklama"] is None
    assert "base64" not in (cikis / "parti-0001.jsonl").read_text(encoding="utf-8")
    assert ozet["urun"] == 3


def test_disa_parti_sinir_urun_id(con, tmp_path):
    a, b, c, d = _db(con)
    cikis, satirlar, ozet = _disa(con, tmp_path, "--parti", "2")
    assert sorted(p.name for p in cikis.glob("parti-*.jsonl")) == ["parti-0001.jsonl", "parti-0002.jsonl"]
    _, satirlar, _ = _disa(con, tmp_path, "--sinir", "1")
    assert len(satirlar) == 1
    _, satirlar, _ = _disa(con, tmp_path, "--urun-id", f"{a},{b}")
    assert sorted(s["urun_id"] for s in satirlar) == sorted([a, b])


def test_disa_yalniz_eksik(con, tmp_path):
    a, b, c, d = _db(con)
    with con:
        for dil in ("tr", "en"):
            con.execute("INSERT INTO urun_aciklama VALUES (?, ?, 'x', 'kaynak', NULL, 't')", (a, dil))
        con.execute("INSERT INTO urun_aciklama VALUES (?, 'tr', 'x', 'llm-taslak', 'm', 't')", (b,))
    _, satirlar, _ = _disa(con, tmp_path, "--yalniz-eksik")
    assert sorted(s["urun_id"] for s in satirlar) == sorted([b, d])


def test_disa_salt_okunur(con, tmp_path):
    _db(con)
    ro = aciklama_disa.salt_okunur_baglan(_db_yolu(con))
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("DELETE FROM urun")
    ro.close()
    assert aciklama_disa.calistir(["--db", str(tmp_path / "yok.db"), "--cikis", str(tmp_path / "c")],
                                  io.StringIO(), io.StringIO()) == 1


def test_disa_ornek_durum_belirtilmemis_sayilir(con, tmp_path):
    a, *_ = _db(con)
    with con:
        con.execute("UPDATE urun SET durum_kodu='yeni', durum_ornek=1 WHERE id=?", (a,))
    _, satirlar, _ = _disa(con, tmp_path, "--urun-id", str(a))
    assert satirlar[0]["durum_kodu"] == "belirtilmemis" and satirlar[0]["durum_kaynak"] == "ornek"


# ---------- yükleme ----------
def _siemens_metin(dil):
    return TR if dil == "tr" else EN


def _yukle_urunu(con):
    uid = urun_ekle(con, sku="8102030100019", ad=URUN["ad"], uretici_kodu=URUN["uretici_kodu"])
    with con:
        con.execute("UPDATE urun SET durum_kodu='ikinci_el_test_edildi' WHERE id=?", (uid,))
        con.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)", (uid, json.dumps(
            {"ozellikler": URUN["teknik"], "bolumler": [["", URUN["kaynak_aciklama"]]]}, ensure_ascii=False)))
    return uid


def _yukle(con, tmp_path, satirlar, *arg):
    girdi = tmp_path / "girdi"
    girdi.mkdir(exist_ok=True)
    (girdi / "cikti-0001.jsonl").write_text(
        "\n".join(s if isinstance(s, str) else json.dumps(s, ensure_ascii=False) for s in satirlar) + "\n",
        encoding="utf-8")
    cikti = io.StringIO()
    kod = aciklama_yukle.calistir(["--db", _db_yolu(con), "--girdi", str(girdi), "--model", "claude-haiku-5-5", *arg],
                                  cikti)
    assert kod == 0
    reddedilen = [json.loads(s) for s in (girdi / "reddedilen.jsonl").read_text(encoding="utf-8").splitlines()]
    return json.loads(cikti.getvalue()), reddedilen


def test_yukle_yazar_ve_llm_taslagi_gunceller(con, tmp_path):
    uid = _yukle_urunu(con)
    ozet, red = _yukle(con, tmp_path, [{"urun_id": uid, "dil": "tr", "metin": TR},
                                       {"urun_id": uid, "dil": "en", "metin": EN}])
    assert ozet["okunan"] == 2 and ozet["yazilan"] == 2 and ozet["reddedilen"] == 0 and red == []
    r = con.execute("SELECT * FROM urun_aciklama WHERE urun_id=? AND dil='tr'", (uid,)).fetchone()
    assert r["kaynak"] == "llm-taslak" and r["model"] == "claude-haiku-5-5" and r["metin"] == TR
    yeni = TR.replace("Genellikle", "Çoğunlukla genellikle")
    ozet, _ = _yukle(con, tmp_path, [{"urun_id": uid, "dil": "tr", "metin": yeni},
                                     {"urun_id": uid, "dil": "en", "metin": EN}])
    assert ozet["yazilan"] == 2
    assert con.execute("SELECT metin FROM urun_aciklama WHERE urun_id=? AND dil='tr'", (uid,)).fetchone()[0] == yeni


def test_yukle_kaynak_satiri_ezilmez(con, tmp_path):
    uid = _yukle_urunu(con)
    with con:
        con.execute("INSERT INTO urun_aciklama VALUES (?, 'tr', 'ELLE', 'kaynak', NULL, 't')", (uid,))
    ozet, red = _yukle(con, tmp_path, [{"urun_id": uid, "dil": "tr", "metin": TR},
                                       {"urun_id": uid, "dil": "en", "metin": EN}])
    assert ozet["yazilan"] == 1 and ozet["nedenler"] == {"kaynak_korumali": 1}
    assert red[0]["nedenler"] == ["kaynak_korumali"] and red[0]["dil"] == "tr"
    assert con.execute("SELECT metin, kaynak FROM urun_aciklama WHERE dil='tr'").fetchone()[:] == ("ELLE", "kaynak")


def test_yukle_kuru_yazmaz(con, tmp_path):
    uid = _yukle_urunu(con)
    ozet, _ = _yukle(con, tmp_path, [{"urun_id": uid, "dil": "tr", "metin": TR},
                                     {"urun_id": uid, "dil": "en", "metin": EN}], "--kuru")
    assert ozet["yazilan"] == 2 and ozet["kuru"] is True
    assert con.execute("SELECT COUNT(*) FROM urun_aciklama").fetchone()[0] == 0


def test_yukle_reddedilenler_ve_devam(con, tmp_path):
    uid = _yukle_urunu(con)
    pasif = urun_ekle(con, sku="P1", ad="PASİF", aktif=False)
    ozet, red = _yukle(con, tmp_path, [
        "{bozuk json", {"urun_id": 99999, "dil": "tr", "metin": TR}, {"urun_id": pasif, "dil": "tr", "metin": TR},
        {"urun_id": uid, "dil": "tr", "metin": "kısa ve bir"}, {"urun_id": uid, "dil": "fr", "metin": TR},
        {"urun_id": uid, "dil": "en", "metin": EN},
    ])
    assert ozet["okunan"] == 6 and ozet["yazilan"] == 0 and ozet["reddedilen"] == 6  # en geçti ama tr geçmedi: cift_eksik
    assert ozet["nedenler"]["cift_eksik"] == 1 and ozet["nedenler"]["bozuk_json"] == 1 and ozet["nedenler"]["urun_yok"] == 2
    assert ozet["nedenler"]["uzunluk"] == 1 and ozet["nedenler"]["bozuk_alan"] == 1
    assert len(red) == 6 and {"urun_id": 99999, "dil": "tr", "nedenler": ["urun_yok"], "dosya": "cikti-0001.jsonl",
                              "satir_no": 2} in red
    assert con.execute("SELECT COUNT(*) FROM urun_aciklama").fetchone()[0] == 0
