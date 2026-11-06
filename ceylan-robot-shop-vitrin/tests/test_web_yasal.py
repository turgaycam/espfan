"""Görev 16 — yasal sayfalar (TestClient ile)."""
import re

import pytest

from app.web.rotalar.yasal import SAYFALAR

BANT = {"tr": "TASLAK – hukuki onay bekliyor (SY Hukuk)", "en": "DRAFT – pending legal approval (SY Hukuk)"}


def test_on_sayfa_tanimli():
    assert SAYFALAR == ("on-bilgilendirme", "mesafeli-satis", "iade", "garanti", "kvkk",
                        "acik-riza", "cerez", "gizlilik", "kullanim", "kunye")


@pytest.mark.parametrize("dil", ["tr", "en"])
@pytest.mark.parametrize("sayfa", SAYFALAR)
def test_yasal_sayfa_200_ve_taslak_bandi(istemci, dil, sayfa):
    r = istemci.get(f"/{dil}/yasal/{sayfa}")
    assert r.status_code == 200
    assert 'class="taslak-bandi"' in r.text
    assert BANT[dil] in r.text
    assert re.search(r"<h1[^>]*>[^<]{4,}</h1>", r.text)
    assert len(re.findall(r"<h2", r.text)) >= 3          # madde başlıkları var


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_kunye_doldurulacak(istemci, dil):
    """G3e madde 21: doldurulmamış alanlar listelenmez; tek satır demo notu."""
    r = istemci.get(f"/{dil}/yasal/kunye")
    assert "[doldurulacak]" not in r.text
    assert 'data-e2e="kunye-demo-notu"' in r.text
    assert "MUSTAFA CEYLAN ENDÜSTRİ A.Ş." in r.text
    assert "K.O.S.B. 3. Sk., No: 7, 42250 Selçuklu / Konya" in r.text
    for terim in ("MERSİS", "KEP"):
        assert terim not in r.text


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_iade_ve_garanti_b2c_b2b_ayrimi(istemci, dil):
    iade = istemci.get(f"/{dil}/yasal/iade").text
    garanti = istemci.get(f"/{dil}/yasal/garanti").text
    if dil == "tr":
        assert "14 gün" in iade and "cayma hakkı uygulanmaz" in iade
        assert "test edildi" in garanti and "olduğu gibi" in garanti and "TBK m.221" in garanti
    else:
        assert "14 days" in iade and "no right of withdrawal" in iade
        assert "tested" in garanti and "as is" in garanti and "Article 221" in garanti


@pytest.mark.parametrize("yol", ["/tr/yasal/yok", "/en/yasal/bilinmeyen", "/de/yasal/kvkk",
                                 "/tr/yasal/KVKK", "/tr/yasal/_taban"])
def test_bilinmeyen_sayfa_404(istemci, yol):
    assert istemci.get(yol).status_code == 404


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_alt_bilgi_ve_metin_ici_yasal_baglantilar_calisir(istemci, dil):
    sayfa = istemci.get(f"/{dil}/yasal/kunye")
    alt_bilgiler = re.findall(r"<footer.*?</footer>", sayfa.text, re.S)
    assert alt_bilgiler, "sayfada <footer> yok"
    alt_bilgi = alt_bilgiler[-1]                      # taban.html'in alt bilgisi sayfadaki son <footer>
    assert re.findall(rf'href="/{dil}/yasal/', alt_bilgi), "alt bilgide yasal bağlantı yok"
    baglantilar = set(re.findall(r'href="(/(?:tr|en)/yasal/[^"#?]+)"', sayfa.text))
    assert baglantilar, "yasal bağlantı bulunamadı"
    for sayfa_adi in SAYFALAR:      # metin içi çapraz bağlantılar dahil bütün yasal sayfalar
        r = istemci.get(f"/{dil}/yasal/{sayfa_adi}")
        baglantilar |= set(re.findall(r'href="(/(?:tr|en)/yasal/[^"#?]+)"', r.text))
    for yol in sorted(baglantilar):
        assert istemci.get(yol).status_code == 200, yol


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_kayit_sayfasindaki_kvkk_baglantisi(istemci, dil):
    kayit = istemci.get(f"/{dil}/kayit")
    assert kayit.status_code == 200
    assert f'href="/{dil}/yasal/kvkk"' in kayit.text
    assert istemci.get(f"/{dil}/yasal/kvkk").status_code == 200


@pytest.mark.parametrize("dil,terim", [("tr", "ticari"), ("en", "commercial")])
def test_kullanim_yurt_disi_cayma_daraltmasi(istemci, dil, terim):
    metin = istemci.get(f"/{dil}/yasal/kullanim").text
    assert terim in metin
    assert ("emredici tüketici" if dil == "tr" else "mandatory consumer") in metin
