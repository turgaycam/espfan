"""G3c madde 23: kategori adı çevirisi (EN arayüz). Kaynak: kategori_ceviri.yaml (elle çevrilmiş; anahtar Türkçe ad).

Eşleme app.metin.normalize ile yapılır: veri kaynağındaki "DIGER" / "DİĞER", "ISLEME" / "İŞLEME" gibi yazım farkları
aynı çeviriye düşer. Türkçe arayüzde ad olduğu gibi kalır; çevirisi olmayan ad EN arayüzde ham haliyle döner
(şablon lang="tr" ile işaretler)."""
from __future__ import annotations

from pathlib import Path

import yaml

from app.katalog.marka import BILINEN_MARKALAR
from app.metin import normalize

VARSAYILAN_YOL = Path(__file__).parent / "kategori_ceviri.yaml"

# G3e madde 19: EN arayüzde tamamı BÜYÜK HARF adlar gösterimde Title Case olur (veri değişmez).
_KUCUK_KELIMELER = {"and", "or", "of", "for", "with", "the", "in", "to", "ve", "ile", "veya"}
_BIRIMLER = {"KG": "kg"}
_KISALTMALAR = {"LED", "IRB", "I/O", "PCS"}
_MARKA_YAZIMI = {gorunen.upper(): gorunen for _, gorunen in BILINEN_MARKALAR if " " not in gorunen}
_SESLI = set("AEIOUYÄÖÜÂÎÛÇŞĞİI")


def _tr_kucuk(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def _tr_buyuk_bas(s: str) -> str:
    if not s:
        return s
    ilk = {"i": "İ", "ı": "I"}.get(s[0], s[0].upper())
    return ilk + s[1:]


def baslik_bicimi(metin: str, turkce: bool = False) -> str:
    """Tamamı büyük harf adı Title Case yapar; içinde küçük harf olan ad olduğu gibi kalır. Marka yazımları (ABB, KUKA,
    Yaskawa), rakam içeren kodlar (KRC4, C4), sesli harfsiz kısaltmalar (PLC, CNC) ve iki harfli kodlar (KR) korunur;
    bağlaçlar (and, of, ve) küçük; turkce=True: Türkçe büyük/küçük harf kuralı (I -> ı, İ -> i)."""
    if not metin or any(c.islower() for c in metin):
        return metin
    sonuc = []
    for i, kelime in enumerate(metin.split(" ")):
        cekirdek = kelime.strip(".,()/&-")
        if not cekirdek:
            sonuc.append(kelime)
        elif i > 0 and cekirdek.lower() in _KUCUK_KELIMELER:
            sonuc.append(kelime.lower())
        elif cekirdek in _BIRIMLER:
            sonuc.append(kelime.replace(cekirdek, _BIRIMLER[cekirdek]))
        elif cekirdek in _MARKA_YAZIMI:
            sonuc.append(kelime.replace(cekirdek, _MARKA_YAZIMI[cekirdek]))
        elif (any(c.isdigit() for c in cekirdek) or cekirdek in _KISALTMALAR or len(cekirdek) <= 2
              or (len(cekirdek) <= 4 and not _SESLI.intersection(cekirdek))):
            sonuc.append(kelime)
        elif turkce:
            sonuc.append(_tr_buyuk_bas(_tr_kucuk(kelime)))
        else:
            sonuc.append(kelime[:1] + kelime[1:].replace("İ", "i").lower())
    return " ".join(sonuc)


class KategoriCeviri:
    def __init__(self, yol: Path = VARSAYILAN_YOL) -> None:
        ham = yaml.safe_load(Path(yol).read_text(encoding="utf-8")) or {}
        self._tablo: dict[str, dict[str, str]] = {}
        for dil, ciftler in ham.items():
            self._tablo[str(dil)] = {normalize(str(tr)): str(karsilik).strip()
                                     for tr, karsilik in (ciftler or {}).items() if str(karsilik).strip()}

    def cevir(self, ad: str | None, dil: str) -> str | None:
        """Çeviri varsa karşılığı, yoksa None. Türkçe arayüzde her zaman None (ad kendisidir)."""
        if not ad or dil == "tr":
            return None
        return self._tablo.get(dil, {}).get(normalize(ad))

    def metin(self, ad: str | None, dil: str) -> str:
        """Düz metin (başlık, meta, öznitelik, JSON-LD): çeviri yoksa ham ad. G3e madde 19: EN'de tamamı büyük harf
        ad (çeviri ya da ham Türkçe ad) Title Case gösterilir; TR arayüzde ad değişmez."""
        if dil == "tr":
            return ad or ""
        ceviri = self.cevir(ad, dil)
        return baslik_bicimi(ceviri) if ceviri else baslik_bicimi(ad or "", turkce=True)

    def cevrilmis_mi(self, ad: str | None, dil: str) -> bool:
        return dil == "tr" or self.cevir(ad, dil) is not None
