"""G3k madde 21: LLM taslak açıklamasının (urun_aciklama.kaynak = 'llm-taslak') GÖSTERİM katmanı denetimi.

Veri silinmez, G3d/G3f betikleri ve doğrulayıcıları değişmez: bu yardımcı yalnız ürün sayfasında taslağın gösterilip
gösterilmeyeceğine karar verir. Gizlenen taslağın yerine G3i madde 14'ün olgusal bloğu gösterilir.

Kurallar:
- Metindeki her sayı + birim jetonu ("8.5 Nm", "24V", "0,5 A") ürün adında, parça no / stok kodunda ya da teknik
  verisinde (etiket ve değerler) de geçmelidir; ondalık virgül/nokta ve sayı ile birim arasındaki boşluk farkı yok.
- Hiçbir paragraf küçük harfle başlamaz (kesik sözcük: "ğır yük robot kollarının…"); paragraf başı tam sözcük.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

BIRIMLER = ("kVA", "VA", "kW", "KW", "kw", "mW", "W", "VAC", "VDC", "Vac", "Vdc", "mV", "kV", "V", "mA", "A", "Ah",
            "mAh", "Nm", "NM", "mm", "cm", "m", "kg", "Kg", "KG", "g", "kHz", "MHz", "Hz", "rpm", "RPM", "dev/dk", "bar",
            "Bar", "°C", "Ω", "ohm", "Ohm", "kOhm", "µF", "uF", "mH", "ms", "l/min", "L/min",
            # yazım çeşitleri (kanonik birime çevrilir): "480v", "4 Amp", "2.5 Watt", "24 Volt"
            "v", "Volt", "volt", "Watt", "watt", "Amp", "amp", "Amper", "amper", "metre", "meter", "metres", "meters",
            "Metre", "mt", "MT", "gr", "gram", "grams", "l/dk", "lt/dk", "L/dk", "Nl/min", "Nl/dk", "L/dakika",
            "l/dakika", "lt/dakika", "l/dak", "L/dak", "lt/dak", "MPa", "psi",
            # fix 1 m-1: "100M" (metre), "nm", "mm²", "litre/dakika", Türkçe ekli metre
            "M", "nm", "mm²", "litre/dakika", "litre/dk", "metreye", "metrelik", "metrede", "metreden")
KANONIK = {"volt": "v", "watt": "w", "amp": "a", "amper": "a", "Ω": "ohm", "uf": "µf", "dev/dk": "rpm", "metre": "m",
           "meter": "m", "metres": "m", "meters": "m", "mt": "m", "gr": "g", "gram": "g", "grams": "g", "l/dk": "l/min",
           "lt/dk": "l/min", "nl/min": "l/min", "nl/dk": "l/min",
           "l/dakika": "l/min", "lt/dakika": "l/min", "l/dak": "l/min", "lt/dak": "l/min",
           "vdc": "v", "vac": "v", "litre/dakika": "l/min", "litre/dk": "l/min", "metreye": "m", "metrelik": "m",
           "metrede": "m", "metreden": "m"}
_BIRIM = "|".join(re.escape(b) for b in sorted(BIRIMLER, key=len, reverse=True))
# sayıdan önce rakam/nokta yok, birimden sonra harf yok. fix 1 m-1: önünde harf olabilir ("DC24V", "3x400V"),
# virgül olabilir ("3 kV,50 Hz"); binlik ayraçlı sayı ("1.500 rpm") tek sayı
SAYI_BIRIM = re.compile(rf"(?<![\d.])(\d{{1,3}}(?:\.\d{{3}})+(?![\d,])|\d+(?:[.,]\d+)?)\s?({_BIRIM})(?![^\W\d_])")
_BINLIK = re.compile(r"\d{1,3}(?:\.\d{3})+")
_PARAGRAF = re.compile(r"\n\s*\n")
_SOZCUK = re.compile(r"\w+")


def _jeton(sayi: str, birim: str) -> str:
    b = birim.lower()
    sayi = sayi.replace(".", "") if _BINLIK.fullmatch(sayi) else sayi.replace(",", ".")
    return sayi + KANONIK.get(b, KANONIK.get(birim, b))


def sayi_birim_jetonlari(metin: str | None) -> set[str]:
    return {_jeton(s, b) for s, b in SAYI_BIRIM.findall(metin or "")}


def _kaynak_jetonlari(kaynaklar: Iterable[str | None]) -> set[str]:
    jetonlar: set[str] = set()
    for k in kaynaklar:
        jetonlar |= sayi_birim_jetonlari(k)
    return jetonlar


def taslak_gosterilir(metin: str, adlar: Iterable[str | None], teknik: Iterable[str | None]) -> bool:
    """adlar: ürün adı (TR/EN), SKU, üretici kodu; teknik: teknik veri etiket ve değerleri (düz metin)."""
    adlar = [a for a in adlar if a]
    kaynak = _kaynak_jetonlari([*adlar, *teknik])
    if not sayi_birim_jetonlari(metin) <= kaynak:
        return False
    # küçük harfle başlayan paragraf yalnız ilk sözcüğü ürün adında/kodunda da geçiyorsa (ör. "ifm" markası) kabul
    ad_sozcukleri = {w.casefold() for a in adlar for w in _SOZCUK.findall(a)}
    for paragraf in _PARAGRAF.split(metin.strip()):
        ilk = _SOZCUK.match(paragraf.lstrip())
        if ilk and ilk.group(0)[0].isalpha() and ilk.group(0)[0].islower() and ilk.group(0).casefold() not in ad_sozcukleri:
            return False
    return True
