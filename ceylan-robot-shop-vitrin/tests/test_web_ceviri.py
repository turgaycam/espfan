"""G3f — /en arayüzünde EN ürün adı ve teknik özellik çevirisi (gösterim, SEO, arama, sepet/sipariş)."""
from __future__ import annotations

import json
import re

from app.katalog.indeks import indeksi_yeniden_kur
from app.katalog.urun_ceviri import kaynak_ozeti
from app.fiyat.kurallar import MusteriTipi
from tests.conftest import istemci_db, kategori_ekle, sayfa_denetle, urun_ekle
from tests.test_performans import buyuk_katalog  # noqa: F401  (fixture)
from tests.test_web_sepet_odeme import (  # noqa: F401  (db fixture'ı)
    _giris, _kur, _musteri, _odeme_gonder, _sepete_ekle, _siparis_no, db,
)

AD = "KUKA 00-109-802 KRC2 GÜÇ KAYNAĞI 27V-NT"
AD_EN = "KUKA 00-109-802 KRC2 Power Supply 27V-NT"
TEKNIK = [["Giriş Voltajı (Input)", "0,72 kV"], ["Ağırlık", "3,5 kg"]]
TEKNIK_EN = [["Input Voltage (Input)", "0.72 kV"], ["Weight", "3.5 kg"]]
DIGER = "SİEMENS RÖLE MODÜLÜ 24V"
NOT_EN = "Machine-translated from Turkish; values as supplied."
NOT_TR = "Technical data is shown as supplied (in Turkish)."


def _veri(con, *, gecerli=True):
    k = kategori_ekle(con, kaynak_id="k1", ad="GÜÇ SİSTEMLERİ", yol="1", seviye=0)
    a = urun_ekle(con, sku="A1", ad=AD, kategori_id=k, fiyat="100.00")
    b = urun_ekle(con, sku="B2", ad=DIGER, kategori_id=k, fiyat="50.00")
    con.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)",
                (a, json.dumps({"ozellikler": TEKNIK, "bolumler": []}, ensure_ascii=False)))
    con.execute("INSERT INTO urun_ceviri VALUES (?, 'en', ?, ?, 'llm-taslak', 'claude-haiku-5-5', ?, 't')",
                (a, AD_EN, json.dumps(TEKNIK_EN), kaynak_ozeti(AD, TEKNIK) if gecerli else "bayat"))
    indeksi_yeniden_kur(con)
    return k, a, b


def _json_ld(html):
    return [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def test_en_urun_sayfasi_ceviriyi_gosterir(istemci):
    with istemci_db(istemci) as con:
        _, a, _ = _veri(con)
    html = sayfa_denetle(istemci.get(f"/en/urun/{a}"))
    assert f"<h1>{AD_EN}</h1>" in html
    assert f'<span aria-current="page">{AD_EN}</span>' in html
    assert AD_EN in re.search(r"<title>(.*?)</title>", html).group(1)
    assert AD not in html                                     # TR ad hiçbir yerde (alt, meta, JSON-LD) kalmaz
    urun_ld = next(x for x in _json_ld(html) if x.get("@type") == "Product")
    assert urun_ld["name"] == AD_EN
    assert [p["name"] for p in urun_ld["additionalProperty"]] == ["Input Voltage (Input)", "Weight"]
    tablo = re.search(r'<table class="teknik-tablo".*?</table>', html, re.S).group(0)
    assert 'lang="tr"' not in tablo and "<th scope=\"row\">Weight</th><td>3.5 kg</td>" in tablo
    assert NOT_EN in html and 'data-e2e="teknik-ceviri-notu"' in html and NOT_TR not in html


def test_tr_arayuz_degismez(istemci):
    with istemci_db(istemci) as con:
        k, a, _ = _veri(con)
    html = sayfa_denetle(istemci.get(f"/tr/urun/{a}"))
    assert f"<h1>{AD}</h1>" in html and AD_EN not in html
    assert "<th scope=\"row\">Ağırlık</th><td>3,5 kg</td>" in html
    assert 'data-e2e="teknik-ceviri-notu"' not in html and 'lang="tr"' not in html.split("<body", 1)[1]
    liste = istemci.get(f"/tr/kategori/{k}").text
    assert AD_EN not in liste and AD in liste


def test_bayat_ceviri_gosterilmez(istemci):
    with istemci_db(istemci) as con:
        k, a, _ = _veri(con, gecerli=False)
    html = sayfa_denetle(istemci.get(f"/en/urun/{a}"))
    assert AD_EN not in html
    assert f'<h1><span lang="tr">{AD}</span></h1>' in html
    assert re.search(r'<table class="teknik-tablo"[^>]*lang="tr"', html)
    # G3l madde 19: çevrilmemiş tabloda tek not, tablonun üstünde başlık (alttaki "(in Turkish)" notu yok)
    assert "Technical data — original Turkish (not translated)" in html and NOT_TR not in html and NOT_EN not in html
    urun_ld = next(x for x in _json_ld(html) if x.get("@type") == "Product")
    assert urun_ld["name"] == AD


def test_esitleme_adi_degistirince_ceviri_duser(istemci):
    with istemci_db(istemci) as con:
        _, a, _ = _veri(con)
        con.execute("UPDATE urun SET ad = ? WHERE id = ?", (AD + " YENİ", a))
    html = istemci.get(f"/en/urun/{a}").text
    assert AD_EN not in html and f'<span lang="tr">{AD} YENİ</span>' in html


def test_en_liste_kart_ve_json_ld(istemci):
    with istemci_db(istemci) as con:
        k, a, b = _veri(con)
    html = sayfa_denetle(istemci.get(f"/en/kategori/{k}"))
    assert f'data-e2e="urun-baglanti">{AD_EN}</a>' in html
    assert f'data-e2e="urun-baglanti"><span lang="tr">{DIGER}</span></a>' in html
    ogeler = next(x for x in _json_ld(html) if x.get("@type") == "ItemList")["itemListElement"]
    assert {o["name"] for o in ogeler} == {AD_EN, DIGER}
    tum = sayfa_denetle(istemci.get("/en/urunler"))
    assert AD_EN in tum


def test_en_arama_en_adla_bulur(istemci):
    with istemci_db(istemci) as con:
        _, a, _ = _veri(con)
    html = istemci.get("/en/ara?q=power+supply").text
    assert f'href="/en/urun/{a}"' in html and AD_EN in html
    with istemci_db(istemci) as con:   # yalnız EN adda geçen sözcük
        con.execute("UPDATE urun_ceviri SET ad = ? WHERE urun_id = ?", ("KUKA 00-109-802 KRC2 Zorbatron 27V-NT", a))
        indeksi_yeniden_kur(con)
    assert f'href="/en/urun/{a}"' in istemci.get("/en/ara?q=zorbatron").text
    assert f'href="/tr/urun/{a}"' not in istemci.get("/tr/ara?q=zorbatron").text


def test_karsilastirma_en_ad(istemci):
    with istemci_db(istemci) as con:
        _, a, b = _veri(con)
    for uid in (a, b):
        csrf = re.search(r'name="csrf" value="([^"]+)"', istemci.get("/en/urunler").text).group(1)
        istemci.post("/en/karsilastir/ekle", data={"csrf": csrf, "urun_id": str(uid), "sonraki": "/en/urunler"})
    html = sayfa_denetle(istemci.get("/en/karsilastir"))
    assert f'<a href="/en/urun/{a}">{AD_EN}</a>' in html
    assert f'<a href="/en/urun/{b}"><span lang="tr">{DIGER}</span></a>' in html


def test_sepet_ve_siparis_en_ad_kayit_tr(istemci, db):
    _kur(db)
    with db:
        _, a, _ = _veri(db)
    _musteri(db, tip=MusteriTipi.YURTDISI, eposta="export@ornek.test", ulke="DE")
    _giris(istemci, "export@ornek.test", dil="en")
    assert _sepete_ekle(istemci, a, dil="en").status_code == 303
    sepet = sayfa_denetle(istemci.get("/en/sepet"))
    assert f'>{AD_EN}</a>' in sepet and AD not in sepet
    odeme = istemci.get("/en/odeme")
    assert f"× {AD_EN}" in odeme.text
    r = _odeme_gonder(istemci, dil="en", sayfa_html=odeme.text, ulke="DE", teslim="yurtdisi_dap",
                      on_bilgi_onay="", mesafeli_onay="")
    assert r.status_code == 303, r.text
    assert db.execute("SELECT ad FROM siparis_kalemi").fetchone()[0] == AD        # kalıcı kayıt TR
    no = _siparis_no(r.headers["location"])
    assert f"× {AD_EN}" in istemci.get(f"/en/odeme/{no}/kart").text
    assert f'<span class="kalem-ad">{AD_EN}</span>' in istemci.get(f"/en/siparis/{no}").text
    assert f'<span class="kalem-ad">{AD}</span>' in istemci.get(f"/tr/siparis/{no}").text


def test_karsilastirma_csv_en_ad(istemci):
    with istemci_db(istemci) as con:
        _, a, _ = _veri(con)
    csrf = re.search(r'name="csrf" value="([^"]+)"', istemci.get("/en/urunler").text).group(1)
    istemci.post("/en/karsilastir/ekle", data={"csrf": csrf, "urun_id": str(a), "sonraki": "/en/urunler"})
    assert AD_EN in istemci.get("/en/karsilastir.csv").text
    assert AD in istemci.get("/tr/karsilastir.csv").text


def test_g3f_cevirili_en_liste_300ms_ve_150kb_altinda(istemci, buyuk_katalog):
    from tests.test_performans import BOYUT_SINIRI, SURE_SINIRI, _olc

    with istemci_db(istemci) as con:
        satirlar = con.execute("SELECT id, ad FROM urun").fetchall()
        con.executemany(
            "INSERT INTO urun_ceviri VALUES (?, 'en', ?, NULL, 'llm-taslak', 'm', ?, 't')",
            [(i, ad.replace("GÜÇ KAYNAĞI", "Power Supply Unit").replace("SÜRÜCÜ", "Drive") + " EN", kaynak_ozeti(ad, []))
             for i, ad in satirlar])
        indeksi_yeniden_kur(con)
    k = buyuk_katalog
    for yol in ("/en/urunler?adet=48", f"/en/kategori/{k['kok']}", "/en/ara?q=power+supply+unit", "/en/urunler"):
        sure, boyut = _olc(istemci, yol)
        print(f"\nPERF G3f {sure * 1000:6.1f} ms  {boyut / 1024:6.1f} KB  {yol}")
        assert sure < SURE_SINIRI, (yol, sure)
        assert boyut < BOYUT_SINIRI, (yol, boyut)
    assert "Power Supply Unit" in istemci.get("/en/ara?q=power+supply+unit").text


# ---------- Düzeltme turu 1 ----------
def test_m1_bildirimlerde_en_ad(istemci):
    with istemci_db(istemci) as con:
        _, a, b = _veri(con)
    for yol, veri in (("/en/sepet/ekle", {"adet": "1"}), ("/en/karsilastir/ekle", {})):
        csrf = re.search(r'name="csrf" value="([^"]+)"', istemci.get("/en/urunler").text).group(1)
        r = istemci.post(yol, data={"csrf": csrf, "urun_id": str(a), "sonraki": "/en/urunler", **veri},
                         follow_redirects=False)
        assert r.status_code == 303
        html = istemci.get("/en/urunler").text
        bildirim = re.search(r'class="bildirim.*?</(?:div|p)>', html, re.S).group(0)
        assert AD_EN in bildirim and AD not in bildirim


def test_i3_xss_ceviri_adi_kacislanir(istemci):
    kotu = 'KUKA 00-109-802 KRC2 <script>alert(1)</script> "q" & 27V-NT'
    with istemci_db(istemci) as con:
        k, a, _ = _veri(con)
        con.execute("UPDATE urun_ceviri SET ad = ? WHERE urun_id = ?", (kotu, a))
    for yol in (f"/en/urun/{a}", f"/en/kategori/{k}"):
        html = sayfa_denetle(istemci.get(yol))
        assert "<script>alert" not in html
        for ld in _json_ld(html):
            adlar = [ld.get("name")] + [o.get("name") for o in ld.get("itemListElement", [])]
            if kotu in adlar:
                break
        else:
            raise AssertionError("JSON-LD'de ad yok")
    html = istemci.get(f"/en/urun/{a}").text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert re.search(r'alt="KUKA 00-109-802 KRC2 &lt;script&gt;alert\(1\)&lt;/script&gt; &#34;q&#34; &amp; 27V-NT', html)


def test_i3_teknikli_cevirilerle_perf(istemci, buyuk_katalog):
    from tests.test_performans import BOYUT_SINIRI, SURE_SINIRI, _olc

    with istemci_db(istemci) as con:
        satirlar = con.execute("SELECT id, ad FROM urun").fetchall()
        teknik = [[f"Özellik {n}", f"{n},5 kV"] for n in range(10)]
        teknik_en = [[f"Property {n}", f"{n}.5 kV"] for n in range(10)]
        con.executemany("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)",
                        [(i, json.dumps({"ozellikler": teknik, "bolumler": []}, ensure_ascii=False)) for i, _ in satirlar])
        con.executemany(
            "INSERT INTO urun_ceviri VALUES (?, 'en', ?, ?, 'llm-taslak', 'm', ?, 't')",
            [(i, ad + " EN", json.dumps(teknik_en), kaynak_ozeti(ad, teknik)) for i, ad in satirlar])
        indeksi_yeniden_kur(con)
        bir = satirlar[0][0]
    k = buyuk_katalog
    for yol in ("/en/urunler?adet=48", f"/en/kategori/{k['kok']}", "/en/ara?q=power+supply", f"/en/urun/{bir}"):
        sure, boyut = _olc(istemci, yol)
        print(f"\nPERF G3f-teknik {sure * 1000:6.1f} ms  {boyut / 1024:6.1f} KB  {yol}")
        assert sure < SURE_SINIRI, (yol, sure)
        assert boyut < BOYUT_SINIRI, (yol, boyut)
    assert "Property 3" in istemci.get(f"/en/urun/{bir}").text
