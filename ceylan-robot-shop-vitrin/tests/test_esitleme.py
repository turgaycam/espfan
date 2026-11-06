import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.esitleme.esitle import esitle, son_basarili_esitleme, son_esitleme
from app.esitleme.kaynak import KaynakIstemci
from tests.conftest import urun_ekle

ORNEK = Path(__file__).parent / "ornekler"
TABAN = "https://www.ceylanrobot.com"
ZAMAN = datetime(2026, 10, 13, 2, 30, tzinfo=UTC)


def yukle(ad: str) -> bytes:
    return (ORNEK / ad).read_bytes()


def sayfa_govdesi(ad: str, total: int | None = None) -> bytes:
    if total is None:
        return yukle(ad)
    veri = json.loads(yukle(ad))
    veri["total"] = total
    return json.dumps(veri).encode()


def kaynak(sayfalar: dict[int, bytes | int], uykular: list[float] | None = None,
           kategori: bytes | None = None) -> KaynakIstemci:
    """sayfalar: sayfa no -> gövde (200) ya da HTTP durum kodu. Listede olmayan sayfa boş döner."""
    def isleyici(istek: httpx.Request) -> httpx.Response:
        if istek.url.path == "/api/public/categories":
            return httpx.Response(200, content=kategori or yukle("kategoriler.json"))
        sayfa = int(istek.url.params["page"])
        cevap = sayfalar.get(sayfa)
        if cevap is None:
            return httpx.Response(200, json={"data": [], "total": 3})
        if isinstance(cevap, int):
            return httpx.Response(cevap)
        return httpx.Response(200, content=cevap)

    http = httpx.Client(transport=httpx.MockTransport(isleyici))
    return KaynakIstemci(http, TABAN, bekleme=1.0, uyku=(uykular if uykular is not None else []).append)


def iki_sayfa() -> dict[int, bytes | int]:
    return {1: yukle("urunler_s1.json"), 2: yukle("urunler_s2.json")}


def urun(con, sku):
    return con.execute("SELECT * FROM urun WHERE sku=?", (sku,)).fetchone()


def test_tam_tur(con, bantlar):
    eski = urun_ekle(con, sku="ESKI1", ad="Kaynakta artık yok")
    s = esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    assert (s.durum, s.api_toplam, s.cekilen, s.eklenen, s.guncellenen, s.pasiflenen, s.hata, s.bozuk) == (
        "tam", 3, 3, 3, 0, 1, None, 0)
    aktif = con.execute("SELECT COUNT(*) FROM urun WHERE aktif=1").fetchone()[0]
    assert aktif == s.api_toplam == 3
    assert con.execute("SELECT aktif FROM urun WHERE id=?", (eski,)).fetchone()[0] == 0
    g = son_esitleme(con)
    assert (g["durum"], g["api_toplam"], g["cekilen"], g["pasiflenen"]) == ("tam", 3, 3, 1)
    assert g["bitis"] == ZAMAN.isoformat()


def test_urun_esleme_ve_kategori(con, bantlar):
    esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    siemens = urun(con, "8102030100019")
    assert siemens["ad"] == "SIEMENS SIRIUS İZLEME RÖLESİ"
    assert siemens["uretici_kodu"] == "3UG4512-1BR20"
    assert siemens["kdv_orani"] == "20" and siemens["stok"] == 1
    assert siemens["gorsel_url"] is None
    assert siemens["kok_kategori_ad"] == "Elektrik ve Elektronik"
    assert siemens["kaynak_guncelleme"] == "2026-10-12T17:40:02.577Z"
    kat = con.execute("SELECT * FROM kategori WHERE id=?", (siemens["kategori_id"],)).fetchone()
    assert (kat["ad"], kat["yol"], kat["seviye"], kat["erp_id"]) == ("ROLELER/ZAMANLAYICILAR", "10.18.75", 2, 75)
    assert kat["ust_kaynak_id"] == "6a26d4fcd01723cd75a4fcb4"
    # adı null olan kategori kaydı atlanır
    assert con.execute("SELECT COUNT(*) FROM kategori").fetchone()[0] == 8


def test_temsili_fiyat_ve_teklif_zorunlu(con, bantlar):
    esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    kuka = urun(con, "8301033800019")
    assert kuka["kok_kategori_ad"] == "Endüstriyel Robotlar"
    assert kuka["teklif_zorunlu"] == 1
    assert kuka["fiyat_temsili"] == 1 and kuka["kaynak_fiyat_eur"] == "0.00"
    assert kuka["temsili_fiyat_eur"] == "15515.00"
    assert kuka["gorsel_url"] == TABAN + "/api/uploads/admin-uploads/ee278328-79d2-45db-bb15-99d3f9b44f5e.webp"
    siemens = urun(con, "8102030100019")
    assert siemens["temsili_fiyat_eur"] == "511.00" and siemens["teklif_zorunlu"] == 0
    # kaynak fiyatı > 0 olan ürün: kaynak fiyat gösterilir, temsili rozet yok
    meanwell = urun(con, "8205010100007")
    assert meanwell["kaynak_fiyat_eur"] == "125.50"
    assert meanwell["temsili_fiyat_eur"] == "125.50" and meanwell["fiyat_temsili"] == 0


def test_ikinci_tur_gunceller_fiyat_degismez(con, bantlar):
    esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    ilk = urun(con, "8102030100019")["temsili_fiyat_eur"]
    s = esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    assert (s.durum, s.eklenen, s.guncellenen, s.pasiflenen) == ("tam", 0, 3, 0)
    assert urun(con, "8102030100019")["temsili_fiyat_eur"] == ilk
    assert con.execute("SELECT COUNT(*) FROM urun").fetchone()[0] == 3


def test_eksik_tur_total_degisirse_pasifleme_yok(con, bantlar):
    eski = urun_ekle(con, sku="ESKI1", ad="Kaynakta artık yok")
    # sayfalama sırasında kaynağa bir kayıt eklendi: 2. ve 3. sayfa total=4 bildiriyor
    sayfalar = {1: yukle("urunler_s1.json"), 2: sayfa_govdesi("urunler_s2.json", total=4),
                3: json.dumps({"data": [], "total": 4}).encode()}
    s = esitle(con, kaynak(sayfalar), bantlar, lambda: ZAMAN)
    assert s.durum == "eksik" and s.api_toplam == 4 and s.pasiflenen == 0
    assert s.eklenen == 3
    assert con.execute("SELECT aktif FROM urun WHERE id=?", (eski,)).fetchone()[0] == 1
    assert son_esitleme(con)["durum"] == "eksik"
    assert son_basarili_esitleme(con) is None


def test_eksik_tur_sayfa_alinamazsa(con, bantlar):
    eski = urun_ekle(con, sku="ESKI1", ad="Kaynakta artık yok")
    uykular: list[float] = []
    sayfalar = {1: yukle("urunler_s1.json"), 2: 503}
    s = esitle(con, kaynak(sayfalar, uykular), bantlar, lambda: ZAMAN)
    assert s.durum == "eksik" and s.pasiflenen == 0 and s.cekilen == 2
    assert s.hata == "alinamayan_sayfa: 2"
    assert con.execute("SELECT aktif FROM urun WHERE id=?", (eski,)).fetchone()[0] == 1
    assert urun(con, "8301033800019") is not None


def test_ag_hatasi_hata_ve_veri_degismez(con, bantlar):
    eski = urun_ekle(con, sku="ESKI1", ad="Eski ürün", fiyat="42.00")
    uykular: list[float] = []
    cagrilar = {"n": 0}

    def ag_yok(istek):
        cagrilar["n"] += 1
        raise httpx.ConnectError("ag yok", request=istek)

    http = httpx.Client(transport=httpx.MockTransport(ag_yok))
    s = esitle(con, KaynakIstemci(http, TABAN, uyku=uykular.append), bantlar, lambda: ZAMAN)
    assert s.durum == "hata" and "KaynakHatasi" in s.hata
    assert cagrilar["n"] == 3                     # ilk istek + 2 yeniden deneme
    assert uykular == [1.0, 2.0, 1.0, 4.0, 1.0]
    satir = con.execute("SELECT aktif, temsili_fiyat_eur FROM urun WHERE id=?", (eski,)).fetchone()
    assert tuple(satir) == (1, "42.00")
    assert con.execute("SELECT COUNT(*) FROM urun").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM kategori").fetchone()[0] == 0
    assert son_esitleme(con)["durum"] == "hata"


def test_bozuk_kayit_atlanir(con, bantlar):
    eski = urun_ekle(con, sku="ESKI1", ad="Kaynakta artık yok")
    s = esitle(con, kaynak({1: yukle("urunler_bozuk.json")}), bantlar, lambda: ZAMAN)
    # K1: 1 geçerli + 3 bozuk == total 4 -> tur tam; bozuklar ayrı sayılır
    assert (s.durum, s.cekilen, s.eklenen, s.bozuk) == ("tam", 1, 1, 3)
    assert s.hata.startswith("bozuk_kayit: 3 [")
    assert "B0001:eksik_alan" in s.hata and "s1#3:eksik_alan" in s.hata   # sku boş -> sayfa+sıra
    assert son_esitleme(con)["bozuk"] == 3
    assert con.execute("SELECT sku FROM urun WHERE aktif=1").fetchall()[0][0] == "8102030100019"
    assert con.execute("SELECT aktif FROM urun WHERE id=?", (eski,)).fetchone()[0] == 0


def test_bozuk_karakter_temizlenir(con, bantlar):
    esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    kok = con.execute("SELECT ad FROM kategori WHERE yol='511'").fetchone()[0]
    assert kok == "GÜÇ KAYNA�I"
    meanwell = urun(con, "8205010100007")
    assert meanwell["ad"] == "MEAN WELL 24V GÜÇ KAYNA�I"
    assert meanwell["kok_kategori_ad"] == "GÜÇ KAYNA�I"
    meanwell["ad"].encode("utf-8")


def test_arama_indeksi_yeniden_kurulur(con, bantlar):
    eski = urun_ekle(con, sku="ESKI1", ad="Eski Röle")
    esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    bul = lambda q: [r[0] for r in con.execute(
        "SELECT urun_id FROM urun_ara WHERE urun_ara MATCH ?", (q,))]
    siemens_id = urun(con, "8102030100019")["id"]
    assert bul("izleme") == [siemens_id]
    assert bul("3ug4512*") == [siemens_id]
    assert bul("eski") == []                              # pasif ürün indekste yok
    assert bul("rol*") == [siemens_id]
    assert con.execute("SELECT COUNT(*) FROM urun_ara").fetchone()[0] == 3


def test_son_basarili_esitleme(con, bantlar):
    assert son_basarili_esitleme(con) is None
    assert son_esitleme(con) is None
    esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    assert son_basarili_esitleme(con) == ZAMAN
    sonra = datetime(2026, 10, 14, 2, 30, tzinfo=UTC)
    http = httpx.Client(transport=httpx.MockTransport(lambda istek: httpx.Response(500)))
    esitle(con, KaynakIstemci(http, TABAN, uyku=lambda s: None), bantlar, lambda: sonra)
    assert son_esitleme(con)["durum"] == "hata"
    assert son_basarili_esitleme(con) == ZAMAN


def _s1_degistir(degistir) -> bytes:
    veri = json.loads(yukle("urunler_s1.json"))
    degistir(veri)
    return json.dumps(veri).encode()          # ensure_ascii: surrogate "\udc9e" kaçışı korunur


def test_gorsel_yolunda_surrogate_temizlenir_tur_cokmez(con, bantlar):
    def boz(v):
        v["data"][0]["images"] = ["/api/uploads/a\udc9eb.webp"]
    s = esitle(con, kaynak({1: _s1_degistir(boz), 2: yukle("urunler_s2.json")}), bantlar, lambda: ZAMAN)
    # tüm API metin alanları temizlenir: tek surrogate U+FFFD olur, kayıt bozuk sayılmaz, tur çökmez
    assert (s.durum, s.cekilen, s.bozuk, s.hata) == ("tam", 3, 0, None)
    assert urun(con, "8301033800019")["gorsel_url"] == TABAN + "/api/uploads/a�b.webp"
    assert urun(con, "8102030100019") is not None and urun(con, "8205010100007") is not None


def test_nan_fiyat_bozuk_sayilir(con, bantlar):
    def boz(v):
        v["data"][0]["price"]["amount"] = "NaN"
    s = esitle(con, kaynak({1: _s1_degistir(boz), 2: yukle("urunler_s2.json")}), bantlar, lambda: ZAMAN)
    assert s.bozuk == 1 and s.cekilen == 2 and s.durum == "tam"
    assert urun(con, "8301033800019") is None


def test_bos_kategori_listesi_hata(con, bantlar):
    eski = urun_ekle(con, sku="ESKI1", ad="Eski ürün", fiyat="42.00")
    s = esitle(con, kaynak(iki_sayfa(), kategori=b"[]"), bantlar, lambda: ZAMAN)
    assert s.durum == "hata"
    assert con.execute("SELECT aktif FROM urun WHERE id=?", (eski,)).fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM urun").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM kategori").fetchone()[0] == 0


def test_stok_sonsuz_bozuk_ve_hata_gunlukte(con, bantlar):
    def boz(v):
        v["data"][0]["stock"] = float("inf")          # json.dumps -> Infinity; sonsuz stok
    govde = _s1_degistir(boz).replace(b"Infinity", b"1e999")
    s = esitle(con, kaynak({1: govde, 2: yukle("urunler_s2.json")}), bantlar, lambda: ZAMAN)
    assert (s.durum, s.cekilen, s.bozuk) == ("tam", 2, 1)
    assert "8301033800019:OverflowError" in s.hata
    assert "8301033800019:OverflowError" in son_esitleme(con)["hata"]
    assert "bozuk_kayit: 1" in son_esitleme(con)["hata"]


def test_programlama_hatasi_bozuk_sayilmaz_tur_hata(con, bantlar, monkeypatch):
    import app.esitleme.esitle as modul

    def patla(kayit, taban, gorsel_dizin=None):
        raise AttributeError("kod hatasi")

    monkeypatch.setattr(modul, "_urun_esle_ic", patla)
    s = esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    assert s.durum == "hata" and "AttributeError" in s.hata
    assert con.execute("SELECT COUNT(*) FROM urun").fetchone()[0] == 0


def test_esitleme_urun_aciklama_tablosuna_yazmaz_silmez(con, bantlar):
    """G2: urun_aciklama eşitlemeden bağımsızdır; ürün pasiflense de satır silinmez/değişmez."""
    eski = urun_ekle(con, sku="ESKI1", ad="Kaynakta artık yok")
    with con:
        con.execute("INSERT INTO urun_aciklama (urun_id, dil, metin, kaynak, model, uretildi) VALUES (?, ?, ?, ?, ?, ?)",
                    (eski, "tr", "Elle yazılmış açıklama", "kaynak", None, "2026-10-13T00:00:00+00:00"))
    esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    assert urun(con, "ESKI1")["aktif"] == 0
    satirlar = con.execute("SELECT urun_id, dil, metin, kaynak FROM urun_aciklama").fetchall()
    assert [tuple(r) for r in satirlar] == [(eski, "tr", "Elle yazılmış açıklama", "kaynak")]


def test_g3a_esitleme_turetilmis_alanlari_doldurur(con, bantlar):
    from app.katalog.depo import ListeSorgusu, urun_listele

    esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    kuka, siemens = urun(con, "8301033800019"), urun(con, "8102030100019")
    assert (kuka["sira_anahtari"], kuka["kod_birlesik"], kuka["marka"]) == (
        "kuka krc5 kr 140 r3200-2 pa", "8301033800019 0010035195", "KUKA")
    assert siemens["kod_birlesik"] == "8102030100019 3ug45121br20" and siemens["marka"] == "Siemens"
    assert [x.id for x in urun_listele(con, ListeSorgusu(arama="3UG45121BR20")).urunler] == [siemens["id"]]
    assert [x.id for x in urun_listele(con, ListeSorgusu(arama="3UG4512 1BR20")).urunler] == [siemens["id"]]


# ---------------------------------------------------------------------------
# G3b: teknik özellikler (urun_teknik) ve durum çıkarımı
# ---------------------------------------------------------------------------

def _s1_teknik(**alanlar_sku) -> bytes:
    """urunler_s1.json'daki ürünlere alan ekler: {sku: {alan: değer}}."""
    veri = json.loads(yukle("urunler_s1.json"))
    for kayit in veri["data"]:
        kayit.update(alanlar_sku.get(kayit["sku"], {}))
    return json.dumps(veri, ensure_ascii=False).encode("utf-8")


SIEMENS_TEKNIK = {
    "techSpecs": [{"label": "Besleme", "value": "<b>24 V</b> DC"}, {"label": "Tip", "value": "3UG4512"}],
    "descriptionSections": [{"title": "", "content": "SIEMENS SIRIUS İZLEME RÖLESİ\n\n*Görseldeki ürün ikinci eldir."
                             "<img src='data:image/jpeg;base64," + "A" * 5000 + "'>"}],
}


def _teknik(con, sku):
    r = con.execute("SELECT t.veri FROM urun_teknik t JOIN urun u ON u.id = t.urun_id WHERE u.sku = ?",
                    (sku,)).fetchone()
    return json.loads(r[0]) if r else None


def test_g3b_teknik_ozellikler_saklanir_ve_durum_cikarilir(con, bantlar):
    sayfalar = {1: _s1_teknik(**{"8102030100019": SIEMENS_TEKNIK}), 2: yukle("urunler_s2.json")}
    s = esitle(con, kaynak(sayfalar), bantlar, lambda: ZAMAN)
    assert s.durum == "tam"
    t = _teknik(con, "8102030100019")
    assert t == {"ozellikler": [["Besleme", "24 V DC"], ["Tip", "3UG4512"]],
                 "bolumler": [["", "*Görseldeki ürün ikinci eldir."]]}
    ham = con.execute("SELECT veri FROM urun_teknik").fetchone()[0]
    assert "base64" not in ham and "AAAA" not in ham and "<" not in ham
    siemens = urun(con, "8102030100019")
    assert (siemens["durum_kodu"], siemens["durum_ornek"], siemens["durum_kaynak"]) == ("ikinci_el", 0, "cikarim")
    # teknik verisi olmayan ürün: satır yok, durum dokunulmaz
    assert _teknik(con, "8301033800019") is None
    assert urun(con, "8301033800019")["durum_kodu"] == "belirtilmemis"
    assert con.execute("SELECT COUNT(*) FROM urun_teknik").fetchone()[0] == 1


def test_g3b_belirsizse_onceki_durum_korunur_ornek_durum_cikarimla_degisir(con, bantlar):
    esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    with con:
        con.execute("UPDATE urun SET durum_kodu = 'yeni', durum_ornek = 0 WHERE sku = '8301033800019'")
        con.execute("UPDATE urun SET durum_kodu = 'yeni', durum_ornek = 1 WHERE sku = '8102030100019'")
    sayfalar = {1: _s1_teknik(**{"8102030100019": SIEMENS_TEKNIK}), 2: yukle("urunler_s2.json")}
    esitle(con, kaynak(sayfalar), bantlar, lambda: ZAMAN)
    # metinde kalıp yok: önceki değer (elle girilmiş 'yeni') korunur
    assert (urun(con, "8301033800019")["durum_kodu"], urun(con, "8301033800019")["durum_ornek"]) == ("yeni", 0)
    # örnek durum, kaynaktan çıkarılan gerçek durumla değişir (örnek işareti kalkar)
    assert (urun(con, "8102030100019")["durum_kodu"], urun(con, "8102030100019")["durum_ornek"]) == ("ikinci_el", 0)


def test_g3b_kaynakta_teknik_bosalinca_satir_silinir(con, bantlar):
    sayfalar = {1: _s1_teknik(**{"8102030100019": SIEMENS_TEKNIK}), 2: yukle("urunler_s2.json")}
    esitle(con, kaynak(sayfalar), bantlar, lambda: ZAMAN)
    assert _teknik(con, "8102030100019") is not None
    esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    assert _teknik(con, "8102030100019") is None
    # düzeltme turu 1: önceki değer eşitlemenin çıkarımıydı -> kaynakta ibare kalkınca geri alınır
    assert (urun(con, "8102030100019")["durum_kodu"], urun(con, "8102030100019")["durum_kaynak"]) == ("belirtilmemis", None)


def test_g3b_bozuk_teknik_alani_kaydi_bozmaz(con, bantlar):
    sayfalar = {1: _s1_teknik(**{"8102030100019": {"techSpecs": "bozuk", "descriptionSections": [None, 5]}}),
                2: yukle("urunler_s2.json")}
    s = esitle(con, kaynak(sayfalar), bantlar, lambda: ZAMAN)
    assert (s.durum, s.bozuk) == ("tam", 0)
    assert _teknik(con, "8102030100019") is None
