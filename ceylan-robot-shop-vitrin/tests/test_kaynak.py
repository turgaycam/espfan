import json
from pathlib import Path

import httpx
import pytest

from app.esitleme.kaynak import KaynakHatasi, KaynakIstemci

ORNEK = Path(__file__).parent / "ornekler"
TABAN = "https://kaynak.test"


def yukle(ad: str) -> bytes:
    return (ORNEK / ad).read_bytes()


def istemci(isleyici, uykular: list[float]) -> KaynakIstemci:
    http = httpx.Client(transport=httpx.MockTransport(isleyici))
    return KaynakIstemci(http, TABAN + "/", bekleme=1.0, uyku=uykular.append)


def test_kategoriler_ve_bekleme():
    uykular: list[float] = []
    yollar = []

    def isleyici(istek):
        yollar.append(istek.url.path)
        return httpx.Response(200, content=yukle("kategoriler.json"))

    k = istemci(isleyici, uykular).kategoriler()
    assert yollar == ["/api/public/categories"]
    assert len(k) == 9 and k[0]["name"] == "Endüstriyel Robotlar"
    assert uykular == [1.0]          # her çağrıdan önce `bekleme`


def test_urun_sayfasi_parametreler():
    uykular: list[float] = []
    gorulen = []

    def isleyici(istek):
        gorulen.append(dict(istek.url.params))
        return httpx.Response(200, content=yukle("urunler_s1.json"))

    veri, toplam = istemci(isleyici, uykular).urun_sayfasi(1)
    assert gorulen == [{"page": "1", "limit": "20"}]
    assert toplam == 3 and [u["sku"] for u in veri] == ["8301033800019", "8102030100019"]


def test_gecici_hata_sonra_basari():
    uykular: list[float] = []
    sayac = {"n": 0}

    def isleyici(istek):
        sayac["n"] += 1
        if sayac["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, content=yukle("urunler_s2.json"))

    veri, toplam = istemci(isleyici, uykular).urun_sayfasi(2)
    assert sayac["n"] == 3 and toplam == 3 and len(veri) == 1
    assert uykular == [1.0, 2.0, 1.0, 4.0, 1.0]


def test_uc_denemeden_sonra_kaynak_hatasi():
    uykular: list[float] = []
    sayac = {"n": 0}

    def isleyici(istek):
        sayac["n"] += 1
        raise httpx.ConnectTimeout("zaman asimi", request=istek)

    with pytest.raises(KaynakHatasi):
        istemci(isleyici, uykular).urun_sayfasi(1)
    assert sayac["n"] == 3                       # ilk istek + 2 yeniden deneme
    assert uykular == [1.0, 2.0, 1.0, 4.0, 1.0]


@pytest.mark.parametrize("govde", [
    b"<html>bakim</html>",
    json.dumps({"data": "yok", "total": 3}).encode(),
    json.dumps({"data": [], "total": "3"}).encode(),
])
def test_bicimsiz_yanit_hata_sayilir(govde):
    uykular: list[float] = []
    with pytest.raises(KaynakHatasi):
        istemci(lambda istek: httpx.Response(200, content=govde), uykular).urun_sayfasi(1)
