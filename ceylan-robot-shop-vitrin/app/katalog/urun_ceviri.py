"""G3f: ürün adı ve teknik özelliklerin EN çevirisi (urun_ceviri tablosu, geçiş 010) — okuma ve geçerlilik.

Çeviri yalnız `kaynak_ozet` ürünün GÜNCEL TR adı + teknik satırlarıyla (urun_teknik.ozellikler) tutuyorsa geçerlidir;
eşitleme adı ya da teknik veriyi değiştirince çeviri kendiliğinden gösterilmez olur (tablo silinmez, yeniden üretilir).
teknik_json TR satır sayısıyla aynı sayıda geçerli çift değilse yalnız ad kullanılır.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

DIL = "en"
_PARCA = 500


def _ciftler(x: object) -> list[tuple[str, str]]:
    if not isinstance(x, list):
        return []
    return [(a, b) for a, b in (p for p in x if isinstance(p, list) and len(p) == 2)
            if isinstance(a, str) and isinstance(b, str)]


def teknik_satirlari(veri: str | None) -> list[tuple[str, str]]:
    """urun_teknik.veri -> özellik satırları (app.katalog.depo.teknik_getir ile aynı süzme)."""
    if not veri:
        return []
    try:
        d = json.loads(veri)
    except (ValueError, TypeError):
        return []
    return _ciftler(d.get("ozellikler")) if isinstance(d, dict) else []


def kaynak_ozeti(ad: str, teknik: Iterable[Sequence[str]]) -> str:
    """TR ad + teknik satırlarının sha256'sı (ilk 16 hex). Sıra ve boşluk dahil birebir."""
    veri = json.dumps([ad, [[str(k), str(v)] for k, v in teknik]], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(veri.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class UrunCeviri:
    ad: str
    teknik: tuple[tuple[str, str], ...] | None    # None: yalnız ad çevrildi (ya da satırlar tutmuyor)
    kaynak: str                                   # 'llm-taslak' | 'kaynak'
    model: str | None

    @property
    def taslak(self) -> bool:
        return self.kaynak == "llm-taslak"


_SORGU = (
    "SELECT c.urun_id, c.ad, c.teknik_json, c.kaynak, c.model, c.kaynak_ozet, u.ad AS tr_ad, t.veri"
    " FROM urun_ceviri c JOIN urun u ON u.id = c.urun_id LEFT JOIN urun_teknik t ON t.urun_id = c.urun_id"
    " WHERE c.dil = ?"
)


def _gecerli(r: sqlite3.Row | tuple, teknik_gerekli: bool = True) -> UrunCeviri | None:
    _, ad, teknik_json, kaynak, model, ozet, tr_ad, veri = tuple(r)
    if not (ad or "").strip():
        return None
    tr_teknik = teknik_satirlari(veri)
    if ozet != kaynak_ozeti(tr_ad, tr_teknik):
        return None
    teknik = None
    if teknik_gerekli and teknik_json and tr_teknik:
        try:
            satirlar = _ciftler(json.loads(teknik_json))
        except (ValueError, TypeError):
            satirlar = []
        if len(satirlar) == len(tr_teknik):
            teknik = tuple(satirlar)
    return UrunCeviri(ad=ad.strip(), teknik=teknik, kaynak=kaynak, model=model)


def ceviriler_getir(con: sqlite3.Connection, urun_idleri: Iterable[int] | None, dil: str = DIL,
                    teknik: bool = True) -> dict[int, UrunCeviri]:
    """Ürünlerin GEÇERLİ çevirileri (urun_id -> UrunCeviri); urun_idleri None ise tüm ürünler. TR'de boş.
    teknik=False: yalnız ad gerekir (arama indeksi), teknik_json ayrıştırılmaz (UrunCeviri.teknik None)."""
    if dil != DIL:
        return {}
    sonuc: dict[int, UrunCeviri] = {}
    if urun_idleri is None:
        parcalar: list[list[int]] = [[]]
    else:
        idler = list(dict.fromkeys(i for i in urun_idleri if isinstance(i, int)))
        if not idler:
            return {}
        parcalar = [idler[i:i + _PARCA] for i in range(0, len(idler), _PARCA)]
    for parca in parcalar:
        sql, arg = _SORGU, [dil]
        if urun_idleri is not None:
            sql += f" AND c.urun_id IN ({','.join('?' * len(parca))})"
            arg += parca
        for r in con.execute(sql, arg):
            c = _gecerli(r, teknik)
            if c is not None:
                sonuc[int(r[0])] = c
    return sonuc
