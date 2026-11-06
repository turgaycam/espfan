"""VKN (Gelir İdaresi algoritması) ve TCKN kontrol hanesi doğrulaması; G3c: e-posta, telefon ve VAT ID biçimi."""
import re


def _rakamlar_mi(s: str, uzunluk: int) -> bool:
    # str.isdigit() "²" gibi karakterleri de kabul eder; yalnız ASCII 0-9
    return len(s) == uzunluk and all("0" <= c <= "9" for c in s)


def vkn_gecerli(s: str) -> bool:
    if not _rakamlar_mi(s, 10):
        return False
    toplam = 0
    for i in range(9):
        p = (int(s[i]) + 9 - i) % 10
        q = (p * 2 ** (9 - i)) % 9
        if p != 0 and q == 0:
            q = 9
        toplam += q
    kontrol = (10 - toplam % 10) % 10
    return kontrol == int(s[9])


def tckn_gecerli(s: str) -> bool:
    if not _rakamlar_mi(s, 11) or s[0] == "0":
        return False
    r = [int(c) for c in s]
    tek = r[0] + r[2] + r[4] + r[6] + r[8]
    cift = r[1] + r[3] + r[5] + r[7]
    if (tek * 7 - cift) % 10 != r[9]:
        return False
    return sum(r[:10]) % 10 == r[10]


def vergi_no_hatasi(no: str) -> str | None:
    """G3m madde 26: vergi numarası (10 haneli VKN ya da 11 haneli TCKN) hata kodu; geçerliyse None. Hane sayısı / biçim
    yanlışsa "gecersiz_vkn"; hane sayısı doğru (yalnız rakam) ama doğrulama basamağı tutmuyorsa "vkn_basamak"."""
    if _rakamlar_mi(no, 10):
        return None if vkn_gecerli(no) else "vkn_basamak"
    if _rakamlar_mi(no, 11) and no[0] != "0":       # inceleme m8: TCKN 0 ile başlamaz (biçim hatası)
        return None if tckn_gecerli(no) else "vkn_basamak"
    return "gecersiz_vkn"


# ---------- G3c: iletişim ve VAT ID (kayıt, teklif ve hızlı teklif aynı yardımcıları kullanır — G3a N-4) ----------


EPOSTA_DESENI = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s.]{2,}")
TELEFON_DESENI = re.compile(r"\+?[0-9 ()./-]{7,40}")
TELEFON_EN_AZ_RAKAM = 7

# AB içi VAT numarası biçimleri (ülke öneki dahil). Yalnız mağazanın ülke listesindeki (baglam.ULKELER) AB üyeleri;
# liste genişlerse buraya eklenir. Kaynak: AB VIES biçim tablosu.
AB_VAT_DESENLERI = {
    "AT": re.compile(r"ATU\d{8}"),
    "DE": re.compile(r"DE\d{9}"),
    "FR": re.compile(r"FR[0-9A-HJ-NP-Z]{2}\d{9}"),
    "IT": re.compile(r"IT\d{11}"),
    "NL": re.compile(r"NL\d{9}B\d{2}"),
    "PL": re.compile(r"PL\d{10}"),
}
VAT_GENEL_DESENI = re.compile(r"[A-Z0-9]{4,20}")      # AB dışı vergi numarası: serbest, yalnız harf/rakam
_VAT_AYRAC = re.compile(r"[\s.\-/]")


def eposta_gecerli(deger: str | None) -> bool:
    return bool(deger) and EPOSTA_DESENI.fullmatch(deger) is not None


def telefon_gecerli(deger: str | None) -> bool:
    return (bool(deger) and TELEFON_DESENI.fullmatch(deger) is not None
            and sum(c.isdigit() for c in deger) >= TELEFON_EN_AZ_RAKAM)


def ab_ulkesi_mi(ulke: str | None) -> bool:
    return (ulke or "").upper() in AB_VAT_DESENLERI


def vat_id_kontrol(deger: str | None, ulke: str | None, *, zorunlu_ab: bool) -> tuple[str | None, str | None]:
    """(normalize VAT ID ya da None, hata kodu ya da None). Boşluk, nokta, tire, eğik çizgi atılır, büyük harfe
    çevrilir; AB ülkesinde önek yazılmamışsa ülke öneki eklenir ve ülkenin biçimi aranır (başka ülke öneki:
    'vat_ulke_uyumsuz'). zorunlu_ab: AB ülkesinde boş değer 'zorunlu' hatasıdır (yurt dışı kurumsal kayıt)."""
    ulke = (ulke or "").strip().upper()
    vat = _VAT_AYRAC.sub("", deger or "").upper()
    if not vat:
        return None, ("zorunlu" if zorunlu_ab and ab_ulkesi_mi(ulke) else None)
    desen = AB_VAT_DESENLERI.get(ulke)
    if desen is not None:
        if vat[:1].isdigit():
            vat = ulke + vat
        if vat[:2] != ulke and vat[:2].isalpha() and vat[:2] in AB_VAT_DESENLERI:
            return None, "vat_ulke_uyumsuz"
        if not desen.fullmatch(vat) and desen.fullmatch(ulke + vat):   # g3c M-6: önek yok, harfli anahtar (FR)
            vat = ulke + vat
        return (vat, None) if desen.fullmatch(vat) else (None, "gecersiz_vat")
    return (vat, None) if VAT_GENEL_DESENI.fullmatch(vat) else (None, "gecersiz_vat")
