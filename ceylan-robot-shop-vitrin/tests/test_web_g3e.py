"""G3e: persona tur 2 bulguları (A: doğruluk hataları 1–9, B: anlaşılırlık/güven 10–23)."""
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from html import unescape

import pytest

from app.fiyat.kur import Kur
from app.fiyat.kurallar import MusteriTipi, TeslimYontemi
from app.hesap.servis import Adres
from app.katalog.depo import ListeSorgusu, faset_sayilari, urun_listele
from app.sepet import servis as sepet_servis
from app.siparis.servis import StokYetersiz, siparis_olustur
from pathlib import Path

from tests.conftest import csrf_al, istemci_db, sayfa_denetle
from tests.test_web_katalog import katalog  # noqa: F401 — fixture
from tests.test_web_sepet_odeme import (GECERLI_VKN, _adres_formu, _giris, _gizli, _kur, _musteri, _odeme_gonder,
                                        _sepete_ekle, _siparis_no, _urun, db)  # noqa: F401


KOK_DIZIN = Path(__file__).resolve().parent.parent


def _post(istemci, yol, veri, csrf_yolu="/tr/"):
    veri = {**veri, "csrf": csrf_al(istemci, csrf_yolu)}
    return istemci.post(yol, data=veri, follow_redirects=False)


def _bildirimler(html):
    m = re.search(r'<div class="bildirimler" role="status">(.*?)</div>', html, re.S)
    return m.group(1) if m else ""


def _sepet_adedi(db, urun_id):
    r = db.execute("SELECT SUM(adet) FROM sepet_kalemi WHERE urun_id = ?", (urun_id,)).fetchone()
    return r[0] or 0


def _durum_ata(db, urun_id, kod, ornek=0):
    with db:
        db.execute("UPDATE urun SET durum_kodu = ?, durum_ornek = ? WHERE id = ?", (kod, ornek, urun_id))


# =====================================================================================================
# A1 — stok denetimi
# =====================================================================================================

def test_g3e_sepete_ekleme_stoku_asamaz_bildirim_ve_teklif_baglantisi(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-STOK1", ad="Stoklu Güç Kaynağı", fiyat="100.00", stok=1)
    yol = f"/tr/urun/{uid}"
    r = _post(istemci, "/tr/sepet/ekle", {"urun_id": uid, "adet": "99", "sonraki": yol}, yol)
    assert r.status_code == 303
    assert _sepet_adedi(db, uid) == 1
    bildirim = _bildirimler(istemci.get(r.headers["location"].split("#")[0]).text)
    assert "Sepete 1 adet eklendi; stokta yalnız 1 adet var" in bildirim     # fix 1 I-4: istenen 99 değil
    assert "99 adet" not in bildirim and "Sepete eklendi:" not in bildirim
    assert f'href="/tr/teklif?urun_id={uid}&amp;adet=99"' in bildirim
    # ikinci ekleme de stoku aşmaz; hiç eklenmediği için "eklendi" denmez
    r = _post(istemci, "/tr/sepet/ekle", {"urun_id": uid, "adet": "1", "sonraki": yol}, yol)
    assert _sepet_adedi(db, uid) == 1
    bildirim = _bildirimler(istemci.get(r.headers["location"].split("#")[0]).text)
    assert "eklendi" not in bildirim and "stokta yalnız 1 adet var" in bildirim


def test_g3e_sepet_adet_guncelleme_stoka_iner(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-STOK2", ad="Stoklu Kart", fiyat="50.00", stok=3)
    assert _sepete_ekle(istemci, uid).status_code == 303
    r = _post(istemci, "/tr/sepet/adet", {"urun_id": uid, "adet": "7"}, "/tr/sepet")
    assert r.status_code == 303
    assert _sepet_adedi(db, uid) == 3
    html = istemci.get("/tr/sepet").text
    assert "Stokta 3 adet var; adet 3&#39;e düşürüldü." in _bildirimler(html)   # G3n madde 1 metni
    assert f'href="/tr/teklif?urun_id={uid}&amp;adet=7"' in _bildirimler(html)


def test_g3e_stok_asimi_teklif_formunda_adet_onceden_dolu(istemci, db):
    uid = _urun(db, sku="S-STOK3", ad="Stoklu Motor", fiyat="50.00", stok=1)
    html = istemci.get(f"/tr/teklif?urun_id={uid}&adet=99").text
    assert re.search(r'id="adet" name="adet" type="number" value="99"', html)
    html = istemci.get(f"/tr/teklif?urun_id={uid}&adet=abc").text
    assert re.search(r'id="adet" name="adet" type="number" value="1"', html)


def test_g3e_stoku_bilinmeyen_urunde_sinir_yok_tedarik_metni(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-TED", ad="Tedarikli Ürün", fiyat="50.00", stok=0)
    assert _sepete_ekle(istemci, uid, adet="5").status_code == 303
    assert _sepet_adedi(db, uid) == 5
    html = istemci.get("/tr/sepet").text
    assert "Tedarik süresi siparişten sonra bildirilir" in html   # G3l madde 7


def test_g3e_sepette_stoktan_fazla_kalem_kendiliginden_iner(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-STOK4", ad="Azalan Stok", fiyat="50.00", stok=5)
    _sepete_ekle(istemci, uid, adet="4")
    with db:
        db.execute("UPDATE urun SET stok = 2 WHERE id = ?", (uid,))
    html = istemci.get("/tr/sepet").text
    assert _sepet_adedi(db, uid) == 2
    assert "Stokta 2 adet var" in html


def test_g3e_siparis_olusturma_islem_icinde_stoku_yeniden_denetler(con, simdi):
    from app.hesap.servis import KayitGirdisi, kayit_ol
    from tests.conftest import urun_ekle
    uid = urun_ekle(con, sku="S-YARIS", stok=1)
    with con:
        m = kayit_ol(con, KayitGirdisi(tip=MusteriTipi.KURUMSAL, ad="QATest A.Ş.", eposta="k@ornek.test",
                                       parola="demo-parola-123", ulke="TR", kvkk_onay=True,
                                       vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk"), simdi)
        sid = sepet_servis.sepet_bul(con, None, m.id, simdi)
        con.execute("INSERT INTO sepet_kalemi (sepet_id, urun_id, adet) VALUES (?, ?, 3)", (sid, uid))
    adres = Adres(ad_soyad="QATest", satir1="Adres 1", sehir="Konya", ulke="TR")
    with pytest.raises(StokYetersiz):
        with con:
            siparis_olustur(con, m, sid, TeslimYontemi.KARGO, adres, adres, None, simdi)
    assert con.execute("SELECT COUNT(*) FROM siparis").fetchone()[0] == 0


def test_g3e_odeme_gonderiminde_stok_azaldiysa_siparis_acilmaz(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-STOK5", ad="Yarış Ürünü", fiyat="100.00", stok=2)
    _musteri(db, eposta="stok@ornek.test")
    _giris(istemci, "stok@ornek.test")
    _sepete_ekle(istemci, uid, adet="2")
    sayfa = istemci.get("/tr/odeme").text
    with db:
        db.execute("UPDATE urun SET stok = 1 WHERE id = ?", (uid,))
    r = _odeme_gonder(istemci, sayfa_html=sayfa)
    assert r.status_code == 409
    assert db.execute("SELECT COUNT(*) FROM siparis").fetchone()[0] == 0
    assert _sepet_adedi(db, uid) == 1


# =====================================================================================================
# A2 — fiyat sıralaması: teklifle satılanlar iki yönde de sonda
# =====================================================================================================

@pytest.mark.parametrize("sira", ["fiyat_artan", "fiyat_azalan"])
def test_g3e_fiyat_siralamasinda_teklifliler_sonda(con, sira):
    from tests.conftest import urun_ekle
    ucuz = urun_ekle(con, sku="F1", ad="Ucuz", fiyat="2.00")
    pahali = urun_ekle(con, sku="F2", ad="Pahalı", fiyat="900.00")
    robot = urun_ekle(con, sku="F3", ad="Robot", fiyat="32000.00", teklif=True)
    sonuc = urun_listele(con, ListeSorgusu(siralama=sira))
    kimlikler = [u.id for u in sonuc.urunler]
    assert kimlikler[-1] == robot
    assert kimlikler[:2] == ([ucuz, pahali] if sira == "fiyat_artan" else [pahali, ucuz])


# =====================================================================================================
# A3 — hatalı gönderimde girilen değerler korunur (ödeme, kayıt, teklif)
# =====================================================================================================

def test_g3e_odeme_hatasinda_degerler_korunur(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-FORM", ad="Form Ürünü", fiyat="100.00", stok=5)
    _musteri(db, eposta="form@ornek.test")
    _giris(istemci, "form@ornek.test")
    _sepete_ekle(istemci, uid)
    r = _odeme_gonder(istemci, teslimat_satir1="Deneme Cd. No 42", teslimat_posta_kodu="42999",
                      teslimat_sehir="Karatay", teslimat_telefon="+90 555 111 22 33", on_bilgi_onay="")
    assert r.status_code == 400
    for deger in ("Deneme Cd. No 42", "42999", "Karatay", "+90 555 111 22 33"):
        assert f'value="{deger}"' in r.text, deger


def test_g3e_kayit_hatasinda_degerler_korunur(istemci):
    csrf = csrf_al(istemci, "/tr/kayit")
    r = istemci.post("/tr/kayit", data={"csrf": csrf, "tip": "kurumsal", "ad": "QATest Otomasyon A.Ş.",
                                        "eposta": "qatest+kayit@example.com", "parola": "demo-parola-123",
                                        "vergi_kimlik_no": "123", "vergi_dairesi": "Selçuk", "kvkk_onay": "1"})
    assert r.status_code == 400
    for deger in ("QATest Otomasyon A.Ş.", "qatest+kayit@example.com", "123", "Selçuk"):
        assert f'value="{deger}"' in unescape(r.text), deger


def test_g3e_teklif_hatasinda_degerler_korunur(istemci):
    r = _post(istemci, "/tr/teklif", {"ad": "QATestUser", "firma": "QATest A.Ş.", "eposta": "qatest@example.com",
                                      "telefon": "+90 555 000 00 00", "ulke": "TR", "adet": "10", "mesaj": "",
                                      "kvkk_onay": "1"}, "/tr/teklif")
    assert r.status_code == 400
    for deger in ("QATestUser", "QATest A.Ş.", "qatest@example.com", "+90 555 000 00 00", "10"):
        assert f'value="{deger}"' in unescape(r.text), deger


# =====================================================================================================
# A4 — iade satırı müşteri tipine göre
# =====================================================================================================

def _garanti_satiri(html):
    return re.search(r'data-e2e="garanti-satiri">(.*?)</p>', html, re.S).group(1)


def test_g3e_iade_satiri_misafirde_karma(istemci, katalog):
    with istemci_db(istemci) as con:   # G3m madde 7: belirtilmemiş durumun ticari satırı ayrı (test_web_g3m)
        con.execute("UPDATE urun SET durum_kodu = 'yeni' WHERE id = ?", (katalog["role"],))
    satir = _garanti_satiri(istemci.get(f"/tr/urun/{katalog['role']}").text)
    # G3i madde 13: misafirde bireysel ve ticari satır birlikte
    assert "Bireysel alım: 14 gün cayma hakkı (temsili)" in satir
    assert "Ticari alım: cayma hakkı yok; açık ayıplar teslimden itibaren 2 gün içinde yazılı bildirilir" in satir


def test_g3e_iade_satiri_bireyselde_14_gun(istemci, katalog, db):
    _musteri(db, eposta="b@ornek.test")
    _giris(istemci, "b@ornek.test")
    satir = _garanti_satiri(istemci.get(f"/tr/urun/{katalog['role']}").text)
    assert "İade 14 gün (temsili)" in satir


@pytest.mark.parametrize("tip,ulke,ek", [
    (MusteriTipi.KURUMSAL, "TR", {"vergi_kimlik_no": GECERLI_VKN, "vergi_dairesi": "Selçuk"}),
    (MusteriTipi.YURTDISI, "DE", {"vat_id": "DE123456789"}),
])
def test_g3e_iade_satiri_ticari_alicida_garanti(istemci, katalog, db, tip, ulke, ek):
    _musteri(db, tip=tip, eposta="t@ornek.test", ulke=ulke, **ek)
    _giris(istemci, "t@ornek.test")
    _durum_ata(db, katalog["role"], "yeni")   # G3m madde 7: belirtilmemiş durumun ticari satırı ayrı (test_web_g3m)
    html = istemci.get(f"/tr/urun/{katalog['role']}").text
    satir = _garanti_satiri(html)
    # G3i madde 13: ticari alım özeti (cayma yok, açık ayıp 2 gün içinde yazılı ihbar, garanti kapsamında değişim/iade)
    assert ("Ticari alım: cayma hakkı yok; açık ayıplar teslimden itibaren 2 gün içinde yazılı bildirilir; "
            "garanti kapsamında değişim/iade") in satir
    assert "14 gün" not in satir


# =====================================================================================================
# A5 — navlun gösterimi (ihracat) ve TR sepet toplamı "tahmini"
# =====================================================================================================

def _yurtdisi_sepet(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-DAP", ad="İhracat Ürünü", fiyat="100.00", stok=5)
    _musteri(db, tip=MusteriTipi.YURTDISI, eposta="de@ornek.test", ulke="DE", vat_id="DE123456789")
    _giris(istemci, "de@ornek.test", dil="en")
    _sepete_ekle(istemci, uid, dil="en")
    return uid


def test_g3e_navlun_sepet_odeme_kartta_sifir_kargo_yok(istemci, db):
    _yurtdisi_sepet(istemci, db)
    for yol in ("/en/sepet", "/en/odeme"):
        html = istemci.get(yol).text
        ozet = re.search(r'<dl class="tutar-ozeti">.*?</dl>', html, re.S).group(0)
        assert "Shipping" not in ozet and "€0.00" not in ozet.split("Export")[0], yol
        assert "Freight: on quotation (not included in this payment)" in ozet, yol
        assert "Goods total" in ozet, yol
    r = _odeme_gonder(istemci, dil="en", ulke="DE", teslim="yurtdisi_dap", teslimat_sehir="Berlin")
    assert r.status_code == 303, r.text
    no = _siparis_no(r.headers["location"])
    html = istemci.get(f"/en/odeme/{no}/kart").text
    ozet = re.search(r'<dl class="tutar-ozeti">.*?</dl>', html, re.S).group(0)
    assert "Shipping" not in ozet and "Freight: on quotation (not included in this payment)" in ozet
    assert re.search(r'data-e2e="kart-gonder">.*?Pay goods total', html, re.S)


def test_g3e_tr_sepet_toplami_tahmini(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-TAH", ad="Tahmini Ürün", fiyat="100.00", stok=5)
    _sepete_ekle(istemci, uid)
    html = istemci.get("/tr/sepet").text
    ozet = re.search(r'<dl class="tutar-ozeti">.*?</dl>', html, re.S).group(0)
    assert "Tahmini toplam" in ozet and "<dt>Kargo</dt>" in ozet


# =====================================================================================================
# A6 — durum etiketi "belirtilmemiş" + faset sayıları tutarlı
# =====================================================================================================

def test_g3e_durum_belirtilmemis_tr_en(istemci, katalog):
    html = istemci.get(f"/tr/urun/{katalog['role']}").text
    assert "Durum: belirtilmemiş" in html and "(satıştan önce fotoğraf/test raporuyla teyit edilir)" in html
    assert "teklifle teyit" not in html.lower()
    html = istemci.get(f"/en/urun/{katalog['role']}").text
    assert "Condition: not specified" in html and "(confirmed before sale with photos/test report)" in html
    liste = istemci.get(f"/tr/kategori/{katalog['elk']}").text
    assert "Belirtilmemiş" in liste and "Teklifle teyit" not in liste


def test_g3e_faset_sayisi_secilince_gelecek_sonuc(con):
    from tests.conftest import urun_ekle
    kimlikler = [urun_ekle(con, sku=f"D{i}", ad=f"KUKA Parça {i}" if i % 2 else f"ABB Parça {i}", stok=i % 3)
                 for i in range(12)]
    with con:
        for i, k in enumerate(kimlikler):
            con.execute("UPDATE urun SET durum_kodu = ? WHERE id = ?",
                        ("ikinci_el" if i % 4 == 0 else "belirtilmemis", k))
    for s in (ListeSorgusu(), ListeSorgusu(markalar=("KUKA",)), ListeSorgusu(stokta=True),
              ListeSorgusu(markalar=("KUKA",), durumlar=("ikinci_el",))):
        f = faset_sayilari(con, s, [])
        for x in f.durum:
            beklenen = urun_listele(con, ListeSorgusu(markalar=s.markalar, stokta=s.stokta, durumlar=(x.deger,))).toplam
            assert x.sayi == beklenen, (s, x)
        for x in f.marka:
            beklenen = urun_listele(con, ListeSorgusu(durumlar=s.durumlar, stokta=s.stokta, markalar=(x.deger,))).toplam
            assert x.sayi == beklenen, (s, x)
        if not s.durumlar:
            assert sum(x.sayi for x in f.durum) == urun_listele(con, s).toplam == f.toplam


# =====================================================================================================
# A7 — "[örnek]" yer tutucuları kalkar
# =====================================================================================================

def test_g3e_urun_sayfasinda_ornek_yer_tutucu_yok(istemci, katalog, db):
    _durum_ata(db, katalog["role"], "ikinci_el_test_edildi", ornek=1)
    html = istemci.get(f"/tr/urun/{katalog['role']}").text
    assert "[örnek]" not in html and "Mockup: değerler örnektir" not in html and "Tarih kodu" not in html
    assert '<span class="rozet rozet-ornek" title="demo için elle girilmiş durum kaydı">demo kaydı</span>' in html
    html = istemci.get(f"/en/urun/{katalog['role']}").text
    assert "[sample]" not in html and "Mockup" not in html


# =====================================================================================================
# A8 — sayfalama: aralık dışı -> son sayfa, "Son", sayfa başına 24/48 (kontrolcü kararı: 96 yok)
# =====================================================================================================

@pytest.fixture
def cok_urun(istemci):
    from tests.conftest import urun_ekle
    with istemci_db(istemci) as con:
        for i in range(60):
            urun_ekle(con, sku=f"P{i:03d}", ad=f"PARÇA {i:03d}", fiyat=f"{10 + i}.00")
    return 60


def test_g3e_aralik_disi_sayfa_son_sayfaya_302(istemci, cok_urun):
    r = istemci.get("/tr/urunler?stokta=1&sayfa=999", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/tr/urunler?stokta=1&sayfa=3"
    r = istemci.get("/tr/urunler?sayfa=0", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/tr/urunler"
    r = istemci.get("/tr/urunler?adet=48&sayfa=3", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/tr/urunler?adet=48&sayfa=2"


def test_g3e_son_sayfa_baglantisi_ve_sayfa_boyu(istemci, cok_urun):
    html = istemci.get("/tr/urunler").text
    nav = re.search(r'<nav class="sayfalama".*?</nav>', html, re.S).group(0)
    assert 'href="/tr/urunler?sayfa=3"' in nav and "Son" in nav
    assert html.count('class="ut-satir') == 24
    html = istemci.get("/tr/urunler?adet=48").text
    assert html.count('class="ut-satir') == 48
    assert re.search(r'<select id="adet" name="adet">.*?<option value="48" selected>', html, re.S)
    for gecersiz in ("7", "96"):          # fix 1 I-1: 96 ve diğer değerler 24'e düşer
        html = istemci.get(f"/tr/urunler?adet={gecersiz}").text
        assert html.count('class="ut-satir') == 24
        assert 'value="96"' not in html
    nav = re.search(r'<nav class="sayfalama".*?</nav>', istemci.get("/tr/urunler?adet=48").text, re.S).group(0)
    assert 'href="/tr/urunler?adet=48&amp;sayfa=2"' in nav


def test_g3e_sayfa_boyu_robots_ve_canonical(istemci_uretim):
    robots = istemci_uretim.get("/robots.txt").text
    assert "Disallow: /*?*adet=" in robots
    html = istemci_uretim.get("/tr/urunler?adet=48").text
    assert '<link rel="canonical" href="https://shop.example.com/tr/urunler">' in html


# =====================================================================================================
# A9 — fiyat aralığı görünen para birimi ve KDV kipinde
# =====================================================================================================

def test_g3e_fiyat_araligi_misafir_try_kdv_dahil(istemci, katalog):
    # RÖLE 120 € net, kur 35,20, KDV %20 -> 5.068,80 ₺ KDV dahil; SİGORTA 40 € -> 1.689,60 ₺
    html = istemci.get(f"/tr/kategori/{katalog['elk']}?fmin=5000&fmax=5100").text
    assert "RÖLE MODÜLÜ 24V" in html and "SİGORTA KUTUSU" not in html
    assert "₺, KDV dahil" in html
    cipler = re.search(r'<ul class="cipler".*?</ul>', html, re.S).group(0)
    assert "En az 5.000,00 ₺" in cipler and "En çok 5.100,00 ₺" in cipler


def test_g3e_fiyat_araligi_kurumsal_eur_net(istemci, katalog, db):
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="kf@ornek.test", vergi_kimlik_no=GECERLI_VKN,
             vergi_dairesi="Selçuk")
    _giris(istemci, "kf@ornek.test")
    html = istemci.get(f"/tr/kategori/{katalog['elk']}?fmin=100&fmax=130").text
    assert "RÖLE MODÜLÜ 24V" in html and "SİGORTA KUTUSU" not in html
    assert "€, KDV hariç" in html


def test_g3e_fiyat_araligi_ters_girilince_bildirilir(istemci, katalog):
    html = istemci.get(f"/tr/kategori/{katalog['elk']}?fmin=5100&fmax=5000").text
    assert "RÖLE MODÜLÜ 24V" in html
    assert "En az &gt; en çok: değerler yer değiştirildi" in html      # G3g madde 9 metni


# =====================================================================================================
# B10 — parça no önceliği: üretici kodu büyük "Parça no", iç SKU küçük "Stok kodu"
# =====================================================================================================

@pytest.fixture
def kodlu(istemci, katalog):
    from tests.conftest import urun_ekle
    with istemci_db(istemci) as con:
        uid = urun_ekle(con, sku="8503053800001", ad="KUKA KRC2 GÜÇ KAYNAĞI 27V-NT", kok="Elektrik ve Elektronik",
                        fiyat="3621.00", kategori_id=katalog["kontrol"], stok=2, uretici_kodu="00-109-802")
    return {**katalog, "kodlu": uid}


def test_g3e_urun_sayfasi_parca_no_uretici_kodu(istemci, kodlu):
    html = sayfa_denetle(istemci.get(f"/tr/urun/{kodlu['kodlu']}"))
    kodlar = re.search(r'<dl class="urun-kodlar">.*?</dl>', html, re.S).group(0)
    assert re.search(r'<dt>Parça no</dt>\s*<dd><span class="parca-no">00-109-802</span>', kodlar)
    assert 'data-kopyala="00-109-802"' in kodlar
    assert re.search(r'<dt>Stok kodu</dt>\s*<dd><span class="parca-no stok-kodu">8503053800001</span>', kodlar)
    assert "Üretici kodu" not in kodlar
    ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
    assert '"sku":"8503053800001"' in ld and '"mpn":"00-109-802"' in ld
    # üretici kodu yoksa parça no iç koddur; "Stok kodu" satırı yok
    kodlar = re.search(r'<dl class="urun-kodlar">.*?</dl>', istemci.get(f"/tr/urun/{kodlu['role']}").text, re.S).group(0)
    assert '<span class="parca-no">RL-24</span>' in kodlar and "Stok kodu" not in kodlar


def test_g3e_liste_kart_sepet_karsilastirma_parca_no(istemci, kodlu, db):
    liste = istemci.get(f"/tr/kategori/{kodlu['kontrol']}").text
    satir = re.search(rf'<tr class="ut-satir[^"]*" id="urun-{kodlu["kodlu"]}">.*?</tr>', liste, re.S).group(0)
    assert re.search(r'<span class="ut-kodlar"><span class="parca-no">00-109-802</span>', satir)
    assert "Stok kodu 8503053800001" in satir
    ana = istemci.get("/tr/").text
    kart = re.search(rf'<article class="kart" id="urun-{kodlu["kodlu"]}">.*?</article>', ana, re.S).group(0)
    assert '<p class="kart-sku"><span class="parca-no">00-109-802</span>' in kart and "Stok kodu 8503053800001" in kart
    _kur(db)
    _sepete_ekle(istemci, kodlu["kodlu"])
    sepet = istemci.get("/tr/sepet").text
    kalem = re.search(r'<tr data-e2e="sepet-kalemi">.*?</tr>', sepet, re.S).group(0)
    assert '<span class="parca-no">00-109-802</span>' in kalem and "Stok kodu 8503053800001" in kalem
    _post(istemci, "/tr/karsilastir/ekle", {"urun_id": kodlu["kodlu"], "sonraki": "/tr/karsilastir"})
    _post(istemci, "/tr/karsilastir/ekle", {"urun_id": kodlu["role"], "sonraki": "/tr/karsilastir"})
    tablo = istemci.get("/tr/karsilastir").text
    assert re.search(r'<th scope="row">Parça no</th>\s*<td class="parca-no">00-109-802</td><td class="parca-no">RL-24</td>',
                     tablo)
    assert re.search(r'<th scope="row">Stok kodu</th>\s*<td class="parca-no">8503053800001</td>', tablo)


# =====================================================================================================
# B11 — tahmini varış tarihi aralığı (iş günü, hafta sonu atlanır)
# =====================================================================================================

def test_g3e_is_gunu_araligi():
    from app.web.teslim import is_gunu_ekle
    pazartesi = date(2026, 10, 12)
    assert is_gunu_ekle(pazartesi, 2) == date(2026, 10, 14)
    assert is_gunu_ekle(pazartesi, 4) == date(2026, 10, 16)
    assert is_gunu_ekle(pazartesi, 8) == date(2026, 10, 22)
    assert is_gunu_ekle(date(2026, 10, 16), 1) == date(2026, 10, 19)     # cuma + 1 -> pazartesi
    assert is_gunu_ekle(date(2026, 10, 17), 2) == date(2026, 10, 20)     # cumartesi + 2 -> salı


@pytest.fixture
def sabit_gun(monkeypatch):
    import app.web.baglam as baglam_modulu
    monkeypatch.setattr(baglam_modulu, "simdi", lambda: datetime(2026, 10, 12, 9, 0, tzinfo=UTC))   # pazartesi


def test_g3e_teslim_tarihi_tr_ab_diger(istemci, katalog, sabit_gun):
    html = istemci.get(f"/tr/urun/{katalog['role']}").text
    # G3n madde 6: tek biçim "Kargoya veriliş: 1–2 iş günü · varış: <aralık> (temsili)"; liste de aynı metin
    assert re.search(r'data-e2e="teslim-suresi">.*?Kargoya veriliş: 1–2 iş günü · varış: 14–16 Ekim \(temsili\)',
                     html, re.S)
    liste = istemci.get(f"/tr/kategori/{katalog['kontrol']}").text
    assert "Kargoya veriliş: 1–2 iş günü · varış: 14–16 Ekim (temsili)" in liste
    istemci.cookies.set("ulke", "DE")
    html = istemci.get(f"/en/urun/{katalog['role']}").text
    assert "Dispatch: 1–2 business days · arrival: Oct 16–22 (indicative)" in html
    istemci.cookies.set("ulke", "US")
    html = istemci.get(f"/tr/urun/{katalog['role']}").text
    assert "Teslim süresi teklifle" in html and "Kargoya veriliş" not in html
    html = istemci.get(f"/tr/urun/{katalog['stoksuz']}").text
    assert "Tedarik süresi siparişten sonra bildirilir" in html   # G3l madde 7


def test_g3e_teslim_tarihi_sepet_odeme_ve_siparis(istemci, db, sabit_gun):
    _kur(db)
    uid = _urun(db, sku="S-TES", ad="Teslim Ürünü", fiyat="100.00", stok=5)
    _musteri(db, eposta="tes@ornek.test")
    _giris(istemci, "tes@ornek.test")
    _sepete_ekle(istemci, uid)
    assert "varış: 14–16 Ekim" in istemci.get("/tr/sepet").text      # G3n madde 6 biçimi
    sayfa = istemci.get("/tr/odeme").text
    ozet = re.search(r'<aside class="siparis-ozeti".*?</aside>', sayfa, re.S).group(0)
    assert "varış: 14–16 Ekim" in ozet
    r = _odeme_gonder(istemci, sayfa_html=sayfa)
    no = _siparis_no(r.headers["location"])
    with db:
        db.execute("UPDATE siparis SET olusturma = ?, durum = 'odendi' WHERE no = ?", ("2026-10-12T09:00:00+00:00", no))
    html = istemci.get(f"/tr/siparis/{no}").text
    assert "Kargoya veriliş: 1–2 iş günü · varış: 14–16 Ekim (temsili)" in html


# =====================================================================================================
# B12 — ihracat KDV metni
# =====================================================================================================

IHRACAT_TR = ("Türkiye KDV'si uygulanmaz (ihracat, KDVK md. 11/1-a). Varış ülkesindeki ithalat KDV'si ve gümrük "
              "vergileri alıcıya aittir (DAP). VAT numaranız faturada yer alır.")
IHRACAT_EN = ("Turkish VAT does not apply (export, Turkish VAT Law Art. 11/1-a). Import VAT and customs duties in the "
              "destination country are borne by the buyer (DAP). Your VAT number is shown on the invoice.")


def _ihracat_satiri(html):
    m = re.search(r'data-e2e="ihracat-kdv">(.*?)</p>', html, re.S)
    assert m, "ihracat KDV satırı yok"
    return unescape(m.group(1))


def test_g3e_ihracat_kdv_metni_urun_sepet_odeme_kart(istemci, db):
    _yurtdisi_sepet(istemci, db)
    uid = db.execute("SELECT id FROM urun WHERE sku = 'S-DAP'").fetchone()[0]
    for yol in (f"/tr/urun/{uid}", "/tr/sepet", "/tr/odeme"):
        satir = _ihracat_satiri(istemci.get(yol).text)
        assert IHRACAT_TR in satir and 'href="/tr/yasal/kullanim#ihracat-export"' in satir, yol   # G3m madde 25
    for yol in (f"/en/urun/{uid}", "/en/sepet", "/en/odeme"):
        html = istemci.get(yol).text
        assert IHRACAT_EN in _ihracat_satiri(html) and "reverse charge" not in html.lower(), yol
    r = _odeme_gonder(istemci, dil="en", ulke="DE", teslim="yurtdisi_dap", teslimat_sehir="Berlin")
    no = _siparis_no(r.headers["location"])
    html = istemci.get(f"/en/odeme/{no}/kart").text
    assert IHRACAT_EN in _ihracat_satiri(html) and 'href="/en/yasal/kullanim#ihracat-export"' in _ihracat_satiri(html)


def test_g3e_ihracat_ayrinti_capasi_yasal_sayfada(istemci):
    for dil in ("tr", "en"):
        html = istemci.get(f"/{dil}/yasal/kullanim").text
        assert 'id="ihracat"' in html
        assert "reverse charge" not in html.lower()


def test_g3e_tr_teslimde_ihracat_satiri_yok(istemci, katalog):
    assert 'data-e2e="ihracat-kdv"' not in istemci.get(f"/tr/urun/{katalog['role']}").text


# =====================================================================================================
# B13 — ülke varsayılanı Accept-Language bölgesinden
# =====================================================================================================

def _fiyat_ana(html):
    return re.search(r'data-e2e="fiyat-ana" data-para="(\w+)" data-kdv="(\w+)"', html).groups()


def test_g3e_ulke_accept_language_bolgesi(istemci, katalog):
    html = istemci.get(f"/en/urun/{katalog['role']}", headers={"Accept-Language": "de-DE,de;q=0.9,en;q=0.8"}).text
    assert _fiyat_ana(html) == ("EUR", "haric")
    assert '<option value="DE" selected>' in html
    html = istemci.get(f"/tr/urun/{katalog['role']}", headers={"Accept-Language": "tr-TR,tr;q=0.9"}).text
    assert _fiyat_ana(html) == ("TRY", "dahil")


def test_g3e_ulke_secilmemis_en_eur_net_ve_ipucu(istemci, katalog):
    html = istemci.get(f"/en/urun/{katalog['role']}", headers={"Accept-Language": "en-CA,en;q=0.9"}).text
    assert _fiyat_ana(html) == ("EUR", "haric")
    assert 'data-e2e="ulke-sec-ipucu"' in html and "Select your country" in html
    assert re.search(r'<select id="sec-ulke" name="ulke">\s*<option value="" selected>', html)
    html = istemci.get(f"/tr/urun/{katalog['role']}", headers={"Accept-Language": "en-CA"}).text
    assert _fiyat_ana(html) == ("TRY", "dahil") and 'data-e2e="ulke-sec-ipucu"' not in html


def test_g3e_secilen_ulke_accept_language_onune_gecer(istemci, katalog):
    istemci.cookies.set("ulke", "TR")
    html = istemci.get(f"/en/urun/{katalog['role']}", headers={"Accept-Language": "de-DE"}).text
    assert _fiyat_ana(html) == ("TRY", "dahil")


# =====================================================================================================
# B14 — listede ikincil fiyat satırı (KDV karşılığı)
# =====================================================================================================

def test_g3e_listede_kdv_karsiligi(istemci, katalog):
    liste = istemci.get(f"/tr/kategori/{katalog['kontrol']}").text
    satir = re.search(rf'<tr class="ut-satir[^"]*" id="urun-{katalog["role"]}">.*?</tr>', liste, re.S).group(0)
    assert 'data-e2e="fiyat-kdv-karsilik">KDV hariç: 4.224,00 ₺' in satir


# =====================================================================================================
# B15 — havale/EFT (proforma) kurumsal ve yurt dışında
# =====================================================================================================

def _kurumsal_sepet(istemci, db, eposta="kur@ornek.test"):
    _kur(db)
    uid = _urun(db, sku="S-HAV", ad="Havale Ürünü", fiyat="100.00", stok=5)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta=eposta, vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    _giris(istemci, eposta)
    _sepete_ekle(istemci, uid)
    return uid


def test_g3e_odeme_yontemi_secenekleri(istemci, db):
    _kurumsal_sepet(istemci, db)
    html = istemci.get("/tr/odeme").text
    assert re.search(r'<input type="radio" id="odeme-kart" name="odeme_yontemi" value="kart" checked>', html)
    assert 'name="odeme_yontemi" value="havale"' in html and "Havale/EFT (proforma fatura)" in html
    _post(istemci, "/tr/cikis", {}, "/tr/")
    _musteri(db, eposta="bir@ornek.test")
    _giris(istemci, "bir@ornek.test")
    _sepete_ekle(istemci, db.execute("SELECT id FROM urun WHERE sku = 'S-HAV'").fetchone()[0])
    assert "odeme_yontemi" not in istemci.get("/tr/odeme").text


def test_g3e_havale_siparisi_proforma_ve_zaman_asimi_yok(istemci, db):
    _kurumsal_sepet(istemci, db)
    r = _odeme_gonder(istemci, odeme_yontemi="havale")
    assert r.status_code == 303 and re.fullmatch(r"/tr/siparis/CR-DEMO-\d{8}-\d{4}", r.headers["location"])
    no = r.headers["location"].rsplit("/", 1)[1]
    html = sayfa_denetle(istemci.get(r.headers["location"]))
    assert 'data-durum="odeme_bekliyor"' in html
    proforma = re.search(r'<section class="proforma" data-e2e="proforma".*?</section>', html, re.S).group(0)
    assert "IBAN" in proforma and "(temsili)" in proforma and no in proforma
    assert f'href="/tr/odeme/{no}/kart"' not in html
    assert istemci.get(f"/tr/odeme/{no}/kart", follow_redirects=False).headers["location"] == f"/tr/siparis/{no}"
    with db:
        db.execute("UPDATE siparis SET olusturma = ? WHERE no = ?", ("2026-01-01T09:00:00+00:00", no))
    assert 'data-durum="odeme_bekliyor"' in istemci.get(f"/tr/siparis/{no}").text   # 30 dk zaman aşımı yok
    assert db.execute("SELECT odeme_yontemi FROM siparis WHERE no = ?", (no,)).fetchone()[0] == "havale"


def test_g3e_bireysel_havale_secemez_kart_varsayilan(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-BIR", ad="Bireysel Ürün", fiyat="100.00", stok=5)
    _musteri(db, eposta="bh@ornek.test")
    _giris(istemci, "bh@ornek.test")
    _sepete_ekle(istemci, uid)
    r = _odeme_gonder(istemci, odeme_yontemi="havale")
    assert r.status_code == 303 and r.headers["location"].endswith("/kart")
    assert db.execute("SELECT odeme_yontemi FROM siparis").fetchone()[0] == "kart"


def test_g3e_yonetimde_odeme_bekleniyor_suzgeci(istemci, db):
    from tests.test_web_teklif_yonetim import _yonetici_giris
    _kurumsal_sepet(istemci, db)
    r = _odeme_gonder(istemci, odeme_yontemi="havale")
    no = r.headers["location"].rsplit("/", 1)[1]
    _yonetici_giris(istemci)
    html = istemci.get("/yonetim/siparisler").text
    assert 'href="/yonetim/siparisler?durum=odeme_bekliyor"' in html
    html = istemci.get("/yonetim/siparisler?durum=odeme_bekliyor").text
    assert no in html and "Havale/EFT" in html
    assert no not in istemci.get("/yonetim/siparisler?durum=odendi").text


def test_g3e_yazdirma_css(istemci):
    css = istemci.get("/statik/site.css").text
    assert "@media print" in css and ".proforma" in css


# =====================================================================================================
# B16 — hesapsız yol: sepeti teklif olarak gönder
# =====================================================================================================

def test_g3e_sepeti_teklif_olarak_gonder_baglantisi(istemci, db):
    uid = _urun(db, sku="S-ST1", ad="Sepet Teklif Ürünü", fiyat="100.00", stok=5)
    _sepete_ekle(istemci, uid, adet="2")
    for yol in ("/tr/giris?sonraki=/tr/odeme", "/tr/sepet"):
        html = istemci.get(yol).text
        assert re.search(r'<a class="dugme ikincil" href="/tr/teklif\?sepet=1" data-e2e="sepet-teklif">'
                         r'Sepeti teklif olarak gönder</a>', html), yol          # G3g madde 2: herkes için


def test_g3e_sepet_teklif_formu_dolu_telefon_zorunlu(istemci, db):
    a = _urun(db, sku="S-ST2", ad="Birinci Ürün", fiyat="100.00", stok=5, uretici_kodu="ABC-1")
    b = _urun(db, sku="S-ST3", ad="İkinci Ürün", fiyat="50.00", stok=5)
    _sepete_ekle(istemci, a, adet="2")
    _sepete_ekle(istemci, b, adet="1")
    html = istemci.get("/tr/teklif?sepet=1").text
    mesaj = unescape(re.search(r'<textarea id="mesaj"[^>]*>(.*?)</textarea>', html, re.S).group(1))
    # G3g madde 2: kalemler mesaj yerine düzenlenebilir satırlarda (ürün, parça no, adet)
    assert mesaj == "Sepetimdeki ürünler için teklif rica ederim."
    assert "ABC-1" in html and "S-ST3" in html
    assert '<input type="hidden" name="kaynak" value="sepet">' in html
    assert re.search(r'id="telefon" name="telefon" type="tel"[^>]*required', html)
    veri = {"kaynak": "sepet", "ad": "QATestUser", "ulke": "TR", "mesaj": mesaj, "kvkk_onay": "1",
            "kalem_urun": [str(a), str(b)], "kalem_adet": ["2", "1"]}
    r = _post(istemci, "/tr/teklif", veri, "/tr/teklif?sepet=1")
    assert r.status_code == 400 and 'id="hata-telefon"' in r.text
    r = _post(istemci, "/tr/teklif", {**veri, "telefon": "+90 555 000 00 00"}, "/tr/teklif?sepet=1")
    assert r.status_code == 303
    kayit = db.execute("SELECT eposta, telefon, mesaj, id FROM teklif").fetchone()
    assert kayit[0] is None and kayit[2] == mesaj
    assert [tuple(x) for x in db.execute("SELECT urun_id, adet FROM teklif_kalem WHERE teklif_id = ?",
                                         (kayit[3],))] == [(a, 2), (b, 1)]


def test_g3e_tek_kalemli_sepet_urun_ve_adet_dolu(istemci, db):
    a = _urun(db, sku="S-ST4", ad="Tek Ürün", fiyat="100.00", stok=9)
    _sepete_ekle(istemci, a, adet="3")
    html = istemci.get("/tr/teklif?sepet=1").text
    # G3g madde 2: tek kalem de düzenlenebilir satır olarak gelir
    assert f'name="kalem_urun" value="{a}"' in html
    assert re.search(r'name="kalem_adet"[^>]*value="3"', html)


# =====================================================================================================
# B17 — teklif formu: profil bilgileri ve yeni alanlar
# =====================================================================================================

def test_g3e_teklif_kurumsal_profil_dolu(istemci, db):
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="tk@ornek.test", vergi_kimlik_no=GECERLI_VKN,
             vergi_dairesi="Selçuk")
    _giris(istemci, "tk@ornek.test")
    html = istemci.get("/tr/teklif").text
    assert 'id="firma" name="firma" type="text" value="QATestUser kurumsal"' in html
    assert f'id="vkn" name="vkn" type="text" value="{GECERLI_VKN}"' in html
    assert 'id="vergi_dairesi" name="vergi_dairesi" type="text" value="Selçuk"' in html


def test_g3e_teklif_yeni_alanlar_kaydedilir_ve_yonetimde(istemci, db):
    from tests.test_web_teklif_yonetim import _yonetici_giris
    html = istemci.get("/tr/teklif").text
    for ad in ("istenen_tarih", "hedef_fiyat", "parca_kodu"):
        assert f'name="{ad}"' in html, ad
    assert 'id="istenen_tarih" name="istenen_tarih" type="date"' in html
    uid = _urun(db, sku="S-TK", ad="Teklif Ürünü", fiyat="100.00")
    urunlu = istemci.get(f"/tr/teklif?urun_id={uid}").text
    ana_form = re.search(r'<form method="post" action="/tr/teklif".*?</form>', urunlu, re.S).group(0)
    assert 'name="parca_kodu"' not in ana_form          # ürünlü formda yok (G3g: alttaki hızlı talep formu ayrı)
    veri = {"ad": "QATestUser", "eposta": "qatest@example.com", "ulke": "TR", "adet": "10", "mesaj": "Fiyat rica",
            "kvkk_onay": "1", "istenen_tarih": "2026-11-20", "hedef_fiyat": "10+ adet için %8 iskonto",
            "parca_kodu": "00-109-802"}
    r = _post(istemci, "/tr/teklif", {**veri, "istenen_tarih": "20.11.2026"}, "/tr/teklif")
    assert r.status_code == 400 and 'id="hata-istenen_tarih"' in r.text
    r = _post(istemci, "/tr/teklif", veri, "/tr/teklif")
    assert r.status_code == 303
    kayit = db.execute("SELECT istenen_tarih, hedef_fiyat, parca_kodu FROM teklif").fetchone()
    assert tuple(kayit) == ("2026-11-20", "10+ adet için %8 iskonto", "00-109-802")
    tamam = istemci.get(r.headers["location"]).text
    assert "1 iş günü içinde yanıt verir (temsili)" in tamam
    _yonetici_giris(istemci)
    yonetim = istemci.get("/yonetim/teklifler").text
    assert "00-109-802" in yonetim and "10+ adet için %8 iskonto" in yonetim and "20.11.2026" in yonetim  # G3k m. 12


# =====================================================================================================
# B18 — sepete eklendi bildirimi: "Sepete git" + "Ödemeye geç"; POST dönüşü #urun-<id>
# =====================================================================================================

def test_g3e_sepete_ekle_capa_ve_iki_baglanti(istemci, katalog):
    yol = f"/tr/kategori/{katalog['kontrol']}?stokta=1"
    r = _post(istemci, "/tr/sepet/ekle", {"urun_id": katalog["role"], "adet": "1", "sonraki": yol}, yol)
    assert r.headers["location"] == f"{yol}#urun-{katalog['role']}"
    html = istemci.get(yol).text
    bildirim = _bildirimler(html)
    assert '<a href="/tr/sepet" data-e2e="sepete-git">Sepete git</a>' in bildirim
    assert '<a href="/tr/odeme" data-e2e="bildirim-odemeye-gec">Ödemeye geç</a>' in bildirim
    assert f'id="urun-{katalog["role"]}"' in html


def test_g3e_karsilastir_capa(istemci, katalog):
    yol = f"/tr/kategori/{katalog['kontrol']}"
    r = _post(istemci, "/tr/karsilastir/ekle", {"urun_id": katalog["role"], "sonraki": yol}, yol)
    assert r.headers["location"] == f"{yol}#urun-{katalog['role']}"
    r = _post(istemci, "/tr/karsilastir/kaldir", {"urun_id": katalog["role"], "sonraki": yol}, yol)
    assert r.headers["location"] == f"{yol}#urun-{katalog['role']}"


# =====================================================================================================
# B19 — 0 ürünlü kategoriler menüde yok; EN büyük harf adlar Title Case
# =====================================================================================================

def test_g3e_bos_kategori_menude_yok_url_calisir(istemci, katalog):
    from tests.conftest import kategori_ekle
    with istemci_db(istemci) as con:
        bos = kategori_ekle(con, kaynak_id="k99", ad="Pozisyonerler", yol="99", seviye=0)
    for yol in ("/tr/", f"/tr/kategori/{katalog['elk']}", "/tr/sepet"):
        assert f'href="/tr/kategori/{bos}"' not in istemci.get(yol).text, yol
    assert istemci.get(f"/tr/kategori/{bos}").status_code == 200


def test_g3e_en_kategori_adlari_title_case(istemci, katalog):
    from app.katalog.kategori_ceviri import baslik_bicimi
    assert baslik_bicimi("ABB ROBOT PARTS") == "ABB Robot Parts"
    assert baslik_bicimi("CABLES AND CONNECTORS") == "Cables and Connectors"
    assert baslik_bicimi("KUKA ROBOT PARTS") == "KUKA Robot Parts"
    assert baslik_bicimi("GÜÇ KAYNAKLARI", turkce=True) == "Güç Kaynakları"
    assert baslik_bicimi("KR C4") == "KR C4"
    assert baslik_bicimi("Robot Control Units") == "Robot Control Units"
    html = istemci.get(f"/en/kategori/{katalog['kontrol']}").text
    assert "Control Systems" in html and "CONTROL SYSTEMS" not in html
    assert "KONTROL SISTEMLERI" in istemci.get(f"/tr/kategori/{katalog['kontrol']}").text


# =====================================================================================================
# B20 — EN/TR/DE arama eşanlamlıları
# =====================================================================================================

@pytest.fixture
def esanlam_katalog(con):
    from tests.conftest import urun_ekle
    return {
        "kaynak": urun_ekle(con, sku="E1", ad="KUKA KRC2 GÜÇ KAYNAĞI 27V-NT"),
        "surucu": urun_ekle(con, sku="E2", ad="ABB DSQC 663 SERVO SÜRÜCÜ"),
        "kablo": urun_ekle(con, sku="E3", ad="FANUC ENKODER KABLOSU"),
        "lumberg": urun_ekle(con, sku="E4", ad="LUMBERG POWER SUPPLY CONNECTOR"),
        "reduktor": urun_ekle(con, sku="E5", ad="NABTESCO REDÜKTÖR RV-80E"),
    }


@pytest.mark.parametrize("sorgu,anahtar", [
    ("power supply", "kaynak"), ("Netzteil", "kaynak"), ("Stromversorgung", "kaynak"), ("güç kaynağı", "kaynak"),
    # G3k madde 4: "Umrichter" artık yalnız frekans konvertörü (sürücü değil); sürücü için "Antrieb"
    ("servo drive", "surucu"), ("Antrieb", "surucu"), ("cable", "kablo"), ("Kabel", "kablo"),
    ("gearbox", "reduktor"), ("Getriebe", "reduktor"), ("KUKA power supply", "kaynak"),
])
def test_g3e_esanlamli_arama(con, esanlam_katalog, sorgu, anahtar):
    sonuc = urun_listele(con, ListeSorgusu(arama=sorgu))
    assert esanlam_katalog[anahtar] in [u.id for u in sonuc.urunler], sorgu


def test_g3e_esanlamli_aramada_ingilizce_ad_da_bulunur(con, esanlam_katalog):
    kimlikler = {u.id for u in urun_listele(con, ListeSorgusu(arama="power supply")).urunler}
    assert {esanlam_katalog["kaynak"], esanlam_katalog["lumberg"]} <= kimlikler
    assert esanlam_katalog["kablo"] not in kimlikler


def test_g3e_esanlamli_arama_web(istemci, katalog):
    from tests.conftest import urun_ekle
    with istemci_db(istemci) as con:
        urun_ekle(con, sku="8503053800001", ad="KUKA KRC2 GÜÇ KAYNAĞI 27V-NT", stok=2)
    html = istemci.get("/en/ara", params={"q": "Netzteil"}).text
    assert "KUKA KRC2 GÜÇ KAYNAĞI 27V-NT" in html


# =====================================================================================================
# B21 — künye ve iletişim
# =====================================================================================================

def test_g3e_kunye_doldurulacak_yok_iletisim_saatleri(istemci):
    for dil, not_, saat in (("tr", "Demo: üretimde doldurulacak", "Hafta içi 08:30–18:00 (TSİ, UTC+3)"),
                            ("en", "Demo: to be completed for production", "Mon–Fri 08:30–18:00 (TRT, UTC+3)")):
        html = istemci.get(f"/{dil}/yasal/kunye").text
        assert "[doldurulacak]" not in html and not_ in html and saat in html
        assert "MERSİS" not in html and "KEP" not in html
        assert 'data-e2e="kunye-eposta"' not in html     # ayarda e-posta yok: satır gizli


def test_g3e_kunye_eposta_ayardan(tmp_path):
    from fastapi.testclient import TestClient
    from app.ayarlar import Ayarlar, ayarlari_oku
    from app.hesap.servis import parola_ozeti
    from app.web.uygulama import uygulama_olustur
    from tests.conftest import TEST_GIZLI
    ayarlar = Ayarlar(db_yolu=tmp_path / "k.db", gizli_anahtar=TEST_GIZLI, yonetici_kullanici="yonetici",
                      yonetici_parola_ozeti=parola_ozeti("yonetici-parola-123"), eposta="satis@ornek.test")
    with TestClient(uygulama_olustur(ayarlar)) as c:
        html = c.get("/tr/yasal/kunye").text
    assert re.search(r'data-e2e="kunye-eposta"><a href="mailto:satis@ornek.test">satis@ornek.test</a>', html)
    ortam = {"SHOP_DB": "x.db", "SHOP_GIZLI_ANAHTAR": "g" * 32, "SHOP_YONETICI": "y", "SHOP_YONETICI_OZET": "o"}
    assert ayarlari_oku({**ortam, "SHOP_EPOSTA": " satis@ornek.test "}).eposta == "satis@ornek.test"
    assert ayarlari_oku(ortam).eposta == ""


# =====================================================================================================
# B22 — mobil: dil seçici kısa kod, ana sayfada tek arama kutusu
# =====================================================================================================

def test_g3e_dil_secici_kisa_kod(istemci, katalog):
    html = istemci.get("/tr/").text
    secici = re.search(r'<select id="sec-dil" name="dil">.*?</select>', html, re.S).group(0)
    assert re.search(r'<option value="tr" selected title="Türkçe">TR</option>', secici)
    assert re.search(r'<option value="en" title="English">EN</option>', secici)


def test_g3e_ana_sayfa_mobilde_tek_arama(istemci):
    """Arama yalnız üst çubukta. Kahraman ikinci bir form taşımaz (mobilde de tek kutu)."""
    html = istemci.get("/tr/").text
    assert html.count('role="search"') == 1
    assert 'id="ust-arama"' in html
    kahraman = re.search(r'<section class="kahraman".*?</section>', html, re.S).group(0)
    assert "<form" not in kahraman


# =====================================================================================================
# B23 — karşılaştırma: kaydırma ipucu, boş satırlar gizli, farklılıklar, uzun değer
# =====================================================================================================

def test_g3e_karsilastirma_tablosu(istemci, katalog):
    uzun = "Yaklaşık 9.04 lbs - 11 kg civarı " + "x" * 200
    with istemci_db(istemci) as con:
        con.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)", (
            katalog["role"],
            '{"ozellikler":[["Gerilim","24 V"],["Ağırlık","%s"],["Ortak","aynı"]],"bolumler":[]}' % uzun))
        con.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)", (
            katalog["stoksuz"], '{"ozellikler":[["Gerilim","230 V"],["Ortak","aynı"]],"bolumler":[]}'))
    for u in (katalog["role"], katalog["stoksuz"]):
        _post(istemci, "/tr/karsilastir/ekle", {"urun_id": u, "sonraki": "/tr/karsilastir"})
    html = sayfa_denetle(istemci.get("/tr/karsilastir"))
    assert 'class="karsilastir-kaydir"' not in html     # G3g madde 18: iki ürün dar ekranda yan yana; ipucu 3 üründe
    assert '<th scope="row">Üretici kodu</th>' not in html and '<th scope="row">Marka</th>' not in html  # tümü "—"
    assert '<th scope="row">Ortak</th>' in html
    hucre = re.search(r'<details class="uzun-deger"><summary>(.*?)</summary>(.*?)</details>', html, re.S)
    assert hucre and len(unescape(hucre.group(1)).rstrip("…")) <= 140 and uzun in unescape(hucre.group(2))
    assert 'href="/tr/karsilastir?fark=1"' in html             # G3h madde 12: onay kutusu yerine bağlantı
    fark = istemci.get("/tr/karsilastir?fark=1").text
    assert '<th scope="row">Ortak</th>' not in fark and '<th scope="row">Gerilim</th>' in fark
    assert '<a href="/tr/karsilastir?fark=1" aria-current="page">' in fark


# =====================================================================================================
# Düzeltme turu 1
# =====================================================================================================

def test_fix1_havale_sepeti_bosaltir_sonraki_odeme_iptal_etmez(istemci, db):
    """I-2: havale siparişi sepeti boşaltır; sonraki ödeme gönderimi bekleyen havale siparişini iptal etmez."""
    _kurumsal_sepet(istemci, db)
    r = _odeme_gonder(istemci, odeme_yontemi="havale")
    no = r.headers["location"].rsplit("/", 1)[1]
    assert db.execute("SELECT COUNT(*) FROM sepet_kalemi").fetchone()[0] == 0
    uid2 = _urun(db, sku="S-HAV2", ad="İkinci Ürün", fiyat="50.00", stok=5)
    _sepete_ekle(istemci, uid2)
    r = _odeme_gonder(istemci)
    assert r.status_code == 303 and r.headers["location"].endswith("/kart")
    assert db.execute("SELECT durum FROM siparis WHERE no = ?", (no,)).fetchone()[0] == "odeme_bekliyor"


def _uc_musteri_sepet(con, simdi, stok=1, adetler=(1, 1)):
    from app.hesap.servis import KayitGirdisi, kayit_ol
    from tests.conftest import urun_ekle
    uid = urun_ekle(con, sku="S-SON", stok=stok)
    sonuc = []
    with con:
        for i, adet in enumerate(adetler):
            m = kayit_ol(con, KayitGirdisi(tip=MusteriTipi.BIREYSEL, ad=f"QATest {i}", eposta=f"y{i}@ornek.test",
                                           parola="demo-parola-123", ulke="TR", kvkk_onay=True), simdi)
            sid = sepet_servis.sepet_bul(con, None, m.id, simdi)
            con.execute("INSERT INTO sepet_kalemi (sepet_id, urun_id, adet) VALUES (?, ?, ?)", (sid, uid, adet))
            sonuc.append((m, sid))
    return uid, sonuc


ADRES = Adres(ad_soyad="QATest", satir1="Adres 1", sehir="Konya", ulke="TR")
KUR = Kur(tarih=date(2026, 10, 12), eur_alis=Decimal("35.00"), eur_satis=Decimal("35.20"))


def test_fix1_acik_siparis_stoku_ayirir(con, simdi):
    """I-3: stok=1; ilk sipariş (ödenmemiş kart, süresi içinde) son adedi ayırır, ikinci sipariş StokYetersiz."""
    _, ((m1, s1), (m2, s2)) = _uc_musteri_sepet(con, simdi)
    with con:
        siparis_olustur(con, m1, s1, TeslimYontemi.KARGO, ADRES, ADRES, KUR, simdi)
    with pytest.raises(StokYetersiz):
        with con:
            siparis_olustur(con, m2, s2, TeslimYontemi.KARGO, ADRES, ADRES, KUR, simdi)


def test_fix1_suresi_dolan_kart_siparisi_ayirmayi_birakir(con, simdi):
    from datetime import timedelta
    _, ((m1, s1), (m2, s2)) = _uc_musteri_sepet(con, simdi)
    with con:
        siparis_olustur(con, m1, s1, TeslimYontemi.KARGO, ADRES, ADRES, KUR, simdi)
    with con:
        siparis_olustur(con, m2, s2, TeslimYontemi.KARGO, ADRES, ADRES, KUR, simdi + timedelta(minutes=31))


@pytest.mark.parametrize("durum,yontem,ayirir", [
    ("odendi", "kart", True), ("hazirlaniyor", "kart", True), ("kargoda", "kart", False),
    ("iptal", "kart", False), ("odeme_bekliyor", "havale", True),
])
def test_fix1_ayirma_durumlari(con, simdi, durum, yontem, ayirir):
    from datetime import timedelta
    _, ((m1, s1), (m2, s2)) = _uc_musteri_sepet(con, simdi)
    with con:
        s = siparis_olustur(con, m1, s1, TeslimYontemi.KARGO, ADRES, ADRES, KUR, simdi, yontem)
        con.execute("UPDATE siparis SET durum = ? WHERE id = ?", (durum, s.id))
    sonra = simdi + timedelta(days=2)     # 30 dk kart süresi doldu; havale son tarihi (3 iş günü, G3g) henüz değil
    if ayirir:
        with pytest.raises(StokYetersiz):
            with con:
                siparis_olustur(con, m2, s2, TeslimYontemi.KARGO, ADRES, ADRES, KUR, sonra)
    else:
        with con:
            siparis_olustur(con, m2, s2, TeslimYontemi.KARGO, ADRES, ADRES, KUR, sonra)


def test_fix1_eszamanli_iki_siparis_son_adet_yalniz_biri(tmp_path, simdi):
    """I-3: iki ayrı bağlantı aynı anda son adede sipariş verir: biri başarılı, biri StokYetersiz (BEGIN IMMEDIATE)."""
    import threading
    from app.db import baglan, gecisleri_uygula
    yol = tmp_path / "yaris.db"
    con = baglan(yol)
    gecisleri_uygula(con)
    _, musteriler = _uc_musteri_sepet(con, simdi)
    con.close()
    engel = threading.Barrier(2)
    sonuclar = []

    def calis(m, sid):
        c = baglan(yol)
        try:
            engel.wait()
            with c:
                siparis_olustur(c, m, sid, TeslimYontemi.KARGO, ADRES, ADRES, KUR, simdi)
            sonuclar.append("tamam")
        except StokYetersiz:
            sonuclar.append("stok")
        finally:
            c.close()

    is_parcaciklari = [threading.Thread(target=calis, args=x) for x in musteriler]
    for p in is_parcaciklari:
        p.start()
    for p in is_parcaciklari:
        p.join(10)
    assert sorted(sonuclar) == ["stok", "tamam"]


def test_fix1_siparis_olustur_acik_islem_baslatir(con, simdi):
    """I-3: siparis_olustur işlem dışında çağrılsa da BEGIN IMMEDIATE ile yazma kilidini en başta alır."""
    _, ((m1, s1), _) = _uc_musteri_sepet(con, simdi)
    komutlar = []
    con.set_trace_callback(komutlar.append)
    with con:
        siparis_olustur(con, m1, s1, TeslimYontemi.KARGO, ADRES, ADRES, KUR, simdi)
    con.set_trace_callback(None)
    assert komutlar and komutlar[0].strip().upper() == "BEGIN IMMEDIATE"


@pytest.mark.parametrize("baslik,beklenen", [
    ("en-ZA,de-DE;q=0.9", "DE"), ("de-DE;q=0", None), ("de-DE;q=0,fr-FR;q=0.5", "FR"),
    ("en-US;q=abc,de-AT", "AT"), (";;,,-,x-", None), ("de-DE;q=nan", None), ("tr", None),
])
def test_fix1_accept_language_bozuk_ve_q0(baslik, beklenen):
    """M-1 + M-9(b): q<=0 atlanır; desteklenen ülkesi olan ilk bölge alınır; bozuk girdi çökmez."""
    from starlette.requests import Request
    from app.web.baglam import dil_bolgesi
    istek = Request({"type": "http", "headers": [(b"accept-language", baslik.encode())], "path": "/en/"})
    assert dil_bolgesi(istek) == beklenen


def test_fix1_html_yaniti_vary(istemci, katalog):
    assert "Accept-Language" in istemci.get(f"/en/urun/{katalog['role']}").headers.get("Vary", "")


def test_fix1_fiyat_araligi_sinirda_gorunen_tutar(istemci, katalog):
    """M-2: ekranda tam 460,00 ₺ görünen ürün (10,89 € × 35,20, KDV ayrı yuvarlanır) fmin=460 ile listede kalır."""
    from tests.conftest import urun_ekle
    with istemci_db(istemci) as con:
        urun_ekle(con, sku="S-SINIR", ad="SINIR ÜRÜNÜ", fiyat="10.89", kategori_id=katalog["kontrol"], stok=2)
    html = istemci.get(f"/tr/kategori/{katalog['kontrol']}?fmin=460&fmax=460").text
    assert "SINIR ÜRÜNÜ" in html and "460,00 ₺" in html


def test_fix1_proforma_alici_tek_kaynak(istemci, db):
    """M-3: proforma alıcı unvanı ve künye aynı ayardan."""
    from app.web.baglam import SATICI_UNVAN
    _kurumsal_sepet(istemci, db)
    r = _odeme_gonder(istemci, odeme_yontemi="havale")
    proforma = re.search(r'<section class="proforma".*?</section>', istemci.get(r.headers["location"]).text, re.S)
    assert SATICI_UNVAN in proforma.group(0)
    assert SATICI_UNVAN in istemci.get("/tr/yasal/kunye").text
    sablon = (KOK_DIZIN / "app/web/sablonlar/siparis.html").read_text(encoding="utf-8")
    assert "MUSTAFA CEYLAN" not in sablon


def test_fix1_havale_bekleyen_varis_bugunden(istemci, db, sabit_gun):
    """M-4: ödemesi beklenen havale siparişinde varış aralığı sipariş tarihinden değil bugünden hesaplanır."""
    _kurumsal_sepet(istemci, db)
    r = _odeme_gonder(istemci, odeme_yontemi="havale")
    no = r.headers["location"].rsplit("/", 1)[1]
    with db:
        db.execute("UPDATE siparis SET olusturma = ? WHERE no = ?", ("2026-10-01T09:00:00+00:00", no))
    html = istemci.get(r.headers["location"]).text
    # G3m madde 3: ödeme bekleyen havalede tarih aralığı yok; ödeme sonrası iş günü aralığı
    # G3n madde 6: ürün sayfasıyla aynı gün sayıları ("kargoya veriliş 1–2 · varış 2–4 iş günü")
    assert ("Ödeme alındıktan sonra kargoya veriliş: 1–2 iş günü · varış: 2–4 iş günü (temsili)" in html
            and "varış: 1" not in html)


def test_fix1_fabrikadan_teslimde_dap_yazmaz(istemci, db):
    """M-5: yurt dışı müşteri fabrikadan teslim seçerse ihracat satırında DAP ibaresi yok."""
    _yurtdisi_sepet(istemci, db)
    html = istemci.get("/en/odeme").text
    form = {"teslimat_ad_soyad": "QATest", "teslimat_satir1": "Str 1", "teslimat_sehir": "Berlin", "teslimat_ulke": "DE",
            "fatura_ayni": "1", "teslim": "fabrika", "islem": "hesapla"}
    r = _post(istemci, "/en/odeme", form, "/en/odeme")
    satir = _ihracat_satiri(r.text)
    assert "Turkish VAT does not apply" in satir and "(DAP)" not in satir
    assert "(DAP)" in _ihracat_satiri(html)


def test_fix1_kart_ve_siparis_sayfasinda_parca_no(istemci, db):
    """M-6: kart ve sipariş onayında da parça no = üretici kodu."""
    _kur(db)
    uid = _urun(db, sku="S-KOD", ad="Kodlu Ürün", fiyat="100.00", stok=5, uretici_kodu="00-109-802")
    _musteri(db, eposta="kod@ornek.test")
    _giris(istemci, "kod@ornek.test")
    _sepete_ekle(istemci, uid)
    r = _odeme_gonder(istemci)
    no = _siparis_no(r.headers["location"])
    for yol in (f"/tr/odeme/{no}/kart", f"/tr/siparis/{no}"):
        html = istemci.get(yol).text
        assert '<span class="parca-no">00-109-802</span>' in html, yol
        assert "Stok kodu S-KOD" in html, yol


def test_fix1_upsert_sabit_yamasi_yok():
    """M-7: SQL metni replace ile yamanmaz."""
    kaynak = (KOK_DIZIN / "app/sepet/servis.py").read_text(encoding="utf-8")
    assert "_UPSERT.replace" not in kaynak


def test_fix1_en_ulkesiz_teklif_formunda_ulke_bos(istemci):
    """M-8: /en'de ülke seçilmemişken teklif formunda TR ön seçili değil."""
    html = istemci.get("/en/teklif", headers={"Accept-Language": "en-CA"}).text
    secim = re.search(r'<select id="ulke" name="ulke".*?</select>', html, re.S).group(0)
    assert re.search(r'<option value="" selected>', secim) and '<option value="TR" selected>' not in secim
    html = istemci.get("/en/teklif", headers={"Accept-Language": "de-DE"}).text
    assert '<option value="DE" selected>' in re.search(r'<select id="ulke".*?</select>', html, re.S).group(0)


XSS = '"><script>alert(1)</script>'


def test_fix1_geri_basilan_degerler_kacislanir(istemci, db):
    """M-9(a): hatalı gönderimde geri basılan değerler HTML olarak çalışmaz."""
    r = _post(istemci, "/tr/teklif", {"ad": XSS, "firma": XSS, "telefon": XSS, "ulke": "TR", "adet": "1", "mesaj": "",
                                      "hedef_fiyat": XSS, "kvkk_onay": "1"}, "/tr/teklif")
    assert r.status_code == 400 and "<script>alert(1)" not in r.text and "&lt;script&gt;" in r.text
    _kur(db)
    uid = _urun(db, sku="S-XSS", ad="XSS Ürünü", fiyat="100.00", stok=5)
    _musteri(db, eposta="xss@ornek.test")
    _giris(istemci, "xss@ornek.test")
    _sepete_ekle(istemci, uid)
    r = _odeme_gonder(istemci, teslimat_satir1=XSS, teslimat_sehir=XSS, on_bilgi_onay="")
    assert r.status_code == 400 and "<script>alert(1)" not in r.text


# =====================================================================================================
# Düzeltme turu 2
# =====================================================================================================

def _baska_musterinin_havalesi(db, uid, adet, simdi=None):
    """Başka bir kurumsal müşterinin bekleyen havale siparişi uid'den adet kadar ayırır."""
    from app.hesap.servis import KayitGirdisi, kayit_ol
    simdi = simdi or datetime.now(UTC)
    with db:
        m = kayit_ol(db, KayitGirdisi(tip=MusteriTipi.KURUMSAL, ad="QATest Rakip A.Ş.", eposta="rakip@ornek.test",
                                      parola="demo-parola-123", ulke="TR", kvkk_onay=True,
                                      vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk"), simdi)
        sid = sepet_servis.sepet_bul(db, None, m.id, simdi)
        db.execute("INSERT INTO sepet_kalemi (sepet_id, urun_id, adet) VALUES (?, ?, ?)", (sid, uid, adet))
    with db:
        siparis_olustur(db, m, sid, TeslimYontemi.KARGO, ADRES, ADRES, KUR, simdi, "havale")
        sepet_servis.bosalt(db, sid)      # rota gibi: havale siparişi sepeti boşaltır


def _ozet(html):
    m = re.search(r'<div class="form-hata-ozet islem-hatasi" role="alert".*?</div>', html, re.S)
    assert m, "role=alert özeti yok"
    return unescape(m.group(0))


def test_fix2_rezervasyonla_409_kalem_kaldirilir_ve_aciklanir(istemci, db):
    """N-1: son adet başka siparişte ayrılı: 409 özeti ürünü, ayrılabilir adedi, yapılan işlemi ve teklif bağlantısını
    gösterir; kalem sepetten çıkar."""
    _kur(db)
    uid = _urun(db, sku="S-REZ1", ad="Rezerve Ürün", fiyat="100.00", stok=1)
    _musteri(db, eposta="a@ornek.test")
    _giris(istemci, "a@ornek.test")
    _sepete_ekle(istemci, uid)
    sayfa = istemci.get("/tr/odeme").text
    _baska_musterinin_havalesi(db, uid, 1)
    r = _odeme_gonder(istemci, sayfa_html=sayfa)
    assert r.status_code == 409
    ozet = _ozet(r.text)
    assert "Rezerve Ürün" in ozet and "Stokta şu an 0 adet ayrılabilir" in ozet and "sepetten çıkarıldı" in ozet
    assert f'href="/tr/teklif?urun_id={uid}&adet=1"' in ozet
    assert "döviz" not in ozet.lower()
    assert _sepet_adedi(db, uid) == 0
    assert db.execute("SELECT COUNT(*) FROM siparis WHERE sepet_id IN (SELECT id FROM sepet WHERE musteri_id ="
                      " (SELECT id FROM musteri WHERE eposta = 'a@ornek.test'))").fetchone()[0] == 0


def test_fix2_rezervasyonla_409_adet_iner_yeniden_gonderim_basarili(istemci, db):
    """N-1: stok 2, biri ayrılı, sepette 2: adet 1'e iner, özet açıklar; yeniden gönderim siparişi açar."""
    _kur(db)
    uid = _urun(db, sku="S-REZ2", ad="Kısmi Ürün", fiyat="100.00", stok=2)
    _musteri(db, eposta="b@ornek.test")
    _giris(istemci, "b@ornek.test")
    _sepete_ekle(istemci, uid, adet="2")
    sayfa = istemci.get("/tr/odeme").text
    _baska_musterinin_havalesi(db, uid, 1)
    r = _odeme_gonder(istemci, sayfa_html=sayfa)
    assert r.status_code == 409
    ozet = _ozet(r.text)
    assert "Kısmi Ürün" in ozet and "Stokta şu an 1 adet ayrılabilir" in ozet and "1 olarak güncellendi" in ozet
    assert f'href="/tr/teklif?urun_id={uid}&adet=2"' in ozet
    assert _sepet_adedi(db, uid) == 1
    r = _odeme_gonder(istemci, sayfa_html=r.text)
    assert r.status_code == 303 and r.headers["location"].endswith("/kart")


def test_fix2_ust_sinir_99_kirpilan_adet_bildirilir(istemci, db):
    """N-2: sepette 98 varken 5 eklenince 1 eklenir; bildirim kırpılan adedi ve 99 sınırını yazar."""
    uid = _urun(db, sku="S-99", ad="Bol Ürün", fiyat="1.00", stok=500)
    _sepete_ekle(istemci, uid, adet="98")
    yol = f"/tr/urun/{uid}"
    r = _post(istemci, "/tr/sepet/ekle", {"urun_id": uid, "adet": "5", "sonraki": yol}, yol)
    bildirim = _bildirimler(istemci.get(r.headers["location"].split("#")[0]).text)
    assert "Bol Ürün (1 adet)" in bildirim and "(5 adet)" not in bildirim and "en fazla 99" in bildirim
    r = _post(istemci, "/tr/sepet/ekle", {"urun_id": uid, "adet": "3", "sonraki": yol}, yol)
    bildirim = _bildirimler(istemci.get(r.headers["location"].split("#")[0]).text)
    assert "Sepete eklendi" not in bildirim and "en fazla 99" in bildirim
    assert _sepet_adedi(db, uid) == 99


def test_fix2_adet_guncelleme_99_siniri_bildirilir(istemci, db):
    uid = _urun(db, sku="S-99B", ad="Bol Ürün 2", fiyat="1.00", stok=500)
    _sepete_ekle(istemci, uid)
    _post(istemci, "/tr/sepet/adet", {"urun_id": uid, "adet": "150"}, "/tr/sepet")
    assert _sepet_adedi(db, uid) == 99
    assert "en fazla 99" in _bildirimler(istemci.get("/tr/sepet").text)


# =====================================================================================================
# Düzeltme turu 3 — ödenmiş siparişin ayırması son tam eşitlemede biter; sitede "ayrılabilir" stok
# =====================================================================================================

def _odenmis_siparis(db, uid, adet, odeme_zamani, eposta="odenmis@ornek.test", durum="odendi"):
    """Başka müşterinin ödenmiş siparişi (sepeti boşaltılmış), ödeme zamanı verilen ISO metin."""
    from app.hesap.servis import KayitGirdisi, kayit_ol
    simdi = datetime.fromisoformat(odeme_zamani)
    with db:
        m = kayit_ol(db, KayitGirdisi(tip=MusteriTipi.KURUMSAL, ad="QATest Alıcı A.Ş.", eposta=eposta,
                                      parola="demo-parola-123", ulke="TR", kvkk_onay=True,
                                      vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk"), simdi)
        sid = sepet_servis.sepet_bul(db, None, m.id, simdi)
        db.execute("INSERT INTO sepet_kalemi (sepet_id, urun_id, adet) VALUES (?, ?, ?)", (sid, uid, adet))
    with db:
        s = siparis_olustur(db, m, sid, TeslimYontemi.KARGO, ADRES, ADRES, KUR, simdi)
        db.execute("UPDATE siparis SET durum = ?, odeme_zamani = ? WHERE id = ?", (durum, odeme_zamani, s.id))
        sepet_servis.bosalt(db, sid)
    return s


def _tam_esitleme(db, bitis, durum="tam"):
    with db:
        db.execute("INSERT INTO esitleme_gunlugu (basla, bitis, durum) VALUES (?, ?, ?)", (bitis, bitis, durum))


@pytest.mark.parametrize("esitleme,ayirir", [
    (None, True),                                         # hiç tam eşitleme yok: ayırır
    ("2026-10-13T02:40:00+00:00", True),                  # ödeme son tam eşitlemeden sonra: ayırır
    ("2026-10-13T11:00:00+00:00", False),                 # tam eşitleme ödemeden sonra: ERP stoku zaten düşük sayılır
])
def test_fix3_odenmis_siparis_son_tam_esitlemeye_kadar_ayirir(con, esitleme, ayirir):
    from app.stok import ayrilan_adetler
    from tests.conftest import urun_ekle
    uid = urun_ekle(con, sku="S-ESIT", stok=3)
    _odenmis_siparis(con, uid, 2, "2026-10-13T09:00:00+00:00")
    if esitleme:
        _tam_esitleme(con, esitleme)
    _tam_esitleme(con, "2026-10-13T23:00:00+00:00", durum="eksik")   # tam olmayan eşitleme bırakmaz
    sonuc = ayrilan_adetler(con, datetime(2026, 10, 13, 12, 0, tzinfo=UTC))
    assert sonuc.get(uid, 0) == (2 if ayirir else 0)


def test_fix3_odeme_zamani_kart_ve_yonetim_odendi(istemci, db):
    """Ödeme zamanı kartla başarılı ödemede ve yönetimin havaleyi "ödendi" yapmasında yazılır."""
    from app.siparis.servis import SiparisDurumu, durum_degistir
    from app.siparis.odeme_sim import BASARILI_KART
    from tests.test_web_sepet_odeme import _kart_ode, _sms
    no = None
    _kur(db)
    uid = _urun(db, sku="S-OZ", ad="Ödeme Zamanı", fiyat="100.00", stok=5)
    _musteri(db, eposta="oz@ornek.test")
    _giris(istemci, "oz@ornek.test")
    _sepete_ekle(istemci, uid)
    no = _siparis_no(_odeme_gonder(istemci).headers["location"])
    r, _ = _kart_ode(istemci, no, BASARILI_KART)
    _sms(istemci, no, r.headers["location"])
    assert db.execute("SELECT odeme_zamani FROM siparis WHERE no = ?", (no,)).fetchone()[0]
    s = _odenmis_siparis(db, uid, 1, "2026-10-13T09:00:00+00:00", eposta="hv@ornek.test", durum="odeme_bekliyor")
    with db:
        db.execute("UPDATE siparis SET odeme_zamani = NULL, odeme_yontemi = 'havale' WHERE id = ?", (s.id,))
        durum_degistir(db, s.id, SiparisDurumu.ODENDI, datetime(2026, 10, 14, 8, 0, tzinfo=UTC))
    assert db.execute("SELECT odeme_zamani FROM siparis WHERE id = ?", (s.id,)).fetchone()[0].startswith("2026-10-14")


def test_fix3_urun_sayfasi_tumu_ayrilmis(istemci, db):
    """Stok 1, başka müşterinin ödenmiş siparişi ayırıyor: Sepete ekle yok, "tümü ayrılmış — teklif isteyin" ve teklif
    bağlantısı; son tam eşitleme ödemeden sonra olunca ürün yeniden satılabilir."""
    _kur(db)
    uid = _urun(db, sku="S-AYR", ad="Ayrılmış Ürün", fiyat="100.00", stok=1)
    _odenmis_siparis(db, uid, 1, datetime.now(UTC).isoformat())
    html = istemci.get(f"/tr/urun/{uid}").text
    assert 'data-e2e="sepete-ekle"' not in html
    assert "Şu an alınabilir stok yok · en geç " in html and "· teklif isteyin" in html   # G3g madde 5, G3m madde 1
    assert f'href="/tr/teklif?urun_id={uid}"' in html
    liste = istemci.get("/tr/urunler").text
    satir = re.search(rf'<tr class="ut-satir[^"]*" id="urun-{uid}">.*?</tr>', liste, re.S).group(0)
    assert "Şu an alınabilir stok yok" in satir and 'action="/tr/sepet/ekle"' not in satir
    _tam_esitleme(db, (datetime.now(UTC) + timedelta(minutes=1)).isoformat())
    istemci.app.state.katalog_onbellek.clear()
    html = istemci.get(f"/tr/urun/{uid}").text
    assert 'data-e2e="sepete-ekle"' in html and "Stokta: 1 adet" in html


def test_fix3_urun_sayfasi_ayrilabilir_adet(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-AYR2", ad="Kısmen Ayrılmış", fiyat="100.00", stok=3)
    _odenmis_siparis(db, uid, 2, datetime.now(UTC).isoformat())
    html = istemci.get(f"/tr/urun/{uid}").text
    assert "Stokta: 1 adet" in html and 'data-e2e="sepete-ekle"' in html


def test_fix3_sepete_ekleme_ayrilabilir_adetle_sinirli(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-AYR3", ad="Sınırlı Ürün", fiyat="100.00", stok=2)
    _odenmis_siparis(db, uid, 1, datetime.now(UTC).isoformat())
    yol = f"/tr/urun/{uid}"
    r = _post(istemci, "/tr/sepet/ekle", {"urun_id": uid, "adet": "2", "sonraki": yol}, yol)
    assert _sepet_adedi(db, uid) == 1
    assert "Sepete 1 adet eklendi; stokta yalnız 1 adet var" in _bildirimler(istemci.get(yol).text)


def test_fix3_tumu_ayrilmis_urun_sepete_eklenmez(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-AYR4", ad="Tükenmiş Ürün", fiyat="100.00", stok=1)
    _odenmis_siparis(db, uid, 1, datetime.now(UTC).isoformat())
    yol = f"/tr/urun/{uid}"
    _post(istemci, "/tr/sepet/ekle", {"urun_id": uid, "adet": "1", "sonraki": yol}, yol)
    assert _sepet_adedi(db, uid) == 0
    bildirim = _bildirimler(istemci.get(yol).text)
    assert "Stokta: tümü ayrılmış — teklif isteyin" in bildirim and f"/tr/teklif?urun_id={uid}" in bildirim


def test_fix3_sepet_ayrilabilir_adede_iner(istemci, db):
    """Sepetteki adet sonradan başka siparişin ayırmasıyla ayrılabilir adedi aşarsa sepet görüntülenirken iner."""
    _kur(db)
    uid = _urun(db, sku="S-AYR5", ad="Sepette Ürün", fiyat="100.00", stok=3)
    _sepete_ekle(istemci, uid, adet="3")
    _odenmis_siparis(db, uid, 2, datetime.now(UTC).isoformat())
    html = istemci.get("/tr/sepet").text
    assert _sepet_adedi(db, uid) == 1 and "Stokta 1 adet var" in html


def test_fix3_kendi_bekleyen_kart_siparisi_kendi_sepetini_kesmez(istemci, db):
    """Kendi sepetinin ödemesi beklenen kart siparişi kendi sepetini ve ürün sayfasını kısıtlamaz (yeniden gönderimde
    zaten iptal edilir)."""
    _kur(db)
    uid = _urun(db, sku="S-KEN", ad="Kendi Ürünüm", fiyat="100.00", stok=1)
    _musteri(db, eposta="ken@ornek.test")
    _giris(istemci, "ken@ornek.test")
    _sepete_ekle(istemci, uid)
    assert _odeme_gonder(istemci).status_code == 303
    assert _sepet_adedi(db, uid) == 1
    istemci.get("/tr/sepet")
    assert _sepet_adedi(db, uid) == 1
    assert 'data-e2e="sepete-ekle"' in istemci.get(f"/tr/urun/{uid}").text
    assert _odeme_gonder(istemci).status_code == 303
