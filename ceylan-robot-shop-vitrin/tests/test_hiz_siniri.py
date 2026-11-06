"""HizSiniri bellek yönetimi: süpürme ve üst sınır (G2 düzeltme turu 1)."""
from app.web.guvenlik import HizSiniri


def test_pencere_gecince_tablo_bosalir():
    h = HizSiniri(limit=5, pencere=60.0)
    for i in range(20_000):
        assert h.izin(f"ip{i}", 100.0)
    assert len(h._kayit) == 20_000
    assert h.izin("yeni", 100.0 + 61.0)  # pencere geçti: süpürme bu çağrıda
    assert len(h._kayit) == 1


def test_supurme_her_istekte_degil_pencerede_bir(monkeypatch):
    h = HizSiniri(limit=5, pencere=60.0)
    cagri = []
    asil = h._supur
    monkeypatch.setattr(h, "_supur", lambda s: (cagri.append(s), asil(s)))
    for i in range(1000):
        h.izin(f"ip{i}", 100.0 + i * 0.01)  # 10 sn içinde
    assert cagri == []
    h.izin("x", 170.0)
    assert len(cagri) == 1


def test_ust_sinir_korunur_en_eskiler_atilir():
    h = HizSiniri(limit=5, pencere=3600.0, azami=1000)
    for i in range(5000):
        h.izin(f"ip{i}", 100.0 + i * 0.001)
    assert len(h._kayit) <= 1000
    assert "ip4999" in h._kayit and "ip0" not in h._kayit


def test_limit_ve_pencere_davranisi_korunur():
    h = HizSiniri(limit=2, pencere=10.0)
    assert h.izin("a", 0.0) and h.izin("a", 1.0) and not h.izin("a", 2.0)
    assert h.izin("a", 10.5)  # ilk kayıt pencere dışına çıktı
