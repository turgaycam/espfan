"""app/katalog/marka.py: bilinen üretici markaları izin listesi (G2; G3 fasetleri de kullanır)."""
import pytest

from app.katalog.marka import BILINEN_MARKALAR, marka_cikar


@pytest.mark.parametrize(
    ("ad", "beklenen"),
    [
        ("ABB IRB 6640 Robot Kolu", "ABB"),
        ("Fanuc A06B-6077 Servo Sürücü", "FANUC"),
        ("kuka KRC4 Kontrol Ünitesi", "KUKA"),
        ("KUKA KRC2 GÜÇ KAYNAĞI", "KUKA"),
        ("SIEMENS SIRIUS İZLEME RÖLESİ", "Siemens"),
        ("siemens sirius izleme rölesi", "Siemens"),
        ("ALLEN-BRADLEY 140M", "Allen-Bradley"),
        ("Allen Bradley 140M", "Allen-Bradley"),
        ("UNIVERSAL ROBOTS UR5e Kol", "Universal Robots"),
        ("STÄUBLI TX60 Kablo Seti", "Stäubli"),
        ("STAUBLI TX60", "Stäubli"),
        ("Phoenix Contact Klemens", "Phoenix Contact"),
        ("BOSCH REXROTH Valf 4WE6", "Bosch Rexroth"),
        ("IFM Sensör O5D100", "ifm"),
        ("İGUS ENERJİ ZİNCİRİ", "igus"),
        ("Röle 24V SMC Valf", "SMC"),
    ],
)
def test_bilinen_marka_bulunur(ad, beklenen):
    assert marka_cikar(ad) == beklenen


@pytest.mark.parametrize(
    "ad",
    ["RÖLE MODÜLÜ 24V", "SERVO MOTOR 1KW", "Kablo Demeti", "6640 Robot Kolu", "A6 Sürücü", "", "   ", None,
     "SIGORTA KUTUSU", "Sewing machine part x"],
)
def test_bilinmeyen_ya_da_jenerik_ad_marka_vermez(ad):
    assert marka_cikar(ad) is None


def test_kelime_siniri_ve_en_erken_eslesme():
    assert marka_cikar("ABBA KART") is None  # "abb" kelime parçası eşleşmez
    assert marka_cikar("KUKA KRC4 ABB ADAPTÖR") == "KUKA"  # adda ilk geçen
    assert marka_cikar("ADAPTÖR ABB KUKA") == "ABB"
    assert marka_cikar("Universal Robots SIEMENS") == "Universal Robots"


def test_liste_tutarli():
    anahtarlar = [a for a, _ in BILINEN_MARKALAR]
    assert len(anahtarlar) == len(set(anahtarlar))
    for ad in ("ABB", "KUKA", "FANUC", "YASKAWA", "MOTOMAN", "NACHI", "KAWASAKI", "STAUBLI", "COMAU", "SIEMENS",
               "SCHNEIDER", "OMRON", "MITSUBISHI", "FESTO", "SMC", "PILZ", "SICK", "WAGO", "BECKHOFF", "ROCKWELL",
               "PANASONIC", "LENZE", "SEW", "DANFOSS", "ATOS", "ASCO", "AVENTICS", "AUTONICS", "ADVANTECH",
               "BORUNTE", "KROMER", "IFM", "BALLUFF", "HARTING", "LAPP", "IGUS", "SCHUNK", "ZIMMER", "KEYENCE",
               "COGNEX", "PHOENIX CONTACT", "BOSCH REXROTH", "ALLEN-BRADLEY", "UNIVERSAL ROBOTS"):
        assert ad.lower() in anahtarlar, ad
