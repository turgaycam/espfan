"""Yönetici parolasından SHOP_YONETICI_OZET değerini üretir (ortam dosyası için).

Kullanım (release ya da araç kopyası kökünden): venv/bin/python -m betikler.yonetici_ozet
  - Terminalde: parolayı iki kez sorar, ekranda göstermez.
  - Boru ile: stdin'in ilk satırını parola olarak okur (ör. kimlik Excel'inden okuyan betikten).
Çıktı: yalnız özet ("scrypt$..."), tek satır. Parola hiçbir yere yazılmaz.
"""
from __future__ import annotations

import getpass
import sys
from typing import TextIO

from app.hesap.servis import parola_ozeti

EN_AZ_UZUNLUK = 12


def parola_al(giris: TextIO) -> str:
    if giris.isatty():
        birinci = getpass.getpass("Yönetici parolası: ")
        ikinci = getpass.getpass("Tekrar: ")
        if birinci != ikinci:
            raise ValueError("parolalar_uyusmuyor")
        return birinci
    return giris.readline().rstrip("\r\n")


def calistir(giris: TextIO = sys.stdin, cikti: TextIO = sys.stdout, hata: TextIO = sys.stderr) -> int:
    try:
        parola = parola_al(giris)
    except ValueError:
        print("HATA: parolalar uyuşmuyor.", file=hata)
        return 1
    if len(parola) < EN_AZ_UZUNLUK:
        print(f"HATA: parola en az {EN_AZ_UZUNLUK} karakter olmalı.", file=hata)
        return 1
    print(parola_ozeti(parola), file=cikti)
    return 0


if __name__ == "__main__":
    sys.exit(calistir())
