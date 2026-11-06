"""Kötü niyetli tarayıcı koruması: bal küpü (24 saat IP engeli) ve ürün/kategori sayfası hız sınırı.

- Bal küpü: taban şablondaki gizli bağlantı `/_iz/<sabit>`; robots.txt'e uyan iyi botlar ve gerçek kullanıcılar
  oraya gitmez. Giden istemci IP'si `engelli_ip` tablosuna (SQLite) ve süreç içi tabloya yazılır; 24 saat 403 alır.
  Engeller yönetim panosundan tek tıkla kaldırılabilir. `/yonetim` ve `/robots.txt` engelden muaftır
  (yöneticinin kendi IP'si engellense bile panoya girip kaldırabilmesi için).
- Hız sınırı: `/{tr|en}/urun/…`, `/{tr|en}/kategori/…`, `/{tr|en}/urunler` ve `/{tr|en}/ara` için IP başına dakikada `sayfa_hiz_limiti` (120) istek;
  aşımda 429 + Retry-After. Statik dosyalar ve /gorsel/ sayılmaz.
Not: istemci IP'si ASGI `scope["client"]`'tır. Önde bir CDN/ters vekil varsa uvicorn `--proxy-headers`
ve `--forwarded-allow-ips` ile çalıştırılmalıdır; aksi halde vekil IP'si engellenir.
"""
from __future__ import annotations

import ipaddress
import logging
import re
import sqlite3
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.db import baglan
from app.web.guvenlik import HizSiniri
from app.web.seo import BAL_KUPU_ONEKI

log = logging.getLogger("cr_shop.koruma")

ENGEL_SURESI = timedelta(hours=24)
# G3a: /urunler ve /ara de katalog dökümüne açık (sayfa=1..N, fasetler) -> aynı kova
SINIRLI_YOL = re.compile(r"^/(?:tr|en)/(?:(?:urun|kategori)/|(?:urunler|ara)/?$)")
MUAF_YOL = re.compile(r"^/(?:yonetim(?:/|$)|robots\.txt$)")
RETRY_AFTER = "60"


class EngelDeposu:
    """IP engelleri: süreç içi tablo (hızlı kontrol) + SQLite `engelli_ip` (yeniden başlatmada korunur)."""

    def __init__(self, db_yolu: Path, simdi: Callable[[], datetime] | None = None, sure: timedelta = ENGEL_SURESI) -> None:
        self.db_yolu = db_yolu
        self.simdi = simdi or (lambda: datetime.now(UTC))
        self.sure = sure
        self._tablo: dict[str, datetime] = {}
        self._kilit = threading.Lock()

    def yukle(self) -> None:
        """Başlangıçta süresi dolmamış engelleri belleğe alır; süresi dolanları siler."""
        con = baglan(self.db_yolu)
        try:
            with con:
                con.execute("DELETE FROM engelli_ip WHERE bitis <= ?", (self.simdi().isoformat(),))
            satirlar = con.execute("SELECT ip, bitis FROM engelli_ip").fetchall()
        finally:
            con.close()
        with self._kilit:
            self._tablo = {r["ip"]: datetime.fromisoformat(r["bitis"]) for r in satirlar}

    def _db(self, sql: str, param: tuple) -> None:
        try:
            con = baglan(self.db_yolu)
            try:
                with con:
                    con.execute(sql, param)
            finally:
                con.close()
        except sqlite3.Error:
            log.exception("engelli_ip yazılamadı")  # bellek tablosu yine de geçerli kalır

    def engelli_mi(self, ip: str) -> bool:
        simdi = self.simdi()
        with self._kilit:
            bitis = self._tablo.get(ip)
            if bitis is None:
                return False
            if bitis > simdi:
                return True
            del self._tablo[ip]
        self._db("DELETE FROM engelli_ip WHERE ip = ?", (ip,))
        return False

    def engelle(self, ip: str, neden: str, yol: str | None) -> None:
        simdi = self.simdi()
        with self._kilit:
            zaten = self._tablo.get(ip)
        if zaten is not None and zaten > simdi:
            return  # zaten engelli: yazma/günlük tekrarı yok
        self._db("DELETE FROM engelli_ip WHERE bitis <= ?", (simdi.isoformat(),))
        bitis = simdi + self.sure
        with self._kilit:
            self._tablo[ip] = bitis
        self._db("INSERT OR REPLACE INTO engelli_ip (ip, neden, yol, engellendi, bitis) VALUES (?, ?, ?, ?, ?)",
                 (ip, neden, (yol or "")[:200], simdi.isoformat(), bitis.isoformat()))
        log.warning("IP engellendi ip=%s neden=%s yol=%r", ip, neden, yol)

    def kaldir(self, ip: str) -> bool:
        with self._kilit:
            vardi = self._tablo.pop(ip, None) is not None
        self._db("DELETE FROM engelli_ip WHERE ip = ?", (ip,))
        return vardi

    def listele(self) -> list[dict]:
        """Yönetim panosu için: süresi dolmamış engeller, en yeni önce."""
        con = baglan(self.db_yolu)
        try:
            satirlar = con.execute(
                "SELECT ip, neden, yol, engellendi, bitis FROM engelli_ip WHERE bitis > ? ORDER BY engellendi DESC",
                (self.simdi().isoformat(),)).fetchall()
        finally:
            con.close()
        return [{"ip": r["ip"], "neden": r["neden"], "yol": r["yol"],
                 "engellendi": datetime.fromisoformat(r["engellendi"]), "bitis": datetime.fromisoformat(r["bitis"])}
                for r in satirlar]


def muaf_mi(ip: str, muaf: tuple) -> bool:
    """IP, SHOP_KORUMA_MUAF_IP ağlarından birinde mi."""
    if not muaf:
        return False
    try:
        adres = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(adres in ag for ag in muaf if ag.version == adres.version)


class KoruMiddleware:
    """Saf ASGI: bal küpü isabeti ve engelli IP -> 403; ürün/kategori sayfalarında hız aşımı -> 429."""

    def __init__(self, app: ASGIApp, engel: EngelDeposu, hiz: HizSiniri, muaf: tuple = ()) -> None:
        self.app = app
        self.muaf = muaf
        self.engel = engel
        self.hiz = hiz

    def _muaf_mi(self, ip: str) -> bool:
        return muaf_mi(ip, self.muaf)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        yol = scope["path"]
        istemci = scope.get("client")
        ip = istemci[0] if istemci else "bilinmiyor"
        if self._muaf_mi(ip):  # SHOP_KORUMA_MUAF_IP: engel ve hız sınırı yok; bal küpü isabeti yalnız günlüğe yazılır
            if yol.startswith(BAL_KUPU_ONEKI):
                log.warning("bal küpü isabeti (muaf IP, engellenmedi) ip=%s yol=%r", ip, yol)
            await self.app(scope, receive, send)
            return
        if yol.startswith(BAL_KUPU_ONEKI):
            self.engel.engelle(ip, "bal-kupu", yol)
            await PlainTextResponse("403", status_code=403)(scope, receive, send)
            return
        if not MUAF_YOL.match(yol) and self.engel.engelli_mi(ip):
            await PlainTextResponse("403", status_code=403)(scope, receive, send)
            return
        if SINIRLI_YOL.match(yol) and not self.hiz.izin(f"sayfa:{ip}", time.monotonic()):
            await PlainTextResponse("429", status_code=429, headers={"Retry-After": RETRY_AFTER})(scope, receive, send)
            return
        await self.app(scope, receive, send)
