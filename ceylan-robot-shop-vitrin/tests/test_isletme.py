"""Görev 17 — işletme betikleri, gecis_calistir, asgi fabrikası ve systemd birimleri."""
from __future__ import annotations

import configparser
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.db import baglan, gecisleri_uygula
from app.fiyat.kur import Kur, kur_kaydet, son_kur
from app.hesap.servis import parola_dogru, parola_ozeti

KOK = Path(__file__).resolve().parents[1]
SYSTEMD = KOK / "dagitim" / "systemd"
SIMDI = datetime(2026, 10, 13, 2, 30, tzinfo=UTC)

# Gerçek API biçimi (12.10.2026'da doğrulandı): categories düz liste,
# products {"data", "total", "page", "limit", "totalPages"}.
KATEGORILER = [
    {"_id": "k12", "name": "Endüstriyel Robotlar", "parentId": None, "path": "12", "level": 0, "isActive": True, "erpId": 12},
    {"_id": "k41", "name": "KUKA", "parentId": "k12", "path": "12.41", "level": 1, "isActive": True, "erpId": 41},
    {"_id": "k243", "name": "KR C4", "parentId": "k41", "path": "12.41.243", "level": 2, "isActive": True, "erpId": 243},
    {"_id": "k11", "name": "Mekanik", "parentId": None, "path": "11", "level": 0, "isActive": True, "erpId": 11},
]


def _urun(sku: str, ad: str, kat_id: str, kat_ad: str, yol: str, uretici: str) -> dict:
    return {
        "_id": f"u{sku}", "sku": sku, "name": ad,
        "attributes": {"manufacturerCode": uretici, "vatRate": 20, "weight": 0},
        "categoryId": {"_id": kat_id, "name": kat_ad, "path": yol},
        "images": [], "price": {"amount": 0, "currency": "EUR"}, "stock": 0,
        "status": "active", "updatedAt": "2026-10-12T17:41:23.369Z",
    }


URUNLER = [
    _urun("8301033800019", "KUKA KRC5 KR 140 R3200-2 PA", "k243", "KR C4", "12.41.243", "0010035195"),
    _urun("1100000000011", "QA Rulman 6205", "k11", "Mekanik", "11", "6205-2RS"),
    _urun("1100000000012", "QA Kaplin 24 mm", "k11", "Mekanik", "11", "KPL-24"),
]

TCMB_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<Tarih_Date Tarih="13.10.2026" Date="10/13/2026" Bulten_No="2026/191">
  <Currency CrossOrder="9" Kod="EUR" CurrencyCode="EUR">
    <Unit>1</Unit><Isim>EURO</Isim><CurrencyName>EURO</CurrencyName>
    <ForexBuying>49.1234</ForexBuying><ForexSelling>49.2119</ForexSelling>
    <BanknoteBuying>49.0890</BanknoteBuying><BanknoteSelling>49.2857</BanknoteSelling>
    <CrossRateUSD/><CrossRateOther>1.1702</CrossRateOther>
  </Currency>
</Tarih_Date>"""


def _kaynak_isleyici(istekler: list[httpx.Request]):
    def isle(istek: httpx.Request) -> httpx.Response:
        istekler.append(istek)
        if istek.url.path == "/api/public/categories":
            return httpx.Response(200, json=KATEGORILER)
        if istek.url.path == "/api/public/products":
            sayfa = int(istek.url.params.get("page", "1"))
            limit = int(istek.url.params.get("limit", "20"))
            veri = URUNLER if sayfa == 1 else []
            return httpx.Response(200, json={"data": veri, "total": len(URUNLER), "page": sayfa,
                                             "limit": limit, "totalPages": 1})
        return httpx.Response(404)
    return isle


@pytest.fixture
def ortam(tmp_path) -> dict[str, str]:
    db = tmp_path / "shop.db"
    con = baglan(db)
    gecisleri_uygula(con)
    con.close()
    return {
        "SHOP_DB": str(db),
        "SHOP_GIZLI_ANAHTAR": "t" * 32,
        "SHOP_YONETICI": "yonetici",
        "SHOP_YONETICI_OZET": parola_ozeti("yonetici-parola-123"),
        "SHOP_KAYNAK_API": "https://kaynak.test",
    }


def _say(ortam: dict[str, str], sql: str):
    con = baglan(Path(ortam["SHOP_DB"]))
    try:
        return con.execute(sql).fetchone()
    finally:
        con.close()


# ---------- betikler/esitle.py ----------

def test_esitle_betigi_tam_tur_json_ve_cikis_0(ortam):
    from betikler.esitle import calistir

    istekler: list[httpx.Request] = []
    cikti = io.StringIO()
    kod = calistir(ortam, transport=httpx.MockTransport(_kaynak_isleyici(istekler)),
                   uyku=lambda sn: None, simdi=lambda: SIMDI, cikti=cikti)

    assert kod == 0
    satirlar = cikti.getvalue().strip().splitlines()
    assert len(satirlar) == 1, "çıktı tek satır JSON olmalı"
    sonuc = json.loads(satirlar[0])
    assert sonuc["durum"] == "tam"
    assert sonuc["api_toplam"] == 3
    assert sonuc["cekilen"] == 3
    assert sonuc["bozuk"] == 0
    assert sonuc["hata"] is None
    assert istekler, "kaynağa hiç istek gitmedi"
    assert all(i.url.host == "kaynak.test" for i in istekler)
    assert all(i.headers["user-agent"] == "cr-shop-demo-esitleme/1.0" for i in istekler)
    assert _say(ortam, "SELECT COUNT(*) FROM urun WHERE aktif = 1")[0] == 3
    gunluk = _say(ortam, "SELECT durum, api_toplam FROM esitleme_gunlugu ORDER BY id DESC LIMIT 1")
    assert (gunluk[0], gunluk[1]) == ("tam", 3)


def test_esitle_betigi_kaynak_hatasinda_cikis_1_ve_veri_degismez(ortam):
    from betikler.esitle import calistir

    cikti = io.StringIO()
    kod = calistir(ortam, transport=httpx.MockTransport(lambda istek: httpx.Response(503)),
                   uyku=lambda sn: None, simdi=lambda: SIMDI, cikti=cikti)

    assert kod == 1
    sonuc = json.loads(cikti.getvalue())
    assert sonuc["durum"] == "hata"
    assert sonuc["hata"]
    assert _say(ortam, "SELECT COUNT(*) FROM urun")[0] == 0
    assert _say(ortam, "SELECT durum FROM esitleme_gunlugu ORDER BY id DESC LIMIT 1")[0] == "hata"


def test_esitle_betigi_eksik_turda_cikis_0_json_eksik(ortam):
    """K1: 1. sayfadan sonraki sayfa alınamazsa tur 'eksik' — çıkış 0, JSON'da durum 'eksik', pasifleme yok."""
    from betikler.esitle import calistir

    def isle(istek: httpx.Request) -> httpx.Response:
        if istek.url.path == "/api/public/categories":
            return httpx.Response(200, json=KATEGORILER)
        sayfa = int(istek.url.params.get("page", "1"))
        if sayfa == 1:
            return httpx.Response(200, json={"data": URUNLER, "total": 23, "page": 1, "limit": 20, "totalPages": 2})
        return httpx.Response(503)

    cikti = io.StringIO()
    kod = calistir(ortam, transport=httpx.MockTransport(isle), uyku=lambda sn: None, simdi=lambda: SIMDI, cikti=cikti)

    assert kod == 0
    sonuc = json.loads(cikti.getvalue())
    assert sonuc["durum"] == "eksik"
    assert sonuc["api_toplam"] == 23
    assert "bozuk" in sonuc
    assert _say(ortam, "SELECT COUNT(*) FROM urun WHERE aktif = 1")[0] == 3
    gunluk = _say(ortam, "SELECT durum, hata FROM esitleme_gunlugu ORDER BY id DESC LIMIT 1")
    assert gunluk[0] == "eksik"
    assert "alinamayan_sayfa: 2" in gunluk[1]


def test_esitle_http_istemcisi_zaman_asimi_ve_kullanici_ajani():
    from betikler.esitle import http_istemcisi

    with http_istemcisi() as http:
        assert http.timeout.connect == 30
        assert http.timeout.read == 30
        assert http.headers["User-Agent"] == "cr-shop-demo-esitleme/1.0"


# ---------- betikler/kur_al.py ----------

def test_kur_betigi_basarili(ortam):
    from betikler.kur_al import calistir

    cikti = io.StringIO()
    kod = calistir(ortam, transport=httpx.MockTransport(lambda istek: httpx.Response(200, content=TCMB_XML)),
                   simdi=SIMDI, cikti=cikti)

    assert kod == 0
    sonuc = json.loads(cikti.getvalue())
    assert sonuc["durum"] == "tamam"
    assert sonuc["tarih"] == "2026-10-13"
    assert Decimal(sonuc["eur_satis"]) == Decimal("49.2119")
    con = baglan(Path(ortam["SHOP_DB"]))
    try:
        assert son_kur(con).eur_satis == Decimal("49.2119")
    finally:
        con.close()


def test_kur_betigi_hatada_cikis_1_son_kur_korunur(ortam):
    from betikler.kur_al import calistir

    con = baglan(Path(ortam["SHOP_DB"]))
    with con:
        kur_kaydet(con, Kur(date(2026, 10, 12), Decimal("48.9000"), Decimal("49.0000")), SIMDI)
    con.close()

    cikti = io.StringIO()
    kod = calistir(ortam, transport=httpx.MockTransport(lambda istek: httpx.Response(503)),
                   simdi=SIMDI, cikti=cikti)

    assert kod == 1
    sonuc = json.loads(cikti.getvalue())
    assert sonuc["durum"] == "hata"
    assert sonuc["son_kur_tarihi"] == "2026-10-12"
    assert Decimal(sonuc["son_kur_eur_satis"]) == Decimal("49.0000")
    con = baglan(Path(ortam["SHOP_DB"]))
    try:
        kur = son_kur(con)
        assert kur.tarih == date(2026, 10, 12)
        assert kur.eur_satis == Decimal("49.0000")
    finally:
        con.close()


# ---------- betikler/yonetici_ozet.py ----------

def test_yonetici_ozet_borudan_parola_okur():
    from betikler.yonetici_ozet import calistir

    cikti, hata = io.StringIO(), io.StringIO()
    assert calistir(giris=io.StringIO("QATest-Yonetim-2026\n"), cikti=cikti, hata=hata) == 0
    ozet = cikti.getvalue().strip()
    assert ozet.startswith("scrypt$")
    assert parola_dogru("QATest-Yonetim-2026", ozet)
    assert "QATest-Yonetim-2026" not in cikti.getvalue() + hata.getvalue()


def test_yonetici_ozet_kisa_parolayi_reddeder():
    from betikler.yonetici_ozet import calistir

    cikti, hata = io.StringIO(), io.StringIO()
    assert calistir(giris=io.StringIO("kisa\n"), cikti=cikti, hata=hata) == 1
    assert cikti.getvalue() == ""
    assert "12" in hata.getvalue()


# ---------- app/gecis_calistir.py ----------

def _ortam_dosyasi(tmp_path: Path, db: Path) -> Path:
    yol = tmp_path / "ortam"
    yol.write_text(f"# yorum\n\nSHOP_DB='{db}'\nSHOP_GIZLI_ANAHTAR='abc$def-uzun-test-anahtari-0123456789'\nSHOP_YONETICI=yonetici\n",
                   encoding="utf-8")
    return yol


def test_ortam_dosyasi_tirnaklari_ve_yorumlari_isler(tmp_path):
    from app.gecis_calistir import ortam_dosyasi_oku

    db = tmp_path / "shop.db"
    assert ortam_dosyasi_oku(_ortam_dosyasi(tmp_path, db)) == {
        "SHOP_DB": str(db), "SHOP_GIZLI_ANAHTAR": "abc$def-uzun-test-anahtari-0123456789", "SHOP_YONETICI": "yonetici"}


def test_gecis_calistir_ilk_kurulumda_yedeksiz_sonra_yedekli(tmp_path):
    from app.gecis_calistir import calistir

    db = tmp_path / "veri" / "shop.db"
    db.parent.mkdir()
    ortam_dosyasi = _ortam_dosyasi(tmp_path, db)

    cikti = io.StringIO()
    assert calistir(ortam_dosyasi, release="20261013-0900", cikti=cikti) == 0
    ilk = json.loads(cikti.getvalue())
    assert ilk["yedek"] is None
    assert any(ad.startswith("001_baslangic") for ad in ilk["uygulanan"])

    cikti = io.StringIO()
    assert calistir(ortam_dosyasi, release="20261013-1000", cikti=cikti) == 0
    ikinci = json.loads(cikti.getvalue())
    yedek = db.parent / "shop-onceki-20261013-1000.db"
    assert ikinci["uygulanan"] == []
    assert ikinci["yedek"] == str(yedek)
    kopya = sqlite3.connect(yedek)
    try:
        assert kopya.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert kopya.execute("SELECT COUNT(*) FROM sema_surumu").fetchone()[0] >= 1
    finally:
        kopya.close()


def test_gecis_calistir_son_uc_yedegi_tutar(tmp_path):
    from app.gecis_calistir import calistir

    db = tmp_path / "veri" / "shop.db"
    db.parent.mkdir()
    ortam_dosyasi = _ortam_dosyasi(tmp_path, db)
    assert calistir(ortam_dosyasi, release="20261001-0000", cikti=io.StringIO()) == 0
    for ad in ("20261001-0900", "20261002-0900", "20261003-0900", "20261004-0900"):
        (db.parent / f"shop-onceki-{ad}.db").write_bytes(b"")

    assert calistir(ortam_dosyasi, release="20261005-0900", cikti=io.StringIO()) == 0

    kalan = sorted(p.name for p in db.parent.glob("shop-onceki-*.db"))
    assert kalan == ["shop-onceki-20261003-0900.db", "shop-onceki-20261004-0900.db",
                     "shop-onceki-20261005-0900.db"]


def test_gecis_calistir_shop_db_yoksa_cikis_1(tmp_path):
    from app.gecis_calistir import calistir

    yol = tmp_path / "ortam"
    yol.write_text("SHOP_YONETICI=yonetici\n", encoding="utf-8")
    cikti = io.StringIO()
    assert calistir(yol, release="20261013-0900", cikti=cikti) == 1
    assert json.loads(cikti.getvalue())["durum"] == "hata"


# ---------- app/web/asgi.py ----------

def test_asgi_fabrikasi_ortamdan_uygulama_kurar(ortam, monkeypatch):
    from fastapi.testclient import TestClient

    from app.web.asgi import uygulama

    for anahtar, deger in ortam.items():
        monkeypatch.setenv(anahtar, deger)
    with TestClient(uygulama()) as istemci:
        yanit = istemci.get("/saglik")
    assert yanit.status_code == 200
    assert yanit.json()["durum"] == "ok"
    assert "script-src 'self'" in yanit.headers["content-security-policy"]


# ---------- betikler/yedek.sh ----------

@pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None,
                    reason="yedek.sh yalnız Linux'ta (VM) çalışır")
def test_yedek_betigi_python_yolu_ve_eski_yedek_silme(ortam, tmp_path):
    yedek_dizin = tmp_path / "yedek"
    yedek_dizin.mkdir()
    eski = yedek_dizin / "shop-20260101.db"
    eski.write_bytes(b"x")
    on_gun_once = time.time() - 10 * 86400
    os.utime(eski, (on_gun_once, on_gun_once))
    yakin = yedek_dizin / "shop-20261010.db"
    yakin.write_bytes(b"x")
    uc_gun_once = time.time() - 3 * 86400
    os.utime(yakin, (uc_gun_once, uc_gun_once))

    sonuc = subprocess.run(
        ["bash", str(KOK / "betikler" / "yedek.sh")],
        env={**os.environ, "SHOP_DB": ortam["SHOP_DB"], "SHOP_YEDEK_DIZIN": str(yedek_dizin),
             "SHOP_YEDEK_ARAC": "python", "SHOP_PYTHON": sys.executable},
        capture_output=True, text=True, timeout=60,
    )

    assert sonuc.returncode == 0, sonuc.stderr
    bugun = yedek_dizin / f"shop-{date.today():%Y%m%d}.db"
    assert bugun.exists()
    assert not eski.exists(), "7 günden eski yedek silinmeli"
    assert yakin.exists(), "7 günden yeni yedek kalmalı"
    kopya = sqlite3.connect(bugun)
    try:
        assert kopya.execute("SELECT COUNT(*) FROM sema_surumu").fetchone()[0] >= 1
    finally:
        kopya.close()
    assert "via python" in sonuc.stdout


@pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None,
                    reason="yedek.sh yalnız Linux'ta (VM) çalışır")
def test_yedek_betigi_veritabani_yoksa_cikis_1(tmp_path):
    sonuc = subprocess.run(
        ["bash", str(KOK / "betikler" / "yedek.sh")],
        env={**os.environ, "SHOP_DB": str(tmp_path / "yok.db"), "SHOP_YEDEK_DIZIN": str(tmp_path),
             "SHOP_PYTHON": sys.executable},
        capture_output=True, text=True, timeout=60,
    )
    assert sonuc.returncode == 1
    assert "veritabanı yok" in sonuc.stderr


# ---------- dagitim/systemd ----------

def _birim(ad: str) -> configparser.ConfigParser:
    p = configparser.ConfigParser(interpolation=None, strict=False)
    p.optionxform = str
    with open(SYSTEMD / ad, encoding="utf-8") as f:
        p.read_file(f)
    return p


SERVISLER = ["cr-shop-demo.service", "cr-shop-esitle.service", "cr-shop-yedek.service", "cr-shop-kur.service"]


@pytest.mark.parametrize("ad", SERVISLER)
def test_servis_ortak_sertlestirme(ad):
    s = _birim(ad)["Service"]
    assert s["User"] == "crshop"
    assert s["Group"] == "crshop"
    assert s["EnvironmentFile"] == "/opt/cr-shop-demo/ortam"
    assert s["WorkingDirectory"] == "/opt/cr-shop-demo/current"
    assert s["NoNewPrivileges"] == "true"
    assert s["ProtectSystem"] == "strict"
    assert s["ReadWritePaths"] == "/opt/cr-shop-demo/veri /opt/cr-shop-demo/yedek"
    assert s["ProtectHome"] == "true"
    assert s["PrivateTmp"] == "true"
    assert s["PrivateDevices"] == "true"


def test_web_servisi():
    s = _birim("cr-shop-demo.service")["Service"]
    assert s["MemoryMax"] == "600M"
    assert s["Restart"] == "always"
    assert s["ExecStart"] == ("/opt/cr-shop-demo/current/venv/bin/uvicorn --factory app.web.asgi:uygulama "
                              "--host 0.0.0.0 --port 3030 --workers 1")


def test_esitleme_servisi():
    s = _birim("cr-shop-esitle.service")["Service"]
    assert s["Type"] == "oneshot"
    assert s["MemoryMax"] == "400M"
    assert s["TimeoutStartSec"] == "30min"
    assert s["ExecStart"] == "/opt/cr-shop-demo/current/venv/bin/python -m betikler.esitle"


@pytest.mark.parametrize("ad,saat", [("cr-shop-esitle.timer", "*-*-* 02:30:00"),
                                     ("cr-shop-yedek.timer", "*-*-* 03:00:00"),
                                     ("cr-shop-kur.timer", "*-*-* 06:00:00")])
def test_zamanlayicilar(ad, saat):
    t = _birim(ad)
    assert t["Timer"]["OnCalendar"] == saat
    assert t["Timer"]["Persistent"] == "true"
    assert t["Timer"]["Unit"] == ad.replace(".timer", ".service")
    assert t["Install"]["WantedBy"] == "timers.target"


# ---------- dagitim/uzak-yayinla.sh (geri alma; sahte sudo/curl, sudo kullanmaz) ----------

def _sahte(klasor: Path, ad: str, govde: str) -> None:
    yol = klasor / ad
    yol.write_text("#!/usr/bin/env bash\n" + govde + "\n", encoding="utf-8", newline="\n")
    yol.chmod(0o755)


def _yayin_ortami(tmp_path: Path, saglik_kodu: str, restart_kodu: int) -> tuple[Path, Path, Path, dict[str, str]]:
    kok = tmp_path / "kok"
    (kok / "releases" / "20261013-0900").mkdir(parents=True)
    yeni = kok / "releases" / "20261013-1000"
    yeni.mkdir()
    (yeni / "SURUM").write_text("abc1234\n", encoding="utf-8")
    (kok / "current").symlink_to("releases/20261013-0900")
    sahte = tmp_path / "sahte"
    sahte.mkdir()
    sudo_gunluk = tmp_path / "sudo.log"
    curl_gunluk = tmp_path / "curl.log"
    # python3 -m venv venv: venv/bin/{pip,python} her zaman 0 döner
    _sahte(sahte, "python3", 'if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then mkdir -p "$3/bin"; '
                             'for f in pip python; do printf "#!/bin/sh\nexit 0\n" > "$3/bin/$f"; '
                             'chmod +x "$3/bin/$f"; done; fi')
    # sudo: geçiş (-u crshop) başarılı, systemctl restart restart_kodu ile döner
    _sahte(sahte, "sudo", f'echo "$*" >> "{sudo_gunluk}"\n'
                          f'case "$*" in *"-u crshop"*) exit 0 ;; *"systemctl restart"*) exit {restart_kodu} ;; esac\n'
                          'exit 1')
    _sahte(sahte, "curl", f'echo x >> "{curl_gunluk}"\nprintf "{saglik_kodu}"')
    _sahte(sahte, "sleep", "exit 0")
    _sahte(sahte, "journalctl", "exit 0")
    env = {**os.environ, "PATH": f"{sahte}:{os.environ['PATH']}", "CR_SHOP_KOK": str(kok)}
    return kok, sudo_gunluk, curl_gunluk, env


def _yayinla(env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(KOK / "dagitim" / "uzak-yayinla.sh"), "20261013-1000"],
                          env=env, capture_output=True, text=True, timeout=60)


def _restartlar(gunluk: Path) -> list[str]:
    return [s for s in gunluk.read_text(encoding="utf-8").splitlines() if "systemctl restart" in s]


LINUX_BASH = pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None,
                                reason="uzak-yayinla.sh yalnız Linux'ta (VM) çalışır")


@LINUX_BASH
@pytest.mark.parametrize("saglik_kodu", ["000", "200"])
def test_uzak_yayinla_restart_basarisizsa_saglikdan_bagimsiz_oncekine_doner(tmp_path, saglik_kodu):
    """Restart hatasında eski süreç çalışmaya devam eder; sağlık 200 olsa bile yayın başarısızdır."""
    kok, sudo_gunluk, curl_gunluk, env = _yayin_ortami(tmp_path, saglik_kodu, restart_kodu=1)
    sonuc = _yayinla(env)

    assert sonuc.returncode == 1, sonuc.stdout + sonuc.stderr
    assert os.readlink(kok / "current") == "releases/20261013-0900"
    assert (kok / "releases" / "20261013-1000").is_dir(), "hatalı release inceleme için kalmalı"
    assert "HATA: systemctl restart cr-shop-demo başarısız" in sonuc.stderr
    assert "GERİ ALINDI: current -> 20261013-0900" in sonuc.stderr
    assert _restartlar(sudo_gunluk) == ["-n /usr/bin/systemctl restart cr-shop-demo"] * 2
    assert not curl_gunluk.exists(), "restart başarısızken sağlık kontrolüne geçilmemeli"


@LINUX_BASH
def test_uzak_yayinla_saglik_basarisizsa_oncekine_doner(tmp_path):
    kok, sudo_gunluk, _, env = _yayin_ortami(tmp_path, "000", restart_kodu=0)
    sonuc = _yayinla(env)

    assert sonuc.returncode == 1, sonuc.stdout + sonuc.stderr
    assert os.readlink(kok / "current") == "releases/20261013-0900"
    assert "200 dönmedi" in sonuc.stderr
    assert "GERİ ALINDI: current -> 20261013-0900" in sonuc.stderr
    assert len(_restartlar(sudo_gunluk)) == 2


@LINUX_BASH
def test_uzak_yayinla_restart_ve_saglik_basariliysa_yayinda(tmp_path):
    kok, sudo_gunluk, _, env = _yayin_ortami(tmp_path, "200", restart_kodu=0)
    sonuc = _yayinla(env)

    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    assert os.readlink(kok / "current") == "releases/20261013-1000"
    assert "UYARI" not in sonuc.stderr
    assert "TAMAM: 20261013-1000 yayında" in sonuc.stdout
    assert len(_restartlar(sudo_gunluk)) == 1
