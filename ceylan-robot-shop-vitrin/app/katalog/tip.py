"""G3h madde 5: ürün tipi sınıflaması (app/katalog/tip.yaml). Saf fonksiyonlar (veritabanı yok).

tip_bul: önce ürün adı, sonra kategori yolu (yapraktan köke) sırayla kurallarla denenir; ilk eşleşen tip kazanır,
yoksa "diger". sorgu_tipi: arama metni yalnız kurallarla eşleşirse tip (alaka sırası için), yoksa None.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

from app.metin import normalize

TIP_YOLU = Path(__file__).parent / "tip.yaml"
DIGER = "diger"
_AYRAC = re.compile(r"[\W_]+")


@dataclass(frozen=True)
class Tip:
    anahtar: str
    tr: str
    en: str
    desen: re.Pattern | None      # "diger" için None


def katla(metin: str | None) -> str:
    """normalize + harf/rakam dışı karakterler tek boşluk; başta/sonda boşluk (kelime sınırı için)."""
    return " " + _AYRAC.sub(" ", normalize(metin or "")).strip() + " "


def _desen(kelimeler: Sequence[str]) -> re.Pattern:
    parcalar = []
    for k in kelimeler:
        k = str(k).strip()
        onek = k.endswith("*")
        govde = katla(k.rstrip("*")).strip()
        if not govde:
            continue
        parcalar.append(" " + re.escape(govde) + ("" if onek else " "))
    return re.compile("|".join(parcalar))


@cache
def _kurallar() -> tuple[Tip, ...]:
    """Kural sırasıyla tüm kurallar ("diger" anahtarlı erken kurallar dahil) + kuralsız son "diger"."""
    ham = yaml.safe_load(TIP_YOLU.read_text(encoding="utf-8")) or {}
    diger = ham.get("diger") or {}
    diger_tr, diger_en = str(diger.get("tr", "Diğer")), str(diger.get("en", "Other"))
    sonuc = []
    for t in ham.get("tipler") or []:
        anahtar = str(t["anahtar"])
        tr, en = (diger_tr, diger_en) if anahtar == DIGER else (str(t["tr"]), str(t["en"]))
        sonuc.append(Tip(anahtar, tr, en, _desen(t.get("kelimeler") or [])))
    sonuc.append(Tip(DIGER, diger_tr, diger_en, None))
    return tuple(sonuc)


@cache
def tipler() -> tuple[Tip, ...]:
    """Faset sırasıyla tekil tipler (yaml sırası); son öğe "diger"."""
    gorulen: dict[str, Tip] = {}
    for t in _kurallar():
        if t.anahtar != DIGER:
            gorulen.setdefault(t.anahtar, t)
    return (*gorulen.values(), _kurallar()[-1])


@cache
def _tip_haritasi() -> dict[str, Tip]:
    return {t.anahtar: t for t in tipler()}


def tip_adi(anahtar: str, dil: str) -> str:
    t = _tip_haritasi().get(anahtar)
    if t is None:
        return anahtar
    return t.en if dil == "en" else t.tr


def gecerli_mi(anahtar: str) -> bool:
    return anahtar in _tip_haritasi()


def _eslesen(metin: str) -> str | None:
    k = katla(metin)
    for t in _kurallar():
        if t.desen is not None and t.desen.pattern and t.desen.search(k):
            return t.anahtar
    return None


def tip_bul(ad: str | None, kategori_adlari: Sequence[str] = ()) -> str:
    """Ürün tipi: ad, sonra kategori adları (yaprak -> kök sırasıyla verilmeli)."""
    for metin in (ad, *kategori_adlari):
        if metin:
            bulunan = _eslesen(metin)
            if bulunan:
                return bulunan
    return DIGER


def sorgu_tipi(arama: str | None) -> str | None:
    """Arama metninin tipi (ör. "servo motor" -> servo_motor; "fanuc" -> None)."""
    tip = _eslesen(arama) if arama and arama.strip() else None
    return None if tip == DIGER else tip
