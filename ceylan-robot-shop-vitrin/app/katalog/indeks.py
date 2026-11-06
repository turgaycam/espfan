"""Ürün arama indeksi (FTS5 tablosu urun_ara) ve türetilmiş ürün alanları — tek yerden metin üretimi ve yeniden kurulum.

Türetilmiş alanlar (geçiş 004) istek sırasında hesaplanmaz; eşitleme her turda `indeksi_yeniden_kur` ile yeniler:
- sira_anahtari: Türkçe katlanmış ad (ada göre sıralama, indeksli)
- kod_birlesik: SKU ve üretici kodunun ayraçsız biçimleri, boşlukla ayrılmış ("00-109-802" -> "00109802")
- marka: bilinen üretici markası (app/katalog/marka.py) ya da None
G3f: urun_ara.ad_en sütunu geçerli EN ürün adını (urun_ceviri, app/katalog/urun_ceviri.py) taşır; yalnız /en aramasında
eşleşir. Yükleme betiği yazdığı ürünlerde ad_en_guncelle ile, eşitleme her turda indeksi_yeniden_kur ile yeniler
(bayat çeviri indeksten düşer).
G3h (geçiş 013): katli_metin (ad, SKU, üretici kodu, kategori; kelime başından ayraçsız pencereler; bitişik kod
araması: "DSQC626" ↔ "DSQC 626 A") ve tip
(app/katalog/tip.py) türetilmiş alanları; urun_ara'ya kategori (yaprak kategori adı) ve aciklama (TR açıklama) sütunları.
Eşitleme urun_aciklama/urun_ceviri'ye yazmaz, yalnız okur.
"""
import re
import sqlite3

from app.katalog.marka import marka_cikar
from app.katalog.tip import tip_bul
from app.katalog.urun_ceviri import ceviriler_getir
from app.metin import en_ad_duzelt, normalize

_AYRAC = re.compile(r"[\W_]+")


def indeks_metni(ad: str, sku: str, uretici_kodu: str | None) -> str:
    return normalize(f"{ad} {sku} {uretici_kodu or ''}")


def kod_birlesik(kod: str | None) -> str:
    """Parça kodunun ayraçsız biçimi: tire, boşluk, nokta, eğik çizgi (ve diğer harf/rakam dışı karakterler) atılır;
    Türkçe katlanmış küçük harf; baştaki sıfırlar korunur."""
    return _AYRAC.sub("", normalize(kod or ""))


def sira_anahtari(ad: str | None) -> str:
    return normalize(ad or "")


KATLI_PENCERE = 40     # kelime başından itibaren saklanan katlanmış metin (en uzun aranabilir bitişik kod)


def katli_metin(ad: str | None, sku: str | None, uretici_kodu: str | None, kategori: str | None = None) -> str:
    """G3h madde 1: ad, SKU, üretici kodu ve yaprak kategori adının ayraçsız biçimleri, HER KELİME BAŞINDAN başlayan
    pencereler olarak ("|" ile ayrık): "KUKA KR C4" -> "|kukakrc4|krc4|c4". Arama `LIKE '%|krc4%'` ile yalnız kelime
    başından eşleşir (inceleme M-1: "la12" "TABLA 12" içinde bulunmaz). Açıklama girmez (uzun metinde yanlış pozitif)."""
    parcalar: list[str] = []
    for alan in (ad, sku, uretici_kodu, kategori):
        kelimeler = [k for k in _AYRAC.split(normalize(alan or "")) if k]
        parcalar += ["".join(kelimeler[i:])[:KATLI_PENCERE] for i in range(len(kelimeler))]
    return "|" + "|".join(parcalar) if parcalar else ""


def turetilmis_alanlar(ad: str, sku: str, uretici_kodu: str | None, kategori_adlari: tuple[str, ...] = ()) -> dict:
    """kategori_adlari: ürünün kategori yolu, yapraktan köke (tip için; boşsa tip yalnız addan)."""
    kodlar = dict.fromkeys(k for k in (kod_birlesik(sku), kod_birlesik(uretici_kodu)) if k)
    return {"sira_anahtari": sira_anahtari(ad), "kod_birlesik": " ".join(kodlar), "marka": marka_cikar(ad),
            "katli_metin": katli_metin(ad, sku, uretici_kodu, kategori_adlari[0] if kategori_adlari else None),
            "tip": tip_bul(ad, kategori_adlari)}


def kategori_zincirleri(con: sqlite3.Connection) -> dict[str, tuple[str, ...]]:
    """Kategori yolu -> adlar (yapraktan köke). Kaynakta üst kategori yoksa zincir kısalır."""
    adlar = {r[0]: r[1] for r in con.execute("SELECT yol, ad FROM kategori")}
    zincir: dict[str, tuple[str, ...]] = {}
    for yol in adlar:
        parcalar = yol.split(".")
        zincir[yol] = tuple(adlar[o] for o in (".".join(parcalar[:i]) for i in range(len(parcalar), 0, -1))
                            if o in adlar)
    return zincir


_TURETILMIS = ("sira_anahtari", "kod_birlesik", "marka", "katli_metin", "tip", "teknik_var")
_TEKNIK_VAR_SQL = ("SELECT urun_id FROM urun_teknik WHERE CASE WHEN json_valid(veri)"
                   " THEN json_array_length(veri, '$.ozellikler') ELSE 0 END > 0")


def turetilmisleri_doldur(con: sqlite3.Connection) -> int:
    """Tüm ürünlerin türetilmiş alanlarını yeniden hesaplar (değişenleri yazar). Commit etmez."""
    zincir = kategori_zincirleri(con)
    teknikli = {r[0] for r in con.execute(_TEKNIK_VAR_SQL)}
    satirlar = con.execute(
        "SELECT u.id, u.ad, u.sku, u.uretici_kodu, k.yol, " + ", ".join(f"u.{a}" for a in _TURETILMIS)
        + " FROM urun u LEFT JOIN kategori k ON k.id = u.kategori_id").fetchall()
    degisen = []
    for r in satirlar:
        t = turetilmis_alanlar(r[1], r[2], r[3], zincir.get(r[4], ()) if r[4] else ())
        t["teknik_var"] = int(r[0] in teknikli)
        yeni = tuple(t[a] for a in _TURETILMIS)
        if yeni != tuple(r[5:]):
            degisen.append((*yeni, r[0]))
    con.executemany("UPDATE urun SET " + ", ".join(f"{a} = ?" for a in _TURETILMIS) + " WHERE id = ?", degisen)
    return len(degisen)


def ad_en_metni(ad_en: str | None) -> str | None:
    """G3n madde 14: EN dizin metni gösterimle aynı düzeltilmiş addan ("EVOLUTİON" -> "evolution")."""
    return normalize(en_ad_duzelt(ad_en)) if ad_en and ad_en.strip() else None


def ad_en_guncelle(con: sqlite3.Connection, urun_id: int, ad_en: str | None) -> None:
    """Ürünün arama satırındaki EN adı (aktif değilse satır yoktur) ve EN sıralama anahtarı. Commit etmez."""
    con.execute("UPDATE urun_ara SET ad_en = ? WHERE urun_id = ?", (ad_en_metni(ad_en), urun_id))
    con.execute("UPDATE urun SET sira_anahtari_en = COALESCE(?, sira_anahtari) WHERE id = ?",
                (sira_anahtari(ad_en) if ad_en and ad_en.strip() else None, urun_id))


def indeksi_yeniden_kur(con: sqlite3.Connection) -> None:
    """Türetilmiş alanları yeniler ve urun_ara'yı aktif ürünlerden baştan kurar (G3f: geçerli EN ad dahil).
    Commit etmez; çağıranın transaction'ında çalışır."""
    turetilmisleri_doldur(con)
    con.execute("DELETE FROM urun_ara")
    satirlar = con.execute(
        "SELECT u.id, u.ad, u.sku, u.uretici_kodu, u.kod_birlesik, k.ad, a.metin FROM urun u"
        " LEFT JOIN kategori k ON k.id = u.kategori_id"
        " LEFT JOIN urun_aciklama a ON a.urun_id = u.id AND a.dil = 'tr' WHERE u.aktif=1").fetchall()
    en = {i: c.ad for i, c in ceviriler_getir(con, None, teknik=False).items()}
    con.execute("UPDATE urun SET sira_anahtari_en = sira_anahtari")      # M-2: çevirisizde TR anahtarı
    con.executemany("UPDATE urun SET sira_anahtari_en = ? WHERE id = ?",
                    [(sira_anahtari(ad), i) for i, ad in en.items()])
    con.executemany(
        "INSERT INTO urun_ara (metin, kod_birlesik, ad_en, kategori, aciklama, urun_id) VALUES (?, ?, ?, ?, ?, ?)",
        ((indeks_metni(r[1], r[2], r[3]), r[4], ad_en_metni(en.get(int(r[0]))), normalize(r[5] or ""),
          normalize(r[6] or ""), int(r[0])) for r in satirlar),
    )
