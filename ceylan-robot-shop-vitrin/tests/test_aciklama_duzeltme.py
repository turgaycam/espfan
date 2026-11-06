"""G3d düzeltme turu 1: doğrulayıcı kaçakları (C-1, I-1, I-2, I-4, M-1, M-4), yükleme sertleştirme ve disa/yukle testleri."""
from __future__ import annotations

import io
import json
import sqlite3

import pytest

from app.katalog.aciklama_dogrula import dogrula
from betikler import aciklama_disa, aciklama_yukle
from tests.conftest import urun_ekle
from tests.test_aciklama import EN, TR, URUN, _db_yolu, _yukle, _yukle_urunu

KUKA = {
    "ad": "KUKA KR 16 R2010 ROBOT KOLU", "sku": "8102030100019", "uretici_kodu": "00-123-456", "marka": "KUKA",
    "durum_kodu": "ikinci_el_test_edildi", "teknik": [["Yük", "16,5 kg"], ["Besleme", "24 V DC"]],
    "kaynak_aciklama": None,
}
GOVDE = (
    "KUKA KR 16 R2010 robot kolu, 00-123-456 üretici koduyla listelenen bir endüstriyel robot ürünüdür. "
    "Genellikle üretim hatlarında taşıma ve montaj işlerinde kullanılır ve yedek parça olarak aranır.\n\n"
    "Kayıtlı teknik özellikler arasında yük 16,5 kg ve besleme 24 V DC bilgisi yer alır. Bunun dışında bir değer "
    "verilmemiştir; kullanım öncesinde uyumluluğu parça numarasından doğrulayın.\n\n"
    "Ürün ikinci el ve test edilmiş olarak sunulur. Fiyat ve ihracat koşulları için teklif isteyebilirsiniz."
)


def _k(metin, dil="tr", **d):
    return dogrula(metin, dil, {**KUKA, **d})


def test_govde_gecerli():
    assert _k(GOVDE) == []


@pytest.mark.parametrize("ek", [
    "Yük 16 kg taşır.", "Yük 5 kg taşır.", "Erişim 2010 mm.", "Çap 00 mm.", "Yük 30 kg.", "Hız 24 m/s.",
    "Ağırlık 1020 adet.", "Kapasite 2030 kg.", "Kod mr-j3 uyumlu.", "Kod 1EA00 uyumlu.", "Uzunluk 123 mm.",
    "Gerilim 5 V.", "Ağırlık 165 kg.", "Çıkış 6 eksen.", "Üretim yılı 2019.", "Güç 456 W.",
])
def test_c1_uydurma_sayi_kacaklari(ek):
    assert "uydurma_sayi" in _k(GOVDE + " " + ek)


def test_c1_kaynaktaki_degerler_gecer():
    assert "uydurma_sayi" not in _k(GOVDE + " Yük 16,5 kg ve model KR 16 olarak kayıtlıdır.")
    assert "uydurma_sayi" not in _k(GOVDE + " Besleme 24V DC olarak belirtilmiştir.")
    assert "uydurma_sayi" not in _k(GOVDE + " Kod 00123456 olarak da yazılır.")


def test_c1_sku_ad_rakamlari_bagimsiz_sayi_degil():
    s = {"ad": "SIEMENS S7-300 MODÜL", "sku": "8102030100019", "uretici_kodu": None}
    assert "uydurma_sayi" in dogrula(GOVDE + " Boyut 300 mm.", "tr", {**KUKA, **s})
    assert "uydurma_sayi" not in dogrula(GOVDE.replace("KUKA KR 16 R2010", "S7-300") + " S7-300 serisi.", "tr",
                                           {**KUKA, **s, "teknik": KUKA["teknik"], "uretici_kodu": "00-123-456"})


def test_i1_garanti_yalniz_garantili_durumlarda():
    ek = " 12 ay garanti sunulur."
    assert "durum_celiski" in _k(GOVDE.replace("ikinci el ve test edilmiş", "ikinci el") + ek, durum_kodu="ikinci_el")
    assert "durum_celiski" in _k(GOVDE + ek, durum_kodu="yeni") or "uydurma_sayi" in _k(GOVDE + ek, durum_kodu="yeni")
    assert "uydurma_sayi" not in _k(GOVDE + ek) and "durum_celiski" not in _k(GOVDE + ek)


@pytest.mark.parametrize("ek", ["12-month warranty.", "14-day return.", "2nd hand unit.", "2nd-hand item.",
                                "12 aylık garanti.", "14 günlük iade."])
def test_i2_izinli_kaliplar(ek):
    assert "uydurma_sayi" not in _k(GOVDE + " " + ek)


@pytest.mark.parametrize("durum,ek", [
    ("ikinci_el", "Kullanılmamış ürün."), ("ikinci_el", "Unused item."), ("ikinci_el_oldugu_gibi", "Yenilenmiş ve test edilmiş."),
    ("yeni", "Bu bir ikinci el ürün."), ("yeni", "A used part."), ("yenilenmis", "Test edilmemiş durumda."),
    ("ikinci_el_test_edildi", "Refurbished unit."), ("belirtilmemis", "İkinci el ürün."),
])
def test_i4_durum_celiskileri(durum, ek):
    govde = GOVDE.replace("ikinci el ve test edilmiş olarak", "olarak")
    assert "durum_celiski" in _k(govde + " " + ek, durum_kodu=durum)


def test_i4_olumsuzlama_izinli():
    assert "durum_celiski" not in _k(GOVDE + " Yenilenmiş değildir. It is not refurbished.")


@pytest.mark.parametrize("ek", ["Authorised dealer.", "Official dealer.", "Yetkili servis.", "Yetkili distribütör.",
                                "Official distributor.", "Fabrika garantisi.", "PazarOtomasyon gibi.", "Mers-Robot gibi."])
def test_m1_yasak_ifade(ek):
    assert "yasak_ifade" in _k(GOVDE + " " + ek)


def test_m4_dil_sezgisi():
    ingilizce_tr_oneki = "The unit is generally used in robot systems. " * 8 + "Çıkış 5 A."
    assert "dil" in dogrula(ingilizce_tr_oneki, "tr", {**KUKA, "teknik": [["Çıkış", "5 A"]]})
    ad_turkce = {**KUKA, "ad": "KUKA ÇIKIŞ ÜNİTESİ KR 16"}
    assert "dil" not in dogrula(EN.replace("Siemens SIMATIC S7-300 power supply", "KUKA ÇIKIŞ ÜNİTESİ"), "en", ad_turkce)


def test_m6_numarali_liste():
    assert "html" in _k("1. madde\n" + GOVDE)


def test_uzun_metin_yalniz_uzunluk():
    assert _k("a@b.co " * 2000) == ["uzunluk"]


# ---------- yükleme ----------
def _satir_yaz(girdi, ad, satirlar, kodlama="utf-8"):
    girdi.mkdir(exist_ok=True)
    (girdi / ad).write_bytes(("\n".join(satirlar) + "\n").encode(kodlama))


def _calistir(con, girdi, *arg):
    cikti = io.StringIO()
    assert aciklama_yukle.calistir(["--db", _db_yolu(con), "--girdi", str(girdi), "--model", "m", *arg], cikti) == 0
    return json.loads(cikti.getvalue()), [json.loads(s) for s in
                                          (girdi / "reddedilen.jsonl").read_text(encoding="utf-8").splitlines()]


def test_m2_bom_u2028_yinelenen_ve_konum(con, tmp_path):
    uid = _yukle_urunu(con)
    girdi = tmp_path / "g"
    satir_tr = json.dumps({"urun_id": uid, "dil": "tr", "metin": TR}, ensure_ascii=False)
    ham_u2028 = json.dumps({"urun_id": uid, "dil": "en", "metin": EN.replace("part ", "part ")}, ensure_ascii=False)
    _satir_yaz(girdi, "cikti-0001.jsonl", [satir_tr, satir_tr, "{bozuk", ham_u2028], "utf-8-sig")
    ozet, red = _calistir(con, girdi)
    assert ozet["nedenler"].get("yinelenen") == 1 and ozet["nedenler"].get("bozuk_json") == 1
    assert ozet["yazilan"] == 2  # tr (ilk) + en; yinelenen tr reddedildi
    assert not any(r["nedenler"] == ["bozuk_json"] and r["satir_no"] == 4 for r in red)  # U+2028 satırı bölmedi
    bozuk = [r for r in red if r["nedenler"] == ["bozuk_json"]][0]
    assert bozuk["dosya"] == "cikti-0001.jsonl" and bozuk["satir_no"] == 3
    assert con.execute("SELECT COUNT(*) FROM urun_aciklama WHERE dil='tr'").fetchone()[0] == 1


def test_i3_atomik_ve_yazma_dogrulamadan_sonra(con, tmp_path, monkeypatch):
    uid = _yukle_urunu(con)
    girdi = tmp_path / "g"
    _satir_yaz(girdi, "cikti-0001.jsonl", [json.dumps({"urun_id": uid, "dil": "tr", "metin": TR}, ensure_ascii=False),
                                          json.dumps({"urun_id": uid, "dil": "en", "metin": EN}, ensure_ascii=False)])
    olaylar: list[str] = []
    orijinal = aciklama_yukle.dogrula

    def izle(*a, **k):
        olaylar.append("dogrula")
        return orijinal(*a, **k)

    monkeypatch.setattr(aciklama_yukle, "dogrula", izle)
    _calistir(con, girdi)
    assert olaylar == ["dogrula", "dogrula"]
    assert con.execute("SELECT COUNT(*) FROM urun_aciklama").fetchone()[0] == 2


def test_i3_yazma_hatasinda_hicbiri_yazilmaz(con, tmp_path, monkeypatch):
    uid = _yukle_urunu(con)
    girdi = tmp_path / "g"
    _satir_yaz(girdi, "cikti-0001.jsonl", [json.dumps({"urun_id": uid, "dil": "tr", "metin": TR}, ensure_ascii=False),
                                          json.dumps({"urun_id": uid, "dil": "en", "metin": EN}, ensure_ascii=False)])
    monkeypatch.setattr(aciklama_yukle, "_UPSERT", aciklama_yukle._UPSERT.replace("'llm-taslak'), ?, ?)", "'llm-taslak'), ?)", 1)
                        .replace("VALUES (?, ?, ?, 'llm-taslak', ?, ?)", "VALUES (?, ?, ?, 'gecersiz-kaynak', ?, ?)"))
    with pytest.raises(sqlite3.IntegrityError):
        aciklama_yukle.calistir(["--db", _db_yolu(con), "--girdi", str(girdi), "--model", "m"], io.StringIO())
    assert con.execute("SELECT COUNT(*) FROM urun_aciklama").fetchone()[0] == 0


def test_m5_kaynak_en_ve_karisik_girdi(con, tmp_path):
    uid = _yukle_urunu(con)
    with con:
        con.execute("INSERT INTO urun_aciklama VALUES (?, 'en', 'HAND', 'kaynak', NULL, 't')", (uid,))
    girdi = tmp_path / "g"
    _satir_yaz(girdi, "cikti-0001.jsonl", [
        json.dumps({"urun_id": uid, "dil": "tr", "metin": TR}, ensure_ascii=False),
        json.dumps({"urun_id": uid, "dil": "en", "metin": EN}, ensure_ascii=False),
        json.dumps({"urun_id": True, "dil": "tr", "metin": TR}), json.dumps({"urun_id": uid, "dil": "tr"}),
    ])
    ozet, red = _calistir(con, girdi, "--kuru")
    assert ozet["yazilan"] == 1 and ozet["nedenler"] == {"bozuk_alan": 2, "kaynak_korumali": 1}
    assert len(red) == 3
    ozet, _ = _calistir(con, girdi)
    assert con.execute("SELECT metin FROM urun_aciklama WHERE dil='en'").fetchone()[0] == "HAND"


def test_m5_calistir_salt_okunur_baglanir(con, tmp_path, monkeypatch):
    _yukle_urunu(con)
    cagrilar = []
    gercek = aciklama_disa.salt_okunur_baglan
    monkeypatch.setattr(aciklama_disa, "salt_okunur_baglan", lambda y: cagrilar.append(y) or gercek(y))
    assert aciklama_disa.calistir(["--db", _db_yolu(con), "--cikis", str(tmp_path / "c")], io.StringIO()) == 0
    assert len(cagrilar) == 1


def test_m5_parti_dagilimi_ve_eski_dosya_silme(con, tmp_path):
    for i in range(5):
        urun_ekle(con, sku=f"Z{i}", ad=f"URUN {i}")
    cikis = tmp_path / "c"
    cikis.mkdir()
    (cikis / "parti-0009.jsonl").write_text("eski", encoding="utf-8")
    assert aciklama_disa.calistir(["--db", _db_yolu(con), "--cikis", str(cikis), "--parti", "2"], io.StringIO()) == 0
    adlar = sorted(p.name for p in cikis.glob("parti-*.jsonl"))
    assert adlar == ["parti-0001.jsonl", "parti-0002.jsonl", "parti-0003.jsonl"]
    sayilar = [len((cikis / a).read_text(encoding="utf-8").splitlines()) for a in adlar]
    assert sayilar == [2, 2, 1]


def test_m6_bos_teknik_teknik_sayilmaz(con, tmp_path):
    a = urun_ekle(con, sku="T1", ad="BOS TEKNIK")
    b = urun_ekle(con, sku="T2", ad="DOLU TEKNIK")
    c = urun_ekle(con, sku="T0", ad="TEKNIKSIZ")
    with con:
        con.execute("INSERT INTO urun_teknik VALUES (?, ?)", (a, '{"ozellikler":[],"bolumler":[]}'))
        con.execute("INSERT INTO urun_teknik VALUES (?, ?)", (b, '{"ozellikler":[["a","b"]],"bolumler":[]}'))
    cikis = tmp_path / "c"
    aciklama_disa.calistir(["--db", _db_yolu(con), "--cikis", str(cikis), "--sinir", "2"], io.StringIO())
    satirlar = [json.loads(s) for s in (cikis / "parti-0001.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [s["urun_id"] for s in satirlar] == [b, a]
    assert c


# ---------- düzeltme turu 2 ----------
@pytest.mark.parametrize("ek", [
    "Yük 165kg taşır.", "Yük 1,65kg taşır.", "Yük 1,6kg taşır.", "Besleme 2,4V olarak verilir.",
    "Yük 16 ton taşır.", "Süre 16 saat.", "Süre 16 yıl.", "Kesit 16 mm2.", "Yük .5 kg.", "Yük 1/2 kg taşır.",
    "Yük 5  kg taşır.", "Yük 5\nkg taşır.", "Yük 165 kg.", "Yük 1,65 kg.", "Besleme 2,4 V.", "Yük 16-kg sınıfı.",
])
def test_n1_n2_n3_birim_ve_ondalik_kacaklari(ek):
    assert "uydurma_sayi" in _k(GOVDE + " " + ek, teknik=[["Yük", "16,5 kg"], ["Besleme", "24 V DC"], ["Ağırlık", "12 kg"]])


@pytest.mark.parametrize("ek", [
    "Yük 16,5kg taşır.", "Yük 16.50 kg taşır.", "Yük 16.5kg.", "Besleme 24V olarak verilir.", "KR 16 serisi.", "KR 16 ile uyumlu.",
    "Kimlik 00-123-456 ve 00123456 olarak yazılır.", "Ağırlık 12 kg.",
])
def test_n1_dogru_yazimlar_gecer(ek):
    assert "uydurma_sayi" not in _k(GOVDE + " " + ek, teknik=[["Yük", "16,5 kg"], ["Besleme", "24 V DC"],
                                                              ["Ağırlık", "12 kg"]])


@pytest.mark.parametrize("ek", ["12 ayrı kanal.", "14 günde teslim.", "14 days shipping.", "12 aydır."])
def test_n4_izinli_baglam_dar(ek):
    assert "uydurma_sayi" in _k(GOVDE + " " + ek)


def test_n4_dogru_kaliplar_hala_gecer():
    for ek in ("12 ay garanti.", "12 aylık garanti.", "12-month warranty.", "14 günlük iade.", "14-day return.",
               "14 gün içinde iade.", "2. el ürün."):
        assert "uydurma_sayi" not in _k(GOVDE + " " + ek), ek


@pytest.mark.parametrize("ek", ["İki yıl garanti sunulur.", "Beş kilogram taşır.", "Twenty kg load.", "Three years."])
def test_n5_yazi_ile_sayi(ek):
    assert "uydurma_sayi" in _k(GOVDE + " " + ek)


def test_n5_not_only_olumsuzlama_degil():
    assert "durum_celiski" in _k(GOVDE + " It is not only refurbished but great.")


def test_n6_garantili_durumlar_seo_ile_ayni():
    from app.katalog import aciklama_dogrula
    from app.web import seo
    assert aciklama_dogrula.GARANTILI_DURUMLAR == seo.GARANTILI_DURUMLAR


def test_n8_eposta_regex_dogrusal():
    assert _k("@" * 1500)  # hızlı döner, reddedilir


# ---------- N-7: sağlam atomiklik / sıralama testleri ----------
def _yukle_girdi(tmp_path, uid):
    girdi = tmp_path / "g2"
    _satir_yaz(girdi, "cikti-0001.jsonl", [json.dumps({"urun_id": uid, "dil": "tr", "metin": TR}, ensure_ascii=False),
                                          json.dumps({"urun_id": uid, "dil": "en", "metin": EN}, ensure_ascii=False)])
    return girdi


def test_n7_ikinci_satirda_hata_birinciyi_geri_alir(con, tmp_path):
    uid = _yukle_urunu(con)
    with con:
        con.execute("CREATE TRIGGER t_en BEFORE INSERT ON urun_aciklama WHEN NEW.dil = 'en'"
                    " BEGIN SELECT RAISE(ABORT, 'x'); END")
    girdi = _yukle_girdi(tmp_path, uid)
    with pytest.raises(sqlite3.IntegrityError):
        aciklama_yukle.calistir(["--db", _db_yolu(con), "--girdi", str(girdi), "--model", "m"], io.StringIO())
    assert [tuple(r) for r in con.execute("SELECT urun_id, dil FROM urun_aciklama")] == []


def test_n7_yazma_tum_dogrulamalardan_sonra(con, tmp_path, monkeypatch):
    uid = _yukle_urunu(con)
    girdi = _yukle_girdi(tmp_path, uid)
    olaylar: list[str] = []

    class Izle(sqlite3.Connection):
        def execute(self, sql, *a):
            if sql.lstrip().startswith("INSERT INTO urun_aciklama"):
                olaylar.append("yaz")
            return super().execute(sql, *a)

    def baglan_izle(yol):
        c = sqlite3.connect(str(yol), factory=Izle)
        c.row_factory = sqlite3.Row
        return c

    orijinal = aciklama_yukle.dogrula
    monkeypatch.setattr(aciklama_yukle, "baglan", baglan_izle)
    monkeypatch.setattr(aciklama_yukle, "dogrula", lambda *a, **k: olaylar.append("dogrula") or orijinal(*a, **k))
    aciklama_yukle.calistir(["--db", _db_yolu(con), "--girdi", str(girdi), "--model", "m"], io.StringIO())
    assert olaylar == ["dogrula", "dogrula", "yaz", "yaz"]
