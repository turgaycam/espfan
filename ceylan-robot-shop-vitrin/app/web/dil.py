"""TR/EN arayüz metinleri ve dil yol dönüştürücüsü."""
from __future__ import annotations

import json
from pathlib import Path

from starlette.convertors import Convertor, register_url_convertor

DILLER = ("tr", "en")


class DilConvertor(Convertor):
    """`/{dil:dil}/...` yalnız tr|en ile eşleşir; diğer önekler rotaya hiç düşmez (404)."""

    regex = "tr|en"

    def convert(self, value: str) -> str:
        return value

    def to_string(self, value: str) -> str:
        return str(value)


register_url_convertor("dil", DilConvertor())


class _Eksiksiz(dict):
    """str.format_map ile doldurma; verilmeyen yer tutucu olduğu gibi kalır."""

    def __missing__(self, anahtar: str) -> str:
        return "{" + anahtar + "}"


class Ceviri:
    def __init__(self, klasor: Path) -> None:
        self._metinler: dict[str, dict[str, str]] = {}
        for dil in DILLER:
            dosya = Path(klasor) / f"{dil}.json"
            self._metinler[dil] = json.loads(dosya.read_text(encoding="utf-8")) if dosya.exists() else {}

    def var(self, anahtar: str) -> bool:
        return anahtar in self._metinler["tr"]

    def t(self, dil: str, anahtar: str, **degerler) -> str:
        metin = self._metinler.get(dil, {}).get(anahtar)
        if metin is None:
            metin = self._metinler["tr"].get(anahtar)
        if metin is None:
            return anahtar
        if degerler:
            try:
                metin = metin.format_map(_Eksiksiz(degerler))
            except (ValueError, IndexError):
                pass
        return metin

    def eksik_anahtarlar(self) -> dict[str, list[str]]:
        tr = set(self._metinler["tr"])
        en = set(self._metinler["en"])
        return {"tr": sorted(en - tr), "en": sorted(tr - en)}
