"""Kök yönlendirme, sağlık kontrolü, dil/ülke tercihi, çerez onayı (JS'siz)."""
from __future__ import annotations

from urllib.parse import parse_qsl, quote, urlencode, urlsplit

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app.esitleme.esitle import son_basarili_esitleme
from app.fiyat.kurallar import FIYAT_GOSTERIMLERI
from app.web.baglam import ULKELER
from app.web.dil import DILLER
from app.web.guvenlik import csrf_dogrula, guvenli_sonraki
from app.web.bagimlilik import db_bagimliligi
from app.web.rotalar.katalog import FIYAT_BIRIMLERI, gosterim_para_birimi

router = APIRouter()
BIR_YIL = 365 * 24 * 3600


@router.get("/")
def kok(request: Request):
    dil = request.cookies.get("dil")
    if dil not in DILLER:
        dil = "tr"
    return RedirectResponse(f"/{dil}/", status_code=302)


@router.get("/saglik")
def saglik(con=Depends(db_bagimliligi)):
    son = son_basarili_esitleme(con)
    adet = con.execute("SELECT COUNT(*) FROM urun WHERE aktif = 1").fetchone()[0]
    return {"durum": "ok", "son_esitleme": son.isoformat() if son else None, "urun": adet}


def _fpb_sabitle(request: Request, con, hedef: str) -> str:
    """G3l madde 5: dönüş adresinde fiyat aralığı (fmin/fmax) var ama geçerli fpb yoksa aralık o ana kadar gösterim
    para biriminde yorumlanıyordu: fpb o anki (değişiklik öncesi) gösterim birimine sabitlenir, ₺/€ ya da ülke
    değişse de filtre aynı ürünleri seçer."""
    hedef, diyez, parca = hedef.partition("#")          # fix 1 M-2: çapa sorguya karışmasın, sonda korunur
    yol, ayrac, sorgu = hedef.partition("?")
    ciftler = parse_qsl(sorgu, keep_blank_values=True)
    fiyatli = any(k in ("fmin", "fmax") and v.strip() for k, v in ciftler)
    fpb_var = any(k == "fpb" and v.upper() in FIYAT_BIRIMLERI for k, v in ciftler)
    if not fiyatli or fpb_var:
        return hedef + diyez + parca
    ciftler = [(k, v) for k, v in ciftler if k != "fpb"] + [("fpb", gosterim_para_birimi(request, con))]
    return yol + "?" + urlencode(ciftler) + diyez + parca


@router.post("/tercih", dependencies=[Depends(csrf_dogrula)])
def tercih(request: Request, dil: str = Form(""), ulke: str = Form(""), sonraki: str = Form("/"),
           fiyat: str = Form(""), con=Depends(db_bagimliligi)):
    hedef = guvenli_sonraki(sonraki, "/")
    yeni_dil = dil if dil in DILLER else None
    if yeni_dil:
        yol, ayrac, sorgu = hedef.partition("?")
        parcalar = yol.split("/")
        if len(parcalar) > 1 and parcalar[1] in DILLER:
            parcalar[1] = yeni_dil
            hedef = "/".join(parcalar) + ayrac + sorgu
        elif yol == "/":
            hedef = f"/{yeni_dil}/"
    ulke = (ulke or "").strip().upper()
    yeni_ulke = ulke if ulke in ULKELER else None
    yeni_fiyat = fiyat if fiyat in FIYAT_GOSTERIMLERI else None
    if yeni_ulke or yeni_fiyat:
        hedef = _fpb_sabitle(request, con, hedef)
    if yeni_ulke:
        request.session["ulke"] = yeni_ulke
    # G3i madde 2: fiyat gösterimi (₺ KDV dahil | € KDV hariç); oturum + çerez, girişten sonra da geçerli
    if yeni_fiyat:
        request.session["fiyat"] = yeni_fiyat
    yanit = RedirectResponse(hedef, status_code=303)
    if yeni_dil:
        yanit.set_cookie("dil", yeni_dil, max_age=BIR_YIL, httponly=True, samesite="lax")
    if yeni_ulke:
        yanit.set_cookie("ulke", yeni_ulke, max_age=BIR_YIL, httponly=True, samesite="lax")
    if yeni_fiyat:
        yanit.set_cookie("fiyat", yeni_fiyat, max_age=BIR_YIL, httponly=True, samesite="lax")
    return yanit


@router.post("/cerez-onay", dependencies=[Depends(csrf_dogrula)])
def cerez_onay(request: Request, sonraki: str = Form("")):
    """G3c düzeltme 2: çerez bandı JS'siz de kapanır. Dönüş: form `sonraki` alanı, yoksa aynı kökenli Referer yolu;
    ikisi de güvenli değilse kök (guvenli_sonraki; açık yönlendirme yok). JS yolu aynı çerezi document.cookie ile yazar."""
    hedef = guvenli_sonraki(sonraki[:500], "")
    if not hedef:
        referer = urlsplit(request.headers.get("referer", ""))
        if referer.netloc and referer.netloc == request.url.netloc and referer.scheme in ("http", "https"):
            hedef = guvenli_sonraki((referer.path + (f"?{referer.query}" if referer.query else ""))[:500], "")
    yanit = RedirectResponse(hedef or "/", status_code=303)
    yanit.set_cookie("cerez_onay", "1", max_age=BIR_YIL, samesite="lax", path="/")
    return yanit


# G3g madde 16: İngilizce yol takma adları -> mevcut rotalara 301 (sorgu olduğu gibi korunur; mevcut rotalar değişmez)
EN_TAKMA_ADLARI = {"search": "ara", "products": "urunler", "cart": "sepet", "checkout": "odeme",
                   "compare": "karsilastir", "quote": "teklif"}


def _takma_ad_yonlendir(hedef: str):
    def yonlendir(request: Request) -> RedirectResponse:
        sorgu = request.url.query
        return RedirectResponse(f"/en/{hedef}" + (f"?{sorgu}" if sorgu else ""), status_code=301)
    return yonlendir


for _takma, _hedef in EN_TAKMA_ADLARI.items():
    router.add_api_route(f"/en/{_takma}", _takma_ad_yonlendir(_hedef), methods=["GET"], include_in_schema=False)


# G3i madde 7–9: Hesabım sipariş ayrıntısı, proforma ve fatura bilgileri için EN takma adları (301)
@router.get("/en/account", include_in_schema=False)
def _hesabim_takma() -> RedirectResponse:
    return RedirectResponse("/en/hesabim", status_code=301)


@router.get("/en/account/billing", include_in_schema=False)
def _fatura_takma() -> RedirectResponse:
    return RedirectResponse("/en/hesabim/fatura", status_code=301)


@router.get("/en/account/orders/{no}", include_in_schema=False)
def _siparis_takma(no: str) -> RedirectResponse:
    return RedirectResponse(f"/en/hesabim/siparis/{quote(no[:40], safe='')}", status_code=301)


@router.get("/en/account/orders/{no}/proforma", include_in_schema=False)
def _proforma_takma(no: str) -> RedirectResponse:
    return RedirectResponse(f"/en/hesabim/siparis/{quote(no[:40], safe='')}/proforma", status_code=301)
