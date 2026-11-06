"""G3e: stok ayırma (rezervasyon) — açık siparişlerin tuttuğu adet ve sitede gösterilen "ayrılabilir" stok.

Ayırır:
  - ödemesi beklenen havale siparişi, ödeme son tarihine (oluşturma + SHOP_HAVALE_GUN iş günü, G3g madde 4) kadar;
    son tarih geçince "süresi doldu" sayılır ve ayırmaz (yönetim yeniden açarsa yeni son tarihle yine ayırır),
  - süresi (30 dk) dolmamış, ödemesi beklenen kart siparişi,
  - ödenmiş ama kargoya verilmemiş (odendi, hazirlaniyor) sipariş, YALNIZ ödeme zamanı son başarılı TAM eşitlemenin
    bitişinden sonraysa (düzeltme turu 3: tam eşitleme ERP'nin gerçeğini temsil eder; üretimde ERP stoku satışı zaten
    düşmüş olur, demo siparişleri ERP'ye hiç gitmez — gece 02:30 eşitlemesi ayırmayı bırakır).
Ayırmaz: iptal, kargoda, teslim, süresi dolmuş kart siparişi.
Stok <= 0 (tedarikli) üründe ayırma anlamsızdır; sınır yoktur.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, time, timedelta, timezone

ODEME_SURESI = timedelta(minutes=30)
HAVALE_GUN = 3                                  # varsayılan; çalışma anında Ayarlar.havale_gun (SHOP_HAVALE_GUN)
TR_SAAT = timezone(timedelta(hours=3))          # Türkiye sabit UTC+3
ESITLEME_SAATI = time(2, 30)                    # dagitim/systemd/cr-shop-esitle.timer: her gece 02:30 (TSİ)


# G3g inceleme M-1: sabit tarihli resmî tatiller (ay, gün). Dinî bayramlar her yıl değiştiği için listede yok.
SABIT_TATILLER = frozenset({(1, 1), (4, 23), (5, 1), (5, 19), (7, 15), (8, 30), (10, 29)})


def is_gunu_mu(gun) -> bool:
    return gun.weekday() < 5 and (gun.month, gun.day) not in SABIT_TATILLER


def havale_son_tarih(baslangic: datetime, gun: int = HAVALE_GUN) -> datetime:
    """G3g madde 4: başlangıçtan `gun` iş günü sonrası, aynı saat (TSİ; cumartesi/pazar ve sabit tarihli resmî tatiller
    sayılmaz), UTC olarak."""
    z = baslangic.astimezone(TR_SAAT)
    kalan = gun
    while kalan > 0:
        z += timedelta(days=1)
        if is_gunu_mu(z):
            kalan -= 1
    return z.astimezone(UTC)


def sonraki_esitleme(simdi: datetime) -> datetime:
    """Bir sonraki gece tam eşitlemesinin başlangıcı (02:30 TSİ), UTC."""
    yerel = simdi.astimezone(TR_SAAT)
    aday = yerel.replace(hour=ESITLEME_SAATI.hour, minute=ESITLEME_SAATI.minute, second=0, microsecond=0)
    if aday <= yerel:
        aday += timedelta(days=1)
    return aday.astimezone(UTC)


def son_tam_esitleme_bitisi(con: sqlite3.Connection) -> str | None:
    r = con.execute("SELECT MAX(bitis) FROM esitleme_gunlugu WHERE durum = 'tam' AND bitis IS NOT NULL").fetchone()
    return r[0] if r else None


_AYIRAN = (
    " FROM siparis_kalemi k JOIN siparis s ON s.id = k.siparis_id"
    " WHERE ((s.durum IN ('odendi', 'hazirlaniyor')"
    "         AND (? IS NULL OR COALESCE(s.odeme_zamani, s.olusturma) > ?))"
    "     OR (s.durum = 'odeme_bekliyor' AND s.odeme_yontemi = 'havale'"
    "         AND (s.odeme_son_tarih IS NULL OR s.odeme_son_tarih > ?))"
    "     OR (s.durum = 'odeme_bekliyor' AND s.odeme_yontemi = 'kart' AND s.olusturma >= ?))"
    " AND NOT (s.durum = 'odeme_bekliyor' AND s.odeme_yontemi = 'kart' AND s.sepet_id IS ?)"
    " AND s.id IS NOT ?"
)


def _ayiran_param(con: sqlite3.Connection, simdi: datetime, haric_sepet_id: int | None,
                  haric_siparis_id: int | None) -> tuple:
    esitleme = son_tam_esitleme_bitisi(con)
    return (esitleme, esitleme, simdi.isoformat(), (simdi - ODEME_SURESI).isoformat(), haric_sepet_id,
            haric_siparis_id)


def ayrilan_adetler(con: sqlite3.Connection, simdi: datetime, haric_sepet_id: int | None = None,
                    haric_siparis_id: int | None = None) -> dict[int, int]:
    """Ürün -> açık siparişlerin ayırdığı adet. haric_sepet_id: bu sepetin ödemesi beklenen KART siparişleri sayılmaz
    (ziyaretçinin kendi bekleyen siparişi kendi sepetini kısıtlamasın; yeniden gönderimde zaten iptal edilir).
    haric_siparis_id: G3g madde 4 — siparişin kendi onay sayfasında kendi rezervasyonu düşülür."""
    return {r[0]: r[1] for r in con.execute(
        "SELECT k.urun_id, SUM(k.adet)" + _AYIRAN + " GROUP BY k.urun_id",
        _ayiran_param(con, simdi, haric_sepet_id, haric_siparis_id))}


def ayirma_bitisleri(con: sqlite3.Connection, simdi: datetime, urun_idleri, haric_sepet_id: int | None = None,
                     haric_siparis_id: int | None = None) -> dict[int, datetime]:
    """G3g madde 5: ürün -> ayırmalarından EN ERKEN bitecek olanın zamanı (UTC): kart siparişi oluşturma + 30 dk,
    havale siparişi ödeme son tarihi, ödenmiş/hazırlanan sipariş bir sonraki gece tam eşitlemesi (02:30 TSİ)."""
    kimlikler = [i for i in dict.fromkeys(urun_idleri) if isinstance(i, int)]
    if not kimlikler:
        return {}
    esitleme = sonraki_esitleme(simdi)
    sonuc: dict[int, datetime] = {}
    yer = ",".join("?" * len(kimlikler))
    for r in con.execute(
        "SELECT k.urun_id, s.durum, s.odeme_yontemi, s.olusturma, s.odeme_son_tarih" + _AYIRAN
        + f" AND k.urun_id IN ({yer})", (*_ayiran_param(con, simdi, haric_sepet_id, haric_siparis_id), *kimlikler)):
        if r[1] != "odeme_bekliyor":
            bitis = esitleme
        elif r[2] == "havale":
            if not r[4]:        # inceleme M-8: son tarihsiz (eski) havale süresiz ayırır; bitiş zamanı bilinmez
                continue
            bitis = datetime.fromisoformat(r[4])
        else:
            bitis = datetime.fromisoformat(r[3]) + ODEME_SURESI
        if bitis.tzinfo is None:
            bitis = bitis.replace(tzinfo=UTC)
        if r[0] not in sonuc or bitis < sonuc[r[0]]:
            sonuc[r[0]] = bitis
    return sonuc


def musait_adet(stok: int, ayrilan: int) -> int:
    """Ayrılabilir adet (stok > 0 üründe); stok <= 0 (tedarikli) için stok döner (sınırsız sayılır)."""
    return max(0, stok - ayrilan) if stok > 0 else stok
