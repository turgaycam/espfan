"""G3f: LLM taslağı EN ürün adı ve teknik özellik çevirisinin denetimi. Saf fonksiyon (veritabanı/ağ yok).

dogrula(kaynak, ceviri) -> neden kodları listesi (boş = geçerli).
  kaynak: {"ad": TR ad, "teknik": [[anahtar, değer], ...]}   (betikler.ceviri_disa satırı)
  ceviri: {"ad_en": str, "teknik_en": [[anahtar, değer], ...] | None}   (None: yalnız ad çevrildi)
Kodlar (sabit sırada, tekil):
  bos            EN ad ya da bir teknik anahtar/değer boş (yalnız boşluk)
  uzunluk        EN ad 3–200 kr değil ya da TR adın 0,5–2,5 katı dışında
  satir_sayisi   teknik satır sayısı TR ile aynı değil
  sayi_kod       sayı/kod jetonlarının çoklu kümesi farklı (ad; her teknik satırda anahtar ve değer AYRI AYRI)
  birim          sayılar aynı ama bir değerin birimi ya da akım türü (AC/DC) farklı
  kod            TR'deki büyük harfli model/seri/marka sözcüğü (SIMATIC, KCP, AC ...) EN'de yok
  turkce_kalinti EN metinde Türkçe harf ya da sık Türkçe sözcük
  marka          TR addaki izin listesi markası EN adda yok ya da EN ada yeni marka eklenmiş
uyarilar(kaynak) -> ret olmayan uyarılar (binlik_ayrac: "1.000" / "1,500" gibi belirsiz binlik ayraç).

Jetonlar (düzeltme turu 1): metin boşluk ve ,;()[]{}"' ile parçalara ayrılır. Parça:
  - sayı: [işaret/karşılaştırma -+±<>≤≥~] sayı (ondalık virgül -> nokta; aralık "0.5-3", kesir "1/2", çarpım "3x400")
    + birim. Birim bitişik ya da sonraki parça olabilir ("24V" == "24 V"), YALNIZ sembol eşdeğerlik tablosuyla
    kanonikleşir (amper -> A, sn -> s, dak -> min, mVss -> mVpp; kg ≠ lb, V ≠ kV). "%15" == "15%".
    VAC/VDC -> V + AC/DC. Sayıdan sonra "-sözcük" ("3-phase", "1-FAZ") sayı + sözcük sayılır.
  - kod: rakam içeren diğer parçalar ham hâliyle (büyük harf, ayraçlar korunur: "00-109-802" ≠ "00109802",
    "Ç-200", "Ø20", "6EP1961-2BA11").
  - büyük harfli sözcük: ≤4 harfli kısaltmalar (kısa Türkçe sözcükler hariç) ve bilinen marka/seri adları EN'de
    (büyük/küçük harf ve İ/I duyarsız, çoğul -s serbest) geçmeli. Uzun Türkçe sözcükler bir sözlükle ayrılamadığı
    için listede olmayan uzun seri adı denetlenmez (bilinen sınırlama).
  - binlik ayraç: TR'de noktalı ("6.000" == "6000"), EN'de noktalı ya da virgüllü binlik ayraçsız sayılır.
Belirsizlikte yanlış ret yanlış kabule tercih edilir. TR addaki "2. EL" ("Used") sayı sayılmaz.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.katalog.marka import _DESENLER, BILINEN_MARKALAR, _kat
from app.metin import normalize

AD_EN_AZ = 3
AD_EN_COK = 200
ORAN_EN_AZ = 0.5
ORAN_EN_COK = 2.5

KODLAR = ("bos", "uzunluk", "satir_sayisi", "sayi_kod", "birim", "binlik", "kod", "turkce_kalinti", "marka")

_IKINCI_EL = re.compile(r"(?<![\w.])2\s*\.\s*(?:EL|el|El)\b")
_ONDALIK = re.compile(r"(?<=\d),(?=\d)")
_TR_HARF = re.compile("[ğşıİçöüĞŞÇÖÜ]")
_KELIME = re.compile(r"\w+")
_PARCA_AYIRICI = re.compile(r"""[\s,;:()\[\]{}"“”‘’'`]+|//+|\.{3}|…""")
_SAYI = re.compile(
    r"(?P<on>[-+±<>≤≥~]?)(?P<y1>%?)"
    r"(?P<sayi>\d+(?:\.\d+)?(?:[/xX-]\d+(?:\.\d+)?)*)"
    r"(?P<y2>%?)(?P<birim>°[CFcf]?|[^\W\d_]+(?:/[^\W\d_]+)?)?")
_SAYI_SOZCUK = re.compile(r"(?P<sayi>\d+(?:\.\d+)?(?:/\d+)?)[-.](?P<soz>[^\W\d_]+)")
# Türkçe sayı ekleri ("8'li" -> "8Lİ", "10LU", "3LÜ"): sayı birimsiz sayılır
_TR_SAYI_EKI = frozenset({"li", "lu", "lik", "luk", "lık", "lük", "ncu", "nci", "uncu", "inci", "lı", "lü"})
_KOD_SOZCUK = re.compile(r"(?P<kod>\w*\d\w*)-(?P<soz>[^\W\d_]+)")
_KARSILASTIRMA = frozenset("<>≤≥±~")
_BINLIK_NOKTA = re.compile(r"(?<![\d.,])\d{1,3}(?:\.\d{3})+(?![.,]?\d)")
_BINLIK_EN = re.compile(r"(?<![\d.,])\d{1,3}(?:([.,])\d{3})(?:\1\d{3})*(?![.,]?\d)")
_YUZDE_ONCE = re.compile(r"(?<!\d)%\s?([-+±]?)\s?(\d+(?:[.,]\d+)?)")
_YUZDE_BOSLUK = re.compile(r"(\d)\s+%")
_SIRA_EKI = frozenset({"st", "nd", "rd", "th"})
_AYRIK_OLMAYAN_BIRIM = frozenset({"in", "a", "t", "h", "s", "m", "g", "k", "n", "f", "l"})   # İngilizce sözcük olabilir
_BINLIK = re.compile(r"(?<![\d.,])\d{1,3}(?:[.,]\d{3})+(?![\d.,]*\d)")
# N-5: TR'de KESİN binlik: iki ya da daha çok nokta grubu ("10.000.000") ya da ".000" ("1.000"; ondalık olarak
# "1.000" yazılması beklenmez). Tek grup ve sıfırdan farklı ("1.500", "2.688") belirsiz: kaynak İngilizce biçimli
# ondalık da kullanıyor ("1.65 A") -> ret değil uyarı.
_BINLIK_KESIN = re.compile(r"(?<![\d.,])[1-9]\d{0,2}(?:(?:\.\d{3}){2,}|\.000)(?![.,]?\d)")

# Birim eşdeğerlik tablosu: kanonik sembol -> yazımlar. Semboller HARF DUYARLI yazılır (N-1: MW ≠ mW, MHz ≠ mHz,
# MΩ ≠ mΩ, MB ≠ mb); sözcük yazımları (volt, amper, saniye ...) küçük harfle. Yalnız aynı birimin yazımları; ölçek ya
# da sistem dönüşümü YOK (kV ≠ V, kg ≠ lb). Eşleme: _birim().
_BIRIM_TABLOSU: dict[str, tuple[str, ...]] = {
    "V": ("volt", "volts"), "kV": (), "mV": (), "MV": (), "µV": ("uV",),
    "A": ("amper", "ampere", "amperes", "amp", "amps", "amperlik"), "mA": (), "kA": (), "µA": ("uA",),
    "W": ("watt", "watts"), "kW": (), "mW": (), "MW": (), "VA": (), "kVA": (), "VAr": ("var",),
    "Hz": ("hertz",), "kHz": (), "MHz": (), "mHz": (), "GHz": (),
    "mm": (), "cm": (), "m": ("mt", "metre", "meter", "metres", "meters"), "km": (), "µm": ("um",),
    "kg": (), "g": ("gr", "gram", "grams"), "mg": (), "t": ("ton",),
    "N": (), "kN": (), "Nm": (), "bar": (), "mbar": (), "psi": (),
    "Pa": (), "kPa": (), "MPa": (), "mPa": (),
    "°C": ("C°",), "°F": (), "°": (), "K": (),
    "rpm": ("d/dk", "dev/dk"), "s": ("sn", "sec", "secs", "san", "second", "seconds"), "ms": (), "µs": ("us",),
    "ns": (), "min": ("dk", "dak", "minute", "minutes", "mins"),
    "h": ("sa", "hr", "hrs", "hour", "hours", "saat"),
    "mVpp": ("mVss", "mVp-p"), "Ω": ("ohm",), "kΩ": ("kohm",), "MΩ": ("Mohm", "MOhm"), "mΩ": ("mohm",),
    "F": (), "µF": ("uF",), "nF": (), "pF": (),
    "Ah": (), "mAh": (), "Wh": (), "kWh": (), "kWs": (), "Ws": (),
    "dB": (), "dBA": ("dB(A)",), "l": ("lt",), "ml": (), "l/min": ("l/dk", "lt/dk"),
    "bit": ("bits",), "kB": (), "MB": (), "GB": (), "Mbps": (), "kbps": (), "Gbps": (), "baud": (),
    "B": ("byte", "bytes", "bayt"),
    "m/s": (), "mm/s": (), "°/s": (), "kg/m": (),
    # inç: birim düşer (19" == 19 inch == 19 in; ayrık "in" İngilizcede edat olabilir)
    "": ("in", "inch", "inches", "inç", "inc", "″"),
}
_BIRIM_SOZCUK = frozenset(y for ys in _BIRIM_TABLOSU.values() for y in ys if len(y) >= 3 and y.isalpha() and y.islower())
_BIRIM_TAM: dict[str, str] = {}
_BIRIM_KUCUK: dict[str, set[str]] = {}
for _kanonik, _yazimlar in _BIRIM_TABLOSU.items():
    for _y in (_kanonik, *_yazimlar):
        if _y:
            _BIRIM_TAM[_y] = _kanonik
            _BIRIM_KUCUK.setdefault(_y.lower(), set()).add(_kanonik)
# N-3: kontak tipleri tam eşleşir (sayı ve tür): NO ↔ NC değişimi, eklenen/düşen kontak red. Yalnız büyük harfle.
_KONTAK = frozenset({"NO", "NC", "COM"})
_TR_KONTAK = {"NA": "NO", "NK": "NC"}       # normalde açık / kapalı
_NO_NUMARA = frozenset({"parca", "seri", "sira", "siparis", "kod", "model", "urun", "part", "serial", "item"})
_AKIM_TURU = {"vac": ("V", "AC"), "vdc": ("V", "DC")}

# I-1: büyük harfli sözcüklerden EN'de (büyük/küçük harf duyarsız, İ -> I katlanmış) geçmesi ZORUNLU olanlar:
#   (a) en çok 4 harfli kısaltma/kod sözcükleri (KRC, KCP, PLC, CPU, AC, DC, IE ...) — kısa Türkçe sözcükler hariç;
#   (b) bilinen marka/seri adları (SIMATIC, SITOP, SINAMICS ...; izin listesi markaları dahil).
# Ürün adları tamamen büyük harfle yazıldığından uzun Türkçe sözcükleri ayırt eden bir sözlük kurulamaz; bu yüzden
# uzun sözcüklerde yalnız bilinen ad listesi zorunludur (bilinen sınırlama: listede olmayan uzun seri adı denetlenmez).
_KISA_TR = frozenset({
    "ve", "ile", "icin", "guc", "yol", "yolu", "hat", "ray", "hiz", "bir", "uc", "iki", "tek", "ana", "alt", "ust",
    "sol", "sag", "hal", "kati", "blok", "kol", "kolu", "mil", "el", "faz", "kart", "role", "valf", "fan", "aku",
    "pil", "set", "seti", "tip", "tipi", "seri", "ag", "on", "arka", "yan", "ic", "dis", "kit", "uzun", "kisa",
    "adet", "veri", "aci", "acik", "raf", "kapi", "kasa", "kutu", "yuva", "pim", "cift", "orta", "kafa", "bas",
    "tam", "yari", "yeni", "eski", "gri", "mavi", "sari", "ince", "kaln", "isi", "isik", "gaz", "su", "yag",
    "hava", "bant", "saat", "ara", "uc", "ucu", "ucu", "ayar", "dur", "tus", "pin", "sac", "boru",
    "kok", "vana", "fren", "dis", "disi", "ici", "tutu", "kafa", "ag", "agi", "pano", "pul", "yay", "yayi", "tel",
    "teli", "bobi", "akim", "test", "sert", "yumu", "sabit", "kayi", "mod", "kod", "kodu", "tork", "eksi", "arti",
    "kuru", "islak", "sicak", "soğuk", "soguk", "hidr", "pnom", "tam", "lt", "adt", "mt", "nolu", "li",
    "lu", "lik", "luk", "ici", "basi", "ucu", "yeri", "eli", "eki", "ek", "gibi", "tum", "her", "cok", "az",
    "ozel", "ayna", "lens", "renk", "beyaz", "kare", "daire", "kesi", "taban", "bant", "zil", "ses", "goz",
    "ters", "vida", "itme", "duz", "dik", "acil", "stop", "tur", "turu", "bos", "dolu", "ayak",
    "alan", "top", "debi", "rot", "fani", "veya", "rayi", "mili", "ikiz", "aks", "adim", "yer", "sonu", "sivi",
    "saha", "rafi", "priz", "onlu", "mor", "kiri", "kap", "gres", "geri", "fon", "alti", "alin", "yuk", "kafa",
    "anma",
})
_KORUNAN_ADLAR = frozenset({
    *(normalize(p).upper() for _, gorunen in BILINEN_MARKALAR for p in re.split(r"[\s-]+", gorunen)),
    "SIMATIC", "SITOP", "SINAMICS", "SIMODRIVE", "SIMOTION", "SIMOTICS", "SINUMERIK", "SIRIUS", "SENTRON", "SIDAC",
    "SCALANCE", "LOGO", "MICROMASTER", "SIPLUS", "MOVIDRIVE", "MOVITRAC", "MOVIFIT", "MOVIMOT", "MOVISAFE",
    "INDRADRIVE", "INDRADYN", "INDRAMAT", "ECODRIVE", "COMBIVERT", "PROFIBUS", "PROFINET", "INTERBUS", "ETHERCAT",
    "DEVICENET", "MODBUS", "CANOPEN", "ETHERNET", "QUINT", "STRATIX", "TESYS", "TELEMECANIQUE", "ANYBUS", "IXXAT",
    "REXROTH", "EURODRIVE", "PHOENIX", "CONTACT", "BALLUFF", "EUCHNER", "WENGLOR", "BOSCH", "ATLAS", "COPCO",
    "SOMMER", "NEUGART", "FUCHS", "MOELLER", "PEPPERL", "TURCK", "SCHMALZ", "NORGREN", "RITTAL", "WITTENSTEIN",
    "SCHMERSAL", "DALMEC", "LEUZE", "CLECO", "TECNA", "KISTLER", "KOLLMORGEN", "ALLEN", "BRADLEY", "HIRSCHMANN",
    "LUMBERG", "BAUMULLER", "PARKER", "NUMATICS", "MEANWELL", "CLOOS", "HEIDENHAIN", "BAUMER", "BENDER", "NORATEL",
    "SENSOPART", "BURKERT", "SCHEUGENPFLUG", "TUNKERS", "PLASMATREAT", "EATON", "FLINTEC", "PROGLOVE", "HITACHI",
    "TRUMPF", "BEIJER", "RICOH", "TAMRON", "INTERMEC", "CROUZET", "HIWIN", "DEUBLIN", "PRESSOTECHNIK", "VICKERS",
    "LAMBDA", "KNICK", "MAGNESCALE", "KEITHLEY", "HERION", "FRAKO", "HARMS", "WENDE",
})


def _kanonik_metin(metin: str, tr: bool = False) -> str:
    s = unicodedata.normalize("NFC", metin)
    s = (s.replace("−", "-").replace("º", "°").replace("×", "x").replace("<=", "≤").replace(">=", "≥")
         .replace("μ", "µ"))
    s = re.sub(r"(?<=\d)[–—](?=\d)", "-", s)
    s = re.sub(r"(?<![\w.])[–—](?=\d)", "-", s)                         # eksi yerine yazılmış tire: "–25 °C"
    s = re.sub(r"(?<=\d)[\"″](?!\w)", "in", s)                            # 19" == 19 inch
    # binlik ayraç: TR'de yalnız nokta ("6.000" == "6000"); EN'de nokta ve virgül ("1,000" == "1.000" == "1000").
    # TR "1,500" (= 1,5) EN'de "1,500" kalırsa bin beş yüz okunur: eşleşmez, red.
    s = (_BINLIK_NOKTA if tr else _BINLIK_EN).sub(lambda m: re.sub(r"[.,]", "", m.group(0)), s)
    s = _ONDALIK.sub(".", s)
    s = _YUZDE_ONCE.sub(r"\1\2%", s)                                    # "%-15", "% +10", "%±5" -> "-15%"
    return _YUZDE_BOSLUK.sub(r"\1%", s)                                 # "0.01 %/K" -> "0.01%/K"


def _buyuk(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def _tr_sozcuk(s: str) -> bool:
    return all(normalize(p) in _KISA_TR or len(p) > 4 for p in re.split(r"[-/.!]+", s) if p)


_TR_BIRIM_KOKLERI = (("metre", "m"), ("amper", "A"), ("volt", "V"), ("watt", "W"), ("gram", "g"), ("saniye", "s"),
                     ("dakika", "min"), ("inc", ""))     # normalize edilmiş (ç -> c)


_TR_BIRIM_EKLI = re.compile("(" + "|".join(k for k, _ in _TR_BIRIM_KOKLERI) + ")"
                            r"(lik|luk|nin|nun|ye|ya|e|a|de|da|te|ta|den|dan|ten|tan|i|u|si|su|ler|lar)?")


def _birim(s: str) -> str | None:
    """Birim yazımı -> kanonik sembol (yoksa None). Önce tam (harf duyarlı) eşleşme. Değilse büyük/küçük harf
    duyarsız adaylar: M/m ön ekli (MW/mW, MHz/mHz ...) adayda ilk harf birebir aynı olmalı; yalnız tamamı büyük harf
    yazımda ("MHZ", "KW", "100 MA": TR adlarında yaygın) M önekli aday, yoksa tek aday seçilir."""
    if not s:
        return None
    if s in _BIRIM_TAM:
        return _BIRIM_TAM[s]
    adaylar = _BIRIM_KUCUK.get(s.lower(), set())
    if s.lower() in _BIRIM_SOZCUK and len(adaylar) == 1:
        return next(iter(adaylar))          # sözcük yazımı (Meter, METRE, Volts): harf duyarsız
    if adaylar:
        ayni = [k for k in adaylar if k[:1] == s[:1]]
        if len(ayni) == 1:
            return ayni[0]
        if s.isupper():
            buyuk = [k for k in adaylar if k[:1].isupper()]
            if len(buyuk) == 1:
                return buyuk[0]
            if len(adaylar) == 1:
                return next(iter(adaylar))
        elif len(adaylar) == 1 and next(iter(adaylar))[:1] not in "Mm":
            return next(iter(adaylar))      # "hz" -> Hz, "kv" -> kV (ön ek belirsizliği yok)
    m = _TR_BIRIM_EKLI.fullmatch(normalize(s))   # Türkçe ekli birim sözcüğü: "metrelik", "METRELİK", "amperlik"
    return dict(_TR_BIRIM_KOKLERI)[m[1]] if m else None


@dataclass
class _Jetonlar:
    sayi: Counter = field(default_factory=Counter)        # "on+sayi|birim" ya da ham kod
    birimsiz: Counter = field(default_factory=Counter)    # birimleri atılmış (birim kodu ayrımı için)
    buyuk: Counter = field(default_factory=Counter)       # korunacak büyük harfli sözcükler (büyük harfle)
    kontak: Counter = field(default_factory=Counter)      # N-3: NO / NC / COM (TR NA -> NO, NK -> NC), birebir


def _parcalar(metin: str) -> list[str]:
    return [p for p in _PARCA_AYIRICI.split(metin) if p]


def jetonlar(metin: str, tr: bool = False) -> _Jetonlar:
    if tr:
        metin = _IKINCI_EL.sub(" ", metin)
    parcalar = [p.strip(".:!?*") or p for p in _parcalar(_kanonik_metin(metin, tr))]
    j = _Jetonlar()
    i = 0

    def sayi_ekle(on: str, sayi: str, birim: str | None) -> None:
        j.sayi[f"{on}{sayi.upper()}|{birim or ''}"] += 1
        j.birimsiz[f"{on}{sayi.upper()}"] += 1

    while i < len(parcalar):
        p = parcalar[i]
        on = ""
        k = i
        while k < len(parcalar) and parcalar[k] in _KARSILASTIRMA:
            k += 1
        if k > i and k < len(parcalar) and re.match(r"[-+±]?\d", parcalar[k]):
            on = "".join(parcalar[i:k])           # "< 100 mV", "< ± 0.1%": ayrı yazılmış karşılaştırma
            i, p = k, parcalar[k]
        if p.endswith("-") and p[:-1][-1:].isdigit():
            p = p[:-1]                            # "4- or 6-wire"
        m = _SAYI.fullmatch(p)
        if m and not (m["birim"] and (m["y1"] or m["y2"])):
            on = on + m["on"]
            birim_ham = m["birim"] or ""
            if m["y1"] or m["y2"]:
                birim = "%"
            elif birim_ham.lower() in _AKIM_TURU:
                birim, tur = _AKIM_TURU[birim_ham.lower()]
                j.buyuk[tur] += 1
            elif birim_ham.lower() in _SIRA_EKI or (tr and normalize(birim_ham) in {normalize(x) for x in _TR_SAYI_EKI}):
                birim = None                       # "44th" == "44."
            elif birim_ham:
                birim = _birim(birim_ham)
                if birim is None:                 # "200S", "1U", "3AC": kod, ham
                    kod = _buyuk(on[:len(on) - len(m["on"])] + p)
                    j.sayi[kod] += 1
                    j.birimsiz[kod] += 1
                    i += 1
                    continue
            else:
                birim = None
                if i + 1 < len(parcalar):         # ayrı yazılmış birim: "24 V", "+60 °C", "15 %"
                    sonraki = parcalar[i + 1]
                    if sonraki.lower() in _AKIM_TURU:
                        birim, tur = _AKIM_TURU[sonraki.lower()]
                        j.buyuk[tur] += 1
                        i += 1
                    elif _birim(sonraki) is not None and sonraki.lower() not in _AYRIK_OLMAYAN_BIRIM - {"a", "s", "m", "g", "h", "t"}:
                        birim = _birim(sonraki)
                        i += 1
            sayi_ekle(on, m["sayi"], birim)
            i += 1
            continue
        m = _SAYI_SOZCUK.fullmatch(p) or _KOD_SOZCUK.fullmatch(p)
        if m and m.re is _SAYI_SOZCUK and _birim(m["soz"]) is not None:
            sayi_ekle(on, m["sayi"], _birim(m["soz"]))      # "19-inch"
            i += 1
            continue
        if m and m.re is _KOD_SOZCUK and not m["soz"].isupper():
            j.sayi[_buyuk(on + m["kod"])] += 1               # "1U-height" == "1U"
            j.birimsiz[_buyuk(on + m["kod"])] += 1
            i += 1
            continue
        if m and m.re is _SAYI_SOZCUK and (not m["soz"].isupper() or _tr_sozcuk(m["soz"])):
            sayi_ekle(on, m["sayi"], None)        # "3-phase", "1-FAZ", "40-pole"
            p = m["soz"]
        elif any(c.isdigit() for c in p):
            j.sayi[_buyuk(on + p)] += 1           # kod: ham, ayraçlar korunur
            j.birimsiz[_buyuk(on + p)] += 1
            i += 1
            continue
        onceki = normalize(parcalar[i - 1]) if i > 0 else ""
        for soz in re.split(r"[-/.!&+]+", p):
            if soz in _KONTAK or (tr and soz in _TR_KONTAK):
                if not (soz == "NO" and onceki in _NO_NUMARA):      # "PARÇA NO 12": numara kısaltması
                    j.kontak[_TR_KONTAK.get(soz, soz) if tr else soz] += 1
                continue
            if len(soz) >= 2 and soz.isalpha() and soz.isupper() and _birim(soz) is None and _zorunlu(soz):
                j.buyuk[_katla(soz)] += 1
        i += 1
    return j


def _katla(soz: str) -> str:
    """Karşılaştırma biçimi: İ -> I, büyük harf, Türkçe harfler katlanmış (SİEMENS == SIEMENS == Siemens)."""
    return normalize(soz).upper()


def _zorunlu(soz: str) -> bool:
    n = normalize(soz)
    if len(soz) <= 4:
        return n not in _KISA_TR and not re.search("[ğşçöüĞŞÇÖÜ]", soz)
    return n.upper() in _KORUNAN_ADLAR


def sayi_kod_jetonlari(metin: str, tr: bool = False) -> Counter[str]:
    """Geri uyum: metnin sayı/kod jetonları (birimli)."""
    return jetonlar(metin, tr).sayi


def markalar(metin: str) -> set[str]:
    """Metinde geçen tüm izin listesi markaları (görünen ad)."""
    n = _kat(metin or "")
    return {gorunen for desen, _, gorunen in _DESENLER if desen.search(n)}


_MARKA_JETONLARI = frozenset(normalize(p) for _, gorunen in BILINEN_MARKALAR for p in gorunen.split())


def _turkce_kalinti(metin: str, korunan: Iterable[str] = ()) -> bool:
    """korunan: TR kaynakta büyük harfle geçen ve korunması gereken sözcükler (EVOLUTİON gibi yazımlar dahil)."""
    korunan = set(korunan)
    for jeton in metin.split():
        if any(c.isdigit() for c in jeton):
            continue                                   # kod jetonu (Ç-200, 6ES7 ...)
        cekirdek = jeton.strip(".,;:()[]{}\"'/!")
        if normalize(cekirdek) in _MARKA_JETONLARI or all(
                w.isupper() and w in korunan and normalize(w) not in _TR_SIK
                for w in re.findall(r"[^\W\d_]+", cekirdek) if _TR_HARF.search(w)):
            continue
        if _TR_HARF.search(cekirdek):
            return True
    return any(k in _TR_SIK for k in _KELIME.findall(normalize(metin)))


# normalize edilmiş sık Türkçe sözcükler: EN çeviride kalırsa red (İngilizcede de geçebilenler yok: var, set, tip)
_TR_SIK = frozenset({
    "ve", "ile", "icin", "arasi", "yaklasik", "adet", "veya", "olan", "olarak", "degil", "yok", "giris", "cikis",
    "gerilim", "akim", "guc", "kaynagi", "surucu", "karti", "kablosu", "motoru", "agirlik", "sicaklik", "basinc",
    "uzunluk", "ikinci", "takim", "takimi", "parca", "parcasi", "seri", "serisi", "tipi", "boyut", "olcu",
    "kablo", "kart", "valf", "reduktor", "sigorta", "trafo", "kontaktor", "filtre", "kaynak",
})


def _bos(x: Any) -> bool:
    return not isinstance(x, str) or not x.strip()


def _karsilastir(tr: str, en: str, kodlar: set[str]) -> None:
    a, b = jetonlar(tr, tr=True), jetonlar(en)
    if a.sayi != b.sayi:
        kodlar.add("birim" if a.birimsiz == b.birimsiz else "sayi_kod")
    if a.kontak != b.kontak:
        kodlar.add("kod")
    if any(re.search(rf"(?<![\d.,]){re.escape(x)}(?![.,]?\d)", en) for x in _BINLIK_KESIN.findall(tr)):
        kodlar.add("binlik")    # N-5: TR'de kesin binlik ("1.000", "10.000.000") EN'de noktalı kaldı: 1 okunur
    en_sozcukler = {_katla(x) for x in re.findall(r"[^\W\d_]+", en)} | set(b.buyuk)
    en_sozcukler |= {x[:-1] for x in en_sozcukler if x.endswith("S")}    # LEDs, PLCs, CPUs
    eksik = [k for k in a.buyuk if k not in en_sozcukler]
    # akım türü: TR'deki AC/DC EN'de olmalı; TR'de yalnız biri varken EN'de karşıtı çıkarsa red. EN'nin "doğru akım"ı
    # DC diye yazması (TR'de sözcükle) serbest.
    if (any(k in ("AC", "DC") for k in eksik)
            or (a.buyuk["AC"] and not a.buyuk["DC"] and b.buyuk["DC"])
            or (a.buyuk["DC"] and not a.buyuk["AC"] and b.buyuk["AC"])):
        kodlar.add("birim")
    if any(k not in ("AC", "DC") for k in eksik):
        kodlar.add("kod")


def dogrula(kaynak: Mapping[str, Any], ceviri: Mapping[str, Any]) -> list[str]:
    ad = str(kaynak.get("ad") or "")
    tr_teknik = [(str(k), str(v)) for k, v in (kaynak.get("teknik") or [])]
    ad_en = ceviri.get("ad_en")
    teknik_en = ceviri.get("teknik_en")
    kodlar: set[str] = set()

    if _bos(ad_en):
        kodlar.add("bos")
        ad_en = ""
    ad_en = str(ad_en).strip()
    satirlar: list[tuple[str, str]] = []
    if teknik_en is not None:
        for satir in teknik_en:
            k, v = satir
            if _bos(k) or _bos(v):
                kodlar.add("bos")
            satirlar.append((str(k or ""), str(v or "")))

    if ad_en and not (AD_EN_AZ <= len(ad_en) <= AD_EN_COK and ORAN_EN_AZ * len(ad) <= len(ad_en) <= ORAN_EN_COK * len(ad)):
        kodlar.add("uzunluk")
    if teknik_en is not None and len(satirlar) != len(tr_teknik):
        kodlar.add("satir_sayisi")

    _karsilastir(ad, ad_en, kodlar)
    for (tk, tv), (ek, ev) in zip(tr_teknik, satirlar):
        _karsilastir(tk, ek, kodlar)          # M-4: anahtar ve değer ayrı ayrı
        _karsilastir(tv, ev, kodlar)

    # TR kaynakta aynen geçen büyük harfli sözcükler (SEW-EURODRİVE, EVOLUTİON gibi yazımlar) EN'de kalabilir
    korunan = {w for m in [ad, *(f"{k} {v}" for k, v in tr_teknik)] for w in re.findall(r"[^\W\d_]+", m)
               if w.isupper() and not re.search("[ĞŞÇÖÜ]", w)}
    if (_turkce_kalinti(ad_en, korunan)
            or any(_turkce_kalinti(f"{k} {v}", korunan) for k, v in satirlar)):
        kodlar.add("turkce_kalinti")
    if markalar(ad) != markalar(ad_en):
        kodlar.add("marka")
    return [k for k in KODLAR if k in kodlar]


def uyarilar(kaynak: Mapping[str, Any]) -> list[str]:
    """Ret olmayan uyarılar. binlik_ayrac: TR'de "1.000" / "1,500" gibi binlik ayraç olabilecek sayı (çeviride
    nokta/virgül dönüşümü anlamı değiştirebilir; istem ayraçsız ya da aynen yazmayı söyler)."""
    metinler = [str(kaynak.get("ad") or "")] + [f"{k} {v}" for k, v in (kaynak.get("teknik") or [])]
    belirsiz = (x for m in metinler for x in _BINLIK.findall(m) if not _BINLIK_KESIN.fullmatch(x))
    return ["binlik_ayrac"] if any(True for _ in belirsiz) else []
