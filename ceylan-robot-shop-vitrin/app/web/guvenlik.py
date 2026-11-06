"""Güvenlik başlıkları, açık yönlendirme engeli, hız sınırı, oturum ve CSRF yardımcıları."""
from __future__ import annotations

import secrets
import sqlite3
import threading
from collections import deque
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.hesap.servis import Musteri, musteri_getir
from app.web.seo import robots_basligi

GUVENLIK_BASLIKLARI = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' https://www.ceylanrobot.com data:; style-src 'self'; script-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Robots-Tag": "noindex, nofollow",
}


def guvenlik_basliklari(yayin_modu: str, yol: str) -> dict[str, str]:
    """GUVENLIK_BASLIKLARI + yayın moduna göre X-Robots-Tag: demoda her yanıtta, üretimde yalnız işlemsel sayfalarda."""
    basliklar = {k: v for k, v in GUVENLIK_BASLIKLARI.items() if k != "X-Robots-Tag"}
    robots = robots_basligi(yayin_modu, yol)
    if robots:
        basliklar["X-Robots-Tag"] = robots
    return basliklar


class BaslikMiddleware:
    """Saf ASGI middleware: her HTTP yanıtına güvenlik başlıklarını yazar (statik dosyalar dahil)."""

    def __init__(self, app: ASGIApp, yayin_modu: str = "demo") -> None:
        self.app = app
        self.yayin_modu = yayin_modu

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def gonder(message: Message) -> None:
            if message["type"] == "http.response.start":
                basliklar = MutableHeaders(scope=message)
                for anahtar, deger in guvenlik_basliklari(self.yayin_modu, scope["path"]).items():
                    basliklar[anahtar] = deger
            await send(message)

        await self.app(scope, receive, gonder)


def guvenli_sonraki(deger: str | None, varsayilan: str = "/") -> str:
    if not deger or not isinstance(deger, str):
        return varsayilan
    if not deger.startswith("/") or deger.startswith("//") or "\\" in deger:
        return varsayilan
    if any(ord(c) < 32 or ord(c) == 127 for c in deger):
        return varsayilan
    parca = urlsplit(deger)
    if parca.scheme or parca.netloc:
        return varsayilan
    return deger


def capali(sonraki: str, urun_id: int) -> str:
    """G3e madde 18: JS'siz POST dönüşünde kaydırma korunur: güvenli dönüş adresi + #urun-<id> çapası (varsa eski
    çapa atılır)."""
    return sonraki.split("#", 1)[0] + f"#urun-{int(urun_id)}"


class HizSiniri:
    """Kayan pencere: `pencere` saniyede anahtar başına en fazla `limit` izin. Reddedilen deneme sayılmaz.

    Bellek: pencere süresinde bir kez (her istekte değil) süresi dolmuş anahtarlar süpürülür; toplam anahtar sayısı
    `azami`yı aşarsa en eski eklenen anahtarlar atılır (IP sayısı sınırsız büyüyemez)."""

    def __init__(self, limit: int = 10, pencere: float = 60.0, azami: int = 50_000) -> None:
        self.limit = limit
        self.pencere = pencere
        self.azami = azami
        self._kayit: dict[str, deque[float]] = {}
        self._kilit = threading.Lock()
        self._son_supurme: float | None = None

    def _supur(self, simdi: float) -> None:
        sinir = simdi - self.pencere
        for k in [k for k, v in self._kayit.items() if not v or v[-1] <= sinir]:
            del self._kayit[k]
        self._son_supurme = simdi

    def _kirp(self) -> None:
        hedef = int(self.azami * 0.9)
        for k in list(self._kayit)[: len(self._kayit) - hedef]:  # sözlük eklenme sırasını korur: en eskiler
            del self._kayit[k]

    def izin(self, anahtar: str, simdi: float) -> bool:
        with self._kilit:
            if self._son_supurme is None:
                self._son_supurme = simdi
            elif simdi - self._son_supurme >= self.pencere:
                self._supur(simdi)
            kuyruk = self._kayit.setdefault(anahtar, deque())
            sinir = simdi - self.pencere
            while kuyruk and kuyruk[0] <= sinir:
                kuyruk.popleft()
            if len(kuyruk) >= self.limit:
                return False
            kuyruk.append(simdi)
            if len(self._kayit) > self.azami:
                self._kirp()
            return True


def oturum_kimligi(request: Request) -> str:
    oid = request.session.get("oid")
    if not isinstance(oid, str) or not oid:
        oid = secrets.token_urlsafe(16)
        request.session["oid"] = oid
    return oid


def csrf_jetonu(request: Request) -> str:
    jeton = request.session.get("csrf")
    if not isinstance(jeton, str) or len(jeton) < 20:
        jeton = secrets.token_urlsafe(32)
        request.session["csrf"] = jeton
    return jeton


async def csrf_dogrula(request: Request) -> None:
    beklenen = request.session.get("csrf")
    try:
        form = await request.form()
    except Exception:  # bozuk gövde
        raise HTTPException(status_code=403) from None
    gelen = form.get("csrf")
    if not isinstance(beklenen, str) or not isinstance(gelen, str) or not secrets.compare_digest(gelen, beklenen):
        raise HTTPException(status_code=403)


def aktif_musteri(request: Request, con: sqlite3.Connection) -> Musteri | None:
    if "session" not in request.scope:
        return None
    mid = request.session.get("mid")
    if mid is None:
        return None
    if type(mid) is not int:
        request.session.pop("mid", None)
        return None
    musteri = musteri_getir(con, mid)
    if musteri is None:
        request.session.pop("mid", None)
    return musteri
