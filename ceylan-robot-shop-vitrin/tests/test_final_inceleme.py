"""Son (tüm dal) inceleme düzeltmeleri: I-1 adet alanları JS'siz / tarayıcı engelsiz, M-11 indeks göçü,
M-6 tüm POST rotalarında CSRF."""
import re
import sqlite3

import pytest
from starlette.routing import Route

from app.db import GECIS_KLASORU, baglan, gecisleri_uygula
from tests.conftest import csrf_al, sayfa_denetle
from tests.test_web_g3j import _bildirimler, _metin
from tests.test_web_sepet_odeme import _kur, _sepete_ekle, _urun, db  # noqa: F401


def _bolum(html, desen):
    m = re.search(desen, html, re.S)
    assert m, desen
    return m.group(0)


# =====================================================================================================
# I-1 — ürün sayfası adet alanı
# =====================================================================================================

def test_urun_sayfasi_adet_alani_tarayicida_engellenmez(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-FI1", ad="Adet Alanı Ürünü", fiyat="100.00", stok=5)
    html = sayfa_denetle(istemci.get(f"/tr/urun/{uid}"))
    form = _bolum(html, r'<form class="sepet-form"[^>]*>.*?</form>')
    girdi = _bolum(form, r'<input id="adet"[^>]*>')
    assert "novalidate" in form.split(">", 1)[0], form.split(">", 1)[0]
    assert 'type="number"' not in girdi and " required" not in girdi and " min=" not in girdi, girdi
    assert 'name="adet"' in girdi and 'inputmode="numeric"' in girdi and 'type="text"' in girdi


def _ekle(istemci, uid, adet, sonraki=True):
    csrf = csrf_al(istemci, f"/tr/urun/{uid}")
    veri = {"csrf": csrf, "urun_id": str(uid), "adet": adet}
    if sonraki:
        veri["sonraki"] = f"/tr/urun/{uid}"
    return istemci.post("/tr/sepet/ekle", data=veri, follow_redirects=False)


@pytest.mark.parametrize("adet, metin", [("1,5", "Geçersiz adet: tam sayı girin"),
                                         ("abc", "Geçersiz adet: tam sayı girin"),
                                         ("", "Geçersiz adet: tam sayı girin"),
                                         ("0", "Geçersiz adet: 1 veya daha büyük tam sayı girin"),
                                         ("-3", "Geçersiz adet: 1 veya daha büyük tam sayı girin")])
def test_urun_sayfasi_gecersiz_adet_bildirim_ve_capa(istemci, db, adet, metin):
    _kur(db)
    uid = _urun(db, sku="S-FI2", ad="Geçersiz Adet Ürünü", fiyat="100.00", stok=5)
    r = _ekle(istemci, uid, adet)
    assert r.status_code == 303 and r.headers["location"] == f"/tr/urun/{uid}#urun-{uid}", (r.status_code, r.headers)
    html = sayfa_denetle(istemci.get(f"/tr/urun/{uid}"))
    assert _bildirimler(html) == metin, _bildirimler(html)
    assert metin in _metin(_bolum(html, r'<p class="yerel-bildirim[^"]*" role="status">.*?</p>'))   # satın alma kutusu
    assert db.execute("SELECT COUNT(*) FROM sepet_kalemi").fetchone()[0] == 0     # 0 sessizce 1'e çevrilmez


def test_urun_sayfasi_gecersiz_adet_sonrakisiz_urun_capasina(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-FI3", ad="Sonrakisiz Ürün", fiyat="100.00", stok=5)
    r = _ekle(istemci, uid, "0", sonraki=False)
    assert r.status_code == 303 and r.headers["location"] == f"/tr/urun/{uid}#urun-{uid}"
    assert db.execute("SELECT COUNT(*) FROM sepet_kalemi").fetchone()[0] == 0


def test_urun_sayfasi_ust_sinir_99(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-FI4", ad="Çok Stoklu Ürün", fiyat="10.00", stok=500)
    r = _ekle(istemci, uid, "100")
    assert r.status_code == 303 and r.headers["location"].endswith(f"#urun-{uid}")
    assert db.execute("SELECT adet FROM sepet_kalemi").fetchone()[0] == 99
    assert "99" in _bildirimler(istemci.get(f"/tr/urun/{uid}").text)


# =====================================================================================================
# I-1 — hızlı talep formları (sıfır sonuç listesi, teklif sayfası)
# =====================================================================================================

def _hizli_form(html):
    return _bolum(html, r'<form class="hizli-teklif"[^>]*>.*?</form>')


def test_hizli_talep_formlari_novalidate_ve_metin_adet(istemci, db):
    _kur(db)
    for yol in ("/tr/ara?q=zzxqkwyok", "/tr/teklif"):
        form = _hizli_form(sayfa_denetle(istemci.get(yol)))
        assert "novalidate" in form.split(">", 1)[0], (yol, form.split(">", 1)[0])
        girdi = _bolum(form, r'<input id="ht-adet"[^>]*>')
        assert 'type="number"' not in girdi and " min=" not in girdi and 'inputmode="numeric"' in girdi, girdi


@pytest.mark.parametrize("adet", ["0", "-3", "1,5", "abc", "10000"])
def test_hizli_talep_gecersiz_adet_form_hatasi(istemci, db, adet):
    csrf = csrf_al(istemci, "/tr/teklif")
    r = istemci.post("/tr/teklif/hizli", data={"csrf": csrf, "ad": "Teknisyen", "iletisim": "+90 532 000 00 00",
                                              "parca_kodu": "KPS-600/20", "adet": adet}, follow_redirects=False)
    assert r.status_code == 400 and "hizli-teklif" in r.text            # çıplak 400 değil: form hata özetiyle
    assert _metin(_bolum(r.text, r'<p class="alan-hata" id="hata-adet">.*?</p>'))
    assert db.execute("SELECT COUNT(*) FROM teklif").fetchone()[0] == 0


# =====================================================================================================
# M-11 — 016 indeks göçü
# =====================================================================================================

def test_016_indeksler_ve_iki_kez_uygulanir(tmp_path):
    con = baglan(tmp_path / "ix.db")
    assert "016_indeksler.sql" in gecisleri_uygula(con)
    indeksler = {r["name"]: r["tbl_name"] for r in con.execute("SELECT name, tbl_name FROM sqlite_master"
                                                               " WHERE type = 'index'")}
    assert indeksler.get("ix_siparis_kalemi_siparis") == "siparis_kalemi"
    assert indeksler.get("ix_siparis_durum") == "siparis"
    sql = (GECIS_KLASORU / "016_indeksler.sql").read_text(encoding="utf-8")
    con.executescript(sql)          # IF NOT EXISTS: ikinci kez temiz uygulanır
    con.executescript(sql)
    assert gecisleri_uygula(con) == []
    plan = " ".join(str(tuple(r)) for r in con.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM siparis_kalemi WHERE siparis_id = 1"))
    assert "ix_siparis_kalemi_siparis" in plan, plan
    con.close()


# =====================================================================================================
# M-6 — tüm POST rotalarında CSRF
# =====================================================================================================

# Muafiyet listesi boş: bütün POST rotaları CSRF jetonu ister. Muafiyet eklenecekse rota + gerekçe burada yazılmalı.
CSRF_MUAF: dict[str, str] = {}
ORNEK_PARAM = {"dil": "tr", "no": "CR-DEMO-20261014-0001", "siparis_id": "1", "teklif_id": "1", "gb_id": "1"}


def _post_rotalari(app):
    return sorted({r.path for r in app.routes if isinstance(r, Route) and "POST" in (r.methods or set())})


def _somut(yol):
    return re.sub(r"\{(\w+)(?::\w+)?\}", lambda m: ORNEK_PARAM[m.group(1)], yol)


def test_csrf_tum_post_rotalari_listede(istemci):
    rotalar = _post_rotalari(istemci.app)
    assert len(rotalar) >= 26, rotalar
    for yol in rotalar:
        assert re.sub(r"\{(\w+)(?::\w+)?\}", "", yol).count("{") == 0 and all(
            p in ORNEK_PARAM for p in re.findall(r"\{(\w+)", yol)), yol


@pytest.mark.parametrize("jeton", ["yok", "yanlis"])
def test_csrf_tum_post_rotalari_jetonsuz_reddedilir(istemci, jeton):
    from tests.test_web_g3j import _yonetici
    _yonetici(istemci)                         # oturum var (csrf + yönetici): reddin nedeni yalnız jeton olsun
    csrf_al(istemci, "/tr/")
    veri = {"urun_id": "1", "adet": "1", "eposta": "x@ornek.test", "parola": "x", "metin": "x"}
    if jeton == "yanlis":
        veri["csrf"] = "yanlis-jeton"
    for yol in _post_rotalari(istemci.app):
        if yol in CSRF_MUAF:
            continue
        r = istemci.post(_somut(yol), data=veri, follow_redirects=False)
        assert r.status_code == 403, (yol, r.status_code)
