"""G3b (Ö3 madde 10–16 + kategori silüeti): ürün sayfası ve güven."""
import re
from html import unescape
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from app.web.baglam import yer_tutucu
from tests.conftest import csrf_al, istemci_db, sayfa_denetle
from tests.test_web_katalog import katalog  # noqa: F401 — fixture
from tests.test_web_sepet_odeme import _giris, _kur, _musteri, _sepete_ekle, _urun, db  # noqa: F401

YT_KLASOR = Path(__file__).resolve().parent.parent / "app" / "web" / "statik" / "yer-tutucu"
SILUETLER = ("robot", "pozisyoner", "kontrol", "robotik-parca", "slider", "reduktor", "guc", "elektrik",
             "mekanik", "genel")
# tasarım belgesi §1 tokenlarının sabit değerleri (SVG'de var() çalışmaz)
TOKEN_RENKLERI = {"#f4f1e9", "#ffffff", "#ebe7db", "#1d231f", "#5b645d", "#303a32", "#4f5e48", "#687860",
                  "#a83c29", "#8f3222", "#c9c4b4", "#7f857b", "none"}


def _tercih(istemci, ulke, sonraki="/tr/"):
    csrf = csrf_al(istemci, "/tr/")
    r = istemci.post("/tercih", data={"ulke": ulke, "sonraki": sonraki, "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303


# ---------- A. kategori silüeti ----------

@pytest.mark.parametrize(("kok", "dosya"), [
    ("Endüstriyel Robotlar", "robot"), ("Pozisyonerler", "pozisyoner"), ("Robot Kontrol Üniteleri", "kontrol"),
    ("Robotik Parçaları", "robotik-parca"), ("Slider", "slider"), ("ABB REDÜKTÖR", "reduktor"),
    ("GÜÇ KAYNAĞI", "guc"), ("Elektrik ve Elektronik", "elektrik"), ("Mekanik", "mekanik"),
    ("Bilinmeyen Kök", "genel"), ("", "genel"), (None, "genel"),
])
def test_g3b_yer_tutucu_kok_kategoriye_gore(kok, dosya):
    assert yer_tutucu(kok) == f"/statik/yer-tutucu/{dosya}.svg"


@pytest.mark.parametrize("ad", SILUETLER)
def test_g3b_siluet_dosyalari_guvenli_ve_tutarli(istemci, ad):
    yanit = istemci.get(f"/statik/yer-tutucu/{ad}.svg")
    assert yanit.status_code == 200 and yanit.headers["content-type"].startswith("image/svg+xml")
    metin = yanit.text
    for yasak in ("<script", "href", "url(", "<foreignObject", "<image", "on", "var("):
        if yasak == "on":
            assert not re.search(r"\son\w+\s*=", metin), ad
        else:
            assert yasak not in metin, (ad, yasak)
    assert re.findall(r"https?://[^\"']+", metin) == ["http://www.w3.org/2000/svg"]
    kok = ET.fromstring(metin)
    assert kok.get("viewBox") == "0 0 96 72" and kok.get("role") == "img" and kok.get("aria-hidden") is None
    renkler = set(re.findall(r'(?:fill|stroke)="([^"]+)"', metin))
    assert renkler <= TOKEN_RENKLERI, (ad, renkler - TOKEN_RENKLERI)
    assert set(re.findall(r'stroke-width="([^"]+)"', metin)) == {"1.5"}, ad


def test_g3b_temsili_gorsel_ibaresi(istemci, katalog):
    html = sayfa_denetle(istemci.get(f"/tr/urun/{katalog['robot']}"))
    assert 'src="/statik/yer-tutucu/robot.svg"' in html
    assert re.search(r'<p class="temsili-gorsel" data-temsili>Temsili görsel</p>', html)
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET gorsel_url = ? WHERE id = ?", ("gorsel:" + "a" * 32 + ".webp", katalog["robot"]))
    html = istemci.get(f"/tr/urun/{katalog['robot']}").text
    # gerçek görsel: ibare gizli (yüklenemezse site.js yer tutucuya geçip ibareyi açar)
    assert re.search(r'<p class="temsili-gorsel" data-temsili hidden>Temsili görsel</p>', html)
    assert "Representative image" in istemci.get(f"/en/urun/{katalog['role']}").text


def test_g3b_ana_sayfa_kartinda_temsili_gorsel_ve_garanti(istemci, katalog):
    html = istemci.get("/tr/").text
    kart = html[html.index('<article class="kart"'):]
    kart = kart[:kart.index("</article>")]
    assert "Temsili görsel" in kart
    # G3e madde 4: misafir metni; G3n madde 5: ürün sayfasıyla aynı iade satırları
    assert "12 ay garanti" not in kart and "Bireysel alım: 14 gün cayma hakkı (temsili)" in kart
    assert re.search(r'</a>\s*<p class="temsili-gorsel" data-temsili>Temsili görsel</p>', kart)   # aria-hidden bağlantı dışında
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET durum_kodu = 'yenilenmis' WHERE id = ?", (katalog["role"],))
    html = istemci.get("/tr/").text
    kart = html[html.index('<article class="kart"'):]
    # G3g inceleme turu 1 (kontrolcü kararı): "12 ay garanti" yerine duruma göre garanti özeti + garanti sayfası çapası
    kart = kart[:kart.index("</article>")]
    assert "12 ay garanti" not in kart and "Test edilmiş ürün garantisi" in kart   # G3l madde 18 metni
    assert 'href="/tr/yasal/garanti#durum-ikinci_el_test_edildi"' in kart


# ---------- madde 11: teslim süresi ----------

def test_g3b_teslim_suresi_urun_ve_listede(istemci, katalog):
    html = istemci.get(f"/tr/urun/{katalog['role']}").text
    # G3n madde 6: "Kargoya veriliş: 1–2 iş günü · varış: <aralık> (temsili)" (ürün, liste, sipariş aynı)
    assert 'data-e2e="teslim-suresi"' in html and "Kargoya veriliş: 1–2 iş günü · varış: " in html
    html = istemci.get(f"/tr/urun/{katalog['stoksuz']}").text
    assert "Tedarik süresi siparişten sonra bildirilir" in html and "Kargoya veriliş" not in html  # G3l madde 7
    liste = istemci.get(f"/tr/kategori/{katalog['kontrol']}").text
    # G3n madde 6: listede de ürün sayfasıyla aynı metin (G3h madde 13'teki kısa "Varış: …" kalktı)
    assert "Kargoya veriliş: 1–2 iş günü · varış: " in liste and "Tedarik süresi siparişten sonra bildirilir" in liste
    en = istemci.get(f"/en/urun/{katalog['role']}", headers={"Accept-Language": "tr-TR"}).text
    assert "Dispatch: 1–2 business days · arrival: " in en and "(indicative)" in en


# ---------- madde 12: KDV dahil + hariç ----------

def test_g3b_kdv_dahil_ve_haric_birlikte(istemci, katalog):
    # anonim TR (bireysel): ana TRY KDV dahil 120 € × 35,20 = 4.224,00 ₺ + %20 = 5.068,80 ₺; ikinci satırda KDV hariç
    html = istemci.get(f"/tr/urun/{katalog['role']}").text
    assert '<span class="tutar">5.068,80 ₺</span>' in html
    assert re.search(r'data-e2e="fiyat-kdv-karsilik"[^>]*>KDV hariç: 4\.224,00 ₺<', html)
    # yurt dışı: KDV uygulanmaz
    _tercih(istemci, "DE")
    html = istemci.get(f"/tr/urun/{katalog['role']}").text
    assert re.search(r'data-e2e="fiyat-kdv-karsilik"[^>]*>KDV uygulanmaz \(ihracat\)<', html)


def test_g3b_kdv_karsiligi_ozellik_testi():
    """M-6: ana fiyat ile KDV karşılığı tek hesaptan: dahil − hariç = yuvarla(hariç × oran / 100)."""
    import random
    from decimal import Decimal

    from app.fiyat.kurallar import Baglam, MusteriTipi, birim_fiyat_gosterimi, kdv_karsiligi
    from app.para import yuvarla

    rnd = random.Random(3)
    for _ in range(300):
        net = Decimal(rnd.randint(1, 5_000_000)) / 100
        oran = Decimal(rnd.choice([1, 10, 18, 20]))
        kur = Decimal(rnd.randint(300_000, 600_000)) / 10_000
        for b in (Baglam(MusteriTipi.BIREYSEL, "TR"), Baglam(MusteriTipi.KURUMSAL, "TR")):
            g = birim_fiyat_gosterimi(net, oran, b, kur)
            tutar, para, dahil = kdv_karsiligi(net, oran, b, kur, g)
            assert para == g.ana_para and dahil != g.kdv_dahil
            haric, dahil_t = (g.ana_tutar, tutar) if dahil else (tutar, g.ana_tutar)
            assert dahil_t - haric == yuvarla(haric * oran / 100)


def test_g3b_kdv_karsiligi_kurumsal_ve_kursuz():
    from decimal import Decimal

    from app.fiyat.kurallar import Baglam, MusteriTipi, birim_fiyat_gosterimi, kdv_karsiligi

    net, kdv = Decimal("100.00"), Decimal("20")
    b = Baglam(MusteriTipi.KURUMSAL, "TR")
    g = birim_fiyat_gosterimi(net, kdv, b, Decimal("35"))
    assert kdv_karsiligi(net, kdv, b, Decimal("35"), g) == (Decimal("120.00"), "EUR", True)
    b = Baglam(MusteriTipi.BIREYSEL, "TR")
    g = birim_fiyat_gosterimi(net, kdv, b, None)       # kur yok: EUR net ana fiyat
    assert kdv_karsiligi(net, kdv, b, None, g) == (Decimal("120.00"), "EUR", True)
    g = birim_fiyat_gosterimi(net, kdv, b, Decimal("35.20"))
    assert kdv_karsiligi(net, kdv, b, Decimal("35.20"), g) == (Decimal("3520.00"), "TRY", False)
    b = Baglam(MusteriTipi.YURTDISI, "DE")
    assert kdv_karsiligi(net, kdv, b, None, birim_fiyat_gosterimi(net, kdv, b, None)) is None


# ---------- madde 13: durum rozeti ----------

def test_g3b_durum_belirtilmemis_notr_rozet(istemci, katalog):
    html = istemci.get(f"/tr/urun/{katalog['role']}").text
    # G3e madde 6: "Teklifle teyit" -> "Durum: belirtilmemiş" (+ teyit ipucu)
    assert '<span class="rozet rozet-notr" data-e2e="durum-teyit">Durum: belirtilmemiş</span>' in html
    assert "rozet-durum" not in html and "teklifle teyit" not in html.lower()
    liste = istemci.get(f"/tr/kategori/{katalog['kontrol']}").text
    assert "Belirtilmemiş" in liste and "Teklifle teyit" not in liste
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET durum_kodu = 'ikinci_el_oldugu_gibi' WHERE id = ?", (katalog["role"],))
    html = istemci.get(f"/tr/urun/{katalog['role']}").text
    assert "rozet-notr" not in html and '<span class="rozet rozet-durum">2. el – olduğu gibi</span>' in html


# ---------- madde 14: teknik özellikler ----------

def test_g3b_teknik_ozellikler_tablosu(istemci, katalog):
    html = istemci.get(f"/tr/urun/{katalog['role']}").text
    assert "Teknik veri sayfası (datasheet) talep üzerine." in html
    assert f'href="/tr/teklif?urun_id={katalog["role"]}"' in html
    assert 'data-e2e="teknik-tablo"' not in html
    with istemci_db(istemci) as con:
        con.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)", (
            katalog["role"],
            '{"ozellikler":[["Gerilim","24 V"],["Not","<b>kalın</b>"]],"bolumler":[["Bilgi","Satır 1\\nSatır 2"]]}'))
    html = sayfa_denetle(istemci.get(f"/tr/urun/{katalog['role']}"))
    tablo = html[html.index('data-e2e="teknik-tablo"'):]
    tablo = tablo[:tablo.index("</table>")]
    assert '<th scope="row">Gerilim</th><td>24 V</td>' in tablo
    assert "&lt;b&gt;kalın&lt;/b&gt;" in tablo and "<b>" not in tablo
    assert '<h3 class="teknik-bolum-baslik">Bilgi</h3>' in html
    assert '<p class="teknik-bolum-metin">Satır 1\nSatır 2</p>' in html
    assert "Teknik veri sayfası (datasheet) talep üzerine." not in html


# ---------- madde 15: garanti/test satırı ----------

@pytest.mark.parametrize(("durum", "ornek", "garantili"), [
    ("ikinci_el_test_edildi", 0, True), ("yenilenmis", 0, True), ("yeni", 0, False), ("ikinci_el", 0, False),
    ("ikinci_el_oldugu_gibi", 0, False), ("belirtilmemis", 0, False), ("ikinci_el_test_edildi", 1, False),
])
def test_g3b_garanti_satiri_yalniz_test_edilmis_ya_da_yenilenmis(istemci, katalog, durum, ornek, garantili):
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET durum_kodu = ?, durum_ornek = ? WHERE id = ?", (durum, ornek, katalog["role"]))
    html = istemci.get(f"/tr/urun/{katalog['role']}").text
    satir = re.search(r'<p class="garanti-satiri" data-e2e="garanti-satiri">(.*?)</p>', html, re.S).group(1)
    # G3g inceleme turu 1: güven satırında süre iddiası yok; garanti özeti durum satırının altında (garanti-ozeti)
    assert "12 ay garanti" not in html and "12-month" not in istemci.get(f"/en/urun/{katalog['role']}").text
    ozet = re.search(r'data-e2e="garanti-ozeti">(.*?)</p>', html, re.S).group(1)
    assert ("test edilmiş ürün garantisi" in ozet.lower()) == (garantili or durum == "ikinci_el_test_edildi")
    # G3e madde 4: misafirde iade metni bireysel + kurumsal birlikte
    assert "Test edilmiştir" not in satir
    # G3i madde 13: misafirde iki satır (bireysel + ticari alım kuralları)
    assert '<a href="/tr/yasal/iade">Bireysel alım: 14 gün cayma hakkı (temsili)</a>' in satir
    # G3l madde 18: "olduğu gibi" üründe ticari satır garantiye dayanmaz; G3m madde 7-8: aynı kalıp ("Ticari alım:
    # cayma hakkı yok. …"), belirtilmemiş durumda ücretsiz iptal istisnası aynı cümlede
    beklenen = {"ikinci_el_oldugu_gibi": "Ticari alım: cayma hakkı yok. Olduğu gibi satılır: garanti yok; açık ayıplar "
                                         "teslimden itibaren 2 gün içinde yazılı bildirilir.",
                "belirtilmemis": "Ticari alım: cayma hakkı yok. İstisna: durum belirtilmemiş ürünlerde"}.get(
        durum, "Ticari alım: cayma hakkı yok; açık ayıplar teslimden itibaren 2 gün içinde yazılı bildirilir")
    assert beklenen in satir


# ---------- madde 16: ülkeye göre kargo metni, ülke tercihi ----------

def test_g3b_ulke_tr_disi_ihracat_metni(istemci, katalog):
    html = istemci.get(f"/tr/urun/{katalog['role']}").text
    assert "Kargo: TR 15 € + KDV (temsili)" in html and "İhracat: KDV'siz" not in html
    _tercih(istemci, "DE")
    html = unescape(istemci.get(f"/tr/urun/{katalog['role']}").text)
    # G3e madde 12: ihracat KDV metni (hukuk-notlari.md) + DAP navlun
    assert "Türkiye KDV'si uygulanmaz (ihracat, KDVK md. 11/1-a)" in html and "ters ibraz" not in html
    assert "Yurt dışı: DAP teslim · Navlun teklifle; bu ödemeye dahil değildir." in html   # G3m madde 6
    assert "TR 15 € + KDV" not in html
    # ülke oturumda (ve çerezde) hatırlanır: başka sayfada da seçili
    assert '<option value="DE" selected>' in istemci.get("/tr/").text
    en = unescape(istemci.get(f"/en/urun/{katalog['role']}").text)
    assert "Turkish VAT does not apply (export, Turkish VAT Law Art. 11/1-a)" in en and "reverse charge" not in en.lower()


def test_g3b_odemede_teslim_ulkesi_tercihten(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-ULKE", ad="Ülke Ürünü", fiyat="100.00")
    _musteri(db, eposta="ulke@ornek.test")
    _giris(istemci, "ulke@ornek.test")
    _tercih(istemci, "AT")
    assert _sepete_ekle(istemci, uid).status_code == 303
    html = istemci.get("/tr/odeme").text
    secim = html[html.index('id="teslimat_ulke"'):]
    secim = secim[:secim.index("</select>")]
    assert '<option value="AT" selected>' in secim
    # M-7: ürün sayfası da aynı ülkeyle fiyatlar (ihracat: KDV uygulanmaz) ve üst bant AT gösterir
    urun = istemci.get(f"/tr/urun/{uid}").text
    assert "KDV uygulanmaz (ihracat)" in urun and '<option value="AT" selected>' in urun


def test_g3b_giris_oncesi_ulke_secimi_giriste_silinir(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-ULKE3", ad="Ülke Ürünü 3", fiyat="100.00")
    _musteri(db, eposta="ulke3@ornek.test")
    _tercih(istemci, "AT")
    _giris(istemci, "ulke3@ornek.test")
    assert _sepete_ekle(istemci, uid).status_code == 303
    html = istemci.get("/tr/odeme").text
    secim = html[html.index('id="teslimat_ulke"'):]
    assert '<option value="TR" selected>' in secim[:secim.index("</select>")]
    assert "KDV uygulanmaz" not in istemci.get(f"/tr/urun/{uid}").text


def test_g3b_odemede_tercih_yoksa_musteri_ulkesi(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-ULKE2", ad="Ülke Ürünü 2", fiyat="100.00")
    _musteri(db, eposta="ulke2@ornek.test")
    _giris(istemci, "ulke2@ornek.test")
    assert _sepete_ekle(istemci, uid).status_code == 303
    html = istemci.get("/tr/odeme").text
    secim = html[html.index('id="teslimat_ulke"'):]
    assert '<option value="TR" selected>' in secim[:secim.index("</select>")]


def test_g3b_kayit_ulkesi_tercihten(istemci):
    _tercih(istemci, "NL")
    html = istemci.get("/tr/kayit").text
    secim = html[html.index('id="a-ulke"'):]
    assert '<option value="NL" selected>' in secim[:secim.index("</select>")]


# ---------- madde 10: mobil ilk ekran (yapı; ölçüm tarayıcıda, rapor) ----------

def test_g3b_kirinti_yolu_mobilde_tek_satir_ust_kategori(istemci, katalog):
    html = istemci.get(f"/tr/urun/{katalog['robot']}").text
    iz = html[html.index('<nav class="iz"'):]
    iz = iz[:iz.index("</nav>")]
    # son kategori (bir üst düzey) işaretli; CSS dar ekranda yalnız onu "‹ <ad>" olarak gösterir
    assert re.search(rf'<li class="iz-ust"><a href="/tr/kategori/{katalog["krc4"]}">KR C4</a></li>', iz)
    css = (Path(__file__).resolve().parent.parent / "app" / "web" / "statik" / "site.css").read_text(encoding="utf-8")
    assert ".iz li:not(.iz-ust)" in css


# ---------- düzeltme turu 1 ----------

def test_g3b_teklif_urununde_teslim_satiri_teklifle(istemci, katalog):
    """I-4: teklif zorunlu üründe stok olsa da kargo süresi vaat edilmez (detay, liste, kart aynı fonksiyon)."""
    html = istemci.get(f"/tr/urun/{katalog['robot']}").text
    assert re.search(r'data-e2e="teslim-suresi">.*?Teslim ve fiyat: teklifle', html, re.S)
    assert "1–2 iş günü" not in html
    liste = istemci.get(f"/tr/kategori/{katalog['rob']}").text
    assert "Teslim ve fiyat: teklifle" in liste and "1–2 iş günü" not in liste


def test_g3b_ikinci_el_kodu_etiket_ve_faset(istemci, katalog):
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET durum_kodu = 'ikinci_el' WHERE id = ?", (katalog["role"],))
    html = istemci.get(f"/tr/urun/{katalog['role']}").text
    assert '<span class="rozet rozet-durum" title="2. el: kullanılmış, test durumu kaynakta belirtilmemiş">2. el</span>' \
        in html   # G3m madde 9: rozette kısa açıklama
    assert "Durum bilgisi" not in html        # G3e madde 7: örnek değerli durum bilgisi bölümü kaldırıldı
    liste = istemci.get(f"/tr/kategori/{katalog['kontrol']}").text
    assert 'value="ikinci_el"' in liste
    assert '<span class="rozet rozet-durum" title="Used: previously used, test status not recorded in the source">Used</span>' in istemci.get(f"/en/urun/{katalog['role']}").text


def test_g3b_yer_tutucu_alt_metni_temsili(istemci, katalog):
    html = istemci.get(f"/tr/urun/{katalog['robot']}").text
    assert 'alt="KUKA KRC5 KR 140 R3200-2 PA – 8301033800019 (temsili görsel)"' in html
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET gorsel_url = ? WHERE id = ?", ("gorsel:" + "a" * 32 + ".webp", katalog["robot"]))
    assert 'alt="KUKA KRC5 KR 140 R3200-2 PA – 8301033800019"' in istemci.get(f"/tr/urun/{katalog['robot']}").text


def test_g3b_kategori_metasinda_ornek_durum_yok(istemci, katalog):
    """I-6: örnek (durum_ornek=1) durumlar kategori meta'sına girmez; gerçek durum girer."""
    from html import unescape

    def meta():
        html = istemci.get(f"/tr/kategori/{katalog['kontrol']}").text
        return unescape(re.search(r'<meta name="description" content="([^"]*)"', html).group(1))

    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET durum_kodu = 'yeni', durum_ornek = 1 WHERE id = ?", (katalog["role"],))
    assert "durum:" not in meta() and "sıfır" not in meta()
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET durum_kodu = 'ikinci_el', durum_ornek = 0 WHERE id = ?", (katalog["stoksuz"],))
    assert "durum: 2. el." in meta() and "sıfır" not in meta()


def test_g3b_mobil_baslik_ve_geri_bildirim_kurallari():
    """I-7/I-8 CSS yapısı (ölçüm tarayıcıda, rapor): dar ekranda ince DEMO bandı, ürün sayfasında kategori şeridi
    gizli, logo 24 px; geri bildirim düğmesi küçük ve ürün sayfasında eylem formu düğmenin altına girmez."""
    css = (Path(__file__).resolve().parent.parent / "app" / "web" / "statik" / "site.css").read_text(encoding="utf-8")
    blok = css[css.index("/* G3b düzeltme turu 1: mobil başlık"):]
    assert "@media (max-width: 400px)" in blok and ".demo-uzun" in blok and "height: 24px" in blok
    assert "body:has(.urun-detay) .kategori-serit { display: none; }" in blok
    assert "#gb-dugme { position: static;" in blok      # G3g madde 20: düğme alt bilgide akışta, hiçbir eylemi örtmez


def test_g3b_demo_bandi_kisa_ve_uzun_metin(istemci):
    html = istemci.get("/tr/").text
    bant = html[html.index('class="demo-bandi"'):]
    bant = bant[:bant.index("</div>")]
    assert '<span class="demo-uzun">DEMO – gerçek satış ve ödeme yapılmaz</span>' in bant
    assert '<span class="demo-kisa" aria-hidden="true">DEMO</span>' in bant
