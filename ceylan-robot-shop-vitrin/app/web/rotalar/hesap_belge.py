"""G3i B: Hesabım sipariş ayrıntısı (madde 8), proforma fatura belgesi (madde 7) ve fatura bilgilerim (madde 9).
Yalnız sahibi görür (başkasına 404); POST'lar CSRF'li, JS'siz."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.fiyat.kurallar import MusteriTipi
from app.hesap.dogrulama import telefon_gecerli
from app.hesap.servis import Adres, KayitHatasi, Musteri, adres_kaydet, adres_son, fatura_bilgisi_guncelle
from app.katalog.depo import urun_getir
from app.para import yuvarla
from app.sepet import servis as sepet_servis
from app.siparis.servis import Siparis, siparis_no_ile
from app.stok import ODEME_SURESI, ayrilan_adetler
from app.web.bagimlilik import db_bagimliligi
from app.web.baglam import SATICI_ADRES, bildir, gorunen_ad, kur_bicimle, sablon, siparis_alicisi
from app.web.guvenlik import aktif_musteri, csrf_dogrula, oturum_kimligi

router = APIRouter()

NO_AZAMI = 40
UZUNLUK = 200
FATURA_ALANLARI = ("ad", "vergi_dairesi", "satir1", "satir2", "posta_kodu", "sehir", "telefon")


def _simdi() -> datetime:
    return datetime.now(UTC)


def _giris_yonlendir(dil: str, yol: str) -> RedirectResponse:
    return RedirectResponse(f"/{dil}/giris?sonraki=" + quote(yol, safe=""), status_code=303)


def _sahip_siparis(con: sqlite3.Connection, no: str, musteri: Musteri) -> Siparis:
    with con:  # siparis_no_ile zaman aşımını uygular (yazabilir)
        siparis = siparis_no_ile(con, no[:NO_AZAMI], _simdi())
    if siparis is None or siparis.musteri_id != musteri.id:
        raise HTTPException(status_code=404)
    return siparis


def _urunler(con: sqlite3.Connection, siparis: Siparis) -> dict:
    return {k.urun_id: u for k in siparis.kalemler if (u := urun_getir(con, k.urun_id)) is not None}


# ---------- madde 8: sipariş ayrıntısı + kalemleri tekrar sepete ekle ----------

@router.get("/{dil:dil}/hesabim/siparis/{no}")
def siparis_ayrintisi(request: Request, dil: str, no: str, con=Depends(db_bagimliligi)) -> Response:
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return _giris_yonlendir(dil, f"/{dil}/hesabim/siparis/{no}")
    siparis = _sahip_siparis(con, no, musteri)
    # G3k madde 15: TL siparişte genel toplamın sabitlenen kurla € karşılığı
    toplam_eur = (yuvarla(siparis.toplam / siparis.kur) if siparis.para_birimi == "TRY" and siparis.kur
                  else None)
    return sablon(request, "hesabim_siparis.html", {"siparis": siparis, "urunler": _urunler(con, siparis),
                                                    "alici": siparis_alicisi(siparis, musteri),
                                                    "toplam_eur": toplam_eur,
                                                    "gecmis": _durum_gecmisi(con, siparis),
                                                    "kur_sayi": lambda kur: kur_bicimle(kur, dil).replace("₺", "").strip()})


def _zaman(metin: str | None) -> datetime | None:
    if not metin:
        return None
    z = datetime.fromisoformat(metin)
    return z if z.tzinfo is not None else z.replace(tzinfo=UTC)


def _durum_gecmisi(con: sqlite3.Connection, siparis: Siparis) -> list[dict]:
    """G3l madde 9: siparişte saklanan zaman damgalarından durum geçmişi (yeni kayıt uydurulmaz): oluşturuldu
    (olusturma), ödendi (odeme_zamani), ödeme bekliyor (+ havalede son tarih), süresi doldu (havale son tarihi ya da kart
    ödemesinin 30 dakikalık süresi dolduğu için iptal: guncelleme), iptal / hazırlanıyor / kargoda / teslim edildi
    (son durum değişikliği: guncelleme)."""
    r = con.execute("SELECT odeme_zamani, guncelleme FROM siparis WHERE id = ?", (siparis.id,)).fetchone()
    odeme, guncelleme = _zaman(r["odeme_zamani"]), _zaman(r["guncelleme"])
    gecmis = [{"anahtar": "hesap.gecmis_olusturuldu", "zaman": siparis.olusturma}]
    if odeme is not None:
        gecmis.append({"anahtar": "siparis_durum.odendi", "zaman": odeme})
    durum = str(siparis.durum)
    if durum == "odeme_bekliyor":
        gecmis.append({"anahtar": "siparis_durum.odeme_bekliyor", "zaman": None, "son": siparis.odeme_son_tarih})
    elif durum == "suresi_doldu":
        gecmis.append({"anahtar": "siparis_durum.suresi_doldu", "zaman": siparis.odeme_son_tarih})
    elif durum == "iptal":
        olusturma = siparis.olusturma if siparis.olusturma.tzinfo else siparis.olusturma.replace(tzinfo=UTC)
        # fix 1 I-2: kart ödemesi süresinde yapılmadı: zaman aşımı ilk okumada uygulanır ve guncelleme'ye okuma anını
        # yazar; olayın gerçek zamanı olusturma + ODEME_SURESI. Yönetimin iptali de önce zaman aşımını uyguladığından
        # (siparis_getir) 30 dk sonrası ödemesiz kart iptali her zaman süre dolmasıdır. Etiket rozetle ("İptal") uyumlu.
        kart_suresi = (siparis.odeme_yontemi == "kart" and odeme is None and guncelleme is not None
                       and guncelleme >= olusturma + ODEME_SURESI)
        gecmis.append({"anahtar": "hesap.gecmis_kart_suresi", "zaman": olusturma + ODEME_SURESI} if kart_suresi
                      else {"anahtar": "siparis_durum.iptal", "zaman": guncelleme})
    elif durum in ("hazirlaniyor", "kargoda", "teslim"):
        gecmis.append({"anahtar": f"siparis_durum.{durum}", "zaman": guncelleme})
    return gecmis


TEKRAR_NEDEN_AZAMI = 10


@router.post("/{dil:dil}/hesabim/siparis/{no}/tekrar")
async def kalemleri_tekrar_ekle(request: Request, dil: str, no: str, con=Depends(db_bagimliligi)) -> Response:
    """Siparişin kalemleri sepete eklenir; sepete ekleme kuralları aynen (teklifle satılan ve pasif ürün eklenmez,
    adet ayrılabilir stoka ve genel üst sınıra iner). Sonuç bildirimle sepette."""
    await csrf_dogrula(request)
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return _giris_yonlendir(dil, f"/{dil}/hesabim/siparis/{no}")
    siparis = _sahip_siparis(con, no, musteri)
    eklenen, sinirli, eklenemeyen, ust_sinir = 0, [], [], False
    t = request.app.state.ceviri.t
    with con:
        sepet_id = sepet_servis.sepet_bul(con, oturum_kimligi(request), musteri.id, _simdi())
        ayrilan = ayrilan_adetler(con, _simdi(), haric_sepet_id=sepet_id)
        for k in siparis.kalemler:
            ad = gorunen_ad(request, con, k.urun_id, k.ad)
            onceki = con.execute("SELECT adet FROM sepet_kalemi WHERE sepet_id = ? AND urun_id = ?",
                                 (sepet_id, k.urun_id)).fetchone()
            # G3k madde 18: eklenemeyen kalemin nedeni ayrı (satıştan kalktı / teklifle satılır / stokta yok /
            # kendi ödeme bekleyen siparişiniz ayırıyor)
            try:
                yeni, stok = sepet_servis.ekle(con, sepet_id, k.urun_id, k.adet, ayrilan)
            except sepet_servis.UrunYok:
                eklenemeyen.append(t(dil, "hesap.neden_ad", ad=ad, neden=t(dil, "hesap.neden_satistan_kalkti")))
                continue
            except sepet_servis.TeklifZorunlu:
                eklenemeyen.append(t(dil, "hesap.neden_ad", ad=ad, neden=t(dil, "hesap.neden_teklif")))
                continue
            fark = yeni - (onceki[0] if onceki else 0)
            if fark > 0:
                eklenen += 1
            if stok is not None and fark > 0:    # ayrılabilir stok sınırı
                sinirli.append(ad)
            elif stok is not None:
                kendi = _kendi_bekleyen(con, musteri.id, k.urun_id)
                neden = (t(dil, "hesap.neden_kendi_siparis", no=kendi) if kendi
                         else t(dil, "hesap.neden_stok_yok"))
                eklenemeyen.append(t(dil, "hesap.neden_ad", ad=ad, neden=neden))
            elif fark < k.adet:                  # inceleme M-2: genel üst sınır (99), stok değil
                ust_sinir = True
    if eklenen:
        bildir(request, "hesap.tekrar_eklendi", adet=eklenen)
    if sinirli:
        bildir(request, "hesap.tekrar_sinirli", adlar=", ".join(sinirli))
    if eklenemeyen and not eklenen and con.execute("SELECT 1 FROM sepet_kalemi WHERE sepet_id = ? LIMIT 1",
                                                    (sepet_id,)).fetchone() is None:
        # G3n madde 3: hiçbiri eklenemedi ve sepet boş: sepet sayfasında "Sepetiniz boş" yerine neden listesi
        # (bir kez; PRG). Çerez boyutu için en çok 10 neden, her biri kısaltılmış.
        request.session["tekrar_nedenleri"] = [n[:200] for n in eklenemeyen[:TEKRAR_NEDEN_AZAMI]]
    elif eklenemeyen:
        bildir(request, "hesap.tekrar_eklenemedi", adlar="; ".join(eklenemeyen))
    if ust_sinir:
        bildir(request, "sepet.ust_sinir", azami=sepet_servis.ADET_MAX)
    return RedirectResponse(f"/{dil}/sepet", status_code=303)


def _kendi_bekleyen(con: sqlite3.Connection, musteri_id: int, urun_id: int) -> str | None:
    """G3k madde 18: müşterinin bu ürünü içeren ödeme bekleyen siparişinin numarası (stoğu o ayırıyor) ya da None."""
    r = con.execute("SELECT s.no FROM siparis s JOIN siparis_kalemi k ON k.siparis_id = s.id WHERE s.musteri_id = ?"
                    " AND s.durum = 'odeme_bekliyor' AND k.urun_id = ? ORDER BY s.id DESC LIMIT 1",
                    (musteri_id, urun_id)).fetchone()
    return r[0] if r else None


# ---------- madde 7: proforma fatura ----------

def _proforma_baglami(siparis: Siparis, urunler: dict, dil: str) -> dict:
    p, kur = siparis.para_birimi, siparis.kur
    satirlar = []
    for k in siparis.kalemler:
        u = urunler.get(k.urun_id)
        oran = (k.kdv * 100 / k.net).quantize(Decimal("1")) if k.net else Decimal("0")
        # inceleme M-3: birim gösterim için yuvarlanır; satır tutarı (kayıtlı net) birim × adetten kuruş sapabilir (not)
        birim = yuvarla(k.birim_net_eur * kur) if p == "TRY" and kur is not None else yuvarla(k.birim_net_eur)
        satirlar.append({"kalem": k, "kod": (u.uretici_kodu if u else None) or k.sku, "birim": birim, "oran": oran})
    kdv_urunler = sum((k.kdv for k in siparis.kalemler), Decimal("0.00"))
    toplamlar = [("tutar.ara_toplam", siparis.ara_toplam)]
    if siparis.teslim_yontemi != "yurtdisi_dap":
        toplamlar.append(("tutar.kargo", siparis.kargo))
    if siparis.ihracat_istisnasi:
        toplamlar.append(("tutar.ihracat_istisnasi", siparis.kdv))
    else:
        toplamlar += [("tutar.kdv_urunler", kdv_urunler), ("tutar.kdv_kargo", siparis.kdv - kdv_urunler)]
    toplamlar.append(("tutar.mal_bedeli" if siparis.teslim_yontemi == "yurtdisi_dap" else "tutar.toplam",
                      siparis.toplam))
    eur = p == "TRY" and kur is not None and kur > 0     # TL toplamların sabitlenen kurla EUR karşılığı
    return {
        "satirlar": satirlar,
        "toplamlar": [{"etiket": e, "tutar": t, "eur": yuvarla(t / kur) if eur else None} for e, t in toplamlar],
        "eur_karsilik": eur,
        "kur_metni": kur_bicimle(kur, dil) if kur is not None else "",
        "yurtdisi": siparis.teslimat_ulkesi != "TR",
    }


@router.get("/{dil:dil}/hesabim/siparis/{no}/proforma")
def proforma(request: Request, dil: str, no: str, con=Depends(db_bagimliligi)) -> Response:
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return _giris_yonlendir(dil, f"/{dil}/hesabim/siparis/{no}/proforma")
    siparis = _sahip_siparis(con, no, musteri)
    if siparis.odeme_yontemi != "havale" or siparis.durum == "iptal":   # inceleme M-4: iptalde belge yok
        raise HTTPException(status_code=404)
    ayarlar = request.app.state.ayarlar
    urunler = _urunler(con, siparis)
    return sablon(request, "proforma.html", {
        "siparis": siparis, "urunler": urunler, **_proforma_baglami(siparis, urunler, dil),
        "alici": siparis_alicisi(siparis, musteri),
        "satici_vkn": (getattr(ayarlar, "satici_vkn", "") or "").strip(),
        "satici_vergi_dairesi": (getattr(ayarlar, "satici_vergi_dairesi", "") or "").strip(),
        "satici_adres": SATICI_ADRES + ("" if dil == "tr" else ", Türkiye"),
        "gb_gizle": True,
    })


# ---------- madde 9: fatura bilgilerim ----------

def _son_siparis_adresleri(con: sqlite3.Connection, musteri_id: int) -> tuple[Adres | None, Adres | None]:
    """G3j madde 3: hesabın son siparişindeki (fatura, teslimat) adres anlık görüntüsü; sipariş yoksa (None, None)."""
    r = con.execute("SELECT fatura_adresi, teslimat_adresi FROM siparis WHERE musteri_id = ? ORDER BY id DESC LIMIT 1",
                    (musteri_id,)).fetchone()
    if r is None:
        return None, None
    try:
        return (Adres(**json.loads(r["fatura_adresi"])) if r["fatura_adresi"] else None,
                Adres(**json.loads(r["teslimat_adresi"])) if r["teslimat_adresi"] else None)
    except (ValueError, TypeError):
        return None, None


def _fatura_alanlari(con: sqlite3.Connection, musteri: Musteri) -> dict[str, str]:
    """Kayıtlı fatura (yoksa teslimat) adresi. G3j madde 3: profilde adres kaydı yoksa (eski hesap) son siparişin fatura
    / teslimat adresinden ön doldurulur — kaydedilmez, ziyaretçi "Kaydet" ile onaylar. Telefon fatura adresinde yoksa
    teslimat adresinden."""
    fatura, teslimat = adres_son(con, musteri.id, "fatura"), adres_son(con, musteri.id, "teslimat")
    if fatura is None and teslimat is None:
        fatura, teslimat = _son_siparis_adresleri(con, musteri.id)
    adres = fatura or teslimat
    telefon = next((a.telefon for a in (fatura, teslimat) if a is not None and a.telefon), "")
    return {"ad": musteri.ad, "vergi_dairesi": musteri.vergi_dairesi or "",
            "satir1": adres.satir1 if adres else "", "satir2": (adres.satir2 or "") if adres else "",
            "posta_kodu": (adres.posta_kodu or "") if adres else "", "sehir": adres.sehir if adres else "",
            "telefon": telefon or ""}


def _fatura_sayfasi(request: Request, musteri: Musteri, alanlar: dict, hatalar: dict, durum: int = 200) -> Response:
    return sablon(request, "hesabim_fatura.html", {"alanlar": alanlar, "hatalar": hatalar,
                                                   "kurumsal": musteri.tip == MusteriTipi.KURUMSAL}, durum)


@router.get("/{dil:dil}/hesabim/fatura")
def fatura_bilgilerim(request: Request, dil: str, con=Depends(db_bagimliligi)) -> Response:
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return _giris_yonlendir(dil, f"/{dil}/hesabim/fatura")
    return _fatura_sayfasi(request, musteri, _fatura_alanlari(con, musteri), {})


@router.post("/{dil:dil}/hesabim/fatura")
async def fatura_kaydet(request: Request, dil: str, con=Depends(db_bagimliligi)) -> Response:
    await csrf_dogrula(request)
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return _giris_yonlendir(dil, f"/{dil}/hesabim/fatura")
    form = await request.form()
    alanlar = {ad: str(form.get(ad, "")).strip()[:UZUNLUK + 1] for ad in FATURA_ALANLARI}
    kurumsal = musteri.tip == MusteriTipi.KURUMSAL
    if not kurumsal:
        alanlar["vergi_dairesi"] = ""
    hatalar: dict[str, str] = {}
    for ad, deger in alanlar.items():
        if len(deger) > UZUNLUK:
            hatalar[ad] = "hata_kodu.cok_uzun"
            alanlar[ad] = deger[:UZUNLUK]
    # kayıt formunun kuralları: unvan/ad zorunlu, kurumsalda vergi dairesi zorunlu; adreste satır 1 ve şehir zorunlu
    for ad in ("ad", "satir1", "sehir") + (("vergi_dairesi",) if kurumsal else ()):
        if not alanlar[ad]:
            hatalar[ad] = "hata_kodu.zorunlu"
    if alanlar["telefon"] and "telefon" not in hatalar and not telefon_gecerli(alanlar["telefon"]):
        hatalar["telefon"] = "hata_kodu.telefon_gecersiz"
    if hatalar:
        return _fatura_sayfasi(request, musteri, alanlar, hatalar, 400)
    adres = Adres(ad_soyad=alanlar["ad"], satir1=alanlar["satir1"], sehir=alanlar["sehir"],
                  ulke=(musteri.ulke or "TR").upper(), satir2=alanlar["satir2"] or None,
                  posta_kodu=alanlar["posta_kodu"] or None, telefon=alanlar["telefon"] or None)
    try:
        with con:
            fatura_bilgisi_guncelle(con, musteri.id, ad=alanlar["ad"],
                                    vergi_dairesi=alanlar["vergi_dairesi"] if kurumsal else None)
            adres_kaydet(con, musteri.id, "fatura", adres)
    except KayitHatasi as hata:
        return _fatura_sayfasi(request, musteri, alanlar, {hata.alan: f"hata_kodu.{hata.kod}"}, 400)
    bildir(request, "hesap.fatura_guncellendi")
    return RedirectResponse(f"/{dil}/hesabim/fatura", status_code=303)
