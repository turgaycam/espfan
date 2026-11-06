"""G3m: persona tur 8 — A: stok ve sipariş dili (1–6), B: B2B metin tutarlılığı (7–11), C: karşılaştırma ve CSV
(12–15), D: arama, sıfır sonuç, formlar (16–26)."""
import csv
import io
import re
from datetime import UTC, datetime, timedelta
from html import unescape
from pathlib import Path

import pytest

from app.fiyat.kurallar import MusteriTipi
from app.katalog.indeks import indeksi_yeniden_kur
from tests.conftest import csrf_al, istemci_db, sayfa_denetle, urun_ekle  # noqa: F401
from tests.test_web_g3e import _baska_musterinin_havalesi, _durum_ata
from tests.test_web_g3j import _bildirimler, _metin, _satir, _satirlar, _ulke_ve_fiyat
from tests.test_web_sepet_odeme import (GECERLI_VKN, PAROLA, _giris, _gizli, _kur, _musteri,  # noqa: F401
                                        _odeme_gonder, _sepete_ekle, _urun, db)

KOK = Path(__file__).resolve().parent.parent


def _bolum(html, desen):
    m = re.search(desen, html, re.S)
    assert m, desen
    return m.group(0)


def _katalog(istemci, adlar, **ortak):
    kimlikler = []
    with istemci_db(istemci) as con:
        for i, (ad, ek) in enumerate(adlar):
            kimlikler.append(urun_ekle(con, sku=ek.pop("sku", f"S-G3M{i}"), ad=ad, **{**ortak, **ek}))
        indeksi_yeniden_kur(con)
    return kimlikler


def _kurumsal_havale(istemci, db, eposta="g3m@ornek.test", stok=1, **urun):
    """Girişli kurumsal müşteri, stok kadar adetli havale siparişi (kendi rezervasyonu stoğun tümü). (no, uid)."""
    _kur(db)
    uid = _urun(db, sku=urun.pop("sku", "S-G3MH"), ad=urun.pop("ad", "Havale Kalemi"), fiyat="100.00", stok=stok)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta=eposta, vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    _giris(istemci, eposta)
    _sepete_ekle(istemci, uid, adet=str(stok))
    r = _odeme_gonder(istemci, odeme_yontemi="havale")
    assert r.status_code == 303, r.text[:2000]
    return r.headers["location"].rsplit("/", 1)[1], uid


# =====================================================================================================
# A1 — "tümü ayrılmış": onay ikonu yok, uyarı ikonu + "Şu an alınabilir stok yok · …" (liste, ürün, karşılaştırma)
# =====================================================================================================

def test_g3m_tumu_ayrilmis_uyari_dili(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3MA", ad="Ayrılmış Servo", fiyat="100.00", stok=2)
    _baska_musterinin_havalesi(db, uid, 2)
    desen = re.compile(r"Şu an alınabilir stok yok · en geç \d\d\.\d\d\.\d{4} \d\d:\d\d \(TSİ\) serbest kalabilir"
                       r" · teklif isteyin")
    urun = sayfa_denetle(istemci.get(f"/tr/urun/{uid}"))
    stok = _bolum(urun, r'<p class="stok-not stok-ayrilmis".*?</p>')
    assert desen.search(_metin(stok)) and "#uyari" in stok and "#kontrol" not in stok, stok
    assert "Stokta" not in _metin(stok)
    liste = sayfa_denetle(istemci.get("/tr/urunler"))
    hucre = _bolum(_satir(liste, uid), r'<td class="ut-stok">.*?</td>')
    assert desen.search(_metin(hucre)) and "#uyari" in hucre and "#kontrol" not in hucre, hucre
    csrf = csrf_al(istemci, "/tr/karsilastir")
    istemci.post("/tr/karsilastir/ekle", data={"csrf": csrf, "urun_id": str(uid)})
    tablo = sayfa_denetle(istemci.get("/tr/karsilastir"))
    stok_satiri = _metin(_bolum(tablo, r'<tr>\s*<th scope="row">Stok</th>.*?</tr>'))
    assert desen.search(stok_satiri), stok_satiri
    assert "Stokta yok" not in stok_satiri
    en = istemci.get(f"/en/urun/{uid}").text
    assert re.search(r"No stock available right now · may be released by .*? at the latest · request a quote",
                     _metin(_bolum(en, r'<p class="stok-not stok-ayrilmis".*?</p>')))


# =====================================================================================================
# A2 + A3 — siparişin kendi kalemi: stok metni yok; havale bekleyende "Sizin için ayrıldı" + ödeme sonrası süre
# =====================================================================================================

def _kalem_notlari(html):
    return [_metin(x) for x in re.findall(r'<span class="not kalem-teslim"[^>]*>(.*?)</span>', html, re.S)]


@pytest.mark.parametrize("yol", ["/tr/siparis/{no}", "/tr/hesabim/siparis/{no}"])
def test_g3m_kendi_siparisin_kalemi_havale_bekleyen(istemci, db, yol):
    no, uid = _kurumsal_havale(istemci, db)
    html = sayfa_denetle(istemci.get(yol.format(no=no)))
    notlar = _kalem_notlari(html)
    # G3n madde 6: ürün sayfasıyla aynı biçim ve gün sayıları
    assert notlar == ["Sizin için ayrıldı (ödeme son tarihine kadar) · Ödeme alındıktan sonra kargoya veriliş: 1–2 iş "
                      "günü · varış: 2–4 iş günü (temsili)"], \
        notlar
    for yasak in ("alınabilir stok yok", "serbest kalabilir", "tümü", "Tahmini varış", "Stokta"):
        assert yasak not in " ".join(notlar), yasak
    en = istemci.get(yol.format(no=no).replace("/tr/", "/en/")).text
    assert _kalem_notlari(en) == ["Reserved for you (until the payment deadline) · After payment is received: "
                                  "dispatch: 1–2 business days · arrival: 2–4 business days (indicative)"], \
        _kalem_notlari(en)


def test_g3m_kendi_siparisin_kalemi_proforma_ve_odenmis(istemci, db):
    no, uid = _kurumsal_havale(istemci, db)
    proforma = _metin(sayfa_denetle(istemci.get(f"/tr/hesabim/siparis/{no}/proforma")))
    for yasak in ("alınabilir stok yok", "serbest kalabilir", "tümü açık", "Sizin için ayrıldı"):
        assert yasak not in proforma, yasak
    with db:
        db.execute("UPDATE siparis SET durum = 'odendi', odeme_zamani = ? WHERE no = ?",
                   (datetime.now(UTC).isoformat(), no))
    for yol in (f"/tr/siparis/{no}", f"/tr/hesabim/siparis/{no}"):
        notlar = _kalem_notlari(istemci.get(yol).text)
        assert len(notlar) == 1 and notlar[0].startswith("Kargoya veriliş: 1–2 iş günü · varış: "), (yol, notlar)
        assert "ayrıl" not in notlar[0] and "Ödeme alındıktan" not in notlar[0]


# =====================================================================================================
# A4 — ters / geçersiz fiyat uyarısı: tek kez, liste başlığından önce, role="status"; filtre sütununda kopya yok
# =====================================================================================================

@pytest.mark.parametrize("yol", ["/tr/urunler", "/tr/ara?q=servo"])
def test_g3m_fiyat_uyarisi_tek_ve_ustte(istemci, db, yol):
    _kur(db)
    _urun(db, sku="S-G3MF", ad="SIEMENS SERVO MOTOR", fiyat="100.00", stok=1)
    ek = "&" if "?" in yol else "?"
    for sorgu, metin in (("fmin=5000&fmax=1000", "En az > en çok: değerler yer değiştirildi"),
                         ("fmin=abc", "Geçersiz fiyat değeri yok sayıldı")):
        html = sayfa_denetle(istemci.get(yol + ek + sorgu))
        assert _metin(html).count(metin) == 1, (sorgu, _metin(html).count(metin))
        kutular = re.findall(r'<p class="bilgi-kutu fiyat-ters" role="status">(.*?)</p>', html, re.S)
        assert len(kutular) == 1 and _metin(kutular[0]).startswith(metin), kutular
        assert html.index('class="bilgi-kutu fiyat-ters"') < html.index('<div class="liste-baslik">'), sorgu
        assert metin not in _bolum(html, r'<fieldset class="alan faset-fiyat-araligi">.*?</fieldset>')


# =====================================================================================================
# A5 — sepet adedi: 0 satırı kaldırır, negatif reddedilir (satır değişmez)
# =====================================================================================================

def test_g3m_sepet_negatif_adet(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3MS", ad="Adet Ürünü", fiyat="10.00", stok=5)
    _sepete_ekle(istemci, uid, adet="2")
    csrf = csrf_al(istemci, "/tr/sepet")
    r = istemci.post("/tr/sepet/adet", data={"csrf": csrf, "urun_id": str(uid), "adet": "-2"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/tr/sepet"
    assert _bildirimler(sayfa_denetle(istemci.get("/tr/sepet"))) == "Geçersiz adet: 1 veya daha büyük tam sayı girin"
    assert db.execute("SELECT adet FROM sepet_kalemi").fetchone()[0] == 2
    istemci.post("/en/sepet/adet", data={"csrf": csrf, "urun_id": str(uid), "adet": "-1"}, follow_redirects=False)
    assert _bildirimler(istemci.get("/en/sepet").text) == "Invalid quantity: enter a whole number of 1 or more"
    istemci.post("/tr/sepet/adet", data={"csrf": csrf, "urun_id": str(uid), "adet": "0"}, follow_redirects=False)
    assert _bildirimler(istemci.get("/tr/sepet").text) == "Adet Ürünü sepetten çıkarıldı."
    assert db.execute("SELECT COUNT(*) FROM sepet_kalemi").fetchone()[0] == 0


# =====================================================================================================
# A6 — kargo / navlun metni: ürün, sepet ve ödeme aynı anahtardan
# =====================================================================================================

KARGO_TR = "Kargo: TR 15 € + KDV (temsili), fabrikadan teslim alırsanız ücretsiz"
NAVLUN = "Navlun teklifle; bu ödemeye dahil değildir."


def test_g3m_kargo_metni_tr(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3MK", ad="Kargo Ürünü", fiyat="10.00", stok=3)
    assert KARGO_TR in _metin(sayfa_denetle(istemci.get(f"/tr/urun/{uid}")))
    _sepete_ekle(istemci, uid)
    ozet = _metin(_bolum(sayfa_denetle(istemci.get("/tr/sepet")), r'<aside class="siparis-ozeti".*?</aside>'))
    assert KARGO_TR in ozet and "değişebilir" not in ozet and "kesinleşir" not in ozet, ozet
    odeme = _metin(_bolum(istemci.get("/tr/odeme").text, r'<aside class="siparis-ozeti".*?</aside>'))
    assert KARGO_TR in odeme, odeme


def test_g3m_navlun_metni_yurtdisi(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3MN", ad="Navlun Ürünü", fiyat="10.00", stok=3)
    _ulke_ve_fiyat(istemci, "DE", "eur", "en")
    tr_cumle = NAVLUN
    en_cumle = "Freight on quotation; not included in this payment."
    assert en_cumle in _metin(sayfa_denetle(istemci.get(f"/en/urun/{uid}")))
    assert tr_cumle in _metin(istemci.get(f"/tr/urun/{uid}").text)
    _sepete_ekle(istemci, uid, dil="en")
    ozet = _metin(_bolum(sayfa_denetle(istemci.get("/en/sepet")), r'<aside class="siparis-ozeti".*?</aside>'))
    assert en_cumle in ozet and "finalised at checkout" not in ozet, ozet
    odeme = _metin(_bolum(istemci.get("/en/odeme").text, r'<aside class="siparis-ozeti".*?</aside>'))
    assert en_cumle in odeme, odeme


# =====================================================================================================
# B7 — belirtilmemiş durumda ticari cayma ve ücretsiz iptal tek, çelişkisiz satır (kurumsal / yurt dışı görünüm)
# =====================================================================================================

BELIRSIZ_TR = ("Ticari alım: cayma hakkı yok. İstisna: durum belirtilmemiş ürünlerde fotoğraf/test raporunu uygun "
               "bulmazsanız siparişi ücretsiz iptal edebilirsiniz (temsili). Fotoğraf/test raporu siparişten sonra 1 iş "
               "günü içinde e-postayla gönderilir.")   # inceleme m1: taahhüt cümlesi
BELIRSIZ_EN = ("Business purchase: no right of withdrawal. Exception: for items whose condition is not specified, if the "
               "photos/test report do not suit you, you can cancel the order free of charge (indicative). The "
               "photos/test report are e-mailed within 1 business day after the order.")


def _bloklar(html):
    """Görünür metin blokları (p, span, li, dd): iç içe olanlar ayrı ayrı."""
    return [_metin(x) for x in re.findall(r"<(?:p|span|li|dd)\b[^>]*>(.*?)</(?:p|span|li|dd)>", html, re.S)]


def _celiski_yok(html, cayma, iptal):
    for blok in _bloklar(html):
        if cayma in blok or iptal in blok:
            assert cayma in blok and iptal in blok, blok


def test_g3m_belirtilmemis_ticari_tek_satir(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3MB", ad="Belirsiz Ürün", fiyat="100.00", stok=3)
    _durum_ata(db, uid, "belirtilmemis")
    # yurt dışı misafir (EN): bireysel satır + ticari satır; ayrı "free of charge" satırı yok
    _ulke_ve_fiyat(istemci, "DE", "eur", "en")
    en = sayfa_denetle(istemci.get(f"/en/urun/{uid}"))
    assert 'data-e2e="durum-guvence"' not in en
    assert BELIRSIZ_EN in _metin(_bolum(en, r'<p class="garanti-satiri".*?</p>'))
    _celiski_yok(en, "no right of withdrawal", "cancel the order free of charge")
    istemci.cookies.clear()
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="b7@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Meram")
    _giris(istemci, "b7@ornek.test")
    tr = sayfa_denetle(istemci.get(f"/tr/urun/{uid}"))
    assert 'data-e2e="durum-guvence"' not in tr
    assert _metin(_bolum(tr, r'<p class="garanti-satiri".*?</p>')) == BELIRSIZ_TR
    _celiski_yok(tr, "cayma hakkı yok", "ücretsiz iptal")
    # bireysel: mevcut (ayrı güvence satırı kalır)
    istemci.cookies.clear()
    _musteri(db, eposta="b7b@ornek.test")
    _giris(istemci, "b7b@ornek.test")
    assert 'data-e2e="durum-guvence"' in istemci.get(f"/tr/urun/{uid}").text


# =====================================================================================================
# B8 — "olduğu gibi" satırı diğer durumlarla aynı kalıp
# =====================================================================================================

def test_g3m_oldugu_gibi_ticari_satir(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3MO", ad="Olduğu Gibi Ürün", fiyat="100.00", stok=3)
    _durum_ata(db, uid, "ikinci_el_oldugu_gibi")
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="b8@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Meram")
    _giris(istemci, "b8@ornek.test")
    tr = sayfa_denetle(istemci.get(f"/tr/urun/{uid}"))
    assert _metin(_bolum(tr, r'<p class="garanti-satiri".*?</p>')) == (
        "Ticari alım: cayma hakkı yok. Olduğu gibi satılır: garanti yok; açık ayıplar teslimden itibaren 2 gün içinde "
        "yazılı bildirilir.")   # inceleme I2
    en = istemci.get(f"/en/urun/{uid}").text
    assert _metin(_bolum(en, r'<p class="garanti-satiri".*?</p>')) == (
        "Business purchase: no right of withdrawal. Sold as is: no warranty; obvious defects must be notified in "
        "writing within 2 days of delivery.")


# =====================================================================================================
# B9 — "2. el" ile "2. el – test edildi" ayrımı: filtrede title + not, rozette title
# =====================================================================================================

IKINCI_EL = "2. el: kullanılmış, test durumu kaynakta belirtilmemiş"
TEST_EDILDI = "Test edilmiş: satıştan önce test edildi"


def test_g3m_ikinci_el_test_edildi_aciklama(istemci, db):
    _kur(db)
    a = _urun(db, sku="S-G3M2", ad="İkinci El Ürün", fiyat="100.00", stok=3)
    b = _urun(db, sku="S-G3M3", ad="Test Edilmiş Ürün", fiyat="100.00", stok=3)
    _durum_ata(db, a, "ikinci_el")
    _durum_ata(db, b, "ikinci_el_test_edildi")
    html = sayfa_denetle(istemci.get("/tr/urunler"))
    faset = _bolum(html, r'<fieldset class="faset" data-faset="durum">.*?</fieldset>')
    # inceleme m3: seçenek title'ı yok (altındaki not aynı metni verir; sayfa boyutu)
    assert 'name="durum" value="ikinci_el"' in faset and "title=" not in faset
    # inceleme m7: not kapalı <details> içinde (filtre sütunu yüksekliği)
    not_ = _bolum(faset, r'<details class="faset-daha durum-aciklama">.*?</details>')
    assert _metin(_bolum(not_, r"<summary>.*?</summary>")) == "2. el ile test edildi farkı"
    assert _metin(_bolum(not_, r'<p class="alan-ipucu">.*?</p>')) == f"{IKINCI_EL} · {TEST_EDILDI}"
    assert f'<span class="rozet rozet-durum" title="{IKINCI_EL}">2. el</span>' in _satir(html, a)
    assert f'title="{TEST_EDILDI}"' in _satir(html, b)
    urun = istemci.get(f"/tr/urun/{a}").text
    assert f'<span class="rozet rozet-durum" title="{IKINCI_EL}">' in urun
    en = istemci.get("/en/urunler").text
    assert "Used: previously used, test status not recorded in the source · Tested: tested before sale" in _metin(en)


# =====================================================================================================
# B10 — tedarikçi notu başlığı içerikle uyumlu; kaynak cümlesi teknik tablonun notu
# =====================================================================================================

def test_g3m_tedarikci_notu_ve_tablo_notu(istemci, db):
    import json
    _kur(db)
    uid = _urun(db, sku="S-G3MT", ad="Teknik Ürün", fiyat="100.00", stok=3)
    with db:
        db.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)",
                   (uid, json.dumps({"ozellikler": [["Güç", "1 kW"]], "bolumler": [["Not", "Tedarikçinin Türkçe notu"]]})))
    kaynak_en = "Values are taken from the source product record and confirmed before ordering."
    en = sayfa_denetle(istemci.get(f"/en/urun/{uid}"))
    detay = _bolum(en, r'<details class="kaynak-not".*?</details>')
    assert _metin(_bolum(detay, r"<summary>.*?</summary>")) == "Original supplier note (Turkish, not translated)"
    assert kaynak_en not in detay
    assert en.index("</table>") < en.index(kaynak_en) < en.index('<details class="kaynak-not"')
    assert _metin(en).count(kaynak_en) == 1
    tr = istemci.get(f"/tr/urun/{uid}").text
    kaynak_tr = "Değerler kaynak ürün kaydından aktarılmıştır; sipariş öncesi teyit edilir."
    assert tr.index("</table>") < tr.index(kaynak_tr) < tr.index("Tedarikçinin Türkçe notu")


# =====================================================================================================
# B11 — stok faseti etiketleri (sayılar değişmez)
# =====================================================================================================

def test_g3m_stok_faseti_etiketleri(istemci, db):
    _kur(db)
    a = _urun(db, sku="S-G3MR", ad="Ayrılan", fiyat="100.00", stok=1)
    _urun(db, sku="S-G3MD", ad="Tedarikli", fiyat="100.00", stok=0)
    _baska_musterinin_havalesi(db, a, 1)
    for dil, ayrilmis, tedarikli in (
            ("tr", "Ayrılmış — en geç 3 iş gününde serbest", "Tedarikli — süre siparişte bildirilir"),
            ("en", "Reserved — released within 3 business days at the latest",
             "On order — lead time stated with the order")):
        html = sayfa_denetle(istemci.get(f"/{dil}/urunler"))
        faset = _bolum(html, r'<fieldset class="faset" data-faset="stok">.*?</fieldset>')
        assert re.search(rf'name="ayrilmis" value="1"> <span class="faset-ad">{ayrilmis}</span> '
                         r'<span class="faset-sayi">1</span>', faset), faset
        assert re.search(rf'name="tedarikli" value="1"> <span class="faset-ad">{tedarikli}</span> '
                         r'<span class="faset-sayi">1</span>', faset), faset


# =====================================================================================================
# C — karşılaştırma ve CSV
# =====================================================================================================

def _teknik(db, uid, ozellikler):
    import json
    with db:
        db.execute("INSERT OR REPLACE INTO urun_teknik (urun_id, veri) VALUES (?, ?)",
                   (uid, json.dumps({"ozellikler": ozellikler, "bolumler": []}, ensure_ascii=False)))


def _karsilastira_ekle(istemci, *kimlikler, dil="tr"):
    csrf = csrf_al(istemci, f"/{dil}/urunler")
    for uid in kimlikler:
        istemci.post(f"/{dil}/karsilastir/ekle", data={"csrf": csrf, "urun_id": str(uid), "sonraki": f"/{dil}/urunler"})


def _uc_servo(db):
    _kur(db)
    a = _urun(db, sku="8101010100001", ad="ABB AC SERVO MOTOR", fiyat="638.00", stok=2, uretici_kodu="3HAC17484-8")
    b = _urun(db, sku="8101010100002", ad="ABB AC SERVO MOTOR", fiyat="412.50", stok=1, uretici_kodu="3HAC17484-10")
    c = _urun(db, sku="8101010100003", ad="KUKA SERVO MOTOR", fiyat="99.99", stok=0, teklif=False)
    _teknik(db, a, [["Nominal Tork", "2,2 Nm"], ["Fren Sistemi", "Var"], ["Güç", "0,7 kW"]])
    _teknik(db, b, [["Nominal Tork", "4,4 Nm"], ["Güç", "0,7 kW"]])
    _teknik(db, c, [["Mil Tipi", "Kamalı"], ["Güç", "0,7 kW"]])
    return a, b, c


def test_g3m_ayni_adli_sutunlar_kodla_ayrilir(istemci, db):
    a, b, c = _uc_servo(db)
    _karsilastira_ekle(istemci, a, b, c)
    html = sayfa_denetle(istemci.get("/tr/karsilastir"))
    for uid, kod in ((a, "3HAC17484-8 · 8101010100001"), (b, "3HAC17484-10 · 8101010100002")):
        th = _bolum(html, rf'<th scope="col" class="karsilastir-urun" id="urun-{uid}">.*?</th>')
        assert _metin(_bolum(th, r'<span class="karsilastir-kod parca-no">.*?</span>')) == kod, th
    th = _bolum(html, rf'<th scope="col" class="karsilastir-urun" id="urun-{c}">.*?</th>')
    assert "karsilastir-kod" not in th                    # adı tek olan sütunda ek satır yok


def test_g3m_yalniz_farkliliklar_tek_urun_satirlari(istemci, db):
    from tests.test_web_g3l import _teknik_satirlar
    a, b, c = _uc_servo(db)
    _karsilastira_ekle(istemci, a, b, c)
    assert {"Fren Sistemi", "Mil Tipi", "Nominal Tork", "Güç"} <= set(_teknik_satirlar(istemci.get("/tr/karsilastir").text))
    fark = sayfa_denetle(istemci.get("/tr/karsilastir?fark=1"))
    assert _teknik_satirlar(fark) == ["Nominal Tork"], _teknik_satirlar(fark)
    bag = _bolum(fark, r'<p class="karsilastir-tek".*?</p>')
    assert _metin(bag) == "Yalnız tek üründe bulunan 2 özellik gizlendi — göster", bag
    assert 'href="/tr/karsilastir?fark=1&amp;tek=1"' in bag
    assert fark.index('class="karsilastir-tek"') < fark.index('data-e2e="karsilastir-tablo"')
    goster = sayfa_denetle(istemci.get("/tr/karsilastir?fark=1&tek=1"))
    assert set(_teknik_satirlar(goster)) == {"Nominal Tork", "Fren Sistemi", "Mil Tipi"}, _teknik_satirlar(goster)
    assert 'href="/tr/karsilastir?fark=1"' in _bolum(goster, r'<p class="karsilastir-tek".*?</p>')
    en = istemci.get("/en/karsilastir?fark=1").text
    assert _metin(_bolum(en, r'<p class="karsilastir-tek".*?</p>')) == "2 attributes found in only one product hidden — show"


CSV_SUTUNLARI = ["urun_id", "sku", "parca_no", "ad", "marka", "durum", "stok_adet", "alinabilir_adet", "teslim_gun_min",
                 "teslim_gun_max", "fiyat_kdv_haric_try", "fiyat_kdv_dahil_try", "fiyat_kdv_haric_eur", "fiyat_temsili",
                 "para_birimi_notu", "url"]


def _csv(istemci, yol="/tr/karsilastir.csv"):
    r = istemci.get(yol)
    assert r.status_code == 200 and r.content.startswith("﻿".encode())
    return list(csv.reader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))


def test_g3m_csv_duz_tablo(istemci, db):
    a, b, c = _uc_servo(db)
    with db:
        db.execute("UPDATE urun SET ad = '=HYPERLINK(1)' WHERE id = ?", (c,))
    _baska_musterinin_havalesi(db, a, 1)
    _karsilastira_ekle(istemci, a, b, c)
    satirlar = _csv(istemci)
    baslik = satirlar[0]
    assert baslik[:len(CSV_SUTUNLARI)] == CSV_SUTUNLARI, baslik
    assert all(re.fullmatch(r"[a-z0-9_]+", s) for s in baslik), baslik
    teknik = baslik[len(CSV_SUTUNLARI):]
    assert {"teknik_nominal_tork", "teknik_fren_sistemi", "teknik_guc", "teknik_mil_tipi"} == set(teknik), teknik
    assert len(satirlar) == 1 + 3                                       # ürün başına bir satır
    kayit = {int(s[0]): dict(zip(baslik, s)) for s in satirlar[1:]}
    assert kayit[a]["sku"] == "8101010100001" and kayit[a]["parca_no"] == "3HAC17484-8"
    assert kayit[a]["stok_adet"] == "2" and kayit[a]["alinabilir_adet"] == "1"
    assert kayit[a]["fiyat_kdv_haric_eur"] == "638.00" and kayit[b]["fiyat_kdv_haric_eur"] == "412.50"
    assert kayit[a]["fiyat_kdv_haric_try"] == "22330.00" and kayit[a]["fiyat_kdv_dahil_try"] == "26796.00"
    assert kayit[a]["fiyat_temsili"] == "1" and kayit[a]["marka"] == "ABB"
    assert kayit[a]["teknik_fren_sistemi"] == "Var" and kayit[b]["teknik_fren_sistemi"] == ""
    assert kayit[a]["url"].endswith(f"/tr/urun/{a}")
    assert kayit[c]["ad"] == "'=HYPERLINK(1)"                           # enjeksiyon koruması
    assert "1 € = 35,0000 ₺" in kayit[a]["para_birimi_notu"] and "KDV hariç" in kayit[a]["para_birimi_notu"]
    assert all(re.fullmatch(r"\d+\.\d{2}|", kayit[u][s]) for u in kayit for s in
               ("fiyat_kdv_haric_try", "fiyat_kdv_dahil_try", "fiyat_kdv_haric_eur"))


def test_g3m_karsilastirma_fiyat_satirlari_rozet(istemci, db):
    a, b, _ = _uc_servo(db)
    _karsilastira_ekle(istemci, a, b)
    html = sayfa_denetle(istemci.get("/tr/karsilastir"))
    for etiket in ("Fiyat (KDV hariç)", "Fiyat (KDV dahil)"):
        satir = _bolum(html, rf'<th scope="row">{re.escape(etiket)}</th>.*?</tr>')
        assert satir.count('class="rozet rozet-temsili"') == 2, (etiket, satir)
    haric = _bolum(html, r'<th scope="row">Fiyat \(KDV hariç\)</th>.*?</tr>')
    dahil = _bolum(html, r'<th scope="row">Fiyat \(KDV dahil\)</th>.*?</tr>')
    euro = lambda s: re.findall(r"≈ ([\d.]+,\d{2}) €", _metin(s))  # noqa: E731
    from decimal import Decimal
    for h, d in zip(euro(haric), euro(dahil)):
        hx, dx = (Decimal(x.replace(".", "").replace(",", ".")) for x in (h, d))
        assert dx == (hx * Decimal("1.2")).quantize(Decimal("0.01")), (h, d)
    assert euro(haric) == ["638,00", "412,50"]


# =====================================================================================================
# D16 — Almanca terimler ve bitişik / ayrık yazım eşdeğerliği
# =====================================================================================================

def test_g3m_almanca_ve_bitisik_ayrik(istemci):
    _katalog(istemci, [("SIEMENS SERVOMOTOR 1FK7", {}), ("ABB SERVO MOTOR", {}), ("KUKA SERVO MOTORU", {}),
                       ("YASKAWA SERVO SÜRÜCÜ MOTOR KABLOSU", {}), ("ASENKRON MOTOR", {}),
                       ("KUKA ROBOT KR16", {}), ("ABB ROBOT KONTROL ÜNİTESİ", {}), ("ELEKTRİK PANOSU", {}),
                       ("KUKA KONTROL KABİNİ KRC4", {}), ("FESTO VALF", {})], stok=1)

    def ara(q, dil="tr"):
        return sorted(_satirlar(sayfa_denetle(istemci.get(f"/{dil}/ara", params={"q": q}))))
    for dil in ("tr", "en"):
        assert ara("Servomotor", dil) == ara("servo motor", dil) == ara("servo-motor", dil), dil
        assert "YASKAWA SERVO SÜRÜCÜ MOTOR KABLOSU" in ara("Servomotor", dil)
        assert "ASENKRON MOTOR" not in ara("Servomotor", dil)
        assert ara("Roboter", dil) == ara("robot", dil) and ara("Roboter", dil), dil
        pano = ara("Schaltschrank", dil)
        assert {"ELEKTRİK PANOSU", "KUKA KONTROL KABİNİ KRC4"} <= set(pano) and "FESTO VALF" not in pano, pano


# =====================================================================================================
# D17 — yakın kodlar: en çok 5, ortak önek kısaldıkça doldurulur (en az 5 karakter)
# =====================================================================================================

def test_g3m_yakin_kodlar_doldurulur(istemci):
    kodlar = {"6ES7215-1AG40-0XB0": "SIEMENS CPU 1215C", "6ES7211-1AE40-0XB0": "SIEMENS CPU 1211C",
              "6ES7231-4HD32-0XB0": "SIEMENS SM 1231", "6ES7241-1CH32-0XB0": "SIEMENS CM 1241",
              "6ES7253-1AA22-0XA0": "SIEMENS SM 1253", "6ES7261-4XX00-0XA0": "SIEMENS SM 1261",
              "6ES7315-2AG10-0AB0": "SIEMENS CPU 315-2"}
    _katalog(istemci, [(ad, {"uretici_kodu": kod}) for kod, ad in kodlar.items()], stok=1)
    blok = _bolum(istemci.get("/tr/ara", params={"q": "6ES7214"}).text, r'<div class="yakin-kodlar".*?</div>')
    ogeler = [_metin(x) for x in re.findall(r"<li>(.*?)</li>", blok, re.S)]
    assert len(ogeler) == 5, ogeler
    assert ogeler[0].startswith("6ES7211") and ogeler[1].startswith("6ES7215"), ogeler   # en uzun önek önce
    assert not any(o.startswith("6ES7315") for o in ogeler)                             # 4 karakter: kural korunur


# =====================================================================================================
# D18 — sıfır sonuç: boş "Kategoriler" ve fiyat filtresi yok; filtre sütunu yerine "Parçayı bizim için bulun"
# =====================================================================================================

def test_g3m_sifir_sonuc_yan_sutun(istemci):
    _katalog(istemci, [("FESTO VALF", {})], stok=1)
    html = sayfa_denetle(istemci.get("/tr/ara", params={"q": "zzxqv"}))
    yan = _bolum(html, r'<aside class="yan[^"]*".*?</aside>')
    assert 'name="fmin"' not in html and 'class="agac-kutu"' not in html and "Kategoriler" not in _metin(yan), yan
    assert _metin(_bolum(yan, r"<h2[^>]*>.*?</h2>")) == "Parçayı bizim için bulun"
    assert 'href="/tr/teklif?kod=zzxqv"' in yan
    assert 'class="hizli-teklif"' in html                          # kısa talep formu sonuç alanında kalır
    en = istemci.get("/en/ara", params={"q": "zzxqv"}).text
    assert _metin(_bolum(_bolum(en, r'<aside class="yan[^"]*".*?</aside>'), r"<h2[^>]*>.*?</h2>")) == "Let us find the part"
    dolu = istemci.get("/tr/ara", params={"q": "festo"}).text
    assert 'name="fmin"' in dolu                                   # sonuçlu sayfada filtre sütunu aynı


# =====================================================================================================
# D19 — boş fiyat parametreleri 302 ile temizlenir
# =====================================================================================================

@pytest.mark.parametrize("giris,hedef", [
    ("/tr/urunler?fmin=&fmax=&fpb=TRY&stokta=1", "/tr/urunler?stokta=1"),
    ("/tr/urunler?fmin=&fmax=&fpb=TRY", "/tr/urunler"),
    ("/tr/ara?q=valf&fmin=&fmax=&fpb=EUR&marka=FESTO", "/tr/ara?q=valf&marka=FESTO"),
    ("/tr/urunler?fmin=100&fmax=&fpb=TRY", "/tr/urunler?fmin=100&fpb=TRY"),
    ("/en/urunler?fpb=EUR&sira=ad", "/en/urunler?sira=ad"),
])
def test_g3m_bos_fiyat_parametreleri_302(istemci, giris, hedef):
    _katalog(istemci, [("FESTO VALF", {})], stok=1)
    r = istemci.get(giris, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == hedef, (r.status_code, r.headers.get("location"))
    assert istemci.get(hedef, follow_redirects=False).status_code == 200


def test_g3m_dolu_fiyat_parametresi_yonlendirilmez(istemci):
    _katalog(istemci, [("FESTO VALF", {})], stok=1)
    assert istemci.get("/tr/urunler?fmin=10&fmax=200&fpb=TRY", follow_redirects=False).status_code == 200


# =====================================================================================================
# D20 — hızlı talep formu yerleşimi (CSS; ölçüm Playwright ile rapora)
# =====================================================================================================

def test_g3m_hizli_talep_yerlesim_css():
    css = (KOK / "app/web/statik/site.css").read_text(encoding="utf-8")
    assert re.search(r"\.hizli-teklif \.aciliyet legend \{[^}]*white-space: nowrap", css)
    assert re.search(r"\.hizli-teklif \.aciliyet \.secim \{[^}]*display: flex", css)
    assert re.search(r"\.hizli-teklif \.adet-alani \{[^}]*min-width: 8ch", css)
    assert re.search(r"\.bos-teklif \.hizli-teklif \{[^}]*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)", css)


# =====================================================================================================
# D21 — teklif formu ön dolum: ilgili kişi adı ve telefon (adres ya da son siparişin alıcı anlık görüntüsü)
# =====================================================================================================

def _alan(html, ad):
    m = re.search(rf'<input id="{ad}" name="{ad}"[^>]*value="([^"]*)"', html)
    return unescape(m.group(1)) if m else None


def test_g3m_teklif_on_dolum_ilgili_kisi(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3MTK", ad="Teklif Ürünü", fiyat="10.00", stok=3)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="d21@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Meram")
    _giris(istemci, "d21@ornek.test")
    _sepete_ekle(istemci, uid)
    r = _odeme_gonder(istemci, odeme_yontemi="havale", teslimat_ad_soyad="Ayşe Yılmaz",
                      teslimat_telefon="+90 332 111 22 33")
    assert r.status_code == 303
    html = istemci.get("/tr/teklif").text
    assert _alan(html, "ad") == "Ayşe Yılmaz" and _alan(html, "telefon") == "+90 332 111 22 33"
    assert _alan(html, "firma") == "QATestUser kurumsal"
    with db:
        db.execute("DELETE FROM adres")                       # adres kaydı yok: son siparişin anlık görüntüsü
    html = istemci.get("/tr/teklif").text
    assert _alan(html, "ad") == "Ayşe Yılmaz" and _alan(html, "telefon") == "+90 332 111 22 33"


# =====================================================================================================
# D22 — teklif detayı: yanıt süresi ve durum geçmişi
# =====================================================================================================

def test_g3m_teklif_detayi_yanit_suresi_ve_gecmis(istemci, db):
    _musteri(db, eposta="d22@ornek.test")
    _giris(istemci, "d22@ornek.test")
    r = istemci.post("/tr/teklif", data={"csrf": csrf_al(istemci, "/tr/teklif"), "ad": "Ali", "eposta": "d22@ornek.test",
                                         "ulke": "TR", "adet": "1", "mesaj": "Fiyat lütfen"}, follow_redirects=False)
    assert r.status_code == 303, r.text[:1500]
    no = db.execute("SELECT no FROM teklif").fetchone()[0]
    html = sayfa_denetle(istemci.get(f"/tr/hesabim/teklif/{no}"))
    ust = _metin(_bolum(html, r'<p class="siparis-ust">.*?</p>'))
    assert "Yanıt süresi: 1 iş günü (temsili)" in ust, ust
    gecmis = [_metin(x) for x in re.findall(r"<li>(.*?)</li>", _bolum(html, r'<ol class="durum-gecmisi" '
                                                                          r'data-e2e="teklif-gecmisi">.*?</ol>'), re.S)]
    assert len(gecmis) == 1 and re.fullmatch(r"Talep oluşturuldu \d\d\.\d\d\.\d{4} \d\d:\d\d \(TSİ\)", gecmis[0]), gecmis
    with db:
        db.execute("UPDATE teklif SET durum = 'teklif_verildi'")
    html = istemci.get(f"/tr/hesabim/teklif/{no}").text
    gecmis = [_metin(x) for x in re.findall(r"<li>(.*?)</li>", _bolum(html, r'data-e2e="teklif-gecmisi">.*?</ol>'), re.S)]
    assert gecmis[1:] == ["Yanıtlandı — teklif verildi"], gecmis
    assert "Yanıt süresi" not in html
    with db:
        db.execute("UPDATE teklif SET durum = 'kapandi'")
    en = istemci.get(f"/en/hesabim/teklif/{no}").text
    gecmis = [_metin(x) for x in re.findall(r"<li>(.*?)</li>", _bolum(en, r'data-e2e="teklif-gecmisi">.*?</ol>'), re.S)]
    assert gecmis[0].startswith("Request created") and gecmis[1:] == ["Closed"], gecmis


# =====================================================================================================
# D23 — yurt dışı ödeme sırası: havale ilk ve varsayılan; OUR notu; iade sayfasında havale iadesi
# =====================================================================================================

def _yontemler(html):
    return re.findall(r'<input type="radio" id="odeme-(\w+)" name="odeme_yontemi" value="\w+"( checked)?>', html)


def test_g3m_yurtdisi_havale_ilk_ve_varsayilan(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3MY", ad="Export Ürünü", fiyat="100.00", stok=3)
    _musteri(db, tip=MusteriTipi.YURTDISI, eposta="d23@ornek.test", ulke="DE", vat_id="DE123456789")
    _giris(istemci, "d23@ornek.test", dil="en")
    _sepete_ekle(istemci, uid, dil="en")
    html = sayfa_denetle(istemci.get("/en/odeme"))
    assert _yontemler(html) == [("havale", " checked"), ("kart", "")], _yontemler(html)
    havale = _metin(_bolum(html, r'<p class="odeme-aciklama odeme-aciklama-havale".*?</p>'))
    assert "Bank charges: paid by the sender (OUR) (indicative)" in havale, havale
    tr = istemci.get("/tr/odeme").text
    assert "Banka masrafları: gönderen öder (OUR) (temsili)" in _metin(tr)
    # misafir, ülke DE (varsayılan hesap tipi yurt dışı): aynı sıra
    istemci.cookies.clear()
    _ulke_ve_fiyat(istemci, "DE", "eur", "en")
    _sepete_ekle(istemci, uid, dil="en")
    assert _yontemler(istemci.get("/en/odeme").text) == [("havale", " checked"), ("kart", "")]


def test_g3m_kurumsal_tr_odeme_sirasi_degismez(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3MK2", ad="Kurumsal Ürün", fiyat="100.00", stok=3)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="d23k@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Meram")
    _giris(istemci, "d23k@ornek.test")
    _sepete_ekle(istemci, uid)
    html = istemci.get("/tr/odeme").text
    assert _yontemler(html) == [("kart", " checked"), ("havale", "")]
    assert "(OUR)" not in html


def test_g3m_iade_sayfasi_havale_iadesi(istemci):
    tr = _metin(sayfa_denetle(istemci.get("/tr/yasal/iade")))
    assert ("Kurumsal ve yurt dışı alımlarda havale/EFT ile ödenen bedelin iadesi, ödemenin geldiği banka hesabına "
            "havale/EFT ile yapılır (temsili).") in tr
    en = _metin(istemci.get("/en/yasal/iade").text)
    assert ("For business and international purchases, amounts paid by bank transfer are refunded by bank transfer "
            "to the account the payment came from (indicative).") in en
    notlar = " ".join((KOK / "docs/hukuk-notlari.md").read_text(encoding="utf-8").split())
    assert "havale/EFT ile ödenen bedelin iadesi" in notlar and "(OUR)" in notlar


# =====================================================================================================
# D24 — ihracat siparişi: DAP / ithalat metni ve sipariş özeti bir kez; proformada OUR notu
# =====================================================================================================

def test_g3m_ihracat_siparis_tekrarsiz(istemci, db):
    from tests.test_web_g3k import _yurtdisi_havale
    no, _ = _yurtdisi_havale(istemci, db)
    html = sayfa_denetle(istemci.get(f"/en/siparis/{no}"))
    metin = _metin(html)
    for cumle in ("Freight is not included. We e-mail a DAP freight quote", "Import VAT and duties are paid by the buyer",
                  "Delivery terms: DAP (Incoterms 2020)"):
        assert metin.count(cumle) == 1, (cumle, metin.count(cumle))
    assert html.count('<dl class="tutar-ozeti">') == 1 and 'data-e2e="kalem-toplam"' not in html
    assert metin.count("Goods total") == 1
    assert "Bank charges: paid by the sender (OUR) (indicative)" in _metin(_bolum(html, r'<section class="proforma".*?</section>'))
    belge = _metin(istemci.get(f"/en/hesabim/siparis/{no}/proforma").text)
    assert belge.count("Freight is not included. We e-mail a DAP freight quote") == 1
    assert "Bank charges: paid by the sender (OUR) (indicative)" in belge


# =====================================================================================================
# D25 — ihracat bağlantıları tek çapaya; hedef id sayfada var
# =====================================================================================================

def test_g3m_ihracat_baglantilari_olu_capa_yok(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3MX", ad="Capa Ürünü", fiyat="100.00", stok=3)
    _ulke_ve_fiyat(istemci, "DE", "eur", "en")
    _sepete_ekle(istemci, uid, dil="en")
    hedefler = set()
    for dil in ("tr", "en"):
        for yol in (f"/{dil}/", f"/{dil}/urun/{uid}", f"/{dil}/sepet", f"/{dil}/odeme"):
            for capa in re.findall(r'href="/\w\w/yasal/kullanim#([^"]+)"', istemci.get(yol).text):
                hedefler.add((dil, capa))
        urun = istemci.get(f"/{dil}/urun/{uid}").text
        assert f'href="/{dil}/yasal/kullanim#ihracat-export"' in _bolum(urun, r'<p class="guven-satiri">.*?</p>')
    assert {c for _, c in hedefler} == {"ihracat-export"}, hedefler
    for dil, capa in hedefler:
        assert f'id="{capa}"' in istemci.get(f"/{dil}/yasal/kullanim").text, (dil, capa)


# =====================================================================================================
# D26 — VKN: hane hatası ile doğrulama basamağı hatası ayrı mesaj
# =====================================================================================================

BASAMAK = "Vergi kimlik numarası geçersiz: hane sayısı doğru ama doğrulama basamağı tutmuyor"
HANE = "Vergi kimlik numarası geçersiz (10 haneli VKN veya 11 haneli TCKN girin)."


@pytest.mark.parametrize("vkn,beklenen", [("1234567891", BASAMAK), ("10000000145", BASAMAK), ("123456789", HANE),
                                          ("12345abcde", HANE)])
def test_g3m_vkn_hata_metinleri(istemci, vkn, beklenen):
    veri = {"csrf": csrf_al(istemci, "/tr/kayit?tip=kurumsal"), "tip": "kurumsal", "ad": "Deneme A.Ş.",
            "eposta": f"v{vkn}@ornek.test", "parola": PAROLA, "vergi_kimlik_no": vkn, "vergi_dairesi": "Meram",
            "kvkk_onay": "1"}
    html = istemci.post("/tr/kayit", data=veri, follow_redirects=False).text
    assert beklenen in _metin(html), _metin(html)[:3000]
    teklif = istemci.post("/tr/teklif", data={"csrf": csrf_al(istemci, "/tr/teklif"), "ad": "Ali",
                                              "eposta": "a@ornek.test", "ulke": "TR", "adet": "1", "mesaj": "m",
                                              "vkn": vkn}, follow_redirects=False).text
    assert beklenen in _metin(teklif)


def test_g3m_vkn_hata_metni_en_ve_servis(con, simdi):
    from app.hesap.servis import KayitGirdisi, KayitHatasi, kayit_ol
    with pytest.raises(KayitHatasi) as e:
        kayit_ol(con, KayitGirdisi(tip=MusteriTipi.KURUMSAL, ad="A", eposta="s@ornek.test", parola=PAROLA, ulke="TR",
                                   kvkk_onay=True, vergi_kimlik_no="1234567891", vergi_dairesi="Meram"), simdi)
    assert (e.value.alan, e.value.kod) == ("vergi_kimlik_no", "vkn_basamak")
    import json
    en = json.loads((KOK / "app/web/dil/en.json").read_text(encoding="utf-8"))
    assert en["hata_kodu.vkn_basamak"] == ("Invalid tax number: the number of digits is correct but the check digit "
                                           "does not match")


# =====================================================================================================
# Fix turu 1
# =====================================================================================================

def test_g3m_f1_misafir_tip_bireysele_gecince_varsayilan_havale_karta(istemci, db):
    """I1: misafir yurt dışı varsayılanında havale işaretli + gizli odeme_varsayilan; kullanıcı tipi bireysel yapıp
    gönderirse (gizli grup havaleyle gider) 400 yok, sipariş kartla açılır; parola bir kez girilir."""
    from tests.test_web_sepet_odeme import _adres_formu
    _kur(db)
    uid = _urun(db, sku="S-G3MF1", ad="Misafir Ürünü", fiyat="100.00", stok=3)
    _ulke_ve_fiyat(istemci, "DE", "eur", "en")
    _sepete_ekle(istemci, uid, dil="en")
    sayfa = istemci.get("/en/odeme").text
    assert _yontemler(sayfa) == [("havale", " checked"), ("kart", "")]
    assert '<input type="hidden" name="odeme_varsayilan" value="havale">' in sayfa
    from app.web.rotalar.sepet_odeme import _teslim_secenekleri
    form = _adres_formu(ulke="DE", teslim=_teslim_secenekleri("DE")[0].value, odeme_yontemi="havale",
                        odeme_varsayilan="havale", hesap_tip="bireysel", hesap_eposta="f1@ornek.test",
                        hesap_parola=PAROLA, hesap_kvkk_onay="1")
    form["csrf"] = _gizli(sayfa, "csrf")
    # tip değişince tutar değişebilir (tahsilat birimi); gösterilen tutar o tipin sayfasından (aksi halde 409 "tutar
    # güncellendi" — G3a kuralı, bu testin konusu değil)
    bireysel = istemci.get("/en/odeme?tip=bireysel").text
    for ad in ("gosterilen_toplam", "gosterilen_kur"):
        form[ad] = _gizli(bireysel, ad)
    r = istemci.post("/en/odeme", data=form, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/kart"), (r.status_code, r.text[:1500])
    assert db.execute("SELECT odeme_yontemi FROM siparis").fetchone()[0] == "kart"


def test_g3m_f1_misafir_acik_havale_secimi_bireyselde_hata(istemci, db):
    """I1: varsayılan işareti yoksa (kullanıcı havaleyi kendisi seçti) G3g M-7 kuralı aynen: bireyselde hata."""
    from tests.test_web_sepet_odeme import _adres_formu
    _kur(db)
    uid = _urun(db, sku="S-G3MF2", ad="Misafir Ürünü 2", fiyat="100.00", stok=3)
    _sepete_ekle(istemci, uid)
    sayfa = istemci.get("/tr/odeme").text
    assert 'name="odeme_varsayilan"' not in sayfa            # TR misafir: varsayılan kart, işaret yok
    form = _adres_formu(odeme_yontemi="havale", hesap_tip="bireysel", hesap_eposta="f2@ornek.test",
                        hesap_parola=PAROLA, hesap_kvkk_onay="1")
    for ad in ("csrf", "gosterilen_toplam", "gosterilen_kur"):
        form[ad] = _gizli(sayfa, ad)
    r = istemci.post("/tr/odeme", data=form, follow_redirects=False)
    assert r.status_code == 400 and "Havale/EFT yalnız kurumsal ve yurt dışı müşteride" in _metin(r.text)


def test_g3m_f1_oldugu_gibi_teslimden_itibaren(istemci, db):
    """I2: üç anahtarda ihbar süresinin başlangıcı (yasal sayfa ve urun.iade_ticari ile aynı)."""
    import json
    for dil, parca in (("tr", "açık ayıplar teslimden itibaren {gun} gün içinde yazılı bildirilir."),
                       ("en", "obvious defects must be notified in writing within {gun} days of delivery.")):
        metinler = json.loads((KOK / f"app/web/dil/{dil}.json").read_text(encoding="utf-8"))
        for anahtar in ("urun.iade_ticari_oldugu_gibi", "urun.iade_ozet_ticari_oldugu_gibi", "urun.iade_ozet_oldugu_gibi"):
            assert metinler[anahtar].endswith(parca), (dil, anahtar)


def test_g3m_f1_liste_en_kotu_boyut(istemci):
    """m3: 48 satırın tamamı "2. el" (rozet + title + örnek rozeti), uzun ad ve kodlarla liste < 150 KB."""
    adlar = [(f"SIEMENS SINAMICS S120 SERVO SÜRÜCÜ GÜÇ MODÜLÜ MOTOR MODULE DOUBLE AXIS {i:02d} 2X9A",
              {"uretici_kodu": f"6SL3120-2TE21-8AD{i:02d}", "sku": f"810101010{i:04d}"}) for i in range(48)]
    kimlikler = _katalog(istemci, adlar, stok=3)
    with istemci_db(istemci) as con:
        con.execute(f"UPDATE urun SET durum_kodu = 'ikinci_el', durum_ornek = 1 WHERE id IN "
                    f"({','.join(map(str, kimlikler))})")
    for yol in ("/tr/urunler?adet=48", "/en/urunler?adet=48"):
        html = sayfa_denetle(istemci.get(yol))
        assert html.count('class="rozet rozet-durum" title=') == 48
        assert len(html.encode("utf-8")) < 150_000, (yol, len(html.encode("utf-8")))
    faset = _bolum(istemci.get("/tr/urunler").text, r'<fieldset class="faset" data-faset="durum">.*?</fieldset>')
    assert "title=" not in faset and 'class="faset-daha durum-aciklama"' in faset   # tekrar eden faset title yok


def test_g3m_f1_kontrol_unitesi_kumesi(istemci):
    """m4: "kontrol ünitesi" grubu (controller / kontrolör) — kelime-VE genişlemesi makul küme."""
    _katalog(istemci, [("KUKA KRC4 KONTROL ÜNİTESİ", {}), ("ABB IRC5 CONTROLLER", {}), ("FANUC R-30IB KONTROLÖR", {}),
                       ("ROBOT KONTROL KABİNİ ÜNİTESİ", {}), ("SICAKLIK KONTROL VALFİ", {}), ("HİDROLİK GÜÇ ÜNİTESİ", {}),
                       ("FESTO VALF", {})], stok=1)

    def ara(q):
        return sorted(_satirlar(istemci.get("/tr/ara", params={"q": q}).text))
    beklenen = sorted(["KUKA KRC4 KONTROL ÜNİTESİ", "ABB IRC5 CONTROLLER", "FANUC R-30IB KONTROLÖR",
                       "ROBOT KONTROL KABİNİ ÜNİTESİ"])
    assert ara("controller") == ara("kontrol ünitesi") == ara("kontrolör") == beklenen


def test_g3m_f1_el_terminali_kumesi(istemci):
    """m4: "el terminali" grubu: "el" tam kelime (ELEKTRİK … TERMİNALİ gibi klemens ürünleri gelmez)."""
    _katalog(istemci, [("KUKA KCP4 EL TERMİNALİ", {}), ("ABB TEACH PENDANT 3HAC028357", {}),
                       ("KUKA SMARTPAD HANDBEDIENGERÄT", {}), ("YASKAWA EL TERMINALI KABLOSU", {}),
                       ("ELEKTRİK BAĞLANTI TERMİNALİ", {}), ("PHOENIX KLEMENS TERMİNALİ", {})], stok=1)

    def ara(q):
        return sorted(_satirlar(istemci.get("/tr/ara", params={"q": q}).text))
    beklenen = sorted(["KUKA KCP4 EL TERMİNALİ", "ABB TEACH PENDANT 3HAC028357", "KUKA SMARTPAD HANDBEDIENGERÄT",
                       "YASKAWA EL TERMINALI KABLOSU"])
    assert ara("el terminali") == ara("teach pendant") == ara("Handbediengerät") == beklenen


def test_g3m_f1_misafir_belirtilmemis_rapor_taahhudu(istemci, db):
    """m1: ticari / misafir tek cümlesinde fotoğraf/test raporu taahhüdü (1 iş günü) kaybolmaz; çelişki yok."""
    _kur(db)
    uid = _urun(db, sku="S-G3MF3", ad="Belirsiz 2", fiyat="100.00", stok=3)
    _durum_ata(db, uid, "belirtilmemis")
    tr = _metin(_bolum(istemci.get(f"/tr/urun/{uid}").text, r'<p class="garanti-satiri".*?</p>'))
    assert "siparişten sonra 1 iş günü içinde e-postayla gönderilir" in tr, tr
    _ulke_ve_fiyat(istemci, "DE", "eur", "en")
    en = istemci.get(f"/en/urun/{uid}").text
    assert "e-mailed within 1 business day after the order" in _metin(_bolum(en, r'<p class="garanti-satiri".*?</p>'))
    _celiski_yok(en, "no right of withdrawal", "cancel the order free of charge")


def test_g3m_f1_yinelenen_fmin_fpb_korunur(istemci):
    """m2: ?fmin=100&fmin=&fpb=EUR — dolu fmin varken fpb atılmaz (yalnız boş değer atılır)."""
    _katalog(istemci, [("FESTO VALF", {})], stok=1)
    r = istemci.get("/tr/urunler?fmin=100&fmin=&fpb=EUR", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/tr/urunler?fmin=100&fpb=EUR", r.headers.get("location")


def test_g3m_f1_odenmis_havalede_varis_odeme_tarihinden(istemci, db):
    """m5: ödenmiş havale siparişinde tahmini varış ödeme zamanından (sipariş tarihinden değil)."""
    no, _ = _kurumsal_havale(istemci, db, eposta="f5@ornek.test")
    with db:
        db.execute("UPDATE siparis SET olusturma = '2026-09-01T09:00:00+00:00', durum = 'odendi', "
                   "odeme_zamani = '2026-10-12T09:00:00+00:00' WHERE no = ?", (no,))
    notlar = _kalem_notlari(istemci.get(f"/tr/hesabim/siparis/{no}").text)
    assert notlar == ["Kargoya veriliş: 1–2 iş günü · varış: 14–16 Ekim (temsili)"], notlar   # G3n madde 6


def test_g3m_f1_basi_sifir_11_hane_bicim_hatasi():
    """m8: başı 0 olan 11 haneli numara biçim (hane) hatası sayılır."""
    from app.hesap.dogrulama import vergi_no_hatasi
    assert vergi_no_hatasi("01234567890") == "gecersiz_vkn"
    assert vergi_no_hatasi("10000000145") == "vkn_basamak"
