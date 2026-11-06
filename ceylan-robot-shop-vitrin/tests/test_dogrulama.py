import pytest

from app.hesap.dogrulama import tckn_gecerli, vkn_gecerli

# Örnekler gerçek kişi/kurum numarası DEĞİL; algoritmayla üretilmiştir.
GECERLI_VKN = "4728136592"
GECERLI_TCKN = "10000000146"


def test_vkn_gecerli_ornek():
    assert vkn_gecerli(GECERLI_VKN) is True
    assert vkn_gecerli("1234567890") is True  # tüm ara değerleri 0 olan uç durum


def test_vkn_son_hane_degisirse_gecersiz():
    assert vkn_gecerli("4728136593") is False
    assert vkn_gecerli("4728136590") is False


@pytest.mark.parametrize("s", ["472813659", "47281365921", "", "47281365a2", "4728 36592", "４７２８１３６５９２"])
def test_vkn_bicim_hatalari(s):
    assert vkn_gecerli(s) is False


def test_tckn_gecerli_ornek():
    assert tckn_gecerli(GECERLI_TCKN) is True


def test_tckn_kontrol_haneleri():
    assert tckn_gecerli("10000000147") is False  # 11. hane yanlış
    assert tckn_gecerli("10000000156") is False  # 10. hane yanlış


def test_tckn_ilk_hane_sifir():
    # 01000000168 kontrol haneleri bakımından tutarlıdır; yalnız ilk hane 0 olduğu için geçersiz
    assert tckn_gecerli("01000000168") is False


@pytest.mark.parametrize("s", ["1000000014", "100000001460", "", "1000000014a", "1000000014 "])
def test_tckn_bicim_hatalari(s):
    assert tckn_gecerli(s) is False
