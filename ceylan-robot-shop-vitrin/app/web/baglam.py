"""Fiyat bağlamı, şablon ortak değişkenleri, biçimleyiciler ve hata sayfası."""
from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from dataclasses import replace
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from jinja2 import pass_context
from markupsafe import Markup, escape

from app.db import baglan
from app.esitleme.gorsel import KISA_YOL_SINIRI, ON_EK, base64_mu, yerel_ad
from app.fiyat.kur import kur_bayat_mi, son_kur
from app.fiyat.kurallar import (FIYAT_GOSTERIMLERI, Baglam, MusteriTipi, birim_fiyat_gosterimi, gosterim_kipi,
                                kdv_karsiligi, kdv_uygulanir)
from app.hesap.dogrulama import ab_ulkesi_mi
from app.hesap.servis import Musteri
from app.katalog.depo import kategori_agaci_onbellekli
from app.katalog.urun_ceviri import UrunCeviri, ceviriler_getir
from app.metin import en_ad_duzelt, normalize
from app.para import d, yuvarla
from app.sepet.servis import adet_toplam
from app.web.dil import DILLER
from app.web import karsilastirma
from app.web import seo as seo_modulu
from app.stok import ayirma_bitisleri, ayrilan_adetler, musait_adet
from app.web.teslim import AB_IS_GUNU, KARGO_IS_GUNU, TR_IS_GUNU, teslim_metni
from app.web.guvenlik import aktif_musteri, csrf_jetonu, guvenlik_basliklari, oturum_kimligi

log = logging.getLogger("cr_shop.web")

TR_SAAT = timezone(timedelta(hours=3))  # Türkiye 2016'dan beri sabit UTC+3
SATICI_UNVAN = "MUSTAFA CEYLAN ENDÜSTRİ A.Ş."   # künye ve proforma alıcısı (tek kaynak, G3e düzeltme 1 M-3)
SATICI_ADRES = "K.O.S.B. 3. Sk., No: 7, 42250 Selçuklu / Konya"   # künye merkez adresi (G3i: proforma satıcı adresi)
ACIK_AYIP_IHBAR_GUN = 2   # G3i madde 13: ticari alımda açık ayıp ihbar süresi (İade sayfası B; ürün sayfası özeti)
ULKELER = ("TR", "DE", "AT", "NL", "FR", "IT", "PL", "GB", "US", "AZ", "SA", "AE")
PARA_SEMBOLU = {"TRY": "₺", "EUR": "€"}
# G3m madde 9: rozet ve filtrede kısa açıklaması olan durumlar (sıra filtre notundaki sıradır)
DURUM_ACIKLAMALI = ("ikinci_el", "ikinci_el_test_edildi")
YASAL_SAYFALAR = (
    "on-bilgilendirme", "mesafeli-satis", "iade", "garanti", "kvkk",
    "acik-riza", "cerez", "gizlilik", "kullanim", "kunye",
)


def simdi() -> datetime:
    return datetime.now(UTC)


def _sayi(x: Decimal, hane: int, dil: str) -> str:
    metin = f"{abs(x):,.{hane}f}"
    if dil == "tr":
        metin = metin.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return metin


def para_bicimle(tutar: Decimal, para: str, dil: str) -> str:
    q = yuvarla(d(tutar))
    isaret = "-" if q < 0 else ""
    sembol = PARA_SEMBOLU.get(para, para)
    sayi = _sayi(q, 2, dil)
    return f"{isaret}{sayi} {sembol}" if dil == "tr" else f"{isaret}{sembol}{sayi}"


def kur_bicimle(kur: Decimal, dil: str) -> str:
    q = d(kur).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    sayi = _sayi(q, 4, dil)
    return f"{sayi} ₺" if dil == "tr" else f"₺{sayi}"


AY_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _gun_metni(z: date, dil: str) -> str:
    return z.strftime("%d.%m.%Y") if dil == "tr" else f"{z.day} {AY_EN[z.month - 1]} {z.year}"


def tarih_bicimle(z: date | datetime, dil: str, saatsiz: bool = False) -> str:
    """TR "13.10.2026 22:21", EN "13 Oct 2026 22:21" (G3l madde 10: kullanıcıya ISO biçim gösterilmez); saatli değer TR
    saatine çevrilir. saatsiz: yalnız (TR saatine göre) gün."""
    if isinstance(z, datetime):
        if z.tzinfo is None:
            z = z.replace(tzinfo=UTC)
        z = z.astimezone(TR_SAAT)
        if not saatsiz:
            return f"{_gun_metni(z.date(), dil)} {z:%H:%M}"
        z = z.date()
    return _gun_metni(z, dil)


def gun_tarihi(deger, dil: str) -> str:
    """G3k madde 12: gün tarihi (YYYY-MM-DD metni ya da date): TR "15.11.2026", EN "15 Nov 2026"; okunamazsa aynen."""
    try:
        z = deger if isinstance(deger, date) else date.fromisoformat(str(deger))
    except ValueError:
        return str(deger or "")
    return _gun_metni(z, dil)


# G3k madde 23: alıcı ülkesinin saat dilimi (AB + Birleşik Krallık + İsviçre + ABD doğu; fix 1 m-4: AZ, SA, AE);
# eşlemesi olmayan: UTC. tzdata paketi requirements'ta (Windows / slim imajda da çalışsın)
ULKE_SAAT_DILIMI = {"DE": "Europe/Berlin", "AT": "Europe/Vienna", "NL": "Europe/Amsterdam", "FR": "Europe/Paris",
                    "IT": "Europe/Rome", "PL": "Europe/Warsaw", "GB": "Europe/London", "CH": "Europe/Zurich",
                    "US": "America/New_York", "AZ": "Asia/Baku", "SA": "Asia/Riyadh", "AE": "Asia/Dubai"}


def _yerel_dilim(ulke: str | None):
    """Türkiye ya da ülke seçilmemişse None; yoksa ülkenin saat dilimi (bulunamazsa UTC)."""
    if not ulke or ulke == "TR":
        return None
    try:
        return ZoneInfo(ULKE_SAAT_DILIMI[ulke]) if ulke in ULKE_SAAT_DILIMI else UTC
    except ZoneInfoNotFoundError:
        return UTC


def _kisaltma(yerel: datetime) -> str:
    """Saat dilimi kısaltması; sayısal adlarda ("+04") "UTC+4"."""
    ad = yerel.tzname() or "UTC"
    if ad[:1] in "+-" and ad[1:].isdigit():
        return f"UTC{ad[0]}{int(ad[1:3])}" + (f":{ad[3:5]}" if len(ad) > 3 and ad[3:5] != "00" else "")
    return ad


def _saat_ve_kisaltma(z: datetime, dilim) -> str:
    yerel = z.astimezone(dilim)
    return f"{yerel:%H:%M} {_kisaltma(yerel)}"


def tarih_tz_bicimle(z: datetime, dil: str, ulke: str | None, t) -> str:
    """G3j madde 14 + G3k madde 23: saatli zaman TSİ/TRT ile; alıcı ülkesi Türkiye değilse yanında yerel saat.
    G3l madde 10 (tek biçim): TR "13.10.2026 22:21 (TSİ)", EN "13 Oct 2026 22:21 TRT"; yurt dışı
    "16.10.2026 13:55 TSİ (12:55 CEST)" / "16 Oct 2026 13:55 TRT (12:55 CEST)"."""
    dilim = _yerel_dilim(ulke)
    if dilim is None:
        return f"{tarih_bicimle(z, dil)} {t('genel.saat_dilimi')}"
    if z.tzinfo is None:
        z = z.replace(tzinfo=UTC)
    return f"{tarih_bicimle(z, dil)} {t('genel.saat_kisa')} ({_saat_ve_kisaltma(z, dilim)})"


def calisma_saatleri_metni(ulke: str | None, t, bugun: date | None = None) -> str:
    """G3k madde 23: alt bilgideki çalışma saatleri; Türkiye dışı ülkede alıcı saatiyle."""
    dilim = _yerel_dilim(ulke)
    if dilim is None:
        return t("alt.calisma_saatleri")
    gun = bugun or simdi().astimezone(TR_SAAT).date()
    bas = datetime(gun.year, gun.month, gun.day, 8, 30, tzinfo=TR_SAAT).astimezone(dilim)
    son = datetime(gun.year, gun.month, gun.day, 18, 0, tzinfo=TR_SAAT).astimezone(dilim)
    return t("alt.calisma_saatleri_yerel", yerel=f"{bas:%H:%M}–{son:%H:%M} {_kisaltma(son)}")


def _oturum(request: Request) -> dict:
    return request.session if "session" in request.scope else {}


def dil_bul(request: Request) -> str:
    dil = request.path_params.get("dil")
    if dil in DILLER:
        return dil
    parca = request.url.path.strip("/").split("/", 1)[0]
    return parca if parca in DILLER else "tr"  # dil öneksiz yollar (yönetim, /geri-bildirim) Türkçe — K9


def ulke_secimi(request: Request) -> str | None:
    """Ziyaretçinin /tercih ile açıkça seçtiği ülke (oturum, yoksa çerez); seçim yoksa None."""
    ulke = _oturum(request).get("ulke") or request.cookies.get("ulke")
    return ulke if ulke in ULKELER else None


def dil_bolgesi(request: Request) -> str | None:
    """G3e madde 13: Accept-Language'daki (q sırasıyla) ilk bölge alt etiketli dil etiketinin bölgesi (de-DE -> DE)."""
    etiketler = []
    for sira, parca in enumerate(request.headers.get("accept-language", "")[:200].split(",")):
        etiket, _, param = parca.strip().partition(";")
        q = 1.0
        if param.strip().startswith("q="):
            try:
                q = float(param.strip()[2:])
            except ValueError:
                q = 0.0
        if not q > 0:            # düzeltme 1 (M-1): q=0 "istemiyorum" demektir; nan/bozuk değer de atlanır
            continue
        etiketler.append((-q, sira, etiket.strip()))
    for _, _, etiket in sorted(etiketler):
        alt = etiket.split("-")
        if len(alt) >= 2 and len(alt[1]) == 2 and alt[1].isalpha() and alt[1].upper() in ULKELER:
            return alt[1].upper()   # düzeltme 1 (M-1): desteklenen ülkesi olan ilk bölge
    return None


def varsayilan_ulke(request: Request) -> str | None:
    """G3e madde 13: açık seçim (oturum/çerez) > Accept-Language bölgesi (desteklenen ülkeyse) > /tr -> TR;
    /en'de ülke seçilmemiş sayılır (None: fiyat EUR KDV hariç + "Ülkenizi seçin" ipucu)."""
    secim = ulke_secimi(request)
    if secim:
        return secim
    bolge = dil_bolgesi(request)
    if bolge in ULKELER:
        return bolge
    return "TR" if dil_bul(request) == "tr" else None


def ulke_tercihi(request: Request) -> str:
    """Formlarda (teklif ülkesi) varsayılan; ülke seçilmemişse TR."""
    return varsayilan_ulke(request) or "TR"


def oturum_ulkesi(request: Request) -> str | None:
    """Bu oturumda üst bantta seçilen ülke (çerez sayılmaz). Girişte silinir (hesap.oturum_ac): girişli müşteride
    giriş SONRASI seçim fiyat bağlamının ve ödemedeki teslim ülkesi varsayılanının kaynağıdır."""
    ulke = _oturum(request).get("ulke")
    return ulke if ulke in ULKELER else None


def musteri_ulkesi(request: Request, musteri: Musteri) -> str:
    """Girişli müşterinin geçerli teslim ülkesi: oturumda seçilen ülke, yoksa kayıtlı ülke."""
    return oturum_ulkesi(request) or (musteri.ulke or "TR").upper()


def fiyat_tercihi(request: Request) -> str | None:
    """G3i madde 2: ziyaretçinin /tercih ile seçtiği fiyat gösterimi ("try" | "eur"; oturum, yoksa çerez). Açık seçim
    girişten sonra da geçerlidir; seçim yoksa None (müşteri tipinin varsayılanı)."""
    tercih = _oturum(request).get("fiyat") or request.cookies.get("fiyat")
    return tercih if tercih in FIYAT_GOSTERIMLERI else None


def _varsayilan_baglam(request: Request, musteri: Musteri | None) -> Baglam:
    if musteri is not None:
        return Baglam(musteri_tipi=musteri.tip, teslimat_ulkesi=musteri_ulkesi(request, musteri))
    ulke = varsayilan_ulke(request)
    if ulke is None:   # G3e madde 13: ülke seçilmemiş (EN): EUR, KDV hariç; teslim ülkesi boş
        return Baglam(musteri_tipi=MusteriTipi.YURTDISI, teslimat_ulkesi="")
    tip = MusteriTipi.BIREYSEL if ulke == "TR" else MusteriTipi.YURTDISI
    return Baglam(musteri_tipi=tip, teslimat_ulkesi=ulke)


def fiyat_baglami(request: Request, musteri: Musteri | None) -> Baglam:
    return replace(_varsayilan_baglam(request, musteri), gosterim=fiyat_tercihi(request))


def etkin_gosterim(b: Baglam, kur_eur_try: Decimal | None) -> str:
    """Sayfada görünen fiyat gösterimi ("try" | "eur"): seçicide basılı düğme ve giriş bildirimi için."""
    return "try" if gosterim_kipi(b, kur_eur_try)[0] == "TRY" else "eur"


def mevcut_sepet_id(con: sqlite3.Connection, request: Request, musteri: Musteri | None) -> int | None:
    """Sepet OLUŞTURMADAN mevcut sepetin id'si (üye sepeti ya da oturum sepeti)."""
    if musteri is not None:
        satir = con.execute("SELECT id FROM sepet WHERE musteri_id = ?", (musteri.id,)).fetchone()
    else:
        oid = _oturum(request).get("oid")
        if not oid:
            return None
        satir = con.execute("SELECT id FROM sepet WHERE oturum_id = ?", (oid,)).fetchone()
    return int(satir[0]) if satir else None


def iade_anahtarlari(durum_kodu: str | None, iade_kipi: str) -> list[tuple[str, str]]:
    """G3n madde 5: iade satırı anahtarları ve yasal/iade çapası. Bireysel: 14 gün; ticari (kurumsal / yurt dışı):
    duruma göre tek ticari satır; misafir: bireysel satır + ticari satır."""
    ticari = {"ikinci_el_oldugu_gibi": "urun.iade_ticari_oldugu_gibi",
              "belirtilmemis": "urun.iade_ticari_belirtilmemis"}.get(durum_kodu or "", "urun.iade_ticari")
    if iade_kipi == "bireysel":
        return [("urun.iade_satiri", "")]
    if iade_kipi == "ticari":
        return [(ticari, "#ticari")]
    return [("urun.iade_bireysel_satir", ""), (ticari, "#ticari")]


def iade_ozet_anahtarlari(durum_kodu: str | None, iade_kipi: str) -> list[str]:
    """Fix 1 (m-1): ürün sayfası "Teslimat ve iade" özetinin anahtarları (iade_anahtarlari ile aynı durum × kip
    kuralı; metinler G3i md 13 / G3m md 7–8)."""
    if iade_kipi == "bireysel":
        return ["urun.iade_ozet_bireysel"]
    if durum_kodu == "belirtilmemis":
        return (["urun.iade_ozet_bireysel"] if iade_kipi == "misafir" else []) + ["urun.iade_ticari_belirtilmemis"]
    ek = "_oldugu_gibi" if durum_kodu == "ikinci_el_oldugu_gibi" else ""
    return [("urun.iade_ozet_ticari" if iade_kipi == "ticari" else "urun.iade_ozet") + ek]


BILDIRIM_AZAMI = 3


def bildir(request: Request, anahtar: str, *, bag: tuple[str, str, str] | None = None,
           bag2: tuple[str, str, str] | None = None, urun: int | None = None, **degerler) -> None:
    """Bir sonraki sayfada bir kez gösterilecek bilgi mesajı (çeviri anahtarı + değerler). G3c: bag=(adres, metin
    anahtarı, data-e2e) verilirse mesajın sonunda bağlantı ("Sepete git", "Karşılaştır") basılır; G3e madde 18:
    bag2 ikinci bağlantı ("Ödemeye geç"). G3g madde 6: urun verilirse mesaj o ürünün kartında / satın alma kutusunda
    (çapa #urun-<id>) da role="status" ile gösterilir."""
    liste = request.session.setdefault("bildirimler", [])
    if urun is not None:
        degerler = {**degerler, "_urun": int(urun)}
    liste.append([anahtar, degerler, *(bag or ()), *((bag2 or ()) if bag else ())])
    liste[:] = liste[-BILDIRIM_AZAMI:]   # g3c M-2: okunmayan bildirimler birikip çerezi 4 KB üstüne taşımasın


# G3b: kök kategori -> sade çizim (app/web/statik/yer-tutucu/<ad>.svg). Sıra önemlidir: "Robot Kontrol Üniteleri" ve
# "Robotik Parçaları" genel "robot" kuralından önce eşleşir. Normalize (Türkçe katlanmış) adda alt dize aranır.
YER_TUTUCU_KURALLARI = (
    (("pozisyoner",), "pozisyoner"),
    (("kontrol",), "kontrol"),
    (("robotik", "parca"), "robotik-parca"),
    (("robot",), "robot"),
    (("reduktor",), "reduktor"),
    (("guc", "kaynak"), "guc"),
    (("slider", "lineer"), "slider"),
    (("elektrik", "elektronik"), "elektrik"),
    (("mekanik",), "mekanik"),
)


def yer_tutucu(kok_kategori_ad: str | None) -> str:
    n = normalize(kok_kategori_ad or "")
    ad = next((dosya for anahtarlar, dosya in YER_TUTUCU_KURALLARI if n and any(a in n for a in anahtarlar)),
              "genel")
    return f"/statik/yer-tutucu/{ad}.svg"


# Vitrin: kök kategori kapak fotoğrafları (ceylanrobot.com vitrininden kopyalanmış statik dosyalar).
# Sıra yer tutucu ile aynıdır: kontrol ve robotik, genel "robot" kuralından önce gelir.
KAPAK_KURALLARI = (
    (("kontrol",), "kontrol"),
    (("robotik", "parca"), "parca"),
    (("robot",), "robot"),
    (("elektrik", "elektronik"), "elektrik"),
    (("mekanik",), "mekanik"),
)
KAPAK_DOSYA = {
    "robot": "kapak-robot.jpg",
    "elektrik": "kapak-elektrik.webp",
    "mekanik": "kapak-mekanik.webp",
    "kontrol": "kapak-kontrol.webp",
    "parca": "kapak-parca.webp",
    "genel": "kapak-genel.jpg",
}


def kategori_kapak(kok_kategori_ad: str | None) -> str:
    """Ana sayfa kategori kartı ve görseli olmayan öne çıkan ürün için kapak fotoğrafı."""
    n = normalize(kok_kategori_ad or "")
    ad = next((dosya for anahtarlar, dosya in KAPAK_KURALLARI if n and any(a in n for a in anahtarlar)), "genel")
    return f"/statik/vitrin/{KAPAK_DOSYA[ad]}"


def yer_tutucu_mu(adres: str) -> bool:
    return adres.startswith("/statik/yer-tutucu/")


def gorsel_adresi(urun, gorsel_kok: str, boy: str = "k") -> str:
    """Yerel görsel: /gorsel/<boy>/<ad> (k: liste/kart/teklif, b: ürün detayı). Base64'e benzeyen,
    çok uzun ya da data: değerler asla src'ye basılmaz (yer tutucu)."""
    url = (getattr(urun, "gorsel_url", None) or "").strip()
    if not url:
        return yer_tutucu(urun.kok_kategori_ad)
    ad = yerel_ad(url)
    if ad:
        return f"/gorsel/{'b' if boy == 'b' else 'k'}/{ad}"
    if (url.startswith(ON_EK) or url.startswith("data:") or len(url) > KISA_YOL_SINIRI
            or (url.startswith("/") and base64_mu(url))):
        return yer_tutucu(urun.kok_kategori_ad)
    if url.startswith("https://"):
        return url
    if url.startswith("/"):
        return gorsel_kok.rstrip("/") + url
    return gorsel_kok.rstrip("/") + "/" + url


def seo_baglami(request: Request, *, aciklama: str, dil: str | None = None, baslik: str | None = None, **ek) -> dict:
    """Taban şablonun `seo` sözlüğü (başlık, açıklama, robots, canonical, hreflang, OG, JSON-LD)."""
    ayarlar = request.app.state.ayarlar
    return seo_modulu.sayfa_seo(
        yayin_modu=ayarlar.yayin_modu, site_kok=ayarlar.site_kok, dil=dil or dil_bul(request),
        yol=request.url.path, baslik=baslik, aciklama=aciklama, **ek)


def _ortak(request: Request) -> dict[str, Any]:
    durum = request.app.state
    ceviri = durum.ceviri
    dil = dil_bul(request)
    oturum_var = "session" in request.scope
    if oturum_var:
        oturum_kimligi(request)
    con = getattr(request.state, "con", None)
    musteri = None
    sid = None
    sepet_adet = 0
    kur = None
    kok_kategoriler = []
    karsilastir_listesi: list[int] = []
    if con is not None:
        musteri = aktif_musteri(request, con)
        sid = mevcut_sepet_id(con, request, musteri)
        if sid is not None:
            sepet_adet = adet_toplam(con, sid)
        kur = son_kur(con)
        # K22 şerit; G3a: süreç içi önbellek; G3e madde 19: 0 ürünlü kategoriler menüde gösterilmez (URL çalışır)
        kok_kategoriler = [d for d in kategori_agaci_onbellekli(con, durum.katalog_onbellek) if d.urun_sayisi]
        if oturum_var:
            karsilastir_listesi = karsilastirma.aktifler(request, con)   # G3c madde 24: pasifleşen ürün düşer
    fb = fiyat_baglami(request, musteri)
    kur_degeri = kur.eur_satis if kur is not None else None
    gorsel_kok = durum.ayarlar.gorsel_kok
    telefon = (getattr(durum.ayarlar, "telefon", "") or "").strip()

    def t(anahtar: str, **k) -> str:
        return ceviri.t(dil, anahtar, **k)

    def para(tutar: Decimal, para_birimi: str) -> str:
        return para_bicimle(tutar, para_birimi, dil)

    def fiyat_goster(urun):
        return birim_fiyat_gosterimi(urun.net_fiyat_eur, urun.kdv_orani, fb, kur_degeri)

    def musait(urun) -> int:
        """G3e düzeltme 3: ayrılabilir adet = stok − açık siparişlerin ayırdığı (ziyaretçinin kendi bekleyen kart
        siparişi hariç). Stok <= 0 (tedarikli) üründe stok döner."""
        return musait_adet(urun.stok, ayrilan_haritasi(request, con, sid).get(urun.id, 0))

    def tumu_ayrilmis(urun) -> bool:
        return urun.stok > 0 and musait(urun) <= 0

    def ayrilmis_metni(urun) -> str:
        """G3g madde 5: "tümü ayrılmış" + en erken bitecek rezervasyonun zamanı."""
        return ayrilmis_metni_uret(request, con, urun, sid, t, dil, fb.teslimat_ulkesi)

    def teslim_notu(urun, ulke: str | None = None, baz: date | datetime | None = None, kisa: bool = False) -> str:
        """G3b I-4 + G3e madde 11: detay, liste, kart, sepet, ödeme ve sipariş için tek teslim metni (ülkeye göre
        tahmini varış tarihi aralığı). ulke verilmezse fiyat bağlamının ülkesi; baz verilmezse bugün (TR saati)."""
        if isinstance(baz, datetime):
            baz = (baz if baz.tzinfo else baz.replace(tzinfo=UTC)).astimezone(TR_SAAT).date()
        bugun = baz or simdi().astimezone(TR_SAAT).date()
        if baz is None and tumu_ayrilmis(urun):
            return ayrilmis_metni(urun)
        return teslim_metni(urun, fb.teslimat_ulkesi if ulke is None else ulke, bugun, dil, t, kisa=kisa)

    def siparis_teslim(urun, siparis) -> str:
        """G3m madde 2-3: siparişin KENDİ kalemi (onay, Hesabım ayrıntısı). Stok / serbest kalma metni hiç gösterilmez.
        Havale ödemesi bekleyen stoklu kalem: "Sizin için ayrıldı (ödeme son tarihine kadar)" + ödeme sonrası iş günü
        aralığı (TR 2–4, AB 4–8; tarih aralığı yok); diğer ülkede / tedarikli kalemde "Ödeme alındıktan sonra:" + teslim
        metni. Ödenmiş ve kart siparişi: sipariş tarihine göre tahmini varış (mevcut)."""
        ulke = siparis.teslimat_ulkesi
        if not (siparis.odeme_yontemi == "havale" and siparis.durum == "odeme_bekliyor"):
            # inceleme m5: ödenmiş siparişte baz ödeme zamanı (havale günler sonra ödenebilir); yoksa sipariş tarihi
            return teslim_notu(urun, ulke, getattr(siparis, "odeme_zamani", None) or siparis.olusturma)
        if urun.stok > 0 and not urun.teklif_zorunlu and (ulke == "TR" or ab_ulkesi_mi(ulke or "")):
            alt, ust = TR_IS_GUNU if ulke == "TR" else AB_IS_GUNU
            return (f"{t('siparis.sizin_icin_ayrildi')} · "   # G3n madde 6: ürün sayfasıyla aynı gün sayıları
                    f"{t('siparis.odeme_sonrasi_sure', kmin=KARGO_IS_GUNU[0], kmax=KARGO_IS_GUNU[1], min=alt, max=ust)}")
        bugun = simdi().astimezone(TR_SAAT).date()
        metin = f"{t('siparis.odeme_sonrasi')} {teslim_metni(urun, ulke, bugun, dil, t)}"
        return f"{t('siparis.sizin_icin_ayrildi')} · {metin}" if urun.stok > 0 and not urun.teklif_zorunlu else metin

    kat_ceviri = durum.kategori_ceviri

    def kat_metin(ad: str | None) -> str:
        """G3c madde 23: kategori adı düz metin (öznitelik, başlık): EN'de çeviri, yoksa ham ad."""
        return kat_ceviri.metin(ad, dil)

    def kat_ad(ad: str | None) -> Markup:
        """Görünen kategori adı: EN'de çevirisi olmayan ad Türkçe kalır ve lang="tr" ile işaretlenir (G3e: EN'de
        büyük harf ad Title Case)."""
        if kat_ceviri.cevrilmis_mi(ad, dil):
            return escape(kat_ceviri.metin(ad, dil))
        return Markup('<span lang="tr">{}</span>').format(kat_ceviri.metin(ad, dil))

    def kdv_karsilik(urun, gosterim):
        """G3b madde 12: ana fiyatın diğer KDV karşılığı (tutar, para, kdv_dahil) ya da None (ihracat)."""
        return kdv_karsiligi(urun.net_fiyat_eur, urun.kdv_orani, fb, kur_degeri, gosterim)

    if musteri is not None:
        iade_kipi = "bireysel" if musteri.tip == MusteriTipi.BIREYSEL else "ticari"
    else:
        # Fix 1 (I-1, denetleyici kararı): "site kime açık" kararına dek yurt dışı misafir de TR misafiri gibi iki satır
        # görür (bireysel 14 gün + ticari); yalnız girişli kurumsal / yurt dışı hesap tek ticari satır
        iade_kipi = "misafir"

    def iade_metinleri(urun) -> list[dict]:
        """G3n madde 5: kart, karşılaştırma ve ürün sayfasının TEK iade satırı kaynağı (durum × müşteri tipi;
        G3m madde 7–8 metinleri). [{"metin", "capa"}]"""
        return [{"metin": t(anahtar, gun=ACIK_AYIP_IHBAR_GUN), "capa": capa}
                for anahtar, capa in iade_anahtarlari(urun.durum_kodu, iade_kipi)]

    def iade_ozet_metni(urun) -> str:
        """Fix 1 (m-1): "Teslimat ve iade" özeti de aynı durum × kip yardımcısından."""
        return " ".join(t(a, gun=ACIK_AYIP_IHBAR_GUN) for a in iade_ozet_anahtarlari(urun.durum_kodu, iade_kipi))

    bildirimler = []
    yerel_bildirimler: dict[int, list[dict]] = {}
    if oturum_var:
        for kayit in request.session.pop("bildirimler", []):
            anahtar, degerler, *bag = kayit
            degerler = dict(degerler or {})
            urun_id = degerler.pop("_urun", None)
            baglar = [{"url": bag[i], "metin": ceviri.t(dil, bag[i + 1]), "e2e": bag[i + 2]}
                      for i in range(0, len(bag) - len(bag) % 3, 3)]
            b = {"metin": ceviri.t(dil, anahtar, **degerler), "baglar": baglar,
                 # G3l madde 17: karşılaştırma bildirimi ürün sayfasında yalnız çapada (genel listede tekrar yok)
                 "capa_urun": urun_id if type(urun_id) is int and anahtar.startswith("karsilastir.") else None}
            bildirimler.append(b)
            if type(urun_id) is int:      # G3g madde 6: ürün kartındaki / satın alma kutusundaki onay
                yerel_bildirimler.setdefault(urun_id, []).append(b)
    yol = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    return {
        "seo": seo_baglami(request, dil=dil, aciklama=seo_modulu.varsayilan_aciklama(dil)),
        "bal_kupu_yolu": seo_modulu.BAL_KUPU_YOLU,
        "dil": dil,
        "diller": DILLER,
        "t": t,
        "csrf": csrf_jetonu(request) if oturum_var else "",
        "musteri": musteri,
        "sepet_adet": sepet_adet,
        # Fix 14/1-4: girişli müşteride üst bant seçicisi müşterinin ülkesini gösterir (fiyat bağlamıyla tutarlı)
        "ulke": (musteri_ulkesi(request, musteri) if musteri is not None and musteri_ulkesi(request, musteri) in ULKELER
                 else varsayilan_ulke(request)),   # G3e madde 13: None = ülke seçilmemiş (EN)
        "ulkeler": ULKELER,
        "para": para,
        "para_sembolu": lambda p: PARA_SEMBOLU.get(p, p),
        "fiyat_goster": fiyat_goster,
        "kdv_karsilik": kdv_karsilik,
        "teslim_notu": teslim_notu,
        "siparis_teslim": siparis_teslim,      # G3m madde 2-3
        "havale_gun": durum.ayarlar.havale_gun,   # G3m madde 11: "Ayrılmış — en geç N iş gününde serbest"
        "durum_aciklamali": DURUM_ACIKLAMALI,
        "durum_title": lambda kod: (Markup(' title="{}"').format(t(f"durum.aciklama_{kod}"))
                                    if kod in DURUM_ACIKLAMALI else ""),   # G3m madde 9
        "musait": musait,
        "tumu_ayrilmis": tumu_ayrilmis,
        "garantili_mi": seo_modulu.garantili_mi,
        "kdv_var": kdv_uygulanir(fb),
        "fiyat_gosterim": etkin_gosterim(fb, kur_degeri),   # G3i madde 2: seçicide basılı düğme
        # G3e madde 4: iade metninin bağlamı (misafirde müşteri tipi bilinmez). G3n madde 5: yurt dışı ülke seçmiş
        # misafir yurt dışı (ticari) görünümdedir; iki satır yalnız TR / ülkesiz misafirde
        "iade_kipi": iade_kipi,
        "iade_metinleri": iade_metinleri,
        "iade_ozet_metni": iade_ozet_metni,
        "kur": kur,
        "kur_metni": kur_bicimle(kur.eur_satis, dil) if kur is not None else "",
        "kur_tarihi": tarih_bicimle(kur.tarih, dil) if kur is not None else "",
        "kur_bayat": kur is not None and kur_bayat_mi(kur, simdi().date()),
        "istek_yolu": yol[:500],
        "yasal_sayfalar": YASAL_SAYFALAR,
        "cerez_onay": request.cookies.get("cerez_onay") == "1",
        "yer_tutucu": yer_tutucu,
        "yer_tutucu_mu": yer_tutucu_mu,
        "kategori_kapak": kategori_kapak,
        "gorsel_adresi": lambda u, boy="k": gorsel_adresi(u, gorsel_kok, boy),
        "tarih": lambda z: tarih_bicimle(z, dil),
        "tarih_gun": lambda z: tarih_bicimle(z, dil, saatsiz=True),   # G3l madde 10: saatli değerin günü
        "gun_tarihi": lambda z: gun_tarihi(z, dil),   # G3k madde 12: istenen teslim tarihi (YYYY-MM-DD metni)
        # G3j madde 14: saatli son tarih / serbest kalma zamanı saat dilimiyle: "… 14:30 (TSİ)" / "(TRT, UTC+3)"
        # G3k madde 23: alıcı ülkesi Türkiye değilse yerel saat de (ulke verilmezse fiyat bağlamının ülkesi)
        "tarih_tz": lambda z, ulke=None: tarih_tz_bicimle(z, dil, ulke or fb.teslimat_ulkesi, t),
        "calisma_saatleri": calisma_saatleri_metni(fb.teslimat_ulkesi, t),
        "bildirimler": bildirimler,
        "yerel_bildirimler": yerel_bildirimler,
        "ayrilmis_metni": ayrilmis_metni,
        "arama_q": "",
        "kok_kategoriler": kok_kategoriler,
        "kat_ad": kat_ad,
        # G3f: şablon globalleri urun_ad / urun_metin bunu kullanır (bkz. sablon_globalleri)
        "urun_cevirisi_bul": lambda urun_id: urun_cevirisi(request, con, urun_id, dil),
        "ab_ulkesi_mi": ab_ulkesi_mi,
        "kat_metin": kat_metin,
        "karsilastirma": karsilastir_listesi,
        "aktif_kok_id": None,
        "telefon": telefon,
        "satici_unvan": SATICI_UNVAN,
        "acik_ayip_gun": ACIK_AYIP_IHBAR_GUN,   # G3i madde 13: İade sayfası B ve ürün sayfası ticari iade özeti
        "iletisim_eposta": (getattr(durum.ayarlar, "eposta", "") or "").strip(),
        "telefon_tel": ("+" if telefon.startswith("+") else "") + "".join(c for c in telefon if c.isdigit()),
    }


def urun_cevirileri(request: Request, con, urun_idleri, dil: str) -> dict[int, UrunCeviri]:
    """G3f: ürünlerin geçerli EN çevirileri; istek başına önbellekli (liste sayfası tek sorguyla önceden doldurur).
    TR'de ve bağlantı yoksa boş."""
    if dil == "tr" or con is None:
        return {}
    onbellek = getattr(request.state, "urun_ceviri", None)
    if onbellek is None:
        onbellek = request.state.urun_ceviri = {}
    eksik = [i for i in dict.fromkeys(urun_idleri) if isinstance(i, int) and i not in onbellek]
    if eksik:
        bulunan = ceviriler_getir(con, eksik, dil)
        for i in eksik:
            c = bulunan.get(i)
            # G3n madde 14: EN adda Türkçe İ/ı kalıntısı gösterimde düzeltilir (urun_ceviri verisi değişmez)
            onbellek[i] = replace(c, ad=en_ad_duzelt(c.ad)) if c is not None else None
    return {i: onbellek[i] for i in urun_idleri if isinstance(i, int) and onbellek.get(i) is not None}


def urun_cevirisi(request: Request, con, urun_id, dil: str) -> UrunCeviri | None:
    return urun_cevirileri(request, con, [urun_id], dil).get(urun_id) if isinstance(urun_id, int) else None


def gorunen_ad(request: Request, con, urun_id, tr_ad: str | None) -> str:
    """G3f düzeltme 1 (M-1): bildirim gibi düz metinlerde ürün adı: /en'de geçerli çeviri varsa EN, yoksa TR."""
    c = urun_cevirisi(request, con, urun_id, dil_bul(request))
    return c.ad if c is not None else (tr_ad or "")


def _ceviri_bul(ctx, urun_id) -> UrunCeviri | None:
    bul = ctx.get("urun_cevirisi_bul")
    return bul(urun_id) if callable(bul) and ctx.get("dil", "tr") != "tr" else None


@pass_context
def urun_metin(ctx, urun_id, ad: str | None) -> str:
    """G3f: ürün adı düz metin (başlık, öznitelik): EN'de geçerli çevirisi varsa EN ad, yoksa TR ad."""
    c = _ceviri_bul(ctx, urun_id)
    return c.ad if c is not None else (ad or "")


@pass_context
def urun_ad(ctx, urun_id, ad: str | None) -> Markup:
    """G3f: görünen ürün adı. EN'de geçerli çeviri yoksa TR ad lang="tr" ile işaretlenir; TR arayüz değişmez.
    Sipariş/sepet kaleminde TR kayıt adı verilir; görünen ad güncel çeviriden gelir (kayıt değişmez)."""
    c = _ceviri_bul(ctx, urun_id)
    if c is not None:
        return escape(c.ad)
    if ctx.get("dil", "tr") == "tr":
        return escape(ad or "")
    return Markup('<span lang="tr">{}</span>').format(ad or "")


def sablon_globalleri(env) -> None:
    env.globals.update(urun_ad=urun_ad, urun_metin=urun_metin)


def ayrilan_haritasi(request: Request, con, sepet_id: int | None) -> dict[int, int]:
    """İstek başına bir kez hesaplanan ayırma haritası (G3e düzeltme 3). G3g madde 4: sipariş onay sayfası
    request.state.haric_siparis ile siparişin kendi rezervasyonunu düşer."""
    onbellek = getattr(request.state, "ayrilan", None)
    if onbellek is None:
        onbellek = (ayrilan_adetler(con, simdi(), haric_sepet_id=sepet_id,
                                    haric_siparis_id=getattr(request.state, "haric_siparis", None))
                    if con is not None else {})
        request.state.ayrilan = onbellek
    return onbellek


def ayrilmis_metni_uret(request: Request, con, urun, sepet_id: int | None, t, dil: str, ulke: str | None = None) -> str:
    """G3g madde 5: "Stokta: tümü açık siparişlerce ayrılmış · en geç <tarih saat> serbest kalabilir · teklif isteyin".
    Zaman: ürünün ayırmalarından en erken biteni (kart 30 dk, havale son tarihi, ödenmiş: sonraki tam eşitleme)."""
    onbellek = getattr(request.state, "ayirma_bitis", None)   # inceleme M-9: ürün başına bir sorgu (istek boyunca)
    if onbellek is None:
        onbellek = request.state.ayirma_bitis = {}
    if urun.id not in onbellek:
        onbellek[urun.id] = (ayirma_bitisleri(con, simdi(), [urun.id], haric_sepet_id=sepet_id,
                                              haric_siparis_id=getattr(request.state, "haric_siparis", None))
                             .get(urun.id) if con is not None else None)
    bitis = onbellek[urun.id]
    if bitis is None:
        return t("urun.stok_tumu_ayrilmis_zamansiz")
    return t("urun.stok_tumu_ayrilmis", zaman=tarih_tz_bicimle(bitis, dil, ulke, t))   # G3j m. 14, G3k m. 23


def sablon(request: Request, ad: str, baglam: dict, durum: int = 200) -> HTMLResponse:
    ctx = _ortak(request)
    ctx.update(baglam)
    if durum >= 400:  # hata yanıtı kendi adresiyle indekslenmez; canonical/alternatif/JSON-LD üretmez
        ctx["seo"] = {**ctx["seo"], "canonical": None, "alternatifler": [], "og": None, "json_ld": []}
    yanit = request.app.state.sablonlar.TemplateResponse(request, ad, ctx, status_code=durum)
    # G3e düzeltme 1 (M-1): fiyat/ülke Accept-Language ve çereze bağlı; ara önbellek ayrı tutsun
    yanit.headers["Vary"] = "Accept-Language, Cookie"
    return yanit


def hata_yaniti(
    request: Request, durum: int, kimlik: str | None = None, db: bool = True, basliklar: dict | None = None
) -> Response:
    """hata.html'i üretir. 500 yanıtı ServerErrorMiddleware'den çıktığı için güvenlik başlıkları burada da yazılır."""
    ceviri = request.app.state.ceviri
    dil = dil_bul(request)
    b = f"hata.baslik_{durum}" if ceviri.var(f"hata.baslik_{durum}") else "hata.baslik_genel"
    a = f"hata.aciklama_{durum}" if ceviri.var(f"hata.aciklama_{durum}") else "hata.aciklama_genel"
    baglam = {"durum": durum, "baslik": ceviri.t(dil, b), "aciklama": ceviri.t(dil, a), "hata_kimligi": kimlik}
    con = None
    try:
        if db:
            try:
                con = baglan(request.app.state.ayarlar.db_yolu)
            except Exception:  # noqa: BLE001
                con = None
        request.state.con = con
        yanit: Response = sablon(request, "hata.html", baglam, durum=durum)
    except Exception:  # noqa: BLE001
        log.exception("hata sayfası üretilemedi")
        yanit = PlainTextResponse(f"{durum}" + (f" – {kimlik}" if kimlik else ""), status_code=durum)
    finally:
        request.state.con = None
        if con is not None:
            con.close()
    for anahtar, deger in guvenlik_basliklari(request.app.state.ayarlar.yayin_modu, request.url.path).items():
        yanit.headers[anahtar] = deger
    for anahtar, deger in (basliklar or {}).items():
        yanit.headers[anahtar] = deger
    return yanit


def siparis_alicisi(siparis, musteri: Musteri) -> dict:
    """G3i inceleme I-1: sipariş belgelerindeki alıcı kimliği (proforma, onay, Hesabım ayrıntısı) siparişteki anlık
    görüntüden. Yedek YALNIZ anlık görüntü yoksa (G3i öncesi sipariş, alici_tip NULL): unvan fatura adresindeki ad,
    vergi bilgileri hesaptaki değer. Ülke hesaptandır (hesapta değiştirilemez)."""
    if siparis.alici_tip is not None:
        return {"tip": siparis.alici_tip, "ad": siparis.alici_unvan or siparis.fatura_adresi.ad_soyad,
                "vkn": siparis.alici_vkn, "vergi_dairesi": siparis.alici_vergi_dairesi,
                "vat_id": siparis.alici_vat_id, "ulke": musteri.ulke}
    return {"tip": musteri.tip.value, "ad": siparis.alici_unvan or siparis.fatura_adresi.ad_soyad,
            "vkn": musteri.vergi_kimlik_no, "vergi_dairesi": musteri.vergi_dairesi, "vat_id": musteri.vat_id,
            "ulke": musteri.ulke}
