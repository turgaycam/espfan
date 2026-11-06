"""Ana sayfa, kategori / arama / tüm ürünler listesi, ürün detayı."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.katalog.depo import (
    SAYFA_BOYLARI, Fasetler, Kategori, KategoriDugum, ListeSorgusu, aciklama_getir, ad_kod_jetonlari, arama_terimleri,
    ayni_parca_nolu, kod_sorgusu_mu, sorgu_jetonlari, yakin_kodlar,
    faset_sayilari, gercek_durumlar, karisik_kod, kategori_agaci_onbellekli, kategori_getir, kategori_sayilari,
    kategori_yolu, one_cikanlar, suzulmus_agac, teknik_getir, urun_getir, urun_listele, urun_sayisi,
)
from app.fiyat.kur import son_kur
from app.fiyat.kurallar import Baglam, MusteriTipi, birim_fiyat_gosterimi, gosterim_kipi
from app.katalog.indeks import kod_birlesik
from app.katalog.marka import marka_cikar
from app.katalog.tip import gecerli_mi as tip_gecerli_mi, tip_adi
from app.metin import normalize
from app.web import seo
from app.web.karsilastirma import tip_parca_no_ayni
from app.web.aciklama_gosterim import taslak_gosterilir
from app.stok import musait_adet
from app.web.baglam import (ayrilan_haritasi, dil_bul, fiyat_baglami, gorsel_adresi, mevcut_sepet_id, sablon,
                            seo_baglami, urun_cevirileri, urun_cevirisi)
from app.web.guvenlik import aktif_musteri
from app.web.bagimlilik import db_bagimliligi

router = APIRouter()

SIRALAR = ("onerilen", "ad", "fiyat_artan", "fiyat_azalan")   # G3h madde 8: sorgusuz varsayılan "Önerilen"
ARAMA_SIRALARI = ("alaka", *SIRALAR)        # G3a: aramada varsayılan alaka (tam kod > kod öneki > ad)
SAYFA_UST = 10_000
FIYAT_UST = Decimal("100000000")
ARAMA_UZUNLUK = 100
EN_BUYUK_ID = 2**62  # SQLite INTEGER taşmasını önler
ONE_CIKAN_ADET = 8
ONE_CIKAN_HAVUZ = 96  # K22 "Stoktaki öne çıkanlar": bu kadar aday içinden stoktaki, teklif dışı ürünler seçilir
# G3a fasetleri: URL parametreleri (çoklu seçim aynı adın tekrarıyla: ?marka=KUKA&marka=ABB)
FASET_DEGER_UST = 20          # bir parametrede en çok değer
FASET_DEGER_UZUNLUK = 60
DURUM_DESENI = re.compile(r"[a-z_]{1,40}")
BAYRAKLAR = ("stokta", "ayrilmis", "tedarikli", "fiyatli", "teklifle")   # ?ad=1 (G3j madde 5: ayrilmis)
MARKA_GORUNEN = 4             # marka fasetinde ilk N seçenek açık, kalanı "daha fazla" içinde (G3k m. 10: 8 -> 4)
TIP_GORUNEN = 4               # G3j madde 9: ürün tipi fasetinde ilk N seçenek açık (G3k madde 10: 6 -> 4)
# G3k madde 10: "Test edilmiş" çipi kaldırıldı (Durum grubu tek yer, varsayılan açık)
HIZLI_CIPLER = (("stokta", "bayrak", "stokta"), ("yenilenmis", "durum", "yenilenmis"), ("fiyatli", "bayrak", "fiyatli"))


def _sayfa(deger: str | None) -> int:
    try:
        n = int(deger) if deger is not None else 1
    except ValueError:
        return 1
    return min(max(n, 1), SAYFA_UST)


GECERSIZ = object()          # tutar_coz: okunamayan giriş
_SAYI_TR = (re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?"), re.compile(r"\d+(?:,\d+)?"), re.compile(r"\d+\.\d{1,2}"))
_SAYI_EN = (re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?"), re.compile(r"\d+(?:\.\d+)?"), re.compile(r"\d+,\d{1,2}"))
_PARA_ISARETI = re.compile(r"[\s  ₺€]|TL$|EUR$", re.I)


def tutar_coz(deger: str | None, dil: str = "tr"):
    """G3h madde 6: fiyat aralığı girişi. TR: "10.000" = 10000, "10.000,50" = 10000,5, "10,5"; nokta + 1–2 hane ondalık
    sayılır ("12.5"). EN: "10,000.50", "10.5"; virgül + 1–2 hane ondalık. Boş -> None, okunamayan -> GECERSIZ."""
    if deger is None:
        return None
    ham = _PARA_ISARETI.sub("", deger.strip()[:30])
    if not ham:
        return None
    binlik, ondalik = (".", ",") if dil == "tr" else (",", ".")
    gruplu, duz, ters = _SAYI_TR if dil == "tr" else _SAYI_EN
    if gruplu.fullmatch(ham):
        metin = ham.replace(binlik, "").replace(ondalik, ".")
    elif duz.fullmatch(ham):
        metin = ham.replace(ondalik, ".")
    elif ters.fullmatch(ham):            # ziyaretçi diğer dilin ondalık ayracını kullandı
        metin = ham.replace(binlik, ".")
    else:
        return GECERSIZ
    try:
        x = Decimal(metin)
    except InvalidOperation:
        return GECERSIZ
    return min(x, FIYAT_UST) if x.is_finite() else GECERSIZ


def _tutar(deger: str | None, dil: str = "tr") -> Decimal | None:
    x = tutar_coz(deger, dil)
    return None if x is GECERSIZ else x


def _gecersiz_tutarlar(request: Request) -> list[str]:
    """Okunamayan fiyat girişleri (uyarı için, ham metin)."""
    dil = dil_bul(request)
    return [request.query_params[a].strip()[:20] for a in ("fmin", "fmax")
            if a in request.query_params and tutar_coz(request.query_params[a], dil) is GECERSIZ]


def _arama_metni(request: Request) -> str:
    ham = request.query_params.get("q") or ""
    temiz = "".join(c for c in ham if c.isprintable())
    return temiz.strip()[:ARAMA_UZUNLUK]


def _fiyat_araligi(request: Request) -> tuple[Decimal | None, Decimal | None, bool]:
    """(en az, en çok, yer değişti mi). Ters girilen aralık düzeltilir."""
    q = request.query_params
    dil = dil_bul(request)
    fmin, fmax = _tutar(q.get("fmin"), dil), _tutar(q.get("fmax"), dil)
    if fmin is not None and fmax is not None and fmin > fmax:
        return fmax, fmin, True
    return fmin, fmax, False


def _coklu(request: Request, ad: str) -> tuple[str, ...]:
    degerler = []
    for v in request.query_params.getlist(ad):
        v = "".join(c for c in v if c.isprintable()).strip()[:FASET_DEGER_UZUNLUK]
        if v and v not in degerler:
            degerler.append(v)
    return tuple(degerler[:FASET_DEGER_UST])


def _kimlikler(request: Request, ad: str) -> tuple[int, ...]:
    sonuc: list[int] = []
    for v in request.query_params.getlist(ad):
        try:
            n = int(v)
        except ValueError:
            continue
        if 0 < n <= EN_BUYUK_ID and n not in sonuc:
            sonuc.append(n)
    return tuple(sonuc[:FASET_DEGER_UST])


def _sayfa_boyu(request: Request) -> int:
    """G3e madde 8: ?adet= yalnız 24/48; başka değer (96 dahil) varsayılana (24) düşer."""
    deger = request.query_params.get("adet")
    return int(deger) if deger in {str(n) for n in SAYFA_BOYLARI} else SAYFA_BOYLARI[0]


def _fiyat_kipi(request: Request, con) -> tuple[str, Decimal, bool]:
    """G3e madde 9: fiyat aralığı ziyaretçinin gördüğü para birimi ve KDV kipinde (ürün listesindeki ana fiyat)."""
    kur = son_kur(con)
    return gosterim_kipi(fiyat_baglami(request, aktif_musteri(request, con)), kur.eur_satis if kur else None)


def gosterim_para_birimi(request: Request, con) -> str:
    """G3l madde 5: ziyaretçinin şu anki liste fiyatı gösterim para birimi ("TRY" | "EUR")."""
    return _fiyat_kipi(request, con)[0]


FIYAT_BIRIMLERI = ("TRY", "EUR")
YAKLASIK_KDV = Decimal("20")       # fix 1 I-2: çipteki "≈" karşılığında KDV dahil ↔ hariç çevrimi için yaygın oran   # G3k madde 8: ?fpb= fiyat aralığının girildiği para birimi


def _filtre_kipi(request: Request, con, kip: tuple[str, Decimal, bool]) -> tuple[str, Decimal, bool]:
    """G3k madde 8: fiyat aralığı girildiği para biriminde (fpb) yorumlanır; gösterim ₺/€ değişse de anlam korunur
    (₺ ↔ € dönüşümü sabit kurla SQL'de). fpb yoksa, geçersizse, aralık boşsa ya da gösterimle aynıysa gösterim kipi.
    KDV kipi o para biriminin bu ziyaretçideki gösterimiyle aynıdır (TR teslimde ₺ KDV dahil, € KDV hariç)."""
    q = request.query_params
    fpb = (q.get("fpb") or "").upper()
    if fpb not in FIYAT_BIRIMLERI or fpb == kip[0] or not ((q.get("fmin") or "").strip() or (q.get("fmax") or "").strip()):
        return kip
    kur = son_kur(con)
    b = replace(fiyat_baglami(request, aktif_musteri(request, con)), gosterim="try" if fpb == "TRY" else "eur")
    yeni = gosterim_kipi(b, kur.eur_satis if kur else None)
    return yeni if yeni[0] == fpb else kip


def _ayrilmis_idler(request: Request, con) -> tuple[int, ...]:
    """G3j madde 5: stoklu ama tümü açık siparişlerce ayrılmış ürünler (ziyaretçinin kendi bekleyen kart siparişi
    hariç; ürün kartındaki "tümü ayrılmış" ile aynı harita)."""
    ayrilan = ayrilan_haritasi(request, con, mevcut_sepet_id(con, request, aktif_musteri(request, con)))
    kimlikler = [i for i, n in ayrilan.items() if n > 0]
    if not kimlikler:
        return ()
    sonuc: list[int] = []
    for i in range(0, len(kimlikler), 500):
        parca = kimlikler[i:i + 500]
        sonuc += [r[0] for r in con.execute(
            f"SELECT id, stok FROM urun WHERE id IN ({','.join('?' * len(parca))})", parca)
            if r[1] > 0 and musait_adet(r[1], ayrilan[r[0]]) <= 0]
    return tuple(sorted(sonuc))


def _sorgu(request: Request, kategori_id: int | None, arama: str | None,
           kip: tuple[str, Decimal, bool] = ("EUR", Decimal("1"), False),
           ayrilmis_idler: tuple[int, ...] = ()) -> ListeSorgusu:
    q = request.query_params
    gecerli = ARAMA_SIRALARI if arama else SIRALAR
    sira = q.get("sira") or gecerli[0]
    fmin, fmax, _ = _fiyat_araligi(request)
    return ListeSorgusu(
        dil=dil_bul(request),   # G3f: /en aramasında EN ürün adı da eşleşir
        fiyat_carpani=kip[1],
        fiyat_kdv_dahil=kip[2],
        sayfa_boyu=_sayfa_boyu(request),
        kategori_id=kategori_id,
        arama=arama,
        stokta=q.get("stokta") == "1",
        ayrilmis=q.get("ayrilmis") == "1",
        ayrilmis_idler=ayrilmis_idler,
        tedarikli=q.get("tedarikli") == "1",
        fiyatli=q.get("fiyatli") == "1",
        teklifle=q.get("teklifle") == "1",
        markalar=_coklu(request, "marka"),
        tipler=tuple(x for x in _coklu(request, "tip") if tip_gecerli_mi(x)),
        durumlar=tuple(d for d in _coklu(request, "durum") if DURUM_DESENI.fullmatch(d)),
        alt_kategoriler=_kimlikler(request, "kat"),
        fiyat_min=fmin,
        fiyat_max=fmax,
        siralama=sira if sira in gecerli else gecerli[0],
        sayfa=_sayfa(q.get("sayfa")),
    )


def _url(request: Request, *, ekle: tuple[str, str] | None = None, cikar: tuple[str, str] | None = None,
         **degisen) -> str:
    """Geçerli adresin parametreleri (çoklu değerler korunur) üzerinde değişiklik: degisen[ad]=None parametreyi
    kaldırır, değer verilirse ilk geçtiği yerde (yoksa sonda) tek değere ayarlar; ekle/cikar tek (ad, değer) çiftini
    ekler/kaldırır (çoklu fasetlerde tek seçeneği açıp kapatmak için)."""
    ciftler: list[tuple[str, str]] = []
    ayarlanan: set[str] = set()
    fiyatsiz = not _fiyat_girildi(request)
    for k, v in request.query_params.multi_items():
        if (k, v) == cikar or (k == "fpb" and fiyatsiz):   # fix 1 m-5: fiyat yoksa fpb bağlantılara taşınmaz
            continue
        if k in degisen:
            if k not in ayarlanan and degisen[k] is not None:
                ciftler.append((k, str(degisen[k])))
            ayarlanan.add(k)
            continue
        ciftler.append((k, v))
    ciftler += [(k, str(v)) for k, v in degisen.items() if k not in ayarlanan and v is not None]
    if ekle is not None and ekle not in ciftler:
        ciftler.append(ekle)
    return request.url.path + ("?" + urlencode(ciftler) if ciftler else "")


def _cipler(request: Request, s: ListeSorgusu, kategori_adlari: dict[int, str],
            yaklasik=None) -> list[dict]:
    """K22/G3a: uygulanan filtreler; her çip yalnız kendi değerini (ve sayfayı) kaldıran bağlantı taşır.
    etiket verilmişse düz metin; yoksa şablon `tur`/`deger`'den çeviri üretir."""
    _, _, ters = _fiyat_araligi(request)
    cipler = []
    for ad in BAYRAKLAR:
        if getattr(s, ad):
            cipler.append({"tur": ad, "deger": None, "url": _url(request, **{ad: None, "sayfa": None})})
    for tip in s.tipler:
        cipler.append({"tur": "tip", "deger": tip, "url": _url(request, cikar=("tip", tip), sayfa=None)})
    for marka in s.markalar:
        cipler.append({"tur": "marka", "deger": marka, "url": _url(request, cikar=("marka", marka), sayfa=None)})
    for durum in s.durumlar:
        cipler.append({"tur": "durum", "deger": durum, "url": _url(request, cikar=("durum", durum), sayfa=None)})
    for kimlik in s.alt_kategoriler:
        if kimlik in kategori_adlari:
            cipler.append({"tur": "kat", "deger": kategori_adlari[kimlik],
                           "url": _url(request, cikar=("kat", str(kimlik)), sayfa=None)})
    if s.fiyat_min is not None:
        param = "fmax" if ters else "fmin"
        cipler.append({"tur": "fmin", "deger": s.fiyat_min, "url": _url(request, **{param: None, "sayfa": None}),
                       "yaklasik": yaklasik(s.fiyat_min) if yaklasik else None})
    if s.fiyat_max is not None:
        param = "fmin" if ters else "fmax"
        cipler.append({"tur": "fmax", "deger": s.fiyat_max, "url": _url(request, **{param: None, "sayfa": None}),
                       "yaklasik": yaklasik(s.fiyat_max) if yaklasik else None})
    return cipler


def _hizli_cipler(request: Request, s: ListeSorgusu, f: Fasetler) -> list[dict]:
    """G3a madde 6: listenin üstünde tek dokunuşla aç/kapa filtreler. Sayısı 0 (ve seçili değil) olan gösterilmez."""
    sayilar = {("bayrak", "stokta"): next((x.sayi for x in f.stok if x.deger == "stokta"), 0),
               ("bayrak", "fiyatli"): next((x.sayi for x in f.fiyat if x.deger == "fiyatli"), 0)}
    sayilar.update({("durum", x.deger): x.sayi for x in f.durum})
    cipler = []
    for ad, tur, deger in HIZLI_CIPLER:
        if tur == "bayrak":
            secili = getattr(s, deger)
            url = _url(request, **{deger: None if secili else 1, "sayfa": None})
        else:
            secili = deger in s.durumlar
            url = (_url(request, cikar=("durum", deger), sayfa=None) if secili
                   else _url(request, ekle=("durum", deger), sayfa=None))
        sayi = sayilar.get((tur, deger), 0)
        if sayi or secili:
            cipler.append({"ad": ad, "url": url, "secili": secili, "sayi": sayi})
    return cipler


ONEK_EN_AZ = 4   # G3g madde 22: kod öneki rozeti için aranan kodun en az uzunluğu (rakam da içermeli)


def _onek_eslesenler(urunler, birlesik: str) -> dict[int, str]:
    """G3g madde 22: aranan kod bir parça kodunun öneki (tam değil) ise ürün -> tam kod (üretici kodu, yoksa SKU).
    G3k madde 7: kod ürün adında aynen görünüyorsa (adın art arda jetonlarının katlanmış birleşimi onunla başlıyorsa)
    eşleşme addan da gelir: rozet yok."""
    if len(birlesik) < ONEK_EN_AZ or not any(c.isdigit() for c in birlesik):
        return {}
    sonuc: dict[int, str] = {}
    for u in urunler:
        kodlar = [k for k in (u.uretici_kodu, u.sku) if k]
        if any(kod_birlesik(k) == birlesik for k in kodlar):
            continue
        if any(j.startswith(birlesik) for j in ad_kod_jetonlari(u.ad)):
            continue
        tam = next((k for k in kodlar if kod_birlesik(k).startswith(birlesik)), None)
        if tam:
            sonuc[u.id] = tam
    return sonuc


_KELIME = re.compile(r"\w+")


def _tip_gruplari(secenekler) -> tuple[list, list]:
    """G3j madde 9: (üstte gösterilen tipler, "+N tip daha" içindekiler). Seçililer her zaman üstte; sıra fasetteki
    sıra (çok ürünlüden aza, "Diğer" sonda)."""
    secili = {x.deger for x in secenekler if x.secili}
    ust_kume = secili | {x.deger for x in [x for x in secenekler if not x.secili][:max(0, TIP_GORUNEN - len(secili))]}
    return [x for x in secenekler if x.deger in ust_kume], [x for x in secenekler if x.deger not in ust_kume]


def _marka_gruplari(secenekler) -> tuple[list, list[tuple[str, list]]]:
    """G3h madde 7: (üstte gösterilenler, "+N marka daha" içindeki harf grupları). Seçili markalar her zaman üstte,
    sonra çok ürünlüler (MARKA_GORUNEN'e kadar); kalanlar alfabetik ve baş harfe göre gruplu."""
    secili = [x for x in secenekler if x.secili]
    ust = secili + [x for x in secenekler if not x.secili][:max(0, MARKA_GORUNEN - len(secili))]
    gosterilen = {x.deger for x in ust}
    kalan = sorted((x for x in secenekler if x.deger not in gosterilen), key=lambda x: (normalize(x.deger), x.deger))
    gruplar: list[tuple[str, list]] = []
    for x in kalan:
        harf = next((c for c in x.deger if c.isalnum()), "#").upper()
        harf = harf if harf.isalpha() else "#"
        if not gruplar or gruplar[-1][0] != harf:
            gruplar.append((harf, []))
        gruplar[-1][1].append(x)
    return ust, gruplar


GEVSETME_TERIM_UST = 5        # G3h inceleme I-1: gevşetmede en çok 5 anlamlı terim (ilk 5)
GEVSETME_TERIM_EN_KISA = 2    # bundan kısa terim (tek harf) gevşetmeye ve sayıma girmez
NADIR_ORAN = 10               # G3l madde 1: sonuç sayısı en yaygın terimin ≤ 1/10'u olan terim "nadir"


def _gevsetme(request: Request, con, s: ListeSorgusu, q: str):
    """G3h madde 2: çok terimli sorgu (VE) 0 sonuç verdiyse VEYA ile yeniden arar. (sorgu, sonuç, terim bağlantıları)
    ya da gevşetme yoksa None. Terim bağlantısı aynı filtrelerle yalnız o terimi arar; sayı o aramanın sonucudur.
    İnceleme I-1: yalnız en az 2 karakterlik terimler, en çok GEVSETME_TERIM_UST tanesi; terim sayıları yalnız COUNT."""
    ozgun = sorgu_jetonlari(unicodedata.normalize("NFC", q))     # kullanıcının yazımı (büyük/küçük, Türkçe harf)
    tum = arama_terimleri(q)
    hizali = bool(tum) and len(ozgun) == tum[-1].son
    metinler = [" ".join(ozgun[t.bas:t.son] if hizali else t.kelimeler) for t in tum
                if len(" ".join(t.kelimeler)) >= GEVSETME_TERIM_EN_KISA][:GEVSETME_TERIM_UST]
    if len(metinler) < 2:
        return None
    veya = replace(s, arama=" ".join(metinler), veya=True)
    bag = []
    for metin in metinler:
        sayi = urun_sayisi(con, replace(s, arama=metin))
        bag.append({"metin": metin, "sayi": sayi, "url": _url(request, q=metin, sayfa=None) if sayi else None})
    # G3l madde 1: bir terimin sonucu diğerinin ≤ 1/10'u ise yalnız nadir terim(ler)i içerenler; yaygın terimlerin
    # ürünleri "… de göster" bağlantısıyla (?genis=1)
    en_cok = max(b["sayi"] for b in bag)
    nadir = [b["metin"] for b in bag if b["sayi"] and b["sayi"] * NADIR_ORAN <= en_cok]
    yaygin = [b["metin"] for b in bag if b["sayi"] * NADIR_ORAN > en_cok]
    genis = None
    if nadir and yaygin and request.query_params.get("genis") != "1":
        dar = replace(s, arama=" ".join(nadir), veya=len(nadir) > 1)
        sonuc = urun_listele(con, dar)
        if sonuc.toplam:
            ek = urun_sayisi(con, veya) - sonuc.toplam
            genis = {"terimler": ", ".join(f"“{m}”" for m in yaygin), "sayi": ek, "url": _url(request, genis=1, sayfa=None)} if ek > 0 else None
            return dar, sonuc, bag, genis
    sonuc = urun_listele(con, veya)
    if not sonuc.toplam:
        return None
    return veya, sonuc, bag, genis


KOD_SERI_UZUNLUK = 4    # G3j madde 6: "Aynı seri" öneki (ilk kod jetonunun ilk 4 karakteri: 6ES7, A06B, 1FK7)


def _kod_yok(request: Request, con, s: ListeSorgusu, q: str) -> dict | None:
    """G3j madde 6: sorguda harf + rakam karışık bir kod jetonu varsa ve sonuç yoksa gevşetme (VEYA) yapılmaz (sayı
    jetonları alakasız ürün getirir); yerine "koduyla ürün yok", ilk kod jetonunun önekiyle "Aynı seri" bağlantısı
    (aynı filtrelerle, sayılı; 0 ise yok) ve parça kodu dolu teklif bağlantısı. Kod jetonu yoksa None."""
    jeton = next((w for w in sorgu_jetonlari(unicodedata.normalize("NFC", q)) if karisik_kod(kod_birlesik(w))), None)
    if jeton is None:
        return None
    # inceleme M-5: sonuçsuzluk filtrelerden geliyorsa (filtresiz aynı sorgu sonuçlu) "koduyla ürün yok" denmez;
    # filtreleri kaldırma bağlantısı (yalnız arama metni) ve filtresiz sonuç sayısı
    filtresiz = urun_sayisi(con, ListeSorgusu(arama=s.arama, dil=s.dil))
    if filtresiz:
        return {"q": q, "filtresiz": filtresiz, "temizle_url": request.url.path + "?" + urlencode({"q": q})}
    seri = kod_birlesik(jeton)[:KOD_SERI_UZUNLUK].upper()
    sayi = urun_sayisi(con, replace(s, arama=seri, veya=False))
    # G3l madde 3: en uzun ortak katlanmış önekli en çok 5 ürün (tek kod sorgusunda tüm sorgu: "6ES7 214" -> 6es7214)
    yakin = yakin_kodlar(con, kod_birlesik(q) if kod_sorgusu_mu(q) else kod_birlesik(jeton))
    return {"q": q, "seri": seri, "sayi": sayi, "seri_url": _url(request, q=seri, sayfa=None) if sayi else None,
            "yakin": yakin}


def _agac_baglantisi(request: Request, dil: str, arama_sayfasi: bool) -> tuple[str, str]:
    """G3h madde 4: süzülmüş ağaçta kategori bağlantısı geçerli arama/filtreleri taşır (sayfa ve kategori faseti hariç).
    Arama sayfasında aynı arama kategori fasetiyle (?kat=), listelerde kategori sayfasına."""
    kalan = [(k, v) for k, v in request.query_params.multi_items()
             if k not in ("kat", "sayfa") and not (not arama_sayfasi and k == "sira" and v == "alaka")]
    if arama_sayfasi:
        return f"/{dil}/ara?" + urlencode([*kalan, ("kat", "")]), ""
    return f"/{dil}/kategori/", ("?" + urlencode(kalan) if kalan else "")


def _dugum_bul(dugumler: list[KategoriDugum], kategori_id: int) -> KategoriDugum | None:
    for d in dugumler:
        if d.kategori.id == kategori_id:
            return d
        bulunan = _dugum_bul(d.cocuklar, kategori_id)
        if bulunan is not None:
            return bulunan
    return None


def _kategori_adlari(dugumler: list[KategoriDugum]) -> dict[int, str]:
    adlar: dict[int, str] = {}
    yigin = list(dugumler)
    while yigin:
        d = yigin.pop()
        adlar[d.kategori.id] = d.kategori.ad
        yigin.extend(d.cocuklar)
    return adlar


def _agac(request: Request, con) -> list[KategoriDugum]:
    return kategori_agaci_onbellekli(con, request.app.state.katalog_onbellek)


def _fiyat_girildi(request: Request) -> bool:
    """Dolu fmin / fmax var mı (G3m inceleme m2: yinelenen parametrelerin TÜM değerlerine bakılır)."""
    q = request.query_params
    return any(v.strip() for ad in ("fmin", "fmax") for v in q.getlist(ad))


def _gizli_parametreler(request: Request, haric: tuple[str, ...]) -> list[tuple[str, str]]:
    haric = haric if _fiyat_girildi(request) else (*haric, "fpb")      # fix 1 m-5
    return [(k, v) for k, v in request.query_params.multi_items() if k not in haric][:60]


def _bos_fiyat_temiz_url(request: Request) -> str | None:
    """G3m madde 19: JS'siz filtre formu boş fmin= / fmax= ve fiyat girilmemişken fpb gönderir; bu parametreler atılmış
    adres (yönlendirme gerekmiyorsa None). Diğer parametrelerin sırası ve çoklu değerleri korunur; canonical/robots
    kuralları değişmez (temiz adres zaten filtre adresidir)."""
    fiyatsiz = not _fiyat_girildi(request)
    ciftler = request.query_params.multi_items()
    kalan = [(k, v) for k, v in ciftler
             if not ((k in ("fmin", "fmax") and not v.strip()) or (k == "fpb" and fiyatsiz))]
    if len(kalan) == len(ciftler):
        return None
    return request.url.path + ("?" + urlencode(kalan) if kalan else "")


def _liste(request: Request, con, *, kategori: Kategori | None = None, q: str = "", tum: bool = False):
    """kategori: kategori sayfası; q: arama; tum: /urunler (tüm aktif ürünler)."""
    temiz = _bos_fiyat_temiz_url(request)
    if temiz is not None:
        return RedirectResponse(temiz, status_code=302)
    arama_sayfasi = kategori is None and not tum
    kip = _fiyat_kipi(request, con)
    filtre_kip = _filtre_kipi(request, con, kip)      # G3k madde 8
    s = _sorgu(request, kategori.id if kategori else None, q or None, filtre_kip, _ayrilmis_idler(request, con))
    sonuc = urun_listele(con, s)
    kod_yok = _kod_yok(request, con, s, q) if q and not sonuc.toplam else None
    gevset = _gevsetme(request, con, s, q) if q and not sonuc.toplam and kod_yok is None else None
    gevset_genis = None
    if gevset is not None:
        s, sonuc, gevset, gevset_genis = gevset
    dil = dil_bul(request)
    # G3f: sayfadaki ürünlerin EN çevirileri tek sorguda (şablon urun_ad bu önbellekten okur)
    cevirmeler = urun_cevirileri(request, con, [u.id for u in sonuc.urunler], dil)
    # G3e madde 8: aralık dışı sayfa 404 değil, en yakın geçerli sayfaya 302 (sayfa 1 parametresiz; canonical bozulmaz)
    try:
        istenen = int(request.query_params["sayfa"]) if "sayfa" in request.query_params else None
    except ValueError:
        istenen = None
    if istenen is not None and (istenen < 1 or istenen > sonuc.sayfa_sayisi):
        hedef = sonuc.sayfa_sayisi if istenen > 1 else 1
        return RedirectResponse(_url(request, sayfa=hedef if hedef > 1 else None), status_code=302)
    yol = kategori_yolu(con, kategori.id) if kategori else []
    agac = _agac(request, con)
    dugum = _dugum_bul(agac, kategori.id) if kategori else None
    faset_kategorileri = [d.kategori for d in (dugum.cocuklar if dugum else ([] if kategori else agac))]
    fasetler = faset_sayilari(con, s, faset_kategorileri)
    if q and sonuc.toplam == 1:
        # G3n madde 13: tek sonuçlu aramada tek seçenekli (seçili olmayan) faset grupları gizlenir
        fasetler = replace(fasetler, **{ad: () for ad in ("marka", "tip", "durum", "stok", "fiyat", "kategori")
                                        if len(getattr(fasetler, ad)) == 1 and not getattr(fasetler, ad)[0].secili})
    kategori_adlari = _kategori_adlari(agac)
    ham = request.query_params
    yaklasik = None
    if filtre_kip[0] != kip[0]:          # G3k madde 8: çipte girilen birim + gösterim biriminde yaklaşık karşılık
        # fix 1 I-2: karşılık gösterimin KDV kipinde (₺ KDV dahil ↔ € KDV hariç); ürün başına oran değiştiği için
        # yaygın oran (%20) ile yaklaşık; çipte kipi yazılır
        kdv = Decimal("1") + YAKLASIK_KDV / 100
        oran = (kip[1] * (kdv if kip[2] else 1)) / (filtre_kip[1] * (kdv if filtre_kip[2] else 1))
        yaklasik = lambda x: (x * oran).quantize(Decimal("0.01"))   # noqa: E731
    cipler = _cipler(request, s, kategori_adlari, yaklasik)
    marka_ust, marka_harfler = _marka_gruplari(fasetler.marka)
    tip_ust, tip_daha = _tip_gruplari(fasetler.tip)
    # G3h madde 4: arama ya da filtre etkinken ağaç sonuç kümesinin sayılarını gösterir (0 olan gizlenir)
    if q or cipler:
        agac_gorunen = suzulmus_agac(agac, kategori_sayilari(con, s))
        agac_onek, agac_ek = _agac_baglantisi(request, dil, arama_sayfasi)
    else:
        agac_gorunen, agac_onek, agac_ek = agac, f"/{dil}/kategori/", ""
    bas, son = max(1, sonuc.sayfa - 2), min(sonuc.sayfa_sayisi, sonuc.sayfa + 2)
    t = request.app.state.ceviri
    ayarlar = request.app.state.ayarlar
    kat = request.app.state.kategori_ceviri       # G3c madde 23: EN başlık/meta/JSON-LD'de çevrilmiş kategori adı

    def km(ad: str | None) -> str:
        return kat.metin(ad, dil)
    giris = None
    if arama_sayfasi:
        seo_ = seo_baglami(request, aciklama=seo.sablon_metni(dil, "arama_aciklama"))  # /ara işlemsel: noindex
    elif tum:
        seo_ = seo_baglami(request, dil=dil, sayfa=sonuc.sayfa, aciklama=t.t(dil, "katalog.tum_urunler_aciklama"))
    else:
        adet = dugum.urun_sayisi if dugum else sonuc.toplam   # filtresiz (alt kategoriler dahil) aktif ürün sayısı
        # g3c M-3: EN'de ad (ya da kök) çevrilmemişse Türkçe ad İngilizce cümleye girmesin: giriş paragrafı basılmaz
        if kat.cevrilmis_mi(kategori.ad, dil) and (not yol or kat.cevrilmis_mi(yol[0].ad, dil)):
            giris = seo.kategori_girisi(dil, km(kategori.ad), km(yol[0].ad) if yol else None, adet)
        ld = seo.liste_json_ld(
            site_kok=ayarlar.site_kok, dil=dil, ana_sayfa_adi=t.t(dil, "genel.ana_sayfa"),
            yol=[(k.id, km(k.ad)) for k in yol],
            urunler=[replace(u, ad=cevirmeler[u.id].ad) if u.id in cevirmeler else u for u in sonuc.urunler])
        seo_ = seo_baglami(
            request, dil=dil, sayfa=sonuc.sayfa,
            baslik=seo.kategori_basligi(dil, km(kategori.ad), adet, sonuc.sayfa, kok=km(yol[0].ad) if yol else None),
            aciklama=seo.kategori_aciklamasi(
                dil, km(kategori.ad), adet, sonuc.sayfa, markalar=[x.deger for x in fasetler.marka],
                durumlar=gercek_durumlar(con, kategori.id)),   # I-6: örnek durumlar meta'ya girmez
            json_ld=[seo.json_ld_metni(x) for x in ld])
    birlesik = kod_birlesik(q) if q else ""
    durum_adlari = {x.deger: (t.t(dil, f"durum.{x.deger}") if t.var(f"durum.{x.deger}") else x.deger)
                    for x in fasetler.durum}
    durum_adlari.update({d: (t.t(dil, f"durum.{d}") if t.var(f"durum.{d}") else d) for d in s.durumlar})
    return sablon(request, "liste.html", {
        "seo": seo_,
        "kategori_giris": giris,
        "kategori": kategori,
        "yol": yol,
        "acik": {k.id for k in yol},
        "agac": agac,
        "agac_gorunen": agac_gorunen,
        "agac_onek": agac_onek,
        "agac_ek": agac_ek,
        "gevset": gevset,
        "gevset_genis": gevset_genis,
        "kod_yok": kod_yok,
        "alt_kategoriler": dugum.cocuklar if dugum else [],
        "sonuc": sonuc,
        "sorgu": s,
        "q": q,
        "arama_q": q,
        "arama_sayfasi": arama_sayfasi,
        "tum_urunler": tum,
        "aktif_kok_id": yol[0].id if yol else None,
        # G3n madde 8: ters aralık yer değiştirildiyse alanlar da değiştirilmiş değerlerle dolar
        "form": ({"fmin": (ham.get("fmax") or "")[:20], "fmax": (ham.get("fmin") or "")[:20]}
                 if _fiyat_araligi(request)[2] else {"fmin": (ham.get("fmin") or "")[:20],
                                                      "fmax": (ham.get("fmax") or "")[:20]}),
        "fiyat_para": filtre_kip[0], "fiyat_kdv_dahil": filtre_kip[2], "gosterim_para": kip[0], "gosterim_kdv_dahil": kip[2],
        "fiyat_ters": _fiyat_araligi(request)[2],
        "sayfa_boylari": SAYFA_BOYLARI,
        "liste_yolu": request.url.path,
        "siralar": ARAMA_SIRALARI if q else SIRALAR,
        "fasetler": fasetler,
        "marka_gorunen": MARKA_GORUNEN,
        "marka_ust": marka_ust,
        "marka_harfler": marka_harfler,
        "marka_kalan_sayi": sum(len(g) for _, g in marka_harfler),
        "tip_ust": tip_ust,
        "tip_daha": tip_daha,
        "tip_adlari": {x.deger: tip_adi(x.deger, dil) for x in fasetler.tip} | {x: tip_adi(x, dil) for x in s.tipler},
        "fiyat_gecersiz": _gecersiz_tutarlar(request),
        "durum_adlari": durum_adlari,
        "kategori_adlari": kategori_adlari,
        "hizli_cipler": _hizli_cipler(request, s, fasetler),
        "tam_eslesenler": {u.id for u in sonuc.urunler if birlesik and birlesik in u.kod_birlesik.split()},
        "onek_eslesenler": _onek_eslesenler(sonuc.urunler, birlesik),
        "siralama_gizli": _gizli_parametreler(request, ("sira", "sayfa", "adet")),
        "sayfa_baglantilari": [(n, _url(request, sayfa=n)) for n in range(bas, son + 1)] if sonuc.sayfa_sayisi > 1 else [],
        "onceki_url": _url(request, sayfa=sonuc.sayfa - 1) if sonuc.sayfa > 1 else None,
        "sonraki_url": _url(request, sayfa=sonuc.sayfa + 1) if sonuc.sayfa < sonuc.sayfa_sayisi else None,
        "son_url": _url(request, sayfa=sonuc.sayfa_sayisi) if sonuc.sayfa < sonuc.sayfa_sayisi else None,
        "temizle_url": request.url.path + ("?" + urlencode({"q": q}) if q else ""),
        "teklif_kod_url": f"/{dil}/teklif?" + urlencode({"kod": q}) if q else f"/{dil}/teklif",
        "filtre_var": bool(cipler),
        "cipler": cipler,
    })


@router.get("/{dil:dil}/")
def ana_sayfa(request: Request, dil: str, con=Depends(db_bagimliligi)):
    kokler = [d for d in _agac(request, con) if d.urun_sayisi]   # G3e madde 19: boş kategori gösterilmez
    ayrilan = ayrilan_haritasi(request, con, mevcut_sepet_id(con, request, aktif_musteri(request, con)))
    stoktakiler = [u for u in one_cikanlar(con, ONE_CIKAN_HAVUZ)
                   if musait_adet(u.stok, ayrilan.get(u.id, 0)) > 0 and not u.teklif_zorunlu][:ONE_CIKAN_ADET]
    ayarlar = request.app.state.ayarlar
    ld = seo.ana_sayfa_json_ld(site_kok=ayarlar.site_kok, dil=dil, telefon=ayarlar.telefon)
    return sablon(request, "ana.html", {
        "seo": seo_baglami(request, dil=dil, baslik=seo.sablon_metni(dil, "ana_baslik"),
                           aciklama=seo.sablon_metni(dil, "ana_aciklama"), json_ld=[seo.json_ld_metni(x) for x in ld]),
        "kokler": kokler,
        "one_cikanlar": stoktakiler,
        "toplam_urun": sum(d.urun_sayisi for d in kokler),
    })


@router.get("/{dil:dil}/kategori/{kategori_id:int}")
def kategori_sayfasi(request: Request, dil: str, kategori_id: int, con=Depends(db_bagimliligi)):
    kategori = kategori_getir(con, kategori_id) if kategori_id <= EN_BUYUK_ID else None
    if kategori is None:
        raise HTTPException(status_code=404)
    return _liste(request, con, kategori=kategori)


@router.get("/{dil:dil}/urunler")
def tum_urunler(request: Request, dil: str, con=Depends(db_bagimliligi)):
    """G3a madde 8: tüm aktif ürünler (fasetli, sonuç sayısıyla)."""
    return _liste(request, con, tum=True)


@router.get("/{dil:dil}/ara")
def arama_sayfasi(request: Request, dil: str, con=Depends(db_bagimliligi)):
    q = _arama_metni(request)
    if not q:   # G3a madde 8: boş arama tüm ürünlere (filtreler korunur; alaka sırası aramaya özgü)
        kalan = [(k, v) for k, v in request.query_params.multi_items()
                 if k not in ("q", "sayfa") and not (k == "sira" and v == "alaka")]
        return RedirectResponse(f"/{dil}/urunler" + ("?" + urlencode(kalan) if kalan else ""), status_code=303)
    return _liste(request, con, q=q)


@router.get("/{dil:dil}/urun/{urun_id:int}")
def urun_sayfasi(request: Request, dil: str, urun_id: int, con=Depends(db_bagimliligi)):
    urun = urun_getir(con, urun_id) if urun_id <= EN_BUYUK_ID else None
    if urun is None or not urun.aktif:
        raise HTTPException(status_code=404)
    yol = kategori_yolu(con, urun.kategori_id) if urun.kategori_id else []
    ayarlar = request.app.state.ayarlar
    kayit = aciklama_getir(con, urun.id, dil)
    teknik = teknik_getir(con, urun.id)
    # G3i madde 14: LLM taslağı, ürünün teknik verisi (özellik) ve kaynak açıklaması (bölüm) yoksa bilgi taşımayan şablon
    # metindir: sayfada, meta'da ve JSON-LD'de kullanılmaz (urun_aciklama satırı silinmez); yerine olgusal blok
    zayif_taslak = kayit is not None and kayit.taslak and teknik is None
    # G3f: geçerli EN çeviri varsa başlık/meta/JSON-LD adı ve teknik satırlar EN (görüntülenen `urun` değişmez)
    cev = urun_cevirisi(request, con, urun.id, dil)
    # G3k madde 21: taslaktaki her sayı+birim ürün adında / kodunda / teknik verisinde geçmeli; paragraf küçük harfle
    # (kesik sözcükle) başlamamalı. Aksi halde gösterilmez (veri silinmez), yerine olgusal blok
    if kayit is not None and kayit.taslak and not zayif_taslak:
        teknik_metin = [x for cift in ((teknik.ozellikler + teknik.bolumler) if teknik else ()) for x in cift]
        teknik_metin += [x for cift in (cev.teknik or ()) for x in cift] if cev is not None else []
        if not taslak_gosterilir(kayit.metin, [urun.ad, urun.sku, urun.uretici_kodu, cev.ad if cev else None],
                                 teknik_metin):
            zayif_taslak = True
    if zayif_taslak:
        kayit = None
    teknik_en = cev.teknik if cev is not None and teknik is not None and teknik.ozellikler else None
    adli = replace(urun, ad=cev.ad) if cev is not None else urun
    teknik_ld = replace(teknik, ozellikler=teknik_en) if teknik_en else teknik
    kategori_adi = request.app.state.kategori_ceviri.metin(yol[-1].ad, dil) if yol else None
    metin = kayit.metin if kayit else seo.urun_aciklama_sablonu(dil, adli.ad, urun.sku, urun.uretici_kodu, kategori_adi)
    durum = seo.gercek_durum(urun)
    # kayıtlı (kaynak / LLM taslağı) açıklama varsa meta odur (G2); yoksa yapılandırılmış meta (G3b, 120–155 kr)
    meta = seo.meta_aciklama(kayit.metin) if kayit else seo.urun_meta(
        dil=dil, ad=adli.ad, parca_no=urun.sku, uretici_kodu=urun.uretici_kodu, kategori=kategori_adi,
        durum_kodu=durum, stokta=urun.stok > 0, teklif=urun.teklif_zorunlu)
    marka = marka_cikar(urun.ad)
    gorsel = gorsel_adresi(urun, ayarlar.gorsel_kok, "b")
    kur = son_kur(con)
    gosterim = birim_fiyat_gosterimi(urun.net_fiyat_eur, urun.kdv_orani, Baglam(MusteriTipi.BIREYSEL, "TR"),
                                     kur.eur_satis if kur is not None else None)  # anonim TR ziyaretçi (sayfadakiyle aynı hesap)
    ld = seo.urun_json_ld(site_kok=ayarlar.site_kok, dil=dil, urun=adli, marka=marka, aciklama=metin,
                          gorsel=gorsel, kategori=kategori_adi, gosterim=gosterim, teknik=teknik_ld)
    teknik_basliklari = {normalize(request.app.state.ceviri.t(d, "urun.teknik_baslik")) for d in ("tr", "en")}
    return sablon(request, "urun.html", {
        "urun": urun, "yol": yol, "aktif_kok_id": yol[0].id if yol else None, "aciklama": kayit, "teknik": teknik,
        "sayfa_urun_id": urun.id,       # G3l madde 17: bu ürünün bildirimi yalnız çapada
        "aciklama_bilinen": {"marka": marka} if zayif_taslak else None,
        "ayni_parca_nolu": ayni_parca_nolu(con, urun),          # G3j madde 17
        "teknik_en": teknik_en, "teknik_ceviri_taslak": cev is not None and cev.taslak,
        # G3n madde 12: parça no'yu tekrarlayan "Type"/"Tip" satırı gösterilmez (her dilde kendi etiketiyle süzülür)
        "teknik_satirlari": [(e, d) for e, d in (teknik_en or (teknik.ozellikler if teknik else ()))
                             if not tip_parca_no_ayni(e, d, urun.uretici_kodu or urun.sku)],
        # Fix 1 (m-2): summary ile aynı bölüm başlığı (büyük harf "TEKNİK ÖZELLİKLER" dahil) basılmaz
        "teknik_bolumleri": [("" if normalize(b or "") in teknik_basliklari else b, m)
                             for b, m in (teknik.bolumler if teknik else ())],
        "seo": seo_baglami(request, dil=dil, baslik=seo.urun_basligi(dil, adli.ad, urun.sku, marka, durum,
                                                                     urun.uretici_kodu),
                           aciklama=meta, og_tur="product", gorsel=gorsel,
                           json_ld=[seo.json_ld_metni(ld)]),
    })
