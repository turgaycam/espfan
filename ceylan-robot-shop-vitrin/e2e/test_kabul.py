"""§11 kabul senaryoları 1–4, geri bildirim/yönetim (5), güvenlik (7), TR/EN ve 360 px mobil.

Sahte veri: ad "QATestUser", e-posta her çalışmada benzersiz (zaman damgası).
"""
from __future__ import annotations

import re
import time

import pytest
from playwright.sync_api import Page, expect

KUKA_SKU = "8301033800019"
BASARILI_KART = "4111 1111 1111 1111"
RET_KARTI = "4000 0000 0000 0002"
GECERSIZ_KART = "5555 5555 5555 4444"
SMS_KODU = "000000"
TEST_VKN = "1234567890"          # GİB algoritmasına göre geçerli test VKN'si
PAROLA = "QATest-Parola-2026"
ARAMA_TERIMLERI = ("ABB", "KABLO", "MOTOR", "RÖLE", "SÜRÜCÜ")
SIPARIS_NO = re.compile(r"CR-DEMO-\d{8}-\d{4}")
TEKLIF_NO = re.compile(r"CR-TKL-\d{8}-\d{4}")
KONTROL_SAYFALARI = ["/tr/", "/tr/ara?q=ABB", "/tr/sepet", "/tr/kayit", "/tr/giris", "/tr/teklif",
                     "/tr/yasal/kvkk", "/en/", "/en/kayit"]


# ---------- yardımcılar ----------

def benzersiz_eposta(etiket: str) -> str:
    return f"qatestuser+{etiket}-{time.strftime('%Y%m%d%H%M%S')}-{time.perf_counter_ns() % 100000}@example.com"


def e2e(sayfa: Page, ad: str):
    return sayfa.locator(f'[data-e2e="{ad}"]')


def alan(sayfa: Page, ad: str):
    # name'i olmayan kart son kullanma/CVC alanları id ile bulunur (Görev 14: sunucuya gönderilmezler).
    # Arama <main> içinde: üst banttaki tercih formunun #sec-ulke (name="ulke") seçicisi DOM'da önce gelir ve
    # değişince /tercih'e gönderilip sayfayı yeniler; form alanı yerine onu doldurmak girilen değerleri siler.
    return sayfa.locator("main#icerik").locator(f'[name="{ad}"], #{ad}')


def doldur(sayfa: Page, ad: str, deger: str | bool) -> bool:
    """Alan varsa türüne göre doldurur; yoksa ya da gizliyse False döner."""
    loc = alan(sayfa, ad)
    if loc.count() == 0:
        return False
    tur = loc.first.evaluate("e => e.tagName === 'SELECT' ? 'select' : (e.type || 'text')")
    if tur == "hidden":
        return False
    if tur == "radio":
        loc.and_(sayfa.locator(f'[value="{deger}"]')).check()
        return True
    if not loc.first.is_visible():
        return False
    if tur == "select":
        loc.first.select_option(str(deger))
    elif tur == "checkbox":
        loc.first.check() if deger else loc.first.uncheck()
    else:
        loc.first.fill(str(deger))
    return True


def zorunlu(sayfa: Page, ad: str, deger: str | bool) -> None:
    assert doldur(sayfa, ad, deger), f"form alanı bulunamadı: {ad} ({sayfa.url})"


def oturum_acik(sayfa: Page) -> None:
    expect(e2e(sayfa, "cikis")).to_have_count(1)


def kayit_ol(sayfa: Page, dil: str, tip: str, eposta: str, *, ulke: str = "TR", vkn: str | None = None,
             vergi_dairesi: str | None = None, vat_id: str | None = None, sonraki: str | None = None) -> None:
    yol = f"/{dil}/kayit?tip={tip}" + (f"&sonraki={sonraki}" if sonraki else "")
    sayfa.goto(yol)
    doldur(sayfa, "tip", tip)
    zorunlu(sayfa, "ad", "QATestUser")
    zorunlu(sayfa, "eposta", eposta)
    zorunlu(sayfa, "parola", PAROLA)
    doldur(sayfa, "ulke", ulke)
    if vkn:
        zorunlu(sayfa, "vergi_kimlik_no", vkn)
        zorunlu(sayfa, "vergi_dairesi", vergi_dairesi or "Pendik")
    if vat_id:
        doldur(sayfa, "vat_id", vat_id)
    zorunlu(sayfa, "kvkk_onay", True)
    e2e(sayfa, "kayit-gonder").click()
    sayfa.wait_for_load_state()
    assert "/kayit" not in sayfa.url, f"kayıt başarısız: {sayfa.url}"
    oturum_acik(sayfa)


def sepete_eklenebilir_urun_ac(sayfa: Page, dil: str) -> str:
    """Arama ile (kabul §11.1: 'ürün aranır') sepete eklenebilen ilk ürünü açar; yolunu döner."""
    for terim in ARAMA_TERIMLERI:
        sayfa.goto(f"/{dil}/ara?q={terim}")
        baglantilar = [a.get_attribute("href") for a in e2e(sayfa, "urun-baglanti").all()[:12]]
        for href in baglantilar:
            sayfa.goto(href)
            if e2e(sayfa, "sepete-ekle").count() > 0:
                return href
    pytest.fail(f"sepete eklenebilir ürün bulunamadı: {ARAMA_TERIMLERI}")


def sepete_ekle_ve_sepete_git(sayfa: Page, dil: str) -> None:
    e2e(sayfa, "sepete-ekle").first.click()
    sayfa.wait_for_load_state("networkidle")
    sayfa.goto(f"/{dil}/sepet")
    expect(e2e(sayfa, "sepet-kalemi").first).to_be_visible()


def odeme_formu(sayfa: Page, *, ulke: str, teslim: str) -> None:
    tr = ulke == "TR"
    zorunlu(sayfa, "teslimat_ad_soyad", "QATestUser Teslim")
    zorunlu(sayfa, "teslimat_satir1", "Test Mah. Demo Sok. No:1" if tr else "Teststrasse 1")
    zorunlu(sayfa, "teslimat_sehir", "İstanbul" if tr else "Berlin")
    doldur(sayfa, "teslimat_posta_kodu", "34906" if tr else "10115")
    zorunlu(sayfa, "teslimat_ulke", ulke)
    doldur(sayfa, "teslimat_telefon", "+90 555 000 00 00" if tr else "+49 30 000000")
    doldur(sayfa, "fatura_ayni", True)
    zorunlu(sayfa, "teslim", teslim)
    doldur(sayfa, "on_bilgi_onay", True)
    doldur(sayfa, "mesafeli_onay", True)
    doldur(sayfa, "kosullar_onay", True)   # kurumsal / yurt dışı (Görev 14)


def odemeye_gec_ve_siparis_ac(sayfa: Page, dil: str, *, ulke: str, teslim: str, odeme_yontemi: str | None = None) -> str:
    sayfa.goto(f"/{dil}/odeme")
    odeme_formu(sayfa, ulke=ulke, teslim=teslim)
    if odeme_yontemi:      # G3m madde 23: yurt dışı müşteride varsayılan havale; kart akışı açıkça seçilir
        zorunlu(sayfa, "odeme_yontemi", odeme_yontemi)
    e2e(sayfa, "odeme-gonder").click()
    sayfa.wait_for_url(re.compile(rf"/{dil}/odeme/CR-DEMO-\d{{8}}-\d{{4}}/kart"))
    return SIPARIS_NO.search(sayfa.url).group(0)


def kart_gir(sayfa: Page, kart: str) -> None:
    zorunlu(sayfa, "kart_no", kart)
    doldur(sayfa, "kart_ad", "QATestUser")
    doldur(sayfa, "kart_skt", "12/30")
    doldur(sayfa, "kart_cvc", "123")
    e2e(sayfa, "kart-gonder").click()
    sayfa.wait_for_load_state()


def sms_gir(sayfa: Page) -> None:
    sayfa.wait_for_url(re.compile(r"/odeme/CR-DEMO-\d{8}-\d{4}/3d"))
    zorunlu(sayfa, "sms_kodu", SMS_KODU)
    e2e(sayfa, "sms-gonder").click()
    sayfa.wait_for_load_state()


def basarili_ode(sayfa: Page, dil: str, no: str) -> None:
    if f"/odeme/{no}/kart" not in sayfa.url:
        sayfa.goto(f"/{dil}/odeme/{no}/kart")
    kart_gir(sayfa, BASARILI_KART)
    sms_gir(sayfa)
    sayfa.wait_for_url(re.compile(rf"/{dil}/siparis/{no}"))
    expect(e2e(sayfa, "siparis-durum")).to_have_attribute("data-durum", "odendi")


def hesabimda_gorunur(sayfa: Page, dil: str, no: str) -> None:
    sayfa.goto(f"/{dil}/hesabim")
    expect(sayfa.get_by_text(no).first).to_be_visible()


def yonetime_gir(sayfa: Page, yonetici: tuple[str, str]) -> None:
    sayfa.goto("/yonetim/giris")
    zorunlu(sayfa, "kullanici", yonetici[0])
    zorunlu(sayfa, "parola", yonetici[1])
    e2e(sayfa, "yonetim-giris").click()
    sayfa.wait_for_load_state()
    assert "/yonetim/giris" not in sayfa.url, "yönetici girişi başarısız"


def tercih_sec(sayfa: Page, ad: str, deger: str, beklenen_url: re.Pattern) -> None:
    form = sayfa.locator('form[action="/tercih"]').first
    form.locator(f'select[name="{ad}"]').select_option(deger)
    try:
        sayfa.wait_for_url(beklenen_url, timeout=2000)   # JS seçimde formu kendisi gönderiyorsa
    except Exception:
        form.locator('[type="submit"]').first.click()
        sayfa.wait_for_url(beklenen_url)


# ---------- §11.1 Bireysel TR siparişi ----------

def test_senaryo1_bireysel_tr_siparisi(sayfa: Page):
    sepete_eklenebilir_urun_ac(sayfa, "tr")
    fiyat = e2e(sayfa, "fiyat-ana").first
    expect(fiyat).to_have_attribute("data-para", "TRY")
    expect(fiyat).to_have_attribute("data-kdv", "dahil")
    expect(fiyat).to_contain_text("₺")
    expect(sayfa.locator(".rozet-temsili").first).to_be_visible()
    sepete_ekle_ve_sepete_git(sayfa, "tr")

    e2e(sayfa, "odemeye-gec").click()
    sayfa.wait_for_url(re.compile(r"/tr/odeme$"))  # G3g madde 1: giriş duvarı yok; hesap ödeme formunda açılabilir
    expect(e2e(sayfa, "odeme-hesap")).to_be_visible()
    kayit_ol(sayfa, "tr", "bireysel", benzersiz_eposta("bireysel"), sonraki="/tr/odeme")   # kayıt sayfası yolu aynen

    sayfa.goto("/tr/sepet")                            # misafir sepeti üye sepetine geçti
    expect(e2e(sayfa, "sepet-kalemi").first).to_be_visible()
    no = odemeye_gec_ve_siparis_ac(sayfa, "tr", ulke="TR", teslim="kargo")
    expect(e2e(sayfa, "satir-kdv").first).to_be_visible()
    basarili_ode(sayfa, "tr", no)
    hesabimda_gorunur(sayfa, "tr", no)


# ---------- §11.2 Kurumsal TR siparişi (+ §11.7 test dışı kart reddi) ----------

def test_senaryo2_kurumsal_tr_ret_sonra_basari(sayfa: Page):
    kayit_ol(sayfa, "tr", "kurumsal", benzersiz_eposta("kurumsal"), vkn=TEST_VKN, vergi_dairesi="Pendik",
             sonraki="/tr/")
    sepete_eklenebilir_urun_ac(sayfa, "tr")
    fiyat = e2e(sayfa, "fiyat-ana").first
    expect(fiyat).to_have_attribute("data-para", "EUR")
    expect(fiyat).to_have_attribute("data-kdv", "haric")
    expect(e2e(sayfa, "fiyat-ikincil").first).to_contain_text("₺")
    sepete_ekle_ve_sepete_git(sayfa, "tr")
    expect(e2e(sayfa, "satir-kdv").first).to_be_visible()   # KDV sepette ayrı satır

    no = odemeye_gec_ve_siparis_ac(sayfa, "tr", ulke="TR", teslim="kargo")

    kart_gir(sayfa, GECERSIZ_KART)                             # test kartı değil -> sunucu reddeder
    expect(sayfa.locator('[data-e2e="odeme-hata"][data-kod="gecersiz_kart"]')).to_be_visible()
    assert "/3d" not in sayfa.url

    sayfa.goto(f"/tr/odeme/{no}/kart")
    kart_gir(sayfa, RET_KARTI)
    sms_gir(sayfa)
    expect(sayfa.locator('[data-e2e="odeme-hata"][data-kod="ret"]')).to_be_visible()

    basarili_ode(sayfa, "tr", no)                              # aynı sipariş, yeni sipariş açılmaz
    hesabimda_gorunur(sayfa, "tr", no)


# ---------- §11.3 Yurt dışı siparişi (EN) ----------

def test_senaryo3_yurtdisi_en_ihracat_istisnasi(sayfa: Page):
    kayit_ol(sayfa, "en", "yurtdisi", benzersiz_eposta("yurtdisi"), ulke="DE", vat_id="DE123456789",
             sonraki="/en/")
    expect(sayfa.locator("html")).to_have_attribute("lang", "en")
    sepete_eklenebilir_urun_ac(sayfa, "en")
    fiyat = e2e(sayfa, "fiyat-ana").first
    expect(fiyat).to_have_attribute("data-para", "EUR")
    expect(fiyat).to_have_attribute("data-kdv", "haric")
    sepete_ekle_ve_sepete_git(sayfa, "en")

    no = odemeye_gec_ve_siparis_ac(sayfa, "en", ulke="DE", teslim="yurtdisi_dap", odeme_yontemi="kart")
    expect(e2e(sayfa, "satir-ihracat").first).to_be_visible()
    expect(e2e(sayfa, "not-dap").first).to_be_visible()
    expect(e2e(sayfa, "satir-kdv")).to_have_count(0)
    basarili_ode(sayfa, "en", no)
    expect(e2e(sayfa, "satir-ihracat").first).to_be_visible()
    hesabimda_gorunur(sayfa, "en", no)


# ---------- G3g madde 1: ödemede gömülü hesap (hesap siparişle aynı işlemde açılır) ----------

def test_g3g_odemede_gomulu_hesap_ile_siparis(sayfa: Page):
    sepete_eklenebilir_urun_ac(sayfa, "tr")
    sepete_ekle_ve_sepete_git(sayfa, "tr")
    e2e(sayfa, "odemeye-gec").click()
    sayfa.wait_for_url(re.compile(r"/tr/odeme$"))
    expect(e2e(sayfa, "odeme-hesap")).to_be_visible()
    expect(e2e(sayfa, "odeme-hesap-giris")).to_have_attribute("href", "/tr/giris?sonraki=%2Ftr%2Fodeme")
    zorunlu(sayfa, "hesap_tip", "bireysel")
    zorunlu(sayfa, "hesap_eposta", benzersiz_eposta("gomulu"))
    zorunlu(sayfa, "hesap_parola", PAROLA)
    zorunlu(sayfa, "hesap_kvkk_onay", True)
    odeme_formu(sayfa, ulke="TR", teslim="kargo")
    e2e(sayfa, "odeme-gonder").click()
    sayfa.wait_for_url(re.compile(r"/tr/odeme/CR-DEMO-\d{8}-\d{4}/kart"))
    oturum_acik(sayfa)                                   # hesap açıldı, oturum açık
    no = SIPARIS_NO.search(sayfa.url).group(0)
    basarili_ode(sayfa, "tr", no)
    hesabimda_gorunur(sayfa, "tr", no)


# ---------- G3g madde 2: sepeti teklif olarak gönder (çok kalemli) ----------

def test_g3g_sepeti_teklif_olarak_gonder(sayfa: Page):
    sepete_eklenebilir_urun_ac(sayfa, "tr")
    sepete_ekle_ve_sepete_git(sayfa, "tr")
    e2e(sayfa, "sepet-teklif").click()
    sayfa.wait_for_url(re.compile(r"/tr/teklif\?sepet=1"))
    expect(e2e(sayfa, "teklif-kalem").first).to_be_visible()
    zorunlu(sayfa, "ad", "QATestUser")
    zorunlu(sayfa, "telefon", "+90 555 000 00 00")
    doldur(sayfa, "ulke", "TR")
    doldur(sayfa, "kvkk_onay", True)
    e2e(sayfa, "teklif-gonder").click()
    sayfa.wait_for_url(re.compile(r"/tr/teklif/tamam"))
    expect(e2e(sayfa, "teklif-no")).to_contain_text("CR-TKL-")


# ---------- §11.4 Teklif (KUKA) ----------

def test_senaryo4_kuka_teklif_yonetimde_listelenir(sayfa: Page, yonetici):
    sayfa.goto(f"/tr/ara?q={KUKA_SKU}")
    e2e(sayfa, "urun-baglanti").first.click()
    sayfa.wait_for_url(re.compile(r"/tr/urun/\d+"))
    expect(sayfa.get_by_text("KUKA KRC5 KR 140 R3200-2 PA").first).to_be_visible()
    expect(e2e(sayfa, "sepete-ekle")).to_have_count(0)
    e2e(sayfa, "teklif-iste").first.click()
    sayfa.wait_for_url(re.compile(r"/tr/teklif"))

    zorunlu(sayfa, "ad", "QATestUser")
    doldur(sayfa, "firma", "QATest Otomasyon A.Ş.")
    zorunlu(sayfa, "eposta", benzersiz_eposta("teklif"))
    doldur(sayfa, "telefon", "+90 555 000 00 00")
    doldur(sayfa, "ulke", "TR")
    doldur(sayfa, "adet", "1")
    zorunlu(sayfa, "mesaj", "QATest: KUKA KRC5 için fiyat ve teslim süresi rica ederiz.")
    doldur(sayfa, "kvkk_onay", True)   # G3c madde 21: misafir teklifinde aydınlatma onayı (alan yoksa atlanır)
    e2e(sayfa, "teklif-gonder").click()
    sayfa.wait_for_url(re.compile(r"/tr/teklif/tamam"))
    no = TEKLIF_NO.search(e2e(sayfa, "teklif-no").inner_text()).group(0)

    yonetime_gir(sayfa, yonetici)
    sayfa.goto("/yonetim/teklifler")
    expect(sayfa.get_by_text(no).first).to_be_visible()


# ---------- §11.5 Geri bildirim ve son eşitleme yönetimde ----------

def test_geri_bildirim_yonetimde_gorunur_ve_son_esitleme(sayfa: Page, yonetici):
    metin = f"QATest geri bildirim {time.strftime('%Y%m%d%H%M%S')}"
    sayfa.goto("/tr/")
    sayfa.locator("#gb-dugme").click()
    pencere = sayfa.locator("#gb-pencere")
    expect(pencere).to_be_visible()
    pencere.locator('[name="metin"]').fill(metin)
    pencere.locator('[name="isim"]').fill("QATestUser")
    pencere.locator('[type="submit"]').click()
    expect(e2e(sayfa, "gb-tamam")).to_be_visible()

    yonetime_gir(sayfa, yonetici)
    sayfa.goto("/yonetim")
    expect(e2e(sayfa, "son-esitleme")).to_have_text(re.compile(r"\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2}"))
    sayfa.goto("/yonetim/geri-bildirimler")
    expect(sayfa.get_by_text(metin).first).to_be_visible()


# ---------- TR/EN geçişi ----------

def test_tr_en_gecisi_yolu_ve_tr_fiyatini_korur(sayfa: Page):
    yol = sepete_eklenebilir_urun_ac(sayfa, "tr")
    urun_kimligi = re.search(r"/urun/(\d+)", yol).group(1)
    tercih_sec(sayfa, "dil", "en", re.compile(rf"/en/urun/{urun_kimligi}"))
    expect(sayfa.locator("html")).to_have_attribute("lang", "en")
    # Ülke dilden bağımsız: EN arayüzdeki Türkiye ziyaretçisi yine TRY ve KDV dahil görür
    expect(e2e(sayfa, "fiyat-ana").first).to_have_attribute("data-para", "TRY")
    tercih_sec(sayfa, "dil", "tr", re.compile(rf"/tr/urun/{urun_kimligi}"))
    expect(sayfa.locator("html")).to_have_attribute("lang", "tr")


# ---------- §11.7 güvenlik: CSP, satır içi script/stil yok, demo bandı ----------

@pytest.mark.parametrize("yol", KONTROL_SAYFALARI)
def test_guvenlik_basliklari_ve_satir_ici_kod_yok(sayfa: Page, yol: str):
    yanit = sayfa.goto(yol)
    assert yanit is not None and yanit.status == 200, f"{yol}: {yanit and yanit.status}"
    basliklar = yanit.all_headers()
    assert "script-src 'self'" in basliklar.get("content-security-policy", "")
    assert basliklar.get("x-robots-tag") == "noindex, nofollow"
    # Satır içi script yasak; tek istisna JSON-LD veri bloğu (type="application/ld+json")
    assert sayfa.evaluate(
        "() => [...document.scripts].filter(s => !s.src && s.type !== 'application/ld+json').length") == 0, "satır içi <script> var"
    assert sayfa.evaluate("() => document.querySelectorAll('[style]').length") == 0, "style=\"\" özniteliği var"
    expect(sayfa.locator(".demo-bandi")).to_be_visible()


# ---------- 360 px mobil ekran görüntüleri ----------

@pytest.mark.parametrize("yol", KONTROL_SAYFALARI)
def test_mobil_360_ekran_goruntusu_ve_yatay_tasma_yok(mobil_sayfa: Page, ekran_klasoru, yol: str):
    yanit = mobil_sayfa.goto(yol)
    assert yanit is not None and yanit.status == 200
    mobil_sayfa.wait_for_load_state("networkidle")
    ad = re.sub(r"[^a-z0-9]+", "-", yol.lower()).strip("-") or "kok"
    mobil_sayfa.screenshot(path=str(ekran_klasoru / f"{ad}-360.png"), full_page=True)
    genislik = mobil_sayfa.evaluate("() => document.documentElement.scrollWidth")
    assert genislik <= 360, f"{yol}: yatay taşma ({genislik}px)"


def test_mobil_360_urun_ve_sepet(mobil_sayfa: Page, ekran_klasoru):
    sepete_eklenebilir_urun_ac(mobil_sayfa, "tr")
    mobil_sayfa.screenshot(path=str(ekran_klasoru / "urun-360.png"), full_page=True)
    assert mobil_sayfa.evaluate("() => document.documentElement.scrollWidth") <= 360
    sepete_ekle_ve_sepete_git(mobil_sayfa, "tr")
    mobil_sayfa.screenshot(path=str(ekran_klasoru / "sepet-360.png"), full_page=True)
    assert mobil_sayfa.evaluate("() => document.documentElement.scrollWidth") <= 360


# ---------- G2: SEO / LLM uyumu (demo modunda; üretimde farklı olanlar birim testlerde) ----------

def test_robots_llms_ve_sitemap_dosyalari(sayfa: Page):
    robots = sayfa.request.get("/robots.txt")
    assert robots.status == 200
    satirlar = robots.text().splitlines()
    assert satirlar[:2] == ["User-agent: *", "Disallow: /"] and "Disallow: /_iz/" in satirlar
    llms = sayfa.request.get("/llms.txt")
    assert llms.status == 200 and llms.text().startswith("# Ceylan Robot")
    assert llms.headers["content-type"].startswith("text/plain")
    indeks = sayfa.request.get("/sitemap.xml")
    assert indeks.status == 200 and indeks.headers["content-type"].startswith("application/xml")
    assert "<sitemapindex" in indeks.text() and "/sitemap-urunler-1.xml" in indeks.text()
    urunler = sayfa.request.get("/sitemap-urunler-1.xml")
    assert urunler.status == 200 and 'hreflang="x-default"' in urunler.text()


def test_urun_sayfasinda_json_ld_canonical_ve_gizli_iz(sayfa: Page):
    yol = sepete_eklenebilir_urun_ac(sayfa, "tr")
    ld = sayfa.evaluate("() => [...document.querySelectorAll('script[type=\"application/ld+json\"]')].map(s => JSON.parse(s.textContent))")
    assert len(ld) == 1 and ld[0]["@type"] == "Product" and ld[0]["sku"]
    # G2 düzeltme turu kararı (progress.md, e48aadc): Offer fiyatı sayfada ziyaretçiye birincil gösterilen fiyattır;
    # anonim TR ziyaretçide TRY, KDV dahil. JSON-LD görünen fiyatla aynı para birimi ve KDV durumunu taşımalı.
    fiyat = e2e(sayfa, "fiyat-ana").first
    teklif = ld[0]["offers"]
    assert teklif["priceCurrency"] == fiyat.get_attribute("data-para") == "TRY"
    assert teklif["priceSpecification"]["valueAddedTaxIncluded"] is (fiyat.get_attribute("data-kdv") == "dahil")
    gorunen = re.sub(r"\D", "", fiyat.locator(".tutar").inner_text())
    assert re.sub(r"\D", "", teklif["price"]) == gorunen, f"JSON-LD {teklif['price']} ≠ sayfa {gorunen}"
    canonical = sayfa.locator('link[rel="canonical"]').get_attribute("href")
    assert canonical.endswith(yol) and canonical.startswith("http")
    expect(sayfa.locator('meta[name="robots"]')).to_have_attribute("content", "noindex,nofollow")  # demo
    gizli = sayfa.locator("a.gizli-iz")
    assert gizli.get_attribute("aria-hidden") == "true" and gizli.get_attribute("tabindex") == "-1"
    expect(gizli).not_to_be_in_viewport()
    expect(sayfa.locator("html")).to_have_attribute("lang", "tr")



# ---------- G3j madde 9/10 (inceleme M-1, M-7): filtre sütunu ve mobil araç çubuğu yerleşimi ----------

_GORUNUR = """e => { const b = e.getBoundingClientRect(); const st = getComputedStyle(e);
  return st.display !== 'none' && st.visibility !== 'hidden' && b.width > 1 && b.height > 1
         && b.top >= 0 && b.bottom <= innerHeight; }"""


@pytest.mark.parametrize("yol", ["/tr/urunler", "/en/urunler", "/tr/ara?q=servo+motor"])
def test_g3j_filtre_sutunu_1366_ilk_ekranda_uygula(sayfa: Page, yol: str):
    sayfa.set_viewport_size({"width": 1366, "height": 768})
    sayfa.goto(yol)
    sayfa.wait_for_load_state("networkidle")
    dugmeler = sayfa.locator('aside.yan form.filtre button[type="submit"]')
    assert any(dugmeler.nth(i).evaluate(_GORUNUR) for i in range(dugmeler.count())), "ilk ekranda Uygula yok"
    yukseklik = sayfa.evaluate("() => document.querySelector('aside.yan').scrollHeight")
    assert yukseklik <= 1.5 * 768, f"filtre sütunu {yukseklik} px (> 1,5 ekran)"
    # varsayılan: tip/stok/marka/fiyat/durum açık (G3k madde 10), kategori kapalı
    for ad, acik in (("tip", True), ("stok", True), ("marka", True), ("fiyat", True), ("durum", True),
                     ("kategori", False)):
        grup = sayfa.locator(f'details.faset-grup[data-grup="{ad}"]')
        if grup.count():
            assert grup.evaluate("e => e.open") is acik, ad


@pytest.mark.parametrize("boyut", [(1366, 768), (1440, 900)])
def test_g3k_durum_grubu_acik_belirtilmemis_ilk_ekranda(sayfa: Page, boyut):
    """G3k madde 10: Durum grubu açık, "Belirtilmemiş" sütunun iç kaydırması olmadan görünür; sütun ≤ 1,5 ekran."""
    sayfa.set_viewport_size({"width": boyut[0], "height": boyut[1]})
    sayfa.goto("/tr/urunler")
    sayfa.wait_for_load_state("networkidle")
    assert sayfa.locator('details.faset-grup[data-grup="durum"]').evaluate("e => e.open")
    secenek = sayfa.locator('aside.yan input[name="durum"][value="belirtilmemis"]')
    assert secenek.count() == 1, "Belirtilmemiş seçeneği yok"            # fix 1 m-9: koşulsuz denetim
    assert secenek.locator("xpath=..").evaluate(_GORUNUR), "Belirtilmemiş ilk ekranda değil"
    assert sayfa.evaluate("() => document.querySelector('aside.yan').scrollHeight") <= 1.5 * boyut[1]
    assert sayfa.locator(".hizli-cip", has_text="Test edilmiş").count() == 0


def test_g3j_mobil_360_arac_cubugu_ve_cekmece(mobil_sayfa: Page):
    mobil_sayfa.goto("/tr/urunler")
    mobil_sayfa.wait_for_load_state("networkidle")
    for secici in ('label[for="sira"]', 'label[for="adet"]'):
        assert mobil_sayfa.locator(secici).evaluate(_GORUNUR), f"{secici} görünmüyor"
    dugmeler = mobil_sayfa.locator(".liste-ust .fiyat-secici-dugme")
    kutular = [dugmeler.nth(i).bounding_box() for i in range(dugmeler.count())]
    assert len(kutular) == 2 and kutular[0]["y"] == kutular[1]["y"] and all(k["height"] <= 44 for k in kutular)
    ozet = mobil_sayfa.locator(".cekmece > summary")
    ozet.click()
    uygula = mobil_sayfa.locator('.cekmece-ic form.filtre .dugmeler button[type="submit"]')
    panel = mobil_sayfa.locator(".cekmece[open] > .cekmece-ic").bounding_box()
    # Uygula ve Kapat panelin üstünde, yüzen "Filtrele" yerine "Kapat"
    assert uygula.evaluate(_GORUNUR) and uygula.bounding_box()["y"] < panel["y"] + 60
    assert ozet.inner_text().strip().startswith("Kapat") and ozet.bounding_box()["y"] < panel["y"] + 60
    mobil_sayfa.locator(".cekmece-ic").evaluate("e => { e.scrollTop = 600; }")
    assert uygula.evaluate(_GORUNUR), "kaydırınca Uygula kayboldu"
    ozet.click()
    assert ozet.inner_text().strip().startswith("Filtrele")


# ---------- G3k madde 25: mobil dokunma hedefleri ve kategori şeridi ----------

def test_g3k_mobil_360_dokunma_hedefleri(mobil_sayfa: Page):
    mobil_sayfa.goto("/tr/")
    mobil_sayfa.wait_for_load_state("networkidle")
    serit = mobil_sayfa.evaluate("() => { const u = document.querySelector('.kategori-serit ul');"
                                 " return u ? u.scrollWidth - u.clientWidth : 0; }")
    assert serit <= 0, f"kategori şeridi {serit} px taşıyor"
    mobil_sayfa.goto("/tr/urunler")
    mobil_sayfa.wait_for_load_state("networkidle")
    mobil_sayfa.locator(".cekmece > summary").click()
    kutular = mobil_sayfa.evaluate("""() => [...document.querySelectorAll('.cekmece-ic input[type=checkbox]')]
        .filter(e => e.offsetParent !== null).map(e => { const b = e.getBoundingClientRect();
          return [b.width, b.height, e.closest('label').getBoundingClientRect().height]; })""")
    assert kutular and all(w >= 24 and h >= 24 and s >= 32 for w, h, s in kutular), kutular
