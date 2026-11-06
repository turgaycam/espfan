"""Ortam değişkenlerinden uygulama ayarları."""
import ipaddress
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


YAYIN_MODLARI = ("demo", "uretim")
GIZLI_ANAHTAR_ORNEK = "ornek-degil-uretilecek"   # dagitim/ortam.ornek ile aynı (testte denetlenir)
GIZLI_ANAHTAR_EN_AZ = 32
MUAF_UYARI_ONEK = 8   # IPv4'te bundan geniş (prefixlen < 8) muaf ağ uyarı günlüğü yazar
log = logging.getLogger("cr_shop.ayarlar")


@dataclass(frozen=True)
class Ayarlar:
    db_yolu: Path
    gizli_anahtar: str
    yonetici_kullanici: str
    yonetici_parola_ozeti: str
    kaynak_api: str = "https://www.ceylanrobot.com"
    gorsel_kok: str = "https://www.ceylanrobot.com"
    bantlar_yolu: Path = Path(__file__).parent / "fiyat" / "bantlar.yaml"
    telefon: str = "+90 (332) 239 15 75"  # başlıktaki satış hattı; boş string: satır basılmaz
    eposta: str = ""  # G3e madde 21: künyedeki iletişim e-postası (SHOP_EPOSTA); boşsa satır basılmaz
    gorsel_dizin: Path | None = None  # yerel ürün görselleri; boşsa SHOP_DB klasörü altında gorsel/
    yayin_modu: str = "demo"  # "demo": arama motorlarına kapalı; "uretim": indekslenebilir (SEO uyumu)
    site_kok: str = "http://192.168.5.30:3030"  # mutlak URL'ler (canonical, sitemap, JSON-LD) için kök; sonda "/" yok
    ai_tarayicilar: tuple[str, ...] = ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "CCBot")  # yalnız üretimde izinli
    sayfa_hiz_limiti: int = 120  # ürün/kategori sayfalarında IP başına dakikadaki istek üst sınırı
    koruma_muaf: tuple = ()  # hız sınırı ve bal küpü engelinden muaf IP ağları (ipaddress nesneleri; e2e makinesi için)
    havale_gun: int = 3  # G3g madde 4: havale siparişinin ödeme süresi (iş günü); sonra rezervasyon bırakılır
    # G3i madde 7: proformadaki satıcı vergi bilgileri (SHOP_SATICI_VKN, SHOP_SATICI_VERGI_DAIRESI); boşsa
    # "Demo: üretimde doldurulacak"
    satici_vkn: str = ""
    satici_vergi_dairesi: str = ""

    def __post_init__(self) -> None:
        # Son inceleme M-1: oturum çerezi (yönetici bayrağı dahil) bu anahtarla imzalanır; örnek değer ya da kısa anahtarla
        # uygulama açılmaz. Hata metni anahtarın kendisini içermez.
        if self.gizli_anahtar == GIZLI_ANAHTAR_ORNEK or len(self.gizli_anahtar) < GIZLI_ANAHTAR_EN_AZ:
            raise RuntimeError(f"SHOP_GIZLI_ANAHTAR: en az {GIZLI_ANAHTAR_EN_AZ} karakter olmalı ve "
                               "dagitim/ortam.ornek'teki örnek değer kullanılamaz; üretmek için: "
                               'python3 -c "import secrets;print(secrets.token_urlsafe(48))"')
        if self.yayin_modu not in YAYIN_MODLARI:
            raise RuntimeError("SHOP_YAYIN_MODU")
        if self.sayfa_hiz_limiti < 1:
            raise RuntimeError("SHOP_SAYFA_HIZ")
        if not 1 <= self.havale_gun <= 60:
            raise RuntimeError("SHOP_HAVALE_GUN")
        object.__setattr__(self, "site_kok", self.site_kok.rstrip("/"))
        if self.gorsel_dizin is None:
            object.__setattr__(self, "gorsel_dizin", self.db_yolu.parent / "gorsel")


def _muaf_aglar(deger: str) -> tuple:
    """SHOP_KORUMA_MUAF_IP: virgüllü IP/ağ listesi. Tüm adresleri kapsayan ağ (prefixlen 0: 0.0.0.0/0, ::/0)
    korumayı tamamen kapatacağı için başlangıç hatasıdır; /8'den geniş IPv4 ağı uyarı günlüğü yazar."""
    try:
        aglar = tuple(ipaddress.ip_network(p.strip(), strict=False) for p in deger.split(",") if p.strip())
    except ValueError:
        raise RuntimeError("SHOP_KORUMA_MUAF_IP") from None
    for ag in aglar:
        if ag.prefixlen == 0:
            raise RuntimeError("SHOP_KORUMA_MUAF_IP")
        if ag.version == 4 and ag.prefixlen < MUAF_UYARI_ONEK:
            log.warning("SHOP_KORUMA_MUAF_IP çok geniş bir ağ içeriyor (%s): bu ağdaki herkes hız sınırı ve "
                        "bal küpü engelinden muaf", ag)
    return aglar


_ZORUNLU = ("SHOP_DB", "SHOP_GIZLI_ANAHTAR", "SHOP_YONETICI", "SHOP_YONETICI_OZET")


def ayarlari_oku(ortam: Mapping[str, str] = os.environ) -> Ayarlar:
    for anahtar in _ZORUNLU:
        if not ortam.get(anahtar):
            raise RuntimeError(anahtar)
    ek: dict[str, str] = {}
    if ortam.get("SHOP_KAYNAK_API"):
        ek["kaynak_api"] = ortam["SHOP_KAYNAK_API"].rstrip("/")
    if "SHOP_TELEFON" in ortam:  # boş değer de geçerli: telefon satırını kapatır
        ek["telefon"] = ortam["SHOP_TELEFON"].strip()
    if ortam.get("SHOP_EPOSTA"):
        ek["eposta"] = ortam["SHOP_EPOSTA"].strip()
    for anahtar, alan in (("SHOP_SATICI_VKN", "satici_vkn"), ("SHOP_SATICI_VERGI_DAIRESI", "satici_vergi_dairesi")):
        if ortam.get(anahtar):
            ek[alan] = ortam[anahtar].strip()
    if ortam.get("SHOP_GORSEL_DIZIN"):
        ek["gorsel_dizin"] = Path(ortam["SHOP_GORSEL_DIZIN"])
    if "SHOP_YAYIN_MODU" in ortam:  # bilinmeyen değer Ayarlar.__post_init__'te başlangıç hatası olur
        ek["yayin_modu"] = ortam["SHOP_YAYIN_MODU"].strip()
    if ortam.get("SHOP_SITE_KOK"):
        ek["site_kok"] = ortam["SHOP_SITE_KOK"].strip()
    if ortam.get("SHOP_AI_TARAYICILAR"):
        ek["ai_tarayicilar"] = tuple(a.strip() for a in ortam["SHOP_AI_TARAYICILAR"].split(",") if a.strip())
    if ortam.get("SHOP_SAYFA_HIZ"):
        try:
            ek["sayfa_hiz_limiti"] = int(ortam["SHOP_SAYFA_HIZ"])
        except ValueError:
            raise RuntimeError("SHOP_SAYFA_HIZ") from None
    if ortam.get("SHOP_HAVALE_GUN"):
        try:
            ek["havale_gun"] = int(ortam["SHOP_HAVALE_GUN"])
        except ValueError:
            raise RuntimeError("SHOP_HAVALE_GUN") from None
    if ortam.get("SHOP_KORUMA_MUAF_IP"):
        ek["koruma_muaf"] = _muaf_aglar(ortam["SHOP_KORUMA_MUAF_IP"])
    return Ayarlar(
        db_yolu=Path(ortam["SHOP_DB"]),
        gizli_anahtar=ortam["SHOP_GIZLI_ANAHTAR"],
        yonetici_kullanici=ortam["SHOP_YONETICI"],
        yonetici_parola_ozeti=ortam["SHOP_YONETICI_OZET"],
        **ek,
    )
