"""G3b: API techSpecs / descriptionSections -> güvenli düz metin; ürün durumu çıkarımı (saf fonksiyonlar)."""
import pytest

from app.esitleme.teknik import EN_COK_BAYT, durum_cikar, duz_metin, teknik_cikar, teknik_json

BASE64 = "iVBORw0KGgo" + "A" * 4000 + "=="


def test_duz_metin_html_etiketlerini_temizler():
    ham = "<p>Gerilim <b>24&nbsp;V</b></p><script>alert(1)</script><style>p{}</style><br>İkinci&amp;satır"
    assert duz_metin(ham, 500) == "Gerilim 24 V\nİkinci&satır"


def test_duz_metin_tablo_hucreleri_anahtar_deger_olur():
    ham = "<table><tr><th>Tip</th><td>SNBP-27</td></tr><tr><td>Voltaj</td><td>600V</td></tr></table>"
    assert duz_metin(ham, 500) == "Tip: SNBP-27\nVoltaj: 600V"


def test_duz_metin_base64_ve_data_uri_atilir():
    ham = f'Önce <img src="data:image/png;base64,{BASE64}"> sonra data:image/jpeg;base64,{BASE64} {BASE64} son'
    sonuc = duz_metin(ham, 500)
    assert sonuc == "Önce sonra son"
    assert "base64" not in sonuc and "AAAA" not in sonuc


def test_duz_metin_sinir_ve_tur():
    assert duz_metin(None, 10) is None
    assert duz_metin(42, 10) is None
    assert duz_metin("   ", 10) is None
    assert duz_metin("a" * 50, 10) == "a" * 9 + "…"
    assert duz_metin("a\x00b\x07c", 10) == "abc"


API_KAYDI = {
    "name": "SUNS KALDIRMA VE VİNÇ İÇİN MEKANİK LİMİT SWİTCH",
    "techSpecs": [
        {"label": "Type", "value": "SNBP-27-SL2-NC"},
        {"label": "Anma Yalıtım Voltajı", "value": "600V"},
        {"label": "İşletme Akım ve Voltaj Değerleri", "value": "240V'ta 3A"},
        {"label": "İşletme Akım ve Voltaj Değerleri", "value": "250V'ta 0.27A"},
        {"label": "", "value": "etiketsiz"},
        {"label": "Boş", "value": ""},
        "bozuk",
    ],
    "descriptionSections": [
        {"title": "", "content": "SUNS KALDIRMA VE VİNÇ İÇİN MEKANİK LİMİT SWİTCH\n\n*Görseldeki ürün ikinci eldir."},
        {"title": "Not", "content": f"<img src='data:image/png;base64,{BASE64}'>"},
    ],
}


def test_teknik_cikar_ozellik_ve_bolumler():
    t = teknik_cikar(API_KAYDI, API_KAYDI["name"])
    assert t["ozellikler"] == [
        ["Type", "SNBP-27-SL2-NC"], ["Anma Yalıtım Voltajı", "600V"],
        ["İşletme Akım ve Voltaj Değerleri", "240V'ta 3A"], ["İşletme Akım ve Voltaj Değerleri", "250V'ta 0.27A"],
    ]
    # ad tekrarı olan satır atılır; yalnız görselden oluşan bölüm boş kalır ve atılır
    assert t["bolumler"] == [["", "*Görseldeki ürün ikinci eldir."]]


def test_teknik_cikar_bos_ya_da_bozuk_alan_none():
    assert teknik_cikar({"techSpecs": [], "descriptionSections": []}, "X") is None
    assert teknik_cikar({"techSpecs": "metin", "descriptionSections": {"a": 1}}, "X") is None
    assert teknik_cikar({}, "X") is None


def test_teknik_cikar_8_kb_siniri():
    kayit = {
        "techSpecs": [{"label": f"Özellik {i}", "value": "ğ" * 400} for i in range(100)],
        "descriptionSections": [{"title": "Uzun", "content": "ş" * 4000}],
    }
    t = teknik_cikar(kayit, "X")
    assert len(teknik_json(t).encode("utf-8")) <= EN_COK_BAYT
    assert 1 <= len(t["ozellikler"]) < 100


@pytest.mark.parametrize(("ad", "metinler", "beklenen"), [
    # G3b düzeltme turu 1: genel 2. el kodu; "olduğu gibi" yalnız açık ibareyle
    ("SUNS LİMİT SWİTCH", ["SUNS LİMİT SWİTCH\n\n*Görseldeki ürün ikinci eldir."], "ikinci_el"),
    ("KUKA MOTOR 2. EL", [], "ikinci_el"),
    ("KUKA MOTOR İKİNCİ EL", [], "ikinci_el"),
    ("USED ABB MOTOR", [], "ikinci_el"),
    ("ABB KART", ["2. el, olduğu gibi satılır."], "ikinci_el_oldugu_gibi"),
    ("ABB KART", ["Used, sold as is."], "ikinci_el_oldugu_gibi"),
    ("FANUC KART", ["2.el, test edilmiştir"], "ikinci_el_test_edildi"),
    ("FANUC KART", ["Ürün 2. el olup test edilmiştir."], "ikinci_el_test_edildi"),
    ("ABB SÜRÜCÜ YENİLENMİŞ", [], "yenilenmis"),
    ("SIEMENS PANEL REFURBISHED", [], "yenilenmis"),
    # tek başına "test edilmiş" durum değildir (yeni ürün de sevkiyat öncesi test edilir)
    ("ABB SÜRÜCÜ", ["Sevkiyattan önce test edilmiştir."], None),
    # test ibaresi başka metinde: yükseltme yok
    ("ABB SÜRÜCÜ 2. EL", ["Test edilmiştir."], "ikinci_el"),
    # yeni/sıfır/new kalıpları kaldırıldı
    ("SIEMENS PANEL SIFIR", [], None),
    ("OMRON SENSÖR NEW SERIES", [], None),
    ("KR C4 NEW TYPE", [], None),
    ("NABTESCO SIFIR BOŞLUKLU REDÜKTÖR", [], None),
    # olumsuz cümle
    ("ABB KART", ["Bu ürün ikinci el değildir."], None),
    ("ABB KART", ["This unit is not used."], None),
    ("ABB KART", ["Kutusu açılmamış; ikinci el değildir. Garanti kapsamındadır."], None),
    # sıradan İngilizce kullanım ve "yenilenmiş tasarım"
    ("ABB KART", ["This module is used for welding and new projects."], None),
    ("ABB KART", ["Yenilenmiş tasarım ile daha kompakt."], None),
    ("ABB KART", [], None),
    ("İKİNCİ ELEKTRİK KUTUSU", [], None),
    # en güçlü sonuç kazanır
    ("ABB KART 2. EL", ["Yenilenmiştir."], "yenilenmis"),
])
def test_durum_cikar(ad, metinler, beklenen):
    assert durum_cikar(ad, metinler) == beklenen


def test_duz_metin_kapanmayan_etiketlerde_dogrusal():
    import time
    bas = time.perf_counter()
    assert duz_metin("<" * 200_000 + "a", 100).startswith("<")   # metin olarak kalır (şablon kaçışlar)
    assert duz_metin("<script" * 20_000, 100) is not None
    assert time.perf_counter() - bas < 2


def test_duz_metin_satir_kirilimli_base64_atilir():
    satirlar = "\n".join("QUJD" * 19 for _ in range(30))       # 76 kr'lik MIME satırları
    ham = f"Önce\n{satirlar}\nsonra <img src=\"data:image/png;base64,\n{satirlar}\">bitti"
    assert duz_metin(ham, 4000) == "Önce\nsonra bitti"
