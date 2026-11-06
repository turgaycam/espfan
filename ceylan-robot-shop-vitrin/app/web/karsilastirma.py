"""G3c madde 24: karşılaştırma listesi (oturumda en fazla AZAMI ürün kimliği, eklenme sırasıyla). Veritabanına yazmaz.
G3h madde 9: teknik özellik adlarının karşılaştırma anahtarı (ozellik_anahtari)."""
from __future__ import annotations

import re
import sqlite3
from functools import cache
from pathlib import Path

import yaml
from fastapi import Request

from app.metin import normalize

OTURUM_ANAHTARI = "karsilastir"
AZAMI = 5                     # G3h madde 11 (önce 3)
OZELLIK_ESANLAM_YOLU = Path(__file__).resolve().parent.parent / "katalog" / "ozellik_esanlam.yaml"
# G3h inceleme C-1: yalnız etiketin kendisini öbür dilde tekrarlayan ekler atılır (beyaz liste). Ek -> etikette
# bulunması gereken kelimeler (normalize): "Giriş Voltajı (Input)", "Input Voltage (Giriş)", "Input Voltage (Input)".
# Nitelik/birim/eksen ekleri ("(Statik)", "(Nominal)", "(kW)", "(AC)", "(MA,MB)", "(G x Y x D)") asla atılmaz.
DIL_EKLERI = {
    "input": ("giris", "input"), "output": ("cikis", "output"),
    "giris": ("giris", "input"), "cikis": ("cikis", "output"),
}
_SON_PARANTEZ = re.compile(r"^(.*?)\s*\(\s*([^()]*?)\s*\)\s*$")


def etiket_temizle(etiket: str) -> str:
    """Satır etiketi: yalnız beyaz listedeki dil eki atılmış ad (ör. "Giriş Voltajı (Input)" -> "Giriş Voltajı")."""
    temiz = etiket.strip()
    m = _SON_PARANTEZ.match(temiz)
    if m and m.group(1):
        kelimeler = normalize(m.group(1)).split()
        gerekli = DIL_EKLERI.get(normalize(m.group(2)))
        if gerekli and any(k.startswith(g) for k in kelimeler for g in gerekli):
            return m.group(1).strip()
    return temiz


@cache
def _ozellik_esanlam() -> dict[str, str]:
    ham = yaml.safe_load(OZELLIK_ESANLAM_YOLU.read_text(encoding="utf-8")) or {}
    sozluk: dict[str, str] = {}
    for grup in ham.get("gruplar") or []:
        adlar = [normalize(etiket_temizle(str(x))) for x in grup]
        for ad in adlar:
            sozluk.setdefault(ad, adlar[0])
    return sozluk


def ozellik_anahtari(etiket: str) -> str:
    """Karşılaştırmada aynı satıra düşen özellik adları aynı anahtarı verir (ek atılır, açık eşanlamlılar birleşir)."""
    n = normalize(etiket_temizle(etiket))
    return _ozellik_esanlam().get(n, n)


def _oturum(request: Request) -> dict:
    return request.session if "session" in request.scope else {}


def liste(request: Request) -> list[int]:
    """Oturumdaki kimlikler (bozuk/yinelenen değerler atılır, en fazla AZAMI)."""
    sonuc: list[int] = []
    for x in _oturum(request).get(OTURUM_ANAHTARI) or []:
        if isinstance(x, int) and not isinstance(x, bool) and 0 < x < 2**62 and x not in sonuc:
            sonuc.append(x)
    return sonuc[-AZAMI:]


def _yaz(request: Request, kimlikler: list[int]) -> None:
    if "session" not in request.scope:
        return
    if kimlikler:
        request.session[OTURUM_ANAHTARI] = kimlikler
    else:
        request.session.pop(OTURUM_ANAHTARI, None)


def ekle(request: Request, urun_id: int) -> tuple[bool, int | None]:
    """(eklendi mi, listeden çıkan en eski kimlik). Zaten listedeyse (False, None)."""
    kimlikler = liste(request)
    if urun_id in kimlikler:
        return False, None
    kimlikler.append(urun_id)
    cikan = kimlikler.pop(0) if len(kimlikler) > AZAMI else None
    _yaz(request, kimlikler)
    return True, cikan


def kaldir(request: Request, urun_id: int) -> None:
    _yaz(request, [x for x in liste(request) if x != urun_id])


def temizle(request: Request) -> None:
    _yaz(request, [])


def aktifler(request: Request, con: sqlite3.Connection) -> list[int]:
    """Listede kalan AKTİF ürünler (sıra korunur). Pasifleşen ya da silinen ürün listeden düşer, oturum güncellenir."""
    kimlikler = liste(request)
    if not kimlikler:
        return []
    yer = ",".join("?" * len(kimlikler))
    var = {r[0] for r in con.execute(f"SELECT id FROM urun WHERE aktif = 1 AND id IN ({yer})", kimlikler)}
    kalan = [x for x in kimlikler if x in var]
    if kalan != (_oturum(request).get(OTURUM_ANAHTARI) or []):
        _yaz(request, kalan)
    return kalan


_KOD_DISI = re.compile(r"[^a-z0-9]")


def tip_parca_no_ayni(etiket: str, deger: str, parca_no: str | None) -> bool:
    """G3n madde 12 / 15: kaynaktaki "Type" / "Tip" satırı ürünün parça numarasını tekrarlıyorsa (ayraçlar ve büyük/
    küçük harf yok sayılarak) bilgi taşımaz: ürün sayfasında gösterilmez, CSV teknik_tip hücresi boş."""
    if normalize(etiket_temizle(etiket)) not in ("type", "tip") or not parca_no:
        return False
    return _KOD_DISI.sub("", normalize(deger)) == _KOD_DISI.sub("", normalize(parca_no)) != ""
