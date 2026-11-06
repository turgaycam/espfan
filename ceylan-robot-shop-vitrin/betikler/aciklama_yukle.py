"""G3d: LLM çıktılarını (cikti-*.jsonl) doğrulayıp urun_aciklama tablosuna yükler.

Kullanım: python -m betikler.aciklama_yukle --db <yol> --girdi <klasör> --model claude-haiku-5-5 [--kuru]
Girdi satırı: {"urun_id": 1, "dil": "tr"|"en", "metin": "..."}.
İki aşama: (1) okuma + doğrulama (yazma kilidi yok), (2) geçenler tek kısa işlemde yazılır. Yalnız satır yoksa ya da
mevcut kaynak 'llm-taslak' ise yazılır (kaynak='kaynak' olan asla ezilmez). Reddedilenler <klasör>/reddedilen.jsonl'ye
({urun_id, dil, nedenler, dosya, satir_no}) yazılır. Ek red kodları: bozuk_json, bozuk_alan, urun_yok (bilinmeyen/pasif),
yinelenen (aynı urun_id+dil ikinci kez), cift_eksik (tr ve en birlikte geçmedi: ikisi de yazılmaz), kaynak_korumali.
Özet `uyari`: ret olmayan heuristik uyarı sayıları (islev_fiili).
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
from app.katalog.aciklama_dogrula import dogrula, uyarilar
from app.katalog.kategori_ceviri import KategoriCeviri
from betikler.aciklama_disa import SORGU, kayit_olustur

_UPSERT = (
    "INSERT INTO urun_aciklama (urun_id, dil, metin, kaynak, model, uretildi) VALUES (?, ?, ?, 'llm-taslak', ?, ?)"
    " ON CONFLICT(urun_id, dil) DO UPDATE SET metin = excluded.metin, kaynak = 'llm-taslak',"
    " model = excluded.model, uretildi = excluded.uretildi WHERE urun_aciklama.kaynak = 'llm-taslak'"
)


def _satirlari_oku(klasor: Path) -> Iterator[tuple[str, int, str]]:
    """(dosya, satır no, ham). Yalnız \\n ile bölünür (JSON içindeki U+2028 vb. satır bölmez); BOM atılır."""
    for yol in sorted(klasor.glob("cikti-*.jsonl")):
        metin = yol.read_bytes().decode("utf-8-sig", errors="replace")
        for no, ham in enumerate(metin.split("\n"), start=1):
            if ham.strip():
                yield yol.name, no, ham.rstrip("\r")


def _coz(ham: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        s = json.loads(ham)
    except ValueError:
        return None, "bozuk_json"
    if (not isinstance(s, dict) or isinstance(s.get("urun_id"), bool) or not isinstance(s.get("urun_id"), int)
            or s.get("dil") not in ("tr", "en") or not isinstance(s.get("metin"), str)):
        return None, "bozuk_alan"
    return s, None


def calistir(argv: Sequence[str] | None = None, cikti: TextIO = sys.stdout, hata: TextIO = sys.stderr) -> int:
    p = argparse.ArgumentParser(prog="betikler.aciklama_yukle", description=__doc__.splitlines()[0])
    p.add_argument("--db", required=True)
    p.add_argument("--girdi", required=True)
    p.add_argument("--model", required=True)
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
    ceviri = KategoriCeviri()
    okunan = 0
    nedenler: Counter[str] = Counter()
    reddedilen: list[dict[str, Any]] = []
    onbellek: dict[int, dict[str, Any] | None] = {}
    gorulen: set[tuple[int, str]] = set()
    uyari: Counter[str] = Counter()
    yazilacak: list[tuple[int, str, str, str | None, int]] = []  # urun_id, dil, metin, dosya, satır no
    zaman = datetime.now(UTC).isoformat(timespec="seconds")

    def reddet(urun_id: Any, dil: Any, kodlar: list[str], dosya: str | None, satir_no: int | None) -> None:
        reddedilen.append({"urun_id": urun_id, "dil": dil, "nedenler": kodlar, "dosya": dosya, "satir_no": satir_no})
        nedenler.update(kodlar)

    yazilan = 0
    try:
        # Aşama 1: oku + doğrula (yazma işlemi yok, kilit tutulmaz)
        for dosya, no, ham in _satirlari_oku(klasor):
            okunan += 1
            s, kod = _coz(ham)
            if s is None:
                reddet(None, None, [kod or "bozuk_json"], dosya, no)
                continue
            uid, dil = s["urun_id"], s["dil"]
            if (uid, dil) in gorulen:
                reddet(uid, dil, ["yinelenen"], dosya, no)
                continue
            gorulen.add((uid, dil))
            if uid not in onbellek:
                r = con.execute(SORGU + " AND u.id = ?", (uid,)).fetchone()
                onbellek[uid] = kayit_olustur(r, ceviri) if r is not None else None
            kayit = onbellek[uid]
            if kayit is None:
                reddet(uid, dil, ["urun_yok"], dosya, no)
                continue
            metin = s["metin"].strip()
            kodlar = dogrula(metin, dil, kayit)
            if kodlar:
                reddet(uid, dil, kodlar, dosya, no)
                continue
            yazilacak.append((uid, dil, metin, dosya, no))

        # Çift kuralı: ürün yalnız tr VE en ikisi de geçtiyse yazılır; aksi halde geçen dil de reddedilir
        diller: dict[int, set[str]] = {}
        for uid, dil, *_ in yazilacak:
            diller.setdefault(uid, set()).add(dil)
        tam = []
        for ogre in yazilacak:
            if diller[ogre[0]] == {"tr", "en"}:
                tam.append(ogre)
            else:
                reddet(ogre[0], ogre[1], ["cift_eksik"], ogre[3], ogre[4])
        yazilacak = tam
        for uid, dil, metin, _d, _n in yazilacak:  # uyarılar ret değildir; yalnız sayılır
            for u in uyarilar(metin, dil, onbellek[uid] or {}):
                uyari[u] += 1

        # Aşama 2: tek kısa işlem (beklenmeyen hata olursa hiçbiri yazılmaz)
        if a.kuru:
            for uid, dil, _m, dosya, no in yazilacak:
                var = con.execute("SELECT kaynak FROM urun_aciklama WHERE urun_id = ? AND dil = ?",
                                  (uid, dil)).fetchone()
                if var is not None and var["kaynak"] != "llm-taslak":
                    reddet(uid, dil, ["kaynak_korumali"], dosya, no)
                else:
                    yazilan += 1
        else:
            # Açık BEGIN: Python'un örtük BEGIN'i ("INSERT" büyük harfli ifadelerde) güvenilir değil; hata olursa geri al.
            con.execute("BEGIN IMMEDIATE")
            try:
                for uid, dil, metin, dosya, no in yazilacak:
                    once = con.total_changes
                    con.execute(_UPSERT, (uid, dil, metin, a.model, zaman))
                    if con.total_changes > once:
                        yazilan += 1
                    else:
                        reddet(uid, dil, ["kaynak_korumali"], dosya, no)
                con.commit()
            except BaseException:
                con.rollback()
                raise
    finally:
        con.close()

    with (klasor / "reddedilen.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for x in reddedilen:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print(json.dumps({"kuru": a.kuru, "okunan": okunan, "yazilan": yazilan, "reddedilen": len(reddedilen),
                      "nedenler": dict(sorted(nedenler.items())), "uyari": dict(sorted(uyari.items()))}, ensure_ascii=False), file=cikti)
    return 0


if __name__ == "__main__":
    sys.exit(calistir())
