"""Ortak test fixture'ları ve veri yardımcıları."""
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.db import baglan, gecisleri_uygula
from app.katalog.indeks import indeks_metni, turetilmis_alanlar

KOK = Path(__file__).resolve().parent.parent
SABIT_ZAMAN = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


@pytest.fixture
def con(tmp_path):
    c = baglan(tmp_path / "test.db")
    gecisleri_uygula(c)
    yield c
    c.close()


@pytest.fixture
def simdi() -> datetime:
    return SABIT_ZAMAN


@pytest.fixture
def bantlar():
    # kurallar modülü Görev 4'te yazılır; içe aktarma fixture içinde ki
    # Görev 1-3 testleri bu modül yokken de toplanabilsin.
    from app.fiyat.kurallar import bantlari_oku

    return bantlari_oku(KOK / "app" / "fiyat" / "bantlar.yaml")


def kategori_ekle(con: sqlite3.Connection, *, kaynak_id: str, ad: str, yol: str,
                  seviye: int, ust_kaynak_id: str | None = None) -> int:
    with con:
        cur = con.execute(
            "INSERT INTO kategori (kaynak_id, ad, ust_kaynak_id, yol, seviye)"
            " VALUES (?, ?, ?, ?, ?)",
            (kaynak_id, ad, ust_kaynak_id, yol, seviye),
        )
    return cur.lastrowid


def urun_ekle(con: sqlite3.Connection, *, sku: str = "S1", ad: str = "Test Ürün",
              kok: str = "ELEKTRİK", fiyat: str = "100.00", teklif: bool = False,
              stok: int = 1, aktif: bool = True, kategori_id: int | None = None,
              kdv: str = "20", simdi: datetime | None = None,
              uretici_kodu: str | None = None, gorsel_url: str | None = None,
              tedarik_suresi_gun: int | None = None) -> int:
    """Ürünü ekler (türetilmiş alanlar dahil, G3a; G3h katli_metin ve addan tip); aktifse arama indeksine (urun_ara) tek satır yazar. Commit eder."""
    zaman = (simdi or SABIT_ZAMAN).isoformat()
    t = turetilmis_alanlar(ad, sku, uretici_kodu)
    with con:
        cur = con.execute(
            "INSERT INTO urun (sku, ad, uretici_kodu, kategori_id, kok_kategori_ad, kdv_orani,"
            " stok, tedarik_suresi_gun, gorsel_url, temsili_fiyat_eur, fiyat_temsili,"
            " teklif_zorunlu, aktif, olusturma, sira_anahtari, kod_birlesik, marka, katli_metin, tip)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sku, ad, uretici_kodu, kategori_id, kok, kdv, stok, tedarik_suresi_gun,
             gorsel_url, fiyat, int(teklif), int(aktif), zaman, t["sira_anahtari"], t["kod_birlesik"], t["marka"],
             t["katli_metin"], t["tip"]),
        )
        urun_id = int(cur.lastrowid)
        if aktif:
            con.execute(
                "INSERT INTO urun_ara (metin, kod_birlesik, urun_id) VALUES (?, ?, ?)",
                (indeks_metni(ad, sku, uretici_kodu), t["kod_birlesik"], urun_id),
            )
    return urun_id


# ---------------------------------------------------------------------------
# Web testleri (Görev 11)
# ---------------------------------------------------------------------------
import base64
import json
import re
from contextlib import contextmanager

from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner

from app.ayarlar import Ayarlar
from app.db import baglan as _baglan
from app.hesap.servis import parola_ozeti as _parola_ozeti

TEST_GIZLI = "t" * 32


@pytest.fixture
def istemci(tmp_path):
    from app.web.uygulama import uygulama_olustur

    ayarlar = Ayarlar(
        db_yolu=tmp_path / "web.db",
        gizli_anahtar=TEST_GIZLI,
        yonetici_kullanici="yonetici",
        yonetici_parola_ozeti=_parola_ozeti("yonetici-parola-123"),
    )
    with TestClient(uygulama_olustur(ayarlar)) as c:
        yield c


@pytest.fixture
def istemci_uretim(tmp_path):
    """Yayın modu `uretim` olan uygulama (SEO üretim davranışı)."""
    from app.web.uygulama import uygulama_olustur

    ayarlar = Ayarlar(
        db_yolu=tmp_path / "uretim.db",
        gizli_anahtar=TEST_GIZLI,
        yonetici_kullanici="yonetici",
        yonetici_parola_ozeti=_parola_ozeti("yonetici-parola-123"),
        yayin_modu="uretim",
        site_kok="https://shop.example.com",
    )
    with TestClient(uygulama_olustur(ayarlar)) as c:
        yield c


_CSRF_DESENI = re.compile(r'name="csrf" value="([^"]+)"')


def csrf_al(istemci, yol: str) -> str:
    """Sayfayı açar ve sayfadaki ilk csrf gizli alanının değerini döner."""
    yanit = istemci.get(yol)
    eslesme = _CSRF_DESENI.search(yanit.text)
    assert eslesme, f"{yol} sayfasında csrf alanı yok (durum {yanit.status_code})"
    return eslesme.group(1)


@contextmanager
def istemci_db(istemci):
    """Uygulamanın kullandığı veritabanına bağlanır; blok sonunda commit + close."""
    con = _baglan(istemci.app.state.ayarlar.db_yolu)
    try:
        with con:
            yield con
    finally:
        con.close()


def oturum_oku(istemci) -> dict:
    """Starlette imzalı oturum çerezini çözer (test için)."""
    deger = None
    for cerez in istemci.cookies.jar:
        if cerez.name == "cr_oturum":
            deger = cerez.value
    if not deger:
        return {}
    ham = TimestampSigner(TEST_GIZLI).unsign(deger.strip('"').encode())
    return json.loads(base64.b64decode(ham))


def oturum_yaz(istemci, veri: dict) -> None:
    """Geçerli imzalı bir oturum çerezi üretir; yalnız yeni istemcide, ilk istekten önce kullanılır."""
    deger = TimestampSigner(TEST_GIZLI).sign(base64.b64encode(json.dumps(veri).encode())).decode()
    istemci.cookies.set("cr_oturum", deger)


# Satır içi <script> yasak; tek istisna JSON-LD veri bloğu (type="application/ld+json"), kod çalıştırmaz.
_SATIR_ICI_SCRIPT = re.compile(
    r"<script(?![^>]*\bsrc\s*=)(?![^>]*\btype\s*=\s*[\"']application/ld\+json[\"'])[^>]*>", re.I)
_STIL_OZNITELIGI = re.compile(r"\sstyle\s*=", re.I)
_OLAY_OZNITELIGI = re.compile(r"<[^>]+\son[a-z]+\s*=", re.I)


def sayfa_denetle(yanit, robots: str | None = "noindex, nofollow") -> str:
    """HTML yanıtın ortak kurallarını denetler ve gövdeyi döner. `robots`: beklenen X-Robots-Tag (demo: noindex)."""
    from app.web.guvenlik import GUVENLIK_BASLIKLARI

    for anahtar, deger in GUVENLIK_BASLIKLARI.items():
        if anahtar != "X-Robots-Tag":
            assert yanit.headers.get(anahtar) == deger, anahtar
    assert yanit.headers.get("X-Robots-Tag") == robots
    html = yanit.text
    assert 'class="demo-bandi"' in html, "DEMO bandı yok"
    assert not _SATIR_ICI_SCRIPT.search(html), "satır içi <script> var"
    assert not _STIL_OZNITELIGI.search(html), 'style="" özniteliği var'
    assert "<style" not in html.lower(), "<style> etiketi var"
    assert not _OLAY_OZNITELIGI.search(html), "on*= olay özniteliği var"
    return html
