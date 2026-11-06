"""İstek başına veritabanı bağlantısı."""
from __future__ import annotations

import sqlite3
from typing import Iterator

from fastapi import Request

from app.db import baglan


def db_bagimliligi(request: Request) -> Iterator[sqlite3.Connection]:
    con = baglan(request.app.state.ayarlar.db_yolu)
    request.state.con = con  # sablon() ortak bağlamı müşteri/sepet/kur için buradan okur
    try:
        yield con
    finally:
        request.state.con = None
        con.close()
