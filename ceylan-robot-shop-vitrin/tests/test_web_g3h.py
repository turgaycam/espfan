"""G3h: persona tur 4 — arama (A 1–4), filtre (B 5–8), karşılaştırma (C 9–12), liste ve mobil (D 13–15)."""
import re
from html import unescape

import pytest

from app.katalog.depo import ListeSorgusu, faset_sayilari, urun_listele
from app.katalog.indeks import indeksi_yeniden_kur
from tests.conftest import istemci_db, kategori_ekle, sayfa_denetle, urun_ekle


def _idler(sonuc):
    return [u.id for u in sonuc.urunler]


def _aciklama(con, urun_id, metin, dil="tr"):
    con.execute("INSERT INTO urun_aciklama (urun_id, dil, metin, kaynak, uretildi) VALUES (?, ?, ?, 'kaynak', 'z')",
                (urun_id, dil, metin))


def _satirlar(html):
    """Liste tablosundaki ürün adları (sırayla)."""
    return [unescape(re.sub(r"<[^>]+>", "", m)) for m in re.findall(r'data-e2e="urun-baglanti">(.*?)</a>', html)]


# =====================================================================================================
# A1 — bitişik/ayrık kod eşdeğerliği (katlanmış metin sütunu)
# =====================================================================================================

@pytest.fixture
def kodlu(con):
    k = {
        "dsqc": urun_ekle(con, sku="3HAC14178-1", ad="ABB DSQC 626 A GÜÇ KAYNAĞI"),
        "krc4_bitisik": urun_ekle(con, sku="K1", ad="KUKA KRC4 KR 10 R1100"),
        "krc4_ayrik": urun_ekle(con, sku="K2", ad="KUKA KR C4 SMARTPAD"),
        "krc4_ayrik2": urun_ekle(con, sku="K3", ad="KUKA KR C4 GÜÇ KAYNAĞI"),
        "krc2": urun_ekle(con, sku="K4", ad="KUKA KRC2 GÜÇ KAYNAĞI 27V-NT", uretici_kodu="00-109-802"),
        "sayi": urun_ekle(con, sku="Z1", ad="ZİNCİR 1100109802X"),
        "kategoride": urun_ekle(con, sku="K5", ad="KUKA KR 150 R3100 PRIME",
                                kategori_id=kategori_ekle(con, kaynak_id="kc4", ad="KR C4", yol="9", seviye=0)),
        "aciklamada": urun_ekle(con, sku="K6", ad="KUKA FREN DİRENCİ"),
    }
    _aciklama(con, k["aciklamada"], "KR C4 kontrol dolabında kullanılır.")
    indeksi_yeniden_kur(con)
    con.commit()
    return k


@pytest.mark.parametrize("sorgu", ["DSQC626", "DSQC626A", "dsqc 626", "DSQC 626 A", "dsqc-626a", "DSQC626 güç"])
def test_g3h_bitisik_kod_ayrik_adi_bulur(con, kodlu, sorgu):
    assert kodlu["dsqc"] in _idler(urun_listele(con, ListeSorgusu(arama=sorgu))), sorgu


def test_g3h_krc4_ve_kr_c4_ayni_sonuc_kumesi(con, kodlu):
    bitisik = set(_idler(urun_listele(con, ListeSorgusu(arama="KRC4"))))
    ayrik = set(_idler(urun_listele(con, ListeSorgusu(arama="KR C4"))))
    # ad ve kategori ("KR C4") her iki yazımda da eşleşir; inceleme M-1: açıklama katlanmış metne girmez, açıklamadaki
    # "KR C4" yalnız ayrık yazımla (FTS) bulunur
    assert bitisik == ayrik - {kodlu["aciklamada"]} == {kodlu["krc4_bitisik"], kodlu["krc4_ayrik"], kodlu["krc4_ayrik2"],
                                                         kodlu["kategoride"]}
    assert kodlu["aciklamada"] in ayrik
    assert set(_idler(urun_listele(con, ListeSorgusu(arama="kuka krc4 güç kaynağı")))) == {kodlu["krc4_ayrik2"]}


def test_g3h_salt_rakam_kodda_mevcut_davranis(con, kodlu):
    # 00109802 tiresiz kod: üretici kodu eşleşir; yalnız rakamdan oluşan sorgu adın ortasında alt dize aranmaz
    assert _idler(urun_listele(con, ListeSorgusu(arama="00109802"))) == [kodlu["krc2"]]
    assert _idler(urun_listele(con, ListeSorgusu(arama="00-109-802", siralama="alaka")))[0] == kodlu["krc2"]


def test_g3h_katli_metin_ve_tip_eslemede_yazilir(con):
    elk = kategori_ekle(con, kaynak_id="k1", ad="ROBOT MOTORLARI", yol="1", seviye=0)
    servo = kategori_ekle(con, kaynak_id="k2", ad="SERVO MOTORLAR", yol="1.2", seviye=1, ust_kaynak_id="k1")
    u = urun_ekle(con, sku="A06B-0235-B605", ad="FANUC A06B-0235-B605", kategori_id=servo)
    _aciklama(con, u, "Açıklama metni")
    con.execute("UPDATE urun SET katli_metin = '', tip = 'diger'")
    indeksi_yeniden_kur(con)
    r = con.execute("SELECT katli_metin, tip FROM urun WHERE id = ?", (u,)).fetchone()
    assert tuple(r) == ("|fanuca06b0235b605|a06b0235b605|0235b605|b605|a06b0235b605|0235b605|b605|servomotorlar"
                        "|motorlar", "servo_motor")     # addan bulunamadı: kategoriden
    assert con.execute("SELECT metin FROM urun_aciklama WHERE urun_id = ?", (u,)).fetchone()[0] == "Açıklama metni"
    assert elk


def test_g3h_bitisik_kod_web(istemci):
    with istemci_db(istemci) as con:
        urun_ekle(con, sku="3HAC14178-1", ad="ABB DSQC 626 A GÜÇ KAYNAĞI", stok=2)
    for q in ("DSQC626", "DSQC626A"):
        html = sayfa_denetle(istemci.get("/tr/ara", params={"q": q}))
        assert "ABB DSQC 626 A GÜÇ KAYNAĞI" in html, q


# =====================================================================================================
# A2 — sıfır sonuçta gevşetme + eşanlamlılar
# =====================================================================================================

@pytest.fixture
def gevsek(istemci):
    with istemci_db(istemci) as con:
        k = {
            "fanuc_motor": urun_ekle(con, sku="F1", ad="FANUC AC SERVO MOTOR", stok=1),
            "fanuc_enk": urun_ekle(con, sku="F2", ad="FANUC ENKODER", stok=1),
            "kuka_gk": urun_ekle(con, sku="G1", ad="KUKA GÜÇ KAYNAĞI KPS-600", stok=1),
            "sie_gk": urun_ekle(con, sku="G2", ad="SIEMENS SITOP GÜÇ KAYNAĞI", stok=1),
            "role": urun_ekle(con, sku="R1", ad="RÖLE MODÜLÜ", stok=1),
        }
        indeksi_yeniden_kur(con)
    return k


def test_g3h_sifir_sonucta_kelimelerden_birini_icerenler(istemci, gevsek):
    html = sayfa_denetle(istemci.get("/tr/ara", params={"q": "fanuc güç kaynağı"}))
    assert "“fanuc güç kaynağı” için tüm kelimeleri içeren ürün yok. Kelimelerden birini içerenler:" in html
    adlar = _satirlar(html)
    assert set(adlar) == {"FANUC AC SERVO MOTOR", "FANUC ENKODER", "KUKA GÜÇ KAYNAĞI KPS-600",
                          "SIEMENS SITOP GÜÇ KAYNAĞI"}
    gevset = re.search(r'<p class="gevset"[^>]*>.*?</p>', html, re.S).group(0)
    assert re.search(r'<a href="/tr/ara\?q=fanuc">fanuc</a> \(2\)', gevset)
    assert re.search(r'<a href="/tr/ara\?q=g%C3%BC%C3%A7\+kayna%C4%9F%C4%B1">güç kaynağı</a> \(2\)', gevset)
    assert "Parçayı bulamadınız mı?" not in html             # sonuç var: boş sonuç bloğu yok
    en = sayfa_denetle(istemci.get("/en/ara", params={"q": "fanuc power supply"}))
    assert "No product contains all the words of “fanuc power supply”. Products containing any of the words:" in en
    assert len(_satirlar(en)) == 4


def test_g3h_tum_kelimeler_varsa_gevsetme_yok(istemci, gevsek):
    html = istemci.get("/tr/ara", params={"q": "kuka güç kaynağı"}).text
    assert _satirlar(html) == ["KUKA GÜÇ KAYNAĞI KPS-600"] and 'class="gevset"' not in html
    bos = istemci.get("/tr/ara", params={"q": "xyzzy qwerty"}).text      # hiçbir kelime yok: boş sonuç bloğu
    assert 'class="gevset"' not in bos and "Parçayı bulamadınız mı?" in bos


@pytest.fixture
def esanlam(con):
    k = {
        "resolver": urun_ekle(con, sku="E1", ad="KUKA RESOLVER RDC KUTUSU"),
        "surucu": urun_ekle(con, sku="E2", ad="YASKAWA SERVO SÜRÜCÜ"),
        "surucu_kart": urun_ekle(con, sku="E3", ad="ABB DSQC 601 SÜRÜCÜ KARTI"),
        "drive_board": urun_ekle(con, sku="E4", ad="FANUC DRIVE BOARD"),
        "plc": urun_ekle(con, sku="E5", ad="SIEMENS S7-300 PLC İŞLEMCİ"),
        "hmi": urun_ekle(con, sku="E6", ad="SIEMENS SIMATIC OPERATÖR PANELİ"),
        "enkoder": urun_ekle(con, sku="E7", ad="HEIDENHAIN ENKODER"),
        "frekans": urun_ekle(con, sku="E8", ad="ABB FREKANS KONVERTÖRÜ 7,5KW"),
        "invertor": urun_ekle(con, sku="E9", ad="DELTA İNVERTÖR 2KW"),
    }
    indeksi_yeniden_kur(con)
    return k


@pytest.mark.parametrize("sorgu,anahtarlar", [
    ("resolver", ["resolver"]), ("rezolver", ["resolver"]),
    ("servo amplifier", ["surucu"]), ("servo amplifikatör", ["surucu"]),
    ("sürücü kartı", ["surucu_kart", "drive_board"]), ("drive card", ["surucu_kart", "drive_board"]),
    ("PLC", ["plc"]), ("programmable logic controller", ["plc"]),
    ("HMI", ["hmi"]), ("operatör paneli", ["hmi"]), ("operator panel", ["hmi"]),
    ("encoder", ["enkoder"]), ("enkoder", ["enkoder"]),
    ("inverter", ["frekans", "invertor"]), ("invertör", ["frekans", "invertor"]),
    ("frekans konvertörü", ["frekans", "invertor"]), ("frequency converter", ["frekans", "invertor"]),
    ("Umrichter", ["frekans", "invertor"]),     # G3k madde 4: Umrichter yalnız frekans konvertörü (sürücü değil)
])
def test_g3h_esanlamlilar(con, esanlam, sorgu, anahtarlar):
    bulunan = set(_idler(urun_listele(con, ListeSorgusu(arama=sorgu))))
    assert {esanlam[a] for a in anahtarlar} <= bulunan, sorgu


# =====================================================================================================
# A3 — alaka sıralaması
# =====================================================================================================

SERVO_ADLARI = ("ABB 2,2KW AC SERVO MOTOR", "ABB 0,75KW AC SERVO MOTOR", "ABB 4KW AC SERVO MOTOR",
                "ABB 7KW AC SERVO MOTOR", "KUKA 1FK7060 SIMOTICS SERVO MOTOR", "KUKA 4,2KW SERVO MOTOR",
                "KUKA 3KW SERVO MOTOR", "FANUC AİS 30/4000 AC SERVO MOTOR", "YASKAWA 1,3KW R EKSENİ AC SERVO MOTOR",
                "REXROTH INDRAMAT AC SERVO MOTOR", "KOLLMORGEN SERVO MOTOR")
GURULTU = ("0.37KW ÜÇ FAZLI ASENKRON MOTOR", "ALLEN-BRADLEY 32A ÜÇ KUTUPLU MOTOR KONTAKTÖRÜ",
           "ATLAS ENDÜSTRİYEL SERVO MOTOR / HAVA MOTORU", "ABB SOĞUTMALI MOTOR SÜRÜCÜSÜ",
           "DELTA 15KW TEK FAZLI AC MOTOR HIZ KONTROL SÜRÜCÜSÜ")


def _alaka_tohumu(con):
    motorlar = kategori_ekle(con, kaynak_id="m", ad="MOTORLAR", yol="5", seviye=0)
    servolar = kategori_ekle(con, kaynak_id="s", ad="SERVO MOTORLAR", yol="6", seviye=0)
    kontak = kategori_ekle(con, kaynak_id="c", ad="KONTAKTÖRLER", yol="7", seviye=0)
    for i, ad in enumerate(SERVO_ADLARI):
        urun_ekle(con, sku=f"SV{i}", ad=ad, kategori_id=servolar, stok=1)
    asenkron = urun_ekle(con, sku="N1", ad=GURULTU[0], kategori_id=motorlar, stok=1)
    _aciklama(con, asenkron, "Üç fazlı asenkron motor; servo motor değildir, sabit hızlı uygulamalar içindir.")
    urun_ekle(con, sku="N2", ad=GURULTU[1], kategori_id=kontak, stok=1)
    urun_ekle(con, sku="N3", ad=GURULTU[2], kategori_id=motorlar, stok=1)
    urun_ekle(con, sku="N4", ad=GURULTU[3], kategori_id=motorlar, stok=1)
    urun_ekle(con, sku="N5", ad=GURULTU[4], kategori_id=motorlar, stok=1)
    kablo = urun_ekle(con, sku="N6", ad="SERVO MOTOR KABLOSU 10M", stok=1)
    kodsuz = urun_ekle(con, sku="N7", ad="FANUC A06B-0235-B605", kategori_id=servolar, stok=1)   # tipi kategoriden
    indeksi_yeniden_kur(con)
    con.commit()
    return kablo, kodsuz


def test_g3h_servo_motor_alakasi(con):
    kablo, kodsuz = _alaka_tohumu(con)
    sonuc = urun_listele(con, ListeSorgusu(arama="servo motor", siralama="alaka"))
    adlar = [u.ad for u in sonuc.urunler]
    assert not set(adlar[:10]) & set(GURULTU), adlar[:10]
    assert set(adlar[:11]) == set(SERVO_ADLARI)              # ad içinde ifade + servo motor tipi önce
    assert kodsuz in _idler(sonuc) and adlar.index("SERVO MOTOR KABLOSU 10M") > 10
    # ifade adda geçen servo motorlar, adında geçmeyen (yalnız kategori/tip) servo motordan önce. G3j madde 7: alaka
    # katmanı tipten önce gelir — adında "servo motor" geçen kablo ve hava motoru da (11, 12) kategoriden eşleşenden önce
    assert _idler(sonuc).index(kodsuz) == 13
    # kontaktör ve asenkron motor hiç eşleşmez ya da en sonda
    for gurultu in GURULTU[:2]:
        assert gurultu not in adlar or adlar.index(gurultu) >= len(SERVO_ADLARI) + 2


def test_g3h_aramada_varsayilan_alaka_web(istemci):
    with istemci_db(istemci) as con:
        _alaka_tohumu(con)
    for dil in ("tr", "en"):
        html = istemci.get(f"/{dil}/ara", params={"q": "servo motor"}).text
        assert '<option value="alaka" selected>' in html
        adlar = _satirlar(html)
        assert not set(adlar[:10]) & set(GURULTU), (dil, adlar[:10])


# =====================================================================================================
# A4 — arama-duyarlı kategori ağacı
# =====================================================================================================

def test_g3h_kategori_agaci_arama_sayilari(istemci):
    with istemci_db(istemci) as con:
        elk = kategori_ekle(con, kaynak_id="k10", ad="Elektrik ve Elektronik", yol="10", seviye=0)
        guc = kategori_ekle(con, kaynak_id="k11", ad="GÜÇ KAYNAKLARI", yol="10.1", seviye=1, ust_kaynak_id="k10")
        rob = kategori_ekle(con, kaynak_id="k12", ad="Endüstriyel Robotlar", yol="12", seviye=0)
        for i in range(3):
            urun_ekle(con, sku=f"G{i}", ad=f"KUKA GÜÇ KAYNAĞI {i}", kategori_id=guc, stok=1)
        urun_ekle(con, sku="R1", ad="KUKA KR 150 ROBOT", kategori_id=rob, stok=1)
        urun_ekle(con, sku="R2", ad="ABB IRB 2400 ROBOT", kategori_id=rob, stok=0)
        indeksi_yeniden_kur(con)
    html = istemci.get("/tr/ara", params={"q": "kuka"}).text
    agac = re.search(r'<details class="agac-kutu".*?</details>', html, re.S).group(0)
    assert re.search(rf'href="/tr/ara\?q=kuka&amp;kat={elk}">Elektrik ve Elektronik <span class="sayi">\(3\)</span>',
                     agac)
    assert re.search(rf'href="/tr/ara\?q=kuka&amp;kat={rob}">Endüstriyel Robotlar <span class="sayi">\(1\)</span>',
                     agac)
    # filtre (stokta yok) + arama: 0 sonuçlu kategoriler gizlenir
    html = istemci.get("/tr/ara", params={"q": "robot", "tedarikli": "1"}).text
    agac = re.search(r'<details class="agac-kutu".*?</details>', html, re.S).group(0)
    assert "Elektrik ve Elektronik" not in agac
    assert re.search(r'Endüstriyel Robotlar <span class="sayi">\(1\)</span>', agac)
    # filtresiz liste: genel sayılar ve düz kategori bağlantıları
    html = istemci.get("/tr/urunler").text
    agac = re.search(r'<details class="agac-kutu".*?</details>', html, re.S).group(0)
    assert re.search(rf'href="/tr/kategori/{rob}">Endüstriyel Robotlar <span class="sayi">\(2\)</span>', agac)
    # filtreli liste: sayılar süzülmüş, bağlantı filtreyi taşır
    html = istemci.get("/tr/urunler", params={"stokta": "1"}).text
    agac = re.search(r'<details class="agac-kutu".*?</details>', html, re.S).group(0)
    assert re.search(rf'href="/tr/kategori/{rob}\?stokta=1">Endüstriyel Robotlar <span class="sayi">\(1\)</span>', agac)


# =====================================================================================================
# B5 — ürün tipi faseti
# =====================================================================================================

@pytest.mark.parametrize("ad,kategoriler,tip", [
    ("FANUC SERVO MOTOR KABLOSU 10M", (), "kablo"),
    ("YASKAWA AC SERVO SÜRÜCÜ", (), "surucu"),
    ("KUKA SERVO MOTOR SÜRÜCÜSÜ", (), "surucu"),
    ("0.37KW ÜÇ FAZLI ASENKRON MOTOR", (), "motor"),
    ("ABB 2,2KW AC SERVO MOTOR", (), "servo_motor"),
    ("ATLAS ENDÜSTRİYEL SERVO MOTOR / HAVA MOTORU", (), "pnomatik"),
    ("ALLEN-BRADLEY 32A ÜÇ KUTUPLU MOTOR KONTAKTÖRÜ", (), "kontaktor_role"),
    ("KUKA KRC2 GÜÇ KAYNAĞI 27V-NT", (), "guc_kaynagi"),
    ("SIEMENS GÜÇ KABLOSU 9.5M", (), "kablo"),
    ("FANUC A06B-0235-B605", ("SERVO MOTORLAR", "ROBOT MOTORLARI"), "servo_motor"),
    ("FANUC A06B-6114-H105", (), "diger"),                   # "fanuc" fan değildir; veri yoksa diğer
    ("PANO SOĞUTMA FANI", (), "fan"),
    ("SIEMENS SIMATIC OP 270 OPERATÖR PANELİ", (), "hmi"),
    ("SIEMENS SIMATIC S7-300 CPU319F-3 İŞLEMCİ", (), "plc"),
    ("KUKA RESOLVER RDC KUTUSU", (), "enkoder"),
    ("ABB FREKANS KONVERTÖRÜ 7,5KW", (), "frekans_konvertoru"),
    ("ABB DSQC 601 SÜRÜCÜ KARTI", (), "surucu"),
    ("ABB DSQC 652 I/O KARTI", (), "kart"),
    ("KUKA KCP2 TEACH PENDANT", (), "teach_pendant"),
    ("YASKAWA REDÜKTÖR RV-80E", (), "reduktor"),
    ("FESTO SELENOİD VALF", (), "valf"),
    ("IFM ENDÜKTİF SENSÖR", (), "sensor"),
    ("SIEMENS 3RV MOTOR KORUMA ŞALTERİ", (), "sigorta_salter"),
    ("BLOCK EMC FİLTRE", (), "filtre"),
    ("KUKA KRC4 AKÜ PAKETİ", (), "aku_pil"),
])
def test_g3h_tip_kural_sirasi(ad, kategoriler, tip):
    from app.katalog.tip import tip_bul
    assert tip_bul(ad, kategoriler) == tip


def test_g3h_tip_etiketleri():
    from app.katalog.tip import sorgu_tipi, tip_adi, tipler
    anahtarlar = [t.anahtar for t in tipler()]
    assert anahtarlar[-1] == "diger" and len(anahtarlar) == len(set(anahtarlar))
    for gerekli in ("servo_motor", "motor", "surucu", "frekans_konvertoru", "guc_kaynagi", "kontaktor_role",
                    "sigorta_salter", "plc", "hmi", "teach_pendant", "kart", "kablo", "enkoder", "reduktor", "sensor",
                    "valf", "filtre", "fan", "aku_pil"):
        assert gerekli in anahtarlar, gerekli
    assert tip_adi("servo_motor", "tr") == "Servo motor" and tip_adi("diger", "en") == "Other"
    assert tip_adi("guc_kaynagi", "en") == "Power supply"
    assert sorgu_tipi("servo motor") == "servo_motor" and sorgu_tipi("fanuc") is None


@pytest.fixture
def tipli(istemci):
    with istemci_db(istemci) as con:
        for i, ad in enumerate(("ABB AC SERVO MOTOR", "KUKA SERVO MOTOR", "KUKA GÜÇ KAYNAĞI", "SIEMENS GÜÇ KAYNAĞI",
                                "KUKA SERVO MOTOR KABLOSU")):
            urun_ekle(con, sku=f"T{i}", ad=ad, stok=1 if i != 1 else 0)
        indeksi_yeniden_kur(con)
    return istemci


def test_g3h_tip_faseti_web(tipli):
    html = sayfa_denetle(tipli.get("/tr/urunler"))
    faset = re.search(r'<fieldset class="faset" data-faset="tip">.*?</fieldset>', html, re.S).group(0)
    assert "<legend>Ürün tipi</legend>" in faset
    assert re.search(r'name="tip" value="servo_motor"> <span class="faset-ad">Servo motor</span> '
                     r'<span class="faset-sayi">2</span>', faset)
    assert re.search(r'value="guc_kaynagi"> <span class="faset-ad">Güç kaynağı</span> <span class="faset-sayi">2</span>',
                     faset)
    html = tipli.get("/tr/urunler", params={"tip": "servo_motor"}).text
    assert sorted(_satirlar(html)) == ["ABB AC SERVO MOTOR", "KUKA SERVO MOTOR"]
    assert re.search(r'<a class="cip" href="/tr/urunler">Ürün tipi: Servo motor', html)
    # faset sayıları diğer fasetlerle tutarlı: stokta seçiliyken servo motor 1; tipin kendi seçimi sayıyı etkilemez
    html = tipli.get("/tr/urunler", params={"tip": "servo_motor", "stokta": "1"}).text
    faset = re.search(r'data-faset="tip">.*?</fieldset>', html, re.S).group(0)
    assert re.search(r'value="servo_motor" checked> <span class="faset-ad">Servo motor</span> '
                     r'<span class="faset-sayi">1</span>', faset)
    assert re.search(r'value="guc_kaynagi"> <span class="faset-ad">Güç kaynağı</span> <span class="faset-sayi">2</span>',
                     faset)
    assert _satirlar(html) == ["ABB AC SERVO MOTOR"]
    en = tipli.get("/en/urunler").text
    assert "<legend>Product type</legend>" in en and '<span class="faset-ad">Power supply</span>' in en
    # bilinmeyen tip değeri yok sayılır
    assert len(_satirlar(tipli.get("/tr/urunler", params={"tip": "yok"}).text)) == 5


def test_g3h_tip_faseti_depo(con):
    for i, ad in enumerate(("ABB AC SERVO MOTOR", "KUKA SERVO MOTOR", "KUKA GÜÇ KAYNAĞI")):
        urun_ekle(con, sku=f"T{i}", ad=ad)
    f = faset_sayilari(con, ListeSorgusu(tipler=("servo_motor",), markalar=("KUKA",)), [])
    assert {x.deger: x.sayi for x in f.tip} == {"servo_motor": 1, "guc_kaynagi": 1}
    assert {x.deger: x.sayi for x in f.marka} == {"ABB": 1, "KUKA": 1}
    assert urun_listele(con, ListeSorgusu(tipler=("servo_motor", "guc_kaynagi"))).toplam == 3


def test_g3h_tip_robots_ve_canonical(istemci_uretim):
    robots = istemci_uretim.get("/robots.txt").text
    assert "Disallow: /*?*tip=" in robots
    html = istemci_uretim.get("/tr/urunler", params={"tip": "servo_motor"}).text
    assert '<link rel="canonical" href="https://shop.example.com/tr/urunler">' in html


def test_g3h_tip_geri_doldurma_betigi(tmp_path, capsys):
    import json

    from app.db import baglan, gecisleri_uygula
    from betikler import turetilmis_doldur
    yol = tmp_path / "shop.db"
    c = baglan(yol)
    gecisleri_uygula(c)
    urun_ekle(c, sku="A", ad="KUKA SERVO MOTOR")
    urun_ekle(c, sku="B", ad="TANIMSIZ PARÇA")
    c.execute("UPDATE urun SET tip = 'diger', katli_metin = ''")
    c.commit()
    c.close()
    assert turetilmis_doldur.main(["--db", str(yol)]) == 0
    ozet = json.loads(capsys.readouterr().out)
    assert ozet["toplam"] == 2 and ozet["dagilim"]["servo_motor"] == 1 and ozet["dagilim"]["diger"] == 1
    assert ozet["diger_orani"] == 0.5
    c = baglan(yol)
    assert c.execute("SELECT tip FROM urun WHERE sku = 'A'").fetchone()[0] == "servo_motor"
    assert c.execute("SELECT katli_metin FROM urun WHERE sku = 'A'").fetchone()[0].startswith("|kukaservomotor|")
    c.close()


# =====================================================================================================
# B6 — Türkçe sayı girişi (fiyat aralığı)
# =====================================================================================================

@pytest.mark.parametrize("dil,girdi,beklenen", [
    ("tr", "10.000", "10000"), ("tr", "10.000,50", "10000.50"), ("tr", "10000", "10000"), ("tr", "10,5", "10.5"),
    ("tr", "1.234.567", "1234567"), ("tr", " 2.500 ₺", "2500"), ("tr", "12.5", "12.5"),
    ("en", "10,000.50", "10000.50"), ("en", "10000", "10000"), ("en", "10.5", "10.5"), ("en", "1,234,567", "1234567"),
])
def test_g3h_sayi_cozumleme(dil, girdi, beklenen):
    from decimal import Decimal

    from app.web.rotalar.katalog import tutar_coz
    assert tutar_coz(girdi, dil) == Decimal(beklenen)


@pytest.mark.parametrize("girdi", ["abc", "10.00.0", "1,2,3", "-5", "10.000,5,0", "1e5"])
def test_g3h_sayi_cozumleme_gecersiz(girdi):
    from app.web.rotalar.katalog import GECERSIZ, tutar_coz
    assert tutar_coz(girdi, "tr") is GECERSIZ


def test_g3h_fiyat_araligi_turkce_web(istemci):
    from datetime import UTC, date, datetime
    from decimal import Decimal

    from app.fiyat.kur import Kur, kur_kaydet
    with istemci_db(istemci) as con:
        urun_ekle(con, sku="P1", ad="UCUZ PARÇA", fiyat="100.00", stok=1)
        urun_ekle(con, sku="P2", ad="ORTA PARÇA", fiyat="400.00", stok=1)
        kur_kaydet(con, Kur(tarih=date(2026, 10, 12), eur_alis=Decimal("35.00"), eur_satis=Decimal("35.20")),
                   datetime(2026, 10, 12, 6, 0, tzinfo=UTC))
    # misafir TR: ₺, KDV dahil. ORTA: 400 × 35,20 × 1,2 = 16.896,00 ₺; UCUZ 4.224,00 ₺
    html = sayfa_denetle(istemci.get("/tr/urunler", params={"fmin": "10.000", "fmax": "20.000,50"}))
    assert _satirlar(html) == ["ORTA PARÇA"]
    assert "En az 10.000,00 ₺" in html and "En çok 20.000,50 ₺" in html
    assert 'value="10.000"' in html                         # kullanıcının yazdığı biçim formda korunur
    html = istemci.get("/tr/urunler", params={"fmin": "abc"}).text
    assert "“abc” fiyat olarak okunamadı; örnek: 10.000 ya da 10.000,50" in html
    assert len(_satirlar(html)) == 2                        # geçersiz değer filtre uygulamaz
    en = istemci.get("/en/urunler", params={"fmin": "10,000.50"}).text
    assert re.search(r'<a class="cip"[^>]*>Min [^<]*10,000\.50', en)


# =====================================================================================================
# B7 — marka listesi: alfabetik, harf başlıklı, seçili üstte
# =====================================================================================================

MARKALAR = ("ABB", "KUKA", "FANUC", "Siemens", "Festo", "SMC", "Pilz", "SICK", "Omron", "Balluff", "Lenze", "Yaskawa")


def test_g3h_marka_listesi_alfabetik_harfli(istemci):
    with istemci_db(istemci) as con:
        for i, marka in enumerate(MARKALAR):
            for j in range(len(MARKALAR) - i):           # ABB en çok, Yaskawa en az ürünlü
                urun_ekle(con, sku=f"M{i}-{j}", ad=f"{marka.upper()} PARÇA {j}", stok=1)
    html = istemci.get("/tr/urunler").text
    faset = re.search(r'data-faset="marka">.*?</fieldset>', html, re.S).group(0)
    ust, daha = faset.split('<details class="faset-daha"')
    # G3k madde 10: üstte ilk 4 (önce 8; filtre sütunu ≤ 1,5 ekran, Durum açık)
    assert re.findall(r'name="marka" value="([^"]+)"', ust) == list(MARKALAR[:4])     # ilk 4: çok ürünlü
    assert "+8 marka daha" in daha
    assert re.findall(r'<p class="faset-harf">(\w)</p>', daha) == ["B", "F", "L", "O", "P", "S", "Y"]
    assert re.findall(r'name="marka" value="([^"]+)"', daha) == ["Balluff", "Festo", "Lenze", "Omron", "Pilz", "SICK",
                                                                  "SMC", "Yaskawa"]
    # seçili marka (az ürünlü) her zaman üstte; "daha" kapalı kalır
    html = istemci.get("/tr/urunler", params={"marka": "Yaskawa"}).text
    faset = re.search(r'data-faset="marka">.*?</fieldset>', html, re.S).group(0)
    ust, daha = faset.split('<details class="faset-daha"')
    assert re.findall(r'name="marka" value="([^"]+)"', ust)[0] == "Yaskawa"
    assert 'value="Yaskawa"' not in daha and not daha.startswith(" open")


# =====================================================================================================
# B8 — varsayılan sıralama "Önerilen" (sorgusuz)
# =====================================================================================================

def test_g3h_onerilen_varsayilan_siralama(istemci):
    with istemci_db(istemci) as con:
        urun_ekle(con, sku="O1", ad="AAA ÜRÜN", stok=0, teklif=True)
        b = urun_ekle(con, sku="O2", ad="ZZZ ÜRÜN", stok=1, gorsel_url="https://www.ceylanrobot.com/g/b.jpg")
        urun_ekle(con, sku="O3", ad="MMM ÜRÜN", stok=1)
        a = urun_ekle(con, sku="O4", ad="BBB ÜRÜN", stok=0)
        con.execute("UPDATE urun SET durum_kodu = 'yeni' WHERE id = ?", (b,))
        con.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)",
                    (b, '{"ozellikler": [["Gerilim", "24 V"]], "bolumler": []}'))
        con.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)", (a, '{"ozellikler": [], "bolumler": []}'))
        indeksi_yeniden_kur(con)                      # inceleme M-6: teknik_var eşitlemede hesaplanır
    html = sayfa_denetle(istemci.get("/tr/urunler"))
    assert '<option value="onerilen" selected>Önerilen</option>' in html
    assert '<option value="ad">Ada göre</option>' in html
    assert _satirlar(html) == ["ZZZ ÜRÜN", "MMM ÜRÜN", "BBB ÜRÜN", "AAA ÜRÜN"]
    assert _satirlar(istemci.get("/tr/urunler", params={"sira": "ad"}).text) == [
        "AAA ÜRÜN", "BBB ÜRÜN", "MMM ÜRÜN", "ZZZ ÜRÜN"]
    en = istemci.get("/en/urunler").text
    assert '<option value="onerilen" selected>Recommended</option>' in en
    # aramada varsayılan alaka kalır; "Önerilen" seçilebilir
    ara = istemci.get("/tr/ara", params={"q": "ürün"}).text
    assert '<option value="alaka" selected>' in ara and '<option value="onerilen">Önerilen</option>' in ara


# =====================================================================================================
# C9–C12 — karşılaştırma: anahtar birleştirme, veri yok sütunu, sınır 5, yalnız farklılıklar
# =====================================================================================================

def _post(istemci, yol, veri, csrf_yolu="/tr/"):
    from tests.conftest import csrf_al
    return istemci.post(yol, data={**veri, "csrf": csrf_al(istemci, csrf_yolu)}, follow_redirects=False)


def _karsilastir(istemci, *urunler, dil="tr"):
    for u in urunler:
        r = _post(istemci, f"/{dil}/karsilastir/ekle", {"urun_id": u, "sonraki": f"/{dil}/karsilastir"},
                  f"/{dil}/karsilastir")
        assert r.status_code == 303


def _teknik(con, urun_id, ozellikler):
    import json
    con.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)",
                (urun_id, json.dumps({"ozellikler": ozellikler, "bolumler": []}, ensure_ascii=False)))


def _tablo(html):
    return re.search(r'<table class="karsilastir-tablo".*?</table>', html, re.S).group(0)


def _satir(tablo, etiket):
    m = re.search(rf'<tr[^>]*>\s*<th scope="row">{re.escape(etiket)}</th>.*?</tr>', tablo, re.S)
    return m.group(0) if m else None


@pytest.fixture
def karsi(istemci):
    with istemci_db(istemci) as con:
        a = urun_ekle(con, sku="KA", ad="KUKA KPP 600-20 GÜÇ KAYNAĞI", stok=1)
        b = urun_ekle(con, sku="KB", ad="KUKA KPS 600-20 GÜÇ KAYNAĞI", stok=1)
        c = urun_ekle(con, sku="KC", ad="FRED KUKA KRC2 GÜÇ KAYNAĞI", stok=1)
        _teknik(con, a, [["Giriş Voltajı (Input)", "400 V"], ["Çıkış Voltajı (Output)", "600 V"],
                         ["Ağırlık", "3,5 kg"]])
        _teknik(con, b, [["Giriş Gerilimi", "400 V"], ["Doğru Akım (DC) Çıkışı", "27 V"], ["Ağırlık", "4 kg"]])
    return {"a": a, "b": b, "c": c}


def test_g3h_karsilastirma_anahtar_birlestirme(istemci, karsi):
    _karsilastir(istemci, karsi["a"], karsi["b"])
    tablo = _tablo(sayfa_denetle(istemci.get("/tr/karsilastir")))
    giris = _satir(tablo, "Giriş Voltajı")
    assert giris and giris.count("400 V") == 2                      # (Input) eki ve "Giriş Gerilimi" aynı satır
    assert "Giriş Voltajı (Input)" not in tablo and _satir(tablo, "Giriş Gerilimi") is None
    cikis = _satir(tablo, "Çıkış Voltajı")
    dc = _satir(tablo, "Doğru Akım (DC) Çıkışı")
    assert cikis and dc and "600 V" in cikis and "27 V" in dc          # anlamı farklı olabilir: birleşmez


def test_g3h_karsilastirma_anahtar_normalize_birim():
    from app.web.karsilastirma import ozellik_anahtari
    assert ozellik_anahtari("Giriş Voltajı (Input)") == ozellik_anahtari("giriş voltajı")
    assert ozellik_anahtari("Giriş Gerilimi") == ozellik_anahtari("Giriş Voltajı")
    assert ozellik_anahtari("Input Voltage (Giriş)") == ozellik_anahtari("Input voltage")   # dil eki (beyaz liste)
    assert ozellik_anahtari("Input Voltage (Nominal)") != ozellik_anahtari("Input voltage")  # nitelik eki korunur
    assert ozellik_anahtari("Input Voltage") == ozellik_anahtari("Input voltage (input)")
    assert ozellik_anahtari("Çıkış Voltajı") != ozellik_anahtari("Doğru Akım (DC) Çıkışı")
    assert ozellik_anahtari("Sönümleme (Yastıklama)") != ozellik_anahtari("Sönümleme")    # Türkçe parantez korunur


def test_g3h_karsilastirma_veri_yok_sutunu(istemci, karsi):
    _karsilastir(istemci, karsi["a"], karsi["b"], karsi["c"])
    html = sayfa_denetle(istemci.get("/tr/karsilastir"))
    tablo = _tablo(html)
    assert "Teknik verisi olan: 2/3 ürün" in tablo
    hucre = re.findall(r'<td rowspan="(\d+)" class="karsilastir-veri-yok"[^>]*>([^<]+)</td>', tablo)
    satir_sayisi = len(re.findall(r'<tr class="teknik-satir"', tablo))
    assert hucre == [(str(satir_sayisi), "Kaynakta teknik veri yok — teknik veri sayfası (datasheet) için teklif isteyin")]
    giris = _satir(tablo, "Giriş Voltajı")
    assert "karsilastir-bos-hucre" not in giris                   # veri yok sütunu "—" ile doldurulmaz
    en = _tablo(istemci.get("/en/karsilastir").text)
    assert "With technical data: 2/3 products" in en
    assert "No technical data in source — request the datasheet via quote" in en


def test_g3h_karsilastirma_hicbirinde_veri_yok(istemci):
    with istemci_db(istemci) as con:
        a = urun_ekle(con, sku="N1", ad="BİRİNCİ", stok=1)
        b = urun_ekle(con, sku="N2", ad="İKİNCİ", stok=1)
    _karsilastir(istemci, a, b)
    tablo = _tablo(istemci.get("/tr/karsilastir").text)
    assert "Teknik verisi olan: 0/2 ürün" in tablo
    assert tablo.count("Kaynakta teknik veri yok — teknik veri sayfası (datasheet) için teklif isteyin") == 2


def test_g3h_karsilastirma_siniri_5(istemci):
    from app.web import karsilastirma
    assert karsilastirma.AZAMI == 5
    with istemci_db(istemci) as con:
        urunler = [urun_ekle(con, sku=f"L{i}", ad=f"ÜRÜN {i}", stok=1) for i in range(6)]
    _karsilastir(istemci, *urunler[:5])
    html = istemci.get("/tr/karsilastir").text
    assert len(re.findall(r'<th scope="col" class="karsilastir-urun"', html)) == 5
    assert "En fazla 5 ürün" in html
    r = _post(istemci, "/tr/karsilastir/ekle", {"urun_id": urunler[5], "sonraki": "/tr/karsilastir"}, "/tr/karsilastir")
    html = istemci.get(r.headers["location"]).text
    assert "Karşılaştırmaya en fazla 5 ürün eklenebilir: ÜRÜN 5 eklendi, en eski ürün (ÜRÜN 0) listeden çıkarıldı." in html
    with istemci_db(istemci) as con:
        yeni = urun_ekle(con, sku="L9", ad="ÜRÜN 9", stok=1)
    _post(istemci, "/tr/karsilastir/kaldir", {"urun_id": urunler[1], "sonraki": "/tr/karsilastir"}, "/tr/karsilastir")
    r = _post(istemci, "/tr/karsilastir/ekle", {"urun_id": yeni, "sonraki": "/tr/karsilastir"}, "/tr/karsilastir")
    assert "Karşılaştırmaya eklendi: ÜRÜN 9 (5/5)." in istemci.get(r.headers["location"]).text
    tr = istemci.get("/tr/karsilastir").text
    assert "en fazla 5 ürünü" in tr                                  # meta açıklama


def test_g3h_karsilastirma_yalniz_farkliliklar_baglantilari(istemci, karsi):
    _karsilastir(istemci, karsi["a"], karsi["b"])
    html = sayfa_denetle(istemci.get("/tr/karsilastir"))
    assert 'name="fark"' not in html                                 # onay kutusu + Uygula yok
    gecis = re.search(r'<nav class="karsilastir-fark".*?</nav>', html, re.S).group(0)
    assert '<a href="/tr/karsilastir" aria-current="page">Tümü</a>' in gecis
    assert '<a href="/tr/karsilastir?fark=1">Yalnız farklılıklar</a>' in gecis
    assert "Garanti / iade" in _tablo(html)
    fark = istemci.get("/tr/karsilastir", params={"fark": "1"}).text
    gecis = re.search(r'<nav class="karsilastir-fark".*?</nav>', fark, re.S).group(0)
    assert '<a href="/tr/karsilastir?fark=1" aria-current="page">Yalnız farklılıklar</a>' in gecis
    tablo = _tablo(fark)
    assert "Garanti / iade" not in tablo                             # iki üründe aynı metin: gizli
    assert _satir(tablo, "Giriş Voltajı") is None                    # 400 V = 400 V
    assert _satir(tablo, "Ağırlık") is not None                      # 3,5 kg ≠ 4 kg
    assert _satir(tablo, "Parça no") is not None


def test_g3h_karsilastir_sayac_baglantisi(istemci, karsi):
    html = istemci.get("/tr/urunler").text
    assert 'data-e2e="karsilastir-git-liste"' not in html
    _karsilastir(istemci, karsi["a"])
    assert 'data-e2e="karsilastir-git-liste"' not in istemci.get("/tr/urunler").text   # 1 ürün: bağlantı yok
    _karsilastir(istemci, karsi["b"])
    for yol in ("/tr/urunler", "/tr/ara?q=kuka", f"/tr/urun/{karsi['c']}"):
        html = sayfa_denetle(istemci.get(yol))
        assert re.search(r'<a class="[^"]*karsilastir-git[^"]*" href="/tr/karsilastir" '
                         r'data-e2e="karsilastir-git-liste">[^<]*(<[^>]+>[^<]*)*Karşılaştır \(2\)', html), yol
    assert "Compare (2)" in istemci.get("/en/urunler").text


# =====================================================================================================
# D13 — liste yoğunluğu: kısa teslim metni, sıkı satır kuralları
# D14 — mobil metin: kısa arama yer tutucusu, 32 px alt bilgi bağlantıları
# D15 — "Kod öneki eşleşmesi": parça no zaten tam kodu gösteriyorsa "tam kod" ipucu yok
# =====================================================================================================

def _css():
    from pathlib import Path
    return (Path(__file__).resolve().parent.parent / "app/web/statik/site.css").read_text(encoding="utf-8")


def _medya_blogu(css, isaret):
    i = css.index(isaret)
    bas = css.index("@media", i)
    derinlik, j = 0, css.index("{", bas)
    while True:
        if css[j] == "{":
            derinlik += 1
        elif css[j] == "}":
            derinlik -= 1
            if derinlik == 0:
                return css[bas:j]
        j += 1


# G3n madde 6: stoktaki üründe kisa=True de ürün sayfasıyla aynı metin (kısa yalnız "ülke seçin" ipucunda)
@pytest.mark.parametrize("ulke,dil,beklenen", [
    ("DE", "tr", "Kargoya veriliş: 1–2 iş günü · varış: 19–23 Ekim (temsili)"),
    ("DE", "en", "Dispatch: 1–2 business days · arrival: Oct 19–23 (indicative)"),
    ("TR", "tr", "Kargoya veriliş: 1–2 iş günü · varış: 15–19 Ekim (temsili)"),
    ("TR", "en", "Dispatch: 1–2 business days · arrival: Oct 15–19 (indicative)"),
    (None, "en", "Delivery date: select country"), (None, "tr", "Teslim tarihi: ülke seçin"),
])
def test_g3h_kisa_teslim_metni(ulke, dil, beklenen):
    import json
    from datetime import date
    from pathlib import Path
    from types import SimpleNamespace

    from app.web.teslim import teslim_metni
    sozluk = json.loads((Path(__file__).resolve().parent.parent / f"app/web/dil/{dil}.json").read_text(encoding="utf-8"))

    def t(anahtar, **k):
        return sozluk[anahtar].format(**k)
    u = SimpleNamespace(teklif_zorunlu=False, stok=3, tedarik_suresi_gun=None)
    assert teslim_metni(u, ulke, date(2026, 10, 13), dil, t, kisa=True) == beklenen
    uzun = teslim_metni(u, ulke, date(2026, 10, 13), dil, t)
    assert (uzun == beklenen) if ulke else (uzun != beklenen)
    stoksuz = SimpleNamespace(teklif_zorunlu=False, stok=0, tedarik_suresi_gun=None)
    assert teslim_metni(stoksuz, ulke, date(2026, 10, 13), dil, t, kisa=True) == t("urun.teslim_tedarik")


def test_g3h_listede_kisa_teslim_urun_sayfasinda_uzun(istemci, monkeypatch):
    from datetime import UTC, datetime

    from app.web import baglam as baglam_modulu
    monkeypatch.setattr(baglam_modulu, "simdi", lambda: datetime(2026, 10, 13, 9, 0, tzinfo=UTC))
    with istemci_db(istemci) as con:
        u = urun_ekle(con, sku="T1", ad="TESLİM ÜRÜNÜ", stok=3)
    html = sayfa_denetle(istemci.get("/tr/urunler"))
    satir = re.search(rf'<tr class="ut-satir[^"]*" id="urun-{u}">.*?</tr>', html, re.S).group(0)
    # G3n madde 6: liste ve ürün sayfası aynı metin
    assert "Kargoya veriliş: 1–2 iş günü · varış: 15–19 Ekim (temsili)" in satir
    urun = istemci.get(f"/tr/urun/{u}").text
    assert "Kargoya veriliş: 1–2 iş günü · varış: 15–19 Ekim (temsili)" in urun


def test_g3h_liste_yogunluk_kurallari():
    css = _css()
    blok = _medya_blogu(css, "G3h madde 13: liste yoğunluğu (masaüstü)")
    assert "min-width: 1024px" in blok
    for kural in (".urun-tablo td { padding: 5px 8px;", ".ut-kodlar .stok-kodu { display: inline;",
                  ".ut-karsilastir .karsilastir-dugme span:not(.gizli)"):
        assert kural in blok, kural
    mobil = _medya_blogu(css, "G3h madde 13: liste yoğunluğu (mobil)")
    assert "max-width: 767px" in mobil and "td.ut-eylem { display: flex;" in mobil


def test_g3h_mobil_arama_yer_tutucusu_ve_alt_baglantilar(istemci):
    tr = istemci.get("/tr/").text
    assert 'placeholder="Parça no veya ürün adı"' in tr
    assert 'placeholder="Part no. or product name"' in istemci.get("/en/").text
    assert re.search(r"\.alt ul a \{[^}]*min-height: 32px", _css())


def test_g3h_kod_oneki_rozetinde_tekrar_eden_tam_kod_yok(istemci):
    with istemci_db(istemci) as con:
        u = urun_ekle(con, sku="3HAC039602-002", ad="ABB SMB KUTUSU", stok=1)
        v = urun_ekle(con, sku="8503053800777", ad="SIEMENS PS307", stok=1, uretici_kodu="6ES7307-1EA00-0AA0")
    for q, uid, kod in (("3HAC0396", u, "3HAC039602-002"), ("6ES7 307", v, "6ES7307-1EA00-0AA0")):
        html = sayfa_denetle(istemci.get("/tr/ara", params={"q": q}))
        satir = re.search(rf'<tr class="ut-satir[^"]*" id="urun-{uid}">.*?</tr>', html, re.S).group(0)
        assert 'data-e2e="onek-eslesme">Parça no ile eşleşti</span>' in satir     # G3k madde 7 metni
        assert "tam kod:" not in satir and satir.count(kod) == 1    # parça no satırda bir kez


def test_g3h_48_urunluk_liste_150_kb_alti(istemci):
    with istemci_db(istemci) as con:
        for i in range(48):
            urun_ekle(con, sku=f"3HAC0{i:05d}-001/0{i % 9}", ad=f"ABB {i},2KW AC SERVO MOTOR İKİNCİ EL TEST EDİLMİŞ {i}",
                      stok=i % 3, uretici_kodu=f"3HAC0{i:05d}-001", gorsel_url="https://www.ceylanrobot.com/g/x.jpg")
        indeksi_yeniden_kur(con)
    r = istemci.get("/tr/urunler", params={"adet": "48"})
    assert len(_satirlar(r.text)) == 48 and len(r.content) < 150 * 1024


# =====================================================================================================
# İnceleme turu 1 (g3h-review.md): C-1, I-1, M-1..M-7
# =====================================================================================================

@pytest.mark.parametrize("a,b", [
    ("Maksimum Kuvvet Fy (Dinamik)", "Maksimum Kuvvet Fy (Statik)"),
    ("İzin Verilebilir Statik Moment (MA,MB)", "İzin Verilebilir Statik Moment (MC)"),
    ("İzin Verilebilir Moment (Mx max)", "İzin Verilebilir Moment (My max)"),
    ("Giriş Gerilimi (Nominal)", "Giriş Gerilimi"),
    ("Boyutlar (G x Y x D)", "Boyutlar (Y x G x D)"),
    ("Çıkış Akımı (AC)", "Çıkış Akımı (DC)"),
    ("Güç (kW)", "Güç (HP)"),
    ("Kuvvet (Maks.)", "Kuvvet"),
    ("S (Standard Backlash)", "S (Standard Lubrication)"),
])
def test_g3h_f1_anahtar_yalniz_dil_eki_atilir_negatif(a, b):
    from app.web.karsilastirma import ozellik_anahtari
    assert ozellik_anahtari(a) != ozellik_anahtari(b), (a, b)


@pytest.mark.parametrize("a,b", [
    ("Giriş Voltajı (Input)", "Giriş Voltajı"), ("Çıkış Gerilimi (Output)", "Çıkış Voltajı"),
    ("Input Voltage (Giriş)", "Input voltage"), ("Output Current (Çıkış)", "Output current"),
    ("Input Voltage (Input)", "Input Voltage"),
])
def test_g3h_f1_anahtar_dil_eki_pozitif(a, b):
    from app.web.karsilastirma import ozellik_anahtari
    assert ozellik_anahtari(a) == ozellik_anahtari(b), (a, b)


def test_g3h_f1_ayni_urunde_iki_etiket_birlesmez(istemci):
    with istemci_db(istemci) as con:
        a = urun_ekle(con, sku="Y1", ad="KIZAK A", stok=1)
        b = urun_ekle(con, sku="Y2", ad="KIZAK B", stok=1)
        _teknik(con, a, [["Giriş Gerilimi", "24 V"], ["Giriş Voltajı (Input)", "230 V"]])   # aynı anahtara düşer
        _teknik(con, b, [["Giriş Voltajı", "48 V"]])
    _karsilastir(istemci, a, b)
    tablo = _tablo(istemci.get("/tr/karsilastir").text)
    assert "24 V; 230 V" not in tablo
    satir = _satir(tablo, "Giriş Gerilimi")
    assert satir and "24 V" in satir and "48 V" in satir
    ikinci = _satir(tablo, "Giriş Voltajı (Input)")
    assert ikinci and "230 V" in ikinci                       # aynı üründeki ikinci etiket ayrı satır, etiketi korunur


def _gevset_tohumu(con, n=4500):
    import random
    rnd = random.Random(7)
    hece = ["ka", "lo", "mi", "re", "su", "ta", "ne", "ro", "vi", "de", "po", "ga"]
    for i in range(n):
        ad = " ".join("".join(rnd.choice(hece) for _ in range(3)) for _ in range(4)).upper()
        con.execute("INSERT INTO urun (sku, ad, kok_kategori_ad, kdv_orani, stok, temsili_fiyat_eur, fiyat_temsili,"
                    " teklif_zorunlu, aktif, olusturma) VALUES (?, ?, 'X', '20', 1, '10.00', 1, 0, 1, 'z')",
                    (f"S{i}", f"{ad} {i}"))
    indeksi_yeniden_kur(con)


def test_g3h_f1_gevsetme_terim_siniri_ve_suresi(istemci):
    import time
    with istemci_db(istemci) as con:
        _gevset_tohumu(con)
    q = " ".join(["kalomi", "rotare"] + [f"x{i}" for i in range(48)])        # 50 terim (VE 0 sonuç)
    istemci.get("/tr/ara", params={"q": "ısınma"})
    t = time.perf_counter()
    html = istemci.get("/tr/ara", params={"q": q}).text
    sure = (time.perf_counter() - t) * 1000
    gevset = re.search(r'<p class="gevset"[^>]*>.*?</p>', html, re.S)
    assert gevset and gevset.group(0).count("<a href=") + gevset.group(0).count(" (0)") <= 5
    assert sure < 300, sure
    tek = " ".join("abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwx")       # 50 tek harf: gevşetme yok
    t = time.perf_counter()
    html = istemci.get("/tr/ara", params={"q": tek}).text
    assert (time.perf_counter() - t) * 1000 < 300 and 'class="gevset"' not in html


def test_g3h_f1_katli_eslesme_kelime_basinda(con):
    a = urun_ekle(con, sku="W1", ad="TABLA 12 V LAMBA")
    b = urun_ekle(con, sku="W2", ad="ABB 24 V 5A MODUL")
    c = urun_ekle(con, sku="W3", ad="KUKA KR C4 GÜÇ KAYNAĞI")
    d = urun_ekle(con, sku="W4", ad="KUKA KRC4 KR16")
    indeksi_yeniden_kur(con)
    assert a not in _idler(urun_listele(con, ListeSorgusu(arama="la12")))
    # eşleşme kelime BAŞINDAN başlar (bitişi kelime ortası olabilir: "24v5" -> "24 V 5A" öneki gibi)
    assert b in _idler(urun_listele(con, ListeSorgusu(arama="24v5")))
    assert b not in _idler(urun_listele(con, ListeSorgusu(arama="4v5a")))
    assert b in _idler(urun_listele(con, ListeSorgusu(arama="24v5a")))          # kelime başından: "24 V 5A"
    sira = _idler(urun_listele(con, ListeSorgusu(arama="KRC4", siralama="alaka")))
    assert set(sira) == {c, d} and sira.index(c) < 2                             # alt dize eşleşmesi alakada adda sayılır


def test_g3h_f1_aciklama_katli_metne_girmez(con):
    u = urun_ekle(con, sku="W5", ad="KUKA FREN DİRENCİ")
    _aciklama(con, u, "Bu parça KRC4 dolabı için uygundur; ölçü 24v5a.")
    indeksi_yeniden_kur(con)
    katli = con.execute("SELECT katli_metin FROM urun WHERE id = ?", (u,)).fetchone()[0]
    assert "uygundur" not in katli and "kukafren" in katli


@pytest.mark.parametrize("ad,tip", [
    ("VOLTAJ REGÜLATÖRÜ", "diger"), ("HIZ REGÜLATÖRÜ", "diger"), ("FESTO BASINÇ REGÜLATÖRÜ", "pnomatik"),
    ("KUKA ROBOT CONTROLLER", "robot"), ("RÖLE SOKETİ", "kontaktor_role"), ("HARD DRIVE 500GB", "diger"),
    ("FAN MOTORU", "fan"), ("SIEMENS S7-300 PLC KARTI", "plc"), ("ELEKTRİKLİ SİLİNDİR", "lineer"),
])
def test_g3h_f1_tip_negatif_vakalar(ad, tip):
    from app.katalog.tip import tip_bul
    assert tip_bul(ad) == tip


def test_g3h_f1_onek_sku_eslesmesinde_stok_kodu_mobilde_gorunur(istemci):
    with istemci_db(istemci) as con:
        u = urun_ekle(con, sku="8503053800777", ad="SIEMENS PS307", stok=1, uretici_kodu="6ES7307-1EA00-0AA0")
    html = istemci.get("/tr/ara", params={"q": "8503053800"}).text
    satir = re.search(rf'<tr class="ut-satir[^"]*" id="urun-{u}">', html).group(0)
    assert "ut-onek-sku" in satir and 'data-e2e="onek-eslesme"' in html and "tam kod" not in html
    kod = istemci.get("/tr/ara", params={"q": "6ES7 307"}).text
    assert "ut-onek-sku" not in kod
    assert re.search(r"\.ut-onek-sku \.ut-kodlar \.stok-kodu \{ display: inline;", _css())


def test_g3h_f1_fark_kipinde_veri_yok_kaybolmaz(istemci):
    with istemci_db(istemci) as con:
        a = urun_ekle(con, sku="F1", ad="BİR", stok=1)
        b = urun_ekle(con, sku="F2", ad="İKİ", stok=1)
        c = urun_ekle(con, sku="F3", ad="ÜÇ", stok=1)
        _teknik(con, a, [["Gerilim", "24 V"]])
        _teknik(con, b, [["Gerilim", "24 V"]])
    _karsilastir(istemci, a, b, c)
    tablo = _tablo(istemci.get("/tr/karsilastir", params={"fark": "1"}).text)
    assert "Teknik verisi olan: 2/3 ürün" in tablo
    assert tablo.count("Kaynakta teknik veri yok — teknik veri sayfası (datasheet) için teklif isteyin") == 1
    assert tablo.count("Teknik değerler aynı") == 2


def test_g3h_f1_geri_doldurma_gecis_uygulamaz(tmp_path, capsys):
    import json
    import shutil

    from app import db as db_modulu
    from app.db import baglan, gecisleri_uygula
    from betikler import turetilmis_doldur
    eski = tmp_path / "gecisler"
    eski.mkdir()
    for dosya in sorted(db_modulu.GECIS_KLASORU.glob("[0-9][0-9][0-9]_*.sql")):
        if dosya.name < "013":
            shutil.copy(dosya, eski / dosya.name)
    yol = tmp_path / "eski.db"
    import unittest.mock
    with unittest.mock.patch.object(db_modulu, "GECIS_KLASORU", eski):
        c = baglan(yol)
        gecisleri_uygula(c)
        c.close()
    assert turetilmis_doldur.main(["--db", str(yol)]) == 2
    cikti = json.loads(capsys.readouterr().out)
    assert cikti["durum"] == "hata" and "013_katli_tip.sql" in cikti["bekleyen_gecisler"]
    assert "gecis_calistir" in cikti["hata"]
    c = baglan(yol)
    assert "013_katli_tip.sql" not in {r[0] for r in c.execute("SELECT dosya FROM sema_surumu")}
    c.close()


def test_g3h_f1_onerilen_teknik_var_sutunu(con):
    a = urun_ekle(con, sku="T1", ad="AAA", stok=1)
    b = urun_ekle(con, sku="T2", ad="BBB", stok=1)
    _teknik(con, b, [["Gerilim", "24 V"]])
    con.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)", (a, '{"ozellikler": [], "bolumler": []}'))
    indeksi_yeniden_kur(con)
    assert dict(con.execute("SELECT sku, teknik_var FROM urun").fetchall()) == {"T1": 0, "T2": 1}
    assert _idler(urun_listele(con, ListeSorgusu(siralama="onerilen"))) == [b, a]
    from app.katalog.depo import ONERILEN_PUAN
    assert "urun_teknik" not in ONERILEN_PUAN and "json" not in ONERILEN_PUAN


def test_g3h_f1_tr_sayfada_en_bicimi_uyari(istemci):
    with istemci_db(istemci) as con:
        urun_ekle(con, sku="P1", ad="PARÇA", stok=1)
    html = istemci.get("/tr/urunler", params={"fmin": "10,000.50"}).text
    assert "“10,000.50” fiyat olarak okunamadı" in html


def test_g3h_f1_liste_satiri_erisilebilir_karsilastir(istemci):
    with istemci_db(istemci) as con:
        u = urun_ekle(con, sku="A1", ad="ERİŞİLEBİLİR ÜRÜN", stok=1)
    html = istemci.get("/tr/urunler").text
    satir = re.search(rf'<tr class="ut-satir[^"]*" id="urun-{u}">.*?</tr>', html, re.S).group(0)
    dugme = re.search(r'<button type="submit" class="karsilastir-dugme"[^>]*>.*?</button>', satir, re.S).group(0)
    assert 'title="Karşılaştır"' in dugme and "<span>Karşılaştır</span>" in dugme
    assert '<span class="gizli">: ERİŞİLEBİLİR ÜRÜN</span>' in dugme
    assert "varış:" in satir or "ülke seçin" in satir
