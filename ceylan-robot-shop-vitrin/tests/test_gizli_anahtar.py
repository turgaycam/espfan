"""Son inceleme M-1: SHOP_GIZLI_ANAHTAR başlangıç doğrulaması (örnek değer ve 32 karakterden kısa anahtar reddedilir)."""
import re
from pathlib import Path

import pytest

from app.ayarlar import GIZLI_ANAHTAR_EN_AZ, GIZLI_ANAHTAR_ORNEK, Ayarlar, ayarlari_oku
from app.web.uygulama import uygulama_olustur

KOK = Path(__file__).resolve().parent.parent


def _ortam(anahtar, tmp_path):
    return {"SHOP_DB": str(tmp_path / "g.db"), "SHOP_GIZLI_ANAHTAR": anahtar, "SHOP_YONETICI": "y",
            "SHOP_YONETICI_OZET": "o"}


def test_ornek_deger_ortam_ornek_dosyasindakiyle_ayni():
    metin = (KOK / "dagitim/ortam.ornek").read_text(encoding="utf-8")
    m = re.search(r"^SHOP_GIZLI_ANAHTAR='([^']*)'$", metin, re.M)
    assert m and m.group(1) == GIZLI_ANAHTAR_ORNEK
    assert GIZLI_ANAHTAR_EN_AZ == 32


@pytest.mark.parametrize("anahtar", [GIZLI_ANAHTAR_ORNEK, "k" * 31, "kisa", "  " + "k" * 20 + "  "])
def test_gecersiz_anahtar_baslangicta_reddedilir_ve_degeri_yazmaz(tmp_path, anahtar):
    with pytest.raises(RuntimeError) as hata:
        ayarlari_oku(_ortam(anahtar, tmp_path))
    mesaj = str(hata.value)
    assert mesaj.startswith("SHOP_GIZLI_ANAHTAR") and "32" in mesaj, mesaj
    assert anahtar.strip() not in mesaj
    with pytest.raises(RuntimeError):            # doğrudan kurulan Ayarlar da (uygulama_olustur yolu) reddeder
        Ayarlar(db_yolu=tmp_path / "d.db", gizli_anahtar=anahtar, yonetici_kullanici="y", yonetici_parola_ozeti="o")


def test_gecerli_anahtar_kabul_edilir_ve_uygulama_acilir(tmp_path):
    import secrets
    anahtar = secrets.token_urlsafe(48)
    ayarlar = ayarlari_oku(_ortam(anahtar, tmp_path))
    assert ayarlar.gizli_anahtar == anahtar
    assert ayarlari_oku(_ortam("k" * 32, tmp_path)).gizli_anahtar == "k" * 32     # sınır: tam 32
    assert uygulama_olustur(ayarlar) is not None
