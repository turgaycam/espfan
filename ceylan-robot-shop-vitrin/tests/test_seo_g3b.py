"""G3b C/D: ürün ve kategori title/meta (seo/oneriler.md uyumu) ve JSON-LD itemCondition / additionalProperty."""
import json
import re
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.katalog.depo import UrunTeknik
from app.web import seo
from tests.conftest import istemci_db, kategori_ekle, urun_ekle

KOK = "https://shop.example.com"
RAKIP_VE_YASAK = ("pazar otomasyon", "pazarotomasyon", "rotosis", "mers robot", "bktronic", "generis", "lektronix",
                  "yetkili satıcı", "yetkili bayi", "authorized", "official distributor")


# ---------- ürün başlığı ----------

def test_urun_basligi_kalibi_tr_en():
    assert seo.urun_basligi("tr", "Röle", "RL-24", "ABB", "yeni") == "Röle | RL-24 | ABB Sıfır | Ceylan Robot"
    assert seo.urun_basligi("en", "Relay", "RL-24", "ABB", "ikinci_el_test_edildi") == \
        "Relay | RL-24 | ABB Used, Tested | Ceylan Robot"
    assert seo.urun_basligi("tr", "Röle", "RL-24", None, "yenilenmis") == "Röle | RL-24 | Yenilenmiş | Ceylan Robot"
    assert seo.urun_basligi("tr", "Röle", "RL-24", None, "belirtilmemis") == "Röle | RL-24 | Ceylan Robot"


def test_urun_basligi_marka_adda_varsa_tekrarlanmaz_uretici_kodu_eklenir():
    assert seo.urun_basligi("tr", "SIEMENS RÖLE", "8102", "Siemens", "ikinci_el_oldugu_gibi", "3UG4512") == \
        "SIEMENS RÖLE 3UG4512 | 8102 | 2. El | Ceylan Robot"
    # üretici kodu adda zaten geçiyorsa (ayraçsız karşılaştırma) eklenmez
    assert seo.urun_basligi("tr", "SIEMENS 3UG4512-1BR20 RÖLE", "8102", "Siemens", "yeni", "3UG45121BR20") == \
        "SIEMENS 3UG4512-1BR20 RÖLE | 8102 | Sıfır | Ceylan Robot"


def test_urun_basligi_kesme_sirasi_once_marka_durum_parca_no_asla():
    # tam başlık sığmaz: önce marka, sonra uzun durum adı düşer
    b = seo.urun_basligi("tr", "KUKA KRC5 KR 140 R3", "8301033800019", "ABB", "ikinci_el_test_edildi")
    assert b == "KUKA KRC5 KR 140 R3 | 8301033800019 | 2. El | Ceylan Robot"
    # kısa durum da sığmazsa durum atılır, ad tam kalır
    b = seo.urun_basligi("tr", "KUKA KRC5 KR 140 R3200", "8301033800019", "ABB", "ikinci_el_test_edildi")
    assert b == "KUKA KRC5 KR 140 R3200 | 8301033800019 | Ceylan Robot"
    ad = "SIEMENS SIRIUS 24V SICAKLIK İZLEME RÖLESİ"
    b = seo.urun_basligi("tr", ad, "8102030100016", "Siemens", "ikinci_el_test_edildi", "3RS1040-1GD50")
    assert len(b) <= seo.BASLIK_SINIRI and "8102030100016" in b and "3RS1040-1GD50" in b and "…" in b
    # parça no çok uzun: hedef aşılır ama parça no tam kalır
    uzun = "ABCDEFGHIJKLMNOPQRSTUVWXYZ-1234567890-ABCDEFGHIJ"
    b = seo.urun_basligi("tr", "ÇOK UZUN ÜRÜN ADI BURADA", uzun, "SIEMENS", "yeni")
    assert uzun in b and b.startswith("ÇOK UZUN")


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_urun_basligi_100_rastgele_sinirda(dil):
    import random
    rnd = random.Random(7)
    for i in range(100):
        ad = " ".join(rnd.choice(["SIEMENS", "SERVO", "SÜRÜCÜ", "MODÜLÜ", "KUKA", "KABLO", "24V", "RÖLE"])
                      for _ in range(rnd.randint(2, 9)))
        sku = f"{rnd.randint(10**12, 10**13 - 1)}"
        b = seo.urun_basligi(dil, ad, sku, rnd.choice([None, "Siemens", "ABB"]),
                             rnd.choice(["yeni", "belirtilmemis", "ikinci_el_test_edildi", "yenilenmis"]),
                             rnd.choice([None, "6ES7 307-1EA00"]))
        assert len(b) <= seo.BASLIK_SINIRI and sku in b, b


# ---------- ürün meta ----------

def test_urun_meta_aciklamasi_120_155_ve_icerik():
    m = seo.urun_meta(dil="tr", ad="SIEMENS SIRIUS İZLEME RÖLESİ", parca_no="8102030100019", uretici_kodu="3UG4512-1BR20",
                      kategori="ROLELER/ZAMANLAYICILAR", durum_kodu="ikinci_el", stokta=True, teklif=False)
    assert 120 <= len(m) <= 155, (len(m), m)
    assert m.startswith("SIEMENS SIRIUS İZLEME RÖLESİ 3UG4512-1BR20, parça no 8102030100019: 2. el.")
    assert "Stokta." in m
    en = seo.urun_meta(dil="en", ad="SIEMENS SIRIUS RELAY", parca_no="8102030100019", uretici_kodu=None,
                       kategori="RELAYS", durum_kodu="belirtilmemis", stokta=False, teklif=True)
    assert 120 <= len(en) <= 155 and en.startswith("SIEMENS SIRIUS RELAY, part no. 8102030100019: condition not specified")  # G3e madde 6
    assert "Price and lead time on quotation." in en


def test_urun_meta_uzun_parca_no_kesilmez():
    """M-4: zorunlu kısım sınırı aşsa da parça no ve üretici kodu bölünmez; yalnız ad kısalır."""
    sku, kod = "P" * 70, "K-" + "9" * 60
    m = seo.urun_meta(dil="tr", ad="SERVO SÜRÜCÜ " * 10, parca_no=sku, uretici_kodu=kod, kategori="X",
                      durum_kodu="ikinci_el", stokta=True, teklif=False)
    assert sku in m and kod in m


def test_urun_meta_uzun_adda_sinirda_parca_no_korunur():
    m = seo.urun_meta(dil="tr", ad="ÇOK UZUN " * 30, parca_no="8102030100019", uretici_kodu="X-1",
                      kategori=None, durum_kodu="yeni", stokta=True, teklif=False)
    assert len(m) <= 155 and "8102030100019" in m and "X-1" in m


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_sablonlarda_rakip_ve_yetkili_ifadesi_yok(dil):
    metin = json.dumps(seo.SABLONLAR[dil], ensure_ascii=False).lower()
    metin += seo.urun_meta(dil=dil, ad="X", parca_no="1", uretici_kodu=None, kategori="K", durum_kodu="yeni",
                           stokta=True, teklif=False).lower()
    metin += seo.kategori_aciklamasi(dil, "K", 5, markalar=("KUKA",), durumlar=("yeni",)).lower()
    for yasak in RAKIP_VE_YASAK:
        assert yasak not in metin, yasak


# ---------- kategori ----------

def test_kategori_basligi_kalibi_tr_en():
    assert seo.kategori_basligi("tr", "KR C4", 12, kok="Mekanik") == "KR C4: Mekanik Yedek Parçaları | Ceylan Robot"
    assert seo.kategori_basligi("en", "KR C4", 12, kok="Mekanik") == "KR C4 | Mekanik Spare Parts | Ceylan Robot"
    # kök sığmazsa atılır
    assert seo.kategori_basligi("tr", "KR C4", 12, kok="Robot Kontrol Üniteleri") == \
        "KR C4 Yedek Parçaları | Ceylan Robot"
    assert seo.kategori_basligi("tr", "Mekanik", 300) == "Mekanik: Yedek Parça ve Ürünler (300) | Ceylan Robot"
    # sığmazsa kök atılır, sonra kategori kısalır; hep ≤ 60
    b = seo.kategori_basligi("tr", "ROLELER/ZAMANLAYICILAR VE ZAMAN RÖLELERİ", 41, kok="Elektrik ve Elektronik")
    assert b == "ROLELER/ZAMANLAYICILAR VE ZAMAN RÖLELERİ | Ceylan Robot"
    assert seo.kategori_basligi("tr", "KR C4", 90, sayfa=3, kok="Robot Kontrol Üniteleri").endswith(
        " – Sayfa 3 | Ceylan Robot")
    assert len(seo.kategori_basligi("tr", "Ç" * 120, 5, sayfa=12, kok="K")) <= 60


def test_kategori_meta_marka_ve_durum_listesi():
    m = seo.kategori_aciklamasi("tr", "ROLELER/ZAMANLAYICILAR", 41, markalar=("Siemens", "Omron", "Phoenix Contact", "ABB"),
                                durumlar=("ikinci_el_test_edildi", "yenilenmis"))
    assert 120 <= len(m) <= 155, (len(m), m)
    assert m.startswith("ROLELER/ZAMANLAYICILAR grubunda 41 ürün; markalar: Siemens, Omron, Phoenix Contact; "
                        "durum: 2. el test edilmiş, yenilenmiş.")
    assert "ABB" not in m   # en çok 3 marka
    en = seo.kategori_aciklamasi("en", "RELAYS", 41, markalar=("Siemens",), durumlar=())
    assert en.startswith("41 products in RELAYS; brands: Siemens.") and len(en) <= 155
    iki = seo.kategori_aciklamasi("tr", "KUKA", 90, 2)
    assert iki.endswith("Sayfa 2") and len(iki) <= 155


# ---------- JSON-LD ----------

def _urun(**ek):
    taban = dict(id=7, sku="3HAC1234", ad="ABB IRB 6640 Robot Kolu", uretici_kodu="6640-180", stok=2,
                 tedarik_suresi_gun=None, net_fiyat_eur=Decimal("1250.5"), teklif_zorunlu=False,
                 durum_kodu="ikinci_el_test_edildi", durum_ornek=False)
    taban.update(ek)
    return SimpleNamespace(**taban)


def test_json_ld_item_condition_cikarilan_durumdan_ornekte_yok():
    ld = seo.urun_json_ld(site_kok=KOK, dil="tr", urun=_urun(durum_kodu="yenilenmis"), marka="ABB", aciklama="a",
                          gorsel="/g.png", kategori="K")
    assert ld["itemCondition"] == "https://schema.org/RefurbishedCondition"
    ld = seo.urun_json_ld(site_kok=KOK, dil="tr", urun=_urun(), marka="ABB", aciklama="a", gorsel="/g.png", kategori="K")
    assert ld["itemCondition"] == "https://schema.org/UsedCondition"
    ld = seo.urun_json_ld(site_kok=KOK, dil="tr", urun=_urun(durum_kodu="ikinci_el"), marka="ABB", aciklama="a",
                          gorsel="/g.png", kategori="K")
    assert ld["itemCondition"] == "https://schema.org/UsedCondition"
    assert seo.urun_basligi("tr", "Röle", "RL-24", None, "ikinci_el") == "Röle | RL-24 | 2. El | Ceylan Robot"
    assert seo.urun_basligi("en", "Relay", "RL-24", None, "ikinci_el") == "Relay | RL-24 | Used | Ceylan Robot"
    ld = seo.urun_json_ld(site_kok=KOK, dil="tr", urun=_urun(durum_ornek=True), marka="ABB", aciklama="a",
                          gorsel="/g.png", kategori="K")
    assert "itemCondition" not in ld   # örnek (gösterim amaçlı) durum yapısal veriye girmez


def test_json_ld_additional_property_en_cok_20():
    teknik = UrunTeknik(ozellikler=tuple((f"Özellik {i}", f"{i} V") for i in range(25)), bolumler=(("", "metin"),))
    ld = seo.urun_json_ld(site_kok=KOK, dil="tr", urun=_urun(), marka=None, aciklama="a", gorsel="/g.png",
                          kategori=None, teknik=teknik)
    ozellik = ld["additionalProperty"]
    assert len(ozellik) == 20
    assert ozellik[0] == {"@type": "PropertyValue", "name": "Özellik 0", "value": "0 V"}
    ld = seo.urun_json_ld(site_kok=KOK, dil="tr", urun=_urun(), marka=None, aciklama="a", gorsel="/g.png", kategori=None)
    assert "additionalProperty" not in ld


# ---------- sayfa ----------

def _baslik(html):
    from html import unescape
    return unescape(re.search(r"<title>(.*?)</title>", html, re.S).group(1))


def _meta(html):
    from html import unescape
    return unescape(re.search(r'<meta name="description" content="([^"]*)"', html).group(1))


def _ld(html):
    for blok in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        veri = json.loads(blok)
        if veri.get("@type") == "Product":
            return veri
    raise AssertionError("Product JSON-LD yok")


def test_urun_sayfasi_title_meta_json_ld(istemci):
    with istemci_db(istemci) as con:
        k = kategori_ekle(con, kaynak_id="k1", ad="ROLELER/ZAMANLAYICILAR", yol="1", seviye=0)
        uid = urun_ekle(con, sku="8102030100019", ad="SIEMENS SIRIUS İZLEME RÖLESİ", kok="Elektrik", kategori_id=k,
                        uretici_kodu="3UG4512-1BR20", stok=3)
        con.execute("UPDATE urun SET durum_kodu = 'ikinci_el' WHERE id = ?", (uid,))
        con.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)",
                    (uid, '{"ozellikler":[["Besleme","24 V DC"]],"bolumler":[]}'))
    html = istemci.get(f"/tr/urun/{uid}").text
    b = _baslik(html)
    assert len(b) <= 60 and "8102030100019" in b and b.endswith("| Ceylan Robot")
    m = _meta(html)
    assert 120 <= len(m) <= 155 and "8102030100019" in m and "2. el" in m
    ld = _ld(html)
    assert ld["itemCondition"] == "https://schema.org/UsedCondition"
    assert ld["additionalProperty"] == [{"@type": "PropertyValue", "name": "Besleme", "value": "24 V DC"}]
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET durum_ornek = 1 WHERE id = ?", (uid,))
    html = istemci.get(f"/tr/urun/{uid}").text
    assert "itemCondition" not in _ld(html) and "2. El" not in _baslik(html)


def test_kategori_sayfasi_title_meta(istemci):
    with istemci_db(istemci) as con:
        kok = kategori_ekle(con, kaynak_id="k1", ad="Elektrik ve Elektronik", yol="1", seviye=0)
        alt = kategori_ekle(con, kaynak_id="k2", ad="RÖLELER", yol="1.2", seviye=1, ust_kaynak_id="k1")
        for i, ad in enumerate(["SIEMENS RÖLE", "SIEMENS RÖLE 2", "OMRON RÖLE"]):
            urun_ekle(con, sku=f"R{i}", ad=ad, kok="Elektrik ve Elektronik", kategori_id=alt)
    html = istemci.get(f"/tr/kategori/{alt}").text
    assert _baslik(html) == "RÖLELER Yedek Parçaları | Ceylan Robot"
    m = _meta(html)
    assert m.startswith("RÖLELER grubunda 3 ürün; markalar: Siemens, Omron.") and len(m) <= 155
    assert _baslik(istemci.get(f"/tr/kategori/{kok}").text) == "Elektrik ve Elektronik Yedek Parça ve Ürünler | Ceylan Robot"
