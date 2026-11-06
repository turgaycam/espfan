"""API görselleri: base64 -> içerik adresli yerel webp dosyaları (k: 320 px, b: 1000 px)."""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import os
import re
import sqlite3
import time
import warnings
from pathlib import Path

from PIL import Image, ImageOps

BOYLAR = {"k": (320, 78), "b": (1000, 82)}      # klasör -> (en uzun kenar, webp kalitesi)
AD_DESENI = re.compile(r"[0-9a-f]{32}\.webp")
ON_EK = "gorsel:"
EN_COK_BAYT = 5 * 1024 * 1024
KISA_YOL_SINIRI = 500
MAKS_PIKSEL = 20_000_000          # 20 MP RGB ~ 60 MB; deflate'li tek renk PNG/WebP 5 MB altına sığar
Image.MAX_IMAGE_PIXELS = MAKS_PIKSEL
FORMATLAR = ["JPEG", "PNG", "WEBP"]
GECICI_DESENI = re.compile(r"[0-9a-f]{32}\.webp\.\d+\.tmp")
ESKI_GECICI_SN = 3600
# Pillow açma/çözme hataları; yazma hataları (PermissionError, disk dolu) ve MemoryError bunlara girmez
_COZME_HATALARI = (OSError, ValueError, SyntaxError, EOFError, Image.DecompressionBombError,
                   Image.DecompressionBombWarning)
_BASE64_DISI = re.compile(r"[^A-Za-z0-9+/=]")
_UZANTILI = re.compile(r"\.(jpg|png|webp)$", re.IGNORECASE)
_BOSLUK = re.compile(r"\s+")
_DATA_ON_EK = re.compile(r"^data:image/[A-Za-z0-9.+-]+;base64,", re.IGNORECASE)


def kisa_yol_mu(deger: str) -> bool:
    """'/' ile başlayan kısa yol (base64 değil)."""
    s = _BOSLUK.sub("", deger)
    return (s.startswith("/") and len(s) <= KISA_YOL_SINIRI
            and (bool(_BASE64_DISI.search(s)) or bool(_UZANTILI.search(s))))


def base64_mu(deger: str) -> bool:
    """Alan URL/yol değilse base64 sayılır (ekranlar bunu src'ye basmaz)."""
    return not deger.startswith(("http://", "https://")) and not kisa_yol_mu(deger)


def yerel_ad(deger: str | None) -> str | None:
    """'gorsel:<ad>' saklama biçiminden dosya adını döner; biçim bozuksa None."""
    if deger and deger.startswith(ON_EK) and AD_DESENI.fullmatch(deger[len(ON_EK):]):
        return deger[len(ON_EK):]
    return None


def _coz(deger: str) -> bytes | None:
    deger = _DATA_ON_EK.sub("", deger.strip(), count=1)
    deger = _BOSLUK.sub("", deger)
    if not deger or len(deger) > EN_COK_BAYT * 4 // 3 + 8:
        return None
    try:
        bayt = base64.b64decode(deger, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(bayt) > EN_COK_BAYT:
        return None
    if bayt[:3] == b"\xff\xd8\xff" or bayt[:4] == b"\x89PNG" or (bayt[:4] == b"RIFF" and bayt[8:12] == b"WEBP"):
        return bayt
    return None


def _atomik_yaz(yol: Path, icerik: bytes) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name(f"{yol.name}.{os.getpid()}.tmp")
    try:
        gecici.write_bytes(icerik)
        os.replace(gecici, yol)
    finally:
        gecici.unlink(missing_ok=True)


def _coz_goruntu(bayt: bytes) -> Image.Image | None:
    """Çözme aşaması: en uzun kenarı en çok 1000 px, yönü düzeltilmiş RGB görüntü. Pillow açamazsa
    ya da görüntü çok büyükse None. Yazma ve bellek hataları buradan geçer (yakalanmaz)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(bayt), formats=FORMATLAR) as im:
                if im.width * im.height > MAKS_PIKSEL:
                    return None
                if im.format == "JPEG":
                    im.draft("RGB", (1000, 1000))     # çözümde küçült
                im.load()
                if im.mode in ("RGBA", "LA", "P", "PA") or "transparency" in im.info:
                    rgba = im.convert("RGBA")
                    zemin = Image.new("RGB", rgba.size, "white")
                    zemin.paste(rgba, mask=rgba.getchannel("A"))
                    rgba.close()
                    taban = zemin
                    taban.info.update({k: v for k, v in im.info.items() if k == "exif"})
                elif im.mode != "RGB":
                    taban = im.convert("RGB")
                    taban.info.update({k: v for k, v in im.info.items() if k == "exif"})
                else:
                    taban = im.copy()                 # with bloğu kapanınca im geçersiz olur
            taban.thumbnail((1000, 1000), Image.Resampling.LANCZOS)   # önce küçült, sonra yönlendir
            ImageOps.exif_transpose(taban, in_place=True)
            return taban
    except _COZME_HATALARI:
        return None


def _uret(taban: Image.Image, hedefler: dict[str, Path]) -> None:
    for boy, yol in hedefler.items():
        kenar, kalite = BOYLAR[boy]
        kopya = taban.copy()
        kopya.thumbnail((kenar, kenar), Image.Resampling.LANCZOS)
        tampon = io.BytesIO()
        kopya.save(tampon, "WEBP", quality=kalite)
        _atomik_yaz(yol, tampon.getvalue())   # yazma hatası (OSError) yükselir: tur 'hata' olur


def base64_kaydet(deger: str, gorsel_dizin: Path | None) -> str | None:
    """Base64 görseli iki webp'e çevirir; 'gorsel:<ad>' döner. Geçersizse ya da klasör
    verilmemişse None (ürün görselsiz kalır, bozuk sayılmaz). Dosya yazma hataları yükselir."""
    if gorsel_dizin is None:
        return None
    bayt = _coz(deger)
    if bayt is None:
        return None
    ad = hashlib.sha256(bayt).hexdigest()[:32] + ".webp"
    eksik = {b: gorsel_dizin / b / ad for b in BOYLAR if not (gorsel_dizin / b / ad).is_file()}
    if eksik:
        taban = _coz_goruntu(bayt)
        if taban is None:
            return None
        try:
            _uret(taban, eksik)
        finally:
            taban.close()
    return ON_EK + ad


def eski_gecicileri_sil(gorsel_dizin: Path) -> None:
    """SIGKILL gibi kesintilerde kalan, 1 saatten eski kendi geçici dosyalarımızı siler."""
    sinir = time.time() - ESKI_GECICI_SN
    for boy in BOYLAR:
        klasor = gorsel_dizin / boy
        if not klasor.is_dir():
            continue
        for yol in klasor.iterdir():
            try:
                if GECICI_DESENI.fullmatch(yol.name) and yol.stat().st_mtime < sinir:
                    yol.unlink(missing_ok=True)
            except OSError:
                pass


def yetim_sil(con: sqlite3.Connection, gorsel_dizin: Path) -> int:
    """Hiçbir (aktif) ürünün göstermediği yerel görsel dosyalarını siler."""
    kullanilan = set()
    for (g,) in con.execute("SELECT gorsel_url FROM urun WHERE aktif = 1 AND gorsel_url LIKE 'gorsel:%'"):
        ad = yerel_ad(g)
        if ad:
            kullanilan.add(ad)
    silinen = 0
    for boy in BOYLAR:
        klasor = gorsel_dizin / boy
        if not klasor.is_dir():
            continue
        for yol in klasor.iterdir():
            if AD_DESENI.fullmatch(yol.name) and yol.name not in kullanilan and yol.is_file():
                yol.unlink(missing_ok=True)
                silinen += 1
    return silinen
