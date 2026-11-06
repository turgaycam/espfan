"""G3f — EN ürün adı / teknik özellik çevirisi doğrulayıcısı (app/katalog/ceviri_dogrula.py)."""
from __future__ import annotations

import pytest

from app.katalog.ceviri_dogrula import dogrula

KAYNAK = {
    "ad": "KUKA 00-109-802 KRC2 GÜÇ KAYNAĞI 27V-NT",
    "teknik": [["Giriş Voltajı (Input)", "0,72 kV"], ["Çıkış akımı", "%15 tolerans, 25 A"], ["Ağırlık", "3,5 kg"]],
}
CEVIRI = {
    "ad_en": "KUKA 00-109-802 KRC2 Power Supply 27V-NT",
    "teknik_en": [["Input Voltage (Input)", "0.72 kV"], ["Output Current", "15% tolerance, 25 A"],
                  ["Weight", "3.5 kg"]],
}


def _kodlar(**degisiklik):
    ceviri = {**CEVIRI, **degisiklik}
    return dogrula(KAYNAK, ceviri)


def test_gecerli_ceviri_gecer():
    assert _kodlar() == []


def test_yalniz_ad_cevirisi_gecer():
    assert _kodlar(teknik_en=None) == []


def test_ondalik_ayrac_ve_yuzde_yeri_izinli():
    k = {"ad": "TRAFO 0,72 KV", "teknik": [["Oran", "%15"]]}
    assert dogrula(k, {"ad_en": "Transformer 0.72 kV", "teknik_en": [["Ratio", "15%"]]}) == []


def test_ikinci_el_used_olur():
    k = {"ad": "2. EL ABB IRB 2400 ROBOT KOLU", "teknik": []}
    assert dogrula(k, {"ad_en": "Used ABB IRB 2400 Robot Arm", "teknik_en": None}) == []


@pytest.mark.parametrize("ad_en", [
    "KUKA 00-109-802 KRC2 Power Supply",                 # kod eksik
    "KUKA 00-109-802 KRC2 Power Supply 27V-NT 2x",      # fazla sayı
    "KUKA 00-109-803 KRC2 Power Supply 27V-NT",          # kod değişmiş
    "KUKA 00-109-802 KRC4 Power Supply 27V-NT",          # model değişmiş
])
def test_ad_sayi_kod_red(ad_en):
    assert "sayi_kod" in _kodlar(ad_en=ad_en)


def test_ayrac_farki_kod_degisikligidir():
    # Düzeltme turu 1 (C-1): parça numarasının ayraç biçimi korunmalı (yanlış red, yanlış kabulden iyidir)
    assert "sayi_kod" in _kodlar(ad_en="KUKA 00109802 KRC2 Power Supply 27V-NT")
    assert "sayi_kod" in _kodlar(ad_en="KUKA 001-09-802 KRC2 Power Supply 27V-NT")


@pytest.mark.parametrize("teknik_en", [
    [["Input Voltage", "0.27 kV"], ["Output Current", "15% tolerance, 25 A"], ["Weight", "3.5 kg"]],
    [["Input Voltage", "0.72 kV"], ["Output Current", "tolerance, 25 A"], ["Weight", "3.5 kg"]],
    [["Input Voltage", "0.72 kV"], ["Output Current", "15% tolerance, 25 A"], ["Weight", "3.5 kg, 2 pcs"]],
])
def test_teknik_sayi_kod_red(teknik_en):
    assert "sayi_kod" in _kodlar(teknik_en=teknik_en)


def test_teknik_sayilar_satirlar_arasi_tasinamaz():
    # aynı sayılar ama başka satırda: satır bazında red
    teknik = [["Input Voltage", "25 A"], ["Output Current", "15% tolerance, 0.72 kV"], ["Weight", "3.5 kg"]]
    assert "sayi_kod" in _kodlar(teknik_en=teknik)


def test_satir_sayisi():
    assert "satir_sayisi" in _kodlar(teknik_en=CEVIRI["teknik_en"][:2])
    assert "satir_sayisi" in _kodlar(teknik_en=[])
    assert "satir_sayisi" in _kodlar(teknik_en=CEVIRI["teknik_en"] + [["Extra", "x"]])


@pytest.mark.parametrize("degisiklik", [
    {"ad_en": "KUKA 00-109-802 KRC2 Güç Supply 27V-NT"},
    {"ad_en": "KUKA 00-109-802 KRC2 Power Supply ve Kablo 27V-NT"},
    {"teknik_en": [["Input Voltage", "0.72 kV"], ["Output Current", "15% tolerance, 25 A"], ["Ağırlık", "3.5 kg"]]},
    {"teknik_en": [["Input Voltage", "yaklaşık 0.72 kV"], ["Output Current", "15% tolerance, 25 A"],
                   ["Weight", "3.5 kg"]]},
])
def test_turkce_kalinti(degisiklik):
    assert "turkce_kalinti" in _kodlar(**degisiklik)


def test_turkce_harf_kod_ve_marka_jetonunda_serbest():
    k = {"ad": "STÄUBLI TX90 ŞALTER Ç-200", "teknik": []}
    assert "turkce_kalinti" not in dogrula(k, {"ad_en": "Stäubli TX90 Switch Ç-200", "teknik_en": None})


@pytest.mark.parametrize("ad_en", ["KR", "K" * 201, "KUKA KRC2 27V", "KUKA 00-109-802 KRC2 " + "Power Supply Unit For Industrial Robot Controller Cabinets And Spares " * 2 + "27V-NT"])
def test_uzunluk(ad_en):
    assert "uzunluk" in _kodlar(ad_en=ad_en)


def test_marka_korunmali_ve_eklenmemeli():
    assert "marka" in _kodlar(ad_en="00-109-802 KRC2 Power Supply Unit 27V-NT")
    assert "marka" in _kodlar(ad_en="KUKA ABB 00-109-802 KRC2 Power Supply 27V-NT")
    assert "marka" not in _kodlar()


@pytest.mark.parametrize("degisiklik", [
    {"ad_en": ""}, {"ad_en": "   "},
    {"teknik_en": [["", "0.72 kV"], ["Output Current", "15% tolerance, 25 A"], ["Weight", "3.5 kg"]]},
    {"teknik_en": [["Input Voltage", " "], ["Output Current", "15% tolerance, 25 A"], ["Weight", "3.5 kg"]]},
])
def test_bos(degisiklik):
    assert "bos" in _kodlar(**degisiklik)


def test_kodlar_tekil_ve_sirali():
    kodlar = _kodlar(ad_en="Güç", teknik_en=[])
    assert len(kodlar) == len(set(kodlar))
    assert {"turkce_kalinti", "uzunluk", "satir_sayisi", "marka", "sayi_kod"} <= set(kodlar)


# ---------- Düzeltme turu 1: C-1, C-2, I-1, M-4 ----------
def _tek(ad, ad_en, teknik=(), teknik_en=None):
    return dogrula({"ad": ad, "teknik": [list(x) for x in teknik]},
                   {"ad_en": ad_en, "teknik_en": None if teknik_en is None else [list(x) for x in teknik_en]})


def _satir(tr, en):
    return _tek("ABB ROBOT KABLOSU 3M", "ABB Robot Cable 3M", [tr], [en])


@pytest.mark.parametrize("tr, en", [
    (("Sıcaklık", "-20 ... +60 °C"), ("Temperature", "20 ... 60 °C")),        # işaret düştü
    (("Tepki", "<5 ms"), ("Response", ">5 ms")),                               # karşılaştırma ters
    (("Tolerans", "±10%"), ("Tolerance", "10%")),
    (("Tolerans", "±%10"), ("Tolerance", "-10%")),
    (("Mil", "Ø20"), ("Shaft", "20")),                                          # harf ön eki düştü
    (("Bağlantı", "1/2\""), ("Connection", "12\"")),                          # kesir 12 oldu
])
def test_c1_isaret_karsilastirma_kesir_onek_red(tr, en):
    assert "sayi_kod" in _satir(tr, en)


def test_c1_ad_kesir_ve_harf_onek_red():
    assert "sayi_kod" in _tek('FESTO VALF 1/2"', 'FESTO Valve 12"')
    assert "sayi_kod" in _tek("ABB ŞALTER Ç-200", "ABB Switch 200")


@pytest.mark.parametrize("tr, en", [
    (("Gerilim", "0,72 kV"), ("Voltage", "0.72 V")),
    (("Ağırlık", "3,5 kg"), ("Weight", "3.5 lb")),
    (("Gerilim", "24 V AC"), ("Voltage", "24 V DC")),
    (("Gerilim", "24 VAC"), ("Voltage", "24 VDC")),
])
def test_c2_birim_degisikligi_red(tr, en):
    assert _satir(tr, en)


def test_c2_ad_akim_turu_red():
    assert _tek("ABB RÖLE 24 V AC", "ABB Relay 24 V DC")


@pytest.mark.parametrize("tr, en", [
    (("Gerilim", "24V"), ("Voltage", "24 V")),
    (("Gerilim", "24 VDC"), ("Voltage", "24 V DC")),
    (("Akım", "51 Amper"), ("Current", "51 A")),
    (("Çalışma Sıcaklığı", "-40°C ile +71°C arası (61°C'den sonra)"), ("Operating Temperature", "-40°C to +71°C (after 61°C)")),
    (("Verimlilik", "%98'e varan"), ("Efficiency", "Up to 98%")),
    (("Giriş Tipi", "3 Fazlı AC"), ("Input Type", "3-phase AC")),
    (("Giriş Tipi", "1-FAZ"), ("Input Type", "1-Phase")),
    (("İzolasyon", "3 kV,50 Hz,1 dak."), ("Insulation", "3 kV, 50 Hz, 1 min.")),
    (("Giriş Akımı", "3x400 V AC'de: 1,65 A"), ("Input Current", "1.65 A at 3x400 V AC")),
    (("Akım", "0,5-3 A"), ("Current", "0.5-3 A")),
    (("Dalgalanma", "< 100 mVss"), ("Ripple", "< 100 mVpp")),
])
def test_dogru_cevirilerde_yanlis_red_yok(tr, en):
    assert _satir(tr, en) == []


def test_ad_gercek_ornekler_gecer():
    assert _tek("SIEMENS SIDAC-S 3 FAZLI GÜÇ KAYNAĞI", "SIEMENS SIDAC-S 3-Phase Power Supply") == []
    assert _tek("MURR EVOLUTİON 20 GÜÇ KAYNAĞI 20A", "MURR EVOLUTİON 20 Power Supply 20A") == []
    assert _tek("SIEMENS LOGO! GÜÇ KAYNAĞI 24V DC/4A", "SIEMENS LOGO! Power Supply 24V DC/4A") == []
    assert _tek("SCHAFFER SEBEKE HATTI FILTRESI", "SCHAFFER Mains Line Filter") == []


@pytest.mark.parametrize("tr, en", [
    ("SIEMENS SIMATIC KART 6ES7", "Siemens SINAMICS Board 6ES7"),
    ("KUKA KCP KRC KART", "KUKA KRC Board"),
    ("SIEMENS SITOP GÜÇ KAYNAĞI 24V", "SIEMENS Power Supply 24V"),
])
def test_i1_model_seri_adlari_korunur(tr, en):
    assert "kod" in _tek(tr, en)


def test_m4_anahtar_deger_yer_degistirme_red():
    assert "sayi_kod" in _satir(("Ağırlık", "3,5 kg"), ("3.5 kg", "Weight"))
    assert "sayi_kod" in _satir(("Giriş 3 faz", "400 V"), ("Input", "3 phase 400 V"))


def test_m4_binlik_ayrac_uyarisi():
    from app.katalog.ceviri_dogrula import uyarilar
    assert uyarilar({"ad": "ABB MOTOR 1.200 W", "teknik": []}) == ["binlik_ayrac"]   # tur 2: 1.000 kesin -> ret
    assert uyarilar({"ad": "ABB MOTOR", "teknik": [["Güç", "1,500 W"]]}) == ["binlik_ayrac"]
    assert uyarilar({"ad": "ABB MOTOR 0,72 KV", "teknik": [["Güç", "1,5 W"]]}) == []


@pytest.mark.parametrize("tr, en", [   # gerçek Haiku çıktılarından: doğru çeviriler geçmeli
    (("LED", "Ön panelde \"DC-OK\" LED'leri bulunur"), ("LED", "\"DC-OK\" LEDs on front panel")),
    (("Değer", "-%3/K güç düşümü"), ("Value", "power derating of -3%/K")),
    (("Verim", "> %80 - %92 arası"), ("Efficiency", "> 80% - 92%")),
    (("Tolerans", "% -15 / % +10"), ("Tolerance", "-15% / +10%")),
    (("Tolerans", "%±5 kademe"), ("Tolerance", "±5% step")),
    (("Tolerans", "± %25"), ("Tolerance", "± 25%")),
    (("Tolerans", "< ± %0.1"), ("Tolerance", "< ±0.1%")),
    (("Hata", "±0.01 %/K"), ("Error", "±0.01%/K")),
    (("Form", "19 inç kabin"), ("Form", "19-inch cabinet")),
    (("Not", "\"3,5\" ibaresi 3.5 kVA"), ("Note", "the \"3.5\" in the code means 3.5 kVA")),
    (("Ağırlık", "Yaklaşık 50 gram"), ("Weight", "Approx. 50 g")),
    (("Veri", "2 bit, 1 byte"), ("Data", "2 bits, 1 byte")),
    (("Akım", "1 amperlik adımlarla"), ("Current", "in 1 ampere steps")),
    (("Gerilim", "6.000 V AC"), ("Voltage", "6000 V AC")),
    (("Sınıf", "44. voltaj sınıfı"), ("Class", "44th voltage class")),
    (("Kasa", "1U Yüksekliğinde"), ("Housing", "1U-height")),
    (("Kontak", "2 NK + 2 NA"), ("Contact", "2 NC + 2 NO")),
    (("Arayüz", "entegre CPU'lar ve PLC'lerinden"), ("Interface", "integrated CPUs and PLCs")),
])
def test_gercek_ciktilar_yanlis_red_yok(tr, en):
    assert _satir(tr, en) == []


def test_gercek_ad_yazim_hatali_marka_korunabilir():
    assert _tek("SEW-EURODRİVE EMV MODUL 826385X", "SEW-EURODRİVE EMV Module 826385X") == []
    assert _tek("SPS-ELECTRONİC YÜKSEK GERİLİM RÖLESİ", "SPS-ELECTRONİC High Voltage Relay") == []


def test_binlik_ayrac_tr_virgul_bin_kati_red():
    assert "sayi_kod" in _satir(("Güç", "1,500 W"), ("Power", "1500 W"))


# ---------- Düzeltme turu 2 ----------
@pytest.mark.parametrize("tr, en", [
    ("5 MW", "5 mW"), ("5 MHz", "5 mHz"), ("5 MΩ", "5 mΩ"), ("5 MB", "5 mb"), ("5 mW", "5 MW"),
    ("5 MPa", "5 mPa"), ("5 MV", "5 mV"),
])
def test_n1_birim_on_eki_harf_duyarli(tr, en):
    assert _satir(("Değer", tr), ("Value", en))


@pytest.mark.parametrize("tr, en", [
    ("5 MHZ", "5 MHz"), ("10 KW", "10 kW"), ("3 KG", "3 kg"), ("24 V", "24 volts"), ("5 Mhz", "5 MHz"),
    ("100 MA", "100 mA"), ("2 MOHM", "2 MΩ"),
])
def test_n1_buyuk_harf_yazimlar_gecer(tr, en):
    assert _satir(("Değer", tr), ("Value", en)) == []


def test_n2_buyuk_harfli_turkce_ekli_birim():
    assert _satir(("Kablo", "5 METRELİK"), ("Cable", "5 m")) == []
    assert _satir(("Kablo", "5 METRELIK"), ("Cable", "5 m")) == []


@pytest.mark.parametrize("tr, en", [
    ("1 NO + 1 NC", "1 NC + 1 NC"), ("1 NO", "1 NC"), ("NC/COM", "NO/COM"), ("1 NO", "1 NO + 1 NC"),
    ("2 NA kontak", "2 NC contacts"), ("COM, NO", "NO"),
])
def test_n3_kontak_tipi_tam_eslesme(tr, en):
    assert "kod" in _satir(("Kontak", tr), ("Contact", en))


def test_n3_kontak_dogru_ceviri_ve_parca_no():
    assert _satir(("Kontak", "2 NK + 2 NA, COM"), ("Contact", "2 NC + 2 NO, COM")) == []
    assert _tek("ABB RÖLE PARÇA NO 12", "ABB Relay Part No. 12") == []


def test_n5_tr_kesin_binlik_en_noktali_kalirsa_red():
    assert "binlik" in _satir(("Güç", "1.000 W"), ("Power", "1.000 W"))
    assert "binlik" in _satir(("Döngü", "10.000.000 çevrim"), ("Cycles", "10.000.000 cycles"))
    assert _satir(("Güç", "1.000 W"), ("Power", "1000 W")) == []
    assert _satir(("Güç", "1.000 W"), ("Power", "1,000 W")) == []
    # belirsiz: TR "1.500" 1,5 (İngilizce biçimli kaynak) ya da 1500 olabilir -> ret değil, uyarı
    assert _satir(("Güç", "1.500 W"), ("Power", "1.500 W")) == []
    from app.katalog.ceviri_dogrula import uyarilar
    assert uyarilar({"ad": "X", "teknik": [["Güç", "1.500 W"]]}) == ["binlik_ayrac"]
    assert uyarilar({"ad": "X", "teknik": [["Güç", "1.000 W"]]}) == []


def test_tur2_gercek_ornekler():
    assert _tek("KEYENCE M8 10 METRE BAĞLANTI KABLOSU", "KEYENCE M8 10 Meter Connection Cable") == []
    assert _tek("TOX SERVO MOTOR 055.098.500.001", "TOX Servo Motor 055.098.500.001") == []   # parça no, binlik değil
