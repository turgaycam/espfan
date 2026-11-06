"""G3d: aktif ürünleri LLM taslak üretimi için JSONL partilerine döker (salt okunur).

Kullanım: python -m betikler.aciklama_disa --db <yol> --cikis <klasör> [--parti 100] [--sinir N]
                                            [--yalniz-eksik] [--urun-id 1,2,3]
Çıktı: <klasör>/parti-0001.jsonl, parti-0002.jsonl, ... (klasördeki eski parti-*.jsonl dosyaları silinir).
Satır: {urun_id, ad, sku, uretici_kodu, marka, kategori, kok_kategori, kategori_en, kok_kategori_en, durum_kodu,
        durum_kaynak, stok_durumu, teknik: [[anahtar, değer], ...] (en çok 20), kaynak_aciklama: ≤1500 kr ya da null}
Sıra: önce teknik özelliği olanlar, sonra kalanlar; her grupta id. Görsel/base64 yazılmaz.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from app.katalog.aciklama_dogrula import tur_celiskisi
from app.katalog.kategori_ceviri import KategoriCeviri
from app.katalog.marka import marka_cikar
from app.metin import normalize

EN_COK_TEKNIK = 20
KAYNAK_SINIRI = 1500

SORGU = (
    "SELECT u.id, u.ad, u.sku, u.uretici_kodu, u.marka, u.durum_kodu, u.durum_ornek, u.durum_kaynak, u.stok,"
    " u.tedarik_suresi_gun, u.kok_kategori_ad, k.ad AS kategori_ad, t.veri AS teknik_veri"
    " FROM urun u LEFT JOIN kategori k ON k.id = u.kategori_id LEFT JOIN urun_teknik t ON t.urun_id = u.id"
    " WHERE u.aktif = 1"
)


def salt_okunur_baglan(yol: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(Path(yol).resolve().as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _teknik(veri: str | None) -> tuple[list[list[str]], str | None]:
    if not veri:
        return [], None
    try:
        d = json.loads(veri)
    except (ValueError, TypeError):
        return [], None
    if not isinstance(d, dict):
        return [], None
    ozellikler = [[str(c[0]), str(c[1])] for c in d.get("ozellikler") or []
                  if isinstance(c, list) and len(c) == 2][:EN_COK_TEKNIK]
    bolumler = []
    for c in d.get("bolumler") or []:
        if isinstance(c, list) and len(c) == 2 and str(c[1]).strip():
            bolumler.append(f"{c[0]}: {c[1]}" if c[0] else str(c[1]))
    kaynak = "\n\n".join(bolumler)
    if len(kaynak) > KAYNAK_SINIRI:
        kaynak = kaynak[: KAYNAK_SINIRI - 1].rstrip() + "…"
    return ozellikler, (kaynak or None)


def kayit_olustur(r: sqlite3.Row, ceviri: KategoriCeviri) -> dict[str, Any]:
    """SORGU satırından dışa aktarma satırı; yükleme doğrulayıcısı da aynı kaydı kullanır."""
    ozellikler, kaynak = _teknik(r["teknik_veri"])
    if r["stok"] and r["stok"] > 0:
        stok_durumu = "stokta"
    else:
        stok_durumu = "tedarik_suresi_var" if r["tedarik_suresi_gun"] else "stok_yok"
    ornek = bool(r["durum_ornek"])
    return {
        "urun_id": r["id"], "ad": r["ad"], "sku": r["sku"], "uretici_kodu": r["uretici_kodu"],
        "marka": r["marka"] or marka_cikar(r["ad"]),  # boşsa sitenin kullandığı ad -> marka izin listesi
        "kategori": r["kategori_ad"], "kok_kategori": r["kok_kategori_ad"] or None,
        "kategori_en": ceviri.cevir(r["kategori_ad"], "en"),
        "kok_kategori_en": ceviri.cevir(r["kok_kategori_ad"], "en"),
        # gösterim amaçlı örnek durum gerçek durum değildir (app.web.seo.gercek_durum ile aynı kural)
        "durum_kodu": "belirtilmemis" if ornek else r["durum_kodu"],
        "durum_kaynak": "ornek" if ornek else r["durum_kaynak"],
        "stok_durumu": stok_durumu, "teknik": ozellikler, "kaynak_aciklama": kaynak,
    }


_SINIFLAR = {  # --cesitli için zorunlu kategori sınıfları (ad + kategori + kök kategori, normalize edilmiş)
    "robot_kolu": re.compile(r"robot kol|robot arm|manipulator|endustriyel robot"),
    "servo_motor": re.compile(r"servo\s*motor"),
    "teach_pendant": re.compile(r"pendant"),
    "kart": re.compile(r"\bkart|\bboard\b|\bcard\b"),
    "kablo": re.compile(r"\bkablo|\bcable"),
}
_DURUMLAR = ("yeni", "yenilenmis", "ikinci_el", "ikinci_el_test_edildi", "ikinci_el_oldugu_gibi", "belirtilmemis")


def _siniflar(k: dict[str, Any]) -> set[str]:
    n = normalize(" ".join(str(k.get(x) or "") for x in ("ad", "kategori", "kok_kategori")))
    return {ad for ad, d in _SINIFLAR.items() if d.search(n)}


def cesitli_sec(kayitlar: list[dict[str, Any]], adet: int, tohum: int = 1) -> list[dict[str, Any]]:
    """Kategori ve durum çeşitliliğini kapsayan tabakalı, deterministik (tohumlu) örnek.
    Zorunlu: var olan her sınıf (robot kolu, servo motor, teach pendant, kart, kablo) ve her durum kodu en az bir kez
    (adet bunlardan küçükse zorunlular yine dahil edilir). Kalan yer kategoriler arası dönüşümlü doldurulur.
    Dönüş, girdideki sıraya göre."""
    rng = random.Random(tohum)
    sirali = sorted(kayitlar, key=lambda k: k["urun_id"])
    rng.shuffle(sirali)
    secilen: list[dict[str, Any]] = []
    secili_idler: set[int] = set()
    gereken = {("sinif", c) for k in sirali for c in _siniflar(k)} | {("durum", k["durum_kodu"]) for k in sirali}
    kapsanan: set[tuple[str, str]] = set()

    def ozellikler(k: dict[str, Any]) -> set[tuple[str, str]]:
        return {("sinif", c) for c in _siniflar(k)} | {("durum", k["durum_kodu"])}

    while gereken - kapsanan:
        eksik = gereken - kapsanan
        en_iyi = max(sirali, key=lambda k: (len(ozellikler(k) & eksik), -sirali.index(k)))
        if not ozellikler(en_iyi) & eksik:
            break
        secilen.append(en_iyi)
        secili_idler.add(en_iyi["urun_id"])
        kapsanan |= ozellikler(en_iyi)
        sirali = [k for k in sirali if k["urun_id"] not in secili_idler]
    gruplar: dict[str, list[dict[str, Any]]] = {}
    for k in sirali:
        gruplar.setdefault(str(k.get("kategori") or k.get("kok_kategori") or ""), []).append(k)
    sira = list(gruplar)
    i = 0
    while len(secilen) < adet and any(gruplar.values()):
        anahtar = sira[i % len(sira)]
        i += 1
        if gruplar[anahtar]:
            secilen.append(gruplar[anahtar].pop(0))
    secili = {k["urun_id"] for k in secilen}
    return [k for k in kayitlar if k["urun_id"] in secili]


def urunleri_oku(con: sqlite3.Connection, *, urun_idleri: Sequence[int] | None = None,
                 sinir: int | None = None, yalniz_eksik: bool = False, cesitli: int | None = None,
                 tohum: int = 1, atla_celiskili: bool = True,
                 celiskili: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    kosul, arg = "", []
    if urun_idleri:
        kosul += f" AND u.id IN ({','.join('?' * len(urun_idleri))})"
        arg += list(urun_idleri)
    if yalniz_eksik:
        kosul += (" AND (SELECT COUNT(DISTINCT a.dil) FROM urun_aciklama a WHERE a.urun_id = u.id"
                  " AND a.dil IN ('tr','en')) < 2")
    ceviri = KategoriCeviri()
    kayitlar = [kayit_olustur(r, ceviri) for r in con.execute(SORGU + kosul + " ORDER BY u.id", arg).fetchall()]
    # ad ile teknik alanları çelişen ürünler (kaynak adı yanlış olabilir) insan kuyruğuna: LLM'e gönderilmez
    saglam = []
    for k in kayitlar:
        neden = tur_celiskisi(k)
        if neden:
            if celiskili is not None:
                celiskili.append({"urun_id": k["urun_id"], "ad": k["ad"], "neden": neden})
            if atla_celiskili:
                continue
        saglam.append(k)
    kayitlar = saglam
    # teknik özelliği (özellik ya da kaynak açıklama) GERÇEKTEN olanlar önce; sıralama kararlı, her grupta id
    kayitlar.sort(key=lambda k: not (k["teknik"] or k["kaynak_aciklama"]))
    if cesitli is not None:
        return cesitli_sec(kayitlar, max(0, cesitli), tohum)
    return kayitlar if sinir is None else kayitlar[:max(0, sinir)]


def parti_yaz(satirlar: list[dict[str, Any]], klasor: Path, parti: int) -> list[Path]:
    klasor.mkdir(parents=True, exist_ok=True)
    for eski in klasor.glob("parti-*.jsonl"):
        eski.unlink()
    yollar = []
    for i in range(0, len(satirlar), parti):
        yol = klasor / f"parti-{i // parti + 1:04d}.jsonl"
        with yol.open("w", encoding="utf-8", newline="\n") as f:
            for s in satirlar[i:i + parti]:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        yollar.append(yol)
    return yollar


def calistir(argv: Sequence[str] | None = None, cikti: TextIO = sys.stdout, hata: TextIO = sys.stderr) -> int:
    p = argparse.ArgumentParser(prog="betikler.aciklama_disa", description=__doc__.splitlines()[0])
    p.add_argument("--db", required=True)
    p.add_argument("--cikis", required=True)
    p.add_argument("--parti", type=int, default=100)
    p.add_argument("--sinir", type=int)
    p.add_argument("--yalniz-eksik", action="store_true")
    p.add_argument("--urun-id", help="virgülle ayrılmış ürün kimlikleri")
    p.add_argument("--cesitli", type=int, help="kategori ve durum kodlarını kapsayan tabakalı örnek (N ürün)")
    p.add_argument("--tohum", type=int, default=1, help="--cesitli için deterministik tohum")
    p.add_argument("--atla-celiskili", action=argparse.BooleanOptionalAction, default=True,
                   help="ad ile teknik alanı çelişen ürünleri atla (celiskili.jsonl'ye yaz); varsayılan açık")
    a = p.parse_args(argv)
    if a.parti < 1:
        print("HATA: --parti en az 1 olmalı.", file=hata)
        return 2
    try:
        idler = [int(x) for x in a.urun_id.split(",") if x.strip()] if a.urun_id else None
    except ValueError:
        print("HATA: --urun-id tam sayıların virgüllü listesi olmalı.", file=hata)
        return 2
    celiskili: list[dict[str, Any]] = []
    try:
        con = salt_okunur_baglan(a.db)
        try:
            satirlar = urunleri_oku(con, urun_idleri=idler, sinir=a.sinir, yalniz_eksik=a.yalniz_eksik,
                                    cesitli=a.cesitli, tohum=a.tohum, atla_celiskili=a.atla_celiskili,
                                    celiskili=celiskili)
        finally:
            con.close()
    except sqlite3.Error as e:
        print(f"HATA: veritabanı okunamadı: {e}", file=hata)
        return 1
    yollar = parti_yaz(satirlar, Path(a.cikis), a.parti)
    with (Path(a.cikis) / "celiskili.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for c in celiskili:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(json.dumps({"urun": len(satirlar), "parti": len(yollar), "celiskili": len(celiskili),
                      "klasor": str(Path(a.cikis))},
                     ensure_ascii=False), file=cikti)
    return 0


if __name__ == "__main__":
    sys.exit(calistir())
