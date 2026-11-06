"""Uçtan uca kabul testleri — laptopta, staging'e karşı. Çalıştırma: python -m pytest e2e -q

Ortam: CR_SHOP_TABAN (varsayılan http://192.168.5.30:3030),
       CR_SHOP_YONETICI / CR_SHOP_YONETICI_PAROLA (yönetim paneli kontrolleri için).
VM'deki release venv'inde Playwright yoktur; o durumda bu klasör hiç toplanmaz.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # VM: Playwright yok -> e2e toplanmaz
    collect_ignore_glob = ["*.py"]
else:
    TABAN = os.environ.get("CR_SHOP_TABAN", "http://192.168.5.30:3030").rstrip("/")
    TABAN_HOST = urlparse(TABAN).hostname
    EKRANLAR = Path(__file__).parent / "ekranlar"
    # Form doğrulama yanıtları (400/409/422) Chrome'da "Failed to load resource" olarak loglanır; bunlar beklenen akıştır.
    BEKLENEN_DURUM = re.compile(r"status of (400|409|422)")

    def _kabul_edilebilir(metin: str, konum: str) -> bool:
        if not metin.startswith("Failed to load resource"):
            return False
        yer = urlparse(konum)
        if yer.hostname == "www.ceylanrobot.com":  # görsel 404 -> yer tutucu (beklenen)
            return True
        return yer.hostname == TABAN_HOST and not yer.path.startswith("/statik/") and bool(BEKLENEN_DURUM.search(metin))

    @pytest.fixture(scope="session")
    def tarayici():
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            yield b
            b.close()

    def _yeni_sayfa(tarayici, **secenekler):
        baglam = tarayici.new_context(base_url=TABAN, locale="tr-TR", **secenekler)
        sayfa = baglam.new_page()
        hatalar: list[str] = []

        def konsol(mesaj):
            if mesaj.type != "error":
                return
            konum = (mesaj.location or {}).get("url", "")
            if not _kabul_edilebilir(mesaj.text, konum):
                hatalar.append(f"{mesaj.text} @ {konum}")

        sayfa.on("console", konsol)
        sayfa.on("pageerror", lambda hata: hatalar.append(f"pageerror: {hata}"))

        def yanit(r):
            # Hız sınırı (429) ya da bal küpü engeli (403) e2e'yi sessizce bozmasın: bağlamı kapat, teardown'da başarısız ol
            if r.status in (403, 429) and r.request.method == "GET" and urlparse(r.url).hostname == TABAN_HOST:
                hatalar.append(f"koruma tetiklendi ({r.status} {r.url}): SHOP_KORUMA_MUAF_IP'e laptop IP'sini ekleyin")
                try:
                    baglam.close()
                except Exception:  # noqa: BLE001
                    pass

        sayfa.on("response", yanit)
        return baglam, sayfa, hatalar

    @pytest.fixture
    def sayfa(tarayici):
        """Her test için yeni bağlam (çerez/oturum paylaşılmaz); sonunda konsol hatası olmamalı."""
        baglam, s, hatalar = _yeni_sayfa(tarayici, viewport={"width": 1366, "height": 900})
        yield s
        baglam.close()
        assert hatalar == [], "JS konsol hataları:\n" + "\n".join(hatalar)

    @pytest.fixture
    def mobil_sayfa(tarayici):
        baglam, s, hatalar = _yeni_sayfa(tarayici, viewport={"width": 360, "height": 780},
                                        device_scale_factor=2, is_mobile=True, has_touch=True)
        yield s
        baglam.close()
        assert hatalar == [], "JS konsol hataları (mobil):\n" + "\n".join(hatalar)

    @pytest.fixture(scope="session")
    def ekran_klasoru() -> Path:
        EKRANLAR.mkdir(exist_ok=True)
        return EKRANLAR

    @pytest.fixture(scope="session")
    def yonetici() -> tuple[str, str]:
        kullanici = os.environ.get("CR_SHOP_YONETICI", "yonetici")
        parola = os.environ.get("CR_SHOP_YONETICI_PAROLA")
        if not parola:
            pytest.fail("CR_SHOP_YONETICI_PAROLA tanımlı değil (kimlik Excel'i, 'cr-shop-demo' satırı)")
        return kullanici, parola
