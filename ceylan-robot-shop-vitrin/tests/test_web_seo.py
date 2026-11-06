"""G2: robots.txt, yayın modu, sitemap, llms.txt (web katmanı)."""
import re
import xml.etree.ElementTree as ET

from app.web import seo
from tests import conftest as ortak
from tests.conftest import istemci_db, kategori_ekle, sayfa_denetle, urun_ekle

NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "x": "http://www.w3.org/1999/xhtml"}
URETIM_KOK = "https://shop.example.com"
DEMO_KOK = "http://192.168.5.30:3030"


def katalog_kur(istemci) -> dict:
    """3 kök kategori (biri boş), 3 aktif + 1 pasif ürün (biri teklif zorunlu/2. el). Kimlikleri döner."""
    with istemci_db(istemci) as con:
        rob = kategori_ekle(con, kaynak_id="k12", ad="Endüstriyel Robotlar", yol="12", seviye=0)
        kuka = kategori_ekle(con, kaynak_id="k1241", ad="KUKA", yol="12.41", seviye=1, ust_kaynak_id="k12")
        elk = kategori_ekle(con, kaynak_id="k10", ad="Elektrik ve Elektronik", yol="10", seviye=0)
        bos = kategori_ekle(con, kaynak_id="k99", ad="Boş Kategori", yol="99", seviye=0)
        r1 = urun_ekle(con, sku="RL-24", ad="RÖLE MODÜLÜ 24V", kok="Elektrik ve Elektronik", kategori_id=elk, stok=5)
        r2 = urun_ekle(con, sku="8301033800019", ad="KUKA KRC5 KR 140", kok="Endüstriyel Robotlar", kategori_id=kuka,
                       fiyat="32000.00", teklif=True, uretici_kodu="KRC5-140")
        r3 = urun_ekle(con, sku="SG-1", ad="SİGORTA KUTUSU", kok="Elektrik ve Elektronik", kategori_id=elk, stok=0)
        pasif = urun_ekle(con, sku="PS-9", ad="PASİF ÜRÜN", kok="Elektrik ve Elektronik", kategori_id=elk, aktif=False)
        con.execute("UPDATE urun SET kaynak_guncelleme = '2026-10-05T08:00:00+00:00',"
                    " durum_kodu = 'ikinci_el_test_edildi' WHERE id = ?", (r2,))
    return {"rob": rob, "kuka": kuka, "elk": elk, "bos": bos, "urunler": [r1, r2, r3], "pasif": pasif}


# ---------- robots.txt ----------

def test_robots_demo(istemci):
    yanit = istemci.get("/robots.txt")
    assert yanit.status_code == 200 and yanit.headers["content-type"].startswith("text/plain")
    satirlar = yanit.text.splitlines()
    assert satirlar[:2] == ["User-agent: *", "Disallow: /"]
    assert "Disallow: /_iz/" in satirlar
    assert "Sitemap" not in yanit.text


def test_robots_uretim(istemci_uretim):
    metin = istemci_uretim.get("/robots.txt").text
    satirlar = metin.splitlines()
    for beklenen in ("Allow: /", "Disallow: /*/sepet", "Disallow: /*/ara?", "Disallow: /_iz/", "Disallow: /yonetim",
                     f"Sitemap: {URETIM_KOK}/sitemap.xml"):
        assert beklenen in satirlar
    assert "Disallow: /" not in satirlar  # site bütünüyle kapalı değil
    for ad in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "CCBot"):
        assert f"User-agent: {ad}" in satirlar


# ---------- yayın modu: meta robots + X-Robots-Tag ----------

def test_demoda_tum_html_yanitlarinda_noindex(istemci):
    k = katalog_kur(istemci)
    for yol in ("/tr/", "/en/", f"/tr/urun/{k['urunler'][0]}", f"/tr/kategori/{k['elk']}", "/tr/sepet", "/tr/yasal/iade"):
        yanit = istemci.get(yol)
        assert yanit.status_code == 200, yol
        html = sayfa_denetle(yanit)
        assert '<meta name="robots" content="noindex,nofollow">' in html, yol


def test_uretimde_urun_sayfasi_indekslenebilir_sepet_degil(istemci_uretim):
    k = katalog_kur(istemci_uretim)
    urun = istemci_uretim.get(f"/tr/urun/{k['urunler'][0]}")
    html = sayfa_denetle(urun, robots=None)
    assert 'name="robots"' not in html and "x-robots-tag" not in urun.headers
    for yol in ("/tr/", f"/tr/kategori/{k['elk']}", "/tr/teklif", "/tr/yasal/iade"):
        yanit = istemci_uretim.get(yol)
        assert "x-robots-tag" not in yanit.headers and 'name="robots"' not in yanit.text, yol
    for yol in ("/tr/sepet", "/tr/giris", "/tr/kayit", "/tr/ara?q=role", "/yonetim/giris"):
        yanit = istemci_uretim.get(yol)
        assert yanit.headers["x-robots-tag"] == "noindex, nofollow", yol
        assert '<meta name="robots" content="noindex,nofollow">' in yanit.text, yol


def test_uretimde_hata_ve_dosya_yanitlari_baslik_kurali(istemci_uretim):
    assert "x-robots-tag" not in istemci_uretim.get("/tr/olmayan-sayfa").headers
    assert "x-robots-tag" not in istemci_uretim.get("/statik/site.css").headers
    assert "x-robots-tag" not in istemci_uretim.get("/robots.txt").headers


def test_json_ld_disinda_satir_ici_script_hala_hata():
    ld = '<script type="application/ld+json">{"a":1}</script>'
    assert not ortak._SATIR_ICI_SCRIPT.search(ld)
    assert not ortak._SATIR_ICI_SCRIPT.search("<script src='/x.js'></script>")
    assert ortak._SATIR_ICI_SCRIPT.search("<script>alert(1)</script>")
    assert ortak._SATIR_ICI_SCRIPT.search('<script type="text/javascript">x</script>')
    assert ortak._SATIR_ICI_SCRIPT.search('<script type="application/json">x</script>')


# ---------- sitemap ----------

def _loclar(kok) -> list[str]:
    return [u.find("s:loc", NS).text for u in kok.findall("s:url", NS)]


def test_sitemap_indeksi_ve_urun_dosyasi(istemci):
    k = katalog_kur(istemci)
    yanit = istemci.get("/sitemap.xml")
    assert yanit.status_code == 200 and yanit.headers["content-type"].startswith("application/xml")
    kok = ET.fromstring(yanit.text)
    assert kok.tag == f"{{{NS['s']}}}sitemapindex"
    assert [e.find("s:loc", NS).text for e in kok.findall("s:sitemap", NS)] == [
        f"{DEMO_KOK}/sitemap-urunler-1.xml", f"{DEMO_KOK}/sitemap-kategoriler.xml", f"{DEMO_KOK}/sitemap-sayfalar.xml"]

    urunler = ET.fromstring(istemci.get("/sitemap-urunler-1.xml").text)
    loclar = _loclar(urunler)
    assert sorted(loclar) == sorted(f"{DEMO_KOK}/tr/urun/{i}" for i in k["urunler"])  # aktif ürün sayısı kadar
    assert f"{DEMO_KOK}/tr/urun/{k['pasif']}" not in loclar  # pasif ürün yok
    for u in urunler.findall("s:url", NS):
        bag = {a.get("hreflang"): a.get("href") for a in u.findall("x:link", NS)}
        kimlik = u.find("s:loc", NS).text.rsplit("/", 1)[1]
        assert bag == {"tr": f"{DEMO_KOK}/tr/urun/{kimlik}", "en": f"{DEMO_KOK}/en/urun/{kimlik}",
                       "x-default": f"{DEMO_KOK}/tr/urun/{kimlik}"}
        assert u.find("s:lastmod", NS) is not None  # eşitleme kaydı yoksa olusturma tarihine düşer
    kuka = next(u for u in urunler.findall("s:url", NS) if u.find("s:loc", NS).text.endswith(f"/{k['urunler'][1]}"))
    assert kuka.find("s:lastmod", NS).text == "2026-10-05"  # urun.kaynak_guncelleme


def test_sitemap_urun_dosyalari_siniriyla_bolunur(istemci, monkeypatch):
    assert seo.SITEMAP_URL_SINIRI == 5000
    katalog_kur(istemci)
    monkeypatch.setattr(seo, "SITEMAP_URL_SINIRI", 2)
    indeks = ET.fromstring(istemci.get("/sitemap.xml").text)
    assert [e.find("s:loc", NS).text for e in indeks.findall("s:sitemap", NS)][:2] == [
        f"{DEMO_KOK}/sitemap-urunler-1.xml", f"{DEMO_KOK}/sitemap-urunler-2.xml"]
    bir = _loclar(ET.fromstring(istemci.get("/sitemap-urunler-1.xml").text))
    iki = _loclar(ET.fromstring(istemci.get("/sitemap-urunler-2.xml").text))
    assert (len(bir), len(iki)) == (2, 1) and not set(bir) & set(iki)
    assert istemci.get("/sitemap-urunler-3.xml").status_code == 404
    assert istemci.get("/sitemap-urunler-0.xml").status_code == 404


def test_sitemap_kategoriler_ve_sayfalar(istemci_uretim):
    k = katalog_kur(istemci_uretim)
    kat = _loclar(ET.fromstring(istemci_uretim.get("/sitemap-kategoriler.xml").text))
    assert sorted(kat) == sorted(f"{URETIM_KOK}/tr/kategori/{i}" for i in (k["rob"], k["kuka"], k["elk"]))
    assert f"{URETIM_KOK}/tr/kategori/{k['bos']}" not in kat  # ürünsüz kategori yok
    sayfalar = _loclar(ET.fromstring(istemci_uretim.get("/sitemap-sayfalar.xml").text))
    assert f"{URETIM_KOK}/tr/" in sayfalar and f"{URETIM_KOK}/tr/yasal/iade" in sayfalar
    assert all("/sepet" not in s and "/yonetim" not in s for s in sayfalar)


def test_sitemap_pasif_kategori_yok(istemci):
    k = katalog_kur(istemci)
    with istemci_db(istemci) as con:
        con.execute("UPDATE kategori SET aktif = 0 WHERE id = ?", (k["elk"],))
    kat = _loclar(ET.fromstring(istemci.get("/sitemap-kategoriler.xml").text))
    assert f"{DEMO_KOK}/tr/kategori/{k['elk']}" not in kat


def test_sitemap_bos_katalogda_gecerli(istemci):
    kok = ET.fromstring(istemci.get("/sitemap.xml").text)
    assert len(kok.findall("s:sitemap", NS)) == 2  # ürün dosyası yok, kategoriler + sayfalar
    assert istemci.get("/sitemap-urunler-1.xml").status_code == 404


# ---------- llms.txt ----------

def test_llms_txt_yapisi_demo(istemci):
    katalog_kur(istemci)
    yanit = istemci.get("/llms.txt")
    assert yanit.status_code == 200 and yanit.headers["content-type"] == "text/plain; charset=utf-8"
    satirlar = yanit.text.splitlines()
    assert satirlar[0] == "# Ceylan Robot"
    assert "Bu bir iç demodur; veriler temsilidir." in satirlar[:4]
    assert any(s.startswith("> ") for s in satirlar[:6])
    basliklar = [s for s in satirlar if s.startswith("## ")]
    assert basliklar[:5] == ["## Ürün grupları", "## Satın alma ve teklif", "## Teslimat ve ihracat", "## İletişim", "## Yasal"]
    assert "## Optional" in basliklar
    assert re.search(r"- \[Endüstriyel Robotlar\]\(http://192\.168\.5\.30:3030/tr/kategori/\d+\): 1 ürün", yanit.text)
    assert re.search(r"- \[Elektrik ve Elektronik\]\(.+/tr/kategori/\d+\): 2 ürün", yanit.text)
    assert "Boş Kategori" not in yanit.text
    assert "http://192.168.5.30:3030/tr/yasal/kvkk" in yanit.text


def test_llms_txt_uretimde_demo_notu_yok(istemci_uretim):
    katalog_kur(istemci_uretim)
    metin = istemci_uretim.get("/llms.txt").text
    assert "iç demodur" not in metin and f"{URETIM_KOK}/tr/teklif" in metin


def test_llms_full_urun_satiri_aktif_urun_kadar(istemci):
    k = katalog_kur(istemci)
    yanit = istemci.get("/llms-full.txt")
    assert yanit.headers["content-type"] == "text/plain; charset=utf-8"
    urun_satirlari = [s for s in yanit.text.splitlines() if s.startswith("- ")]
    assert len(urun_satirlari) == len(k["urunler"])
    assert "PASİF ÜRÜN" not in yanit.text and "PS-9" not in yanit.text
    kuka = next(s for s in urun_satirlari if "KUKA KRC5" in s)
    assert "parça no: 8301033800019" in kuka and "üretici kodu: KRC5-140" in kuka
    assert "durum: 2. El, Test Edilmiş" in kuka and f"[bağlantı]({DEMO_KOK}/tr/urun/{k['urunler'][1]})" in kuka
    assert "## Endüstriyel Robotlar" in yanit.text and "## Elektrik ve Elektronik" in yanit.text


# ---------- önbellek (düzeltme turu 1) ----------

def test_sitemap_ve_llms_full_onbellegi_esitlemeyle_gecersiz_olur(istemci):
    from datetime import UTC, datetime

    k = katalog_kur(istemci)
    ilk = istemci.get("/llms-full.txt").text
    with istemci_db(istemci) as con:  # eşitleme/aktif sayısı değişmeden içerik değişirse önbellek yanıtı korur
        con.execute("UPDATE urun SET ad = 'DEGISTI' WHERE id = ?", (k["urunler"][0],))
    assert istemci.get("/llms-full.txt").text == ilk
    with istemci_db(istemci) as con:  # başarılı eşitleme kaydı gelince anahtar değişir
        con.execute("INSERT INTO esitleme_gunlugu (basla, bitis, durum) VALUES (?, ?, 'tam')",
                    (datetime(2026, 10, 14, tzinfo=UTC).isoformat(), datetime(2026, 10, 14, 0, 1, tzinfo=UTC).isoformat()))
    assert "DEGISTI" in istemci.get("/llms-full.txt").text
    bir = istemci.get("/sitemap-urunler-1.xml").text
    assert istemci.get("/sitemap-urunler-1.xml").text == bir
    assert "2026-10-14" in bir  # lastmod yeni eşitleme gününe göre yenilendi (ürünün kaynak tarihi olmayanlar)


def test_g3a_seo_onbellegi_uygulama_olusturulurken_hazir(istemci):
    """Y3: önbellek sözlüğü istek sırasında değil, uygulama kurulurken app.state'e konur."""
    assert istemci.app.state.seo_onbellek == {}
    istemci.get("/llms-full.txt")
    assert istemci.app.state.seo_onbellek


def test_g3a_robots_faset_parametreleri_kapali(istemci_uretim):
    satirlar = istemci_uretim.get("/robots.txt").text.splitlines()
    for ad in ("marka", "durum", "kat", "tedarikli", "fiyatli", "teklifle"):
        assert f"Disallow: /*?*{ad}=" in satirlar, ad
