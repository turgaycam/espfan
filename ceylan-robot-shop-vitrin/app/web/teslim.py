"""G3e madde 11: ülkeye göre tahmini varış tarihi aralığı (temsili). Saf fonksiyonlar.

Kural (bugün + iş günü; cumartesi/pazar atlanır, resmi tatiller hesaba katılmaz):
  teklifle satılan ürün        -> "Teslim ve fiyat: teklifle"
  stokta yok (tedarikli)       -> "Tedarik süresi: N gün" (kaynakta varsa) ya da "Tedarik süresi teklifle"
  stokta, teslim ülkesi TR     -> kargoya veriliş 1–2 iş günü · varış 2–4 iş günü
  stokta, AB ülkesi            -> kargoya veriliş 1–2 iş günü · varış 4–8 iş günü
  (G3n madde 6: ürün, liste, onay ve sipariş ayrıntısı aynı metin: "Kargoya veriliş: 1–2 iş günü · varış: <aralık>")
  stokta, diğer ülkeler        -> "Teslim süresi teklifle"
  ülke seçilmemiş              -> ülke seçme ipucu
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from app.hesap.dogrulama import ab_ulkesi_mi

KARGO_IS_GUNU = (1, 2)   # G3n madde 6: stoktaki ürünün kargoya verilişi
TR_IS_GUNU = (2, 4)
AB_IS_GUNU = (4, 8)
AYLAR = {
    "tr": ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım",
           "Aralık"),
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
}
# G3h madde 13: listede kısa ay adları
KISA_AYLAR = {
    "tr": ("Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"),
    "en": AYLAR["en"],
}


def is_gunu_ekle(baslangic: date, gun: int) -> date:
    """baslangic'tan sonraki gun'üncü iş günü (hafta sonu sayılmaz)."""
    z = baslangic
    while gun > 0:
        z += timedelta(days=1)
        if z.weekday() < 5:
            gun -= 1
    return z


def aralik_metni(bas: date, son: date, dil: str, kisa: bool = False) -> str:
    """TR "14–16 Ekim", "30 Ekim – 3 Kasım" (kisa: "14–16 Eki"); EN "Oct 14–16", "Oct 30 – Nov 3"."""
    aylar = (KISA_AYLAR if kisa else AYLAR).get(dil, AYLAR["tr"])
    if dil == "en":
        if bas.month == son.month:
            return f"{aylar[bas.month - 1]} {bas.day}–{son.day}"
        return f"{aylar[bas.month - 1]} {bas.day} – {aylar[son.month - 1]} {son.day}"
    if bas.month == son.month:
        return f"{bas.day}–{son.day} {aylar[bas.month - 1]}"
    return f"{bas.day} {aylar[bas.month - 1]} – {son.day} {aylar[son.month - 1]}"


def teslim_metni(urun, ulke: str | None, bugun: date, dil: str, t: Callable[..., str], kisa: bool = False) -> str:
    """Ürün, liste, kart, karşılaştırma, sepet, ödeme özeti ve sipariş onayının ortak teslim metni. G3h madde 13:
    kisa=True (ürün listesi satırı) stoktaki üründe yalnız varış aralığı: "Varış: 19–23 Eki (temsili)"; iş günü
    açıklaması ürün sayfasında kalır."""
    if urun.teklif_zorunlu:
        return t("urun.teslim_teklif")
    if urun.stok <= 0:
        if urun.tedarik_suresi_gun:
            return t("urun.tedarik_gun", gun=urun.tedarik_suresi_gun)
        return t("urun.teslim_tedarik")
    if not ulke:
        return t("urun.teslim_ulke_sec_kisa" if kisa else "urun.teslim_ulke_sec")
    if ulke == "TR" or ab_ulkesi_mi(ulke):
        tr = ulke == "TR"
        bas, son = (is_gunu_ekle(bugun, n) for n in (TR_IS_GUNU if tr else AB_IS_GUNU))
        # G3n madde 6: liste satırı da ürün sayfasıyla aynı hesap ve biçim (kisa yalnız "ülke seçin" ipucunda)
        return t("urun.teslim_stokta", kmin=KARGO_IS_GUNU[0], kmax=KARGO_IS_GUNU[1],
                 aralik=aralik_metni(bas, son, dil))
    return t("urun.teslim_diger")
