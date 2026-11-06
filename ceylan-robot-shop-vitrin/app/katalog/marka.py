"""Ürün adından marka çıkarma: bilinen üretici markaları izin listesi.

Saf fonksiyon (veritabanı/ağ yok). G2'de başlık ve JSON-LD `brand`, G3'te marka fasetleri kullanır.
Ad içinde kelime sınırıyla eşleşen bilinen marka aranır; birden çok eşleşme varsa adda en erken geçen kazanır
(eşit konumda daha uzun/çok kelimeli marka önce). Eşleşme yoksa marka YOK (`None`): "RÖLE MODÜLÜ 24V" gibi
jenerik adlar yanlış marka üretmez.
Liste tek yerde: BILINEN_MARKALAR = (aranan ad, görünen ad). Aranan ad küçük harf/ASCII katlanmış yazılır;
boşluk ve tire eşleşmede birbirinin yerine geçer.
"""
from __future__ import annotations

import re
import unicodedata

from app.metin import normalize

BILINEN_MARKALAR: tuple[tuple[str, str], ...] = (
    ("abb", "ABB"), ("kuka", "KUKA"), ("fanuc", "FANUC"), ("yaskawa", "Yaskawa"), ("motoman", "Motoman"),
    ("nachi", "Nachi"), ("kawasaki", "Kawasaki"), ("staubli", "Stäubli"), ("comau", "Comau"),
    ("universal robots", "Universal Robots"), ("siemens", "Siemens"), ("schneider", "Schneider Electric"),
    ("omron", "Omron"), ("mitsubishi", "Mitsubishi"), ("festo", "Festo"), ("smc", "SMC"), ("pilz", "Pilz"),
    ("sick", "SICK"), ("phoenix contact", "Phoenix Contact"), ("wago", "WAGO"), ("beckhoff", "Beckhoff"),
    ("bosch rexroth", "Bosch Rexroth"), ("allen-bradley", "Allen-Bradley"), ("rockwell", "Rockwell"),
    ("panasonic", "Panasonic"), ("lenze", "Lenze"), ("sew", "SEW"), ("danfoss", "Danfoss"), ("atos", "Atos"),
    ("asco", "ASCO"), ("aventics", "Aventics"), ("autonics", "Autonics"), ("advantech", "Advantech"),
    ("borunte", "Borunte"), ("kromer", "Kromer"), ("ifm", "ifm"), ("balluff", "Balluff"), ("harting", "Harting"),
    ("lapp", "LAPP"), ("igus", "igus"), ("schunk", "Schunk"), ("zimmer", "Zimmer"), ("keyence", "Keyence"),
    ("cognex", "Cognex"),
)


def _kat(metin: str) -> str:
    """Küçük harf, Türkçe İ/I doğru, aksanlar atılmış (ä -> a)."""
    n = unicodedata.normalize("NFKD", normalize(metin))
    return "".join(c for c in n if not unicodedata.combining(c))


def _desen(anahtar: str) -> re.Pattern[str]:
    kelimeler = re.split(r"[\s\-]+", anahtar)
    return re.compile(r"(?<![a-z0-9])" + r"[\s\-]+".join(map(re.escape, kelimeler)) + r"(?![a-z0-9])")


_DESENLER = tuple((_desen(anahtar), anahtar, gorunen) for anahtar, gorunen in BILINEN_MARKALAR)


def marka_cikar(ad: str | None) -> str | None:
    if not ad or not ad.strip():
        return None
    metin = _kat(ad)
    en_iyi: tuple[int, int, str] | None = None
    for desen, anahtar, gorunen in _DESENLER:
        m = desen.search(metin)
        if m is None:
            continue
        aday = (m.start(), -len(anahtar), gorunen)
        if en_iyi is None or aday < en_iyi:
            en_iyi = aday
    return en_iyi[2] if en_iyi else None
