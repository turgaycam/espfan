"""G3n: persona tur 9 — A: staging'de gözlenen bildirimler (1–4), B: tutarlılık (5–15)."""
import csv
import io
import json
import re
from datetime import UTC, datetime
from html import unescape

import pytest

from app.fiyat.kurallar import MusteriTipi
from app.katalog.indeks import indeksi_yeniden_kur
from app.katalog.urun_ceviri import kaynak_ozeti
from app.metin import en_ad_duzelt, yonelme_eki
from app.web.teslim import TR_IS_GUNU, aralik_metni, is_gunu_ekle
from app.web import baglam as baglam_modulu
from tests.conftest import csrf_al, istemci_db, sayfa_denetle, urun_ekle  # noqa: F401
from tests.test_web_g3e import _durum_ata
from tests.test_web_g3j import _bildirimler, _metin, _satir, _ulke_ve_fiyat
from tests.test_web_g3m import _kurumsal_havale
from tests.test_web_sepet_odeme import (GECERLI_VKN, _giris, _gizli, _kur, _musteri,  # noqa: F401
                                        _odeme_gonder, _sepete_ekle, _urun, db)


def _bolum(html, desen):
    m = re.search(desen, html, re.S)
    assert m, desen
    return m.group(0)


def _sepet_satiri(html):
    return _bolum(html, r'<tr data-e2e="sepet-kalemi">.*?</tr>')


def _adet_gonder(istemci, uid, adet, dil="tr"):
    csrf = csrf_al(istemci, f"/{dil}/sepet")
    r = istemci.post(f"/{dil}/sepet/adet", data={"csrf": csrf, "urun_id": str(uid), "adet": adet},
                     follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/{dil}/sepet", (adet, r.status_code)
    return sayfa_denetle(istemci.get(f"/{dil}/sepet"))


def _kurumsal(db, istemci, eposta="g3n-k@ornek.test"):
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta=eposta, vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Meram")
    _giris(istemci, eposta)


# =====================================================================================================
# A1 — sepet adet: tarayıcı doğrulaması gönderimi engellemez; bildirim sayfa üstünde ve satırda
# =====================================================================================================

@pytest.mark.parametrize("sayi, beklenen", [(0, "0'a"), (1, "1'e"), (2, "2'ye"), (3, "3'e"), (4, "4'e"), (5, "5'e"),
                                            (6, "6'ya"), (7, "7'ye"), (8, "8'e"), (9, "9'a"), (10, "10'a"),
                                            (20, "20'ye"), (30, "30'a"), (40, "40'a"), (50, "50'ye"), (60, "60'a"),
                                            (70, "70'e"), (80, "80'e"), (90, "90'a"), (99, "99'a"), (100, "100'e"),
                                            (1000, "1000'e"), (2000000, "2000000'a"), (17, "17'ye")])
def test_g3n_yonelme_eki(sayi, beklenen):
    assert yonelme_eki(sayi) == beklenen


def test_g3n_sepet_adet_alani_tarayicida_engellenmez(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3NF", ad="Form Ürünü", fiyat="100.00", stok=7)
    _sepete_ekle(istemci, uid)
    html = sayfa_denetle(istemci.get("/tr/sepet"))
    form = _bolum(html, r'<form method="post" action="/tr/sepet/adet"[^>]*>.*?</form>')
    girdi = _bolum(form, r'<input id="adet-\d+"[^>]*>')
    assert "novalidate" in form.split(">", 1)[0]                    # 2.5 / -3 / 0 / 100 sunucuya ulaşır
    assert 'type="number"' not in girdi and " min=" not in girdi and " max=" not in girdi, girdi
    assert 'name="adet"' in girdi and 'inputmode="numeric"' in girdi


def test_g3n_sepet_adet_bildirimleri_ustte_ve_satirda(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3NA", ad="Adet Ürünü", fiyat="100.00", stok=7)
    _sepete_ekle(istemci, uid)
    html = _adet_gonder(istemci, uid, "8")
    assert _bildirimler(html).startswith("Stokta 7 adet var; adet 7'ye düşürüldü."), _bildirimler(html)
    assert "Stokta 7 adet var; adet 7'ye düşürüldü." in _metin(_bolum(_sepet_satiri(html),
                                                                         r'<p class="yerel-bildirim.*?</p>'))
    assert db.execute("SELECT adet FROM sepet_kalemi").fetchone()[0] == 7
    for deger in ("abc", "2.5", "3,5", "", "-3"):
        html = _adet_gonder(istemci, uid, deger)
        assert _bildirimler(html).startswith("Geçersiz adet"), (deger, _bildirimler(html))
        satir = _metin(_bolum(_sepet_satiri(html), r'<p class="yerel-bildirim.*?</p>'))
        assert satir.startswith("Geçersiz adet"), (deger, satir)
        assert db.execute("SELECT adet FROM sepet_kalemi").fetchone()[0] == 7
    with db:   # Fix 1 (m-8): genel üst sınır (99) bildirimi de satırda
        db.execute("UPDATE urun SET stok = 500 WHERE id = ?", (uid,))
    html = _adet_gonder(istemci, uid, "150")
    satir = _metin(_bolum(_sepet_satiri(html), r'<p class="yerel-bildirim.*?</p>'))
    assert "99" in satir and satir in _bildirimler(html), (satir, _bildirimler(html))
    html = _adet_gonder(istemci, uid, "0")
    assert _bildirimler(html) == "Adet Ürünü sepetten çıkarıldı."
    en_uid = _urun(db, sku="S-G3NB", ad="İkinci Ürün", fiyat="10.00", stok=3)
    _sepete_ekle(istemci, en_uid, dil="en")
    html = _adet_gonder(istemci, en_uid, "5", dil="en")
    assert _bildirimler(html).startswith("Only 3 in stock; quantity reduced to 3."), _bildirimler(html)


# =====================================================================================================
# A2 — fatura bilgileri kaydı bildirimi (koruma: staging'de görünüyor)
# =====================================================================================================

def test_g3n_fatura_kaydi_bildirimi_ana_icerikten_once(istemci, db):
    _kurumsal(db, istemci, "g3n-f@ornek.test")
    csrf = csrf_al(istemci, "/tr/hesabim/fatura")
    r = istemci.post("/tr/hesabim/fatura", data={"csrf": csrf, "ad": "QATest A.Ş.", "vergi_dairesi": "Meram",
                                                 "satir1": "Test Mah. 1", "sehir": "Konya", "satir2": "",
                                                 "posta_kodu": "", "telefon": ""}, follow_redirects=False)
    assert r.status_code == 303
    html = sayfa_denetle(istemci.get("/tr/hesabim/fatura"))
    assert _bildirimler(html) == "Fatura bilgileriniz kaydedildi."
    assert html.index('class="bildirimler"') < html.index('<main id="icerik"')


# =====================================================================================================
# A3 — tekrar sepete ekle: hiçbiri eklenemediyse "Sepetiniz boş" yerine neden listesi
# =====================================================================================================

def test_g3n_tekrar_ekle_hicbiri_eklenemedi_neden_listesi(istemci, db):
    no, uid = _kurumsal_havale(istemci, db, eposta="g3n-t@ornek.test")
    csrf = csrf_al(istemci, f"/tr/hesabim/siparis/{no}")
    r = istemci.post(f"/tr/hesabim/siparis/{no}/tekrar", data={"csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/tr/sepet"
    html = sayfa_denetle(istemci.get("/tr/sepet"))
    assert "Sepetiniz boş" not in html
    blok = _metin(_bolum(html, r'<div class="tekrar-nedenler[^"]*"[^>]*>.*?</div>'))
    assert blok.startswith("Siparişteki kalemler sepete eklenemedi:"), blok
    assert f"Havale Kalemi (kendi ödeme bekleyen siparişiniz ({no}) bu stoğu ayırıyor)" in blok, blok
    assert "Sepete eklenemeyen" not in _bildirimler(html)         # aynı neden iki kez yazılmaz
    assert "Sepetiniz boş" in istemci.get("/tr/sepet").text       # bir kez gösterilir (PRG)


def test_g3n_tekrar_ekle_sepet_doluysa_bildirim(istemci, db):
    no, uid = _kurumsal_havale(istemci, db, eposta="g3n-t2@ornek.test")
    diger = _urun(db, sku="S-G3ND", ad="Dolu Sepet Ürünü", fiyat="10.00", stok=5)
    _sepete_ekle(istemci, diger)
    csrf = csrf_al(istemci, f"/tr/hesabim/siparis/{no}")
    istemci.post(f"/tr/hesabim/siparis/{no}/tekrar", data={"csrf": csrf}, follow_redirects=False)
    html = sayfa_denetle(istemci.get("/tr/sepet"))   # sepet dolu: neden üstteki bildirimde (mevcut), liste yok
    assert "Sepete eklenemeyen: Havale Kalemi (kendi ödeme bekleyen siparişiniz" in _bildirimler(html)
    assert 'data-e2e="sepet-kalemi"' in html and "tekrar-nedenler" not in html


# =====================================================================================================
# A4 — sepeti boşalt bildirimi (koruma)
# =====================================================================================================

def test_g3n_sepeti_bosalt_bildirimi(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3NE", ad="Boşalt Ürünü", fiyat="10.00", stok=5)
    _sepete_ekle(istemci, uid)
    csrf = csrf_al(istemci, "/tr/sepet")
    istemci.post("/tr/sepet/bosalt", data={"csrf": csrf}, follow_redirects=False)
    html = sayfa_denetle(istemci.get("/tr/sepet"))
    assert _bildirimler(html) == "Sepet boşaltıldı."


# =====================================================================================================
# B5 — iade/garanti satırı tek kaynaktan (kart, karşılaştırma, ürün sayfası; liste satırında iade satırı yok)
# =====================================================================================================

def _iade_bloklari(html):
    return [_metin(m) for m in re.findall(r'<span class="iade-satirlari"[^>]*>(.*?)</span></span>', html, re.S)]


def _dort_yuzey(istemci, uid, dil="tr"):
    csrf = csrf_al(istemci, f"/{dil}/urun/{uid}")
    istemci.post(f"/{dil}/karsilastir/ekle", data={"csrf": csrf, "urun_id": str(uid), "sonraki": f"/{dil}/"})
    ana = _iade_bloklari(istemci.get(f"/{dil}/").text)
    urun = _iade_bloklari(istemci.get(f"/{dil}/urun/{uid}").text)
    kars = istemci.get(f"/{dil}/karsilastir").text
    liste = _satir(istemci.get(f"/{dil}/urunler").text, uid)
    return ana, urun, _iade_bloklari(kars), kars, liste


@pytest.mark.parametrize("durum", ["belirtilmemis", "ikinci_el_oldugu_gibi", "yeni"])
def test_g3n_iade_satiri_tek_kaynak(istemci, db, durum):
    _kur(db)
    uid = _urun(db, sku="S-G3NI", ad="İade Ürünü", fiyat="100.00", stok=3)
    _durum_ata(db, uid, durum)
    # misafir (TR): iki satır, dört yüzeyde aynı
    ana, urun, kars, kars_html, liste = _dort_yuzey(istemci, uid)
    assert len(urun) == 1 and ana == urun == kars, (ana, urun, kars)
    assert urun[0].startswith("Bireysel alım: 14 gün cayma hakkı (temsili) Ticari alım: cayma hakkı yok")
    assert "iade-satirlari" not in liste and "cayma" not in _metin(liste)   # liste: iade satırı yok (bütçe kararı)
    # kurumsal: bireysel satır yok
    istemci.cookies.clear()
    _kurumsal(db, istemci, f"g3n-i-{durum}@ornek.test")
    ana, urun, kars, kars_html, _ = _dort_yuzey(istemci, uid)
    assert ana == urun == kars and urun[0].startswith("Ticari alım: cayma hakkı yok"), (ana, urun, kars)
    assert "Bireysel alım" not in kars_html and "14 gün" not in urun[0]
    # Fix 1 (I-1): yurt dışı misafir (EN, DE seçili) TR misafiri gibi iki satır; eski genel cümle hiçbir yüzeyde yok
    istemci.cookies.clear()
    _ulke_ve_fiyat(istemci, "DE", "eur", "en")
    ana, urun, kars, kars_html, _ = _dort_yuzey(istemci, uid, "en")
    assert ana == urun == kars, (ana, urun, kars)
    assert urun[0].startswith("Consumer purchase: 14-day right of withdrawal (indicative) Business purchase: no right")
    assert "14-day withdrawal for consumers" not in kars_html
    # girişli yurt dışı hesap: yalnız ticari satır
    istemci.cookies.clear()
    _musteri(db, tip=MusteriTipi.YURTDISI, eposta=f"g3n-y-{durum}@ornek.test", ulke="DE", vat_id="DE123456789")
    _giris(istemci, f"g3n-y-{durum}@ornek.test", dil="en")
    ana, urun, kars, kars_html, _ = _dort_yuzey(istemci, uid, "en")
    assert ana == urun == kars and urun[0].startswith("Business purchase: no right of withdrawal"), (ana, urun)
    assert "Consumer purchase" not in kars_html


def test_g3n_eski_genel_iade_cumlesi_kalkti():
    for dil in ("tr", "en"):
        metinler = json.load(open(f"app/web/dil/{dil}.json", encoding="utf-8"))
        assert "urun.iade_satiri_misafir" not in metinler and "urun.iade_satiri_misafir_oldugu_gibi" not in metinler


# =====================================================================================================
# B6 — teslim süresi tek kaynaktan
# =====================================================================================================

def test_g3n_teslim_metni_urun_liste_siparis_ayni(istemci, db):
    no, uid = _kurumsal_havale(istemci, db, eposta="g3n-s@ornek.test", stok=2)
    with db:   # ürün sayfası ve liste stoklu görünsün (kendi rezervasyonu stoğun yalnız bir kısmı)
        db.execute("UPDATE urun SET stok = 5 WHERE id = ?", (uid,))
    bugun = baglam_modulu.simdi().astimezone(baglam_modulu.TR_SAAT).date()
    aralik = aralik_metni(*(is_gunu_ekle(bugun, n) for n in TR_IS_GUNU), "tr")
    beklenen = f"Kargoya veriliş: 1–2 iş günü · varış: {aralik} (temsili)"
    urun = _metin(_bolum(istemci.get(f"/tr/urun/{uid}").text, r'<p class="teslim-not".*?</p>'))
    assert urun == beklenen, urun
    liste = _metin(_bolum(_satir(istemci.get("/tr/urunler").text, uid), r'<span class="ut-teslim">.*?</span>'))
    assert liste == beklenen, liste
    havale = f"Ödeme alındıktan sonra kargoya veriliş: 1–2 iş günü · varış: {TR_IS_GUNU[0]}–{TR_IS_GUNU[1]} iş günü"
    for yol in (f"/tr/siparis/{no}", f"/tr/hesabim/siparis/{no}"):
        notlar = [_metin(x) for x in re.findall(r'<span class="not kalem-teslim"[^>]*>(.*?)</span>',
                                                istemci.get(yol).text, re.S)]
        assert notlar == [f"Sizin için ayrıldı (ödeme son tarihine kadar) · {havale} (temsili)"], (yol, notlar)
    with db:
        db.execute("UPDATE siparis SET durum = 'odendi', odeme_zamani = ? WHERE no = ?",
                   (datetime.now(UTC).isoformat(), no))
    for yol in (f"/tr/siparis/{no}", f"/tr/hesabim/siparis/{no}"):
        notlar = [_metin(x) for x in re.findall(r'<span class="not kalem-teslim"[^>]*>(.*?)</span>',
                                                istemci.get(yol).text, re.S)]
        assert notlar == [beklenen], (yol, notlar)


def test_g3n_teslim_metni_en_ab(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3NT", ad="AB Ürünü", fiyat="100.00", stok=3)
    _ulke_ve_fiyat(istemci, "DE", "eur", "en")
    metin = _metin(_bolum(istemci.get(f"/en/urun/{uid}").text, r'<p class="teslim-not".*?</p>'))
    assert re.fullmatch(r"Dispatch: 1–2 business days · arrival: .+ \(indicative\)", metin), metin


# =====================================================================================================
# B7 — "₺ KDV dahil" seçiliyken satırda "KDV hariç" yok (KDV uygulanmayan yurt dışı teslim)
# =====================================================================================================

def test_g3n_try_gosterimde_kdv_haric_etiketi_yok(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3NK", ad="Kur Ürünü", fiyat="100.00", stok=3)
    _ulke_ve_fiyat(istemci, "DE", "try", "en")
    _sepete_ekle(istemci, uid, dil="en")
    html = sayfa_denetle(istemci.get("/en/sepet"))
    tablo = _bolum(html, r'<table class="tablo sepet-tablo.*?</table>')
    assert "excl. VAT" not in _metin(tablo), _metin(tablo)
    assert "No VAT (export)" in _metin(_sepet_satiri(html))
    satir = _metin(_satir(istemci.get("/en/urunler").text, uid))
    assert "excl. VAT" not in satir, satir
    tr = sayfa_denetle(istemci.get("/tr/sepet"))
    assert "KDV hariç" not in _metin(_bolum(tr, r'<table class="tablo sepet-tablo.*?</table>'))


# =====================================================================================================
# B8 — ters aralık: form alanları yer değiştirmiş değerlerle dolar
# =====================================================================================================

def _deger(html, ad):
    return unescape(re.search(rf'<input id="{ad}" name="{ad}"[^>]*value="([^"]*)"', html).group(1))


def test_g3n_ters_aralik_form_alanlari(istemci, db):
    _kur(db)
    _urun(db, sku="S-G3NR", ad="Aralık Ürünü", fiyat="100.00", stok=3)
    html = sayfa_denetle(istemci.get("/tr/urunler?fmin=5.000&fmax=1.000"))
    assert "fiyat-ters" in html
    assert (_deger(html, "fmin"), _deger(html, "fmax")) == ("1.000", "5.000")
    html = istemci.get("/tr/urunler?fmin=1.000&fmax=5.000").text
    assert (_deger(html, "fmin"), _deger(html, "fmax")) == ("1.000", "5.000")


# =====================================================================================================
# B9 — PO 40 karakter: kırpılmaz, form hatası
# =====================================================================================================

def test_g3n_po_kirpilmaz_form_hatasi(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3NP", ad="PO Ürünü", fiyat="100.00", stok=3)
    _kurumsal(db, istemci, "g3n-p@ornek.test")
    _sepete_ekle(istemci, uid)
    sayfa = istemci.get("/tr/odeme").text
    girdi = _bolum(sayfa, r'<input id="musteri_po"[^>]*>')
    assert 'maxlength="40"' not in girdi        # fix 1 (m-7): görünür sınırın üstünde maxlength 200
    po = "P" * 41
    r = _odeme_gonder(istemci, sayfa_html=sayfa, musteri_po=po, odeme_yontemi="havale")
    assert r.status_code == 400
    assert _metin(_bolum(r.text, r'<p class="alan-hata" id="hata-musteri_po">.*?</p>')) == "En çok 40 karakter"
    assert f'value="{po}"' in _bolum(r.text, r'<input id="musteri_po"[^>]*>')
    teklif = sayfa_denetle(istemci.get(f"/tr/teklif?urun_id={uid}"))
    assert 'maxlength="40"' not in _bolum(teklif, r'<input[^>]*name="musteri_po"[^>]*>')
    form = {"csrf": _gizli(teklif, "csrf"), "ad": "QATest", "firma": "QATest A.Ş.", "eposta": "g3n-p@ornek.test",
            "telefon": "+90 555 000 00 00", "ulke": "TR", "urun_id": str(uid), "adet": "1", "mesaj": "deneme",
            "musteri_po": po, "kvkk_onay": "1"}
    r = istemci.post("/tr/teklif", data=form, follow_redirects=False)
    assert r.status_code == 400
    assert "En çok 40 karakter" in r.text and f'value="{po}"' in r.text


# =====================================================================================================
# B10 — karşılaştırma fiyat satırı gösterim tercihine uyar (koruma)
# =====================================================================================================

def test_g3n_karsilastirma_fiyat_tercihi(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3NC", ad="Karşılaştırma Ürünü", fiyat="100.00", stok=3)
    _kurumsal(db, istemci, "g3n-c@ornek.test")
    csrf = csrf_al(istemci, f"/tr/urun/{uid}")
    istemci.post("/tr/karsilastir/ekle", data={"csrf": csrf, "urun_id": str(uid), "sonraki": "/tr/"})

    def fiyat_satiri():
        return _metin(_bolum(istemci.get("/tr/karsilastir").text, r'<tr>\s*<th scope="row">Fiyat \(KDV hariç\)</th>.*?</tr>'))
    s = fiyat_satiri()
    assert s.index("€") < s.index("₺"), s                          # kurumsal varsayılan: € ana
    _ulke_ve_fiyat(istemci, "TR", "try")
    s = fiyat_satiri()
    assert s.index("₺") < s.index("€"), s
    _ulke_ve_fiyat(istemci, "TR", "eur")
    s = fiyat_satiri()
    assert s.index("€") < s.index("₺"), s


# =====================================================================================================
# B11 — ürün sayfası "Teklif iste" her üründe
# =====================================================================================================

def test_g3n_urun_sayfasi_ikincil_teklif_iste(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3NQ", ad="Fiyatlı Ürün", fiyat="100.00", stok=3, uretici_kodu="6ES7-G3N")
    html = sayfa_denetle(istemci.get(f"/tr/urun/{uid}"))
    bag = _bolum(html, r'<a [^>]*data-e2e="teklif-iste-ikincil"[^>]*>.*?</a>')
    assert f'href="/tr/teklif?urun_id={uid}"' in bag and "ikincil" in bag and _metin(bag) == "Teklif iste"
    assert 'data-e2e="sepete-ekle"' in html
    teklif = sayfa_denetle(istemci.get(f"/tr/teklif?urun_id={uid}"))
    assert f'name="urun_id" value="{uid}"' in teklif and "6ES7-G3N" in teklif and "Fiyatlı Ürün" in teklif
    zorunlu = _urun(db, sku="S-G3NZ", ad="Teklifli Ürün", fiyat="100.00", stok=3, teklif=True)
    html = istemci.get(f"/tr/urun/{zorunlu}").text
    assert 'data-e2e="teklif-iste"' in html and 'data-e2e="teklif-iste-ikincil"' not in html


# =====================================================================================================
# B12 — teknik özellikler: başlık bir kez, parça no ile aynı "Type" yok, kimlik satırları tekrarlanmaz
# =====================================================================================================

def test_g3n_teknik_bolum_tekrarsiz(istemci, db):
    _kur(db)
    uid = _urun(db, sku="8402033800001", ad="KUKA KRC4 PANEL", fiyat="100.00", stok=3, uretici_kodu="00-168-334")
    with db:
        db.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)", (uid, json.dumps(
            {"ozellikler": [["Type", "00-168-334"], ["Ekran Tipi", "8.4 inç"]], "bolumler": [["", "*Not."]]},
            ensure_ascii=False)))
    for dil, baslik in (("tr", "Teknik özellikler"), ("en", "Technical specifications")):
        html = sayfa_denetle(istemci.get(f"/{dil}/urun/{uid}"))
        bolum = _bolum(html, r'<details class="bolum" open>\s*<summary id="teknik-baslik">[^<]*</summary>.*?</details>')
        assert _metin(bolum).count(baslik) == 1, _metin(bolum)
        assert "00-168-334" not in bolum and "8402033800001" not in bolum, bolum
        assert ">Type<" not in bolum and "Ekran Tipi" in bolum
    uid2 = _urun(db, sku="S-G3NT2", ad="Başka Tip", fiyat="100.00", stok=3, uretici_kodu="ABC-1")
    with db:
        db.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)", (uid2, json.dumps(
            {"ozellikler": [["Type", "XYZ 9"]], "bolumler": []})))
    assert "XYZ 9" in istemci.get(f"/tr/urun/{uid2}").text      # parça no'dan farklı tip kalır


# =====================================================================================================
# B13 — tek sonuçlu aramada tek seçenekli faset grupları gizli (seçili olanlar hariç)
# =====================================================================================================

def test_g3n_tek_sonuclu_aramada_faset_gizli(istemci, db):
    _kur(db)
    _urun(db, sku="S-G3NS1", ad="ABB DSQC626 KART", fiyat="100.00", stok=3, uretici_kodu="DSQC626")
    _urun(db, sku="S-G3NS2", ad="SIEMENS ROLE", fiyat="50.00", stok=3)
    html = sayfa_denetle(istemci.get("/tr/ara?q=DSQC626"))
    assert html.count('data-e2e="urun-baglanti"') == 1
    assert 'class="faset-grup"' not in html, re.findall(r'data-grup="(\w+)"', html)
    html = sayfa_denetle(istemci.get("/tr/ara?q=DSQC626&marka=ABB"))
    assert re.findall(r'data-grup="(\w+)"', html) == ["marka"]
    coklu = istemci.get("/tr/urunler").text
    assert 'data-grup="marka"' in coklu


# =====================================================================================================
# B14 — EN adda noktalı İ / ı kalıntıları gösterim katmanında düzeltilir
# =====================================================================================================

@pytest.mark.parametrize("ham, duz", [("MURR EVOLUTİON 20 Power Supply", "MURR EVOLUTION 20 Power Supply"),
                                      ("KEB COMBIVERT F5-Basıc", "KEB COMBIVERT F5-Basic"),
                                      ("KUKA KRC4 KR10 R1100 SİXX", "KUKA KRC4 KR10 R1100 SIXX"),
                                      ("AİS/224000 Cable", "AIS/224000 Cable"), ("Power Supply", "Power Supply"),
                                      # Fix 1 (I-2): ç ğ ö ş ü içeren sözcük Türkçedir, dokunulmaz
                                      ("İÇİN", "İÇİN"), ("ŞİŞLİ", "ŞİŞLİ"),
                                      ("SIEMENS ET 200S İÇİN EVOLUTİON", "SIEMENS ET 200S İÇİN EVOLUTION")])
def test_g3n_en_ad_duzelt(ham, duz):
    assert en_ad_duzelt(ham) == duz


def test_g3n_en_ad_gosterimde_duzelir_veri_degismez(istemci):
    ad = "MURR EVOLUTİON 20 GÜÇ KAYNAĞI"
    ad_en = "MURR EVOLUTİON 20 Power Supply"
    with istemci_db(istemci) as con:
        uid = urun_ekle(con, sku="S-G3NN", ad=ad, fiyat="100.00")
        con.execute("INSERT INTO urun_ceviri VALUES (?, 'en', ?, NULL, 'llm-taslak', 'm', ?, 't')",
                    (uid, ad_en, kaynak_ozeti(ad, [])))
        indeksi_yeniden_kur(con)
        con.commit()
    en = sayfa_denetle(istemci.get(f"/en/urun/{uid}"))
    assert "<h1>MURR EVOLUTION 20 Power Supply</h1>" in en and "EVOLUTİON" not in en
    assert "MURR EVOLUTION 20 Power Supply" in istemci.get("/en/ara?q=evolution").text
    tr = istemci.get(f"/tr/urun/{uid}").text
    assert f"<h1>{ad}</h1>" in tr
    with istemci_db(istemci) as con:
        assert con.execute("SELECT ad FROM urun_ceviri WHERE urun_id = ?", (uid,)).fetchone()[0] == ad_en


# =====================================================================================================
# B15 — CSV ondalık virgül seçeneği; teknik_tip parça no ile aynıysa boş
# =====================================================================================================

def _csv(istemci, yol):
    r = istemci.get(yol)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    return list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))


def test_g3n_csv_ondalik_virgul_ve_teknik_tip(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-G3NV", ad="CSV Ürünü", fiyat="1234.50", stok=3, uretici_kodu="6EP1961-2BA11")
    uid2 = _urun(db, sku="S-G3NV2", ad="CSV Ürünü 2", fiyat="10.00", stok=3, uretici_kodu="X-2")
    with db:
        db.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)", (uid, json.dumps(
            {"ozellikler": [["Type", "6EP1961-2BA11"], ["Akım", "2,5 A"]], "bolumler": []}, ensure_ascii=False)))
        db.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)", (uid2, json.dumps(
            {"ozellikler": [["Type", "Başka"]], "bolumler": []}, ensure_ascii=False)))
    for u in (uid, uid2):
        csrf = csrf_al(istemci, f"/tr/urun/{u}")
        istemci.post("/tr/karsilastir/ekle", data={"csrf": csrf, "urun_id": str(u), "sonraki": "/tr/"})
    sayfa = sayfa_denetle(istemci.get("/tr/karsilastir"))
    assert 'href="/tr/karsilastir.csv?ondalik=virgul"' in sayfa
    nokta = {int(s["urun_id"]): s for s in _csv(istemci, "/tr/karsilastir.csv")}
    virgul = {int(s["urun_id"]): s for s in _csv(istemci, "/tr/karsilastir.csv?ondalik=virgul")}
    assert nokta[uid]["fiyat_kdv_haric_eur"] == "1234.50" and virgul[uid]["fiyat_kdv_haric_eur"] == "1234,50"
    assert virgul[uid]["fiyat_kdv_haric_try"] == nokta[uid]["fiyat_kdv_haric_try"].replace(".", ",")
    assert "." not in virgul[uid]["fiyat_kdv_dahil_try"]
    assert virgul[uid]["teknik_akim"] == "2,5 A"                    # metin hücreleri değişmez
    assert nokta[uid]["teknik_tip"] == "" and nokta[uid2]["teknik_tip"] == "Başka"
    assert virgul[uid]["url"] == nokta[uid]["url"]


# =====================================================================================================
# Fix turu 1 (g3n-review.md)
# =====================================================================================================

def test_g3n_f1_iade_ozeti_ayni_yardimci(istemci, db):
    """m-1: "Teslimat ve iade" özeti iade_ozet_anahtarlari'ndan; I-1: yurt dışı misafir tüketici cümlesini de görür."""
    _kur(db)
    uid = _urun(db, sku="S-G3NO", ad="Özet Ürünü", fiyat="100.00", stok=3)
    _durum_ata(db, uid, "yeni")

    def ozet(dil):
        html = istemci.get(f"/{dil}/urun/{uid}").text
        bolum = _bolum(html, r'<details class="bolum">\s*<summary>(Teslimat ve iade|Delivery and returns)</summary>.*?</details>')
        return _metin(re.findall(r"<p>(.*?)</p>", bolum, re.S)[1])
    assert ozet("tr").startswith("Bireysel alımlarda 14 gün cayma hakkı vardır. Ticari alımda cayma hakkı yoktur")
    _ulke_ve_fiyat(istemci, "DE", "eur", "en")
    assert ozet("en").startswith("Consumers have a 14-day right of withdrawal.")
    istemci.cookies.clear()
    _musteri(db, tip=MusteriTipi.YURTDISI, eposta="g3n-f1o@ornek.test", ulke="DE", vat_id="DE123456789")
    _giris(istemci, "g3n-f1o@ornek.test", dil="en")
    assert ozet("en").startswith("Business purchase: no right of withdrawal")
    _durum_ata(db, uid, "ikinci_el_oldugu_gibi")
    assert ozet("en").startswith("Business purchase: no right of withdrawal. Sold as is: no warranty")
    _durum_ata(db, uid, "belirtilmemis")
    assert ozet("en").startswith("Business purchase: no right of withdrawal. Exception:")


def test_g3n_f1_hukuk_notu_site_kime_acik():
    notlar = open("docs/hukuk-notlari.md", encoding="utf-8").read()
    bolum = notlar[notlar.index("## Yurt dışı misafirde iade satırları"):]
    assert "site kime açık" in bolum and "2011/83/AB" in bolum and "Bekleyen madde" in bolum


def _teknikli(db, sku, uretici, veri):
    uid = _urun(db, sku=sku, ad=f"Teknik {sku}", fiyat="100.00", stok=3, uretici_kodu=uretici)
    with db:
        db.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)", (uid, json.dumps(veri, ensure_ascii=False)))
    return uid


def test_g3n_f1_buyuk_harf_bolum_basligi_ve_foy(istemci, db):
    """m-2: "TEKNİK ÖZELLİKLER" bölüm başlığı summary ile aynı sayılır; m-3: yalnız Type = parça no olan üründe föy."""
    _kur(db)
    uid = _teknikli(db, "S-G3NU", "ABC-1", {"ozellikler": [["Ağırlık", "3 kg"]],
                                           "bolumler": [["TEKNİK ÖZELLİKLER", "Kaynak notu."]]})
    bolum = _bolum(istemci.get(f"/tr/urun/{uid}").text,
                   r'<details class="bolum" open>\s*<summary id="teknik-baslik">[^<]*</summary>.*?</details>')
    assert _metin(bolum).casefold().count("teknik özellikler") == 1 and "Kaynak notu." in bolum, _metin(bolum)
    yalniz_tip = _teknikli(db, "S-G3NV", "XYZ-9", {"ozellikler": [["Type", "XYZ-9"]], "bolumler": []})
    html = istemci.get(f"/tr/urun/{yalniz_tip}").text
    assert 'class="teknik-foy"' in html and 'data-e2e="teknik-tablo"' not in html


def test_g3n_f1_karsilastirma_tip_satiri_parca_no(istemci, db):
    """Denetleyici kararı: karşılaştırma tablosunda Type/Tip = parça no hücresi gizli (ürün sayfası ve CSV kuralı)."""
    _kur(db)
    a = _teknikli(db, "S-G3NK1", "CAN-CR220", {"ozellikler": [["Type", "CAN-CR220"], ["Akım", "1 A"]], "bolumler": []})
    b = _teknikli(db, "S-G3NK2", "CAN-CR230", {"ozellikler": [["Type", "CAN-CR230"], ["Akım", "2 A"]], "bolumler": []})
    for u in (a, b):
        csrf = csrf_al(istemci, f"/tr/urun/{u}")
        istemci.post("/tr/karsilastir/ekle", data={"csrf": csrf, "urun_id": str(u), "sonraki": "/tr/"})
    html = sayfa_denetle(istemci.get("/tr/karsilastir"))
    assert '<th scope="row">Tip</th>' not in html and "Akım" in html
    c = _teknikli(db, "S-G3NK3", "Z-1", {"ozellikler": [["Type", "Başka Tip"]], "bolumler": []})
    csrf = csrf_al(istemci, f"/tr/urun/{c}")
    istemci.post("/tr/karsilastir/ekle", data={"csrf": csrf, "urun_id": str(c), "sonraki": "/tr/"})
    tablo = istemci.get("/tr/karsilastir").text
    tip = _metin(_bolum(tablo, r'<tr class="teknik-satir"[^>]*>\s*<th scope="row">Tip</th>.*?</tr>'))
    assert "Başka Tip" in tip and "CAN-CR" not in tip, tip


def test_g3n_f1_csv_virgul_dosya_adi_ve_formul_hucresi(istemci, db):
    """m-6 ayrı dosya adı; m-8 virgüllü kipte formül önekli metin hücresi yine "'" ile."""
    _kur(db)
    uid = _teknikli(db, "S-G3NF1", "F-1", {"ozellikler": [["Not", "=1+2"]], "bolumler": []})
    csrf = csrf_al(istemci, f"/tr/urun/{uid}")
    istemci.post("/tr/karsilastir/ekle", data={"csrf": csrf, "urun_id": str(uid), "sonraki": "/tr/"})
    r = istemci.get("/tr/karsilastir.csv?ondalik=virgul")
    assert 'filename="ceylan-robot-karsilastirma-virgul.csv"' in r.headers["content-disposition"]
    assert 'filename="ceylan-robot-karsilastirma.csv"' in istemci.get("/tr/karsilastir.csv").headers["content-disposition"]
    for yol in ("/tr/karsilastir.csv", "/tr/karsilastir.csv?ondalik=virgul"):
        assert _csv(istemci, yol)[0]["teknik_not"] == "'=1+2"


def test_g3n_f1_po_yansimasi_sinirli(istemci, db):
    """m-7: görünür sınırın çok üstündeki PO hata sayfasında 200 karakterle yansır; alan maxlength 200."""
    _kur(db)
    uid = _urun(db, sku="S-G3NP2", ad="PO Ürünü 2", fiyat="100.00", stok=3)
    _kurumsal(db, istemci, "g3n-p2@ornek.test")
    _sepete_ekle(istemci, uid)
    sayfa = istemci.get("/tr/odeme").text
    assert 'maxlength="200"' in _bolum(sayfa, r'<input id="musteri_po"[^>]*>')
    r = _odeme_gonder(istemci, sayfa_html=sayfa, musteri_po="Q" * 5000, odeme_yontemi="havale")
    assert r.status_code == 400
    assert f'value="{"Q" * 200}"' in _bolum(r.text, r'<input id="musteri_po"[^>]*>')
    teklif = istemci.get(f"/tr/teklif?urun_id={uid}").text
    assert 'maxlength="200"' in _bolum(teklif, r'<input[^>]*name="musteri_po"[^>]*>')
    form = {"csrf": _gizli(teklif, "csrf"), "ad": "QATest", "firma": "QATest A.Ş.", "eposta": "g3n-p2@ornek.test",
            "telefon": "+90 555 000 00 00", "ulke": "TR", "urun_id": str(uid), "adet": "1", "mesaj": "deneme",
            "musteri_po": "Q" * 5000, "kvkk_onay": "1"}
    r = istemci.post("/tr/teklif", data=form, follow_redirects=False)
    assert r.status_code == 400 and f'value="{"Q" * 200}"' in r.text and "Q" * 201 not in r.text
