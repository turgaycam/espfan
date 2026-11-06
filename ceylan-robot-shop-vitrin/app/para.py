"""Para tutarları: yalnız Decimal, ROUND_HALF_UP, 2 hane."""
from decimal import ROUND_HALF_UP, Decimal

IKI_HANE = Decimal("0.01")


def d(deger: str | int | Decimal) -> Decimal:
    if isinstance(deger, (bool, float)):
        raise TypeError("float/bool para değeri olarak kabul edilmez")
    if isinstance(deger, Decimal):
        return deger
    if isinstance(deger, (str, int)):
        return Decimal(deger)
    raise TypeError(f"desteklenmeyen tip: {type(deger).__name__}")


def yuvarla(x: Decimal) -> Decimal:
    return x.quantize(IKI_HANE, rounding=ROUND_HALF_UP)
