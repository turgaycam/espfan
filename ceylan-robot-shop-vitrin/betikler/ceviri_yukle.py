"""G3f: LLM çeviri çıktılarını (cikti-*.jsonl) doğrulayıp urun_ceviri tablosuna (dil='en') yükler.

Kullanım: python -m betikler.ceviri_yukle --db <yol> --girdi <klasör> --model claude-haiku-5-5 --ret <klasör> [--kuru]
Girdi satırı: {"urun_id": 1, "ad_en": "...", "teknik_en": [[anahtar_en, değer_en], ...] | null}
  teknik_en null (ya da yok): yalnız ad çevrildi; mevcut teknik çevirisi, kaynak özeti aynıysa korunur.
İki aşama: (1) okuma + doğrulama (app.katalog.ceviri_dogrula; yazma kilidi yok), (2) geçenler tek işlemde
(BEGIN IMMEDIATE) yazılır ve arama indeksindeki EN ad (urun_ara.ad_en) güncellenir. kaynak_ozet yükleme anındaki
DB verisinden (TR ad + teknik satırları) hesaplanır. kaynak='kaynak' satırı asla ezilmez.
Reddedilenler <ret>/reddedilen.jsonl'ye ({urun_id, nedenler, dosya, satir_no}) yazılır (girdi klasörüne yazılmaz).
Ek red kodları: bozuk_json, bozuk_alan, urun_yok (bilinmeyen/pasif), yinelenen (aynı urun_id ikinci kez),
kaynak_korumali, kaynak_degisti (aşama 1 ile yazma arasında eşitleme TR ad/teknik veriyi değiştirdi: yazma işlemi
içinde özet yeniden hesaplanır). Özet (stdout, tek satır JSON): {kuru, okunan, yazilan, reddedilen, nedenler, uyari}
(uyari: ret olmayan sayımlar, ör. binlik_ayrac).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from app.db import baglan
from app.katalog.ceviri_dogrula import dogrula, uyarilar
from app.katalog.indeks import ad_en_guncelle
from app.katalog.urun_ceviri import kaynak_ozeti, teknik_satirlari

_URUN = ("SELECT u.id, u.ad, t.veri FROM urun u LEFT JOIN urun_teknik t ON t.urun_id = u.id"
         " WHERE u.aktif = 1 AND u.id = ?")
# teknik_json NULL gelirse (yalnız ad) ve kaynak özeti değişmediyse mevcut teknik çevirisi korunur
_UPSERT = (
    "INSERT INTO urun_ceviri (urun_id, dil, ad, teknik_json, kaynak, model, kaynak_ozet, uretildi)"
    " VALUES (?, 'en', ?, ?, 'llm-taslak', ?, ?, ?)"
    " ON CONFLICT(urun_id, dil) DO UPDATE SET ad = excluded.ad,"
    " teknik_json = CASE WHEN excluded.teknik_json IS NULL AND urun_ceviri.kaynak_ozet = excluded.kaynak_ozet"
    " THEN urun_ceviri.teknik_json ELSE excluded.teknik_json END,"
    " model = excluded.model, kaynak_ozet = excluded.kaynak_ozet, uretildi = excluded.uretildi"
    " WHERE urun_ceviri.kaynak = 'llm-taslak'"
)


def _satirlari_oku(klasor: Path) -> Iterator[tuple[str, int, str]]:
    """(dosya, satır no, ham). Yalnız \\n ile bölünür; BOM atılır."""
    for yol in sorted(klasor.glob("cikti-*.jsonl")):
        metin = yol.read_bytes().decode("utf-8-sig", errors="replace")
        for no, ham in enumerate(metin.split("\n"), start=1):
            if ham.strip():
                yield yol.name, no, ham.rstrip("\r")


def _cift_listesi(x: object) -> bool:
    return isinstance(x, list) and all(
        isinstance(p, list) and len(p) == 2 and all(isinstance(e, str) for e in p) for p in x)


def _coz(ham: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        s = json.loads(ham)
    except ValueError:
        return None, "bozuk_json"
    if (not isinstance(s, dict) or isinstance(s.get("urun_id"), bool) or not isinstance(s.get("urun_id"), int)
            or not isinstance(s.get("ad_en"), str)
            or not (s.get("teknik_en") is None or _cift_listesi(s.get("teknik_en")))):
        return None, "bozuk_alan"
    return s, None


Yazilacak = tuple[int, str, str | None, str, str, int]   # urun_id, ad_en, teknik_json, kaynak_ozet, dosya, satır no


def _asama1(con, klasor: Path, reddet, uyari: Counter) -> tuple[int, list[Yazilacak]]:
    """Girdi satırlarını okur ve doğrular (kilitsiz). (okunan, yazılacaklar) döner; retler `reddet` ile bildirilir."""
    okunan = 0
    gorulen: set[int] = set()
    yazilacak: list[Yazilacak] = []
    for dosya, no, ham in _satirlari_oku(klasor):
        okunan += 1
        s, kod = _coz(ham)
        if s is None:
            reddet(None, [kod or "bozuk_json"], dosya, no)
            continue
        uid = s["urun_id"]
        if uid in gorulen:
            reddet(uid, ["yinelenen"], dosya, no)
            continue
        gorulen.add(uid)
        r = con.execute(_URUN, (uid,)).fetchone()
        if r is None:
            reddet(uid, ["urun_yok"], dosya, no)
            continue
        teknik = teknik_satirlari(r["veri"])
        ad_en = s["ad_en"].strip()
        teknik_en = s.get("teknik_en")
        if teknik_en is not None:
            teknik_en = [[k.strip(), v.strip()] for k, v in teknik_en]
        kaynak = {"ad": r["ad"], "teknik": teknik}
        kodlar = dogrula(kaynak, {"ad_en": ad_en, "teknik_en": teknik_en})
        if kodlar:
            reddet(uid, kodlar, dosya, no)
            continue
        uyari.update(uyarilar(kaynak))     # ret değil; yalnız sayılır (M-4: binlik ayraç)
        teknik_json = json.dumps(teknik_en, ensure_ascii=False) if teknik_en else None
        yazilacak.append((uid, ad_en, teknik_json, kaynak_ozeti(r["ad"], teknik), dosya, no))
    return okunan, yazilacak


def calistir(argv: Sequence[str] | None = None, cikti: TextIO = sys.stdout, hata: TextIO = sys.stderr) -> int:
    p = argparse.ArgumentParser(prog="betikler.ceviri_yukle", description=__doc__.splitlines()[0])
    p.add_argument("--db", required=True)
    p.add_argument("--girdi", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--ret", required=True, help="reddedilen.jsonl'nin yazılacağı klasör (girdi klasöründen ayrı)")
    p.add_argument("--kuru", action="store_true", help="yalnız doğrula, yazma")
    a = p.parse_args(argv)
    klasor = Path(a.girdi)
    if not klasor.is_dir():
        print(f"HATA: girdi klasörü yok: {klasor}", file=hata)
        return 1
    if not Path(a.db).is_file():
        print(f"HATA: veritabanı yok: {a.db}", file=hata)
        return 1

    con = baglan(Path(a.db))
    yazilan = 0
    uyari: Counter[str] = Counter()
    nedenler: Counter[str] = Counter()
    reddedilen: list[dict[str, Any]] = []
    zaman = datetime.now(UTC).isoformat(timespec="seconds")

    def reddet(urun_id: Any, kodlar: list[str], dosya: str | None, satir_no: int | None) -> None:
        reddedilen.append({"urun_id": urun_id, "nedenler": kodlar, "dosya": dosya, "satir_no": satir_no})
        nedenler.update(kodlar)

    try:
        # Aşama 1: oku + doğrula (yazma işlemi yok, kilit tutulmaz)
        okunan, yazilacak = _asama1(con, klasor, reddet, uyari)

        # Aşama 2: tek kısa işlem (beklenmeyen hata olursa hiçbiri yazılmaz)
        if a.kuru:
            for uid, *_, dosya, no in yazilacak:
                var = con.execute("SELECT kaynak FROM urun_ceviri WHERE urun_id = ? AND dil = 'en'", (uid,)).fetchone()
                if var is not None and var["kaynak"] != "llm-taslak":
                    reddet(uid, ["kaynak_korumali"], dosya, no)
                else:
                    yazilan += 1
        else:
            con.execute("BEGIN IMMEDIATE")
            try:
                for uid, ad_en, teknik_json, ozet, dosya, no in yazilacak:
                    # I-2: aşama 1'den sonra eşitleme adı/teknik veriyi değiştirdiyse (ya da ürün pasifleştiyse)
                    # doğrulanan çeviri bayattır: kilit altında yeniden okunur, yazılmaz.
                    r = con.execute(_URUN, (uid,)).fetchone()
                    if r is None or kaynak_ozeti(r["ad"], teknik_satirlari(r["veri"])) != ozet:
                        reddet(uid, ["kaynak_degisti"], dosya, no)
                        continue
                    once = con.total_changes
                    con.execute(_UPSERT, (uid, ad_en, teknik_json, a.model, ozet, zaman))
                    if con.total_changes > once:
                        ad_en_guncelle(con, uid, ad_en)
                        yazilan += 1
                    else:
                        reddet(uid, ["kaynak_korumali"], dosya, no)
                con.commit()
            except BaseException:
                con.rollback()
                raise
    finally:
        con.close()

    ret = Path(a.ret)
    ret.mkdir(parents=True, exist_ok=True)
    with (ret / "reddedilen.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for x in reddedilen:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print(json.dumps({"kuru": a.kuru, "okunan": okunan, "yazilan": yazilan, "reddedilen": len(reddedilen),
                      "nedenler": dict(sorted(nedenler.items())), "uyari": dict(sorted(uyari.items()))},
                     ensure_ascii=False), file=cikti)
    return 0


if __name__ == "__main__":
    sys.exit(calistir())
