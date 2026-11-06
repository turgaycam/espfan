"""Yönetim paneli (Görev 15): giriş, pano, siparişler, teklifler, geri bildirimler."""
from __future__ import annotations

import secrets
import sqlite3
import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.esitleme.esitle import son_basarili_esitleme, son_esitleme
from app.fiyat.kur import kur_bayat_mi, son_kur
from app.geribildirim import servis as gb_servis
from app.hesap.servis import parola_dogru
from app.katalog.depo import kod_eslesmeleri_toplu, urun_getir
from app.katalog.veri_kalitesi import veri_kalitesi_raporu
from app.siparis.servis import (IZINLI_GECISLER, GecersizGecis, SiparisDurumu, StokYetersiz, durum_degistir,
                                siparis_getir, tum_siparisler)
from app.teklif.servis import TEKLIF_GECISLERI, teklif_durum_degistir, teklifler
from app.web.bagimlilik import db_bagimliligi
from app.web.baglam import sablon
from app.web.guvenlik import csrf_dogrula, csrf_jetonu, guvenli_sonraki

router = APIRouter(prefix="/yonetim")

GIRIS_YOLU = "/yonetim/giris"
ESITLEME_UYARI_SURESI = timedelta(hours=36)
GIRDI_UST = 200          # kullanıcı adı/parola üst sınırı (scrypt'e dev girdi gitmesin)
SAYI_SORGULARI = {
    "urun": "SELECT COUNT(*) FROM urun WHERE aktif = 1",
    "siparis": "SELECT COUNT(*) FROM siparis",
    # G3g madde 4: ödeme son tarihi geçmiş havale "süresi doldu" sayılır, bekleyenlere girmez
    "odeme_bekleyen": "SELECT COUNT(*) FROM siparis WHERE durum = 'odeme_bekliyor' AND NOT (odeme_yontemi = 'havale'"
                      " AND odeme_son_tarih <= strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))",
    "siparis_yeni": "SELECT COUNT(*) FROM siparis WHERE durum = 'odendi'",
    "teklif_yeni": "SELECT COUNT(*) FROM teklif WHERE durum = 'yeni'",
    "teklif_acik": "SELECT COUNT(*) FROM teklif WHERE durum <> 'kapandi'",
    "gb_yeni": "SELECT COUNT(*) FROM geri_bildirim WHERE durum = 'yeni'",
}
# Panoda yalnız sayı olarak listelenenler (diğerleri üstteki dört kartta)
SAYI_LISTESI = ("urun", "siparis", "odeme_bekleyen")


def _simdi() -> datetime:
    return datetime.now(UTC)


def _utc(z: datetime | None) -> datetime | None:
    if z is not None and z.tzinfo is None:
        z = z.replace(tzinfo=UTC)
    return z.astimezone(UTC) if z is not None else None


def _iso(metin: str | None) -> datetime | None:
    if not metin:
        return None
    try:
        return _utc(datetime.fromisoformat(metin))
    except ValueError:
        return None


def _yetkisiz(request: Request) -> RedirectResponse | None:
    if request.session.get("yonetici") is True:
        return None
    return RedirectResponse(GIRIS_YOLU, status_code=303)


def _kimlik(deger: int) -> int:
    """Yol parametresi: SQLite tamsayı aralığı dışındaki kimlik kayıt olamaz (OverflowError yerine 404)."""
    if not 0 < deger < 2**63:
        raise HTTPException(status_code=404)
    return deger


def _sayfa(request: Request, ad: str, aktif: str, baglam: dict, durum: int = 200) -> Response:
    """Yönetim sayfaları (girişli): sol menüde etkin öğe; başlıkta Çıkış."""
    return sablon(request, ad, {"aktif_menu": aktif, "kok_kategoriler": [], "yonetici": True, **baglam}, durum)


# ---------- giriş / çıkış ----------

def _giris_sayfasi(request: Request, hata: str | None, kullanici: str, durum: int = 200) -> Response:
    return sablon(request, "yonetim/giris.html", {"hata": hata, "kullanici": kullanici, "kok_kategoriler": []}, durum)


@router.get("/giris")
def giris_formu(request: Request) -> Response:
    if request.session.get("yonetici") is True:
        return RedirectResponse("/yonetim", status_code=303)
    return _giris_sayfasi(request, None, "")


@router.post("/giris")
async def giris_gonder(request: Request) -> Response:
    await csrf_dogrula(request)
    ip = request.client.host if request.client else "bilinmiyor"
    if not request.app.state.hiz.izin(f"yonetim:{ip}", time.monotonic()):
        return _giris_sayfasi(request, "yonetim.cok_deneme", "", 429)
    form = await request.form()
    kullanici = str(form.get("kullanici", "")).strip()[:GIRDI_UST]
    parola = str(form.get("parola", ""))
    ayarlar = request.app.state.ayarlar
    ad_dogru = secrets.compare_digest(kullanici.encode(), ayarlar.yonetici_kullanici.encode())
    parola_tamam = len(parola) <= GIRDI_UST and parola_dogru(parola, ayarlar.yonetici_parola_ozeti)
    if not (ad_dogru and parola_tamam):
        return _giris_sayfasi(request, "yonetim.hatali_giris", kullanici, 401)
    # Oturum sabitlemeye karşı: girişten önceki csrf jetonu geçersiz olur (Görev 13 oturum_ac kalıbı)
    request.session.pop("csrf", None)
    csrf_jetonu(request)
    request.session["yonetici"] = True
    return RedirectResponse("/yonetim", status_code=303)


@router.post("/cikis")
async def cikis(request: Request) -> Response:
    await csrf_dogrula(request)
    request.session.pop("yonetici", None)
    request.session.pop("csrf", None)
    return RedirectResponse(GIRIS_YOLU, status_code=303)


# ---------- pano ----------

@router.get("")
def pano(request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    if (yonlendir := _yetkisiz(request)) is not None:
        return yonlendir
    simdi = _simdi()
    son_tam = _utc(son_basarili_esitleme(con))
    son = son_esitleme(con)
    kur = son_kur(con)
    return _sayfa(request, "yonetim/pano.html", "pano", {
        "son": son,
        "son_basla": _iso(son["basla"]) if son is not None else None,
        "son_tam": son_tam,
        # Başarısızlık `durum` ile belirlenir; `hata` alanı 'tam' turda da bozuk kayıt özeti taşıyabilir.
        "son_basarisiz": son is not None and son["durum"] in ("eksik", "hata"),
        "esitleme_uyari": son_tam is None or simdi - son_tam > ESITLEME_UYARI_SURESI,
        "kur": kur, "kur_bayat": kur is not None and kur_bayat_mi(kur, simdi.date()),
        "sayilar": {ad: con.execute(sql).fetchone()[0] for ad, sql in SAYI_SORGULARI.items()},
        "sayi_listesi": SAYI_LISTESI,
        "engelliler": request.app.state.engel.listele(),
    })


@router.post("/engel/kaldir")
async def engel_kaldir(request: Request) -> Response:
    """Bal küpüyle engellenen bir IP'nin engelini tek tıkla kaldırır."""
    if (yonlendir := _yetkisiz(request)) is not None:
        return yonlendir
    await csrf_dogrula(request)
    form = await request.form()
    ip = str(form.get("ip", "")).strip()[:64]
    if not ip:
        raise HTTPException(status_code=400)
    request.app.state.engel.kaldir(ip)
    return RedirectResponse("/yonetim#engelliler", status_code=303)


# ---------- siparişler ----------

def _siparisler_sayfasi(request: Request, con: sqlite3.Connection, hata: dict | None = None,
                        durum: int = 200, stok_hatasi: dict | None = None) -> Response:
    with con:  # tum_siparisler zaman aşımını uygular (yazabilir)
        liste = tum_siparisler(con, _simdi())
    # G3e madde 15: durum süzgeci (ör. ?durum=odeme_bekliyor: havale bekleyenler); bilinmeyen değer yok sayılır
    filtre = request.query_params.get("durum")
    filtre = filtre if filtre in {d.value for d in SiparisDurumu} else None
    if filtre:
        liste = [s for s in liste if s.durum == filtre]
    return _sayfa(request, "yonetim/siparisler.html", "siparisler", {
        "siparisler": liste, "gecisler": {s.id: sorted(IZINLI_GECISLER[s.durum]) for s in liste},
        "hata": hata, "filtre": filtre, "durumlar": [d.value for d in SiparisDurumu], "stok_hatasi": stok_hatasi,
    }, durum)


@router.get("/siparisler")
def siparisler(request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    if (yonlendir := _yetkisiz(request)) is not None:
        return yonlendir
    return _siparisler_sayfasi(request, con)


@router.post("/siparis/{siparis_id}/durum")
async def siparis_durum(siparis_id: int, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    if (yonlendir := _yetkisiz(request)) is not None:
        return yonlendir
    await csrf_dogrula(request)
    siparis_id = _kimlik(siparis_id)
    form = await request.form()
    try:
        yeni = SiparisDurumu(str(form.get("durum", "")))
    except ValueError:
        raise HTTPException(status_code=400) from None
    try:
        with con:
            durum_degistir(con, siparis_id, yeni, _simdi(), havale_gun=request.app.state.ayarlar.havale_gun)
    except LookupError:                                   # K17
        raise HTTPException(status_code=404) from None
    except StokYetersiz as hata:                          # G3g inceleme I-1: çift satış yok; nedeni yönetime görünür
        with con:
            mevcut = siparis_getir(con, siparis_id, _simdi())
        stok_hatasi = {"no": mevcut.no if mevcut else "", "yeni": yeni.value,
                       "kalemler": [{"ad": ad, "kalan": kalan} for _, ad, kalan in hata.kalemler]}
        return _siparisler_sayfasi(request, con, stok_hatasi=stok_hatasi, durum=409)
    except GecersizGecis:
        with con:
            mevcut = siparis_getir(con, siparis_id, _simdi())
        if mevcut is None:
            raise HTTPException(status_code=404) from None
        hata = {"no": mevcut.no, "eski": mevcut.durum.value, "yeni": yeni.value}
        return _siparisler_sayfasi(request, con, hata=hata, durum=409)
    return RedirectResponse("/yonetim/siparisler", status_code=303)


# ---------- teklifler ----------

def _teklifler_sayfasi(request: Request, con: sqlite3.Connection, hata: dict | None = None,
                       durum: int = 200) -> Response:
    # G3i madde 16: kapanmamış acil hızlı talepler üstte (kendi içinde yeniden eskiye); diğerleri aynen
    liste = sorted(teklifler(con), key=lambda tk: not (tk.aciliyet == "acil" and tk.durum != "kapandi"))
    # G3j madde 1: ürüne bağlanmamış, kapanmamış parça kodlu talepte katalogdaki tam eşleşmeler (birden çok olabilir).
    # İnceleme M-3: tüm kodlar tek geçişte (satır başına tam tarama yok)
    adaylar = [tk for tk in liste if tk.parca_kodu and not tk.urun_id and not tk.kalemler and tk.durum != "kapandi"]
    harita = kod_eslesmeleri_toplu(con, [tk.parca_kodu for tk in adaylar]) if adaylar else {}
    urunler = {i: urun_getir(con, i) for i in dict.fromkeys(i for ids in harita.values() for i in ids)}
    eslesmeler = {tk.id: [urunler[i] for i in harita.get(tk.parca_kodu, []) if urunler.get(i)] for tk in adaylar}
    return _sayfa(request, "yonetim/teklifler.html", "teklifler", {
        "teklifler": liste, "gecisler": {tk.id: sorted(TEKLIF_GECISLERI[tk.durum]) for tk in liste},
        "hata": hata, "eslesmeler": eslesmeler,
    }, durum)


@router.get("/teklifler")
def teklif_listesi(request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    if (yonlendir := _yetkisiz(request)) is not None:
        return yonlendir
    return _teklifler_sayfasi(request, con)


@router.post("/teklif/{teklif_id}/durum")
async def teklif_durum(teklif_id: int, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    if (yonlendir := _yetkisiz(request)) is not None:
        return yonlendir
    await csrf_dogrula(request)
    teklif_id = _kimlik(teklif_id)
    form = await request.form()
    yeni = str(form.get("durum", ""))
    if yeni not in TEKLIF_GECISLERI:
        raise HTTPException(status_code=400)
    try:
        with con:
            teklif_durum_degistir(con, teklif_id, yeni)
    except LookupError:                                   # K17
        raise HTTPException(status_code=404) from None
    except GecersizGecis:
        mevcut = next((tk for tk in teklifler(con) if tk.id == teklif_id), None)
        if mevcut is None:
            raise HTTPException(status_code=404) from None
        hata = {"no": mevcut.no, "eski": mevcut.durum, "yeni": yeni}
        return _teklifler_sayfasi(request, con, hata=hata, durum=409)
    return RedirectResponse("/yonetim/teklifler", status_code=303)


# ---------- G3j madde 4: veri kalitesi (yalnız okuma) ----------

@router.get("/veri-kalitesi")
def veri_kalitesi(request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    if (yonlendir := _yetkisiz(request)) is not None:
        return yonlendir
    return _sayfa(request, "yonetim/veri_kalitesi.html", "veri_kalitesi", {"rapor": veri_kalitesi_raporu(con)})


# ---------- geri bildirimler ----------

@router.get("/geri-bildirimler")
def geri_bildirimler(request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    if (yonlendir := _yetkisiz(request)) is not None:
        return yonlendir
    filtre = request.query_params.get("durum")
    if filtre not in gb_servis.DURUMLAR:
        filtre = None
    kayitlar = gb_servis.listele(con, filtre)
    return _sayfa(request, "yonetim/geri_bildirimler.html", "geri_bildirimler", {
        "kayitlar": kayitlar, "filtre": filtre, "durumlar": gb_servis.DURUMLAR,
        "zamanlar": {k["id"]: _iso(k["olusturma"]) for k in kayitlar},
        # Ziyaretçinin gönderdiği sayfa yolu yalnız güvenli bir site içi yolsa bağlantı olur (\ ve // reddedilir)
        "baglanti": {k["id"] for k in kayitlar if guvenli_sonraki(k["sayfa"], "") == k["sayfa"]},
    })


@router.post("/geri-bildirim/{gb_id}/durum")
async def geri_bildirim_durum(gb_id: int, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    if (yonlendir := _yetkisiz(request)) is not None:
        return yonlendir
    await csrf_dogrula(request)
    gb_id = _kimlik(gb_id)
    form = await request.form()
    yeni = str(form.get("durum", ""))
    if yeni not in gb_servis.DURUMLAR:
        raise HTTPException(status_code=400)
    try:
        with con:
            gb_servis.durum_degistir(con, gb_id, yeni)
    except LookupError:                                   # K17
        raise HTTPException(status_code=404) from None
    filtre = str(form.get("filtre", ""))
    hedef = "/yonetim/geri-bildirimler" + (f"?durum={filtre}" if filtre in gb_servis.DURUMLAR else "")
    return RedirectResponse(hedef, status_code=303)
