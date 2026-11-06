"""G3l: persona tur 7 — A: arama kalıntıları (1–4), B: fiyat (5–8), C: Hesabım ve formlar (9–17),
D: ürün sayfası, karşılaştırma, mobil (18–22)."""
import re
from html import unescape
from pathlib import Path

import pytest

from app.fiyat.kurallar import MusteriTipi
from app.katalog.indeks import indeksi_yeniden_kur
from tests.conftest import csrf_al, istemci_db, sayfa_denetle, urun_ekle  # noqa: F401
from tests.test_web_g3j import _metin, _satir, _satirlar
from tests.test_web_sepet_odeme import (GECERLI_VKN, _giris, _kur, _musteri, _sepete_ekle, _urun,  # noqa: F401
                                        db)


def _bolum(html, desen):
    m = re.search(desen, html, re.S)
    assert m, desen
    return m.group(0)


def _katalog(istemci, adlar, **ortak):
    """adlar: [(ad, ek alanlar)] -> kimlikler (indeks yeniden kurulur)."""
    kimlikler = []
    with istemci_db(istemci) as con:
        for i, (ad, ek) in enumerate(adlar):
            kimlikler.append(urun_ekle(con, sku=ek.pop("sku", f"S-G3L{i}"), ad=ad, **{**ortak, **ek}))
        indeksi_yeniden_kur(con)
    return kimlikler


# =====================================================================================================
# A1 — nadir terimli gevşetme: yalnız nadir terimi içerenler + "… içeren N ürünü de göster"
# =====================================================================================================

def test_g3l_nadir_terimli_gevsetme(istemci):
    adlar = [("KUKA RESOLVER KARTI RDW", {}), ("ABB SERVO MOTOR RESOLVER", {}), ("SIEMENS RESOLVER ÜNİTESİ", {})]
    adlar += [("2.0 USB KABLOSU", {}), ("İNTERNET KABLOSU 1M", {})]
    adlar += [(f"SIEMENS MOTOR KABLOSU {i}M", {}) for i in range(1, 29)]       # kablosu: 30 ürün, resolver: 3
    _katalog(istemci, adlar, stok=1)
    html = sayfa_denetle(istemci.get("/tr/ara", params={"q": "resolver kablosu"}))
    satirlar = _satirlar(html)
    assert len(satirlar) == 3 and all("RESOLVER" in s for s in satirlar), satirlar
    assert not any("USB" in s or "İNTERNET" in s for s in satirlar)
    assert 'class="gevset"' in html                                   # terim bağlantıları kalır
    bag = re.search(r'<a href="([^"]*genis=1[^"]*)"[^>]*>(.*?)</a>', html)
    assert bag and _metin(bag.group(2)) == "“kablosu” içeren 30 ürünü de göster", bag and bag.group(2)
    genis = sayfa_denetle(istemci.get(unescape(bag.group(1))))
    assert "2.0 USB KABLOSU" in _satirlar(genis) and len(_satirlar(genis)) == 24
    assert "33 ürün" in _metin(_bolum(genis, r'<p class="sonuc-sayisi">.*?</p>'))
    en = istemci.get("/en/ara", params={"q": "resolver kablosu"}).text
    assert len(_satirlar(en)) == 3 and "Also show the 30 products containing “kablosu”" in _metin(en)
    # oran 1/10'dan büyükse (ör. 3 ile 20) eski gevşetme: hepsi
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET aktif = 0 WHERE ad LIKE 'SIEMENS MOTOR KABLOSU%' AND sku > 'S-G3L22'")
        indeksi_yeniden_kur(con)
    html = istemci.get("/tr/ara", params={"q": "resolver kablosu"}).text
    assert "genis=1" not in html and "2.0 USB KABLOSU" in _satirlar(html)


def test_g3l_genis_robots_yasak(istemci_uretim):
    # fix 1 M-6: sabit listeye değil, yayınlanan robots.txt çıktısına bakılır
    satirlar = istemci_uretim.get("/robots.txt").text.splitlines()
    assert "Disallow: /*?*genis=" in satirlar


# =====================================================================================================
# A2 — tip eşlemeli eşanlam grubu: o tipteki tüm ürünler sonuçta
# =====================================================================================================

def test_g3l_tip_eslemeli_esanlam_grubu(istemci):
    adlar = ["SEW EURODRIVE FREKANS İNVERTÖRÜ", "DANFOSS FREKANS KONVERTÖRÜ FC302", "SIEMENS SINAMICS G120C ANMA GÜCÜ",
             "SIEMENS MICROMASTER 4 LINE REACTOR", "MITSUBISHI FR-D740 Inverter", "KUKA SERVO SÜRÜCÜ KSD1-16",
             "FESTO VALF", "ABB SERVO MOTOR"]
    kimlikler = _katalog(istemci, [(a, {}) for a in adlar], stok=1)
    with istemci_db(istemci) as con:
        tipler = dict(con.execute("SELECT ad, tip FROM urun").fetchall())
        beklenen = {a for a in adlar if tipler[a] == "frekans_konvertoru"}
    assert len(beklenen) == 5, tipler
    faset = re.search(r'name="tip" value="frekans_konvertoru"[^>]*>.*?<span class="faset-sayi">(\d+)</span>',
                      istemci.get("/tr/urunler").text, re.S)
    assert faset and int(faset.group(1)) == len(beklenen)
    for dil in ("tr", "en"):
        for q in ("Frequenzumrichter", "Umrichter", "inverter", "invertör", "frekans konvertörü",
                  "frekans dönüştürücü"):
            html = sayfa_denetle(istemci.get(f"/{dil}/ara", params={"q": q}))
            sonuc = set(_satirlar(html))
            assert beklenen <= sonuc, (dil, q, beklenen - sonuc)
            if q in ("Frequenzumrichter", "Umrichter"):
                assert sonuc == beklenen, (q, sonuc)
    # çok terimde tip yalnız o terimin yerine geçer: diğer terim yine aranır
    sonuc = set(_satirlar(istemci.get("/tr/ara", params={"q": "Frequenzumrichter SEW"}).text))
    assert sonuc == {"SEW EURODRIVE FREKANS İNVERTÖRÜ"}, sonuc
    assert kimlikler


# =====================================================================================================
# A3 — yakın kodlar (en uzun ortak katlanmış önek, en az 5 karakter, en çok 5 ürün)
# =====================================================================================================

def test_g3l_yakin_kodlar(istemci):
    kodlar = {"6ES7215-1AG40-0XB0": "SIEMENS S7-1200 CPU 1215C", "6ES7211-1AE40-0XB0": "SIEMENS S7-1200 CPU 1211C",
              "6ES7231-4HD32-0XB0": "SIEMENS SM 1231 ANALOG", "6ES7315-2AG10-0AB0": "SIEMENS S7-300 CPU 315-2"}
    _katalog(istemci, [(ad, {"uretici_kodu": kod}) for kod, ad in kodlar.items()], stok=1)
    for q in ("6ES7214", "6ES7 214"):
        html = sayfa_denetle(istemci.get("/tr/ara", params={"q": q}))
        assert 'data-e2e="ayni-seri"' in html
        blok = _bolum(html, r'<div class="yakin-kodlar".*?</div>')
        assert _metin(blok).startswith("Yakın kodlar:"), blok
        assert "6ES7215-1AG40-0XB0" in blok and "6ES7211-1AE40-0XB0" in blok
        # G3m madde 17: liste daha kısa önekle (6ES72…) doldurulur, en uzun önekliler önce; 4 karakter (6ES7) yok
        assert "6ES7315" not in blok and blok.index("6ES7211") < blok.index("6ES7231")
    en = istemci.get("/en/ara", params={"q": "6ES7214"}).text
    assert "Similar codes:" in _metin(_bolum(en, r'<div class="yakin-kodlar".*?</div>'))
    # 6ES721… yoksa 6ES72…
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET aktif = 0 WHERE uretici_kodu LIKE '6ES721%'")
        indeksi_yeniden_kur(con)
    blok = _bolum(istemci.get("/tr/ara", params={"q": "6ES7214"}).text, r'<div class="yakin-kodlar".*?</div>')
    assert "6ES7231-4HD32-0XB0" in blok and "6ES7315" not in blok
    # 5 karakterden kısa ortak önek: liste yok
    html = istemci.get("/tr/ara", params={"q": "6ES8999"}).text
    assert 'class="yakin-kodlar"' not in html


def test_g3l_yakin_kodlar_en_cok_bes(istemci):
    _katalog(istemci, [(f"SIEMENS CPU {i}", {"uretici_kodu": f"6ES721{i}-1AG40-0XB0"}) for i in range(5, 10)]
             + [("SIEMENS CPU X", {"uretici_kodu": "6ES7210-1AG40-0XB0"})], stok=1)
    blok = _bolum(istemci.get("/tr/ara", params={"q": "6ES7214"}).text, r'<div class="yakin-kodlar".*?</div>')
    assert len(re.findall(r"<li>", blok)) == 5


# =====================================================================================================
# A4 — tireli / eğik çizgili kod tek jeton
# =====================================================================================================

def test_g3l_ayracli_kod_tek_jeton(istemci):
    _katalog(istemci, [("FESTO BASINÇ REGÜLATÖRÜ //159625", {"uretici_kodu": "LR-D-MINI"}),
                       ("FESTO LR SERİSİ D TİPİ MINI SİLİNDİR", {}),
                       ("FESTO D MINI LR BAĞLANTI", {}),
                       ("ABB DSQC 626 A GÜÇ KAYNAĞI", {"uretici_kodu": "3HAC026289-001"}),
                       ("ABB 001 KART 3HAC026289", {}),
                       ("SIEMENS SITOP", {"uretici_kodu": "6EP1961-2BA11"})], stok=1)

    def ara(q):
        return _satirlar(sayfa_denetle(istemci.get("/tr/ara", params={"q": q})))
    assert ara("LR-D-MINI") == ara("lrdmini") == ["FESTO BASINÇ REGÜLATÖRÜ //159625"]
    assert ara("LR/D/MINI") == ara("lrdmini")
    assert ara("3HAC026289-001") == ara("3HAC026289001") == ["ABB DSQC 626 A GÜÇ KAYNAĞI"]
    assert ara("6ep1961-2ba11") == ["SIEMENS SITOP"]


def test_g3l_f1_kisa_ayracli_jeton_kod_sayilmaz(istemci):
    """fix 1 C-1: katlanmış biçimi 4 karakterden kısa ayraçlı jeton ("I/O", "G1/4", "A/B", "U/I") tek kod değildir;
    G3l öncesi gibi kelimelere bölünür. 4+ karakterli olanlar ("X-20", "LR-D-MINI") tek kod kalır."""
    from dataclasses import replace
    from app.katalog import depo
    adlar = [("SİEMENS SIMATIC I/O MODÜL KLEMENSİ", {}), ("SIEMENS SIMATIC ET200 I/O MODÜLÜ", {}),
             ("SIEMENS SIMATIC S7-300 CPU", {}), ("SIEMENS SIMATIC HMI PANEL", {}),
             ("TURCK IO-LINK MASTER", {}),
             ("SCHMALZ VAKUM VANTUZU SGM-S70", {"uretici_kodu": "SGM-HD-S 70 G1/4-IG PNP"}),
             ("B&R X20 DİJİTAL GİRİŞ MODÜLÜ", {"uretici_kodu": "X20DI9371"}),
             ("FESTO BASINÇ REGÜLATÖRÜ", {"uretici_kodu": "LR-D-MINI"}),
             ("A/B ANAHTARI", {}), ("U/I ÇEVİRİCİ", {})]
    _katalog(istemci, adlar, stok=1)
    for q in ("I/O", "G1/4", "A/B", "U/I", "R1/2"):
        assert not depo.ayracli_kod_mu(q), q
    for q in ("X-20", "LR-D-MINI", "3HAC026289-001"):
        assert depo.ayracli_kod_mu(q), q

    def ara(q):
        html = sayfa_denetle(istemci.get("/tr/ara", params={"q": q}))
        return _satirlar(html), html
    simatic, html = ara("SIMATIC I/O")
    assert set(simatic[:2]) == {"SİEMENS SIMATIC I/O MODÜL KLEMENSİ", "SIEMENS SIMATIC ET200 I/O MODÜLÜ"}, simatic
    assert 'class="gevset"' not in html and "genis=1" not in html      # bozuk jeton md 1 daraltmasını tetiklemez
    io_, _ = ara("I/O")
    assert {"SİEMENS SIMATIC I/O MODÜL KLEMENSİ", "SIEMENS SIMATIC ET200 I/O MODÜLÜ"} <= set(io_), io_
    assert "SCHMALZ VAKUM VANTUZU SGM-S70" in ara("G1/4")[0]
    for q, bolunmus in (("A/B", "A B"), ("U/I", "U I")):         # G3l öncesi davranış: kelimelere bölünmüş arama
        assert ara(q)[0] == ara(bolunmus)[0], q
        assert [t.kelimeler for t in depo.arama_terimleri(q)] == [t.kelimeler for t in depo.arama_terimleri(bolunmus)]
    assert ara("X-20")[0] == ["B&R X20 DİJİTAL GİRİŞ MODÜLÜ"]
    assert ara("LR-D-MINI")[0] == ["FESTO BASINÇ REGÜLATÖRÜ"]
    assert replace  # noqa


def test_g3l_f1_tek_harf_kelime_kod_sorgusu_katli(istemci):
    """fix 1 M-1: rakamsız tek kelimelik sorgu ("lrdmini") da katlanmış metinde kelime başından aranır: adında kod
    ayrık yazılmış ürün ("LR D MINI") hem "LR-D-MINI" hem "lrdmini" ile bulunur (sayılar aynı)."""
    _katalog(istemci, [("FESTO REGÜLATÖR LR D MINI", {}), ("FESTO REGÜLATÖR", {"uretici_kodu": "LR-D-MINI"})],
             stok=1)

    def ara(q):
        return sorted(_satirlar(istemci.get("/tr/ara", params={"q": q}).text))
    assert ara("LR-D-MINI") == ara("lrdmini") == ["FESTO REGÜLATÖR", "FESTO REGÜLATÖR LR D MINI"]


# =====================================================================================================
# B5 — fiyat filtresi para birimi: ₺/€ geçişi filtre anlamını korur; etiket fpb birimini ve bazını yazar
# =====================================================================================================

def _fiyat_katalogu(istemci, db):
    _kur(db)          # 1 € = 35 ₺; ₺ KDV dahil = net € × 42
    return {p: _urun(db, sku=f"S-FP{p}", ad=f"FİYAT ÜRÜNÜ {p}", fiyat=f"{p}.00", stok=1) for p in (10, 50, 100, 200)}


def _fiyat_etiketi(html):
    alan = _bolum(html, r'<fieldset class="alan faset-fiyat-araligi">.*?</fieldset>')
    return _metin(re.search(r'<p class="alan-ipucu">(.*?)</p>', alan, re.S).group(1))


def test_g3l_fiyat_filtresi_gosterim_degisince_anlam_korunur(istemci, db):
    _fiyat_katalogu(istemci, db)
    eski = "/tr/urunler?fmin=1.000&fmax=5.000"           # fpb yok: gösterim (₺ KDV dahil) birimi
    html = sayfa_denetle(istemci.get(eski))
    kume = set(_satirlar(html))
    assert kume == {"FİYAT ÜRÜNÜ 50", "FİYAT ÜRÜNÜ 100"}, kume
    assert _fiyat_etiketi(html) == "₺, KDV dahil"
    assert '<input type="hidden" name="fpb" value="TRY">' in html
    csrf = csrf_al(istemci, "/tr/urunler")
    r = istemci.post("/tercih", data={"csrf": csrf, "fiyat": "eur", "sonraki": eski}, follow_redirects=False)
    assert r.status_code == 303 and "fpb=TRY" in r.headers["location"], r.headers["location"]
    html = sayfa_denetle(istemci.get(r.headers["location"]))
    assert set(_satirlar(html)) == kume                      # aynı ürün kümesi (221 → € geçişi)
    assert _fiyat_etiketi(html) == "₺, KDV dahil"            # etiket fpb birimi ve bazı, gösterimden bağımsız
    assert '<input type="hidden" name="fpb" value="TRY">' in html
    # fiyat girilmemiş listede geçiş fpb eklemez; € gösterimde etiket € KDV hariç
    r = istemci.post("/tercih", data={"csrf": csrf, "fiyat": "try", "sonraki": "/tr/urunler?stokta=1"},
                     follow_redirects=False)
    assert "fpb" not in r.headers["location"]
    istemci.post("/tercih", data={"csrf": csrf, "fiyat": "eur", "sonraki": "/tr/urunler"})
    assert _fiyat_etiketi(istemci.get("/tr/urunler").text) == "€, KDV hariç"
    # fpb zaten varsa korunur (değiştirilmez)
    r = istemci.post("/tercih", data={"csrf": csrf, "fiyat": "try", "sonraki": "/tr/urunler?fmin=50&fpb=EUR"},
                     follow_redirects=False)
    assert "fpb=EUR" in r.headers["location"] and "fpb=TRY" not in r.headers["location"]
    en = istemci.get("/en/urunler?fmin=50&fpb=EUR").text
    assert _fiyat_etiketi(en) == "€, excl. VAT"


# =====================================================================================================
# B6 — sepet/ödeme toplamı gösterime uyar (kurumsal € KDV hariç): € ara toplam, KDV oranı, ₺ (ödenecek) ≈ €
# =====================================================================================================

def _ozet(html):
    return _bolum(html, r'<dl class="tutar-ozeti">.*?</dl>')


def test_g3l_sepet_odeme_toplami_gosterime_uyar(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-TG", ad="Toplam Ürünü", fiyat="100.00", stok=5)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="tg@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Meram")
    _giris(istemci, "tg@ornek.test")
    _sepete_ekle(istemci, uid)
    # 3.500 + kargo 525 + KDV 700 + 105 = 4.830 ₺ = 138 €. fix 1 M-3/M-6: sepette tahmini toplam "(ödenecek)" demez;
    # ödeme adımında "Genel toplam … (ödenecek)"
    for yol, desen in (("/tr/sepet", r"Tahmini toplam 4\.830,00 ₺ ≈ 138,00 €"),
                       ("/tr/odeme", r"Genel toplam 4\.830,00 ₺ \(ödenecek\) · ≈ 138,00 €")):
        ozet = _metin(_ozet(sayfa_denetle(istemci.get(yol))))
        assert "Ara toplam (KDV hariç) 100,00 €" in ozet, (yol, ozet)
        assert "KDV (ürünler) %20" in ozet and "KDV (kargo) %20" in ozet, ozet
        assert re.search(desen, ozet), (yol, ozet)
    assert "(ödenecek)" not in _metin(_ozet(istemci.get("/tr/sepet").text))
    assert "Tahmini" not in _metin(_ozet(istemci.get("/tr/odeme").text))
    en = _metin(_ozet(istemci.get("/en/sepet").text))
    assert "VAT (items) 20%" in en and "≈ €138.00" in en and "(payable)" not in en, en
    assert "(payable) · ≈ €138.00" in _metin(_ozet(istemci.get("/en/odeme").text))


def test_g3l_bireysel_tl_toplam_mevcut_karisik_oran(istemci, db):
    _kur(db)
    a = _urun(db, sku="S-K20", ad="Yirmilik", fiyat="100.00", stok=5)
    b = _urun(db, sku="S-K10", ad="Onluk", fiyat="100.00", stok=5, kdv="10")
    _sepete_ekle(istemci, a)
    ozet = _metin(_ozet(istemci.get("/tr/sepet").text))
    assert "(ödenecek)" not in ozet and "KDV (ürünler) %20" in ozet
    _sepete_ekle(istemci, b)
    ozet = _metin(_ozet(istemci.get("/tr/sepet").text))
    assert "KDV (ürünler) %10 + %20" in ozet, ozet


# =====================================================================================================
# B7 — fiyatlı, sepete eklenebilir tedarikli ürün: "Tedarik süresi siparişten sonra bildirilir"
# =====================================================================================================

def test_g3l_tedarikli_urun_metni(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-TED", ad="TEDARİKLİ SÜRÜCÜ", fiyat="100.00", stok=0)
    tek = _urun(db, sku="S-TEK", ad="TEKLİFLİ SÜRÜCÜ", fiyat="100.00", stok=0, teklif=True)
    html = sayfa_denetle(istemci.get("/tr/urunler"))
    hucre = _metin(_bolum(_satir(html, uid), r'<td class="ut-stok">.*?</td>'))
    assert hucre == "Tedarik süresi siparişten sonra bildirilir" and "teklifle" not in hucre
    assert 'action="/tr/sepet/ekle"' in _satir(html, uid)
    assert "teklifle" in _metin(_bolum(_satir(html, tek), r'<td class="ut-stok">.*?</td>')).lower()
    en = istemci.get("/en/urunler").text
    assert _metin(_bolum(_satir(en, uid), r'<td class="ut-stok">.*?</td>')) == "Lead time confirmed after the order"


# =====================================================================================================
# B8 — yalnız kart sunulan müşteri tipinde havale/proforma notu (≥ 50.000 ₺ vurgulu); kural değişmez
# =====================================================================================================

def _havale_notu(html):
    m = re.search(r'<p class="([^"]*havale-notu[^"]*)"[^>]*>(.*?)</p>', html, re.S)
    return (m.group(1), m.group(2)) if m else None


def test_g3l_odeme_havale_notu(istemci, db):
    _kur(db)
    ucuz = _urun(db, sku="S-HU", ad="Ucuz", fiyat="100.00", stok=5)
    pahali = _urun(db, sku="S-HP", ad="Pahalı", fiyat="2000.00", stok=5)     # 2.000 × 42 = 84.000 ₺
    _musteri(db, eposta="hn@ornek.test")
    _giris(istemci, "hn@ornek.test")
    _sepete_ekle(istemci, ucuz)
    html = sayfa_denetle(istemci.get("/tr/odeme"))
    assert 'name="odeme_yontemi"' not in html                    # kural aynı: bireysel yalnız kart
    sinif, icerik = _havale_notu(html)
    assert _metin(icerik) == "Havale/proforma ile ödemek için: kurumsal hesap ya da teklif isteyin"
    assert 'href="/tr/kayit?tip=kurumsal"' in icerik and 'href="/tr/teklif?sepet=1"' in icerik
    assert "vurgulu" not in sinif
    _sepete_ekle(istemci, pahali)
    sinif, _ = _havale_notu(istemci.get("/tr/odeme").text)
    assert "vurgulu" in sinif
    en = istemci.get("/en/odeme").text
    assert _metin(_havale_notu(en)[1]) == "To pay by bank transfer / pro forma: a business account or request a quote"


def test_g3l_odeme_havale_notu_kurumsalda_yok(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-HK", ad="Kurumsal", fiyat="100.00", stok=5)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="hk@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Meram")
    _giris(istemci, "hk@ornek.test")
    _sepete_ekle(istemci, uid)
    html = istemci.get("/tr/odeme").text
    assert 'name="odeme_yontemi"' in html and _havale_notu(html) is None


def test_g3l_odeme_havale_notu_girissiz_bireysel_grubu(istemci, db):
    _kur(db)
    _sepete_ekle(istemci, _urun(db, sku="S-HG", ad="Girişsiz", fiyat="100.00", stok=5))
    html = istemci.get("/tr/odeme").text
    assert re.search(r'<div data-tipler="bireysel"><p class="[^"]*havale-notu', html), "girişsizde bireysel grubunda"


# =====================================================================================================
# C9 — Hesabım sipariş detayı: tahmini varış (onaydakiyle aynı), durum geçmişi, fatura e-posta notu
# =====================================================================================================

ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def _kart_siparisi(istemci, db, eposta="kd9@ornek.test"):
    from tests.test_web_sepet_odeme import _kart_ode, _odeme_gonder, _siparis_no, _sms
    _kur(db)
    uid = _urun(db, sku="S-SD", ad="Detay Ürünü", fiyat="100.00", stok=3)
    _musteri(db, eposta=eposta)
    _giris(istemci, eposta)
    _sepete_ekle(istemci, uid)
    no = _siparis_no(_odeme_gonder(istemci).headers["location"])
    r, _ = _kart_ode(istemci, no, "4111 1111 1111 1111")
    r, _ = _sms(istemci, no, r.headers["location"])
    assert r.headers["location"] == f"/tr/siparis/{no}"
    return no


def _gecmis(html):
    return [_metin(x) for x in re.findall(r"<li[^>]*>(.*?)</li>",
                                           _bolum(html, r'<ol class="durum-gecmisi"[^>]*>.*?</ol>'), re.S)]


def test_g3l_hesabim_siparis_detayi_varis_ve_gecmis(istemci, db):
    no = _kart_siparisi(istemci, db)
    onay = istemci.get(f"/tr/siparis/{no}").text
    varis = _metin(_bolum(onay, r'<span class="not kalem-teslim">.*?</span>'))
    assert varis.startswith("Kargoya veriliş: 1–2 iş günü · varış: "), varis   # G3n madde 6
    html = sayfa_denetle(istemci.get(f"/tr/hesabim/siparis/{no}"))
    assert varis in _metin(_bolum(html, r'<table class="tablo siparis-ayrinti-kalemler">.*?</table>'))
    gecmis = _gecmis(html)
    assert len(gecmis) == 2, gecmis
    assert re.fullmatch(r"Sipariş oluşturuldu \d{2}\.\d{2}\.\d{4} \d{2}:\d{2} \(TSİ\)", gecmis[0]), gecmis
    assert re.fullmatch(r"Ödendi \d{2}\.\d{2}\.\d{4} \d{2}:\d{2} \(TSİ\)", gecmis[1]), gecmis
    assert "Fatura e-posta ile gönderilir (temsili)." in _metin(html)
    assert not ISO.search(_metin(html)), ISO.search(_metin(html))
    en = istemci.get(f"/en/hesabim/siparis/{no}").text
    assert re.fullmatch(r"Order placed \d{1,2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2} TRT", _gecmis(en)[0]), _gecmis(en)
    assert not ISO.search(_metin(en))


def test_g3l_hesabim_siparis_gecmisi_havale_ve_suresi_dolan(istemci, db):
    from datetime import UTC, datetime, timedelta
    from tests.test_web_sepet_odeme import _odeme_gonder
    _kur(db)
    uid = _urun(db, sku="S-SH", ad="Havale Ürünü", fiyat="100.00", stok=3)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="hv9@ornek.test", vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Meram")
    _giris(istemci, "hv9@ornek.test")
    _sepete_ekle(istemci, uid)
    no = _odeme_gonder(istemci, odeme_yontemi="havale").headers["location"].rsplit("/", 1)[1]
    gecmis = _gecmis(istemci.get(f"/tr/hesabim/siparis/{no}").text)
    assert gecmis[0].startswith("Sipariş oluşturuldu") and len(gecmis) == 2
    assert re.fullmatch(r"Ödeme bekliyor — son tarih \d{2}\.\d{2}\.\d{4} \d{2}:\d{2} \(TSİ\)", gecmis[1]), gecmis
    with db:
        db.execute("UPDATE siparis SET odeme_son_tarih = ? WHERE no = ?",
                   ((datetime.now(UTC) - timedelta(hours=1)).isoformat(), no))
    gecmis = _gecmis(istemci.get(f"/tr/hesabim/siparis/{no}").text)
    assert re.fullmatch(r"Süresi doldu \d{2}\.\d{2}\.\d{4} \d{2}:\d{2} \(TSİ\)", gecmis[1]), gecmis


# =====================================================================================================
# C10 — tarih/saat biçimi tek tip (TR "13.10.2026 22:21 (TSİ)", EN "13 Oct 2026 22:21 TRT", yurt dışı + alıcı saati)
# =====================================================================================================

TR_ZAMAN = r"\d{2}\.\d{2}\.\d{4} \d{2}:\d{2} \(TSİ\)"
EN_ZAMAN = r"\d{1,2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2} TRT"


def test_g3l_tarih_bicimi_hesabim_listeleri(istemci, db):
    no = _kart_siparisi(istemci, db, "tb10@ornek.test")
    istemci.post("/tr/teklif", data={"csrf": csrf_al(istemci, "/tr/teklif"), "ad": "Ali", "eposta": "a@ornek.test",
                                     "ulke": "TR", "adet": "1", "mesaj": "m", "parca_kodu": "6ES7214-1AG40"})
    tr = sayfa_denetle(istemci.get("/tr/hesabim"))
    satirlar = re.findall(r"<tr>\s*<td>.*?</tr>", tr, re.S)
    assert len(satirlar) == 2
    for s in satirlar:
        assert re.search(TR_ZAMAN, _metin(s)), _metin(s)
    assert not ISO.search(_metin(tr))
    en = istemci.get("/en/hesabim").text
    for s in re.findall(r"<tr>\s*<td>.*?</tr>", en, re.S):
        assert re.search(EN_ZAMAN, _metin(s)), _metin(s)
    assert not ISO.search(_metin(en))
    for yol in (f"/en/hesabim/siparis/{no}", f"/en/siparis/{no}"):
        assert not ISO.search(_metin(istemci.get(yol).text)), yol


def test_g3l_tarih_bicimi_yurtdisi_alici_saati(istemci, db):
    from tests.test_web_g3k import _yurtdisi_havale
    no, _ = _yurtdisi_havale(istemci, db)
    en = istemci.get("/en/hesabim").text
    satir = _metin(re.search(r"<tr>\s*<td>.*?</tr>", en, re.S).group(0))
    assert re.search(EN_ZAMAN + r" \(\d{2}:\d{2} CES?T\)", satir), satir
    for yol in ("/en/hesabim", f"/en/hesabim/siparis/{no}", f"/en/siparis/{no}", f"/en/hesabim/siparis/{no}/proforma"):
        assert not ISO.search(_metin(istemci.get(yol).text)), yol


# =====================================================================================================
# C11 — Hesabım teklif detayı ve listesi
# =====================================================================================================

def test_g3l_hesabim_teklif_detayi_ve_listesi(istemci, db):
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="tk11@ornek.test", vergi_kimlik_no=GECERLI_VKN,
             vergi_dairesi="Meram")
    _giris(istemci, "tk11@ornek.test")
    r = istemci.post("/tr/teklif", data={"csrf": csrf_al(istemci, "/tr/teklif"), "ad": "Ayşe Kaya",
                                         "eposta": "a@ornek.test", "ulke": "TR", "adet": "2", "mesaj": "m",
                                         "parca_kodu": "6ES7214-1BD23-0XB0", "musteri_po": "PO-7002",
                                         "teslim_adresi": "Teststrasse 1, 70173 Stuttgart", "vkn": GECERLI_VKN,
                                         "vergi_dairesi": "Meram", "firma": "Deneme A.Ş."},
                     follow_redirects=False)
    assert r.status_code == 303, r.text[:2000]
    no = r.headers["location"].split("no=")[1]
    html = sayfa_denetle(istemci.get(f"/tr/hesabim/teklif/{no}"))
    metin = _metin(html)
    for parca in ("Teststrasse 1, 70173 Stuttgart", GECERLI_VKN, "PO-7002", "6ES7214-1BD23-0XB0"):
        assert parca in metin, parca
    assert metin.count("PO-7002") == 1
    liste = istemci.get("/tr/hesabim").text
    satir = _metin(_bolum(liste, rf'<td><a href="/tr/hesabim/teklif/{no}">.*?</tr>'))
    assert "6ES7214-1BD23-0XB0" in satir and "Genel teklif" not in satir, satir


def test_g3l_hesabim_teklif_listesi_ilk_kalem_adi(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-TL", ad="Liste Teklif Ürünü", fiyat="100.00", stok=3)
    _musteri(db, eposta="tk11b@ornek.test")
    _giris(istemci, "tk11b@ornek.test")
    _sepete_ekle(istemci, uid)
    html = istemci.get("/tr/teklif?sepet=1").text
    from tests.test_web_sepet_odeme import _gizli
    r = istemci.post("/tr/teklif", data={"csrf": _gizli(html, "csrf"), "ad": "Ali", "eposta": "a@ornek.test",
                                         "ulke": "TR", "mesaj": "m", "kaynak": "sepet", "kalem_urun": str(uid),
                                         "kalem_adet": "2"}, follow_redirects=False)
    no = r.headers["location"].split("no=")[1]
    satir = _metin(_bolum(istemci.get("/tr/hesabim").text, rf'<td><a href="/tr/hesabim/teklif/{no}">.*?</tr>'))
    assert "Liste Teklif Ürünü" in satir, satir


# =====================================================================================================
# C12 — fatura bilgileri kaydı bildirimi (PRG)
# =====================================================================================================

def test_g3l_fatura_bilgileri_kaydedildi(istemci, db):
    from tests.test_web_g3j import _bildirimler
    from tests.test_web_g3k import _fatura_kaydet
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="fk12@ornek.test", vergi_kimlik_no=GECERLI_VKN,
             vergi_dairesi="Meram")
    _giris(istemci, "fk12@ornek.test")
    r = _fatura_kaydet(istemci)
    assert r.status_code == 303 and r.headers["location"] == "/tr/hesabim/fatura"
    html = sayfa_denetle(istemci.get(r.headers["location"]))
    assert _bildirimler(html) == "Fatura bilgileriniz kaydedildi."
    assert "kaydedildi" not in _bildirimler(istemci.get("/tr/hesabim/fatura").text)    # bir kez


# =====================================================================================================
# C13 — teklif formu ön dolum (firma ve telefon profilden; ad yalnız kişi adı)
# =====================================================================================================

def _alan(html, ad):
    m = re.search(rf'<input id="{ad}" name="{ad}"[^>]*value="([^"]*)"', html)
    return unescape(m.group(1)) if m else None


def test_g3l_teklif_formu_on_dolum(istemci, db):
    from tests.test_web_g3k import _fatura_kaydet
    _musteri(db, tip=MusteriTipi.YURTDISI, eposta="yd13@ornek.test", ulke="DE", vat_id="DE123456789")
    _giris(istemci, "yd13@ornek.test")
    html = istemci.get("/tr/teklif").text
    assert _alan(html, "firma") == "QATestUser yurtdisi" and _alan(html, "ad") == ""
    istemci.cookies.clear()
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="kr13@ornek.test", vergi_kimlik_no=GECERLI_VKN,
             vergi_dairesi="Meram")
    _giris(istemci, "kr13@ornek.test")
    _fatura_kaydet(istemci)
    html = istemci.get("/tr/teklif").text
    assert _alan(html, "firma") == "Deneme Makina A.Ş." and _alan(html, "ad") == ""
    assert _alan(html, "telefon") == "0 (332) 000 00 00"
    istemci.cookies.clear()
    _musteri(db, eposta="br13@ornek.test")
    _giris(istemci, "br13@ornek.test")
    html = istemci.get("/tr/teklif").text
    assert _alan(html, "ad") == "QATestUser bireysel" and _alan(html, "firma") == ""


# =====================================================================================================
# C14 — teklif onayında PO bir kez
# =====================================================================================================

def test_g3l_teklif_onayi_po_bir_kez(istemci, db):
    r = istemci.post("/tr/teklif", data={"csrf": csrf_al(istemci, "/tr/teklif"), "ad": "Ali", "eposta": "a@ornek.test",
                                         "ulke": "TR", "adet": "1", "mesaj": "m", "musteri_po": "PO-TEKLIF-7001",
                                         "kvkk_onay": "1", "parca_kodu": "KPS-600"}, follow_redirects=False)
    assert r.status_code == 303, r.text[:1500]
    assert _metin(istemci.get(r.headers["location"]).text).count("PO-TEKLIF-7001") == 1


# =====================================================================================================
# C15 — sepet adet hataları
# =====================================================================================================

def test_g3l_sepet_adet_hatalari(istemci, db):
    from tests.test_web_g3j import _bildirimler
    _kur(db)
    uid = _urun(db, sku="S-AD", ad="Adet Ürünü", fiyat="10.00", stok=5)
    _sepete_ekle(istemci, uid)
    csrf = csrf_al(istemci, "/tr/sepet")
    for deger in ("1,5", "abc", "1.5", ""):
        r = istemci.post("/tr/sepet/adet", data={"csrf": csrf, "urun_id": str(uid), "adet": deger},
                         follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/tr/sepet", (deger, r.status_code)
        html = sayfa_denetle(istemci.get("/tr/sepet"))
        assert _bildirimler(html) == "Geçersiz adet: tam sayı girin", (deger, _bildirimler(html))
        assert db.execute("SELECT adet FROM sepet_kalemi").fetchone()[0] == 1
    for deger in ("0",):              # G3m madde 5: negatif adet artık reddedilir (test_g3m_sepet_negatif_adet)
        _sepete_ekle(istemci, uid)
        r = istemci.post("/tr/sepet/adet", data={"csrf": csrf, "urun_id": str(uid), "adet": deger},
                         follow_redirects=False)
        assert r.status_code == 303
        assert _bildirimler(istemci.get("/tr/sepet").text) == "Adet Ürünü sepetten çıkarıldı."
        assert db.execute("SELECT COUNT(*) FROM sepet_kalemi").fetchone()[0] == 0
    _sepete_ekle(istemci, uid, dil="en")
    istemci.post("/en/sepet/adet", data={"csrf": csrf, "urun_id": str(uid), "adet": "x"}, follow_redirects=False)
    assert _bildirimler(istemci.get("/en/sepet").text) == "Invalid quantity: enter a whole number"


# =====================================================================================================
# C16 — sepeti boşalt iki adım (<details>, mevcut POST rotası, CSRF)
# =====================================================================================================

def test_g3l_sepeti_bosalt_iki_adim(istemci, db):
    from tests.test_web_sepet_odeme import _gizli
    _kur(db)
    uid = _urun(db, sku="S-BO", ad="Boşalt Ürünü", fiyat="100.00", stok=3)
    _sepete_ekle(istemci, uid)
    html = istemci.get("/tr/teklif?sepet=1").text
    r = istemci.post("/tr/teklif", data={"csrf": _gizli(html, "csrf"), "ad": "Ali", "eposta": "a@ornek.test",
                                         "telefon": "+90 532 000 00 00", "ulke": "TR", "mesaj": "m", "kvkk_onay": "1",
                                         "kaynak": "sepet",
                                         "kalem_urun": str(uid), "kalem_adet": "1"}, follow_redirects=False)
    assert r.status_code == 303, re.findall(r'class="alan-hata"[^>]*>(.*?)<', r.text)
    onay = sayfa_denetle(istemci.get(r.headers["location"]))
    form = _bolum(onay, r'<form method="post" action="/tr/sepet/bosalt".*?</form>')
    detay = _bolum(form, r"<details[^>]*>.*?</details>")
    assert re.search(r"<summary[^>]*>.*Sepeti boşalt.*</summary>", detay, re.S)
    dugme = re.search(r'<button type="submit"[^>]*>(.*?)</button>', detay, re.S)
    assert dugme and _metin(dugme.group(1)) == "Evet, sepeti boşalt"
    assert form.count('type="submit"') == 1 and 'name="csrf"' in form


# =====================================================================================================
# C17 — karşılaştırma bildirimi ürün sayfasında bir kez (çapadaki kalır)
# =====================================================================================================

def test_g3l_karsilastirma_bildirimi_bir_kez(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-KB", ad="Karşılaştırma Ürünü", fiyat="100.00", stok=3)
    csrf = csrf_al(istemci, f"/tr/urun/{uid}")
    r = istemci.post("/tr/karsilastir/ekle", data={"csrf": csrf, "urun_id": str(uid), "sonraki": f"/tr/urun/{uid}"},
                     follow_redirects=False)
    html = sayfa_denetle(istemci.get(r.headers["location"]))
    metin = "Karşılaştırmaya eklendi: Karşılaştırma Ürünü"
    assert _metin(html).count(metin) == 1, _metin(html).count(metin)
    assert metin in _metin(_bolum(html, r'<p class="yerel-bildirim".*?</p>'))
    # başka sayfada (liste) genel bildirim kalır
    istemci.post("/tr/karsilastir/kaldir", data={"csrf": csrf, "urun_id": str(uid), "sonraki": "/tr/urunler"})
    istemci.post("/tr/karsilastir/ekle", data={"csrf": csrf, "urun_id": str(uid), "sonraki": "/tr/sepet"},
                 follow_redirects=False)
    assert metin in _metin(istemci.get("/tr/sepet").text)


# =====================================================================================================
# D18 — durum–garanti–iade tutarlılığı (her durum tek garanti satırı; "olduğu gibi"de garanti kapsamında iade yok)
# =====================================================================================================

DURUMLAR = ("yeni", "ikinci_el_test_edildi", "ikinci_el", "ikinci_el_oldugu_gibi", "belirtilmemis")


def _durumlu_urunler(db):
    _kur(db)
    kimlik = {}
    for i, d in enumerate(DURUMLAR):
        kimlik[d] = _urun(db, sku=f"S-DG{i}", ad=f"DURUM ÜRÜNÜ {i}", fiyat="100.00", stok=2)
        with db:
            db.execute("UPDATE urun SET durum_kodu = ? WHERE id = ?", (d, kimlik[d]))
    return kimlik


@pytest.mark.parametrize("kip", ["misafir", "ticari", "bireysel"])
def test_g3l_durum_garanti_iade_tutarliligi(istemci, db, kip):
    kimlik = _durumlu_urunler(db)
    if kip == "ticari":
        _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="dg@ornek.test", vergi_kimlik_no=GECERLI_VKN,
                 vergi_dairesi="Meram")
        _giris(istemci, "dg@ornek.test")
    elif kip == "bireysel":
        _musteri(db, eposta="dgb@ornek.test")
        _giris(istemci, "dgb@ornek.test")
    for d, uid in kimlik.items():
        html = sayfa_denetle(istemci.get(f"/tr/urun/{uid}"))
        metin = _metin(html)
        assert html.count('data-e2e="garanti-ozeti"') == 1, d
        if d == "ikinci_el_oldugu_gibi":
            assert "garanti kapsamında" not in metin.lower(), (kip, metin)
            if kip != "bireysel":
                # G3m madde 8: diğer durumlarla aynı kalıp ("Ticari alım: cayma hakkı yok. …")
                assert ("Ticari alım: cayma hakkı yok. Olduğu gibi satılır: garanti yok; açık ayıplar teslimden "
                        "itibaren 2 gün içinde "
                        "yazılı bildirilir.") in metin
        if d == "ikinci_el_test_edildi":
            ozet = _bolum(html, r'<p class="garanti-ozeti".*?</p>')
            assert _metin(ozet) == ("Test edilmiş ürün garantisi: süre ve kapsam Garanti Koşulları'nda (temsili) · "
                                    "Garanti koşulları"), ozet                # fix 1 I-1
            assert 'href="/tr/yasal/garanti#durum-ikinci_el_test_edildi"' in ozet
            assert not re.search(r"\b\d+ ay\b", metin), metin                     # süre uydurulmaz
    en = _metin(istemci.get(f"/en/urun/{kimlik['ikinci_el_oldugu_gibi']}").text)
    assert "under warranty" not in en, en


def test_g3l_karsilastirma_oldugu_gibi_garanti_kapsami_yok(istemci, db):
    kimlik = _durumlu_urunler(db)
    csrf = csrf_al(istemci, "/tr/urunler")
    istemci.post("/tr/karsilastir/ekle", data={"csrf": csrf, "urun_id": str(kimlik["ikinci_el_oldugu_gibi"]),
                                               "sonraki": "/tr/karsilastir"})
    hucre = _metin(_bolum(istemci.get("/tr/karsilastir").text, r'<p class="kart-garanti".*?</p>'))
    assert "garanti kapsamında" not in hucre.lower(), hucre


# =====================================================================================================
# D19 — EN çevrilmemiş teknik tablo: başlık tablonun üstünde, tek not
# =====================================================================================================

def test_g3l_en_cevrilmemis_teknik_tablo_tek_not(istemci):
    from tests.test_web_g3g import _ceviri_verisi
    with istemci_db(istemci) as con:
        a, b, _ = _ceviri_verisi(con)
    html = sayfa_denetle(istemci.get(f"/en/urun/{b}"))
    bolum = _bolum(html, r'<h3 class="teknik-tablo-baslik"[^>]*>.*?</table>')
    assert _metin(re.search(r"<h3[^>]*>(.*?)</h3>", bolum, re.S).group(1)) == \
        "Technical data — original Turkish (not translated)"
    assert re.search(r'<table class="teknik-tablo"[^>]*lang="tr"', bolum)
    assert "Technical data is shown as supplied (in Turkish)." not in html
    assert "Machine-translated" not in html
    cevrilmis = istemci.get(f"/en/urun/{a}").text
    assert "Machine-translated from Turkish" in cevrilmis and 'class="teknik-tablo-baslik"' not in cevrilmis
    assert cevrilmis.count("Machine-translated from Turkish") == 1
    assert 'class="teknik-tablo-baslik"' not in istemci.get(f"/tr/urun/{b}").text


# =====================================================================================================
# D20 — karşılaştırma: yalnız farklılıklar teknik bölümde, "Tip", EUR gösterimde KDV dahil satırı yok, CSV
# =====================================================================================================

def _teknik_ekle(istemci, uid, ozellikler):
    import json
    with istemci_db(istemci) as con:
        con.execute("INSERT OR REPLACE INTO urun_teknik (urun_id, veri) VALUES (?, ?)",
                    (uid, json.dumps({"ozellikler": ozellikler, "bolumler": []}, ensure_ascii=False)))


def _karsilastir_kur(istemci, db):
    _kur(db)
    a = _urun(db, sku="S-KA", ad="FESTO REGÜLATÖR", fiyat="100.00", stok=4, uretici_kodu="LR-D-MINI")
    b = _urun(db, sku="S-KB2", ad="FESTO VALF", fiyat="50.00", stok=0, tedarik_suresi_gun=10)
    _teknik_ekle(istemci, a, [["Type", "LR-D-MINI"], ["Çalışma Basıncı", "1–16 bar"], ["Boyut", "40 mm"],
                              ["Sıcaklık Aralığı", "-10 °C ile +60 °C"], ["Malzeme", "Alüminyum"]])
    _teknik_ekle(istemci, b, [["Type", "CPE14"], ["Çalışma Basıncı", "2–8 bar"], ["Bobin", "24 V"],
                              ["Malzeme", "Alüminyum"]])
    csrf = csrf_al(istemci, "/tr/urunler")
    for u in (a, b):
        istemci.post("/tr/karsilastir/ekle", data={"csrf": csrf, "urun_id": str(u), "sonraki": "/tr/karsilastir"})
    return a, b, csrf


def _teknik_satirlar(html):
    return [_metin(x) for x in re.findall(r'<tr class="teknik-satir"[^>]*>\s*<th scope="row">(.*?)</th>', html, re.S)]


def test_g3l_karsilastirma_yalniz_farkliliklar_teknik(istemci, db):
    _karsilastir_kur(istemci, db)
    tumu = _teknik_satirlar(istemci.get("/tr/karsilastir").text)
    assert {"Tip", "Çalışma Basıncı", "Boyut", "Bobin", "Malzeme"} <= set(tumu) and "Type" not in tumu, tumu
    fark = _teknik_satirlar(sayfa_denetle(istemci.get("/tr/karsilastir?fark=1")))
    # tek üründe dolu ("—" karşısı) ve aynı satırlar gizli; G3n fix 1: a'nın Type'ı parça no (LR-D-MINI) olduğundan
    # hücresi "—", Tip satırı yalnız b'de dolu kalır ve farklılıklarda gizlenir
    assert set(fark) == {"Çalışma Basıncı"}, fark
    assert "Type" in _teknik_satirlar(istemci.get("/en/karsilastir").text)


def test_g3l_karsilastirma_eur_gosterimde_kdv_dahil_satiri_yok(istemci, db):
    _, _, csrf = _karsilastir_kur(istemci, db)
    satirlar = lambda h: [_metin(x) for x in re.findall(r'<tr>\s*<th scope="row">(.*?)</th>', h, re.S)]  # noqa: E731
    assert "Fiyat (KDV dahil)" in satirlar(istemci.get("/tr/karsilastir").text)
    istemci.post("/tercih", data={"csrf": csrf, "fiyat": "eur", "sonraki": "/tr/karsilastir"})
    assert "Fiyat (KDV dahil)" not in satirlar(istemci.get("/tr/karsilastir").text)
    istemci.post("/tercih", data={"csrf": csrf, "ulke": "DE", "fiyat": "eur", "sonraki": "/en/karsilastir"})
    en = satirlar(istemci.get("/en/karsilastir").text)
    assert "Price (incl. VAT)" not in en and "Price (excl. VAT)" in en, en


def test_g3l_karsilastirma_csv_sayisal_stok_teslim(istemci, db):
    import csv
    import io
    _karsilastir_kur(istemci, db)
    r = istemci.get("/tr/karsilastir.csv")
    # G3m madde 14: düz tablo — sütun adı -> ürün değerleri (teknik özellikler ASCII snake_case sütunlar)
    tablo = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
    satirlar = {ad: [s[i] for s in tablo[1:]] for i, ad in enumerate(tablo[0])}
    assert satirlar["stok_adet"] == ["4", "0"], satirlar.get("stok_adet")
    assert satirlar["teslim_gun_min"] == ["2", "10"] and satirlar["teslim_gun_max"] == ["4", "10"]
    assert satirlar["teknik_bobin"] == ["", "24 V"]                            # "—" boş hücre
    assert satirlar["teknik_boyut"] == ["40 mm", ""]
    assert not any(h.startswith("'—") or h == "—" for s in satirlar.values() for h in s)
    assert satirlar["teknik_sicaklik_araligi"] == ["'-10 °C ile +60 °C", ""]   # formül önekli gerçek metin korunur


# =====================================================================================================
# D21 — mobil taşma: CSS kuralları (ölçüm Playwright ile rapora)
# =====================================================================================================

def test_g3l_mobil_tasma_css():
    from tests.test_web_g3j import _css
    css = _css()
    assert re.search(r"\.rozet-taslak\s*\{[^}]*white-space:\s*normal", css)
    # fix 1 M-6: ≤ 767 px kuralları (mobil kart listesinde başlık genişlik üretmez; sipariş kalemleri ekrana sığar)
    mobil = "".join(re.findall(r"@media \(max-width: 767px\) \{(.*?)\n\}", css, re.S))
    assert re.search(r"\.urun-tablo thead\s*\{\s*display:\s*none", mobil)
    assert re.search(r"\.siparis-ayrinti-kalemler\s*\{\s*table-layout:\s*fixed", mobil)
    assert re.search(r"\.siparis-ayrinti-kalemler th, \.siparis-ayrinti-kalemler td\s*\{[^}]*overflow-wrap:\s*anywhere", mobil)


# =====================================================================================================
# D22 — ihracat havale tutarı: yalnız mallar notu (onay + proforma, TR/EN)
# =====================================================================================================

def test_g3l_ihracat_havale_tutari_notu(istemci, db):
    from tests.test_web_g3k import _yurtdisi_havale
    no, _ = _yurtdisi_havale(istemci, db)
    en_not = "This amount covers the goods only; freight is invoiced separately with the DAP quote."
    tr_not = "Bu tutar yalnız mallar içindir; navlun DAP teklifiyle ayrıca faturalanır."
    onay = _bolum(sayfa_denetle(istemci.get(f"/en/siparis/{no}")), r'<dl class="proforma-banka">.*?</dl>')
    assert en_not in _metin(onay)
    assert tr_not in _metin(_bolum(istemci.get(f"/tr/siparis/{no}").text, r'<dl class="proforma-banka">.*?</dl>'))
    pb = _bolum(sayfa_denetle(istemci.get(f"/en/hesabim/siparis/{no}/proforma")), r'<dl class="pb-toplam">.*?</dl>')
    assert en_not in _metin(pb)
    assert tr_not in _metin(istemci.get(f"/tr/hesabim/siparis/{no}/proforma").text)


def test_g3l_tr_havale_tutari_notu_yok(istemci, db):
    from tests.test_web_sepet_odeme import _odeme_gonder
    _kur(db)
    uid = _urun(db, sku="S-TH", ad="TR Havale", fiyat="100.00", stok=3)
    _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="th22@ornek.test", vergi_kimlik_no=GECERLI_VKN,
             vergi_dairesi="Meram")
    _giris(istemci, "th22@ornek.test")
    _sepete_ekle(istemci, uid)
    no = _odeme_gonder(istemci, odeme_yontemi="havale").headers["location"].rsplit("/", 1)[1]
    assert "yalnız mallar içindir" not in istemci.get(f"/tr/siparis/{no}").text


# =====================================================================================================
# Fix turu 1
# =====================================================================================================

@pytest.mark.parametrize("dil", ["tr", "en"])
def test_g3l_f1_garanti_satiri_yasal_sayfayla_celismez(istemci, db, dil):
    """fix 1 I-1: ürün sayfasındaki garanti özeti, bağlandığı yasal sayfa bölümünün rejimiyle çelişmez: süre sayısı
    yok; test edilmiş üründe yasal sayfanın "2. el (genel)" ifadesi ("teklif ve fatura") kullanılmaz; çapa var."""
    kimlik = _durumlu_urunler(db)
    yasal = istemci.get(f"/{dil}/yasal/garanti").text
    genel = _metin(_bolum(yasal, r'<dt id="durum-ikinci_el">.*?</dd>'))
    assert ("teklif ve fatura" in genel) if dil == "tr" else ("quotation" in genel), genel
    for d, uid in kimlik.items():
        ozet = _bolum(istemci.get(f"/{dil}/urun/{uid}").text, r'<p class="garanti-ozeti".*?</p>')
        metin = _metin(ozet)
        assert not re.search(r"\d", metin), (d, metin)                  # süre (6 ay / 12 ay) ürün sayfasında yazılmaz
        cap = re.search(r'href="/' + dil + r'/yasal/garanti#(durum-[a-z_]+)"', ozet).group(1)
        assert f'id="{cap}"' in yasal, cap
        if d == "ikinci_el_test_edildi":
            assert cap == "durum-ikinci_el_test_edildi"
            assert "teklif ve fatura" not in metin and "quotation" not in metin, metin
    assert "Tested-item warranty: period and scope in the warranty terms (indicative)" in _metin(
        istemci.get(f"/en/urun/{kimlik['ikinci_el_test_edildi']}").text)


def test_g3l_f1_garanti_satiri_12_ay_anahtari_yok():
    import json
    for dil in ("tr", "en"):
        veri = json.loads((Path(__file__).resolve().parent.parent / f"app/web/dil/{dil}.json").read_text(encoding="utf-8"))
        assert "urun.garanti_satiri" not in veri
        assert not any(re.search(r"12[ -](ay|month)", v) for v in veri.values()), dil


def test_g3l_f1_kart_suresi_dolan_siparis_gecmisi(istemci, db):
    """fix 1 I-2: ödenmemiş kart siparişi 30 dk sonra iptal (zaman aşımı ilk okumada uygulanır): geçmiş zamanı
    olusturma + ODEME_SURESI (okuma anı değil), etiket rozetle uyumlu ("İptal — ödeme süresi doldu")."""
    from datetime import UTC, datetime, timedelta
    from app.web.baglam import tarih_tz_bicimle
    from tests.test_web_sepet_odeme import _odeme_gonder, _siparis_no
    _kur(db)
    uid = _urun(db, sku="S-KS", ad="Kart Süre Ürünü", fiyat="100.00", stok=3)
    _musteri(db, eposta="ks@ornek.test")
    _giris(istemci, "ks@ornek.test")
    _sepete_ekle(istemci, uid)
    no = _siparis_no(_odeme_gonder(istemci).headers["location"])
    olusturma = datetime(2026, 10, 10, 8, 0, tzinfo=UTC)          # iki gün önce; ilk okuma şimdi
    with db:
        db.execute("UPDATE siparis SET olusturma = ?, guncelleme = ? WHERE no = ?",
                   (olusturma.isoformat(), olusturma.isoformat(), no))
    html = sayfa_denetle(istemci.get(f"/tr/hesabim/siparis/{no}"))
    rozet = _metin(_bolum(html, r'<strong class="rozet durum-rozeti[^"]*"[^>]*>.*?</strong>'))
    assert rozet == "İptal"
    gecmis = _gecmis(html)
    beklenen = tarih_tz_bicimle(olusturma + timedelta(minutes=30), "tr", "TR", lambda k: "(TSİ)")
    assert gecmis[-1] == f"İptal — ödeme süresi doldu {beklenen}", gecmis
    assert gecmis[-1].startswith(rozet)
    en = _gecmis(istemci.get(f"/en/hesabim/siparis/{no}").text)
    assert en[-1].startswith("Cancelled — payment time expired"), en


def test_g3l_f1_tercih_fpb_parca_isareti_korunur(istemci, db):
    """fix 1 M-2: dönüş adresinde #çapa varsa fpb sorguya eklenir, çapa sonda kalır (fmin bozulmaz)."""
    _fiyat_katalogu(istemci, db)
    csrf = csrf_al(istemci, "/tr/urunler")
    r = istemci.post("/tercih", data={"csrf": csrf, "fiyat": "eur", "sonraki": "/tr/urunler?fmin=1.000#urun-5"},
                     follow_redirects=False)
    konum = r.headers["location"]
    assert konum.endswith("#urun-5") and "fpb=TRY" in konum and "fmin=1.000" in konum.replace("%2C", ","), konum
    assert "%23" not in konum


def test_g3l_f1_teklif_listesi_ulkesiz_tr_saati(istemci, db):
    """fix 1 M-7: teklif ülkesi boşsa saat Türkiye (TSİ) — ziyaretçinin ülkesine göre değişmez."""
    _musteri(db, eposta="ul7@ornek.test")
    _giris(istemci, "ul7@ornek.test")
    istemci.post("/tr/teklif", data={"csrf": csrf_al(istemci, "/tr/teklif"), "ad": "Ali", "eposta": "a@ornek.test",
                                     "ulke": "TR", "adet": "1", "mesaj": "m", "parca_kodu": "KPS-600"})
    with db:
        db.execute("UPDATE teklif SET ulke = ''")
    from tests.test_web_g3j import _ulke_ve_fiyat
    _ulke_ve_fiyat(istemci, "DE", "eur")
    satir = _metin(re.search(r"<tr>\s*<td><a href=\"/tr/hesabim/teklif/.*?</tr>", istemci.get("/tr/hesabim").text,
                             re.S).group(0))
    assert re.search(TR_ZAMAN, satir) and "CES" not in satir, satir
