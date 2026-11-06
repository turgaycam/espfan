"""Arama motoru / yapay zekâ tarayıcısı dosyaları: robots.txt, sitemap*.xml, llms.txt, llms-full.txt.

Sitemap ve llms dosyaları demoda da üretilir (doğrulanabilsin); demoda yalnız robots.txt bunları ilan etmez.
"""
from __future__ import annotations

import re
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response

from app.esitleme.esitle import son_basarili_esitleme
from app.katalog.depo import KategoriDugum, kategori_agaci
from app.web import seo
from app.web.baglam import YASAL_SAYFALAR
from app.web.bagimlilik import db_bagimliligi

router = APIRouter()
_TARIH = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _gun(metin: str | None) -> str | None:
    """ISO zamandan YYYY-MM-DD (sitemap lastmod)."""
    m = _TARIH.match(metin or "")
    return m.group(0) if m else None


def _son_esitleme_gunu(con: sqlite3.Connection) -> str | None:
    son = son_basarili_esitleme(con)
    return son.date().isoformat() if son else None


def _xml(icerik: str) -> Response:
    return Response(icerik, media_type="application/xml")


def _onbellekli(request: Request, ad: str, con: sqlite3.Connection, uret) -> str:
    """Süreç içi önbellek (sitemap ürün dosyaları, llms-full). Anahtar: son başarılı eşitleme + aktif ürün sayısı +
    yayın modu/site kökü/dosya sınırı; eşitleme sonrası anahtar değişir ve içerik yeniden üretilir."""
    a = request.app.state.ayarlar
    son = son_basarili_esitleme(con)
    anahtar = (son.isoformat() if son else None, _urun_sayisi(con), a.yayin_modu, a.site_kok, seo.SITEMAP_URL_SINIRI)
    depo = request.app.state.seo_onbellek  # uygulama_olustur kurar (G3a Y3)
    kayit = depo.get(ad)
    if kayit is not None and kayit[0] == anahtar:
        return kayit[1]
    icerik = uret()
    if len(depo) > 64:
        depo.clear()
    depo[ad] = (anahtar, icerik)
    return icerik


def _urun_sayisi(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COUNT(*) FROM urun WHERE aktif = 1").fetchone()[0]


def _dosya_sayisi(adet: int) -> int:
    boy = seo.SITEMAP_URL_SINIRI
    return (adet + boy - 1) // boy


@router.get("/robots.txt")
def robots(request: Request) -> Response:
    a = request.app.state.ayarlar
    return PlainTextResponse(seo.robots_metni(a.yayin_modu, a.site_kok, a.ai_tarayicilar))


@router.get("/sitemap.xml")
def sitemap_indeksi(request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    kok = request.app.state.ayarlar.site_kok
    gun = _son_esitleme_gunu(con)
    dosyalar = [(f"/sitemap-urunler-{n}.xml", gun) for n in range(1, _dosya_sayisi(_urun_sayisi(con)) + 1)]
    dosyalar += [("/sitemap-kategoriler.xml", gun), ("/sitemap-sayfalar.xml", gun)]
    return _xml(seo.sitemap_indeks_xml(kok, dosyalar))


@router.get("/sitemap-urunler-{n:int}.xml")
def sitemap_urunleri(request: Request, n: int, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    if n < 1 or n > _dosya_sayisi(_urun_sayisi(con)):
        raise HTTPException(status_code=404)
    boy = seo.SITEMAP_URL_SINIRI

    def uret() -> str:
        gun = _son_esitleme_gunu(con)
        satirlar = con.execute(
            "SELECT id, kaynak_guncelleme, olusturma FROM urun WHERE aktif = 1 ORDER BY id LIMIT ? OFFSET ?",
            (boy, (n - 1) * boy),
        ).fetchall()
        girdiler = [(f"/{{dil}}/urun/{r['id']}", _gun(r["kaynak_guncelleme"]) or gun or _gun(r["olusturma"])) for r in satirlar]
        return seo.sitemap_xml(request.app.state.ayarlar.site_kok, girdiler)

    return _xml(_onbellekli(request, f"sitemap-urunler-{n}", con, uret))


def _duzlestir(dugumler: list[KategoriDugum]):
    for d in dugumler:
        yield d
        yield from _duzlestir(d.cocuklar)


@router.get("/sitemap-kategoriler.xml")
def sitemap_kategorileri(request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    gun = _son_esitleme_gunu(con)
    # Yalnız aktif kategoriler; alt dalları dahil en az bir aktif ürünü olanlar (boş sayfa sitemap'e girmez)
    girdiler = [(f"/{{dil}}/kategori/{d.kategori.id}", gun) for d in _duzlestir(kategori_agaci(con)) if d.urun_sayisi > 0]
    return _xml(seo.sitemap_xml(request.app.state.ayarlar.site_kok, girdiler))


@router.get("/sitemap-sayfalar.xml")
def sitemap_sayfalari(request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    gun = _son_esitleme_gunu(con)
    girdiler = [("/{dil}/", gun), ("/{dil}/teklif", None)] + [(f"/{{dil}}/yasal/{s}", None) for s in YASAL_SAYFALAR]
    return _xml(seo.sitemap_xml(request.app.state.ayarlar.site_kok, girdiler))


@router.get("/llms.txt")
def llms(request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    a = request.app.state.ayarlar
    ceviri = request.app.state.ceviri
    gruplar = [(d.kategori.ad, d.kategori.id, d.urun_sayisi) for d in kategori_agaci(con) if d.urun_sayisi > 0]
    yasal = [(ceviri.t("tr", "alt.yasal_" + s.replace("-", "_")), s) for s in YASAL_SAYFALAR]
    return PlainTextResponse(seo.llms_metni(site_kok=a.site_kok, demo=a.yayin_modu == "demo", gruplar=gruplar,
                                            telefon=a.telefon, yasal=yasal))


@router.get("/llms-full.txt")
def llms_tam(request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    a = request.app.state.ayarlar

    def uret() -> str:
        satirlar = con.execute(
            "SELECT id, sku, ad, uretici_kodu, durum_kodu, kok_kategori_ad FROM urun WHERE aktif = 1"
            " ORDER BY kok_kategori_ad, ad, id"
        ).fetchall()
        gruplar: dict[str, list] = {}
        for r in satirlar:
            gruplar.setdefault(r["kok_kategori_ad"] or "Diğer", []).append(r)
        return seo.llms_full_metni(site_kok=a.site_kok, demo=a.yayin_modu == "demo", gruplar=gruplar.items())

    return PlainTextResponse(_onbellekli(request, "llms-full", con, uret))
