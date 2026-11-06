from decimal import Decimal

import pytest

from app.katalog.depo import (
    Kategori,
    ListeSonucu,
    ListeSorgusu,
    kategori_agaci,
    kategori_getir,
    kategori_yolu,
    one_cikanlar,
    urun_getir,
    urun_listele,
)
from app.katalog.indeks import indeksi_yeniden_kur
from tests.conftest import kategori_ekle, urun_ekle

# urun_ekle (K6) yeni ürün için urun_ara satırını da yazar; kısa ad:
u = urun_ekle


def idler(sonuc):
    return [x.id for x in sonuc.urunler]


@pytest.fixture
def agac(con):
    """12 Endüstriyel Robotlar > 12.41 KUKA > 12.41.243 KR C4 ; 12 > 12.410 KUKA Eski ; 10 Elektrik ve Elektronik."""
    k12 = kategori_ekle(con, kaynak_id="k12", ad="Endüstriyel Robotlar", yol="12", seviye=0)
    k41 = kategori_ekle(con, kaynak_id="k41", ad="KUKA", yol="12.41", seviye=1, ust_kaynak_id="k12")
    k243 = kategori_ekle(con, kaynak_id="k243", ad="KR C4", yol="12.41.243", seviye=2, ust_kaynak_id="k41")
    k410 = kategori_ekle(con, kaynak_id="k410", ad="KUKA Eski", yol="12.410", seviye=1, ust_kaynak_id="k12")
    k10 = kategori_ekle(con, kaynak_id="k10", ad="Elektrik ve Elektronik", yol="10", seviye=0)
    return {"k12": k12, "k41": k41, "k243": k243, "k410": k410, "k10": k10}


def test_kategori_agaci_ve_urun_sayisi(con, agac):
    u(con, sku="A1", kategori_id=agac["k243"])
    u(con, sku="A2", kategori_id=agac["k41"])
    u(con, sku="A3", kategori_id=agac["k243"], aktif=False)
    u(con, sku="A4", kategori_id=agac["k410"])
    u(con, sku="B1", kategori_id=agac["k10"])
    kokler = kategori_agaci(con)
    assert [d.kategori.ad for d in kokler] == ["Elektrik ve Elektronik", "Endüstriyel Robotlar"]
    elektrik, robot = kokler
    assert elektrik.urun_sayisi == 1 and elektrik.cocuklar == []
    assert robot.kategori.ust_id is None and robot.urun_sayisi == 3
    assert [c.kategori.ad for c in robot.cocuklar] == ["KUKA", "KUKA Eski"]
    kuka = robot.cocuklar[0]
    assert kuka.kategori.ust_id == agac["k12"] and kuka.urun_sayisi == 2
    assert kuka.cocuklar[0].kategori.ad == "KR C4" and kuka.cocuklar[0].urun_sayisi == 1


def test_kategori_getir_ve_yolu(con, agac):
    assert kategori_getir(con, agac["k41"]) == Kategori(
        id=agac["k41"], ad="KUKA", yol="12.41", seviye=1, ust_id=agac["k12"]
    )
    assert kategori_getir(con, 99999) is None
    assert [k.ad for k in kategori_yolu(con, agac["k243"])] == ["Endüstriyel Robotlar", "KUKA", "KR C4"]
    assert [k.ad for k in kategori_yolu(con, agac["k12"])] == ["Endüstriyel Robotlar"]
    assert kategori_yolu(con, 99999) == []


def test_urun_listele_kategori_alt_agaci(con, agac):
    a1 = u(con, sku="A1", ad="Robot Kol", kategori_id=agac["k243"])
    a2 = u(con, sku="A2", ad="Robot Kablo", kategori_id=agac["k41"])
    a3 = u(con, sku="A3", ad="Eski Kol", kategori_id=agac["k410"])
    u(con, sku="B1", ad="Röle", kategori_id=agac["k10"])
    u(con, sku="C1", ad="Kategorisiz")
    assert set(idler(urun_listele(con, ListeSorgusu(kategori_id=agac["k12"])))) == {a1, a2, a3}
    kuka = urun_listele(con, ListeSorgusu(kategori_id=agac["k41"]))
    assert set(idler(kuka)) == {a1, a2}          # 12.410 "12.41" önekine rağmen dahil değil
    yaprak = urun_listele(con, ListeSorgusu(kategori_id=agac["k243"]))
    assert idler(yaprak) == [a1]
    assert yaprak.urunler[0].kategori_ad == "KR C4"
    assert yaprak.urunler[0].kategori_yol == "12.41.243"
    yok = urun_listele(con, ListeSorgusu(kategori_id=99999))
    assert (yok.toplam, yok.sayfa, yok.sayfa_sayisi, yok.urunler) == (0, 1, 1, [])


def test_stokta_filtresi(con):
    a = u(con, sku="A", ad="A", stok=3)
    u(con, sku="B", ad="B", stok=0)
    assert idler(urun_listele(con, ListeSorgusu(stokta=True))) == [a]
    assert urun_listele(con, ListeSorgusu()).toplam == 2


def test_fiyat_araligi_net_eur(con):
    u(con, sku="A", ad="A", fiyat="99.99")
    b = u(con, sku="B", ad="B", fiyat="100.00")
    c = u(con, sku="C", ad="C", fiyat="250.00")
    u(con, sku="D", ad="D", fiyat="1000.00")
    s = urun_listele(con, ListeSorgusu(fiyat_min=Decimal("100"), fiyat_max=Decimal("250.00")))
    assert idler(s) == [b, c]                      # metin karşılaştırması olsaydı "1000.00" de girerdi
    assert s.urunler[0].net_fiyat_eur == Decimal("100.00")
    assert urun_listele(con, ListeSorgusu(fiyat_min=Decimal("1000.01"))).toplam == 0
    assert urun_listele(con, ListeSorgusu(fiyat_max=Decimal("99.99"))).toplam == 1


def test_siralama_uc_tur(con):
    a = u(con, sku="S1", ad="Çelik Kablo", fiyat="300.00")
    b = u(con, sku="S2", ad="Adaptör", fiyat="1200.00")
    c = u(con, sku="S3", ad="Bağlantı", fiyat="45.50")
    d = u(con, sku="S4", ad="Dişli", fiyat="300.00")
    # Türkçe sıra: Ç, C ile D arasında (NOCASE olsaydı Ç en sona düşerdi)
    assert idler(urun_listele(con, ListeSorgusu(siralama="ad"))) == [b, c, a, d]
    assert idler(urun_listele(con, ListeSorgusu(siralama="fiyat_artan"))) == [c, a, d, b]
    assert idler(urun_listele(con, ListeSorgusu(siralama="fiyat_azalan"))) == [b, a, d, c]


def test_sayfalama(con):
    ids = [u(con, sku=f"P{i:02d}", ad=f"Ürün {i:02d}") for i in range(30)]
    s1 = urun_listele(con, ListeSorgusu(sayfa=1))
    assert (s1.toplam, s1.sayfa, s1.sayfa_sayisi, len(s1.urunler)) == (30, 1, 2, 24)
    s2 = urun_listele(con, ListeSorgusu(sayfa=2))
    assert (s2.sayfa, len(s2.urunler)) == (2, 6)
    assert idler(s1) + idler(s2) == ids
    s10 = urun_listele(con, ListeSorgusu(sayfa=3, sayfa_boyu=10))
    assert (s10.sayfa_sayisi, idler(s10)) == (3, ids[20:30])


def test_sayfa_kisilir(con):
    for i in range(30):
        u(con, sku=f"P{i:02d}", ad=f"Ürün {i:02d}")
    assert urun_listele(con, ListeSorgusu(sayfa=-1)).sayfa == 1
    assert urun_listele(con, ListeSorgusu(sayfa=0)).sayfa == 1
    son = urun_listele(con, ListeSorgusu(sayfa=99999))
    assert (son.sayfa, son.sayfa_sayisi, len(son.urunler)) == (2, 2, 6)
    bos = urun_listele(con, ListeSorgusu(arama="yokboyleurun", sayfa=5))
    assert (bos.toplam, bos.sayfa, bos.sayfa_sayisi, bos.urunler) == (0, 1, 1, [])


def test_arama_turkce_harf_duyarsiz(con):
    hedef = u(con, sku="8301033800019", ad="RÖLE İzleme Modülü", uretici_kodu="KR-C4/ABX-77")
    u(con, sku="X2", ad="Kablo Kanalı")
    for sorgu in ["RÖLE", "röle", "role", "Role", "İzleme", "izleme", "IZLEME", "izle", "röle izl", "modulu"]:
        assert idler(urun_listele(con, ListeSorgusu(arama=sorgu))) == [hedef], sorgu
    for sorgu in ["8301033800019", "830103", "KR-C4", "kr-c4/abx", "abx-77"]:
        assert idler(urun_listele(con, ListeSorgusu(arama=sorgu))) == [hedef], sorgu
    assert urun_listele(con, ListeSorgusu(arama="kablo röle")).toplam == 0


def test_bos_arama(con):
    u(con, sku="A", ad="A")
    u(con, sku="B", ad="B")
    for sorgu in [None, "", "   ", "\t\n"]:
        assert urun_listele(con, ListeSorgusu(arama=sorgu)).toplam == 2, repr(sorgu)


@pytest.mark.parametrize(
    "sorgu",
    ['"', '""', "*", "***", "-", "+", "^", ":", "(", ")", "NEAR(", "AND", "OR NOT", "röle AND", 'a"b', "ad:röle"],
)
def test_arama_fts_ozel_karakterler_hata_vermez(con, sorgu):
    u(con, sku="R1", ad="Röle")
    assert isinstance(urun_listele(con, ListeSorgusu(arama=sorgu)), ListeSonucu)


def test_arama_ozel_karakterli_terimler(con):
    hedef = u(con, sku="R1", ad="Röle")
    assert idler(urun_listele(con, ListeSorgusu(arama="-röle"))) == [hedef]
    assert idler(urun_listele(con, ListeSorgusu(arama="röle*"))) == [hedef]
    assert idler(urun_listele(con, ListeSorgusu(arama='"röle"'))) == [hedef]
    assert urun_listele(con, ListeSorgusu(arama="*")).toplam == 0     # kelime yok -> boş sonuç
    assert urun_listele(con, ListeSorgusu(arama="AND")).toplam == 0   # operatör değil, düz kelime


def test_pasif_urun_listede_yok_ama_getir_doner(con):
    p = u(con, sku="P", ad="Pasif Röle", aktif=False)
    a = u(con, sku="A", ad="Aktif Röle")
    assert idler(urun_listele(con, ListeSorgusu(arama="röle"))) == [a]
    assert idler(urun_listele(con, ListeSorgusu())) == [a]
    g = urun_getir(con, p)
    assert g is not None and g.aktif is False and g.sku == "P"
    assert urun_getir(con, 99999) is None


def test_indeks_yeniden_kurulunca_arama_guncel(con):
    a = u(con, sku="A", ad="Eski Ad")
    con.execute("UPDATE urun SET ad = 'Yeni Şalter', uretici_kodu = 'QX-9' WHERE id = ?", (a,))
    assert urun_listele(con, ListeSorgusu(arama="salter")).toplam == 0     # indeks henüz eski
    indeksi_yeniden_kur(con)
    for sorgu in ["şalter", "SALTER", "qx-9"]:
        assert idler(urun_listele(con, ListeSorgusu(arama=sorgu))) == [a], sorgu
    assert urun_listele(con, ListeSorgusu(arama="eski")).toplam == 0


def test_urun_getir_alanlar(con, agac):
    uid = u(
        con, sku="K1", ad="KUKA KRC5", kok="Endüstriyel Robotlar", fiyat="20000.00", teklif=True,
        stok=0, kategori_id=agac["k243"], uretici_kodu="KRC5", gorsel_url="/img/a.jpg",
    )
    g = urun_getir(con, uid)
    assert (g.kategori_id, g.kategori_ad, g.kategori_yol) == (agac["k243"], "KR C4", "12.41.243")
    assert g.kok_kategori_ad == "Endüstriyel Robotlar"
    assert g.net_fiyat_eur == Decimal("20000.00") and g.kdv_orani == Decimal("20")
    assert g.teklif_zorunlu is True and g.stok == 0 and g.tedarik_suresi_gun is None
    assert g.uretici_kodu == "KRC5" and g.gorsel_url == "/img/a.jpg"
    assert g.durum_kodu == "belirtilmemis" and g.durum_ornek is False and g.aktif is True


def test_one_cikanlar(con):
    assert one_cikanlar(con) == []
    g1 = u(con, sku="G1", gorsel_url="/a.jpg")
    u(con, sku="G2", gorsel_url="/b.jpg", aktif=False)
    n1 = u(con, sku="N1")
    g3 = u(con, sku="G3", gorsel_url="/c.jpg")
    u(con, sku="N2", gorsel_url="")
    assert [x.id for x in one_cikanlar(con, adet=3)] == [g1, g3, n1]
    assert [x.id for x in one_cikanlar(con, adet=1)] == [g1]


# ---------- G3a Ö2: parça kodu normalizasyonu, çok kelimeli arama, alaka, fasetler ----------

from app.katalog.depo import Fasetler, faset_sayilari  # noqa: E402
from app.katalog.indeks import kod_birlesik, turetilmis_alanlar  # noqa: E402


def test_g3a_kod_birlesik_ve_turetilmis_alanlar():
    assert kod_birlesik("00-109-802") == "00109802"
    assert kod_birlesik("6ES7 307-1EA00") == "6es73071ea00"
    assert kod_birlesik("KR-C4/ABX.77") == "krc4abx77"
    assert kod_birlesik("0010035195") == "0010035195"          # baştaki sıfırlar korunur
    assert kod_birlesik(None) == "" and kod_birlesik(" - ") == ""
    t = turetilmis_alanlar("KUKA KRC2 GÜÇ KAYNAĞI 27V-NT", "8503053800001", "00-109-802")
    assert t == {"sira_anahtari": "kuka krc2 guc kaynagi 27v-nt", "kod_birlesik": "8503053800001 00109802",
                 "marka": "KUKA", "katli_metin": "|kukakrc2guckaynagi27vnt|krc2guckaynagi27vnt|guckaynagi27vnt|kaynagi27vnt|27vnt|nt"
                                                "|8503053800001|00109802|109802|802",   # G3h: kelime başı pencereleri
                 "tip": "guc_kaynagi"}
    assert turetilmis_alanlar("RÖLE MODÜLÜ 24V", "RL-24", None) == {
        "sira_anahtari": "role modulu 24v", "kod_birlesik": "rl24", "marka": None,
        "katli_metin": "|rolemodulu24v|modulu24v|24v|rl24|24", "tip": "kontaktor_role"}
    assert turetilmis_alanlar("X", "AB-1", "ab1")["kod_birlesik"] == "ab1"   # yinelenen kod bir kez


@pytest.mark.parametrize("sorgu", ["00-109-802", "00109802", "00 109 802", "00.109.802", "00/109/802", "00-109"])
def test_g3a_parca_kodu_ayraclarindan_bagimsiz(con, sorgu):
    hedef = u(con, sku="8503053800001", ad="KUKA KRC2 GÜÇ KAYNAĞI", uretici_kodu="00-109-802")
    u(con, sku="X1", ad="Başka ürün", uretici_kodu="01-109-802")
    assert idler(urun_listele(con, ListeSorgusu(arama=sorgu))) == [hedef]


@pytest.mark.parametrize("sorgu", ["6ES7 307-1EA00", "6ES7307-1EA00", "6es7307-1ea00-0aa0", "6ES73071EA00",
                                   "6ES7 3071EA000AA0"])
def test_g3a_siemens_kodu_bosluklu_ve_birlesik(con, sorgu):
    hedef = u(con, sku="8102000000001", ad="SIEMENS S7-300 GÜÇ KAYNAĞI", uretici_kodu="6ES7307-1EA00-0AA0")
    u(con, sku="X2", ad="SIEMENS S7-300 CPU", uretici_kodu="6ES7315-2AH14-0AB0")
    assert idler(urun_listele(con, ListeSorgusu(arama=sorgu))) == [hedef]


def test_g3a_bastaki_sifirlar_korunur(con):
    a = u(con, sku="A1", ad="Parça A", uretici_kodu="00-109-802")
    b = u(con, sku="B1", ad="Parça B", uretici_kodu="0-109-802")
    assert idler(urun_listele(con, ListeSorgusu(arama="00109802"))) == [a]
    assert idler(urun_listele(con, ListeSorgusu(arama="0109802"))) == [b]


def test_g3a_cok_kelimeli_and_ve_turkce_katlama(con):
    izleme = u(con, sku="S1", ad="SIEMENS SIRIUS İZLEME RÖLESİ")
    u(con, sku="S2", ad="SIEMENS SIRIUS KONTAKTÖR")
    u(con, sku="S3", ad="OMRON RÖLE")
    sart = u(con, sku="S4", ad="SİNYAL ŞARTLANDIRICI 4-20mA")
    kmotor = u(con, sku="K1", ad="KUKA SERVO MOTOR 1FK7")
    u(con, sku="K2", ad="KUKA KABLO")
    u(con, sku="K3", ad="FANUC MOTOR")
    assert idler(urun_listele(con, ListeSorgusu(arama="sirius röle"))) == [izleme]
    assert idler(urun_listele(con, ListeSorgusu(arama="SIRIUS RÖLE"))) == [izleme]
    for sorgu in ("şartlandırıcı", "sartlandirici", "ŞARTLANDIRICI", "SARTLANDIRICI", "şartlan"):
        assert idler(urun_listele(con, ListeSorgusu(arama=sorgu))) == [sart], sorgu
    assert idler(urun_listele(con, ListeSorgusu(arama="kuka motor"))) == [kmotor]
    assert idler(urun_listele(con, ListeSorgusu(arama="motor kuka"))) == [kmotor]


def test_g3a_alaka_tam_kod_sonra_onek_sonra_ad(con):
    ad_eslesmesi = u(con, sku="C1", ad="AA kablo 00 109 802 uyumlu")
    onek = u(con, sku="B1", ad="MM güç kaynağı", uretici_kodu="00-109-8021")
    tam = u(con, sku="A1", ad="ZZ güç kaynağı", uretici_kodu="00-109-802")
    assert idler(urun_listele(con, ListeSorgusu(arama="00-109-802", siralama="alaka"))) == [tam, onek, ad_eslesmesi]
    assert idler(urun_listele(con, ListeSorgusu(arama="00109802", siralama="alaka")))[:2] == [tam, onek]
    # SKU ile tam eşleşme de en üstte
    assert idler(urun_listele(con, ListeSorgusu(arama="b1", siralama="alaka"))) == [onek]
    # açık "ad" sıralaması alaka değil ada göre sıralar
    assert idler(urun_listele(con, ListeSorgusu(arama="00-109-802", siralama="ad"))) == [ad_eslesmesi, onek, tam]
    # aramasız liste "alaka" isterse ada göre sıralanır
    assert idler(urun_listele(con, ListeSorgusu(siralama="alaka"))) == [ad_eslesmesi, onek, tam]


def test_g3a_ad_siralamasi_udf_yok_indeks_kullanir(con):
    for i, ad in enumerate(["Çelik", "Cam", "Dişli"]):
        u(con, sku=f"S{i}", ad=ad)
    sorgular: list[str] = []
    con.set_trace_callback(sorgular.append)
    try:
        sonuc = urun_listele(con, ListeSorgusu(siralama="ad"))
    finally:
        con.set_trace_callback(None)
    assert [x.ad for x in sonuc.urunler] == ["Cam", "Çelik", "Dişli"]
    assert not any("tr_sira" in q for q in sorgular)
    sayfa_sorgusu = next(q for q in sorgular if "ORDER BY" in q)
    plan = " ".join(r[3] for r in con.execute("EXPLAIN QUERY PLAN " + sayfa_sorgusu))
    assert "ix_urun_sira" in plan, plan


def test_g3a_fiyat_araligi_teklifli_urunleri_disler(con):
    a = u(con, sku="A", ad="A", fiyat="500.00")
    u(con, sku="R", ad="Robot", fiyat="800.00", teklif=True)
    assert idler(urun_listele(con, ListeSorgusu(fiyat_min=Decimal("100")))) == [a]
    assert idler(urun_listele(con, ListeSorgusu(fiyat_max=Decimal("1000")))) == [a]
    assert urun_listele(con, ListeSorgusu()).toplam == 2


@pytest.fixture
def faset_veri(con, agac):
    v = {
        "kuka1": u(con, sku="F1", ad="KUKA SERVO MOTOR", kategori_id=agac["k243"], stok=2),
        "kuka2": u(con, sku="F2", ad="KUKA KABLO", kategori_id=agac["k410"], stok=0),
        "abb": u(con, sku="F3", ad="ABB ROBOT", kategori_id=agac["k41"], stok=1, teklif=True, fiyat="20000.00"),
        "siemens": u(con, sku="F4", ad="SIEMENS RÖLE", kategori_id=agac["k10"], stok=0),
        "markasiz": u(con, sku="F5", ad="RÖLE MODÜLÜ 24V", kategori_id=agac["k10"], stok=3),
    }
    con.execute("UPDATE urun SET durum_kodu = 'ikinci_el_test_edildi' WHERE id IN (?, ?)", (v["kuka1"], v["siemens"]))
    con.execute("UPDATE urun SET durum_kodu = 'yeni' WHERE id = ?", (v["abb"],))
    con.commit()
    return v


def _secenekler(liste):
    return [(s.deger, s.sayi, s.secili) for s in liste]


def test_g3a_marka_durum_stok_fiyat_filtreleri(con, faset_veri):
    v = faset_veri
    assert set(idler(urun_listele(con, ListeSorgusu(markalar=("KUKA",))))) == {v["kuka1"], v["kuka2"]}
    assert set(idler(urun_listele(con, ListeSorgusu(markalar=("KUKA", "ABB"))))) == {v["kuka1"], v["kuka2"], v["abb"]}
    assert set(idler(urun_listele(con, ListeSorgusu(durumlar=("ikinci_el_test_edildi",))))) == {v["kuka1"], v["siemens"]}
    assert set(idler(urun_listele(con, ListeSorgusu(durumlar=("belirtilmemis", "yeni"))))) == {
        v["kuka2"], v["markasiz"], v["abb"]}
    assert set(idler(urun_listele(con, ListeSorgusu(tedarikli=True)))) == {v["kuka2"], v["siemens"]}
    assert urun_listele(con, ListeSorgusu(stokta=True, tedarikli=True)).toplam == 5
    assert idler(urun_listele(con, ListeSorgusu(teklifle=True))) == [v["abb"]]
    assert v["abb"] not in idler(urun_listele(con, ListeSorgusu(fiyatli=True)))
    assert urun_listele(con, ListeSorgusu(fiyatli=True, teklifle=True)).toplam == 5
    assert idler(urun_listele(con, ListeSorgusu(markalar=("KUKA",), stokta=True))) == [v["kuka1"]]


def test_g3a_alt_kategori_faseti_coklu(con, agac, faset_veri):
    v = faset_veri
    s = ListeSorgusu(kategori_id=agac["k12"], alt_kategoriler=(agac["k41"],))
    assert set(idler(urun_listele(con, s))) == {v["kuka1"], v["abb"]}       # 12.41 alt ağacı, 12.410 hariç
    s = ListeSorgusu(kategori_id=agac["k12"], alt_kategoriler=(agac["k41"], agac["k410"]))
    assert urun_listele(con, s).toplam == 3
    assert urun_listele(con, ListeSorgusu(alt_kategoriler=(99999,))).toplam == 5   # bilinmeyen kimlik yok sayılır


def test_g3a_faset_sayilari_ayrik_ve_sifirlar_gizli(con, agac, faset_veri):
    secenekler = [kategori_getir(con, agac["k41"]), kategori_getir(con, agac["k410"])]
    f = faset_sayilari(con, ListeSorgusu(kategori_id=agac["k12"]), secenekler)
    assert isinstance(f, Fasetler)
    assert _secenekler(f.marka) == [("KUKA", 2, False), ("ABB", 1, False)]
    assert _secenekler(f.durum) == [("yeni", 1, False), ("ikinci_el_test_edildi", 1, False),
                                    ("belirtilmemis", 1, False)]
    assert _secenekler(f.stok) == [("stokta", 2, False), ("tedarikli", 1, False)]
    assert _secenekler(f.fiyat) == [("fiyatli", 2, False), ("teklifle", 1, False)]
    assert _secenekler(f.kategori) == [(str(agac["k41"]), 2, False), (str(agac["k410"]), 1, False)]
    assert f.toplam == 3
    # seçili marka kendi faset sayısını daraltmaz (ayrık sayım), diğer fasetleri daraltır
    f = faset_sayilari(con, ListeSorgusu(kategori_id=agac["k12"], markalar=("ABB",)), secenekler)
    assert _secenekler(f.marka) == [("KUKA", 2, False), ("ABB", 1, True)]
    assert _secenekler(f.stok) == [("stokta", 1, False)]                       # tedarikli 0 -> gizli
    assert _secenekler(f.kategori) == [(str(agac["k41"]), 1, False)]
    assert f.toplam == 1
    # seçili ama sayısı 0 olan seçenek yine görünür (kaldırılabilsin)
    f = faset_sayilari(con, ListeSorgusu(kategori_id=agac["k12"], markalar=("SIEMENS",)), secenekler)
    assert ("SIEMENS", 0, True) in _secenekler(f.marka)


def test_g3a_faset_sayilari_arama_ve_fiyat_araligiyla(con, faset_veri):
    f = faset_sayilari(con, ListeSorgusu(arama="röle"), [])
    assert _secenekler(f.marka) == [("Siemens", 1, False)]                     # markasız ürün marka seçeneği üretmez
    assert sum(s.sayi for s in f.stok) == 2
    f = faset_sayilari(con, ListeSorgusu(fiyat_min=Decimal("1")), [])
    assert _secenekler(f.fiyat) == [("fiyatli", 4, False)]                     # fiyat aralığı teklifliyi dışlar


def test_g3a_gecis_004_mevcut_veriyi_doldurur(tmp_path, monkeypatch):
    """003'e kadar kurulu veritabanındaki ürünler 004 sonrası türetilmiş alanlar ve yeni FTS ile aranır."""
    import shutil

    from app import db as db_modulu
    from app.db import baglan, gecisleri_uygula

    eski = tmp_path / "gecisler"
    eski.mkdir()
    for dosya in sorted(db_modulu.GECIS_KLASORU.glob("00[123]_*.sql")):
        shutil.copy(dosya, eski / dosya.name)
    monkeypatch.setattr(db_modulu, "GECIS_KLASORU", eski)
    c = baglan(tmp_path / "eski.db")
    gecisleri_uygula(c)
    with c:
        c.execute("INSERT INTO urun (sku, ad, uretici_kodu, temsili_fiyat_eur, olusturma)"
                  " VALUES ('8503053800001', 'KUKA KRC2 GÜÇ KAYNAĞI', '00-109-802', '100.00', 'x')")
        c.execute("INSERT INTO urun_ara (metin, urun_id) VALUES ('kuka krc2 guc kaynagi 8503053800001 00-109-802', 1)")
    monkeypatch.undo()
    assert gecisleri_uygula(c) == ["004_arama_faset.sql", "005_teknik_durum.sql", "006_durum_kaynak.sql",
                                  "007_teklif_iletisim.sql", "008_odeme_teklif_alanlari.sql",
                                   "009_odeme_zamani.sql", "010_urun_ceviri.sql", "011_urun_sira_en.sql",
                                   "012_teklif_kalem_havale_suresi.sql",
                                   "013_katli_tip.sql", "014_po_aciliyet.sql",
                                   "015_teklif_teslim_adresi.sql", "016_indeksler.sql"]
    r = c.execute("SELECT sira_anahtari, kod_birlesik, marka FROM urun").fetchone()
    assert tuple(r) == ("kuka krc2 guc kaynagi", "8503053800001 00109802", "KUKA")
    assert idler(urun_listele(c, ListeSorgusu(arama="00109802"))) == [1]
    assert idler(urun_listele(c, ListeSorgusu(arama="krc2"))) == [1]
    c.close()


# ---------------------------------------------------------------------------
# G3b: teknik özellikler
# ---------------------------------------------------------------------------

def test_g3b_teknik_getir(con):
    from app.katalog.depo import UrunTeknik, teknik_getir

    a, b, c = u(con, sku="A1"), u(con, sku="B1"), u(con, sku="C1")
    with con:
        con.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)",
                    (a, '{"ozellikler":[["Gerilim","24 V"],["Tip","X"]],"bolumler":[["","Not metni"]]}'))
        con.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (?, ?)", (b, "{bozuk json"))
    t = teknik_getir(con, a)
    assert t == UrunTeknik(ozellikler=(("Gerilim", "24 V"), ("Tip", "X")), bolumler=(("", "Not metni"),))
    assert teknik_getir(con, b) is None       # bozuk veri sayfayı düşürmez
    assert teknik_getir(con, c) is None


def test_g3b_gecis_005_mevcut_veriyi_korur(tmp_path, monkeypatch):
    """004'e kadar kurulu veritabanı: 005 yalnız urun_teknik tablosunu ekler, ürün/durum verisi değişmez."""
    import shutil

    from app import db as db_modulu
    from app.db import baglan, gecisleri_uygula

    eski = tmp_path / "gecisler"
    eski.mkdir()
    for dosya in sorted(db_modulu.GECIS_KLASORU.glob("00[1234]_*.sql")):
        shutil.copy(dosya, eski / dosya.name)
    monkeypatch.setattr(db_modulu, "GECIS_KLASORU", eski)
    c = baglan(tmp_path / "eski.db")
    gecisleri_uygula(c)
    with c:
        c.execute("INSERT INTO urun (sku, ad, temsili_fiyat_eur, olusturma, durum_kodu, durum_ornek)"
                  " VALUES ('S1', 'X', '1.00', 'x', 'yeni', 1)")
    monkeypatch.undo()
    assert gecisleri_uygula(c) == ["005_teknik_durum.sql", "006_durum_kaynak.sql", "007_teklif_iletisim.sql",
                                   "008_odeme_teklif_alanlari.sql",
                                   "009_odeme_zamani.sql", "010_urun_ceviri.sql", "011_urun_sira_en.sql",
                                   "012_teklif_kalem_havale_suresi.sql",
                                   "013_katli_tip.sql", "014_po_aciliyet.sql",
                                   "015_teklif_teslim_adresi.sql", "016_indeksler.sql"]
    assert tuple(c.execute("SELECT durum_kodu, durum_ornek FROM urun").fetchone()) == ("yeni", 1)
    with pytest.raises(Exception):
        with c:
            c.execute("INSERT INTO urun_teknik (urun_id, veri) VALUES (1, ?)", ("x" * 8193,))
    c.close()


def test_g3b_gecis_006_cikarimlari_isaretler_ve_genel_koda_cevirir(tmp_path, monkeypatch):
    import shutil

    from app import db as db_modulu
    from app.db import baglan, gecisleri_uygula

    eski = tmp_path / "gecisler"
    eski.mkdir()
    for dosya in sorted(db_modulu.GECIS_KLASORU.glob("00[1-5]_*.sql")):
        shutil.copy(dosya, eski / dosya.name)
    monkeypatch.setattr(db_modulu, "GECIS_KLASORU", eski)
    c = baglan(tmp_path / "eski.db")
    gecisleri_uygula(c)
    with c:
        for sku, durum, ornek in (("A", "ikinci_el_oldugu_gibi", 0), ("B", "ikinci_el_oldugu_gibi", 1),
                                  ("C", "yeni", 0), ("D", "belirtilmemis", 0)):
            c.execute("INSERT INTO urun (sku, ad, temsili_fiyat_eur, olusturma, durum_kodu, durum_ornek)"
                      " VALUES (?, 'X', '1.00', 'x', ?, ?)", (sku, durum, ornek))
    monkeypatch.undo()
    assert gecisleri_uygula(c) == ["006_durum_kaynak.sql", "007_teklif_iletisim.sql", "008_odeme_teklif_alanlari.sql",
                                   "009_odeme_zamani.sql", "010_urun_ceviri.sql", "011_urun_sira_en.sql",
                                   "012_teklif_kalem_havale_suresi.sql",
                                   "013_katli_tip.sql", "014_po_aciliyet.sql",
                                   "015_teklif_teslim_adresi.sql", "016_indeksler.sql"]
    satirlar = [tuple(r) for r in c.execute("SELECT sku, durum_kodu, durum_ornek, durum_kaynak FROM urun ORDER BY sku")]
    assert satirlar == [("A", "ikinci_el", 0, "cikarim"), ("B", "ikinci_el_oldugu_gibi", 1, None),
                        ("C", "yeni", 0, "cikarim"), ("D", "belirtilmemis", 0, None)]
    c.close()
