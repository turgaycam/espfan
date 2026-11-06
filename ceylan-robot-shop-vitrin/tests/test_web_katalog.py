import re
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.fiyat.kur import Kur, kur_kaydet
from app.katalog.indeks import indeksi_yeniden_kur
from tests.conftest import csrf_al, istemci_db, kategori_ekle, sayfa_denetle, urun_ekle


def _fiyat_blogu(html: str) -> str:
    eslesme = re.search(r'<div class="fiyat-blok">(.*?)</div>', html, re.S)
    assert eslesme, "fiyat bloğu yok"
    return eslesme.group(1)


@pytest.fixture
def katalog(istemci):
    with istemci_db(istemci) as con:
        elk = kategori_ekle(con, kaynak_id="k10", ad="Elektrik ve Elektronik", yol="10", seviye=0)
        kontrol = kategori_ekle(con, kaynak_id="k1018", ad="KONTROL SISTEMLERI", yol="10.18", seviye=1, ust_kaynak_id="k10")
        rob = kategori_ekle(con, kaynak_id="k12", ad="Endüstriyel Robotlar", yol="12", seviye=0)
        kuka = kategori_ekle(con, kaynak_id="k1241", ad="KUKA", yol="12.41", seviye=1, ust_kaynak_id="k12")
        krc4 = kategori_ekle(con, kaynak_id="k1241243", ad="KR C4", yol="12.41.243", seviye=2, ust_kaynak_id="k1241")
        role = urun_ekle(con, sku="RL-24", ad="RÖLE MODÜLÜ 24V", kok="Elektrik ve Elektronik", fiyat="120.00",
                         kategori_id=kontrol, stok=5)
        robot = urun_ekle(con, sku="8301033800019", ad="KUKA KRC5 KR 140 R3200-2 PA", kok="Endüstriyel Robotlar",
                          fiyat="32000.00", teklif=True, kategori_id=krc4, stok=1, uretici_kodu="KRC5-140")
        stoksuz = urun_ekle(con, sku="SG-1", ad="SİGORTA KUTUSU", kok="Elektrik ve Elektronik", fiyat="40.00",
                            kategori_id=kontrol, stok=0)
        pasif = urun_ekle(con, sku="PS-1", ad="ESKİ KART", kok="Elektrik ve Elektronik", fiyat="10.00",
                          kategori_id=kontrol, aktif=False)
        kur_kaydet(con, Kur(tarih=date(2026, 10, 12), eur_alis=Decimal("35.00"), eur_satis=Decimal("35.20")),
                   datetime(2026, 10, 12, 6, 0, tzinfo=UTC))
        indeksi_yeniden_kur(con)  # K6: urun_ekle zaten indeksler; pasif ürün indeks dışı kalır
    return {"elk": elk, "kontrol": kontrol, "rob": rob, "kuka": kuka, "krc4": krc4,
            "role": role, "robot": robot, "stoksuz": stoksuz, "pasif": pasif}


def test_ana_sayfa_kok_kategoriler(istemci, katalog):
    yanit = istemci.get("/tr/")
    assert yanit.status_code == 200
    html = sayfa_denetle(yanit)
    assert "Elektrik ve Elektronik" in html and "Endüstriyel Robotlar" in html
    assert f'href="/tr/kategori/{katalog["elk"]}"' in html
    assert "Robotlar için teklif alın" in html and 'href="/tr/teklif"' in html


def test_kok_adres_ana_sayfaya_gider(istemci, katalog):
    assert istemci.get("/").status_code == 200


def test_kategori_sayfasi_alt_kategori_urunlerini_listeler(istemci, katalog):
    html = sayfa_denetle(istemci.get(f"/tr/kategori/{katalog['elk']}"))
    assert "RÖLE MODÜLÜ 24V" in html and "SİGORTA KUTUSU" in html
    assert f'<a href="/tr/urun/{katalog["role"]}" data-e2e="urun-baglanti">' in html
    assert "KUKA KRC5" not in html
    assert "ESKİ KART" not in html
    assert "KONTROL SISTEMLERI" in html  # sol ağaç


def test_kategori_konum_izi(istemci, katalog):
    html = istemci.get(f"/tr/kategori/{katalog['krc4']}").text
    iz = re.search(r'<nav class="iz".*?</nav>', html, re.S).group(0)
    assert "Endüstriyel Robotlar" in iz and "KUKA" in iz and "KR C4" in iz


def test_filtreler(istemci, katalog):
    html = istemci.get(f"/tr/kategori/{katalog['elk']}?stokta=1").text
    assert "RÖLE MODÜLÜ 24V" in html and "SİGORTA KUTUSU" not in html
    # G3e madde 9: aralık görünen kipte (misafir TR: ₺, KDV dahil); SİGORTA 1.689,60 ₺, RÖLE 5.068,80 ₺
    html = istemci.get(f"/tr/kategori/{katalog['elk']}?fmax=2000").text
    assert "SİGORTA KUTUSU" in html and "RÖLE MODÜLÜ 24V" not in html


@pytest.mark.parametrize("q", ["role", "RÖLE", "röle", "Role", "rl-24"])
def test_arama_turkce(istemci, katalog, q):
    yanit = istemci.get("/tr/ara", params={"q": q})
    assert yanit.status_code == 200
    assert "RÖLE MODÜLÜ 24V" in sayfa_denetle(yanit)


def test_arama_sku(istemci, katalog):
    assert "KUKA KRC5 KR 140 R3200-2 PA" in istemci.get("/tr/ara", params={"q": "8301033800019"}).text


def test_bos_arama_ve_bos_sonuc_onerisi(istemci, katalog):
    yanit = istemci.get("/tr/ara", params={"q": "   "})
    assert yanit.status_code == 200
    assert "<h1>Tüm ürünler</h1>" in yanit.text          # G3a madde 8: boş arama -> tüm ürünler
    yanit = istemci.get("/tr/ara", params={"q": "yokboyleurun"})
    assert yanit.status_code == 200
    assert "Bu ölçütlere uyan ürün bulunamadı." in yanit.text
    assert 'href="/tr/teklif?kod=yokboyleurun"' in yanit.text   # G3a madde 9: aranan kod teklif formuna taşınır
    assert f'href="/tr/kategori/{katalog["elk"]}"' in yanit.text


def test_urun_teklif_zorunlu_kuka(istemci, katalog):
    yanit = istemci.get(f"/tr/urun/{katalog['robot']}")
    assert yanit.status_code == 200
    html = sayfa_denetle(yanit)
    assert "8301033800019" in html and "KRC5-140" in html
    assert f'href="/tr/teklif?urun_id={katalog["robot"]}"' in html
    assert 'action="/tr/sepet/ekle"' not in html
    assert 'data-e2e="teklif-iste"' in html and 'data-e2e="sepete-ekle"' not in html
    assert "Teklif iste" in html


def test_urun_normal_sepet_formu(istemci, katalog):
    html = sayfa_denetle(istemci.get(f"/tr/urun/{katalog['role']}"))
    assert 'action="/tr/sepet/ekle"' in html
    assert 'data-e2e="sepete-ekle"' in html and 'data-e2e="teklif-iste"' not in html
    assert f'name="urun_id" value="{katalog["role"]}"' in html
    assert 'name="adet"' in html and 'name="csrf"' in html
    # G3b: teknik föy bağlantısı ürünü teklif formuna taşır; G3n madde 11: fiyatlı üründe ikincil "Teklif iste" de
    assert html.count("?urun_id=") == 2 and f'teklif?urun_id={katalog["role"]}">Teklif formuyla isteyin' in html
    assert f'href="/tr/teklif?urun_id={katalog["role"]}" data-e2e="teklif-iste-ikincil"' in html
    assert "Stokta: 5 adet" in html


def test_stoksuz_urunde_tedarik_notu(istemci, katalog):
    html = istemci.get(f"/tr/urun/{katalog['stoksuz']}").text
    assert "Tedarik süresi siparişten sonra bildirilir" in html   # G3b madde 11 (G3l madde 7 metni)
    assert 'action="/tr/sepet/ekle"' in html


def test_fiyat_tr_misafir_try_kdv_dahil(istemci, katalog):
    blok = _fiyat_blogu(istemci.get(f"/tr/urun/{katalog['role']}").text)
    assert "₺" in blok and "KDV dahil" in blok
    assert 'data-e2e="fiyat-ana" data-para="TRY" data-kdv="dahil"' in blok
    assert 'data-e2e="fiyat-ikincil"' in blok
    assert "5.068,80 ₺" in blok  # 120 € × 35,20 = 4.224,00 + %20 KDV
    assert "35,2000 ₺" in blok   # kur satırı


def test_fiyat_de_ziyaretci_eur_kdv_haric(istemci, katalog):
    csrf = csrf_al(istemci, "/tr/")
    istemci.post("/tercih", data={"csrf": csrf, "ulke": "DE", "sonraki": "/tr/"}, follow_redirects=False)
    blok = _fiyat_blogu(istemci.get(f"/tr/urun/{katalog['role']}").text)
    assert "€" in blok and "120,00 €" in blok
    assert 'data-para="EUR" data-kdv="haric"' in blok
    assert "KDV hariç" in blok and "KDV dahil" not in blok  # K3: KDV'siz EUR gösterimi açıkça yazılır
    assert "₺" not in blok and 'data-e2e="fiyat-ikincil"' not in blok


def test_temsili_rozet(istemci, katalog):
    blok = _fiyat_blogu(istemci.get(f"/tr/urun/{katalog['role']}").text)
    assert 'class="rozet rozet-temsili"' in blok and "Temsili fiyat" in blok
    assert blok.index("Temsili fiyat") < blok.index('class="tutar"')


def test_durum_rozeti_yalniz_belirtilmisse(istemci, katalog):
    assert "rozet-durum" not in istemci.get(f"/tr/urun/{katalog['role']}").text
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET durum_kodu = 'ikinci_el_test_edildi', durum_ornek = 1 WHERE id = ?",
                    (katalog["role"],))
    html = istemci.get(f"/tr/urun/{katalog['role']}").text
    assert ('<span class="rozet rozet-durum" title="Test edilmiş: satıştan önce test edildi">2. el – test edildi</span>'
            in html)   # G3m madde 9: rozette kısa açıklama
    assert '<span class="rozet rozet-ornek" title="demo için elle girilmiş durum kaydı">demo kaydı</span>' in html


def test_yer_tutucu_gorsel(istemci, katalog):
    html = istemci.get(f"/tr/urun/{katalog['robot']}").text
    assert 'src="/statik/yer-tutucu/robot.svg"' in html


@pytest.mark.parametrize("yol_sablonu", [
    "/tr/urun/{pasif}", "/tr/urun/999999", "/tr/urun/abc", "/tr/kategori/999999",
    "/tr/kategori/99999999999999999999", "/tr/urun/99999999999999999999", "/de/urun/{role}",
])
def test_bulunamayanlar_404(istemci, katalog, yol_sablonu):
    yanit = istemci.get(yol_sablonu.format(**katalog))
    assert yanit.status_code == 404
    sayfa_denetle(yanit)


@pytest.mark.parametrize("sorgu", [
    "fmin=x", "fmax=abc", "fmin=-5", "fmin=NaN", "fmax=Infinity", "fmin=1e999",
    "sayfa=-1", "sayfa=abc", "sayfa=0", "sayfa=99999", "sayfa=1e3",
    "sira=zzz", "stokta=evet", "fmin=200&fmax=10",
])
def test_bozuk_sorgu_parametreleri(istemci, katalog, sorgu):
    yanit = istemci.get(f"/tr/kategori/{katalog['elk']}?{sorgu}")
    assert yanit.status_code == 200, sorgu
    sayfa_denetle(yanit)


@pytest.mark.parametrize("q", ['"', "*", "AND", "röle OR", "x" * 500, "\u0000abc", "(", "NEAR("])
def test_bozuk_arama_sorgulari(istemci, katalog, q):
    yanit = istemci.get("/tr/ara", params={"q": q, "sayfa": "-3"})
    assert yanit.status_code == 200, q


def test_en_arayuz_ingilizce(istemci, katalog):
    html = sayfa_denetle(istemci.get("/en/"))
    assert '<html lang="en">' in html
    assert "Categories" in html and "Get a quote for robots" in html
    html = istemci.get(f"/en/urun/{katalog['role']}").text
    assert "Add to cart" in html and "Indicative price" in html
    assert "RÖLE MODÜLÜ 24V" in html  # ürün adı çevrilmez


# ---------- K22 "Atölye" tasarım yönü (docs/tasarim/2026-10-13-tasarim-yonu-atolye.md §5) ----------

def test_k22_ana_sayfa_duzeni(istemci, katalog):
    html = sayfa_denetle(istemci.get("/tr/"))
    kahraman = re.search(r'<section class="kahraman".*?</section>', html, re.S).group(0)
    assert "<h1" in kahraman and "Test edilmiş robot ve otomasyon parçaları" in kahraman
    assert "<form" not in kahraman and 'name="q"' not in kahraman
    assert 'href="/tr/urunler"' in kahraman and "Ürünleri keşfet" in kahraman
    ust = re.search(r'<header class="ust">.*?</header>', html, re.S).group(0)
    assert 'action="/tr/ara"' in ust and 'name="q"' in ust
    kutular = re.search(r'<ul class="kategori-kutular">.*?</ul>', html, re.S).group(0)
    assert 'class="kategori-foto"' in kutular and "/statik/vitrin/kapak-" in kutular
    assert f'href="/tr/kategori/{katalog["rob"]}"' in kutular and "Endüstriyel Robotlar" in kutular
    assert "2 ürün" in kutular  # Elektrik ve Elektronik: alt kategorideki 2 aktif ürün; pasif sayılmaz
    guven = re.search(r'<ul class="guven-serit">.*?</ul>', html, re.S).group(0)
    for sayfa in ("garanti", "iade", "kullanim"):
        assert f'href="/tr/yasal/{sayfa}"' in guven, sayfa
    one = re.search(r'<section class="[^"]*one-cikanlar[^"]*".*?</section>', html, re.S).group(0)
    assert "Stoktaki öne çıkanlar" in one
    kart = one[one.index('<article class="kart"'):]
    assert kart.index("Temsili fiyat") < kart.index('class="tutar"')
    assert "RÖLE MODÜLÜ 24V" in one and "SİGORTA KUTUSU" not in one  # stoksuz ürün öne çıkmaz
    assert "Robot mu arıyorsunuz?" in html
    assert "karusel" not in html and "carousel" not in html
    alt = re.search(r'<footer class="alt">.*?</footer>', html, re.S).group(0)
    assert "K.O.S.B. 3. Sk., No: 7, 42250 Selçuklu / Konya" in alt
    assert 'href="tel:+903322391575"' in alt


def test_k22_liste_tablo_ve_mono_parca_no(istemci, katalog):
    html = sayfa_denetle(istemci.get(f"/tr/kategori/{katalog['elk']}"))
    tablo = re.search(r'<table class="urun-tablo".*?</table>', html, re.S)
    assert tablo, "liste tablosu yok"
    satirlar = re.findall(r'<tr class="ut-satir" id="urun-\d+">(.*?)</tr>', tablo.group(0), re.S)   # G3e: çapa
    assert len(satirlar) == 2
    for satir in satirlar:
        assert 'class="parca-no"' in satir
        assert re.search(r'<img [^>]*width="48" height="48"', satir)
        assert "KDV dahil" in satir
    assert "<th" in tablo.group(0) and 'scope="col"' in tablo.group(0)


def test_k22_liste_satir_eylemleri(istemci, katalog):
    html = istemci.get(f"/tr/kategori/{katalog['rob']}").text
    assert f'href="/tr/teklif?urun_id={katalog["robot"]}"' in html
    html = istemci.get(f"/tr/kategori/{katalog['kontrol']}").text
    assert html.count('action="/tr/sepet/ekle"') == 2
    assert f'name="urun_id" value="{katalog["role"]}"' in html


def test_k22_filtre_cekmecesi_ve_cipler(istemci, katalog):
    html = sayfa_denetle(istemci.get(f"/tr/kategori/{katalog['elk']}?stokta=1&fmax=6000&sira=fiyat_artan"))
    assert re.search(r'<details class="cekmece"[^>]*>\s*<summary', html), "filtre çekmecesi yok"
    cipler = re.search(r'<ul class="cipler"[^>]*>.*?</ul>', html, re.S).group(0)
    assert "Yalnız stoktakiler" in cipler
    k = katalog["elk"]
    assert f'href="/tr/kategori/{k}?fmax=6000&amp;sira=fiyat_artan"' in cipler  # stokta çipini kaldırır
    assert f'href="/tr/kategori/{k}?stokta=1&amp;sira=fiyat_artan"' in cipler  # fmax çipini kaldırır
    ust = re.search(r'<div class="liste-ust">.*?</div>', html, re.S).group(0)
    assert "1 ürün" in ust and 'name="sira"' in ust
    assert '<option value="fiyat_artan" selected>' in ust
    assert 'class="cipler"' not in istemci.get(f"/tr/kategori/{k}").text  # filtre yokken çip satırı yok


def test_k22_ters_fiyat_araliginda_cip_dogru_parametreyi_kaldirir(istemci, katalog):
    html = istemci.get(f"/tr/kategori/{katalog['elk']}?fmin=5100&fmax=5000").text
    cipler = re.search(r'<ul class="cipler"[^>]*>.*?</ul>', html, re.S).group(0)
    k = katalog["elk"]
    # gösterilen en az = 5000 (fmax'tan gelir) → çipi fmax'ı kaldırır (G3e: tutar görünen para biriminde)
    assert re.search(rf'href="/tr/kategori/{k}\?fmin=5100"[^>]*>[^<]*5.000,00 ₺', cipler)


def test_k22_alt_kategori_baglantilari(istemci, katalog):
    html = istemci.get(f"/tr/kategori/{katalog['rob']}").text
    alt = re.search(r'<ul class="alt-kategoriler"[^>]*>.*?</ul>', html, re.S).group(0)
    assert f'href="/tr/kategori/{katalog["kuka"]}"' in alt


def test_k22_aktif_kok_kategori_serit(istemci, katalog):
    html = istemci.get(f"/tr/urun/{katalog['robot']}").text
    serit = re.search(r'<nav class="kategori-serit"[^>]*>.*?</nav>', html, re.S).group(0)
    assert f'<a href="/tr/kategori/{katalog["rob"]}" aria-current="true">' in serit


def test_k22_bos_arama_onerileri(istemci, katalog):
    html = sayfa_denetle(istemci.get("/tr/ara", params={"q": "yokboyleurun"}))
    bos = re.search(r'<div class="bos-sonuc">.*?</section>', html, re.S).group(0)
    assert "Yazımı kontrol edin" in bos
    assert "Parçayı bulamadınız mı?" in bos and 'href="/tr/teklif?kod=yokboyleurun"' in bos
    assert f'href="/tr/kategori/{katalog["rob"]}"' in bos


def test_k22_urun_karar_blogu(istemci, katalog):
    html = sayfa_denetle(istemci.get(f"/tr/urun/{katalog['role']}"))
    assert re.search(r'<span class="parca-no">RL-24</span>', html)
    assert re.search(r'<button type="button" class="kopyala" data-kopyala="RL-24"[^>]*hidden>', html)
    assert "Kargo: TR 15 € + KDV (temsili), fabrikadan teslim alırsanız ücretsiz" in html   # G3m madde 6
    guven = re.search(r'<p class="guven-satiri">.*?</p>', html, re.S).group(0)
    assert 'href="/tr/yasal/garanti"' in guven and 'href="/tr/yasal/iade"' in guven
    assert 'href="/tr/yasal/kullanim#ihracat-export"' in guven   # G3m madde 25
    # karar bloğu sırası: ad → parça no → fiyat → stok → eylem
    sira = [html.index(s) for s in ("<h1", 'class="parca-no"', 'class="fiyat-blok"', "Stokta: 5 adet",
                                     'data-e2e="sepete-ekle"', "Kargo: TR 15 €")]
    assert sira == sorted(sira)
    assert "Teknik özellikler" in html and "Teknik veri sayfası (datasheet) talep üzerine" in html
    assert "Teslimat ve iade" in html
    assert "Durum bilgisi" not in html  # 2. el değil


def test_k22_ikinci_el_durum_bilgisi(istemci, katalog):
    """G3e madde 7: örnek değerli ("[örnek]") durum bilgisi bölümü kaldırıldı; örnek rozeti kalır."""
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET durum_kodu = 'ikinci_el_oldugu_gibi', durum_ornek = 1 WHERE id = ?",
                    (katalog["stoksuz"],))
    html = sayfa_denetle(istemci.get(f"/tr/urun/{katalog['stoksuz']}"))
    assert "Durum bilgisi" not in html and "[örnek]" not in html
    assert '<span class="rozet rozet-ornek" title="demo için elle girilmiş durum kaydı">demo kaydı</span>' in html


def test_k22_en_urun_sayfasi(istemci, katalog):
    html = sayfa_denetle(istemci.get(f"/en/urun/{katalog['robot']}"))
    assert "Technical specifications" in html and "Price on quotation" in html
    assert "Freight and delivery are stated in the quotation" in html
    assert "Shipping: TR €15" not in html  # teklif ürününde kargo satırı yok
    assert 'href="/en/teklif?urun_id=' in html
    html = sayfa_denetle(istemci.get(f"/en/urun/{katalog['role']}"))
    assert "Shipping: TR €15 + VAT (indicative)" in html


# ---------- Fix turu 1: teklif zorunlu ürünlerde hiçbir ekranda fiyat yok ----------

_TUTAR = re.compile(r"\d[\d.,]*\s*[₺€]|[₺€]\s*\d")


def _icerik(html: str) -> str:
    return re.search(r'<main id="icerik".*?</main>', html, re.S).group(0)


def test_teklif_urun_sayfasinda_fiyat_yok(istemci, katalog):
    html = sayfa_denetle(istemci.get(f"/tr/urun/{katalog['robot']}"))
    icerik = _icerik(html)
    assert not _TUTAR.search(icerik), _TUTAR.search(icerik).group(0)
    assert "Fiyat teklifle belirlenir" in icerik
    assert 'data-e2e="fiyat-ana"' not in html and 'data-e2e="fiyat-ikincil"' not in html
    assert 'data-e2e="teklif-iste"' in html
    assert "Navlun ve teslim teklifte belirtilir" in icerik
    assert "Kargo: TR 15 €" not in icerik


def test_teklif_urun_listede_fiyatsiz(istemci, katalog):
    html = istemci.get(f"/tr/kategori/{katalog['rob']}").text
    satir = re.search(r'<tr class="ut-satir" id="urun-\d+">(.*?)</tr>', html, re.S).group(1)
    assert "KUKA KRC5" in satir and "Fiyat teklifle belirlenir" in satir
    assert not _TUTAR.search(satir)
    assert f'href="/tr/teklif?urun_id={katalog["robot"]}"' in satir


def test_teklif_urun_kartinda_fiyat_yok(istemci, katalog):
    from app.katalog.depo import urun_getir

    with istemci_db(istemci) as con:
        robot = urun_getir(con, katalog["robot"])
    ceviri = istemci.app.state.ceviri
    sablon = istemci.app.state.sablonlar.env.from_string(
        '{% from "_makrolar.html" import urun_karti with context %}{{ urun_karti(u) }}')

    def fiyat_goster(_):
        raise AssertionError("teklif ürününde fiyat hesaplanmamalı")

    html = sablon.render(u=robot, dil="tr", t=lambda a, **k: ceviri.t("tr", a, **k),
                         gorsel_adresi=lambda u: "/x.svg", yer_tutucu=lambda a: "/y.svg", yer_tutucu_mu=lambda a: True, teslim_notu=lambda u: "teslim", garantili_mi=lambda u: False,
                         fiyat_goster=fiyat_goster, para=lambda *a: "?", kur=None,
                         iade_metinleri=lambda u: [])     # G3n madde 5: iade satırları bağlamdan
    assert "Fiyat teklifle belirlenir" in html and not _TUTAR.search(html)
    assert f'href="/tr/teklif?urun_id={katalog["robot"]}"' in html


def test_one_cikanlarda_teklif_urunu_yok(istemci, katalog):
    html = istemci.get("/tr/").text
    one = re.search(r'<section class="[^"]*one-cikanlar[^"]*".*?</section>', html, re.S).group(0)
    assert "KUKA KRC5" not in one and "RÖLE MODÜLÜ 24V" in one


def test_ana_sayfa_istatistikte_ulke_sayisi_yok(istemci, katalog):
    html = istemci.get("/tr/").text
    sayilar = re.search(r'<ul class="kahraman-sayilar">.*?</ul>', html, re.S).group(0)
    assert sayilar.count("<li>") == 2 and "ülke" not in sayilar


def test_teknik_destek_telefona_gider(istemci, katalog):
    guven = re.search(r'<ul class="guven-serit">.*?</ul>', istemci.get("/tr/").text, re.S).group(0)
    assert 'href="tel:+903322391575"' in guven and "/yasal/kunye" not in guven


# ---------- G3a Ö2: fasetler, hızlı çipler, filtre yerleşimi, tüm ürünler, boş sonuç formu ----------

@pytest.fixture
def g3a(istemci, katalog):
    with istemci_db(istemci) as con:
        siemens = urun_ekle(con, sku="8102030100019", ad="SIEMENS SIRIUS İZLEME RÖLESİ", kok="Elektrik ve Elektronik",
                            fiyat="250.00", kategori_id=katalog["kontrol"], stok=2, uretici_kodu="3UG4512-1BR20")
        omron = urun_ekle(con, sku="OM-1", ad="OMRON RÖLE G2R", kok="Elektrik ve Elektronik", fiyat="35.00",
                          kategori_id=katalog["kontrol"], stok=0)
        kaynak = urun_ekle(con, sku="8503053800001", ad="KUKA KRC2 GÜÇ KAYNAĞI 27V-NT", kok="Elektrik ve Elektronik",
                           fiyat="3621.00", kategori_id=katalog["elk"], stok=2, uretici_kodu="00-109-802")
        benzer = urun_ekle(con, sku="8503053800002", ad="A KUKA KABLO SETİ", kok="Elektrik ve Elektronik",
                           fiyat="90.00", kategori_id=katalog["elk"], stok=1, uretici_kodu="00-109-8021")
        con.execute("UPDATE urun SET durum_kodu = 'ikinci_el_test_edildi' WHERE id = ?", (siemens,))
    return {**katalog, "siemens": siemens, "omron": omron, "kaynak": kaynak, "benzer": benzer}


def _blok(html, desen):
    m = re.search(desen, html, re.S)
    assert m, desen
    return m.group(0)


def _faset(html, ad):
    return _blok(html, rf'<fieldset class="faset" data-faset="{ad}">.*?</fieldset>')


def test_g3a_faset_paneli_sayimli_ve_sifirlar_yok(istemci, g3a):
    html = sayfa_denetle(istemci.get(f"/tr/kategori/{g3a['elk']}"))
    marka = _faset(html, "marka")
    assert re.search(r'<input type="checkbox" name="marka" value="Siemens"[^>]*>\s*<span class="faset-ad">Siemens</span>'
                     r'\s*<span class="faset-sayi">1</span>', marka)
    assert 'value="KUKA"' in marka and 'value="Omron"' in marka
    durum = _faset(html, "durum")
    assert "2. el – test edildi" in durum and "Belirtilmemiş" in durum and 'value="yeni"' not in durum
    stok = _faset(html, "stok")
    assert 'name="stokta" value="1"' in stok and 'name="tedarikli" value="1"' in stok
    fiyat = _faset(html, "fiyat")
    assert 'name="fiyatli" value="1"' in fiyat and 'name="teklifle"' not in fiyat    # bu kategoride teklifli yok
    kat = _faset(html, "kategori")
    assert f'name="kat" value="{g3a["kontrol"]}"' in kat and "KONTROL SISTEMLERI" in kat


def test_g3a_filtre_paneli_agacin_ustunde_agac_katlanir(istemci, g3a):
    html = istemci.get(f"/tr/kategori/{g3a['elk']}").text
    yan = _blok(html, r'<aside class="yan".*?</aside>')
    assert yan.index('class="filtre"') < yan.index('class="agac"')
    assert re.search(r'<details class="agac-kutu"[^>]*>\s*<summary', yan)


def test_g3a_coklu_secim_urlde_ve_cipler(istemci, g3a):
    k = g3a["elk"]
    html = sayfa_denetle(istemci.get(f"/tr/kategori/{k}?marka=Siemens&marka=Omron"))
    assert "SIEMENS SIRIUS" in html and "OMRON RÖLE" in html and "RÖLE MODÜLÜ 24V" not in html
    assert re.search(r'<input type="checkbox" name="marka" value="Siemens" checked>', html)
    cipler = _blok(html, r'<ul class="cipler"[^>]*>.*?</ul>')
    assert f'href="/tr/kategori/{k}?marka=Omron"' in cipler          # Siemens çipi yalnız kendi değerini kaldırır
    assert f'href="/tr/kategori/{k}?marka=Siemens"' in cipler
    html = istemci.get(f"/tr/kategori/{k}?marka=Siemens&tedarikli=1").text
    assert "Bu ölçütlere uyan ürün bulunamadı." in html               # Siemens stokta
    html = istemci.get(f"/tr/kategori/{k}?kat={g3a['kontrol']}&durum=ikinci_el_test_edildi").text
    assert "SIEMENS SIRIUS" in html and "OMRON" not in html and "KUKA KRC2" not in html


def test_g3a_siralama_formu_coklu_parametreleri_tasir(istemci, g3a):
    html = istemci.get(f"/tr/kategori/{g3a['elk']}?marka=Siemens&marka=KUKA&stokta=1").text
    ust = _blok(html, r'<form class="siralama".*?</form>')
    assert "data-otomatik" in ust and 'class="dugme ikincil js-gizle"' in ust
    assert ust.count('<input type="hidden" name="marka"') == 2 and 'name="stokta" value="1"' in ust


def test_g3a_hizli_cipler(istemci, g3a):
    k = g3a["elk"]
    html = sayfa_denetle(istemci.get(f"/tr/kategori/{k}"))
    hizli = _blok(html, r'<ul class="hizli-cipler"[^>]*>.*?</ul>')
    assert f'href="/tr/kategori/{k}?stokta=1"' in hizli and "Stokta" in hizli
    # G3k madde 10: "Test edilmiş" çipi kaldırıldı (Durum grubu varsayılan açık, tek yer)
    assert "durum=ikinci_el_test_edildi" not in hizli and "Test edilmiş" not in hizli
    assert f'href="/tr/kategori/{k}?fiyatli=1"' in hizli and "Fiyatlı" in hizli
    assert "Yenilenmiş" not in hizli                                   # sayısı 0
    html = istemci.get(f"/tr/kategori/{k}?stokta=1").text
    hizli = _blok(html, r'<ul class="hizli-cipler"[^>]*>.*?</ul>')
    assert re.search(rf'<a class="hizli-cip secili" href="/tr/kategori/{k}"[^>]*>', hizli)   # seçiliyse kaldırır
    assert html.index('class="hizli-cipler"') < html.index('class="urun-tablo"')


def test_g3a_fiyat_min_teklifli_urunleri_disler(istemci, g3a):
    html = istemci.get(f"/tr/kategori/{g3a['rob']}?fmin=1").text
    assert "KUKA KRC5" not in html
    assert "KUKA KRC5" in istemci.get(f"/tr/kategori/{g3a['rob']}").text


def test_g3a_tum_urunler_sayfasi(istemci, g3a):
    yanit = istemci.get("/tr/urunler")
    html = sayfa_denetle(yanit)
    assert yanit.status_code == 200
    assert "<h1>Tüm ürünler</h1>" in html
    ust = _blok(html, r'<div class="liste-ust">.*?</div>')
    assert "7 ürün" in ust                                            # aktif ürünler (pasif hariç)
    assert "ESKİ KART" not in html and "KUKA KRC5" in html and "OMRON" in html
    assert 'data-faset="marka"' in html
    assert 'href="/tr/urunler?stokta=1"' in html
    en = istemci.get("/en/urunler").text
    assert "<h1>All products</h1>" in en and "<h1>Tüm ürünler</h1>" not in en


def test_g3a_bos_arama_tum_urunlere_yonlenir(istemci, g3a):
    r = istemci.get("/tr/ara", params={"q": "   ", "stokta": "1"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/tr/urunler?stokta=1"
    r = istemci.get("/tr/ara", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/tr/urunler"


def test_g3a_arama_tam_kod_en_ustte_ve_isaretli(istemci, g3a):
    for q in ("00-109-802", "00109802", "00 109 802"):
        html = sayfa_denetle(istemci.get("/tr/ara", params={"q": q}))
        sira = [html.index(f'href="/tr/urun/{g3a[a]}"') for a in ("kaynak", "benzer")]
        assert sira[0] < sira[1], q                                    # "A KUKA KABLO" adla önde olurdu
        satir = _blok(html, rf'<tr class="ut-satir[^"]*"[^>]*>(?:(?!</tr>).)*?/tr/urun/{g3a["kaynak"]}".*?</tr>')
        assert 'data-e2e="tam-eslesme"' in satir
    ust = _blok(istemci.get("/tr/ara", params={"q": "00109802"}).text, r'<form class="siralama".*?</form>')
    assert '<option value="alaka" selected>' in ust
    assert '<option value="alaka"' not in istemci.get(f"/tr/kategori/{g3a['elk']}").text


def test_g3a_bos_sonuc_hizli_teklif_formu(istemci, g3a):
    html = sayfa_denetle(istemci.get("/tr/ara", params={"q": "ZX-99 123"}))
    form = _blok(html, r'<form class="hizli-teklif"[^>]*>.*?</form>')
    assert 'action="/tr/teklif/hizli"' in form and 'method="post"' in form
    for ad in ("ad", "iletisim", "parca_kodu"):
        assert f'name="{ad}"' in form
    assert 'name="parca_kodu"' in form and 'value="ZX-99 123"' in form
    assert 'href="/tr/teklif?kod=ZX-99+123"' in html                   # tam forma kodu taşıyan bağlantı


def test_g3a_hizli_teklif_kaydi(istemci, g3a):
    csrf = csrf_al(istemci, "/tr/ara?q=ZX-99")
    r = istemci.post("/tr/teklif/hizli", data={"csrf": csrf, "ad": "QATestUser", "iletisim": "+90 555 000 00 00",
                                               "parca_kodu": "ZX-99"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/tr/teklif/tamam?no=CR-TKL-")
    with istemci_db(istemci) as con:
        t = con.execute("SELECT ad, eposta, telefon, mesaj FROM teklif").fetchone()
    assert t["ad"] == "QATestUser" and t["telefon"] == "+90 555 000 00 00" and "ZX-99" in t["mesaj"]
    r = istemci.post("/tr/teklif/hizli", data={"csrf": csrf, "ad": "QATestUser", "iletisim": "qa@ornek.test",
                                               "parca_kodu": "ZX-98"}, follow_redirects=False)
    assert r.status_code == 303
    with istemci_db(istemci) as con:
        assert con.execute("SELECT eposta FROM teklif ORDER BY id DESC").fetchone()[0] == "qa@ornek.test"


def test_g3a_hizli_teklif_hatalari(istemci, g3a):
    csrf = csrf_al(istemci, "/tr/ara?q=ZX-99")
    r = istemci.post("/tr/teklif/hizli", data={"csrf": csrf, "ad": "", "iletisim": "abc", "parca_kodu": "ZX-99"})
    assert r.status_code == 400
    html = sayfa_denetle(r, robots="noindex, nofollow")
    assert 'class="form-hata-ozet"' in html and 'value="ZX-99"' in html
    with istemci_db(istemci) as con:
        assert con.execute("SELECT COUNT(*) FROM teklif").fetchone()[0] == 0
    assert istemci.post("/tr/teklif/hizli", data={"ad": "x", "iletisim": "x@y.z", "parca_kodu": "1"}).status_code == 403


def test_g3a_teklif_formu_kodu_tasir(istemci, g3a):
    html = istemci.get("/tr/teklif", params={"kod": "00109802"}).text
    assert re.search(r'<textarea id="mesaj"[^>]*>Parça kodu: 00109802', html)


@pytest.mark.parametrize("sorgu", ["kat=abc", "kat=-1", f"kat={2**70}", "marka=" + "x" * 500, "durum=<script>",
                                   "marka=&durum=&kat=", "tedarikli=2&fiyatli=evet", "sira=alaka"])
def test_g3a_bozuk_faset_parametreleri(istemci, g3a, sorgu):
    yanit = istemci.get(f"/tr/kategori/{g3a['elk']}?{sorgu}")
    assert yanit.status_code == 200
    assert "<script>" not in yanit.text.split("</head>", 1)[1].replace('<script src="/statik/site.js" defer></script>', "")


def test_g3a_kategori_agaci_onbellekte_esitlemeyle_yenilenir(istemci, g3a):
    istemci.get(f"/tr/kategori/{g3a['elk']}")
    with istemci_db(istemci) as con:
        yeni = kategori_ekle(con, kaynak_id="k99", ad="YENİ KÖK KATEGORİ", yol="99", seviye=0)
        urun_ekle(con, sku="YK-1", ad="YENİ KÖK ÜRÜNÜ", kategori_id=yeni)   # G3e: boş kategori menüde gösterilmez
    assert "YENİ KÖK KATEGORİ" not in istemci.get("/tr/").text          # önbellek: eşitleme olmadan değişmez
    with istemci_db(istemci) as con:
        con.execute("INSERT INTO esitleme_gunlugu (basla, bitis, durum) VALUES ('2026-10-13T02:30:00+00:00',"
                    " '2026-10-13T02:40:00+00:00', 'tam')")
    assert f'href="/tr/kategori/{yeni}"' in istemci.get("/tr/").text


def test_g3a_kategori_seridinde_tum_urunler(istemci, g3a):
    serit = _blok(istemci.get("/tr/").text, r'<nav class="kategori-serit"[^>]*>.*?</nav>')
    assert '<a href="/tr/urunler">Tüm ürünler</a>' in serit
    serit = _blok(istemci.get("/tr/urunler").text, r'<nav class="kategori-serit"[^>]*>.*?</nav>')
    assert '<a href="/tr/urunler" aria-current="true">' in serit


@pytest.mark.parametrize("iletisim", ["a@b", "a@@b.com", "@ornek.test", "qa@ornek", "12-34", "telefonum yok"])
def test_g3a_hizli_teklif_gecersiz_iletisim(istemci, g3a, iletisim):
    csrf = csrf_al(istemci, "/tr/ara?q=ZX-99")
    r = istemci.post("/tr/teklif/hizli", data={"csrf": csrf, "ad": "Q", "iletisim": iletisim, "parca_kodu": "ZX-99"})
    assert r.status_code == 400 and 'id="hata-iletisim"' in r.text
    assert 'href="/tr/teklif?kod=ZX-99"' in r.text                    # tam forma geçişte kod kaybolmaz


def test_g3a_hizli_teklif_iletisim_alani_telefon_klavyesi(istemci, g3a):
    form = _blok(istemci.get("/tr/ara", params={"q": "ZX-99"}).text, r'<form class="hizli-teklif"[^>]*>.*?</form>')
    assert 'inputmode="email"' not in form


def test_g3a_sonuc_satiri_hizli_ciplerden_once_ve_bos_sonucta_da_var(istemci, g3a):
    html = istemci.get(f"/tr/kategori/{g3a['elk']}").text
    assert html.index('class="liste-ust"') < html.index('class="hizli-cipler"') < html.index('class="urun-tablo"')
    bos = istemci.get("/tr/ara", params={"q": "yokboyleurun"}).text
    assert re.search(r'<div class="liste-ust">\s*<p class="sonuc-sayisi">0 ürün</p>', bos)
    assert 'class="siralama"' not in bos
