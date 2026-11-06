"""G3b: API `techSpecs` / `descriptionSections` -> güvenli düz metin (eşitlemede) ve ürün durumu çıkarımı.

Kaynak alanlar serbest biçimlidir (rakip/ceylanrobot-rapor.md): techSpecs [{label, value}], descriptionSections
[{title, content}]; içerik HTML ya da gömülü base64 görsel taşıyabilir. Burada:
- HTML etiketleri atılır (script/style içerikleriyle), tablo hücreleri "anahtar: değer" satırına, blok etiketleri satır
  sonuna çevrilir; HTML varlıkları çözülür. Sonuç DÜZ METİNDİR; şablon yine kaçışlı basar.
- data: URI'leri ve uzun base64 dizileri atılır; denetim karakterleri silinir.
- Ürün başına saklanan JSON en çok EN_COK_BAYT (8 KB) olur: sığmayan özellik/bölüm atılır, son bölüm kısaltılır.
Durum çıkarımı yalnız açık kalıplarla yapılır; çelişkili ya da belirsiz metinde None döner (eşitleme önceki değeri korur).
"""
from __future__ import annotations

import html
import json
import re
from collections.abc import Iterable

from app.metin import metin_temizle, normalize

EN_COK_BAYT = 8 * 1024
ETIKET_SINIRI = 120
DEGER_SINIRI = 500
BOLUM_BASLIK_SINIRI = 120
BOLUM_METIN_SINIRI = 4000
EN_COK_OZELLIK = 60
EN_COK_BOLUM = 10
_HAM_SINIR = 1_000_000          # tek alanda işlenecek en çok karakter (gömülü görsel MB'larca olabilir)

# Doğrusal kalıplar: etiket içi [^<>] (kapanmayan çok sayıda "<" karesel zamana düşmesin); base64 satır kırılımlı olabilir
_DATA_URI = re.compile(r"data:[\w.+-]+/[\w.+-]+(?:;[\w=.+-]+)*;base64,[A-Za-z0-9+/=\r\n]*", re.IGNORECASE)
_SCRIPT_STYLE = re.compile(r"<(script|style)\b[^<>]*>.*?(?:</\1\s*>|$)", re.IGNORECASE | re.DOTALL)
_YORUM = re.compile(r"<!--.*?(?:-->|$)", re.DOTALL)
_IMG = re.compile(r"<img\b[^<>]*>?", re.IGNORECASE)
_HUCRE_ARASI = re.compile(r"</t[dh]\s*>\s*<t[dh]\b[^>]*>", re.IGNORECASE)
_SATIR_SONU = re.compile(r"<br\s*/?>|</(?:p|div|li|tr|h[1-6]|ul|ol|table|section|article)\s*>", re.IGNORECASE)
_MADDE = re.compile(r"<li\b[^>]*>", re.IGNORECASE)
_ETIKET = re.compile(r"<[^<>]*>|<[a-zA-Z/!][^<>]*$")
_BASE64_DIZI = re.compile(r"[A-Za-z0-9+/]{120,}={0,2}|(?:[A-Za-z0-9+/]{60,}={0,2}[ \t]*(?:\r?\n|$)){2,}")
_DENETIM = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def duz_metin(x: object, sinir: int) -> str | None:
    """Serbest biçimli API metnini güvenli düz metne çevirir; boş/metin dışıysa None."""
    if not isinstance(x, str):
        return None
    s = x[:_HAM_SINIR]
    s = _DATA_URI.sub(" ", s)
    s = _SCRIPT_STYLE.sub(" ", s)
    s = _YORUM.sub(" ", s)
    s = _IMG.sub(" ", s)
    s = _HUCRE_ARASI.sub(": ", s)
    s = _SATIR_SONU.sub("\n", s)
    s = _MADDE.sub("\n- ", s)
    s = _ETIKET.sub(" ", s)
    s = html.unescape(s)
    s = _BASE64_DIZI.sub(" ", s)
    s = metin_temizle(s) or ""
    s = _DENETIM.sub("", s.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " "))
    satirlar = [" ".join(satir.split()) for satir in s.split("\n")]
    s = "\n".join(satir for satir in satirlar if satir)
    if not s:
        return None
    if len(s) > sinir:
        s = s[: sinir - 1].rstrip() + "…"
    return s


def _tek_satir(x: object, sinir: int) -> str | None:
    s = duz_metin(x, sinir)
    return " ".join(s.split()) if s else None


def _liste(x: object) -> list:
    return x if isinstance(x, list) else []


def bolum_metinleri(kayit: dict) -> list[tuple[str, str]]:
    """descriptionSections -> [(başlık, metin)] (temizlenmiş, ad tekrarı atılmamış)."""
    sonuc = []
    for b in _liste(kayit.get("descriptionSections"))[:EN_COK_BOLUM * 3]:
        if not isinstance(b, dict):
            continue
        metin = duz_metin(b.get("content"), BOLUM_METIN_SINIRI)
        if metin:
            sonuc.append((_tek_satir(b.get("title"), BOLUM_BASLIK_SINIRI) or "", metin))
    return sonuc


def teknik_json(veri: dict) -> str:
    """Saklama biçimi (urun_teknik.veri)."""
    return json.dumps(veri, ensure_ascii=False, separators=(",", ":"))


def _bayt(veri: dict) -> int:
    return len(teknik_json(veri).encode("utf-8"))


def teknik_cikar(kayit: dict, ad: str) -> dict | None:
    """{"ozellikler": [[etiket, değer], ...], "bolumler": [[başlık, metin], ...]} ya da hiçbir şey yoksa None.
    JSON (ensure_ascii=False, sıkı ayraç) en çok EN_COK_BAYT bayt."""
    veri: dict = {"ozellikler": [], "bolumler": []}
    for o in _liste(kayit.get("techSpecs"))[:EN_COK_OZELLIK * 3]:
        if len(veri["ozellikler"]) >= EN_COK_OZELLIK:
            break
        if not isinstance(o, dict):
            continue
        etiket, deger = _tek_satir(o.get("label"), ETIKET_SINIRI), _tek_satir(o.get("value"), DEGER_SINIRI)
        if not etiket or not deger:
            continue
        veri["ozellikler"].append([etiket, deger])
        if _bayt(veri) > EN_COK_BAYT:
            veri["ozellikler"].pop()
            break
    ad_n = normalize(ad or "")
    for baslik, metin in bolum_metinleri(kayit)[:EN_COK_BOLUM]:
        metin = "\n".join(s for s in metin.split("\n") if normalize(s) != ad_n)
        if not metin:
            continue
        veri["bolumler"].append([baslik, metin])
        if _bayt(veri) > EN_COK_BAYT:   # son bölüm sığdığı kadar kısaltılır (en uzun sığan önek, ikili arama)
            alt, ust = 0, len(metin)
            while alt < ust:
                orta = (alt + ust + 1) // 2
                veri["bolumler"][-1] = [baslik, metin[:orta].rstrip() + "…"]
                if _bayt(veri) <= EN_COK_BAYT:
                    alt = orta
                else:
                    ust = orta - 1
            if alt < 20:
                veri["bolumler"].pop()
            else:
                veri["bolumler"][-1] = [baslik, metin[:alt].rstrip() + "…"]
            break
    if not veri["ozellikler"] and not veri["bolumler"]:
        return None
    return veri


# ---------- durum çıkarımı ----------
# Muhafazakâr (G3b düzeltme turu 1): yalnız açık 2. el / yenilenmiş ibareleri sayılır. "Yeni/sıfır/new" kalıpları
# model adı ve teknik terimlerle karışır ("NEW SERIES", "sıfır boşluklu redüktör"): yeni durumu ancak kaynakta yapısal
# alan olursa yazılır. Olumsuz cümledeki ("… değildir", "not used") eşleşme yok sayılır. "Test edilmiş" tek başına
# durum değildir; aynı metinde 2. el ibaresi varsa ikinci_el_test_edildi'ye yükseltir. "Olduğu gibi / as is" ancak
# 2. el ibaresiyle birlikte ikinci_el_oldugu_gibi verir. Metinler normalize() edilmiş (Türkçe katlanmış küçük harf).
_EK = r"(?:dir|idir|i|de|den|tir|dur)?"
# "used for/in …" ve "yenilenmiş tasarım/sürüm" durum değildir
_IKINCI_EL = re.compile(rf"\bikinci el{_EK}\b|\b2\. ?el{_EK}\b"
                        r"|\bused\b(?! (?:for|in|to|with|by|as a|on|at|when|where|that|is|are)\b)")
_YENILENMIS = re.compile(r"\byenilenmis(?:tir)?\b(?! (?:versiyon|surum|tasarim|model|seri|kasa))|\brefurbished\b")
_TEST = re.compile(r"\btest edilmis(?:tir)?\b|\btested\b")
_OLDUGU_GIBI = re.compile(r"\boldugu gibi\b|\bas[- ]is\b")
_OLUMSUZ = re.compile(r"\bdegil\w*|\bolmayan\b|\bnot\b|\bnever\b|\bno longer\b")
_CUMLE = re.compile(r"(?<!\d)[.!?]+(?:\s+|$)|[;\n]+")   # "2. el" içindeki nokta cümle sonu değildir
_DURUM_GUCU = ("ikinci_el", "ikinci_el_oldugu_gibi", "ikinci_el_test_edildi", "yenilenmis")


def _cumleler(metin: str) -> list[str]:
    """Normalize edilmiş, olumsuz cümleleri atılmış cümle listesi (bölme normalize'dan önce: satır sonları korunur)."""
    return [c for c in (normalize(x) for x in _CUMLE.split(metin)) if c and not _OLUMSUZ.search(c)]


def durum_cikar(ad: str, metinler: Iterable[str]) -> str | None:
    """Ad + açıklama metinlerinden durum_kodu; açık kalıp yoksa None. Her metin (ad ya da bölüm) ayrı değerlendirilir
    ("test edilmiş" yükseltmesi aynı metinde 2. el ibaresi ister); en güçlü sonuç kazanır."""
    en_iyi: str | None = None
    for metin in [ad or "", *(m for m in metinler if m)]:
        ic = "\n".join(_cumleler(metin))
        if _YENILENMIS.search(ic):
            sonuc = "yenilenmis"
        elif _IKINCI_EL.search(ic):
            sonuc = ("ikinci_el_test_edildi" if _TEST.search(ic)
                     else "ikinci_el_oldugu_gibi" if _OLDUGU_GIBI.search(ic) else "ikinci_el")
        else:
            continue
        if en_iyi is None or _DURUM_GUCU.index(sonuc) > _DURUM_GUCU.index(en_iyi):
            en_iyi = sonuc
    return en_iyi
