"""app/web/seo.py: saf SEO fonksiyonları (başlık/meta, canonical, hreflang, JSON-LD, robots, sitemap)."""
import json
import xml.etree.ElementTree as ET
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.web import seo

KOK = "https://shop.example.com"


def _urun(**ek):
    taban = dict(id=7, sku="3HAC1234", ad="ABB IRB 6640 Robot Kolu", uretici_kodu="6640-180", stok=2,
                 tedarik_suresi_gun=None, net_fiyat_eur=Decimal("1250.5"), teklif_zorunlu=False,
                 durum_kodu="ikinci_el_test_edildi")
    taban.update(ek)
    return SimpleNamespace(**taban)


# ---------- başlık / açıklama ----------

def test_urun_basligi_brief_kalibi():
    # G3b: kalıp seo/oneriler.md ile uyumlu (" | Ceylan Robot" soneki, durum adları "Sıfır" / "2. El, Test Edilmiş")
    assert seo.urun_basligi("tr", "Röle", "RL-24", "ABB", "yeni") == "Röle | RL-24 | ABB Sıfır | Ceylan Robot"
    assert seo.urun_basligi("en", "Relay", "RL-24", "ABB", "ikinci_el_test_edildi") == \
        "Relay | RL-24 | ABB Used, Tested | Ceylan Robot"


def test_urun_basligi_marka_ve_durum_yoksa_yalin():
    assert seo.urun_basligi("tr", "Röle", "RL-24", None, "belirtilmemis") == "Röle | RL-24 | Ceylan Robot"
    assert seo.urun_basligi("tr", "Röle", "RL-24", "ABB", "belirtilmemis") == "Röle | RL-24 | ABB | Ceylan Robot"


def test_urun_basligi_uzunsa_ad_kisalir_parca_no_korunur():
    ad = "SERVO SÜRÜCÜ MODÜLÜ ÇOK UZUN BİR ÜRÜN ADI " * 4
    baslik = seo.urun_basligi("tr", ad, "A06B-6077-H106", "FANUC", "ikinci_el_test_edildi")
    assert len(baslik) <= seo.BASLIK_SINIRI
    assert "A06B-6077-H106" in baslik and baslik.endswith("| Ceylan Robot") and "…" in baslik


def test_urun_basligi_sigmayinca_once_durum_sonra_marka_duser():
    # G3b: marka adda varsa yazılmaz; uzun durum adı sığmazsa kısa biçimi kalır
    assert seo.urun_basligi("tr", "KUKA KRC5 KR 140", "8301033800019", "KUKA", "ikinci_el_test_edildi") == \
        "KUKA KRC5 KR 140 | 8301033800019 | 2. El | Ceylan Robot"
    # marka da sığmazsa yalın kalıp
    baslik = seo.urun_basligi("tr", "ÇOK UZUN ÜRÜN ADI BURADA", "ABCDEFGHIJKLMNOPQRSTUVWXYZ-12345", "SIEMENS", "yeni")
    assert baslik.startswith("ÇOK UZUN") and "ABCDEFGHIJKLMNOPQRSTUVWXYZ-12345" in baslik and "SIEMENS" not in baslik


def test_kategori_basligi_kalibi_ve_siniri():
    assert seo.kategori_basligi("tr", "KUKA", 12) == "KUKA: Yedek Parça ve Ürünler (12) | Ceylan Robot"
    uzun = seo.kategori_basligi("tr", "ELEKTRİK VE ELEKTRONİK KONTROL SİSTEMLERİ", 1234)
    assert len(uzun) <= seo.BASLIK_SINIRI and uzun.startswith("ELEKTRİK VE ELEKTRONİK KONTROL SİSTEMLERİ")
    assert "Sayfa 3" in seo.kategori_basligi("tr", "KUKA", 90, sayfa=3)


def test_aciklama_sinirlari_ve_kisaltma():
    assert len(seo.meta_aciklama("kelime " * 100)) <= seo.ACIKLAMA_SINIRI
    assert seo.meta_aciklama("  a   b ") == "a b"
    aciklama = seo.urun_aciklama_sablonu("tr", "Röle", "RL-24", "K-1", "KONTROL")
    assert "RL-24" in aciklama and "K-1" in aciklama and "KONTROL" in aciklama
    assert len(seo.kategori_aciklamasi("tr", "KUKA", 5)) <= seo.ACIKLAMA_SINIRI


def test_kategori_girisi_kok_ve_adet_iceriyor():
    giris = seo.kategori_girisi("tr", "KR C4", "Endüstriyel Robotlar", 12)
    assert "KR C4" in giris and "Endüstriyel Robotlar" in giris and "12" in giris
    assert "test edil" in giris and "ihracat" in giris and "teklif" in giris
    assert "KUKA (KUKA)" not in seo.kategori_girisi("tr", "KUKA", "KUKA", 3)  # kök kendisiyse tekrarlanmaz
    en = seo.kategori_girisi("en", "KR C4", "Robots", 12)
    assert "tested" in en and "export" in en and "quote" in en


def test_sablonlarda_yasak_ifade_yok():
    metin = json.dumps(seo.SABLONLAR, ensure_ascii=False).lower()
    assert "yetkili satıcı" not in metin and "authorized" not in metin


# ---------- canonical / hreflang ----------

def test_canonical_filtre_parametrelerini_atar_sayfa_korur():
    assert seo.canonical_url(KOK, "/tr/kategori/5") == f"{KOK}/tr/kategori/5"
    assert seo.canonical_url(KOK, "/tr/kategori/5", 1) == f"{KOK}/tr/kategori/5"
    assert seo.canonical_url(KOK, "/tr/kategori/5", 3) == f"{KOK}/tr/kategori/5?sayfa=3"


def test_alternatifler_tr_en_xdefault():
    assert seo.alternatifler(KOK, "/tr/urun/7") == [
        ("tr", f"{KOK}/tr/urun/7"), ("en", f"{KOK}/en/urun/7"), ("x-default", f"{KOK}/tr/urun/7")]
    assert seo.alternatifler(KOK, "/en/kategori/2", 2)[0] == ("tr", f"{KOK}/tr/kategori/2?sayfa=2")
    assert seo.alternatifler(KOK, "/yonetim") == []


def test_sayfa_seo_islemselde_canonical_yok_demoda_robots_var():
    s = seo.sayfa_seo(yayin_modu="uretim", site_kok=KOK, dil="tr", yol="/tr/sepet", baslik=None, aciklama="a")
    assert s["robots"] == "noindex,nofollow" and s["canonical"] is None and s["og"] is None
    s = seo.sayfa_seo(yayin_modu="uretim", site_kok=KOK, dil="tr", yol="/tr/urun/1", baslik="B", aciklama="a")
    assert s["robots"] is None and s["canonical"] == f"{KOK}/tr/urun/1" and s["og"]["gorsel"].startswith(KOK)
    s = seo.sayfa_seo(yayin_modu="demo", site_kok=KOK, dil="tr", yol="/tr/urun/1", baslik="B", aciklama="a")
    assert s["robots"] == "noindex,nofollow" and s["canonical"]  # demoda da doğrulanabilsin


def test_og_gorseli_svg_yer_tutucu_yerine_logo():
    assert seo.og_gorseli(KOK, "/statik/yer-tutucu/robot.svg") == KOK + seo.LOGO_YOLU
    assert seo.og_gorseli(KOK, "/gorsel/b/" + "a" * 32 + ".webp") == KOK + "/gorsel/b/" + "a" * 32 + ".webp"
    assert seo.og_gorseli(KOK, "https://www.ceylanrobot.com/x.jpg") == "https://www.ceylanrobot.com/x.jpg"


@pytest.mark.parametrize("yol", ["/tr/sepet", "/en/odeme/ABC/kart", "/tr/hesabim", "/tr/giris", "/en/kayit",
                                 "/tr/ara", "/yonetim", "/yonetim/giris", "/tr/siparis/X1", "/tr/teklif/tamam"])
def test_islemsel_yollar(yol):
    assert seo.islemsel_mi(yol)
    assert seo.robots_basligi("uretim", yol) == "noindex, nofollow"
    assert seo.robots_meta("uretim", yol) == "noindex,nofollow"


@pytest.mark.parametrize("yol", ["/tr/", "/tr/urun/5", "/en/kategori/2", "/tr/teklif", "/tr/yasal/iade", "/saglik"])
def test_islemsel_olmayan_yollar(yol):
    assert not seo.islemsel_mi(yol)
    assert seo.robots_basligi("uretim", yol) is None and seo.robots_meta("uretim", yol) is None
    assert seo.robots_basligi("demo", yol) == "noindex, nofollow"


# ---------- JSON-LD ----------

def test_json_ld_metni_script_kapatmaz_ve_geri_okunur():
    veri = {"name": "</script><script>alert(1)</script> & <!--   'x'"}
    metin = seo.json_ld_metni(veri)
    assert "</" not in metin and "<script" not in metin.lower() and "<!--" not in metin
    assert " " not in metin
    assert json.loads(metin) == veri


def _g(tutar="1250.50", para="TRY", kdv=True):
    return SimpleNamespace(ana_tutar=Decimal(tutar), ana_para=para, kdv_dahil=kdv)


def test_urun_json_ld_zorunlu_alanlar():
    ld = seo.urun_json_ld(site_kok=KOK, dil="tr", urun=_urun(), marka="ABB", aciklama="Açıklama",
                          gorsel="/gorsel/b/x.webp", kategori="Robotlar", gosterim=_g())
    assert ld["@type"] == "Product" and ld["name"] == "ABB IRB 6640 Robot Kolu"
    assert ld["sku"] == "3HAC1234" and ld["mpn"] == "6640-180"
    assert ld["brand"] == {"@type": "Brand", "name": "ABB"}
    assert ld["image"] == [KOK + "/gorsel/b/x.webp"] and ld["description"] == "Açıklama"
    assert ld["category"] == "Robotlar"
    assert ld["itemCondition"] == "https://schema.org/UsedCondition"   # G3b: test edilmiş 2. el = Used
    teklif = ld["offers"]
    # fiyat ve para birimi sayfanın birincil gösterimiyle aynı (KDV dahil TRY)
    assert teklif["@type"] == "Offer" and teklif["price"] == "1250.50" and teklif["priceCurrency"] == "TRY"
    assert teklif["priceSpecification"] == {"@type": "UnitPriceSpecification", "price": "1250.50",
                                            "priceCurrency": "TRY", "valueAddedTaxIncluded": True}
    assert teklif["availability"] == "https://schema.org/InStock"
    assert teklif["url"] == f"{KOK}/tr/urun/7" and teklif["seller"]["@type"] == "Organization"
    kargo = teklif["shippingDetails"]
    assert kargo["shippingDestination"]["addressCountry"] == "TR" and kargo["shippingRate"]["value"] == "15.00"
    iade = teklif["hasMerchantReturnPolicy"]
    assert iade["merchantReturnDays"] == 14 and iade["merchantReturnLink"] == f"{KOK}/tr/yasal/iade"
    assert "returnFees" not in iade and "FreeReturn" not in json.dumps(ld)  # ücretsiz iade iddiası yok


def test_kdv_haric_eur_gosterim():
    ld = seo.urun_json_ld(site_kok=KOK, dil="tr", urun=_urun(), marka=None, aciklama="a", gorsel="/x.png",
                          kategori=None, gosterim=_g("100.00", "EUR", False))
    assert ld["offers"]["priceCurrency"] == "EUR" and ld["offers"]["priceSpecification"]["valueAddedTaxIncluded"] is False


def test_teklif_zorunlu_urunde_offers_hic_yok():
    ld = seo.urun_json_ld(site_kok=KOK, dil="tr", urun=_urun(teklif_zorunlu=True), marka=None, aciklama="a",
                          gorsel="/x.png", kategori=None, gosterim=_g())
    assert "offers" not in ld and ld["@type"] == "Product" and ld["sku"]
    assert "shippingDetails" not in json.dumps(ld) and "brand" not in ld and "category" not in ld


def test_kargo_degeri_sayfa_metniyle_ayni_kaynak():
    from pathlib import Path

    tr = (Path(__file__).parent.parent / "app" / "web" / "dil" / "tr.json").read_text(encoding="utf-8")
    assert "Türkiye içi kargo 15 € + KDV" in tr and seo.TR_KARGO_EUR == "15.00"
    iade_tr = (Path(__file__).parent.parent / "app/web/sablonlar/yasal/tr/iade.html").read_text(encoding="utf-8")
    iade_en = (Path(__file__).parent.parent / "app/web/sablonlar/yasal/en/iade.html").read_text(encoding="utf-8")
    assert "14 gün" in iade_tr and "14 days" in iade_en  # merchantReturnDays 14 sayfada yazan değer


@pytest.mark.parametrize(("stok", "gun", "beklenen"), [
    (3, None, "InStock"), (0, 12, "PreOrder"), (0, None, "OutOfStock")])
def test_stok_durumu(stok, gun, beklenen):
    assert seo.stok_durumu(stok, gun) == f"https://schema.org/{beklenen}"


@pytest.mark.parametrize(("kod", "sema"), [
    ("yeni", "NewCondition"), ("ikinci_el_test_edildi", "UsedCondition"), ("yenilenmis", "RefurbishedCondition"),
    ("ikinci_el_oldugu_gibi", "UsedCondition")])
def test_item_condition(kod, sema):
    ld = seo.urun_json_ld(site_kok=KOK, dil="tr", urun=_urun(durum_kodu=kod), marka=None, aciklama="a",
                          gorsel="/x.png", kategori=None, gosterim=_g())
    assert ld["itemCondition"] == f"https://schema.org/{sema}"


def test_item_condition_belirtilmemis_yok():
    ld = seo.urun_json_ld(site_kok=KOK, dil="tr", urun=_urun(durum_kodu="belirtilmemis"), marka=None,
                          aciklama="a", gorsel="/x.png", kategori=None, gosterim=_g())
    assert "itemCondition" not in ld and "itemCondition" not in ld["offers"]


def test_liste_ve_ana_sayfa_json_ld():
    liste = seo.liste_json_ld(site_kok=KOK, dil="tr", ana_sayfa_adi="Ana sayfa", yol=[(1, "Robotlar"), (5, "KUKA")],
                              urunler=[_urun(id=1), _urun(id=2)])
    kirinti, ogeler = liste
    assert kirinti["@type"] == "BreadcrumbList" and [o["position"] for o in kirinti["itemListElement"]] == [1, 2, 3]
    assert kirinti["itemListElement"][2]["item"] == f"{KOK}/tr/kategori/5"
    assert ogeler["@type"] == "ItemList" and ogeler["itemListElement"][1]["url"] == f"{KOK}/tr/urun/2"
    kurulus, site = seo.ana_sayfa_json_ld(site_kok=KOK, dil="tr", telefon="+90 (332) 239 15 75")
    assert kurulus["logo"] == KOK + "/statik/marka/ceylan-robot-logo.png"
    assert kurulus["contactPoint"]["telephone"] == "+90 (332) 239 15 75"
    assert site["potentialAction"]["target"]["urlTemplate"] == f"{KOK}/tr/ara?q={{search_term_string}}"
    assert "contactPoint" not in seo.ana_sayfa_json_ld(site_kok=KOK, dil="tr", telefon="")[0]


# ---------- robots.txt ----------

def test_robots_demo():
    metin = seo.robots_metni("demo", KOK, ("GPTBot",))
    satirlar = metin.splitlines()
    assert satirlar[:2] == ["User-agent: *", "Disallow: /"]
    assert "Disallow: /_iz/" in satirlar and "Sitemap" not in metin and "GPTBot" not in metin


def test_robots_uretim():
    metin = seo.robots_metni("uretim", KOK, ("GPTBot", "ClaudeBot"))
    for satir in ("Allow: /", "Disallow: /sepet", "Disallow: /*/sepet", "Disallow: /*/odeme", "Disallow: /*/hesabim",
                  "Disallow: /*/giris", "Disallow: /*/kayit", "Disallow: /yonetim", "Disallow: /*/ara?",
                  "Disallow: /*?*stokta=", "Disallow: /*?*fmin=", "Disallow: /*?*fmax=", "Disallow: /*?*sira=",
                  "Disallow: /_iz/", f"Sitemap: {KOK}/sitemap.xml"):
        assert satir in metin.splitlines(), satir
    assert "sayfa=" not in metin  # sayfalama açık
    assert metin.count("User-agent:") == 3
    bloklar = metin.split("\n\n")
    assert bloklar[0].splitlines()[1:] == bloklar[1].splitlines()[1:]  # AI blokları aynı kurallarla
    assert "Disallow: /\n" not in metin


# ---------- sitemap ----------

def test_sitemap_xml_gecerli_ve_hreflangli():
    xml = seo.sitemap_xml(KOK, [("/{dil}/urun/1", "2026-10-01"), ("/{dil}/urun/2", None)])
    kok = ET.fromstring(xml)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "x": "http://www.w3.org/1999/xhtml"}
    urller = kok.findall("s:url", ns)
    assert [u.find("s:loc", ns).text for u in urller] == [f"{KOK}/tr/urun/1", f"{KOK}/tr/urun/2"]
    assert urller[0].find("s:lastmod", ns).text == "2026-10-01" and urller[1].find("s:lastmod", ns) is None
    bag = {a.get("hreflang"): a.get("href") for a in urller[0].findall("x:link", ns)}
    assert bag == {"tr": f"{KOK}/tr/urun/1", "en": f"{KOK}/en/urun/1", "x-default": f"{KOK}/tr/urun/1"}


def test_sitemap_indeks_xml():
    kok = ET.fromstring(seo.sitemap_indeks_xml(KOK, [("/sitemap-urunler-1.xml", "2026-10-01"), ("/sitemap-sayfalar.xml", None)]))
    assert [e[0].text for e in kok] == [f"{KOK}/sitemap-urunler-1.xml", f"{KOK}/sitemap-sayfalar.xml"]


def test_json_ld_metni_markup_duz_str_kacisli_basilir():
    from markupsafe import Markup

    assert isinstance(seo.json_ld_metni({"a": 1}), Markup)
    # şablon |safe'siz: düz str (json.dumps çıktısı) otomatik kaçışlanır, ham basılmaz
    from jinja2 import Environment

    sablon = Environment(autoescape=True).from_string("{{ j }}")
    assert sablon.render(j='{"a":"</script>"}') != '{"a":"</script>"}'
    cikti = sablon.render(j=seo.json_ld_metni({"a": "</script>"}))
    assert "</script" not in cikti and json.loads(cikti) == {"a": "</script>"}


def test_kategori_aciklamasi_sayfa_eki():
    bir = seo.kategori_aciklamasi("tr", "KUKA", 90, 1)
    iki = seo.kategori_aciklamasi("tr", "KUKA", 90, 2)
    assert bir != iki and iki.endswith("Sayfa 2") and len(iki) <= seo.ACIKLAMA_SINIRI
