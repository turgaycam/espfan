"""ceylanrobot.com public API istemcisi (salt okuma, yavaş ve yeniden denemeli)."""
import time
from collections.abc import Callable
from typing import Any

import httpx


class KaynakHatasi(Exception):
    """Bir uç nokta, bütün yeniden denemelerden sonra da alınamadı."""


class KaynakIstemci:
    YENIDEN_DENEME_BEKLEMELERI = (2.0, 4.0)   # en fazla 3 deneme: ilk istek + 2 yeniden deneme
    ZAMAN_ASIMI = 30.0

    def __init__(self, http: httpx.Client, taban: str, bekleme: float = 1.0,
                 uyku: Callable[[float], None] = time.sleep):
        self.http = http
        self.taban = taban.rstrip("/")
        self.bekleme = bekleme
        self.uyku = uyku

    def _getir(self, yol: str, params: dict[str, int] | None,
               dogrula: Callable[[Any], None]) -> Any:
        son_hata: Exception | None = None
        for deneme in range(len(self.YENIDEN_DENEME_BEKLEMELERI) + 1):
            if deneme > 0:
                self.uyku(self.YENIDEN_DENEME_BEKLEMELERI[deneme - 1])
            self.uyku(self.bekleme)
            try:
                yanit = self.http.get(self.taban + yol, params=params, timeout=self.ZAMAN_ASIMI)
                yanit.raise_for_status()
                veri = yanit.json()
                dogrula(veri)
                return veri
            except (httpx.HTTPError, ValueError) as e:
                son_hata = e
        raise KaynakHatasi(f"{yol} {params or ''}: {son_hata!r}") from son_hata

    @staticmethod
    def _liste_mi(veri: Any) -> None:
        if not isinstance(veri, list):
            raise ValueError("kategori yanıtı liste değil")

    @staticmethod
    def _sayfa_mi(veri: Any) -> None:
        if not isinstance(veri, dict) or not isinstance(veri.get("data"), list):
            raise ValueError("ürün yanıtında 'data' listesi yok")
        toplam = veri.get("total")
        if not isinstance(toplam, int) or isinstance(toplam, bool) or toplam < 0:
            raise ValueError("ürün yanıtında geçerli 'total' yok")

    def kategoriler(self) -> list[dict]:
        return self._getir("/api/public/categories", None, self._liste_mi)

    def urun_sayfasi(self, sayfa: int, limit: int = 20) -> tuple[list[dict], int]:
        veri = self._getir("/api/public/products", {"page": sayfa, "limit": limit}, self._sayfa_mi)
        return veri["data"], veri["total"]
