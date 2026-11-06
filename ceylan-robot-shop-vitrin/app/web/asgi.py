"""uvicorn giriş noktası: uvicorn --factory app.web.asgi:uygulama

Ayarlar ortamdan (systemd EnvironmentFile=/opt/cr-shop-demo/ortam) okunur.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.ayarlar import ayarlari_oku
from app.web.uygulama import uygulama_olustur


def uygulama() -> FastAPI:
    return uygulama_olustur(ayarlari_oku())
