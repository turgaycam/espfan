"""G3d ayar turu 4 (pilot-denetim): istem kuralları, marka türetme, --cesitli, çelişki, çift kabul, EN biçim, SKU, uyarı."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from app.katalog import aciklama_dogrula
from app.katalog.aciklama_dogrula import dogrula, tur_celiskisi, uyarilar
from betikler import aciklama_disa, aciklama_yukle
from tests.conftest import kategori_ekle, urun_ekle
from tests.test_aciklama import EN, TR, URUN, _db_yolu, _disa, _yukle, _yukle_urunu

ISTEM = (Path(__file__).resolve().parents[1] / "betikler" / "aciklama_istem.md").read_text(encoding="utf-8")


# ---------- 1. istem ----------
@pytest.mark.parametrize("parca", [
    "çelişiyorsa",                       # ad/teknik çelişkisinde işlev yazma
    "açıkça",                            # kullanım cümlesi yalnız açık uygulama varsa
    "üç fazlı",                          # çıkarım yasağı örneği (3 × AC)
    "karar",                             # 2-3 karar değeri, ilk satırlar değil
    "SKU",                               # SKU yasağı
    "listelenmektedir",
    "stokta bulunmaktadır",              # sabit stok şablonları
    "şu anda stokta görünmemektedir",
    "currently out of stock",
    "87%",                               # EN yüzde biçimi
    "açılış",                            # açılış kalıbı rotasyonu
])
def test_istem_kurallari(parca):
    assert parca.lower() in ISTEM.lower()


# ---------- 2. dışa aktarma: marka, --cesitli, çelişki ----------
def test_disa_bos_marka_adtan_turetilir(con, tmp_path):
    uid = urun_ekle(con, sku="M1", ad="SIEMENS KONTROL KARTI")
    with con:
        con.execute("UPDATE urun SET marka = NULL WHERE id = ?", (uid,))
    _, satirlar, _ = _disa(con, tmp_path)
    assert satirlar[0]["marka"] == "Siemens"


def _cesit_db(con):
    kat = {ad: kategori_ekle(con, kaynak_id=f"k{i}", ad=ad, yol=str(i), seviye=0)
           for i, ad in enumerate(["Robot Kolu", "Servo Motor", "Teach Pendant", "Kontrol Kartı", "Kablo", "Diğer"])}
    durumlar = ["yeni", "yenilenmis", "ikinci_el", "ikinci_el_test_edildi", "ikinci_el_oldugu_gibi", "belirtilmemis"]
    idler = {}
    n = 0
    for ad, kid in kat.items():
        for d in durumlar:
            for _ in range(3):
                n += 1
                uid = urun_ekle(con, sku=f"C{n}", ad=f"{ad.upper()} URUN {n}", kategori_id=kid)
                with con:
                    con.execute("UPDATE urun SET durum_kodu = ?, durum_ornek = 0 WHERE id = ?", (d, uid))
                idler[uid] = (ad, d)
    return idler


def test_cesitli_tabakali_ornek(con, tmp_path):
    idler = _cesit_db(con)
    _, s1, _ = _disa(con, tmp_path, "--cesitli", "20")
    secilen = {s["urun_id"] for s in s1}
    assert len(secilen) == 20
    assert {idler[i][0] for i in secilen} == {"Robot Kolu", "Servo Motor", "Teach Pendant", "Kontrol Kartı", "Kablo", "Diğer"}
    assert {idler[i][1] for i in secilen} == {"yeni", "yenilenmis", "ikinci_el", "ikinci_el_test_edildi",
                                              "ikinci_el_oldugu_gibi", "belirtilmemis"}
    _, s2, _ = _disa(con, tmp_path, "--cesitli", "20")
    assert [s["urun_id"] for s in s2] == [s["urun_id"] for s in s1]  # deterministik
    _, s3, _ = _disa(con, tmp_path, "--cesitli", "20", "--tohum", "7")
    assert {s["urun_id"] for s in s3} != secilen  # tohum değişince örnek değişir


def test_cesitli_az_urunde_zorunlular_dahil(con, tmp_path):
    idler = _cesit_db(con)
    _, s, _ = _disa(con, tmp_path, "--cesitli", "3")
    assert len(s) >= 6  # N zorunlu tabaka sayısından küçükse zorunlular yine dahil
    assert {idler[x["urun_id"]][1] for x in s} >= {"yeni", "yenilenmis", "ikinci_el", "ikinci_el_test_edildi",
                                                    "ikinci_el_oldugu_gibi", "belirtilmemis"}


FILTRE_TEKNIK = {"ozellikler": [["Nominal Direnç Değeri", "90 Ω"], ["Sürekli Güç", "150 W"]], "bolumler": []}


def _celiskili_urun(con):
    uid = urun_ekle(con, sku="F1", ad="LTI-MOTION AKIM FILTRESI", uretici_kodu="BR-090.02.540")
    with con:
        con.execute("INSERT INTO urun_teknik VALUES (?, ?)", (uid, json.dumps(FILTRE_TEKNIK, ensure_ascii=False)))
    return uid


def test_tur_celiskisi_tablosu():
    f = {"ad": "LTI AKIM FILTRESI", "teknik": FILTRE_TEKNIK["ozellikler"], "kaynak_aciklama": None}
    assert tur_celiskisi(f) == "filtre_direnc"
    assert tur_celiskisi({**f, "teknik": [["Nominal Akım", "16 A"]]}) is None
    trafo = {"ad": "MBS TRANSFORMATÖR", "teknik": [["Çıkış", "20 mA"]], "kaynak_aciklama": None}
    assert tur_celiskisi(trafo) == "trafo_ma_va_yok"
    assert tur_celiskisi({**trafo, "teknik": [["Güç", "100 VA"], ["Çıkış", "20 mA"]]}) is None
    assert tur_celiskisi({"ad": "SEW TRAFO", "teknik": [["Endüktans", "0.1 mH"]], "kaynak_aciklama": None}) == "trafo_ma_va_yok"
    assert tur_celiskisi({"ad": "ABB DEVRE KESICI", "teknik": [["Bobin Gerilimi", "24 V"]],
                          "kaynak_aciklama": None}) == "kesici_bobin"


def test_disa_celiskili_atlanir_ve_listelenir(con, tmp_path):
    bozuk = _celiskili_urun(con)
    saglam = urun_ekle(con, sku="S1", ad="PUELS GUC KAYNAGI")
    cikis, satirlar, ozet = _disa(con, tmp_path)
    assert [s["urun_id"] for s in satirlar] == [saglam]
    assert ozet["celiskili"] == 1
    liste = [json.loads(x) for x in (cikis / "celiskili.jsonl").read_text(encoding="utf-8").splitlines()]
    assert liste[0]["urun_id"] == bozuk and liste[0]["neden"] == "filtre_direnc"
    _, hepsi, _ = _disa(con, tmp_path, "--no-atla-celiskili")
    assert {s["urun_id"] for s in hepsi} == {bozuk, saglam}


# ---------- 3. doğrulayıcı / yükleyici ----------
def test_en_bicim_kurallari():
    assert "en_bicim" in dogrula(EN + " Efficiency is %87.", "en", URUN)
    assert "en_bicim" in dogrula(EN + " Output current is 5 Amper.", "en", URUN)
    assert "en_bicim" in dogrula(EN + " Power is 5 Watt.", "en", URUN)
    assert "en_bicim" not in dogrula(EN, "en", URUN)
    assert "en_bicim" not in dogrula(TR + " Verim %87.", "tr", URUN)  # TR'de % öneki serbest


@pytest.mark.parametrize("kelime", ["Çıkış şalteri", "kademe ışığı", "ığdır", "İkinci"])
def test_en_turkce_karakter(kelime):
    assert "dil" in dogrula(EN + " " + kelime + " is installed.", "en", {**URUN, "ad": "ABB MODUL"})


def test_en_turkce_karakter_ad_icinde_serbest():
    urun = {**URUN, "ad": "SIEMENS ŞEBEKE GÜÇ KAYNAĞI"}
    assert "dil" not in dogrula(EN.replace("power supply", "ŞEBEKE power supply"), "en", urun)


def test_sku_metinde_yasak():
    assert "sku" in dogrula(TR + " Kayıt no 8102030100019.", "tr", URUN)
    assert "sku" in dogrula(TR + " Kayıt no 8102 0301 00019.", "tr", URUN)
    assert "sku" not in dogrula(TR, "tr", URUN)


def test_islev_fiili_yalniz_uyari():
    kaynak = {**URUN, "kaynak_aciklama": None}
    metin = TR + " Cihaz aşırı gerilimi korur ve sinyali yeniler."
    assert "islev_fiili" in uyarilar(metin, "tr", kaynak)
    assert uyarilar(TR, "tr", kaynak) == []
    assert "islev_fiili" not in uyarilar(metin, "tr", {**kaynak, "kaynak_aciklama": "Aşırı gerilimi korur, sinyali yeniler."})
    assert not any(k == "islev_fiili" for k in dogrula(metin, "tr", kaynak))  # ret değil
    assert "islev_fiili" in uyarilar("It protects the line and regenerates the signal.", "en", kaynak)


def _satirlar(uid, tr=TR, en=EN):
    return [{"urun_id": uid, "dil": "tr", "metin": tr}, {"urun_id": uid, "dil": "en", "metin": en}]


def test_cift_eksik_ikisi_de_reddedilir(con, tmp_path):
    uid = _yukle_urunu(con)
    ozet, red = _yukle(con, tmp_path, _satirlar(uid, en="kısa"))  # en geçersiz -> tr de reddedilir
    assert ozet["yazilan"] == 0
    assert ozet["nedenler"]["cift_eksik"] == 1 and ozet["nedenler"]["uzunluk"] == 1
    assert any(r["nedenler"] == ["cift_eksik"] and r["dil"] == "tr" for r in red)
    assert con.execute("SELECT COUNT(*) FROM urun_aciklama").fetchone()[0] == 0


def test_cift_eksik_tek_dil_satiri(con, tmp_path):
    uid = _yukle_urunu(con)
    ozet, red = _yukle(con, tmp_path, [{"urun_id": uid, "dil": "tr", "metin": TR}])
    assert ozet["yazilan"] == 0 and ozet["nedenler"] == {"cift_eksik": 1}
    assert con.execute("SELECT COUNT(*) FROM urun_aciklama").fetchone()[0] == 0


def test_cift_tam_yazilir_ve_uyari_sayilir(con, tmp_path):
    uid = _yukle_urunu(con)
    tr = TR + " Cihaz sinyali yeniler."
    ozet, _ = _yukle(con, tmp_path, _satirlar(uid, tr=tr[:1190]))
    assert ozet["yazilan"] == 2
    assert ozet["uyari"].get("islev_fiili", 0) >= 1
    assert ozet["reddedilen"] == 0
