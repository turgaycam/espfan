"""FastAPI uygulaması: middleware, statik dosyalar, rotalar, hata işleyicileri."""
from __future__ import annotations

import importlib
import logging
import ipaddress
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.ayarlar import Ayarlar
from app.db import baglan, gecisleri_uygula
from app.fiyat.kurallar import bantlari_oku
from app.katalog.kategori_ceviri import KategoriCeviri
from app.web.bagimlilik import db_bagimliligi  # noqa: F401  (yeniden dışa aktarım)
from app.web.baglam import hata_yaniti, sablon_globalleri
from app.web.dil import Ceviri
from app.web.guvenlik import BaslikMiddleware, HizSiniri
from app.web.koruma import EngelDeposu, KoruMiddleware

WEB = Path(__file__).parent
ROTA_SIRASI = ("genel", "seo", "gorsel", "yonetim", "yasal", "katalog", "hesap", "hesap_belge", "sepet_odeme", "teklif_gb",
               "karsilastir")
log = logging.getLogger("cr_shop.web")


def _rotalari_ekle(app: FastAPI) -> None:
    for ad in ROTA_SIRASI:
        modul_adi = f"app.web.rotalar.{ad}"
        try:
            modul = importlib.import_module(modul_adi)
        except ModuleNotFoundError as e:
            if e.name == modul_adi:
                log.info("rota modülü henüz yok: %s", modul_adi)
                continue
            raise
        app.include_router(modul.router)


async def _http_hatasi(request: Request, exc: StarletteHTTPException):
    return hata_yaniti(request, exc.status_code, basliklar=getattr(exc, "headers", None))


async def _dogrulama_hatasi(request: Request, exc: RequestValidationError):
    return hata_yaniti(request, 400)


async def _beklenmeyen_hata(request: Request, exc: Exception):
    kimlik = secrets.token_hex(4).upper()
    log.error("beklenmeyen hata kimlik=%s yol=%s", kimlik, request.url.path, exc_info=exc)
    return hata_yaniti(request, 500, kimlik=kimlik, db=False)


def _ozel_adres_mi(site_kok: str) -> bool:
    ad = urlsplit(site_kok).hostname or ""
    if ad in ("localhost", "") or ad.endswith((".local", ".lan", ".internal")):
        return True
    try:
        a = ipaddress.ip_address(ad)
    except ValueError:
        return False
    return a.is_private or a.is_loopback or a.is_link_local


def uygulama_olustur(ayarlar: Ayarlar) -> FastAPI:
    if ayarlar.yayin_modu == "uretim" and _ozel_adres_mi(ayarlar.site_kok):
        log.warning("SHOP_YAYIN_MODU=uretim ama SHOP_SITE_KOK özel/LAN adresi (%s): canonical, sitemap ve JSON-LD yanlış adrese gider",
                    ayarlar.site_kok)
    ayarlar.db_yolu.parent.mkdir(parents=True, exist_ok=True)
    con = baglan(ayarlar.db_yolu)
    try:
        gecisleri_uygula(con)
    finally:
        con.close()

    app = FastAPI(title="Ceylan Robot demo mağaza", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ayarlar = ayarlar
    app.state.ceviri = Ceviri(WEB / "dil")
    app.state.kategori_ceviri = KategoriCeviri()   # G3c madde 23: kategori adları (EN)
    app.state.sablonlar = Jinja2Templates(directory=str(WEB / "sablonlar"))
    sablon_globalleri(app.state.sablonlar.env)   # G3f: urun_ad / urun_metin
    app.state.bantlar = bantlari_oku(ayarlar.bantlar_yolu)
    app.state.hiz = HizSiniri()
    app.state.teklif_hiz = HizSiniri(limit=5, pencere=600.0)  # G3a: herkese açık teklif uçları, IP başına 10 dk'da 5
    app.state.sayfa_hiz = HizSiniri(limit=ayarlar.sayfa_hiz_limiti, pencere=60.0)  # ürün/kategori sayfaları, IP başına
    app.state.engel = EngelDeposu(ayarlar.db_yolu)
    app.state.engel.yukle()
    app.state.seo_onbellek = {}        # sitemap/llms-full süreç içi önbelleği (rotalar/seo.py)
    app.state.katalog_onbellek = {}    # kategori ağacı (G3a; anahtar son eşitleme kaydı)

    app.add_middleware(
        SessionMiddleware,
        secret_key=ayarlar.gizli_anahtar,
        session_cookie="cr_oturum",
        max_age=14 * 24 * 3600,
        same_site="lax",
        https_only=False,
    )
    app.add_middleware(KoruMiddleware, engel=app.state.engel, hiz=app.state.sayfa_hiz, muaf=ayarlar.koruma_muaf)  # bal küpü + hız sınırı
    app.add_middleware(BaslikMiddleware, yayin_modu=ayarlar.yayin_modu)  # en dışta: oturum çerezli yanıtlara da başlık yazar
    app.mount("/statik", StaticFiles(directory=str(WEB / "statik")), name="statik")
    _rotalari_ekle(app)
    app.add_exception_handler(StarletteHTTPException, _http_hatasi)
    app.add_exception_handler(RequestValidationError, _dogrulama_hatasi)
    app.add_exception_handler(Exception, _beklenmeyen_hata)
    return app
