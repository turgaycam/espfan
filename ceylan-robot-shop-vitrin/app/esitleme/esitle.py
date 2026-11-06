"""Katalog eşitleme turu: kaynak API -> esitleme_ara -> urun/kategori (tam ya da eksik)."""
import gc
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from app.esitleme.gorsel import base64_kaydet, eski_gecicileri_sil, kisa_yol_mu, yetim_sil
from app.esitleme.kaynak import KaynakHatasi, KaynakIstemci
from app.esitleme.teknik import bolum_metinleri, durum_cikar, teknik_cikar, teknik_json
from app.fiyat.kurallar import Bantlar, teklif_zorunlu_mu, temsili_fiyat_eur
from app.katalog.indeks import indeksi_yeniden_kur
from app.metin import metin_temizle
from app.para import yuvarla

SAYFA_BOYU = 20
SAYFA_SINIRI = 1000   # sonsuz döngü emniyeti: 1000*20 = 20.000 kayıt


@dataclass(frozen=True)
class TurSonucu:
    durum: Literal["tam", "eksik", "hata"]
    api_toplam: int | None
    cekilen: int
    eklenen: int
    guncellenen: int
    pasiflenen: int
    hata: str | None
    bozuk: int = 0


# ---------- eşleme ----------

def _ondalik(x: Any) -> Decimal:
    if isinstance(x, bool) or x is None:
        raise TypeError("sayı değil")
    d = Decimal(str(x))
    if not d.is_finite():
        raise ValueError("sonlu sayı değil")
    return d


def _metin(x: Any) -> str | None:
    """API'den gelen metin alanını temizler; metin değilse None."""
    return metin_temizle(x) if isinstance(x, str) else None


def _oran_metni(x: Decimal) -> str:
    if x == x.to_integral_value():
        return str(int(x))
    return str(x.normalize())


def _gorsel_url(kayit: dict, taban: str, gorsel_dizin: Path | None) -> str | None:
    gorseller = kayit.get("images")
    if not isinstance(gorseller, list) or not gorseller or not isinstance(gorseller[0], str):
        return None
    ham = gorseller[0]
    if ham.lstrip().startswith(("http://", "https://")) or kisa_yol_mu(ham):
        yol = _metin(ham)
        if not yol:
            return None
        if yol.startswith(("http://", "https://")):
            return yol
        return taban + yol
    return base64_kaydet(ham, gorsel_dizin)   # base64: dosyaya yazılır, alana yalnız "gorsel:<ad>" girer


_VERI_HATALARI = (ValueError, TypeError, KeyError, InvalidOperation, UnicodeError, OverflowError)


def _kimlik(kayit: Any, konum: str) -> str:
    if isinstance(kayit, dict):
        for alan in ("sku", "_id"):
            v = kayit.get(alan)
            if isinstance(v, str) and v.strip():
                return (metin_temizle(v) or konum)[:40]
    return konum


def _urun_esle(kayit: Any, taban: str, konum: str = "?",
               gorsel_dizin: Path | None = None) -> tuple[dict | None, str | None]:
    """API kaydını ara tablo biçimine çevirir. Zorunlu alan eksik/bozuksa ya da veri kaynaklı
    bir hata çıkarsa (None, "<kimlik>:<neden>") döner; programlama hataları yakalanmaz."""
    try:
        u = _urun_esle_ic(kayit, taban, gorsel_dizin)
        if u is not None:
            json.dumps(u, ensure_ascii=False).encode("utf-8")   # kodlanamayan kayıt bozuk sayılır
    except _VERI_HATALARI as e:
        return None, f"{_kimlik(kayit, konum)}:{type(e).__name__}"
    if u is None:
        return None, f"{_kimlik(kayit, konum)}:eksik_alan"
    return u, None


def _urun_esle_ic(kayit: Any, taban: str, gorsel_dizin: Path | None = None) -> dict | None:
    if not isinstance(kayit, dict):
        return None
    sku = _metin(kayit.get("sku"))
    ad = _metin(kayit.get("name"))
    kategori = kayit.get("categoryId")
    fiyat = kayit.get("price")
    if not sku or not ad:
        return None
    kategori_id = _metin(kategori.get("_id")) if isinstance(kategori, dict) else None
    if not kategori_id:
        return None
    if not isinstance(fiyat, dict) or "amount" not in fiyat:
        return None
    nitelik = kayit.get("attributes") if isinstance(kayit.get("attributes"), dict) else {}
    try:
        kaynak_fiyat = _ondalik(fiyat["amount"])
        kdv = _ondalik(nitelik.get("vatRate", 20))
        stok = int(kayit.get("stock") or 0)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if kaynak_fiyat < 0 or kdv < 0:
        return None
    uretici = _metin(nitelik.get("manufacturerCode"))
    guncelleme = _metin(kayit.get("updatedAt"))
    kategori_yol = _metin(kategori.get("path")) or ""
    teknik = teknik_cikar(kayit, ad)   # G3b: güvenli düz metin (≤ 8 KB); base64/HTML burada atılır
    durum = durum_cikar(ad, [m for b in bolum_metinleri(kayit) for m in b])
    return {
        "sku": sku,
        "ad": ad,
        "uretici_kodu": uretici or None,
        "kdv_orani": _oran_metni(kdv),
        "stok": max(stok, 0),
        "gorsel_url": _gorsel_url(kayit, taban, gorsel_dizin),
        "kaynak_fiyat_eur": str(yuvarla(kaynak_fiyat)),
        "kategori_kaynak_id": kategori_id,
        "kategori_yol": kategori_yol,
        "kaynak_guncelleme": guncelleme,
        "teknik": teknik_json(teknik) if teknik else None,
        "durum": durum,
    }


def _kategori_esle(k: Any) -> dict | None:
    try:
        return _kategori_esle_ic(k)
    except _VERI_HATALARI:
        return None


def _kategori_esle_ic(k: Any) -> dict | None:
    if not isinstance(k, dict):
        return None
    kaynak_id, ad, yol = _metin(k.get("_id")), _metin(k.get("name")), _metin(k.get("path"))
    if not kaynak_id or not ad or not yol:
        return None
    ust = _metin(k.get("parentId"))
    seviye = k.get("level")
    erp = k.get("erpId")
    sonuc = {
        "kaynak_id": kaynak_id,
        "erp_id": erp if isinstance(erp, int) and not isinstance(erp, bool) else None,
        "ad": ad,
        "ust_kaynak_id": ust or None,
        "yol": yol,
        "seviye": seviye if isinstance(seviye, int) and not isinstance(seviye, bool) else yol.count("."),
        "aktif": 0 if k.get("isActive") is False else 1,
    }
    json.dumps(sonuc, ensure_ascii=False).encode("utf-8")
    return sonuc


# ---------- yazma ----------

def _kategorileri_yaz(con: sqlite3.Connection, kategoriler: list[dict], pasifle: bool) -> None:
    con.executemany(
        "INSERT INTO kategori (kaynak_id, erp_id, ad, ust_kaynak_id, yol, seviye, aktif)"
        " VALUES (:kaynak_id, :erp_id, :ad, :ust_kaynak_id, :yol, :seviye, :aktif)"
        " ON CONFLICT(kaynak_id) DO UPDATE SET erp_id=excluded.erp_id, ad=excluded.ad,"
        " ust_kaynak_id=excluded.ust_kaynak_id, yol=excluded.yol, seviye=excluded.seviye,"
        " aktif=excluded.aktif",
        kategoriler,
    )
    if pasifle:
        kimlikler = [k["kaynak_id"] for k in kategoriler]
        yer = ",".join("?" * len(kimlikler)) or "''"
        con.execute(f"UPDATE kategori SET aktif=0 WHERE kaynak_id NOT IN ({yer})", kimlikler)


def _urunleri_yaz(con: sqlite3.Connection, bantlar: Bantlar, kok_adlari: dict[str, str],
                  zaman: str) -> tuple[int, int]:
    mevcut = {r[0] for r in con.execute("SELECT sku FROM urun")}
    kategori_id = {r[0]: r[1] for r in con.execute("SELECT kaynak_id, id FROM kategori")}
    eklenen = guncellenen = 0
    for (veri,) in con.execute("SELECT veri FROM esitleme_ara ORDER BY sku").fetchall():
        u = json.loads(veri)
        kok_ad = kok_adlari.get(u["kategori_yol"].split(".")[0], "")
        kaynak_fiyat = Decimal(u["kaynak_fiyat_eur"])
        durum, teknik = u.get("durum"), u.get("teknik")
        if kaynak_fiyat > 0:
            net, temsili = kaynak_fiyat, 0
        else:
            net, temsili = temsili_fiyat_eur(u["sku"], kok_ad, bantlar), 1
        con.execute(
            "INSERT INTO urun (sku, ad, uretici_kodu, kategori_id, kok_kategori_ad, kdv_orani, stok,"
            " gorsel_url, kaynak_fiyat_eur, temsili_fiyat_eur, fiyat_temsili, teklif_zorunlu, aktif,"
            " kaynak_guncelleme, olusturma, durum_kodu, durum_ornek, durum_kaynak)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, 0, ?)"
            " ON CONFLICT(sku) DO UPDATE SET ad=excluded.ad, uretici_kodu=excluded.uretici_kodu,"
            " kategori_id=excluded.kategori_id, kok_kategori_ad=excluded.kok_kategori_ad,"
            " kdv_orani=excluded.kdv_orani, stok=excluded.stok, gorsel_url=excluded.gorsel_url,"
            " kaynak_fiyat_eur=excluded.kaynak_fiyat_eur, temsili_fiyat_eur=excluded.temsili_fiyat_eur,"
            " fiyat_temsili=excluded.fiyat_temsili, teklif_zorunlu=excluded.teklif_zorunlu, aktif=1,"
            " kaynak_guncelleme=excluded.kaynak_guncelleme,"
            # G3b: kaynak metninden çıkarılan durum yazılır (örnek işareti kalkar, durum_kaynak='cikarim'). Çıkarım
            # yoksa: önceki değer eşitlemenin çıkarımıysa geri alınır (kural/kaynak değişti), değilse (varsayılan,
            # örnek, elle) korunur.
            " durum_kodu=CASE WHEN ? IS NOT NULL THEN excluded.durum_kodu"
            " WHEN urun.durum_kaynak = 'cikarim' THEN 'belirtilmemis' ELSE urun.durum_kodu END,"
            " durum_ornek=CASE WHEN ? IS NOT NULL THEN 0 ELSE urun.durum_ornek END,"
            " durum_kaynak=CASE WHEN ? IS NOT NULL THEN 'cikarim'"
            " WHEN urun.durum_kaynak = 'cikarim' THEN NULL ELSE urun.durum_kaynak END",
            (
                u["sku"], u["ad"], u["uretici_kodu"], kategori_id.get(u["kategori_kaynak_id"]),
                kok_ad, u["kdv_orani"], u["stok"], u["gorsel_url"], u["kaynak_fiyat_eur"],
                str(net), temsili, int(teklif_zorunlu_mu(kok_ad, net, bantlar)),
                u["kaynak_guncelleme"], zaman, durum or "belirtilmemis", "cikarim" if durum else None,
                durum, durum, durum,
            ),
        )
        if teknik:
            con.execute(
                "INSERT INTO urun_teknik (urun_id, veri) SELECT id, ? FROM urun WHERE sku = ?"
                " ON CONFLICT(urun_id) DO UPDATE SET veri = excluded.veri", (teknik, u["sku"]))
        else:
            con.execute("DELETE FROM urun_teknik WHERE urun_id = (SELECT id FROM urun WHERE sku = ?)", (u["sku"],))
        if u["sku"] in mevcut:
            guncellenen += 1
        else:
            eklenen += 1
    return eklenen, guncellenen


# ---------- tur ----------

def esitle(con: sqlite3.Connection, kaynak: KaynakIstemci, bantlar: Bantlar,
           simdi: Callable[[], datetime], gorsel_dizin: Path | None = None) -> TurSonucu:
    with con:
        gid = con.execute(
            "INSERT INTO esitleme_gunlugu (basla, durum) VALUES (?, 'calisiyor')",
            (simdi().isoformat(),),
        ).lastrowid

    api_toplam: int | None = None
    cekilen = bozuk = 0
    bozuk_ornek: list[str] = []
    try:
        if gorsel_dizin is not None:
            eski_gecicileri_sil(gorsel_dizin)
        kategoriler = [k for k in map(_kategori_esle, kaynak.kategoriler()) if k is not None]
        if not kategoriler:
            raise KaynakHatasi("kategori listesi boş")
        kok_adlari = {k["yol"]: k["ad"] for k in kategoriler if k["seviye"] == 0}

        with con:
            con.execute("DELETE FROM esitleme_ara")
        ilk_toplam: int | None = None
        son_toplam: int | None = None
        alinamayan: list[int] = []
        gorulen = 0
        sayfa = 1
        while sayfa <= SAYFA_SINIRI:
            try:
                veri, toplam = kaynak.urun_sayfasi(sayfa, SAYFA_BOYU)
            except KaynakHatasi:
                if sayfa == 1:
                    raise
                alinamayan.append(sayfa)
                gorulen += SAYFA_BOYU
                sayfa += 1
                if son_toplam is not None and gorulen >= son_toplam:
                    break
                continue
            if ilk_toplam is None:
                ilk_toplam = toplam
            son_toplam = toplam
            if not veri:
                break
            gorulen += len(veri)
            satirlar = []
            for sira, kayit in enumerate(veri, 1):
                u, neden = _urun_esle(kayit, kaynak.taban, f"s{sayfa}#{sira}", gorsel_dizin)
                if u is None:
                    bozuk += 1
                    if len(bozuk_ornek) < 5:
                        bozuk_ornek.append(neden)
                    continue
                cekilen += 1
                satirlar.append((u["sku"], json.dumps(u, ensure_ascii=False)))
            with con:
                con.executemany(
                    "INSERT OR REPLACE INTO esitleme_ara (sku, veri) VALUES (?, ?)", satirlar
                )
            # base64'lü sayfa bir sonraki istekten önce bırakılır. httpx 0.27'de Response.stream ->
            # BoundSyncStream._response -> Response döngüsü yanıt gövdesini (sayfa başına ~4 MB)
            # çöp toplayıcıya bırakır; close() döngüyü kırmaz, bu yüzden açıkça toplanır
            del veri, satirlar
            gc.collect()
            if gorulen >= toplam:
                break
            sayfa += 1
        api_toplam = son_toplam

        benzersiz = con.execute("SELECT COUNT(*) FROM esitleme_ara").fetchone()[0]
        # K1: bozuk kayıtlar da kaynakta "görülmüş" sayılır
        tam = not alinamayan and benzersiz + bozuk == ilk_toplam == son_toplam
        pasiflenen = 0
        with con:
            _kategorileri_yaz(con, kategoriler, pasifle=tam)
            eklenen, guncellenen = _urunleri_yaz(con, bantlar, kok_adlari, simdi().isoformat())
            if tam:
                pasiflenen = con.execute(
                    "UPDATE urun SET aktif=0 WHERE aktif=1"
                    " AND sku NOT IN (SELECT sku FROM esitleme_ara)"
                ).rowcount
            indeksi_yeniden_kur(con)
        if tam and gorsel_dizin is not None:
            yetim_sil(con, gorsel_dizin)

        notlar = []
        if bozuk:
            notlar.append(f"bozuk_kayit: {bozuk} [{', '.join(bozuk_ornek)}]")
        if alinamayan:
            notlar.append("alinamayan_sayfa: " + ",".join(map(str, alinamayan)))
        hata_notu = "; ".join(notlar)[:500] or None
        sonuc = TurSonucu("tam" if tam else "eksik", api_toplam, cekilen, eklenen,
                          guncellenen, pasiflenen, hata_notu, bozuk)
    except Exception as e:  # noqa: BLE001 — tur hiçbir koşulda çökmez, günlüğe yazılır
        sonuc = TurSonucu("hata", api_toplam, cekilen, 0, 0, 0,
                          f"{type(e).__name__}: {e}"[:500], bozuk)

    with con:
        con.execute(
            "UPDATE esitleme_gunlugu SET bitis=?, durum=?, api_toplam=?, cekilen=?, eklenen=?,"
            " guncellenen=?, pasiflenen=?, bozuk=?, hata=? WHERE id=?",
            (simdi().isoformat(), sonuc.durum, sonuc.api_toplam, sonuc.cekilen, sonuc.eklenen,
             sonuc.guncellenen, sonuc.pasiflenen, sonuc.bozuk, sonuc.hata, gid),
        )
    return sonuc


def son_basarili_esitleme(con: sqlite3.Connection) -> datetime | None:
    satir = con.execute(
        "SELECT bitis FROM esitleme_gunlugu WHERE durum='tam' AND bitis IS NOT NULL"
        " ORDER BY bitis DESC, id DESC LIMIT 1"
    ).fetchone()
    return datetime.fromisoformat(satir[0]) if satir else None


def son_esitleme(con: sqlite3.Connection) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM esitleme_gunlugu ORDER BY id DESC LIMIT 1").fetchone()
