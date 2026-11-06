from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.fiyat.kur import (
    TCMB_URL,
    Kur,
    kur_al,
    kur_bayat_mi,
    kur_kaydet,
    son_kur,
    tcmb_ayristir,
)

ORNEK = (Path(__file__).parent / "ornekler" / "tcmb_today.xml").read_bytes()


def istemci(isleyici) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(isleyici))


def test_tcmb_ayristir():
    k = tcmb_ayristir(ORNEK)
    assert k == Kur(tarih=date(2026, 10, 13), eur_alis=Decimal("48.1234"), eur_satis=Decimal("48.2101"))


@pytest.mark.parametrize("xml", [
    b"<bozuk",
    b'<Tarih_Date Tarih="13.10.2026"><Currency Kod="USD"><ForexBuying>1</ForexBuying>'
    b"<ForexSelling>1</ForexSelling></Currency></Tarih_Date>",
    b'<Tarih_Date Tarih="13.10.2026"><Currency Kod="EUR"><ForexBuying></ForexBuying>'
    b"<ForexSelling>48.2101</ForexSelling></Currency></Tarih_Date>",
    b'<Tarih_Date><Currency Kod="EUR"><ForexBuying>48.1</ForexBuying>'
    b"<ForexSelling>48.2</ForexSelling></Currency></Tarih_Date>",
])
def test_tcmb_ayristir_bozuk(xml):
    with pytest.raises(ValueError):
        tcmb_ayristir(xml)


def test_kaydet_ve_son_kur(con, simdi):
    assert son_kur(con) is None
    eski = Kur(date(2026, 10, 10), Decimal("47.9000"), Decimal("48.0000"))
    yeni = Kur(date(2026, 10, 13), Decimal("48.1234"), Decimal("48.2101"))
    with con:
        kur_kaydet(con, yeni, simdi)
        kur_kaydet(con, eski, simdi)
    assert son_kur(con) == yeni
    # aynı tarih yeniden kaydedilirse üzerine yazılır
    duzeltme = Kur(date(2026, 10, 13), Decimal("48.1000"), Decimal("48.2000"))
    with con:
        kur_kaydet(con, duzeltme, simdi)
    assert son_kur(con) == duzeltme
    assert con.execute("SELECT COUNT(*) FROM kur").fetchone()[0] == 2


def test_kur_bayat_mi():
    k = Kur(date(2026, 10, 10), Decimal("1"), Decimal("1"))
    assert kur_bayat_mi(k, date(2026, 10, 13)) is False   # 3 gün: bayat değil
    assert kur_bayat_mi(k, date(2026, 10, 14)) is True    # 4 gün: bayat


def test_kur_al_basarili(con, simdi):
    istekler = []

    def isleyici(istek: httpx.Request) -> httpx.Response:
        istekler.append(str(istek.url))
        return httpx.Response(200, content=ORNEK)

    with con:
        k = kur_al(con, istemci(isleyici), simdi)
    assert istekler == [TCMB_URL]
    assert k.eur_satis == Decimal("48.2101")
    assert son_kur(con) == k
    satir = con.execute("SELECT alindi FROM kur").fetchone()
    assert satir[0] == simdi.isoformat()


def test_kur_al_ag_hatasi_son_kuru_korur(con, simdi):
    onceki = Kur(date(2026, 10, 9), Decimal("47.5"), Decimal("47.6"))
    with con:
        kur_kaydet(con, onceki, simdi)

    def ag_hatasi(istek: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("baglanti yok", request=istek)

    with pytest.raises(httpx.ConnectError):
        with con:
            kur_al(con, istemci(ag_hatasi), simdi)
    assert son_kur(con) == onceki


def test_kur_al_http_500_son_kuru_korur(con, simdi):
    onceki = Kur(date(2026, 10, 9), Decimal("47.5"), Decimal("47.6"))
    with con:
        kur_kaydet(con, onceki, simdi)
    with pytest.raises(httpx.HTTPStatusError):
        with con:
            kur_al(con, istemci(lambda istek: httpx.Response(500)), simdi)
    assert son_kur(con) == onceki
