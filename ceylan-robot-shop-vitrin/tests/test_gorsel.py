"""G1: API base64 görselleri -> yerel webp dosyaları, /gorsel rotası, hafif sayfalar."""
import base64
import hashlib
import io
import json
import random
import tracemalloc
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.esitleme.esitle import esitle
from app.esitleme.kaynak import KaynakIstemci
from tests.conftest import istemci_db, kategori_ekle, urun_ekle

TABAN = "https://www.ceylanrobot.com"
ZAMAN = datetime(2026, 10, 13, 2, 30, tzinfo=UTC)
KAT = {"_id": "kat1", "name": "KR C4", "path": "12.41.243"}
KATEGORILER = [{"_id": "kat1", "name": "Robot", "path": "12", "level": 0}]


def resim_bayti(bicim="JPEG", boyut=(1600, 1200), tohum=1, bolen=8, **kw) -> bytes:
    """Her tohum için farklı içerik: küçük rastgele gürültü, boyuta büyütülür."""
    kucuk = (max(boyut[0] // bolen, 1), max(boyut[1] // bolen, 1))
    gurultu = random.Random(tohum).randbytes(kucuk[0] * kucuk[1] * 3)
    im = Image.frombytes("RGB", kucuk, gurultu).resize(boyut)
    tampon = io.BytesIO()
    im.save(tampon, bicim, **kw)
    return tampon.getvalue()


def b64(bayt: bytes) -> str:
    return base64.b64encode(bayt).decode()


def kayit(sku: str, gorsel) -> dict:
    return {"_id": "i" + sku, "sku": sku, "name": "Ürün " + sku, "categoryId": KAT,
            "price": {"amount": 10, "currency": "EUR"}, "stock": 1,
            "attributes": {"vatRate": 20}, "images": [gorsel] if gorsel is not None else []}


def kaynak_kayitlar(kayitlar: list[dict], api_toplam: int | None = None) -> KaynakIstemci:
    def isleyici(istek: httpx.Request) -> httpx.Response:
        if istek.url.path == "/api/public/categories":
            return httpx.Response(200, json=KATEGORILER)
        sayfa = int(istek.url.params["page"])
        limit = int(istek.url.params["limit"])
        return httpx.Response(200, json={"data": kayitlar[(sayfa - 1) * limit: sayfa * limit],
                                         "total": api_toplam if api_toplam is not None else len(kayitlar)})
    http = httpx.Client(transport=httpx.MockTransport(isleyici))
    return KaynakIstemci(http, TABAN, uyku=lambda s: None)


def tur(con, bantlar, kayitlar, gorsel_dizin, api_toplam=None):
    return esitle(con, kaynak_kayitlar(kayitlar, api_toplam), bantlar, lambda: ZAMAN, gorsel_dizin=gorsel_dizin)


def gorsel_url(con, sku):
    return con.execute("SELECT gorsel_url FROM urun WHERE sku=?", (sku,)).fetchone()[0]


def ad_of(bayt: bytes) -> str:
    return hashlib.sha256(bayt).hexdigest()[:32] + ".webp"


# ---------- eşitleme: birim ----------

@pytest.mark.parametrize("onek", ["", "data:image/jpeg;base64,"])
def test_base64_iki_webp_uretir(con, bantlar, tmp_path, onek):
    bayt = resim_bayti()
    gd = tmp_path / "g"
    s = tur(con, bantlar, [kayit("A1", onek + b64(bayt))], gd)
    assert (s.durum, s.bozuk, s.eklenen) == ("tam", 0, 1)
    ad = ad_of(bayt)
    assert gorsel_url(con, "A1") == "gorsel:" + ad
    with Image.open(gd / "k" / ad) as k, Image.open(gd / "b" / ad) as b:
        assert (k.format, b.format) == ("WEBP", "WEBP")
        assert max(k.size) == 320 and max(b.size) == 1000


def test_base64_bosluk_temizlenir(con, bantlar, tmp_path):
    bayt = resim_bayti(boyut=(400, 300))
    govde = b64(bayt)
    govde = "\n".join(govde[i:i + 76] for i in range(0, len(govde), 76))
    tur(con, bantlar, [kayit("A1", govde)], tmp_path / "g")
    assert gorsel_url(con, "A1") == "gorsel:" + ad_of(bayt)


def test_png_ve_webp_kabul(con, bantlar, tmp_path):
    png = resim_bayti("PNG", (500, 400), 2)
    webp = resim_bayti("WEBP", (500, 400), 3)
    tur(con, bantlar, [kayit("P", b64(png)), kayit("W", b64(webp))], tmp_path / "g")
    assert gorsel_url(con, "P") == "gorsel:" + ad_of(png)
    assert gorsel_url(con, "W") == "gorsel:" + ad_of(webp)


def test_exif_yonu_uygulanir(con, bantlar, tmp_path):
    im = Image.new("RGB", (400, 200), "red")
    ex = Image.Exif()
    ex[0x0112] = 6   # 90 derece döndür
    t = io.BytesIO()
    im.save(t, "JPEG", exif=ex)
    bayt = t.getvalue()
    tur(con, bantlar, [kayit("A1", b64(bayt))], tmp_path / "g")
    with Image.open(tmp_path / "g" / "b" / ad_of(bayt)) as b:
        assert b.size == (200, 400)


@pytest.mark.parametrize("gorsel", [
    "!!!bozuk###base64",
    b64(b"merhaba dunya, bu bir resim degil"),               # sihirli bayt yok
    b64(b"\xff\xd8\xff" + b"x" * 100),                       # JPEG baytı ama Pillow açamaz
    b64(b"GIF89a" + b"\x00" * 50),                           # desteklenmeyen tür
    "A" * 7_200_000,                                         # 5 MB üstü
])
def test_gecersiz_gorsel_none_urun_eklenir(con, bantlar, tmp_path, gorsel):
    s = tur(con, bantlar, [kayit("A1", gorsel)], tmp_path / "g")
    assert (s.durum, s.bozuk, s.eklenen) == ("tam", 0, 1)
    assert gorsel_url(con, "A1") is None


def test_bes_mb_ustu_jpeg_yok_sayilir(con, bantlar, tmp_path):
    bayt = b"\xff\xd8\xff\xe0" + b"\x00" * (5 * 1024 * 1024 + 1)
    s = tur(con, bantlar, [kayit("A1", b64(bayt))], tmp_path / "g")
    assert (s.bozuk, s.eklenen) == (0, 1)
    assert gorsel_url(con, "A1") is None


def test_url_girisi_degismez(con, bantlar, tmp_path):
    gd = tmp_path / "g"
    tur(con, bantlar, [kayit("U1", "https://cdn.example.com/a.jpg"),
                       kayit("U2", "/api/uploads/x/y.webp"),
                       kayit("U3", "/api/uploads/xyz.png")], gd)
    assert gorsel_url(con, "U1") == "https://cdn.example.com/a.jpg"
    assert gorsel_url(con, "U2") == TABAN + "/api/uploads/x/y.webp"
    assert gorsel_url(con, "U3") == TABAN + "/api/uploads/xyz.png"
    assert not gd.exists() or not list(gd.rglob("*.webp"))


def test_ayni_icerik_yeniden_yazilmaz(con, bantlar, tmp_path):
    bayt = resim_bayti(boyut=(800, 600))
    gd = tmp_path / "g"
    tur(con, bantlar, [kayit("A1", b64(bayt))], gd)
    yol = gd / "k" / ad_of(bayt)
    once = (yol.stat().st_mtime_ns, yol.stat().st_ino)
    tur(con, bantlar, [kayit("A1", b64(bayt))], gd)
    assert (yol.stat().st_mtime_ns, yol.stat().st_ino) == once
    assert not list(gd.rglob("*.tmp"))


def test_gorsel_dizini_yoksa_base64_gorselsiz(con, bantlar):
    s = esitle(con, kaynak_kayitlar([kayit("A1", b64(resim_bayti(boyut=(100, 100))))]), bantlar, lambda: ZAMAN)
    assert (s.durum, s.bozuk) == ("tam", 0)
    assert gorsel_url(con, "A1") is None


def test_tam_turda_yetim_silinir_kismi_turda_silinmez(con, bantlar, tmp_path):
    gd = tmp_path / "g"
    a, b = resim_bayti(tohum=1, boyut=(400, 300)), resim_bayti(tohum=2, boyut=(400, 300))
    tur(con, bantlar, [kayit("A1", b64(a)), kayit("A2", b64(b))], gd)
    yetim_k = gd / "k" / ("0" * 32 + ".webp")
    yetim_b = gd / "b" / ("0" * 32 + ".webp")
    yabanci = gd / "k" / "notlar.txt"
    for y in (yetim_k, yetim_b, yabanci):
        y.write_bytes(b"x")
    # kısmi tur: API toplamı kayıt sayısından büyük -> eksik
    s = tur(con, bantlar, [kayit("A1", b64(a))], gd, api_toplam=5)
    assert s.durum == "eksik"
    assert yetim_k.exists() and yetim_b.exists()
    # tam tur: A2 artık görselsiz -> onun dosyaları da yetim
    s = tur(con, bantlar, [kayit("A1", b64(a)), kayit("A2", None)], gd)
    assert s.durum == "tam"
    assert not yetim_k.exists() and not yetim_b.exists()
    assert yabanci.exists()
    assert (gd / "k" / ad_of(a)).exists() and (gd / "b" / ad_of(a)).exists()
    assert not (gd / "k" / ad_of(b)).exists() and not (gd / "b" / ad_of(b)).exists()


def test_esitleme_ara_base64_icermez(con, bantlar, tmp_path):
    kayitlar = [kayit(f"S{i}", b64(resim_bayti(boyut=(300, 200), tohum=i))) for i in range(3)]
    tur(con, bantlar, kayitlar, tmp_path / "g")
    satirlar = [v for (v,) in con.execute("SELECT veri FROM esitleme_ara")]
    assert len(satirlar) == 3 and max(map(len, satirlar)) < 4096
    assert all(json.loads(v)["gorsel_url"].startswith("gorsel:") for v in satirlar)


def _tek_renk_png(boyut) -> bytes:
    t = io.BytesIO()
    Image.new("L", boyut, 255).save(t, "PNG")
    return t.getvalue()


def test_40mp_png_gorselsiz_urun_eklenir(con, bantlar, tmp_path):
    bayt = _tek_renk_png((8000, 5000))                 # 40 MP, birkaç KB
    assert len(bayt) < 5 * 1024 * 1024
    s = tur(con, bantlar, [kayit("A1", b64(bayt))], tmp_path / "g")
    assert (s.durum, s.bozuk, s.eklenen) == ("tam", 0, 1)
    assert gorsel_url(con, "A1") is None
    assert not list((tmp_path / "g").rglob("*.webp"))


def test_20mp_png_rss_sinirli(tmp_path):
    """Ayrı süreçte (C tahsisleri tracemalloc'ta görünmez): ru_maxrss < 250 MB."""
    import subprocess
    import sys
    from tests.conftest import KOK
    bayt = _tek_renk_png((4400, 4500))                 # 19.8 MP
    kod = """
import sys, resource
from pathlib import Path
from app.esitleme.gorsel import base64_kaydet
r = base64_kaydet(sys.stdin.read(), Path(sys.argv[1]))
print(r, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
"""
    c = subprocess.run([sys.executable, "-c", kod, str(tmp_path / "g")], input=b64(bayt), text=True,
                       capture_output=True, cwd=KOK, env={"PYTHONPATH": str(KOK), "PATH": ""}, timeout=120)
    assert c.returncode == 0, c.stderr
    ad, kb = c.stdout.split()
    assert ad.startswith("gorsel:")
    print("RSS_KB=", kb)
    assert int(kb) < 250 * 1024                         # Linux: KB
    with Image.open(tmp_path / "g" / "b" / ad[7:]) as im:
        assert im.size == (990, 1000) or max(im.size) == 1000


def test_yazma_hatasi_yutulmaz_tur_hata(con, bantlar, tmp_path):
    engel = tmp_path / "dosya"
    engel.write_text("x")                              # klasör yerine dosya: mkdir başarısız
    urun_ekle(con, sku="ESKI", gorsel_url="/api/eski.webp")
    s = tur(con, bantlar, [kayit("A1", b64(resim_bayti(boyut=(300, 200))))], engel / "g")
    assert s.durum == "hata" and bool(s.hata)
    assert con.execute("SELECT COUNT(*) FROM urun WHERE sku='A1'").fetchone()[0] == 0


def test_bozuk_icerik_pillow_hatasi_yutulur(con, bantlar, tmp_path):
    kesik = resim_bayti(boyut=(600, 400))[:200]        # JPEG başlığı var, gövde kesik
    s = tur(con, bantlar, [kayit("A1", b64(kesik))], tmp_path / "g")
    assert (s.durum, s.bozuk) == ("tam", 0) and gorsel_url(con, "A1") is None


def test_eski_tmp_dosyalari_silinir(con, bantlar, tmp_path):
    import os
    import time
    gd = tmp_path / "g"
    (gd / "k").mkdir(parents=True)
    eski = gd / "k" / ("a" * 32 + ".webp.123.tmp")
    yeni = gd / "k" / ("b" * 32 + ".webp.124.tmp")
    yabanci = gd / "k" / "baska.tmp"
    for y in (eski, yeni, yabanci):
        y.write_bytes(b"x")
    gecmis = time.time() - 7200
    os.utime(eski, (gecmis, gecmis))
    os.utime(yabanci, (gecmis, gecmis))
    tur(con, bantlar, [kayit("A1", None)], gd)
    assert not eski.exists() and yeni.exists() and yabanci.exists()


# ---------- eşitleme: bellek ----------

def test_esitleme_bellek_tepesi(con, bantlar, tmp_path):
    """223 sayfa x 20 kayıt x ~200 KB base64: sayfa başına işlenip bırakılır."""
    gorseller = [b64(resim_bayti(boyut=(1100, 800), tohum=i, bolen=6, quality=70)) for i in range(20)]
    toplam, boy = 223 * 20, 20

    def isleyici(istek: httpx.Request) -> httpx.Response:
        if istek.url.path == "/api/public/categories":
            return httpx.Response(200, json=KATEGORILER)
        sayfa = int(istek.url.params["page"])
        veri = [kayit(f"M{n}", gorseller[n % 20]) for n in range((sayfa - 1) * boy, min(sayfa * boy, toplam))]
        return httpx.Response(200, content=json.dumps({"data": veri, "total": toplam}).encode())

    kaynak = KaynakIstemci(httpx.Client(transport=httpx.MockTransport(isleyici)), TABAN, uyku=lambda s: None)
    ortalama = sum(map(len, gorseller)) // 20
    tracemalloc.start()
    try:
        s = esitle(con, kaynak, bantlar, lambda: ZAMAN, gorsel_dizin=tmp_path / "g")
        _, tepe = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    print(f"\nBELLEK_TEPESI_MB={tepe / 1e6:.1f} ORTALAMA_B64_KB={ortalama / 1024:.0f}")
    assert (s.durum, s.cekilen) == ("tam", toplam)
    assert tepe < 120 * 1024 * 1024
    assert con.execute("SELECT MAX(LENGTH(veri)) FROM esitleme_ara").fetchone()[0] < 4096


# ---------- rota ----------

AD = "a" * 32 + ".webp"


def _gorsel_yaz(istemci, ad: str, boy="k", icerik=b"RIFF....WEBPdata") -> Path:
    yol = istemci.app.state.ayarlar.gorsel_dizin / boy / ad
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_bytes(icerik)
    return yol


@pytest.mark.parametrize("boy", ["k", "b"])
def test_gorsel_rotasi_basliklar(istemci, boy):
    _gorsel_yaz(istemci, AD, boy, b"icerik-" + boy.encode())
    y = istemci.get(f"/gorsel/{boy}/{AD}")
    assert y.status_code == 200
    assert y.content == b"icerik-" + boy.encode()
    assert y.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert y.headers["x-content-type-options"] == "nosniff"
    assert y.headers["content-type"] == "image/webp"


@pytest.mark.parametrize("yol", [
    "/gorsel/k/" + "a" * 31 + ".webp",            # kısa
    "/gorsel/k/" + "a" * 33 + ".webp",
    "/gorsel/k/" + "A" * 32 + ".webp",            # büyük harf
    "/gorsel/k/" + "g" * 32 + ".webp",            # hex değil
    "/gorsel/k/" + "a" * 32 + ".jpg",
    "/gorsel/x/" + "a" * 32 + ".webp",            # yanlış boy
    "/gorsel/K/" + "a" * 32 + ".webp",
    "/gorsel/k/..",
    "/gorsel/k/%2e%2e",
    "/gorsel/k/..%2f" + "a" * 32 + ".webp",
    "/gorsel/..%2fk/" + "a" * 32 + ".webp",
    "/gorsel/k/%2e%2e/b/" + "a" * 32 + ".webp",
    "/gorsel/k/" + "a" * 32 + ".webp%0a",          # satır sonu ($ tuzağı)
    "/gorsel/k/" + "b" * 32 + ".webp",             # geçerli ad ama dosya yok
])
def test_gorsel_rotasi_404(istemci, yol):
    _gorsel_yaz(istemci, AD, "k")
    _gorsel_yaz(istemci, AD, "b")
    assert istemci.get(yol).status_code == 404


# ---------- şablonlar ----------

def test_kategori_sayfasi_hafif_ve_yerel_gorsel(istemci):
    with istemci_db(istemci) as con:
        kok = kategori_ekle(con, kaynak_id="k1", ad="Elektrik", yol="1", seviye=0)
        for i in range(24):
            urun_ekle(con, sku=f"G{i}", ad=f"Ürün {i}", kategori_id=kok,
                      gorsel_url=f"gorsel:{i:032x}.webp")
    html = istemci.get(f"/tr/kategori/{kok}").text
    print("KATEGORI_HTML_BAYT=", len(html.encode()))
    assert len(html.encode()) < 150 * 1024
    assert html.count('src="/gorsel/k/') == 24
    assert 'decoding="async"' in html


def test_eski_base64_satir_yer_tutucu(istemci):
    eski = "/9j/4AAQSkZJRgABAQ" + "A" * 200_000
    with istemci_db(istemci) as con:
        kok = kategori_ekle(con, kaynak_id="k1", ad="Elektrik", yol="1", seviye=0)
        u1 = urun_ekle(con, sku="E1", kategori_id=kok, gorsel_url=eski)
        u2 = urun_ekle(con, sku="E2", kategori_id=kok, gorsel_url="data:image/jpeg;base64,AAAA")
        u3 = urun_ekle(con, sku="E3", kategori_id=kok, gorsel_url="/9j/4AAQSkZJRgAB")
        u4 = urun_ekle(con, sku="E4", kategori_id=kok, gorsel_url=TABAN + eski)   # staging'deki eski biçim
    for yol in (f"/tr/kategori/{kok}", f"/tr/urun/{u1}", f"/tr/urun/{u2}", f"/tr/urun/{u3}", f"/tr/urun/{u4}"):
        html = istemci.get(yol).text
        assert "/9j/" not in html and "base64" not in html
        assert "/statik/yer-tutucu/" in html
        assert len(html) < 150 * 1024


def test_urun_detayi_buyuk_boy(istemci):
    with istemci_db(istemci) as con:
        kok = kategori_ekle(con, kaynak_id="k1", ad="Elektrik", yol="1", seviye=0)
        u = urun_ekle(con, sku="D1", kategori_id=kok, gorsel_url=f"gorsel:{AD}")
    assert f'src="/gorsel/b/{AD}"' in istemci.get(f"/tr/urun/{u}").text


def test_url_gorsel_bugunku_gibi(istemci):
    with istemci_db(istemci) as con:
        kok = kategori_ekle(con, kaynak_id="k1", ad="Elektrik", yol="1", seviye=0)
        u = urun_ekle(con, sku="D1", kategori_id=kok, gorsel_url="/api/uploads/a/b.webp")
    assert 'src="https://www.ceylanrobot.com/api/uploads/a/b.webp"' in istemci.get(f"/tr/urun/{u}").text


# ---------- göç ----------

def test_gecis_002_base64_satirlari_temizler(tmp_path):
    from app.db import baglan, gecisleri_uygula
    con = baglan(tmp_path / "m.db")
    try:
        gecisleri_uygula(con)
        urun_ekle(con, sku="Z1", gorsel_url="/9j/" + "A" * 1000)
        urun_ekle(con, sku="Z2", gorsel_url="/api/uploads/a.webp")
        con.execute("INSERT INTO esitleme_ara (sku, veri) VALUES ('Z', ?)", ("x" * 5000,))
        con.commit()
        con.execute("DELETE FROM sema_surumu WHERE dosya LIKE '002_%'")
        con.commit()
        assert any(d.startswith("002_") for d in gecisleri_uygula(con))
        assert gorsel_url(con, "Z1") is None
        assert gorsel_url(con, "Z2") == "/api/uploads/a.webp"
        assert con.execute("SELECT COUNT(*) FROM esitleme_ara").fetchone()[0] == 0
    finally:
        con.close()


def test_gorsel_rotasi_sembolik_bag_dis_hedef_404(istemci, tmp_path):
    dis = tmp_path / "dis.webp"
    dis.write_bytes(b"gizli")
    yol = istemci.app.state.ayarlar.gorsel_dizin / "k" / AD
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.symlink_to(dis)
    assert istemci.get(f"/gorsel/k/{AD}").status_code == 404


def test_gorsel_rotasi_dosya_gonderimden_once_silinirse_404(istemci, monkeypatch):
    import app.web.rotalar.gorsel as modul
    yol = _gorsel_yaz(istemci, AD, "k")
    gercek = modul.Path.read_bytes
    def sil_sonra_oku(self):
        self.unlink()
        return gercek(self)
    monkeypatch.setattr(modul.Path, "read_bytes", sil_sonra_oku)
    assert istemci.get(f"/gorsel/k/{AD}").status_code == 404
    assert not yol.exists()
