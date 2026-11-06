"""Kayıt, giriş, çıkış ve hesabım."""
from __future__ import annotations

import sqlite3
import time
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.fiyat.kurallar import MusteriTipi
from app.hesap.dogrulama import vat_id_kontrol
from app.hesap.servis import KayitGirdisi, KayitHatasi, Musteri, giris, kayit_ol
from app.sepet.servis import birlestir, sepet_bul
from app.siparis.servis import musteri_siparisleri
from app.teklif.servis import teklif_no_ile, teklifler
from app.fiyat.kur import son_kur
from app.web.baglam import (ULKELER, bildir, dil_bul, etkin_gosterim, fiyat_baglami, fiyat_tercihi, mevcut_sepet_id,
                            sablon, simdi, ulke_secimi)
from app.web.guvenlik import aktif_musteri, csrf_dogrula, csrf_jetonu, guvenli_sonraki, oturum_kimligi
from app.web.bagimlilik import db_bagimliligi

router = APIRouter()

TIPLER = tuple(t.value for t in MusteriTipi)
UZUNLUK = 200
PAROLA_UST = 200


def _kirp(deger: str | None) -> str:
    return (deger or "").strip()[:UZUNLUK]


def oturum_ac(request: Request, con: sqlite3.Connection, musteri: Musteri) -> None:
    """Misafir sepetini üye sepetiyle birleştirir (kendi işleminde commit eder), sonra oturumu yeniler.

    Sıra: misafir sepet id'sini oku -> birleştir + commit -> csrf/oid yenile -> mid yaz (oturum sabitleme koruması).
    """
    misafir = mevcut_sepet_id(con, request, None)
    # G3i madde 2: açık fiyat tercihi yoksa ve girişle varsayılan gösterim değişiyorsa bir kezlik bildirim
    kur = son_kur(con)
    kur_eur = kur.eur_satis if kur is not None else None
    onceki_gosterim = etkin_gosterim(fiyat_baglami(request, None), kur_eur) if fiyat_tercihi(request) is None else None
    adet = 0
    with con:
        uye = sepet_bul(con, None, musteri.id, simdi())
        if misafir is not None and uye != misafir:
            adet = birlestir(con, misafir, uye)
    request.session.pop("csrf", None)
    request.session.pop("oid", None)
    csrf_jetonu(request)
    oturum_kimligi(request)
    request.session["mid"] = musteri.id
    request.session.pop("ulke", None)   # G3b M-7: giriş öncesi seçim kayıtlı ülkenin önüne geçmez (çerez misafir içindir)
    if adet:
        bildir(request, "hesap.sepet_birlesti", adet=adet)
    if onceki_gosterim is not None:
        yeni = etkin_gosterim(fiyat_baglami(request, musteri), kur_eur)
        if yeni != onceki_gosterim:
            bildir(request, f"fiyat.giris_bildirim_{musteri.tip.value}_{yeni}",
                   bag=(f"/{dil_bul(request)}/urunler#fiyat-gosterim", "fiyat.degistir", "fiyat-degistir"))


def _bos_deger(tip: str = "") -> dict:
    return {"tip": tip, "ad": "", "eposta": "", "ulke": "DE", "vergi_kimlik_no": "",
            "vergi_dairesi": "", "vat_id": "", "iys_onay": False, "kvkk_onay": False}


def _hata_metni(request: Request, dil: str, kod: str) -> str:
    ceviri = request.app.state.ceviri
    anahtar = f"hata_kodu.{kod}"  # K14/K17: Görev 7 kodları (zorunlu, gecersiz, gecersiz_vkn, parola_kisa, kvkk_onay_yok, eposta_kayitli)
    return ceviri.t(dil, anahtar if ceviri.var(anahtar) else "hata_kodu.gecersiz")


def _kayit_formu(request: Request, deger: dict, hatalar: dict, durum: int = 200, sonraki: str = ""):
    return sablon(request, "kayit.html", {"deger": deger, "hatalar": hatalar, "sonraki": sonraki}, durum=durum)


@router.get("/{dil:dil}/kayit")
def kayit_sayfasi(request: Request, dil: str, con=Depends(db_bagimliligi)):
    if aktif_musteri(request, con) is not None:
        return RedirectResponse(f"/{dil}/hesabim", status_code=303)
    tip = request.query_params.get("tip", "")
    sonraki = guvenli_sonraki(request.query_params.get("sonraki"), "")
    deger = _bos_deger(tip if tip in TIPLER else "")
    if ulke_secimi(request) not in (None, "TR"):   # G3b madde 16: üst bantta seçilen ülke yurt dışı kaydın varsayılanı
        deger["ulke"] = ulke_secimi(request)
    return _kayit_formu(request, deger, {}, sonraki=sonraki)


@router.post("/{dil:dil}/kayit", dependencies=[Depends(csrf_dogrula)])
def kayit_gonder(
    request: Request,
    dil: str,
    tip: str = Form(""),
    ad: str = Form(""),
    eposta: str = Form(""),
    parola: str = Form(""),
    ulke: str = Form(""),
    vergi_kimlik_no: str = Form(""),
    vergi_dairesi: str = Form(""),
    vat_id: str = Form(""),
    kvkk_onay: str = Form(""),
    iys_onay: str = Form(""),
    sonraki: str = Form(""),
    con=Depends(db_bagimliligi),
):
    if aktif_musteri(request, con) is not None:  # GET ile aynı: yeni hesap açılmaz
        return RedirectResponse(f"/{dil}/hesabim", status_code=303)
    form_sonraki = guvenli_sonraki(sonraki, "")
    deger = {
        "tip": tip if tip in TIPLER else "",
        "ad": _kirp(ad),
        "eposta": _kirp(eposta),
        "ulke": _kirp(ulke).upper(),
        "vergi_kimlik_no": _kirp(vergi_kimlik_no).replace(" ", ""),
        "vergi_dairesi": _kirp(vergi_dairesi),
        "vat_id": _kirp(vat_id),
        "iys_onay": iys_onay == "1",
        "kvkk_onay": kvkk_onay == "1",
    }
    if not deger["tip"]:
        return _kayit_formu(request, deger, {"tip": _hata_metni(request, dil, "tip_sec")}, 400, form_sonraki)
    if len(parola) > PAROLA_UST:
        return _kayit_formu(request, deger, {"parola": _hata_metni(request, dil, "gecersiz")}, 400, form_sonraki)
    musteri_tipi = MusteriTipi(deger["tip"])
    kurumsal = musteri_tipi is MusteriTipi.KURUMSAL
    yurtdisi = musteri_tipi is MusteriTipi.YURTDISI
    if yurtdisi and (deger["ulke"] not in ULKELER or deger["ulke"] == "TR"):
        return _kayit_formu(request, deger, {"ulke": _hata_metni(request, dil, "gecersiz_ulke")}, 400, form_sonraki)
    vat_id = None
    if yurtdisi:   # G3c madde 19: AB ülkesindeki firma için VAT ID zorunlu, biçimi ülke önekiyle doğrulanır
        vat_id, kod = vat_id_kontrol(deger["vat_id"], deger["ulke"], zorunlu_ab=True)
        if kod is not None:
            kod = "vat_zorunlu" if kod == "zorunlu" else kod
            return _kayit_formu(request, deger, {"vat_id": _hata_metni(request, dil, kod)}, 400, form_sonraki)
    girdi = KayitGirdisi(
        tip=musteri_tipi,
        ad=deger["ad"],
        eposta=deger["eposta"],
        parola=parola,
        ulke=deger["ulke"] if yurtdisi else "TR",
        kvkk_onay=deger["kvkk_onay"],
        iys_onay=deger["iys_onay"] if musteri_tipi is MusteriTipi.BIREYSEL else False,
        vergi_kimlik_no=(deger["vergi_kimlik_no"] or None) if kurumsal else None,
        vergi_dairesi=(deger["vergi_dairesi"] or None) if kurumsal else None,
        vat_id=vat_id,
    )
    try:
        with con:
            musteri = kayit_ol(con, girdi, simdi())
    except KayitHatasi as hata:
        return _kayit_formu(request, deger, {hata.alan: _hata_metni(request, dil, hata.kod)}, 400, form_sonraki)
    oturum_ac(request, con, musteri)  # kayıt commit edildikten sonra
    bildir(request, "hesap.kayit_tamam")
    hedef = guvenli_sonraki(sonraki) if sonraki else f"/{dil}/hesabim"  # K12: otomatik giriş + sonraki
    return RedirectResponse(hedef, status_code=303)


@router.get("/{dil:dil}/giris")
def giris_sayfasi(request: Request, dil: str, con=Depends(db_bagimliligi)):
    sonraki = guvenli_sonraki(request.query_params.get("sonraki"), "")
    if aktif_musteri(request, con) is not None:
        return RedirectResponse(sonraki or f"/{dil}/hesabim", status_code=303)
    return sablon(request, "giris.html", {"eposta": "", "sonraki": sonraki, "hata_anahtar": None})


@router.post("/{dil:dil}/giris", dependencies=[Depends(csrf_dogrula)])
def giris_gonder(
    request: Request,
    dil: str,
    eposta: str = Form(""),
    parola: str = Form(""),
    sonraki: str = Form(""),
    con=Depends(db_bagimliligi),
):
    eposta = _kirp(eposta)
    form_sonraki = guvenli_sonraki(sonraki, "")
    ip = request.client.host if request.client else "bilinmiyor"
    if not request.app.state.hiz.izin(f"giris:{ip}", time.monotonic()):
        return sablon(request, "giris.html",
                      {"eposta": eposta, "sonraki": form_sonraki, "hata_anahtar": "hesap.cok_deneme"}, durum=429)
    musteri = giris(con, eposta, parola[:PAROLA_UST]) if eposta and parola else None
    if musteri is None:
        return sablon(request, "giris.html",
                      {"eposta": eposta, "sonraki": form_sonraki, "hata_anahtar": "hesap.hatali_giris"}, durum=400)
    oturum_ac(request, con, musteri)
    bildir(request, "hesap.giris_tamam")
    hedef = guvenli_sonraki(sonraki) if sonraki else f"/{dil}/hesabim"
    return RedirectResponse(hedef, status_code=303)


@router.post("/{dil:dil}/cikis", dependencies=[Depends(csrf_dogrula)])
def cikis(request: Request, dil: str):
    request.session.clear()  # misafir sepeti ve csrf yeni oturumla sıfırdan başlar
    bildir(request, "hesap.cikis_yapildi")
    return RedirectResponse(f"/{dil}/", status_code=303)


@router.get("/{dil:dil}/hesabim")
def hesabim(request: Request, dil: str, con=Depends(db_bagimliligi)):
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return RedirectResponse(f"/{dil}/giris?sonraki=" + quote(f"/{dil}/hesabim", safe=""), status_code=303)
    with con:  # musteri_siparisleri zaman aşımı uygular (yazma)
        siparisler = musteri_siparisleri(con, musteri.id, simdi())
    return sablon(request, "hesabim.html", {
        "musteri": musteri,
        "siparisler": siparisler,
        "teklifler": teklifler(con, musteri_id=musteri.id),
    })


@router.get("/{dil:dil}/hesabim/teklif/{no}")
def hesabim_teklif(request: Request, dil: str, no: str, con=Depends(db_bagimliligi)):
    """G3g madde 26: Hesabım > Tekliflerim satırından teklif detayı (yalnız teklifin sahibi; başkasına 404)."""
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return RedirectResponse(f"/{dil}/giris?sonraki=" + quote(f"/{dil}/hesabim/teklif/{no}", safe=""),
                                status_code=303)
    teklif = teklif_no_ile(con, no[:40])
    if teklif is None or teklif.musteri_id != musteri.id:
        raise HTTPException(status_code=404)
    return sablon(request, "hesabim_teklif.html", {"teklif": teklif})
