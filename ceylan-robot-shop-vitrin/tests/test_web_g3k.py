"""G3k: persona tur 6 — A: gerileme şüphesi (1–3), B: arama isabeti (4–7), C: fiyat ve karşılaştırma (8–10),
D: formlar ve sipariş belgeleri (11–19), E: EN ve güven (20–25)."""
import json
import re
from datetime import UTC, datetime
from html import unescape
from pathlib import Path

import pytest

from app.fiyat.kurallar import MusteriTipi
from app.katalog.indeks import indeksi_yeniden_kur
from tests.conftest import csrf_al, istemci_db, sayfa_denetle, urun_ekle  # noqa: F401
from tests.test_web_g3e import _odenmis_siparis
from tests.test_web_g3j import _bildirimler, _hizli, _metin, _satir, _satirlar, _ulke_ve_fiyat
from tests.test_web_sepet_odeme import (GECERLI_VKN, PAROLA, _adres_formu, _giris, _gizli, _kur,  # noqa: F401
                                        _musteri, _odeme_gonder, _sepete_ekle, _urun, db)

KOK = Path(__file__).resolve().parent.parent


def _bolum(html, desen):
    m = re.search(desen, html, re.S)
    assert m, desen
    return m.group(0)


def _gomulu_odeme(istemci, dil="tr", hesap=None, **adres):
    """Girişsiz ödemede gömülü hesapla sipariş (G3g madde 1)."""
    sayfa = istemci.get(f"/{dil}/odeme").text
    form = _adres_formu(**adres)
    form.update(hesap or {})
    for ad in ("csrf", "gosterilen_toplam", "gosterilen_kur"):
        form[ad] = _gizli(sayfa, ad)
    return istemci.post(f"/{dil}/odeme", data=form, follow_redirects=False)


def _alan_degeri(html, ad):
    m = re.search(rf'name="{ad}" type="\w+" value="([^"]*)"', html)
    assert m, ad
    return unescape(m.group(1))


YURTDISI_HESAP = {"hesap_tip": "yurtdisi", "hesap_eposta": "export@ornek.test", "hesap_parola": PAROLA,
                  "hesap_kvkk_onay": "1", "hesap_firma": "Testfirma Automation GmbH", "hesap_ulke": "DE",
                  "hesap_vat_id": "DE123456789"}
YURTDISI_ADRES = {"ulke": "DE", "teslim": "yurtdisi_dap", "teslimat_ad_soyad": "Testfirma Automation GmbH",
                  "teslimat_satir1": "Teststrasse 1", "teslimat_sehir": "Stuttgart", "teslimat_posta_kodu": "70173",
                  "teslimat_ulke": "DE", "teslimat_telefon": "+49 711 000000", "on_bilgi_onay": "",
                  "mesafeli_onay": "", "kosullar_onay": "1", "odeme_yontemi": "havale"}


def _yurtdisi_havale(istemci, db, dil="en"):
    _kur(db)
    uid = _urun(db, sku="S-YDH", ad="Export Ürünü", fiyat="449.00", stok=3)
    _ulke_ve_fiyat(istemci, "DE", "eur", dil)
    _sepete_ekle(istemci, uid, dil=dil)
    r = _gomulu_odeme(istemci, dil, YURTDISI_HESAP, **YURTDISI_ADRES)
    assert r.status_code == 303, r.text[:3000]
    return r.headers["location"].rsplit("/", 1)[1], uid


# =====================================================================================================
# A1 — fatura bilgileri: gömülü hesapla açılan üç hesap tipi
# =====================================================================================================

@pytest.mark.parametrize("tip", ["bireysel", "kurumsal", "yurtdisi"])
def test_g3k_gomulu_hesap_fatura_bilgileri_uc_tip(istemci, db, tip):
    _kur(db)
    uid = _urun(db, sku="S-GF", ad="Gömülü Ürün", fiyat="10.00", stok=5)
    if tip == "yurtdisi":
        _ulke_ve_fiyat(istemci, "DE", "eur", "en")
        _sepete_ekle(istemci, uid, dil="en")
        r = _gomulu_odeme(istemci, "en", YURTDISI_HESAP, **YURTDISI_ADRES)
        dil, beklenen = "en", {"ad": "Testfirma Automation GmbH", "satir1": "Teststrasse 1", "posta_kodu": "70173",
                               "sehir": "Stuttgart", "telefon": "+49 711 000000"}
    else:
        _sepete_ekle(istemci, uid)
        hesap = {"hesap_tip": tip, "hesap_eposta": f"{tip}@ornek.test", "hesap_parola": PAROLA, "hesap_kvkk_onay": "1"}
        if tip == "kurumsal":
            hesap.update(hesap_firma="Anadolu Otomasyon A.Ş.", hesap_vkn=GECERLI_VKN, hesap_vergi_dairesi="Meram")
        r = _gomulu_odeme(istemci, "tr", hesap, teslimat_telefon="+90 332 111 22 33",
                          **({"odeme_yontemi": "havale"} if tip == "kurumsal" else {}))
        dil = "tr"
        beklenen = {"ad": "Anadolu Otomasyon A.Ş." if tip == "kurumsal" else "QATestUser Alıcı",
                    "satir1": "Test Mah. Deneme Sk. No: 1", "posta_kodu": "42250", "sehir": "Konya",
                    "telefon": "+90 332 111 22 33"}
    assert r.status_code == 303, r.text[:2000]
    html = sayfa_denetle(istemci.get(f"/{dil}/hesabim/fatura"))
    for ad, deger in beklenen.items():
        assert _alan_degeri(html, ad) == deger, (tip, ad)


# =====================================================================================================
# A2 — ters ve geçersiz fiyat aralığı uyarısı (liste ve arama, TR + EN)
# =====================================================================================================

def _uyarilar(html):
    return [_metin(x) for x in re.findall(r'<p class="bilgi-kutu fiyat-ters" role="status">(.*?)</p>', html, re.S)]


def _form_uyarilari(html):
    # G3m madde 18: sıfır sonuçta filtre sütunu (fiyat alanları) yok
    if '<fieldset class="alan faset-fiyat-araligi">' not in html:
        return []
    form = _bolum(html, r'<fieldset class="alan faset-fiyat-araligi">.*?</fieldset>')
    return [_metin(x) for x in re.findall(r'<p class="alan-hata fiyat-uyari"[^>]*>(.*?)</p>', form, re.S)]


@pytest.mark.parametrize("yol", ["/{dil}/urunler", "/{dil}/ara?q=servo"])
def test_g3k_fiyat_araligi_uyarilari(istemci, db, yol):
    _kur(db)
    _urun(db, sku="S-FA1", ad="SIEMENS SERVO MOTOR", fiyat="100.00", stok=1)
    for dil, ters, gecersiz in (("tr", "En az > en çok: değerler yer değiştirildi", "Geçersiz fiyat değeri yok sayıldı"),
                                ("en", "Min > max: the values were swapped", "Invalid price value ignored")):
        adres = yol.format(dil=dil)
        ek = "&" if "?" in adres else "?"
        html = sayfa_denetle(istemci.get(adres + ek + "fmin=5000&fmax=1000"))
        # G3m madde 4: uyarı yalnız listenin üstünde (filtre sütunundaki kopya kaldırıldı)
        assert ters in _uyarilar(html) and _form_uyarilari(html) == [], (dil, _uyarilar(html))
        for deger in ("abc", "-5"):
            html = istemci.get(adres + ek + f"fmin={deger}").text
            assert any(u.startswith(gecersiz) and deger in u for u in _uyarilar(html)), (dil, deger)
            assert _form_uyarilari(html) == []


# =====================================================================================================
# A3 — proformada navlun satırı (TR ve yurt dışı)
# =====================================================================================================

def test_g3k_proforma_navlun_satiri_yurtdisi(istemci, db):
    no, _ = _yurtdisi_havale(istemci, db)
    html = sayfa_denetle(istemci.get(f"/en/hesabim/siparis/{no}/proforma"))
    toplam = _bolum(html, r'<dl class="pb-toplam">.*?</dl>')
    assert re.search(r'<dt data-e2e="pb-navlun">Freight</dt><dd>on quotation \(DAP\)</dd>', toplam), toplam
    tr = istemci.get(f"/tr/hesabim/siparis/{no}/proforma").text
    assert re.search(r'<dt data-e2e="pb-navlun">Navlun</dt><dd>teklifle</dd>',
                     _bolum(tr, r'<dl class="pb-toplam">.*?</dl>'))


def test_g3k_proforma_navlun_satiri_tr_kurumsal_yurtdisi_teslim(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-TRD", ad="TR Kurumsal DAP", fiyat="100.00", stok=3)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="trk@ornek.test", vergi_kimlik_no=GECERLI_VKN,
             vergi_dairesi="Selçuk")
    _giris(istemci, "trk@ornek.test")
    _sepete_ekle(istemci, uid)
    r = _odeme_gonder(istemci, ulke="DE", teslim="yurtdisi_dap", odeme_yontemi="havale",
                      sayfa_html=_odeme_gonder(istemci, ulke="DE", teslim="yurtdisi_dap", islem="hesapla").text)
    assert r.status_code == 303, r.text[:2000]
    no = r.headers["location"].rsplit("/", 1)[1]
    html = istemci.get(f"/tr/hesabim/siparis/{no}/proforma").text
    assert 'data-e2e="pb-navlun"' in _bolum(html, r'<dl class="pb-toplam">.*?</dl>')
    # Türkiye içi kargo siparişinde navlun satırı yok
    _sepete_ekle(istemci, uid)
    r = _odeme_gonder(istemci, odeme_yontemi="havale", sayfa_html=_odeme_gonder(istemci, islem="hesapla").text)
    assert r.status_code == 303
    no = r.headers["location"].rsplit("/", 1)[1]
    assert 'data-e2e="pb-navlun"' not in istemci.get(f"/tr/hesabim/siparis/{no}/proforma").text


# =====================================================================================================
# B4 — eşanlam daraltma (tip kısıtlı Almanca terimler)
# =====================================================================================================

@pytest.fixture
def surucu_katalog(istemci):
    adlar = {"servo_surucu": "KUKA SERVO SÜRÜCÜ KSD1-16", "surucu": "ABB SÜRÜCÜ ÜNİTESİ",
             "pnomatik": "FESTO PNÖMATİK SİLİNDİR SÜRÜCÜ", "valf": "FESTO VALF SÜRÜCÜ",
             "fk": "DANFOSS FREKANS KONVERTÖRÜ FC302", "servo_motor": "SIEMENS SERVO MOTOR 1FK7",
             "plc": "SIEMENS S7-300 PLC KONTROLÖR", "kumanda": "KUKA KRC4 ROBOT KUMANDASI",
             "guc": "MEANWELL GÜÇ KAYNAĞI KONTROLÖR", "inverter": "OMRON İNVERTÖR 3G3MX2",
             # fix 1 I-1: kontrol üniteleri (sürücü tipinde) Steuerung'da kalır; valf/pnömatik dışlanır
             "cu": "SIEMENS SINAMICS CU240D-2 KONTROL ÜNİTESİ", "dkc": "REXROTH SERVO SÜRÜCÜ KONTROLÖRÜ DKC03",
             "valf_k": "FESTO KONTROLÖR VALFİ", "pil": "VARTA PİL 3V", "fan": "EBM LÜFTER 24V",
             "valf_pil": "FESTO VALF KONTROLÖR PİL"}
    with istemci_db(istemci) as con:
        for i, (anahtar, ad) in enumerate(adlar.items()):
            urun_ekle(con, sku=f"S-ES{i}", ad=ad, stok=1)
        indeksi_yeniden_kur(con)
        tipler = dict(con.execute("SELECT ad, tip FROM urun").fetchall())
    assert tipler[adlar["pnomatik"]] == "pnomatik" and tipler[adlar["valf"]] == "valf"
    assert tipler[adlar["guc"]] == "guc_kaynagi" and tipler[adlar["valf_k"]] == "valf"
    assert tipler[adlar["valf_pil"]] == "valf" and tipler[adlar["cu"]] == "surucu"
    return adlar, tipler


def test_g3k_esanlam_tip_kisiti(istemci, surucu_katalog):
    adlar, tipler = surucu_katalog

    def ara(q):
        html = sayfa_denetle(istemci.get("/en/ara", params={"q": q}))
        return set(_satirlar(html)), html

    servo, _ = ara("Servoumrichter")
    assert servo == {adlar["servo_surucu"], adlar["dkc"]}, servo         # servo VE sürücü; yalnız "sürücü" değil
    for q in ("Frequenzumrichter", "Umrichter"):
        sonuc, _ = ara(q)
        assert sonuc and {tipler[a] for a in sonuc} == {"frekans_konvertoru"}, (q, sonuc)
        assert adlar["fk"] in sonuc and adlar["servo_surucu"] not in sonuc
    antrieb, _ = ara("Antrieb")
    assert {adlar["servo_surucu"], adlar["surucu"]} <= antrieb
    assert not {tipler[a] for a in antrieb} & {"valf", "sensor", "pnomatik"}, antrieb
    steuerung, _ = ara("Steuerung")
    assert {adlar["plc"], adlar["kumanda"], adlar["cu"], adlar["dkc"]} <= steuerung, steuerung
    assert adlar["valf_k"] not in steuerung and not {tipler[a] for a in steuerung} & {"valf", "pnomatik", "sensor",
                                                                                      "kablo"}, steuerung
    # fix 1 I-1: gevşetmede kısıt yalnız Steuerung ile eşleşen ürünlere: diğer terimin sonuçları daralmaz
    for q, diger in (("Steuerung Batterie", "pil"), ("Steuerung Lüfter", "fan")):
        sonuc, html = ara(q)
        assert 'class="gevset"' in html, q
        assert sonuc == steuerung | {adlar[diger]} | ({adlar["valf_pil"]} if diger == "pil" else set()), (q, sonuc)
    # üç terimde: kısıtlı terim + başka terimle eşleşen (valf tipli) ürün gevşetmede kalır
    sonuc, html = ara("Steuerung Batterie Qzxv")
    assert 'class="gevset"' in html and adlar["valf_pil"] in sonuc and adlar["valf_k"] not in sonuc
    # Türkçe terim kısıtsız (kullanıcının kendi kelimesi)
    surucu, _ = ara("sürücü")
    assert adlar["pnomatik"] in surucu


# =====================================================================================================
# B5 — tek kod jetonlu sorguda tam robot ürünleri parçaların altında
# =====================================================================================================

@pytest.mark.parametrize("q", ["KRC4", "KR C4", "krc4"])
def test_g3k_kod_sorgusunda_robotlar_sonra(istemci, q):
    with istemci_db(istemci) as con:
        robotlar = [urun_ekle(con, sku=f"S-R{i}", ad=f"KUKA KRC4 KR{i}0 R1100", uretici_kodu=f"KRC4-KR{i}0-R1100",
                              kok="Endüstriyel Robotlar", stok=1) for i in range(1, 6)]
        kumanda = urun_ekle(con, sku="8501010100034", ad="KUKA KRC4 ROBOT KUMANDASI", uretici_kodu="00-168-334",
                            kok="Robot Kontrol Üniteleri", stok=1)
        kart = urun_ekle(con, sku="S-KART", ad="KUKA KRC4 GÜVENLİK ARAYÜZ KARTI", uretici_kodu="00-161-116",
                         kok="Robotik Parçaları", stok=1)
        fren = urun_ekle(con, sku="S-FREN", ad="KUKA KRC4 ROBOT FREN DİRENCİ", uretici_kodu="229876",
                         kok="Robotik Parçaları", stok=1)
        indeksi_yeniden_kur(con)
        adlar = dict(con.execute("SELECT id, ad FROM urun").fetchall())
    sira = _satirlar(istemci.get("/tr/ara", params={"q": q}).text)
    konum = {ad: i for i, ad in enumerate(sira)}
    ilk_robot = min(konum[adlar[r]] for r in robotlar)
    assert konum[adlar[kumanda]] == 0, sira                            # kontrolör en üstte
    assert konum[adlar[kart]] < ilk_robot and konum[adlar[fren]] < ilk_robot, sira


def test_g3k_kod_sorgusu_irc5(istemci):
    with istemci_db(istemci) as con:
        urun_ekle(con, sku="S-I1", ad="ABB IRC5 IRB 6700 ROBOT", uretici_kodu="IRC5-IRB6700", kok="Endüstriyel Robotlar")
        urun_ekle(con, sku="S-I2", ad="ABB IRC5 KONTROL KABİNİ", uretici_kodu="3HAC12345", kok="Robot Kontrol Üniteleri")
        urun_ekle(con, sku="S-I3", ad="ABB IRC5 DSQC 652 KART", uretici_kodu="3HAC025917-001", kok="Robotik Parçaları")
        indeksi_yeniden_kur(con)
    sira = _satirlar(istemci.get("/tr/ara", params={"q": "IRC5"}).text)
    assert sira[-1] == "ABB IRC5 IRB 6700 ROBOT" and sira[0] == "ABB IRC5 KONTROL KABİNİ", sira


# =====================================================================================================
# B6 — gevşetmede nadir terim önce
# =====================================================================================================

def test_g3k_gevsetmede_nadir_terim_once(istemci):
    with istemci_db(istemci) as con:
        for ad in ("2.0 USB KABLOSU", "GÖRÜNTÜ AKTARIM KABLOSU", "İNTERNET KABLOSU 1M", "ATLAS GÜÇ KABLOSU",
                   "ABB ENKODER KABLOSU"):
            urun_ekle(con, sku=f"S-K{len(ad)}{ad[:3]}", ad=ad, stok=1)
        urun_ekle(con, sku="S-RS1", ad="KUKA RESOLVER", stok=1)
        urun_ekle(con, sku="S-RS2", ad="YASKAWA RESOLVER ÜNİTESİ", stok=1)
        indeksi_yeniden_kur(con)
    html = istemci.get("/tr/ara", params={"q": "resolver kablosu"}).text
    assert 'class="gevset"' in html
    sira = _satirlar(html)
    assert set(sira[:2]) == {"KUKA RESOLVER", "YASKAWA RESOLVER ÜNİTESİ"}, sira


# =====================================================================================================
# B7 — "Parça no ile eşleşti" rozeti yalnız katlanmış koddan gelen eşleşmede
# =====================================================================================================

def test_g3k_parca_no_rozeti(istemci):
    with istemci_db(istemci) as con:
        cpu = urun_ekle(con, sku="S-CPU", ad="SIEMENS S7-1200 CPU", uretici_kodu="6ES7214-1AG40-0XB0", stok=1)
        robot = urun_ekle(con, sku="S-KR", ad="KUKA KRC4 KR16-2", uretici_kodu="KRC4-KR16-2", stok=1)
        indeksi_yeniden_kur(con)
    html = sayfa_denetle(istemci.get("/tr/ara", params={"q": "6ES7214"}))
    assert re.search(r'<span class="rozet rozet-onek" data-e2e="onek-eslesme">Parça no ile eşleşti</span>',
                     _satir(html, cpu))
    assert "Kod öneki" not in html
    en = istemci.get("/en/ara", params={"q": "6ES7214"}).text
    assert "Matched by part no." in _satir(en, cpu)
    html = istemci.get("/tr/ara", params={"q": "KRC4"}).text
    assert 'data-e2e="onek-eslesme"' not in _satir(html, robot)            # kod adda aynen görünüyor


# =====================================================================================================
# C8 — fiyat aralığı girildiği para birimine bağlı (fpb)
# =====================================================================================================

def test_g3k_fiyat_filtresi_para_birimine_bagli(istemci, db):
    _kur(db)                                    # 1 € = 35 ₺
    ucuz = _urun(db, sku="S-FP1", ad="AAA Ucuz", fiyat="30.00", stok=1)      # 1.260,00 ₺ KDV dahil
    _urun(db, sku="S-FP2", ad="BBB Orta", fiyat="50.00", stok=1)              # 2.100,00 ₺
    _urun(db, sku="S-FP3", ad="CCC Pahalı", fiyat="100.00", stok=1)           # 4.200,00 ₺
    yol = "/tr/urunler?fmin=1000&fmax=2000&fpb=TRY"
    html = sayfa_denetle(istemci.get(yol))
    assert _satirlar(html) == ["AAA Ucuz"]
    form = _bolum(html, r'<form class="filtre".*?</form>')
    assert '<input type="hidden" name="fpb" value="TRY">' in form and "En az (₺)" in form
    _ulke_ve_fiyat(istemci, "TR", "eur")         # gösterim € KDV hariç: filtre ₺ olarak kalır
    html = sayfa_denetle(istemci.get(yol))
    assert _satirlar(html) == ["AAA Ucuz"]
    cipler = _metin(_bolum(html, r'<ul class="cipler".*?</ul>'))
    # fix 1 I-2: karşılık gösterimin kipinde (₺ KDV dahil -> € KDV hariç, %20): 1.000 / 1,2 / 35 = 23,81 €; 50 € (KDV
    # hariç) ürün listede yok ve ≈ üst sınır 47,62 € onun altında (çip ile liste tutarlı)
    assert "En az 1.000,00 ₺" in cipler and "≈ 23,81 € (KDV hariç)" in cipler, cipler
    assert "En çok 2.000,00 ₺" in cipler and "≈ 47,62 € (KDV hariç)" in cipler, cipler
    form = _bolum(html, r'<form class="filtre".*?</form>')
    assert '<input type="hidden" name="fpb" value="TRY">' in form and "En az (₺)" in form
    # fpb yoksa gösterim birimi (€): 1.000–2.000 € aralığında ürün yok
    assert _satirlar(istemci.get("/tr/urunler?fmin=1000&fmax=2000").text) == []
    yeni = istemci.get("/tr/urunler").text
    assert '<input type="hidden" name="fpb" value="EUR">' in yeni
    # fix 1 m-5: fiyat girilmemişse fpb sayfa / sıralama bağlantılarına taşınmaz
    for i in range(30):
        _urun(db, sku=f"S-FPX{i}", ad=f"DDD Doldur {i}", fiyat="10.00", stok=1)
    bos = istemci.get("/tr/urunler?fmin=&fmax=&fpb=TRY").text
    assert "fpb=" not in _bolum(bos, r'<nav class="sayfalama".*?</nav>')
    assert 'name="fpb" value="TRY"' not in _bolum(bos, r'<form class="siralama".*?</form>')
    # geçersiz fpb yok sayılır (gösterim birimi)
    assert _satirlar(istemci.get("/tr/urunler?fmin=20&fmax=40&fpb=XYZ").text) == ["AAA Ucuz"]
    assert ucuz
    from app.web import seo
    assert "Disallow: /*?*fpb=" in seo.robots_metni("uretim", "https://shop.example.com", ()).splitlines()


# =====================================================================================================
# C9 — karşılaştırma fiyat gösterim tercihi; CSV sayısal sütunlar ve teknik satırlar
# =====================================================================================================

def _karsilastir_hazirla(istemci, db):
    _kur(db)
    a = _urun(db, sku="S-KA", ad="YASKAWA SERVO A", fiyat="100.00", stok=1, uretici_kodu="SGM-A")
    b = _urun(db, sku="S-KB", ad="YASKAWA SERVO B", fiyat="50.00", stok=1, uretici_kodu="SGM-B")
    with db:
        db.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)",
                   (a, json.dumps({"ozellikler": [["Güç", "1,3 kW"]], "bolumler": []})))
    for uid in (a, b):
        istemci.post("/tr/karsilastir/ekle", data={"csrf": csrf_al(istemci, "/tr/urunler"), "urun_id": str(uid),
                                                   "sonraki": "/tr/urunler"})
    return a, b


def _fiyat_hucreleri(html, etiket):
    satir = _bolum(html, rf'<th scope="row">{re.escape(etiket)}</th>.*?</tr>')
    return [_metin(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", satir, re.S)]


def test_g3k_karsilastirma_gosterim_tercihi(istemci, db):
    _karsilastir_hazirla(istemci, db)
    _ulke_ve_fiyat(istemci, "TR", "try")
    html = sayfa_denetle(istemci.get("/tr/karsilastir"))
    haric, dahil = _fiyat_hucreleri(html, "Fiyat (KDV hariç)"), _fiyat_hucreleri(html, "Fiyat (KDV dahil)")
    assert haric[0].startswith("Temsili fiyat 3.500,00 ₺") and "≈ 100,00 €" in haric[0], haric
    assert dahil[0].startswith("Temsili fiyat 4.200,00 ₺") and "≈ 120,00 €" in dahil[0], dahil
    assert re.search(r'<small class="fiyat-ikincil">≈ 100,00 €</small>', html)
    _ulke_ve_fiyat(istemci, "TR", "eur")
    html = istemci.get("/tr/karsilastir").text
    haric = _fiyat_hucreleri(html, "Fiyat (KDV hariç)")
    assert haric[0].startswith("Temsili fiyat 100,00 €") and "≈ 3.500,00 ₺" in haric[0], haric
    assert "Fiyat (KDV dahil)" not in html          # G3l madde 20: € (KDV hariç) gösterimde KDV dahil satırı yok


def test_g3k_karsilastirma_csv_sayisal_ve_teknik(istemci, db):
    _karsilastir_hazirla(istemci, db)
    yanit = istemci.get("/tr/karsilastir.csv")
    ham = yanit.content.decode("utf-8")
    assert ham.startswith("\ufeff")

    # G3m madde 14: düz tablo (ürün başına satır, sütun başına alan); sütun -> ürün değerleri
    def sutunlar(ham):
        import csv
        import io
        tablo = list(csv.reader(io.StringIO(ham.lstrip("\ufeff")), delimiter=";"))
        return {ad: [s[i] for s in tablo[1:]] for i, ad in enumerate(tablo[0])}
    satirlar = sutunlar(ham)
    assert satirlar["fiyat_kdv_haric_try"] == ["3500.00", "1750.00"]
    assert satirlar["fiyat_kdv_dahil_try"] == ["4200.00", "2100.00"]
    assert satirlar["fiyat_kdv_haric_eur"] == ["100.00", "50.00"]
    assert "Fiyat (KDV hariç)" not in satirlar
    assert not any("₺" in satirlar[s][i] for s in ("fiyat_kdv_haric_try", "fiyat_kdv_dahil_try") for i in range(2))
    assert satirlar["teknik_guc"][0] == "1,3 kW"                          # teknik özellik CSV'de ayrı sütun
    # fix 1 m-3: Türkiye dışı teslimde (KDV uygulanmaz) KDV dahil sütunu boş
    _ulke_ve_fiyat(istemci, "DE", "try")
    satirlar = sutunlar(istemci.get("/tr/karsilastir.csv").content.decode("utf-8"))
    assert satirlar["fiyat_kdv_dahil_try"] == ["", ""] and satirlar["fiyat_kdv_haric_try"] == ["3500.00", "1750.00"]


# =====================================================================================================
# C10 — Durum grubu açık, "Test edilmiş" çipi yok, birleşim notu
# =====================================================================================================

def test_g3k_durum_grubu_acik_ve_birlesim_notu(istemci, db):
    for i, durum in enumerate(("yeni", "ikinci_el_test_edildi", "belirtilmemis")):
        uid = _urun(db, sku=f"S-DG{i}", ad=f"Durum Ürünü {i}", fiyat="10.00", stok=1)
        with db:
            db.execute("UPDATE urun SET durum_kodu = ? WHERE id = ?", (durum, uid))
    html = sayfa_denetle(istemci.get("/tr/urunler"))
    assert re.search(r'<details class="faset-grup" data-grup="durum" open>', html)
    durum = _bolum(html, r'data-faset="durum">.*?</fieldset>')
    assert 'value="belirtilmemis"' in durum and "Belirtilmemiş" in durum
    # fix 1 m-9: hızlı çip satırı var (Stokta), "Test edilmiş" ürünü olduğu halde onun çipi yok
    hizli = _bolum(html, r'<ul class="hizli-cipler".*?</ul>')
    assert "Stokta" in hizli and "Test edilmiş" not in hizli and "ikinci_el_test_edildi" not in hizli
    form = _bolum(html, r'<form class="filtre".*?</form>')
    assert "Aynı grupta seçenekler ‘veya’, gruplar arasında ‘ve’ ile birleşir." in _metin(form)
    en = istemci.get("/en/urunler").text
    assert "Options in the same group are combined with ‘or’, groups with ‘and’." in _metin(en)


# =====================================================================================================
# D11 — hızlı talep formu: ortak radyo sınıfı, tam genişlik model, telefon ipucu, KVKK bilgi cümlesi
# =====================================================================================================

def test_g3k_hizli_talep_formu(istemci, db):
    html = sayfa_denetle(istemci.get("/tr/ara", params={"q": "ZX-99-YOK"}))
    form = _bolum(html, r'<form class="hizli-teklif".*?</form>')
    radyolar = re.findall(r'<label class="([^"]+)"><input type="radio"[^>]*name="aciliyet"', form)
    assert len(radyolar) == 3 and len(set(radyolar)) == 1 and "aciliyet-secenek" in radyolar[0], radyolar
    assert re.search(r'<div class="alan alan-tam[^"]*">\s*<label for="ht-model">', form)
    assert "“Hat durdu – acil” seçerseniz telefon gerekli" in _metin(form)
    bilgi = _bolum(html, r'<p class="alan-ipucu kvkk-bilgi"[^>]*>.*?</p>')
    assert 'href="/tr/yasal/kvkk"' in bilgi and 'type="checkbox"' not in form
    for ad in ("parca_kodu", "ad", "iletisim", "aciliyet", "adet", "model"):        # alan adları aynı
        assert f'name="{ad}"' in form
    hatali = istemci.post("/tr/teklif/hizli", data={"csrf": csrf_al(istemci, "/tr/teklif"), "ad": "",
                                                    "iletisim": "x", "parca_kodu": "K1"}).text
    assert "“Hat durdu – acil” seçerseniz telefon gerekli" in _metin(hatali)
    assert 'class="alan-ipucu kvkk-bilgi"' in hatali


def test_g3k_hizli_talep_girisli_hesaba_bagli(istemci, db):
    _musteri(db, eposta="tk@ornek.test")
    _hizli(istemci, iletisim="tk@ornek.test")                                # girişsiz: aynı e-postayla bile bağlanmaz
    assert db.execute("SELECT musteri_id FROM teklif").fetchone()[0] is None
    _giris(istemci, "tk@ornek.test")
    r = _hizli(istemci, iletisim="+90 532 000 00 00")
    no = r.headers["location"].split("no=")[1]
    mid = db.execute("SELECT id FROM musteri WHERE eposta = 'tk@ornek.test'").fetchone()[0]
    assert db.execute("SELECT musteri_id FROM teklif WHERE no = ?", (no,)).fetchone()[0] == mid
    tekliflerim = _bolum(istemci.get("/tr/hesabim").text, r'<section aria-labelledby="b-teklif">.*?</section>')
    assert no in tekliflerim and tekliflerim.count('href="/tr/hesabim/teklif/') == 1


# =====================================================================================================
# D12 — onay özeti: "(isteğe bağlı)" yok, ayrı satırlar, tarih biçimi
# =====================================================================================================

def test_g3k_onay_ozeti_satirlari(istemci, db):
    r = _hizli(istemci, aciliyet="acil", adet="3", model="KRC4")
    ozet = _metin(_bolum(istemci.get(r.headers["location"]).text, r'<dl class="teklif-ozet-iletisim".*?</dl>'))
    assert "isteğe bağlı" not in ozet
    for parca in ("Ad soyad Teknisyen", "Adet 3", "Aciliyet Hat durdu – acil", "Robot / kontrolör modeli KRC4"):
        assert parca in ozet, ozet


def test_g3k_istenen_tarih_bicimi(istemci, db):
    _musteri(db, eposta="tarih@ornek.test")
    _giris(istemci, "tarih@ornek.test")
    r = istemci.post("/tr/teklif", data={"csrf": csrf_al(istemci, "/tr/teklif"), "ad": "Ali", "eposta": "a@ornek.test",
                                         "ulke": "TR", "adet": "1", "mesaj": "m", "istenen_tarih": "2026-11-15"},
                     follow_redirects=False)
    assert r.status_code == 303, r.text[:1500]
    no = r.headers["location"].split("no=")[1]
    assert "15.11.2026" in _metin(istemci.get(r.headers["location"]).text)
    assert "2026-11-15" not in _metin(istemci.get(r.headers["location"]).text)
    assert "15.11.2026" in _metin(istemci.get(f"/tr/hesabim/teklif/{no}").text)
    assert "15 Nov 2026" in _metin(istemci.get(f"/en/hesabim/teklif/{no}").text)


# =====================================================================================================
# D13 — ön dolum: teklif formunda telefon, ad soyad unvanla dolmaz; ödemede teslimat faturadan
# =====================================================================================================

def _fatura_kaydet(istemci, **alanlar):
    veri = {"csrf": csrf_al(istemci, "/tr/hesabim/fatura"), "ad": "Deneme Makina A.Ş.", "vergi_dairesi": "Selçuk",
            "satir1": "Test OSB 1. Cadde No:1", "satir2": "", "posta_kodu": "42000", "sehir": "Konya",
            "telefon": "0 (332) 000 00 00"}
    veri.update(alanlar)
    return istemci.post("/tr/hesabim/fatura", data=veri, follow_redirects=False)


def test_g3k_teklif_formu_on_dolum(istemci, db):
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="kd@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    _giris(istemci, "kd@ornek.test")
    assert _fatura_kaydet(istemci).status_code == 303
    html = istemci.get("/tr/teklif").text
    assert re.search(r'name="telefon"[^>]*value="0 \(332\) 000 00 00"', html)
    assert re.search(r'name="firma"[^>]*value="Deneme Makina A.Ş."', html)
    assert re.search(r'<input id="ad" name="ad"[^>]*value=""', html), _bolum(html, r'<input id="ad"[^>]*>')
    istemci.cookies.clear()
    _musteri(db, eposta="bd@ornek.test")
    _giris(istemci, "bd@ornek.test")
    assert re.search(r'<input id="ad" name="ad"[^>]*value="QATestUser bireysel"', istemci.get("/tr/teklif").text)


def test_g3k_odemede_teslimat_faturadan(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-OD", ad="Ödeme Ürünü", fiyat="10.00", stok=3)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="od3@ornek.test", vergi_kimlik_no=GECERLI_VKN,
             vergi_dairesi="Selçuk")
    _giris(istemci, "od3@ornek.test")
    assert _fatura_kaydet(istemci).status_code == 303
    _sepete_ekle(istemci, uid)
    html = istemci.get("/tr/odeme").text
    assert re.search(r'name="teslimat_satir1" type="text" value="Test OSB 1. Cadde No:1"', html)
    assert re.search(r'name="teslimat_sehir" type="text" value="Konya"', html)
    assert re.search(r'name="teslimat_telefon" type="tel" value="0 \(332\) 000 00 00"', html)
    assert re.search(r'name="fatura_ayni" value="1" checked', html)


# =====================================================================================================
# D14 — fatura bilgileri metni ve hata özeti
# =====================================================================================================

def test_g3k_fatura_bilgileri_metin_ve_hata_ozeti(istemci, db):
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="fh@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    _giris(istemci, "fh@ornek.test")
    html = istemci.get("/tr/hesabim/fatura").text
    assert "sonraki siparişlerin fatura adresi buradan doldurulur" in _metin(html) and "buradan dolar." not in html
    r = _fatura_kaydet(istemci, telefon="abc", sehir="")
    assert r.status_code == 400
    ozet = _bolum(r.text, r'<div class="form-hata-ozet".*?</div>')
    assert re.search(r'<a href="#telefon">Telefon: ', ozet) and re.search(r'<a href="#sehir">Şehir', ozet), ozet
    assert 'id="hata-telefon"' in r.text and 'id="hata-sehir"' in r.text


# =====================================================================================================
# D15 — Hesabım sipariş ayrıntısı tutarlar, adresler; listede "Ayrıntı"
# =====================================================================================================

def test_g3k_hesabim_siparis_ayrintisi(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-HS", ad="Hesap Sipariş Ürünü", fiyat="100.00", stok=3)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="hs@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    _giris(istemci, "hs@ornek.test")
    _sepete_ekle(istemci, uid)
    no = _odeme_gonder(istemci, odeme_yontemi="havale").headers["location"].rsplit("/", 1)[1]
    html = sayfa_denetle(istemci.get(f"/tr/hesabim/siparis/{no}"))
    metin = _metin(html)
    for parca in ("Ara toplam (KDV hariç)", "Kargo", "KDV (ürünler)", "KDV (kargo)", "Genel toplam",
                  "Siparişte sabitlenen kur", "Teslimat adresi", "Fatura adresi", "Test Mah. Deneme Sk. No: 1",
                  "Teslim yöntemi", "Kargo (Türkiye içi)", "Ödeme yöntemi", "Ödeme bekliyor"):
        assert parca in metin, parca
    assert re.search(r"Genel toplam [\d.,]+ ₺ · ≈ [\d.,]+ €", metin), metin
    liste = istemci.get("/tr/hesabim").text
    assert re.search(rf'<a href="/tr/hesabim/siparis/{no}"[^>]*data-e2e="siparis-ayrinti">Ayrıntı</a>', liste)


def test_g3k_hesabim_siparis_ayrintisi_yurtdisi_navlun(istemci, db):
    no, _ = _yurtdisi_havale(istemci, db)
    metin = _metin(istemci.get(f"/en/hesabim/siparis/{no}").text)
    assert "Freight quote pending (indicative)" in metin and "Stuttgart" in metin
    assert "Navlun teklifi bekleniyor (temsili)" in _metin(istemci.get(f"/tr/hesabim/siparis/{no}").text)


# =====================================================================================================
# D16 — havale bekleyen sipariş onayı: "Sipariş alındı", son adım etkin, kalem toplam satırları
# =====================================================================================================

def test_g3k_havale_onay_sayfasi(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-HO", ad="Havale Ürünü", fiyat="100.00", stok=3)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="ho@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    _giris(istemci, "ho@ornek.test")
    _sepete_ekle(istemci, uid)
    r = _odeme_gonder(istemci, odeme_yontemi="havale")
    no = r.headers["location"].rsplit("/", 1)[1]
    html = sayfa_denetle(istemci.get(r.headers["location"]))
    assert _metin(_bolum(html, r"<h1>.*?</h1>")) == f"Sipariş alındı · {no}"
    gecerli = _bolum(html, r'<li class="adim gecerli" aria-current="step">.*?</li>')
    assert "Sipariş alındı" in _metin(gecerli) and "4" in _metin(gecerli)
    alt = _metin(_bolum(html, r'<tfoot data-e2e="kalem-toplam">.*?</tfoot>'))
    for parca in ("Ara toplam (KDV hariç)", "Kargo", "KDV", "Genel toplam"):
        assert parca in alt, alt
    en = istemci.get(f"/en/siparis/{no}").text
    assert _metin(_bolum(en, r"<h1>.*?</h1>")) == f"Order received · {no}"


# =====================================================================================================
# D17 — proforma alıcı bloğu, KDV oranı biçimi, ihracat istisnası satırı
# =====================================================================================================

def test_g3k_proforma_alici_ve_kdv(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-PA", ad="Proforma Ürünü", fiyat="100.00", stok=3)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="pa@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    _giris(istemci, "pa@ornek.test")
    _sepete_ekle(istemci, uid)
    r = _odeme_gonder(istemci, odeme_yontemi="havale", teslimat_ad_soyad="Deneme Makina Sanayi A.S.",
                      teslimat_telefon="0 (332) 000 00 00")
    no = r.headers["location"].rsplit("/", 1)[1]
    html = sayfa_denetle(istemci.get(f"/tr/hesabim/siparis/{no}/proforma"))
    alici = _bolum(html, r'<section class="pb-taraf" aria-labelledby="pb-alici">.*?</section>')
    adres = _metin(re.search(r"<dt>Adres</dt><dd>(.*?)</dd>", alici, re.S).group(1))
    assert "Deneme Makina" not in adres and "0 (332)" not in adres and adres.startswith("Test Mah."), adres
    assert re.search(r"<dt>Telefon</dt><dd>0 \(332\) 000 00 00</dd>", alici)
    assert "%20 · " in _metin(_bolum(html, r'<table class="pb-kalemler">.*?</table>'))
    istemci.cookies.clear()
    no_yd, _ = _yurtdisi_havale(istemci, db)
    en = istemci.get(f"/en/hesabim/siparis/{no_yd}/proforma").text
    assert "0% · " in _metin(_bolum(en, r'<table class="pb-kalemler">.*?</table>'))
    assert "VAT: export exemption (legal basis to be written by counsel for production — indicative)" in _metin(en)
    tr = istemci.get(f"/tr/hesabim/siparis/{no_yd}/proforma").text
    assert "%0 · " in _metin(_bolum(tr, r'<table class="pb-kalemler">.*?</table>'))
    assert "KDV: ihracat istisnası (dayanak üretimde hukukça yazılacak — temsili)" in _metin(tr)
    assert "ihracat istisnası (dayanak üretimde hukukça yazılacak" in (KOK / "docs/hukuk-notlari.md").read_text(
        encoding="utf-8")


# =====================================================================================================
# D18 — tekrar sepete ekle: eklenemeyen kalemin nedeni ayrı
# =====================================================================================================

def test_g3k_tekrar_ekle_nedenleri(istemci, db):
    _kur(db)
    kendi = _urun(db, sku="S-TE1", ad="FESTO ARA ELEMAN", fiyat="10.00", stok=1)
    teklif = _urun(db, sku="S-TE2", ad="Teklifli Robot", fiyat="10.00", stok=1)
    pasif = _urun(db, sku="S-TE3", ad="Kalkan Ürün", fiyat="10.00", stok=1)
    baskasi = _urun(db, sku="S-TE4", ad="Başkasının Ayırdığı", fiyat="10.00", stok=1)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="te@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    _giris(istemci, "te@ornek.test")
    _sepete_ekle(istemci, baskasi)
    eski = _odeme_gonder(istemci, odeme_yontemi="havale").headers["location"].rsplit("/", 1)[1]
    with db:                                   # eski sipariş iptal: ayırmaz; ürünü başka müşterinin siparişi ayırır
        db.execute("UPDATE siparis SET durum = 'iptal' WHERE no = ?", (eski,))
    _odenmis_siparis(db, baskasi, 1, datetime.now(UTC).isoformat(), eposta="baska@ornek.test")
    for uid in (kendi, teklif, pasif):
        _sepete_ekle(istemci, uid)
    no = _odeme_gonder(istemci, odeme_yontemi="havale").headers["location"].rsplit("/", 1)[1]
    with db:
        db.execute("UPDATE urun SET teklif_zorunlu = 1 WHERE id = ?", (teklif,))
        db.execute("UPDATE urun SET aktif = 0 WHERE id = ?", (pasif,))

    def tekrar(siparis_no):
        r = istemci.post(f"/tr/hesabim/siparis/{siparis_no}/tekrar",
                         data={"csrf": csrf_al(istemci, f"/tr/hesabim/siparis/{siparis_no}")}, follow_redirects=False)
        assert r.status_code == 303
        html = istemci.get("/tr/sepet").text
        # G3n madde 3: hiçbiri eklenemediyse ve sepet boşsa nedenler "Sepetiniz boş" yerine listede
        blok = re.search(r'<div class="tekrar-nedenler.*?</div>', html, re.S)
        return _bildirimler(html) + (_metin(blok.group(0)) if blok else "")
    bildirim = tekrar(no)
    assert f"FESTO ARA ELEMAN (kendi ödeme bekleyen siparişiniz ({no}) bu stoğu ayırıyor)" in bildirim, bildirim
    assert "Teklifli Robot (teklifle satılır)" in bildirim and "Kalkan Ürün (satıştan kalktı)" in bildirim
    assert "Başkasının Ayırdığı (stokta yok)" in tekrar(eski)


# =====================================================================================================
# D19 — sepet notu ve TL gösterimde mal bedeli satırı
# =====================================================================================================

def test_g3k_sepet_kargo_notu(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-SN", ad="Sepet Notu Ürünü", fiyat="10.00", stok=3)
    _sepete_ekle(istemci, uid)
    ozet = _metin(_bolum(istemci.get("/tr/sepet").text, r'<aside class="siparis-ozeti".*?</aside>'))
    # G3m madde 6: hesaplanmış TR kargoda ürün ve ödemeyle aynı cümle
    assert "Kargo: TR 15 € + KDV (temsili), fabrikadan teslim alırsanız ücretsiz" in ozet and "kesinleşir" not in ozet


def test_g3k_sepet_tl_gosterimde_mal_bedeli_tl(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-SM", ad="Mal Bedeli Ürünü", fiyat="100.00", stok=3)
    _musteri(db, tip=MusteriTipi.YURTDISI, eposta="yd@ornek.test", ulke="DE", vat_id="DE123456789")
    _giris(istemci, "yd@ornek.test", dil="en")
    _ulke_ve_fiyat(istemci, "DE", "try", "en")
    _sepete_ekle(istemci, uid, dil="en")
    ozet = _bolum(istemci.get("/en/sepet").text, r'<dl class="tutar-ozeti">.*?</dl>')
    toplam = _metin(re.search(r'<dd class="toplam tutar">(.*?)</dd>', ozet, re.S).group(1))
    assert toplam.startswith("₺3,500.00") and "≈ €100.00" in toplam, toplam
    assert "<small" in re.search(r'<dd class="toplam tutar">(.*?)</dd>', ozet, re.S).group(1)


# =====================================================================================================
# E20 — çevrilmemiş kaynak açıklama /en'de kapalı <details> içinde
# =====================================================================================================

def test_g3k_cevrilmemis_kaynak_not_en(istemci, db):
    uid = _urun(db, sku="S-KN", ad="SIEMENS SITOP PSE200U", fiyat="10.00", stok=1)
    with db:
        db.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)", (uid, json.dumps(
            {"ozellikler": [["Kanal Sayısı", "4"]], "bolumler": [["Açıklama", "SITOP PSE200U 3 A seçicilik modülü"]]})))
    en = sayfa_denetle(istemci.get(f"/en/urun/{uid}"))
    kutu = _bolum(en, r'<details class="kaynak-not"[^>]*>.*?</details>')
    assert re.search(r'<details class="kaynak-not" data-e2e="kaynak-not">\s*<summary>Original supplier note '
                     r'\(Turkish, not translated\)</summary>', kutu)
    assert 'lang="tr"' in kutu and "seçicilik modülü" in kutu
    disari = en.replace(kutu, "")
    assert "seçicilik modülü" not in disari and "(original Turkish note)" not in disari
    tr = istemci.get(f"/tr/urun/{uid}").text
    assert 'class="kaynak-not"' not in tr and "seçicilik modülü" in tr


# =====================================================================================================
# E21 — LLM taslak açıklama doğrulaması (gösterim katmanı)
# =====================================================================================================

def _taslak(db, uid, metin, dil="tr"):
    with db:
        db.execute("INSERT INTO urun_aciklama (urun_id, dil, metin, kaynak, model, uretildi) VALUES "
                   "(?, ?, ?, 'llm-taslak', 'test', '2026-10-13')", (uid, dil, metin))


def _teknik(db, uid, ozellikler):
    with db:
        db.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)",
                   (uid, json.dumps({"ozellikler": ozellikler, "bolumler": []})))


def test_g3k_taslak_aciklama_dogrulamasi(istemci, db):
    from app.web.aciklama_gosterim import taslak_gosterilir
    servo = _urun(db, sku="S-T1", ad="KUKA 8.5KW SERVO MOTOR", uretici_kodu="KK67Y-YYYY-050", fiyat="10.00", stok=1)
    _teknik(db, servo, [["Nominal Akım", "19.6 A"]])
    _taslak(db, servo, "KUKA 8.5KW SERVO MOTOR parçası.\n\nGüç 8.5 kW, tork 8.5 Nm ve akım 19.6 A değerlerine bakın.")
    html = sayfa_denetle(istemci.get(f"/tr/urun/{servo}"))
    assert "8.5 Nm" not in html and 'data-e2e="aciklama-bilinen"' in html
    assert db.execute("SELECT COUNT(*) FROM urun_aciklama WHERE urun_id = ?", (servo,)).fetchone()[0] == 1  # silinmez
    iyi = _urun(db, sku="S-T2", ad="SIEMENS SITOP 24V 10A", fiyat="10.00", stok=1)
    _teknik(db, iyi, [["Çıkış Gücü", "240 W"]])
    _taslak(db, iyi, "Siemens SITOP güç kaynağı 24V ve 10 A çıkış verir.\n\nÇıkış gücü 240 W.")
    html = sayfa_denetle(istemci.get(f"/tr/urun/{iyi}"))
    assert "Çıkış gücü 240 W." in html
    assert re.search(r'data-e2e="aciklama-taslak">Kaynak verilerden otomatik özet \(kontrol edilmemiş\)</span>', html)
    _taslak(db, iyi, "Siemens SITOP power supply, 24V and 10 A output.", dil="en")
    assert "Auto-generated summary from source data (unverified)" in istemci.get(f"/en/urun/{iyi}").text
    kesik = _urun(db, sku="S-T3", ad="KUKA SERVO MOTOR", fiyat="10.00", stok=1)
    _teknik(db, kesik, [["Tip", "AC"]])
    _taslak(db, kesik, "KUKA servo motor.\n\nğır yük robot kollarının eksenlerini taşır.")
    assert "ğır yük" not in istemci.get(f"/tr/urun/{kesik}").text
    # yardımcı: virgüllü ondalık ve boşluksuz birim aynı jeton
    assert taslak_gosterilir("Güç 8,5 kW.", ["KUKA 8.5KW"], [])
    assert not taslak_gosterilir("Tork 8.5 Nm.", ["KUKA 8.5KW"], [])
    assert not taslak_gosterilir("ağır yük.\n\nıçin", ["X"], [])
    # fix 1 m-1: yazım farkları aynı jeton
    assert taslak_gosterilir("Besleme 24 V.", ["SITOP 24V"], [])
    assert taslak_gosterilir("Besleme 24 V ve 50 Hz.", ["X"], ["3 kV,50 Hz", "24VDC"])
    assert taslak_gosterilir("Hız 1500 rpm, 100 m kablo.", ["KABLO 100M"], ["1.500 rpm"])
    assert taslak_gosterilir("Giriş 400 V.", ["X"], ["3x400V"])


# =====================================================================================================
# E22 — "demo kaydı" rozeti ve açıklaması tekrar etmez
# =====================================================================================================

def test_g3k_ornek_rozet_metni(istemci, db):
    uid = _urun(db, sku="S-OR", ad="Örnek Durumlu", fiyat="10.00", stok=1)
    with db:
        db.execute("UPDATE urun SET durum_kodu = 'yeni', durum_ornek = 1 WHERE id = ?", (uid,))
    en = _metin(_bolum(istemci.get(f"/en/urun/{uid}").text, r'<p class="urun-durum">.*?</p>'))
    assert en == "New demo record condition entered manually for the demo", en
    tr = _metin(_bolum(istemci.get(f"/tr/urun/{uid}").text, r'<p class="urun-durum">.*?</p>'))
    assert tr == "Yeni demo kaydı demo için elle girilmiş durum kaydı", tr


# =====================================================================================================
# E23 — yurt dışı ülkede alıcı saati
# =====================================================================================================

def test_g3k_yurtdisi_saat_dilimi(istemci, db):
    no, uid = _yurtdisi_havale(istemci, db)
    en = _metin(istemci.get(f"/en/siparis/{no}").text)
    assert re.search(r"Payment deadline: \d{1,2} [A-Z][a-z]{2} \d{4} \d\d:\d\d TRT \(\d\d:\d\d CES?T\)", en), en   # G3l m. 10
    # Yaz saati CEST 07:30–17:00, kış saati CET 06:30–16:00. İkisi de TRT 08:30–18:00 karşılığı.
    assert re.search(r"Mon–Fri 08:30–18:00 TRT \((07:30–17:00 CEST|06:30–16:00 CET)\)", en)
    tr = _metin(istemci.get(f"/tr/hesabim/siparis/{no}").text)
    assert re.search(r"\d\d\.\d\d\.\d{4} \d\d:\d\d TSİ \(\d\d:\d\d CES?T\)", tr), tr
    # Türkiye: değişmez; eşlemesi olmayan ülke: UTC
    istemci.cookies.clear()
    assert "Hafta içi 08:30–18:00 (TSİ, UTC+3)" in _metin(istemci.get("/tr/").text)
    _ulke_ve_fiyat(istemci, "AZ", "eur", "en")                     # fix 1 m-4: Bakü (UTC+4)
    assert "Mon–Fri 08:30–18:00 TRT (09:30–19:00 UTC+4)" in _metin(istemci.get("/en/").text)
    from app.web.baglam import calisma_saatleri_metni               # eşlemesi olmayan ülke: UTC
    t = lambda a, **k: istemci.app.state.ceviri.t("en", a, **k)     # noqa: E731
    assert calisma_saatleri_metni("ZZ", t) == "Mon–Fri 08:30–18:00 TRT (05:30–15:00 UTC)"


# =====================================================================================================
# E24 — EN kullanım şartları ihracat başlığı
# =====================================================================================================

def test_g3k_en_ihracat_basligi(istemci):
    en = istemci.get("/en/yasal/kullanim").text
    baslik = _metin(re.search(r'<h2 id="ihracat-export">(.*?)</h2>', en, re.S).group(1))
    assert baslik == "B. Export: business and international terms of sale", baslik
    tr = istemci.get("/tr/yasal/kullanim").text
    assert re.search(r'<h2 id="ihracat-export">', tr)


# =====================================================================================================
# E25 — "Sepete dön" bağlantısı dokunma sınıfı (ölçüm e2e/Playwright)
# =====================================================================================================

def test_g3k_sepete_don_baglantisi(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-SD", ad="Sepete Dön Ürünü", fiyat="10.00", stok=3)
    _musteri(db, eposta="sd@ornek.test")
    _giris(istemci, "sd@ornek.test")
    _sepete_ekle(istemci, uid)
    html = istemci.get("/tr/odeme").text
    assert re.search(r'<a class="sepete-don" href="/tr/sepet">Sepete dön</a>', html)


# =====================================================================================================
# Fix turu 1
# =====================================================================================================

@pytest.mark.parametrize("q", ["KR 210", "kr210"])
def test_g3k_f1_robot_modeli_sorgusunda_robot_once(istemci, q):
    """m-2: robot ailesi + model numarası ("KR 210") robot arıyor: robot önce; kontrolör sorgusu (KR C4) kuralı aynen."""
    with istemci_db(istemci) as con:
        urun_ekle(con, sku="S-UZ", ad="KUKA KR210 ARA UZATMA KOLU", uretici_kodu="KR210-UZ-01", kok="Robotik Parçaları")
        urun_ekle(con, sku="S-RB", ad="KUKA KR 210 R2700 PRIME", uretici_kodu="KR-210-R2700-PRIME",
                  kok="Endüstriyel Robotlar")
        indeksi_yeniden_kur(con)
    assert _satirlar(istemci.get("/tr/ara", params={"q": q}).text)[0] == "KUKA KR 210 R2700 PRIME"


def test_g3k_f1_veri_kalitesi_teknik_denetimleri(istemci, db):
    """I-3: kaynak teknik satırında küçük harfle başlayan (kesik) değer ve Nm = addaki kW; yönetim raporunda, sayılı ve
    ürün bağlantılı. Ürün sayfası değişmez (veri)."""
    from tests.test_web_g3j import _yonetici
    servo = _urun(db, sku="S-VK1", ad="KUKA 8.5KW SERVO MOTOR", fiyat="10.00", stok=1)
    _teknik(db, servo, [["Tork Sınıfı", "8.5 Nm"], ["Hassas Hareket Kontrolü", "ğır yük robot kollarının eksenleri"],
                        ["Nominal Akım", "19.6 A"]])
    temiz = _urun(db, sku="S-VK2", ad="SIEMENS 1,5KW SERVO MOTOR", fiyat="10.00", stok=1)
    _teknik(db, temiz, [["Tork", "7 Nm"], ["Montaj", "Flanşlı"]])
    _yonetici(istemci)
    html = sayfa_denetle(istemci.get("/yonetim/veri-kalitesi"))
    kesik = _bolum(html, r'<section[^>]*data-e2e="vk-kesik".*?</section>')
    assert re.search(r'<span class="yonetim-sayac">1</span>', kesik) and f'href="/tr/urun/{servo}"' in kesik
    assert "ğır yük" in kesik and f'href="/tr/urun/{temiz}"' not in kesik
    tork = _bolum(html, r'<section[^>]*data-e2e="vk-tork".*?</section>')
    assert re.search(r'<span class="yonetim-sayac">1</span>', tork) and f'href="/tr/urun/{servo}"' in tork
    assert f'href="/tr/urun/{temiz}"' not in tork
    from app.katalog.veri_kalitesi import kesik_deger_mi, tork_kw_esit_mi
    assert kesik_deger_mi("aklaşık 41 kg") and not kesik_deger_mi("Yaklaşık 41 kg") and not kesik_deger_mi("24 V")
    assert tork_kw_esit_mi("ABB 8,5 KW MOTOR", "Tork", "8.5 Nm") and not tork_kw_esit_mi("ABB 8.5KW", "Güç", "8.5 Nm")


def test_g3k_f1_havale_adim_ve_toplam_birimi(istemci, db):
    """m-6: havale bekleyen siparişte "Ödeme" adımı tamamlandı sayılmaz; € ana gösterimde toplamlar da € ana."""
    _kur(db)
    uid = _urun(db, sku="S-HA", ad="Havale Adım Ürünü", fiyat="100.00", stok=3)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="ha@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    _giris(istemci, "ha@ornek.test")
    _sepete_ekle(istemci, uid)
    html = istemci.get(_odeme_gonder(istemci, odeme_yontemi="havale").headers["location"]).text
    adimlar = re.findall(r'<li class="adim([^"]*)"', html)
    assert adimlar == [" tamam", " tamam", " bekliyor", " gecerli"], adimlar
    alt = _bolum(html, r'<tfoot data-e2e="kalem-toplam">.*?</tfoot>')
    toplam = _metin(re.search(r'<tr class="toplam">(.*?)</tr>', alt, re.S).group(1))
    assert re.search(r"Genel toplam 1[\d.,]+ € ≈ [\d.,]+ ₺", toplam), toplam
