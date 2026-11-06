"""G3d: LLM taslağı ürün açıklamasının denetimi. Saf fonksiyon (veritabanı/ağ yok).

dogrula(metin, dil, urun) -> neden kodları listesi (boş = geçerli). `urun` sözlüğü (betikler.aciklama_disa'nın
satırı): ad, sku, uretici_kodu, marka, durum_kodu, teknik [[anahtar, değer], ...], kaynak_aciklama.
Kodlar: uzunluk, dil, en_bicim, sku, uydurma_sayi, yasak_ifade, durum_celiski, html, marka_uydurma.

Sayı kuralı (yanlış reddi yanlış kabule tercih eder): metindeki her yalın sayı, BİRİMİYLE birlikte (kg, mm, V ...)
kaynakta aynı (sayı, birim) çiftiyle geçmeli; harf+rakam karışık kod jetonları kaynaktaki ardışık jetonların
(boşluk/tire/nokta katlanmış) birleşimiyle birebir eşleşmeli. Kodun ya da ondalığın parçası ("R2010" -> 2010,
"16,5" -> 5, "1EA00" -> 1EA00) kabul edilmez.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.katalog.indeks import kod_birlesik
from app.katalog.marka import _DESENLER, _kat
from app.metin import normalize

EN_AZ_UZUNLUK = 300
EN_COK_UZUNLUK = 1200
EN_COK_PARAGRAF = 3

_TR_HARF = set("çğıöşüÇĞİÖŞÜ")
_TR_OZEL = re.compile("[ğşıİĞŞ]")
_TR_SIK = frozenset({"ve", "bir", "icin", "ile", "bu", "olarak", "urun", "genellikle", "teklif", "stok", "da", "de",
                     "veya", "ancak", "icinde", "gibi", "durumda", "sistemlerinde", "kullanilir"})
_EN_TR_ORAN = 0.02  # en metinde (üründen gelen sözcükler hariç) Türkçe harflerin harflere oranı bunu aşarsa "dil"
_TR_MIN_ORAN = 0.02  # tr metinde (ürün sözcükleri hariç) Türkçe harf oranı ya da en az 2 sık sözcük gerekir
_UZUN_METIN = 1500  # bundan uzun metin yalnız "uzunluk" ile reddedilir (regex'lere hiç sokulmaz)

# --- sayı / kod denetimi ---
_BIRIMLER = frozenset({
    "kg", "mg", "g", "mm", "cm", "km", "m", "um", "µm", "v", "kv", "mv", "a", "ma", "ka", "w", "kw", "mw",
    "va", "kva", "hz", "khz", "mhz", "ghz", "rpm", "nm", "kn", "bar", "psi", "mpa", "pa", "ml", "ms",
    "min", "ah", "mah", "db", "kb", "mb", "gb", "tb", "bit", "baud", "pin", "ohm", "ω", "%", "°c", "°",
    "adet", "pcs", "piece", "pieces", "unit", "units", "eksen", "axis", "axes", "kanal", "channel",
    "channels", "mbps", "gbps", "kj", "j"})
# TR<->EN eşdeğer birim/sözcük grupları (normalize edilmiş: ı->i, ç->c ...). Karşılaştırma bu kanonik adla yapılır:
# kaynakta "1 saniye", metinde "1 second" geçer; "2 seconds" geçmez (sayı farklı).
_ESDEGER_GRUPLAR = {
    "saniye": ("saniye", "second", "seconds", "sec", "secs", "s"),
    "dakika": ("dakika", "minute", "minutes", "min", "mins"),
    "saat": ("saat", "hour", "hours", "h", "hr", "hrs"),
    "faz": ("fazli", "faz", "phase", "phases"),
    "adet": ("adet", "pcs", "pc", "piece", "pieces", "unit", "units"),
    "kanal": ("kanal", "kanalli", "channel", "channels"),
    "eksen": ("eksen", "eksenli", "axis", "axes"),
    "cikis": ("cikis", "output", "outputs"),
    "giris": ("giris", "input", "inputs"),
    "bagimsiz": ("bagimsiz", "independent"),
    "kutup": ("kutup", "kutuplu", "pole", "poles"),
    # sıradan ölçü sözcükleri (kaynak "25 Amper", metin "25 A")
    "a": ("a", "amper", "ampere", "amp", "amps"), "v": ("v", "volt", "volts"), "w": ("w", "watt", "watts"),
    "m": ("m", "metre", "meter", "metres", "meters"), "g": ("g", "gram", "grams"),
    "kg": ("kg", "kilogram", "kilograms"), "hz": ("hz", "hertz"),
    "mm": ("mm", "milimetre", "millimeter", "millimeters", "millimetre", "millimetres"),
    "cm": ("cm", "santimetre", "centimeter", "centimeters", "centimetre", "centimetres"),
    "konnektor": ("konnektor", "connector", "connectors"), "kademe": ("kademe", "step", "steps"),
    "genisletme": ("genisletme", "expansion"),
    "iletken": ("iletken", "conductor", "conductors", "wire", "wires"),
}
_ESDEGER = {w: k for k, ws in _ESDEGER_GRUPLAR.items() for w in ws}
_ESDEGER["℃"] = "°c"
# Teknik özellik ANAHTARI -> birim: değeri yalın sayı olan satır ("Kanal Sayısı: 4") kaynakta (4, kanal) sayılır.
_ANAHTAR_BIRIM = {"kanal sayisi": "kanal", "eksen sayisi": "eksen", "cikis sayisi": "cikis", "giris sayisi": "giris",
                  "faz": "faz", "faz sayisi": "faz"}
# Sayıdan sonra gelen ve birim OLMAYAN sıradan sözcükler: bu sözcükle ("KR 16 serisi") yalın sayı kaynakta varsa geçer.
_BAGLAC = frozenset({"ve", "ile", "icin", "için", "olarak", "olan", "serisi", "seri", "series", "model", "modeli",
                     "tipi", "type", "and", "with", "for", "or", "veya", "ya", "da", "de", "ise", "is", "are", "to", "ila", "kadar", "up"})
# Sayı (+ bitişik "-" ve harf) (+ en çok 2 boşluk ve sözcük). Harfe bitişik ama rakamla devam eden jeton (6ES7, 1EA00)
# sayı DEĞİL kod jetonudur; (?![.,/-]\d) sayının kodun parçası olarak bölünmesini önler.
_SAYI = re.compile(
    r"(?<![\w])(?<!\w[.,/-])([.,]?\d+(?:[.,/-]\d+)*)(?![.,/-]\d)"
    r"(?:-?([^\W\d_]+)(?!\w)|(?:\s{0,2}(°\s?[CcFf]?|℃|%)|\s{1,2}([^\W\d_][\w²³]*))?(?!\w))"
)
_SAYI_SOZCUKLERI = {"bir": "1", "iki": "2", "uc": "3", "dort": "4", "bes": "5", "alti": "6", "yedi": "7",
                    "sekiz": "8", "dokuz": "9", "on": "10", "one": "1", "two": "2", "three": "3", "four": "4",
                    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}
_SAYI_SOZCUGU = re.compile(r"\b(" + "|".join(_SAYI_SOZCUKLERI) + r")\s+([^\W\d_]+)")
_ADET_SOZCUK = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:adet|pcs|x)\s+([^\W\d_]\w*)")
_IP_BOSLUKLU = re.compile(r"\bIP[\s-](\d{2})(?!\d)")
_KOD_JETON = re.compile(r"(?<!\w)(?=[\w.,/-]*\d)(?=[\w.,/-]*[^\W\d_])\w[\w.,/-]*")
_SAYI_BIRIM_JETON = re.compile(r"[.,]?\d+(?:[.,/-]\d+)*-?[^\W\d_]+")
_ARDISIK_JETON = 6
_KIMLIK_EN_AZ_RAKAM = 6  # bu kadar rakamlı sayılar kimlik/kod sayılır: ayraç farkı katlanır (00-123-456 == 00123456)
_YAZI_SAYI = re.compile(
    r"\b(?:bir|iki|uc|dort|bes|alti|yedi|sekiz|dokuz|yirmi|otuz|kirk|elli|yuz|one|two|three|four|five|six|seven|"
    r"eight|nine|ten|twenty|thirty|forty|fifty|hundred)\s+(?:yil|ay|gun|kg|kilogram\w*|metre|volt|amper|watt|"
    r"mm|years?|months?|days?|kilograms?|meters?|metres?|volts?|amps?|watts?)\b")

# İzinli genel sayılar yalnız bu bağlamlarda (eşleşme aralığındaki jetonlar atlanır). "12 ay" yalnız garantili durumda.
_GARANTI_12 = re.compile(r"(?<![\w.,/-])12[\s-]*(?:ay(?:lık|lik)?|months?)\b", re.IGNORECASE)
_IZINLI_BAGLAM: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![\w.,/-])14[\s-]*(?:gün(?:lük)?|gun(?:luk)?|days?(?![\s-]+(?:ship|deliver|lead)))\b", re.IGNORECASE),
    re.compile(r"(?<![\w.,/-])2(?:\.\s*el\b|nd[\s-]*hand\b)", re.IGNORECASE),
    re.compile(r"(?<![\w.,/-])1[\s-]*(?:adet|piece|unit)\b", re.IGNORECASE),
)
GARANTILI_DURUMLAR = frozenset({"ikinci_el_test_edildi", "yenilenmis"})  # app.web.seo.GARANTILI_DURUMLAR ile aynı
_GARANTI_SOZ = re.compile(r"\b(?:garanti\w*|warrant\w*)")

# seo/kaliplar.md: rakip/benzer satıcılar (ceylanrobot hariç)
RAKIP_SATICILAR = ("pazar otomasyon", "rotosis", "mers robot", "bktronic", "generis", "lektronix")
_YASAK_IFADE = (
    "yetkili satıcı", "yetkili distribütör", "yetkili dağıtımcı", "authorized dealer", "authorized distributor",
    "official distributor", "orijinal garanti", "fabrika garantisi", "en ucuz", "%100",
) + RAKIP_SATICILAR
_YASAK_NORMAL = tuple(normalize(x) for x in _YASAK_IFADE)
_YASAK_DESEN = re.compile(
    r"authori[sz]ed\s+(?:dealer|distributor|reseller|partner)|official\s+(?:dealer|distributor|partner|reseller)"
    r"|yetkili\s+(?:satici|distributor|dagitimci|servis|bayi|temsilci)")
_RAKIP_BITISIK = tuple(re.sub(r"\W", "", normalize(x)) for x in RAKIP_SATICILAR if " " in x)
_RAKIP_TEK = re.compile(r"\b(?:" + "|".join(normalize(x) for x in RAKIP_SATICILAR if " " not in x) + r")\b")
_ILETISIM = (
    re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+"),
    re.compile(r"https?://|\bwww\.|\b[\w-]+\.(?:com|net|org|tr|io|eu|de)\b", re.IGNORECASE),
    re.compile(r"\+\d[\d\s().-]{7,}\d|\b0\d{3}[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}\b|\(\d{3}\)\s*\d{3}"),
)

# Durum -> metinde bulunmaması gereken ifadeler (normalize edilmiş metinde; olumsuzlanmışsa sayılmaz)
_YENI_SOZ = r"sifir|yeni|brand[\s-]+new|new"
_KULLANILMAMIS = r"kullanilmamis|unused|like[\s-]+new|as[\s-]+new|mint"
_IKINCI_EL = r"ikinci[\s-]+el|second[\s-]*hand|used|kullanilmis"
_YENILENMIS = r"yenilenmis|refurbished|reconditioned"
_TEST_EDILMIS = r"test\s+edilmis|tested"
_TEST_YOK = r"test\s+edilmemis|untested|as[\s-]+is|oldugu\s+gibi"
_DURUM_YASAK: dict[str, re.Pattern[str]] = {
    "yeni": re.compile(rf"\b(?:{_IKINCI_EL}|{_YENILENMIS})\b"),
    "yenilenmis": re.compile(rf"\b(?:{_YENI_SOZ}|{_KULLANILMAMIS}|{_TEST_YOK})\b"),
    "ikinci_el": re.compile(rf"\b(?:{_YENI_SOZ}|{_KULLANILMAMIS}|{_YENILENMIS}|{_TEST_EDILMIS})\b"),
    "ikinci_el_oldugu_gibi": re.compile(rf"\b(?:{_YENI_SOZ}|{_KULLANILMAMIS}|{_YENILENMIS}|{_TEST_EDILMIS})\b"),
    "ikinci_el_test_edildi": re.compile(rf"\b(?:{_YENI_SOZ}|{_KULLANILMAMIS}|{_YENILENMIS}|{_TEST_YOK})\b"),
    "belirtilmemis": re.compile(
        rf"\b(?:{_YENI_SOZ}|{_KULLANILMAMIS}|{_YENILENMIS}|{_TEST_EDILMIS}|{_IKINCI_EL})\b"),
}
_OLUMSUZ_SONRA = re.compile(r"\s*(?:degil|degildir|olmayan|olmadan)\b")
_OLUMSUZ_ONCE = re.compile(r"\b(?:not(?!\s+only)|non|never|no|hic)\s*$")

_HTML_KARAKTER = re.compile(r"[<>`]")
_MD_SATIR = re.compile(r"^[ \t]*(?:#|\*|-)(?:\s|$)|^[ \t]*\d+[.)]\s|\*\*", re.MULTILINE)


def _alan_metinleri(urun: Mapping[str, Any]) -> list[str]:
    """Her kaynak alan ayrı (alanlar arası kod birleşmesi olmasın)."""
    alanlar = [urun.get("ad"), urun.get("sku"), urun.get("uretici_kodu"), urun.get("kaynak_aciklama")]
    for cift in urun.get("teknik") or []:
        alanlar.extend(str(p) for p in cift)
        alanlar.append(" ".join(str(p) for p in cift))
    return [str(a) for a in alanlar if a]


def _kanonik_sayi(ham: str) -> str:
    """Kanonik değer: tek ondalık ayracı '.', binlik ayraçları atılır, ondalıktaki sondaki sıfırlar atılır.
    Çok parçalı değerler (120/230, 00-123-456, 1-2) ayracıyla korunur (rakamlar birleştirilmez). Belirsizse
    (ör. 1.000) tek ayraç ondalık sayılır: yanlış reddi yanlış kabule tercih ederiz."""
    if re.search(r"[/-]", ham):
        return ham.replace(",", ".")
    if ham[:1] in ".,":
        ham = "0." + ham[1:]
    ayraclar = re.findall(r"[.,]", ham)
    if not ayraclar:
        return ham
    parcalar = re.split(r"[.,]", ham)
    if len(ayraclar) >= 2:
        if len(set(ayraclar)) == 1:
            if len(parcalar[0]) <= 3 and all(len(g) == 3 for g in parcalar[1:]):
                return "".join(parcalar)  # 1.234.567: binlik ayraçlı tam sayı
            return ham.replace(",", ".")  # 12.10.2026 gibi: olduğu gibi
        son = max(ham.rfind("."), ham.rfind(","))
        return re.sub(r"[.,]", "", ham[:son]) + "." + ham[son + 1:]  # 1.234,5
    kesir = parcalar[1].rstrip("0")
    return f"{parcalar[0]}.{kesir}" if kesir else parcalar[0]


def _birim_anahtari(birim: str | None) -> str | None:
    """Birim adayının kanonik adı (küçük harf, TR katlama, TR<->EN eşdeğer grup)."""
    if not birim:
        return None
    b = normalize(birim).replace(" ", "")
    if b in _ESDEGER:
        return _ESDEGER[b]
    for kelime, kanonik in _ESDEGER.items():  # Türkçe/İngilizce ek: saniyeye, saniyedir, kanallari (en çok 3 harf)
        if len(kelime) >= 4 and b.startswith(kelime) and len(b) - len(kelime) <= 3:
            return kanonik
    return b


_BILINEN_BIRIMLER = frozenset(_birim_anahtari(b) for b in _BIRIMLER) | frozenset(_ESDEGER_GRUPLAR)


def _sayi_ciftleri(metin: str) -> list[tuple[int, str, str | None, str]]:
    """(başlangıç, kanonik değer, kanonik birim adayı|None, sayısal ham metin). Birim adayı: sayıyı hemen izleyen
    sözcük/simge (3-phase, 4 kanal, 20 °C). Sayıdan hemen önceki '-' (öncesinde harf/rakam yoksa) işaret sayılır."""
    sonuc = []
    for m in _SAYI.finditer(metin):
        birim = m.group(2) or m.group(3) or m.group(4)
        deger = _kanonik_sayi(m.group(1))
        i = m.start(1)
        if i >= 1 and metin[i - 1] == "%":
            birim = "%"  # %50 == 50 % (öndeki yüzde işareti sonraki sözcükten önce gelir)
        if i >= 1 and metin[i - 1] in "-−–" and (i < 2 or not metin[i - 2].isalnum()) and not deger.startswith("-"):
            deger = "-" + deger
        sonuc.append((m.start(), deger, _birim_anahtari(birim), m.group(1)))
    return sonuc


def _kaynak_modeli(urun: Mapping[str, Any]) -> tuple[set[tuple[str, str | None]], set[str], set[str]]:
    """(değer, birim) çiftleri, kimlik rakam dizileri ve kod jetonlarının (ardışık birleşimler) katlanmış kümesi."""
    ciftler: set[tuple[str, str | None]] = set()
    kimlikler: set[str] = set()
    kodlar: set[str] = set()
    for cift in urun.get("teknik") or []:
        if len(cift) == 2 and re.fullmatch(r"\s*\d+\s*", str(cift[1])):
            birim = _ANAHTAR_BIRIM.get(normalize(str(cift[0])))
            if birim:
                ciftler.add((str(cift[1]).strip(), birim))
    for alan in _alan_metinleri(urun):
        n = normalize(alan)
        for m in _SAYI_SOZCUGU.finditer(n):  # "Üç Fazlı", "iki faz": yazıyla yazılmış sayı + bilinen birim sözcüğü
            b = _birim_anahtari(m.group(2))
            if b in _ESDEGER_GRUPLAR:
                ciftler.add((_SAYI_SOZCUKLERI[m.group(1)], b))
        for m in _ADET_SOZCUK.finditer(n):  # "2 adet bağımsız giriş" -> (2, bagimsiz)
            ciftler.add((_kanonik_sayi(m.group(1)), _birim_anahtari(m.group(2)) or ""))
        for _b, deger, birim, ham in _sayi_ciftleri(alan):
            ciftler.add((deger, birim))
            if birim not in _BILINEN_BIRIMLER:
                ciftler.add((deger, None))  # birim olmayan sözcük: yalın sayı da kaynakta var sayılır
            rakamlar = re.sub(r"\D", "", ham)
            if len(rakamlar) >= _KIMLIK_EN_AZ_RAKAM:
                kimlikler.add(rakamlar)
        jetonlar = [kod_birlesik(j.strip(".,;:()[]/")) for j in alan.split()]
        jetonlar = [j for j in jetonlar if j]
        for i in range(len(jetonlar)):
            birlesik = ""
            for j in jetonlar[i:i + _ARDISIK_JETON]:
                birlesik += j
                kodlar.add(birlesik)
    return ciftler, kimlikler, kodlar


def _uydurma_sayilar(metin: str, urun: Mapping[str, Any], garantili: bool) -> bool:
    """Her sayı BİRİMİYLE birlikte kaynakta aynı kanonik değer + aynı birim sözcüğüyle bulunmalı."""
    ciftler, kimlikler, kodlar = _kaynak_modeli(urun)
    izinli = [m.span() for p in _IZINLI_BAGLAM for m in p.finditer(metin)]
    if garantili:
        izinli += [m.span() for m in _GARANTI_12.finditer(metin)]

    def atla(konum: int) -> bool:
        return any(a <= konum < b for a, b in izinli)

    for m in _IP_BOSLUKLU.finditer(metin):  # "IP 20" kod jetonudur (ip20), sayı değil
        izinli.append(m.span())
        if "ip" + m.group(1) not in kodlar:
            return True
    if _YAZI_SAYI.search(normalize(metin)):
        return True  # "iki yıl", "beş kilogram": yazıyla yazılmış ölçü/süre denetlenemez
    for m in _KOD_JETON.finditer(metin):
        jeton = m.group(0).rstrip(".,/-")
        if atla(m.start()) or _SAYI_BIRIM_JETON.fullmatch(jeton):
            continue  # sayı+birim jetonları aşağıdaki değer yolunda denetlenir (ayraç katlaması YOK)
        if not (any(c.isdigit() for c in jeton) and any(c.isalpha() for c in jeton)):
            continue
        if kod_birlesik(jeton) not in kodlar:
            return True
    for baslangic, deger, birim, ham in _sayi_ciftleri(metin):
        if atla(baslangic):
            continue
        rakamlar = re.sub(r"\D", "", ham)
        if len(rakamlar) >= _KIMLIK_EN_AZ_RAKAM and rakamlar in kimlikler:
            continue
        if birim is None or (birim in _BAGLAC and birim not in _BILINEN_BIRIMLER):
            if (deger, None) in ciftler:
                continue
            return True
        if (deger, birim) not in ciftler:
            return True
    return False


def _dil_hatasi(metin: str, dil: str, urun: Mapping[str, Any]) -> bool:
    """Ürün adı/marka/kategorideki sözcükler (Türkçe adın kopyası) sayımdan düşülür."""
    urun_sozcukleri = {w.lower() for w in re.findall(r"\w+", " ".join(
        str(urun.get(k) or "") for k in ("ad", "marka", "kategori", "uretici_kodu")))}
    kendi = [w for w in re.findall(r"\w+", metin) if w.lower() not in urun_sozcukleri]
    harfler = [c for w in kendi for c in w if c.isalpha()]
    tr_harf = sum(1 for c in harfler if c in _TR_HARF)
    sik = sum(1 for w in re.findall(r"[a-z]+", normalize(" ".join(kendi))) if w in _TR_SIK)
    if dil == "tr":
        return (not harfler or tr_harf / len(harfler) < _TR_MIN_ORAN) and sik < 2
    if dil == "en":
        if any(_TR_OZEL.search(w) for w in kendi):
            return True  # çevrilmemiş Türkçe sözcük (ğ ş ı İ): ürün adı/kod dışında İngilizce metinde olmamalı
        return bool(harfler) and (tr_harf / len(harfler) > _EN_TR_ORAN or sik >= 3)
    return True


def _yasak_ifade(metin: str) -> bool:
    n = normalize(metin)
    if any(ifade in n for ifade in _YASAK_NORMAL) or _YASAK_DESEN.search(n) or _RAKIP_TEK.search(n):
        return True
    bitisik = re.sub(r"\W", "", n)
    if any(r in bitisik for r in _RAKIP_BITISIK):
        return True
    return any(d.search(metin) for d in _ILETISIM)


def _olumsuz(n: str, m: re.Match[str]) -> bool:
    return bool(_OLUMSUZ_SONRA.match(n, m.end()) or _OLUMSUZ_ONCE.search(n[max(0, m.start() - 12):m.start()]))


def _durum_celiskisi(metin: str, durum: str | None) -> bool:
    n = normalize(metin)
    desen = _DURUM_YASAK.get(durum or "")
    if desen is not None and any(not _olumsuz(n, m) for m in desen.finditer(n)):
        return True
    # garanti taahhüdü yalnız site politikasındaki durumlarda (app.web.seo.garantili_mi)
    return durum not in GARANTILI_DURUMLAR and bool(_GARANTI_SOZ.search(n))


def _html_hatasi(metin: str) -> bool:
    if _HTML_KARAKTER.search(metin) or _MD_SATIR.search(metin):
        return True
    return len([p for p in re.split(r"\n\s*\n", metin) if p.strip()]) > EN_COK_PARAGRAF


def _marka_uydurma(metin: str, marka: str | None) -> bool:
    n = _kat(metin)
    gercek = _kat(marka) if marka else None
    for desen, _anahtar, gorunen in _DESENLER:
        if desen.search(n) and _kat(gorunen) != gercek:
            return True
    return False


_EN_YUZDE_ONEKI = re.compile(r"(?<!\w)%\s?\d")


def _en_bicim(metin: str) -> bool:
    """EN metinde yüzde "87%" yazılır (önek "%87" değil); "Amper"/"Watt" yerine A / W (ya da amperes / watts)."""
    return bool(_EN_YUZDE_ONEKI.search(metin) or re.search(r"\bamper\b", metin, re.IGNORECASE)
                or re.search(r"\bWatt\b", metin))


def _sku_var(metin: str, urun: Mapping[str, Any]) -> bool:
    sku = kod_birlesik(str(urun.get("sku") or ""))
    return len(sku) >= 6 and sku in kod_birlesik(metin)


_ISLEV_FIILLERI = {
    "tr": ("korur", "yeniler", "aktarir", "kontrol eder", "saglar", "filtreler", "iletir", "donusturur", "besler",
           "bastirir", "yukseltir", "ayarlar", "sinirlar", "izler", "algilar", "dengeler"),
    "en": ("protects", "regenerates", "transmits", "controls", "provides", "filters", "converts", "supplies",
           "suppresses", "amplifies", "regulates", "limits", "monitors", "detects", "ensures", "stabilizes"),
}


def uyarilar(metin: str, dil: str, urun: Mapping[str, Any]) -> list[str]:
    """RET DEĞİL, yalnız uyarı: kaynakta (ad/kategori/teknik/kaynak açıklama) kökü geçmeyen işlev fiili ("korur",
    "yeniler", "protects" ...). İnsan denetimi için sayılır."""
    n = normalize(metin)
    kaynak = normalize(" ".join(_alan_metinleri(urun) + [str(urun.get("kategori") or ""),
                                                          str(urun.get("kategori_en") or "")]))
    for fiil in _ISLEV_FIILLERI.get(dil, ()):
        if re.search(r"\b" + fiil + r"\b", n) and fiil.split()[0][:4] not in kaynak:
            return ["islev_fiili"]
    return []


# Ad ile teknik alanların çelişkisi (kaynak veri adı yanlış olabilir: "akım filtresi" ama özellikler fren direnci).
# Çelişkili ürünler LLM'e gönderilmez, insan kuyruğuna alınır.
_VA = re.compile(r"\b\d+(?:[.,]\d+)?\s*k?va\b")
_MA = re.compile(r"\b\d+(?:[.,]\d+)?\s*ma\b")
_ENDUKTANS = re.compile(r"enduktans|inductance|\b\d+(?:[.,]\d+)?\s*mh\b")


def tur_celiskisi(urun: Mapping[str, Any]) -> str | None:
    ad = normalize(str(urun.get("ad") or ""))
    parcalar = [str(urun.get("kaynak_aciklama") or "")]
    for cift in urun.get("teknik") or []:
        parcalar.extend(str(p) for p in cift)
    spec = normalize(" ".join(parcalar))
    if "filtre" in ad and re.search(r"\bdirenc|\bohm\b|ω|fren", spec):
        return "filtre_direnc"
    if re.search(r"trafo|transformator|transformer", ad) and not _VA.search(spec) and (
            _MA.search(spec) or _ENDUKTANS.search(spec)):
        return "trafo_ma_va_yok"
    if re.search(r"devre kesici|circuit breaker", ad) and re.search(r"bobin|kontaktor|coil", spec):
        return "kesici_bobin"
    return None


def dogrula(metin: str, dil: str, urun: Mapping[str, Any]) -> list[str]:
    nedenler: list[str] = []
    if not isinstance(metin, str):
        return ["uzunluk"]
    if len(metin) > _UZUN_METIN:
        return ["uzunluk"]
    if not EN_AZ_UZUNLUK <= len(metin.strip()) <= EN_COK_UZUNLUK:
        nedenler.append("uzunluk")
    if _dil_hatasi(metin, dil, urun):
        nedenler.append("dil")
    if dil == "en" and _en_bicim(metin):
        nedenler.append("en_bicim")
    if _sku_var(metin, urun):
        nedenler.append("sku")
    if _uydurma_sayilar(metin, urun, urun.get("durum_kodu") in GARANTILI_DURUMLAR):
        nedenler.append("uydurma_sayi")
    if _yasak_ifade(metin):
        nedenler.append("yasak_ifade")
    if _durum_celiskisi(metin, urun.get("durum_kodu")):
        nedenler.append("durum_celiski")
    if _html_hatasi(metin):
        nedenler.append("html")
    if _marka_uydurma(metin, urun.get("marka")):
        nedenler.append("marka_uydurma")
    return nedenler
