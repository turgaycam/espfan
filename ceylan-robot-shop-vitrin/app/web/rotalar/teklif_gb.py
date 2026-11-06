"""Teklif formu ve geri bildirim uç noktası (Görev 15; G3c madde 21 + G3a N-1/N-1b/N-4, G3b N-4)."""
from __future__ import annotations

import re
import sqlite3
import time
from datetime import UTC, date, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.geribildirim import servis as gb_servis
from app.fiyat.kurallar import MusteriTipi
from app.hesap.servis import adres_son
from app.siparis.servis import son_siparis_adresleri
from app.hesap.dogrulama import eposta_gecerli, telefon_gecerli, vat_id_kontrol, vergi_no_hatasi
from app.katalog.depo import Urun, kod_eslesmeleri, urun_getir
from app.sepet import servis as sepet_servis
from app.teklif.servis import (KALEM_MAX, TeklifGirdisi, TeklifHatasi, hizli_teklif_olustur, iletisim_ayir,
                               teklif_no_ile, teklif_olustur)
from app.web.bagimlilik import db_bagimliligi
from app.web.baglam import ULKELER, mevcut_sepet_id, musteri_ulkesi, sablon, ulke_tercihi, varsayilan_ulke
from app.web.koruma import muaf_mi
from app.web.guvenlik import aktif_musteri, csrf_dogrula

router = APIRouter()

TEKLIF_ALANLARI = ("ad", "firma", "eposta", "telefon", "ulke", "vat_id", "urun_id", "adet", "mesaj", "kvkk_onay",
                   # G3e madde 17: isteğe bağlı yeni alanlar; madde 16: kaynak=sepet (sepeti teklif olarak gönder)
                   "vkn", "vergi_dairesi", "istenen_tarih", "hedef_fiyat", "parca_kodu", "kaynak",
                   "musteri_po",   # G3i madde 6
                   "teslim_adresi")   # G3j madde 16
# Herkese açık form: HTML maxlength ile aynı sınırlar sunucuda da uygulanır (kontrolcü kararı, Görev 15).
AZAMI_UZUNLUK = {"ad": 120, "eposta": 254, "firma": 160, "telefon": 40, "vat_id": 30, "vkn": 11,
                 "vergi_dairesi": 120, "istenen_tarih": 10, "hedef_fiyat": 200, "parca_kodu": 100,
                 "teslim_adresi": 200}
TARIH_DESENI = re.compile(r"\d{4}-\d{2}-\d{2}")
MESAJ_AZAMI = 2000
PO_AZAMI = 40
PO_YANSIMA = 200   # Fix 1 (m-7): hatalı PO formda en çok bu kadar karakterle geri basılır (41–200 yine hata alır)
ZORUNLU = ("ad", "mesaj")      # G3c: e-posta ya da telefondan biri; misafirde KVKK aydınlatma onayı
# Formun üstündeki hata özetinin sırası ve etiketleri (alan sırası = form sırası)
ETIKETLER = {"ad": "teklif.ad", "firma": "teklif.firma", "vkn": "teklif.vkn", "vergi_dairesi": "teklif.vergi_dairesi",
             "eposta": "teklif.eposta", "telefon": "teklif.telefon",
             "ulke": "teklif.ulke", "vat_id": "teklif.vat_id", "parca_kodu": "teklif.parca_kodu",
             "kalemler": "teklif.kalemler", "adet": "teklif.adet",
             "istenen_tarih": "teklif.istenen_tarih", "hedef_fiyat": "teklif.hedef_fiyat",
             "musteri_po": "odeme.musteri_po", "teslim_adresi": "teklif.teslim_adresi", "mesaj": "teklif.mesaj",
             "urun_id": "teklif.urun", "kvkk_onay": "teklif.kvkk_etiket"}
TEKLIF_NO_DESENI = re.compile(r"CR-TKL-\d{8}-\d{4,6}")   # günlük sayaç 9.999'u aşarsa genişler
ADET_AZAMI = 9999
TEKLIF_RETRY_AFTER = "600"   # app.state.teklif_hiz penceresi (10 dk); 429 metni "10 dakika" der
KOD_AZAMI = 100              # ?kod= ve hızlı talepteki parça kodu
HIZLI_ALANLAR = ("ad", "iletisim", "parca_kodu")
HIZLI_SINIRLAR = {"ad": 120, "iletisim": 254, "parca_kodu": KOD_AZAMI}
HIZLI_ETIKETLER = {"parca_kodu": "teklif.parca_kodu", "ad": "teklif.ad", "iletisim": "teklif.iletisim_alani",
                   "aciliyet": "teklif.aciliyet", "adet": "teklif.adet", "model": "teklif.model"}
ACILIYETLER = ("acil", "bu_hafta", "planli")   # G3i madde 16; seçilmezse NULL (zorunlu değil)
MODEL_AZAMI = 100
COK_DENEME = "hata_kodu.teklif_cok_deneme"


def _simdi() -> datetime:
    return datetime.now(UTC)


def _hata_anahtari(request: Request, kod: str) -> str:
    """K14: servis hata kodu -> i18n anahtarı (hata_kodu.*; Görev 11 zorunlu metnini hata_kodu.zorunlu adıyla tanımladı)."""
    anahtar = f"hata_kodu.{kod}"
    return anahtar if request.app.state.ceviri.var(anahtar) else "hata_kodu.gecersiz"


def _tamsayi(deger: object) -> int | None:
    try:
        return int(str(deger).strip())
    except (TypeError, ValueError):
        return None


def _urun(con: sqlite3.Connection, deger: object) -> Urun | None:
    urun_id = _tamsayi(deger)
    if urun_id is None or not 0 < urun_id < 2**63:
        return None
    urun = urun_getir(con, urun_id)
    return urun if urun is not None and urun.aktif else None


def _teklif_sayfasi(request: Request, alanlar: dict[str, str], urun: Urun | None,
                    hatalar: dict[str, str], durum: int = 200, *, genel_hata: str | None = None,
                    kvkk_gerekli: bool = True, kalemler: list[dict] | None = None,
                    atlanan: list[dict] | None = None) -> Response:
    """kalemler: G3g madde 2 — sepetten gelen düzenlenebilir satırlar ({urun_id, ad, kod, adet})."""
    ozet = [{"hedef": ad, "etiket": etiket, "hata": hatalar[ad]} for ad, etiket in ETIKETLER.items() if ad in hatalar]
    yanit = sablon(request, "teklif.html", {
        "alanlar": alanlar, "urun": urun, "hatalar": hatalar, "hata_ozeti": ozet, "genel_hata": genel_hata,
        "ulke_secenekleri": ULKELER, "sinirlar": AZAMI_UZUNLUK, "mesaj_azami": MESAJ_AZAMI,
        "kvkk_gerekli": kvkk_gerekli, "kalemler": kalemler or [], "kalem_azami": KALEM_MAX,
        "atlanan": atlanan or [],
        "telefon_zorunlu": alanlar.get("kaynak") == "sepet" and kvkk_gerekli,   # hesapsız sepet yolunda
    }, durum)
    if durum == 429:
        yanit.headers["Retry-After"] = TEKLIF_RETRY_AFTER
    return yanit


def _musteri_ulkesi(request: Request, musteri) -> str | None:
    """G3b N-4: girişli müşteride teklif ülkesi fiyat bağlamıyla aynı kaynaktan (oturumda seçilen > kayıtlı)."""
    if musteri is None:
        return None
    ulke = musteri_ulkesi(request, musteri)
    return ulke if ulke in ULKELER else None


@router.get("/{dil:dil}/teklif")
def teklif_formu(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    musteri = aktif_musteri(request, con)
    alanlar = {ad: "" for ad in TEKLIF_ALANLARI}
    alanlar["adet"] = "1"
    # düzeltme 1 (M-8): ülke seçilmemişse (EN, bölgesiz) boş: "Ülkenizi seçin"
    alanlar["ulke"] = _musteri_ulkesi(request, musteri) or varsayilan_ulke(request) or ""
    if musteri is not None:
        # G3c madde 21: kayıtlı VAT ID taşınır. G3e madde 17: kurumsal hesapta "Ad soyad / unvan" kayıtta unvan olarak
        # alınır; Firma, VKN ve vergi dairesi profilden dolar (bireysel / yurt dışında Firma boş kalır).
        # G3k madde 13: "Ad soyad" yalnız bireysel hesapta (kişi adı) dolar; kurumsal / yurt dışı hesapta kayıtlı ad
        # firma unvanıdır, kişi adı yoktur: boş kalır. Telefon fatura bilgilerinden (yoksa son teslimat adresinden).
        # G3m madde 21: kurumsal / yurt dışı hesapta "Ad soyad" kayıtlı adreslerdeki ya da son siparişin alıcı anlık
        # görüntüsündeki kişi adından (unvandan farklıysa: proformadaki "İlgili" kuralı); telefon da aynı sırayla
        siparis_adresleri = son_siparis_adresleri(con, musteri.id) or ()
        adresler = [a for a in (adres_son(con, musteri.id, "fatura"), adres_son(con, musteri.id, "teslimat"),
                                *siparis_adresleri) if a is not None]
        ilgili = next((a.ad_soyad.strip() for a in adresler
                       if (a.ad_soyad or "").strip() and a.ad_soyad.strip().casefold() != musteri.ad.strip().casefold()),
                      "")
        alanlar.update(ad=musteri.ad if musteri.tip == MusteriTipi.BIREYSEL else ilgili, eposta=musteri.eposta,
                       vat_id=musteri.vat_id or "")
        alanlar["telefon"] = next((a.telefon for a in adresler if a.telefon), "")
        if musteri.tip != MusteriTipi.BIREYSEL:      # G3l madde 13: yurt dışı hesapta da Firma = kayıtlı unvan
            alanlar["firma"] = musteri.ad
        if musteri.tip == MusteriTipi.KURUMSAL:
            alanlar.update(vkn=musteri.vergi_kimlik_no or "", vergi_dairesi=musteri.vergi_dairesi or "")
    urun = _urun(con, request.query_params.get("urun_id"))
    if urun is not None:
        alanlar["urun_id"] = str(urun.id)
    adet = _tamsayi(request.query_params.get("adet"))
    if adet is not None and 1 <= adet <= ADET_AZAMI:   # G3e madde 1: stok aşımında istenen adet formda dolu
        alanlar["adet"] = str(adet)
    kalemler: list[dict] = []
    atlanan: list[dict] = []
    if request.query_params.get("sepet") == "1":       # G3e madde 16 / G3g madde 2: sepeti teklif olarak gönder
        kalemler, atlanan = _sepet_teklifi(request, con, musteri, dil, alanlar)
        if kalemler:
            urun = None
    kod = _temiz_kod(request.query_params.get("kod"))
    if kod:   # G3a madde 9: listede bulunamayan parça kodu forma taşınır (G3e: "Parça kodu" alanına da)
        alanlar["mesaj"] = request.app.state.ceviri.t(dil, "teklif.parca_mesaj", kod=kod)
        alanlar["parca_kodu"] = kod
    yanit = _teklif_sayfasi(request, alanlar, urun, {}, kvkk_gerekli=musteri is None, kalemler=kalemler,
                            atlanan=atlanan)
    return yanit


def _sepet_teklifi(request: Request, con: sqlite3.Connection, musteri, dil: str,
                   alanlar: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """G3g madde 2: sepet kalemleri -> düzenlenebilir teklif satırları (ürün, parça no, adet; en çok KALEM_MAX).
    Sınırı aşan kalemler (inceleme I-2) sessizce düşmez: ikinci listede döner, formun üstünde uyarıyla ve mesaja satır
    olarak yazılır (kaydedilen mesaj formda görünenle aynı). GET yan etkisizdir (inceleme M-3): stok sınırı uygulanmaz,
    tümü ayrılmış kalem de teklif yoluna sepetteki adediyle girer."""
    sid = mevcut_sepet_id(con, request, musteri)
    if sid is None:
        return [], []
    with con:
        kalemler, _ = sepet_servis.kalemler(con, sid)
    if not kalemler:
        return [], []
    satirlar = []
    for k in kalemler:
        u = urun_getir(con, k.urun_id)
        satirlar.append({"urun_id": k.urun_id, "ad": k.ad, "kod": (u.uretici_kodu if u else None) or k.sku,
                         "adet": str(k.adet)})
    t = request.app.state.ceviri.t
    alanlar["kaynak"] = "sepet"
    satirlar, atlanan = satirlar[:KALEM_MAX], satirlar[KALEM_MAX:]
    alanlar["mesaj"] = "\n".join([t(dil, "teklif.sepet_mesaj"),
                                  *(t(dil, "teklif.sepet_satiri", adet=k["adet"], ad=k["ad"], kod=k["kod"])
                                    for k in atlanan)])
    return satirlar, atlanan


def _kalem_satirlari(con: sqlite3.Connection, form) -> tuple[list[dict], list[tuple[int, int]], str | None]:
    """G3g madde 2: gönderilen satırlar (kalem_urun / kalem_adet; en çok 20) -> (formda geri basılacak satırlar,
    kaydedilecek (urun_id, adet) listesi, hata anahtarı). 0 adetli satır gönderilmez; aynı ürün birleşir."""
    urunler, adetler = form.getlist("kalem_urun"), form.getlist("kalem_adet")
    hata = "hata_kodu.kalem_cok" if len(urunler) > KALEM_MAX else None   # inceleme I-2: sessiz kırpma yok
    urunler = urunler[:KALEM_MAX]
    satirlar: list[dict] = []
    toplam: dict[int, int] = {}
    for i, ham in enumerate(urunler):
        urun = _urun(con, ham)
        adet_ham = str(adetler[i] if i < len(adetler) else "").strip()[:6]
        if urun is None:
            hata = hata or "hata_kodu.gecersiz"
            continue
        satirlar.append({"urun_id": urun.id, "ad": urun.ad, "kod": urun.uretici_kodu or urun.sku, "adet": adet_ham})
        adet = _tamsayi(adet_ham or "0")
        if adet is None or not 0 <= adet <= ADET_AZAMI:
            hata = hata or "hata_kodu.adet_araligi"
        elif adet:
            toplam[urun.id] = min(ADET_AZAMI, toplam.get(urun.id, 0) + adet)
    return satirlar, list(toplam.items()), hata


def _teklif_hizi_asildi(request: Request) -> bool:
    """G3a: herkese açık teklif yazma uçlarında IP başına hız sınırı (geri bildirimdeki kalıp, ayrı kova). Yalnız
    doğrulamadan geçen (kayıt açacak) gönderimlerde çağrılır: yazım hatası düzelten kullanıcı kotasını harcamaz
    (G3a N-1: iletişim biçimi de sınırdan önce denetlenir). Aşımda çağıran aynı formu girdisiyle 429 + Retry-After
    ile gösterir (N-1b). Bal küpüyle engelli IP zaten KoruMiddleware'de 403 alır; SHOP_KORUMA_MUAF_IP sınırdan muaftır."""
    ip = request.client.host if request.client else "bilinmiyor"
    if muaf_mi(ip, request.app.state.ayarlar.koruma_muaf):
        return False
    return not request.app.state.teklif_hiz.izin(f"teklif:{ip}", time.monotonic())


def _tarih_gecerli(deger: str) -> bool:
    """G3e madde 17: istenen teslim tarihi YYYY-MM-DD (input type=date biçimi), gerçek bir gün."""
    if not TARIH_DESENI.fullmatch(deger):
        return False
    try:
        date.fromisoformat(deger)
    except ValueError:
        return False
    return True


def _temiz_kod(deger: object) -> str:
    return "".join(c for c in str(deger or "") if c.isprintable()).strip()[:KOD_AZAMI]


@router.post("/{dil:dil}/teklif/hizli")
async def hizli_teklif(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    """G3a madde 9: boş sonuç sayfasındaki kısa form -> teklif kaydı. Hata olursa aynı 3 alanlı form, hata özetiyle;
    hız sınırı aşılırsa aynı form girdisiyle 429 (G3a N-1b)."""
    await csrf_dogrula(request)
    musteri = aktif_musteri(request, con)
    form = await request.form()
    alanlar = {ad: "".join(c for c in str(form.get(ad, "")) if c.isprintable()).strip() for ad in HIZLI_ALANLAR}
    hatalar: dict[str, str] = {}
    for ad, sinir in HIZLI_SINIRLAR.items():
        if not alanlar[ad]:
            hatalar[ad] = "hata_kodu.zorunlu"
        elif len(alanlar[ad]) > sinir:
            hatalar[ad] = "hata_kodu.cok_uzun"
            alanlar[ad] = alanlar[ad][:sinir]
    # G3i madde 16: isteğe bağlı aciliyet, adet (boşsa 1) ve robot/kontrolör modeli
    alanlar["aciliyet"] = str(form.get("aciliyet", "")).strip()[:20]
    alanlar["adet"] = str(form.get("adet", "")).strip()[:6]
    alanlar["model"] = "".join(c for c in str(form.get("model", "")) if c.isprintable()).strip()
    if alanlar["aciliyet"] and alanlar["aciliyet"] not in ACILIYETLER:
        hatalar["aciliyet"] = "hata_kodu.gecersiz"
        alanlar["aciliyet"] = ""
    adet = _tamsayi(alanlar["adet"] or "1")
    if adet is None or not 1 <= adet <= ADET_AZAMI:
        hatalar["adet"] = "hata_kodu.adet_araligi"
    if len(alanlar["model"]) > MODEL_AZAMI:
        hatalar["model"] = "hata_kodu.cok_uzun"
        alanlar["model"] = alanlar["model"][:MODEL_AZAMI]
    if "iletisim" not in hatalar:
        try:
            eposta, _ = iletisim_ayir(alanlar["iletisim"])   # G3a N-1: biçim hatası hız kotasını harcamaz
        except TeklifHatasi as hata:
            hatalar["iletisim"] = _hata_anahtari(request, hata.kod)
        else:
            if alanlar["aciliyet"] == "acil" and eposta is not None:   # G3j madde 2: acilde telefonla dönüş
                hatalar["iletisim"] = "hata_kodu.acil_telefon"
    genel_hata = None
    if not hatalar:
        if _teklif_hizi_asildi(request):
            genel_hata = COK_DENEME
        else:
            ceviri = request.app.state.ceviri
            # G3j madde 1: parça kodu katalogda tam eşleşirse talep ürüne bağlanır (tek eşleşme); mesaj gerçeği yazar
            eslesmeler = kod_eslesmeleri(con, alanlar["parca_kodu"])
            kod = alanlar["parca_kodu"]
            if len(eslesmeler) == 1:
                mesaj = ceviri.t(dil, "teklif.hizli_mesaj_bulundu", ad=eslesmeler[0].ad, kod=kod)
            elif eslesmeler:
                mesaj = ceviri.t(dil, "teklif.hizli_mesaj_n", n=len(eslesmeler), kod=kod)
            else:
                mesaj = ceviri.t(dil, "teklif.hizli_mesaj", kod=kod)
            try:
                with con:
                    teklif = hizli_teklif_olustur(
                        con, ad=alanlar["ad"], iletisim=alanlar["iletisim"], parca_kodu=alanlar["parca_kodu"],
                        ulke=_musteri_ulkesi(request, musteri) or ulke_tercihi(request),
                        mesaj=mesaj, simdi=_simdi(),
                        musteri_id=musteri.id if musteri is not None else None, adet=adet,
                        aciliyet=alanlar["aciliyet"] or None, model=alanlar["model"] or None,
                        urun_id=eslesmeler[0].id if len(eslesmeler) == 1 else None)
            except TeklifHatasi as hata:
                hatalar[hata.alan if hata.alan in HIZLI_ALANLAR else "iletisim"] = _hata_anahtari(request, hata.kod)
            else:
                request.session["son_teklif"] = teklif.no     # G3g madde 26: onay sayfasında özet yalnız gönderene
                return RedirectResponse(f"/{dil}/teklif/tamam?no={quote(teklif.no)}", status_code=303)
    ozet = [{"hedef": "ht-aciliyet-acil" if ad == "aciliyet" else f"ht-{ad}", "etiket": etiket, "hata": hatalar[ad]}
            for ad, etiket in HIZLI_ETIKETLER.items() if ad in hatalar]
    yanit = sablon(request, "teklif_hizli.html", {"alanlar": alanlar, "hatalar": hatalar, "hata_ozeti": ozet,
                                                  "genel_hata": genel_hata, "sinirlar": HIZLI_SINIRLAR},
                   429 if genel_hata else 400)
    if genel_hata:
        yanit.headers["Retry-After"] = TEKLIF_RETRY_AFTER
    return yanit


@router.post("/{dil:dil}/teklif")
async def teklif_gonder(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    await csrf_dogrula(request)
    musteri = aktif_musteri(request, con)
    form = await request.form()
    alanlar = {ad: str(form.get(ad, "")).strip() for ad in TEKLIF_ALANLARI}
    alanlar["ulke"] = alanlar["ulke"].upper()
    alanlar["kaynak"] = "sepet" if alanlar["kaynak"] == "sepet" else ""
    alanlar["vkn"] = alanlar["vkn"].replace(" ", "")
    if alanlar["ulke"] != "TR":          # G3g madde 15: VKN / vergi dairesi yalnız Türkiye'deki alıcı için
        alanlar["vkn"] = alanlar["vergi_dairesi"] = ""
    urun = _urun(con, alanlar["urun_id"])
    alanlar["urun_id"] = str(urun.id) if urun is not None else ""
    if urun is not None:
        alanlar["parca_kodu"] = ""          # ürünlü formda parça kodu alanı yok
    kvkk_gerekli = musteri is None     # üye kayıtta aydınlatma metnini onayladı

    hatalar: dict[str, str] = {}
    for ad in ZORUNLU:
        if not alanlar[ad]:
            hatalar[ad] = "hata_kodu.zorunlu"
    for ad, sinir in AZAMI_UZUNLUK.items():
        if len(alanlar[ad]) > sinir:
            hatalar[ad] = "hata_kodu.cok_uzun"
            alanlar[ad] = alanlar[ad][:sinir]          # sayfaya geri yazılan değer de sınırlı kalır
    if len(alanlar["mesaj"]) > MESAJ_AZAMI:
        hatalar["mesaj"] = "hata_kodu.cok_uzun"
    if len(alanlar["musteri_po"]) > PO_AZAMI:          # G3i madde 6
        hatalar["musteri_po"] = "hata_kodu.po_uzun"   # G3n madde 9: 40'ta kırpılmaz (m-7: yansıma 200 ile sınırlı)
        alanlar["musteri_po"] = alanlar["musteri_po"][:PO_YANSIMA]
    # G3c madde 21 + G3a: e-posta ya da telefondan biri yeterli; biçimleri hızlı uçla aynı yardımcılarla (N-4)
    if not alanlar["eposta"] and not alanlar["telefon"]:
        hatalar["eposta"] = "hata_kodu.iletisim_gerekli"
    if alanlar["eposta"] and "eposta" not in hatalar and not eposta_gecerli(alanlar["eposta"]):
        hatalar["eposta"] = "hata_kodu.gecersiz"
    if alanlar["telefon"] and "telefon" not in hatalar and not telefon_gecerli(alanlar["telefon"]):
        hatalar["telefon"] = "hata_kodu.telefon_gecersiz"
    if alanlar["kaynak"] == "sepet" and kvkk_gerekli and not alanlar["telefon"]:   # G3e madde 16: hesapsız yolda
        hatalar["telefon"] = "hata_kodu.zorunlu"
    satirlar, kalemler, kalem_hatasi = _kalem_satirlari(con, form)   # G3g madde 2: sepetten gelen satırlar
    if kalem_hatasi:
        hatalar["kalemler"] = kalem_hatasi
    elif alanlar["kaynak"] == "sepet" and satirlar and not kalemler:
        hatalar["kalemler"] = "hata_kodu.kalem_yok"
    if alanlar["vkn"] and "vkn" not in hatalar and vergi_no_hatasi(alanlar["vkn"]) is not None:   # G3m madde 26
        hatalar["vkn"] = f"hata_kodu.{vergi_no_hatasi(alanlar['vkn'])}"
    if alanlar["istenen_tarih"] and "istenen_tarih" not in hatalar and not _tarih_gecerli(alanlar["istenen_tarih"]):
        hatalar["istenen_tarih"] = "hata_kodu.tarih_gecersiz"
    adet = _tamsayi(alanlar["adet"] or "1")
    if kalemler:                               # çok kalemli teklif: teklif.adet kalemlerin toplamı, ürün yok
        adet, urun = min(ADET_AZAMI, sum(a for _, a in kalemler)), None
        alanlar["urun_id"] = ""
    elif adet is None or not 1 <= adet <= ADET_AZAMI:
        hatalar["adet"] = "hata_kodu.adet_araligi"
    if alanlar["ulke"] not in ULKELER:
        hatalar["ulke"] = "hata_kodu.ulke_kodu"
    vat_id = None
    if "vat_id" not in hatalar and "ulke" not in hatalar:
        vat_id, kod = vat_id_kontrol(alanlar["vat_id"], alanlar["ulke"], zorunlu_ab=False)
        if kod is not None:
            hatalar["vat_id"] = _hata_anahtari(request, kod)
    if kvkk_gerekli and alanlar["kvkk_onay"] != "1":
        hatalar["kvkk_onay"] = "hata_kodu.kvkk_onay_yok"
    if hatalar:
        return _teklif_sayfasi(request, alanlar, urun, hatalar, 400, kvkk_gerekli=kvkk_gerekli, kalemler=satirlar)

    if _teklif_hizi_asildi(request):   # yalnız kayıt oluşturacak gönderimler sayılır; form girdisiyle geri döner
        return _teklif_sayfasi(request, alanlar, urun, {}, 429, genel_hata=COK_DENEME, kvkk_gerekli=kvkk_gerekli,
                               kalemler=satirlar)
    girdi = TeklifGirdisi(ad=alanlar["ad"], eposta=alanlar["eposta"] or None, ulke=alanlar["ulke"],
                          mesaj=alanlar["mesaj"], firma=alanlar["firma"] or None, telefon=alanlar["telefon"] or None,
                          urun_id=urun.id if urun is not None else None, adet=adet,
                          musteri_id=musteri.id if musteri is not None else None, vat_id=vat_id,
                          kvkk_onay=_simdi().isoformat() if kvkk_gerekli else None,
                          vkn=alanlar["vkn"] or None, vergi_dairesi=alanlar["vergi_dairesi"] or None,
                          istenen_tarih=alanlar["istenen_tarih"] or None, hedef_fiyat=alanlar["hedef_fiyat"] or None,
                          parca_kodu=alanlar["parca_kodu"] or None, kalemler=tuple(kalemler),
                          musteri_po=alanlar["musteri_po"] or None,
                          teslim_adresi=alanlar["teslim_adresi"] or None)
    try:
        with con:
            teklif = teklif_olustur(con, girdi, _simdi())
    except TeklifHatasi as hata:
        return _teklif_sayfasi(request, alanlar, urun, {hata.alan: _hata_anahtari(request, hata.kod)}, 400,
                               kvkk_gerekli=kvkk_gerekli, kalemler=satirlar)
    request.session["son_teklif"] = teklif.no          # G3g madde 26: onay sayfasında özet yalnız gönderene
    return RedirectResponse(f"/{dil}/teklif/tamam?no={quote(teklif.no)}", status_code=303)


@router.get("/{dil:dil}/teklif/tamam")
def teklif_tamam(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    # con: ortak bağlam (başlıktaki hesap/sepet, "Hesabım" bağlantısı) için
    no = request.query_params.get("no", "")
    no = no if TEKLIF_NO_DESENI.fullmatch(no) else None
    teklif = None
    if no is not None:
        # G3g madde 26: kalem özeti yalnız bu oturumda gönderilen ya da hesabın kendi teklifinde (numara tahmin edilebilir)
        aday = teklif_no_ile(con, no)
        musteri = aktif_musteri(request, con)
        if aday is not None and (request.session.get("son_teklif") == no
                                 or (musteri is not None and aday.musteri_id == musteri.id)):
            teklif = aday
    # G3j madde 1: parça kodlu talepte katalog eşleşmesi (ürün, stok, doğrudan sipariş bağlantısı)
    eslesmeler = (kod_eslesmeleri(con, teklif.parca_kodu) if teklif is not None and teklif.parca_kodu
                  and not teklif.kalemler else [])
    return sablon(request, "teklif_tamam.html", {"no": no, "teklif": teklif, "eslesmeler": eslesmeler})


@router.post("/geri-bildirim")
async def geri_bildirim(request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    await csrf_dogrula(request)
    ip = request.client.host if request.client else "bilinmiyor"
    if not request.app.state.hiz.izin(f"gb:{ip}", time.monotonic()):   # IP başına 10/dk
        return JSONResponse({"tamam": False, "hata": "cok_deneme"}, status_code=429)
    form = await request.form()
    metin = str(form.get("metin", "")).strip()
    sayfa = str(form.get("sayfa", "")).strip()[:500] or "/"
    isim = str(form.get("isim", "")).strip()[:100] or None
    try:
        with con:
            gb_servis.kaydet(con, sayfa, metin, isim, _simdi())
    except ValueError:
        return JSONResponse({"tamam": False, "hata": "gecersiz"}, status_code=400)
    return JSONResponse({"tamam": True})
