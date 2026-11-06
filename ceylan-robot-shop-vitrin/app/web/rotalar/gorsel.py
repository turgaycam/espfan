"""Yerel ürün görselleri (içerik adresli webp): GET /gorsel/{boy}/{ad}."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

router = APIRouter()
BOYLAR = ("k", "b")
AD_DESENI = re.compile(r"[0-9a-f]{32}\.webp")
BASLIKLAR = {
    "Cache-Control": "public, max-age=31536000, immutable",
    "X-Content-Type-Options": "nosniff",
}


@router.get("/gorsel/{boy}/{ad}")
def gorsel(request: Request, boy: str, ad: str) -> Response:
    if boy not in BOYLAR or not AD_DESENI.fullmatch(ad):
        raise HTTPException(status_code=404)
    kok = request.app.state.ayarlar.gorsel_dizin.resolve()
    yol = (kok / boy / ad).resolve()
    if not yol.is_relative_to(kok):
        raise HTTPException(status_code=404)
    try:
        icerik = Path.read_bytes(yol)   # küçük dosya: tek okuma, varlık kontrolü ile gönderim arası yarış yok
    except OSError:
        raise HTTPException(status_code=404) from None
    return Response(icerik, media_type="image/webp", headers=BASLIKLAR)
