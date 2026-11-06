import re
from decimal import Decimal

import pytest
from fastapi import Depends, Request
from fastapi.testclient import TestClient

from app.web import uygulama as uygulama_modulu
from app.web.baglam import para_bicimle, sablon, yer_tutucu
from app.web.dil import Ceviri
from app.web.guvenlik import GUVENLIK_BASLIKLARI, HizSiniri, guvenli_sonraki
from app.web.bagimlilik import db_bagimliligi
from tests.conftest import csrf_al, istemci_db, oturum_oku, oturum_yaz, sayfa_denetle, urun_ekle


@pytest.fixture
def prob(istemci):
    """Görev 11'de katalog sayfası henüz yok: taban.html'i tam yığından geçiren deneme rotası."""

    @istemci.app.get("/{dil:dil}/_prob")
    def _prob(request: Request, dil: str, con=Depends(db_bagimliligi)):
        return sablon(request, "hata.html", {"durum": 200, "baslik": "Prob", "aciklama": "prob", "hata_kimligi": None})

    return "/tr/_prob"


def _basliklari_denetle(yanit):
    for anahtar, deger in GUVENLIK_BASLIKLARI.items():
        assert yanit.headers.get(anahtar) == deger, (yanit.url, anahtar)


def test_guvenlik_basliklari_her_yanitta(istemci, prob):
    yanitlar = [
        istemci.get("/saglik"),
        istemci.get("/", follow_redirects=False),
        istemci.get("/statik/site.css"),
        istemci.get("/statik/yer-tutucu/robot.svg"),
        istemci.get("/tr/boyle-bir-sayfa-yok"),
        istemci.get(prob),
    ]
    for y in yanitlar:
        _basliklari_denetle(y)
    assert GUVENLIK_BASLIKLARI["X-Robots-Tag"] == "noindex, nofollow"
    assert "script-src 'self'" in GUVENLIK_BASLIKLARI["Content-Security-Policy"]


def test_sayfada_satir_ici_script_ve_stil_yok(istemci, prob):
    html = sayfa_denetle(istemci.get(prob))
    assert '<script src="/statik/site.js" defer></script>' in html
    assert 'href="/statik/site.css"' in html
    assert 'id="gb-dugme"' in html and '<dialog id="gb-pencere"' in html
    assert 'id="cerez-bandi"' in html
    assert 'action="/tercih"' in html
    assert re.search(r'<form class="tercih" action="/tercih"[^>]*>.*?<button type="submit"', html, re.S)


def test_demo_bandi_hata_sayfalarinda_da_var(istemci):
    y404 = istemci.get("/tr/olmayan")
    assert y404.status_code == 404
    assert "DEMO – gerçek satış ve ödeme yapılmaz" in sayfa_denetle(y404)
    y403 = istemci.post("/tercih", data={"dil": "en"}, follow_redirects=False)
    assert y403.status_code == 403
    assert "Oturum süresi doldu, sayfayı yenileyip tekrar deneyin" in sayfa_denetle(y403)


@pytest.mark.parametrize(
    "deger",
    ["https://evil.com", "//evil.com", "/\\evil", "\\\\evil", "javascript:alert(1)", "http:/evil",
     " /tr/", "/tr/\nLocation: x", None, ""],
)
def test_guvenli_sonraki_reddeder(deger):
    assert guvenli_sonraki(deger) == "/"


@pytest.mark.parametrize("deger", ["/tr/sepet", "/en/urun/5?x=1", "/"])
def test_guvenli_sonraki_korur(deger):
    assert guvenli_sonraki(deger) == deger


def test_guvenli_sonraki_varsayilan():
    assert guvenli_sonraki("https://evil.com", "/tr/hesabim") == "/tr/hesabim"


def test_hiz_siniri():
    h = HizSiniri(limit=10, pencere=60.0)
    assert all(h.izin("ip", 100.0 + i) for i in range(10))
    assert h.izin("ip", 110.0) is False
    assert h.izin("baska-ip", 110.0) is True
    assert h.izin("ip", 161.0) is True  # 100 ve 101'deki denemeler pencereden çıktı


def test_csrf_eksik_veya_yanlis_post_403(istemci, prob):
    assert istemci.post("/tercih", data={"dil": "en", "sonraki": "/tr/"}, follow_redirects=False).status_code == 403
    csrf_al(istemci, prob)
    yanit = istemci.post("/tercih", data={"dil": "en", "csrf": "yanlis"}, follow_redirects=False)
    assert yanit.status_code == 403


def test_eski_oturum_misafire_duser(istemci, prob):
    oturum_yaz(istemci, {"mid": 999, "csrf": "x"})
    yanit = istemci.get(prob)
    assert yanit.status_code == 200
    assert 'href="/tr/giris"' in yanit.text
    assert 'action="/tr/cikis"' not in yanit.text

    istemci.cookies.clear()
    istemci.cookies.set("cr_oturum", "bozuk.imza.degeri")
    yanit = istemci.get(prob)
    assert yanit.status_code == 200
    assert 'href="/tr/giris"' in yanit.text


def test_mid_tamsayi_degilse_misafir(istemci, prob):
    oturum_yaz(istemci, {"mid": "abc"})
    yanit = istemci.get(prob)
    assert yanit.status_code == 200
    assert 'href="/tr/giris"' in yanit.text


def test_tercih_dil_degisince_yol_degisir(istemci, prob):
    csrf = csrf_al(istemci, prob)
    yanit = istemci.post(
        "/tercih", data={"csrf": csrf, "dil": "en", "ulke": "TR", "sonraki": "/tr/sepet?x=1"}, follow_redirects=False
    )
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/en/sepet?x=1"
    assert yanit.cookies.get("dil") == "en"
    assert istemci.get("/", follow_redirects=False).headers["location"] == "/en/"


def test_tercih_kokte_dil_onekli_yola_gider(istemci, prob):
    csrf = csrf_al(istemci, prob)
    yanit = istemci.post("/tercih", data={"csrf": csrf, "dil": "en", "sonraki": "/"}, follow_redirects=False)
    assert yanit.headers["location"] == "/en/"


def test_tercih_ulke_oturuma_ve_cereze_yazilir(istemci, prob):
    csrf = csrf_al(istemci, prob)
    yanit = istemci.post(
        "/tercih", data={"csrf": csrf, "dil": "tr", "ulke": "DE", "sonraki": prob}, follow_redirects=False
    )
    assert yanit.headers["location"] == prob
    assert yanit.cookies.get("ulke") == "DE"
    assert oturum_oku(istemci)["ulke"] == "DE"
    assert '<option value="DE" selected>' in istemci.get(prob).text


def test_tercih_gecersiz_degerler_yok_sayilir(istemci, prob):
    csrf = csrf_al(istemci, prob)
    yanit = istemci.post(
        "/tercih", data={"csrf": csrf, "dil": "xx", "ulke": "XX", "sonraki": "https://evil.com"}, follow_redirects=False
    )
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/"
    assert "ulke" not in oturum_oku(istemci)
    assert "dil" not in yanit.cookies


def test_kok_yonlendirme_varsayilan_tr(istemci):
    yanit = istemci.get("/", follow_redirects=False)
    assert yanit.status_code == 302
    assert yanit.headers["location"] == "/tr/"


@pytest.mark.parametrize(
    ("tutar", "para", "dil", "beklenen"),
    [
        (Decimal("1234.5"), "TRY", "tr", "1.234,50 ₺"),
        (Decimal("1234.5"), "EUR", "tr", "1.234,50 €"),
        (Decimal("1234.5"), "EUR", "en", "€1,234.50"),
        (Decimal("1234.5"), "TRY", "en", "₺1,234.50"),
        (Decimal("1234567.891"), "TRY", "tr", "1.234.567,89 ₺"),
        (Decimal("0"), "TRY", "tr", "0,00 ₺"),
        (Decimal("0.005"), "EUR", "en", "€0.01"),
        (Decimal("-15"), "EUR", "tr", "-15,00 €"),
    ],
)
def test_para_bicimle(tutar, para, dil, beklenen):
    assert para_bicimle(tutar, para, dil) == beklenen


def test_ceviri_eksik_anahtar_tr_ye_sonra_anahtara_duser(tmp_path):
    (tmp_path / "tr.json").write_text(
        '{"a.b": "Merhaba {ad}", "a.yalniz_tr": "Yalnız TR"}', encoding="utf-8"
    )
    (tmp_path / "en.json").write_text('{"a.b": "Hello {ad}", "a.yalniz_en": "Only EN"}', encoding="utf-8")
    c = Ceviri(tmp_path)
    assert c.t("en", "a.b", ad="Ayşe") == "Hello Ayşe"
    assert c.t("en", "a.yalniz_tr") == "Yalnız TR"
    assert c.t("tr", "a.yok") == "a.yok"
    assert c.t("tr", "a.b") == "Merhaba {ad}"
    assert c.t("de", "a.b", ad="X") == "Merhaba X"
    assert c.var("a.b") and not c.var("a.yok")
    assert c.eksik_anahtarlar() == {"tr": ["a.yalniz_en"], "en": ["a.yalniz_tr"]}


def test_ceviri_dosyalari_esit():
    """Sonraki görevler anahtar ekledikçe bu test korunur: tr ve en aynı anahtar kümesine sahip."""
    c = Ceviri(uygulama_modulu.WEB / "dil")
    assert c.eksik_anahtarlar() == {"tr": [], "en": []}
    desen = re.compile(r"^[a-z_]+\.[A-Za-z0-9_]+$")
    for dil in ("tr", "en"):
        for anahtar in c._metinler[dil]:
            assert desen.match(anahtar), anahtar
            assert isinstance(c._metinler[dil][anahtar], str) and c._metinler[dil][anahtar].strip(), anahtar


def test_saglik_json(istemci):
    yanit = istemci.get("/saglik")
    assert yanit.status_code == 200
    assert yanit.json() == {"durum": "ok", "son_esitleme": None, "urun": 0}
    with istemci_db(istemci) as con:
        urun_ekle(con, sku="S1")
        urun_ekle(con, sku="S2", aktif=False)
        con.execute(
            "INSERT INTO esitleme_gunlugu(basla, bitis, durum) VALUES (?, ?, 'tam')",
            ("2026-10-12T02:30:00+00:00", "2026-10-12T02:35:00+00:00"),
        )
    assert istemci.get("/saglik").json() == {"durum": "ok", "son_esitleme": "2026-10-12T02:35:00+00:00", "urun": 1}


def test_404_sayfasi(istemci):
    yanit = istemci.get("/tr/olmayan")
    assert yanit.status_code == 404
    assert '<html lang="tr">' in yanit.text and "Sayfa bulunamadı" in yanit.text
    yanit = istemci.get("/en/olmayan")
    assert yanit.status_code == 404
    assert '<html lang="en">' in yanit.text and "Page not found" in yanit.text
    assert istemci.get("/xx/").status_code == 404


def test_dil_oneksiz_yolda_tr(istemci):
    istemci.cookies.set("dil", "en")
    yanit = istemci.get("/olmayan-oneksiz")
    assert yanit.status_code == 404
    assert '<html lang="tr">' in yanit.text and "Sayfa bulunamadı" in yanit.text


def test_500_hata_kimligi_gosterilir_yigin_izi_gosterilmez(istemci):
    @istemci.app.get("/_patlat")
    def _patlat():
        raise RuntimeError("gizli-yigin-izi")

    c = TestClient(istemci.app, raise_server_exceptions=False)
    yanit = c.get("/_patlat")
    assert yanit.status_code == 500
    _basliklari_denetle(yanit)
    assert re.search(r'<code class="hata-kimligi">[0-9A-F]{8}</code>', yanit.text)
    assert "gizli-yigin-izi" not in yanit.text
    assert "Traceback" not in yanit.text
    assert 'class="demo-bandi"' in yanit.text


@pytest.mark.parametrize(
    ("kok", "dosya"),
    [("Endüstriyel Robotlar", "robot"), ("Pozisyonerler", "pozisyoner"), ("GÜÇ KAYNAĞI", "guc"),
     ("Elektrik ve Elektronik", "elektrik"), ("ABB REDÜKTÖR", "reduktor"), ("Slider", "slider"),
     ("", "genel"), (None, "genel")],
)
def test_yer_tutucu(kok, dosya):
    assert yer_tutucu(kok) == f"/statik/yer-tutucu/{dosya}.svg"


@pytest.mark.parametrize("ad", ["robot", "elektrik", "mekanik", "genel"])
def test_yer_tutucu_dosyalari_sunulur(istemci, ad):
    yanit = istemci.get(f"/statik/yer-tutucu/{ad}.svg")
    assert yanit.status_code == 200
    assert yanit.headers["content-type"].startswith("image/svg+xml")
    assert "<script" not in yanit.text


# ---------------------------------------------------------------------------
# K22 (tasarım yönü "Atölye") doğrulamaları — docs/tasarim/2026-10-13-tasarim-yonu-atolye.md §5
# ---------------------------------------------------------------------------
import xml.etree.ElementTree as ET

from app.fiyat.kurallar import MusteriTipi
from app.hesap.servis import KayitGirdisi, kayit_ol
from tests.conftest import SABIT_ZAMAN, TEST_GIZLI, kategori_ekle

# Vitrin: lacivert + #fa5f0b. Aralık tokenları K22 ile aynı; renkler ceylanrobot.com ailesi.
K22_TOKENLARI = {
    "--bg": "#f3f5f8", "--surface": "#ffffff", "--surface-2": "#e7edf3",
    "--ink": "#071320", "--ink-muted": "#4a5563",
    "--brand-900": "#02111e", "--brand-600": "#16324d", "--brand-500": "#2a4a68",
    "--accent": "#fa5f0b", "--accent-700": "#c2410c",
    "--info": "#267593", "--info-700": "#1d607c",
    "--border": "#d3dce6", "--border-strong": "#7d8b9c",
    "--ok": "#2e6b3a", "--ok-bg": "#e3efe2", "--warn": "#7a4f00", "--warn-bg": "#fbefd0",
    "--danger": "#8f3222", "--danger-bg": "#f8e3de",
    "--focus": "#267593", "--focus-on-dark": "#f2b705",
    "--r-sm": "4px", "--r-md": "6px", "--r-pill": "999px",
    "--s1": "4px", "--s2": "8px", "--s3": "12px", "--s4": "16px", "--s5": "24px", "--s6": "32px", "--s7": "48px",
    "--container": "1280px",
}
ESKI_TOKEN_TAKMA_ADLARI = {
    "--yesil-koyu": "var(--brand-900)", "--yesil": "var(--brand-600)", "--kiremit": "var(--accent)",
    "--mavi": "var(--info)", "--zemin": "var(--bg)", "--cizgi": "var(--border)", "--yazi": "var(--ink)",
}
IKONLAR = {"arama", "sepet", "kullanici", "telefon", "kontrol", "kalkan", "kamyon", "dunya", "dosya",
           "filtre", "carpi", "ok-sag", "uyari", "bilgi", "kopyala", "karsilastir"}   # G3c: karsilastir
_SVG = "{http://www.w3.org/2000/svg}"


def _kok_tokenlari() -> dict[str, str]:
    css = (uygulama_modulu.WEB / "statik" / "site.css").read_text(encoding="utf-8")
    kok = re.search(r":root\s*\{(.*?)\}", css, re.S)
    assert kok, ":root bloğu yok"
    return {a.strip(): v.strip() for a, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", kok.group(1))}


def test_site_css_k22_tokenlari():
    tokenlar = _kok_tokenlari()
    for ad, deger in K22_TOKENLARI.items():
        assert tokenlar.get(ad, "").lower() == deger, ad
    for ad in ("--font-ui", "--font-mono", "--font-display", "--shadow-pop"):
        assert ad in tokenlar, ad
    assert tokenlar["--font-display"].startswith("system-ui")


def test_site_css_eski_token_adlari_takma_ad():
    tokenlar = _kok_tokenlari()
    for ad, deger in ESKI_TOKEN_TAKMA_ADLARI.items():
        assert tokenlar.get(ad) == deger, ad
    assert "--gri" in tokenlar


def test_ikon_sprite_her_sembol_var():
    kok = ET.parse(uygulama_modulu.WEB / "statik" / "ikonlar.svg").getroot()
    assert kok.tag == f"{_SVG}svg"
    semboller = {s.get("id"): s for s in kok.iter(f"{_SVG}symbol")}
    assert set(semboller) == IKONLAR
    for ad, s in semboller.items():
        assert s.get("viewBox") == "0 0 24 24", ad
        assert s.get("stroke") == "currentColor" and s.get("stroke-width") == "1.5", ad
        assert len(list(s)) > 0, ad
    assert not list(kok.iter(f"{_SVG}script"))


def test_ikon_sprite_sunulur(istemci):
    yanit = istemci.get("/statik/ikonlar.svg")
    assert yanit.status_code == 200
    assert yanit.headers["content-type"].startswith("image/svg+xml")


def test_baslik_duzeni(istemci, prob):
    html = sayfa_denetle(istemci.get(prob))
    bant = re.search(r'<div class="ust-bant">.*?</div>\s*</div>', html, re.S).group(0)
    assert 'class="demo-bandi"' in bant and 'action="/tercih"' in bant
    ust = re.search(r'<header class="ust">.*?</header>', html, re.S).group(0)
    assert 'class="logo"' in ust and 'href="/tr/"' in ust
    assert re.search(r'<img class="logo-resim" src="/statik/marka/ceylan-robot-logo\.png" alt="Ceylan Robot" width="\d+" height="\d+"', ust)
    assert 'placeholder="Parça no veya ürün adı"' in ust          # G3h madde 14: 360 px'te kesilmeyen kısa metin
    assert 'href="/tr/sepet"' in ust and '<span class="sayac"' in ust
    assert '<use href="/statik/ikonlar.svg#arama"></use>' in ust
    assert '<use href="/statik/ikonlar.svg#sepet"></use>' in ust
    assert 'class="kategori-serit"' not in html  # kategori yokken şerit basılmaz


def test_resmi_logo_ve_favicon(istemci, prob):
    html = sayfa_denetle(istemci.get(prob))
    assert '<link rel="icon" type="image/png" sizes="48x48" href="/statik/marka/favicon-48.png">' in html
    assert '<link rel="icon" type="image/png" sizes="192x192" href="/statik/marka/favicon-192.png">' in html
    for yol in ("ceylan-robot-logo.png", "favicon-48.png", "favicon-192.png"):
        y = istemci.get(f"/statik/marka/{yol}")
        assert y.status_code == 200 and y.headers["content-type"] == "image/png", yol
        assert y.content[:8] == b"\x89PNG\r\n\x1a\n", yol


def test_yonetim_basliginda_logo(istemci):
    html = istemci.get("/yonetim/giris").text
    assert 'src="/statik/marka/ceylan-robot-logo.png" alt="Ceylan Robot"' in html


def test_kok_kategori_seridi(istemci, prob):
    with istemci_db(istemci) as con:
        elk = kategori_ekle(con, kaynak_id="k10", ad="Elektrik ve Elektronik", yol="10", seviye=0)
        rob = kategori_ekle(con, kaynak_id="k12", ad="Endüstriyel Robotlar", yol="12", seviye=0)
        alt = kategori_ekle(con, kaynak_id="k1241", ad="KUKA", yol="12.41", seviye=1, ust_kaynak_id="k12")
        # G3e madde 19: 0 ürünlü kategoriler menüde gösterilmez; şerit için ürünlü kökler
        urun_ekle(con, sku="SR-1", ad="ŞERİT ÜRÜNÜ", kategori_id=elk)
        urun_ekle(con, sku="SR-2", ad="ŞERİT ROBOTU", kategori_id=alt)
    html = sayfa_denetle(istemci.get(prob))
    serit = re.search(r'<nav class="kategori-serit"[^>]*>.*?</nav>', html, re.S).group(0)
    assert f'href="/tr/kategori/{elk}"' in serit and f'href="/tr/kategori/{rob}"' in serit
    assert f'href="/tr/kategori/{alt}"' not in serit
    en = istemci.get("/en/_prob").text
    assert f'href="/en/kategori/{rob}"' in en
    assert f'href="/tr/kategori/{rob}"' in istemci.get("/tr/olmayan").text  # 404 sayfasında da


def test_site_js_kopyala_kodu_var():
    js = (uygulama_modulu.WEB / "statik" / "site.js").read_text(encoding="utf-8")
    assert "[data-kopyala]" in js


def test_parola_hata_kodlari_cevrildi():
    c = Ceviri(uygulama_modulu.WEB / "dil")
    for kod in ("parola_uzun", "gecersiz", "parola_kisa"):
        assert c.var(f"hata_kodu.{kod}"), kod
    assert c.t("en", "hata_kodu.parola_uzun") != c.t("tr", "hata_kodu.parola_uzun")


def test_telefon_varsayilan_baslikta(istemci, prob):
    html = sayfa_denetle(istemci.get(prob))
    bant = re.search(r'<div class="ust-bant">.*?</div>\s*</div>', html, re.S).group(0)
    assert 'href="tel:+903322391575"' in bant
    assert "+90 (332) 239 15 75" in bant
    assert 'aria-label="Satış ve teknik destek: +90 (332) 239 15 75"' in bant


def test_telefon_bos_ise_satir_basilmaz(tmp_path):
    from app.ayarlar import ayarlari_oku
    from app.web.uygulama import uygulama_olustur

    ortam = {"SHOP_DB": str(tmp_path / "t.db"), "SHOP_GIZLI_ANAHTAR": TEST_GIZLI,
             "SHOP_YONETICI": "yonetici", "SHOP_YONETICI_OZET": "x", "SHOP_TELEFON": ""}
    ayarlar = ayarlari_oku(ortam)
    assert ayarlar.telefon == ""
    assert ayarlari_oku({k: v for k, v in ortam.items() if k != "SHOP_TELEFON"}).telefon == "+90 (332) 239 15 75"
    with TestClient(uygulama_olustur(ayarlar)) as c:
        html = sayfa_denetle(c.get("/tr/olmayan"))
    assert 'href="tel:' not in html and 'class="ust-iletisim"' not in html


def test_musteri_adi_baslikta_kacislanir(istemci, prob):
    with istemci_db(istemci) as con:
        mid = kayit_ol(con, KayitGirdisi(tip=MusteriTipi.BIREYSEL, ad="<script>alert(1)</script>",
                                         eposta="qa.xss@example.com", parola="QATest-parola-1", ulke="TR",
                                         kvkk_onay=True), SABIT_ZAMAN).id
    oturum_yaz(istemci, {"mid": mid})
    html = sayfa_denetle(istemci.get(prob))
    ust = re.search(r'<header class="ust">.*?</header>', html, re.S).group(0)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in ust
    assert "<script>alert" not in html
    assert 'action="/tr/cikis"' in ust
