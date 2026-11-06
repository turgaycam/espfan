"""Yasal sayfa taslakları (Görev 16)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.web import seo
from app.web.baglam import sablon, seo_baglami
from app.web.bagimlilik import db_bagimliligi

router = APIRouter()

SAYFALAR = ("on-bilgilendirme", "mesafeli-satis", "iade", "garanti", "kvkk",
            "acik-riza", "cerez", "gizlilik", "kullanim", "kunye")


@router.get("/{dil:dil}/yasal/{sayfa}")
def yasal_sayfa(dil: str, sayfa: str, request: Request, con=Depends(db_bagimliligi)) -> Response:  # başlıkta oturum/sepet doğru görünsün
    if sayfa not in SAYFALAR:   # beyaz liste: şablon yolu kullanıcı girdisinden türetilmez
        raise HTTPException(status_code=404)
    etiket = request.app.state.ceviri.t(dil, "alt.yasal_" + sayfa.replace("-", "_"))
    return sablon(request, f"yasal/{dil}/{sayfa}.html", {
        "yasal_sayfa": sayfa,
        "seo": seo_baglami(request, dil=dil, aciklama=seo.sablon_metni(dil, "yasal_aciklama", sayfa=etiket)),
    })
