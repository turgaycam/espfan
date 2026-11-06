"""G3d pilot düzeltmesi: TR<->EN birim eşdeğerliği, anahtar->birim haritası, sıcaklık/işaret."""
from __future__ import annotations

import pytest

from app.katalog.aciklama_dogrula import dogrula
from tests.test_aciklama_duzeltme import GOVDE, KUKA

KAYNAK = {
    **KUKA,
    "teknik": [["Yük", "16,5 kg"], ["Besleme", "24 V DC"], ["Kanal Sayısı", "4"], ["Faz", "3"], ["Çıkış Sayısı", "2"], ["Giriş Sayısı", "8"],
               ["Eksen Sayısı", "6"], ["Süre", "1 saniye"], ["Bağımsız çıkış", "2 bağımsız"],
               ["Faz tipi", "3 fazlı"], ["Sıcaklık", "-20 °C ile +70 °C"], ["Aralık", "-5°C < T < +50°C"],
               ["Bekleme", "10 dakika"], ["Çalışma", "8 saat"], ["Kutup", "4 kutuplu"], ["Paket", "5 adet"]],
}


def _k(ek, **d):
    return dogrula(GOVDE + " " + ek, "tr", {**KAYNAK, **d})


@pytest.mark.parametrize("ek", [
    "The unit has 1 second delay.", "It is a 3-phase device.", "It has 3 phase input.", "2 independent outputs.",
    "4-channel module.", "4 channels in total.", "6 axes in total.", "6-axis arm.", "2 outputs.", "8 inputs.",
    "10 minutes wait.", "10 min wait.", "8 hours of use.", "4 poles.", "4-pole motor.", "5 pcs in a pack.",
    "5 pieces.", "5 units.", "1 sec.", "2 çıkış ve 8 giriş.", "3 fazlı yapı.", "4 kanallı yapı.", "1 saniye.",
])
def test_esdeger_birimler_gecer(ek):
    assert "uydurma_sayi" not in _k(ek), ek


@pytest.mark.parametrize("ek", [
    "5-channel module.", "5 channels in total.", "2 seconds delay.", "1 minute delay.", "4-phase device.",
    "3 independent outputs.", "7-axis arm.", "3 outputs.", "9 inputs.", "11 minutes wait.", "8 days of use.",
    "5 poles.", "6 pcs in a pack.", "4 axes.", "2-channel module.", "1 hour.", "3 seconds.",
])
def test_uydurma_varyantlar_hala_reddedilir(ek):
    assert "uydurma_sayi" in _k(ek), ek


def test_anahtar_birim_haritasi_yalniz_saf_sayi_degerinde():
    # "Kanal Sayısı: 4" -> (4, kanal); değer birimli ya da başka anahtar ise harita devreye girmez
    kaynak = {"teknik": [["Kanal Sayısı", "4 adet"], ["Renk", "4"]]}
    assert "uydurma_sayi" in _k("4-channel module.", **kaynak)
    assert "uydurma_sayi" in _k("4 inputs.", **kaynak)


@pytest.mark.parametrize("ek", [
    "Çalışma sıcaklığı -20 °C ile +70 °C arasındadır.", "Çalışma sıcaklığı -20°C ve +70°C.",
    "Aralık -5°C ile +50°C.", "Operating range is -20 °C to +70 °C.",
])
def test_sicaklik_isaret_gecer(ek):
    assert "uydurma_sayi" not in _k(ek), ek


@pytest.mark.parametrize("ek", [
    "Sıcaklık +20 °C ile +70 °C.", "Sıcaklık 20 °C ile 70 °C.", "Sıcaklık -20 °C ile -70 °C.",
    "Sıcaklık -20 °F ile +70 °C.", "Sıcaklık -30 °C.", "Sıcaklık -20 °C ile +80 °C.", "Sıcaklık -20 ile +70.",
])
def test_sicaklik_isaret_uydurma_reddedilir(ek):
    assert "uydurma_sayi" in _k(ek), ek


def test_html_karakteri_hala_reddedilir():
    assert "html" in _k("Seviye < 100 mVss olmalıdır.")


YUZDE = {**KAYNAK, "teknik": KAYNAK["teknik"] + [["Tepe Yük", "%160 oranında"], ["Verim", "> %80 - %92 arası"],
                                                  ["Genişletilebilirlik", "en fazla 3 adet genişletme modülü"],
                                                  ["Aralık", "0 - 100 kHz"]]}


@pytest.mark.parametrize("ek", ["Tepe yük 160% oranındadır.", "Verim 80% ile 92% arasındadır.",
                                "Peak load is %160.", "Up to 3 expansion modules.", "Range 0 to 100 kHz."])
def test_yuzde_oneki_ve_ek_esdegerler(ek):
    assert "uydurma_sayi" not in dogrula(GOVDE + " " + ek, "tr", YUZDE), ek


@pytest.mark.parametrize("ek", ["Tepe yük 150% oranındadır.", "Verim 85% olur.", "Up to 4 expansion modules.",
                                "Range 0 to 200 kHz."])
def test_yuzde_uydurma_reddedilir(ek):
    assert "uydurma_sayi" in dogrula(GOVDE + " " + ek, "tr", YUZDE), ek
