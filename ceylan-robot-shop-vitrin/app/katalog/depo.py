"""Katalog okuma katmanı: kategori ağacı, ürün listesi/filtre/faset/sıralama, FTS5 arama.

Yazma yapmaz; eşitleme (Görev 5) urun/kategori/urun_ara tablolarını ve türetilmiş alanları (G3a) doldurur.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Literal

import yaml

from app.fiyat.kurallar import kdv_gecerli, kdv_gecersiz_sql
from app.katalog.indeks import KATLI_PENCERE, kod_birlesik
from app.katalog.tip import sorgu_tipi
from app.metin import normalize

SAYFA_BOYU_MAX = 100
_KELIME = re.compile(r"\w+")

_URUN_SQL = (
    "SELECT u.*, k.ad AS kategori_ad, k.yol AS kategori_yol "
    "FROM urun u LEFT JOIN kategori k ON k.id = u.kategori_id"
)
_SAYI_SQL = "SELECT COUNT(*) FROM urun u LEFT JOIN kategori k ON k.id = u.kategori_id"
_KATEGORI_SQL = (
    "SELECT k.id, k.ad, k.yol, k.seviye, ust.id AS ust_id "
    "FROM kategori k LEFT JOIN kategori ust ON ust.kaynak_id = k.ust_kaynak_id"
)
# Fiyat yalnız SQL'de karşılaştırma/sıralama için REAL'e çevrilir; hesap yapılmaz (değerler 2 hane).
_FIYAT = "CAST(u.temsili_fiyat_eur AS REAL)"
# G3j madde 4: KDV oranı geçersiz ürün de teklifle satılır (fiyat sıralaması, fiyat faseti, aralık, önerilen puanı)
_TEKLIFLE = f"(u.teklif_zorunlu = 1 OR {kdv_gecersiz_sql('u')})"
# G3a: ada göre sıra eşitlemede hesaplanan sira_anahtari sütunundan (ix_urun_sira); istekte Python UDF yok.
_SIRALAR = {
    "ad": "u.sira_anahtari, u.id",
    # G3e madde 2: teklifle satılan (fiyatı gösterilmeyen) ürünler iki yönde de sonda
    "fiyat_artan": f"{_TEKLIFLE}, {_FIYAT} ASC, u.id",
    "fiyat_azalan": f"{_TEKLIFLE}, {_FIYAT} DESC, u.id",
}
SAYFA_BOYLARI = (24, 48)   # G3e madde 8 (kontrolcü kararı, düzeltme 1): ?adet= yalnız 24/48; başka değer 24
# G3h madde 8: "Önerilen" puanı: stokta + fiyatlı + durumu bilinen + görselli + teknik verili (her biri 1)
# G3j inceleme M-8: stok puanı alınabilir stoktan (madde 5): tümü ayrılmış ürünler ({ayrilmis}: kimlik yer tutucuları) almaz
ONERILEN_PUAN = (    # teknik_var eşitlemede hesaplanır (inceleme M-6)
    "((u.stok > 0 AND u.id NOT IN ({ayrilmis})) + (NOT " + _TEKLIFLE + ") + (u.durum_kodu != 'belirtilmemis')"
    " + (COALESCE(u.gorsel_url, '') != '') + u.teknik_var)"
)
FASETLER = ("marka", "durum", "stok", "fiyat", "kategori", "tip")    # G3h madde 5: tip (urun.tip, tip.yaml)
DURUM_SIRASI = ("yeni", "ikinci_el_test_edildi", "yenilenmis", "ikinci_el", "ikinci_el_oldugu_gibi")  # 'belirtilmemis' en sonda


@dataclass(frozen=True)
class Kategori:
    id: int
    ad: str
    yol: str
    seviye: int
    ust_id: int | None


@dataclass
class KategoriDugum:
    kategori: Kategori
    cocuklar: list[KategoriDugum]
    urun_sayisi: int        # alt kategoriler dahil aktif ürün


@dataclass(frozen=True)
class Urun:
    id: int
    sku: str
    ad: str
    uretici_kodu: str | None
    kategori_id: int | None
    kategori_ad: str | None
    kategori_yol: str | None
    kok_kategori_ad: str
    kdv_orani: Decimal
    stok: int
    tedarik_suresi_gun: int | None
    gorsel_url: str | None
    net_fiyat_eur: Decimal
    fiyat_temsili: bool
    teklif_zorunlu: bool
    durum_kodu: str
    durum_ornek: bool
    aktif: bool
    kod_birlesik: str = ""
    kdv_gecersiz: bool = False    # G3j madde 4: KDV oranı {0, 1, 10, 20} dışında: teklif_zorunlu da True sayılır


@dataclass(frozen=True)
class ListeSorgusu:
    kategori_id: int | None = None
    arama: str | None = None
    stokta: bool = False
    # G3e madde 9: aralık ziyaretçinin gördüğü para birimi ve KDV kipindedir: karşılaştırılan değer
    # net EUR × fiyat_carpani (× (1 + KDV oranı) fiyat_kdv_dahil ise). Verilirse teklifle satılanlar dışlanır (G3a).
    fiyat_min: Decimal | None = None
    fiyat_max: Decimal | None = None
    fiyat_carpani: Decimal = Decimal("1")  # TRY gösterimde EUR satış kuru
    fiyat_kdv_dahil: bool = False
    # alaka: yalnız aramada (yoksa ad); G3h madde 8: onerilen (sorgusuz listelerin varsayılanı, rota seçer)
    siralama: Literal["ad", "fiyat_artan", "fiyat_azalan", "alaka", "onerilen"] = "ad"
    sayfa: int = 1
    sayfa_boyu: int = 24
    # G3a fasetleri (çoklu seçim; aynı faset içinde VEYA, fasetler arası VE)
    tedarikli: bool = False               # stok faseti: stokta / ayrılmış / tedarikli (hepsi ya da hiçbiri = filtre yok)
    # G3j madde 5: "stokta" = alınabilir stok (stok − açık siparişlerin ayırdığı > 0). Stoklu ama tümü ayrılmış ürünler
    # (kimlikleri rota ayırma haritasından verir) "ayrilmis" seçeneğinde sayılır.
    ayrilmis: bool = False
    ayrilmis_idler: tuple[int, ...] = ()
    markalar: tuple[str, ...] = ()        # urun.marka (marka.py görünen adı)
    tipler: tuple[str, ...] = ()          # G3h madde 5: urun.tip (tip.yaml anahtarı)
    durumlar: tuple[str, ...] = ()        # urun.durum_kodu ('belirtilmemis' dahil)
    fiyatli: bool = False                 # fiyat türü faseti: fiyatlı / teklifle (ikisi birden = filtre yok)
    teklifle: bool = False
    alt_kategoriler: tuple[int, ...] = ()  # kategori faseti: seçilen kategorilerin alt ağaçları (bilinmeyen yok sayılır)
    dil: str = "tr"                       # G3f: "en" aramada EN ürün adı (urun_ara.ad_en) da eşleşir
    veya: bool = False                    # G3h madde 2: kelimeler VEYA ile (VE 0 sonuç verdiğinde gevşetme)


@dataclass(frozen=True)
class ListeSonucu:
    urunler: list[Urun]
    toplam: int
    sayfa: int
    sayfa_sayisi: int


@dataclass(frozen=True)
class Secenek:
    deger: str
    sayi: int          # bu seçenek eklenirse (aynı fasetin diğer seçimleri yok sayılarak) eşleşen ürün
    secili: bool


@dataclass(frozen=True)
class Fasetler:
    marka: tuple[Secenek, ...] = ()
    tip: tuple[Secenek, ...] = ()
    durum: tuple[Secenek, ...] = ()
    stok: tuple[Secenek, ...] = ()
    fiyat: tuple[Secenek, ...] = ()
    kategori: tuple[Secenek, ...] = ()
    toplam: int = 0


def _bos_sonuc() -> ListeSonucu:
    return ListeSonucu(urunler=[], toplam=0, sayfa=1, sayfa_sayisi=1)


def _urun(r: sqlite3.Row) -> Urun:
    kdv_gecersiz = not kdv_gecerli(r["kdv_orani"])
    return Urun(
        id=r["id"], sku=r["sku"], ad=r["ad"], uretici_kodu=r["uretici_kodu"],
        kategori_id=r["kategori_id"], kategori_ad=r["kategori_ad"], kategori_yol=r["kategori_yol"],
        kok_kategori_ad=r["kok_kategori_ad"], kdv_orani=Decimal(r["kdv_orani"]), stok=r["stok"],
        tedarik_suresi_gun=r["tedarik_suresi_gun"], gorsel_url=r["gorsel_url"],
        net_fiyat_eur=Decimal(r["temsili_fiyat_eur"]), fiyat_temsili=bool(r["fiyat_temsili"]),
        teklif_zorunlu=bool(r["teklif_zorunlu"]) or kdv_gecersiz, durum_kodu=r["durum_kodu"],
        durum_ornek=bool(r["durum_ornek"]), aktif=bool(r["aktif"]), kod_birlesik=r["kod_birlesik"] or "",
        kdv_gecersiz=kdv_gecersiz,
    )


def _kategori(r: sqlite3.Row) -> Kategori:
    return Kategori(id=r["id"], ad=r["ad"], yol=r["yol"], seviye=r["seviye"], ust_id=r["ust_id"])


def kategori_getir(con: sqlite3.Connection, kategori_id: int) -> Kategori | None:
    r = con.execute(_KATEGORI_SQL + " WHERE k.id = ?", (kategori_id,)).fetchone()
    return _kategori(r) if r is not None else None


def kategori_yolu(con: sqlite3.Connection, kategori_id: int) -> list[Kategori]:
    yol: list[Kategori] = []
    gorulen: set[int] = set()
    simdiki: int | None = kategori_id
    while simdiki is not None and simdiki not in gorulen:   # bozuk veride döngüye girmez
        gorulen.add(simdiki)
        k = kategori_getir(con, simdiki)
        if k is None:
            break
        yol.append(k)
        simdiki = k.ust_id
    yol.reverse()
    return yol


def kategori_agaci(con: sqlite3.Connection) -> list[KategoriDugum]:
    satirlar = con.execute(_KATEGORI_SQL + " WHERE k.aktif = 1").fetchall()
    sayilar = {
        r["kategori_id"]: r["n"]
        for r in con.execute(
            "SELECT kategori_id, COUNT(*) AS n FROM urun "
            "WHERE aktif = 1 AND kategori_id IS NOT NULL GROUP BY kategori_id"
        )
    }
    dugumler = {
        r["id"]: KategoriDugum(kategori=_kategori(r), cocuklar=[], urun_sayisi=sayilar.get(r["id"], 0))
        for r in satirlar
    }
    kokler: list[KategoriDugum] = []
    for d in dugumler.values():
        ust = dugumler.get(d.kategori.ust_id) if d.kategori.ust_id is not None else None
        (ust.cocuklar if ust is not None else kokler).append(d)

    def topla(d: KategoriDugum) -> int:
        d.cocuklar.sort(key=lambda c: (normalize(c.kategori.ad), c.kategori.id))
        d.urun_sayisi += sum(topla(c) for c in d.cocuklar)
        return d.urun_sayisi

    kokler.sort(key=lambda c: (normalize(c.kategori.ad), c.kategori.id))
    for d in kokler:
        topla(d)
    return kokler


def _esitleme_anahtari(con: sqlite3.Connection) -> tuple:
    r = con.execute("SELECT id, bitis FROM esitleme_gunlugu ORDER BY id DESC LIMIT 1").fetchone()
    return (r[0], r[1]) if r is not None else (None, None)


def kategori_agaci_onbellekli(con: sqlite3.Connection, depo: dict) -> list[KategoriDugum]:
    """Süreç içi önbellekli kategori ağacı (G3a). Anahtar: veritabanındaki son eşitleme kaydı (kimlik + bitiş);
    eşitleme başlayınca ve bitince anahtar değişir, ağaç yeniden kurulur. Dönen düğümler paylaşılır: DEĞİŞTİRMEYİN."""
    anahtar = _esitleme_anahtari(con)
    kayit = depo.get("kategori_agaci")
    if kayit is not None and kayit[0] == anahtar:
        return kayit[1]
    agac = kategori_agaci(con)
    depo["kategori_agaci"] = (anahtar, agac)
    return agac


def urun_getir(con: sqlite3.Connection, urun_id: int) -> Urun | None:
    r = con.execute(_URUN_SQL + " WHERE u.id = ?", (urun_id,)).fetchone()
    return _urun(r) if r is not None else None


ESANLAM_YOLU = Path(__file__).parent / "esanlam.yaml"
ESANLAM_EN_UZUN = 3          # en uzun eşanlamlı terimin kelime sayısı
KISA_TERIM = 3               # bu uzunluğa kadar eşanlamlı terim tam kelime aranır (önek değil)


def _terim_listesi(grup) -> tuple[tuple[str, ...], ...]:
    terimler = tuple(dict.fromkeys(tuple(_KELIME.findall(normalize(str(x)))) for x in grup or []))
    return tuple(x for x in terimler if x)


@cache
def _esanlam_verisi() -> tuple[dict[tuple[str, ...], tuple[tuple[str, ...], ...]],
                               dict[tuple[str, ...], tuple[tuple[str, ...], tuple[str, ...]]],
                               dict[tuple[str, ...], tuple[str, ...]]]:
    """(terim -> grubun terimleri, terim -> izinli ürün tipleri, terim -> dahil edilen ürün tipleri). Liste biçimli grup
    çift yönlüdür; G3k madde 4: sözlük biçimli grup ({terimler, karsiliklar, tipler}) tek yönlüdür ve terimin
    eşleşmesini ürün tipleriyle kısıtlar (karsiliklar yoksa terimler birbirine eşlenir: çift yönlü). G3l madde 2: açık
    tip eşlemesi (`tip_dahil`) olan grubun terimi o tipteki TÜM ürünleri de eşleştirir (yalnız bu alanı olan gruplar)."""
    ham = yaml.safe_load(ESANLAM_YOLU.read_text(encoding="utf-8")) or {}
    sozluk: dict[tuple[str, ...], dict[tuple[str, ...], None]] = {}
    tipler: dict[tuple[str, ...], tuple[tuple[str, ...], tuple[str, ...]]] = {}
    dahil: dict[tuple[str, ...], dict[str, None]] = {}
    for grup in ham.get("gruplar") or []:
        if isinstance(grup, dict):
            anahtarlar = _terim_listesi(grup.get("terimler"))
            hepsi = tuple(dict.fromkeys(anahtarlar + _terim_listesi(grup.get("karsiliklar"))))
            izinli = tuple(str(x) for x in grup.get("tipler") or [])
            haric = tuple(str(x) for x in grup.get("haric_tipler") or [])
            tip_dahil = grup.get("tip_dahil") or []
            eklenen = tuple(str(x) for x in ([tip_dahil] if isinstance(tip_dahil, str) else tip_dahil))
        else:
            anahtarlar = hepsi = _terim_listesi(grup)
            izinli = haric = eklenen = ()
        for terim in anahtarlar:
            sozluk.setdefault(terim, {}).update(dict.fromkeys(hepsi))
            if izinli or haric:
                tipler[terim] = (izinli, haric)
            if eklenen:
                dahil.setdefault(terim, {}).update(dict.fromkeys(eklenen))
    return {k: tuple(v) for k, v in sozluk.items()}, tipler, {k: tuple(v) for k, v in dahil.items()}


def esanlam_sozlugu() -> dict[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    """G3e madde 20: normalize edilmiş terim (kelime dizisi) -> grubun tüm terimleri. G3h: birden çok grupta geçen
    terim grupların birleşimine eşlenir."""
    return _esanlam_verisi()[0]


def esanlam_tipleri() -> dict[tuple[str, ...], tuple[tuple[str, ...], tuple[str, ...]]]:
    """G3k madde 4: terim -> (izinli ürün tipleri, dışlanan ürün tipleri) (yalnız tip kısıtlı gruplardaki terimler)."""
    return _esanlam_verisi()[1]


def _fts_terim(kelimeler: tuple[str, ...], onek: bool) -> str:
    return '"' + " ".join(kelimeler) + '"' + ("*" if onek else "")


@dataclass(frozen=True)
class AramaTerimi:
    """Sorgunun VE ile bağlanan bir parçası (G3h madde 2: tek başına arama bağlantısı için kelimeleri taşır)."""
    kelimeler: tuple[str, ...]     # normalize edilmiş kelimeler (eşanlamlı terim çok kelimeli olabilir)
    fts: str                       # FTS5 parçası
    katli: str | None              # G3h madde 1: harf+rakam karışık, en az 4 karakterlik kelime (alt dize araması)
    bas: int = 0                   # sorgudaki ilk kelimenin sırası
    son: int = 0                   # son kelimeden sonraki sıra
    # G3j madde 7: terimin yazımları (kelimeler, önek mi) — "tüm terimler adda" alaka katmanı
    secenekler: tuple[tuple[tuple[str, ...], bool], ...] = ()
    tipler: tuple[str, ...] = ()   # G3k madde 4: terimin eşleştiği ürünlerin izinli tipleri (boş: kısıt yok)
    haric_tipler: tuple[str, ...] = ()   # fix 1 I-1: terimin eşleştiği ürünlerde dışlanan tipler
    dahil_tipler: tuple[str, ...] = ()   # G3l madde 2: bu tiplerdeki tüm ürünler de terimle eşleşir


KATLI_EN_AZ = 4


def karisik_kod(x: str) -> bool:
    """Harf + rakam karışık ve en az 4 karakter (G3h madde 1)."""
    return len(x) >= KATLI_EN_AZ and any(c.isdigit() for c in x) and any(c.isalpha() for c in x)


_AYRACLI_KOD = re.compile(r"\w+(?:[-/]+\w+)+")
_KOD_KENAR = re.compile(r"^\W+|\W+$")


def ayracli_kod_mu(parca: str) -> bool:
    """G3l madde 4: boşluksuz, tire / eğik çizgiyle ayrılmış jeton ("LR-D-MINI", "3HAC026289-001", "6EP1961-2BA11") tek
    kod jetonudur: rakam içerir ya da bir parçası en çok 3 karakterdir (düz bileşik sözcükler, "servo-motor", bölünür)."""
    if not _AYRACLI_KOD.fullmatch(parca):
        return False
    # fix 1 C-1: katlanmış biçimi 4 karakterden kısa jeton ("I/O", "G1/4", "R1/2", "A/B", "U/I") kod değildir, G3l
    # öncesi gibi bölünür. İstisna: yalnız tireyle ayrılmış harf + rakam kodu ("X-20" -> x20, B&R X20 ailesi)
    katli = kod_birlesik(parca)
    if len(katli) < KATLI_EN_AZ:
        tireli_kod = "/" not in parca and len(katli) == KATLI_EN_AZ - 1 and any(c.isdigit() for c in katli) \
            and any(c.isalpha() for c in katli)
        if not tireli_kod:
            return False
    return any(c.isdigit() for c in parca) or any(len(p) <= 3 for p in re.split(r"[-/]+", parca))


def sorgu_jetonlari(metin: str) -> list[str]:
    """Sorgunun kelimeleri (yazıldığı biçimde): boşlukla ayrılmış ayraçlı kod jetonu tek parça (G3l madde 4), diğerleri
    \\w+ kelimeleri. arama_terimleri ve gevşetme aynı bölmeyi kullanır (terim sıraları hizalı kalır)."""
    sonuc: list[str] = []
    for parca in metin.split():
        cekirdek = _KOD_KENAR.sub("", parca)
        if ayracli_kod_mu(cekirdek):
            sonuc.append(cekirdek)
        else:
            sonuc += _KELIME.findall(parca)
    return sonuc


def arama_terimleri(arama: str) -> list[AramaTerimi]:
    """Sorgu kelimeleri -> VE ile bağlanacak terimler. Sözlükteki terim (en uzun eşleşme önce) grubun terimleriyle
    VEYA'lanır; kullanıcının yazdığı biçim önekli kalır. G3l madde 4: ayraçlı kod jetonu katlanmış tek kelimedir
    ("LR-D-MINI" -> "lrdmini": "lrdmini" yazılmış gibi aranır, sonuç sayısı aynı)."""
    jetonlar = sorgu_jetonlari(normalize(arama))
    ayracli = {i for i, j in enumerate(jetonlar) if not _KELIME.fullmatch(j)}
    kelimeler = [kod_birlesik(j) if i in ayracli else j for i, j in enumerate(jetonlar)]
    sozluk, kisitlar, dahiller = _esanlam_verisi()
    terimler: list[AramaTerimi] = []
    i = 0
    while i < len(kelimeler):
        for uzunluk in range(min(ESANLAM_EN_UZUN, len(kelimeler) - i), 0, -1):
            terim = tuple(kelimeler[i:i + uzunluk])
            grup = sozluk.get(terim)
            if grup:
                yazimlar = ((terim, True),) + tuple((x, len(" ".join(x)) > KISA_TERIM) for x in grup if x != terim)
                secenekler = [_fts_terim(x, onek) for x, onek in yazimlar]
                # inceleme M-6: çok kelimeli terimin kelimeleri ayrı ayrı (VE) da eşleşir; bitişik ifade şart değil.
                # G3m madde 16: bu, grubun TÜM çok kelimeli terimleri için yapılır (yalnız yazılan için değil): bitişik
                # ("Servomotor") ve ayrık ("servo motor") yazım aynı sonuç kümesini verir
                for x, _ in yazimlar:
                    if len(x) > 1:
                        secenekler.append("(" + " AND ".join(_fts_terim((w,), len(w) > KISA_TERIM) for w in x) + ")")
                terimler.append(AramaTerimi(terim, "(" + " OR ".join(secenekler) + ")", None, i, i + uzunluk,
                                            yazimlar, *kisitlar.get(terim, ((), ())), dahiller.get(terim, ())))
                i += uzunluk
                break
        else:
            k = kelimeler[i]
            katli = kod_birlesik(k)
            # G3l madde 4: ayraçlı kod jetonu rakamsız/harfsiz olsa da katlanmış metinde aranır ("00-109-802" adda
            # "00 109 802")
            kod_mu = karisik_kod(katli) or i in ayracli     # fix 1 C-1: ayraçlı jeton artık en az 3 (X-20) / 4 karakter
            terimler.append(AramaTerimi((k,), _fts_terim((k,), True), katli if kod_mu else None, i, i + 1,
                                        (((k,), True),)))
            i += 1
    return terimler


_TR_SUTUNLAR = "{metin kod_birlesik kategori aciklama} : "
# G3h madde 3: bm25 sütun ağırlıkları (metin, kod_birlesik, ad_en, kategori, aciklama, urun_id): ad > kategori > açıklama
BM25 = "bm25(urun_ara, 10.0, 8.0, 10.0, 3.0, 1.0, 0.0)"


def _fts_ifadesi(parcalar: Sequence[str], en: bool, veya: bool = False) -> str:
    ifade = "(" + (" OR " if veya else " AND ").join(parcalar) + ")"
    return ifade if en else _TR_SUTUNLAR + ifade


def _arama_ifadesi(arama: str, en: bool = False, veya: bool = False) -> str | None:
    """FTS5 ifadesi. Her kelime tırnaklanıp prefix yapılır (operatörler/özel karakterler etkisiz), kelimeler VE ile
    (G3h madde 2 gevşetmede VEYA ile) bağlanır. G3a: sorgunun ayraçsız biçimi (rakam içeren, en az 4 karakter)
    kod_birlesik sütununda prefix olarak da aranır: "00109802" ↔ "00-109-802", "6ES7 307-1EA00" ↔ "6ES7307-1EA00-0AA0".
    G3e: eşanlamlı terimler (esanlam.yaml) grubun diğer terimleriyle VEYA'lanır. G3f: TR'de EN ad sütunu (ad_en)
    aranmaz, en=True ise tüm sütunlar aranır. G3h: kategori ve açıklama sütunları da aranır (alakada düşük ağırlık).
    Aranacak bir şey yoksa None."""
    parcalar = []
    terimler = arama_terimleri(arama)
    if terimler:
        parcalar.append(_fts_ifadesi([t.fts for t in terimler], en, veya))
    birlesik = kod_birlesik(arama)
    if len(birlesik) >= 4 and any(c.isdigit() for c in birlesik):
        parcalar.append(f'kod_birlesik : "{birlesik}"*')
    return " OR ".join(parcalar) or None


_FTS_IN = "u.id IN (SELECT urun_id FROM urun_ara WHERE urun_ara MATCH ?)"


def _arama_kosulu(arama: str, en: bool, veya: bool = False) -> tuple[str, list] | None:
    """Arama WHERE parçası. FTS eşleşmesine G3h madde 1'in katlanmış metin alt dize eşleşmesi eklenir: sorgunun tamamı
    ("KR C4" -> "krc4") ya da harf+rakam karışık en az 4 karakterlik bir kelimesi ("DSQC626") ürünün ayraçsız
    ad/SKU/üretici kodunda geçerse eşleşir (çok kelimede diğer kelimeler yine FTS ile, VE)."""
    ifade = _arama_ifadesi(arama, en=en, veya=veya)
    if not ifade:
        return None
    sql, param = [_FTS_IN], [ifade]
    birlesik = kod_birlesik(arama)
    terimler = arama_terimleri(arama)
    # G3l madde 4: tek ayraçlı kod. fix 1 M-1: rakamsız tek kelimelik sorgu (eşanlamsız, en az 4 harf: "lrdmini") da
    # katlanmış metinde kelime başından aranır; "LR-D-MINI" ile "lrdmini" aynı ürünleri bulur
    tek_kelime = (len(terimler) == 1 and len(terimler[0].kelimeler) == 1 and len(terimler[0].secenekler) == 1
                  and len(birlesik) >= KATLI_EN_AZ)
    if karisik_kod(birlesik) or (len(terimler) == 1 and terimler[0].katli) or tek_kelime:
        sql.append("u.katli_metin LIKE ?")
        param.append(f"%|{birlesik}%")
    katlilar = [t for t in terimler if t.katli]
    dahiller = [t for t in terimler if t.dahil_tipler]       # G3l madde 2: tip eşlemeli terim
    if (katlilar and len(terimler) > 1) or dahiller:
        if veya:
            for t in terimler:
                if t.katli and len(terimler) > 1:
                    sql.append("u.katli_metin LIKE ?")
                    param.append(f"%|{t.katli}%")
                if t.dahil_tipler:
                    sql.append(f"u.tip IN ({','.join('?' * len(t.dahil_tipler))})")
                    param += list(t.dahil_tipler)
        else:
            parcalar = []
            for t in terimler:
                tek_sql, tek_p = _terim_eslesmesi(t, en)
                parcalar.append(tek_sql)
                param += tek_p
            sql.append("(" + " AND ".join(parcalar) + ")")
    return "(" + " OR ".join(sql) + ")", param


def _terim_eslesmesi(t: AramaTerimi, en: bool) -> tuple[str, list]:
    """Terimin tek başına eşleştiği ürünler (FTS; kod terimi ayrıca katlanmış metinde; G3l madde 2: tip eşlemeli
    terimde o tipteki tüm ürünler)."""
    sql, param = [_FTS_IN], [_fts_ifadesi([t.fts], en)]
    if t.katli:
        sql.append("u.katli_metin LIKE ?")
        param.append(f"%|{t.katli}%")
    if t.dahil_tipler:
        sql.append(f"u.tip IN ({','.join('?' * len(t.dahil_tipler))})")
        param += list(t.dahil_tipler)
    return ("(" + " OR ".join(sql) + ")" if len(sql) > 1 else sql[0]), param


def _tip_uygun(t: AramaTerimi) -> tuple[str, list]:
    parcalar, param = [], []
    if t.tipler:
        parcalar.append(f"u.tip IN ({','.join('?' * len(t.tipler))})")
        param += list(t.tipler)
    if t.haric_tipler:
        parcalar.append(f"u.tip NOT IN ({','.join('?' * len(t.haric_tipler))})")
        param += list(t.haric_tipler)
    return "(" + " AND ".join(parcalar) + ")", param


def _tip_kisiti(arama: str, en: bool, veya: bool) -> tuple[str, list] | None:
    """G3k madde 4 (+ fix 1 I-1): tip kısıtlı eşanlamlı terim (ör. "Servoumrichter" -> yalnız sürücü; "Steuerung" ->
    pnömatik/valf/sensör/kablo değil). Kısıt yalnız O TERİMLE eşleşen ürünlere uygulanır: VE aramada her ürün tüm
    terimlerle eşleştiği için tüm sonuca; gevşetmede (VEYA) yalnız kısıtlı terimle eşleşip başka hiçbir terimle
    eşleşmeyen ürünlere (diğer terimlerden gelen sonuçlar daralmaz)."""
    terimler = arama_terimleri(arama)
    kisitli = [t for t in terimler if t.tipler or t.haric_tipler]
    if not kisitli:
        return None
    parcalar, param = [], []
    for t in kisitli:
        uygun_sql, uygun_p = _tip_uygun(t)
        if not veya:
            parcalar.append(uygun_sql)
            param += uygun_p
            continue
        eslesme_sql, eslesme_p = _terim_eslesmesi(t, en)
        diger = [_terim_eslesmesi(x, en) for x in terimler if x is not t]
        sql = f"({uygun_sql} OR NOT {eslesme_sql}" + "".join(f" OR {d[0]}" for d in diger) + ")"
        parcalar.append(sql)
        param += uygun_p + eslesme_p + [p for d in diger for p in d[1]]
    return "(" + " AND ".join(parcalar) + ")", param


def _yol_kosulu(yol: str) -> tuple[str, list]:
    return "(k.yol = ? OR substr(k.yol, 1, ?) = ?)", [yol, len(yol) + 1, yol + "."]


def _alt_kategori_yollari(con: sqlite3.Connection, kimlikler: Sequence[int]) -> list[str]:
    gecerli = [i for i in dict.fromkeys(kimlikler) if isinstance(i, int) and 0 < i < 2**62][:100]
    if not gecerli:
        return []
    yer = ",".join("?" * len(gecerli))
    return [r[0] for r in con.execute(f"SELECT yol FROM kategori WHERE id IN ({yer}) ORDER BY yol", gecerli)]


@dataclass
class _Kosullar:
    taban: list[str]                         # her zaman: aktif, kategori, arama, fiyat aralığı
    param: list[object]
    faset: dict[str, tuple[str, list]]       # yalnız seçimi olan fasetler: ad -> (SQL, parametreler)
    alt_yollar: list[str]


def _kosullar(con: sqlite3.Connection, s: ListeSorgusu) -> _Kosullar | None:
    """Sorgunun WHERE parçaları; sonuç kesin boşsa (bilinmeyen kategori, aranacak kelime yok) None."""
    taban = ["u.aktif = 1"]
    param: list[object] = []
    if s.kategori_id is not None:
        k = kategori_getir(con, s.kategori_id)
        if k is None:
            return None
        sql, p = _yol_kosulu(k.yol)
        taban.append(sql)
        param += p
    if s.arama is not None and s.arama.strip():
        kosul = _arama_kosulu(s.arama, en=s.dil == "en", veya=s.veya)
        if kosul is None:
            return None
        taban.append(kosul[0])
        param += kosul[1]
        tip_kosulu = _tip_kisiti(s.arama, s.dil == "en", s.veya)
        if tip_kosulu is not None:
            taban.append(tip_kosulu[0])
            param += tip_kosulu[1]
    if s.fiyat_min is not None or s.fiyat_max is not None:
        taban.append(f"NOT {_TEKLIFLE}")            # G3a: fiyat aralığı teklifle satılanları dışlar
    # G3e düzeltme 1 (M-2): gösterimle aynı sıra: net = yuvarla(eur × kur), KDV = yuvarla(net × oran / 100), toplam.
    # Kayan nokta artığı için 0,001 tolerans (tutarlar 2 hanedir).
    net = f"ROUND({_FIYAT} * CAST(? AS REAL), 2)"
    gorunen = f"({net} + ROUND({net} * CAST(u.kdv_orani AS REAL) / 100.0, 2))" if s.fiyat_kdv_dahil else net
    adet = 2 if s.fiyat_kdv_dahil else 1
    if s.fiyat_min is not None:
        taban.append(f"{gorunen} >= CAST(? AS REAL) - 0.001")
        param += [str(s.fiyat_carpani)] * adet + [str(s.fiyat_min)]
    if s.fiyat_max is not None:
        taban.append(f"{gorunen} <= CAST(? AS REAL) + 0.001")
        param += [str(s.fiyat_carpani)] * adet + [str(s.fiyat_max)]

    faset: dict[str, tuple[str, list]] = {}
    markalar = list(dict.fromkeys(s.markalar))
    if markalar:
        faset["marka"] = (f"u.marka IN ({','.join('?' * len(markalar))})", markalar)
    durumlar = list(dict.fromkeys(s.durumlar))
    if durumlar:
        faset["durum"] = (f"u.durum_kodu IN ({','.join('?' * len(durumlar))})", durumlar)
    stok_secili = _stok_secili(s)
    if 0 < len(stok_secili) < len(STOK_SECENEKLERI):
        ayr = list(dict.fromkeys(s.ayrilmis_idler))
        yer = ",".join("?" * len(ayr))
        kosul = {"stokta": (f"(u.stok > 0 AND u.id NOT IN ({yer}))", ayr),
                 "ayrilmis": (f"(u.stok > 0 AND u.id IN ({yer}))", ayr),
                 "tedarikli": ("u.stok <= 0", [])}
        secilen = [kosul[d] for d in stok_secili]
        faset["stok"] = ("(" + " OR ".join(sql for sql, _ in secilen) + ")", [x for _, p in secilen for x in p])
    if s.fiyatli != s.teklifle:
        faset["fiyat"] = (f"NOT {_TEKLIFLE}" if s.fiyatli else _TEKLIFLE, [])
    tipler = list(dict.fromkeys(s.tipler))
    if tipler:
        faset["tip"] = (f"u.tip IN ({','.join('?' * len(tipler))})", tipler)
    alt_yollar = _alt_kategori_yollari(con, s.alt_kategoriler)
    if alt_yollar:
        parcalar = [_yol_kosulu(y) for y in alt_yollar]
        faset["kategori"] = ("(" + " OR ".join(sql for sql, _ in parcalar) + ")", [x for _, p in parcalar for x in p])
    return _Kosullar(taban, param, faset, alt_yollar)


STOK_SECENEKLERI = ("stokta", "ayrilmis", "tedarikli")


def _stok_secili(s: ListeSorgusu) -> list[str]:
    return [d for d in STOK_SECENEKLERI if getattr(s, d)]


def _where(k: _Kosullar) -> tuple[str, list]:
    kosullar, param = list(k.taban), list(k.param)
    for sql, p in k.faset.values():
        kosullar.append(sql)
        param += p
    return " WHERE " + " AND ".join(kosullar), param


def urun_sayisi(con: sqlite3.Connection, s: ListeSorgusu) -> int:
    """Yalnız eşleşen ürün sayısı (sıralama/sayfa/bm25 yok) — G3h inceleme I-1: gevşetmede terim sayıları."""
    k = _kosullar(con, s)
    if k is None:
        return 0
    where, param = _where(k)
    return con.execute(_SAYI_SQL + where, param).fetchone()[0]


def urun_listele(con: sqlite3.Connection, s: ListeSorgusu) -> ListeSonucu:
    k = _kosullar(con, s)
    if k is None:
        return _bos_sonuc()
    where, param = _where(k)
    toplam = con.execute(_SAYI_SQL + where, param).fetchone()[0]
    boy = max(1, min(SAYFA_BOYU_MAX, s.sayfa_boyu))
    sayfa_sayisi = max(1, (toplam + boy - 1) // boy)
    sayfa = min(max(1, s.sayfa), sayfa_sayisi)
    en = s.dil == "en"
    ad_sira = "COALESCE(u.sira_anahtari_en, u.sira_anahtari), u.id" if en else "u.sira_anahtari, u.id"
    ifade = _arama_ifadesi(s.arama, en=en, veya=s.veya) if s.arama and s.arama.strip() else None
    if s.siralama == "alaka" and ifade:
        kimlikler = _alaka_sirasi(con, s, where, param, ifade, en)[(sayfa - 1) * boy:sayfa * boy]
        if not kimlikler:
            return ListeSonucu(urunler=[], toplam=toplam, sayfa=sayfa, sayfa_sayisi=sayfa_sayisi)
        satirlar = {r["id"]: r for r in con.execute(
            _URUN_SQL + f" WHERE u.id IN ({','.join('?' * len(kimlikler))})", kimlikler)}
        return ListeSonucu(urunler=[_urun(satirlar[i]) for i in kimlikler], toplam=toplam, sayfa=sayfa,
                           sayfa_sayisi=sayfa_sayisi)
    sira_param: list = []
    if s.siralama in ("ad", "alaka"):
        sira = ad_sira                                   # G3f M-2: /en'de görünen EN ada göre
    elif s.siralama == "onerilen":
        ayr = list(dict.fromkeys(s.ayrilmis_idler))
        sira = ONERILEN_PUAN.format(ayrilmis=",".join("?" * len(ayr))) + f" DESC, {ad_sira}"
        sira_param = ayr
    else:
        sira = _SIRALAR.get(s.siralama, _SIRALAR["ad"])
    satirlar = con.execute(
        _URUN_SQL + where + f" ORDER BY {sira} LIMIT ? OFFSET ?", [*param, *sira_param, boy, (sayfa - 1) * boy],
    ).fetchall()
    return ListeSonucu(urunler=[_urun(r) for r in satirlar], toplam=toplam, sayfa=sayfa, sayfa_sayisi=sayfa_sayisi)


def _alaka_sirasi(con: sqlite3.Connection, s: ListeSorgusu, where: str, param: list, ifade: str, en: bool) -> list[int]:
    """Eşleşen tüm ürünlerin alaka sırası (kimlikler). G3a: SKU/üretici koduyla tam eşleşme > kod öneki; G3h madde 3:
    sorgunun tipiyle (tip.yaml) aynı tip > tam ifade ürün adında (inceleme M-1: ya da katlanmış kod adda/kodda kelime
    başından) > bm25 (ad > kategori > açıklama) > ad. İnceleme I-1: bm25 tek FTS sorgusuyla bir kez hesaplanır, sıralama
    Python'da yapılır (SQL'de bm25 alt sorgusuyla birleştirme satır başına yeniden tarıyordu: geniş VEYA aramada ~0,7 s)."""
    birlesik = kod_birlesik(s.arama)
    tip = sorgu_tipi(s.arama)
    ifade_adi = " " + " ".join(_KELIME.findall(normalize(s.arama)))
    katli = "|" + birlesik if karisik_kod(birlesik) else None
    skor = dict(con.execute(f"SELECT urun_id, {BM25} FROM urun_ara WHERE urun_ara MATCH ?", (ifade,)).fetchall())
    satirlar = con.execute(
        "SELECT u.id, u.kod_birlesik, u.sira_anahtari, u.sira_anahtari_en, u.tip, u.katli_metin, u.ad,"
        " u.kok_kategori_ad FROM urun u LEFT JOIN kategori k ON k.id = u.kategori_id" + where, param).fetchall()
    terimler = arama_terimleri(s.arama)
    # G3j madde 7: çok terimde her terimin (herhangi bir alanda) eşleştiği ürünler: VE'de hepsi, gevşetmede kısmi
    kumeler = [_terim_kumesi(con, t, en) for t in terimler] if len(terimler) > 1 else []
    kod_sorgusu = kod_sorgusu_mu(s.arama)
    model_sorgusu = robot_modeli_mu(s.arama)      # fix 1 m-2: "KR 210", "IRB 6700": robot arayan sorgu

    def anahtar(r) -> tuple:
        kodlar = (r[1] or "").split()
        kod = 0 if birlesik in kodlar else (1 if birlesik and any(x.startswith(birlesik) for x in kodlar) else 2)
        adlar = [" " + (r[2] or "")] + ([" " + r[3]] if en and r[3] else [])
        adda = any(ifade_adi in a for a in adlar) or bool(katli and katli in (r[5] or ""))
        kelime_listeleri = [_KELIME.findall(a) for a in adlar]
        tumu_adda = bool(terimler) and all(any(_terim_adda(t, k, r[5] or "") for k in kelime_listeleri)
                                           for t in terimler)
        eslesen = sum(r[0] in k for k in kumeler) if kumeler else len(terimler)
        # G3k madde 6: gevşetmede eşleşen terim sayısından sonra terimin nadirliği (en az ürün döndüren terim önce)
        nadir = min((len(k) for k in kumeler if r[0] in k), default=0)
        katman = 0 if tumu_adda else (1 if eslesen >= len(terimler) else 2)
        ad = (r[3] or r[2] or "") if en else (r[2] or "")
        # G3k madde 5: tek kod jetonlu sorguda tam robot ürünleri (tam kod eşleşmesi hariç) parçaların altında
        robot = 1 if kod_sorgusu and kod != 0 and tam_robot_mu(r[6], r[7], r[4]) else 0
        if model_sorgusu and kod != 0:              # robot model sorgusunda robotlar önce
            robot = 0 if tam_robot_mu(r[6], r[7], r[4]) else 1
        return (0 if kod == 0 else 1, robot, kod, katman, -eslesen, nadir, 0 if tip and r[4] == tip else 1,
                0 if adda else 1, skor.get(r[0], 0.0), ad, r[0])
    return [r[0] for r in sorted(satirlar, key=anahtar)]


KONTROLOR_KELIMELERI = ("kumanda", "kontrol", "kabin")   # G3k madde 5: adda geçerse robot değil kontrolör/kabin


def kod_sorgusu_mu(arama: str | None) -> bool:
    """G3k madde 5: sorgu tek bir kod jetonu mu ("KRC4", "KR C4", "IRC5"): katlanmış hali harf + rakam karışık ve her
    kelimesi ya rakam içerir ya da en çok 3 karakterdir (düz sözcük yok)."""
    kelimeler = _KELIME.findall(normalize(arama or ""))
    return bool(kelimeler) and karisik_kod(kod_birlesik(arama or "")) and all(
        any(c.isdigit() for c in w) or len(w) <= 3 for w in kelimeler)


ROBOT_AILELERI = ("kr", "irb", "mh", "gp", "lr")   # fix 1 m-2: robot ailesi sözcükleri (KUKA KR, ABB IRB, Motoman MH/GP)
_ROBOT_MODELI = re.compile(rf"(?:{'|'.join(ROBOT_AILELERI)})\d{{1,4}}")


def robot_modeli_mu(arama: str | None) -> bool:
    """fix 1 m-2: sorgu robot ailesi sözcüğü + yalnız rakamdan model jetonu mu ("KR 210", "KR210", "IRB 6700"). Kontrolör
    adları ("KR C4", "KRC4", "IRC5") model jetonu harf içerdiği için kapsam dışı (madde 5 kuralı aynen)."""
    return bool(_ROBOT_MODELI.fullmatch(kod_birlesik(arama or "")))


def tam_robot_mu(ad: str | None, kok_kategori_ad: str | None, tip: str | None) -> bool:
    """G3k madde 5: tam robot ürünü (robot kökü ya da robot tipi; kontrol ünitesi / parça kökü değil) ve adında
    kumanda/kontrol/kabin geçmeyen."""
    kok = normalize(kok_kategori_ad or "")
    if "kontrol" in kok or "parca" in kok:
        return False
    if not (("robot" in kok) or tip == "robot"):
        return False
    ad_n = normalize(ad or "")
    return not any(k in ad_n for k in KONTROLOR_KELIMELERI)


def _terim_kumesi(con: sqlite3.Connection, t: AramaTerimi, en: bool) -> set[int]:
    """Terimin herhangi bir aranan alanda (FTS) ya da katlanmış kodda eşleştiği ürünler."""
    kume = {r[0] for r in con.execute("SELECT urun_id FROM urun_ara WHERE urun_ara MATCH ?",
                                      (_fts_ifadesi([t.fts], en),))}
    if t.katli:
        kume |= {r[0] for r in con.execute("SELECT id FROM urun WHERE katli_metin LIKE ?", (f"%|{t.katli}%",))}
    if t.dahil_tipler:
        kume |= {r[0] for r in con.execute(
            f"SELECT id FROM urun WHERE tip IN ({','.join('?' * len(t.dahil_tipler))})", t.dahil_tipler)}
    return kume


def _terim_adda(t: AramaTerimi, kelimeler: Sequence[str], katli_metin: str) -> bool:
    """G3j madde 7: terim (ya da eşanlamlısı) ürün adında art arda kelimeler olarak geçiyor mu (son kelime önekse
    başlangıç eşleşmesi; FTS ile aynı kural). Kod terimi katlanmış metinde kelime başından."""
    if t.katli and "|" + t.katli in katli_metin:
        return True
    if len(t.kelimeler) > 1 and all(any(k.startswith(w) for k in kelimeler) for w in t.kelimeler):
        return True      # inceleme M-6: çok kelimeli terimin kelimeleri adda ayrı ayrı (FTS'teki VE biçimi)
    for yazim, onek in t.secenekler:
        n = len(yazim)
        for i in range(len(kelimeler) - n + 1):
            if all(kelimeler[i + j] == yazim[j] for j in range(n - 1)) and (
                    kelimeler[i + n - 1].startswith(yazim[-1]) if onek else kelimeler[i + n - 1] == yazim[-1]):
                return True
    return False


KOD_ESLESME_UST = 10


def ad_kod_jetonlari(ad: str | None) -> set[str]:
    """G3k madde 7: _ad_kod_jetonlari'nın dışa açık adı (arama rozeti: kod adda aynen görünüyor mu)."""
    return _ad_kod_jetonlari(ad)


def _ad_kod_jetonlari(ad: str | None) -> set[str]:
    """Adın boşlukla ayrılmış art arda jetonlarının katlanmış birleşimleri (G3j madde 1: adda tam kod eşleşmesi)."""
    jetonlar = [x for x in (kod_birlesik(p) for p in (ad or "").split()) if x]
    sonuc: set[str] = set()
    for i in range(len(jetonlar)):
        birlesim = ""
        for j in range(i, len(jetonlar)):
            birlesim += jetonlar[j]
            if len(birlesim) > KATLI_PENCERE:
                break
            sonuc.add(birlesim)
    return sonuc


def _ad_kodu_olabilir(k: str) -> bool:
    return len(k) >= KATLI_EN_AZ and any(c.isdigit() for c in k)


def kod_eslesmeleri(con: sqlite3.Connection, kod: str) -> list[Urun]:
    """G3j madde 1: parça kodunun (katlanmış: büyük/küçük harf ve ayraç farkı yok) katalogda TAM eşleştiği aktif ürünler:
    önce SKU ya da üretici kodu, sonra ürün adındaki kod (art arda boşlukla ayrılmış jetonların katlanmış birleşimi
    koda eşit: "KPP 600 20" ↔ adda "KPP-600-20"; "KPP-600" eşleşmez). Ad eşleşmesi yalnız rakam içeren, en az 4
    karakterlik kodda. En çok KOD_ESLESME_UST ürün. İnceleme M-4: ad adayları (kelime başından önek) sınırsız taranır;
    döngü KOD_ESLESME_UST tam eşleşmede durur."""
    k = kod_birlesik(kod)
    if len(k) < 3:
        return []
    tam = [_urun(r) for r in con.execute(
        _URUN_SQL + " WHERE u.aktif = 1 AND instr(' ' || u.kod_birlesik || ' ', ?) > 0 ORDER BY u.id LIMIT ?",
        (f" {k} ", KOD_ESLESME_UST))]
    sonuc = {u.id: u for u in tam}
    if _ad_kodu_olabilir(k):
        for r in con.execute(_URUN_SQL + " WHERE u.aktif = 1 AND u.katli_metin LIKE ? ORDER BY u.id", (f"%|{k}%",)):
            if len(sonuc) >= KOD_ESLESME_UST:
                break
            if k in _ad_kod_jetonlari(r["ad"]):
                sonuc.setdefault(r["id"], _urun(r))
    return list(sonuc.values())


def kod_eslesmeleri_toplu(con: sqlite3.Connection, kodlar) -> dict[str, list[int]]:
    """İnceleme M-3: kod_eslesmeleri ile aynı kural, birçok kod için TEK geçişte (yönetim teklif listesi): kod -> eşleşen
    aktif ürün kimlikleri (SKU/üretici kodu önce, sonra ad; en çok KOD_ESLESME_UST)."""
    hedef = {kod: kod_birlesik(kod) for kod in dict.fromkeys(kodlar)}
    gecerli = {k for k in hedef.values() if len(k) >= 3}
    ad_kodlari = {k for k in gecerli if _ad_kodu_olabilir(k)}
    tam: dict[str, list[int]] = {}
    adda: dict[str, list[int]] = {}
    if gecerli:
        for r in con.execute("SELECT id, kod_birlesik, ad, katli_metin FROM urun WHERE aktif = 1 ORDER BY id"):
            for x in set((r[1] or "").split()) & gecerli:
                tam.setdefault(x, []).append(r[0])
            if ad_kodlari and any("|" + k in (r[3] or "") for k in ad_kodlari):
                for x in _ad_kod_jetonlari(r[2]) & ad_kodlari:
                    adda.setdefault(x, []).append(r[0])
    sonuc = {}
    for kod, k in hedef.items():
        ilk = tam.get(k, [])
        sonuc[kod] = (ilk + [i for i in adda.get(k, []) if i not in ilk])[:KOD_ESLESME_UST]
    return sonuc


YAKIN_KOD_EN_KISA = 5   # G3l madde 3: ortak önek en az 5 karakter
YAKIN_KOD_UST = 5


def _ortak_onek(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def yakin_kodlar(con: sqlite3.Connection, birlesik: str, adet: int = YAKIN_KOD_UST) -> list[tuple[Urun, str | None]]:
    """G3l madde 3: katlanmış kodla ortak öneki (en az YAKIN_KOD_EN_KISA karakter) paylaşan aktif ürünler, en çok `adet`.
    G3m madde 17: önce en uzun önek düzeyi ("6es7214" -> "6es721…"); liste dolmazsa önek kısaldıkça ("6es72…") doldurulur
    (5 karakter alt sınırı korunur). Aynı düzeyde ada göre. Önek ürünün katlanmış ad/SKU/üretici kodu kelime başlarında
    aranır. (ürün, öneki taşıyan parça kodu ya da None)."""
    if len(birlesik) < YAKIN_KOD_EN_KISA:
        return []
    adaylar = con.execute(_URUN_SQL + " WHERE u.aktif = 1 AND u.katli_metin LIKE ?",
                          (f"%|{birlesik[:YAKIN_KOD_EN_KISA]}%",)).fetchall()
    uzunluk = {r["id"]: max(_ortak_onek(birlesik, p) for p in (r["katli_metin"] or "").split("|") if p)
               for r in adaylar}
    if not uzunluk:
        return []
    secilen = sorted((r for r in adaylar if uzunluk[r["id"]] >= YAKIN_KOD_EN_KISA),
                     key=lambda r: (-uzunluk[r["id"]], r["sira_anahtari"] or "", r["id"]))
    sonuc = []
    for r in secilen[:adet]:
        n = uzunluk[r["id"]]
        kod = next((k for k in (r["uretici_kodu"], r["sku"]) if k and kod_birlesik(k)[:n] == birlesik[:n]), None)
        sonuc.append((_urun(r), kod))
    return sonuc


def ayni_parca_nolu(con: sqlite3.Connection, urun: Urun) -> list[Urun]:
    """G3j madde 17: aynı üretici koduna (büyük/küçük harf ve baş/son boşluk farkı yok) sahip DİĞER aktif ürünler."""
    kod = (urun.uretici_kodu or "").strip()
    if not kod:
        return []
    return [_urun(r) for r in con.execute(
        _URUN_SQL + " WHERE u.aktif = 1 AND u.id != ? AND upper(trim(u.uretici_kodu)) = upper(?) ORDER BY u.id LIMIT 20",
        (urun.id, kod))]


def kategori_sayilari(con: sqlite3.Connection, s: ListeSorgusu) -> dict[int, int]:
    """G3h madde 4: arama/filtre etkinken kategori ağacı sayıları. Sayfanın kategorisi ve kategori faseti hariç tüm
    koşullarla (arama + diğer fasetler + fiyat aralığı) kategori başına doğrudan ürün sayısı: ağaçtaki bağlantı aynı
    koşullarla o kategoriye gider, sayı oradaki sonuç sayısıdır."""
    k = _kosullar(con, replace(s, kategori_id=None, alt_kategoriler=()))
    if k is None:
        return {}
    where, param = _where(k)
    return {r[0]: r[1] for r in con.execute(
        "SELECT u.kategori_id, COUNT(*) FROM urun u LEFT JOIN kategori k ON k.id = u.kategori_id" + where
        + " AND u.kategori_id IS NOT NULL GROUP BY u.kategori_id", param)}


def suzulmus_agac(agac: Sequence[KategoriDugum], sayilar: dict[int, int]) -> list[KategoriDugum]:
    """Ağacın kopyası; ürün sayıları verilen doğrudan sayılardan (alt kategoriler dahil) yeniden toplanır.
    Paylaşılan (önbellekli) ağaç değiştirilmez."""
    def kopya(d: KategoriDugum) -> KategoriDugum:
        cocuklar = [kopya(c) for c in d.cocuklar]
        return KategoriDugum(kategori=d.kategori, cocuklar=cocuklar,
                             urun_sayisi=sayilar.get(d.kategori.id, 0) + sum(c.urun_sayisi for c in cocuklar))
    return [kopya(d) for d in agac]


def _kategori_degeri(yol: str | None, secenek_yollari: dict[str, str], onbellek: dict) -> str | None:
    """Ürünün kategori yolu hangi seçenek kategorisinin alt ağacında (yoksa None)."""
    if yol is None:
        return None
    if yol not in onbellek:
        parcalar = yol.split(".")
        onekler = (".".join(parcalar[:i]) for i in range(1, len(parcalar) + 1))
        onbellek[yol] = next((secenek_yollari[o] for o in onekler if o in secenek_yollari), None)
    return onbellek[yol]


def _secenekler(sayac: Counter, secili: Sequence[str], sira: Sequence[str] | None = None) -> tuple[Secenek, ...]:
    """Sayısı 0 olan seçenek gizlenir; seçili olan (kaldırılabilsin diye) her zaman görünür.
    sira yoksa: çok ürünlü önce, eşitse ada göre."""
    degerler = [d for d in dict.fromkeys([*sayac, *secili]) if d is not None]
    if sira is None:
        degerler.sort(key=lambda d: (-sayac.get(d, 0), normalize(d), d))
    else:
        konum = {d: i for i, d in enumerate(sira)}
        degerler.sort(key=lambda d: (konum.get(d, len(sira)), d == "belirtilmemis", d))
    return tuple(Secenek(d, sayac.get(d, 0), d in secili) for d in degerler if sayac.get(d, 0) > 0 or d in secili)


def faset_sayilari(con: sqlite3.Connection, s: ListeSorgusu, kategori_secenekleri: Sequence[Kategori]) -> Fasetler:
    """Sayımlı fasetler (G3a). Her fasetin sayıları o fasetin kendi seçimi hariç tüm koşullarla hesaplanır (ayrık
    sayım): aynı fasette ikinci bir seçenek eklemenin kaç sonuç vereceği görünür. Tek taban sorgusu (eşleşen
    ürünlerin faset alanları) + Python'da sayım. kategori_secenekleri: kategori fasetinde gösterilecek kategoriler
    (genelde geçerli kategorinin çocukları)."""
    k = _kosullar(con, s)
    if k is None:
        return Fasetler()
    satirlar = con.execute(
        f"SELECT u.marka, u.durum_kodu, u.stok > 0, {_TEKLIFLE}, k.yol, u.tip, u.id"
        " FROM urun u LEFT JOIN kategori k ON k.id = u.kategori_id WHERE " + " AND ".join(k.taban),
        k.param,
    ).fetchall()
    ayrilmis = set(s.ayrilmis_idler)
    stok_secili = set(_stok_secili(s))

    def stok_degeri(r) -> str:      # G3j madde 5: alınabilir stok
        return "tedarikli" if not r[2] else ("ayrilmis" if r[6] in ayrilmis else "stokta")
    secenek_yollari = {kat.yol: str(kat.id) for kat in kategori_secenekleri}
    alt_yollar = k.alt_yollar
    yol_onbellek: dict = {}
    markalar, durumlar, tipler = set(s.markalar), set(s.durumlar), set(s.tipler)

    def kategoride(yol: str | None) -> bool:
        return yol is not None and any(yol == y or yol.startswith(y + ".") for y in alt_yollar)

    testler = {
        "marka": lambda r: r[0] in markalar,
        "durum": lambda r: r[1] in durumlar,
        "stok": lambda r: stok_degeri(r) in stok_secili,
        "fiyat": lambda r: (not r[3]) == s.fiyatli,
        "kategori": lambda r: kategoride(r[4]),
        "tip": lambda r: r[5] in tipler,
    }
    etkin = [(ad, testler[ad]) for ad in FASETLER if ad in k.faset]
    sayaclar = {ad: Counter() for ad in FASETLER}
    toplam = 0
    for r in satirlar:
        eleyen = [ad for ad, f in etkin if not f(r)]
        if len(eleyen) > 1:
            continue
        if not eleyen:
            toplam += 1
        for ad in eleyen or FASETLER:      # tek faset eliyorsa satır yalnız o fasetin sayısına girer
            if ad == "marka":
                sayaclar[ad][r[0]] += 1
            elif ad == "durum":
                sayaclar[ad][r[1]] += 1
            elif ad == "stok":
                sayaclar[ad][stok_degeri(r)] += 1
            elif ad == "fiyat":
                sayaclar[ad]["teklifle" if r[3] else "fiyatli"] += 1
            elif ad == "tip":
                sayaclar[ad][r[5]] += 1
            else:
                sayaclar[ad][_kategori_degeri(r[4], secenek_yollari, yol_onbellek)] += 1
    sayaclar["marka"].pop(None, None)
    sayaclar["kategori"].pop(None, None)
    fiyat_secili = [d for d, b in (("fiyatli", s.fiyatli), ("teklifle", s.teklifle)) if b]
    kat_kimlikleri = [str(kat.id) for kat in kategori_secenekleri]
    kat_secili = [str(i) for i in dict.fromkeys(s.alt_kategoriler) if str(i) in kat_kimlikleri]
    return Fasetler(
        marka=_secenekler(sayaclar["marka"], list(dict.fromkeys(s.markalar))),
        durum=_secenekler(sayaclar["durum"], list(dict.fromkeys(s.durumlar)), DURUM_SIRASI),
        stok=_secenekler(sayaclar["stok"], _stok_secili(s), STOK_SECENEKLERI),
        fiyat=_secenekler(sayaclar["fiyat"], fiyat_secili, ("fiyatli", "teklifle")),
        kategori=_secenekler(sayaclar["kategori"], kat_secili, kat_kimlikleri),
        tip=_diger_sonda(_secenekler(sayaclar["tip"], list(dict.fromkeys(s.tipler)))),
        toplam=toplam,
    )


def _diger_sonda(secenekler: tuple[Secenek, ...]) -> tuple[Secenek, ...]:
    """Tip faseti: çok ürünlüden aza, "diger" her zaman sonda."""
    return tuple(x for x in secenekler if x.deger != "diger") + tuple(x for x in secenekler if x.deger == "diger")


def one_cikanlar(con: sqlite3.Connection, adet: int = 8) -> list[Urun]:
    satirlar = con.execute(
        _URUN_SQL
        + " WHERE u.aktif = 1 ORDER BY (u.gorsel_url IS NULL OR u.gorsel_url = ''), u.id LIMIT ?",
        (max(0, adet),),
    ).fetchall()
    return [_urun(r) for r in satirlar]


@dataclass(frozen=True)
class UrunAciklama:
    metin: str
    kaynak: str            # 'llm-taslak' | 'kaynak'
    model: str | None
    uretildi: str

    @property
    def taslak(self) -> bool:
        return self.kaynak == "llm-taslak"


def aciklama_getir(con: sqlite3.Connection, urun_id: int, dil: str) -> UrunAciklama | None:
    """urun_aciklama tablosundan ürünün o dildeki açıklaması (eşitleme bu tabloya dokunmaz)."""
    r = con.execute(
        "SELECT metin, kaynak, model, uretildi FROM urun_aciklama WHERE urun_id = ? AND dil = ?",
        (urun_id, dil),
    ).fetchone()
    if r is None or not (r["metin"] or "").strip():
        return None
    return UrunAciklama(metin=r["metin"].strip(), kaynak=r["kaynak"], model=r["model"], uretildi=r["uretildi"])


@dataclass(frozen=True)
class UrunTeknik:
    """G3b: eşitlemenin urun_teknik'e yazdığı güvenli düz metin (app/esitleme/teknik.py)."""
    ozellikler: tuple[tuple[str, str], ...]
    bolumler: tuple[tuple[str, str], ...]


def _ciftler(x: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(x, list):
        return ()
    return tuple((a, b) for a, b in (p for p in x if isinstance(p, list) and len(p) == 2)
                 if isinstance(a, str) and isinstance(b, str))


def teknik_getir(con: sqlite3.Connection, urun_id: int) -> UrunTeknik | None:
    r = con.execute("SELECT veri FROM urun_teknik WHERE urun_id = ?", (urun_id,)).fetchone()
    if r is None:
        return None
    try:
        veri = json.loads(r[0])
    except (ValueError, TypeError):
        return None
    if not isinstance(veri, dict):
        return None
    t = UrunTeknik(ozellikler=_ciftler(veri.get("ozellikler")), bolumler=_ciftler(veri.get("bolumler")))
    return t if t.ozellikler or t.bolumler else None


def gercek_durumlar(con: sqlite3.Connection, kategori_id: int) -> list[str]:
    """G3b I-6: kategori (alt ağaç dahil) aktif ürünlerinin GERÇEK durum kodları (örnek durumlar ve 'belirtilmemis'
    hariç), çok ürünlüden aza. SEO meta'sı için; faset sayımı örnekleri de gösterir, meta göstermez."""
    k = kategori_getir(con, kategori_id)
    if k is None:
        return []
    sql, p = _yol_kosulu(k.yol)
    return [r[0] for r in con.execute(
        "SELECT u.durum_kodu, COUNT(*) AS n FROM urun u JOIN kategori k ON k.id = u.kategori_id"
        f" WHERE u.aktif = 1 AND u.durum_ornek = 0 AND u.durum_kodu != 'belirtilmemis' AND {sql}"
        " GROUP BY u.durum_kodu ORDER BY n DESC, u.durum_kodu", p)]
