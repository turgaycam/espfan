"""Türkçe arama normalizasyonu ve bozuk karakter temizliği."""
import re
import unicodedata

_TR_CEVIR = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c"})
# İsteğe bağlı bir U+FFFD ve ardından gelen bir ya da daha çok surrogate (U+D800..DFFF)
_BOZUK = re.compile("�?[\ud800-\udfff]+")


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = s.replace("I", "ı").replace("İ", "i").lower()
    s = s.translate(_TR_CEVIR).casefold()
    return " ".join(s.split())


def metin_temizle(s: str | None) -> str | None:
    if s is None:
        return None
    return _BOZUK.sub("�", s).strip()


# G3n madde 1: sayıya Türkçe yönelme eki ("7'ye", "3'e", "10'a"); son okunan sözcüğün ünlüsü ve ünlüyle bitip
# bitmemesi. Sıfırla bitenlerde sondaki basamak grubunun adı (on, yirmi, …, yüz, bin, milyon, milyar).
_BIRLER = {1: "e", 2: "ye", 3: "e", 4: "e", 5: "e", 6: "ya", 7: "ye", 8: "e", 9: "a"}
_ONLAR = {1: "a", 2: "ye", 3: "a", 4: "a", 5: "ye", 6: "a", 7: "e", 8: "e", 9: "a"}


def yonelme_eki(sayi: int) -> str:
    n = abs(int(sayi))
    if n == 0:
        ek = "a"                                  # sıfır
    elif n % 10:
        ek = _BIRLER[n % 10]
    elif n % 100:
        ek = _ONLAR[(n % 100) // 10]
    elif n % 1000:
        ek = "e"                                  # yüz
    elif n % 1_000_000:
        ek = "e"                                  # bin
    elif n % 1_000_000_000:
        ek = "a"                                  # milyon
    else:
        ek = "a"                                  # milyar
    return f"{sayi}'{ek}"


_TURKCE_HARF = re.compile(r"[çğöşüÇĞÖŞÜ]")


def en_ad_duzelt(ad: str) -> str:
    """G3n madde 14: EN görünen adda Türkçe büyük/küçük harf dönüşüm kalıntısı ("EVOLUTİON", "Basıc"): sözcükte
    "İ" -> "I", "ı" -> "i". Fix 1 (I-2): ç, ğ, ö, ş, ü içeren sözcük Türkçe sayılır ve dokunulmaz ("İÇİN", "ŞİŞLİ").
    Yalnız gösterim ve EN arama dizini; veri (urun_ceviri) değişmez."""
    return " ".join(s if _TURKCE_HARF.search(s) else s.replace("İ", "I").replace("ı", "i") for s in ad.split(" "))
