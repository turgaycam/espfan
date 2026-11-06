"""SEO tek noktası: başlık/meta şablonları, canonical + hreflang, JSON-LD, robots.txt, sitemap XML.

Saf fonksiyonlar (veritabanı yok). Başlık ve açıklama kalıpları (SABLONLAR) ve ürün durumu adları
(DURUM_ADLARI) burada tek yerde durur. G3b: kalıplar anahtar kelime araştırmasının önerileriyle
(seo/oneriler.md, kaliplar.md) uyumlu:
  ürün      = "{ad} {üretici kodu} | {parça no} | {marka} {durum} | Ceylan Robot"   (≤ 60 kr hedef)
              sığmazsa sırayla: marka atılır (adda zaten varsa hiç yazılmaz) -> durum kısalır -> durum atılır ->
              ad kısalır (en az 14 kr); parça no ve üretici kodu asla kesilmez
  ürün meta = "{ad} {üretici kodu}, parça no {sku}: {durum}. {stok}. Kategori: … ." (+ sevkiyat/teklif cümleleri), 120–155 kr
  kategori  = "{kategori}: {kök} Yedek Parçaları | Ceylan Robot" (kökte "{kategori}: Yedek Parça ve Ürünler ({n})")
  kat. meta = "{kategori} grubunda {n} ürün; markalar: (en çok 3, gerçek veriden); durum: … . …"
Kurallar: rakip marka/satıcı adı ve "yetkili satıcı" ifadesi hiçbir şablonda kullanılmaz; durum yalnız gerçek
(örnek olmayan) veriden yazılır.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from urllib.parse import urlencode
from xml.sax.saxutils import escape

from markupsafe import Markup

SITE_ADI = "Ceylan Robot"
BASLIK_SINIRI = 60       # hedef (bazı durumlarda parça no yüzünden aşılabilir)
ACIKLAMA_SINIRI = 155
LOGO_YOLU = "/statik/marka/ceylan-robot-logo.png"
BAL_KUPU_ONEKI = "/_iz/"
BAL_KUPU_YOLU = BAL_KUPU_ONEKI + "k7f3q9x2m4b8"   # rastgele sabit; robots.txt'de Disallow, tabanda gizli bağlantı
SITEMAP_URL_SINIRI = 5000
DILLER = ("tr", "en")
OG_YEREL = {"tr": "tr_TR", "en": "en_US"}

SABLONLAR: dict[str, dict[str, str]] = {
    "tr": {
        "urun_baslik": "{ad} | {parca_no} | {marka_durum} – Ceylan Robot",
        "urun_baslik_yalin": "{ad} | {parca_no} – Ceylan Robot",
        "urun_aciklama": "{ad}, parça no {parca_no}{uretici}{kategori}. Test edilmiş yedek parça ve robotlar; teklif ve ihracat desteği: Ceylan Robot.",
        "kategori_baslik_alt": ["{kategori}: {kok} Yedek Parçaları{sayfa} | Ceylan Robot",
                                "{kategori} Yedek Parçaları{sayfa} | Ceylan Robot", "{kategori}{sayfa} | Ceylan Robot"],
        "kategori_baslik_kok": ["{kategori}: Yedek Parça ve Ürünler ({adet}){sayfa} | Ceylan Robot",
                                "{kategori} Yedek Parça ve Ürünler{sayfa} | Ceylan Robot", "{kategori}{sayfa} | Ceylan Robot"],
        "sayfa_ek": " – Sayfa {sayfa}",
        "kategori_meta": "{kategori} grubunda {adet} ürün{markalar}{durumlar}.",
        "kategori_meta_marka": "; markalar: {liste}",
        "kategori_meta_durum": "; durum: {liste}",
        "kategori_meta_ek": ["Stoktaki ürünleri parça numarasıyla inceleyin, teklif isteyin.",
                             "Türkiye'ye ve yurt dışına teslimat."],
        "urun_meta": "{ad}{uretici}, parça no {parca_no}: {durum}.",
        "urun_meta_ek": ["{stok}.", "Kategori: {kategori}.", "Türkiye içi sevkiyat, yurt dışına ihracat.",
                         "Parça numarasıyla teklif isteyin."],
        "stok_var": "Stokta", "stok_yok": "Sipariş üzerine", "stok_teklif": "Fiyat ve teslim teklifle",
        "durum_yok": "durum belirtilmemiş",
        "kategori_giris": "{kategori}{kok} kategorisinde {adet} ürün listeleniyor. Ürünlerimiz test edilmiştir; teklif isteyebilir, Türkiye'ye ve yurt dışına (ihracat) sipariş verebilirsiniz.",
        "kategori_giris_kok": " ({kok})",
        "ana_baslik": "Ceylan Robot – Test edilmiş robot ve otomasyon parçaları",
        "ana_aciklama": "Test edilmiş 2. el robotlar, kontrol üniteleri ve yedek parçalar; Türkiye'ye ve yurt dışına teslimat. Parça numarasıyla arayın, teklif alın.",
        "varsayilan_aciklama": "Ceylan Robot: test edilmiş 2. el robotlar, kontrol üniteleri ve yedek parçalar; ihracat ve teklif desteği.",
        "yasal_aciklama": "{sayfa} – Ceylan Robot satış koşulları ve bilgilendirme metinleri.",
        "uretici_ek": ", üretici kodu {kod}",
        "kategori_ek": ", {kategori}",
        "arama_aciklama": "Ceylan Robot katalogunda parça numarası, üretici kodu veya ürün adıyla arama.",
    },
    "en": {
        "urun_baslik": "{ad} | {parca_no} | {marka_durum} – Ceylan Robot",
        "urun_baslik_yalin": "{ad} | {parca_no} – Ceylan Robot",
        "urun_aciklama": "{ad}, part no. {parca_no}{uretici}{kategori}. Tested spare parts and robots; quotes and export support from Ceylan Robot.",
        "kategori_baslik_alt": ["{kategori} | {kok} Spare Parts{sayfa} | Ceylan Robot",
                                "{kategori} Spare Parts{sayfa} | Ceylan Robot", "{kategori}{sayfa} | Ceylan Robot"],
        "kategori_baslik_kok": ["{kategori}: Spare Parts and Products ({adet}){sayfa} | Ceylan Robot",
                                "{kategori} Spare Parts and Products{sayfa} | Ceylan Robot", "{kategori}{sayfa} | Ceylan Robot"],
        "sayfa_ek": " – Page {sayfa}",
        "kategori_meta": "{adet} products in {kategori}{markalar}{durumlar}.",
        "kategori_meta_marka": "; brands: {liste}",
        "kategori_meta_durum": "; condition: {liste}",
        "kategori_meta_ek": ["Browse stock by part number and request a quote.", "Delivery in Turkey and abroad."],
        "urun_meta": "{ad}{uretici}, part no. {parca_no}: {durum}.",
        "urun_meta_ek": ["{stok}.", "Category: {kategori}.", "Ships from Turkey, export worldwide.",
                         "Request a quote by part number."],
        "stok_var": "In stock", "stok_yok": "On request", "stok_teklif": "Price and lead time on quotation",
        "durum_yok": "condition not specified",
        "kategori_giris": "{adet} products are listed in {kategori}{kok}. Our products are tested; you can request a quote and order in Turkey or abroad (export).",
        "kategori_giris_kok": " ({kok})",
        "ana_baslik": "Ceylan Robot – Tested robots and automation parts",
        "ana_aciklama": "Tested used robots, controllers and spare parts, delivered in Turkey and abroad. Search by part number and request a quote.",
        "varsayilan_aciklama": "Ceylan Robot: tested used robots, controllers and spare parts; export and quote support.",
        "yasal_aciklama": "{sayfa} – Ceylan Robot terms of sale and information notices.",
        "uretici_ek": ", manufacturer code {kod}",
        "kategori_ek": ", {kategori}",
        "arama_aciklama": "Search the Ceylan Robot catalogue by part number, manufacturer code or product name.",
    },
}

# Başlıkta kullanılan durum adı (oneriler.md §1), kısaltılmış biçimi, meta cümlesindeki küçük harfli biçimi ve
# schema.org itemCondition (durum_kodu'ndan). "Test edilmiş 2. el" schema.org'da UsedCondition'dır; RefurbishedCondition
# yalnız yenilenmiş (profesyonel olarak onarılmış) ürün içindir.
DURUM_ADLARI = {
    "tr": {"yeni": "Sıfır", "ikinci_el_test_edildi": "2. El, Test Edilmiş", "yenilenmis": "Yenilenmiş",
           "ikinci_el": "2. El", "ikinci_el_oldugu_gibi": "2. El, Olduğu Gibi"},
    "en": {"yeni": "New", "ikinci_el_test_edildi": "Used, Tested", "yenilenmis": "Refurbished",
           "ikinci_el": "Used", "ikinci_el_oldugu_gibi": "Used, As Is"},
}
DURUM_KISA = {
    "tr": {"ikinci_el_test_edildi": "2. El", "ikinci_el_oldugu_gibi": "2. El"},
    "en": {"ikinci_el_test_edildi": "Used", "ikinci_el_oldugu_gibi": "Used"},
}
DURUM_META = {
    "tr": {"yeni": "sıfır", "ikinci_el_test_edildi": "2. el test edilmiş", "yenilenmis": "yenilenmiş",
           "ikinci_el": "2. el", "ikinci_el_oldugu_gibi": "2. el, olduğu gibi"},
    "en": {"yeni": "new", "ikinci_el_test_edildi": "used, tested", "yenilenmis": "refurbished",
           "ikinci_el": "used", "ikinci_el_oldugu_gibi": "used, as is"},
}
DURUM_SEMA = {
    "yeni": "https://schema.org/NewCondition",
    "ikinci_el_test_edildi": "https://schema.org/UsedCondition",
    "yenilenmis": "https://schema.org/RefurbishedCondition",
    "ikinci_el": "https://schema.org/UsedCondition",
    "ikinci_el_oldugu_gibi": "https://schema.org/UsedCondition",
}
EN_COK_OZELLIK_LD = 20     # JSON-LD additionalProperty üst sınırı
EN_COK_MARKA_META = 3
AD_EN_AZ = 14

# robots.txt ve X-Robots-Tag için işlemsel (indekslenmemesi gereken) yollar.
ISLEMSEL_YOL = re.compile(
    r"^/(?:(?:tr|en)/)?(?:sepet|odeme|hesabim|giris|kayit|cikis|ara|siparis|teklif/tamam|karsilastir(?:\.csv)?)(?:/|$)"
    r"|^/(?:yonetim|geri-bildirim|tercih|cerez-onay)(?:/|$)"
)
ROBOTS_YASAK = (
    "/sepet", "/*/sepet", "/*/odeme", "/*/hesabim", "/*/giris", "/*/kayit", "/yonetim", "/*/ara?", "/*/karsilastir",
    "/*?*stokta=", "/*?*fmin=", "/*?*fmax=", "/*?*fpb=", "/*?*sira=",
    "/*?*tedarikli=", "/*?*fiyatli=", "/*?*teklifle=", "/*?*marka=", "/*?*durum=", "/*?*kat=", "/*?*adet=", "/*?*tip=", "/*?*genis=",
    BAL_KUPU_ONEKI,
)
# Sayfalama kasıtlı olarak açık bırakılır (/*?*sayfa= yasaklanmaz).


def islemsel_mi(yol: str) -> bool:
    return bool(ISLEMSEL_YOL.match(yol))


def robots_meta(yayin_modu: str, yol: str) -> str | None:
    """<meta name=robots> değeri: demoda her sayfa, üretimde yalnız işlemsel sayfalar kapalı."""
    return "noindex,nofollow" if yayin_modu == "demo" or islemsel_mi(yol) else None


def robots_basligi(yayin_modu: str, yol: str) -> str | None:
    """X-Robots-Tag değeri (aynı kural)."""
    return "noindex, nofollow" if yayin_modu == "demo" or islemsel_mi(yol) else None


# ---------- metin yardımcıları ----------

def _bosluk(metin: str) -> str:
    return " ".join((metin or "").split())


def kisalt(metin: str, sinir: int) -> str:
    """Boşlukları sadeleştirir; sınırı aşarsa kelime sınırında keser ve '…' ekler."""
    metin = _bosluk(metin)
    if len(metin) <= sinir:
        return metin
    kesik = metin[: sinir - 1].rstrip()
    son_bosluk = kesik.rfind(" ")
    if son_bosluk >= sinir * 0.6:
        kesik = kesik[:son_bosluk]
    return kesik.rstrip(" ,;:-–|") + "…"


def mutlak(site_kok: str, yol: str) -> str:
    return yol if yol.startswith(("http://", "https://")) else site_kok.rstrip("/") + yol


def _sablon(dil: str, anahtar: str) -> str:
    return SABLONLAR.get(dil, SABLONLAR["tr"])[anahtar]


def sablon_metni(dil: str, anahtar: str, **degerler: object) -> str:
    return _sablon(dil, anahtar).format(**degerler)


# ---------- başlık / açıklama ----------

def _ayracsiz(metin: str | None) -> str:
    return re.sub(r"[\W_]+", "", (metin or "").casefold())


def _uretici_eki(ad: str, uretici_kodu: str | None) -> str:
    """Üretici kodu adda (ayraçsız karşılaştırmayla) zaten yoksa ' <kod>'."""
    if not uretici_kodu or _ayracsiz(uretici_kodu) in _ayracsiz(ad):
        return ""
    return " " + _bosluk(uretici_kodu)


def _marka_adda(ad: str, marka: str | None) -> bool:
    return bool(marka) and _ayracsiz(marka) in _ayracsiz(ad)


def urun_basligi(dil: str, ad: str, parca_no: str, marka: str | None, durum_kodu: str,
                 uretici_kodu: str | None = None) -> str:
    """'{ad}{ üretici kodu} | {parça no} | {marka durum} | Ceylan Robot' (≤ BASLIK_SINIRI hedef).
    Kesme sırası: marka -> durum kısalır -> durum atılır -> ad kısalır (en az AD_EN_AZ kr). Parça no ve üretici
    kodu kesilmez; ikisi birlikte sığmazsa hedef aşılır (benzersizlik korunur)."""
    adlar = DURUM_ADLARI.get(dil, DURUM_ADLARI["tr"])
    durum = adlar.get(durum_kodu, "")
    durum_kisa = DURUM_KISA.get(dil, DURUM_KISA["tr"]).get(durum_kodu, durum)
    marka_ = "" if _marka_adda(ad, marka) else (marka or "")
    ek = _uretici_eki(ad, uretici_kodu)
    nitelikler = list(dict.fromkeys([" ".join(p for p in (marka_, durum) if p), durum, durum_kisa, ""]))

    def kur(ad_: str, nitelik: str) -> str:
        parcalar = [f"{ad_}{ek}", parca_no] + ([nitelik] if nitelik else []) + [SITE_ADI]
        return " | ".join(parcalar)

    ad = _bosluk(ad)
    for nitelik in nitelikler:
        if len(kur(ad, nitelik)) <= BASLIK_SINIRI:
            return kur(ad, nitelik)
    for nitelik in nitelikler:
        kalan = BASLIK_SINIRI - len(kur("", nitelik))
        if kalan >= AD_EN_AZ:
            return kur(kisalt(ad, kalan), nitelik)
    return kur(kisalt(ad, 10), "")


def _sigdir(zorunlu: str, ekler: Iterable[str], sinir: int = ACIKLAMA_SINIRI) -> str:
    """Zorunlu cümleye, sınırı aşmadığı sürece sıradaki ek cümleleri ekler."""
    metin = zorunlu
    for ek in ekler:
        if ek and len(metin) + 1 + len(ek) <= sinir:
            metin = f"{metin} {ek}"
    return metin


def urun_meta(*, dil: str, ad: str, parca_no: str, uretici_kodu: str | None, kategori: str | None,
              durum_kodu: str, stokta: bool, teklif: bool) -> str:
    """Ürün meta description (hedef 120–155 kr): ad + üretici kodu + parça no + durum zorunlu; stok, kategori,
    sevkiyat ve teklif cümleleri sığdıkça eklenir. Uzun adda yalnız ad kısalır."""
    sablon = SABLONLAR.get(dil, SABLONLAR["tr"])
    durum = DURUM_META.get(dil, DURUM_META["tr"]).get(durum_kodu) or sablon["durum_yok"]
    stok = sablon["stok_teklif" if teklif else ("stok_var" if stokta else "stok_yok")]
    ek = _uretici_eki(ad, uretici_kodu)
    ad = _bosluk(ad)

    def zorunlu(ad_: str) -> str:
        return sablon["urun_meta"].format(ad=ad_, uretici=ek, parca_no=parca_no, durum=durum)

    ilk = zorunlu(ad)
    if len(ilk) > ACIKLAMA_SINIRI - 20:   # yalnız ad kısalır; parça no / üretici kodu hiç bölünmez (gerekirse sınır aşılır)
        ilk = zorunlu(kisalt(ad, max(AD_EN_AZ, ACIKLAMA_SINIRI - 20 - len(zorunlu("")))))
    ekler = [e.format(stok=stok, kategori=_bosluk(kategori or "")) for e in sablon["urun_meta_ek"]
             if kategori or "{kategori}" not in e]
    return _sigdir(ilk, ekler)


def urun_aciklama_sablonu(dil: str, ad: str, parca_no: str, uretici_kodu: str | None, kategori: str | None) -> str:
    """Kayıtlı açıklama yokken JSON-LD/meta için şablon tabanlı kısa açıklama."""
    uretici = _sablon(dil, "uretici_ek").format(kod=uretici_kodu) if uretici_kodu else ""
    kat = _sablon(dil, "kategori_ek").format(kategori=kategori) if kategori else ""
    return _bosluk(_sablon(dil, "urun_aciklama").format(ad=ad, parca_no=parca_no, uretici=uretici, kategori=kat))


def meta_aciklama(metin: str) -> str:
    return kisalt(metin, ACIKLAMA_SINIRI)


def kategori_basligi(dil: str, kategori: str, adet: int, sayfa: int = 1, kok: str | None = None) -> str:
    """Alt kategori: '{kategori}: {kök} Yedek Parçaları | Ceylan Robot'; kök (ya da kök bilinmiyor):
    '{kategori}: Yedek Parça ve Ürünler ({adet}) | Ceylan Robot'. Sığmayan sırayla daha kısa kalıba düşer, en sonda
    kategori adı kısalır. Sayfa > 1: ' – Sayfa N' eki (hep korunur)."""
    sablon = SABLONLAR.get(dil, SABLONLAR["tr"])
    sayfa_ek = sablon["sayfa_ek"].format(sayfa=sayfa) if sayfa > 1 else ""
    alt = bool(kok) and kok != kategori
    kaliplar = sablon["kategori_baslik_alt" if alt else "kategori_baslik_kok"]
    kategori = _bosluk(kategori)
    for kalip in kaliplar:
        baslik = kalip.format(kategori=kategori, kok=_bosluk(kok or ""), adet=adet, sayfa=sayfa_ek)
        if len(baslik) <= BASLIK_SINIRI:
            return baslik
    son = kaliplar[-1]
    kalan = BASLIK_SINIRI - len(son.format(kategori="", kok="", adet=adet, sayfa=sayfa_ek))
    return son.format(kategori=kisalt(kategori, max(kalan, 8)), kok="", adet=adet, sayfa=sayfa_ek)


def kategori_aciklamasi(dil: str, kategori: str, adet: int, sayfa: int = 1, *, markalar: Sequence[str] = (),
                        durumlar: Sequence[str] = ()) -> str:
    """Kategori meta: '{kategori} grubunda {n} ürün; markalar: A, B, C; durum: … .' + ek cümleler (≤ 155 kr).
    markalar: kategorideki en çok ürünlü üretici markaları (gerçek veri, en çok 3); durumlar: durum_kodu'lar
    ('belirtilmemis' yok sayılır). Sığmazsa önce durum, sonra marka listesi atılır."""
    sablon = SABLONLAR.get(dil, SABLONLAR["tr"])
    adlar = DURUM_META.get(dil, DURUM_META["tr"])
    marka_metni = ", ".join(list(dict.fromkeys(m for m in markalar if m))[:EN_COK_MARKA_META])
    durum_metni = ", ".join(dict.fromkeys(adlar[d] for d in durumlar if d in adlar))
    marka_ek = sablon["kategori_meta_marka"].format(liste=marka_metni) if marka_metni else ""
    durum_ek = sablon["kategori_meta_durum"].format(liste=durum_metni) if durum_metni else ""
    kategori = _bosluk(kategori)
    sayfa_ek = f" – {'Sayfa' if dil == 'tr' else 'Page'} {sayfa}" if sayfa > 1 else ""
    sinir = ACIKLAMA_SINIRI - len(sayfa_ek)
    for m_ek, d_ek in ((marka_ek, durum_ek), (marka_ek, ""), ("", "")):
        ilk = sablon["kategori_meta"].format(kategori=kategori, adet=adet, markalar=m_ek, durumlar=d_ek)
        if len(ilk) <= sinir:
            break
    metin = _sigdir(ilk, sablon["kategori_meta_ek"], sinir)
    return kisalt(metin, sinir) + sayfa_ek


def kategori_girisi(dil: str, kategori: str, kok: str | None, adet: int) -> str:
    kok_metni = _sablon(dil, "kategori_giris_kok").format(kok=kok) if kok and kok != kategori else ""
    return _sablon(dil, "kategori_giris").format(kategori=kategori, kok=kok_metni, adet=adet)


def varsayilan_aciklama(dil: str) -> str:
    return _sablon(dil, "varsayilan_aciklama")


# ---------- canonical / hreflang ----------

def dil_yolu(yol: str, dil: str) -> str | None:
    """'/tr/urun/5' -> '/en/urun/5'; dil öneksiz yollar için None."""
    parcalar = yol.split("/", 2)
    if len(parcalar) >= 2 and parcalar[1] in DILLER:
        parcalar[1] = dil
        return "/".join(parcalar)
    return None


def canonical_url(site_kok: str, yol: str, sayfa: int = 1) -> str:
    """Filtre/sıralama/arama parametrelerini atar; `sayfa` > 1 korunur."""
    return mutlak(site_kok, yol) + (f"?{urlencode({'sayfa': sayfa})}" if sayfa > 1 else "")


def alternatifler(site_kok: str, yol: str, sayfa: int = 1) -> list[tuple[str, str]]:
    """[(hreflang, mutlak url)] tr, en, x-default(=tr). Dil öneksiz yolda boş liste."""
    if dil_yolu(yol, "tr") is None:
        return []
    bag = {d: canonical_url(site_kok, dil_yolu(yol, d) or yol, sayfa) for d in DILLER}
    return [("tr", bag["tr"]), ("en", bag["en"]), ("x-default", bag["tr"])]


def og_gorseli(site_kok: str, adres: str) -> str:
    """Open Graph görseli mutlak olmalı; SVG yer tutucular paylaşım önizlemesinde çalışmaz -> logo."""
    if adres.lower().endswith(".svg"):
        adres = LOGO_YOLU
    return mutlak(site_kok, adres)


def sayfa_seo(*, yayin_modu: str, site_kok: str, dil: str, yol: str, baslik: str | None, aciklama: str,
              og_tur: str = "website", gorsel: str | None = None, sayfa: int = 1,
              json_ld: Sequence[str] = ()) -> dict:
    """Taban şablonun kullandığı tek sözlük. İşlemsel sayfalarda canonical/hreflang/OG yoktur."""
    seo: dict = {
        "baslik": baslik,
        "aciklama": aciklama,
        "robots": robots_meta(yayin_modu, yol),
        "canonical": None,
        "alternatifler": [],
        "og": None,
        "json_ld": list(json_ld),
    }
    if not islemsel_mi(yol):
        canonical = canonical_url(site_kok, yol, sayfa)
        seo["canonical"] = canonical
        seo["alternatifler"] = alternatifler(site_kok, yol, sayfa)
        seo["og"] = {
            "tur": og_tur, "url": canonical, "yerel": OG_YEREL.get(dil, "tr_TR"),
            "gorsel": og_gorseli(site_kok, gorsel or LOGO_YOLU),
        }
    return seo


# ---------- JSON-LD ----------

def json_ld_metni(veri: dict | list) -> Markup:
    """<script type="application/ld+json"> içine güvenle yazılır: <, >, & ve satır ayırıcılar \\uXXXX kaçışlıdır
    (json.loads aynı değeri geri verir); '</script>' gövdede asla görünmez."""
    ham = json.dumps(veri, ensure_ascii=False, separators=(",", ":"))
    kacisli = (ham.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
               .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    return Markup(kacisli)  # yalnız bu çıktı şablonda kaçışsız basılır


def _satici(site_kok: str) -> dict:
    return {"@type": "Organization", "name": SITE_ADI, "url": site_kok}


# Sayfadaki "Türkiye içi kargo 15 € + KDV (temsili)" metniyle (tr.json urun.teslim_ozet) aynı değer; testle bağlıdır.
TR_KARGO_EUR = "15.00"


def _kargo_detayi() -> dict:
    """Yalnız Türkiye teslimatı (sepete eklenebilir ürün). Yurt dışı: navlun teklifle -> shippingDetails verilmez."""
    return {
        "@type": "OfferShippingDetails",
        "shippingRate": {"@type": "MonetaryAmount", "value": TR_KARGO_EUR, "currency": "EUR"},
        "shippingDestination": {"@type": "DefinedRegion", "addressCountry": "TR"},
    }


def _iade_politikasi(site_kok: str, dil: str) -> dict:
    """yasal/iade (A. bireysel alıcılar): 14 gün cayma hakkı. Ücretsiz iade iddiası yok; kurumsal/yurt dışı koşullar
    sözleşmeye bağlıdır ve sayfa bağlantısıyla anlatılır. Yasal onaydan sonra gözden geçirilmelidir."""
    return {
        "@type": "MerchantReturnPolicy",
        "applicableCountry": "TR",
        "returnPolicyCategory": "https://schema.org/MerchantReturnFiniteReturnWindow",
        "merchantReturnDays": 14,
        "merchantReturnLink": f"{site_kok}/{dil}/yasal/iade",
    }


def stok_durumu(stok: int, tedarik_gun: int | None) -> str:
    if stok > 0:
        return "https://schema.org/InStock"
    return "https://schema.org/PreOrder" if tedarik_gun else "https://schema.org/OutOfStock"


def gercek_durum(urun) -> str:
    """Yapısal veri, başlık ve güven satırı için durum: gösterim amaçlı örnek durum (durum_ornek) sayılmaz."""
    return "belirtilmemis" if getattr(urun, "durum_ornek", False) else urun.durum_kodu


GARANTILI_DURUMLAR = frozenset({"ikinci_el_test_edildi", "yenilenmis"})


def garantili_mi(urun) -> bool:
    """G3b I-2: "Test edilmiştir · 12 ay garanti" yalnız gerçek durumu test edilmiş 2. el ya da yenilenmiş üründe."""
    return gercek_durum(urun) in GARANTILI_DURUMLAR


def urun_json_ld(*, site_kok: str, dil: str, urun, marka: str | None, aciklama: str, gorsel: str,
                 kategori: str | None, gosterim=None, teknik=None) -> dict:
    """schema.org Product. `gosterim`: sayfanın anonim (TR) ziyaretçiye birincil gösterdiği FiyatGosterim
    (aynı `birim_fiyat_gosterimi` hesabı). Teklif zorunlu üründe `offers` hiç verilmez (fiyatsız Offer geçersiz öğedir).
    G3b: itemCondition kaynaktan çıkarılan (örnek olmayan) durumdan; additionalProperty teknik özelliklerden (≤ 20)."""
    url = f"{site_kok}/{dil}/urun/{urun.id}"
    sema_durum = DURUM_SEMA.get(gercek_durum(urun))
    veri: dict = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": urun.ad,
        "sku": urun.sku,
        "image": [mutlak(site_kok, gorsel)],
        "description": aciklama,
        "url": url,
    }
    if urun.uretici_kodu:
        veri["mpn"] = urun.uretici_kodu
    if marka:
        veri["brand"] = {"@type": "Brand", "name": marka}
    if kategori:
        veri["category"] = kategori
    if sema_durum:
        veri["itemCondition"] = sema_durum
    if teknik is not None and teknik.ozellikler:
        veri["additionalProperty"] = [{"@type": "PropertyValue", "name": ad, "value": deger}
                                      for ad, deger in teknik.ozellikler[:EN_COK_OZELLIK_LD]]
    if not urun.teklif_zorunlu and gosterim is not None:
        fiyat = f"{gosterim.ana_tutar:.2f}"
        teklif: dict = {
            "@type": "Offer",
            "url": url,
            "price": fiyat,
            "priceCurrency": gosterim.ana_para,
            "priceSpecification": {
                "@type": "UnitPriceSpecification", "price": fiyat, "priceCurrency": gosterim.ana_para,
                "valueAddedTaxIncluded": bool(gosterim.kdv_dahil),
            },
            "availability": stok_durumu(urun.stok, urun.tedarik_suresi_gun),
            "seller": _satici(site_kok),
            "shippingDetails": _kargo_detayi(),
            "hasMerchantReturnPolicy": _iade_politikasi(site_kok, dil),
        }
        if sema_durum:
            teklif["itemCondition"] = sema_durum
        veri["offers"] = teklif
    return veri


def liste_json_ld(*, site_kok: str, dil: str, ana_sayfa_adi: str, yol: Sequence[tuple[int, str]],
                  urunler: Iterable) -> list[dict]:
    """BreadcrumbList (Ana sayfa > kategori yolu) + ItemList (sayfadaki ürünler)."""
    ogeler = [{"@type": "ListItem", "position": 1, "name": ana_sayfa_adi, "item": f"{site_kok}/{dil}/"}]
    for kimlik, ad in yol:
        ogeler.append({"@type": "ListItem", "position": len(ogeler) + 1, "name": ad,
                       "item": f"{site_kok}/{dil}/kategori/{kimlik}"})
    liste = [
        {"@type": "ListItem", "position": i, "url": f"{site_kok}/{dil}/urun/{u.id}", "name": u.ad}
        for i, u in enumerate(urunler, 1)
    ]
    return [
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": ogeler},
        {"@context": "https://schema.org", "@type": "ItemList", "numberOfItems": len(liste), "itemListElement": liste},
    ]


def ana_sayfa_json_ld(*, site_kok: str, dil: str, telefon: str) -> list[dict]:
    kurulus: dict = {
        "@context": "https://schema.org", "@type": "Organization", "name": SITE_ADI,
        "url": site_kok + "/", "logo": mutlak(site_kok, LOGO_YOLU),
    }
    if telefon:
        kurulus["contactPoint"] = {"@type": "ContactPoint", "telephone": telefon, "contactType": "sales"}
    site = {
        "@context": "https://schema.org", "@type": "WebSite", "name": SITE_ADI, "url": f"{site_kok}/{dil}/",
        "potentialAction": {
            "@type": "SearchAction",
            "target": {"@type": "EntryPoint", "urlTemplate": f"{site_kok}/tr/ara?q={{search_term_string}}"},
            "query-input": "required name=search_term_string",
        },
    }
    return [kurulus, site]


# ---------- robots.txt ----------

def robots_metni(yayin_modu: str, site_kok: str, ai_tarayicilar: Sequence[str]) -> str:
    if yayin_modu == "demo":
        return f"User-agent: *\nDisallow: /\nDisallow: {BAL_KUPU_ONEKI}\n"
    kurallar = "Allow: /\n" + "".join(f"Disallow: {y}\n" for y in ROBOTS_YASAK)
    bloklar = ["User-agent: *\n" + kurallar]
    bloklar += [f"User-agent: {ad}\n" + kurallar for ad in ai_tarayicilar]
    return "\n".join(bloklar) + f"\nSitemap: {site_kok}/sitemap.xml\n"


# ---------- sitemap XML ----------

_XML_BASLIK = '<?xml version="1.0" encoding="UTF-8"?>\n'


def sitemap_xml(site_kok: str, girdiler: Iterable[tuple[str, str | None]]) -> str:
    """girdiler: ('/{dil}/urun/5', 'YYYY-MM-DD' | None). Her <url> tr loc + tr/en/x-default alternatifleri."""
    parcalar = [_XML_BASLIK,
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n']
    for kalip, lastmod in girdiler:
        tr, en = (site_kok + kalip.format(dil=d) for d in DILLER)
        parcalar.append(f"<url><loc>{escape(tr)}</loc>")
        if lastmod:
            parcalar.append(f"<lastmod>{escape(lastmod)}</lastmod>")
        for hreflang, adres in (("tr", tr), ("en", en), ("x-default", tr)):
            parcalar.append(f'<xhtml:link rel="alternate" hreflang="{hreflang}" href="{escape(adres)}"/>')
        parcalar.append("</url>\n")
    parcalar.append("</urlset>\n")
    return "".join(parcalar)


def sitemap_indeks_xml(site_kok: str, dosyalar: Iterable[tuple[str, str | None]]) -> str:
    parcalar = [_XML_BASLIK, '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n']
    for yol, lastmod in dosyalar:
        parcalar.append(f"<sitemap><loc>{escape(site_kok + yol)}</loc>")
        if lastmod:
            parcalar.append(f"<lastmod>{escape(lastmod)}</lastmod>")
        parcalar.append("</sitemap>\n")
    parcalar.append("</sitemapindex>\n")
    return "".join(parcalar)


# ---------- llms.txt (llmstxt.org biçimi; düz Markdown) ----------
# Gizli talimat/prompt enjeksiyonu YOK: metin yalnız gerçek site içeriğini özetler (cloaking sayılır).

DEMO_NOTU = "Bu bir iç demodur; veriler temsilidir."
LLMS_OZET = (
    "Ceylan Robot; test edilmiş 2. el robotlar, kontrol üniteleri ve otomasyon yedek parçalarını Türkiye'ye ve "
    "yurt dışına (ihracat) satar. Fiyatlar EUR cinsindendir; bazı ürünler yalnızca teklifle satılır."
)
LLMS_BOLUMLER = {
    "gruplar": "Ürün grupları",
    "satin_alma": "Satın alma ve teklif",
    "teslimat": "Teslimat ve ihracat",
    "iletisim": "İletişim",
    "yasal": "Yasal",
    "ek": "Optional",
}


def _tek_satir(metin: str) -> str:
    return _bosluk(metin).replace("[", "(").replace("]", ")")


def llms_metni(*, site_kok: str, demo: bool, gruplar: Sequence[tuple[str, int, int]], telefon: str,
               yasal: Sequence[tuple[str, str]]) -> str:
    """gruplar: (kök kategori adı, id, ürün sayısı); yasal: (başlık, sayfa adı)."""
    s = [f"# {SITE_ADI}", ""]
    if demo:
        s += [DEMO_NOTU, ""]
    s += [f"> {LLMS_OZET}", "", f"## {LLMS_BOLUMLER['gruplar']}", ""]
    s += [f"- [{_tek_satir(ad)}]({site_kok}/tr/kategori/{kid}): {adet} ürün" for ad, kid, adet in gruplar]
    s += ["", f"## {LLMS_BOLUMLER['satin_alma']}", "",
          f"- [Teklif iste]({site_kok}/tr/teklif): fiyatı gösterilmeyen ürünler ve robotlar için teklif formu",
          f"- [Ön bilgilendirme]({site_kok}/tr/yasal/on-bilgilendirme): sipariş öncesi bilgilendirme",
          "", f"## {LLMS_BOLUMLER['teslimat']}", "",
          f"- [Kullanım ve satış koşulları]({site_kok}/tr/yasal/kullanim): teslimat, KDV ve ihracat (DAP) koşulları",
          f"- [İade ve cayma]({site_kok}/tr/yasal/iade): iade ve cayma koşulları",
          "", f"## {LLMS_BOLUMLER['iletisim']}", ""]
    if telefon:
        s.append(f"- Telefon: {telefon}")
    s.append(f"- [Künye ve iletişim bilgileri]({site_kok}/tr/yasal/kunye)")
    s += ["", f"## {LLMS_BOLUMLER['yasal']}", ""]
    s += [f"- [{_tek_satir(ad)}]({site_kok}/tr/yasal/{sayfa})" for ad, sayfa in yasal]
    s += ["", f"## {LLMS_BOLUMLER['ek']}", "", f"- [Tüm ürünler]({site_kok}/llms-full.txt): ad, parça no, üretici kodu ve durumla tam liste", ""]
    return "\n".join(s)


def llms_full_metni(*, site_kok: str, demo: bool, gruplar: Iterable[tuple[str, Iterable]]) -> str:
    """gruplar: (kategori başlığı, ürünler); ürün: id, ad, sku, uretici_kodu, durum_kodu. Ürün satırları '- ' ile başlar."""
    s = [f"# {SITE_ADI} – tüm ürünler", ""]
    if demo:
        s += [DEMO_NOTU, ""]
    s += [f"> {LLMS_OZET}", ""]
    for baslik, urunler in gruplar:
        s += [f"## {_tek_satir(baslik)}", ""]
        for u in urunler:
            parcalar = [_tek_satir(u["ad"]), f"parça no: {_tek_satir(u['sku'])}"]
            if u["uretici_kodu"]:
                parcalar.append(f"üretici kodu: {_tek_satir(u['uretici_kodu'])}")
            durum = DURUM_ADLARI["tr"].get(u["durum_kodu"])
            if durum:
                parcalar.append(f"durum: {durum}")
            parcalar.append(f"[bağlantı]({site_kok}/tr/urun/{u['id']})")
            s.append("- " + " — ".join(parcalar))
        s.append("")
    return "\n".join(s)
