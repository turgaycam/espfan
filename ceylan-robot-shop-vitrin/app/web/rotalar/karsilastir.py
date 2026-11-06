"""G3c madde 24: ürün karşılaştırma (oturumda en fazla AZAMI = 5 ürün; JS'siz POST ile ekle/çıkar; tablo ve CSV).

Sayfa işlemseldir: noindex (seo.ISLEMSEL_YOL), canonical/JSON-LD yok, robots.txt'de Disallow."""
from __future__ import annotations

import csv
import io
import re
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.fiyat.kur import son_kur
from decimal import Decimal

from app.fiyat.kurallar import _kdv_dahil, gosterim_kipi, kdv_uygulanir
from app.para import yuvarla
from app.katalog.depo import Urun, kategori_yolu, teknik_getir, urun_getir
from app.katalog.marka import marka_cikar
from app.metin import normalize
from app.web import karsilastirma
from app.web.bagimlilik import db_bagimliligi
from app.web import baglam as baglam_modulu
from app.stok import musait_adet
from app.web.baglam import (gorunen_ad, TR_SAAT, ayrilan_haritasi, bildir, dil_bul, fiyat_baglami, mevcut_sepet_id, para_bicimle,
                            sablon, seo_baglami)
from app.hesap.dogrulama import ab_ulkesi_mi
from app.web.teslim import AB_IS_GUNU, TR_IS_GUNU, teslim_metni
from app.web.guvenlik import aktif_musteri, capali, csrf_dogrula, guvenli_sonraki

router = APIRouter()
BOS = "—"
TEKNIK_SATIR_UST = 40          # birleşik teknik özellik satırı üst sınırı (tablo okunur kalsın)
UZUN_DEGER = 140               # G3e madde 23: bu uzunluktan uzun hücre kesilir, tamamı <details> içinde
CSV_TEHLIKELI = ("=", "+", "-", "@", "\t", "\r")


def _kimlik(deger: object) -> int:
    try:
        n = int(str(deger).strip())
    except (TypeError, ValueError):
        raise HTTPException(status_code=400) from None
    if not 0 < n < 2**62:
        raise HTTPException(status_code=400)
    return n


def _sonraki(form, dil: str) -> str:
    return guvenli_sonraki(str(form.get("sonraki", ""))[:500], f"/{dil}/karsilastir")


@router.post("/{dil:dil}/karsilastir/ekle")
async def karsilastir_ekle(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    await csrf_dogrula(request)
    form = await request.form()
    urun_id = _kimlik(form.get("urun_id"))
    urun = urun_getir(con, urun_id)
    if urun is None or not urun.aktif:
        raise HTTPException(status_code=404)
    karsilastirma.aktifler(request, con)               # pasifleşmiş ürünler önce düşer (yer açılır)
    eklendi, cikan = karsilastirma.ekle(request, urun_id)
    bag = (f"/{dil}/karsilastir", "karsilastir.git", "karsilastir-git")
    ad = gorunen_ad(request, con, urun.id, urun.ad)
    if cikan is not None:
        eski = urun_getir(con, cikan)
        bildir(request, "karsilastir.en_eski_cikti", ad=ad, eski=gorunen_ad(request, con, cikan, eski.ad) if eski else "",
               azami=karsilastirma.AZAMI, bag=bag, urun=urun_id)
    elif eklendi:   # G3g madde 6: onay ürünün kartında da (çapa)
        bildir(request, "karsilastir.eklendi", ad=ad, adet=len(karsilastirma.liste(request)),
               azami=karsilastirma.AZAMI, bag=bag, urun=urun_id)
    else:
        bildir(request, "karsilastir.zaten_var", ad=ad, bag=bag, urun=urun_id)
    return RedirectResponse(capali(_sonraki(form, dil), urun_id), status_code=303)


@router.post("/{dil:dil}/karsilastir/kaldir")
async def karsilastir_kaldir(dil: str, request: Request) -> Response:
    await csrf_dogrula(request)
    form = await request.form()
    urun_id = _kimlik(form.get("urun_id"))
    karsilastirma.kaldir(request, urun_id)
    return RedirectResponse(capali(_sonraki(form, dil), urun_id), status_code=303)


@router.post("/{dil:dil}/karsilastir/temizle")
async def karsilastir_temizle(dil: str, request: Request) -> Response:
    await csrf_dogrula(request)
    form = await request.form()
    karsilastirma.temizle(request)
    return RedirectResponse(_sonraki(form, dil), status_code=303)


def _tek_urunde(degerler: list[str]) -> bool:
    """G3m madde 13: teknik satır yalnız bir üründe dolu (karşılaştırılamaz)."""
    return sum(d != BOS for d in degerler) == 1


def _satir_gerekli(degerler: list[str], fark: bool, teknik: bool = False, tek: bool = False) -> bool:
    """G3e madde 23: tümü "—" olan satır gizlenir; fark=True (Farklılıkları göster) iken tüm ürünlerde aynı olan satır
    da gizlenir. G3l madde 20: teknik bölümde "yalnız farklılıklar" dolu ("—" olmayan) değerleri karşılaştırır: en az
    iki farklı dolu değer yoksa (yalnız bir üründe dolu, diğerleri "—"; ya da dolu değerler aynı) satır gizlenir.
    G3m madde 13: tek=True ("göster" bağlantısı) iken yalnız bir üründe dolu satırlar gösterilir."""
    if all(d == BOS for d in degerler):
        return False
    if fark and teknik:
        return len({d for d in degerler if d != BOS}) > 1 or (tek and _tek_urunde(degerler))
    return not (fark and len(degerler) > 1 and len(set(degerler)) == 1)


def garanti_kodu(u: Urun) -> str:
    """Güven satırının (garanti özeti) durum kodu — _makrolar.html garanti_ozeti ile aynı eşleme (G3h madde 12:
    yalnız farklılıklarda aynı garanti metni gizlenir)."""
    if u.durum_kodu == "yenilenmis":
        return "ikinci_el_test_edildi"
    return u.durum_kodu if u.durum_kodu in ("yeni", "ikinci_el", "ikinci_el_test_edildi", "ikinci_el_oldugu_gibi") \
        else "belirtilmemis"


def _tablo(request: Request, con: sqlite3.Connection, fark: bool = False, tek: bool = False) -> dict:
    """Karşılaştırma tablosunun ortak verisi (HTML ve CSV): ürünler + düz metin satırları + birleşik teknik satırlar."""
    dil = dil_bul(request)
    ceviri = request.app.state.ceviri
    kat_ceviri = request.app.state.kategori_ceviri

    def t(anahtar: str, **k) -> str:
        return ceviri.t(dil, anahtar, **k)

    urunler: list[Urun] = [u for u in (urun_getir(con, i) for i in karsilastirma.aktifler(request, con))
                           if u is not None]
    musteri = aktif_musteri(request, con)
    baglam = fiyat_baglami(request, musteri)
    sid = mevcut_sepet_id(con, request, musteri)
    ayrilan = ayrilan_haritasi(request, con, sid)

    def musait(u: Urun) -> int:     # G3e düzeltme 3: ayrılabilir adet
        return musait_adet(u.stok, ayrilan.get(u.id, 0))
    kur = son_kur(con)
    kur_degeri = kur.eur_satis if kur is not None else None

    tercih_para = gosterim_kipi(baglam, kur_degeri)[0]
    # G3j madde 12: yurt dışında € ana gösterimde ₺ ikincil yok
    try_ikincil = baglam.teslimat_ulkesi == "TR"

    def ikili(eur: Decimal, try_: Decimal | None) -> tuple[str, str | None]:
        """G3k madde 9: ana tutar ziyaretçinin gösterim tercihinde (₺ ya da €), ikincil küçük satır diğer birim."""
        if tercih_para == "TRY" and try_ is not None:
            return para_bicimle(try_, "TRY", dil), para_bicimle(eur, "EUR", dil)
        return para_bicimle(eur, "EUR", dil), (para_bicimle(try_, "TRY", dil) if try_ is not None and try_ikincil
                                               else None)

    def fiyatlar(u: Urun) -> tuple[tuple[str, str | None], tuple[str, str | None]]:
        """((KDV hariç ana, ikincil), (KDV dahil ana, ikincil))."""
        if u.teklif_zorunlu:
            metin = t("urun.fiyat_teklifle_kdv" if u.kdv_gecersiz else "urun.fiyat_teklifle")   # G3j madde 4
            return (metin, None), (metin, None)
        net = sayisal_fiyatlar(u, kur_degeri)
        haric = ikili(net["eur"], net["try"])
        if not kdv_uygulanir(baglam):
            return haric, (t("fiyat.kdv_uygulanmaz"), None)
        return haric, ikili(_kdv_dahil(net["eur"], u.kdv_orani),
                            _kdv_dahil(net["try"], u.kdv_orani) if net["try"] is not None else None)

    def durum(u: Urun) -> str:
        if u.durum_kodu == "belirtilmemis":
            return t("durum.belirtilmemis")
        ad = t(f"durum.{u.durum_kodu}") if ceviri.var(f"durum.{u.durum_kodu}") else u.durum_kodu
        return f"{ad} ({t('urun.ornek_aciklama')})" if u.durum_ornek else ad   # G3i madde 11: anlamıyla

    bugun = baglam_modulu.simdi().astimezone(TR_SAAT).date()

    def tumu_ayrilmis(u: Urun) -> bool:
        return u.stok > 0 and musait(u) <= 0

    def stok(u: Urun) -> str:
        """G3m madde 1: tümü ayrılmışsa liste ve ürün sayfasıyla aynı "Şu an alınabilir stok yok · …" metni."""
        if tumu_ayrilmis(u):
            return baglam_modulu.ayrilmis_metni_uret(request, con, u, sid, t, dil, baglam.teslimat_ulkesi)   # G3g m. 5
        return t("urun.stokta", adet=musait(u)) if u.stok > 0 else t("karsilastir.stok_yok")

    def teslim(u: Urun) -> str:   # G3e madde 11: ürün sayfasıyla aynı metin (tümü ayrılmışta stok satırında)
        if tumu_ayrilmis(u):
            return BOS
        return teslim_metni(u, baglam.teslimat_ulkesi, bugun, dil, t)

    def teslim_gun(u: Urun) -> tuple[int | None, int | None]:
        """G3l madde 20 (CSV): teslim metniyle aynı kural, sayısal (iş günü; tedarikli üründe kaynaktaki tedarik süresi
        günü); teklifle / tümü ayrılmış / bilinmeyen: boş."""
        if u.teklif_zorunlu:
            return None, None
        if u.stok <= 0:
            return (u.tedarik_suresi_gun, u.tedarik_suresi_gun) if u.tedarik_suresi_gun else (None, None)
        ulke = baglam.teslimat_ulkesi
        if musait(u) <= 0 or not ulke:
            return None, None
        if ulke == "TR":
            return TR_IS_GUNU
        return AB_IS_GUNU if ab_ulkesi_mi(ulke) else (None, None)

    def kategori(u: Urun) -> str:
        yol = kategori_yolu(con, u.kategori_id) if u.kategori_id else []
        return " › ".join(kat_ceviri.metin(k.ad, dil) for k in yol) or BOS

    fiyat = [fiyatlar(u) for u in urunler]
    metin_satirlari = [   # G3e madde 10: parça no = üretici kodu (varsa), stok kodu = iç SKU
        # G3j madde 11: fiyat görsel/addan hemen sonra (ilk ekranda); ardından durum, stok, teslim; sonra kimlik satırları
        ("karsilastir.fiyat_haric", [f[0][0] for f in fiyat], "sayi"),
        # G3l madde 20: yurt dışı (KDV uygulanmaz) ya da € (KDV hariç) gösterimde "KDV dahil" satırı yok
        *([("karsilastir.fiyat_dahil", [f[1][0] for f in fiyat], "sayi")]
          if kdv_uygulanir(baglam) and tercih_para == "TRY" else []),
        ("karsilastir.durum", [durum(u) for u in urunler], ""),
        ("karsilastir.stok", [stok(u) for u in urunler], ""),
        ("karsilastir.teslim", [teslim(u) for u in urunler], ""),
        ("karsilastir.parca_no", [u.uretici_kodu or u.sku for u in urunler], "parca-no"),
        *([("karsilastir.stok_kodu", [u.sku for u in urunler], "parca-no")] if any(u.uretici_kodu for u in urunler)
          else []),
        ("karsilastir.marka", [marka_cikar(u.ad) or BOS for u in urunler], ""),
        ("karsilastir.kategori", [kategori(u) for u in urunler], ""),
    ]
    # teknik özellikler: etiketler normalize edilerek birleşir (ilk görülen yazım), eksik hücre "—".
    # G3g madde 11: /en'de geçerli EN çevirisi olan ürünün satırları EN (ürün sayfasıyla aynı yardımcı); çevirisi
    # olmayanın satırları Türkçe kalır, ayrı anahtarla (EN satırla karışmaz) ve lang="tr" işaretiyle.
    cevirmeler = baglam_modulu.urun_cevirileri(request, con, [u.id for u in urunler], dil)
    anahtarlar: dict[str, str] = {}
    tr_anahtar: set[str] = set()
    makine = False
    hucreler: list[dict[str, str]] = []
    for u in urunler:
        teknik = teknik_getir(con, u.id)
        ozellikler = teknik.ozellikler if teknik else ()
        cev = cevirmeler.get(u.id)
        en_satirlar = cev.teknik if cev is not None and cev.teknik and ozellikler else None
        if en_satirlar:
            ozellikler, makine = en_satirlar, makine or cev.taslak
        tr_mi = dil != "tr" and not en_satirlar
        satir: dict[str, str] = {}
        ham: dict[str, str] = {}          # anahtar -> bu üründe o anahtara düşen ham etiket
        for etiket, deger in ozellikler:
            if karsilastirma.tip_parca_no_ayni(etiket, deger, u.uretici_kodu or u.sku):
                continue   # Fix 1: parça no'yu tekrarlayan "Type"/"Tip" hücresi "—" (ürün sayfası ve CSV ile aynı kural)
            # G3h madde 9: yalnız dil eki ("(Input)") atılır, açık eşanlamlılar (ozellik_esanlam.yaml) aynı satır
            n = karsilastirma.ozellik_anahtari(etiket)
            if not n:
                continue
            etiket_n, gorunen = normalize(etiket), karsilastirma.etiket_temizle(etiket)
            if dil == "tr" and normalize(gorunen) == "type":      # G3l madde 20: kaynaktaki İngilizce "Type" anahtarı
                gorunen = t("karsilastir.tip")
            if n in ham and ham[n] != etiket_n:
                # inceleme C-1: aynı üründe iki farklı etiket aynı anahtara düşerse birleştirilmez (ayrı satır)
                n, gorunen = "ham:" + etiket_n, etiket.strip()
            ham.setdefault(n, etiket_n)
            n = "tr:" + n if tr_mi else n
            if tr_mi:
                tr_anahtar.add(n)
            anahtarlar.setdefault(n, gorunen)
            satir[n] = f"{satir[n]}; {deger}" if n in satir else deger
        hucreler.append(satir)
    # G3h madde 10: teknik verisi hiç olmayan ürün sütunu tek birleşik "veri yok" hücresidir; satır gizleme ve
    # farklılık karşılaştırması yalnız verisi olan ürünlerin değerleriyle yapılır
    veri_yok = [not h for h in hucreler]

    def verili(degerler: list[str]) -> list[str]:
        return [d for d, yok in zip(degerler, veri_yok) if not yok]
    teknik_satirlari = [(etiket, [h.get(n, BOS) for h in hucreler], n in tr_anahtar)
                        for n, etiket in list(anahtarlar.items())[:TEKNIK_SATIR_UST]]
    metin_satirlari = [s for s in metin_satirlari if _satir_gerekli(s[1], fark)]
    # G3m madde 13: "yalnız farklılıklar"da gizlenen tek ürünlük satır sayısı ("… N özellik gizlendi — göster")
    tek_sayisi = sum(1 for s in teknik_satirlari if _tek_urunde(verili(s[1]))) if fark else 0
    teknik_satirlari = [s for s in teknik_satirlari if _satir_gerekli(verili(s[1]), fark, teknik=True, tek=tek)]
    # G3m madde 12: aynı görünen adlı ürünlerin sütun başlığında parça no / stok kodu ikinci satır
    gorunen = [normalize(cevirmeler[u.id].ad if u.id in cevirmeler else u.ad) for u in urunler]
    ayni_adli = {u.id for u, ad in zip(urunler, gorunen) if gorunen.count(ad) > 1}
    garanti_kodlari = {garanti_kodu(u) for u in urunler}
    return {"urunler": urunler, "metin_satirlari": metin_satirlari, "teknik_satirlari": teknik_satirlari,
            "stok_adet": [max(0, u.stok) for u in urunler],     # G3m madde 14: ham stok; alınabilir ayrı
            "alinabilir_adet": [max(0, musait(u)) if u.stok > 0 else 0 for u in urunler],
            "durum_metin": [durum(u) for u in urunler],
            "teslim_gun": [teslim_gun(u) for u in urunler],
            "fiyat_ikincil": {"karsilastir.fiyat_haric": [f[0][1] for f in fiyat],
                              "karsilastir.fiyat_dahil": [f[1][1] for f in fiyat]},
            "kur_degeri": kur_degeri, "kdv_var": kdv_uygulanir(baglam),
            "veri_yok": veri_yok, "teknik_verili": veri_yok.count(False),
            "guven_goster": not (fark and len(urunler) > 1 and len(garanti_kodlari) == 1),
            "teknik_kirpildi": len(anahtarlar) > TEKNIK_SATIR_UST, "fark": fark, "tek": tek,
            "tek_sayisi": tek_sayisi, "ayni_adli": ayni_adli,
            "teknik_tr_var": any(s[2] for s in teknik_satirlari),
            "teknik_makine": makine and any(not s[2] for s in teknik_satirlari)}


@router.get("/{dil:dil}/karsilastir")
def karsilastir_sayfasi(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    fark = request.query_params.get("fark") == "1"
    tablo = _tablo(request, con, fark=fark, tek=fark and request.query_params.get("tek") == "1")
    ceviri = request.app.state.ceviri
    return sablon(request, "karsilastir.html", {
        **tablo, "azami": karsilastirma.AZAMI, "uzun_deger": UZUN_DEGER,
        "seo": seo_baglami(request, aciklama=ceviri.t(dil, "karsilastir.aciklama")),
    })


def sayisal_fiyatlar(u: Urun, kur: Decimal | None) -> dict:
    """G3k madde 9: KDV hariç € ve (kur varsa) ₺ birim fiyat (sepetle aynı yuvarlama)."""
    return {"eur": yuvarla(u.net_fiyat_eur), "try": yuvarla(u.net_fiyat_eur * kur) if kur is not None else None}


def _csv_sayi(x: Decimal | None, virgul: bool = False) -> str:
    """G3n madde 15: virgul=True (?ondalik=virgul, Türkçe Excel) ondalık ayraç virgül; varsayılan nokta."""
    metin = "" if x is None else f"{x:.2f}"
    return metin.replace(".", ",") if virgul else metin


def _csv_hucre(deger: str) -> str:
    """Metin hücresi: "—" (değer yok) boş hücre (G3l madde 20); formül gibi başlayan gerçek metin "'" önekiyle."""
    deger = str(deger)
    if deger == BOS:
        return ""
    return "'" + deger if deger.startswith(CSV_TEHLIKELI) else deger


CSV_SUTUNLARI = ("urun_id", "sku", "parca_no", "ad", "marka", "durum", "stok_adet", "alinabilir_adet", "teslim_gun_min",
                 "teslim_gun_max", "fiyat_kdv_haric_try", "fiyat_kdv_dahil_try", "fiyat_kdv_haric_eur", "fiyat_temsili",
                 "para_birimi_notu", "url")


def _csv_sutun_adi(etiket: str, kullanilan: set[str]) -> str:
    """G3m madde 14: teknik özellik sütunu ASCII snake_case ("Nominal Tork" -> teknik_nominal_tork); çakışırsa _2, _3."""
    kok = "teknik_" + ("_".join(re.findall(r"[a-z0-9]+", normalize(etiket).encode("ascii", "ignore").decode()))
                       or "ozellik")
    ad, n = kok, 1
    while ad in kullanilan:
        n += 1
        ad = f"{kok}_{n}"
    kullanilan.add(ad)
    return ad


@router.get("/{dil:dil}/karsilastir.csv")
def karsilastir_csv(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    """Satın almacı için tablo dökümü (Excel uyumlu: UTF-8 BOM, ';' ayraç). Hücreler formül olarak yorumlanmaz.
    G3m madde 14: düz tablo — ürün başına bir satır; sabit sütunlar (CSV_SUTUNLARI) + teknik özellik başına bir sütun
    (yoksa boş). Sayılar nokta ondalık, tutarlar iki basamak."""
    tablo = _tablo(request, con)
    t = request.app.state.ceviri.t
    urunler = tablo["urunler"]
    virgul = request.query_params.get("ondalik") == "virgul"     # G3n madde 15
    tampon = io.StringIO()
    yazici = csv.writer(tampon, delimiter=";", lineterminator="\r\n")
    en = baglam_modulu.urun_cevirileri(request, con, [u.id for u in urunler], dil)   # G3f
    kullanilan: set[str] = set(CSV_SUTUNLARI)
    teknik = [(_csv_sutun_adi(etiket, kullanilan), etiket, degerler)
              for etiket, degerler, _ in tablo["teknik_satirlari"]]
    yazici.writerow([*CSV_SUTUNLARI, *(ad for ad, _, _ in teknik)])
    # G3k madde 9: fiyatlar sayısal (nokta ondalık, birim simgesi yok; teklifle satılan boş)
    kur = son_kur(con)
    kur_degeri = tablo["kur_degeri"]
    if kur_degeri is None:
        notu = t(dil, "karsilastir.csv_para_notu_kursuz")
    else:
        notu = t(dil, "karsilastir.csv_para_notu", kur=baglam_modulu.kur_bicimle(kur_degeri, dil),
                 tarih=baglam_modulu.tarih_bicimle(kur.tarih, dil) if kur is not None else "")
    if not tablo["kdv_var"]:
        notu += t(dil, "karsilastir.csv_kdv_uygulanmaz")
    kok = request.app.state.ayarlar.site_kok.rstrip("/")
    for i, u in enumerate(urunler):
        f = None if u.teklif_zorunlu else sayisal_fiyatlar(u, kur_degeri)
        # fix 1 m-3: KDV uygulanmayan (ihracat) ziyaretçide KDV dahil sütunu boş (ekranda "KDV uygulanmaz")
        dahil = _kdv_dahil(f["try"], u.kdv_orani) if f and f["try"] is not None and tablo["kdv_var"] else None
        alt, ust = tablo["teslim_gun"][i]
        yazici.writerow([
            str(u.id), _csv_hucre(u.sku), _csv_hucre(u.uretici_kodu or u.sku),
            _csv_hucre(en[u.id].ad if u.id in en else u.ad), _csv_hucre(marka_cikar(u.ad) or ""),
            _csv_hucre(tablo["durum_metin"][i]), str(tablo["stok_adet"][i]), str(tablo["alinabilir_adet"][i]),
            "" if alt is None else str(alt), "" if ust is None else str(ust),
            _csv_sayi(f and f["try"], virgul), _csv_sayi(dahil, virgul), _csv_sayi(f and f["eur"], virgul),
            "" if f is None else ("1" if u.fiyat_temsili else "0"), _csv_hucre(notu),
            f"{kok}/{dil}/urun/{u.id}",
            # G3n madde 15: parça no'yu tekrarlayan "Type"/"Tip" değeri boş
            *("" if karsilastirma.tip_parca_no_ayni(etiket, degerler[i], u.uretici_kodu or u.sku) else _csv_hucre(degerler[i])
              for _, etiket, degerler in teknik)])
    govde = "﻿" + tampon.getvalue()
    return Response(govde.encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition":   # Fix 1 (m-6): virgüllü sürüm ayrı dosya adıyla
                             'attachment; filename="ceylan-robot-karsilastirma%s.csv"' % ("-virgul" if virgul else ""),
                             "Cache-Control": "no-store"})
