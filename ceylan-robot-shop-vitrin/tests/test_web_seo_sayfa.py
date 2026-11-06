"""G2: sayfa başına SEO (başlık/meta, canonical, hreflang, OG, JSON-LD, ürün açıklaması, alt metni)."""
import json
import random
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from html import unescape

from app.fiyat.kur import Kur, kur_kaydet

from tests.conftest import istemci_db, sayfa_denetle, urun_ekle
from tests.test_web_seo import DEMO_KOK, katalog_kur

LD_DESENI = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def json_ld_oku(html: str) -> list[dict]:
    return [json.loads(m) for m in LD_DESENI.findall(html)]


def _meta(html: str, ad: str, oznitelik: str = "name") -> str | None:
    m = re.search(rf'<meta {oznitelik}="{re.escape(ad)}" content="([^"]*)">', html)
    return unescape(m.group(1)) if m else None


def _baslik(html: str) -> str:
    return unescape(re.search(r"<title>(.*?)</title>", html, re.S).group(1))


# ---------- meta / canonical / hreflang / OG ----------

def test_urun_sayfasi_meta_canonical_hreflang_og(istemci):
    k = katalog_kur(istemci)
    kuka_id = k["urunler"][1]
    html = istemci.get(f"/tr/urun/{kuka_id}?sira=ad&stokta=1&fmin=5").text
    assert '<html lang="tr">' in html
    # G3b: üretici kodu eklenir, adda geçen marka yazılmaz, durum sığmayınca düşer
    assert _baslik(html) == "KUKA KRC5 KR 140 KRC5-140 | 8301033800019 | Ceylan Robot"
    assert len(_baslik(html)) <= 60
    assert len(_meta(html, "description")) <= 155 and "8301033800019" in _meta(html, "description")
    assert f'<link rel="canonical" href="{DEMO_KOK}/tr/urun/{kuka_id}">' in html  # filtre parametreleri atılır
    for hl, dil in (("tr", "tr"), ("en", "en"), ("x-default", "tr")):
        assert f'<link rel="alternate" hreflang="{hl}" href="{DEMO_KOK}/{dil}/urun/{kuka_id}">' in html
    assert _meta(html, "og:type", "property") == "product"
    assert _meta(html, "og:title", "property") == _baslik(html)
    assert _meta(html, "og:image", "property").startswith(DEMO_KOK + "/")
    assert _meta(html, "og:url", "property") == f"{DEMO_KOK}/tr/urun/{kuka_id}"
    assert _meta(html, "twitter:card") == "summary_large_image"
    en = istemci.get(f"/en/urun/{kuka_id}").text
    assert '<html lang="en">' in en and _baslik(en).endswith("| Ceylan Robot")
    assert f'<link rel="canonical" href="{DEMO_KOK}/en/urun/{kuka_id}">' in en


def test_urun_basligi_marka_durum_kalibi(istemci):
    with istemci_db(istemci) as con:
        uid = urun_ekle(con, sku="3HAC1", ad="ABB IRB 120", kok="Robot")
        con.execute("UPDATE urun SET durum_kodu = 'yeni' WHERE id = ?", (uid,))
    assert _baslik(istemci.get(f"/tr/urun/{uid}").text) == "ABB IRB 120 | 3HAC1 | Sıfır | Ceylan Robot"


def test_50_rastgele_urunde_baslik_ve_aciklama_benzersiz(istemci):
    rnd = random.Random(42)
    kelimeler = ["SERVO", "SÜRÜCÜ", "KART", "KABLO", "MODÜL", "RÖLE", "ENCODER", "FREN", "MOTOR", "PANO"]
    markalar = ["ABB", "KUKA", "FANUC", "SIEMENS", "YASKAWA", "NACHI"]
    idler = []
    with istemci_db(istemci) as con:
        for i in range(80):
            ad = f"{rnd.choice(markalar)} {rnd.choice(kelimeler)} {rnd.choice(kelimeler)} {rnd.randint(1, 9)}"  # adlar tekrarlanabilir
            idler.append(urun_ekle(con, sku=f"P-{i:04d}-{rnd.randint(100, 999)}", ad=ad, kok="Elektrik"))
    basliklar, aciklamalar = [], []
    for kimlik in rnd.sample(idler, 50):
        html = istemci.get(f"/tr/urun/{kimlik}").text
        basliklar.append(_baslik(html))
        aciklamalar.append(_meta(html, "description"))
    assert len(set(basliklar)) == 50 and len(set(aciklamalar)) == 50
    assert all(len(b) <= 60 for b in basliklar) and all(0 < len(a) <= 155 for a in aciklamalar)


def test_kategori_sayfasi_canonical_filtre_atar_sayfa_korur(istemci):
    from tests.conftest import kategori_ekle

    with istemci_db(istemci) as con:
        elk = kategori_ekle(con, kaynak_id="k10", ad="Elektrik ve Elektronik", yol="10", seviye=0)
        for i in range(30):  # 24'lük sayfa boyu aşılsın
            urun_ekle(con, sku=f"E-{i}", ad=f"ELEKTRİK PARÇA {i}", kok="Elektrik", kategori_id=elk)
    yol = f"/tr/kategori/{elk}"
    html = istemci.get(f"{yol}?stokta=1&sira=fiyat_artan&fmin=1&fmax=9000").text
    assert f'<link rel="canonical" href="{DEMO_KOK}{yol}">' in html
    sayfa2 = istemci.get(f"{yol}?sayfa=2&stokta=1&sira=ad").text
    assert f'<link rel="canonical" href="{DEMO_KOK}{yol}?sayfa=2">' in sayfa2
    assert f'hreflang="en" href="{DEMO_KOK}/en/kategori/{elk}?sayfa=2"' in sayfa2
    assert _baslik(sayfa2) != _baslik(html) and "Sayfa 2" in _baslik(sayfa2)
    assert f'<link rel="canonical" href="{DEMO_KOK}{yol}">' in istemci.get(f"{yol}?sayfa=1").text
    assert _baslik(html).endswith("| Ceylan Robot") and len(_baslik(html)) <= 60
    assert len(_meta(html, "description")) <= 155


def test_kategori_girisi_ve_json_ld(istemci):
    k = katalog_kur(istemci)
    html = istemci.get(f"/tr/kategori/{k['kuka']}").text
    giris = re.search(r'<p class="kategori-giris">(.*?)</p>', html, re.S).group(1)
    assert "KUKA" in giris and "Endüstriyel Robotlar" in giris and "1 ürün" in giris
    assert "test edil" in giris and "ihracat" in giris and "teklif" in giris
    kirinti, liste = json_ld_oku(html)
    assert kirinti["@type"] == "BreadcrumbList"
    assert [o["name"] for o in kirinti["itemListElement"]] == ["Ana sayfa", "Endüstriyel Robotlar", "KUKA"]
    assert liste["@type"] == "ItemList" and liste["numberOfItems"] == 1
    assert liste["itemListElement"][0] == {"@type": "ListItem", "position": 1,
                                           "url": f"{DEMO_KOK}/tr/urun/{k['urunler'][1]}", "name": "KUKA KRC5 KR 140"}
    en = istemci.get(f"/en/kategori/{k['kuka']}").text
    assert "tested" in re.search(r'<p class="kategori-giris">(.*?)</p>', en, re.S).group(1)


def test_ana_sayfa_organization_website_searchaction(istemci):
    katalog_kur(istemci)
    html = istemci.get("/tr/").text
    kurulus, site = json_ld_oku(html)
    assert kurulus["@type"] == "Organization" and kurulus["logo"] == DEMO_KOK + "/statik/marka/ceylan-robot-logo.png"
    assert kurulus["url"].startswith(DEMO_KOK) and kurulus["contactPoint"]["telephone"] == "+90 (332) 239 15 75"
    assert site["@type"] == "WebSite"
    assert site["potentialAction"]["@type"] == "SearchAction"
    assert site["potentialAction"]["target"]["urlTemplate"] == f"{DEMO_KOK}/tr/ara?q={{search_term_string}}"
    assert _baslik(html).startswith("Ceylan Robot –")
    assert _meta(html, "og:type", "property") == "website"


def test_hata_ve_islemsel_sayfalarda_canonical_yok(istemci):
    for yol in ("/tr/olmayan", "/tr/urun/99999", "/tr/sepet", "/tr/giris", "/tr/ara?q=a"):
        html = istemci.get(yol).text
        assert 'rel="canonical"' not in html and 'rel="alternate"' not in html, yol
        assert _meta(html, "description"), yol


# ---------- JSON-LD ürün ----------

def test_urun_json_ld_zorunlu_alanlar_ve_teklif(istemci):
    k = katalog_kur(istemci)
    html = istemci.get(f"/tr/urun/{k['urunler'][0]}").text
    (ld,) = json_ld_oku(html)
    assert ld["@type"] == "Product" and ld["name"] == "RÖLE MODÜLÜ 24V" and ld["sku"] == "RL-24"
    assert ld["description"] and ld["image"][0].startswith(DEMO_KOK + "/")
    assert ld["offers"]["price"] == "100.00" and ld["offers"]["priceCurrency"] == "EUR"  # kur yok: EUR net
    assert ld["offers"]["availability"] == "https://schema.org/InStock"
    assert ld["offers"]["url"] == f"{DEMO_KOK}/tr/urun/{k['urunler'][0]}"
    assert ld["offers"]["seller"]["name"] == "Ceylan Robot"
    assert "shippingDetails" in ld["offers"] and ld["offers"]["hasMerchantReturnPolicy"]["merchantReturnDays"] == 14
    assert "brand" not in ld  # jenerik ad: yanlış marka yayımlanmaz
    sk = json_ld_oku(istemci.get(f"/tr/urun/{k['urunler'][2]}").text)[0]
    assert sk["offers"]["availability"] == "https://schema.org/OutOfStock"


def test_teklif_zorunlu_urunde_offers_yok_mpn_ve_durum_var(istemci):
    k = katalog_kur(istemci)
    (ld,) = json_ld_oku(istemci.get(f"/tr/urun/{k['urunler'][1]}").text)
    assert "offers" not in ld and ld["@type"] == "Product"
    assert ld["mpn"] == "KRC5-140" and ld["brand"]["name"] == "KUKA"
    assert ld["itemCondition"] == "https://schema.org/UsedCondition"
    assert ld["category"] == "KUKA"


def _sayfa_fiyati(html: str) -> tuple[Decimal, str]:
    m = re.search(r'data-e2e="fiyat-ana"[^>]*data-para="(\w+)"[^>]*><span class="tutar">([^<]+)</span>', html)
    assert m, "fiyat-ana yok"
    sayi = re.sub(r"[^\d,.]", "", m.group(2)).replace(".", "").replace(",", ".")
    return Decimal(sayi), m.group(1)


def test_json_ld_fiyati_sayfadaki_birincil_fiyatla_ayni(istemci):
    k = katalog_kur(istemci)
    uid = k["urunler"][0]
    # kur yok: sayfa EUR net gösterir
    html = istemci.get(f"/tr/urun/{uid}").text
    tutar, para = _sayfa_fiyati(html)
    offer = json_ld_oku(html)[0]["offers"]
    assert (Decimal(offer["price"]), offer["priceCurrency"]) == (tutar, para) == (Decimal("100.00"), "EUR")
    assert offer["priceSpecification"]["valueAddedTaxIncluded"] is False
    # kur var: anonim TR ziyaretçiye KDV dahil TRY
    with istemci_db(istemci) as con:
        kur_kaydet(con, Kur(tarih=date(2026, 10, 12), eur_alis=Decimal("35.00"), eur_satis=Decimal("35.20")),
                   datetime(2026, 10, 12, 6, 0, tzinfo=UTC))
    html = istemci.get(f"/tr/urun/{uid}").text
    tutar, para = _sayfa_fiyati(html)
    offer = json_ld_oku(html)[0]["offers"]
    assert para == "TRY" and (Decimal(offer["price"]), offer["priceCurrency"]) == (tutar, "TRY")
    assert tutar == Decimal("4224.00")  # 100 EUR x 35.20 x 1.20
    assert offer["priceSpecification"] == {"@type": "UnitPriceSpecification", "price": "4224.00",
                                           "priceCurrency": "TRY", "valueAddedTaxIncluded": True}
    assert 'data-kdv="dahil"' in html


def test_urun_adinda_script_kapatma_json_ld_ve_sayfayi_bozmaz(istemci):
    kotu = '</script><script>alert(1)</script> "tırnak" & <b>'
    with istemci_db(istemci) as con:
        uid = urun_ekle(con, sku="XSS-1", ad=kotu, kok="Elektrik")
    html = sayfa_denetle(istemci.get(f"/tr/urun/{uid}"))  # satır içi çalışan script yok (yalnız ld+json)
    assert "<script>alert(1)" not in html and "</script><script>" not in html
    (ld,) = json_ld_oku(html)
    assert ld["name"] == kotu
    assert len(LD_DESENI.findall(html)) == 1
    assert json_ld_oku(istemci.get(f"/en/urun/{uid}").text)[0]["name"] == kotu


def test_urun_gorseli_alt_ad_ve_parca_no_liste_alt_bos(istemci):
    k = katalog_kur(istemci)
    html = istemci.get(f"/tr/urun/{k['urunler'][0]}").text
    assert re.search(r'<img src="[^"]+" data-yedek="[^"]+" alt="RÖLE MODÜLÜ 24V – RL-24 \(temsili görsel\)"', html)
    liste = istemci.get(f"/tr/kategori/{k['elk']}").text
    assert 'alt=""' in liste and 'alt="RÖLE' not in liste


# ---------- ürün açıklaması ----------

def _aciklama_yaz(istemci, urun_id, dil, metin, kaynak, model=None):
    with istemci_db(istemci) as con:
        con.execute("INSERT INTO urun_aciklama (urun_id, dil, metin, kaynak, model, uretildi) VALUES (?, ?, ?, ?, ?, ?)",
                    (urun_id, dil, metin, kaynak, model, "2026-10-13T09:00:00+00:00"))


def test_aciklama_yoksa_bolum_yok_json_ld_sablon(istemci):
    k = katalog_kur(istemci)
    html = istemci.get(f"/tr/urun/{k['urunler'][0]}").text
    assert "Ürün açıklaması" not in html and "Taslak açıklama" not in html
    assert "RL-24" in json_ld_oku(html)[0]["description"]


def test_llm_taslak_aciklama_rozetle_gosterilir_ve_json_ld_ye_baglanir(istemci):
    k = katalog_kur(istemci)
    uid = k["urunler"][0]
    _aciklama_yaz(istemci, uid, "tr", "Bu röle modülü 24 V devrelerde kullanılır.", "llm-taslak", "claude-haiku")
    # G3i madde 14: taslak yalnız teknik verisi (ya da kaynak açıklaması) olan üründe gösterilir
    with istemci_db(istemci) as con:
        con.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)",
                    (uid, '{"ozellikler": [["Gerilim", "24 V"]], "bolumler": []}'))
    html = istemci.get(f"/tr/urun/{uid}").text
    assert "Ürün açıklaması" in html and "Bu röle modülü 24 V devrelerde kullanılır." in html
    # G3k madde 21: başlık "Kaynak verilerden otomatik özet (kontrol edilmemiş)" (önce "Taslak açıklama")
    assert 'data-e2e="aciklama-taslak"' in html and "Kaynak verilerden otomatik özet (kontrol edilmemiş)" in html
    assert json_ld_oku(html)[0]["description"] == "Bu röle modülü 24 V devrelerde kullanılır."
    assert _meta(html, "description") == "Bu röle modülü 24 V devrelerde kullanılır."
    en = istemci.get(f"/en/urun/{uid}").text  # EN satırı yok: TR metni EN sayfada gösterilmez
    assert "Product description" not in en and "Bu röle" not in en


def test_kaynak_aciklama_rozetsiz_ve_kacisli(istemci):
    k = katalog_kur(istemci)
    uid = k["urunler"][0]
    _aciklama_yaz(istemci, uid, "en", "Relay <b>module</b> for 24 V circuits.", "kaynak")
    html = istemci.get(f"/en/urun/{uid}").text
    assert "Product description" in html and "Draft description" not in html
    assert "&lt;b&gt;module&lt;/b&gt;" in html and "<b>module</b>" not in html
