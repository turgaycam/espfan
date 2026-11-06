"""G2: kötü niyetli tarayıcı koruması - bal küpü, 24 saatlik IP engeli, yönetim listesi, hız sınırı."""
import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.ayarlar import Ayarlar
from app.db import baglan, gecisleri_uygula
from app.hesap.servis import parola_ozeti
from app.web import seo
from app.web.koruma import EngelDeposu
from app.web.uygulama import uygulama_olustur
from tests.conftest import TEST_GIZLI, csrf_al, istemci_db, urun_ekle

T0 = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
YONETICI_PAROLA = "yonetici-parola-123"


def _baska_ip(istemci, ip: str) -> TestClient:
    """Aynı uygulamaya başka bir istemci IP'siyle bağlanır."""
    return TestClient(istemci.app, client=(ip, 50000))


@pytest.fixture
def urun_id(istemci):
    with istemci_db(istemci) as con:
        return urun_ekle(con, sku="HP-1", ad="TEST ÜRÜNÜ", kok="Elektrik")


# ---------- EngelDeposu (birim) ----------

@pytest.fixture
def depo(tmp_path):
    con = baglan(tmp_path / "e.db")
    gecisleri_uygula(con)
    con.close()
    saat = {"simdi": T0}
    d = EngelDeposu(tmp_path / "e.db", simdi=lambda: saat["simdi"])
    d.saat = saat
    return d


def test_engel_24_saat_sonra_kalkar(depo):
    assert not depo.engelli_mi("1.2.3.4")
    depo.engelle("1.2.3.4", "bal-kupu", "/_iz/x")
    assert depo.engelli_mi("1.2.3.4") and not depo.engelli_mi("1.2.3.5")
    depo.saat["simdi"] = T0 + timedelta(hours=23, minutes=59)
    assert depo.engelli_mi("1.2.3.4")
    depo.saat["simdi"] = T0 + timedelta(hours=24, seconds=1)
    assert not depo.engelli_mi("1.2.3.4")
    assert depo.listele() == []


def test_engel_sqlite_te_saklanir_ve_yeniden_yuklenir(depo, tmp_path):
    depo.engelle("9.9.9.9", "bal-kupu", "/_iz/abc")
    yeni = EngelDeposu(tmp_path / "e.db", simdi=lambda: T0 + timedelta(hours=1))
    assert not yeni.engelli_mi("9.9.9.9")  # henüz yüklenmedi
    yeni.yukle()
    assert yeni.engelli_mi("9.9.9.9")
    (kayit,) = yeni.listele()
    assert kayit["ip"] == "9.9.9.9" and kayit["neden"] == "bal-kupu" and kayit["yol"] == "/_iz/abc"
    assert kayit["bitis"] - kayit["engellendi"] == timedelta(hours=24)
    gec = EngelDeposu(tmp_path / "e.db", simdi=lambda: T0 + timedelta(days=2))
    gec.yukle()  # süresi dolan satır başlangıçta silinir
    assert not gec.engelli_mi("9.9.9.9") and gec.listele() == []


def test_engel_kaldir(depo):
    depo.engelle("5.5.5.5", "bal-kupu", None)
    assert depo.kaldir("5.5.5.5") is True and not depo.engelli_mi("5.5.5.5")
    assert depo.kaldir("5.5.5.5") is False


# ---------- bal küpü ----------

def test_bal_kupune_istek_sonraki_istekleri_403_yapar(istemci, urun_id):
    kotu = _baska_ip(istemci, "203.0.113.7")
    assert kotu.get(f"/tr/urun/{urun_id}").status_code == 200
    assert kotu.get(seo.BAL_KUPU_YOLU).status_code == 403
    for yol in ("/tr/", f"/tr/urun/{urun_id}", "/tr/sepet", "/saglik"):
        assert kotu.get(yol).status_code == 403, yol
    # başka bir istemci ve normal kullanıcı etkilenmez
    assert istemci.get(f"/tr/urun/{urun_id}").status_code == 200
    assert _baska_ip(istemci, "203.0.113.8").get("/tr/").status_code == 200


def test_bal_kupu_altindaki_her_yol_tuzaktir_ve_head_de(istemci):
    k = _baska_ip(istemci, "198.51.100.1")
    assert k.head(seo.BAL_KUPU_ONEKI + "baska-bir-sey").status_code == 403
    assert k.get("/tr/").status_code == 403


def test_engelli_istemci_robots_txt_okuyabilir(istemci):
    k = _baska_ip(istemci, "198.51.100.2")
    k.get(seo.BAL_KUPU_YOLU)
    assert k.get("/robots.txt").status_code == 200
    assert k.get("/llms.txt").status_code == 403


def test_engel_24_saat_sonra_uygulamada_kalkar(istemci):
    k = _baska_ip(istemci, "198.51.100.3")
    k.get(seo.BAL_KUPU_YOLU)
    assert k.get("/tr/").status_code == 403
    istemci.app.state.engel.simdi = lambda: datetime.now(UTC) + timedelta(hours=24, minutes=1)
    assert k.get("/tr/").status_code == 200


def test_robots_iki_modda_bal_kupunu_yasaklar(istemci, istemci_uretim):
    for c in (istemci, istemci_uretim):
        assert "Disallow: /_iz/" in c.get("/robots.txt").text.splitlines()
        assert seo.BAL_KUPU_YOLU.startswith("/_iz/") and len(seo.BAL_KUPU_YOLU) > len("/_iz/") + 8


@pytest.mark.parametrize("fixture_adi", ["istemci", "istemci_uretim"])
def test_gizli_baglanti_gorunmez_ve_erisilebilirlik_agacindan_cikarilmis(request, fixture_adi):
    c = request.getfixturevalue(fixture_adi)
    html = c.get("/tr/").text
    m = re.search(r'<a class="gizli-iz"[^>]*>', html)
    assert m, "bal küpü bağlantısı yok"
    etiket = m.group(0)
    assert f'href="{seo.BAL_KUPU_YOLU}"' in etiket
    assert 'aria-hidden="true"' in etiket and 'tabindex="-1"' in etiket
    assert "style=" not in etiket  # CSP: görünmezlik CSS sınıfıyla
    css = c.get("/statik/site.css").text
    assert re.search(r"\.gizli-iz\s*\{[^}]*left:\s*-9999px", css)


def test_bal_kupu_baglantisi_yonetim_sayfalarinda_da_var_ama_engel_yonetimi_kilitlemez(istemci):
    k = _baska_ip(istemci, "198.51.100.4")
    k.get(seo.BAL_KUPU_YOLU)
    assert k.get("/yonetim/giris").status_code == 200  # yönetim muaf: engel panodan kaldırılabilir


# ---------- yönetim panosu ----------

def _yonetici(istemci) -> None:
    csrf = csrf_al(istemci, "/yonetim/giris")
    r = istemci.post("/yonetim/giris", data={"kullanici": "yonetici", "parola": YONETICI_PAROLA, "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 303, r.text


def test_pano_engellenenleri_listeler_ve_tek_tikla_kaldirir(istemci):
    kotu = _baska_ip(istemci, "203.0.113.50")
    kotu.get(seo.BAL_KUPU_YOLU)
    assert kotu.get("/tr/").status_code == 403
    _yonetici(istemci)
    html = istemci.get("/yonetim").text
    assert 'data-e2e="engelli-tablo"' in html and "203.0.113.50" in html and seo.BAL_KUPU_YOLU in html
    csrf = re.search(r'action="/yonetim/engel/kaldir".*?name="csrf" value="([^"]+)"', html, re.S).group(1)
    r = istemci.post("/yonetim/engel/kaldir", data={"ip": "203.0.113.50", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/yonetim#engelliler"
    assert kotu.get("/tr/").status_code == 200
    assert 'data-e2e="engelli-bos"' in istemci.get("/yonetim").text


def test_engel_kaldirma_yetki_ve_csrf_ister(istemci):
    kotu = _baska_ip(istemci, "203.0.113.51")
    kotu.get(seo.BAL_KUPU_YOLU)
    r = istemci.post("/yonetim/engel/kaldir", data={"ip": "203.0.113.51", "csrf": "x"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/yonetim/giris"  # girişsiz
    assert kotu.get("/tr/").status_code == 403
    _yonetici(istemci)
    r = istemci.post("/yonetim/engel/kaldir", data={"ip": "203.0.113.51", "csrf": "yanlis"}, follow_redirects=False)
    assert r.status_code == 403  # csrf
    assert kotu.get("/tr/").status_code == 403


# ---------- hız sınırı ----------

def test_urun_sayfasinda_121_istekte_429(istemci, urun_id):
    yol = f"/tr/urun/{urun_id}"
    for i in range(120):
        assert istemci.get(yol).status_code == 200, i
    yanit = istemci.get(yol)
    assert yanit.status_code == 429 and int(yanit.headers["retry-after"]) > 0
    assert istemci.get("/tr/kategori/1").status_code == 429  # ürün + kategori aynı kovada
    assert yanit.headers["x-robots-tag"] and yanit.headers["x-content-type-options"] == "nosniff"  # güvenlik başlıkları sürer
    # sınırlanmayanlar
    assert istemci.get("/tr/").status_code == 200
    assert istemci.get("/statik/site.css").status_code == 200
    assert istemci.get("/gorsel/k/" + "a" * 32 + ".webp").status_code == 404  # 429 değil
    # başka istemci etkilenmez
    assert _baska_ip(istemci, "192.0.2.9").get(yol).status_code == 200


def test_hiz_siniri_ayardan_degisir(tmp_path):
    ayarlar = Ayarlar(db_yolu=tmp_path / "h.db", gizli_anahtar=TEST_GIZLI, yonetici_kullanici="y",
                      yonetici_parola_ozeti=parola_ozeti(YONETICI_PAROLA), sayfa_hiz_limiti=3)
    with TestClient(uygulama_olustur(ayarlar)) as c:
        kodlar = [c.get("/tr/urun/1").status_code for _ in range(5)]
    assert kodlar == [404, 404, 404, 429, 429]  # 404 da sayılır (tarayıcı taraması)


def test_hiz_siniri_ayari_ortamdan():
    from app.ayarlar import ayarlari_oku

    ortam = {"SHOP_DB": "/x/s.db", "SHOP_GIZLI_ANAHTAR": "g" * 32, "SHOP_YONETICI": "y", "SHOP_YONETICI_OZET": "o"}
    assert ayarlari_oku({**ortam, "SHOP_SAYFA_HIZ": "600"}).sayfa_hiz_limiti == 600
    with pytest.raises(RuntimeError, match="SHOP_SAYFA_HIZ"):
        ayarlari_oku({**ortam, "SHOP_SAYFA_HIZ": "cok"})


# ---------- muaf IP (SHOP_KORUMA_MUAF_IP) ve ayar doğrulaması ----------

def _muaf_istemci(tmp_path, muaf: str, **ek):
    from app.ayarlar import ayarlari_oku

    ortam = {"SHOP_DB": str(tmp_path / "m.db"), "SHOP_GIZLI_ANAHTAR": TEST_GIZLI, "SHOP_YONETICI": "y",
             "SHOP_YONETICI_OZET": parola_ozeti(YONETICI_PAROLA), "SHOP_KORUMA_MUAF_IP": muaf, **ek}
    return TestClient(uygulama_olustur(ayarlari_oku(ortam)), client=("192.168.5.77", 4000))


def test_muaf_ip_hiz_sinirina_ve_bal_kupu_engeline_tabi_degil(tmp_path, caplog):
    with _muaf_istemci(tmp_path, "10.0.0.0/8, 192.168.5.77", SHOP_SAYFA_HIZ="3") as c:
        assert [c.get("/tr/urun/1").status_code for _ in range(6)] == [404] * 6
        with caplog.at_level("WARNING", logger="cr_shop.koruma"):
            assert c.get(seo.BAL_KUPU_YOLU).status_code == 404  # tuzak yok, normal 404
        assert any("muaf IP" in r.getMessage() for r in caplog.records)
        assert c.get("/tr/").status_code == 200  # engellenmedi
        assert c.app.state.engel.listele() == []
        # muaf olmayan IP hâlâ korunur
        diger = TestClient(c.app, client=("203.0.113.9", 1))
        assert diger.get(seo.BAL_KUPU_YOLU).status_code == 403 and diger.get("/tr/").status_code == 403


def test_muaf_ip_gecersiz_deger_baslangicta_hata():
    from app.ayarlar import ayarlari_oku

    ortam = {"SHOP_DB": "/x/s.db", "SHOP_GIZLI_ANAHTAR": "g" * 32, "SHOP_YONETICI": "y", "SHOP_YONETICI_OZET": "o"}
    with pytest.raises(RuntimeError, match="SHOP_KORUMA_MUAF_IP"):
        ayarlari_oku({**ortam, "SHOP_KORUMA_MUAF_IP": "10.0.0.1, yanlis"})
    assert ayarlari_oku(ortam).koruma_muaf == ()
    assert len(ayarlari_oku({**ortam, "SHOP_KORUMA_MUAF_IP": "10.0.0.1, fd00::/8"}).koruma_muaf) == 2


def test_sayfa_hiz_sifir_ya_da_negatif_baslangicta_hata():
    from app.ayarlar import ayarlari_oku

    ortam = {"SHOP_DB": "/x/s.db", "SHOP_GIZLI_ANAHTAR": "g" * 32, "SHOP_YONETICI": "y", "SHOP_YONETICI_OZET": "o"}
    for deger in ("0", "-5"):
        with pytest.raises(RuntimeError, match="SHOP_SAYFA_HIZ"):
            ayarlari_oku({**ortam, "SHOP_SAYFA_HIZ": deger})


def test_uretimde_lan_site_kok_uyari_gunlugu(tmp_path, caplog):
    def kur(mod, kok):
        return Ayarlar(db_yolu=tmp_path / f"{mod}{len(kok)}.db", gizli_anahtar=TEST_GIZLI, yonetici_kullanici="y",
                       yonetici_parola_ozeti=parola_ozeti(YONETICI_PAROLA), yayin_modu=mod, site_kok=kok)

    with caplog.at_level("WARNING", logger="cr_shop.web"):
        uygulama_olustur(kur("uretim", "http://192.168.5.30:3030"))
    assert any("SHOP_SITE_KOK" in r.getMessage() for r in caplog.records)
    caplog.clear()
    with caplog.at_level("WARNING", logger="cr_shop.web"):
        uygulama_olustur(kur("uretim", "https://shop.example.com"))
        uygulama_olustur(kur("demo", "http://192.168.5.30:3030"))
    assert not caplog.records


def test_zaten_engelli_ip_tekrar_yazilmaz_ve_gunluk_sismez(depo, caplog):
    with caplog.at_level("WARNING", logger="cr_shop.koruma"):
        for _ in range(5):
            depo.engelle("7.7.7.7", "bal-kupu", "/_iz/x%0Asahte")
    assert len([r for r in caplog.records if "engellendi" in r.getMessage()]) == 1
    assert "\n" not in caplog.records[0].getMessage()


# ---------- G3a Y1: aşırı geniş muaf ağ ----------

@pytest.mark.parametrize("deger", ["0.0.0.0/0", "::/0", "10.0.0.1, 0.0.0.0/0", "0.0.0.0/0.0.0.0"])
def test_g3a_muaf_ip_tum_adresler_baslangicta_hata(deger):
    from app.ayarlar import ayarlari_oku

    ortam = {"SHOP_DB": "/x/s.db", "SHOP_GIZLI_ANAHTAR": "g" * 32, "SHOP_YONETICI": "y", "SHOP_YONETICI_OZET": "o"}
    with pytest.raises(RuntimeError, match="SHOP_KORUMA_MUAF_IP"):
        ayarlari_oku({**ortam, "SHOP_KORUMA_MUAF_IP": deger})


def test_g3a_muaf_ip_8den_genis_ipv4_uyari(caplog):
    from app.ayarlar import ayarlari_oku

    ortam = {"SHOP_DB": "/x/s.db", "SHOP_GIZLI_ANAHTAR": "g" * 32, "SHOP_YONETICI": "y", "SHOP_YONETICI_OZET": "o"}
    with caplog.at_level("WARNING", logger="cr_shop.ayarlar"):
        assert len(ayarlari_oku({**ortam, "SHOP_KORUMA_MUAF_IP": "10.0.0.0/8, 192.168.0.0/16"}).koruma_muaf) == 2
    assert not [r for r in caplog.records if r.name == "cr_shop.ayarlar"]
    with caplog.at_level("WARNING", logger="cr_shop.ayarlar"):
        assert len(ayarlari_oku({**ortam, "SHOP_KORUMA_MUAF_IP": "64.0.0.0/2"}).koruma_muaf) == 1
    uyarilar = [r for r in caplog.records if r.name == "cr_shop.ayarlar" and r.levelname == "WARNING"]
    assert len(uyarilar) == 1 and "64.0.0.0/2" in uyarilar[0].getMessage()


# ---------- G3a düzeltme turu 1: yeni liste yolları ve teklif uçları korunur ----------

@pytest.mark.parametrize("yol", ["/tr/urunler", "/en/urunler?stokta=1", "/tr/ara?q=role", "/en/ara?q=x"])  # G3e: boş katalogda sayfa=3 -> 302
def test_g3a_urunler_ve_ara_sayfa_hiz_sinirinda(istemci, yol):
    for i in range(120):
        assert istemci.get(yol).status_code == 200, i
    yanit = istemci.get(yol)
    assert yanit.status_code == 429 and int(yanit.headers["retry-after"]) > 0
    assert _baska_ip(istemci, "192.0.2.10").get(yol).status_code == 200


def test_g3a_urunler_muaf_ip_hiz_sinirina_takilmaz(tmp_path):
    with _muaf_istemci(tmp_path, "192.168.5.77", SHOP_SAYFA_HIZ="3") as c:
        assert [c.get("/tr/urunler").status_code for _ in range(5)] == [200] * 5
        assert [c.get("/tr/ara?q=x").status_code for _ in range(5)] == [200] * 5


def _hizli(istemci, csrf, kod="ZX-1"):
    return istemci.post("/tr/teklif/hizli", data={"csrf": csrf, "ad": "QATestUser", "iletisim": "+90 555 000 00 00",
                                                  "parca_kodu": kod}, follow_redirects=False)


def test_g3a_hizli_teklif_ip_basina_hiz_siniri(istemci):
    csrf = csrf_al(istemci, "/tr/teklif")
    assert [_hizli(istemci, csrf, f"K{i}").status_code for i in range(5)] == [303] * 5
    yanit = _hizli(istemci, csrf, "K6")
    assert yanit.status_code == 429 and int(yanit.headers["retry-after"]) > 0
    # tam teklif formu aynı kovayı paylaşır
    r = istemci.post("/tr/teklif", data={"csrf": csrf, "ad": "Q", "eposta": "q@ornek.test", "ulke": "TR",
                                         "mesaj": "m", "adet": "1", "kvkk_onay": "1"},
                     follow_redirects=False)
    assert r.status_code == 429
    with istemci_db(istemci) as con:
        assert con.execute("SELECT COUNT(*) FROM teklif").fetchone()[0] == 5


def test_g3a_teklif_formu_hiz_siniri(istemci):
    csrf = csrf_al(istemci, "/tr/teklif")
    veri = {"csrf": csrf, "ad": "Q", "eposta": "q@ornek.test", "ulke": "TR", "mesaj": "m", "adet": "1", "kvkk_onay": "1"}
    kodlar = [istemci.post("/tr/teklif", data=veri, follow_redirects=False).status_code for _ in range(6)]
    assert kodlar == [303] * 5 + [429]


def test_g3a_hizli_teklif_engelli_ip_403(istemci):
    csrf = csrf_al(istemci, "/tr/teklif")
    istemci.get(seo.BAL_KUPU_YOLU)
    assert _hizli(istemci, csrf).status_code == 403
    with istemci_db(istemci) as con:
        assert con.execute("SELECT COUNT(*) FROM teklif").fetchone()[0] == 0


def test_g3a_hizli_teklif_muaf_ip_sinirsiz(tmp_path):
    with _muaf_istemci(tmp_path, "192.168.5.77") as c:
        csrf = csrf_al(c, "/tr/teklif")
        assert {_hizli(c, csrf, f"K{i}").status_code for i in range(7)} == {303}
