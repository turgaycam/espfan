"""Sepet, ödeme, kart, sahte 3D Secure ve sipariş onayı rotaları (Görev 14)."""
from __future__ import annotations

import re
import secrets
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Mapping
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.fiyat.kur import Kur, son_kur
from app.fiyat.kurallar import (Baglam, FiyatGosterim, Kalem, KurYok, MusteriTipi, SepetTutari, TeslimYontemi,
                                birim_fiyat_gosterimi, gosterim_kdv_dahil, gosterim_kipi, sepet_hesapla,
                                sepet_hesapla_eur)
from app.hesap.dogrulama import eposta_gecerli, vat_id_kontrol, vergi_no_hatasi
from app.hesap.servis import (PAROLA_MIN, Adres, KayitGirdisi, KayitHatasi, Musteri, adres_kaydet, adres_son,
                              kayit_ol)
from app.para import yuvarla
from app.katalog.depo import urun_getir
from app.metin import yonelme_eki
from app.sepet import servis as sepet_servis
from app.stok import ayrilan_adetler
from app.siparis.odeme_sim import (BASARILI_KART, RET_KARTI, SMS_KODU, OdemeSonucu, deneme_getir,
                                   odeme_baslat, sms_dogrula)
from app.siparis.servis import (GecersizGecis, SepetBos, Siparis, SiparisDurumu, StokYetersiz, durum_degistir,
                                 siparis_getir, siparis_no_ile, siparis_olustur)
from app.web.bagimlilik import db_bagimliligi
from app.web.baglam import (ULKELER, bildir, gorunen_ad, dil_bul, fiyat_baglami, fiyat_tercihi, kur_bicimle,
                            mevcut_sepet_id, oturum_ulkesi, sablon, siparis_alicisi, varsayilan_ulke)
from app.web.guvenlik import aktif_musteri, capali, csrf_dogrula, guvenli_sonraki, oturum_kimligi
from app.web.rotalar.hesap import oturum_ac

router = APIRouter()

ADRES_ALANLARI = ("ad_soyad", "satir1", "satir2", "sehir", "posta_kodu", "ulke", "telefon")
ZORUNLU_ADRES = ("ad_soyad", "satir1", "sehir", "ulke")
ONEKLER = ("teslimat", "fatura")
EK_ALANLAR = ("fatura_ayni", "teslim", "on_bilgi_onay", "mesafeli_onay", "kosullar_onay",
              "gosterilen_toplam", "gosterilen_kur", "odeme_yontemi", "musteri_po")
FORM_ALANLARI = tuple(f"{o}_{a}" for o in ONEKLER for a in ADRES_ALANLARI) + EK_ALANLAR
ULKE_DESENI = re.compile(r"[A-Z]{2}")
ANAHTAR_DESENI = re.compile(r"[A-Za-z0-9_-]{16,64}")
ODEME_HATALARI = frozenset({"gecersiz_kart", "ret", "sms_hatali"})
AZAMI_UZUNLUK = 200
PO_AZAMI = 40   # G3i madde 6: satın alma (PO) numarası
PO_YANSIMA = 200   # Fix 1 (m-7): hatalı PO formda en çok bu kadar karakterle geri basılır (41–200 yine hata alır)
ADRES_ETIKETLERI = {"ad_soyad": "odeme.ad_soyad", "satir1": "odeme.adres_satir1", "satir2": "odeme.adres_satir2",
                    "sehir": "odeme.sehir", "posta_kodu": "odeme.posta_kodu", "ulke": "odeme.ulke",
                    "telefon": "odeme.telefon"}
ONAY_ETIKETLERI = {"on_bilgi_onay": "odeme.belge_on_bilgilendirme", "mesafeli_onay": "odeme.belge_mesafeli_satis",
                   "kosullar_onay": "odeme.onaylar", "teslim": "odeme.teslim_yontemi",
                   "odeme_yontemi": "odeme.odeme_yontemi", "musteri_po": "odeme.musteri_po"}
# G3g madde 1: girişsiz ödemede formun üstündeki "Hesabınız" bölümü (hesap siparişle aynı işlemde açılır)
TIPLER = tuple(t.value for t in MusteriTipi)
HESAP_ALANLARI = ("hesap_tip", "hesap_eposta", "hesap_parola", "hesap_firma", "hesap_vkn", "hesap_vergi_dairesi",
                  "hesap_ulke", "hesap_vat_id", "hesap_kvkk_onay")
HESAP_ETIKETLERI = {"hesap_tip": "hesap.tip_baslik", "hesap_eposta": "hesap.eposta", "hesap_parola": "hesap.parola",
                    "hesap_firma": "odeme.hesap_firma", "hesap_vkn": "hesap.vkn",
                    "hesap_vergi_dairesi": "hesap.vergi_dairesi", "hesap_ulke": "hesap.ulke",
                    "hesap_vat_id": "hesap.vat_id", "hesap_kvkk_onay": "odeme.hesap_kvkk"}
# kayit_ol hata alanı -> form alanı
KAYIT_ALANI = {"ad": "hesap_firma", "eposta": "hesap_eposta", "parola": "hesap_parola",
               "kvkk_onay": "hesap_kvkk_onay", "vergi_kimlik_no": "hesap_vkn", "vergi_dairesi": "hesap_vergi_dairesi",
               "ulke": "hesap_ulke", "vat_id": "hesap_vat_id"}
PAROLA_UST = 200


# ---------- ortak yardımcılar ----------

def _simdi() -> datetime:
    return datetime.now(UTC)


def _sayfa(request: Request, ad: str, baglam: dict, durum: int = 200) -> Response:
    """sablon() + bu ekranların ortak yardımcıları. kur_sayi: ₺ işaretsiz yerel kur metni
    (çeviri metinleri ₺ işaretini kendisi yazar). adim: K22 adım göstergesi (G3g: 1 Sepet … 4 Onay)."""
    dil = dil_bul(request)
    ortak = {"kur_sayi": lambda kur: kur_bicimle(kur, dil).replace("₺", "").strip(),
             # G3g madde 20: sepet, bilgiler (ödeme formu) ve ödeme (kart/3D) adımlarında geri bildirim düğmesi yok
             "gb_gizle": baglam.get("adim") in (1, 2, 3)}
    return sablon(request, ad, {**ortak, **baglam}, durum)


def _tamsayi(deger: object) -> int | None:
    try:
        return int(str(deger).strip())
    except (TypeError, ValueError):
        return None


def _giris_yonlendir(dil: str, sonraki: str) -> RedirectResponse:
    return RedirectResponse(f"/{dil}/giris?sonraki={quote(sonraki, safe='/')}", status_code=303)


def _sepet_id(request: Request, con: sqlite3.Connection, musteri: Musteri | None) -> int:
    with con:
        return sepet_servis.sepet_bul(con, oturum_kimligi(request), musteri.id if musteri else None, _simdi())


def _stok_teklif_bagi(dil: str, urun_id: int, adet: int) -> tuple[str, str, str]:
    """G3e madde 1: stok aşımı bildirimindeki teklif bağlantısı (istenen adet formda önceden dolu)."""
    return (f"/{dil}/teklif?urun_id={urun_id}&adet={max(1, min(9999, adet))}", "sepet.stok_teklif_bag", "stok-teklif")


def _kalemler(con: sqlite3.Connection, sepet_id: int,
              request: Request | None = None, duzeltilen: list | None = None) -> tuple[list[Kalem], list[str]]:
    """duzeltilen verilirse (ödeme gönderimi) stok düzeltmeleri bildirim yerine bu listeye yazılır."""
    with con:  # düşen ürünler silinir, ayrılabilir stoku aşan adetler iner (0 ise çıkar); değişiklik kalıcı olsun
        asanlar = sepet_servis.stok_siniri_uygula(con, sepet_id, _ayrilan(con, sepet_id))
        sonuc = sepet_servis.kalemler(con, sepet_id)
    if duzeltilen is not None:
        duzeltilen.extend(asanlar)
    elif request is not None:
        for uid, ad, stok, _ in asanlar:
            bildir(request, "sepet.stok_azaldi" if stok > 0 else "sepet.stok_tumu_ayrildi",
                   ad=gorunen_ad(request, con, uid, ad), stok=stok)
    return sonuc


def _ayrilan(con: sqlite3.Connection, sepet_id: int) -> dict[int, int]:
    """G3e düzeltme 3: başka açık siparişlerin ayırdığı adetler (bu sepetin bekleyen kart siparişi hariç)."""
    return ayrilan_adetler(con, _simdi(), haric_sepet_id=sepet_id)


def _ulke_secenekleri(musteri: Musteri) -> tuple[str, ...]:
    """Fix 1/4: ülke listesi üst bant seçicisiyle aynı; müşterinin kayıtlı ülkesi listede yoksa eklenir."""
    ulke = (musteri.ulke or "").upper()
    return ULKELER if ulke in ULKELER or not ULKE_DESENI.fullmatch(ulke) else (*ULKELER, ulke)


def _teslim_secenekleri(ulke: str) -> list[TeslimYontemi]:
    """K4: TR -> kargo, fabrika ; TR dışı -> yurtdisi_dap, fabrika."""
    if ulke == "TR":
        return [TeslimYontemi.KARGO, TeslimYontemi.FABRIKA]
    return [TeslimYontemi.YURTDISI_DAP, TeslimYontemi.FABRIKA]


def _teslim_coz(deger: str | None, ulke: str) -> TeslimYontemi:
    secenekler = _teslim_secenekleri(ulke)
    try:
        teslim = TeslimYontemi(deger or "")
    except ValueError:
        return secenekler[0]
    return teslim if teslim in secenekler else secenekler[0]


def _hesapla(kalemler, baglam: Baglam, teslim: TeslimYontemi,
             kur: Kur | None) -> tuple[SepetTutari | None, str | None]:
    """(tutar, hata). K5: TRY tahsilatta kur yoksa hata "kur_yok"; G3a Ö1: tutar yine de EUR yedeğiyle döner
    (gösterim içindir; çağıran hata varken sipariş oluşturmaz, gosterilen_toplam boş kalır)."""
    try:
        return sepet_hesapla(kalemler, baglam, teslim, kur.eur_satis if kur else None), None
    except KurYok:
        return sepet_hesapla_eur(kalemler, baglam, teslim), "kur_yok"


def _kur_metni(tutar: SepetTutari | None) -> str:
    return str(tutar.kur) if tutar is not None and tutar.kur is not None else ""


def _kalem_gosterimi(k, baglam: Baglam, kur_eur: Decimal | None) -> FiyatGosterim:
    """G3g madde 7: satır tutarı, birim fiyatla AYNI ana para birimi ve KDV bazında (kurumsal: € KDV hariç ana, ₺
    ikincil; bireysel: ₺ KDV dahil ana, € ikincil). Yuvarlama sepet hesabıyla aynıdır (net = yuvarla(birim × adet ×
    kur), KDV ayrı yuvarlanır); tahsilat para birimindeki toplamlar ayrıca tutar özetinde."""
    return birim_fiyat_gosterimi(k.birim_net_eur * k.adet, k.kdv_orani, baglam, kur_eur)


def _satir_gosterimleri(kalemler, tutar: SepetTutari | None, hata: str | None, baglam: Baglam,
                        kur_eur: Decimal | None) -> list[FiyatGosterim | None]:
    """Satır tutarları (_kalem_gosterimi). Kur yokken (G3a Ö1 yedeği) toplamlar EUR ve KDV kuralıyla hesaplanır:
    satır da aynı EUR yedek tutarı gösterir (bireyselde KDV dahil)."""
    if tutar is None:
        return [None for _ in kalemler]
    if hata == "kur_yok":
        dahil = gosterim_kdv_dahil(baglam)
        return [FiyatGosterim(st.brut if dahil else st.net, tutar.para_birimi, dahil, None, None)
                for st in tutar.satirlar]
    return [_kalem_gosterimi(k, baglam, kur_eur) for k in kalemler]


def _gosterim_ara_toplam(kalemler, para: str, kur_eur: Decimal | None) -> Decimal:
    """Satırların gösterim para birimindeki KDV hariç ara toplamı (satır yuvarlamasıyla aynı: net = yuvarla(birim ×
    adet [× kur]))."""
    carpan = kur_eur if para == "TRY" and kur_eur is not None else Decimal("1")
    return sum((yuvarla(k.birim_net_eur * k.adet * carpan) for k in kalemler), Decimal("0.00"))


# ---------- sepet ----------

def _sepet_sayfasi(request: Request, con: sqlite3.Connection, *, uyari: str | None = None,
                   teklif_urun_id: int | None = None, durum: int = 200) -> Response:
    musteri = aktif_musteri(request, con)
    kalemler, dusenler = _kalemler(con, _sepet_id(request, con, musteri), request)
    baglam = fiyat_baglami(request, musteri)
    kur = son_kur(con)
    kur_eur = kur.eur_satis if kur else None
    teslim = _teslim_secenekleri(baglam.teslimat_ulkesi)[0]
    tutar, hata = _hesapla(kalemler, baglam, teslim, kur) if kalemler else (None, None)
    # G3j inceleme M-2: TL tahsil edilen (bireysel) yurt dışı teslimde € gösterim: sepet özeti € (aynı KDV/kargo
    # kuralları), ₺ toplam ve TCMB kur satırı yok; yalnız "ödeme TL, kur ödeme adımında" notu. Ödeme özeti değişmez.
    tl_odemede = (tutar is not None and hata is None and tutar.para_birimi == "TRY"
                  and baglam.teslimat_ulkesi != "TR" and gosterim_kipi(baglam, kur_eur)[0] == "EUR")
    if tl_odemede:
        tutar = sepet_hesapla_eur(kalemler, baglam, teslim)
    satirlar = [{"kalem": k, "urun": urun_getir(con, k.urun_id),
                 "gosterim": birim_fiyat_gosterimi(k.birim_net_eur, k.kdv_orani, baglam, kur_eur),
                 "tutar_gosterim": g, "tutar": None}
                for k, g in zip(kalemler, _satir_gosterimleri(kalemler, tutar, hata, baglam, kur_eur))]
    if tutar is not None:
        for satir, satir_tutari in zip(satirlar, tutar.satirlar):
            satir["tutar"] = satir_tutari
    ara = _ara_gosterim(kalemler, tutar, baglam, kur_eur)
    # G3n madde 3: "Kalemleri tekrar sepete ekle" hiçbir kalem ekleyemediyse nedenler (bir kez gösterilir)
    nedenler = request.session.pop("tekrar_nedenleri", None) if "session" in request.scope else None
    return _sayfa(request, "sepet.html", {"adim": 1,
        "tekrar_nedenleri": [str(n) for n in nedenler][:10] if isinstance(nedenler, list) else [],
        "satirlar": satirlar, "tutar": tutar, "hata": hata, "dusenler": dusenler,
        "uyari": uyari, "teklif_urun_id": teklif_urun_id, "teslim": teslim,
        "kdv_dahil": satirlar[0]["tutar_gosterim"].kdv_dahil if satirlar and satirlar[0]["tutar_gosterim"]
        else gosterim_kdv_dahil(baglam), "eklendi": request.query_params.get("eklendi") == "1",
        "tahmini": True,   # G3e madde 5: sepette toplam tahminidir (teslim yöntemi ödeme adımında kesinleşir)
        "ara_gosterim": ara,
        # G3k madde 19: ₺ gösterim, € tahsilat: özet satırları ₺ (karışık birim yok), toplamda ikincil €
        "tl_gosterim_kur": kur_eur if ara and ara["para"] == "TRY" and tutar.para_birimi == "EUR" else None,
        "tl_odemede": tl_odemede,
        "fiyat_secici": True,
        "tedarik_teklifle": _tedarik_teklifle,
    }, durum)


HAVALE_NOTU_VURGU_TL = Decimal("50000")   # G3l madde 8: bu tutardan itibaren havale/proforma notu vurgulu


def _tl_toplam(tutar: SepetTutari | None, kur_eur: Decimal | None) -> Decimal:
    """Sepet genel toplamının ₺ karşılığı (€ tahsilatta kurla; kur yoksa 0)."""
    if tutar is None:
        return Decimal("0")
    if tutar.para_birimi == "TRY":
        return tutar.toplam
    return tutar.toplam * kur_eur if kur_eur else Decimal("0")


def _tedarik_teklifle(urun) -> bool:
    """G3i madde 5: stokta olmayan, tedarik süresi kaynakta bilinmeyen (sepete eklenebilir) ürün: "Tedarik süresi
    teklifle" kalemi. Sipariş engellenmez; sepette ve ödeme özetinde not + teklif bağlantısı."""
    return urun is not None and not urun.teklif_zorunlu and urun.stok <= 0 and not urun.tedarik_suresi_gun


def _ara_gosterim(kalemler, tutar: SepetTutari | None, baglam: Baglam, kur_eur: Decimal | None) -> dict | None:
    """G3g madde 7 + G3i madde 1: gösterim para birimi tahsilat para biriminden farklıysa (kurumsal TR: € gösterim, ₺
    tahsilat; ya da seçilen gösterim) özetteki TEK "Ara toplam (KDV hariç)" satırı gösterim para biriminde, tahsilat
    tutarı yanında "≈" ile. Aynıysa None (satır yalnız tahsilat para biriminde)."""
    if tutar is None:
        return None
    para = gosterim_kipi(baglam, kur_eur)[0]
    if para == tutar.para_birimi:
        return None
    # G3l madde 6: € KDV hariç gösterim, ₺ tahsilat: genel toplamın € karşılığı ("₺ … (ödenecek) · ≈ € …")
    toplam = yuvarla(tutar.toplam / tutar.kur) if para == "EUR" and tutar.para_birimi == "TRY" and tutar.kur else None
    return {"tutar": _gosterim_ara_toplam(kalemler, para, kur_eur), "para": para, "toplam": toplam}


@router.get("/{dil:dil}/sepet")
def sepet_goster(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    return _sepet_sayfasi(request, con)


@router.post("/{dil:dil}/sepet/bosalt")
async def sepet_bosalt(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    """G3j madde 16: sepetten teklif gönderildikten sonra sepeti tek düğmeyle boşaltma (CSRF). Sepet yoksa da sepete
    döner; sepet oluşturulmaz."""
    await csrf_dogrula(request)
    sid = mevcut_sepet_id(con, request, aktif_musteri(request, con))
    if sid is not None:
        with con:
            sepet_servis.bosalt(con, sid)
        bildir(request, "sepet.bosaltildi")
    return RedirectResponse(f"/{dil}/sepet", status_code=303)


@router.post("/{dil:dil}/sepet/ekle")
async def sepet_ekle(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    await csrf_dogrula(request)
    form = await request.form()
    urun_id, adet = _tamsayi(form.get("urun_id")), _tamsayi(form.get("adet", "1"))
    if urun_id is None:
        raise HTTPException(status_code=400)
    if adet is None or adet < sepet_servis.ADET_MIN:
        # Son inceleme I-1: geçersiz ya da 1'den küçük adet çıplak 400 sayfası vermez ve sessizce 1'e çevrilmez:
        # bildirim (üstte + ürünün kartında / satın alma kutusunda) ve ürün çapasına dönüş; sepete bir şey eklenmez
        bildir(request, "sepet.adet_gecersiz" if adet is None else "sepet.adet_negatif", urun=urun_id)
        sonraki = guvenli_sonraki(str(form.get("sonraki", ""))[:500], "") or f"/{dil}/urun/{urun_id}"
        return RedirectResponse(capali(sonraki, urun_id), status_code=303)
    sepet_id = _sepet_id(request, con, aktif_musteri(request, con))
    onceki = con.execute("SELECT adet FROM sepet_kalemi WHERE sepet_id = ? AND urun_id = ?",
                         (sepet_id, urun_id)).fetchone()
    try:
        with con:
            yeni, stok = sepet_servis.ekle(con, sepet_id, urun_id, adet, _ayrilan(con, sepet_id))
    except sepet_servis.UrunYok:
        raise HTTPException(status_code=404) from None
    except sepet_servis.TeklifZorunlu:
        return _sepet_sayfasi(request, con, uyari="sepet.teklif_zorunlu", teklif_urun_id=urun_id, durum=409)
    eklenen = yeni - (onceki[0] if onceki else 0)
    # G3g madde 6: bildirimler ürünün kartında / satın alma kutusunda da (çapa #urun-<id>) gösterilir
    if stok is not None:   # G3e madde 1: adet stoka indirildi; bildirim gerçekten eklenen adedi yazar (düzeltme 1 I-4)
        istenen = max(sepet_servis.ADET_MIN, adet)    # G3g madde 3: teklif İSTENEN adetle (sepet toplamıyla değil)
        if stok <= 0:     # düzeltme 3: stok var ama tümü açık siparişlerce ayrılmış
            bildir(request, "sepet.stok_tumu_ayrilmis", bag=_stok_teklif_bagi(dil, urun_id, istenen), urun=urun_id)
        elif eklenen > 0:
            bildir(request, "sepet.stok_siniri", eklenen=eklenen, stok=stok,
                   bag=_stok_teklif_bagi(dil, urun_id, istenen),
                   bag2=(f"/{dil}/sepet", "sepet.sepete_git", "sepete-git"), urun=urun_id)
        else:
            bildir(request, "sepet.stok_siniri_eklenmedi", stok=stok, bag=_stok_teklif_bagi(dil, urun_id, istenen),
                   bag2=(f"/{dil}/sepet", "sepet.sepete_git", "sepete-git"), urun=urun_id)
    # G3c madde 17: ziyaretçi bulunduğu sayfada kalır (filtreli liste, ürün); bildirim + "Sepete git", başlık sayacı
    # yeni sayfada güncel. sonraki yoksa ya da güvensizse eski davranış: sepete.
    # G3e düzeltme 2 (N-2): genel üst sınır (99) adedi kırptıysa bildirim gerçekten eklenen adedi ve sınırı yazar
    ust_sinir = stok is None and eklenen < max(sepet_servis.ADET_MIN, adet)
    if ust_sinir:
        bildir(request, "sepet.ust_sinir", azami=sepet_servis.ADET_MAX, urun=urun_id)
    sonraki = guvenli_sonraki(str(form.get("sonraki", ""))[:500], "")
    if sonraki and stok is not None:
        return RedirectResponse(capali(sonraki, urun_id), status_code=303)
    if sonraki:
        if eklenen > 0:
            urun = urun_getir(con, urun_id)
            bildir(request, "sepet.eklendi_bildirim", ad=gorunen_ad(request, con, urun_id, urun.ad) if urun else "",
                   adet=eklenen,
                   bag=(f"/{dil}/sepet", "sepet.sepete_git", "sepete-git"),
                   bag2=(f"/{dil}/odeme", "sepet.odemeye_gec", "bildirim-odemeye-gec"),   # G3e madde 18
                   urun=urun_id)
        return RedirectResponse(capali(sonraki, urun_id), status_code=303)
    eklendi = stok is None and not ust_sinir
    return RedirectResponse(f"/{dil}/sepet" + ("?eklendi=1" if eklendi else ""), status_code=303)


@router.post("/{dil:dil}/sepet/adet")
async def sepet_adet(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    await csrf_dogrula(request)
    form = await request.form()
    urun_id, adet = _tamsayi(form.get("urun_id")), _tamsayi(form.get("adet"))
    if urun_id is None:
        raise HTTPException(status_code=400)
    # G3n madde 1: adet bildirimleri sayfa üstünde ve ilgili sepet satırında (urun=)
    if adet is None:          # G3l madde 15: "1,5", metin: 400 sayfası yerine sepete dön + bildirim (adet değişmez)
        bildir(request, "sepet.adet_gecersiz", urun=urun_id)
        return RedirectResponse(f"/{dil}/sepet", status_code=303)
    if adet < 0:              # G3m madde 5: negatif adet geçersiz; satır değişmez
        bildir(request, "sepet.adet_negatif", urun=urun_id)
        return RedirectResponse(f"/{dil}/sepet", status_code=303)
    sepet_id = _sepet_id(request, con, aktif_musteri(request, con))
    if adet < sepet_servis.ADET_MIN:      # G3l madde 15: 0 adet satırı kaldırır ve söyler
        kalem = con.execute("SELECT 1 FROM sepet_kalemi WHERE sepet_id = ? AND urun_id = ?",
                            (sepet_id, urun_id)).fetchone()
        with con:
            sepet_servis.kaldir(con, sepet_id, urun_id)
        if kalem is not None:
            urun = urun_getir(con, urun_id)
            bildir(request, "sepet.cikarildi", ad=gorunen_ad(request, con, urun_id, urun.ad if urun else ""))
        return RedirectResponse(f"/{dil}/sepet", status_code=303)
    with con:
        stok = sepet_servis.adet_ayarla(con, sepet_id, urun_id, adet, _ayrilan(con, sepet_id))
    if stok is not None and stok <= 0:
        bildir(request, "sepet.stok_tumu_ayrilmis", bag=_stok_teklif_bagi(dil, urun_id, adet))
    elif stok is not None:    # G3n madde 1: "Stokta 7 adet var; adet 7'ye düşürüldü."
        bildir(request, "sepet.stok_siniri_guncelle", stok=stok, stok_ek=yonelme_eki(stok),
               bag=_stok_teklif_bagi(dil, urun_id, adet), urun=urun_id)
    elif adet > sepet_servis.ADET_MAX:      # G3e düzeltme 2 (N-2)
        bildir(request, "sepet.ust_sinir", azami=sepet_servis.ADET_MAX, urun=urun_id)
    return RedirectResponse(f"/{dil}/sepet", status_code=303)


@router.post("/{dil:dil}/sepet/kaldir")
async def sepet_kaldir(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    await csrf_dogrula(request)
    form = await request.form()
    urun_id = _tamsayi(form.get("urun_id"))
    if urun_id is None:
        raise HTTPException(status_code=400)
    sepet_id = _sepet_id(request, con, aktif_musteri(request, con))
    with con:
        sepet_servis.kaldir(con, sepet_id, urun_id)
    return RedirectResponse(f"/{dil}/sepet", status_code=303)


# ---------- ödeme formu ----------

def _bos_alanlar() -> dict[str, str]:
    return {ad: "" for ad in FORM_ALANLARI}


def _adresten(onek: str, adres: Adres | None) -> dict[str, str]:
    if adres is None:
        return {}
    return {f"{onek}_{ad}": getattr(adres, ad) or "" for ad in ADRES_ALANLARI}


def _baslangic_alanlari(con: sqlite3.Connection, musteri: Musteri, secilen_ulke: str | None = None) -> dict[str, str]:
    """G3b madde 16: teslim ülkesi varsayılanı = kayıtlı son teslimat adresi > bu oturumda (giriş sonrası) üst bantta
    seçilen ülke > müşteri ülkesi. Ürün sayfasının fiyat bağlamıyla aynı kaynak (baglam.musteri_ulkesi)."""
    alanlar = _bos_alanlar()
    alanlar.update(teslimat_ad_soyad=musteri.ad, teslimat_ulke=secilen_ulke or musteri.ulke, fatura_ulke=musteri.ulke)
    teslimat = adres_son(con, musteri.id, "teslimat")
    fatura = adres_son(con, musteri.id, "fatura")
    # G3k madde 13: kayıtlı teslimat adresi yoksa (ör. yalnız "Fatura bilgilerim" doldurulmuş) teslimat adresi aynı
    # ülkedeki fatura adresinden dolar ve "Fatura adresim teslimat adresiyle aynı" işaretli gelir
    if teslimat is None and fatura is not None and fatura.ulke == alanlar["teslimat_ulke"]:
        teslimat = fatura
    alanlar.update(_adresten("teslimat", teslimat))
    alanlar.update(_adresten("fatura", fatura))
    alanlar["fatura_ayni"] = "1" if fatura is None or fatura == teslimat else ""
    alanlar["teslim"] = _teslim_secenekleri(alanlar["teslimat_ulke"])[0].value
    alanlar["odeme_yontemi"] = _varsayilan_yontem(musteri)
    return alanlar


def _varsayilan_yontem(musteri: Musteri) -> str:
    """G3m madde 23: yurt dışı müşteride havale (proforma) ilk ve varsayılan; diğerlerinde kart (izinli yöntemler aynı)."""
    return "havale" if musteri.tip == MusteriTipi.YURTDISI else "kart"


def _formdan(form: Mapping) -> dict[str, str]:
    alanlar = {ad: str(form.get(ad, "")).strip() for ad in FORM_ALANLARI}
    alanlar["musteri_po"] = alanlar["musteri_po"][:PO_YANSIMA]   # > 40 olduğu sürece hata; yansıma sınırlı
    for onek in ONEKLER:
        alanlar[f"{onek}_ulke"] = alanlar[f"{onek}_ulke"].upper()
    if alanlar["fatura_ayni"]:
        for ad in ADRES_ALANLARI:
            alanlar[f"fatura_{ad}"] = alanlar[f"teslimat_{ad}"]
    return alanlar


def _dogrula(alanlar: dict[str, str], musteri: Musteri) -> dict[str, str]:
    """Alan adı -> i18n hata anahtarı (K14: `hata_kodu.zorunlu`, `hata_kodu.<kod>`)."""
    hatalar: dict[str, str] = {}
    for ad, deger in alanlar.items():
        if len(deger) > AZAMI_UZUNLUK:
            hatalar[ad] = "hata_kodu.cok_uzun"
    if len(alanlar["musteri_po"]) > PO_AZAMI:
        hatalar["musteri_po"] = "hata_kodu.po_uzun"
    for onek in ONEKLER:
        for ad in ZORUNLU_ADRES:
            if not alanlar[f"{onek}_{ad}"]:
                hatalar[f"{onek}_{ad}"] = "hata_kodu.zorunlu"
        ulke = alanlar[f"{onek}_ulke"]
        if ulke and ulke not in _ulke_secenekleri(musteri):
            hatalar[f"{onek}_ulke"] = "hata_kodu.ulke_kodu"
    try:
        teslim = TeslimYontemi(alanlar["teslim"])
    except ValueError:
        hatalar["teslim"] = "hata_kodu.teslim_secilmedi"
    else:
        if "teslimat_ulke" not in hatalar:
            if alanlar["teslimat_ulke"] != "TR" and teslim == TeslimYontemi.KARGO:
                hatalar["teslim"] = "hata_kodu.teslim_yurtdisi"
            elif alanlar["teslimat_ulke"] == "TR" and teslim == TeslimYontemi.YURTDISI_DAP:
                hatalar["teslim"] = "hata_kodu.teslim_yurtici"
    if musteri.tip == MusteriTipi.BIREYSEL:
        onaylar = ("on_bilgi_onay", "mesafeli_onay")
    else:
        onaylar = ("kosullar_onay",)
    for ad in onaylar:
        if not alanlar[ad]:
            hatalar[ad] = "hata_kodu.onay_yok"
    return hatalar


def _adres(alanlar: dict[str, str], onek: str) -> Adres:
    def bos_ise_none(ad: str) -> str | None:
        return alanlar[f"{onek}_{ad}"] or None
    return Adres(ad_soyad=alanlar[f"{onek}_ad_soyad"], satir1=alanlar[f"{onek}_satir1"],
                 sehir=alanlar[f"{onek}_sehir"], ulke=alanlar[f"{onek}_ulke"],
                 satir2=bos_ise_none("satir2"), posta_kodu=bos_ise_none("posta_kodu"),
                 telefon=bos_ise_none("telefon"))


def _hata_ozeti(hatalar: dict[str, str], alanlar: dict[str, str],
                secenekler: list[TeslimYontemi]) -> list[dict]:
    """Formun üstündeki hata özeti (K22): form sırasıyla; alan bağlantısı, etiket anahtarları, hata anahtarı.
    "Fatura adresim aynı" işaretliyse fatura alanları teslimattan kopyalanır, hataları ayrıca listelenmez.
    G3g madde 1: girişsiz ödemede "Hesabınız" alanları en üstte."""
    ozet = []
    for ad in HESAP_ALANLARI:
        if ad in hatalar:
            hedef = f"hesap_tip-{alanlar.get('hesap_tip') or 'bireysel'}" if ad == "hesap_tip" else ad
            ozet.append({"hedef": hedef, "etiketler": ["odeme.hesap_baslik", HESAP_ETIKETLERI[ad]],
                         "hata": hatalar[ad]})
    for ad in FORM_ALANLARI:
        if ad not in hatalar:
            continue
        onek, _, kok = ad.partition("_")
        if onek in ONEKLER and kok in ADRES_ETIKETLERI:
            if onek == "fatura" and alanlar.get("fatura_ayni"):
                continue
            etiketler = [f"odeme.{onek}_adresi", ADRES_ETIKETLERI[kok]]
        else:
            etiketler = [ONAY_ETIKETLERI.get(ad, "odeme.ozet")]
        hedef = (f"teslim-{secenekler[0].value}" if ad == "teslim" else "odeme-havale" if ad == "odeme_yontemi"
                 else ad)
        ozet.append({"hedef": hedef, "etiketler": etiketler, "hata": hatalar[ad]})
    return ozet


def _ayni_tutar(alanlar: dict[str, str], tutar: SepetTutari) -> bool:
    try:
        gosterilen = Decimal(alanlar["gosterilen_toplam"])
    except (InvalidOperation, ValueError):
        return False
    return gosterilen == tutar.toplam and alanlar["gosterilen_kur"] == _kur_metni(tutar)


# ---------- G3g madde 1: girişsiz ödemede gömülü hesap ----------

def _hesap_formdan(form: Mapping) -> dict[str, str]:
    hesap = {ad: str(form.get(ad, "")).strip()[:AZAMI_UZUNLUK] for ad in HESAP_ALANLARI if ad != "hesap_parola"}
    hesap["hesap_parola"] = str(form.get("hesap_parola", ""))[:PAROLA_UST + 1]
    hesap["hesap_ulke"] = hesap["hesap_ulke"].upper()
    hesap["hesap_vkn"] = "".join(hesap["hesap_vkn"].split())
    return hesap


def _hesap_baslangic(request: Request) -> dict[str, str]:
    """Varsayılan tip: ülke TR (seçili, tarayıcı bölgesi ya da /tr) ise bireysel, değilse yurt dışı; ?tip= ile değişir."""
    ulke = varsayilan_ulke(request)
    tip = request.query_params.get("tip", "")
    if tip not in TIPLER:
        tip = (MusteriTipi.BIREYSEL if ulke == "TR" else MusteriTipi.YURTDISI).value
    hesap = {ad: "" for ad in HESAP_ALANLARI}
    hesap.update(hesap_tip=tip, hesap_ulke=ulke if ulke and ulke != "TR" else "DE")
    return hesap


def _taslak_musteri(hesap: dict[str, str]) -> Musteri:
    """Henüz açılmamış hesabın fiyat/doğrulama bağlamı (tip ve ülke); veritabanına yazılmaz."""
    tip = MusteriTipi(hesap["hesap_tip"]) if hesap["hesap_tip"] in TIPLER else MusteriTipi.BIREYSEL
    ulke = "TR"
    if tip is MusteriTipi.YURTDISI:
        ulke = hesap["hesap_ulke"] if hesap["hesap_ulke"] in ULKELER and hesap["hesap_ulke"] != "TR" else "DE"
    return Musteri(id=0, tip=tip, ad="", eposta="", ulke=ulke, vergi_kimlik_no=None, vergi_dairesi=None,
                   vat_id=None, iys_onay=False)


def _misafir_alanlari(musteri: Musteri, request: Request) -> dict[str, str]:
    alanlar = _bos_alanlar()
    ulke = musteri.ulke if musteri.tip is MusteriTipi.YURTDISI else (varsayilan_ulke(request) or "TR")
    alanlar.update(teslimat_ulke=ulke, fatura_ulke=ulke, fatura_ayni="1", odeme_yontemi=_varsayilan_yontem(musteri),
                   teslim=_teslim_secenekleri(ulke)[0].value)
    return alanlar


def _hesap_dogrula(con: sqlite3.Connection, hesap: dict[str, str]) -> dict[str, str]:
    """Kayıt formunun kurallarıyla aynı (kayit_ol işlem içinde yeniden denetler). Alan -> i18n hata anahtarı."""
    h: dict[str, str] = {}
    tip = hesap["hesap_tip"]
    if tip not in TIPLER:
        return {"hesap_tip": "hata_kodu.tip_sec"}
    if not hesap["hesap_eposta"]:
        h["hesap_eposta"] = "hata_kodu.zorunlu"
    elif not eposta_gecerli(hesap["hesap_eposta"]):
        h["hesap_eposta"] = "hata_kodu.gecersiz"
    elif con.execute("SELECT 1 FROM musteri WHERE eposta = ?", (hesap["hesap_eposta"].lower(),)).fetchone():
        h["hesap_eposta"] = "odeme.hesap_eposta_kayitli"
    if len(hesap["hesap_parola"]) < PAROLA_MIN:
        h["hesap_parola"] = "hata_kodu.parola_kisa"
    elif len(hesap["hesap_parola"]) > PAROLA_UST:
        h["hesap_parola"] = "hata_kodu.gecersiz"
    if hesap["hesap_kvkk_onay"] != "1":
        h["hesap_kvkk_onay"] = "hata_kodu.kvkk_onay_yok"
    if tip != MusteriTipi.BIREYSEL.value and not hesap["hesap_firma"]:
        h["hesap_firma"] = "hata_kodu.zorunlu"
    if tip == MusteriTipi.KURUMSAL.value:
        vkn = hesap["hesap_vkn"]
        if not vkn:
            h["hesap_vkn"] = "hata_kodu.zorunlu"
        elif vergi_no_hatasi(vkn) is not None:          # G3m madde 26
            h["hesap_vkn"] = f"hata_kodu.{vergi_no_hatasi(vkn)}"
        if not hesap["hesap_vergi_dairesi"]:
            h["hesap_vergi_dairesi"] = "hata_kodu.zorunlu"
    elif tip == MusteriTipi.YURTDISI.value:
        if hesap["hesap_ulke"] not in ULKELER or hesap["hesap_ulke"] == "TR":
            h["hesap_ulke"] = "hata_kodu.gecersiz_ulke"
        else:
            _, kod = vat_id_kontrol(hesap["hesap_vat_id"], hesap["hesap_ulke"], zorunlu_ab=True)
            if kod is not None:
                h["hesap_vat_id"] = f"hata_kodu.{'vat_zorunlu' if kod == 'zorunlu' else kod}"
    return h


def _kayit_girdisi(hesap: dict[str, str], alanlar: dict[str, str]) -> KayitGirdisi:
    tip = MusteriTipi(hesap["hesap_tip"])
    kurumsal, yurtdisi = tip is MusteriTipi.KURUMSAL, tip is MusteriTipi.YURTDISI
    vat = vat_id_kontrol(hesap["hesap_vat_id"], hesap["hesap_ulke"], zorunlu_ab=True)[0] if yurtdisi else None
    return KayitGirdisi(
        tip=tip, ad=alanlar["teslimat_ad_soyad"] if tip is MusteriTipi.BIREYSEL else hesap["hesap_firma"],
        eposta=hesap["hesap_eposta"], parola=hesap["hesap_parola"],
        ulke=hesap["hesap_ulke"] if yurtdisi else "TR", kvkk_onay=True,
        vergi_kimlik_no=(hesap["hesap_vkn"] or None) if kurumsal else None,
        vergi_dairesi=(hesap["hesap_vergi_dairesi"] or None) if kurumsal else None,
        vat_id=vat)


def _odeme_sayfasi(request: Request, con: sqlite3.Connection, musteri: Musteri,
                   alanlar: dict[str, str], kalemler: list[Kalem], dusenler: list[str], *,
                   hatalar: dict[str, str] | None = None, mesaj: str | None = None,
                   islem_hatasi: str | None = None, durum: int = 200,
                   stok_sorunlari: list[dict] | None = None, hesap: dict[str, str] | None = None,
                   odeme_varsayilan: str | None = None) -> Response:
    """mesaj / islem_hatasi: gönderim sonrası iş kuralı hatası (i18n anahtarı); formun üstünde
    role="alert" özetiyle gösterilir (G3a Ö1: sessiz geri dönüş yok). hesap: girişsiz ödemede "Hesabınız" alanları
    (musteri o zaman henüz açılmamış hesabın taslağıdır)."""
    ulke = alanlar["teslimat_ulke"] if alanlar["teslimat_ulke"] in _ulke_secenekleri(musteri) else musteri.ulke
    teslim = _teslim_coz(alanlar["teslim"], ulke)
    alanlar = {**alanlar, "teslim": teslim.value}
    kur = son_kur(con)
    kur_eur = kur.eur_satis if kur else None
    baglam = Baglam(musteri.tip, ulke, fiyat_tercihi(request))   # G3i madde 2: seçilen fiyat gösterimi
    tutar, hata = _hesapla(kalemler, baglam, teslim, kur) if kalemler else (None, None)
    hatalar = hatalar or {}
    sablon_alanlari = {**alanlar, **(hesap or {}), "hesap_parola": ""}   # parola sayfaya geri basılmaz
    return _sayfa(request, "odeme.html", {
        "adim": 2, "hata_ozeti": _hata_ozeti(hatalar, sablon_alanlari, _teslim_secenekleri(ulke)),
        "kdv_dahil": gosterim_kdv_dahil(baglam),
        "alanlar": sablon_alanlari, "hatalar": hatalar, "mesaj": mesaj, "hata": hata, "islem_hatasi": islem_hatasi,
        "stok_sorunlari": stok_sorunlari or [],
        "dusenler": dusenler, "kalemler": kalemler, "tutar": tutar, "teslim": teslim,
        "teslim_secenekleri": _teslim_secenekleri(ulke), "ulke_secenekleri": _ulke_secenekleri(musteri),
        "bireysel": musteri.tip == MusteriTipi.BIREYSEL,
        "yurtdisi": musteri.tip == MusteriTipi.YURTDISI,     # G3m madde 23: havale ilk, OUR notu
        # bireysel tipte (misafir formunda gizli grup) havale işaretli gönderilmesin: kart
        "secili_yontem": "kart" if musteri.tip == MusteriTipi.BIREYSEL else (alanlar.get("odeme_yontemi") or "kart"),
        # G3m inceleme I-1: misafirde yurt dışı varsayılanı (havale) gizli işaretle taşınır; tip bireysele dönerse
        # kullanıcının seçmediği bu varsayılan sunucuda karta çevrilir (400 yok)
        "odeme_varsayilan": (odeme_varsayilan if odeme_varsayilan is not None
                             else (_varsayilan_yontem(musteri) if hesap is not None else "")),
        "hesap": hesap, "hesap_tipleri": TIPLER, "hesap_ulkeleri": [u for u in ULKELER if u != "TR"],
        # kontrolcü kararı: yeniden hesaplama/hata ile yeniden gösterimde parola geri basılmaz; yeniden girilmeli
        "parola_yeniden": hesap is not None and request.method == "POST",
        "urunler": {k.urun_id: u for k in kalemler if (u := urun_getir(con, k.urun_id)) is not None},
        "kalem_gosterimleri": _satir_gosterimleri(kalemler, tutar, hata, baglam, kur_eur),
        "ara_gosterim": _ara_gosterim(kalemler, tutar, baglam, kur_eur),
        "havale_notu_vurgu": _tl_toplam(tutar, kur_eur) >= HAVALE_NOTU_VURGU_TL,     # G3l madde 8
        "tedarik_teklifle": _tedarik_teklifle,
        "teslim_ulkesi": ulke,
        "gosterilen_toplam": str(tutar.toplam) if tutar is not None and hata is None else "",
        "gosterilen_kur": _kur_metni(tutar),
    }, durum)


@router.get("/{dil:dil}/odeme")
def odeme_formu(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    musteri = aktif_musteri(request, con)
    kalemler, dusenler = _kalemler(con, _sepet_id(request, con, musteri), request)
    if not kalemler and not dusenler:
        return RedirectResponse(f"/{dil}/sepet", status_code=303)
    if musteri is None:   # G3g madde 1: giriş sayfasına atılmaz; formun üstünde "Hesabınız"
        hesap = _hesap_baslangic(request)
        taslak = _taslak_musteri(hesap)
        return _odeme_sayfasi(request, con, taslak, _misafir_alanlari(taslak, request), kalemler, dusenler,
                              hesap=hesap)
    return _odeme_sayfasi(request, con, musteri, _baslangic_alanlari(con, musteri, oturum_ulkesi(request)), kalemler,
                          dusenler)


@router.post("/{dil:dil}/odeme")
async def odeme_gonder(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    await csrf_dogrula(request)
    musteri = aktif_musteri(request, con)
    form = await request.form()
    alanlar = _formdan(form)
    hesap = _hesap_formdan(form) if musteri is None else None
    sepet_id = _sepet_id(request, con, musteri)
    if hesap is not None:
        musteri = _taslak_musteri(hesap)       # G3g madde 1: hesap bu gönderimde, siparişle aynı işlemde açılır
    duzeltilen: list = []
    kalemler, dusenler = _kalemler(con, sepet_id, request, duzeltilen)   # K21: siparis_olustur'dan önce

    # G3m inceleme I-1: misafir formundaki gizli varsayılan işareti (yalnız "havale" anlamlı)
    varsayilan = "havale" if hesap is not None and str(form.get("odeme_varsayilan", "")) == "havale" else ""

    def sayfa(**ek) -> Response:
        return _odeme_sayfasi(request, con, musteri, alanlar, kalemler, dusenler, hesap=hesap,
                              odeme_varsayilan=varsayilan, **ek)

    if duzeltilen:   # düzeltme 3: stok azaldı ya da başka siparişlerce ayrıldı: sepet düzeltildi, nedeni özetde (N-1)
        return sayfa(islem_hatasi="odeme.stok_ayrildi", durum=409, stok_sorunlari=[
            {"urun_id": uid, "ad": ad, "kalan": kalan, "teklif": _stok_teklif_bagi(dil, uid, eski)[0]}
            for uid, ad, kalan, eski in duzeltilen])
    if not kalemler and not dusenler:
        return RedirectResponse(f"/{dil}/sepet", status_code=303)

    if form.get("islem") == "hesapla":                     # yalnız yeniden hesapla, sipariş yok
        return sayfa()
    hatalar = _dogrula(alanlar, musteri)
    if hesap is not None:
        hatalar.update(_hesap_dogrula(con, hesap))
        # G3g inceleme M-7: misafir formunda havale seçeneği (:has'siz tarayıcıda) bireysel tipte de görünür; seçildiyse
        # sessizce karta çevrilmez (girişli bireyselde alan hiç yoktur; G3e kuralı aynen)
        if musteri.tip == MusteriTipi.BIREYSEL and alanlar["odeme_yontemi"] == "havale":
            if varsayilan == "havale":
                # G3m inceleme I-1: havale kullanıcının seçimi değil, yurt dışı varsayılanıydı (tip bireysele döndü;
                # ödeme grubu gizli): karta çevrilir. Açıkça seçilen havalede G3g M-7 hatası aynen
                alanlar["odeme_yontemi"] = "kart"
            else:
                hatalar["odeme_yontemi"] = "hata_kodu.havale_bireysel"
    if hatalar:
        return sayfa(hatalar=hatalar, durum=400)
    if dusenler or not kalemler:                           # sepet değişti: kullanıcı yeni tutarı görsün
        return sayfa(mesaj="odeme.tutar_guncellendi", durum=409)
    teslim = TeslimYontemi(alanlar["teslim"])
    kur = son_kur(con)
    tutar, hata = _hesapla(kalemler, Baglam(musteri.tip, alanlar["teslimat_ulke"]), teslim, kur)
    if hata is not None:                                   # G3a Ö1: 503 yerine 409 + formun üstünde neden
        return sayfa(islem_hatasi=f"odeme.hata_{hata}", durum=409)
    if not _ayni_tutar(alanlar, tutar):
        return sayfa(mesaj="odeme.tutar_guncellendi", durum=409)
    teslimat, fatura = _adres(alanlar, "teslimat"), _adres(alanlar, "fatura")
    # G3e madde 15: havale/EFT yalnız kurumsal ve yurt dışı müşteride; bireyselde (ya da geçersiz değerde) kart
    yontem = "havale" if alanlar["odeme_yontemi"] == "havale" and musteri.tip != MusteriTipi.BIREYSEL else "kart"
    havale_gun = request.app.state.ayarlar.havale_gun
    yeni_hesap = None
    try:
        with con:
            # Fix 1/3: aynı sepetin ödeme bekleyen siparişi varsa ve aynı siparişse yenisi açılmaz (çift tahsil
            # önlemi); farklıysa (tutar, kur, kalemler, teslim, adresler) eskisi iptal edilir, yenisi açılır.
            if not con.in_transaction:
                con.execute("BEGIN IMMEDIATE")   # düzeltme 1 (I-3): stok denetimi ile yazım arasında başka sipariş girmez
            if hesap is not None:
                # G3g madde 1: tek işlem: hesap + sepetin hesaba geçmesi + adresler + sipariş (biri düşerse hiçbiri)
                yeni_hesap = kayit_ol(con, _kayit_girdisi(hesap, alanlar), _simdi())
                con.execute("UPDATE sepet SET musteri_id = ?, oturum_id = NULL WHERE id = ?",
                            (yeni_hesap.id, sepet_id))
            sahip = yeni_hesap or musteri
            for eski in _bekleyen_siparisler(con, sepet_id, sahip.id):
                if eski.odeme_yontemi != "kart":   # düzeltme 1 (I-2): havale siparişi yönetim işaretleyene kadar bekler
                    continue
                if (_ayni_siparis(eski, tutar, kalemler, teslim, teslimat, fatura) and eski.odeme_yontemi == yontem
                        and (eski.musteri_po or "") == alanlar["musteri_po"]):   # G3i: PO değiştiyse yeni sipariş
                    return _odeme_sonrasi(dil, eski)
                try:
                    durum_degistir(con, eski.id, SiparisDurumu.IPTAL, _simdi())
                except GecersizGecis:  # bu arada ödendi ya da iptal oldu
                    pass
            adres_kaydet(con, sahip.id, "teslimat", teslimat)
            adres_kaydet(con, sahip.id, "fatura", fatura)
            siparis = siparis_olustur(con, sahip, sepet_id, teslim, teslimat, fatura, kur, _simdi(), yontem,
                                      havale_gun=havale_gun, musteri_po=alanlar["musteri_po"] or None)
            if yontem == "havale":            # düzeltme 1 (I-2): sipariş verildi; sepet boşalır (kartta ödeme başarısında)
                sepet_servis.bosalt(con, sepet_id)
    except KayitHatasi as hata:                            # eşzamanlı aynı e-posta vb.: hiçbir şey yazılmadı
        alan = KAYIT_ALANI.get(hata.alan, "hesap_eposta")
        if hata.alan == "ad" and musteri.tip is MusteriTipi.BIREYSEL:
            alan = "teslimat_ad_soyad"
        anahtar = "odeme.hesap_eposta_kayitli" if hata.kod == "eposta_kayitli" else f"hata_kodu.{hata.kod}"
        return sayfa(hatalar={alan: anahtar}, durum=400)
    except SepetBos:                                       # G3a: yarış durumu da sessiz kalmasın
        bildir(request, "odeme.sepet_bos_bildirim")
        return RedirectResponse(f"/{dil}/sepet", status_code=303)
    except StokYetersiz as hata:                           # G3e madde 1: işlem içinde stok yeniden denetlendi
        # düzeltme 2 (N-1): ayrılabilir adede indir (0 ise kalemi çıkar), nedeni ve teklif yolunu göster;
        # yeniden gönderim düzeltilmiş sepetle (yeni tutarla) sipariş açar. G3g: misafirde hesap da geri alındı.
        sorunlar = []
        with con:
            for urun_id, ad, kalan in hata.kalemler:
                r = con.execute("SELECT adet FROM sepet_kalemi WHERE sepet_id = ? AND urun_id = ?",
                                (sepet_id, urun_id)).fetchone()
                istenen = r[0] if r else 0
                if kalan > 0:
                    sepet_servis.adet_ayarla(con, sepet_id, urun_id, kalan)
                else:
                    sepet_servis.kaldir(con, sepet_id, urun_id)
                sorunlar.append({"urun_id": urun_id, "ad": ad, "kalan": kalan, "teklif": _stok_teklif_bagi(dil, urun_id, istenen)[0]})
        kalemler, dusenler = _kalemler(con, sepet_id)
        return sayfa(islem_hatasi="odeme.stok_ayrildi", stok_sorunlari=sorunlar, durum=409)
    if yeni_hesap is not None:     # işlem commit edildi: oturum açılır (csrf/oid yenilenir; sepet zaten hesapta)
        oturum_ac(request, con, yeni_hesap)
        bildir(request, "odeme.hesap_acildi", eposta=yeni_hesap.eposta)
    return _odeme_sonrasi(dil, siparis)


def _odeme_sonrasi(dil: str, siparis: Siparis) -> RedirectResponse:
    """Kart: kart sayfası (mevcut akış). Havale/EFT: proforma ve banka bilgisinin olduğu sipariş onay sayfası."""
    if siparis.odeme_yontemi == "havale":
        return RedirectResponse(f"/{dil}/siparis/{siparis.no}", status_code=303)
    return RedirectResponse(f"/{dil}/odeme/{siparis.no}/kart", status_code=303)


def _bekleyen_siparisler(con: sqlite3.Connection, sepet_id: int, musteri_id: int) -> list[Siparis]:
    """Sepetin ödeme bekleyen siparişleri (siparis_getir zaman aşımını uygular)."""
    idler = [r[0] for r in con.execute(
        "SELECT id FROM siparis WHERE sepet_id = ? AND musteri_id = ? AND durum = ? ORDER BY id",
        (sepet_id, musteri_id, SiparisDurumu.ODEME_BEKLIYOR.value))]
    siparisler = (siparis_getir(con, i, _simdi()) for i in idler)
    return [s for s in siparisler if s is not None and s.durum == SiparisDurumu.ODEME_BEKLIYOR]


def _ayni_siparis(s: Siparis, tutar: SepetTutari, kalemler: list[Kalem], teslim: TeslimYontemi,
                  teslimat: Adres, fatura: Adres) -> bool:
    return (s.toplam == tutar.toplam and s.para_birimi == tutar.para_birimi and s.kur == tutar.kur
            and s.teslim_yontemi == teslim and s.teslimat_adresi == teslimat and s.fatura_adresi == fatura
            and sorted((k.urun_id, k.adet) for k in s.kalemler) == sorted((k.urun_id, k.adet) for k in kalemler))


# ---------- kart, 3D, sipariş ----------

def _sahip_siparis(con: sqlite3.Connection, no: str, musteri: Musteri) -> Siparis:
    with con:  # siparis_no_ile zaman aşımını uygular (yazabilir)
        siparis = siparis_no_ile(con, no, _simdi())
    if siparis is None or siparis.musteri_id != musteri.id:
        raise HTTPException(status_code=404)
    return siparis


def _deneme(con: sqlite3.Connection, anahtar: str, siparis: Siparis) -> sqlite3.Row:
    """K13: deneme_getir ile okunur; anahtar biçimsiz, yok ya da başka siparişe aitse 404."""
    deneme = deneme_getir(con, anahtar) if ANAHTAR_DESENI.fullmatch(anahtar) else None
    if deneme is None or deneme["siparis_id"] != siparis.id:
        raise HTTPException(status_code=404)
    return deneme


def _bosluklu(kart: str) -> str:
    return " ".join(kart[i:i + 4] for i in range(0, len(kart), 4))


def _kart_sayfasi(request: Request, siparis: Siparis, hata_kodu: str | None = None,
                  durum: int = 200) -> Response:
    con = request.state.con
    return _sayfa(request, "kart.html", {
        "urunler": {k.urun_id: u for k in siparis.kalemler if (u := urun_getir(con, k.urun_id)) is not None},
        "adim": 3, "siparis": siparis, "islem_anahtari": secrets.token_urlsafe(24), "hata_kodu": hata_kodu,
        "alici": siparis_alicisi(siparis, m) if (m := aktif_musteri(request, con)) is not None else None,
        "test_kartlari": [(_bosluklu(BASARILI_KART), "kart.test_basarili"),
                          (_bosluklu(RET_KARTI), "kart.test_ret")],
        "sms_kodu": SMS_KODU,
    }, durum)


def _siparise(dil: str, siparis: Siparis, hata_kodu: str | None = None) -> RedirectResponse:
    hedef = f"/{dil}/siparis/{siparis.no}"
    if hata_kodu in ODEME_HATALARI:
        hedef += f"?hata={hata_kodu}"
    return RedirectResponse(hedef, status_code=303)


@router.get("/{dil:dil}/odeme/{no}/kart")
def kart_formu(dil: str, no: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return _giris_yonlendir(dil, f"/{dil}/odeme/{no}/kart")
    siparis = _sahip_siparis(con, no, musteri)
    if siparis.durum != SiparisDurumu.ODEME_BEKLIYOR or siparis.odeme_yontemi == "havale":
        return _siparise(dil, siparis)
    return _kart_sayfasi(request, siparis)


@router.post("/{dil:dil}/odeme/{no}/kart")
async def kart_gonder(dil: str, no: str, request: Request,
                      con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    await csrf_dogrula(request)
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return _giris_yonlendir(dil, f"/{dil}/odeme/{no}/kart")
    siparis = _sahip_siparis(con, no, musteri)
    if siparis.odeme_yontemi == "havale":          # havale siparişi kartla ödenmez (G3e madde 15)
        return _siparise(dil, siparis)
    form = await request.form()
    anahtar = str(form.get("islem_anahtari", ""))
    if not ANAHTAR_DESENI.fullmatch(anahtar):
        raise HTTPException(status_code=400)
    with con:
        sonuc = odeme_baslat(con, siparis.id, anahtar, str(form.get("kart_no", "")), _simdi())
    if sonuc == OdemeSonucu.SMS_BEKLIYOR:
        return RedirectResponse(f"/{dil}/odeme/{siparis.no}/3d?a={anahtar}", status_code=303)
    if sonuc == OdemeSonucu.GECERSIZ_KART:
        return _kart_sayfasi(request, siparis, sonuc.value, 400)
    return _siparise(dil, siparis, sonuc.value)   # BASARILI, ZATEN_ODENDI, SIPARIS_GECERSIZ, aynı anahtarla RET/SMS_HATALI


@router.get("/{dil:dil}/odeme/{no}/3d")
def uc_d_formu(dil: str, no: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return _giris_yonlendir(dil, f"/{dil}/odeme/{no}/kart")
    siparis = _sahip_siparis(con, no, musteri)
    anahtar = request.query_params.get("a", "")
    deneme = _deneme(con, anahtar, siparis)
    if deneme["durum"] != "sms_bekliyor":
        return _siparise(dil, siparis, deneme["durum"])
    return _sayfa(request, "uc_d.html", {"adim": 3, "siparis": siparis, "anahtar": anahtar,
                                         "kart_son4": deneme["kart_son4"], "sms_kodu": SMS_KODU})


@router.post("/{dil:dil}/odeme/{no}/3d")
async def uc_d_gonder(dil: str, no: str, request: Request,
                      con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    await csrf_dogrula(request)
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return _giris_yonlendir(dil, f"/{dil}/odeme/{no}/kart")
    siparis = _sahip_siparis(con, no, musteri)
    form = await request.form()
    anahtar = str(form.get("a", ""))
    _deneme(con, anahtar, siparis)
    with con:
        sonuc = sms_dogrula(con, anahtar, str(form.get("sms_kodu", "")).strip(), _simdi())
    if sonuc == OdemeSonucu.SMS_BEKLIYOR:
        return RedirectResponse(f"/{dil}/odeme/{siparis.no}/3d?a={anahtar}", status_code=303)
    return _siparise(dil, siparis, sonuc.value)   # BASARILI -> hatasız; RET / SMS_HATALI -> ?hata=<kod> (K12)


@router.get("/{dil:dil}/siparis/{no}")
def siparis_goster(dil: str, no: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return _giris_yonlendir(dil, f"/{dil}/siparis/{no}")
    siparis = _sahip_siparis(con, no, musteri)
    hata_kodu = request.query_params.get("hata")
    if hata_kodu not in ODEME_HATALARI or siparis.durum != SiparisDurumu.ODEME_BEKLIYOR:
        hata_kodu = None
    adim = {SiparisDurumu.ODEME_BEKLIYOR: 3, SiparisDurumu.ODENDI: 4}.get(siparis.durum)   # G3g madde 23
    # G3k madde 16: havale bekleyen sipariş verilmiştir: son adım "Sipariş alındı" etkin (ödeme adımı değil)
    havale_alindi = siparis.odeme_yontemi == "havale" and siparis.durum == SiparisDurumu.ODEME_BEKLIYOR
    if havale_alindi:
        adim = 4
    urunler = {k.urun_id: u for k in siparis.kalemler if (u := urun_getir(con, k.urun_id)) is not None}
    request.state.haric_siparis = siparis.id   # G3g madde 4: kendi kalemleri kendi rezervasyonuyla "ayrılmış" görünmez
    request.state.ayrilan = None
    request.state.ayirma_bitis = None
    return _sayfa(request, "siparis.html", {"adim": adim, "siparis": siparis, "hata_kodu": hata_kodu,
                                             "son_adim": "siparis_alindi" if havale_alindi else "onay",
                                             "urunler": urunler, "alici": siparis_alicisi(siparis, musteri),
                                             **_siparis_eur_gosterimi(siparis, musteri, fiyat_tercihi(request))})


def _siparis_eur_gosterimi(siparis: Siparis, musteri: Musteri, tercih: str | None = None) -> dict:
    """G3g madde 7 (inceleme): ana gösterim para birimi tahsilat para biriminden farklıysa (kurumsal TR: € KDV hariç
    ana, tahsilat ₺) onay tablosunun Net/KDV/Tutar sütunları € ana + ₺ ikincil, toplam bölümünde € ara toplam. KDV
    oranı siparişte saklanmadığı için satırın kayıtlı ₺ net/KDV'sinden (tam sayı oran) türetilir; yuvarlama sepet
    hesabıyla aynı (net = yuvarla(birim × adet), KDV = yuvarla(net × oran / 100))."""
    ana_para = gosterim_kipi(Baglam(musteri.tip, siparis.teslimat_ulkesi, tercih), siparis.kur)[0]
    if ana_para != "EUR" or ana_para == siparis.para_birimi:
        return {"kalem_eur": None, "ara_gosterim": None}
    p = siparis.para_birimi
    satirlar = []
    for k in siparis.kalemler:
        net = yuvarla(k.birim_net_eur * k.adet)
        oran = (k.kdv * 100 / k.net).quantize(Decimal("1")) if k.net else Decimal("0")
        kdv = yuvarla(net * oran / 100)
        satirlar.append({"net": FiyatGosterim(net, "EUR", False, k.net, p),
                         "kdv": FiyatGosterim(kdv, "EUR", False, k.kdv, p),
                         "brut": FiyatGosterim(net + kdv, "EUR", True, k.brut, p)})
    return {"kalem_eur": satirlar,
            "ara_gosterim": {"tutar": sum((s["net"].ana_tutar for s in satirlar), Decimal("0.00")), "para": "EUR"}}
