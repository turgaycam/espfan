"""Teklif isteği: kayıt, numara, listeleme ve yönetici durum geçişleri. Commit yapmaz."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from app.hesap.dogrulama import eposta_gecerli, telefon_gecerli   # G3a N-4: kayıt, teklif ve hızlı talep ortak
from app.siparis.servis import ISTANBUL, GecersizGecis

TEKLIF_GECISLERI: dict[str, set[str]] = {
    "yeni": {"inceleniyor", "kapandi"},
    "inceleniyor": {"teklif_verildi", "kapandi"},
    "teklif_verildi": {"kapandi"},
    "kapandi": set(),
}
MESAJ_MAX = 2000
ADET_MAX = 9999
ACILIYETLER = ("acil", "bu_hafta", "planli")   # G3i madde 16: hızlı talep aciliyeti
KALEM_MAX = 100         # G3g madde 2 / inceleme I-2: sepetten gelen teklifte en çok 100 kalem (fazlası açıkça bildirilir)

_TEKLIF_SQL = "SELECT t.*, u.ad AS urun_ad FROM teklif t LEFT JOIN urun u ON u.id = t.urun_id"


@dataclass(frozen=True)
class TeklifGirdisi:
    ad: str
    eposta: str | None          # G3c: e-posta ya da telefondan en az biri zorunlu
    ulke: str
    mesaj: str
    firma: str | None = None
    telefon: str | None = None
    urun_id: int | None = None
    adet: int = 1
    musteri_id: int | None = None
    vat_id: str | None = None   # biçimi web katmanında (hesap.dogrulama.vat_id_kontrol) normalize edilir
    kvkk_onay: str | None = None  # misafir gönderimde onay zamanı (ISO)
    # G3e madde 17: isteğe bağlı alanlar (biçimleri web katmanında denetlenir)
    vkn: str | None = None
    vergi_dairesi: str | None = None
    istenen_tarih: str | None = None    # YYYY-MM-DD
    hedef_fiyat: str | None = None
    parca_kodu: str | None = None
    kalemler: tuple[tuple[int, int], ...] = ()   # G3g madde 2: (urun_id, adet); sepetten gelen çok kalemli teklif
    musteri_po: str | None = None   # G3i madde 6: satın alma (PO) numarası (≤ 40, web katmanı denetler)
    teslim_adresi: str | None = None   # G3j madde 16: DAP navlunu için teslim adresi / posta kodu (≤ 200)


@dataclass(frozen=True)
class TeklifKalemi:
    urun_id: int
    ad: str
    kod: str            # parça no: üretici kodu, yoksa SKU
    adet: int


@dataclass(frozen=True)
class Teklif:
    id: int
    no: str
    ad: str
    firma: str | None
    eposta: str | None
    telefon: str | None
    ulke: str
    urun_id: int | None
    urun_ad: str | None
    adet: int
    mesaj: str
    durum: str
    olusturma: datetime
    musteri_id: int | None
    vat_id: str | None = None
    vkn: str | None = None
    vergi_dairesi: str | None = None
    istenen_tarih: str | None = None
    hedef_fiyat: str | None = None
    parca_kodu: str | None = None
    kalemler: tuple[TeklifKalemi, ...] = ()
    musteri_po: str | None = None
    aciliyet: str | None = None     # G3i madde 16: hızlı talep ('acil' | 'bu_hafta' | 'planli')
    model: str | None = None        # G3i madde 16: robot/kontrolör modeli
    teslim_adresi: str | None = None   # G3j madde 16


class TeklifHatasi(ValueError):
    def __init__(self, alan: str, kod: str):
        super().__init__(f"{alan}:{kod}")
        self.alan = alan
        self.kod = kod


def _temiz(s: str | None) -> str | None:
    if s is None:
        return None
    s = s.strip()
    return s or None


def _zorunlu(alan: str, deger: str | None) -> str:
    d = _temiz(deger)
    if d is None:
        raise TeklifHatasi(alan, "zorunlu")
    return d


def _yeni_no(con: sqlite3.Connection, simdi: datetime) -> str:
    onek = f"CR-TKL-{simdi.astimezone(ISTANBUL):%Y%m%d}-"       # K15: gün İstanbul saatine göre
    son = con.execute(
        "SELECT MAX(CAST(substr(no, ?) AS INTEGER)) FROM teklif WHERE no LIKE ?",
        (len(onek) + 1, onek + "%"),
    ).fetchone()[0]
    return f"{onek}{(son or 0) + 1:04d}"


def _kalemler(con: sqlite3.Connection, teklif_idleri: list[int]) -> dict[int, tuple[TeklifKalemi, ...]]:
    if not teklif_idleri:
        return {}
    sonuc: dict[int, list[TeklifKalemi]] = {}
    for i in range(0, len(teklif_idleri), 500):
        parca = teklif_idleri[i:i + 500]
        for r in con.execute(
            "SELECT k.teklif_id, k.urun_id, k.adet, u.ad, COALESCE(NULLIF(u.uretici_kodu, ''), u.sku) AS kod"
            f" FROM teklif_kalem k JOIN urun u ON u.id = k.urun_id WHERE k.teklif_id IN ({','.join('?' * len(parca))})"
            " ORDER BY k.rowid", parca):
            sonuc.setdefault(r["teklif_id"], []).append(TeklifKalemi(r["urun_id"], r["ad"], r["kod"], r["adet"]))
    return {k: tuple(v) for k, v in sonuc.items()}


def _teklif(r: sqlite3.Row, kalemler: tuple[TeklifKalemi, ...] = ()) -> Teklif:
    return Teklif(
        id=r["id"], no=r["no"], ad=r["ad"], firma=r["firma"], eposta=r["eposta"], telefon=r["telefon"],
        ulke=r["ulke"], urun_id=r["urun_id"], urun_ad=r["urun_ad"], adet=r["adet"], mesaj=r["mesaj"],
        durum=r["durum"], olusturma=datetime.fromisoformat(r["olusturma"]), musteri_id=r["musteri_id"],
        vat_id=r["vat_id"], vkn=r["vkn"], vergi_dairesi=r["vergi_dairesi"], istenen_tarih=r["istenen_tarih"],
        hedef_fiyat=r["hedef_fiyat"], parca_kodu=r["parca_kodu"], kalemler=kalemler,
        musteri_po=r["musteri_po"], aciliyet=r["aciliyet"], model=r["model"], teslim_adresi=r["teslim_adresi"],
    )


def _teklif_getir(con: sqlite3.Connection, teklif_id: int) -> Teklif | None:
    r = con.execute(_TEKLIF_SQL + " WHERE t.id = ?", (teklif_id,)).fetchone()
    return _teklif(r, _kalemler(con, [teklif_id]).get(teklif_id, ())) if r is not None else None


def teklif_no_ile(con: sqlite3.Connection, no: str) -> Teklif | None:
    """G3g madde 26: teklif numarasıyla (hesabım detay ve onay sayfası; sahiplik çağıranda denetlenir)."""
    r = con.execute("SELECT id FROM teklif WHERE no = ?", (no,)).fetchone()
    return _teklif_getir(con, r["id"]) if r is not None else None


def teklif_olustur(con: sqlite3.Connection, g: TeklifGirdisi, simdi: datetime) -> Teklif:
    ad = _zorunlu("ad", g.ad)
    eposta, telefon = _temiz(g.eposta), _temiz(g.telefon)
    if eposta is None and telefon is None:
        raise TeklifHatasi("eposta", "iletisim_gerekli")
    if eposta is not None and not eposta_gecerli(eposta):
        raise TeklifHatasi("eposta", "gecersiz")
    if telefon is not None and not telefon_gecerli(telefon):
        raise TeklifHatasi("telefon", "telefon_gecersiz")
    ulke = _zorunlu("ulke", g.ulke).upper()
    mesaj = _zorunlu("mesaj", g.mesaj)
    if len(mesaj) > MESAJ_MAX:
        raise TeklifHatasi("mesaj", "cok_uzun")
    if isinstance(g.adet, bool) or not isinstance(g.adet, int) or not 1 <= g.adet <= ADET_MAX:
        raise TeklifHatasi("adet", "gecersiz")
    if g.urun_id is not None and con.execute("SELECT 1 FROM urun WHERE id = ?", (g.urun_id,)).fetchone() is None:
        raise TeklifHatasi("urun_id", "gecersiz")
    if g.musteri_id is not None and con.execute(
        "SELECT 1 FROM musteri WHERE id = ?", (g.musteri_id,)
    ).fetchone() is None:
        raise TeklifHatasi("musteri_id", "gecersiz")
    if len(g.kalemler) > KALEM_MAX:
        raise TeklifHatasi("kalemler", "kalem_cok")
    for urun_id, adet in g.kalemler:
        if isinstance(adet, bool) or not isinstance(adet, int) or not 1 <= adet <= ADET_MAX:
            raise TeklifHatasi("kalemler", "adet_araligi")
        if con.execute("SELECT 1 FROM urun WHERE id = ?", (urun_id,)).fetchone() is None:
            raise TeklifHatasi("kalemler", "gecersiz")
    cur = con.execute(
        "INSERT INTO teklif (no, musteri_id, ad, firma, eposta, telefon, ulke, urun_id, adet, mesaj, durum, "
        "olusturma, vat_id, kvkk_onay, vkn, vergi_dairesi, istenen_tarih, hedef_fiyat, parca_kodu, musteri_po,"
        " teslim_adresi) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'yeni', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            _yeni_no(con, simdi), g.musteri_id, ad, _temiz(g.firma), eposta, telefon, ulke,
            g.urun_id, g.adet, mesaj, simdi.isoformat(), _temiz(g.vat_id), _temiz(g.kvkk_onay),
            _temiz(g.vkn), _temiz(g.vergi_dairesi), _temiz(g.istenen_tarih), _temiz(g.hedef_fiyat),
            _temiz(g.parca_kodu), _temiz(g.musteri_po), _temiz(g.teslim_adresi),
        ),
    )
    con.executemany("INSERT INTO teklif_kalem (teklif_id, urun_id, adet) VALUES (?, ?, ?)",
                    [(cur.lastrowid, u, a) for u, a in g.kalemler])
    return _teklif_getir(con, cur.lastrowid)


def hizli_teklif_olustur(con: sqlite3.Connection, *, ad: str, iletisim: str, parca_kodu: str, ulke: str,
                         mesaj: str, simdi: datetime, musteri_id: int | None = None, adet: int = 1,
                         aciliyet: str | None = None, model: str | None = None,
                         urun_id: int | None = None) -> Teklif:
    """G3a madde 9: liste boş sonucundaki 3 alanlı kısa talep (ad, telefon ya da e-posta, parça kodu).
    İletişim '@' içeriyorsa e-posta, değilse telefon sayılır (en az 7 rakam); telefonla gelen talepte eposta NULL
    (G3c, 007 geçişi). Biçim kuralı web katmanında da hız sınırından ÖNCE uygulanır (iletisim_ayir). G3j madde 1:
    parça kodu katalogda tek ürüne tam eşleştiyse urun_id ile o ürüne bağlanır (eşleşmeyi web katmanı bulur)."""
    ad = _zorunlu("ad", ad)
    iletisim = _zorunlu("iletisim", iletisim)
    parca_kodu = _zorunlu("parca_kodu", parca_kodu)
    eposta, telefon = iletisim_ayir(iletisim)
    if isinstance(adet, bool) or not isinstance(adet, int) or not 1 <= adet <= ADET_MAX:
        raise TeklifHatasi("adet", "gecersiz")
    if aciliyet is not None and aciliyet not in ACILIYETLER:     # G3i madde 16
        raise TeklifHatasi("aciliyet", "gecersiz")
    if musteri_id is not None and con.execute("SELECT 1 FROM musteri WHERE id = ?", (musteri_id,)).fetchone() is None:
        musteri_id = None
    if urun_id is not None and con.execute("SELECT 1 FROM urun WHERE id = ?", (urun_id,)).fetchone() is None:
        urun_id = None
    cur = con.execute(
        "INSERT INTO teklif (no, musteri_id, ad, firma, eposta, telefon, ulke, urun_id, adet, mesaj, durum, "
        "olusturma, parca_kodu, aciliyet, model) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, 'yeni', ?, ?, ?, ?)",
        (_yeni_no(con, simdi), musteri_id, ad, eposta, telefon, _zorunlu("ulke", ulke).upper(), urun_id, adet,
         _zorunlu("mesaj", mesaj)[:MESAJ_MAX], simdi.isoformat(), parca_kodu, aciliyet, _temiz(model)),
    )
    return _teklif_getir(con, cur.lastrowid)


def iletisim_ayir(iletisim: str) -> tuple[str | None, str | None]:
    """Hızlı talepteki tek "telefon veya e-posta" alanı -> (eposta, telefon). Geçersizse TeklifHatasi."""
    if "@" in iletisim:
        if not eposta_gecerli(iletisim):
            raise TeklifHatasi("iletisim", "iletisim_gecersiz")
        return iletisim, None
    if not telefon_gecerli(iletisim):
        raise TeklifHatasi("iletisim", "iletisim_gecersiz")
    return None, iletisim


def teklifler(con: sqlite3.Connection, musteri_id: int | None = None) -> list[Teklif]:
    if musteri_id is None:
        satirlar = con.execute(_TEKLIF_SQL + " ORDER BY t.id DESC").fetchall()
    else:
        satirlar = con.execute(_TEKLIF_SQL + " WHERE t.musteri_id = ? ORDER BY t.id DESC", (musteri_id,)).fetchall()
    kalemler = _kalemler(con, [r["id"] for r in satirlar])
    return [_teklif(r, kalemler.get(r["id"], ())) for r in satirlar]


def teklif_durum_degistir(con: sqlite3.Connection, teklif_id: int, yeni: str) -> Teklif:
    r = con.execute("SELECT durum FROM teklif WHERE id = ?", (teklif_id,)).fetchone()
    if r is None:
        raise LookupError(teklif_id)
    eski = r["durum"]
    if yeni not in TEKLIF_GECISLERI.get(eski, set()):
        raise GecersizGecis(f"{eski}->{yeni}")
    cur = con.execute(
        "UPDATE teklif SET durum = ? WHERE id = ? AND durum = ?", (yeni, teklif_id, eski)
    )
    if cur.rowcount == 0:                       # başka işlem araya girdi: güncel durumu oku
        r = con.execute("SELECT durum FROM teklif WHERE id = ?", (teklif_id,)).fetchone()
        raise GecersizGecis(f"{eski}->{yeni} (güncel: {r['durum'] if r else None})")
    return _teklif_getir(con, teklif_id)
