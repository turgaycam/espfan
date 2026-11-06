# Ceylan Robot satış sitesi mockup'ı — uygulama planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Netsis kaynaklı gerçek ürünlerle, yurt içi/yurt dışı online ödemeli (simülasyon) e-ticaret sitesinin tıklanabilir mockup'ını cr-web-demo VM'inde `http://192.168.5.30:3030` adresinde çalışır hale getirmek.

**Architecture:** FastAPI + Jinja2 ile sunucu tarafında üretilen sayfalar, SQLite (WAL) veri deposu. Katalog her gece mevcut sitenin public API'sinden yavaşça eşitlenir; Netsis'e dokunulmaz. İş kuralları (fiyat, KDV, kur, teklif, ödeme simülasyonu) web katmanından bağımsız, saf Python servis modüllerindedir ve birim testleriyle sabitlenir.

**Tech Stack:** Python 3.12, FastAPI 0.115, Jinja2 3.1, httpx 0.27, SQLite (FTS5), pytest 8, Playwright (yalnız laptopta, uçtan uca), systemd, ufw.

**Spec:** `docs/specs/2026-10-12-satis-sitesi-mockup-design.md` (bağımsız değerlendirme 8,7/10). Modüller arası adlar ve şema: aşağıdaki **Ortak arayüz sözleşmesi** bölümü — bağlayıcıdır.

## Global Constraints

- Hedef: `cr-web-demo` VM (192.168.5.30), port **3030**; port 80 (`web-demo.service`) ve 3027 (`aic-demo.service`) servislerine **dokunulmaz**.
- Laptopta yalnız git deposu ve `dagitim/deploy.sh`; Python bağımlılıkları laptopa kurulmaz. `pytest` VM'de, release'in kendi venv'inde çalışır. Playwright uçtan uca testleri laptopta, staging adresine karşı.
- Klasör: `/opt/cr-shop-demo/{releases/<YYYYMMDD-HHMM>/(venv dahil), current, veri/shop.db, ortam (600), yedek/}`; son 3 release tutulur.
- Servis kullanıcısı `crshop`; `cr-shop-demo.service` `MemoryMax=600M`; `cr-shop-esitle.service` `MemoryMax=400M`, `TimeoutStartSec=30min`; zamanlayıcılar 02:30 eşitleme, 03:00 yedek (7 gün), 06:00 kur.
- ufw: 3030/tcp yalnız 192.168.2.0/24, 192.168.5.0/24, 192.168.11.0/24, 192.168.12.0/24.
- Eşitleme: sayfa başına 20 kayıt, istekler arası 1 sn, zaman aşımı 30 sn, en fazla 3 deneme (ilk istek + 2 yeniden deneme; 2 ve 4 sn bekleme — K2).
- Fiyat tabanı net EUR; teklif eşiği 15.000 € (net, `>`); robot kökleri `bantlar.yaml`'da; temsili kargo TR 15 € + KDV; yuvarlama ROUND_HALF_UP 2 hane, satır bazında.
- Test kartları: `4111 1111 1111 1111` başarılı, `4000 0000 0000 0002` ret, SMS `000000`; diğer her kart reddedilir; tam kart numarası hiçbir yere yazılmaz; ödenmeyen sipariş 30 dk sonra `iptal`.
- Her sayfada "DEMO – gerçek satış ve ödeme yapılmaz" bandı; her yanıtta `X-Robots-Tag: noindex, nofollow` ve CSP (satır içi script/style yok).
- Gerçek kişi verisi yok; demo verisi sahte (`QATestUser` standardı). Gizli bilgiler yalnız `/opt/cr-shop-demo/ortam` dosyasında.
- sudo gerektiren her komut (paket kurulumu, kullanıcı, systemd, ufw) çalıştırılmadan önce kullanıcıya gösterilir ve onayı alınır.
- Mockup boyunca veritabanı geçişleri yalnız geriye uyumlu (tablo/kolon ekleme).
- Commit sonu: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; commit kimliği `Sami Yilmaz <samiyilmaz@ceylanrobot.com>`.

## Review Focus

1. **Türkçe büyük/küçük harf ve aksanlı arama:** "RÖLE", "röle", "role", "İzleme", "izleme" aynı ürünleri bulmalı; boş veya yalnız boşluk arama 500 değil boş sonuç/yönlendirme → Görev 6 testi `test_arama_turkce_harf_duyarsiz`, `test_bos_arama`.
2. **Bozuk form girdileri:** adet "abc", "0", "-3", "1000"; fiyat filtresi "x"; sayfa "-1" / "99999" → 400 veya kısma, asla 500 → Görev 8 `test_adet_sinirlari`, Görev 6 `test_sayfa_kisilir`, Görev 12 `test_bozuk_sorgu_parametreleri`.
3. **Sepetteyken pasifleşen ya da teklif zorunlu hale gelen ürün:** ödeme adımında sepetten çıkarılmalı ve kullanıcıya adıyla bildirilmeli → Görev 8 `test_pasif_urun_sepetten_duser`, Görev 14 `test_odemede_dusen_urun_bildirilir`.
4. **API'den bozuk kayıt veya bozuk karakter:** `categoryId` null, `price` yok, `sku` boş olan kayıt atlanır ve sayılır, tur çökmez → Görev 5 `test_bozuk_kayit_atlanir`. Gerçek veride kategori adı bozuk kodlamayla geliyor (12.10'da görüldü: `"GÜÇ KAYNA�\udc9eI"`, JSON'da tek başına surrogate). Tek başına surrogate SQLite'a yazılırken `UnicodeEncodeError` verir. `esitleme.esitle` her metni `metin_temizle` ile temizler: `�` + surrogate çifti ve tek surrogate'lar tek bir `�`'ye indirilir → Görev 5 `test_bozuk_karakter_temizlenir`.
5. **Kurcalanmış/eski oturum:** silinmiş müşteriye işaret eden `mid`, geçersiz imzalı çerez → misafir gibi davranılır, 500 yok → Görev 11 `test_eski_oturum_misafire_duser`.

---

## Yürütme sırası

- **Görevler numara sırasıyla seri çalışır:** 0 → 1 → 2 → 3 → 4 → 5 → 5A → 6 → … → 18.
- **Ortak dosyalar:** Görev 11–16 aynı dosyalara ekleme yapar: `app/web/dil/tr.json`, `en.json`, `app/web/statik/site.css`, `app/web/sablonlar/_makrolar.html`, `tests/conftest.py`. Bu yüzden bu görevler **paralel çalıştırılmaz.**
- **Paralel çalışabilecek görevler:** Yalnız 2 ve 3. İkisi de yalnız Görev 1'e bağlı ve ortak dosyaya dokunmuyor. Paralel çalıştırılırsa her biri ayrı git worktree'de çalışır; `test-vm.sh` her çalışma ağacı için VM'de ayrı klasör kullanır.
- **VM kullanımı:** Ajanlar VM'e yalnız `dagitim/test-vm.sh` üzerinden dokunur. Görev 0'ın venv/pip kurulum adımları (1–3), Görev 17'deki `systemd-analyze` kontrolü ve Görev 18'in kurulum adımları istisnadır; sudo gerektiren her adım kullanıcı onayıyla yapılır.
- **Her görevin sonunda** yönetici iki komutu çalıştırıp sonucu görür:
  - `bash dagitim/test-vm.sh -q`: bütün testler geçmeli.
  - `python -c "import json;a=json.load(open('app/web/dil/tr.json',encoding='utf-8'));b=json.load(open('app/web/dil/en.json',encoding='utf-8'));assert a.keys()==b.keys()"`: Görev 11'den sonra tr ve en anahtarları eşit olmalı.

## Ortak arayüz sözleşmesi


Bu dosya modüller arasındaki adları, tipleri ve şemayı **sabitler**. Görev yazarları bu adları birebir kullanır; değişiklik gerekiyorsa yazmazlar, not düşerler.

## Genel kurallar
- Python 3.12, yalnız şu paketler: `fastapi==0.115.*`, `uvicorn==0.32.*`, `jinja2==3.1.*`, `httpx==0.27.*`, `python-multipart==0.0.*`, `itsdangerous==2.2.*`, `pyyaml==6.0.*`; test: `pytest==8.*`. Playwright yalnız laptopta (uçtan uca), `requirements.txt`'e girmez.
- Para: her yerde `decimal.Decimal`, float yasak. Yuvarlama `app.para.yuvarla` (ROUND_HALF_UP, 2 hane).
- Zaman: servis fonksiyonları `simdi: datetime` (UTC, tz-aware) parametresi alır; testler sabit zaman verir. Veritabanında ISO-8601 metin (`datetime.isoformat()`).
- Veritabanı erişimi: her servis fonksiyonu ilk parametre olarak `con: sqlite3.Connection` alır; servisler `commit` yapmaz, **çağıran** (web rotası, betik) `with con:` ile transaction yönetir. İstisna: `esitleme.esitle` ve `db.gecisleri_uygula` kendi transaction'larını yönetir.
- Metin dili: kullanıcıya görünen metinler `app/web/dil/tr.json` ve `en.json` anahtarlarıyla; servis katmanı metin üretmez, hata **kodu** üretir.
- Testler: `tests/` altında, `pytest` ile; her test `tmp_path` altında yeni veritabanı kullanır (fixture `con`, `tests/conftest.py`). Ağ yok: HTTP yanıtları `tests/ornekler/` dosyalarından `httpx.MockTransport` ile verilir.
- Komutlar depo kökünden: `python -m pytest -q`.

## Dosya yapısı
```
requirements.txt
app/__init__.py
app/ayarlar.py          Ayarlar, ayarlari_oku
app/db.py               baglan, gecisleri_uygula
app/gecisler/001_baslangic.sql
app/para.py             d, yuvarla
app/metin.py            normalize
app/katalog/__init__.py, depo.py
app/esitleme/__init__.py, kaynak.py, esitle.py
app/fiyat/__init__.py, bantlar.yaml, kurallar.py, kur.py
app/hesap/__init__.py, dogrulama.py, servis.py
app/sepet/__init__.py, servis.py
app/siparis/__init__.py, servis.py, odeme_sim.py
app/teklif/__init__.py, servis.py
app/geribildirim/__init__.py, servis.py
app/web/__init__.py, uygulama.py, guvenlik.py, dil.py, baglam.py
app/web/rotalar/__init__.py, katalog.py, hesap.py, sepet_odeme.py, teklif_gb.py, yonetim.py, yasal.py, genel.py
app/web/dil/tr.json, en.json
app/web/sablonlar/*.html, sablonlar/yonetim/*.html, sablonlar/yasal/{tr,en}/*.html
app/web/statik/site.css, site.js, yer-tutucu/*.svg
betikler/esitle.py, kur_al.py, yedek.sh, yonetici_ozet.py
dagitim/deploy.sh, kurulum-vm.sh, systemd/*.service, *.timer, ortam.ornek
tests/conftest.py, tests/ornekler/*, tests/test_*.py
e2e/ (laptopta) test_kabul.py, conftest.py
```

## Şema — `app/gecisler/001_baslangic.sql` (birebir)
```sql
CREATE TABLE sema_surumu (dosya TEXT PRIMARY KEY, uygulandi TEXT NOT NULL);

CREATE TABLE kategori (
  id INTEGER PRIMARY KEY,
  kaynak_id TEXT NOT NULL UNIQUE,      -- API _id
  erp_id INTEGER,
  ad TEXT NOT NULL,
  ust_kaynak_id TEXT,                  -- API parentId
  yol TEXT NOT NULL,                   -- "12.41.243"
  seviye INTEGER NOT NULL,
  aktif INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX ix_kategori_yol ON kategori(yol);

CREATE TABLE urun (
  id INTEGER PRIMARY KEY,
  sku TEXT NOT NULL UNIQUE,
  ad TEXT NOT NULL,
  uretici_kodu TEXT,
  kategori_id INTEGER REFERENCES kategori(id),
  kok_kategori_ad TEXT NOT NULL DEFAULT '',
  kdv_orani TEXT NOT NULL DEFAULT '20',          -- Decimal metin
  stok INTEGER NOT NULL DEFAULT 0,
  tedarik_suresi_gun INTEGER,
  gorsel_url TEXT,
  kaynak_fiyat_eur TEXT NOT NULL DEFAULT '0',
  temsili_fiyat_eur TEXT NOT NULL,                -- gösterilen net EUR (kaynak>0 ise kaynak)
  fiyat_temsili INTEGER NOT NULL DEFAULT 1,       -- 1: temsili rozet göster
  teklif_zorunlu INTEGER NOT NULL DEFAULT 0,
  durum_kodu TEXT NOT NULL DEFAULT 'belirtilmemis',
  durum_ornek INTEGER NOT NULL DEFAULT 0,
  aktif INTEGER NOT NULL DEFAULT 1,
  kaynak_guncelleme TEXT,
  olusturma TEXT NOT NULL
);
CREATE INDEX ix_urun_kategori ON urun(kategori_id);
CREATE VIRTUAL TABLE urun_ara USING fts5(metin, urun_id UNINDEXED, tokenize='unicode61 remove_diacritics 2');

CREATE TABLE esitleme_ara (sku TEXT PRIMARY KEY, veri TEXT NOT NULL);
CREATE TABLE esitleme_gunlugu (
  id INTEGER PRIMARY KEY, basla TEXT NOT NULL, bitis TEXT,
  durum TEXT NOT NULL CHECK (durum IN ('calisiyor','tam','eksik','hata')),
  api_toplam INTEGER, cekilen INTEGER NOT NULL DEFAULT 0, eklenen INTEGER NOT NULL DEFAULT 0,
  guncellenen INTEGER NOT NULL DEFAULT 0, pasiflenen INTEGER NOT NULL DEFAULT 0, bozuk INTEGER NOT NULL DEFAULT 0, hata TEXT
);

CREATE TABLE kur (tarih TEXT PRIMARY KEY, eur_alis TEXT NOT NULL, eur_satis TEXT NOT NULL, alindi TEXT NOT NULL);

CREATE TABLE musteri (
  id INTEGER PRIMARY KEY,
  tip TEXT NOT NULL CHECK (tip IN ('bireysel','kurumsal','yurtdisi')),
  ad TEXT NOT NULL, eposta TEXT NOT NULL UNIQUE COLLATE NOCASE, parola_ozeti TEXT NOT NULL,
  vergi_kimlik_no TEXT, vergi_dairesi TEXT, vat_id TEXT, ulke TEXT NOT NULL,
  kvkk_onay TEXT NOT NULL, iys_onay INTEGER NOT NULL DEFAULT 0, olusturma TEXT NOT NULL
);
CREATE TABLE adres (
  id INTEGER PRIMARY KEY, musteri_id INTEGER NOT NULL REFERENCES musteri(id),
  tur TEXT NOT NULL CHECK (tur IN ('teslimat','fatura')),
  ad_soyad TEXT NOT NULL, satir1 TEXT NOT NULL, satir2 TEXT, sehir TEXT NOT NULL,
  posta_kodu TEXT, ulke TEXT NOT NULL, telefon TEXT
);

CREATE TABLE sepet (id INTEGER PRIMARY KEY, oturum_id TEXT, musteri_id INTEGER REFERENCES musteri(id), olusturma TEXT NOT NULL);
CREATE UNIQUE INDEX ux_sepet_oturum ON sepet(oturum_id) WHERE oturum_id IS NOT NULL;
CREATE UNIQUE INDEX ux_sepet_musteri ON sepet(musteri_id) WHERE musteri_id IS NOT NULL;
CREATE TABLE sepet_kalemi (sepet_id INTEGER NOT NULL REFERENCES sepet(id), urun_id INTEGER NOT NULL REFERENCES urun(id), adet INTEGER NOT NULL CHECK (adet BETWEEN 1 AND 99), PRIMARY KEY (sepet_id, urun_id));

CREATE TABLE siparis (
  id INTEGER PRIMARY KEY, no TEXT NOT NULL UNIQUE, musteri_id INTEGER NOT NULL REFERENCES musteri(id),
  durum TEXT NOT NULL CHECK (durum IN ('odeme_bekliyor','odendi','hazirlaniyor','kargoda','teslim','iptal')),
  para_birimi TEXT NOT NULL CHECK (para_birimi IN ('TRY','EUR')),
  ara_toplam TEXT NOT NULL, kdv TEXT NOT NULL, kargo TEXT NOT NULL, toplam TEXT NOT NULL,
  kur TEXT, kur_tarihi TEXT, ihracat_istisnasi INTEGER NOT NULL,
  teslim_yontemi TEXT NOT NULL CHECK (teslim_yontemi IN ('kargo','fabrika','yurtdisi_dap')),
  teslimat_ulkesi TEXT NOT NULL, teslimat_adresi TEXT NOT NULL, fatura_adresi TEXT NOT NULL,
  kart_son4 TEXT, sepet_id INTEGER NOT NULL, olusturma TEXT NOT NULL, guncelleme TEXT NOT NULL
);
CREATE TABLE siparis_kalemi (
  siparis_id INTEGER NOT NULL REFERENCES siparis(id), urun_id INTEGER NOT NULL, sku TEXT NOT NULL, ad TEXT NOT NULL,
  adet INTEGER NOT NULL, birim_net_eur TEXT NOT NULL, net TEXT NOT NULL, kdv TEXT NOT NULL, brut TEXT NOT NULL,
  tedarik_teyit INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE odeme_denemesi (
  islem_anahtari TEXT PRIMARY KEY, siparis_id INTEGER NOT NULL REFERENCES siparis(id),
  kart_son4 TEXT, kart_sonucu TEXT CHECK (kart_sonucu IN ('basarili','ret')),
  durum TEXT NOT NULL CHECK (durum IN ('sms_bekliyor','basarili','ret','sms_hatali','gecersiz_kart')),
  olusturma TEXT NOT NULL
);

CREATE TABLE teklif (
  id INTEGER PRIMARY KEY, no TEXT NOT NULL UNIQUE, musteri_id INTEGER REFERENCES musteri(id),
  ad TEXT NOT NULL, firma TEXT, eposta TEXT NOT NULL, telefon TEXT, ulke TEXT NOT NULL,
  urun_id INTEGER REFERENCES urun(id), adet INTEGER NOT NULL DEFAULT 1, mesaj TEXT NOT NULL,
  durum TEXT NOT NULL DEFAULT 'yeni' CHECK (durum IN ('yeni','inceleniyor','teklif_verildi','kapandi')),
  olusturma TEXT NOT NULL
);
CREATE TABLE geri_bildirim (
  id INTEGER PRIMARY KEY, sayfa TEXT NOT NULL, metin TEXT NOT NULL, isim TEXT,
  durum TEXT NOT NULL DEFAULT 'yeni' CHECK (durum IN ('yeni','okundu','yapildi')), olusturma TEXT NOT NULL
);
```

## İmzalar

### app/ayarlar.py
```python
@dataclass(frozen=True)
class Ayarlar:
    db_yolu: Path
    gizli_anahtar: str
    yonetici_kullanici: str
    yonetici_parola_ozeti: str        # hesap.servis.parola_ozeti biçimi
    kaynak_api: str = "https://www.ceylanrobot.com"
    gorsel_kok: str = "https://www.ceylanrobot.com"
    bantlar_yolu: Path = Path(__file__).parent / "fiyat" / "bantlar.yaml"

def ayarlari_oku(ortam: Mapping[str, str] = os.environ) -> Ayarlar
# Anahtarlar: SHOP_DB, SHOP_GIZLI_ANAHTAR, SHOP_YONETICI, SHOP_YONETICI_OZET, SHOP_KAYNAK_API (ops.)
# Eksik zorunlu anahtar -> RuntimeError(anahtar adı)
```
### app/db.py
```python
def baglan(yol: Path) -> sqlite3.Connection   # row_factory=sqlite3.Row; PRAGMA foreign_keys=ON, journal_mode=WAL, busy_timeout=5000
def gecisleri_uygula(con: sqlite3.Connection) -> list[str]   # app/gecisler/*.sql sıra numarasıyla; uygulananları sema_surumu'na yazar; yeni uygulananların adlarını döner
```
### app/para.py
```python
IKI_HANE = Decimal("0.01")
def d(deger: str | int | Decimal) -> Decimal      # float verilirse TypeError
def yuvarla(x: Decimal) -> Decimal                 # quantize(IKI_HANE, ROUND_HALF_UP)
```
### app/metin.py
```python
def normalize(s: str) -> str   # Türkçe küçük harf (I->ı, İ->i önce), sonra ı->i ş->s ğ->g ü->u ö->o ç->c, casefold, fazla boşluk tekle
def metin_temizle(s: str | None) -> str | None   # "�"+surrogate çiftleri ve tek surrogate'lar (U+D800..DFFF) -> tek "�"; baş/son boşluk kırp; None -> None
```
### app/hesap/dogrulama.py
```python
def vkn_gecerli(s: str) -> bool     # 10 hane, GİB algoritması
def tckn_gecerli(s: str) -> bool    # 11 hane, ilk hane 0 değil, 10. ve 11. hane kontrolleri
```
### app/fiyat/kur.py
```python
TCMB_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"
@dataclass(frozen=True)
class Kur:
    tarih: date
    eur_alis: Decimal
    eur_satis: Decimal
def tcmb_ayristir(xml: bytes) -> Kur                         # Currency Kod="EUR" ForexBuying/ForexSelling; Tarih_Date Tarih="dd.mm.yyyy"
def kur_kaydet(con, kur: Kur, simdi: datetime) -> None       # INSERT OR REPLACE
def son_kur(con) -> Kur | None
def kur_bayat_mi(kur: Kur, bugun: date) -> bool              # (bugun - kur.tarih).days > 3
def kur_al(con, http: httpx.Client, simdi: datetime) -> Kur   # indir+ayrıştır+kaydet; hata -> istisna yükselir (çağıran son_kur'a düşer)
```
### app/fiyat/kurallar.py
```python
TEKLIF_ESIGI_EUR = Decimal("15000")
KARGO_TR_NET_EUR = Decimal("15.00")
class MusteriTipi(StrEnum): BIREYSEL = "bireysel"; KURUMSAL = "kurumsal"; YURTDISI = "yurtdisi"
class TeslimYontemi(StrEnum): KARGO = "kargo"; FABRIKA = "fabrika"; YURTDISI_DAP = "yurtdisi_dap"
@dataclass(frozen=True)
class Bantlar:
    robot_kokleri: frozenset[str]                 # normalize edilmiş kök kategori adları
    bantlar: Mapping[str, tuple[Decimal, Decimal]]  # normalize kök ad -> (min, max) net EUR
    varsayilan: tuple[Decimal, Decimal]
def bantlari_oku(yol: Path) -> Bantlar
def temsili_fiyat_eur(sku: str, kok_kategori_ad: str, bantlar: Bantlar) -> Decimal
    # sha256(sku) ilk 8 bayt -> [0,1) oran; min + oran*(max-min); 1 €'ya yuvarla (ROUND_HALF_UP) ve .00 ile döndür
def teklif_zorunlu_mu(kok_kategori_ad: str, net_eur: Decimal, bantlar: Bantlar) -> bool
    # normalize(kok) in robot_kokleri  or  net_eur > TEKLIF_ESIGI_EUR
@dataclass(frozen=True)
class Baglam:
    musteri_tipi: MusteriTipi
    teslimat_ulkesi: str          # ISO-3166 alpha-2, büyük harf
def kdv_uygulanir(b: Baglam) -> bool              # teslimat_ulkesi == "TR"
def tahsilat_para_birimi(b: Baglam) -> str        # BIREYSEL->"TRY"; KURUMSAL->"TRY" if TR teslim else "EUR"; YURTDISI->"EUR"
def gosterim_kdv_dahil(b: Baglam) -> bool         # BIREYSEL and kdv_uygulanir
@dataclass(frozen=True)
class Kalem:
    urun_id: int; sku: str; ad: str; adet: int
    birim_net_eur: Decimal; kdv_orani: Decimal      # 20 = %20
    tedarik_teyit: bool = False                     # stok 0 ve tedarik süresi yok
@dataclass(frozen=True)
class SatirTutar:
    kalem: Kalem; net: Decimal; kdv: Decimal; brut: Decimal   # tahsilat para biriminde
@dataclass(frozen=True)
class SepetTutari:
    para_birimi: str
    satirlar: tuple[SatirTutar, ...]
    ara_toplam: Decimal; kdv: Decimal
    kargo_net: Decimal; kargo_kdv: Decimal
    toplam: Decimal
    kur: Decimal | None                # TRY tahsilatta kullanılan EUR satış kuru
    ihracat_istisnasi: bool
def sepet_hesapla(kalemler: Sequence[Kalem], b: Baglam, teslim: TeslimYontemi, kur_eur_try: Decimal | None) -> SepetTutari
    # TRY tahsilatta kur None ise ValueError("kur_yok")
    # satır: net = yuvarla(birim_net_eur*adet [*kur]); kdv = yuvarla(net*kdv_orani/100) if kdv_uygulanir else 0; brut = net+kdv
    # kargo: KARGO & TR -> KARGO_TR_NET_EUR [*kur] yuvarla, kdv %20; FABRIKA -> 0; YURTDISI_DAP -> 0
    # ara_toplam = Σnet ; kdv = Σkdv + kargo_kdv ; toplam = ara_toplam + kargo_net + kdv
@dataclass(frozen=True)
class FiyatGosterim:
    ana_tutar: Decimal; ana_para: str; kdv_dahil: bool
    ikincil_tutar: Decimal | None; ikincil_para: str | None
def birim_fiyat_gosterimi(net_eur: Decimal, kdv_orani: Decimal, b: Baglam, kur_eur_try: Decimal | None) -> FiyatGosterim
    # BIREYSEL&TR: ana=TRY KDV dahil, ikincil=EUR net ; KURUMSAL: ana=EUR net, ikincil=TRY net ; YURTDISI veya teslimat≠TR: ana=EUR net, ikincil yok
    # kur None ise TRY gerektiren gösterim ana=EUR net'e düşer, ikincil None
```
### app/esitleme/kaynak.py
```python
class KaynakHatasi(Exception): ...
class KaynakIstemci:
    def __init__(self, http: httpx.Client, taban: str, bekleme: float = 1.0, uyku: Callable[[float], None] = time.sleep): ...
    def kategoriler(self) -> list[dict]                              # GET {taban}/api/public/categories
    def urun_sayfasi(self, sayfa: int, limit: int = 20) -> tuple[list[dict], int]
        # GET {taban}/api/public/products?page=&limit= ; (data, total); en fazla 3 çağrı, beklemeler 2 ve 4 sn (K2); her çağrıdan önce `bekleme` kadar uyku; sonunda KaynakHatasi
```
### app/esitleme/esitle.py
```python
@dataclass(frozen=True)
class TurSonucu:
    durum: Literal["tam", "eksik", "hata"]
    api_toplam: int | None; cekilen: int; eklenen: int; guncellenen: int; pasiflenen: int; hata: str | None
def esitle(con, kaynak: KaynakIstemci, bantlar: Bantlar, simdi: Callable[[], datetime]) -> TurSonucu
    # 1) günlüğe 'calisiyor' 2) kategoriler upsert 3) sayfalar -> esitleme_ara (bozuk kayıt atlanır, sayılır)
    # 4) benzersiz sku sayısı == ilk ve son sayfanın total'i ise 'tam': tek transaction'da upsert + kaynakta olmayanlar aktif=0 + urun_ara yeniden kur
    #    değilse 'eksik': upsert + urun_ara yeniden kur, pasifleme YOK ; istisna -> 'hata', veri değişmez
    # 5) günlüğü kapat
def son_basarili_esitleme(con) -> datetime | None      # son 'tam' kaydın bitis'i
def son_esitleme(con) -> sqlite3.Row | None
```
### app/katalog/depo.py
```python
@dataclass(frozen=True)
class Kategori: id: int; ad: str; yol: str; seviye: int; ust_id: int | None
@dataclass
class KategoriDugum: kategori: Kategori; cocuklar: list["KategoriDugum"]; urun_sayisi: int   # alt kategoriler dahil aktif ürün
@dataclass(frozen=True)
class Urun:
    id: int; sku: str; ad: str; uretici_kodu: str | None
    kategori_id: int | None; kategori_ad: str | None; kategori_yol: str | None; kok_kategori_ad: str
    kdv_orani: Decimal; stok: int; tedarik_suresi_gun: int | None; gorsel_url: str | None
    net_fiyat_eur: Decimal; fiyat_temsili: bool; teklif_zorunlu: bool
    durum_kodu: str; durum_ornek: bool; aktif: bool
@dataclass(frozen=True)
class ListeSorgusu:
    kategori_id: int | None = None; arama: str | None = None; stokta: bool = False
    fiyat_min: Decimal | None = None; fiyat_max: Decimal | None = None      # net EUR
    siralama: Literal["ad", "fiyat_artan", "fiyat_azalan"] = "ad"
    sayfa: int = 1; sayfa_boyu: int = 24
@dataclass(frozen=True)
class ListeSonucu: urunler: list[Urun]; toplam: int; sayfa: int; sayfa_sayisi: int
def kategori_agaci(con) -> list[KategoriDugum]
def kategori_getir(con, kategori_id: int) -> Kategori | None
def kategori_yolu(con, kategori_id: int) -> list[Kategori]           # kökten yaprağa
def urun_getir(con, urun_id: int) -> Urun | None                      # pasif ürün de döner (aktif=False)
def urun_listele(con, s: ListeSorgusu) -> ListeSonucu                 # yalnız aktif; kategori alt ağacı dahil; arama FTS5 normalize(arama) prefix eşleşme; sayfa 1..sayfa_sayisi'na kısılır
def one_cikanlar(con, adet: int = 8) -> list[Urun]                    # görseli olan aktif ürünler, yoksa herhangi aktif
```
### app/hesap/servis.py
```python
@dataclass(frozen=True)
class Musteri:
    id: int; tip: MusteriTipi; ad: str; eposta: str; ulke: str
    vergi_kimlik_no: str | None; vergi_dairesi: str | None; vat_id: str | None; iys_onay: bool
@dataclass(frozen=True)
class KayitGirdisi:
    tip: MusteriTipi; ad: str; eposta: str; parola: str; ulke: str
    kvkk_onay: bool; iys_onay: bool = False
    vergi_kimlik_no: str | None = None; vergi_dairesi: str | None = None; vat_id: str | None = None
class KayitHatasi(ValueError):
    def __init__(self, alan: str, kod: str): ...     # kod örn. "zorunlu", "gecersiz_vkn", "eposta_kayitli", "parola_kisa", "kvkk_onay_yok"
@dataclass(frozen=True)
class Adres: ad_soyad: str; satir1: str; sehir: str; ulke: str; satir2: str | None = None; posta_kodu: str | None = None; telefon: str | None = None
def parola_ozeti(parola: str) -> str            # "scrypt$16384$8$1$<tuz_hex>$<ozet_hex>"
def parola_dogru(parola: str, ozet: str) -> bool
def kayit_ol(con, g: KayitGirdisi, simdi: datetime) -> Musteri
    # kurallar: parola >= 10 karakter; eposta '@' içerir; KURUMSAL -> vergi_kimlik_no zorunlu (10 hane vkn_gecerli veya 11 hane tckn_gecerli) + vergi_dairesi zorunlu, ulke "TR";
    # BIREYSEL -> ulke "TR", iys_onay serbest ; YURTDISI -> ulke != "TR", iys_onay False'a zorlanır ; kvkk_onay True olmalı
def giris(con, eposta: str, parola: str) -> Musteri | None
def musteri_getir(con, musteri_id: int) -> Musteri | None
def adres_kaydet(con, musteri_id: int, tur: Literal["teslimat", "fatura"], a: Adres) -> int
def adres_son(con, musteri_id: int, tur: str) -> Adres | None
```
### app/sepet/servis.py
```python
class TeklifZorunlu(Exception): ...
class UrunYok(Exception): ...
ADET_MIN, ADET_MAX = 1, 99
def sepet_bul(con, oturum_id: str | None, musteri_id: int | None, simdi: datetime) -> int
    # musteri_id varsa üyenin sepeti (yoksa oluştur); yoksa oturum sepeti (yoksa oluştur)
def ekle(con, sepet_id: int, urun_id: int, adet: int = 1) -> None
    # ürün yok/pasif -> UrunYok ; teklif_zorunlu -> TeklifZorunlu ; adet ADET_MIN..ADET_MAX'e kısılır; mevcutsa toplanır (en fazla 99)
def adet_ayarla(con, sepet_id: int, urun_id: int, adet: int) -> None    # <1 -> kaldır ; >99 -> 99
def kaldir(con, sepet_id: int, urun_id: int) -> None
def bosalt(con, sepet_id: int) -> None
def kalemler(con, sepet_id: int) -> tuple[list[Kalem], list[str]]
    # (geçerli kalemler, kaldırılan ürünlerin adları) — pasifleşmiş veya teklif_zorunlu olmuş ürünler sepetten silinir ve adları döner
def adet_toplam(con, sepet_id: int) -> int
def birlestir(con, misafir_sepet_id: int, uye_sepet_id: int) -> int   # adetler toplanır (99 sınırı), misafir sepeti silinir; birleşen kalem sayısı
```
### app/siparis/servis.py
```python
class SiparisDurumu(StrEnum): ODEME_BEKLIYOR="odeme_bekliyor"; ODENDI="odendi"; HAZIRLANIYOR="hazirlaniyor"; KARGODA="kargoda"; TESLIM="teslim"; IPTAL="iptal"
IZINLI_GECISLER: dict[SiparisDurumu, frozenset[SiparisDurumu]] = {
  ODEME_BEKLIYOR: {ODENDI, IPTAL}, ODENDI: {HAZIRLANIYOR, IPTAL}, HAZIRLANIYOR: {KARGODA}, KARGODA: {TESLIM}, TESLIM: set(), IPTAL: set()}
ODEME_SURESI = timedelta(minutes=30)
class GecersizGecis(Exception): ...
class SepetBos(Exception): ...
@dataclass(frozen=True)
class SiparisKalemi: urun_id: int; sku: str; ad: str; adet: int; birim_net_eur: Decimal; net: Decimal; kdv: Decimal; brut: Decimal; tedarik_teyit: bool
@dataclass(frozen=True)
class Siparis:
    id: int; no: str; musteri_id: int; durum: SiparisDurumu; para_birimi: str
    ara_toplam: Decimal; kdv: Decimal; kargo: Decimal; toplam: Decimal
    kur: Decimal | None; kur_tarihi: date | None; ihracat_istisnasi: bool
    teslim_yontemi: TeslimYontemi; teslimat_ulkesi: str; teslimat_adresi: Adres; fatura_adresi: Adres
    kart_son4: str | None; sepet_id: int; olusturma: datetime; kalemler: tuple[SiparisKalemi, ...]
def siparis_olustur(con, musteri: Musteri, sepet_id: int, teslim: TeslimYontemi, teslimat: Adres, fatura: Adres, kur: Kur | None, simdi: datetime) -> Siparis
    # Baglam(musteri.tip, teslimat.ulke); sepet_hesapla ile anlık görüntü; no "CR-DEMO-YYYYMMDD-NNNN" (gün içi sıra); durum ODEME_BEKLIYOR ; boş sepet -> SepetBos
def siparis_getir(con, siparis_id: int, simdi: datetime) -> Siparis | None      # önce zaman aşımı uygular
def siparis_no_ile(con, no: str, simdi: datetime) -> Siparis | None
def musteri_siparisleri(con, musteri_id: int, simdi: datetime) -> list[Siparis]
def tum_siparisler(con, simdi: datetime) -> list[Siparis]
def durum_degistir(con, siparis_id: int, yeni: SiparisDurumu, simdi: datetime) -> Siparis   # izinsiz -> GecersizGecis
def zaman_asimi_uygula(con, siparis_id: int, simdi: datetime) -> None   # ODEME_BEKLIYOR ve olusturma+30dk < simdi -> IPTAL
```
### app/siparis/odeme_sim.py
```python
BASARILI_KART = "4111111111111111"
RET_KARTI = "4000000000000002"
SMS_KODU = "000000"
class OdemeSonucu(StrEnum): SMS_BEKLIYOR="sms_bekliyor"; BASARILI="basarili"; RET="ret"; SMS_HATALI="sms_hatali"; GECERSIZ_KART="gecersiz_kart"; ZATEN_ODENDI="zaten_odendi"; SIPARIS_GECERSIZ="siparis_gecersiz"
def kart_normalize(kart_no: str) -> str          # yalnız rakamlar
def odeme_baslat(con, siparis_id: int, islem_anahtari: str, kart_no: str, simdi: datetime) -> OdemeSonucu
    # aynı anahtar varsa kayıtlı durumu döner (idempotent); sipariş ODEME_BEKLIYOR değilse ZATEN_ODENDI/SIPARIS_GECERSIZ
    # kart test kartı değilse GECERSIZ_KART kaydı; değilse SMS_BEKLIYOR + kart_son4 + kart_sonucu
    # tam kart numarası hiçbir yere yazılmaz
def sms_dogrula(con, islem_anahtari: str, sms_kodu: str, simdi: datetime) -> OdemeSonucu
    # deneme sms_bekliyor değilse kayıtlı durumu döner; kod hatalı -> SMS_HATALI (deneme biter);
    # kart_sonucu 'ret' -> RET ; 'basarili' -> siparis ODENDI + kart_son4 yazılır + sepet bosalt -> BASARILI
```
### app/teklif/servis.py
```python
TEKLIF_GECISLERI = {"yeni": {"inceleniyor","kapandi"}, "inceleniyor": {"teklif_verildi","kapandi"}, "teklif_verildi": {"kapandi"}, "kapandi": set()}
@dataclass(frozen=True)
class TeklifGirdisi: ad: str; eposta: str; ulke: str; mesaj: str; firma: str | None = None; telefon: str | None = None; urun_id: int | None = None; adet: int = 1; musteri_id: int | None = None
@dataclass(frozen=True)
class Teklif: id: int; no: str; ad: str; firma: str | None; eposta: str; telefon: str | None; ulke: str; urun_id: int | None; urun_ad: str | None; adet: int; mesaj: str; durum: str; olusturma: datetime; musteri_id: int | None
class TeklifHatasi(ValueError):  # alan, kod
def teklif_olustur(con, g: TeklifGirdisi, simdi: datetime) -> Teklif      # no "CR-TKL-YYYYMMDD-NNNN"; ad/eposta/mesaj zorunlu; mesaj <= 2000
def teklifler(con, musteri_id: int | None = None) -> list[Teklif]
def teklif_durum_degistir(con, teklif_id: int, yeni: str) -> Teklif         # izinsiz -> GecersizGecis (siparis.servis'ten)
```
### app/geribildirim/servis.py
```python
DURUMLAR = ("yeni", "okundu", "yapildi")
def kaydet(con, sayfa: str, metin: str, isim: str | None, simdi: datetime) -> int   # metin 1..2000, sayfa <= 500 karakter, boşsa ValueError
def listele(con, durum: str | None = None) -> list[sqlite3.Row]
def durum_degistir(con, gb_id: int, durum: str) -> None
```
### app/web — ortak
```python
# uygulama.py
def uygulama_olustur(ayarlar: Ayarlar) -> FastAPI
    # SessionMiddleware(secret_key=ayarlar.gizli_anahtar, session_cookie="cr_oturum", same_site="lax", https_only=False, max_age=14 gün)
    # BaslikMiddleware ; statik /statik ; rotalar include ; hata işleyicileri (404/500 -> hata.html, hata kimliği)
    # app.state.ayarlar, app.state.ceviri, app.state.sablonlar, app.state.bantlar, app.state.hiz = HizSiniri()
# (K9: app/web/bagimlilik.py içinde) def db_bagimliligi(request) -> Iterator[sqlite3.Connection]    # her istekte baglan(), sonunda close()
# guvenlik.py
GUVENLIK_BASLIKLARI = {"Content-Security-Policy": "default-src 'self'; img-src 'self' https://www.ceylanrobot.com data:; style-src 'self'; script-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'",
  "X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin", "X-Robots-Tag": "noindex, nofollow"}
class BaslikMiddleware  # her yanıta GUVENLIK_BASLIKLARI
def guvenli_sonraki(deger: str | None, varsayilan: str = "/") -> str   # yalnız "/" ile başlayan, "//" ve "\\" ile başlamayan, şema içermeyen
class HizSiniri:
    def __init__(self, limit: int = 10, pencere: float = 60.0): ...
    def izin(self, anahtar: str, simdi: float) -> bool
def oturum_kimligi(request) -> str            # session["oid"] yoksa secrets.token_urlsafe(16) üretir
def csrf_jetonu(request) -> str               # session["csrf"] yoksa üretir
async def csrf_dogrula(request) -> None       # form alanı "csrf" == session["csrf"] değilse HTTPException(403)
def aktif_musteri(request, con) -> Musteri | None   # session["mid"]; musteri yoksa session'dan siler ve None
# dil.py
DILLER = ("tr", "en")
class Ceviri:
    def __init__(self, klasor: Path): ...
    def t(self, dil: str, anahtar: str, **degerler) -> str     # dil'de yoksa tr, o da yoksa anahtar
    def eksik_anahtarlar(self) -> dict[str, list[str]]          # en'de olup tr'de olmayan ve tersi
# baglam.py
def fiyat_baglami(request, musteri: Musteri | None) -> Baglam
    # musteri varsa Baglam(musteri.tip, musteri.ulke); yoksa session["ulke"] (varsayılan "TR"): "TR" -> BIREYSEL, diğer -> YURTDISI
def sablon(request, ad: str, baglam: dict, durum: int = 200) -> HTMLResponse
    # ortak değişkenler: dil, t (lambda anahtar, **k), csrf, musteri, sepet_adet, ulke, para (FiyatGosterim biçimleyici), istek_yolu, yasal bağlantılar
def para_bicimle(tutar: Decimal, para: str, dil: str) -> str   # tr: "1.234,50 ₺" / "1.234,50 €" ; en: "€1,234.50" / "₺1,234.50"
```
### URL'ler (rotalar)
```
GET  /                                   -> 302 /{çerezdeki dil|tr}/
GET  /saglik                             -> {"durum":"ok","son_esitleme": iso|null, "urun": n}
POST /tercih                             form: dil, ulke, sonraki(csrf) -> 303 guvenli_sonraki (dil değişirse yolun ilk segmenti değişir)
GET  /{dil}/                             ana sayfa
GET  /{dil}/kategori/{id}                ?stokta=1&fmin=&fmax=&sira=&sayfa=
GET  /{dil}/ara                          ?q=&sayfa=
GET  /{dil}/urun/{id}
GET  /{dil}/sepet ; POST /{dil}/sepet/ekle (urun_id, adet) ; POST /{dil}/sepet/adet (urun_id, adet) ; POST /{dil}/sepet/kaldir (urun_id)
GET/POST /{dil}/kayit ; GET/POST /{dil}/giris (?sonraki=) ; POST /{dil}/cikis ; GET /{dil}/hesabim
GET/POST /{dil}/odeme                    adres+fatura+teslim -> siparis_olustur -> 303 /{dil}/odeme/{no}/kart
GET/POST /{dil}/odeme/{no}/kart          -> odeme_baslat -> 303 /{dil}/odeme/{no}/3d?a=<islem_anahtari>
GET/POST /{dil}/odeme/{no}/3d            -> sms_dogrula -> 303 /{dil}/siparis/{no}
GET  /{dil}/siparis/{no}                 yalnız sahibi
GET/POST /{dil}/teklif                   ?urun_id= ; başarı -> /{dil}/teklif/tamam?no=
GET  /{dil}/yasal/{sayfa}                sayfa ∈ on-bilgilendirme, mesafeli-satis, iade, garanti, kvkk, acik-riza, cerez, gizlilik, kullanim, kunye
POST /geri-bildirim                      form: sayfa, metin, isim, csrf -> JSON {"tamam": true} | 400
GET/POST /yonetim/giris ; POST /yonetim/cikis ; GET /yonetim ; GET /yonetim/siparisler ; POST /yonetim/siparis/{id}/durum ;
GET /yonetim/teklifler ; POST /yonetim/teklif/{id}/durum ; GET /yonetim/geri-bildirimler ; POST /yonetim/geri-bildirim/{id}/durum
```
Yönetim oturumu `session["yonetici"] = True`; yönetici girişi `HizSiniri` ile sınırlı ve `parola_dogru(parola, ayarlar.yonetici_parola_ozeti)`.

### Şablon sözleşmesi
- `taban.html`: üstte `.demo-bandi` (her sayfa), başlık (logo metni "CEYLAN ROBOT", arama, dil ve ülke seçici formu `/tercih`, hesap, sepet sayacı), `{% block icerik %}`, alt bilgi (yasal bağlantılar), sağ altta `#gb-dugme` + `<dialog id="gb-pencere">` formu, çerez bandı (`#cerez-bandi`, kabul çerezle saklanır).
- Satır içi `<script>` ve `style=""` YOK (CSP). Tüm JS `statik/site.js`, tüm CSS `statik/site.css`.
- Tema tokenları (`site.css` `:root`): `--yesil-koyu:#303a32; --yesil:#687860; --kiremit:#a83c29; --mavi:#267593; --zemin:#f4f1e9; --gri:#697265; --cizgi:#c5c8bc; --yazi:#1f2420;` başlık fontu Georgia, gövde "Segoe UI", Arial.
- Fiyat bloğu makrosu `_makrolar.html`: `fiyat(urun, gosterim)` → temsili ise `.rozet-temsili` ("Temsili fiyat" / "Indicative price"), kur tarihi satırı, bayatsa `.kur-bayat`.

### Ortak test fixture'ları (`tests/conftest.py`, Görev 1 yazar)
```python
@pytest.fixture
def con(tmp_path) -> sqlite3.Connection        # baglan + gecisleri_uygula
@pytest.fixture
def simdi() -> datetime                         # datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
@pytest.fixture
def bantlar() -> Bantlar                        # bantlari_oku(app/fiyat/bantlar.yaml)
def urun_ekle(con, *, sku="S1", ad="Test Ürün", kok="ELEKTRİK", fiyat="100.00", teklif=False, stok=1, aktif=True, kategori_id=None, kdv="20", simdi=None, uretici_kodu=None, gorsel_url=None, tedarik_suresi_gun=None) -> int   # FTS satırı da yazar (K6); yardımcı (fixture değil, import edilir)
def kategori_ekle(con, *, kaynak_id, ad, yol, seviye, ust_kaynak_id=None) -> int
```
Web testleri için (`tests/conftest.py`, Görev 11 ekler): `istemci` fixture'ı → `TestClient(uygulama_olustur(Ayarlar(db_yolu=tmp, gizli_anahtar="t"*32, yonetici_kullanici="yonetici", yonetici_parola_ozeti=parola_ozeti("yonetici-parola-123"))))` ve `csrf_al(istemci, yol) -> str` yardımcı (sayfadaki `name="csrf" value="..."` değerini ayrıştırır).

## Entegrasyon kararları (sözleşmeyi günceller; çelişkide bu bölüm kazanır)

Bölüm yazarlarının "Sözleşme notları"ndan çıkan kararlar. Her görev bu kararlara göre yazılmıştır.

**K1 — Eşitleme turunun sınıflandırılması**
- Tur **tam** sayılır: `benzersiz_sku + bozuk_kayit == api_toplam`. Bu toplam ilk ve son sayfanın `total` değeriyle karşılaştırılır.
- `esitleme_gunlugu` tablosuna `bozuk INTEGER NOT NULL DEFAULT 0` kolonu eklenir (001 dosyasında; henüz hiç uygulanmadı). `TurSonucu` dataclass'ına `bozuk: int` alanı eklenir.
- Kategoriler ya da 1. sayfa alınamazsa tur **hata** olur ve veri değişmez.
- Sonraki bir sayfa alınamazsa o sayfa atlanır, tur **eksik** olur. Günlüğün `hata` alanına `alinamayan_sayfa: N` yazılır.
- Kategori upsert'i ürün upsert'iyle aynı son transaction'dadır. Tam turda kaynakta olmayan kategoriler `aktif=0` yapılır.

**K2 — Yeniden deneme**
- Spesifikasyondaki "en fazla 3 deneme" kuralı: ilk istek + 2 yeniden deneme. Beklemeler `YENIDEN_DENEME_BEKLEMELERI = (2.0, 4.0)`.

**K3 — `birim_fiyat_gosterimi` kuralı (spec §5.3 tablosu esastır)**
- `KURUMSAL`: ana fiyat EUR net, ikincil fiyat TRY net. Kur yoksa ikincil gösterilmez. Teslimat TR dışındaysa da aynı kural geçerli.
- Diğer tipler için:
  - ana para = `tahsilat_para_birimi(b)`, `kdv_dahil = gosterim_kdv_dahil(b)`;
  - ana TRY ise ikincil EUR net, ana EUR ise ikincil yok;
  - bireysel müşteride teslimat TR dışındaysa ana fiyat TRY net olur (KDV yok).
- Kur yoksa ve TRY gerekiyorsa ana fiyat EUR net olur ve `kdv_dahil=False`. Şablon bu durumda "KDV hariç" ibaresini açıkça yazar.

**K4 — Kargo:** Teslimat TR değilken `KARGO` yöntemi seçilirse ücret 0 olur. Ödeme formu teslimat TR değilse yalnız `YURTDISI_DAP` ve `FABRIKA` seçeneklerini sunar.

**K5 — Kur hatası:** `app/fiyat/kurallar.py` içinde `class KurYok(ValueError)` tanımlanır. `sepet_hesapla`, TRY tahsilatta kur yoksa `KurYok("kur_yok")` yükseltir; bu sınıf `ValueError`'dan türediği için mevcut testler bozulmaz. Web katmanı `KurYok`'u yakalar.

**K6 — Arama indeksi:** Yeni modül `app/katalog/indeks.py` (Görev 1 yazar) iki fonksiyon içerir:
```python
def indeks_metni(ad: str, sku: str, uretici_kodu: str | None) -> str   # normalize(f"{ad} {sku} {uretici_kodu or ''}")
def indeksi_yeniden_kur(con) -> None   # DELETE FROM urun_ara; INSERT INTO urun_ara(metin, urun_id) SELECT ... FROM urun WHERE aktif=1 — urun_id INTEGER olarak
```
- `esitle` arama indeksini bununla yeniden kurar.
- `tests/conftest.urun_ekle` yeni ürün için tek satır ekler: `INSERT INTO urun_ara(metin, urun_id) VALUES (indeks_metni(...), id)`, `urun_id` int olarak.
- `urun_ekle` imzasına `uretici_kodu=None, gorsel_url=None, tedarik_suresi_gun=None` parametreleri eklenir.
- Görev 6'daki yerel `indeksle` yardımcısı kaldırılır; testler `urun_ekle` ve `indeksi_yeniden_kur`'u kullanır.

**K7 — Testler:**
- `tests/__init__.py` vardır. Yardımcılar her yerde `from tests.conftest import urun_ekle, kategori_ekle, csrf_al` ile alınır; `from conftest import` kullanılmaz.
- Testler depo kökünden `python -m pytest` ile çalıştırılır.

**K8 — Bağlantı:** `baglan`, `sqlite3.connect(..., check_same_thread=False)` ile açılır (Görev 1).

**K9 — Web iskeleti (Görev 11 sahibi):**
- `db_bagimliligi` yeni `app/web/bagimlilik.py` modülündedir. Bütün rota modülleri onu oradan alır; döngüsel import oluşmaz ve geç import gerekmez. `uygulama.py` bunu yeniden dışa aktarabilir.
- Dil segmenti olan rotalar `/{dil:dil}/...` dönüştürücüsüyle yazılır. Her rota modülü `router` dışa aktarır.
- `uygulama.py` içindeki `ROTA_SIRASI = ("genel", "yonetim", "yasal", "katalog", "hesap", "sepet_odeme", "teklif_gb")` sırası modülleri yükler; `yonetim` dil rotalarından önce gelir.
- `sablon()` ortak bağlamında:
  - `para(tutar, para_birimi)`; ekran görevleri kendi `pb` lambdalarını tanımlamaz;
  - `t(anahtar, **k)`: değerleri `str.format` ile doldurur;
  - dil öneksiz yollarda (yönetim, `/geri-bildirim`) dil `"tr"` olur.
- `taban.html` içinde `{% block baslik %}` bloğu vardır. Yönetim şablonları `taban.html`'i genişletir; DEMO bandı orada da görünür.

**K10 — Uvicorn:**
- Fabrika `app/web/asgi.py` içindeki `def uygulama() -> FastAPI: return uygulama_olustur(ayarlari_oku())` fonksiyonudur (Görev 17). Servis `uvicorn --factory app.web.asgi:uygulama` ile başlar.
- Görev 11'deki `uretim_uygulamasi` gibi diğer adlar kaldırılır. Spesifikasyon §8 güncellenmiştir.

**K11 — CSRF:** Hatalı CSRF jetonunda 403 ve hata sayfası döner ("Oturum süresi doldu, sayfayı yenileyip tekrar deneyin"). Spesifikasyon §9 buna göre güncellenmiştir.

**K12 — Form alan adları ve akışlar** (Görev 13/14/15 ile Görev 18 e2e arasında bağlayıcı):
- Müşteri girişi: `eposta`, `parola`, `csrf`; başarıda 303.
- Ödeme onay kutuları: bireyselde `on_bilgi_onay` + `mesafeli_onay`, kurumsal/yurt dışında `kosullar_onay`.
- Yönetim girişi: `kullanici`, `parola`, `csrf`.
- Kayıt formu `?tip=bireysel|kurumsal|yurtdisi` parametresini kabul eder.
- Kayıt sonrası otomatik giriş yapılır, `sonraki=` adresine yönlendirilir ve misafir sepeti **kayıtta da** birleştirilir.
- 3D adımında ödeme reddedilirse kullanıcı sipariş sayfasına döner; sayfada `[data-e2e="odeme-hata"][data-kod="ret"]` ve ödemeyi tekrar deneme bağlantısı gösterilir.
- **`data-e2e` seçici tablosu Görev 18'dedir** (dosyada "Liste ve arama sonuçlarında ürün bağlantısı" satırıyla başlar). Görev 11–16 şablonları bu tablodaki tüm öznitelikleri eksiksiz taşır.

**K13 — Ödeme denemesi okuma:** `app/siparis/odeme_sim.py` içine `def deneme_getir(con, islem_anahtari: str) -> sqlite3.Row | None` eklenir (Görev 9). 3D rotası doğrudan SQL yerine bunu kullanır.

**K14 — i18n anahtar sahipliği:** `siparis_durum.*` ve `teklif_durum.*` anahtarları Görev 11'de tanımlanır. Görev 14/15 bunları kullanır ve `siparis.durum.*`, `teklif.durum.*` gibi yeni kopyalar tanımlamaz. Hata kodu metinleri `hata_kodu.<kod>` altında toplanır; her görev yalnız kendi eklediği kodları yazar.

**K15 — Sipariş ve teklif numaralarındaki tarih:** `zoneinfo.ZoneInfo("Europe/Istanbul")` saatine çevrilmiş `simdi` değerinden alınır (Görev 9 ve 10).

**K16 — Test kimlik numaraları:** Geçerli VKN olarak `1234567890` (uç durum) ve `4728136592` kullanılır, geçersiz VKN olarak `4728136593`; TCKN için `10000000146`. E2E testlerinde kurumsal kayıtta `1234567890` kullanılır.

**K17 — Hesap kuralları (Görev 7 uygulaması esastır):**
- İYS onayı yalnız bireysel müşteride saklanır; kurumsal ve yurt dışı müşteride `False` yapılır.
- Bireysel ve kurumsal müşteride ülke `"TR"` yapılır. E-posta küçük harfle saklanır.
- Görev 7'de tanımlanan hata kodları bağlayıcıdır.
- `durum_degistir` fonksiyonları kayıt bulamazsa `LookupError` yükseltir; web katmanı bunu 404'e çevirir.

**K18 — `/saglik` yanıtı:** `{"durum": "ok", "son_esitleme": iso|null, "urun": <aktif ürün sayısı>}`.

**K19 — Betikler:**
- Betikler modül olarak çalışır (`python -m betikler.esitle` vb.) ve `betikler/__init__.py` dosyası vardır.
- Laptopta `core.autocrlf=true` olduğu için `.gitattributes` dosyası `* text=auto eol=lf` içerir.
- Ek dosyalar: `app/gecis_calistir.py`, `dagitim/uzak-yayinla.sh`.

**K20 — `odeme_sim`:** Bilinmeyen ya da başka siparişe ait işlem anahtarında sonuç `SIPARIS_GECERSIZ` olur. Boş anahtar `ValueError` yükseltir. `gecersiz_kart` kaydında `kart_son4` NULL tutulur.

**K21 — Ödeme formunda düşen ürünler:** Web katmanı (Görev 14), `siparis_olustur`'dan **önce** `sepet.kalemler()`'i çağırır ve sepetten düşen ürünlerin adlarını kullanıcıya gösterir.

## Ek veri: gerçek kök kategoriler (12.10.2026, public API, 497 kategori)

Kök (level 0): `ABB REDÜKTÖR` (397), `Elektrik ve Elektronik` (10), `Endüstriyel Robotlar` (12), `GÜÇ KAYNA�\udc9eI` (511, bozuk kodlama), `Mekanik` (11), `Pozisyonerler` (16), `Robot Kontrol Üniteleri` (13), `Robotik Parçaları` (14), `Slider` (15).
Örnek alt: `12.41 KUKA`, `12.42 ABB`, `12.380 FANUC`, `13.54 ROBOT KONTROL ÜNİTELERİ`, `14.56 ROBOT SÜRÜCÜLERİ`, `10.18 KONTROL SISTEMLERI`.
Ürün örneği: SKU `8301033800019` "KUKA KRC5 KR 140 R3200-2 PA", kategori `KR C4` yol `12.41.243` → kök "Endüstriyel Robotlar" → teklif zorunlu.

`app/fiyat/bantlar.yaml` (birebir):
```yaml
# Temsili fiyat bantları — net EUR, KDV hariç. Anahtarlar normalize() edilmiş kök kategori adı.
robot_kokleri:
  - endustriyel robotlar
  - pozisyonerler
varsayilan: [50, 2000]
bantlar:
  endustriyel robotlar: [8000, 45000]
  pozisyonerler: [5000, 30000]
  robot kontrol uniteleri: [1500, 12000]
  robotik parcalari: [80, 4000]
  slider: [3000, 20000]
  elektrik ve elektronik: [20, 1500]
  mekanik: [15, 900]
  abb reduktor: [400, 6000]
```

---

## Görevler — A bölümü (Görev 0–5: ortam, iskelet, doğrulama, kur, fiyat kuralları, eşitleme)

> **Test komutu kuralı (bütün görevler):** Laptopta Python bağımlılığı kurulmaz. Her test komutu depo kökünden, Git Bash'te **`bash dagitim/test-vm.sh <test_yolu> -q`** biçimindedir. Betik (Görev 0) çalışma ağacını `cr-web-demo` VM'ine kopyalar, `requirements.txt` değiştiyse `pip install` yapar ve VM'deki geliştirme venv'inde `python -m pytest` çalıştırır; çıkış kodu pytest'inkidir. Aşağıda "Run:" satırlarındaki komutların hepsi bu biçimdedir.

> **Commit kuralı:** Her görev sonunda iki `-m` ile commit (ikinci paragraf ortak yazar satırı); kimlik `git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com`.

---

### Görev 0: VM geliştirme ortamı ve `dagitim/test-vm.sh`

**Files:**
- Create: `requirements.txt` (betik bağımlılık kurulumunda kullandığı için Görev 1 yerine burada)
- Create: `tests/__init__.py` (boş)
- Create: `tests/test_ortam.py`
- Create: `dagitim/test-vm.sh`
- VM'de (sudo'suz, depo dışı): `~/gelistirme/.venv`, `~/gelistirme/kod/`, `~/gelistirme/.requirements.sha256`

**Interfaces:**
- Consumes: laptopta `~/.ssh/config` içindeki `cr-web-demo` takma adı (HostName 192.168.5.30, User crwebdemo, IdentityFile ~/.ssh/cr_web_demo); Git Bash'te `git`, `tar` (GNU), `ssh`.
- Produces: `bash dagitim/test-vm.sh [pytest argümanları]` → VM'de `~/gelistirme/kod` içinde `~/gelistirme/.venv/bin/python -m pytest -p no:cacheprovider <argümanlar>`; çıkış kodu pytest'inki (0 geçti, 1 test başarısız, 2 kesildi/toplama hatası, 4 kullanım hatası, 5 test yok). Ortam değişkeni `CR_TEST_HOST` ile hedef değiştirilebilir.

Bu görevde sudo YOK. VM'de `pip`, `venv` (ensurepip) kurulu değil; geliştirme venv'i `--without-pip` ile kurulur ve pip `get-pip.py` ile venv'in içine yüklenir. Bu venv yalnız geliştirme testleri içindir; dağıtımda her release kendi venv'ini `deploy.sh` ile kurar.

- [ ] **Step 1: VM ön koşullarını doğrula**

Run:
```bash
ssh cr-web-demo 'python3 --version; command -v curl; python3 -c "import venv; print(\"venv modulu var\")"; python3 -c "import ensurepip" 2>&1 | tail -1'
```
Expected:
```
Python 3.12.3
/usr/bin/curl
venv modulu var
ModuleNotFoundError: No module named 'ensurepip'
```
(`curl` yoksa dur ve kullanıcıya bildir; sudo'lu kurulum bu görevin kapsamında değil.)

- [ ] **Step 2: pip'siz venv oluştur ve çalıştığını doğrula**

Run:
```bash
ssh cr-web-demo 'set -e; mkdir -p ~/gelistirme; python3 -m venv --without-pip ~/gelistirme/.venv; ~/gelistirme/.venv/bin/python -c "import sys; print(sys.prefix, sys.prefix != sys.base_prefix)"'
```
Expected: `/home/crwebdemo/gelistirme/.venv True`

- [ ] **Step 3: venv'e pip kur**

Run:
```bash
ssh cr-web-demo 'set -e; curl -sS https://bootstrap.pypa.io/get-pip.py | ~/gelistirme/.venv/bin/python - -q; ~/gelistirme/.venv/bin/python -m pip --version'
```
Expected: `pip 2x.y from /home/crwebdemo/gelistirme/.venv/lib/python3.12/site-packages/pip (python 3.12)`

**Yedek yol (yalnız Step 2 veya Step 3 hata verirse):** kullanıcı düzeyinde pip + virtualenv (Ubuntu 24.04 PEP 668 nedeniyle `--break-system-packages` gerekir; yalnız `~/.local` etkilenir, sistem paketlerine dokunulmaz):
```bash
ssh cr-web-demo 'set -e; curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py; python3 /tmp/get-pip.py --user --break-system-packages -q; python3 -m pip install --user --break-system-packages -q virtualenv; rm -rf ~/gelistirme/.venv; python3 -m virtualenv -q ~/gelistirme/.venv; rm -f /tmp/get-pip.py; ~/gelistirme/.venv/bin/python -m pip --version'
```
Expected: yine `pip ... from /home/crwebdemo/gelistirme/.venv/...`. Hangi yolun kullanıldığını görev raporuna yaz.

- [ ] **Step 4: Bağımlılık dosyasını yaz**

`requirements.txt` (sözleşmedeki sürümler birebir; `pytest` release venv'inde de çalıştığı için burada):
```text
fastapi==0.115.*
uvicorn==0.32.*
jinja2==3.1.*
httpx==0.27.*
python-multipart==0.0.*
itsdangerous==2.2.*
pyyaml==6.0.*
pytest==8.*
```

`tests/__init__.py`: boş dosya (testler `from tests.conftest import ...` ile yardımcıları içe aktarır).

- [ ] **Step 5: Ortam duman testini yaz**

`tests/test_ortam.py`:
```python
"""Geliştirme ortamı duman testi: VM venv'inde Python 3.12 + pytest 8."""
import sys

import pytest


def test_python_surumu():
    assert sys.version_info[:2] == (3, 12)


def test_venv_icinde_calisiyor():
    assert sys.prefix != sys.base_prefix
    assert pytest.__version__.startswith("8.")
```

- [ ] **Step 6: Betik yokken çalıştır, başarısız olduğunu gör**

Run: `bash dagitim/test-vm.sh tests/test_ortam.py -q`
Expected: FAIL — `bash: dagitim/test-vm.sh: No such file or directory`

- [ ] **Step 7: `dagitim/test-vm.sh` yaz**

```bash
#!/usr/bin/env bash
# Çalışma ağacını cr-web-demo VM'ine kopyalayıp orada pytest çalıştırır.
# Kullanım (depo kökünden ya da herhangi bir alt klasörden):
#   bash dagitim/test-vm.sh tests/test_para.py -q
#   bash dagitim/test-vm.sh -q            # bütün testler
# Ortam: CR_TEST_HOST (varsayılan: cr-web-demo ssh takma adı)
# Çıkış kodu: VM'deki pytest'in çıkış kodu.
set -euo pipefail
export MSYS_NO_PATHCONV=1

HOST="${CR_TEST_HOST:-cr-web-demo}"
KOK="$(git rev-parse --show-toplevel)"
cd "$KOK"
# Her çalışma ağacı (worktree) VM'de kendi klasörünü kullanır; paralel ajanlar birbirinin testini silmez.
KLASOR="kod-$(printf '%s' "$KOK" | sha256sum | cut -c1-8)"

# 1) İzlenen + izlenmeyen (ignore edilmeyen) ve diskte var olan dosyaları tar'la, VM'de temiz klasöre aç
git ls-files -z -co --exclude-standard \
  | while IFS= read -r -d '' f; do [ -f "$f" ] && printf '%s\0' "$f"; done \
  | tar --null -T - -czf - \
  | ssh "$HOST" "set -e; rm -rf ~/gelistirme/$KLASOR; mkdir -p ~/gelistirme/$KLASOR; tar -xzf - -C ~/gelistirme/$KLASOR"

# 2) requirements.txt değiştiyse bağımlılıkları kur; 3) pytest
ARGS=""
for a in "$@"; do ARGS+=" $(printf '%q' "$a")"; done

set +e
ssh "$HOST" "bash -s -- $KLASOR $ARGS" <<'UZAK'
set -euo pipefail
KLASOR="$1"; shift
cd ~/gelistirme/"$KLASOR"
VENV=~/gelistirme/.venv
OZET_DOSYASI=~/gelistirme/.requirements.sha256
if [ -f requirements.txt ]; then
  YENI="$(sha256sum requirements.txt | cut -d' ' -f1)"
  ESKI="$(cat "$OZET_DOSYASI" 2>/dev/null || true)"
  if [ "$YENI" != "$ESKI" ]; then
    echo ">> requirements.txt değişti, pip install çalışıyor" >&2
    # ortak venv'e aynı anda iki pip kurulumu olmasın
    flock ~/gelistirme/.pip.kilit "$VENV/bin/python" -m pip install -q -r requirements.txt
    echo "$YENI" > "$OZET_DOSYASI"
  fi
fi
exec "$VENV/bin/python" -m pytest -p no:cacheprovider "$@"
UZAK
KOD=$?
set -e
exit "$KOD"
```

- [ ] **Step 8: Çalıştır, geçtiğini gör**

Run: `bash dagitim/test-vm.sh tests/test_ortam.py -q`
Expected: ilk çalıştırmada `>> requirements.txt değişti, pip install çalışıyor` satırı, ardından `2 passed`; çıkış kodu 0 (`echo $?` → `0`). İkinci çalıştırmada pip satırı görünmez.

- [ ] **Step 9: Kontrol — başarısızlık çıkış kodu laptopa dönüyor mu**

Run: `bash dagitim/test-vm.sh tests/yok_boyle_dosya.py -q; echo "kod=$?"`
Expected: `ERROR: file or directory not found: tests/yok_boyle_dosya.py` ve `kod=4`. (Kod 0 görünürse betik pytest'in çıkış kodunu yutuyor demektir; düzeltmeden ilerleme.)

- [ ] **Step 10: Commit**

```bash
git add requirements.txt tests/__init__.py tests/test_ortam.py dagitim/test-vm.sh
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m "build: VM gelistirme venv'i ve test-vm.sh test kosucusu" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Görev 1: Depo iskeleti — ayarlar, veritabanı ve geçişler, para, metin, ortak fixture'lar

**Files:**
- Create: `.gitignore`
- Create: `.gitattributes` (K19)
- Create: `app/__init__.py`, `app/fiyat/__init__.py`, `app/hesap/__init__.py`, `app/esitleme/__init__.py` (hepsi boş)
- Create: `app/ayarlar.py`
- Create: `app/db.py`
- Create: `app/gecisler/001_baslangic.sql`
- Create: `app/para.py`
- Create: `app/metin.py`
- Create: `app/katalog/__init__.py` (boş), `app/katalog/indeks.py` (K6)
- Create: `app/fiyat/bantlar.yaml` (fixture `bantlar` bu dosyayı okur; içerik Görev 4'le aynı, burada oluşturulur)
- Create: `tests/conftest.py`
- Test: `tests/test_iskelet.py`
- (`requirements.txt` ve `tests/__init__.py` Görev 0'da oluşturuldu.)

**Interfaces:**
- Consumes: Görev 0 — `bash dagitim/test-vm.sh`, `requirements.txt`.
- Produces:
  - `app.ayarlar.Ayarlar` (frozen dataclass: `db_yolu: Path, gizli_anahtar: str, yonetici_kullanici: str, yonetici_parola_ozeti: str, kaynak_api: str = "https://www.ceylanrobot.com", gorsel_kok: str = "https://www.ceylanrobot.com", bantlar_yolu: Path = app/fiyat/bantlar.yaml`), `ayarlari_oku(ortam: Mapping[str, str] = os.environ) -> Ayarlar` — eksik zorunlu anahtar → `RuntimeError("<ANAHTAR>")`.
  - `app.db.baglan(yol: Path) -> sqlite3.Connection` (`check_same_thread=False` (K8), Row, foreign_keys=ON, WAL, busy_timeout=5000), `app.db.gecisleri_uygula(con) -> list[str]` (yeni uygulanan dosya adları; ikinci çağrıda `[]`).
  - `app.para.IKI_HANE`, `d(deger: str | int | Decimal) -> Decimal` (float/bool → `TypeError`), `yuvarla(x: Decimal) -> Decimal`.
  - `app.metin.normalize(s: str) -> str`, `metin_temizle(s: str | None) -> str | None`.
  - `app.katalog.indeks.indeks_metni(ad: str, sku: str, uretici_kodu: str | None) -> str` (`normalize(f"{ad} {sku} {uretici_kodu or ''}")`), `indeksi_yeniden_kur(con) -> None` (`urun_ara`'yı `aktif=1` ürünlerden baştan kurar, `urun_id` int; commit etmez).
  - Şema: `esitleme_gunlugu.bozuk INTEGER NOT NULL DEFAULT 0` (K1).
  - `tests/conftest.py`: fixture'lar `con`, `simdi` (= `datetime(2026, 10, 13, 9, 0, tzinfo=UTC)`), `bantlar`; yardımcılar `urun_ekle(con, *, sku="S1", ad="Test Ürün", kok="ELEKTRİK", fiyat="100.00", teklif=False, stok=1, aktif=True, kategori_id=None, kdv="20", simdi=None, uretici_kodu=None, gorsel_url=None, tedarik_suresi_gun=None) -> int`, `kategori_ekle(...) -> int`, sabitler `KOK`, `SABIT_ZAMAN`. `urun_ekle` commit eder ve ürün aktifse `urun_ara`'ya tek satır `(indeks_metni(ad, sku, uretici_kodu), urun_id: int)` yazar (K6). Yardımcılar `from tests.conftest import ...` ile alınır (K7).

- [ ] **Step 1: Statik dosyaları oluştur**

`.gitignore`:
```gitignore
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/
*.db
*.db-wal
*.db-shm
/ortam
e2e/ciktilar/
```

`.gitattributes` (laptopta `core.autocrlf=true`; VM'e giden dosyalar LF olmalı — K19):
```gitattributes
* text=auto eol=lf
*.png binary
*.webp binary
```

`app/__init__.py`, `app/fiyat/__init__.py`, `app/hesap/__init__.py`, `app/esitleme/__init__.py`, `app/katalog/__init__.py`: boş dosyalar.

`app/gecisler/001_baslangic.sql` (sözleşmedeki şema birebir; `esitleme_gunlugu.bozuk` kolonu K1 ile eklendi):
```sql
CREATE TABLE sema_surumu (dosya TEXT PRIMARY KEY, uygulandi TEXT NOT NULL);

CREATE TABLE kategori (
  id INTEGER PRIMARY KEY,
  kaynak_id TEXT NOT NULL UNIQUE,      -- API _id
  erp_id INTEGER,
  ad TEXT NOT NULL,
  ust_kaynak_id TEXT,                  -- API parentId
  yol TEXT NOT NULL,                   -- "12.41.243"
  seviye INTEGER NOT NULL,
  aktif INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX ix_kategori_yol ON kategori(yol);

CREATE TABLE urun (
  id INTEGER PRIMARY KEY,
  sku TEXT NOT NULL UNIQUE,
  ad TEXT NOT NULL,
  uretici_kodu TEXT,
  kategori_id INTEGER REFERENCES kategori(id),
  kok_kategori_ad TEXT NOT NULL DEFAULT '',
  kdv_orani TEXT NOT NULL DEFAULT '20',          -- Decimal metin
  stok INTEGER NOT NULL DEFAULT 0,
  tedarik_suresi_gun INTEGER,
  gorsel_url TEXT,
  kaynak_fiyat_eur TEXT NOT NULL DEFAULT '0',
  temsili_fiyat_eur TEXT NOT NULL,                -- gösterilen net EUR (kaynak>0 ise kaynak)
  fiyat_temsili INTEGER NOT NULL DEFAULT 1,       -- 1: temsili rozet göster
  teklif_zorunlu INTEGER NOT NULL DEFAULT 0,
  durum_kodu TEXT NOT NULL DEFAULT 'belirtilmemis',
  durum_ornek INTEGER NOT NULL DEFAULT 0,
  aktif INTEGER NOT NULL DEFAULT 1,
  kaynak_guncelleme TEXT,
  olusturma TEXT NOT NULL
);
CREATE INDEX ix_urun_kategori ON urun(kategori_id);
CREATE VIRTUAL TABLE urun_ara USING fts5(metin, urun_id UNINDEXED, tokenize='unicode61 remove_diacritics 2');

CREATE TABLE esitleme_ara (sku TEXT PRIMARY KEY, veri TEXT NOT NULL);
CREATE TABLE esitleme_gunlugu (
  id INTEGER PRIMARY KEY, basla TEXT NOT NULL, bitis TEXT,
  durum TEXT NOT NULL CHECK (durum IN ('calisiyor','tam','eksik','hata')),
  api_toplam INTEGER, cekilen INTEGER NOT NULL DEFAULT 0, eklenen INTEGER NOT NULL DEFAULT 0,
  guncellenen INTEGER NOT NULL DEFAULT 0, pasiflenen INTEGER NOT NULL DEFAULT 0, bozuk INTEGER NOT NULL DEFAULT 0, hata TEXT
);

CREATE TABLE kur (tarih TEXT PRIMARY KEY, eur_alis TEXT NOT NULL, eur_satis TEXT NOT NULL, alindi TEXT NOT NULL);

CREATE TABLE musteri (
  id INTEGER PRIMARY KEY,
  tip TEXT NOT NULL CHECK (tip IN ('bireysel','kurumsal','yurtdisi')),
  ad TEXT NOT NULL, eposta TEXT NOT NULL UNIQUE COLLATE NOCASE, parola_ozeti TEXT NOT NULL,
  vergi_kimlik_no TEXT, vergi_dairesi TEXT, vat_id TEXT, ulke TEXT NOT NULL,
  kvkk_onay TEXT NOT NULL, iys_onay INTEGER NOT NULL DEFAULT 0, olusturma TEXT NOT NULL
);
CREATE TABLE adres (
  id INTEGER PRIMARY KEY, musteri_id INTEGER NOT NULL REFERENCES musteri(id),
  tur TEXT NOT NULL CHECK (tur IN ('teslimat','fatura')),
  ad_soyad TEXT NOT NULL, satir1 TEXT NOT NULL, satir2 TEXT, sehir TEXT NOT NULL,
  posta_kodu TEXT, ulke TEXT NOT NULL, telefon TEXT
);

CREATE TABLE sepet (id INTEGER PRIMARY KEY, oturum_id TEXT, musteri_id INTEGER REFERENCES musteri(id), olusturma TEXT NOT NULL);
CREATE UNIQUE INDEX ux_sepet_oturum ON sepet(oturum_id) WHERE oturum_id IS NOT NULL;
CREATE UNIQUE INDEX ux_sepet_musteri ON sepet(musteri_id) WHERE musteri_id IS NOT NULL;
CREATE TABLE sepet_kalemi (sepet_id INTEGER NOT NULL REFERENCES sepet(id), urun_id INTEGER NOT NULL REFERENCES urun(id), adet INTEGER NOT NULL CHECK (adet BETWEEN 1 AND 99), PRIMARY KEY (sepet_id, urun_id));

CREATE TABLE siparis (
  id INTEGER PRIMARY KEY, no TEXT NOT NULL UNIQUE, musteri_id INTEGER NOT NULL REFERENCES musteri(id),
  durum TEXT NOT NULL CHECK (durum IN ('odeme_bekliyor','odendi','hazirlaniyor','kargoda','teslim','iptal')),
  para_birimi TEXT NOT NULL CHECK (para_birimi IN ('TRY','EUR')),
  ara_toplam TEXT NOT NULL, kdv TEXT NOT NULL, kargo TEXT NOT NULL, toplam TEXT NOT NULL,
  kur TEXT, kur_tarihi TEXT, ihracat_istisnasi INTEGER NOT NULL,
  teslim_yontemi TEXT NOT NULL CHECK (teslim_yontemi IN ('kargo','fabrika','yurtdisi_dap')),
  teslimat_ulkesi TEXT NOT NULL, teslimat_adresi TEXT NOT NULL, fatura_adresi TEXT NOT NULL,
  kart_son4 TEXT, sepet_id INTEGER NOT NULL, olusturma TEXT NOT NULL, guncelleme TEXT NOT NULL
);
CREATE TABLE siparis_kalemi (
  siparis_id INTEGER NOT NULL REFERENCES siparis(id), urun_id INTEGER NOT NULL, sku TEXT NOT NULL, ad TEXT NOT NULL,
  adet INTEGER NOT NULL, birim_net_eur TEXT NOT NULL, net TEXT NOT NULL, kdv TEXT NOT NULL, brut TEXT NOT NULL,
  tedarik_teyit INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE odeme_denemesi (
  islem_anahtari TEXT PRIMARY KEY, siparis_id INTEGER NOT NULL REFERENCES siparis(id),
  kart_son4 TEXT, kart_sonucu TEXT CHECK (kart_sonucu IN ('basarili','ret')),
  durum TEXT NOT NULL CHECK (durum IN ('sms_bekliyor','basarili','ret','sms_hatali','gecersiz_kart')),
  olusturma TEXT NOT NULL
);

CREATE TABLE teklif (
  id INTEGER PRIMARY KEY, no TEXT NOT NULL UNIQUE, musteri_id INTEGER REFERENCES musteri(id),
  ad TEXT NOT NULL, firma TEXT, eposta TEXT NOT NULL, telefon TEXT, ulke TEXT NOT NULL,
  urun_id INTEGER REFERENCES urun(id), adet INTEGER NOT NULL DEFAULT 1, mesaj TEXT NOT NULL,
  durum TEXT NOT NULL DEFAULT 'yeni' CHECK (durum IN ('yeni','inceleniyor','teklif_verildi','kapandi')),
  olusturma TEXT NOT NULL
);
CREATE TABLE geri_bildirim (
  id INTEGER PRIMARY KEY, sayfa TEXT NOT NULL, metin TEXT NOT NULL, isim TEXT,
  durum TEXT NOT NULL DEFAULT 'yeni' CHECK (durum IN ('yeni','okundu','yapildi')), olusturma TEXT NOT NULL
);
```

`app/fiyat/bantlar.yaml` (birebir):
```yaml
# Temsili fiyat bantları — net EUR, KDV hariç. Anahtarlar normalize() edilmiş kök kategori adı.
robot_kokleri:
  - endustriyel robotlar
  - pozisyonerler
varsayilan: [50, 2000]
bantlar:
  endustriyel robotlar: [8000, 45000]
  pozisyonerler: [5000, 30000]
  robot kontrol uniteleri: [1500, 12000]
  robotik parcalari: [80, 4000]
  slider: [3000, 20000]
  elektrik ve elektronik: [20, 1500]
  mekanik: [15, 900]
  abb reduktor: [400, 6000]
```

- [ ] **Step 2: Ortak fixture'ları yaz**

`tests/conftest.py`:
```python
"""Ortak test fixture'ları ve veri yardımcıları."""
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.db import baglan, gecisleri_uygula
from app.katalog.indeks import indeks_metni

KOK = Path(__file__).resolve().parent.parent
SABIT_ZAMAN = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


@pytest.fixture
def con(tmp_path):
    c = baglan(tmp_path / "test.db")
    gecisleri_uygula(c)
    yield c
    c.close()


@pytest.fixture
def simdi() -> datetime:
    return SABIT_ZAMAN


@pytest.fixture
def bantlar():
    # kurallar modülü Görev 4'te yazılır; içe aktarma fixture içinde ki
    # Görev 1-3 testleri bu modül yokken de toplanabilsin.
    from app.fiyat.kurallar import bantlari_oku

    return bantlari_oku(KOK / "app" / "fiyat" / "bantlar.yaml")


def kategori_ekle(con: sqlite3.Connection, *, kaynak_id: str, ad: str, yol: str,
                  seviye: int, ust_kaynak_id: str | None = None) -> int:
    with con:
        cur = con.execute(
            "INSERT INTO kategori (kaynak_id, ad, ust_kaynak_id, yol, seviye)"
            " VALUES (?, ?, ?, ?, ?)",
            (kaynak_id, ad, ust_kaynak_id, yol, seviye),
        )
    return cur.lastrowid


def urun_ekle(con: sqlite3.Connection, *, sku: str = "S1", ad: str = "Test Ürün",
              kok: str = "ELEKTRİK", fiyat: str = "100.00", teklif: bool = False,
              stok: int = 1, aktif: bool = True, kategori_id: int | None = None,
              kdv: str = "20", simdi: datetime | None = None,
              uretici_kodu: str | None = None, gorsel_url: str | None = None,
              tedarik_suresi_gun: int | None = None) -> int:
    """Ürünü ekler; aktifse arama indeksine (urun_ara) tek satır yazar. Commit eder."""
    zaman = (simdi or SABIT_ZAMAN).isoformat()
    with con:
        cur = con.execute(
            "INSERT INTO urun (sku, ad, uretici_kodu, kategori_id, kok_kategori_ad, kdv_orani,"
            " stok, tedarik_suresi_gun, gorsel_url, temsili_fiyat_eur, fiyat_temsili,"
            " teklif_zorunlu, aktif, olusturma)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
            (sku, ad, uretici_kodu, kategori_id, kok, kdv, stok, tedarik_suresi_gun,
             gorsel_url, fiyat, int(teklif), int(aktif), zaman),
        )
        urun_id = int(cur.lastrowid)
        if aktif:
            con.execute(
                "INSERT INTO urun_ara (metin, urun_id) VALUES (?, ?)",
                (indeks_metni(ad, sku, uretici_kodu), urun_id),
            )
    return urun_id
```

- [ ] **Step 3: Başarısız testleri yaz**

`tests/test_iskelet.py`:
```python
import threading
from decimal import Decimal

import pytest

from app.ayarlar import ayarlari_oku
from app.db import baglan, gecisleri_uygula
from app.katalog.indeks import indeks_metni, indeksi_yeniden_kur
from app.metin import metin_temizle, normalize
from app.para import d, yuvarla
from tests.conftest import kategori_ekle, urun_ekle

TAM_ORTAM = {
    "SHOP_DB": "/tmp/shop.db",
    "SHOP_GIZLI_ANAHTAR": "g" * 32,
    "SHOP_YONETICI": "yonetici",
    "SHOP_YONETICI_OZET": "scrypt$16384$8$1$00$00",
}


def test_gecisler_ikinci_kez_atlanir(tmp_path):
    c = baglan(tmp_path / "yeni.db")
    assert gecisleri_uygula(c) == ["001_baslangic.sql"]
    assert gecisleri_uygula(c) == []
    kayitlar = [r["dosya"] for r in c.execute("SELECT dosya FROM sema_surumu")]
    assert kayitlar == ["001_baslangic.sql"]
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    c.close()


def test_ayarlar_tam():
    a = ayarlari_oku(TAM_ORTAM)
    assert a.db_yolu.name == "shop.db"
    assert a.kaynak_api == "https://www.ceylanrobot.com"
    assert a.bantlar_yolu.name == "bantlar.yaml"


@pytest.mark.parametrize(
    "eksik", ["SHOP_DB", "SHOP_GIZLI_ANAHTAR", "SHOP_YONETICI", "SHOP_YONETICI_OZET"]
)
def test_ayarlar_eksik_anahtar(eksik):
    ortam = {k: v for k, v in TAM_ORTAM.items() if k != eksik}
    with pytest.raises(RuntimeError, match=eksik):
        ayarlari_oku(ortam)


def test_yuvarla_half_up():
    assert yuvarla(Decimal("2.675")) == Decimal("2.68")
    assert yuvarla(Decimal("2.665")) == Decimal("2.67")
    assert yuvarla(Decimal("-2.675")) == Decimal("-2.68")
    assert str(yuvarla(Decimal("5"))) == "5.00"


def test_d_float_reddeder():
    with pytest.raises(TypeError):
        d(2.675)
    assert d("2.675") == Decimal("2.675")
    assert d(3) == Decimal(3)
    assert d(Decimal("1.5")) == Decimal("1.5")


def test_normalize_turkce():
    assert normalize("İZLEME RÖLESİ") == "izleme rolesi"
    assert normalize("ışık") == "isik"
    assert normalize("  ŞALTER   ÇIKIŞ  ") == "salter cikis"
    assert normalize("Güç Kaynağı") == "guc kaynagi"


def test_metin_temizle_bozuk_kodlama():
    sonuc = metin_temizle("GÜÇ KAYNA�\udc9eI")
    assert sonuc == "GÜÇ KAYNA�I"
    sonuc.encode("utf-8")  # UnicodeEncodeError vermemeli
    assert metin_temizle("A\udc9eB") == "A�B"
    assert metin_temizle("  düz metin ") == "düz metin"
    assert metin_temizle(None) is None


def test_yardimcilar_urun_ve_kategori(con):
    kid = kategori_ekle(con, kaynak_id="k1", ad="Elektrik ve Elektronik", yol="10", seviye=0)
    uid = urun_ekle(con, sku="X1", ad="Röle", kategori_id=kid)
    satir = con.execute("SELECT * FROM urun WHERE id=?", (uid,)).fetchone()
    assert satir["sku"] == "X1" and satir["kategori_id"] == kid
    assert satir["temsili_fiyat_eur"] == "100.00"
    bulunan = con.execute("SELECT urun_id FROM urun_ara WHERE urun_ara MATCH 'role'").fetchone()
    assert bulunan[0] == uid


def test_baglanti_baska_thread_te_kullanilabilir(con):
    # FastAPI senkron bağımlılıkları thread havuzunda çalışır (K8: check_same_thread=False)
    sonuc = []
    th = threading.Thread(target=lambda: sonuc.append(con.execute("SELECT 1").fetchone()[0]))
    th.start()
    th.join()
    assert sonuc == [1]


def test_esitleme_gunlugu_bozuk_kolonu(con):
    kolonlar = [r["name"] for r in con.execute("PRAGMA table_info(esitleme_gunlugu)")]
    assert "bozuk" in kolonlar


def test_indeks_metni():
    assert indeks_metni("SIEMENS SIRIUS İZLEME RÖLESİ", "8102030100019", "3UG4512-1BR20") == (
        "siemens sirius izleme rolesi 8102030100019 3ug4512-1br20")
    assert indeks_metni("Işık Perdesi", "S9", None) == "isik perdesi s9"


def test_urun_ekle_yeni_parametreler(con):
    uid = urun_ekle(con, sku="Y1", ad="Röle", uretici_kodu="3UG4512", gorsel_url="https://x/y.webp",
                    tedarik_suresi_gun=7)
    satir = con.execute("SELECT uretici_kodu, gorsel_url, tedarik_suresi_gun FROM urun WHERE id=?",
                        (uid,)).fetchone()
    assert tuple(satir) == ("3UG4512", "https://x/y.webp", 7)
    ara = con.execute("SELECT urun_id, typeof(urun_id) FROM urun_ara WHERE urun_ara MATCH '3ug4512*'").fetchone()
    assert tuple(ara) == (uid, "integer")


def test_indeksi_yeniden_kur(con):
    a = urun_ekle(con, sku="A1", ad="İzleme Rölesi")
    b = urun_ekle(con, sku="B1", ad="Pasif Ürün", aktif=False)
    with con:
        con.execute("DELETE FROM urun_ara")
        indeksi_yeniden_kur(con)
        indeksi_yeniden_kur(con)   # iki kez çağrılınca çift satır oluşmaz
    assert con.execute("SELECT COUNT(*) FROM urun_ara").fetchone()[0] == 1
    assert [r[0] for r in con.execute("SELECT urun_id FROM urun_ara WHERE urun_ara MATCH 'izleme'")] == [a]
    assert con.execute("SELECT COUNT(*) FROM urun_ara WHERE urun_id=?", (b,)).fetchone()[0] == 0
```

- [ ] **Step 4: Çalıştır, başarısız olduğunu gör**

Run: `bash dagitim/test-vm.sh tests/test_iskelet.py -q`
Expected: FAIL — `ImportError while loading conftest '.../tests/conftest.py'` / `ModuleNotFoundError: No module named 'app.db'`; çıkış kodu 4.

- [ ] **Step 5: `app/ayarlar.py` yaz**

```python
"""Ortam değişkenlerinden uygulama ayarları."""
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Ayarlar:
    db_yolu: Path
    gizli_anahtar: str
    yonetici_kullanici: str
    yonetici_parola_ozeti: str
    kaynak_api: str = "https://www.ceylanrobot.com"
    gorsel_kok: str = "https://www.ceylanrobot.com"
    bantlar_yolu: Path = Path(__file__).parent / "fiyat" / "bantlar.yaml"


_ZORUNLU = ("SHOP_DB", "SHOP_GIZLI_ANAHTAR", "SHOP_YONETICI", "SHOP_YONETICI_OZET")


def ayarlari_oku(ortam: Mapping[str, str] = os.environ) -> Ayarlar:
    for anahtar in _ZORUNLU:
        if not ortam.get(anahtar):
            raise RuntimeError(anahtar)
    ek: dict[str, str] = {}
    if ortam.get("SHOP_KAYNAK_API"):
        ek["kaynak_api"] = ortam["SHOP_KAYNAK_API"].rstrip("/")
    return Ayarlar(
        db_yolu=Path(ortam["SHOP_DB"]),
        gizli_anahtar=ortam["SHOP_GIZLI_ANAHTAR"],
        yonetici_kullanici=ortam["SHOP_YONETICI"],
        yonetici_parola_ozeti=ortam["SHOP_YONETICI_OZET"],
        **ek,
    )
```

- [ ] **Step 6: `app/db.py` yaz**

```python
"""SQLite bağlantısı ve numaralı SQL geçişleri."""
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

GECIS_KLASORU = Path(__file__).parent / "gecisler"


def baglan(yol: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(yol), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    return con


def _uygulananlar(con: sqlite3.Connection) -> set[str]:
    tablo = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sema_surumu'"
    ).fetchone()
    if tablo is None:
        return set()
    return {r[0] for r in con.execute("SELECT dosya FROM sema_surumu")}


def gecisleri_uygula(con: sqlite3.Connection) -> list[str]:
    """Henüz uygulanmamış app/gecisler/NNN_*.sql dosyalarını sırayla, her birini
    kendi transaction'ında uygular; yeni uygulananların adlarını döner."""
    uygulanan = _uygulananlar(con)
    yeni: list[str] = []
    for dosya in sorted(GECIS_KLASORU.glob("[0-9][0-9][0-9]_*.sql")):
        if dosya.name in uygulanan:
            continue
        sql = dosya.read_text(encoding="utf-8")
        zaman = datetime.now(UTC).isoformat()
        ad = dosya.name.replace("'", "''")
        betik = (
            "BEGIN;\n" + sql + "\n;\n"
            f"INSERT INTO sema_surumu (dosya, uygulandi) VALUES ('{ad}', '{zaman}');\n"
            "COMMIT;\n"
        )
        try:
            con.executescript(betik)
        except sqlite3.Error:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        yeni.append(dosya.name)
    return yeni
```

- [ ] **Step 7: `app/para.py` yaz**

```python
"""Para tutarları: yalnız Decimal, ROUND_HALF_UP, 2 hane."""
from decimal import ROUND_HALF_UP, Decimal

IKI_HANE = Decimal("0.01")


def d(deger: str | int | Decimal) -> Decimal:
    if isinstance(deger, (bool, float)):
        raise TypeError("float/bool para değeri olarak kabul edilmez")
    if isinstance(deger, Decimal):
        return deger
    if isinstance(deger, (str, int)):
        return Decimal(deger)
    raise TypeError(f"desteklenmeyen tip: {type(deger).__name__}")


def yuvarla(x: Decimal) -> Decimal:
    return x.quantize(IKI_HANE, rounding=ROUND_HALF_UP)
```

- [ ] **Step 8: `app/metin.py` yaz**

```python
"""Türkçe arama normalizasyonu ve bozuk karakter temizliği."""
import re
import unicodedata

_TR_CEVIR = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c"})
# İsteğe bağlı bir U+FFFD ve ardından gelen bir ya da daha çok surrogate (U+D800..DFFF)
_BOZUK = re.compile("�?[\ud800-\udfff]+")


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = s.replace("I", "ı").replace("İ", "i").lower()
    s = s.translate(_TR_CEVIR).casefold()
    return " ".join(s.split())


def metin_temizle(s: str | None) -> str | None:
    if s is None:
        return None
    return _BOZUK.sub("�", s).strip()
```

Notlar: `"İ".lower()` Python'da `"i̇"` (i + birleşik nokta) üretir; bu yüzden `I→ı` ve `İ→i` değişimi `lower()`'dan **önce** yapılır. `metin_temizle` deseni `�?[\ud800-\udfff]+`: önündeki isteğe bağlı `�` ile birlikte ardışık surrogate'ları tek `�`'ye indirir.

- [ ] **Step 9: `app/katalog/indeks.py` yaz**

```python
"""Ürün arama indeksi (FTS5 tablosu urun_ara) — tek yerden metin üretimi ve yeniden kurulum."""
import sqlite3

from app.metin import normalize


def indeks_metni(ad: str, sku: str, uretici_kodu: str | None) -> str:
    return normalize(f"{ad} {sku} {uretici_kodu or ''}")


def indeksi_yeniden_kur(con: sqlite3.Connection) -> None:
    """urun_ara'yı aktif ürünlerden baştan kurar. Commit etmez; çağıranın transaction'ında çalışır."""
    con.execute("DELETE FROM urun_ara")
    satirlar = con.execute("SELECT id, ad, sku, uretici_kodu FROM urun WHERE aktif=1").fetchall()
    con.executemany(
        "INSERT INTO urun_ara (metin, urun_id) VALUES (?, ?)",
        ((indeks_metni(r[1], r[2], r[3]), int(r[0])) for r in satirlar),
    )
```

- [ ] **Step 10: Çalıştır, geçtiğini gör**

Run: `bash dagitim/test-vm.sh tests/test_iskelet.py -q`
Expected: PASS — `16 passed`

- [ ] **Step 11: Bütün testleri çalıştır**

Run: `bash dagitim/test-vm.sh -q`
Expected: PASS — `18 passed` (test_ortam 2 + test_iskelet 16)

- [ ] **Step 12: Commit**

```bash
git add .gitignore .gitattributes app/__init__.py app/fiyat/__init__.py app/hesap/__init__.py app/esitleme/__init__.py app/katalog/__init__.py app/katalog/indeks.py app/ayarlar.py app/db.py app/gecisler/001_baslangic.sql app/para.py app/metin.py app/fiyat/bantlar.yaml tests/conftest.py tests/test_iskelet.py
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m "feat: iskelet - ayarlar, sqlite gecisleri, para, metin, arama indeksi, test fixture'lari" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Görev 2: VKN ve TCKN doğrulama (`app/hesap/dogrulama.py`)

**Files:**
- Create: `app/hesap/dogrulama.py`
- Test: `tests/test_dogrulama.py`

**Interfaces:**
- Consumes: yok (saf fonksiyonlar).
- Produces: `vkn_gecerli(s: str) -> bool` (10 ASCII rakam, Gelir İdaresi algoritması), `tckn_gecerli(s: str) -> bool` (11 ASCII rakam, ilk hane 0 değil, 10. ve 11. hane kontrolleri). Boşluk kırpma/temizleme çağıranın işidir (`hesap.servis.kayit_ol` girdiyi `strip()` eder).

**Test verisinin hesabı (gerçek kişi/kurum numarası kullanılmaz):**

VKN algoritması: ilk 9 hanenin her biri için (i = 0..8) `p = (hane + 9 − i) mod 10`; `q = (p × 2^(9−i)) mod 9`; `p ≠ 0` ve `q = 0` ise `q = 9`. Kontrol hanesi = `(10 − (Σq mod 10)) mod 10`.

`472813659?` için:

| i | hane | p = (h+9−i) mod 10 | 2^(9−i) | q |
|---|---|---|---|---|
| 0 | 4 | 3 | 512 | 1536 mod 9 = 6 |
| 1 | 7 | 5 | 256 | 1280 mod 9 = 2 |
| 2 | 2 | 9 | 128 | 1152 mod 9 = 0 → p≠0 → 9 |
| 3 | 8 | 4 | 64 | 256 mod 9 = 4 |
| 4 | 1 | 6 | 32 | 192 mod 9 = 3 |
| 5 | 3 | 7 | 16 | 112 mod 9 = 4 |
| 6 | 6 | 9 | 8 | 72 mod 9 = 0 → p≠0 → 9 |
| 7 | 5 | 7 | 4 | 28 mod 9 = 1 |
| 8 | 9 | 0 | 2 | 0 |

Σq = 38 → kontrol = (10 − 8) mod 10 = **2** → geçerli VKN `4728136592`; son hanesi değiştirilmiş `4728136593` ve `4728136590` geçersiz. Uç durum: `1234567890` (her `p` = 0, Σq = 0, kontrol 0) geçerli.

TCKN: `10000000146` → tek konumlar (1,3,5,7,9) toplamı 1+0+0+0+1 = 2, çift konumlar (2,4,6,8) toplamı 0; 10. hane (2×7 − 0) mod 10 = **4** ✓; 11. hane (1+0+0+0+0+0+0+0+1+4) mod 10 = **6** ✓. İlk hane kuralı için kontrol haneleri tutarlı ama 0 ile başlayan `01000000168`: tek 0+0+0+0+1 = 1, çift 1+0+0+0 = 1, 10. hane (7−1) mod 10 = 6, 11. hane (0+1+0+0+0+0+0+0+1+6) mod 10 = 8 → yalnız "ilk hane 0" kuralı yüzünden geçersiz.

- [ ] **Step 1: Başarısız testleri yaz**

`tests/test_dogrulama.py`:
```python
import pytest

from app.hesap.dogrulama import tckn_gecerli, vkn_gecerli

# Örnekler gerçek kişi/kurum numarası DEĞİL; algoritmayla üretilmiştir.
GECERLI_VKN = "4728136592"
GECERLI_TCKN = "10000000146"


def test_vkn_gecerli_ornek():
    assert vkn_gecerli(GECERLI_VKN) is True
    assert vkn_gecerli("1234567890") is True  # tüm ara değerleri 0 olan uç durum


def test_vkn_son_hane_degisirse_gecersiz():
    assert vkn_gecerli("4728136593") is False
    assert vkn_gecerli("4728136590") is False


@pytest.mark.parametrize("s", ["472813659", "47281365921", "", "47281365a2", "4728 36592", "４７２８１３６５９２"])
def test_vkn_bicim_hatalari(s):
    assert vkn_gecerli(s) is False


def test_tckn_gecerli_ornek():
    assert tckn_gecerli(GECERLI_TCKN) is True


def test_tckn_kontrol_haneleri():
    assert tckn_gecerli("10000000147") is False  # 11. hane yanlış
    assert tckn_gecerli("10000000156") is False  # 10. hane yanlış


def test_tckn_ilk_hane_sifir():
    # 01000000168 kontrol haneleri bakımından tutarlıdır; yalnız ilk hane 0 olduğu için geçersiz
    assert tckn_gecerli("01000000168") is False


@pytest.mark.parametrize("s", ["1000000014", "100000001460", "", "1000000014a", "1000000014 "])
def test_tckn_bicim_hatalari(s):
    assert tckn_gecerli(s) is False
```

- [ ] **Step 2: Çalıştır, başarısız olduğunu gör**

Run: `bash dagitim/test-vm.sh tests/test_dogrulama.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.hesap.dogrulama'` (1 error during collection)

- [ ] **Step 3: Uygula**

`app/hesap/dogrulama.py`:
```python
"""VKN (Gelir İdaresi algoritması) ve TCKN kontrol hanesi doğrulaması."""


def _rakamlar_mi(s: str, uzunluk: int) -> bool:
    # str.isdigit() "²" gibi karakterleri de kabul eder; yalnız ASCII 0-9
    return len(s) == uzunluk and all("0" <= c <= "9" for c in s)


def vkn_gecerli(s: str) -> bool:
    if not _rakamlar_mi(s, 10):
        return False
    toplam = 0
    for i in range(9):
        p = (int(s[i]) + 9 - i) % 10
        q = (p * 2 ** (9 - i)) % 9
        if p != 0 and q == 0:
            q = 9
        toplam += q
    kontrol = (10 - toplam % 10) % 10
    return kontrol == int(s[9])


def tckn_gecerli(s: str) -> bool:
    if not _rakamlar_mi(s, 11) or s[0] == "0":
        return False
    r = [int(c) for c in s]
    tek = r[0] + r[2] + r[4] + r[6] + r[8]
    cift = r[1] + r[3] + r[5] + r[7]
    if (tek * 7 - cift) % 10 != r[9]:
        return False
    return sum(r[:10]) % 10 == r[10]
```

- [ ] **Step 4: Çalıştır, geçtiğini gör**

Run: `bash dagitim/test-vm.sh tests/test_dogrulama.py -q`
Expected: PASS — `16 passed`

- [ ] **Step 5: Commit**

```bash
git add app/hesap/dogrulama.py tests/test_dogrulama.py
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m "feat: VKN ve TCKN kontrol hanesi dogrulamasi" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Görev 3: TCMB kuru (`app/fiyat/kur.py`)

**Files:**
- Create: `tests/ornekler/tcmb_today.xml`
- Create: `app/fiyat/kur.py`
- Test: `tests/test_kur.py`

**Interfaces:**
- Consumes: Görev 1 — `con`, `simdi` fixture'ları; `kur` tablosu (`tarih TEXT PK, eur_alis, eur_satis, alindi`).
- Produces:
  - `TCMB_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"`
  - `Kur` (frozen dataclass: `tarih: date, eur_alis: Decimal, eur_satis: Decimal`)
  - `tcmb_ayristir(xml: bytes) -> Kur` — bozuk XML / EUR yok / tarih yok / değer bozuk → `ValueError`
  - `kur_kaydet(con, kur: Kur, simdi: datetime) -> None` — `INSERT OR REPLACE`, commit etmez
  - `son_kur(con) -> Kur | None` — en yeni `tarih`
  - `kur_bayat_mi(kur: Kur, bugun: date) -> bool` — `(bugun - kur.tarih).days > 3`
  - `kur_al(con, http: httpx.Client, simdi: datetime) -> Kur` — indir (zaman aşımı 30 sn), `raise_for_status`, ayrıştır, kaydet; her hata istisna olarak yükselir (çağıran `son_kur`'a düşer), commit çağıranın `with con:` bloğundadır.

- [ ] **Step 1: TCMB örnek yanıtını kaydet**

`tests/ornekler/tcmb_today.xml` (gerçek `today.xml` biçimi; değerler örnek):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet type="text/xsl" href="isokur.xsl"?>
<Tarih_Date Tarih="13.10.2026" Date="10/13/2026" Bulten_No="2026/193">
	<Currency CrossOrder="0" Kod="USD" CurrencyCode="USD">
		<Unit>1</Unit>
		<Isim>ABD DOLARI</Isim>
		<CurrencyName>US DOLLAR</CurrencyName>
		<ForexBuying>41.3456</ForexBuying>
		<ForexSelling>41.4201</ForexSelling>
		<BanknoteBuying>41.3167</BanknoteBuying>
		<BanknoteSelling>41.4822</BanknoteSelling>
		<CrossRateUSD/>
		<CrossRateOther/>
	</Currency>
	<Currency CrossOrder="9" Kod="EUR" CurrencyCode="EUR">
		<Unit>1</Unit>
		<Isim>EURO</Isim>
		<CurrencyName>EURO</CurrencyName>
		<ForexBuying>48.1234</ForexBuying>
		<ForexSelling>48.2101</ForexSelling>
		<BanknoteBuying>48.0897</BanknoteBuying>
		<BanknoteSelling>48.2824</BanknoteSelling>
		<CrossRateUSD/>
		<CrossRateOther>1.1639</CrossRateOther>
	</Currency>
</Tarih_Date>
```

- [ ] **Step 2: Başarısız testleri yaz**

`tests/test_kur.py`:
```python
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.fiyat.kur import (
    TCMB_URL,
    Kur,
    kur_al,
    kur_bayat_mi,
    kur_kaydet,
    son_kur,
    tcmb_ayristir,
)

ORNEK = (Path(__file__).parent / "ornekler" / "tcmb_today.xml").read_bytes()


def istemci(isleyici) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(isleyici))


def test_tcmb_ayristir():
    k = tcmb_ayristir(ORNEK)
    assert k == Kur(tarih=date(2026, 10, 13), eur_alis=Decimal("48.1234"), eur_satis=Decimal("48.2101"))


@pytest.mark.parametrize("xml", [
    b"<bozuk",
    b'<Tarih_Date Tarih="13.10.2026"><Currency Kod="USD"><ForexBuying>1</ForexBuying>'
    b"<ForexSelling>1</ForexSelling></Currency></Tarih_Date>",
    b'<Tarih_Date Tarih="13.10.2026"><Currency Kod="EUR"><ForexBuying></ForexBuying>'
    b"<ForexSelling>48.2101</ForexSelling></Currency></Tarih_Date>",
    b'<Tarih_Date><Currency Kod="EUR"><ForexBuying>48.1</ForexBuying>'
    b"<ForexSelling>48.2</ForexSelling></Currency></Tarih_Date>",
])
def test_tcmb_ayristir_bozuk(xml):
    with pytest.raises(ValueError):
        tcmb_ayristir(xml)


def test_kaydet_ve_son_kur(con, simdi):
    assert son_kur(con) is None
    eski = Kur(date(2026, 10, 10), Decimal("47.9000"), Decimal("48.0000"))
    yeni = Kur(date(2026, 10, 13), Decimal("48.1234"), Decimal("48.2101"))
    with con:
        kur_kaydet(con, yeni, simdi)
        kur_kaydet(con, eski, simdi)
    assert son_kur(con) == yeni
    # aynı tarih yeniden kaydedilirse üzerine yazılır
    duzeltme = Kur(date(2026, 10, 13), Decimal("48.1000"), Decimal("48.2000"))
    with con:
        kur_kaydet(con, duzeltme, simdi)
    assert son_kur(con) == duzeltme
    assert con.execute("SELECT COUNT(*) FROM kur").fetchone()[0] == 2


def test_kur_bayat_mi():
    k = Kur(date(2026, 10, 10), Decimal("1"), Decimal("1"))
    assert kur_bayat_mi(k, date(2026, 10, 13)) is False   # 3 gün: bayat değil
    assert kur_bayat_mi(k, date(2026, 10, 14)) is True    # 4 gün: bayat


def test_kur_al_basarili(con, simdi):
    istekler = []

    def isleyici(istek: httpx.Request) -> httpx.Response:
        istekler.append(str(istek.url))
        return httpx.Response(200, content=ORNEK)

    with con:
        k = kur_al(con, istemci(isleyici), simdi)
    assert istekler == [TCMB_URL]
    assert k.eur_satis == Decimal("48.2101")
    assert son_kur(con) == k
    satir = con.execute("SELECT alindi FROM kur").fetchone()
    assert satir[0] == simdi.isoformat()


def test_kur_al_ag_hatasi_son_kuru_korur(con, simdi):
    onceki = Kur(date(2026, 10, 9), Decimal("47.5"), Decimal("47.6"))
    with con:
        kur_kaydet(con, onceki, simdi)

    def ag_hatasi(istek: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("baglanti yok", request=istek)

    with pytest.raises(httpx.ConnectError):
        with con:
            kur_al(con, istemci(ag_hatasi), simdi)
    assert son_kur(con) == onceki


def test_kur_al_http_500_son_kuru_korur(con, simdi):
    onceki = Kur(date(2026, 10, 9), Decimal("47.5"), Decimal("47.6"))
    with con:
        kur_kaydet(con, onceki, simdi)
    with pytest.raises(httpx.HTTPStatusError):
        with con:
            kur_al(con, istemci(lambda istek: httpx.Response(500)), simdi)
    assert son_kur(con) == onceki
```

- [ ] **Step 3: Çalıştır, başarısız olduğunu gör**

Run: `bash dagitim/test-vm.sh tests/test_kur.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.fiyat.kur'`

- [ ] **Step 4: Uygula**

`app/fiyat/kur.py`:
```python
"""TCMB günlük EUR kuru: indirme, ayrıştırma, saklama."""
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import httpx

TCMB_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"


@dataclass(frozen=True)
class Kur:
    tarih: date
    eur_alis: Decimal
    eur_satis: Decimal


def tcmb_ayristir(xml: bytes) -> Kur:
    try:
        kok = ET.fromstring(xml)
    except ET.ParseError as e:
        raise ValueError(f"tcmb_xml_bozuk: {e}") from e
    tarih_metni = kok.get("Tarih")
    if kok.tag != "Tarih_Date" or not tarih_metni:
        raise ValueError("tcmb_tarih_yok")
    tarih = datetime.strptime(tarih_metni, "%d.%m.%Y").date()
    for doviz in kok.iter("Currency"):
        if doviz.get("Kod") != "EUR":
            continue
        try:
            alis = Decimal((doviz.findtext("ForexBuying") or "").strip())
            satis = Decimal((doviz.findtext("ForexSelling") or "").strip())
        except InvalidOperation as e:
            raise ValueError("tcmb_eur_degeri_bozuk") from e
        if alis <= 0 or satis <= 0:
            raise ValueError("tcmb_eur_degeri_bozuk")
        return Kur(tarih=tarih, eur_alis=alis, eur_satis=satis)
    raise ValueError("tcmb_eur_yok")


def kur_kaydet(con: sqlite3.Connection, kur: Kur, simdi: datetime) -> None:
    con.execute(
        "INSERT OR REPLACE INTO kur (tarih, eur_alis, eur_satis, alindi) VALUES (?, ?, ?, ?)",
        (kur.tarih.isoformat(), str(kur.eur_alis), str(kur.eur_satis), simdi.isoformat()),
    )


def son_kur(con: sqlite3.Connection) -> Kur | None:
    satir = con.execute(
        "SELECT tarih, eur_alis, eur_satis FROM kur ORDER BY tarih DESC LIMIT 1"
    ).fetchone()
    if satir is None:
        return None
    return Kur(
        tarih=date.fromisoformat(satir[0]),
        eur_alis=Decimal(satir[1]),
        eur_satis=Decimal(satir[2]),
    )


def kur_bayat_mi(kur: Kur, bugun: date) -> bool:
    return (bugun - kur.tarih).days > 3


def kur_al(con: sqlite3.Connection, http: httpx.Client, simdi: datetime) -> Kur:
    yanit = http.get(TCMB_URL, timeout=30.0)
    yanit.raise_for_status()
    kur = tcmb_ayristir(yanit.content)
    kur_kaydet(con, kur, simdi)
    return kur
```

- [ ] **Step 5: Çalıştır, geçtiğini gör**

Run: `bash dagitim/test-vm.sh tests/test_kur.py -q`
Expected: PASS — `10 passed`

- [ ] **Step 6: Commit**

```bash
git add tests/ornekler/tcmb_today.xml app/fiyat/kur.py tests/test_kur.py
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m "feat: TCMB EUR kuru ayristirma, saklama ve bayatlik kontrolu" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Görev 4: Fiyat kuralları (`app/fiyat/kurallar.py`)

**Files:**
- Create: `app/fiyat/kurallar.py`
- Test: `tests/test_kurallar.py`
- (`app/fiyat/bantlar.yaml` Görev 1'de oluşturuldu; değişmez.)

**Interfaces:**
- Consumes: Görev 1 — `app.para.d`, `app.para.yuvarla`, `app.metin.normalize`, fixture `bantlar`.
- Produces (sözleşmedeki adlar birebir):
  - `KurYok(ValueError)` (K5)
  - `TEKLIF_ESIGI_EUR = Decimal("15000")`, `KARGO_TR_NET_EUR = Decimal("15.00")`, ek sabitler `KARGO_KDV_ORANI = Decimal("20")`, `SIFIR = Decimal("0.00")`
  - `MusteriTipi(StrEnum)`: `BIREYSEL="bireysel"`, `KURUMSAL="kurumsal"`, `YURTDISI="yurtdisi"`
  - `TeslimYontemi(StrEnum)`: `KARGO="kargo"`, `FABRIKA="fabrika"`, `YURTDISI_DAP="yurtdisi_dap"`
  - `Bantlar(robot_kokleri: frozenset[str], bantlar: Mapping[str, tuple[Decimal, Decimal]], varsayilan: tuple[Decimal, Decimal])`, `bantlari_oku(yol: Path) -> Bantlar`
  - `temsili_fiyat_eur(sku: str, kok_kategori_ad: str, bantlar: Bantlar) -> Decimal` (`sha256(sku)` ilk 8 bayt big-endian / 2^64; 1 €'ya ROUND_HALF_UP; `.00` ile)
  - `teklif_zorunlu_mu(kok_kategori_ad: str, net_eur: Decimal, bantlar: Bantlar) -> bool`
  - `Baglam(musteri_tipi: MusteriTipi, teslimat_ulkesi: str)`, `kdv_uygulanir(b) -> bool`, `tahsilat_para_birimi(b) -> str`, `gosterim_kdv_dahil(b) -> bool`
  - `Kalem(urun_id, sku, ad, adet, birim_net_eur, kdv_orani, tedarik_teyit=False)`, `SatirTutar(kalem, net, kdv, brut)`, `SepetTutari(para_birimi, satirlar, ara_toplam, kdv, kargo_net, kargo_kdv, toplam, kur, ihracat_istisnasi)`
  - `sepet_hesapla(kalemler: Sequence[Kalem], b: Baglam, teslim: TeslimYontemi, kur_eur_try: Decimal | None) -> SepetTutari` — TRY tahsilatta kur yoksa `KurYok("kur_yok")` (K5); EUR tahsilatta `kur=None`; kargo yalnız `KARGO` **ve** teslimat TR iken > 0.
  - `FiyatGosterim(ana_tutar, ana_para, kdv_dahil, ikincil_tutar, ikincil_para)`, `birim_fiyat_gosterimi(net_eur, kdv_orani, b, kur_eur_try) -> FiyatGosterim` — K3: (1) KURUMSAL (teslimat ne olursa olsun) → ana EUR net, ikincil `yuvarla(net×kur)` TRY; kur yoksa ikincil yok. (2) Diğerleri: ana para `tahsilat_para_birimi(b)`, `kdv_dahil = gosterim_kdv_dahil(b)`; EUR ise ikincil yok; TRY ise ikincil EUR net — BIREYSEL & TR: `yuvarla(net×kur)` + `yuvarla(o×oran/100)` (KDV dahil), BIREYSEL & teslimat≠TR: `yuvarla(net×kur)` (KDV yok). (3) TRY gerekiyor ama kur yok → ana EUR net, `kdv_dahil=False`, ikincil yok (şablon "KDV hariç" yazar).

**Beklenen değerlerin hesabı (kur 48.2101, KDV %20):**
- Tek kalem 100.00 EUR: TRY net = 100.00 × 48.2101 = 4821.01; KDV = 964.202 → 964.20; brüt 5785.21.
- Kargo TR, TRY: 15.00 × 48.2101 = 723.1515 → 723.15; KDV = 144.63 (723.15 × 0.2 = 144.630).
- §5.3 satır 1/3 (TRY, KARGO): KDV = 964.20 + 144.63 = 1108.83; toplam = 4821.01 + 723.15 + 1108.83 = 6652.99.
- §5.3 satır 6 (EUR, TR teslim, KARGO): net 100.00, KDV 20.00; kargo 15.00 + 3.00; KDV toplam 23.00; toplam 138.00.
- **Yuvarlama sırası örneği** (bireysel TR, KARGO, üç satır):
  - A: 33.335 × 3 = 100.005 EUR; × 48.2101 = 4821.2510505 → **4821.25**; KDV 964.25 (tam); brüt 5785.50. Birim önce çevrilip yuvarlansaydı: 33.335 × 48.2101 = 1607.0836835 → 1607.08 × 3 = 4821.24 (farklı → sıra testte sabitlenir).
  - B: 0.07 × 48.2101 = 3.374707 → **3.37**; KDV 0.674 → **0.67**.
  - C: 12.34 × 48.2101 = 594.912634 → **594.91**; KDV 118.982 → **118.98**.
  - Ara toplam 4821.25 + 3.37 + 594.91 = **5419.53**. Satır KDV toplamı 964.25 + 0.67 + 118.98 = 1083.90 (toplam üzerinden hesaplansaydı 5419.53 × 0.2 = 1083.906 → 1083.91 olurdu → fark testte sabitlenir).
  - KDV = 1083.90 + 144.63 = **1228.53**; toplam = 5419.53 + 723.15 + 1228.53 = **7371.21**.
- Temsili fiyat: `sha256("8301033800019")[:8] / 2^64 = 0.2031047540…`; 8000 + 0.2031047540 × 37000 = 15514.876 → **15515.00**. `sha256("8102030100019")` oranı 0.3319615622…; 20 + 0.3319615622 × 1480 = 511.303 → **511.00**.

- [ ] **Step 1: Başarısız testleri yaz**

`tests/test_kurallar.py`:
```python
from decimal import Decimal

import pytest

from app.fiyat.kurallar import (
    KARGO_TR_NET_EUR,
    TEKLIF_ESIGI_EUR,
    Baglam,
    FiyatGosterim,
    KurYok,
    Kalem,
    MusteriTipi,
    TeslimYontemi,
    birim_fiyat_gosterimi,
    gosterim_kdv_dahil,
    kdv_uygulanir,
    sepet_hesapla,
    tahsilat_para_birimi,
    temsili_fiyat_eur,
    teklif_zorunlu_mu,
)

KUR = Decimal("48.2101")
D = Decimal


def kalem(birim="100.00", adet=1, kdv="20", urun_id=1, sku="S1"):
    return Kalem(urun_id=urun_id, sku=sku, ad="Ürün " + sku, adet=adet,
                 birim_net_eur=D(birim), kdv_orani=D(kdv))


# ---- bantlar ----

def test_bantlar_okunur(bantlar):
    assert bantlar.robot_kokleri == frozenset({"endustriyel robotlar", "pozisyonerler"})
    assert bantlar.bantlar["endustriyel robotlar"] == (D("8000"), D("45000"))
    assert bantlar.varsayilan == (D("50"), D("2000"))


# ---- temsili fiyat ----

def test_temsili_fiyat_deterministik(bantlar):
    a = temsili_fiyat_eur("8102030100019", "Elektrik ve Elektronik", bantlar)
    b = temsili_fiyat_eur("8102030100019", "Elektrik ve Elektronik", bantlar)
    assert a == b == D("511.00")
    assert str(a) == "511.00"


def test_temsili_fiyat_bilinen_degerler(bantlar):
    # sha256("8301033800019")[:8] / 2^64 = 0.20310475...; 8000 + 0.20310475*37000 = 15514.876 -> 15515
    assert temsili_fiyat_eur("8301033800019", "Endüstriyel Robotlar", bantlar) == D("15515.00")


@pytest.mark.parametrize("kok,alt,ust", [
    ("Endüstriyel Robotlar", 8000, 45000),
    ("ENDÜSTRİYEL ROBOTLAR", 8000, 45000),
    ("Mekanik", 15, 900),
    ("ABB REDÜKTÖR", 400, 6000),
    ("Bilinmeyen Kök", 50, 2000),
    ("", 50, 2000),
])
def test_temsili_fiyat_bant_icinde(bantlar, kok, alt, ust):
    for i in range(200):
        f = temsili_fiyat_eur(f"SKU{i:05d}", kok, bantlar)
        assert D(alt) <= f <= D(ust)
        assert f == f.quantize(D("1"))
        assert f.as_tuple().exponent == -2


# ---- teklif kuralı ----

def test_teklif_robot_koku(bantlar):
    assert teklif_zorunlu_mu("Endüstriyel Robotlar", D("10.00"), bantlar) is True
    assert teklif_zorunlu_mu("POZİSYONERLER", D("10.00"), bantlar) is True
    assert teklif_zorunlu_mu("Robotik Parçaları", D("10.00"), bantlar) is False


def test_teklif_esigi_tam_sinir(bantlar):
    assert TEKLIF_ESIGI_EUR == D("15000")
    assert teklif_zorunlu_mu("Mekanik", D("15000.00"), bantlar) is False
    assert teklif_zorunlu_mu("Mekanik", D("15000.01"), bantlar) is True


# ---- bağlam kuralları ----

def test_baglam_yardimcilari():
    tr_bir = Baglam(MusteriTipi.BIREYSEL, "TR")
    assert kdv_uygulanir(tr_bir) and gosterim_kdv_dahil(tr_bir)
    tr_kur = Baglam(MusteriTipi.KURUMSAL, "TR")
    assert kdv_uygulanir(tr_kur) and not gosterim_kdv_dahil(tr_kur)
    assert not gosterim_kdv_dahil(Baglam(MusteriTipi.BIREYSEL, "DE"))
    assert tahsilat_para_birimi(Baglam(MusteriTipi.KURUMSAL, "DE")) == "EUR"


# ---- §5.3 tahsilat tablosu: her satır ayrı test ----
# Ortak girdi: 1 kalem, birim 100.00 EUR net, KDV %20, kur 48.2101.
# TRY satır: net = 100.00*48.2101 = 4821.01 ; KDV = 964.202 -> 964.20
# TRY kargo: 15.00*48.2101 = 723.1515 -> 723.15 ; KDV = 144.63

def test_tablo_tr_bireysel_tr_teslim():
    t = sepet_hesapla([kalem()], Baglam(MusteriTipi.BIREYSEL, "TR"), TeslimYontemi.KARGO, KUR)
    assert t.para_birimi == "TRY" and t.kur == KUR and t.ihracat_istisnasi is False
    assert (t.ara_toplam, t.kargo_net, t.kargo_kdv) == (D("4821.01"), D("723.15"), D("144.63"))
    assert t.kdv == D("1108.83")          # 964.20 + 144.63
    assert t.toplam == D("6652.99")       # 4821.01 + 723.15 + 1108.83


def test_tablo_tr_bireysel_yurtdisi_teslim():
    t = sepet_hesapla([kalem()], Baglam(MusteriTipi.BIREYSEL, "DE"), TeslimYontemi.YURTDISI_DAP, KUR)
    assert t.para_birimi == "TRY" and t.ihracat_istisnasi is True
    assert t.kdv == D("0.00") and t.satirlar[0].kdv == D("0.00")
    assert t.kargo_net == D("0.00")
    assert t.toplam == D("4821.01")


def test_tablo_tr_kurumsal_tr_teslim():
    t = sepet_hesapla([kalem()], Baglam(MusteriTipi.KURUMSAL, "TR"), TeslimYontemi.KARGO, KUR)
    assert t.para_birimi == "TRY" and t.ihracat_istisnasi is False
    assert t.kdv == D("1108.83") and t.toplam == D("6652.99")


def test_tablo_tr_kurumsal_yurtdisi_teslim():
    t = sepet_hesapla([kalem()], Baglam(MusteriTipi.KURUMSAL, "DE"), TeslimYontemi.YURTDISI_DAP, KUR)
    assert t.para_birimi == "EUR" and t.kur is None and t.ihracat_istisnasi is True
    assert t.kdv == D("0.00") and t.toplam == D("100.00")


def test_tablo_yurtdisi_yurtdisi_teslim():
    t = sepet_hesapla([kalem()], Baglam(MusteriTipi.YURTDISI, "DE"), TeslimYontemi.YURTDISI_DAP, None)
    assert t.para_birimi == "EUR" and t.kur is None and t.ihracat_istisnasi is True
    assert t.kdv == D("0.00") and t.toplam == D("100.00")


def test_tablo_yurtdisi_hesap_tr_teslim():
    t = sepet_hesapla([kalem()], Baglam(MusteriTipi.YURTDISI, "TR"), TeslimYontemi.KARGO, None)
    assert t.para_birimi == "EUR" and t.kur is None and t.ihracat_istisnasi is False
    assert t.satirlar[0].kdv == D("20.00")
    assert (t.kargo_net, t.kargo_kdv) == (KARGO_TR_NET_EUR, D("3.00"))
    assert t.kdv == D("23.00") and t.toplam == D("138.00")   # 100 + 15 + 23


# ---- satır bazında yuvarlama sırası ----

def test_satir_bazinda_yuvarlama_sirasi():
    kalemler = [
        kalem("33.335", adet=3, urun_id=1, sku="A"),
        kalem("0.07", adet=1, urun_id=2, sku="B"),
        kalem("12.34", adet=1, urun_id=3, sku="C"),
    ]
    t = sepet_hesapla(kalemler, Baglam(MusteriTipi.BIREYSEL, "TR"), TeslimYontemi.KARGO, KUR)
    a, b, c = t.satirlar
    # A: 33.335*3 = 100.005 ; *48.2101 = 4821.2510505 -> 4821.25
    #    (birimi önce çevirip yuvarlasaydık: 1607.08*3 = 4821.24 olurdu)
    assert a.net == D("4821.25") and a.kdv == D("964.25") and a.brut == D("5785.50")
    # B: 0.07*48.2101 = 3.374707 -> 3.37 ; KDV 0.674 -> 0.67
    assert b.net == D("3.37") and b.kdv == D("0.67")
    # C: 12.34*48.2101 = 594.912634 -> 594.91 ; KDV 118.982 -> 118.98
    assert c.net == D("594.91") and c.kdv == D("118.98")
    assert t.ara_toplam == D("5419.53")
    # satır KDV toplamı 1083.90 ; toplam üzerinden hesaplansaydı 5419.53*0.2 = 1083.906 -> 1083.91 olurdu
    assert t.kdv == D("1228.53")          # 1083.90 + kargo KDV 144.63
    assert t.toplam == D("7371.21")       # 5419.53 + 723.15 + 1228.53


# ---- kargo ----

def test_kargo_uc_yontem():
    b = Baglam(MusteriTipi.KURUMSAL, "TR")
    kargo = sepet_hesapla([kalem()], b, TeslimYontemi.KARGO, KUR)
    assert (kargo.kargo_net, kargo.kargo_kdv) == (D("723.15"), D("144.63"))
    fabrika = sepet_hesapla([kalem()], b, TeslimYontemi.FABRIKA, KUR)
    assert (fabrika.kargo_net, fabrika.kargo_kdv) == (D("0.00"), D("0.00"))
    assert fabrika.toplam == D("5785.21")   # 4821.01 + 964.20
    dap = sepet_hesapla([kalem()], Baglam(MusteriTipi.YURTDISI, "DE"), TeslimYontemi.YURTDISI_DAP, None)
    assert (dap.kargo_net, dap.kargo_kdv) == (D("0.00"), D("0.00"))


def test_try_tahsilatta_kur_yoksa_hata():
    with pytest.raises(KurYok, match="kur_yok"):
        sepet_hesapla([kalem()], Baglam(MusteriTipi.BIREYSEL, "TR"), TeslimYontemi.KARGO, None)
    assert issubclass(KurYok, ValueError)
    with pytest.raises(KurYok, match="kur_yok"):
        sepet_hesapla([kalem()], Baglam(MusteriTipi.KURUMSAL, "TR"), TeslimYontemi.FABRIKA, None)


def test_bos_sepet_sifir():
    t = sepet_hesapla([], Baglam(MusteriTipi.YURTDISI, "DE"), TeslimYontemi.YURTDISI_DAP, None)
    assert t.satirlar == () and t.toplam == D("0.00")


# ---- birim fiyat gösterimi ----

def test_gosterim_bireysel_tr():
    g = birim_fiyat_gosterimi(D("100.00"), D("20"), Baglam(MusteriTipi.BIREYSEL, "TR"), KUR)
    # 4821.01 + 964.20 = 5785.21 TRY KDV dahil ; ikincil 100.00 EUR net
    assert g == FiyatGosterim(D("5785.21"), "TRY", True, D("100.00"), "EUR")


def test_gosterim_kurumsal_tr():
    g = birim_fiyat_gosterimi(D("100.00"), D("20"), Baglam(MusteriTipi.KURUMSAL, "TR"), KUR)
    assert g == FiyatGosterim(D("100.00"), "EUR", False, D("4821.01"), "TRY")


def test_gosterim_bireysel_yurtdisi_teslim():
    # §5.3 satır 2: TRY, KDV yok (ihracat), ikincil EUR net
    g = birim_fiyat_gosterimi(D("100.00"), D("20"), Baglam(MusteriTipi.BIREYSEL, "DE"), KUR)
    assert g == FiyatGosterim(D("4821.01"), "TRY", False, D("100.00"), "EUR")


def test_gosterim_kurumsal_yurtdisi_teslim():
    g = birim_fiyat_gosterimi(D("100.00"), D("20"), Baglam(MusteriTipi.KURUMSAL, "DE"), KUR)
    assert g == FiyatGosterim(D("100.00"), "EUR", False, D("4821.01"), "TRY")


def test_gosterim_yurtdisi():
    g = birim_fiyat_gosterimi(D("100.00"), D("20"), Baglam(MusteriTipi.YURTDISI, "DE"), KUR)
    assert g == FiyatGosterim(D("100.00"), "EUR", False, None, None)


def test_gosterim_yurtdisi_hesap_tr_teslim():
    g = birim_fiyat_gosterimi(D("100.00"), D("20"), Baglam(MusteriTipi.YURTDISI, "TR"), KUR)
    assert g == FiyatGosterim(D("100.00"), "EUR", False, None, None)


@pytest.mark.parametrize("tip,ulke", [
    (MusteriTipi.BIREYSEL, "TR"), (MusteriTipi.BIREYSEL, "DE"),
    (MusteriTipi.KURUMSAL, "TR"), (MusteriTipi.KURUMSAL, "DE"),
])
def test_gosterim_kur_yoksa_eur_net(tip, ulke):
    g = birim_fiyat_gosterimi(D("100.00"), D("20"), Baglam(tip, ulke), None)
    assert g == FiyatGosterim(D("100.00"), "EUR", False, None, None)
```

- [ ] **Step 2: Çalıştır, başarısız olduğunu gör**

Run: `bash dagitim/test-vm.sh tests/test_kurallar.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.fiyat.kurallar'`

- [ ] **Step 3: Uygula**

`app/fiyat/kurallar.py`:
```python
"""Fiyat, KDV, para birimi, kargo ve teklif kuralları (saf fonksiyonlar)."""
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from pathlib import Path

import yaml

from app.metin import normalize
from app.para import d, yuvarla

TEKLIF_ESIGI_EUR = Decimal("15000")
KARGO_TR_NET_EUR = Decimal("15.00")
KARGO_KDV_ORANI = Decimal("20")
SIFIR = Decimal("0.00")


class KurYok(ValueError):
    """TRY tahsilat/gösterim için kur gerekiyor ama yok. Web katmanı yakalar."""


class MusteriTipi(StrEnum):
    BIREYSEL = "bireysel"
    KURUMSAL = "kurumsal"
    YURTDISI = "yurtdisi"


class TeslimYontemi(StrEnum):
    KARGO = "kargo"
    FABRIKA = "fabrika"
    YURTDISI_DAP = "yurtdisi_dap"


@dataclass(frozen=True)
class Bantlar:
    robot_kokleri: frozenset[str]
    bantlar: Mapping[str, tuple[Decimal, Decimal]]
    varsayilan: tuple[Decimal, Decimal]


def _aralik(deger: list) -> tuple[Decimal, Decimal]:
    alt, ust = (d(str(x)) for x in deger)
    if alt > ust:
        raise ValueError(f"bant alt sınırı üst sınırdan büyük: {deger}")
    return alt, ust


def bantlari_oku(yol: Path) -> Bantlar:
    ham = yaml.safe_load(Path(yol).read_text(encoding="utf-8"))
    return Bantlar(
        robot_kokleri=frozenset(normalize(k) for k in ham["robot_kokleri"]),
        bantlar={normalize(k): _aralik(v) for k, v in ham["bantlar"].items()},
        varsayilan=_aralik(ham["varsayilan"]),
    )


def temsili_fiyat_eur(sku: str, kok_kategori_ad: str, bantlar: Bantlar) -> Decimal:
    alt, ust = bantlar.bantlar.get(normalize(kok_kategori_ad), bantlar.varsayilan)
    ozet = hashlib.sha256(sku.encode("utf-8")).digest()[:8]
    oran = Decimal(int.from_bytes(ozet, "big")) / Decimal(2**64)
    ham = alt + oran * (ust - alt)
    return ham.quantize(Decimal("1"), rounding=ROUND_HALF_UP).quantize(Decimal("0.01"))


def teklif_zorunlu_mu(kok_kategori_ad: str, net_eur: Decimal, bantlar: Bantlar) -> bool:
    return normalize(kok_kategori_ad) in bantlar.robot_kokleri or net_eur > TEKLIF_ESIGI_EUR


@dataclass(frozen=True)
class Baglam:
    musteri_tipi: MusteriTipi
    teslimat_ulkesi: str


def kdv_uygulanir(b: Baglam) -> bool:
    return b.teslimat_ulkesi == "TR"


def tahsilat_para_birimi(b: Baglam) -> str:
    if b.musteri_tipi == MusteriTipi.BIREYSEL:
        return "TRY"
    if b.musteri_tipi == MusteriTipi.KURUMSAL:
        return "TRY" if b.teslimat_ulkesi == "TR" else "EUR"
    return "EUR"


def gosterim_kdv_dahil(b: Baglam) -> bool:
    return b.musteri_tipi == MusteriTipi.BIREYSEL and kdv_uygulanir(b)


@dataclass(frozen=True)
class Kalem:
    urun_id: int
    sku: str
    ad: str
    adet: int
    birim_net_eur: Decimal
    kdv_orani: Decimal
    tedarik_teyit: bool = False


@dataclass(frozen=True)
class SatirTutar:
    kalem: Kalem
    net: Decimal
    kdv: Decimal
    brut: Decimal


@dataclass(frozen=True)
class SepetTutari:
    para_birimi: str
    satirlar: tuple[SatirTutar, ...]
    ara_toplam: Decimal
    kdv: Decimal
    kargo_net: Decimal
    kargo_kdv: Decimal
    toplam: Decimal
    kur: Decimal | None
    ihracat_istisnasi: bool


def sepet_hesapla(kalemler: Sequence[Kalem], b: Baglam, teslim: TeslimYontemi,
                  kur_eur_try: Decimal | None) -> SepetTutari:
    para = tahsilat_para_birimi(b)
    if para == "TRY":
        if kur_eur_try is None:
            raise KurYok("kur_yok")
        carpan = kur_eur_try
        kur = kur_eur_try
    else:
        carpan = Decimal("1")
        kur = None
    kdv_var = kdv_uygulanir(b)

    satirlar: list[SatirTutar] = []
    for k in kalemler:
        net = yuvarla(k.birim_net_eur * k.adet * carpan)
        kdv = yuvarla(net * k.kdv_orani / 100) if kdv_var else SIFIR
        satirlar.append(SatirTutar(kalem=k, net=net, kdv=kdv, brut=net + kdv))

    if teslim == TeslimYontemi.KARGO and b.teslimat_ulkesi == "TR":
        kargo_net = yuvarla(KARGO_TR_NET_EUR * carpan)
        kargo_kdv = yuvarla(kargo_net * KARGO_KDV_ORANI / 100)
    else:
        kargo_net = SIFIR
        kargo_kdv = SIFIR

    ara_toplam = sum((s.net for s in satirlar), SIFIR)
    kdv_toplam = sum((s.kdv for s in satirlar), SIFIR) + kargo_kdv
    return SepetTutari(
        para_birimi=para,
        satirlar=tuple(satirlar),
        ara_toplam=ara_toplam,
        kdv=kdv_toplam,
        kargo_net=kargo_net,
        kargo_kdv=kargo_kdv,
        toplam=ara_toplam + kargo_net + kdv_toplam,
        kur=kur,
        ihracat_istisnasi=not kdv_var,
    )


@dataclass(frozen=True)
class FiyatGosterim:
    ana_tutar: Decimal
    ana_para: str
    kdv_dahil: bool
    ikincil_tutar: Decimal | None
    ikincil_para: str | None


def birim_fiyat_gosterimi(net_eur: Decimal, kdv_orani: Decimal, b: Baglam,
                          kur_eur_try: Decimal | None) -> FiyatGosterim:
    eur_net = yuvarla(net_eur)
    yalniz_eur = FiyatGosterim(eur_net, "EUR", False, None, None)
    if b.musteri_tipi == MusteriTipi.KURUMSAL:
        # teslimat ülkesinden bağımsız: EUR net, kur varsa TRY net ikincil
        if kur_eur_try is None:
            return yalniz_eur
        return FiyatGosterim(eur_net, "EUR", False, yuvarla(net_eur * kur_eur_try), "TRY")
    if tahsilat_para_birimi(b) == "EUR":
        return yalniz_eur
    if kur_eur_try is None:
        return yalniz_eur        # TRY gerekiyor ama kur yok: EUR net, kdv_dahil=False
    try_net = yuvarla(net_eur * kur_eur_try)
    if gosterim_kdv_dahil(b):
        return FiyatGosterim(try_net + yuvarla(try_net * kdv_orani / 100), "TRY", True, eur_net, "EUR")
    return FiyatGosterim(try_net, "TRY", False, eur_net, "EUR")   # bireysel, teslimat TR dışı
```

- [ ] **Step 4: Çalıştır, geçtiğini gör**

Run: `bash dagitim/test-vm.sh tests/test_kurallar.py -q`
Expected: PASS — `32 passed`

- [ ] **Step 5: Kontrol testi — kural bozulunca test gerçekten düşüyor mu**

Geçici olarak `teklif_zorunlu_mu` içindeki `>` işaretini `>=` yap.
Run: `bash dagitim/test-vm.sh tests/test_kurallar.py -q -k esigi`
Expected: FAIL — `test_teklif_esigi_tam_sinir` (`assert True is False`). Sonra `>`'ya geri al ve
Run: `bash dagitim/test-vm.sh tests/test_kurallar.py -q`
Expected: PASS — `32 passed`. Dosyada `or net_eur > TEKLIF_ESIGI_EUR` satırının geri geldiğini doğrula.

- [ ] **Step 6: Commit**

```bash
git add app/fiyat/kurallar.py tests/test_kurallar.py
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m "feat: fiyat kurallari - temsili fiyat, teklif esigi, KDV/para birimi, sepet tutari" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Görev 5: Katalog eşitleme (`app/esitleme/kaynak.py`, `app/esitleme/esitle.py`)

**Files:**
- Create: `tests/ornekler/kategoriler.json`, `tests/ornekler/urunler_s1.json`, `tests/ornekler/urunler_s2.json`, `tests/ornekler/urunler_bozuk.json`
- Create: `app/esitleme/kaynak.py`
- Create: `app/esitleme/esitle.py`
- Test: `tests/test_kaynak.py`, `tests/test_esitleme.py`

**Interfaces:**
- Consumes: Görev 1 — `metin_temizle`, `yuvarla`, `app.katalog.indeks.indeksi_yeniden_kur`, `esitleme_gunlugu.bozuk` kolonu, `con`/`bantlar` fixture'ları, `urun_ekle`; Görev 4 — `Bantlar`, `temsili_fiyat_eur`, `teklif_zorunlu_mu`.
- Produces:
  - `KaynakHatasi(Exception)`; `KaynakIstemci(http: httpx.Client, taban: str, bekleme: float = 1.0, uyku: Callable[[float], None] = time.sleep)`; öznitelik `taban` (sondaki `/` kırpılmış); `kategoriler() -> list[dict]` (GET `{taban}/api/public/categories`, yanıt düz liste); `urun_sayfasi(sayfa: int, limit: int = 20) -> tuple[list[dict], int]` (GET `{taban}/api/public/products?page=&limit=`, `(data, total)`). Her HTTP çağrısından önce `uyku(bekleme)`; hata (ağ, HTTP ≥ 400, JSON değil, biçimsiz) → `YENIDEN_DENEME_BEKLEMELERI = (2.0, 4.0)` sn bekleyerek en fazla 3 deneme (ilk istek + 2 yeniden deneme, K2) → `KaynakHatasi`. Zaman aşımı 30 sn (`ZAMAN_ASIMI`).
  - `TurSonucu(durum, api_toplam, cekilen, eklenen, guncellenen, pasiflenen, hata, bozuk: int = 0)` (K1: `bozuk` alanı sona, varsayılanlı eklendi; günlükte `bozuk` kolonuna yazılır); `esitle(con, kaynak, bantlar, simdi: Callable[[], datetime]) -> TurSonucu` (kendi transaction'larını yönetir, hiçbir koşulda istisna fırlatmaz); `son_basarili_esitleme(con) -> datetime | None`; `son_esitleme(con) -> sqlite3.Row | None`.
  - Davranış: kategoriler ya da 1. sayfa alınamazsa `hata` (urun/kategori değişmez). Sonraki bir sayfa alınamazsa o sayfa atlanır → tur `eksik`, `hata` alanında `alinamayan_sayfa: N`. Bozuk kayıt (sku boş, ad yok, `categoryId` null, `price` yok, sayı alanı bozuk) atlanır ve `bozuk` olarak sayılır. Tur **tam**: alınamayan sayfa yok ve `benzersiz_sku + bozuk == ilk sayfanın total'i == son sayfanın total'i` (K1). `cekilen` = geçerli kayıt sayısı. Sayfalama, görülen kayıt sayısı `total`'e ulaşınca ya da boş sayfa gelince durur (emniyet sınırı 1000 sayfa).
  - Ürün eşleme: `sku`, `name`→`ad`, `attributes.manufacturerCode`→`uretici_kodu`, `attributes.vatRate`→`kdv_orani` ("20"), `stock`→`stok`, `images[0]`→`gorsel_url = kaynak.taban + yol` (mutlak URL ise olduğu gibi), `price.amount`→`kaynak_fiyat_eur` ("0.00"), `categoryId._id`→`kategori_id`, `updatedAt`→`kaynak_guncelleme`. `kok_kategori_ad` = kategori yolunun ilk segmentine eşit `yol`'lu level 0 kategorinin `metin_temizle`'li adı. Kaynak fiyat > 0 → `temsili_fiyat_eur = kaynak`, `fiyat_temsili = 0`; değilse `temsili_fiyat_eur(sku, kok, bantlar)`, `fiyat_temsili = 1`. `teklif_zorunlu = teklif_zorunlu_mu(kok, temsili_fiyat_eur, bantlar)`. Upsert `durum_kodu`, `durum_ornek`, `tedarik_suresi_gun`, `olusturma` alanlarına dokunmaz.
  - `urun_ara`: her tam/eksik turda son transaction içinde `indeksi_yeniden_kur(con)` ile yeniden kurulur (K6).

Gerçek API biçimi 12.10.2026'da doğrulandı: ürün listesi `{"data": [...], "total": 4449, "page": 1, "limit": 2, "totalPages": 2225}`, kategori listesi düz JSON dizisi (`_id, name, parentId, path, level, isActive, erpId, ...`). Örnek dosyalardaki KUKA ve Siemens kayıtları bu yanıttan kısaltılmıştır; `GÜÇ KAYNA�\udc9eI` bozuk kodlaması 12.10 sabahki gözlemi yeniden üretir (JSON'da `\udc9e` kaçışı, `json.loads` tek başına surrogate üretir).

- [ ] **Step 1: API örnek yanıtlarını kaydet**

`tests/ornekler/kategoriler.json` (son kayıt: adı `null` → atlanmalı):
```json
[
  {"_id": "6a26d4fdd01723cd75a5003e", "name": "Endüstriyel Robotlar", "path": "12", "level": 0, "sortOrder": 0, "isActive": true, "erpId": 12},
  {"_id": "6a26d4fdd01723cd75a50041", "name": "KUKA", "parentId": "6a26d4fdd01723cd75a5003e", "path": "12.41", "level": 1, "sortOrder": 0, "isActive": true, "erpId": 41},
  {"_id": "6a26d4fdd01723cd75a5004d", "name": "KR C4", "parentId": "6a26d4fdd01723cd75a50041", "path": "12.41.243", "level": 2, "sortOrder": 0, "isActive": true, "erpId": 243},
  {"_id": "6a26d4fcd01723cd75a4fc9f", "name": "Elektrik ve Elektronik", "path": "10", "level": 0, "sortOrder": 0, "isActive": true, "erpId": 10},
  {"_id": "6a26d4fcd01723cd75a4fcb4", "name": "KONTROL SISTEMLERI", "parentId": "6a26d4fcd01723cd75a4fc9f", "path": "10.18", "level": 1, "sortOrder": 0, "isActive": true, "erpId": 18},
  {"_id": "6a26d4fcd01723cd75a4fcbd", "name": "ROLELER/ZAMANLAYICILAR", "parentId": "6a26d4fcd01723cd75a4fcb4", "path": "10.18.75", "level": 2, "sortOrder": 0, "isActive": true, "erpId": 75},
  {"_id": "6a8fd25892da5f9d69e43233", "name": "GÜÇ KAYNA�\udc9eI", "parentId": "6a47b8e507f6d356d05bee21", "path": "511", "level": 0, "sortOrder": 0, "isActive": true, "erpId": 511},
  {"_id": "6a8fd25892da5f9d69e4ff01", "name": "AC/DC DÖNÜŞTÜRÜCÜLER", "parentId": "6a8fd25892da5f9d69e43233", "path": "511.512", "level": 1, "sortOrder": 0, "isActive": true, "erpId": 512},
  {"_id": "6a8fd25892da5f9d69e4ff02", "name": null, "path": "511.513", "level": 1, "isActive": true, "erpId": 513}
]
```

`tests/ornekler/urunler_s1.json`:
```json
{"data": [
  {"_id": "6accc40e71b553f54c02f4c6", "sku": "8301033800019", "__v": 0,
   "attributes": {"manufacturerCode": "0010035195", "vatRate": 20, "weight": 0, "maxPrice": {"amount": 0, "currency": "EUR"}},
   "categoryId": {"_id": "6a26d4fdd01723cd75a5004d", "name": "KR C4", "path": "12.41.243"},
   "createdAt": "2026-10-12T11:27:10.577Z", "descriptionSections": [],
   "images": ["/api/uploads/admin-uploads/ee278328-79d2-45db-bb15-99d3f9b44f5e.webp"],
   "locked": false, "minOrderQuantity": 1, "name": "KUKA KRC5 KR 140 R3200-2 PA",
   "price": {"amount": 0, "currency": "EUR"}, "source": "erp", "status": "active", "stock": 0,
   "techSpecs": [], "updatedAt": "2026-10-12T17:41:23.369Z"},
  {"_id": "6acc926771b553f54c00916f", "sku": "8102030100019", "__v": 0,
   "attributes": {"manufacturerCode": "3UG4512-1BR20", "vatRate": 20, "weight": 0, "maxPrice": {"amount": 0, "currency": "EUR"}},
   "categoryId": {"_id": "6a26d4fcd01723cd75a4fcbd", "name": "ROLELER/ZAMANLAYICILAR", "path": "10.18.75"},
   "createdAt": "2026-10-12T07:55:19.460Z", "descriptionSections": [], "images": [],
   "locked": false, "minOrderQuantity": 1, "name": "SIEMENS SIRIUS İZLEME RÖLESİ",
   "price": {"amount": 0, "currency": "EUR"}, "source": "erp", "status": "active", "stock": 1,
   "techSpecs": [], "updatedAt": "2026-10-12T17:40:02.577Z"}
], "total": 3, "page": 1, "limit": 2, "totalPages": 2}
```

`tests/ornekler/urunler_s2.json` (kaynak fiyatı > 0 ve adı bozuk kodlamalı ürün):
```json
{"data": [
  {"_id": "6acc926771b553f54c00aa01", "sku": "8205010100007", "__v": 0,
   "attributes": {"manufacturerCode": "LRS-350-24", "vatRate": 20, "weight": 0},
   "categoryId": {"_id": "6a8fd25892da5f9d69e4ff01", "name": "AC/DC DÖNÜŞTÜRÜCÜLER", "path": "511.512"},
   "createdAt": "2026-10-12T07:55:19.460Z", "descriptionSections": [], "images": [],
   "locked": false, "minOrderQuantity": 1, "name": "MEAN WELL 24V GÜÇ KAYNA�\udc9eI",
   "price": {"amount": 125.5, "currency": "EUR"}, "source": "erp", "status": "active", "stock": 4,
   "techSpecs": [], "updatedAt": "2026-10-12T17:40:05.100Z"}
], "total": 3, "page": 2, "limit": 2, "totalPages": 2}
```

`tests/ornekler/urunler_bozuk.json` (3 bozuk + 1 geçerli kayıt, total 4 → K1'e göre tam tur):
```json
{"data": [
  {"sku": "B0001", "name": "Kategorisi null", "attributes": {"vatRate": 20},
   "categoryId": null, "images": [], "price": {"amount": 0, "currency": "EUR"}, "stock": 1},
  {"sku": "B0002", "name": "Fiyat alanı yok", "attributes": {"vatRate": 20},
   "categoryId": {"_id": "6a26d4fcd01723cd75a4fcbd", "name": "ROLELER/ZAMANLAYICILAR", "path": "10.18.75"},
   "images": [], "stock": 1},
  {"sku": "", "name": "SKU boş", "attributes": {"vatRate": 20},
   "categoryId": {"_id": "6a26d4fcd01723cd75a4fcbd", "name": "ROLELER/ZAMANLAYICILAR", "path": "10.18.75"},
   "images": [], "price": {"amount": 0, "currency": "EUR"}, "stock": 1},
  {"sku": "8102030100019", "name": "SIEMENS SIRIUS İZLEME RÖLESİ", "attributes": {"manufacturerCode": "3UG4512-1BR20", "vatRate": 20},
   "categoryId": {"_id": "6a26d4fcd01723cd75a4fcbd", "name": "ROLELER/ZAMANLAYICILAR", "path": "10.18.75"},
   "images": [], "price": {"amount": 0, "currency": "EUR"}, "stock": 1, "updatedAt": "2026-10-12T17:40:02.577Z"}
], "total": 4, "page": 1, "limit": 20, "totalPages": 1}
```

- [ ] **Step 2: Kaynak istemcisi için başarısız testleri yaz**

`tests/test_kaynak.py`:
```python
import json
from pathlib import Path

import httpx
import pytest

from app.esitleme.kaynak import KaynakHatasi, KaynakIstemci

ORNEK = Path(__file__).parent / "ornekler"
TABAN = "https://kaynak.test"


def yukle(ad: str) -> bytes:
    return (ORNEK / ad).read_bytes()


def istemci(isleyici, uykular: list[float]) -> KaynakIstemci:
    http = httpx.Client(transport=httpx.MockTransport(isleyici))
    return KaynakIstemci(http, TABAN + "/", bekleme=1.0, uyku=uykular.append)


def test_kategoriler_ve_bekleme():
    uykular: list[float] = []
    yollar = []

    def isleyici(istek):
        yollar.append(istek.url.path)
        return httpx.Response(200, content=yukle("kategoriler.json"))

    k = istemci(isleyici, uykular).kategoriler()
    assert yollar == ["/api/public/categories"]
    assert len(k) == 9 and k[0]["name"] == "Endüstriyel Robotlar"
    assert uykular == [1.0]          # her çağrıdan önce `bekleme`


def test_urun_sayfasi_parametreler():
    uykular: list[float] = []
    gorulen = []

    def isleyici(istek):
        gorulen.append(dict(istek.url.params))
        return httpx.Response(200, content=yukle("urunler_s1.json"))

    veri, toplam = istemci(isleyici, uykular).urun_sayfasi(1)
    assert gorulen == [{"page": "1", "limit": "20"}]
    assert toplam == 3 and [u["sku"] for u in veri] == ["8301033800019", "8102030100019"]


def test_gecici_hata_sonra_basari():
    uykular: list[float] = []
    sayac = {"n": 0}

    def isleyici(istek):
        sayac["n"] += 1
        if sayac["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, content=yukle("urunler_s2.json"))

    veri, toplam = istemci(isleyici, uykular).urun_sayfasi(2)
    assert sayac["n"] == 3 and toplam == 3 and len(veri) == 1
    assert uykular == [1.0, 2.0, 1.0, 4.0, 1.0]


def test_uc_denemeden_sonra_kaynak_hatasi():
    uykular: list[float] = []
    sayac = {"n": 0}

    def isleyici(istek):
        sayac["n"] += 1
        raise httpx.ConnectTimeout("zaman asimi", request=istek)

    with pytest.raises(KaynakHatasi):
        istemci(isleyici, uykular).urun_sayfasi(1)
    assert sayac["n"] == 3                       # ilk istek + 2 yeniden deneme
    assert uykular == [1.0, 2.0, 1.0, 4.0, 1.0]


@pytest.mark.parametrize("govde", [
    b"<html>bakim</html>",
    json.dumps({"data": "yok", "total": 3}).encode(),
    json.dumps({"data": [], "total": "3"}).encode(),
])
def test_bicimsiz_yanit_hata_sayilir(govde):
    uykular: list[float] = []
    with pytest.raises(KaynakHatasi):
        istemci(lambda istek: httpx.Response(200, content=govde), uykular).urun_sayfasi(1)
```

- [ ] **Step 3: Çalıştır, başarısız olduğunu gör**

Run: `bash dagitim/test-vm.sh tests/test_kaynak.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.esitleme.kaynak'`

- [ ] **Step 4: Kaynak istemcisini uygula**

`app/esitleme/kaynak.py`:
```python
"""ceylanrobot.com public API istemcisi (salt okuma, yavaş ve yeniden denemeli)."""
import time
from collections.abc import Callable
from typing import Any

import httpx


class KaynakHatasi(Exception):
    """Bir uç nokta, bütün yeniden denemelerden sonra da alınamadı."""


class KaynakIstemci:
    YENIDEN_DENEME_BEKLEMELERI = (2.0, 4.0)   # en fazla 3 deneme: ilk istek + 2 yeniden deneme
    ZAMAN_ASIMI = 30.0

    def __init__(self, http: httpx.Client, taban: str, bekleme: float = 1.0,
                 uyku: Callable[[float], None] = time.sleep):
        self.http = http
        self.taban = taban.rstrip("/")
        self.bekleme = bekleme
        self.uyku = uyku

    def _getir(self, yol: str, params: dict[str, int] | None,
               dogrula: Callable[[Any], None]) -> Any:
        son_hata: Exception | None = None
        for deneme in range(len(self.YENIDEN_DENEME_BEKLEMELERI) + 1):
            if deneme > 0:
                self.uyku(self.YENIDEN_DENEME_BEKLEMELERI[deneme - 1])
            self.uyku(self.bekleme)
            try:
                yanit = self.http.get(self.taban + yol, params=params, timeout=self.ZAMAN_ASIMI)
                yanit.raise_for_status()
                veri = yanit.json()
                dogrula(veri)
                return veri
            except (httpx.HTTPError, ValueError) as e:
                son_hata = e
        raise KaynakHatasi(f"{yol} {params or ''}: {son_hata!r}") from son_hata

    @staticmethod
    def _liste_mi(veri: Any) -> None:
        if not isinstance(veri, list):
            raise ValueError("kategori yanıtı liste değil")

    @staticmethod
    def _sayfa_mi(veri: Any) -> None:
        if not isinstance(veri, dict) or not isinstance(veri.get("data"), list):
            raise ValueError("ürün yanıtında 'data' listesi yok")
        toplam = veri.get("total")
        if not isinstance(toplam, int) or isinstance(toplam, bool) or toplam < 0:
            raise ValueError("ürün yanıtında geçerli 'total' yok")

    def kategoriler(self) -> list[dict]:
        return self._getir("/api/public/categories", None, self._liste_mi)

    def urun_sayfasi(self, sayfa: int, limit: int = 20) -> tuple[list[dict], int]:
        veri = self._getir("/api/public/products", {"page": sayfa, "limit": limit}, self._sayfa_mi)
        return veri["data"], veri["total"]
```

- [ ] **Step 5: Çalıştır, geçtiğini gör**

Run: `bash dagitim/test-vm.sh tests/test_kaynak.py -q`
Expected: PASS — `7 passed`

- [ ] **Step 6: Eşitleme turu için başarısız testleri yaz**

`tests/test_esitleme.py`:
```python
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.esitleme.esitle import esitle, son_basarili_esitleme, son_esitleme
from app.esitleme.kaynak import KaynakIstemci
from tests.conftest import urun_ekle

ORNEK = Path(__file__).parent / "ornekler"
TABAN = "https://www.ceylanrobot.com"
ZAMAN = datetime(2026, 10, 13, 2, 30, tzinfo=UTC)


def yukle(ad: str) -> bytes:
    return (ORNEK / ad).read_bytes()


def sayfa_govdesi(ad: str, total: int | None = None) -> bytes:
    if total is None:
        return yukle(ad)
    veri = json.loads(yukle(ad))
    veri["total"] = total
    return json.dumps(veri).encode()


def kaynak(sayfalar: dict[int, bytes | int], uykular: list[float] | None = None,
           kategori: bytes | None = None) -> KaynakIstemci:
    """sayfalar: sayfa no -> gövde (200) ya da HTTP durum kodu. Listede olmayan sayfa boş döner."""
    def isleyici(istek: httpx.Request) -> httpx.Response:
        if istek.url.path == "/api/public/categories":
            return httpx.Response(200, content=kategori or yukle("kategoriler.json"))
        sayfa = int(istek.url.params["page"])
        cevap = sayfalar.get(sayfa)
        if cevap is None:
            return httpx.Response(200, json={"data": [], "total": 3})
        if isinstance(cevap, int):
            return httpx.Response(cevap)
        return httpx.Response(200, content=cevap)

    http = httpx.Client(transport=httpx.MockTransport(isleyici))
    return KaynakIstemci(http, TABAN, bekleme=1.0, uyku=(uykular if uykular is not None else []).append)


def iki_sayfa() -> dict[int, bytes | int]:
    return {1: yukle("urunler_s1.json"), 2: yukle("urunler_s2.json")}


def urun(con, sku):
    return con.execute("SELECT * FROM urun WHERE sku=?", (sku,)).fetchone()


def test_tam_tur(con, bantlar):
    eski = urun_ekle(con, sku="ESKI1", ad="Kaynakta artık yok")
    s = esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    assert (s.durum, s.api_toplam, s.cekilen, s.eklenen, s.guncellenen, s.pasiflenen, s.hata, s.bozuk) == (
        "tam", 3, 3, 3, 0, 1, None, 0)
    aktif = con.execute("SELECT COUNT(*) FROM urun WHERE aktif=1").fetchone()[0]
    assert aktif == s.api_toplam == 3
    assert con.execute("SELECT aktif FROM urun WHERE id=?", (eski,)).fetchone()[0] == 0
    g = son_esitleme(con)
    assert (g["durum"], g["api_toplam"], g["cekilen"], g["pasiflenen"]) == ("tam", 3, 3, 1)
    assert g["bitis"] == ZAMAN.isoformat()


def test_urun_esleme_ve_kategori(con, bantlar):
    esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    siemens = urun(con, "8102030100019")
    assert siemens["ad"] == "SIEMENS SIRIUS İZLEME RÖLESİ"
    assert siemens["uretici_kodu"] == "3UG4512-1BR20"
    assert siemens["kdv_orani"] == "20" and siemens["stok"] == 1
    assert siemens["gorsel_url"] is None
    assert siemens["kok_kategori_ad"] == "Elektrik ve Elektronik"
    assert siemens["kaynak_guncelleme"] == "2026-10-12T17:40:02.577Z"
    kat = con.execute("SELECT * FROM kategori WHERE id=?", (siemens["kategori_id"],)).fetchone()
    assert (kat["ad"], kat["yol"], kat["seviye"], kat["erp_id"]) == ("ROLELER/ZAMANLAYICILAR", "10.18.75", 2, 75)
    assert kat["ust_kaynak_id"] == "6a26d4fcd01723cd75a4fcb4"
    # adı null olan kategori kaydı atlanır
    assert con.execute("SELECT COUNT(*) FROM kategori").fetchone()[0] == 8


def test_temsili_fiyat_ve_teklif_zorunlu(con, bantlar):
    esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    kuka = urun(con, "8301033800019")
    assert kuka["kok_kategori_ad"] == "Endüstriyel Robotlar"
    assert kuka["teklif_zorunlu"] == 1
    assert kuka["fiyat_temsili"] == 1 and kuka["kaynak_fiyat_eur"] == "0.00"
    assert kuka["temsili_fiyat_eur"] == "15515.00"
    assert kuka["gorsel_url"] == TABAN + "/api/uploads/admin-uploads/ee278328-79d2-45db-bb15-99d3f9b44f5e.webp"
    siemens = urun(con, "8102030100019")
    assert siemens["temsili_fiyat_eur"] == "511.00" and siemens["teklif_zorunlu"] == 0
    # kaynak fiyatı > 0 olan ürün: kaynak fiyat gösterilir, temsili rozet yok
    meanwell = urun(con, "8205010100007")
    assert meanwell["kaynak_fiyat_eur"] == "125.50"
    assert meanwell["temsili_fiyat_eur"] == "125.50" and meanwell["fiyat_temsili"] == 0


def test_ikinci_tur_gunceller_fiyat_degismez(con, bantlar):
    esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    ilk = urun(con, "8102030100019")["temsili_fiyat_eur"]
    s = esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    assert (s.durum, s.eklenen, s.guncellenen, s.pasiflenen) == ("tam", 0, 3, 0)
    assert urun(con, "8102030100019")["temsili_fiyat_eur"] == ilk
    assert con.execute("SELECT COUNT(*) FROM urun").fetchone()[0] == 3


def test_eksik_tur_total_degisirse_pasifleme_yok(con, bantlar):
    eski = urun_ekle(con, sku="ESKI1", ad="Kaynakta artık yok")
    # sayfalama sırasında kaynağa bir kayıt eklendi: 2. ve 3. sayfa total=4 bildiriyor
    sayfalar = {1: yukle("urunler_s1.json"), 2: sayfa_govdesi("urunler_s2.json", total=4),
                3: json.dumps({"data": [], "total": 4}).encode()}
    s = esitle(con, kaynak(sayfalar), bantlar, lambda: ZAMAN)
    assert s.durum == "eksik" and s.api_toplam == 4 and s.pasiflenen == 0
    assert s.eklenen == 3
    assert con.execute("SELECT aktif FROM urun WHERE id=?", (eski,)).fetchone()[0] == 1
    assert son_esitleme(con)["durum"] == "eksik"
    assert son_basarili_esitleme(con) is None


def test_eksik_tur_sayfa_alinamazsa(con, bantlar):
    eski = urun_ekle(con, sku="ESKI1", ad="Kaynakta artık yok")
    uykular: list[float] = []
    sayfalar = {1: yukle("urunler_s1.json"), 2: 503}
    s = esitle(con, kaynak(sayfalar, uykular), bantlar, lambda: ZAMAN)
    assert s.durum == "eksik" and s.pasiflenen == 0 and s.cekilen == 2
    assert s.hata == "alinamayan_sayfa: 2"
    assert con.execute("SELECT aktif FROM urun WHERE id=?", (eski,)).fetchone()[0] == 1
    assert urun(con, "8301033800019") is not None


def test_ag_hatasi_hata_ve_veri_degismez(con, bantlar):
    eski = urun_ekle(con, sku="ESKI1", ad="Eski ürün", fiyat="42.00")
    uykular: list[float] = []
    cagrilar = {"n": 0}

    def ag_yok(istek):
        cagrilar["n"] += 1
        raise httpx.ConnectError("ag yok", request=istek)

    http = httpx.Client(transport=httpx.MockTransport(ag_yok))
    s = esitle(con, KaynakIstemci(http, TABAN, uyku=uykular.append), bantlar, lambda: ZAMAN)
    assert s.durum == "hata" and "KaynakHatasi" in s.hata
    assert cagrilar["n"] == 3                     # ilk istek + 2 yeniden deneme
    assert uykular == [1.0, 2.0, 1.0, 4.0, 1.0]
    satir = con.execute("SELECT aktif, temsili_fiyat_eur FROM urun WHERE id=?", (eski,)).fetchone()
    assert tuple(satir) == (1, "42.00")
    assert con.execute("SELECT COUNT(*) FROM urun").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM kategori").fetchone()[0] == 0
    assert son_esitleme(con)["durum"] == "hata"


def test_bozuk_kayit_atlanir(con, bantlar):
    eski = urun_ekle(con, sku="ESKI1", ad="Kaynakta artık yok")
    s = esitle(con, kaynak({1: yukle("urunler_bozuk.json")}), bantlar, lambda: ZAMAN)
    # K1: 1 geçerli + 3 bozuk == total 4 -> tur tam; bozuklar ayrı sayılır
    assert (s.durum, s.cekilen, s.eklenen, s.bozuk, s.hata) == ("tam", 1, 1, 3, None)
    assert son_esitleme(con)["bozuk"] == 3
    assert con.execute("SELECT sku FROM urun WHERE aktif=1").fetchall()[0][0] == "8102030100019"
    assert con.execute("SELECT aktif FROM urun WHERE id=?", (eski,)).fetchone()[0] == 0


def test_bozuk_karakter_temizlenir(con, bantlar):
    esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    kok = con.execute("SELECT ad FROM kategori WHERE yol='511'").fetchone()[0]
    assert kok == "GÜÇ KAYNA�I"
    meanwell = urun(con, "8205010100007")
    assert meanwell["ad"] == "MEAN WELL 24V GÜÇ KAYNA�I"
    assert meanwell["kok_kategori_ad"] == "GÜÇ KAYNA�I"
    meanwell["ad"].encode("utf-8")


def test_arama_indeksi_yeniden_kurulur(con, bantlar):
    eski = urun_ekle(con, sku="ESKI1", ad="Eski Röle")
    esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    bul = lambda q: [r[0] for r in con.execute(
        "SELECT urun_id FROM urun_ara WHERE urun_ara MATCH ?", (q,))]
    siemens_id = urun(con, "8102030100019")["id"]
    assert bul("izleme") == [siemens_id]
    assert bul("3ug4512*") == [siemens_id]
    assert bul("eski") == []                              # pasif ürün indekste yok
    assert bul("rol*") == [siemens_id]
    assert con.execute("SELECT COUNT(*) FROM urun_ara").fetchone()[0] == 3


def test_son_basarili_esitleme(con, bantlar):
    assert son_basarili_esitleme(con) is None
    assert son_esitleme(con) is None
    esitle(con, kaynak(iki_sayfa()), bantlar, lambda: ZAMAN)
    assert son_basarili_esitleme(con) == ZAMAN
    sonra = datetime(2026, 10, 14, 2, 30, tzinfo=UTC)
    http = httpx.Client(transport=httpx.MockTransport(lambda istek: httpx.Response(500)))
    esitle(con, KaynakIstemci(http, TABAN, uyku=lambda s: None), bantlar, lambda: sonra)
    assert son_esitleme(con)["durum"] == "hata"
    assert son_basarili_esitleme(con) == ZAMAN
```

- [ ] **Step 7: Çalıştır, başarısız olduğunu gör**

Run: `bash dagitim/test-vm.sh tests/test_esitleme.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.esitleme.esitle'`

- [ ] **Step 8: Eşitleme turunu uygula**

`app/esitleme/esitle.py`:
```python
"""Katalog eşitleme turu: kaynak API -> esitleme_ara -> urun/kategori (tam ya da eksik)."""
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from app.esitleme.kaynak import KaynakHatasi, KaynakIstemci
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
    return Decimal(str(x))


def _oran_metni(x: Decimal) -> str:
    if x == x.to_integral_value():
        return str(int(x))
    return str(x.normalize())


def _gorsel_url(kayit: dict, taban: str) -> str | None:
    gorseller = kayit.get("images")
    if not isinstance(gorseller, list) or not gorseller:
        return None
    yol = gorseller[0]
    if not isinstance(yol, str) or not yol.strip():
        return None
    yol = yol.strip()
    if yol.startswith(("http://", "https://")):
        return yol
    return taban + (yol if yol.startswith("/") else "/" + yol)


def _urun_esle(kayit: Any, taban: str) -> dict | None:
    """API kaydını ara tablo biçimine çevirir; zorunlu alan eksik/bozuksa None."""
    if not isinstance(kayit, dict):
        return None
    sku = metin_temizle(kayit["sku"]) if isinstance(kayit.get("sku"), str) else None
    ad = metin_temizle(kayit["name"]) if isinstance(kayit.get("name"), str) else None
    kategori = kayit.get("categoryId")
    fiyat = kayit.get("price")
    if not sku or not ad:
        return None
    if not isinstance(kategori, dict) or not isinstance(kategori.get("_id"), str):
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
    uretici = nitelik.get("manufacturerCode")
    guncelleme = kayit.get("updatedAt")
    return {
        "sku": sku,
        "ad": ad,
        "uretici_kodu": metin_temizle(uretici) if isinstance(uretici, str) and uretici.strip() else None,
        "kdv_orani": _oran_metni(kdv),
        "stok": max(stok, 0),
        "gorsel_url": _gorsel_url(kayit, taban),
        "kaynak_fiyat_eur": str(yuvarla(kaynak_fiyat)),
        "kategori_kaynak_id": kategori["_id"],
        "kategori_yol": kategori.get("path") if isinstance(kategori.get("path"), str) else "",
        "kaynak_guncelleme": guncelleme if isinstance(guncelleme, str) else None,
    }


def _kategori_esle(k: Any) -> dict | None:
    if not isinstance(k, dict):
        return None
    if not all(isinstance(k.get(a), str) and k.get(a) for a in ("_id", "name", "path")):
        return None
    ad = metin_temizle(k["name"])
    if not ad:
        return None
    seviye = k.get("level")
    erp = k.get("erpId")
    return {
        "kaynak_id": k["_id"],
        "erp_id": erp if isinstance(erp, int) and not isinstance(erp, bool) else None,
        "ad": ad,
        "ust_kaynak_id": k.get("parentId") if isinstance(k.get("parentId"), str) else None,
        "yol": k["path"],
        "seviye": seviye if isinstance(seviye, int) and not isinstance(seviye, bool) else k["path"].count("."),
        "aktif": 0 if k.get("isActive") is False else 1,
    }


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
        if kaynak_fiyat > 0:
            net, temsili = kaynak_fiyat, 0
        else:
            net, temsili = temsili_fiyat_eur(u["sku"], kok_ad, bantlar), 1
        con.execute(
            "INSERT INTO urun (sku, ad, uretici_kodu, kategori_id, kok_kategori_ad, kdv_orani, stok,"
            " gorsel_url, kaynak_fiyat_eur, temsili_fiyat_eur, fiyat_temsili, teklif_zorunlu, aktif,"
            " kaynak_guncelleme, olusturma)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)"
            " ON CONFLICT(sku) DO UPDATE SET ad=excluded.ad, uretici_kodu=excluded.uretici_kodu,"
            " kategori_id=excluded.kategori_id, kok_kategori_ad=excluded.kok_kategori_ad,"
            " kdv_orani=excluded.kdv_orani, stok=excluded.stok, gorsel_url=excluded.gorsel_url,"
            " kaynak_fiyat_eur=excluded.kaynak_fiyat_eur, temsili_fiyat_eur=excluded.temsili_fiyat_eur,"
            " fiyat_temsili=excluded.fiyat_temsili, teklif_zorunlu=excluded.teklif_zorunlu, aktif=1,"
            " kaynak_guncelleme=excluded.kaynak_guncelleme",
            (
                u["sku"], u["ad"], u["uretici_kodu"], kategori_id.get(u["kategori_kaynak_id"]),
                kok_ad, u["kdv_orani"], u["stok"], u["gorsel_url"], u["kaynak_fiyat_eur"],
                str(net), temsili, int(teklif_zorunlu_mu(kok_ad, net, bantlar)),
                u["kaynak_guncelleme"], zaman,
            ),
        )
        if u["sku"] in mevcut:
            guncellenen += 1
        else:
            eklenen += 1
    return eklenen, guncellenen


# ---------- tur ----------

def esitle(con: sqlite3.Connection, kaynak: KaynakIstemci, bantlar: Bantlar,
           simdi: Callable[[], datetime]) -> TurSonucu:
    with con:
        gid = con.execute(
            "INSERT INTO esitleme_gunlugu (basla, durum) VALUES (?, 'calisiyor')",
            (simdi().isoformat(),),
        ).lastrowid

    api_toplam: int | None = None
    cekilen = bozuk = 0
    try:
        kategoriler = [k for k in map(_kategori_esle, kaynak.kategoriler()) if k is not None]
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
            for kayit in veri:
                u = _urun_esle(kayit, kaynak.taban)
                if u is None:
                    bozuk += 1
                    continue
                cekilen += 1
                satirlar.append((u["sku"], json.dumps(u, ensure_ascii=False)))
            with con:
                con.executemany(
                    "INSERT OR REPLACE INTO esitleme_ara (sku, veri) VALUES (?, ?)", satirlar
                )
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

        hata_notu = ("alinamayan_sayfa: " + ",".join(map(str, alinamayan))) if alinamayan else None
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
```

Tasarım notları: (a) Kategori upsert'i, ürün upsert'i, pasifleme ve FTS yeniden kurulumu **tek** `with con:` bloğundadır; bu bloktan önce oluşan her hata `hata` turudur ve `urun`/`kategori` tablolarına hiç yazılmamış olur. (b) `esitleme_ara` sayfa sayfa commit edilir (ara tablo; bellek 400 MB sınırı için kayıtlar Python'da biriktirilmez). (c) `tam` koşulu (K1): alınamayan sayfa yok **ve** `COUNT(esitleme_ara) + bozuk == ilk sayfanın total'i == son sayfanın total'i`.

- [ ] **Step 9: Çalıştır, geçtiğini gör**

Run: `bash dagitim/test-vm.sh tests/test_esitleme.py -q`
Expected: PASS — `11 passed`

- [ ] **Step 10: Kontrol testi — pasifleme koşulu bozulunca eksik tur testi düşüyor mu**

Geçici olarak `esitle.py`'deki `if tam:` (pasifleme bloğu) satırını `if True:` yap.
Run: `bash dagitim/test-vm.sh tests/test_esitleme.py -q -k eksik`
Expected: FAIL — `test_eksik_tur_total_degisirse_pasifleme_yok` ve `test_eksik_tur_sayfa_alinamazsa` (`pasiflenen == 0` / `aktif == 1` beklentisi). Satırı `if tam:` olarak geri al.

- [ ] **Step 11: Bütün testleri çalıştır**

Run: `bash dagitim/test-vm.sh -q`
Expected: PASS — Görev 0–5 testleri için `94 passed` (ortam 2 + iskelet 16 + doğrulama 16 + kur 10 + kurallar 32 + kaynak 7 + eşitleme 11); başka görevler önce birleştiyse sayı onların testleri kadar fazladır, `failed` olmamalı

- [ ] **Step 12: Commit**

```bash
git add tests/ornekler/kategoriler.json tests/ornekler/urunler_s1.json tests/ornekler/urunler_s2.json tests/ornekler/urunler_bozuk.json app/esitleme/kaynak.py app/esitleme/esitle.py tests/test_kaynak.py tests/test_esitleme.py
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m "feat: katalog esitleme - yeniden denemeli kaynak istemcisi, tam/eksik tur, FTS yeniden kurulum" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Entegrasyon durumu

- K1: tam = `benzersiz + bozuk == total` (ilk ve son sayfa); `esitleme_gunlugu.bozuk` kolonu 001'de; `TurSonucu.bozuk`; kategori/1. sayfa hatası → `hata`, sonraki sayfa → `eksik` + `alinamayan_sayfa: N`; kategori upsert son transaction'da, tam turda kaybolan kategori `aktif=0` (Görev 1, 5).
- K2: `YENIDEN_DENEME_BEKLEMELERI = (2.0, 4.0)`, en fazla 3 çağrı; testler buna göre (Görev 5).
- K3: `birim_fiyat_gosterimi` yeni kural; bireysel/kurumsal yurt dışı teslim ve kur yokken dört durum testi (Görev 4).
- K4: `KARGO` + teslimat≠TR → kargo 0 (Görev 4, `test_tablo_tr_bireysel_yurtdisi_teslim` dolaylı).
- K5: `KurYok(ValueError)`; `sepet_hesapla` `KurYok("kur_yok")` yükseltir (Görev 4).
- K6: `app/katalog/indeks.py` (`indeks_metni`, `indeksi_yeniden_kur`) Görev 1'de; `urun_ekle` yeni parametreler + tek FTS satırı (`urun_id` int); `esitle` indeksi bununla kurar.
- K7: `tests/__init__.py` (Görev 0); yardımcılar `from tests.conftest import ...`.
- K8: `baglan` `check_same_thread=False` + thread testi (Görev 1).
- K16: geçerli VKN `1234567890`, `4728136592`; geçersiz `4728136593`; TCKN `10000000146` (Görev 2).
- K19: `.gitattributes` (`* text=auto eol=lf`) Görev 1'e taşındı.
- Görev 0–5 kodu ve testleri geçici klasörde Python 3.11 + httpx 0.27 ile çalıştırıldı: VM'e özgü `test_ortam` dışında 92 test geçti; pasifleme ve teklif eşiği kontrol mutasyonları testleri düşürdü.

---

### Görev 5A: Örnek ürün durumu seed'i (`app/esitleme/ornek.py`)

Spec §5.1: kaynakta `durum_kodu` yok; gösterim için 15 üründe örnek değer atanır ve "örnek" diye işaretlenir. Eşitleme `durum_kodu`/`durum_ornek` kolonlarına dokunmaz; bu görev atamayı idempotent yapar ve `betikler/esitle.py` (Görev 17) her başarılı/eksik turdan sonra çağırır.

**Files:**
- Create: `app/esitleme/ornek.py`
- Test: `tests/test_ornek_durum.py`

**Interfaces:**
- Consumes: `tests.conftest.urun_ekle` (Görev 1), `urun` tablosu (`durum_kodu`, `durum_ornek`, `aktif`, `teklif_zorunlu`, `sku`).
- Produces: `ORNEK_DURUMLAR = ("yeni", "ikinci_el_test_edildi", "ikinci_el_oldugu_gibi")`, `def ornek_durumlari_ata(con, adet: int = 15) -> int` — zaten `durum_ornek=1` ürün varsa 0 döner, yoksa aktif ve teklif zorunlu olmayan ürünlerden SKU sırasına göre ilk `adet` tanesine durumları sırayla atar ve atanan sayıyı döner. Commit yapmaz.

- [ ] **Step 1: Failing test yaz**

`tests/test_ornek_durum.py`:
```python
from app.esitleme.ornek import ORNEK_DURUMLAR, ornek_durumlari_ata
from tests.conftest import urun_ekle


def test_ilk_cagri_atar_ikinci_cagri_dokunmaz(con):
    for i in range(20):
        urun_ekle(con, sku=f"S{i:03d}", ad=f"Ürün {i}")
    urun_ekle(con, sku="R001", ad="Robot", kok="Endüstriyel Robotlar", teklif=True)
    urun_ekle(con, sku="P001", ad="Pasif", aktif=False)

    assert ornek_durumlari_ata(con, adet=15) == 15
    satirlar = con.execute(
        "SELECT sku, durum_kodu FROM urun WHERE durum_ornek = 1 ORDER BY sku").fetchall()
    assert [s["sku"] for s in satirlar] == [f"S{i:03d}" for i in range(15)]
    assert [s["durum_kodu"] for s in satirlar[:3]] == list(ORNEK_DURUMLAR)
    # teklif zorunlu ve pasif ürünlere atanmaz
    assert con.execute("SELECT COUNT(*) FROM urun WHERE sku IN ('R001','P001') AND durum_ornek = 1").fetchone()[0] == 0

    assert ornek_durumlari_ata(con, adet=15) == 0
    assert con.execute("SELECT COUNT(*) FROM urun WHERE durum_ornek = 1").fetchone()[0] == 15


def test_bos_katalog(con):
    assert ornek_durumlari_ata(con) == 0
```

- [ ] **Step 2: Çalıştır, düştüğünü gör**

Run: `bash dagitim/test-vm.sh tests/test_ornek_durum.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.esitleme.ornek'`

- [ ] **Step 3: Implementasyon**

`app/esitleme/ornek.py`:
```python
"""Gösterim amaçlı örnek ürün durumu (spec §5.1). Kaynakta durum bilgisi yok; atananlar durum_ornek=1 ile işaretlenir."""
from __future__ import annotations

import sqlite3

ORNEK_DURUMLAR = ("yeni", "ikinci_el_test_edildi", "ikinci_el_oldugu_gibi")


def ornek_durumlari_ata(con: sqlite3.Connection, adet: int = 15) -> int:
    if con.execute("SELECT 1 FROM urun WHERE durum_ornek = 1 LIMIT 1").fetchone():
        return 0
    idler = [r[0] for r in con.execute(
        "SELECT id FROM urun WHERE aktif = 1 AND teklif_zorunlu = 0 ORDER BY sku LIMIT ?", (adet,))]
    for sira, urun_id in enumerate(idler):
        con.execute("UPDATE urun SET durum_kodu = ?, durum_ornek = 1 WHERE id = ?",
                    (ORNEK_DURUMLAR[sira % len(ORNEK_DURUMLAR)], urun_id))
    return len(idler)
```

- [ ] **Step 4: Çalıştır, geçtiğini gör**

Run: `bash dagitim/test-vm.sh tests/test_ornek_durum.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/esitleme/ornek.py tests/test_ornek_durum.py
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m "feat: ornek urun durumu seed'i

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Görev 6: Katalog okuma katmanı (`app/katalog/depo.py`)

**Files:**
- Create (Görev 1 oluşturmadıysa): `app/katalog/__init__.py` (boş)
- Create: `app/katalog/depo.py`
- Test: `tests/test_katalog_depo.py`

**Interfaces:**
- Consumes:
  - `app.metin.normalize(s: str) -> str` (Görev 2)
  - Şema: `kategori`, `urun`, `urun_ara` (FTS5: `metin`, `urun_id UNINDEXED`) (Görev 1)
  - `app.katalog.indeks.indeksi_yeniden_kur(con) -> None` (K6, Görev 1)
  - `tests/conftest.py`: fixture `con`; yardımcılar `urun_ekle(con, *, sku, ad, kok, fiyat, teklif, stok, aktif, kategori_id, kdv, simdi, uretici_kodu=None, gorsel_url=None, tedarik_suresi_gun=None) -> int` (yeni ürünün `urun_ara` satırını da yazar, `urun_id` int), `kategori_ekle(con, *, kaynak_id, ad, yol, seviye, ust_kaynak_id=None) -> int` (Görev 1, K6/K7)
- Produces (Görev 11–14 web rotaları kullanır):
  - `Kategori(id, ad, yol, seviye, ust_id)`, `KategoriDugum(kategori, cocuklar, urun_sayisi)`, `Urun(...)`, `ListeSorgusu(...)`, `ListeSonucu(urunler, toplam, sayfa, sayfa_sayisi)`
  - `kategori_agaci(con) -> list[KategoriDugum]` — kökler ve çocuklar `normalize(ad)` sırasıyla; `urun_sayisi` alt kategoriler dahil yalnız aktif ürün
  - `kategori_getir(con, kategori_id) -> Kategori | None`
  - `kategori_yolu(con, kategori_id) -> list[Kategori]` — kökten yaprağa; bulunamazsa `[]`
  - `urun_getir(con, urun_id) -> Urun | None` — pasif de döner
  - `urun_listele(con, s: ListeSorgusu) -> ListeSonucu` — yalnız aktif; `arama` None/boş/yalnız boşluk ise arama filtresi **yok sayılır**; arama dolu ama hiç kelime karakteri yoksa (`"*"`, `"\""`) sonuç boş; sayfa `1..sayfa_sayisi`'na kısılır; 0 sonuçta `sayfa=1, sayfa_sayisi=1`
  - `one_cikanlar(con, adet=8) -> list[Urun]` — önce görseli olan aktif ürünler (id sırası), eksik kalırsa görselsiz aktiflerle tamamlanır

- [ ] **Step 1: Başarısız testi yaz**

`tests/test_katalog_depo.py`:

```python
from decimal import Decimal

import pytest

from app.katalog.depo import (
    Kategori,
    ListeSonucu,
    ListeSorgusu,
    kategori_agaci,
    kategori_getir,
    kategori_yolu,
    one_cikanlar,
    urun_getir,
    urun_listele,
)
from app.katalog.indeks import indeksi_yeniden_kur
from tests.conftest import kategori_ekle, urun_ekle

# urun_ekle (K6) yeni ürün için urun_ara satırını da yazar; kısa ad:
u = urun_ekle


def idler(sonuc):
    return [x.id for x in sonuc.urunler]


@pytest.fixture
def agac(con):
    """12 Endüstriyel Robotlar > 12.41 KUKA > 12.41.243 KR C4 ; 12 > 12.410 KUKA Eski ; 10 Elektrik ve Elektronik."""
    k12 = kategori_ekle(con, kaynak_id="k12", ad="Endüstriyel Robotlar", yol="12", seviye=0)
    k41 = kategori_ekle(con, kaynak_id="k41", ad="KUKA", yol="12.41", seviye=1, ust_kaynak_id="k12")
    k243 = kategori_ekle(con, kaynak_id="k243", ad="KR C4", yol="12.41.243", seviye=2, ust_kaynak_id="k41")
    k410 = kategori_ekle(con, kaynak_id="k410", ad="KUKA Eski", yol="12.410", seviye=1, ust_kaynak_id="k12")
    k10 = kategori_ekle(con, kaynak_id="k10", ad="Elektrik ve Elektronik", yol="10", seviye=0)
    return {"k12": k12, "k41": k41, "k243": k243, "k410": k410, "k10": k10}


def test_kategori_agaci_ve_urun_sayisi(con, agac):
    u(con, sku="A1", kategori_id=agac["k243"])
    u(con, sku="A2", kategori_id=agac["k41"])
    u(con, sku="A3", kategori_id=agac["k243"], aktif=False)
    u(con, sku="A4", kategori_id=agac["k410"])
    u(con, sku="B1", kategori_id=agac["k10"])
    kokler = kategori_agaci(con)
    assert [d.kategori.ad for d in kokler] == ["Elektrik ve Elektronik", "Endüstriyel Robotlar"]
    elektrik, robot = kokler
    assert elektrik.urun_sayisi == 1 and elektrik.cocuklar == []
    assert robot.kategori.ust_id is None and robot.urun_sayisi == 3
    assert [c.kategori.ad for c in robot.cocuklar] == ["KUKA", "KUKA Eski"]
    kuka = robot.cocuklar[0]
    assert kuka.kategori.ust_id == agac["k12"] and kuka.urun_sayisi == 2
    assert kuka.cocuklar[0].kategori.ad == "KR C4" and kuka.cocuklar[0].urun_sayisi == 1


def test_kategori_getir_ve_yolu(con, agac):
    assert kategori_getir(con, agac["k41"]) == Kategori(
        id=agac["k41"], ad="KUKA", yol="12.41", seviye=1, ust_id=agac["k12"]
    )
    assert kategori_getir(con, 99999) is None
    assert [k.ad for k in kategori_yolu(con, agac["k243"])] == ["Endüstriyel Robotlar", "KUKA", "KR C4"]
    assert [k.ad for k in kategori_yolu(con, agac["k12"])] == ["Endüstriyel Robotlar"]
    assert kategori_yolu(con, 99999) == []


def test_urun_listele_kategori_alt_agaci(con, agac):
    a1 = u(con, sku="A1", ad="Robot Kol", kategori_id=agac["k243"])
    a2 = u(con, sku="A2", ad="Robot Kablo", kategori_id=agac["k41"])
    a3 = u(con, sku="A3", ad="Eski Kol", kategori_id=agac["k410"])
    u(con, sku="B1", ad="Röle", kategori_id=agac["k10"])
    u(con, sku="C1", ad="Kategorisiz")
    assert set(idler(urun_listele(con, ListeSorgusu(kategori_id=agac["k12"])))) == {a1, a2, a3}
    kuka = urun_listele(con, ListeSorgusu(kategori_id=agac["k41"]))
    assert set(idler(kuka)) == {a1, a2}          # 12.410 "12.41" önekine rağmen dahil değil
    yaprak = urun_listele(con, ListeSorgusu(kategori_id=agac["k243"]))
    assert idler(yaprak) == [a1]
    assert yaprak.urunler[0].kategori_ad == "KR C4"
    assert yaprak.urunler[0].kategori_yol == "12.41.243"
    yok = urun_listele(con, ListeSorgusu(kategori_id=99999))
    assert (yok.toplam, yok.sayfa, yok.sayfa_sayisi, yok.urunler) == (0, 1, 1, [])


def test_stokta_filtresi(con):
    a = u(con, sku="A", ad="A", stok=3)
    u(con, sku="B", ad="B", stok=0)
    assert idler(urun_listele(con, ListeSorgusu(stokta=True))) == [a]
    assert urun_listele(con, ListeSorgusu()).toplam == 2


def test_fiyat_araligi_net_eur(con):
    u(con, sku="A", ad="A", fiyat="99.99")
    b = u(con, sku="B", ad="B", fiyat="100.00")
    c = u(con, sku="C", ad="C", fiyat="250.00")
    u(con, sku="D", ad="D", fiyat="1000.00")
    s = urun_listele(con, ListeSorgusu(fiyat_min=Decimal("100"), fiyat_max=Decimal("250.00")))
    assert idler(s) == [b, c]                      # metin karşılaştırması olsaydı "1000.00" de girerdi
    assert s.urunler[0].net_fiyat_eur == Decimal("100.00")
    assert urun_listele(con, ListeSorgusu(fiyat_min=Decimal("1000.01"))).toplam == 0
    assert urun_listele(con, ListeSorgusu(fiyat_max=Decimal("99.99"))).toplam == 1


def test_siralama_uc_tur(con):
    a = u(con, sku="S1", ad="Çelik Kablo", fiyat="300.00")
    b = u(con, sku="S2", ad="Adaptör", fiyat="1200.00")
    c = u(con, sku="S3", ad="Bağlantı", fiyat="45.50")
    d = u(con, sku="S4", ad="Dişli", fiyat="300.00")
    # Türkçe sıra: Ç, C ile D arasında (NOCASE olsaydı Ç en sona düşerdi)
    assert idler(urun_listele(con, ListeSorgusu(siralama="ad"))) == [b, c, a, d]
    assert idler(urun_listele(con, ListeSorgusu(siralama="fiyat_artan"))) == [c, a, d, b]
    assert idler(urun_listele(con, ListeSorgusu(siralama="fiyat_azalan"))) == [b, a, d, c]


def test_sayfalama(con):
    ids = [u(con, sku=f"P{i:02d}", ad=f"Ürün {i:02d}") for i in range(30)]
    s1 = urun_listele(con, ListeSorgusu(sayfa=1))
    assert (s1.toplam, s1.sayfa, s1.sayfa_sayisi, len(s1.urunler)) == (30, 1, 2, 24)
    s2 = urun_listele(con, ListeSorgusu(sayfa=2))
    assert (s2.sayfa, len(s2.urunler)) == (2, 6)
    assert idler(s1) + idler(s2) == ids
    s10 = urun_listele(con, ListeSorgusu(sayfa=3, sayfa_boyu=10))
    assert (s10.sayfa_sayisi, idler(s10)) == (3, ids[20:30])


def test_sayfa_kisilir(con):
    for i in range(30):
        u(con, sku=f"P{i:02d}", ad=f"Ürün {i:02d}")
    assert urun_listele(con, ListeSorgusu(sayfa=-1)).sayfa == 1
    assert urun_listele(con, ListeSorgusu(sayfa=0)).sayfa == 1
    son = urun_listele(con, ListeSorgusu(sayfa=99999))
    assert (son.sayfa, son.sayfa_sayisi, len(son.urunler)) == (2, 2, 6)
    bos = urun_listele(con, ListeSorgusu(arama="yokboyleurun", sayfa=5))
    assert (bos.toplam, bos.sayfa, bos.sayfa_sayisi, bos.urunler) == (0, 1, 1, [])


def test_arama_turkce_harf_duyarsiz(con):
    hedef = u(con, sku="8301033800019", ad="RÖLE İzleme Modülü", uretici_kodu="KR-C4/ABX-77")
    u(con, sku="X2", ad="Kablo Kanalı")
    for sorgu in ["RÖLE", "röle", "role", "Role", "İzleme", "izleme", "IZLEME", "izle", "röle izl", "modulu"]:
        assert idler(urun_listele(con, ListeSorgusu(arama=sorgu))) == [hedef], sorgu
    for sorgu in ["8301033800019", "830103", "KR-C4", "kr-c4/abx", "abx-77"]:
        assert idler(urun_listele(con, ListeSorgusu(arama=sorgu))) == [hedef], sorgu
    assert urun_listele(con, ListeSorgusu(arama="kablo röle")).toplam == 0


def test_bos_arama(con):
    u(con, sku="A", ad="A")
    u(con, sku="B", ad="B")
    for sorgu in [None, "", "   ", "\t\n"]:
        assert urun_listele(con, ListeSorgusu(arama=sorgu)).toplam == 2, repr(sorgu)


@pytest.mark.parametrize(
    "sorgu",
    ['"', '""', "*", "***", "-", "+", "^", ":", "(", ")", "NEAR(", "AND", "OR NOT", "röle AND", 'a"b', "ad:röle"],
)
def test_arama_fts_ozel_karakterler_hata_vermez(con, sorgu):
    u(con, sku="R1", ad="Röle")
    assert isinstance(urun_listele(con, ListeSorgusu(arama=sorgu)), ListeSonucu)


def test_arama_ozel_karakterli_terimler(con):
    hedef = u(con, sku="R1", ad="Röle")
    assert idler(urun_listele(con, ListeSorgusu(arama="-röle"))) == [hedef]
    assert idler(urun_listele(con, ListeSorgusu(arama="röle*"))) == [hedef]
    assert idler(urun_listele(con, ListeSorgusu(arama='"röle"'))) == [hedef]
    assert urun_listele(con, ListeSorgusu(arama="*")).toplam == 0     # kelime yok -> boş sonuç
    assert urun_listele(con, ListeSorgusu(arama="AND")).toplam == 0   # operatör değil, düz kelime


def test_pasif_urun_listede_yok_ama_getir_doner(con):
    p = u(con, sku="P", ad="Pasif Röle", aktif=False)
    a = u(con, sku="A", ad="Aktif Röle")
    assert idler(urun_listele(con, ListeSorgusu(arama="röle"))) == [a]
    assert idler(urun_listele(con, ListeSorgusu())) == [a]
    g = urun_getir(con, p)
    assert g is not None and g.aktif is False and g.sku == "P"
    assert urun_getir(con, 99999) is None


def test_indeks_yeniden_kurulunca_arama_guncel(con):
    a = u(con, sku="A", ad="Eski Ad")
    con.execute("UPDATE urun SET ad = 'Yeni Şalter', uretici_kodu = 'QX-9' WHERE id = ?", (a,))
    assert urun_listele(con, ListeSorgusu(arama="salter")).toplam == 0     # indeks henüz eski
    indeksi_yeniden_kur(con)
    for sorgu in ["şalter", "SALTER", "qx-9"]:
        assert idler(urun_listele(con, ListeSorgusu(arama=sorgu))) == [a], sorgu
    assert urun_listele(con, ListeSorgusu(arama="eski")).toplam == 0


def test_urun_getir_alanlar(con, agac):
    uid = u(
        con, sku="K1", ad="KUKA KRC5", kok="Endüstriyel Robotlar", fiyat="20000.00", teklif=True,
        stok=0, kategori_id=agac["k243"], uretici_kodu="KRC5", gorsel_url="/img/a.jpg",
    )
    g = urun_getir(con, uid)
    assert (g.kategori_id, g.kategori_ad, g.kategori_yol) == (agac["k243"], "KR C4", "12.41.243")
    assert g.kok_kategori_ad == "Endüstriyel Robotlar"
    assert g.net_fiyat_eur == Decimal("20000.00") and g.kdv_orani == Decimal("20")
    assert g.teklif_zorunlu is True and g.stok == 0 and g.tedarik_suresi_gun is None
    assert g.uretici_kodu == "KRC5" and g.gorsel_url == "/img/a.jpg"
    assert g.durum_kodu == "belirtilmemis" and g.durum_ornek is False and g.aktif is True


def test_one_cikanlar(con):
    assert one_cikanlar(con) == []
    g1 = u(con, sku="G1", gorsel_url="/a.jpg")
    u(con, sku="G2", gorsel_url="/b.jpg", aktif=False)
    n1 = u(con, sku="N1")
    g3 = u(con, sku="G3", gorsel_url="/c.jpg")
    u(con, sku="N2", gorsel_url="")
    assert [x.id for x in one_cikanlar(con, adet=3)] == [g1, g3, n1]
    assert [x.id for x in one_cikanlar(con, adet=1)] == [g1]
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `bash dagitim/test-vm.sh tests/test_katalog_depo.py -q`
Expected: FAIL — toplama aşamasında `ModuleNotFoundError: No module named 'app.katalog.depo'`

- [ ] **Step 3: Implementasyonu yaz**

`app/katalog/depo.py`:

```python
"""Katalog okuma katmanı: kategori ağacı, ürün listesi/filtre/sıralama, FTS5 arama.

Yazma yapmaz; eşitleme (Görev 5) urun/kategori/urun_ara tablolarını doldurur.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.metin import normalize

SAYFA_BOYU_MAX = 100
_KELIME = re.compile(r"\w+")

_URUN_SQL = (
    "SELECT u.*, k.ad AS kategori_ad, k.yol AS kategori_yol "
    "FROM urun u LEFT JOIN kategori k ON k.id = u.kategori_id"
)
_SAYI_SQL = "SELECT COUNT(*) FROM urun u LEFT JOIN kategori k ON k.id = u.kategori_id"
_KATEGORI_SQL = (
    "SELECT k.id, k.ad, k.yol, k.seviye, ust.id AS ust_id "
    "FROM kategori k LEFT JOIN kategori ust ON ust.kaynak_id = k.ust_kaynak_id"
)
# Fiyat yalnız SQL'de karşılaştırma/sıralama için REAL'e çevrilir; hesap yapılmaz (değerler 2 hane).
_FIYAT = "CAST(u.temsili_fiyat_eur AS REAL)"
_SIRALAR = {
    "ad": "tr_sira(u.ad), u.id",
    "fiyat_artan": f"{_FIYAT} ASC, u.id",
    "fiyat_azalan": f"{_FIYAT} DESC, u.id",
}


@dataclass(frozen=True)
class Kategori:
    id: int
    ad: str
    yol: str
    seviye: int
    ust_id: int | None


@dataclass
class KategoriDugum:
    kategori: Kategori
    cocuklar: list[KategoriDugum]
    urun_sayisi: int        # alt kategoriler dahil aktif ürün


@dataclass(frozen=True)
class Urun:
    id: int
    sku: str
    ad: str
    uretici_kodu: str | None
    kategori_id: int | None
    kategori_ad: str | None
    kategori_yol: str | None
    kok_kategori_ad: str
    kdv_orani: Decimal
    stok: int
    tedarik_suresi_gun: int | None
    gorsel_url: str | None
    net_fiyat_eur: Decimal
    fiyat_temsili: bool
    teklif_zorunlu: bool
    durum_kodu: str
    durum_ornek: bool
    aktif: bool


@dataclass(frozen=True)
class ListeSorgusu:
    kategori_id: int | None = None
    arama: str | None = None
    stokta: bool = False
    fiyat_min: Decimal | None = None      # net EUR
    fiyat_max: Decimal | None = None      # net EUR
    siralama: Literal["ad", "fiyat_artan", "fiyat_azalan"] = "ad"
    sayfa: int = 1
    sayfa_boyu: int = 24


@dataclass(frozen=True)
class ListeSonucu:
    urunler: list[Urun]
    toplam: int
    sayfa: int
    sayfa_sayisi: int


def _bos_sonuc() -> ListeSonucu:
    return ListeSonucu(urunler=[], toplam=0, sayfa=1, sayfa_sayisi=1)


def _sira_anahtari(ad: str | None) -> str:
    return normalize(ad or "")


def _urun(r: sqlite3.Row) -> Urun:
    return Urun(
        id=r["id"], sku=r["sku"], ad=r["ad"], uretici_kodu=r["uretici_kodu"],
        kategori_id=r["kategori_id"], kategori_ad=r["kategori_ad"], kategori_yol=r["kategori_yol"],
        kok_kategori_ad=r["kok_kategori_ad"], kdv_orani=Decimal(r["kdv_orani"]), stok=r["stok"],
        tedarik_suresi_gun=r["tedarik_suresi_gun"], gorsel_url=r["gorsel_url"],
        net_fiyat_eur=Decimal(r["temsili_fiyat_eur"]), fiyat_temsili=bool(r["fiyat_temsili"]),
        teklif_zorunlu=bool(r["teklif_zorunlu"]), durum_kodu=r["durum_kodu"],
        durum_ornek=bool(r["durum_ornek"]), aktif=bool(r["aktif"]),
    )


def _kategori(r: sqlite3.Row) -> Kategori:
    return Kategori(id=r["id"], ad=r["ad"], yol=r["yol"], seviye=r["seviye"], ust_id=r["ust_id"])


def kategori_getir(con: sqlite3.Connection, kategori_id: int) -> Kategori | None:
    r = con.execute(_KATEGORI_SQL + " WHERE k.id = ?", (kategori_id,)).fetchone()
    return _kategori(r) if r is not None else None


def kategori_yolu(con: sqlite3.Connection, kategori_id: int) -> list[Kategori]:
    yol: list[Kategori] = []
    gorulen: set[int] = set()
    simdiki: int | None = kategori_id
    while simdiki is not None and simdiki not in gorulen:   # bozuk veride döngüye girmez
        gorulen.add(simdiki)
        k = kategori_getir(con, simdiki)
        if k is None:
            break
        yol.append(k)
        simdiki = k.ust_id
    yol.reverse()
    return yol


def kategori_agaci(con: sqlite3.Connection) -> list[KategoriDugum]:
    satirlar = con.execute(_KATEGORI_SQL + " WHERE k.aktif = 1").fetchall()
    sayilar = {
        r["kategori_id"]: r["n"]
        for r in con.execute(
            "SELECT kategori_id, COUNT(*) AS n FROM urun "
            "WHERE aktif = 1 AND kategori_id IS NOT NULL GROUP BY kategori_id"
        )
    }
    dugumler = {
        r["id"]: KategoriDugum(kategori=_kategori(r), cocuklar=[], urun_sayisi=sayilar.get(r["id"], 0))
        for r in satirlar
    }
    kokler: list[KategoriDugum] = []
    for d in dugumler.values():
        ust = dugumler.get(d.kategori.ust_id) if d.kategori.ust_id is not None else None
        (ust.cocuklar if ust is not None else kokler).append(d)

    def topla(d: KategoriDugum) -> int:
        d.cocuklar.sort(key=lambda c: (normalize(c.kategori.ad), c.kategori.id))
        d.urun_sayisi += sum(topla(c) for c in d.cocuklar)
        return d.urun_sayisi

    kokler.sort(key=lambda c: (normalize(c.kategori.ad), c.kategori.id))
    for d in kokler:
        topla(d)
    return kokler


def urun_getir(con: sqlite3.Connection, urun_id: int) -> Urun | None:
    r = con.execute(_URUN_SQL + " WHERE u.id = ?", (urun_id,)).fetchone()
    return _urun(r) if r is not None else None


def _arama_ifadesi(arama: str) -> str:
    """Her kelime tırnaklanıp prefix yapılır: FTS5 operatörleri/özel karakterleri etkisizleşir."""
    return " ".join(f'"{t}"*' for t in _KELIME.findall(normalize(arama)))


def urun_listele(con: sqlite3.Connection, s: ListeSorgusu) -> ListeSonucu:
    con.create_function("tr_sira", 1, _sira_anahtari, deterministic=True)
    kosullar = ["u.aktif = 1"]
    param: list[object] = []
    if s.kategori_id is not None:
        k = kategori_getir(con, s.kategori_id)
        if k is None:
            return _bos_sonuc()
        kosullar.append("(k.yol = ? OR substr(k.yol, 1, ?) = ?)")
        param += [k.yol, len(k.yol) + 1, k.yol + "."]
    if s.arama is not None and s.arama.strip():
        ifade = _arama_ifadesi(s.arama)
        if not ifade:
            return _bos_sonuc()
        kosullar.append("u.id IN (SELECT urun_id FROM urun_ara WHERE urun_ara MATCH ?)")
        param.append(ifade)
    if s.stokta:
        kosullar.append("u.stok > 0")
    if s.fiyat_min is not None:
        kosullar.append(f"{_FIYAT} >= CAST(? AS REAL)")
        param.append(str(s.fiyat_min))
    if s.fiyat_max is not None:
        kosullar.append(f"{_FIYAT} <= CAST(? AS REAL)")
        param.append(str(s.fiyat_max))
    where = " WHERE " + " AND ".join(kosullar)

    toplam = con.execute(_SAYI_SQL + where, param).fetchone()[0]
    boy = max(1, min(SAYFA_BOYU_MAX, s.sayfa_boyu))
    sayfa_sayisi = max(1, (toplam + boy - 1) // boy)
    sayfa = min(max(1, s.sayfa), sayfa_sayisi)
    sira = _SIRALAR.get(s.siralama, _SIRALAR["ad"])
    satirlar = con.execute(
        _URUN_SQL + where + f" ORDER BY {sira} LIMIT ? OFFSET ?",
        [*param, boy, (sayfa - 1) * boy],
    ).fetchall()
    return ListeSonucu(urunler=[_urun(r) for r in satirlar], toplam=toplam, sayfa=sayfa, sayfa_sayisi=sayfa_sayisi)


def one_cikanlar(con: sqlite3.Connection, adet: int = 8) -> list[Urun]:
    satirlar = con.execute(
        _URUN_SQL
        + " WHERE u.aktif = 1 ORDER BY (u.gorsel_url IS NULL OR u.gorsel_url = ''), u.id LIMIT ?",
        (max(0, adet),),
    ).fetchall()
    return [_urun(r) for r in satirlar]
```

- [ ] **Step 4: Testlerin geçtiğini gör**

Run: `bash dagitim/test-vm.sh tests/test_katalog_depo.py -q`
Expected: PASS (0 failed)

Run: `bash dagitim/test-vm.sh tests -q`
Expected: PASS (önceki görevlerin testleri bozulmadı)

- [ ] **Step 5: Commit**

```bash
git add app/katalog/__init__.py app/katalog/depo.py tests/test_katalog_depo.py
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m "feat(katalog): kategori ağacı, filtreli ürün listesi ve Türkçe FTS arama

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Görev 7: Hesap servisi (`app/hesap/servis.py`)

**Files:**
- Create: `app/hesap/servis.py`
- Test: `tests/test_hesap_servis.py`

**Interfaces:**
- Consumes:
  - `app.fiyat.kurallar.MusteriTipi` (Görev 3)
  - `app.hesap.dogrulama.vkn_gecerli(s) -> bool`, `tckn_gecerli(s) -> bool` (Görev 2)
  - fixture `con`, `simdi` (Görev 1)
- Produces (Görev 9, 11, 13, 15 kullanır):
  - `Musteri`, `KayitGirdisi`, `KayitHatasi(alan, kod)` (`.alan`, `.kod` öznitelikleri), `Adres`
  - `parola_ozeti(parola) -> str` (`"scrypt$16384$8$1$<32 hex tuz>$<64 hex özet>"`), `parola_dogru(parola, ozet) -> bool` (bozuk özet -> `False`, istisna yok)
  - `kayit_ol(con, g, simdi) -> Musteri` — hata kodları: `("ad","zorunlu")`, `("eposta","zorunlu")`, `("eposta","gecersiz")`, `("eposta","eposta_kayitli")`, `("parola","parola_kisa")`, `("kvkk_onay","kvkk_onay_yok")`, `("vergi_kimlik_no","zorunlu")`, `("vergi_kimlik_no","gecersiz_vkn")`, `("vergi_dairesi","zorunlu")`, `("ulke","zorunlu")`, `("ulke","gecersiz")`
  - `giris(con, eposta, parola) -> Musteri | None`, `musteri_getir(con, musteri_id) -> Musteri | None`
  - `adres_kaydet(con, musteri_id, tur, a) -> int` (geçersiz `tur` -> `ValueError`; boş zorunlu alan -> `KayitHatasi(alan, "zorunlu")`), `adres_son(con, musteri_id, tur) -> Adres | None`
  - Kurallar: e-posta kırpılıp küçük harfe çevrilerek saklanır; BIREYSEL ve KURUMSAL için `ulke` her zaman `"TR"`; `iys_onay` yalnız BIREYSEL'de serbest, KURUMSAL ve YURTDISI'nda `False`; kurumsal `vergi_kimlik_no` içindeki boşluklar atılır.

- [ ] **Step 1: Başarısız testi yaz**

Geçerli örnek VKN'nin hesabı (GİB algoritması: `i=0..8` için `tmp=(hane+10-(i+1))%10`; `tmp==9` ise 9, değilse `(tmp*2**(10-(i+1)))%9`; toplam; son hane `(10-toplam%10)%10`). İlk dokuz hane `123456789`:

| i | hane | tmp = (hane+10-(i+1)) % 10 | v |
|---|---|---|---|
| 0 | 1 | (1+10-1)%10 = 0 | 0·2⁹ % 9 = 0 |
| 1 | 2 | (2+10-2)%10 = 0 | 0 |
| 2 | 3 | 0 | 0 |
| 3 | 4 | 0 | 0 |
| 4 | 5 | 0 | 0 |
| 5 | 6 | 0 | 0 |
| 6 | 7 | 0 | 0 |
| 7 | 8 | 0 | 0 |
| 8 | 9 | (9+10-9)%10 = 0 | 0 |

Toplam 0 → son hane `(10-0)%10 = 0` → **`1234567890` geçerli**; son hanesi farklı `1234567891` geçersiz. TCKN `10000000146`: tek sıralar 1+0+0+0+1=2, çift sıralar 0 → 10. hane (2·7−0)%10=4 ✓; ilk 10 hane toplamı 6 → 11. hane 6 ✓. `10000000145` geçersiz.

`tests/test_hesap_servis.py`:

```python
from dataclasses import replace

import pytest

from app.fiyat.kurallar import MusteriTipi
from app.hesap.dogrulama import tckn_gecerli, vkn_gecerli
from app.hesap.servis import (
    Adres,
    KayitGirdisi,
    KayitHatasi,
    Musteri,
    adres_kaydet,
    adres_son,
    giris,
    kayit_ol,
    musteri_getir,
    parola_dogru,
    parola_ozeti,
)

GECERLI_VKN = "1234567890"
GECERLI_TCKN = "10000000146"
PAROLA = "demo-parola-123"


def girdi(tip, **kw):
    taban = {
        MusteriTipi.BIREYSEL: dict(ad="QATestUser Bireysel", eposta="qa.bireysel@example.com", ulke="TR"),
        MusteriTipi.KURUMSAL: dict(
            ad="QATestUser Ltd", eposta="qa.kurumsal@example.com", ulke="TR",
            vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Kocaeli",
        ),
        MusteriTipi.YURTDISI: dict(
            ad="QATestUser GmbH", eposta="qa.yurtdisi@example.com", ulke="DE", vat_id="DE123456789",
        ),
    }[tip]
    alanlar = dict(tip=tip, parola=PAROLA, kvkk_onay=True, **taban)
    alanlar.update(kw)
    return KayitGirdisi(**alanlar)


def hata(con, simdi, g):
    with pytest.raises(KayitHatasi) as e:
        kayit_ol(con, g, simdi)
    return (e.value.alan, e.value.kod)


def musteri_sayisi(con):
    return con.execute("SELECT COUNT(*) FROM musteri").fetchone()[0]


def test_ornek_numaralar():
    assert vkn_gecerli(GECERLI_VKN) and vkn_gecerli("4728136592") and tckn_gecerli(GECERLI_TCKN)
    assert not vkn_gecerli("1234567891") and not vkn_gecerli("4728136593")
    assert not tckn_gecerli("10000000145")


def test_bireysel_kayit(con, simdi):
    m = kayit_ol(con, girdi(MusteriTipi.BIREYSEL, iys_onay=True, vergi_kimlik_no=GECERLI_VKN), simdi)
    assert isinstance(m, Musteri) and m.tip is MusteriTipi.BIREYSEL
    assert m.ulke == "TR" and m.iys_onay is True
    assert (m.vergi_kimlik_no, m.vergi_dairesi, m.vat_id) == (None, None, None)
    r = con.execute("SELECT kvkk_onay, olusturma, parola_ozeti FROM musteri WHERE id = ?", (m.id,)).fetchone()
    assert r["kvkk_onay"] == simdi.isoformat() and r["olusturma"] == simdi.isoformat()
    assert PAROLA not in r["parola_ozeti"] and parola_dogru(PAROLA, r["parola_ozeti"])
    assert musteri_getir(con, m.id) == m
    assert musteri_getir(con, 99999) is None


def test_bireysel_ulke_tr_zorlanir(con, simdi):
    assert kayit_ol(con, girdi(MusteriTipi.BIREYSEL, ulke="de"), simdi).ulke == "TR"


def test_kurumsal_vkn_veya_tckn(con, simdi):
    m1 = kayit_ol(con, girdi(MusteriTipi.KURUMSAL, iys_onay=True), simdi)
    assert m1.tip is MusteriTipi.KURUMSAL
    assert (m1.vergi_kimlik_no, m1.vergi_dairesi, m1.ulke, m1.iys_onay) == (GECERLI_VKN, "Kocaeli", "TR", False)
    m3 = kayit_ol(con, girdi(MusteriTipi.KURUMSAL, eposta="qa.k3@example.com", vergi_kimlik_no="4728136592"), simdi)
    assert m3.vergi_kimlik_no == "4728136592"
    m2 = kayit_ol(
        con,
        girdi(MusteriTipi.KURUMSAL, eposta="qa.sahis@example.com", vergi_kimlik_no=" 100 000 001 46 ", ulke="DE"),
        simdi,
    )
    assert (m2.vergi_kimlik_no, m2.ulke) == (GECERLI_TCKN, "TR")


@pytest.mark.parametrize(
    "vkn", ["1234567891", "4728136593", "10000000145", "123456789", "123456789012", "12345abcde", "01234567890"]
)
def test_kurumsal_gecersiz_vergi_no(con, simdi, vkn):
    assert hata(con, simdi, girdi(MusteriTipi.KURUMSAL, vergi_kimlik_no=vkn)) == ("vergi_kimlik_no", "gecersiz_vkn")
    assert musteri_sayisi(con) == 0


def test_kurumsal_zorunlu_alanlar(con, simdi):
    assert hata(con, simdi, girdi(MusteriTipi.KURUMSAL, vergi_kimlik_no=None)) == ("vergi_kimlik_no", "zorunlu")
    assert hata(con, simdi, girdi(MusteriTipi.KURUMSAL, vergi_kimlik_no="   ")) == ("vergi_kimlik_no", "zorunlu")
    assert hata(con, simdi, girdi(MusteriTipi.KURUMSAL, vergi_dairesi=" ")) == ("vergi_dairesi", "zorunlu")
    assert hata(con, simdi, girdi(MusteriTipi.KURUMSAL, vergi_dairesi=None)) == ("vergi_dairesi", "zorunlu")


def test_yurtdisi_kayit_iys_zorla_false(con, simdi):
    m = kayit_ol(con, girdi(MusteriTipi.YURTDISI, ulke=" de ", iys_onay=True), simdi)
    assert (m.tip, m.ulke, m.iys_onay, m.vat_id) == (MusteriTipi.YURTDISI, "DE", False, "DE123456789")
    assert con.execute("SELECT iys_onay FROM musteri WHERE id = ?", (m.id,)).fetchone()[0] == 0
    m2 = kayit_ol(con, girdi(MusteriTipi.YURTDISI, eposta="qa.fr@example.com", ulke="FR", vat_id="  "), simdi)
    assert m2.vat_id is None


@pytest.mark.parametrize("ulke", ["TR", "tr", "DEU", "1A", "D"])
def test_yurtdisi_gecersiz_ulke(con, simdi, ulke):
    assert hata(con, simdi, girdi(MusteriTipi.YURTDISI, ulke=ulke)) == ("ulke", "gecersiz")


def test_yurtdisi_ulke_zorunlu(con, simdi):
    assert hata(con, simdi, girdi(MusteriTipi.YURTDISI, ulke="  ")) == ("ulke", "zorunlu")


def test_eposta_tekrari_buyuk_kucuk_harf_duyarsiz(con, simdi):
    kayit_ol(con, girdi(MusteriTipi.BIREYSEL), simdi)
    g = girdi(MusteriTipi.KURUMSAL, eposta="  QA.Bireysel@Example.COM ")
    assert hata(con, simdi, g) == ("eposta", "eposta_kayitli")
    assert musteri_sayisi(con) == 1


def test_eposta_bicimi(con, simdi):
    assert hata(con, simdi, girdi(MusteriTipi.BIREYSEL, eposta="   ")) == ("eposta", "zorunlu")
    assert hata(con, simdi, girdi(MusteriTipi.BIREYSEL, eposta="qa.example.com")) == ("eposta", "gecersiz")


def test_kisa_parola(con, simdi):
    assert hata(con, simdi, girdi(MusteriTipi.BIREYSEL, parola="123456789")) == ("parola", "parola_kisa")
    assert kayit_ol(con, girdi(MusteriTipi.BIREYSEL, parola="1234567890"), simdi).id > 0


def test_kvkk_onay_yok(con, simdi):
    assert hata(con, simdi, girdi(MusteriTipi.BIREYSEL, kvkk_onay=False)) == ("kvkk_onay", "kvkk_onay_yok")
    assert musteri_sayisi(con) == 0


def test_ad_zorunlu(con, simdi):
    assert hata(con, simdi, girdi(MusteriTipi.BIREYSEL, ad="  ")) == ("ad", "zorunlu")


def test_parola_ozeti_bicimi_ve_dogrulama():
    oz = parola_ozeti(PAROLA)
    parcalar = oz.split("$")
    assert len(parcalar) == 6 and parcalar[:4] == ["scrypt", "16384", "8", "1"]
    assert len(parcalar[4]) == 32 and len(parcalar[5]) == 64
    int(parcalar[4], 16)
    int(parcalar[5], 16)
    assert parola_ozeti(PAROLA) != oz                    # tuz her seferinde farklı
    assert parola_dogru(PAROLA, oz) is True
    assert parola_dogru("demo-parola-124", oz) is False


@pytest.mark.parametrize(
    "ozet",
    [
        "", "bozuk", "scrypt$16384$8$1$zz$00", "scrypt$16384$8$1$abcd", "scrypt$x$8$1$00$00",
        "md5$16384$8$1$00$00", "scrypt$16384$8$1$$", "scrypt$1048576$8$1$00112233$0011", None,
    ],
)
def test_bozuk_ozet_false_doner(ozet):
    assert parola_dogru(PAROLA, ozet) is False


def test_giris(con, simdi):
    m = kayit_ol(con, girdi(MusteriTipi.BIREYSEL, eposta="QA.Giris@Example.com"), simdi)
    assert m.eposta == "qa.giris@example.com"
    assert giris(con, "qa.giris@example.com", PAROLA) == m
    assert giris(con, "  QA.GIRIS@EXAMPLE.COM ", PAROLA) == m
    assert giris(con, "qa.giris@example.com", "yanlis-parola-1") is None
    assert giris(con, "yok@example.com", PAROLA) is None
    assert giris(con, "", "") is None


ADRES1 = Adres(ad_soyad="QATestUser Bir", satir1="Demo Cad. 1", sehir="Kocaeli", ulke="tr", posta_kodu="41400")
ADRES2 = Adres(ad_soyad="QATestUser İki", satir1="Demo Sok. 2", sehir="İstanbul", ulke="TR", telefon="+90 500 000 00 00")


def test_adres_kaydet_ve_son(con, simdi):
    m = kayit_ol(con, girdi(MusteriTipi.BIREYSEL), simdi)
    assert adres_son(con, m.id, "teslimat") is None
    i1 = adres_kaydet(con, m.id, "teslimat", ADRES1)
    i2 = adres_kaydet(con, m.id, "teslimat", ADRES2)
    assert i2 > i1
    assert adres_son(con, m.id, "teslimat") == ADRES2
    assert adres_son(con, m.id, "fatura") is None
    adres_kaydet(con, m.id, "fatura", replace(ADRES1, satir2="  ", sehir=" Kocaeli "))
    assert adres_son(con, m.id, "fatura") == replace(ADRES1, ulke="TR")


def test_adres_gecersiz(con, simdi):
    m = kayit_ol(con, girdi(MusteriTipi.BIREYSEL), simdi)
    with pytest.raises(ValueError):
        adres_kaydet(con, m.id, "ev", ADRES1)
    with pytest.raises(KayitHatasi) as e:
        adres_kaydet(con, m.id, "teslimat", replace(ADRES1, satir1="  "))
    assert (e.value.alan, e.value.kod) == ("satir1", "zorunlu")
    assert con.execute("SELECT COUNT(*) FROM adres").fetchone()[0] == 0
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `bash dagitim/test-vm.sh tests/test_hesap_servis.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.hesap.servis'`

- [ ] **Step 3: Implementasyonu yaz**

`app/hesap/servis.py`:

```python
"""Müşteri hesabı: kayıt kuralları, giriş, scrypt parola özeti, adresler. Commit yapmaz."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.fiyat.kurallar import MusteriTipi
from app.hesap.dogrulama import tckn_gecerli, vkn_gecerli

PAROLA_MIN = 10
ADRES_TURLERI = ("teslimat", "fatura")
_N, _R, _P, _DKLEN, _TUZ = 16384, 8, 1, 32, 16


@dataclass(frozen=True)
class Musteri:
    id: int
    tip: MusteriTipi
    ad: str
    eposta: str
    ulke: str
    vergi_kimlik_no: str | None
    vergi_dairesi: str | None
    vat_id: str | None
    iys_onay: bool


@dataclass(frozen=True)
class KayitGirdisi:
    tip: MusteriTipi
    ad: str
    eposta: str
    parola: str
    ulke: str
    kvkk_onay: bool
    iys_onay: bool = False
    vergi_kimlik_no: str | None = None
    vergi_dairesi: str | None = None
    vat_id: str | None = None


class KayitHatasi(ValueError):
    def __init__(self, alan: str, kod: str):
        super().__init__(f"{alan}:{kod}")
        self.alan = alan
        self.kod = kod


@dataclass(frozen=True)
class Adres:
    ad_soyad: str
    satir1: str
    sehir: str
    ulke: str
    satir2: str | None = None
    posta_kodu: str | None = None
    telefon: str | None = None


def _temiz(s: str | None) -> str | None:
    if s is None:
        return None
    s = s.strip()
    return s or None


def parola_ozeti(parola: str) -> str:
    tuz = secrets.token_bytes(_TUZ)
    oz = hashlib.scrypt(parola.encode("utf-8"), salt=tuz, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${tuz.hex()}${oz.hex()}"


def parola_dogru(parola: str, ozet: str) -> bool:
    try:
        ad, n, r, p, tuz_hex, ozet_hex = ozet.split("$")
        if ad != "scrypt" or (int(n), int(r), int(p)) != (_N, _R, _P):
            return False
        tuz = bytes.fromhex(tuz_hex)
        beklenen = bytes.fromhex(ozet_hex)
        if not tuz or len(beklenen) != _DKLEN:
            return False
        hesap = hashlib.scrypt(parola.encode("utf-8"), salt=tuz, n=_N, r=_R, p=_P, dklen=_DKLEN)
    except (ValueError, TypeError, AttributeError):
        return False
    return hmac.compare_digest(hesap, beklenen)


def _vergi_no_gecerli(no: str) -> bool:
    if not (no.isascii() and no.isdigit()):
        return False
    if len(no) == 10:
        return vkn_gecerli(no)
    if len(no) == 11:
        return tckn_gecerli(no)
    return False


def _musteri(r: sqlite3.Row) -> Musteri:
    return Musteri(
        id=r["id"], tip=MusteriTipi(r["tip"]), ad=r["ad"], eposta=r["eposta"], ulke=r["ulke"],
        vergi_kimlik_no=r["vergi_kimlik_no"], vergi_dairesi=r["vergi_dairesi"], vat_id=r["vat_id"],
        iys_onay=bool(r["iys_onay"]),
    )


def musteri_getir(con: sqlite3.Connection, musteri_id: int) -> Musteri | None:
    r = con.execute("SELECT * FROM musteri WHERE id = ?", (musteri_id,)).fetchone()
    return _musteri(r) if r is not None else None


def kayit_ol(con: sqlite3.Connection, g: KayitGirdisi, simdi: datetime) -> Musteri:
    ad = _temiz(g.ad)
    if ad is None:
        raise KayitHatasi("ad", "zorunlu")
    eposta = _temiz(g.eposta)
    if eposta is None:
        raise KayitHatasi("eposta", "zorunlu")
    eposta = eposta.lower()
    if "@" not in eposta:
        raise KayitHatasi("eposta", "gecersiz")
    if len(g.parola or "") < PAROLA_MIN:
        raise KayitHatasi("parola", "parola_kisa")
    if not g.kvkk_onay:
        raise KayitHatasi("kvkk_onay", "kvkk_onay_yok")

    tip = MusteriTipi(g.tip)
    vkn = daire = vat = None
    iys = bool(g.iys_onay)
    if tip is MusteriTipi.KURUMSAL:
        ulke, iys = "TR", False
        vkn = "".join((g.vergi_kimlik_no or "").split())
        if not vkn:
            raise KayitHatasi("vergi_kimlik_no", "zorunlu")
        if not _vergi_no_gecerli(vkn):
            raise KayitHatasi("vergi_kimlik_no", "gecersiz_vkn")
        daire = _temiz(g.vergi_dairesi)
        if daire is None:
            raise KayitHatasi("vergi_dairesi", "zorunlu")
    elif tip is MusteriTipi.YURTDISI:
        ulke = (g.ulke or "").strip().upper()
        if not ulke:
            raise KayitHatasi("ulke", "zorunlu")
        if len(ulke) != 2 or not (ulke.isascii() and ulke.isalpha()) or ulke == "TR":
            raise KayitHatasi("ulke", "gecersiz")
        iys = False
        vat = _temiz(g.vat_id)
    else:
        ulke = "TR"

    if con.execute("SELECT 1 FROM musteri WHERE eposta = ?", (eposta,)).fetchone() is not None:
        raise KayitHatasi("eposta", "eposta_kayitli")
    an = simdi.isoformat()
    try:
        cur = con.execute(
            "INSERT INTO musteri (tip, ad, eposta, parola_ozeti, vergi_kimlik_no, vergi_dairesi, vat_id, "
            "ulke, kvkk_onay, iys_onay, olusturma) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tip.value, ad, eposta, parola_ozeti(g.parola), vkn, daire, vat, ulke, an, int(iys), an),
        )
    except sqlite3.IntegrityError:          # eşzamanlı aynı e-posta
        raise KayitHatasi("eposta", "eposta_kayitli") from None
    return musteri_getir(con, cur.lastrowid)


def giris(con: sqlite3.Connection, eposta: str, parola: str) -> Musteri | None:
    e = (eposta or "").strip().lower()
    if not e:
        return None
    r = con.execute("SELECT id, parola_ozeti FROM musteri WHERE eposta = ?", (e,)).fetchone()
    if r is None or not parola_dogru(parola or "", r["parola_ozeti"]):
        return None
    return musteri_getir(con, r["id"])


def adres_kaydet(
    con: sqlite3.Connection, musteri_id: int, tur: Literal["teslimat", "fatura"], a: Adres
) -> int:
    if tur not in ADRES_TURLERI:
        raise ValueError("tur")
    zorunlu: dict[str, str] = {}
    for alan in ("ad_soyad", "satir1", "sehir", "ulke"):
        deger = _temiz(getattr(a, alan))
        if deger is None:
            raise KayitHatasi(alan, "zorunlu")
        zorunlu[alan] = deger
    cur = con.execute(
        "INSERT INTO adres (musteri_id, tur, ad_soyad, satir1, satir2, sehir, posta_kodu, ulke, telefon) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            musteri_id, tur, zorunlu["ad_soyad"], zorunlu["satir1"], _temiz(a.satir2), zorunlu["sehir"],
            _temiz(a.posta_kodu), zorunlu["ulke"].upper(), _temiz(a.telefon),
        ),
    )
    return cur.lastrowid


def adres_son(con: sqlite3.Connection, musteri_id: int, tur: str) -> Adres | None:
    r = con.execute(
        "SELECT * FROM adres WHERE musteri_id = ? AND tur = ? ORDER BY id DESC LIMIT 1", (musteri_id, tur)
    ).fetchone()
    if r is None:
        return None
    return Adres(
        ad_soyad=r["ad_soyad"], satir1=r["satir1"], sehir=r["sehir"], ulke=r["ulke"],
        satir2=r["satir2"], posta_kodu=r["posta_kodu"], telefon=r["telefon"],
    )
```

- [ ] **Step 4: Testlerin geçtiğini gör**

Run: `bash dagitim/test-vm.sh tests/test_hesap_servis.py -q`
Expected: PASS (0 failed)

Run: `bash dagitim/test-vm.sh tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/hesap/servis.py tests/test_hesap_servis.py
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m "feat(hesap): üç müşteri tipiyle kayıt, scrypt parola, giriş ve adresler

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Görev 8: Sepet servisi (`app/sepet/servis.py`)

**Files:**
- Create: `app/sepet/servis.py`
- Test: `tests/test_sepet.py`

**Interfaces:**
- Consumes:
  - `app.fiyat.kurallar.Kalem(urun_id, sku, ad, adet, birim_net_eur, kdv_orani, tedarik_teyit=False)` (Görev 3)
  - fixture `con`, `simdi`; yardımcı `urun_ekle` (Görev 1)
- Produces (Görev 9, 12, 14 kullanır):
  - `TeklifZorunlu`, `UrunYok`, `ADET_MIN = 1`, `ADET_MAX = 99`
  - `sepet_bul(con, oturum_id, musteri_id, simdi) -> int` — ikisi de yoksa `ValueError("oturum_yok")`; üye sepeti `oturum_id=NULL` ile oluşur
  - `ekle(con, sepet_id, urun_id, adet=1) -> None` — adet önce 1..99'a kısılır, mevcutsa toplanır (en fazla 99)
  - `adet_ayarla(con, sepet_id, urun_id, adet) -> None` — `<1` kaldırır, `>99` 99; sepette olmayan ürün için bir şey yapmaz
  - `kaldir`, `bosalt`, `adet_toplam(con, sepet_id) -> int`
  - `kalemler(con, sepet_id) -> tuple[list[Kalem], list[str]]` — ekleme sırasıyla; `birim_net_eur = Decimal(temsili_fiyat_eur)`, `tedarik_teyit = stok == 0 and tedarik_suresi_gun is None`; pasif veya teklif zorunlu ürünler silinir, adları döner
  - `birlestir(con, misafir_sepet_id, uye_sepet_id) -> int` — misafirdeki kalem sayısını döner; aynı id verilirse 0 ve değişiklik yok

- [ ] **Step 1: Başarısız testi yaz**

`tests/test_sepet.py`:

```python
from decimal import Decimal

import pytest

from app.fiyat.kurallar import Kalem
from app.sepet.servis import (
    ADET_MAX,
    ADET_MIN,
    TeklifZorunlu,
    UrunYok,
    adet_ayarla,
    adet_toplam,
    birlestir,
    bosalt,
    ekle,
    kaldir,
    kalemler,
    sepet_bul,
)
from tests.conftest import urun_ekle


def musteri_ekle(con, simdi, eposta="qa.sepet@example.com"):
    return con.execute(
        "INSERT INTO musteri (tip, ad, eposta, parola_ozeti, ulke, kvkk_onay, olusturma) "
        "VALUES ('bireysel', 'QATestUser', ?, 'x', 'TR', ?, ?)",
        (eposta, simdi.isoformat(), simdi.isoformat()),
    ).lastrowid


def adetler(con, sepet_id):
    return {
        r["urun_id"]: r["adet"]
        for r in con.execute("SELECT urun_id, adet FROM sepet_kalemi WHERE sepet_id = ?", (sepet_id,))
    }


def test_sabitler():
    assert (ADET_MIN, ADET_MAX) == (1, 99)


def test_sepet_bul_misafir_ve_uye(con, simdi):
    s1 = sepet_bul(con, "oid-1", None, simdi)
    assert sepet_bul(con, "oid-1", None, simdi) == s1
    assert sepet_bul(con, "oid-2", None, simdi) != s1
    mid = musteri_ekle(con, simdi)
    s3 = sepet_bul(con, "oid-1", mid, simdi)
    assert s3 != s1
    assert sepet_bul(con, None, mid, simdi) == s3
    r = con.execute("SELECT oturum_id, musteri_id, olusturma FROM sepet WHERE id = ?", (s3,)).fetchone()
    assert (r["oturum_id"], r["musteri_id"], r["olusturma"]) == (None, mid, simdi.isoformat())
    with pytest.raises(ValueError):
        sepet_bul(con, None, None, simdi)


def test_ekle_toplar_ve_99_siniri(con, simdi):
    s = sepet_bul(con, "oid", None, simdi)
    a = urun_ekle(con, sku="A")
    ekle(con, s, a)
    assert adetler(con, s) == {a: 1}
    ekle(con, s, a, 3)
    assert adetler(con, s) == {a: 4}
    ekle(con, s, a, 98)
    assert adetler(con, s) == {a: 99}
    assert adet_toplam(con, s) == 99


def test_teklif_zorunlu_eklenemez(con, simdi):
    s = sepet_bul(con, "oid", None, simdi)
    t = urun_ekle(con, sku="ROBOT", kok="Endüstriyel Robotlar", teklif=True, fiyat="20000.00")
    with pytest.raises(TeklifZorunlu):
        ekle(con, s, t)
    assert adetler(con, s) == {}


def test_urun_yok_ve_pasif(con, simdi):
    s = sepet_bul(con, "oid", None, simdi)
    p = urun_ekle(con, sku="P", aktif=False)
    with pytest.raises(UrunYok):
        ekle(con, s, 99999)
    with pytest.raises(UrunYok):
        ekle(con, s, p)
    assert adetler(con, s) == {}


def test_adet_sinirlari(con, simdi):
    s = sepet_bul(con, "oid", None, simdi)
    a, b, c = (urun_ekle(con, sku=x) for x in ("A", "B", "C"))
    ekle(con, s, a, 0)
    ekle(con, s, b, -3)
    ekle(con, s, c, 1000)
    assert adetler(con, s) == {a: 1, b: 1, c: 99}
    adet_ayarla(con, s, a, 1000)
    assert adetler(con, s)[a] == 99
    adet_ayarla(con, s, a, 5)
    assert adetler(con, s)[a] == 5
    adet_ayarla(con, s, a, 0)
    adet_ayarla(con, s, b, -3)
    assert adetler(con, s) == {c: 99}
    d = urun_ekle(con, sku="D")
    adet_ayarla(con, s, d, 5)                      # sepette olmayan ürün eklenmez
    assert adetler(con, s) == {c: 99}


def test_kaldir_bosalt_adet_toplam(con, simdi):
    s = sepet_bul(con, "oid", None, simdi)
    a, b = urun_ekle(con, sku="A"), urun_ekle(con, sku="B")
    ekle(con, s, a, 2)
    ekle(con, s, b, 3)
    assert adet_toplam(con, s) == 5
    kaldir(con, s, a)
    assert adetler(con, s) == {b: 3}
    bosalt(con, s)
    assert adetler(con, s) == {} and adet_toplam(con, s) == 0


def test_kalemler_fiyat_kalemi_doner(con, simdi):
    s = sepet_bul(con, "oid", None, simdi)
    a = urun_ekle(con, sku="A1", ad="Röle", fiyat="123.45", kdv="20", stok=0)
    b = urun_ekle(con, sku="B1", ad="Kablo", fiyat="10.00", kdv="10", stok=0, tedarik_suresi_gun=14)
    c = urun_ekle(con, sku="C1", ad="Sigorta", fiyat="5.00", stok=7)
    ekle(con, s, a, 2)
    ekle(con, s, b)
    ekle(con, s, c, 3)
    gecerli, dusen = kalemler(con, s)
    assert dusen == []
    assert gecerli == [
        Kalem(urun_id=a, sku="A1", ad="Röle", adet=2, birim_net_eur=Decimal("123.45"),
              kdv_orani=Decimal("20"), tedarik_teyit=True),
        Kalem(urun_id=b, sku="B1", ad="Kablo", adet=1, birim_net_eur=Decimal("10.00"),
              kdv_orani=Decimal("10"), tedarik_teyit=False),
        Kalem(urun_id=c, sku="C1", ad="Sigorta", adet=3, birim_net_eur=Decimal("5.00"),
              kdv_orani=Decimal("20"), tedarik_teyit=False),
    ]


def test_pasif_urun_sepetten_duser(con, simdi):
    s = sepet_bul(con, "oid", None, simdi)
    a = urun_ekle(con, sku="A", ad="Pasifleşen Röle")
    b = urun_ekle(con, sku="B", ad="Pahalanan Sürücü")
    c = urun_ekle(con, sku="C", ad="Kalan Kablo")
    for x in (a, b, c):
        ekle(con, s, x)
    con.execute("UPDATE urun SET aktif = 0 WHERE id = ?", (a,))
    con.execute("UPDATE urun SET teklif_zorunlu = 1 WHERE id = ?", (b,))
    gecerli, dusen = kalemler(con, s)
    assert [k.urun_id for k in gecerli] == [c]
    assert dusen == ["Pasifleşen Röle", "Pahalanan Sürücü"]
    assert adetler(con, s) == {c: 1}
    assert kalemler(con, s)[1] == []                  # ikinci çağrıda bildirilecek bir şey kalmaz


def test_birlestir(con, simdi):
    misafir = sepet_bul(con, "oid", None, simdi)
    uye = sepet_bul(con, None, musteri_ekle(con, simdi), simdi)
    a, b, c = (urun_ekle(con, sku=x) for x in ("A", "B", "C"))
    ekle(con, misafir, a, 60)
    ekle(con, misafir, b, 2)
    ekle(con, uye, a, 50)
    ekle(con, uye, c, 1)
    assert birlestir(con, misafir, uye) == 2
    assert adetler(con, uye) == {a: 99, b: 2, c: 1}
    assert adetler(con, misafir) == {}
    assert con.execute("SELECT COUNT(*) FROM sepet WHERE id = ?", (misafir,)).fetchone()[0] == 0
    assert birlestir(con, uye, uye) == 0
    assert adetler(con, uye) == {a: 99, b: 2, c: 1}
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `bash dagitim/test-vm.sh tests/test_sepet.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.sepet.servis'`

- [ ] **Step 3: Implementasyonu yaz**

`app/sepet/servis.py`:

```python
"""Sepet: misafir (oturum) ve üye sepetleri, adet sınırları, düşen ürünler, birleştirme. Commit yapmaz."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal

from app.fiyat.kurallar import Kalem

ADET_MIN, ADET_MAX = 1, 99

_UPSERT = (
    "INSERT INTO sepet_kalemi (sepet_id, urun_id, adet) VALUES (?, ?, ?) "
    "ON CONFLICT(sepet_id, urun_id) DO UPDATE SET adet = MIN(?, sepet_kalemi.adet + excluded.adet)"
)


class TeklifZorunlu(Exception):
    pass


class UrunYok(Exception):
    pass


def _kis(adet: int) -> int:
    return max(ADET_MIN, min(ADET_MAX, adet))


def sepet_bul(con: sqlite3.Connection, oturum_id: str | None, musteri_id: int | None, simdi: datetime) -> int:
    if musteri_id is not None:
        r = con.execute("SELECT id FROM sepet WHERE musteri_id = ?", (musteri_id,)).fetchone()
        if r is not None:
            return r["id"]
        return con.execute(
            "INSERT INTO sepet (oturum_id, musteri_id, olusturma) VALUES (NULL, ?, ?)",
            (musteri_id, simdi.isoformat()),
        ).lastrowid
    if not oturum_id:
        raise ValueError("oturum_yok")
    r = con.execute("SELECT id FROM sepet WHERE oturum_id = ?", (oturum_id,)).fetchone()
    if r is not None:
        return r["id"]
    return con.execute(
        "INSERT INTO sepet (oturum_id, musteri_id, olusturma) VALUES (?, NULL, ?)",
        (oturum_id, simdi.isoformat()),
    ).lastrowid


def ekle(con: sqlite3.Connection, sepet_id: int, urun_id: int, adet: int = 1) -> None:
    r = con.execute("SELECT aktif, teklif_zorunlu FROM urun WHERE id = ?", (urun_id,)).fetchone()
    if r is None or not r["aktif"]:
        raise UrunYok(urun_id)
    if r["teklif_zorunlu"]:
        raise TeklifZorunlu(urun_id)
    con.execute(_UPSERT, (sepet_id, urun_id, _kis(adet), ADET_MAX))


def adet_ayarla(con: sqlite3.Connection, sepet_id: int, urun_id: int, adet: int) -> None:
    if adet < ADET_MIN:
        kaldir(con, sepet_id, urun_id)
        return
    con.execute(
        "UPDATE sepet_kalemi SET adet = ? WHERE sepet_id = ? AND urun_id = ?",
        (min(ADET_MAX, adet), sepet_id, urun_id),
    )


def kaldir(con: sqlite3.Connection, sepet_id: int, urun_id: int) -> None:
    con.execute("DELETE FROM sepet_kalemi WHERE sepet_id = ? AND urun_id = ?", (sepet_id, urun_id))


def bosalt(con: sqlite3.Connection, sepet_id: int) -> None:
    con.execute("DELETE FROM sepet_kalemi WHERE sepet_id = ?", (sepet_id,))


def kalemler(con: sqlite3.Connection, sepet_id: int) -> tuple[list[Kalem], list[str]]:
    satirlar = con.execute(
        "SELECT k.urun_id, k.adet, u.sku, u.ad, u.temsili_fiyat_eur, u.kdv_orani, u.stok, "
        "u.tedarik_suresi_gun, u.aktif, u.teklif_zorunlu "
        "FROM sepet_kalemi k JOIN urun u ON u.id = k.urun_id WHERE k.sepet_id = ? ORDER BY k.rowid",
        (sepet_id,),
    ).fetchall()
    gecerli: list[Kalem] = []
    dusen: list[str] = []
    for r in satirlar:
        if not r["aktif"] or r["teklif_zorunlu"]:
            kaldir(con, sepet_id, r["urun_id"])
            dusen.append(r["ad"])
            continue
        gecerli.append(
            Kalem(
                urun_id=r["urun_id"], sku=r["sku"], ad=r["ad"], adet=r["adet"],
                birim_net_eur=Decimal(r["temsili_fiyat_eur"]), kdv_orani=Decimal(r["kdv_orani"]),
                tedarik_teyit=r["stok"] == 0 and r["tedarik_suresi_gun"] is None,
            )
        )
    return gecerli, dusen


def adet_toplam(con: sqlite3.Connection, sepet_id: int) -> int:
    return con.execute(
        "SELECT COALESCE(SUM(adet), 0) FROM sepet_kalemi WHERE sepet_id = ?", (sepet_id,)
    ).fetchone()[0]


def birlestir(con: sqlite3.Connection, misafir_sepet_id: int, uye_sepet_id: int) -> int:
    if misafir_sepet_id == uye_sepet_id:
        return 0
    satirlar = con.execute(
        "SELECT urun_id, adet FROM sepet_kalemi WHERE sepet_id = ? ORDER BY rowid", (misafir_sepet_id,)
    ).fetchall()
    for r in satirlar:
        con.execute(_UPSERT, (uye_sepet_id, r["urun_id"], r["adet"], ADET_MAX))
    bosalt(con, misafir_sepet_id)
    con.execute("DELETE FROM sepet WHERE id = ?", (misafir_sepet_id,))
    return len(satirlar)
```

- [ ] **Step 4: Testlerin geçtiğini gör**

Run: `bash dagitim/test-vm.sh tests/test_sepet.py -q`
Expected: PASS (0 failed)

Run: `bash dagitim/test-vm.sh tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/sepet/servis.py tests/test_sepet.py
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m "feat(sepet): misafir/üye sepeti, adet sınırları, düşen ürünler ve birleştirme

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Görev 9: Sipariş servisi ve ödeme simülasyonu (`app/siparis/servis.py`, `app/siparis/odeme_sim.py`)

**Files:**
- Create (Görev 1 oluşturmadıysa): `app/siparis/__init__.py` (boş)
- Create: `app/siparis/servis.py`
- Create: `app/siparis/odeme_sim.py`
- Test: `tests/test_siparis.py`, `tests/test_odeme_sim.py`

**Interfaces:**
- Consumes:
  - `app.fiyat.kurallar`: `Baglam`, `MusteriTipi`, `TeslimYontemi`, `sepet_hesapla(kalemler, b, teslim, kur_eur_try) -> SepetTutari` (TRY tahsilatta kur None -> `KurYok("kur_yok")`, `KurYok(ValueError)`, K5) (Görev 3)
  - `app.fiyat.kur.Kur(tarih, eur_alis, eur_satis)` (Görev 4)
  - `app.para.yuvarla` (Görev 2)
  - `app.hesap.servis`: `Musteri`, `Adres`, `musteri_getir` (Görev 7)
  - `app.sepet.servis`: `kalemler`, `bosalt`, `sepet_bul`, `ekle`, `adet_ayarla` (Görev 8)
  - fixture `con`, `simdi`; yardımcı `urun_ekle` (Görev 1)
- Produces (Görev 10, 13, 14, 15 kullanır):
  - `SiparisDurumu`, `IZINLI_GECISLER` (değerler `frozenset`), `ODEME_SURESI = timedelta(minutes=30)`, `ISTANBUL = ZoneInfo("Europe/Istanbul")`, `GecersizGecis`, `SepetBos`, `SiparisKalemi`, `Siparis`
  - `siparis_olustur(con, musteri, sepet_id, teslim, teslimat, fatura, kur, simdi) -> Siparis` — numaradaki gün `simdi.astimezone(ISTANBUL)` tarihidir (K15); `kur` yalnız TRY tahsilatta yazılır (EUR'da `kur`, `kur_tarihi` None); adresler JSON (`dataclasses.asdict`) olarak saklanır; `kargo` = `kargo_net`
  - `siparis_getir`, `siparis_no_ile`, `musteri_siparisleri` (yeniden eskiye), `tum_siparisler` (yeniden eskiye) — hepsi önce zaman aşımı uygular
  - `durum_degistir(con, siparis_id, yeni, simdi) -> Siparis` — izinsiz -> `GecersizGecis`; sipariş yoksa `LookupError`
  - `zaman_asimi_uygula(con, siparis_id, simdi) -> None` — `olusturma + 30 dk < simdi` ise iptal (tam 30 dk'da henüz değil)
  - `odeme_sim`: `BASARILI_KART`, `RET_KARTI`, `SMS_KODU`, `OdemeSonucu`, `kart_normalize`, `odeme_baslat`, `sms_dogrula`, `deneme_getir(con, islem_anahtari) -> sqlite3.Row | None` (K13) — aynı anahtar başka siparişe aitse veya anahtar bilinmiyorsa `SIPARIS_GECERSIZ`; `gecersiz_kart` kaydında `kart_son4` NULL; boş `islem_anahtari` -> `ValueError`

- [ ] **Step 1: Sipariş servisi için başarısız testi yaz**

`tests/test_siparis.py`:

```python
import itertools
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.fiyat.kur import Kur
from app.fiyat.kurallar import KurYok, MusteriTipi, TeslimYontemi
from app.hesap.servis import Adres, musteri_getir
from app.sepet.servis import adet_ayarla, ekle, sepet_bul
from app.siparis.servis import (
    IZINLI_GECISLER,
    ODEME_SURESI,
    GecersizGecis,
    SepetBos,
    SiparisDurumu,
    durum_degistir,
    musteri_siparisleri,
    siparis_getir,
    siparis_no_ile,
    siparis_olustur,
    tum_siparisler,
    zaman_asimi_uygula,
)
from tests.conftest import urun_ekle

D = SiparisDurumu
KUR = Kur(tarih=date(2026, 10, 13), eur_alis=Decimal("48.00"), eur_satis=Decimal("48.50"))
ADRES_TR = Adres(ad_soyad="QATestUser", satir1="Demo Cad. 1", sehir="Kocaeli", ulke="TR", posta_kodu="41400")
ADRES_DE = Adres(ad_soyad="QATestUser GmbH", satir1="Demostr. 1", sehir="Berlin", ulke="DE", posta_kodu="10115")
_sayac = itertools.count(1)


def musteri(con, simdi, tip=MusteriTipi.BIREYSEL, ulke="TR"):
    mid = con.execute(
        "INSERT INTO musteri (tip, ad, eposta, parola_ozeti, ulke, kvkk_onay, olusturma) "
        "VALUES (?, 'QATestUser', ?, 'x', ?, ?, ?)",
        (tip.value, f"qa.siparis{next(_sayac)}@example.com", ulke, simdi.isoformat(), simdi.isoformat()),
    ).lastrowid
    return musteri_getir(con, mid)


def dolu_sepet(con, m, simdi, fiyat="100.00", adet=2):
    uid = urun_ekle(con, sku=f"S{next(_sayac)}", ad="Röle", fiyat=fiyat, kdv="20")
    sid = sepet_bul(con, None, m.id, simdi)
    ekle(con, sid, uid, adet)
    return sid, uid


def yeni_siparis(con, simdi, m=None):
    m = m or musteri(con, simdi)
    sid, _ = dolu_sepet(con, m, simdi)
    return siparis_olustur(con, m, sid, TeslimYontemi.KARGO, ADRES_TR, ADRES_TR, KUR, simdi)


def test_siparis_olustur_anlik_goruntu(con, simdi):
    m = musteri(con, simdi)
    sid, uid = dolu_sepet(con, m, simdi)
    sku = con.execute("SELECT sku FROM urun WHERE id = ?", (uid,)).fetchone()[0]
    s = siparis_olustur(con, m, sid, TeslimYontemi.KARGO, ADRES_TR, ADRES_TR, KUR, simdi)
    assert s.durum is D.ODEME_BEKLIYOR and s.para_birimi == "TRY"
    # 100,00 € x 2 x 48,50 = 9.700,00 ₺ ; KDV 1.940,00 ; kargo 15 € x 48,50 = 727,50 + KDV 145,50
    assert (s.ara_toplam, s.kdv, s.kargo, s.toplam) == (
        Decimal("9700.00"), Decimal("2085.50"), Decimal("727.50"), Decimal("12513.00"),
    )
    assert s.kur == Decimal("48.50") and s.kur_tarihi == date(2026, 10, 13) and s.ihracat_istisnasi is False
    assert s.teslim_yontemi is TeslimYontemi.KARGO and s.teslimat_ulkesi == "TR"
    assert s.teslimat_adresi == ADRES_TR and s.fatura_adresi == ADRES_TR
    assert (s.musteri_id, s.sepet_id, s.olusturma, s.kart_son4) == (m.id, sid, simdi, None)
    assert len(s.kalemler) == 1
    k = s.kalemler[0]
    assert (k.urun_id, k.sku, k.ad, k.adet, k.birim_net_eur, k.net, k.kdv, k.brut, k.tedarik_teyit) == (
        uid, sku, "Röle", 2, Decimal("100.00"), Decimal("9700.00"), Decimal("1940.00"), Decimal("11640.00"), False,
    )
    # sepet ve ürün sonradan değişse de sipariş değişmez
    adet_ayarla(con, sid, uid, 5)
    con.execute("UPDATE urun SET temsili_fiyat_eur = '999.00', ad = 'Değişti' WHERE id = ?", (uid,))
    assert siparis_getir(con, s.id, simdi) == s


def test_yurtdisi_eur_kur_yazilmaz(con, simdi):
    m = musteri(con, simdi, MusteriTipi.YURTDISI, "DE")
    sid, _ = dolu_sepet(con, m, simdi)
    s = siparis_olustur(con, m, sid, TeslimYontemi.YURTDISI_DAP, ADRES_DE, ADRES_DE, KUR, simdi)
    assert s.para_birimi == "EUR" and s.kur is None and s.kur_tarihi is None
    assert s.ihracat_istisnasi is True and s.teslimat_ulkesi == "DE"
    assert (s.kdv, s.kargo, s.toplam) == (Decimal("0"), Decimal("0"), Decimal("200.00"))


def test_try_tahsilatta_kur_yoksa_hata(con, simdi):
    m = musteri(con, simdi)
    sid, _ = dolu_sepet(con, m, simdi)
    with pytest.raises(KurYok):                       # K5: KurYok(ValueError)
        siparis_olustur(con, m, sid, TeslimYontemi.KARGO, ADRES_TR, ADRES_TR, None, simdi)
    assert issubclass(KurYok, ValueError)
    assert con.execute("SELECT COUNT(*) FROM siparis").fetchone()[0] == 0


def test_siparis_no_ve_gun_ici_sira(con, simdi):
    m = musteri(con, simdi)
    sid, _ = dolu_sepet(con, m, simdi)
    s1 = siparis_olustur(con, m, sid, TeslimYontemi.KARGO, ADRES_TR, ADRES_TR, KUR, simdi)
    s2 = siparis_olustur(con, m, sid, TeslimYontemi.KARGO, ADRES_TR, ADRES_TR, KUR, simdi + timedelta(hours=1))
    s3 = siparis_olustur(con, m, sid, TeslimYontemi.KARGO, ADRES_TR, ADRES_TR, KUR, simdi + timedelta(days=1))
    assert (s1.no, s2.no, s3.no) == ("CR-DEMO-20261013-0001", "CR-DEMO-20261013-0002", "CR-DEMO-20261014-0001")
    assert siparis_no_ile(con, s2.no, simdi + timedelta(hours=1)) == s2
    assert siparis_no_ile(con, "CR-DEMO-YOK", simdi) is None
    baska = yeni_siparis(con, simdi)
    assert [x.no for x in musteri_siparisleri(con, m.id, simdi)] == [s3.no, s2.no, s1.no]
    assert [x.no for x in tum_siparisler(con, simdi)] == [baska.no, s3.no, s2.no, s1.no]
    assert musteri_siparisleri(con, 99999, simdi) == []


def test_siparis_no_tarihi_istanbul_saati(con):
    gece = datetime(2026, 10, 12, 22, 30, tzinfo=UTC)          # İstanbul'da 13.10.2026 01:30
    s = yeni_siparis(con, gece)
    assert s.no == "CR-DEMO-20261013-0001"
    s2 = yeni_siparis(con, datetime(2026, 10, 13, 9, 0, tzinfo=UTC))
    assert s2.no == "CR-DEMO-20261013-0002"                    # aynı İstanbul günü, sıra devam eder


def test_bos_sepet(con, simdi):
    m = musteri(con, simdi)
    sid = sepet_bul(con, None, m.id, simdi)
    with pytest.raises(SepetBos):
        siparis_olustur(con, m, sid, TeslimYontemi.KARGO, ADRES_TR, ADRES_TR, KUR, simdi)
    p = urun_ekle(con, sku="PASIF")
    ekle(con, sid, p)
    con.execute("UPDATE urun SET aktif = 0 WHERE id = ?", (p,))
    with pytest.raises(SepetBos):                     # yalnız düşen ürün varsa da boş sayılır
        siparis_olustur(con, m, sid, TeslimYontemi.KARGO, ADRES_TR, ADRES_TR, KUR, simdi)


def test_izinli_gecis_tablosu():
    assert IZINLI_GECISLER == {
        D.ODEME_BEKLIYOR: {D.ODENDI, D.IPTAL},
        D.ODENDI: {D.HAZIRLANIYOR, D.IPTAL},
        D.HAZIRLANIYOR: {D.KARGODA},
        D.KARGODA: {D.TESLIM},
        D.TESLIM: set(),
        D.IPTAL: set(),
    }
    assert ODEME_SURESI == timedelta(minutes=30)


IZINLI = [(a, b) for a, hedefler in IZINLI_GECISLER.items() for b in sorted(hedefler)]
IZINSIZ = [
    (D.ODEME_BEKLIYOR, D.HAZIRLANIYOR), (D.ODEME_BEKLIYOR, D.TESLIM), (D.ODENDI, D.ODEME_BEKLIYOR),
    (D.ODENDI, D.TESLIM), (D.ODENDI, D.ODENDI), (D.HAZIRLANIYOR, D.IPTAL), (D.KARGODA, D.HAZIRLANIYOR),
    (D.TESLIM, D.IPTAL), (D.IPTAL, D.ODENDI), (D.IPTAL, D.ODEME_BEKLIYOR),
]


@pytest.mark.parametrize("eski,yeni", IZINLI, ids=[f"{a}-{b}" for a, b in IZINLI])
def test_izinli_gecis(con, simdi, eski, yeni):
    s = yeni_siparis(con, simdi)
    con.execute("UPDATE siparis SET durum = ? WHERE id = ?", (eski.value, s.id))
    sonra = simdi + timedelta(minutes=5)
    assert durum_degistir(con, s.id, yeni, sonra).durum is yeni
    assert con.execute("SELECT guncelleme FROM siparis WHERE id = ?", (s.id,)).fetchone()[0] == sonra.isoformat()


@pytest.mark.parametrize("eski,yeni", IZINSIZ, ids=[f"{a}-{b}" for a, b in IZINSIZ])
def test_izinsiz_gecis(con, simdi, eski, yeni):
    s = yeni_siparis(con, simdi)
    con.execute("UPDATE siparis SET durum = ? WHERE id = ?", (eski.value, s.id))
    with pytest.raises(GecersizGecis):
        durum_degistir(con, s.id, yeni, simdi)
    assert siparis_getir(con, s.id, simdi).durum is eski


def test_durum_degistir_olmayan_siparis(con, simdi):
    with pytest.raises(LookupError):
        durum_degistir(con, 99999, D.ODENDI, simdi)


def test_zaman_asimi(con, simdi):
    m = musteri(con, simdi)
    s = yeni_siparis(con, simdi, m)
    assert siparis_getir(con, s.id, simdi + timedelta(minutes=29)).durum is D.ODEME_BEKLIYOR
    assert siparis_getir(con, s.id, simdi + ODEME_SURESI).durum is D.ODEME_BEKLIYOR
    assert siparis_getir(con, s.id, simdi + timedelta(minutes=31)).durum is D.IPTAL
    # sepet korunur
    assert con.execute("SELECT COUNT(*) FROM sepet_kalemi WHERE sepet_id = ?", (s.sepet_id,)).fetchone()[0] == 1
    # ödenmiş sipariş zaman aşımına uğramaz
    s2 = siparis_olustur(con, m, s.sepet_id, TeslimYontemi.KARGO, ADRES_TR, ADRES_TR, KUR, simdi)
    durum_degistir(con, s2.id, D.ODENDI, simdi + timedelta(minutes=1))
    zaman_asimi_uygula(con, s2.id, simdi + timedelta(hours=2))
    assert siparis_getir(con, s2.id, simdi + timedelta(hours=2)).durum is D.ODENDI
    assert siparis_getir(con, 99999, simdi) is None
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `bash dagitim/test-vm.sh tests/test_siparis.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.siparis.servis'`

- [ ] **Step 3: Sipariş servisini yaz**

`app/siparis/servis.py`:

```python
"""Sipariş: sepetten anlık görüntü, sipariş numarası, durum makinesi, 30 dk zaman aşımı. Commit yapmaz."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from app.fiyat.kur import Kur
from app.fiyat.kurallar import Baglam, TeslimYontemi, sepet_hesapla
from app.hesap.servis import Adres, Musteri
from app.para import yuvarla
from app.sepet import servis as sepet_servis


class SiparisDurumu(StrEnum):
    ODEME_BEKLIYOR = "odeme_bekliyor"
    ODENDI = "odendi"
    HAZIRLANIYOR = "hazirlaniyor"
    KARGODA = "kargoda"
    TESLIM = "teslim"
    IPTAL = "iptal"


_D = SiparisDurumu
IZINLI_GECISLER: dict[SiparisDurumu, frozenset[SiparisDurumu]] = {
    _D.ODEME_BEKLIYOR: frozenset({_D.ODENDI, _D.IPTAL}),
    _D.ODENDI: frozenset({_D.HAZIRLANIYOR, _D.IPTAL}),
    _D.HAZIRLANIYOR: frozenset({_D.KARGODA}),
    _D.KARGODA: frozenset({_D.TESLIM}),
    _D.TESLIM: frozenset(),
    _D.IPTAL: frozenset(),
}
ODEME_SURESI = timedelta(minutes=30)
ISTANBUL = ZoneInfo("Europe/Istanbul")


class GecersizGecis(Exception):
    pass


class SepetBos(Exception):
    pass


@dataclass(frozen=True)
class SiparisKalemi:
    urun_id: int
    sku: str
    ad: str
    adet: int
    birim_net_eur: Decimal
    net: Decimal
    kdv: Decimal
    brut: Decimal
    tedarik_teyit: bool


@dataclass(frozen=True)
class Siparis:
    id: int
    no: str
    musteri_id: int
    durum: SiparisDurumu
    para_birimi: str
    ara_toplam: Decimal
    kdv: Decimal
    kargo: Decimal
    toplam: Decimal
    kur: Decimal | None
    kur_tarihi: date | None
    ihracat_istisnasi: bool
    teslim_yontemi: TeslimYontemi
    teslimat_ulkesi: str
    teslimat_adresi: Adres
    fatura_adresi: Adres
    kart_son4: str | None
    sepet_id: int
    olusturma: datetime
    kalemler: tuple[SiparisKalemi, ...]


def _para(x: Decimal) -> str:
    return str(yuvarla(x))


def _yeni_no(con: sqlite3.Connection, simdi: datetime) -> str:
    onek = f"CR-DEMO-{simdi.astimezone(ISTANBUL):%Y%m%d}-"      # K15: gün İstanbul saatine göre
    son = con.execute(
        "SELECT MAX(CAST(substr(no, ?) AS INTEGER)) FROM siparis WHERE no LIKE ?",
        (len(onek) + 1, onek + "%"),
    ).fetchone()[0]
    return f"{onek}{(son or 0) + 1:04d}"


def _adres(metin: str) -> Adres:
    return Adres(**json.loads(metin))


def _siparis(con: sqlite3.Connection, r: sqlite3.Row) -> Siparis:
    kalemler = tuple(
        SiparisKalemi(
            urun_id=k["urun_id"], sku=k["sku"], ad=k["ad"], adet=k["adet"],
            birim_net_eur=Decimal(k["birim_net_eur"]), net=Decimal(k["net"]), kdv=Decimal(k["kdv"]),
            brut=Decimal(k["brut"]), tedarik_teyit=bool(k["tedarik_teyit"]),
        )
        for k in con.execute("SELECT * FROM siparis_kalemi WHERE siparis_id = ? ORDER BY rowid", (r["id"],))
    )
    return Siparis(
        id=r["id"], no=r["no"], musteri_id=r["musteri_id"], durum=SiparisDurumu(r["durum"]),
        para_birimi=r["para_birimi"], ara_toplam=Decimal(r["ara_toplam"]), kdv=Decimal(r["kdv"]),
        kargo=Decimal(r["kargo"]), toplam=Decimal(r["toplam"]),
        kur=Decimal(r["kur"]) if r["kur"] is not None else None,
        kur_tarihi=date.fromisoformat(r["kur_tarihi"]) if r["kur_tarihi"] is not None else None,
        ihracat_istisnasi=bool(r["ihracat_istisnasi"]), teslim_yontemi=TeslimYontemi(r["teslim_yontemi"]),
        teslimat_ulkesi=r["teslimat_ulkesi"], teslimat_adresi=_adres(r["teslimat_adresi"]),
        fatura_adresi=_adres(r["fatura_adresi"]), kart_son4=r["kart_son4"], sepet_id=r["sepet_id"],
        olusturma=datetime.fromisoformat(r["olusturma"]), kalemler=kalemler,
    )


def zaman_asimi_uygula(con: sqlite3.Connection, siparis_id: int, simdi: datetime) -> None:
    r = con.execute("SELECT durum, olusturma FROM siparis WHERE id = ?", (siparis_id,)).fetchone()
    if r is None or r["durum"] != _D.ODEME_BEKLIYOR:
        return
    if datetime.fromisoformat(r["olusturma"]) + ODEME_SURESI < simdi:
        con.execute(
            "UPDATE siparis SET durum = ?, guncelleme = ? WHERE id = ? AND durum = ?",
            (_D.IPTAL.value, simdi.isoformat(), siparis_id, _D.ODEME_BEKLIYOR.value),
        )


def siparis_getir(con: sqlite3.Connection, siparis_id: int, simdi: datetime) -> Siparis | None:
    zaman_asimi_uygula(con, siparis_id, simdi)
    r = con.execute("SELECT * FROM siparis WHERE id = ?", (siparis_id,)).fetchone()
    return _siparis(con, r) if r is not None else None


def siparis_no_ile(con: sqlite3.Connection, no: str, simdi: datetime) -> Siparis | None:
    r = con.execute("SELECT id FROM siparis WHERE no = ?", (no,)).fetchone()
    return siparis_getir(con, r["id"], simdi) if r is not None else None


def musteri_siparisleri(con: sqlite3.Connection, musteri_id: int, simdi: datetime) -> list[Siparis]:
    idler = [r["id"] for r in con.execute(
        "SELECT id FROM siparis WHERE musteri_id = ? ORDER BY id DESC", (musteri_id,)
    )]
    return [siparis_getir(con, i, simdi) for i in idler]


def tum_siparisler(con: sqlite3.Connection, simdi: datetime) -> list[Siparis]:
    idler = [r["id"] for r in con.execute("SELECT id FROM siparis ORDER BY id DESC")]
    return [siparis_getir(con, i, simdi) for i in idler]


def siparis_olustur(
    con: sqlite3.Connection, musteri: Musteri, sepet_id: int, teslim: TeslimYontemi,
    teslimat: Adres, fatura: Adres, kur: Kur | None, simdi: datetime,
) -> Siparis:
    kalem_listesi, _dusen = sepet_servis.kalemler(con, sepet_id)
    if not kalem_listesi:
        raise SepetBos(sepet_id)
    ulke = teslimat.ulke.strip().upper()
    teslim = TeslimYontemi(teslim)
    tutar = sepet_hesapla(
        kalem_listesi, Baglam(musteri_tipi=musteri.tip, teslimat_ulkesi=ulke), teslim,
        kur.eur_satis if kur is not None else None,
    )
    kur_kullanildi = tutar.kur is not None and kur is not None
    an = simdi.isoformat()
    cur = con.execute(
        "INSERT INTO siparis (no, musteri_id, durum, para_birimi, ara_toplam, kdv, kargo, toplam, kur, "
        "kur_tarihi, ihracat_istisnasi, teslim_yontemi, teslimat_ulkesi, teslimat_adresi, fatura_adresi, "
        "kart_son4, sepet_id, olusturma, guncelleme) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)",
        (
            _yeni_no(con, simdi), musteri.id, _D.ODEME_BEKLIYOR.value, tutar.para_birimi,
            _para(tutar.ara_toplam), _para(tutar.kdv), _para(tutar.kargo_net), _para(tutar.toplam),
            str(tutar.kur) if kur_kullanildi else None, kur.tarih.isoformat() if kur_kullanildi else None,
            int(tutar.ihracat_istisnasi), teslim.value, ulke,
            json.dumps(asdict(teslimat), ensure_ascii=False), json.dumps(asdict(fatura), ensure_ascii=False),
            sepet_id, an, an,
        ),
    )
    siparis_id = cur.lastrowid
    for satir in tutar.satirlar:
        k = satir.kalem
        con.execute(
            "INSERT INTO siparis_kalemi (siparis_id, urun_id, sku, ad, adet, birim_net_eur, net, kdv, brut, "
            "tedarik_teyit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                siparis_id, k.urun_id, k.sku, k.ad, k.adet, str(k.birim_net_eur),
                _para(satir.net), _para(satir.kdv), _para(satir.brut), int(k.tedarik_teyit),
            ),
        )
    return siparis_getir(con, siparis_id, simdi)


def durum_degistir(con: sqlite3.Connection, siparis_id: int, yeni: SiparisDurumu, simdi: datetime) -> Siparis:
    zaman_asimi_uygula(con, siparis_id, simdi)
    r = con.execute("SELECT durum FROM siparis WHERE id = ?", (siparis_id,)).fetchone()
    if r is None:
        raise LookupError(siparis_id)
    eski = SiparisDurumu(r["durum"])
    try:
        hedef = SiparisDurumu(yeni)
    except ValueError:
        raise GecersizGecis(f"{eski}->{yeni}") from None
    if hedef not in IZINLI_GECISLER[eski]:
        raise GecersizGecis(f"{eski}->{hedef}")
    con.execute(
        "UPDATE siparis SET durum = ?, guncelleme = ? WHERE id = ?",
        (hedef.value, simdi.isoformat(), siparis_id),
    )
    return siparis_getir(con, siparis_id, simdi)
```

- [ ] **Step 4: Sipariş testlerinin geçtiğini gör**

Run: `bash dagitim/test-vm.sh tests/test_siparis.py -q`
Expected: PASS (0 failed)

- [ ] **Step 5: Ödeme simülasyonu için başarısız testi yaz**

`tests/test_odeme_sim.py`:

```python
import itertools
from datetime import date, timedelta
from decimal import Decimal

from app.fiyat.kur import Kur
from app.fiyat.kurallar import TeslimYontemi
from app.hesap.servis import Adres, musteri_getir
from app.sepet.servis import ekle, sepet_bul
from app.siparis.odeme_sim import (
    BASARILI_KART,
    RET_KARTI,
    SMS_KODU,
    OdemeSonucu,
    deneme_getir,
    kart_normalize,
    odeme_baslat,
    sms_dogrula,
)
from app.siparis.servis import SiparisDurumu, siparis_getir, siparis_olustur
from tests.conftest import urun_ekle

O = OdemeSonucu
KUR = Kur(tarih=date(2026, 10, 13), eur_alis=Decimal("48.00"), eur_satis=Decimal("48.50"))
ADRES = Adres(ad_soyad="QATestUser", satir1="Demo Cad. 1", sehir="Kocaeli", ulke="TR")
_sayac = itertools.count(1)


def hazir_siparis(con, simdi):
    n = next(_sayac)
    mid = con.execute(
        "INSERT INTO musteri (tip, ad, eposta, parola_ozeti, ulke, kvkk_onay, olusturma) "
        "VALUES ('bireysel', 'QATestUser', ?, 'x', 'TR', ?, ?)",
        (f"qa.odeme{n}@example.com", simdi.isoformat(), simdi.isoformat()),
    ).lastrowid
    uid = urun_ekle(con, sku=f"OD{n}", ad="Röle", fiyat="100.00")
    sid = sepet_bul(con, None, mid, simdi)
    ekle(con, sid, uid, 1)
    return siparis_olustur(con, musteri_getir(con, mid), sid, TeslimYontemi.KARGO, ADRES, ADRES, KUR, simdi)


def tum_satirlar(con):
    metin = ""
    for tablo in ("odeme_denemesi", "siparis", "siparis_kalemi", "sepet_kalemi"):
        for r in con.execute(f"SELECT * FROM {tablo}"):
            metin += str(tuple(r))
    return metin


def deneme_sayisi(con):
    return con.execute("SELECT COUNT(*) FROM odeme_denemesi").fetchone()[0]


def sepet_adedi(con, sepet_id):
    return con.execute("SELECT COUNT(*) FROM sepet_kalemi WHERE sepet_id = ?", (sepet_id,)).fetchone()[0]


def test_kart_normalize():
    assert kart_normalize("4111 1111-1111 1111") == BASARILI_KART
    assert kart_normalize(" 4000-0000-0000-0002 ") == RET_KARTI
    assert kart_normalize("abc") == ""
    assert (BASARILI_KART, RET_KARTI, SMS_KODU) == ("4111111111111111", "4000000000000002", "000000")


def test_test_karti_disi_reddedilir_ve_saklanmaz(con, simdi):
    s = hazir_siparis(con, simdi)
    assert odeme_baslat(con, s.id, "a1", "5555 4444 3333 1111", simdi) is O.GECERSIZ_KART
    assert odeme_baslat(con, s.id, "a2", "4111 1111 1111 1112", simdi) is O.GECERSIZ_KART
    r = con.execute("SELECT * FROM odeme_denemesi WHERE islem_anahtari = 'a1'").fetchone()
    assert (r["durum"], r["kart_son4"], r["kart_sonucu"]) == ("gecersiz_kart", None, None)
    metin = tum_satirlar(con)
    assert "5555444433331111" not in metin and "5555 4444 3333 1111" not in metin
    assert "4111111111111112" not in metin
    assert siparis_getir(con, s.id, simdi).durum is SiparisDurumu.ODEME_BEKLIYOR


def test_bosluklu_tireli_kart_normalize_edilir(con, simdi):
    s = hazir_siparis(con, simdi)
    assert odeme_baslat(con, s.id, "b1", "4111-1111 1111-1111", simdi) is O.SMS_BEKLIYOR
    r = con.execute("SELECT * FROM odeme_denemesi WHERE islem_anahtari = 'b1'").fetchone()
    assert (r["durum"], r["kart_son4"], r["kart_sonucu"]) == ("sms_bekliyor", "1111", "basarili")
    assert r["olusturma"] == simdi.isoformat()
    assert BASARILI_KART not in tum_satirlar(con)


def test_deneme_getir(con, simdi):
    s = hazir_siparis(con, simdi)
    assert deneme_getir(con, "yok") is None
    odeme_baslat(con, s.id, "g1", BASARILI_KART, simdi)
    d = deneme_getir(con, "g1")
    assert (d["islem_anahtari"], d["siparis_id"], d["durum"], d["kart_son4"]) == ("g1", s.id, "sms_bekliyor", "1111")
    sms_dogrula(con, "g1", SMS_KODU, simdi)
    assert deneme_getir(con, "g1")["durum"] == "basarili"


def test_ayni_anahtar_idempotent(con, simdi):
    s = hazir_siparis(con, simdi)
    assert odeme_baslat(con, s.id, "k1", BASARILI_KART, simdi) is O.SMS_BEKLIYOR
    assert odeme_baslat(con, s.id, "k1", RET_KARTI, simdi) is O.SMS_BEKLIYOR
    assert deneme_sayisi(con) == 1
    r = con.execute("SELECT kart_sonucu FROM odeme_denemesi WHERE islem_anahtari = 'k1'").fetchone()
    assert r["kart_sonucu"] == "basarili"
    assert sms_dogrula(con, "k1", SMS_KODU, simdi) is O.BASARILI
    assert odeme_baslat(con, s.id, "k1", BASARILI_KART, simdi) is O.BASARILI
    assert sms_dogrula(con, "k1", SMS_KODU, simdi) is O.BASARILI
    assert deneme_sayisi(con) == 1
    baska = hazir_siparis(con, simdi)
    assert odeme_baslat(con, baska.id, "k1", BASARILI_KART, simdi) is O.SIPARIS_GECERSIZ
    assert sms_dogrula(con, "bilinmeyen", SMS_KODU, simdi) is O.SIPARIS_GECERSIZ


def test_sms_hatali(con, simdi):
    s = hazir_siparis(con, simdi)
    odeme_baslat(con, s.id, "h1", BASARILI_KART, simdi)
    assert sms_dogrula(con, "h1", "123456", simdi) is O.SMS_HATALI
    assert sms_dogrula(con, "h1", SMS_KODU, simdi) is O.SMS_HATALI      # deneme bitti
    assert siparis_getir(con, s.id, simdi).durum is SiparisDurumu.ODEME_BEKLIYOR
    assert odeme_baslat(con, s.id, "h2", BASARILI_KART, simdi) is O.SMS_BEKLIYOR
    assert sms_dogrula(con, "h2", f" {SMS_KODU} ", simdi) is O.BASARILI


def test_ret_sonrasi_yeni_anahtarla_basarili(con, simdi):
    s = hazir_siparis(con, simdi)
    assert odeme_baslat(con, s.id, "r1", "4000 0000 0000 0002", simdi) is O.SMS_BEKLIYOR
    assert sms_dogrula(con, "r1", SMS_KODU, simdi) is O.RET
    g = siparis_getir(con, s.id, simdi)
    assert g.durum is SiparisDurumu.ODEME_BEKLIYOR and g.kart_son4 is None
    assert sepet_adedi(con, s.sepet_id) == 1
    assert odeme_baslat(con, s.id, "r2", BASARILI_KART, simdi + timedelta(minutes=2)) is O.SMS_BEKLIYOR
    assert sms_dogrula(con, "r2", SMS_KODU, simdi + timedelta(minutes=3)) is O.BASARILI
    g = siparis_getir(con, s.id, simdi + timedelta(minutes=3))
    assert g.durum is SiparisDurumu.ODENDI and g.kart_son4 == "1111"
    assert sepet_adedi(con, s.sepet_id) == 0
    metin = tum_satirlar(con)
    assert BASARILI_KART not in metin and RET_KARTI not in metin
    assert odeme_baslat(con, s.id, "r3", BASARILI_KART, simdi + timedelta(minutes=4)) is O.ZATEN_ODENDI
    assert deneme_sayisi(con) == 2                                       # r3 kaydedilmez


def test_zaman_asimi_sonrasi_deneme(con, simdi):
    s = hazir_siparis(con, simdi)
    assert odeme_baslat(con, s.id, "t1", BASARILI_KART, simdi + timedelta(minutes=31)) is O.SIPARIS_GECERSIZ
    assert siparis_getir(con, s.id, simdi + timedelta(minutes=31)).durum is SiparisDurumu.IPTAL
    assert odeme_baslat(con, 99999, "t2", BASARILI_KART, simdi) is O.SIPARIS_GECERSIZ
    s2 = hazir_siparis(con, simdi)
    assert odeme_baslat(con, s2.id, "t3", BASARILI_KART, simdi + timedelta(minutes=25)) is O.SMS_BEKLIYOR
    assert sms_dogrula(con, "t3", SMS_KODU, simdi + timedelta(minutes=31)) is O.SIPARIS_GECERSIZ
    assert siparis_getir(con, s2.id, simdi + timedelta(minutes=31)).durum is SiparisDurumu.IPTAL
```

- [ ] **Step 6: Testin başarısız olduğunu gör**

Run: `bash dagitim/test-vm.sh tests/test_odeme_sim.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.siparis.odeme_sim'`

- [ ] **Step 7: Ödeme simülasyonunu yaz**

`app/siparis/odeme_sim.py`:

```python
"""Sahte kart + 3D Secure. Yalnız test kartları kabul edilir; tam kart numarası hiçbir yere yazılmaz."""
from __future__ import annotations

import hmac
import sqlite3
from datetime import datetime
from enum import StrEnum

from app.sepet.servis import bosalt
from app.siparis.servis import SiparisDurumu, durum_degistir, zaman_asimi_uygula

BASARILI_KART = "4111111111111111"
RET_KARTI = "4000000000000002"
SMS_KODU = "000000"


class OdemeSonucu(StrEnum):
    SMS_BEKLIYOR = "sms_bekliyor"
    BASARILI = "basarili"
    RET = "ret"
    SMS_HATALI = "sms_hatali"
    GECERSIZ_KART = "gecersiz_kart"
    ZATEN_ODENDI = "zaten_odendi"
    SIPARIS_GECERSIZ = "siparis_gecersiz"


def kart_normalize(kart_no: str) -> str:
    return "".join(ch for ch in (kart_no or "") if ch in "0123456789")


def deneme_getir(con: sqlite3.Connection, islem_anahtari: str) -> sqlite3.Row | None:
    """K13: 3D rotası deneme kaydını (siparis_id, durum, kart_son4...) buradan okur."""
    return con.execute("SELECT * FROM odeme_denemesi WHERE islem_anahtari = ?", (islem_anahtari,)).fetchone()


def _siparis_engeli(con: sqlite3.Connection, siparis_id: int, simdi: datetime) -> OdemeSonucu | None:
    zaman_asimi_uygula(con, siparis_id, simdi)
    r = con.execute("SELECT durum FROM siparis WHERE id = ?", (siparis_id,)).fetchone()
    if r is None or r["durum"] == SiparisDurumu.IPTAL:
        return OdemeSonucu.SIPARIS_GECERSIZ
    if r["durum"] != SiparisDurumu.ODEME_BEKLIYOR:
        return OdemeSonucu.ZATEN_ODENDI
    return None


def odeme_baslat(
    con: sqlite3.Connection, siparis_id: int, islem_anahtari: str, kart_no: str, simdi: datetime
) -> OdemeSonucu:
    if not islem_anahtari:
        raise ValueError("islem_anahtari")
    onceki = con.execute(
        "SELECT siparis_id, durum FROM odeme_denemesi WHERE islem_anahtari = ?", (islem_anahtari,)
    ).fetchone()
    if onceki is not None:
        if onceki["siparis_id"] != siparis_id:
            return OdemeSonucu.SIPARIS_GECERSIZ
        return OdemeSonucu(onceki["durum"])
    engel = _siparis_engeli(con, siparis_id, simdi)
    if engel is not None:
        return engel
    kart = kart_normalize(kart_no)
    if kart == BASARILI_KART:
        kart_sonucu = "basarili"
    elif kart == RET_KARTI:
        kart_sonucu = "ret"
    else:
        con.execute(
            "INSERT INTO odeme_denemesi (islem_anahtari, siparis_id, kart_son4, kart_sonucu, durum, olusturma) "
            "VALUES (?, ?, NULL, NULL, ?, ?)",
            (islem_anahtari, siparis_id, OdemeSonucu.GECERSIZ_KART.value, simdi.isoformat()),
        )
        return OdemeSonucu.GECERSIZ_KART
    con.execute(
        "INSERT INTO odeme_denemesi (islem_anahtari, siparis_id, kart_son4, kart_sonucu, durum, olusturma) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (islem_anahtari, siparis_id, kart[-4:], kart_sonucu, OdemeSonucu.SMS_BEKLIYOR.value, simdi.isoformat()),
    )
    return OdemeSonucu.SMS_BEKLIYOR


def _deneme_bitir(con: sqlite3.Connection, islem_anahtari: str, sonuc: OdemeSonucu) -> OdemeSonucu:
    con.execute("UPDATE odeme_denemesi SET durum = ? WHERE islem_anahtari = ?", (sonuc.value, islem_anahtari))
    return sonuc


def sms_dogrula(con: sqlite3.Connection, islem_anahtari: str, sms_kodu: str, simdi: datetime) -> OdemeSonucu:
    d = con.execute(
        "SELECT siparis_id, durum, kart_son4, kart_sonucu FROM odeme_denemesi WHERE islem_anahtari = ?",
        (islem_anahtari,),
    ).fetchone()
    if d is None:
        return OdemeSonucu.SIPARIS_GECERSIZ
    if d["durum"] != OdemeSonucu.SMS_BEKLIYOR:
        return OdemeSonucu(d["durum"])
    engel = _siparis_engeli(con, d["siparis_id"], simdi)
    if engel is not None:
        return engel
    if not hmac.compare_digest((sms_kodu or "").strip().encode("utf-8"), SMS_KODU.encode("utf-8")):
        return _deneme_bitir(con, islem_anahtari, OdemeSonucu.SMS_HATALI)
    if d["kart_sonucu"] != "basarili":
        return _deneme_bitir(con, islem_anahtari, OdemeSonucu.RET)
    _deneme_bitir(con, islem_anahtari, OdemeSonucu.BASARILI)
    durum_degistir(con, d["siparis_id"], SiparisDurumu.ODENDI, simdi)
    con.execute("UPDATE siparis SET kart_son4 = ? WHERE id = ?", (d["kart_son4"], d["siparis_id"]))
    sepet_id = con.execute("SELECT sepet_id FROM siparis WHERE id = ?", (d["siparis_id"],)).fetchone()[0]
    bosalt(con, sepet_id)
    return OdemeSonucu.BASARILI
```

- [ ] **Step 8: Testlerin geçtiğini gör**

Run: `bash dagitim/test-vm.sh tests/test_siparis.py tests/test_odeme_sim.py -q`
Expected: PASS (0 failed)

Run: `bash dagitim/test-vm.sh tests -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add app/siparis/__init__.py app/siparis/servis.py app/siparis/odeme_sim.py tests/test_siparis.py tests/test_odeme_sim.py
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m "feat(siparis): anlık görüntülü sipariş, durum makinesi, zaman aşımı ve ödeme simülasyonu

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Görev 10: Teklif ve geri bildirim servisleri (`app/teklif/servis.py`, `app/geribildirim/servis.py`)

**Files:**
- Create (Görev 1 oluşturmadıysa): `app/teklif/__init__.py`, `app/geribildirim/__init__.py` (boş)
- Create: `app/teklif/servis.py`
- Create: `app/geribildirim/servis.py`
- Test: `tests/test_teklif.py`, `tests/test_geribildirim.py`

**Interfaces:**
- Consumes:
  - `app.siparis.servis.GecersizGecis`, `ISTANBUL` (Görev 9)
  - fixture `con`, `simdi`; yardımcı `urun_ekle` (Görev 1)
- Produces (Görev 13, 15 kullanır):
  - `TEKLIF_GECISLERI`, `TeklifGirdisi`, `Teklif`, `TeklifHatasi(alan, kod)` (`.alan`, `.kod`)
  - `teklif_olustur(con, g, simdi) -> Teklif` — numaradaki gün İstanbul saatine göre (K15); hata kodları: `("ad"|"eposta"|"ulke"|"mesaj","zorunlu")`, `("eposta","gecersiz")`, `("mesaj","cok_uzun")` (>2000), `("adet","gecersiz")` (1..9999 dışı), `("urun_id","gecersiz")`, `("musteri_id","gecersiz")` (kayıt yok); boş `firma`/`telefon` -> None; `ulke` büyük harfe çevrilir
  - `teklifler(con, musteri_id=None) -> list[Teklif]` (yeniden eskiye)
  - `teklif_durum_degistir(con, teklif_id, yeni) -> Teklif` — izinsiz/bilinmeyen durum -> `GecersizGecis`; teklif yoksa `LookupError`
  - `geribildirim.servis`: `DURUMLAR`, `kaydet(con, sayfa, metin, isim, simdi) -> int` (metin 1..2000, sayfa 1..500, isim ≤100 karakter, kırpılmış; ihlal -> `ValueError`), `listele(con, durum=None) -> list[sqlite3.Row]` (yeniden eskiye; bilinmeyen durum -> `ValueError`), `durum_degistir(con, gb_id, durum) -> None` (geçersiz durum -> `ValueError`; kayıt yoksa `LookupError`)

- [ ] **Step 1: Teklif için başarısız testi yaz**

`tests/test_teklif.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest

from app.siparis.servis import GecersizGecis
from app.teklif.servis import (
    TEKLIF_GECISLERI,
    Teklif,
    TeklifGirdisi,
    TeklifHatasi,
    teklif_durum_degistir,
    teklif_olustur,
    teklifler,
)
from tests.conftest import urun_ekle


def girdi(**kw):
    alanlar = dict(ad="QATestUser", eposta="qa.teklif@example.com", ulke="TR", mesaj="KR C4 için fiyat istiyoruz.")
    alanlar.update(kw)
    return TeklifGirdisi(**alanlar)


def teklif_sayisi(con):
    return con.execute("SELECT COUNT(*) FROM teklif").fetchone()[0]


def test_teklif_no_ve_alanlar(con, simdi):
    uid = urun_ekle(
        con, sku="8301033800019", ad="KUKA KRC5 KR 140 R3200-2 PA", kok="Endüstriyel Robotlar",
        teklif=True, fiyat="20000.00",
    )
    t1 = teklif_olustur(con, girdi(urun_id=uid, adet=2, firma=" QATest Ltd ", telefon="", ulke="de"), simdi)
    t2 = teklif_olustur(con, girdi(), simdi + timedelta(hours=2))
    t3 = teklif_olustur(con, girdi(), simdi + timedelta(days=1))
    assert (t1.no, t2.no, t3.no) == ("CR-TKL-20261013-0001", "CR-TKL-20261013-0002", "CR-TKL-20261014-0001")
    assert isinstance(t1, Teklif)
    assert (t1.urun_id, t1.urun_ad, t1.adet) == (uid, "KUKA KRC5 KR 140 R3200-2 PA", 2)
    assert (t1.firma, t1.telefon, t1.ulke, t1.durum, t1.olusturma) == ("QATest Ltd", None, "DE", "yeni", simdi)
    assert (t1.ad, t1.eposta, t1.mesaj, t1.musteri_id) == ("QATestUser", "qa.teklif@example.com", "KR C4 için fiyat istiyoruz.", None)
    assert (t2.urun_id, t2.urun_ad, t2.adet) == (None, None, 1)


def test_teklif_no_tarihi_istanbul_saati(con):
    gece = datetime(2026, 10, 12, 22, 30, tzinfo=UTC)          # İstanbul'da 13.10.2026 01:30
    assert teklif_olustur(con, girdi(), gece).no == "CR-TKL-20261013-0001"


@pytest.mark.parametrize(
    "alan,deger,kod",
    [
        ("ad", "  ", "zorunlu"), ("eposta", "", "zorunlu"), ("eposta", "qa.example.com", "gecersiz"),
        ("mesaj", " \n ", "zorunlu"), ("ulke", "", "zorunlu"), ("adet", 0, "gecersiz"),
        ("adet", 10000, "gecersiz"), ("urun_id", 99999, "gecersiz"), ("musteri_id", 99999, "gecersiz"),
    ],
)
def test_teklif_hatalari(con, simdi, alan, deger, kod):
    with pytest.raises(TeklifHatasi) as e:
        teklif_olustur(con, girdi(**{alan: deger}), simdi)
    assert (e.value.alan, e.value.kod) == (alan, kod)
    assert teklif_sayisi(con) == 0


def test_mesaj_2000_siniri(con, simdi):
    assert len(teklif_olustur(con, girdi(mesaj="x" * 2000), simdi).mesaj) == 2000
    with pytest.raises(TeklifHatasi) as e:
        teklif_olustur(con, girdi(mesaj="x" * 2001), simdi)
    assert (e.value.alan, e.value.kod) == ("mesaj", "cok_uzun")
    assert teklif_sayisi(con) == 1


def test_teklifler_musteri_filtresi(con, simdi):
    mid = con.execute(
        "INSERT INTO musteri (tip, ad, eposta, parola_ozeti, ulke, kvkk_onay, olusturma) "
        "VALUES ('kurumsal', 'QATestUser Ltd', 'qa.tk@example.com', 'x', 'TR', ?, ?)",
        (simdi.isoformat(), simdi.isoformat()),
    ).lastrowid
    t1 = teklif_olustur(con, girdi(musteri_id=mid), simdi)
    t2 = teklif_olustur(con, girdi(), simdi)
    t3 = teklif_olustur(con, girdi(musteri_id=mid), simdi)
    assert [t.id for t in teklifler(con, mid)] == [t3.id, t1.id]
    assert [t.id for t in teklifler(con)] == [t3.id, t2.id, t1.id]
    assert teklifler(con, 99999) == []
    assert teklifler(con, mid)[0].musteri_id == mid


def test_teklif_gecis_tablosu():
    assert TEKLIF_GECISLERI == {
        "yeni": {"inceleniyor", "kapandi"},
        "inceleniyor": {"teklif_verildi", "kapandi"},
        "teklif_verildi": {"kapandi"},
        "kapandi": set(),
    }


IZINLI = [(a, b) for a, hedefler in TEKLIF_GECISLERI.items() for b in sorted(hedefler)]
IZINSIZ = [
    ("yeni", "teklif_verildi"), ("yeni", "yeni"), ("inceleniyor", "yeni"), ("teklif_verildi", "inceleniyor"),
    ("kapandi", "yeni"), ("kapandi", "inceleniyor"), ("yeni", "bilinmeyen"),
]


@pytest.mark.parametrize("eski,yeni", IZINLI)
def test_teklif_izinli_gecis(con, simdi, eski, yeni):
    t = teklif_olustur(con, girdi(), simdi)
    con.execute("UPDATE teklif SET durum = ? WHERE id = ?", (eski, t.id))
    assert teklif_durum_degistir(con, t.id, yeni).durum == yeni


@pytest.mark.parametrize("eski,yeni", IZINSIZ)
def test_teklif_izinsiz_gecis(con, simdi, eski, yeni):
    t = teklif_olustur(con, girdi(), simdi)
    con.execute("UPDATE teklif SET durum = ? WHERE id = ?", (eski, t.id))
    with pytest.raises(GecersizGecis):
        teklif_durum_degistir(con, t.id, yeni)
    assert con.execute("SELECT durum FROM teklif WHERE id = ?", (t.id,)).fetchone()[0] == eski


def test_teklif_yok(con):
    with pytest.raises(LookupError):
        teklif_durum_degistir(con, 99999, "inceleniyor")
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

Run: `bash dagitim/test-vm.sh tests/test_teklif.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.teklif.servis'`

- [ ] **Step 3: Teklif servisini yaz**

`app/teklif/servis.py`:

```python
"""Teklif isteği: kayıt, numara, listeleme ve yönetici durum geçişleri. Commit yapmaz."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from app.siparis.servis import ISTANBUL, GecersizGecis

TEKLIF_GECISLERI: dict[str, set[str]] = {
    "yeni": {"inceleniyor", "kapandi"},
    "inceleniyor": {"teklif_verildi", "kapandi"},
    "teklif_verildi": {"kapandi"},
    "kapandi": set(),
}
MESAJ_MAX = 2000
ADET_MAX = 9999

_TEKLIF_SQL = "SELECT t.*, u.ad AS urun_ad FROM teklif t LEFT JOIN urun u ON u.id = t.urun_id"


@dataclass(frozen=True)
class TeklifGirdisi:
    ad: str
    eposta: str
    ulke: str
    mesaj: str
    firma: str | None = None
    telefon: str | None = None
    urun_id: int | None = None
    adet: int = 1
    musteri_id: int | None = None


@dataclass(frozen=True)
class Teklif:
    id: int
    no: str
    ad: str
    firma: str | None
    eposta: str
    telefon: str | None
    ulke: str
    urun_id: int | None
    urun_ad: str | None
    adet: int
    mesaj: str
    durum: str
    olusturma: datetime
    musteri_id: int | None


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


def _teklif(r: sqlite3.Row) -> Teklif:
    return Teklif(
        id=r["id"], no=r["no"], ad=r["ad"], firma=r["firma"], eposta=r["eposta"], telefon=r["telefon"],
        ulke=r["ulke"], urun_id=r["urun_id"], urun_ad=r["urun_ad"], adet=r["adet"], mesaj=r["mesaj"],
        durum=r["durum"], olusturma=datetime.fromisoformat(r["olusturma"]), musteri_id=r["musteri_id"],
    )


def _teklif_getir(con: sqlite3.Connection, teklif_id: int) -> Teklif | None:
    r = con.execute(_TEKLIF_SQL + " WHERE t.id = ?", (teklif_id,)).fetchone()
    return _teklif(r) if r is not None else None


def teklif_olustur(con: sqlite3.Connection, g: TeklifGirdisi, simdi: datetime) -> Teklif:
    ad = _zorunlu("ad", g.ad)
    eposta = _zorunlu("eposta", g.eposta)
    if "@" not in eposta:
        raise TeklifHatasi("eposta", "gecersiz")
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
    cur = con.execute(
        "INSERT INTO teklif (no, musteri_id, ad, firma, eposta, telefon, ulke, urun_id, adet, mesaj, durum, "
        "olusturma) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'yeni', ?)",
        (
            _yeni_no(con, simdi), g.musteri_id, ad, _temiz(g.firma), eposta, _temiz(g.telefon), ulke,
            g.urun_id, g.adet, mesaj, simdi.isoformat(),
        ),
    )
    return _teklif_getir(con, cur.lastrowid)


def teklifler(con: sqlite3.Connection, musteri_id: int | None = None) -> list[Teklif]:
    if musteri_id is None:
        satirlar = con.execute(_TEKLIF_SQL + " ORDER BY t.id DESC").fetchall()
    else:
        satirlar = con.execute(_TEKLIF_SQL + " WHERE t.musteri_id = ? ORDER BY t.id DESC", (musteri_id,)).fetchall()
    return [_teklif(r) for r in satirlar]


def teklif_durum_degistir(con: sqlite3.Connection, teklif_id: int, yeni: str) -> Teklif:
    r = con.execute("SELECT durum FROM teklif WHERE id = ?", (teklif_id,)).fetchone()
    if r is None:
        raise LookupError(teklif_id)
    eski = r["durum"]
    if yeni not in TEKLIF_GECISLERI.get(eski, set()):
        raise GecersizGecis(f"{eski}->{yeni}")
    con.execute("UPDATE teklif SET durum = ? WHERE id = ?", (yeni, teklif_id))
    return _teklif_getir(con, teklif_id)
```

- [ ] **Step 4: Teklif testlerinin geçtiğini gör**

Run: `bash dagitim/test-vm.sh tests/test_teklif.py -q`
Expected: PASS (0 failed)

- [ ] **Step 5: Geri bildirim için başarısız testi yaz**

`tests/test_geribildirim.py`:

```python
from datetime import timedelta

import pytest

from app.geribildirim.servis import DURUMLAR, durum_degistir, kaydet, listele


def test_kaydet_ve_listele(con, simdi):
    i1 = kaydet(con, "/tr/urun/5", "  Fiyat görünmüyor  ", " QATestUser ", simdi)
    i2 = kaydet(con, "/tr/", "Arama yavaş", "", simdi + timedelta(minutes=1))
    satirlar = listele(con)
    assert [r["id"] for r in satirlar] == [i2, i1]
    eski = satirlar[1]
    assert (eski["sayfa"], eski["metin"], eski["isim"], eski["durum"], eski["olusturma"]) == (
        "/tr/urun/5", "Fiyat görünmüyor", "QATestUser", "yeni", simdi.isoformat(),
    )
    assert satirlar[0]["isim"] is None
    assert DURUMLAR == ("yeni", "okundu", "yapildi")


@pytest.mark.parametrize("metin", ["", "   ", "\n\t", None])
def test_bos_metin(con, simdi, metin):
    with pytest.raises(ValueError):
        kaydet(con, "/tr/", metin, None, simdi)


def test_metin_2000_siniri(con, simdi):
    kaydet(con, "/tr/", "x" * 2000, None, simdi)
    with pytest.raises(ValueError):
        kaydet(con, "/tr/", "x" * 2001, None, simdi)
    assert len(listele(con)) == 1


def test_sayfa_500_siniri(con, simdi):
    kaydet(con, "/" + "a" * 499, "metin", None, simdi)
    for sayfa in ["/" + "a" * 500, "", "   ", None]:
        with pytest.raises(ValueError):
            kaydet(con, sayfa, "metin", None, simdi)
    assert len(listele(con)) == 1


def test_isim_100_siniri(con, simdi):
    kaydet(con, "/tr/", "metin", "i" * 100, simdi)
    with pytest.raises(ValueError):
        kaydet(con, "/tr/", "metin", "i" * 101, simdi)


def test_listele_durum_filtresi(con, simdi):
    i1 = kaydet(con, "/tr/", "bir", None, simdi)
    i2 = kaydet(con, "/tr/", "iki", None, simdi)
    durum_degistir(con, i1, "okundu")
    assert [r["id"] for r in listele(con, "okundu")] == [i1]
    assert [r["id"] for r in listele(con, "yeni")] == [i2]
    assert listele(con, "yapildi") == []
    with pytest.raises(ValueError):
        listele(con, "gecersiz")


@pytest.mark.parametrize("durum", ["silindi", "", "YENI"])
def test_durum_degistir_gecersiz(con, simdi, durum):
    i = kaydet(con, "/tr/", "metin", None, simdi)
    with pytest.raises(ValueError):
        durum_degistir(con, i, durum)
    assert listele(con)[0]["durum"] == "yeni"


def test_durum_degistir_olmayan_kayit(con):
    with pytest.raises(LookupError):
        durum_degistir(con, 99999, "okundu")
```

- [ ] **Step 6: Testin başarısız olduğunu gör**

Run: `bash dagitim/test-vm.sh tests/test_geribildirim.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.geribildirim.servis'`

- [ ] **Step 7: Geri bildirim servisini yaz**

`app/geribildirim/servis.py`:

```python
"""Site içi geri bildirim kaydı ve yönetici durum takibi. Commit yapmaz."""
from __future__ import annotations

import sqlite3
from datetime import datetime

DURUMLAR = ("yeni", "okundu", "yapildi")
METIN_MAX = 2000
SAYFA_MAX = 500
ISIM_MAX = 100


def kaydet(con: sqlite3.Connection, sayfa: str, metin: str, isim: str | None, simdi: datetime) -> int:
    metin = (metin or "").strip()
    if not 1 <= len(metin) <= METIN_MAX:
        raise ValueError("metin")
    sayfa = (sayfa or "").strip()
    if not 1 <= len(sayfa) <= SAYFA_MAX:
        raise ValueError("sayfa")
    isim = (isim or "").strip() or None
    if isim is not None and len(isim) > ISIM_MAX:
        raise ValueError("isim")
    return con.execute(
        "INSERT INTO geri_bildirim (sayfa, metin, isim, durum, olusturma) VALUES (?, ?, ?, 'yeni', ?)",
        (sayfa, metin, isim, simdi.isoformat()),
    ).lastrowid


def listele(con: sqlite3.Connection, durum: str | None = None) -> list[sqlite3.Row]:
    if durum is None:
        return con.execute("SELECT * FROM geri_bildirim ORDER BY id DESC").fetchall()
    if durum not in DURUMLAR:
        raise ValueError("durum")
    return con.execute("SELECT * FROM geri_bildirim WHERE durum = ? ORDER BY id DESC", (durum,)).fetchall()


def durum_degistir(con: sqlite3.Connection, gb_id: int, durum: str) -> None:
    if durum not in DURUMLAR:
        raise ValueError("durum")
    if con.execute("UPDATE geri_bildirim SET durum = ? WHERE id = ?", (durum, gb_id)).rowcount == 0:
        raise LookupError(gb_id)
```

- [ ] **Step 8: Testlerin geçtiğini gör**

Run: `bash dagitim/test-vm.sh tests/test_teklif.py tests/test_geribildirim.py -q`
Expected: PASS (0 failed)

Run: `bash dagitim/test-vm.sh tests -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add app/teklif/__init__.py app/teklif/servis.py app/geribildirim/__init__.py app/geribildirim/servis.py tests/test_teklif.py tests/test_geribildirim.py
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m "feat(teklif, geribildirim): teklif kaydı ve durum geçişleri, geri bildirim servisi

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Entegrasyon durumu

- K5: Görev 9 testi `KurYok` yakalıyor (`ValueError` alt sınıfı olduğu da doğrulanıyor).
- K6: yerel `indeksle` kaldırıldı; testler `urun_ekle(uretici_kodu=, gorsel_url=, tedarik_suresi_gun=)` ve `indeksi_yeniden_kur` kullanıyor.
- K7: bütün testler `from tests.conftest import ...` kullanıyor.
- K13: `odeme_sim.deneme_getir` ve testi eklendi.
- K15: sipariş ve teklif numarası İstanbul gününü kullanıyor; 12.10 22:30 UTC -> 20261013 testi var.
- K16: VKN 4728136592 geçerli, 4728136593 geçersiz testlere eklendi.
- K17: hesap kuralları ve hata kodları Görev 7 ile tutarlı; `KayitHatasi.alan` / `.kod` mevcut (Görev 13 ile uyumlu).
- K20: odeme_sim davranışı zaten uygulanmıştı, testlerle kontrol ediliyor.
- K21: `siparis_olustur` düşen ürünleri sessizce siliyor; bildirim Görev 14'te.

---

## Görevler C — web çekirdeği, katalog ekranları, hesap ekranları (Görev 11–13)

Bu bölüm "Ortak arayüz sözleşmesi"ndeki web imzalarına, URL listesine, şablon sözleşmesine, tema tokenlarına ve CSP'ye birebir uyar. Testler VM'de çalışır: `bash dagitim/test-vm.sh tests/<dosya> -q`.

**Bu bölümün getirdiği ortak kurallar (sonraki görevler de uyar):**
- Dil önekli rotalar `/{dil:dil}/...` biçiminde yazılır. `dil` dönüştürücüsü `app/web/dil.py` içinde kayıtlıdır ve yalnız `tr|en` eşleşir. Böylece `/xx/...` doğal olarak 404 olur ve `/yonetim/giris` gibi yollar `/{dil}/giris` tarafından yutulmaz.
- Her rota modülü `router = APIRouter()` dışa aktarır. `uygulama_olustur` modülleri `ROTA_SIRASI` ile kendisi yükler; diğer görevler `uygulama.py`'yi değiştirmez.
- Şablon üreten her rota `con=Depends(db_bagimliligi)` alır (`from app.web.bagimlilik import db_bagimliligi`; K9). `db_bagimliligi`, bağlantıyı `request.state.con`'a da koyar; `sablon()` ortak değişkenleri (müşteri, sepet sayacı, kur) buradan okur.
- Çeviri anahtarları `bolum.anahtar` biçimindedir. `bolum` ekran ya da bileşen adıdır (`genel`, `nav`, `alt`, `gb`, `cerez`, `hata`, `hata_kodu`, `fiyat`, `katalog`, `urun`, `durum`, `hesap`, `siparis_durum`, `teklif_durum`, `ulke`, `dil`). `anahtar` küçük harf ASCII ve `_`'dır; tek istisna `ulke.TR` gibi ISO kodlarıdır. Değerler `{ad}` biçiminde yer tutucu alabilir (`str.format` anlamıyla doldurulur). Servis hata kodlarının metinleri `hata_kodu.<kod>` altındadır (K14); her görev yalnız kendi kodlarını ekler. `tr.json` ile `en.json` aynı anahtar kümesine sahip olmalıdır; `test_ceviri_dosyalari_esit` bunu her görevde denetler. Sonraki görevler kendi bölümlerini ekler (`sepet`, `odeme`, `teklif`, `yasal`, `yonetim`).
- Dil öneki olmayan yollarda (`/yonetim...`, `/geri-bildirim`, `/saglik`) şablon dili `"tr"`dir (K9). Yönetim şablonları `taban.html`'i genişletir ve `{% block baslik %}` / `{% block icerik %}` bloklarını doldurur.
- `data-e2e` öznitelikleri Görev 18'deki seçici tablosuna birebir uyar; bu bölümün ekranlarına düşenler: `urun-baglanti`, `fiyat-ana` (+`data-para`, `data-kdv`), `fiyat-ikincil`, `sepete-ekle`, `teklif-iste`, `cikis`, `kayit-gonder`, `gb-tamam`.
- Web testleri `tests/conftest.py`'deki şu yardımcıları kullanır: `istemci`, `csrf_al`, `istemci_db`, `oturum_oku`, `oturum_yaz`, `sayfa_denetle`. HTML sayfa döndüren her yeni rota testinde `sayfa_denetle(yanit)` çağrılır. Bu çağrı güvenlik başlıklarını, DEMO bandını ve satır içi script/style/olay özniteliği yokluğunu denetler.

---

### Görev 11: Web çekirdeği (uygulama, güvenlik, dil, bağlam, taban şablon, tema, JS)

**Files:**
- Modify: `tests/conftest.py` (dosya sonuna web yardımcıları)
- Create: `app/web/__init__.py`, `app/web/bagimlilik.py`, `app/web/uygulama.py`, `app/web/guvenlik.py`, `app/web/dil.py`, `app/web/baglam.py`
- Create: `app/web/rotalar/__init__.py`, `app/web/rotalar/genel.py`
- Create: `app/web/dil/tr.json`, `app/web/dil/en.json`
- Create: `app/web/sablonlar/taban.html`, `app/web/sablonlar/_makrolar.html`, `app/web/sablonlar/hata.html`
- Create: `app/web/statik/site.css`, `app/web/statik/site.js`
- Create: `app/web/statik/yer-tutucu/robot.svg`, `elektrik.svg`, `mekanik.svg`, `genel.svg`
- Test: `tests/test_web_cekirdek.py`

**Interfaces:**
- Consumes: `app.ayarlar.Ayarlar`, `app.db.baglan/gecisleri_uygula` (`baglan` `check_same_thread=False` ile açar — K8, Görev 1), `app.para.d/yuvarla`, `app.metin.normalize`, `app.fiyat.kurallar.{Baglam, MusteriTipi, birim_fiyat_gosterimi, kdv_uygulanir, bantlari_oku}`, `app.fiyat.kur.{son_kur, kur_bayat_mi}`, `app.hesap.servis.{Musteri, musteri_getir, parola_ozeti}`, `app.sepet.servis.adet_toplam`, `app.esitleme.esitle.son_basarili_esitleme`; testte `tests.conftest.urun_ekle`.
- Produces (sözleşmedekilere ek olarak):
  - `app.web.bagimlilik`: `db_bagimliligi(request) -> Iterator[sqlite3.Connection]` (rota modülleri buradan alır; `app.web.uygulama` yeniden dışa aktarır).
  - `app.web.uygulama`: `WEB: Path`, `ROTA_SIRASI = ("genel", "yonetim", "yasal", "katalog", "hesap", "sepet_odeme", "teklif_gb")`. Uvicorn fabrikası bu görevde YOK: `app/web/asgi.py` Görev 17'dedir (K10).
  - `app.web.dil`: `DilConvertor` (yol dönüştürücüsü `dil`), `Ceviri.var(anahtar) -> bool`.
  - `app.web.baglam`: `ULKELER: tuple[str, ...]`, `YASAL_SAYFALAR`, `simdi() -> datetime`, `dil_bul(request) -> str`, `ulke_tercihi(request) -> str`, `mevcut_sepet_id(con, request, musteri) -> int | None` (sepet oluşturmaz), `bildir(request, anahtar, **degerler) -> None` (flash), `yer_tutucu(kok_kategori_ad) -> str`, `gorsel_adresi(urun, gorsel_kok) -> str`, `kur_bicimle(kur, dil) -> str`, `tarih_bicimle(z, dil) -> str`, `hata_yaniti(request, durum, kimlik=None, db=True, basliklar=None) -> Response`.
  - Şablon ortak değişkenleri: `dil, diller, t, csrf, musteri, sepet_adet, ulke, ulkeler, para(tutar, para_birimi), fiyat_goster(urun) -> FiyatGosterim, kdv_var, kur, kur_metni, kur_tarihi, kur_bayat, istek_yolu, yasal_sayfalar, cerez_onay, yer_tutucu, gorsel_adresi(urun), tarih(z), bildirimler, arama_q`.
  - Çerezler: `cr_oturum` (oturum), `dil`, `ulke`, `cerez_onay`. Oturum anahtarları: `oid`, `csrf`, `mid`, `ulke`, `bildirimler`.
  - `tests/conftest.py`: `istemci` fixture, `csrf_al`, `istemci_db`, `oturum_oku`, `oturum_yaz`, `sayfa_denetle`, `TEST_GIZLI`.

- [ ] **Step 1: Web test yardımcılarını `tests/conftest.py` sonuna ekle**

```python
# ---------------------------------------------------------------------------
# Web testleri (Görev 11)
# ---------------------------------------------------------------------------
import base64
import json
import re
from contextlib import contextmanager

from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner

from app.ayarlar import Ayarlar
from app.db import baglan as _baglan
from app.hesap.servis import parola_ozeti as _parola_ozeti

TEST_GIZLI = "t" * 32


@pytest.fixture
def istemci(tmp_path):
    from app.web.uygulama import uygulama_olustur

    ayarlar = Ayarlar(
        db_yolu=tmp_path / "web.db",
        gizli_anahtar=TEST_GIZLI,
        yonetici_kullanici="yonetici",
        yonetici_parola_ozeti=_parola_ozeti("yonetici-parola-123"),
    )
    with TestClient(uygulama_olustur(ayarlar)) as c:
        yield c


_CSRF_DESENI = re.compile(r'name="csrf" value="([^"]+)"')


def csrf_al(istemci, yol: str) -> str:
    """Sayfayı açar ve sayfadaki ilk csrf gizli alanının değerini döner."""
    yanit = istemci.get(yol)
    eslesme = _CSRF_DESENI.search(yanit.text)
    assert eslesme, f"{yol} sayfasında csrf alanı yok (durum {yanit.status_code})"
    return eslesme.group(1)


@contextmanager
def istemci_db(istemci):
    """Uygulamanın kullandığı veritabanına bağlanır; blok sonunda commit + close."""
    con = _baglan(istemci.app.state.ayarlar.db_yolu)
    try:
        with con:
            yield con
    finally:
        con.close()


def oturum_oku(istemci) -> dict:
    """Starlette imzalı oturum çerezini çözer (test için)."""
    deger = None
    for cerez in istemci.cookies.jar:
        if cerez.name == "cr_oturum":
            deger = cerez.value
    if not deger:
        return {}
    ham = TimestampSigner(TEST_GIZLI).unsign(deger.strip('"').encode())
    return json.loads(base64.b64decode(ham))


def oturum_yaz(istemci, veri: dict) -> None:
    """Geçerli imzalı bir oturum çerezi üretir; yalnız yeni istemcide, ilk istekten önce kullanılır."""
    deger = TimestampSigner(TEST_GIZLI).sign(base64.b64encode(json.dumps(veri).encode())).decode()
    istemci.cookies.set("cr_oturum", deger)


_SATIR_ICI_SCRIPT = re.compile(r"<script(?![^>]*\bsrc\s*=)[^>]*>", re.I)
_STIL_OZNITELIGI = re.compile(r"\sstyle\s*=", re.I)
_OLAY_OZNITELIGI = re.compile(r"<[^>]+\son[a-z]+\s*=", re.I)


def sayfa_denetle(yanit) -> str:
    """HTML yanıtın ortak kurallarını denetler ve gövdeyi döner."""
    from app.web.guvenlik import GUVENLIK_BASLIKLARI

    for anahtar, deger in GUVENLIK_BASLIKLARI.items():
        assert yanit.headers.get(anahtar) == deger, anahtar
    html = yanit.text
    assert 'class="demo-bandi"' in html, "DEMO bandı yok"
    assert not _SATIR_ICI_SCRIPT.search(html), "satır içi <script> var"
    assert not _STIL_OZNITELIGI.search(html), 'style="" özniteliği var'
    assert "<style" not in html.lower(), "<style> etiketi var"
    assert not _OLAY_OZNITELIGI.search(html), "on*= olay özniteliği var"
    return html
```

- [ ] **Step 2: Başarısız testleri yaz — `tests/test_web_cekirdek.py`**

```python
import re
from decimal import Decimal

import pytest
from fastapi import Depends, Request
from fastapi.testclient import TestClient

from app.web import uygulama as uygulama_modulu
from app.web.baglam import para_bicimle, sablon, yer_tutucu
from app.web.dil import Ceviri
from app.web.guvenlik import GUVENLIK_BASLIKLARI, HizSiniri, guvenli_sonraki
from app.web.bagimlilik import db_bagimliligi
from tests.conftest import csrf_al, istemci_db, oturum_oku, oturum_yaz, sayfa_denetle, urun_ekle


@pytest.fixture
def prob(istemci):
    """Görev 11'de katalog sayfası henüz yok: taban.html'i tam yığından geçiren deneme rotası."""

    @istemci.app.get("/{dil:dil}/_prob")
    def _prob(request: Request, dil: str, con=Depends(db_bagimliligi)):
        return sablon(request, "hata.html", {"durum": 200, "baslik": "Prob", "aciklama": "prob", "hata_kimligi": None})

    return "/tr/_prob"


def _basliklari_denetle(yanit):
    for anahtar, deger in GUVENLIK_BASLIKLARI.items():
        assert yanit.headers.get(anahtar) == deger, (yanit.url, anahtar)


def test_guvenlik_basliklari_her_yanitta(istemci, prob):
    yanitlar = [
        istemci.get("/saglik"),
        istemci.get("/", follow_redirects=False),
        istemci.get("/statik/site.css"),
        istemci.get("/statik/yer-tutucu/robot.svg"),
        istemci.get("/tr/boyle-bir-sayfa-yok"),
        istemci.get(prob),
    ]
    for y in yanitlar:
        _basliklari_denetle(y)
    assert GUVENLIK_BASLIKLARI["X-Robots-Tag"] == "noindex, nofollow"
    assert "script-src 'self'" in GUVENLIK_BASLIKLARI["Content-Security-Policy"]


def test_sayfada_satir_ici_script_ve_stil_yok(istemci, prob):
    html = sayfa_denetle(istemci.get(prob))
    assert '<script src="/statik/site.js" defer></script>' in html
    assert 'href="/statik/site.css"' in html
    assert 'id="gb-dugme"' in html and '<dialog id="gb-pencere"' in html
    assert 'id="cerez-bandi"' in html
    assert 'action="/tercih"' in html
    assert re.search(r'<form class="tercih" action="/tercih"[^>]*>.*?<button type="submit"', html, re.S)


def test_demo_bandi_hata_sayfalarinda_da_var(istemci):
    y404 = istemci.get("/tr/olmayan")
    assert y404.status_code == 404
    assert "DEMO – gerçek satış ve ödeme yapılmaz" in sayfa_denetle(y404)
    y403 = istemci.post("/tercih", data={"dil": "en"}, follow_redirects=False)
    assert y403.status_code == 403
    assert "Oturum süresi doldu, sayfayı yenileyip tekrar deneyin" in sayfa_denetle(y403)


@pytest.mark.parametrize(
    "deger",
    ["https://evil.com", "//evil.com", "/\\evil", "\\\\evil", "javascript:alert(1)", "http:/evil",
     " /tr/", "/tr/\nLocation: x", None, ""],
)
def test_guvenli_sonraki_reddeder(deger):
    assert guvenli_sonraki(deger) == "/"


@pytest.mark.parametrize("deger", ["/tr/sepet", "/en/urun/5?x=1", "/"])
def test_guvenli_sonraki_korur(deger):
    assert guvenli_sonraki(deger) == deger


def test_guvenli_sonraki_varsayilan():
    assert guvenli_sonraki("https://evil.com", "/tr/hesabim") == "/tr/hesabim"


def test_hiz_siniri():
    h = HizSiniri(limit=10, pencere=60.0)
    assert all(h.izin("ip", 100.0 + i) for i in range(10))
    assert h.izin("ip", 110.0) is False
    assert h.izin("baska-ip", 110.0) is True
    assert h.izin("ip", 161.0) is True  # 100 ve 101'deki denemeler pencereden çıktı


def test_csrf_eksik_veya_yanlis_post_403(istemci, prob):
    assert istemci.post("/tercih", data={"dil": "en", "sonraki": "/tr/"}, follow_redirects=False).status_code == 403
    csrf_al(istemci, prob)
    yanit = istemci.post("/tercih", data={"dil": "en", "csrf": "yanlis"}, follow_redirects=False)
    assert yanit.status_code == 403


def test_eski_oturum_misafire_duser(istemci, prob):
    oturum_yaz(istemci, {"mid": 999, "csrf": "x"})
    yanit = istemci.get(prob)
    assert yanit.status_code == 200
    assert 'href="/tr/giris"' in yanit.text
    assert 'action="/tr/cikis"' not in yanit.text

    istemci.cookies.clear()
    istemci.cookies.set("cr_oturum", "bozuk.imza.degeri")
    yanit = istemci.get(prob)
    assert yanit.status_code == 200
    assert 'href="/tr/giris"' in yanit.text


def test_mid_tamsayi_degilse_misafir(istemci, prob):
    oturum_yaz(istemci, {"mid": "abc"})
    yanit = istemci.get(prob)
    assert yanit.status_code == 200
    assert 'href="/tr/giris"' in yanit.text


def test_tercih_dil_degisince_yol_degisir(istemci, prob):
    csrf = csrf_al(istemci, prob)
    yanit = istemci.post(
        "/tercih", data={"csrf": csrf, "dil": "en", "ulke": "TR", "sonraki": "/tr/sepet?x=1"}, follow_redirects=False
    )
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/en/sepet?x=1"
    assert yanit.cookies.get("dil") == "en"
    assert istemci.get("/", follow_redirects=False).headers["location"] == "/en/"


def test_tercih_kokte_dil_onekli_yola_gider(istemci, prob):
    csrf = csrf_al(istemci, prob)
    yanit = istemci.post("/tercih", data={"csrf": csrf, "dil": "en", "sonraki": "/"}, follow_redirects=False)
    assert yanit.headers["location"] == "/en/"


def test_tercih_ulke_oturuma_ve_cereze_yazilir(istemci, prob):
    csrf = csrf_al(istemci, prob)
    yanit = istemci.post(
        "/tercih", data={"csrf": csrf, "dil": "tr", "ulke": "DE", "sonraki": prob}, follow_redirects=False
    )
    assert yanit.headers["location"] == prob
    assert yanit.cookies.get("ulke") == "DE"
    assert oturum_oku(istemci)["ulke"] == "DE"
    assert '<option value="DE" selected>' in istemci.get(prob).text


def test_tercih_gecersiz_degerler_yok_sayilir(istemci, prob):
    csrf = csrf_al(istemci, prob)
    yanit = istemci.post(
        "/tercih", data={"csrf": csrf, "dil": "xx", "ulke": "XX", "sonraki": "https://evil.com"}, follow_redirects=False
    )
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/"
    assert "ulke" not in oturum_oku(istemci)
    assert "dil" not in yanit.cookies


def test_kok_yonlendirme_varsayilan_tr(istemci):
    yanit = istemci.get("/", follow_redirects=False)
    assert yanit.status_code == 302
    assert yanit.headers["location"] == "/tr/"


@pytest.mark.parametrize(
    ("tutar", "para", "dil", "beklenen"),
    [
        (Decimal("1234.5"), "TRY", "tr", "1.234,50 ₺"),
        (Decimal("1234.5"), "EUR", "tr", "1.234,50 €"),
        (Decimal("1234.5"), "EUR", "en", "€1,234.50"),
        (Decimal("1234.5"), "TRY", "en", "₺1,234.50"),
        (Decimal("1234567.891"), "TRY", "tr", "1.234.567,89 ₺"),
        (Decimal("0"), "TRY", "tr", "0,00 ₺"),
        (Decimal("0.005"), "EUR", "en", "€0.01"),
        (Decimal("-15"), "EUR", "tr", "-15,00 €"),
    ],
)
def test_para_bicimle(tutar, para, dil, beklenen):
    assert para_bicimle(tutar, para, dil) == beklenen


def test_ceviri_eksik_anahtar_tr_ye_sonra_anahtara_duser(tmp_path):
    (tmp_path / "tr.json").write_text(
        '{"a.b": "Merhaba {ad}", "a.yalniz_tr": "Yalnız TR"}', encoding="utf-8"
    )
    (tmp_path / "en.json").write_text('{"a.b": "Hello {ad}", "a.yalniz_en": "Only EN"}', encoding="utf-8")
    c = Ceviri(tmp_path)
    assert c.t("en", "a.b", ad="Ayşe") == "Hello Ayşe"
    assert c.t("en", "a.yalniz_tr") == "Yalnız TR"
    assert c.t("tr", "a.yok") == "a.yok"
    assert c.t("tr", "a.b") == "Merhaba {ad}"
    assert c.t("de", "a.b", ad="X") == "Merhaba X"
    assert c.var("a.b") and not c.var("a.yok")
    assert c.eksik_anahtarlar() == {"tr": ["a.yalniz_en"], "en": ["a.yalniz_tr"]}


def test_ceviri_dosyalari_esit():
    """Sonraki görevler anahtar ekledikçe bu test korunur: tr ve en aynı anahtar kümesine sahip."""
    c = Ceviri(uygulama_modulu.WEB / "dil")
    assert c.eksik_anahtarlar() == {"tr": [], "en": []}
    desen = re.compile(r"^[a-z_]+\.[A-Za-z0-9_]+$")
    for dil in ("tr", "en"):
        for anahtar in c._metinler[dil]:
            assert desen.match(anahtar), anahtar
            assert isinstance(c._metinler[dil][anahtar], str) and c._metinler[dil][anahtar].strip(), anahtar


def test_saglik_json(istemci):
    yanit = istemci.get("/saglik")
    assert yanit.status_code == 200
    assert yanit.json() == {"durum": "ok", "son_esitleme": None, "urun": 0}
    with istemci_db(istemci) as con:
        urun_ekle(con, sku="S1")
        urun_ekle(con, sku="S2", aktif=False)
        con.execute(
            "INSERT INTO esitleme_gunlugu(basla, bitis, durum) VALUES (?, ?, 'tam')",
            ("2026-10-12T02:30:00+00:00", "2026-10-12T02:35:00+00:00"),
        )
    assert istemci.get("/saglik").json() == {"durum": "ok", "son_esitleme": "2026-10-12T02:35:00+00:00", "urun": 1}


def test_404_sayfasi(istemci):
    yanit = istemci.get("/tr/olmayan")
    assert yanit.status_code == 404
    assert '<html lang="tr">' in yanit.text and "Sayfa bulunamadı" in yanit.text
    yanit = istemci.get("/en/olmayan")
    assert yanit.status_code == 404
    assert '<html lang="en">' in yanit.text and "Page not found" in yanit.text
    assert istemci.get("/xx/").status_code == 404


def test_dil_oneksiz_yolda_tr(istemci):
    istemci.cookies.set("dil", "en")
    yanit = istemci.get("/olmayan-oneksiz")
    assert yanit.status_code == 404
    assert '<html lang="tr">' in yanit.text and "Sayfa bulunamadı" in yanit.text


def test_500_hata_kimligi_gosterilir_yigin_izi_gosterilmez(istemci):
    @istemci.app.get("/_patlat")
    def _patlat():
        raise RuntimeError("gizli-yigin-izi")

    c = TestClient(istemci.app, raise_server_exceptions=False)
    yanit = c.get("/_patlat")
    assert yanit.status_code == 500
    _basliklari_denetle(yanit)
    assert re.search(r'<code class="hata-kimligi">[0-9A-F]{8}</code>', yanit.text)
    assert "gizli-yigin-izi" not in yanit.text
    assert "Traceback" not in yanit.text
    assert 'class="demo-bandi"' in yanit.text


@pytest.mark.parametrize(
    ("kok", "dosya"),
    [("Endüstriyel Robotlar", "robot"), ("Pozisyonerler", "robot"), ("GÜÇ KAYNAĞI", "elektrik"),
     ("Elektrik ve Elektronik", "elektrik"), ("ABB REDÜKTÖR", "mekanik"), ("Slider", "mekanik"),
     ("", "genel"), (None, "genel")],
)
def test_yer_tutucu(kok, dosya):
    assert yer_tutucu(kok) == f"/statik/yer-tutucu/{dosya}.svg"


@pytest.mark.parametrize("ad", ["robot", "elektrik", "mekanik", "genel"])
def test_yer_tutucu_dosyalari_sunulur(istemci, ad):
    yanit = istemci.get(f"/statik/yer-tutucu/{ad}.svg")
    assert yanit.status_code == 200
    assert yanit.headers["content-type"].startswith("image/svg+xml")
    assert "<script" not in yanit.text
```

- [ ] **Step 3: Testlerin başarısız olduğunu gör**

Run: `bash dagitim/test-vm.sh tests/test_web_cekirdek.py -q`
Expected: FAIL. Toplama hatası `ModuleNotFoundError: No module named 'app.web'` olur.

- [ ] **Step 4: `app/web/__init__.py`, `app/web/rotalar/__init__.py` ve `app/web/dil.py`**

`app/web/__init__.py` ve `app/web/rotalar/__init__.py`, tek satırlık docstring içeren dosyalardır:

```python
"""Web katmanı."""
```

`app/web/dil.py`:

```python
"""TR/EN arayüz metinleri ve dil yol dönüştürücüsü."""
from __future__ import annotations

import json
from pathlib import Path

from starlette.convertors import Convertor, register_url_convertor

DILLER = ("tr", "en")


class DilConvertor(Convertor):
    """`/{dil:dil}/...` yalnız tr|en ile eşleşir; diğer önekler rotaya hiç düşmez (404)."""

    regex = "tr|en"

    def convert(self, value: str) -> str:
        return value

    def to_string(self, value: str) -> str:
        return str(value)


register_url_convertor("dil", DilConvertor())


class _Eksiksiz(dict):
    """str.format_map ile doldurma; verilmeyen yer tutucu olduğu gibi kalır."""

    def __missing__(self, anahtar: str) -> str:
        return "{" + anahtar + "}"


class Ceviri:
    def __init__(self, klasor: Path) -> None:
        self._metinler: dict[str, dict[str, str]] = {}
        for dil in DILLER:
            dosya = Path(klasor) / f"{dil}.json"
            self._metinler[dil] = json.loads(dosya.read_text(encoding="utf-8")) if dosya.exists() else {}

    def var(self, anahtar: str) -> bool:
        return anahtar in self._metinler["tr"]

    def t(self, dil: str, anahtar: str, **degerler) -> str:
        metin = self._metinler.get(dil, {}).get(anahtar)
        if metin is None:
            metin = self._metinler["tr"].get(anahtar)
        if metin is None:
            return anahtar
        if degerler:
            try:
                metin = metin.format_map(_Eksiksiz(degerler))
            except (ValueError, IndexError):
                pass
        return metin

    def eksik_anahtarlar(self) -> dict[str, list[str]]:
        tr = set(self._metinler["tr"])
        en = set(self._metinler["en"])
        return {"tr": sorted(en - tr), "en": sorted(tr - en)}
```

- [ ] **Step 5: Çeviri dosyası `app/web/dil/tr.json`**

Bu dosya Görev 11–13 ekranlarının bütün anahtarlarını içerir; Görev 12 ve 13 yeni anahtar eklemez.

```json
{
  "genel.site_adi": "Ceylan Robot Mağaza",
  "genel.demo_bandi": "DEMO – gerçek satış ve ödeme yapılmaz",
  "genel.icerige_atla": "İçeriğe atla",
  "genel.ana_sayfa": "Ana sayfa",
  "nav.ara": "Ara",
  "nav.ara_etiket": "Ürün, SKU veya üretici kodu ara",
  "nav.ara_ipucu": "Ürün adı, SKU, üretici kodu",
  "nav.dil": "Dil",
  "nav.ulke": "Ülke",
  "nav.uygula": "Uygula",
  "nav.giris": "Giriş",
  "nav.kayit": "Üye ol",
  "nav.hesabim": "Hesabım",
  "nav.cikis": "Çıkış",
  "nav.sepet": "Sepet",
  "nav.sepet_adet": "Sepette {adet} ürün",
  "nav.teklif": "Teklif iste",
  "alt.yasal_baslik": "Yasal",
  "alt.not": "Bu site bir tasarım prototipidir; fiyatlar temsilidir.",
  "alt.yasal_on_bilgilendirme": "Ön bilgilendirme formu",
  "alt.yasal_mesafeli_satis": "Mesafeli satış sözleşmesi",
  "alt.yasal_iade": "İade ve cayma",
  "alt.yasal_garanti": "Garanti",
  "alt.yasal_kvkk": "KVKK aydınlatma metni",
  "alt.yasal_acik_riza": "Açık rıza",
  "alt.yasal_cerez": "Çerez politikası",
  "alt.yasal_gizlilik": "Gizlilik",
  "alt.yasal_kullanim": "Kullanım koşulları",
  "alt.yasal_kunye": "Künye",
  "dil.tr": "Türkçe",
  "dil.en": "English",
  "ulke.TR": "Türkiye",
  "ulke.DE": "Almanya",
  "ulke.AT": "Avusturya",
  "ulke.NL": "Hollanda",
  "ulke.FR": "Fransa",
  "ulke.IT": "İtalya",
  "ulke.PL": "Polonya",
  "ulke.GB": "Birleşik Krallık",
  "ulke.US": "ABD",
  "ulke.AZ": "Azerbaycan",
  "ulke.SA": "Suudi Arabistan",
  "ulke.AE": "Birleşik Arap Emirlikleri",
  "gb.dugme": "Geri bildirim",
  "gb.baslik": "Bu sayfa hakkında geri bildirim",
  "gb.aciklama": "Sayfa adresi otomatik eklenir.",
  "gb.isim": "Adınız (isteğe bağlı)",
  "gb.metin": "Görüşünüz",
  "gb.gonder": "Gönder",
  "gb.kapat": "Kapat",
  "gb.tamam": "Kaydedildi, teşekkürler.",
  "gb.hata": "Gönderilemedi, lütfen tekrar deneyin.",
  "cerez.metin": "Bu demo yalnız oturum ve tercih için zorunlu çerezler kullanır.",
  "cerez.politika": "Çerez politikası",
  "cerez.kabul": "Anladım",
  "hata.baslik_400": "Geçersiz istek",
  "hata.baslik_403": "İşlem reddedildi",
  "hata.baslik_404": "Sayfa bulunamadı",
  "hata.baslik_405": "İzin verilmeyen yöntem",
  "hata.baslik_429": "Çok fazla deneme",
  "hata.baslik_500": "Beklenmeyen hata",
  "hata.baslik_genel": "Hata",
  "hata.aciklama_403": "Oturum süresi doldu, sayfayı yenileyip tekrar deneyin.",
  "hata.aciklama_404": "Aradığınız sayfa taşınmış ya da hiç var olmamış olabilir.",
  "hata.aciklama_429": "Lütfen bir dakika bekleyip tekrar deneyin.",
  "hata.aciklama_500": "Bir şeyler ters gitti. Sorunu bildirirken aşağıdaki hata kimliğini paylaşın.",
  "hata.aciklama_genel": "İstek işlenemedi.",
  "hata.kimlik": "Hata kimliği",
  "hata.ana_sayfaya": "Ana sayfaya dön",
  "hata_kodu.zorunlu": "Bu alan zorunludur.",
  "hata_kodu.gecersiz": "Bu değer geçersiz.",
  "hata_kodu.gecersiz_vkn": "Vergi kimlik numarası geçersiz (10 haneli VKN veya 11 haneli TCKN girin).",
  "hata_kodu.eposta_kayitli": "Bu e-posta adresiyle zaten bir hesap var.",
  "hata_kodu.parola_kisa": "Parola en az 10 karakter olmalı.",
  "hata_kodu.kvkk_onay_yok": "Devam etmek için aydınlatma metnini onaylayın.",
  "hata_kodu.gecersiz_ulke": "Yurt dışı hesap için Türkiye dışında bir ülke seçin.",
  "hata_kodu.tip_sec": "Müşteri tipini seçin.",
  "fiyat.temsili": "Temsili fiyat",
  "fiyat.temsili_aciklama": "Kaynakta fiyat bulunmadığından gösterim amacıyla üretilmiştir.",
  "fiyat.kdv_dahil": "KDV dahil",
  "fiyat.kdv_haric": "KDV hariç",
  "fiyat.ikincil": "≈ {tutar} (KDV hariç)",
  "fiyat.kur_satiri": "Kur: 1 € = {kur} · {tarih} TCMB satış",
  "fiyat.kur_bayat": "kur güncel değil",
  "katalog.ana_baslik": "Endüstriyel robot ve yedek parça",
  "katalog.ana_alt": "Test edilmiş 2. el robotlar, kontrol üniteleri ve yedek parçalar; Türkiye'ye ve yurt dışına.",
  "katalog.kategoriler": "Kategoriler",
  "katalog.urun_sayisi": "{adet} ürün",
  "katalog.one_cikanlar": "Öne çıkan ürünler",
  "katalog.robot_teklif_baslik": "Robotlar için teklif alın",
  "katalog.robot_teklif_metin": "Endüstriyel robotlar ve 15.000 € üzerindeki ürünler teklifle satılır. İhtiyacınızı yazın, satış ekibimiz dönüş yapsın.",
  "katalog.robot_teklif_dugme": "Teklif iste",
  "katalog.guven_test_baslik": "Test edilmiş 2. el",
  "katalog.guven_test_metin": "2. el ürünlerde test durumu ürün sayfasında belirtilir.",
  "katalog.guven_ihracat_baslik": "İhracat",
  "katalog.guven_ihracat_metin": "Yurt dışı teslimatlarda KDV istisnası ve DAP teslim.",
  "katalog.guven_destek_baslik": "Teknik destek",
  "katalog.guven_destek_metin": "Robot ve kontrol ünitelerinde uzman ekip desteği.",
  "katalog.iz": "Konum",
  "katalog.arama": "Arama",
  "katalog.arama_baslik": "“{q}” için sonuçlar",
  "katalog.arama_bos": "Aramak için ürün adı, SKU veya üretici kodu yazın.",
  "katalog.sonuc_sayisi": "{toplam} ürün",
  "katalog.filtreler": "Filtreler",
  "katalog.filtre_stokta": "Yalnız stoktakiler",
  "katalog.filtre_fiyat": "Fiyat aralığı",
  "katalog.filtre_fmin": "En az (€)",
  "katalog.filtre_fmax": "En çok (€)",
  "katalog.filtre_fiyat_not": "Net EUR, KDV hariç",
  "katalog.siralama": "Sıralama",
  "katalog.sira_ad": "Ada göre",
  "katalog.sira_fiyat_artan": "Fiyat (artan)",
  "katalog.sira_fiyat_azalan": "Fiyat (azalan)",
  "katalog.uygula": "Uygula",
  "katalog.temizle": "Filtreleri temizle",
  "katalog.bos_sonuc": "Bu ölçütlere uyan ürün bulunamadı.",
  "katalog.bos_oneri_filtre": "Filtreleri kaldırmayı deneyin",
  "katalog.bos_oneri_teklif": "Aradığınızı bulamadıysanız teklif isteyin",
  "katalog.bos_oneri_kategori": "Ya da bir kategoriye göz atın:",
  "katalog.sayfalama": "Sayfalar",
  "katalog.onceki": "Önceki",
  "katalog.sonraki": "Sonraki",
  "katalog.sayfa_n": "Sayfa {n}",
  "urun.sku": "SKU",
  "urun.uretici_kodu": "Üretici kodu",
  "urun.kategori": "Kategori",
  "urun.ornek": "örnek",
  "urun.stokta": "Stokta: {adet} adet",
  "urun.stokta_kisa": "Stokta",
  "urun.tedarik_gun": "Tedarik süresi: {gun} gün",
  "urun.tedarik_teyit": "Tedarik süresi sipariş sonrası teyit edilecek",
  "urun.teklif_ile": "Teklif ile satılır",
  "urun.teklif_aciklama": "Bu ürün sepete eklenemez; fiyat ve teslim için teklif isteyin.",
  "urun.teklif_iste": "Teklif iste",
  "urun.adet": "Adet",
  "urun.sepete_ekle": "Sepete ekle",
  "urun.teslim_baslik": "Teslim ve iade",
  "urun.teslim_ozet": "Türkiye içi kargo 15 € + KDV (temsili). Fabrikadan teslim ücretsiz. Yurt dışı DAP; navlun ayrıca teklif edilir.",
  "urun.iade_ozet": "Bireysel alımlarda 14 gün cayma hakkı vardır; kurumsal alımlarda iade sözleşmeye göre yapılır.",
  "urun.iade_bag": "İade ve cayma",
  "urun.garanti_bag": "Garanti",
  "durum.yeni": "Yeni",
  "durum.ikinci_el_test_edildi": "2. el – test edildi",
  "durum.ikinci_el_oldugu_gibi": "2. el – olduğu gibi",
  "hesap.kayit_baslik": "Üye ol",
  "hesap.demo_parola_uyarisi": "Bu bir demodur ve bağlantı şifreli değildir: gerçek parolanızı ve gerçek müşteri bilgilerini kullanmayın.",
  "hesap.form_hatali": "Formda düzeltilmesi gereken alanlar var:",
  "hesap.tip_baslik": "Müşteri tipi",
  "hesap.tip_bireysel": "Bireysel",
  "hesap.tip_bireysel_aciklama": "Türkiye'de kişisel alım",
  "hesap.tip_kurumsal": "Kurumsal",
  "hesap.tip_kurumsal_aciklama": "Türkiye'de vergi kaydı olan şirket",
  "hesap.tip_yurtdisi": "Yurt dışı",
  "hesap.tip_yurtdisi_aciklama": "Türkiye dışındaki alıcı",
  "hesap.ad": "Ad soyad / unvan",
  "hesap.eposta": "E-posta",
  "hesap.parola": "Parola",
  "hesap.parola_ipucu": "En az 10 karakter.",
  "hesap.ulke": "Ülke",
  "hesap.vkn": "VKN veya TCKN",
  "hesap.vkn_ipucu": "Şirketler için 10 haneli VKN, şahıs şirketleri için 11 haneli TCKN.",
  "hesap.vergi_dairesi": "Vergi dairesi",
  "hesap.vat_id": "VAT ID (isteğe bağlı)",
  "hesap.yalniz_kurumsal": "yalnız kurumsal",
  "hesap.yalniz_yurtdisi": "yalnız yurt dışı",
  "hesap.yalniz_bireysel": "yalnız bireysel",
  "hesap.kvkk_onay": "Kişisel verilerin işlenmesine ilişkin aydınlatma metnini okudum.",
  "hesap.kvkk_bag": "Aydınlatma metni",
  "hesap.iys_onay": "Kampanya ve duyuru iletileri almak istiyorum (İYS).",
  "hesap.kayit_ol": "Hesap oluştur",
  "hesap.zaten_uye": "Zaten üye misiniz?",
  "hesap.giris_baslik": "Giriş",
  "hesap.giris_yap": "Giriş yap",
  "hesap.uye_degil": "Hesabınız yok mu?",
  "hesap.hatali_giris": "E-posta veya parola hatalı.",
  "hesap.cok_deneme": "Çok fazla deneme yapıldı. Lütfen bir dakika sonra tekrar deneyin.",
  "hesap.hesabim_baslik": "Hesabım",
  "hesap.hos_geldin": "Hoş geldiniz, {ad}",
  "hesap.musteri_tipi": "Müşteri tipi: {tip}",
  "hesap.siparislerim": "Siparişlerim",
  "hesap.tekliflerim": "Tekliflerim",
  "hesap.siparis_yok": "Henüz siparişiniz yok.",
  "hesap.teklif_yok": "Henüz teklif isteğiniz yok.",
  "hesap.sutun_no": "No",
  "hesap.sutun_tarih": "Tarih",
  "hesap.sutun_durum": "Durum",
  "hesap.sutun_toplam": "Toplam",
  "hesap.sutun_urun": "Ürün",
  "hesap.sutun_adet": "Adet",
  "hesap.genel_teklif": "Genel teklif",
  "hesap.sepet_birlesti": "Misafir sepetinizdeki {adet} kalem hesabınızın sepetiyle birleştirildi.",
  "hesap.kayit_tamam": "Hesabınız oluşturuldu.",
  "hesap.giris_tamam": "Giriş yapıldı.",
  "hesap.cikis_yapildi": "Çıkış yapıldı.",
  "siparis_durum.odeme_bekliyor": "Ödeme bekliyor",
  "siparis_durum.odendi": "Ödendi",
  "siparis_durum.hazirlaniyor": "Hazırlanıyor",
  "siparis_durum.kargoda": "Kargoda",
  "siparis_durum.teslim": "Teslim edildi",
  "siparis_durum.iptal": "İptal",
  "teklif_durum.yeni": "Yeni",
  "teklif_durum.inceleniyor": "İnceleniyor",
  "teklif_durum.teklif_verildi": "Teklif verildi",
  "teklif_durum.kapandi": "Kapandı"
}
```

- [ ] **Step 6: Çeviri dosyası `app/web/dil/en.json`**

```json
{
  "genel.site_adi": "Ceylan Robot Shop",
  "genel.demo_bandi": "DEMO – no real sales or payments are made",
  "genel.icerige_atla": "Skip to content",
  "genel.ana_sayfa": "Home",
  "nav.ara": "Search",
  "nav.ara_etiket": "Search product, SKU or manufacturer code",
  "nav.ara_ipucu": "Product name, SKU, manufacturer code",
  "nav.dil": "Language",
  "nav.ulke": "Country",
  "nav.uygula": "Apply",
  "nav.giris": "Sign in",
  "nav.kayit": "Create account",
  "nav.hesabim": "My account",
  "nav.cikis": "Sign out",
  "nav.sepet": "Cart",
  "nav.sepet_adet": "{adet} items in cart",
  "nav.teklif": "Request a quote",
  "alt.yasal_baslik": "Legal",
  "alt.not": "This site is a design prototype; prices are indicative.",
  "alt.yasal_on_bilgilendirme": "Pre-contract information",
  "alt.yasal_mesafeli_satis": "Distance sales agreement",
  "alt.yasal_iade": "Returns and withdrawal",
  "alt.yasal_garanti": "Warranty",
  "alt.yasal_kvkk": "Personal data notice (KVKK)",
  "alt.yasal_acik_riza": "Explicit consent",
  "alt.yasal_cerez": "Cookie policy",
  "alt.yasal_gizlilik": "Privacy",
  "alt.yasal_kullanim": "Terms of use",
  "alt.yasal_kunye": "Imprint",
  "dil.tr": "Türkçe",
  "dil.en": "English",
  "ulke.TR": "Turkey",
  "ulke.DE": "Germany",
  "ulke.AT": "Austria",
  "ulke.NL": "Netherlands",
  "ulke.FR": "France",
  "ulke.IT": "Italy",
  "ulke.PL": "Poland",
  "ulke.GB": "United Kingdom",
  "ulke.US": "United States",
  "ulke.AZ": "Azerbaijan",
  "ulke.SA": "Saudi Arabia",
  "ulke.AE": "United Arab Emirates",
  "gb.dugme": "Feedback",
  "gb.baslik": "Feedback about this page",
  "gb.aciklama": "The page address is added automatically.",
  "gb.isim": "Your name (optional)",
  "gb.metin": "Your feedback",
  "gb.gonder": "Send",
  "gb.kapat": "Close",
  "gb.tamam": "Saved, thank you.",
  "gb.hata": "Could not be sent, please try again.",
  "cerez.metin": "This demo only uses cookies required for the session and your preferences.",
  "cerez.politika": "Cookie policy",
  "cerez.kabul": "OK",
  "hata.baslik_400": "Bad request",
  "hata.baslik_403": "Request refused",
  "hata.baslik_404": "Page not found",
  "hata.baslik_405": "Method not allowed",
  "hata.baslik_429": "Too many attempts",
  "hata.baslik_500": "Unexpected error",
  "hata.baslik_genel": "Error",
  "hata.aciklama_403": "Your session has expired; reload the page and try again.",
  "hata.aciklama_404": "The page you are looking for may have moved or never existed.",
  "hata.aciklama_429": "Please wait a minute and try again.",
  "hata.aciklama_500": "Something went wrong. Please share the error ID below when reporting the problem.",
  "hata.aciklama_genel": "The request could not be processed.",
  "hata.kimlik": "Error ID",
  "hata.ana_sayfaya": "Back to home",
  "hata_kodu.zorunlu": "This field is required.",
  "hata_kodu.gecersiz": "This value is invalid.",
  "hata_kodu.gecersiz_vkn": "Invalid tax number (enter a 10-digit VKN or an 11-digit TCKN).",
  "hata_kodu.eposta_kayitli": "An account with this e-mail address already exists.",
  "hata_kodu.parola_kisa": "The password must be at least 10 characters.",
  "hata_kodu.kvkk_onay_yok": "Please confirm the privacy notice to continue.",
  "hata_kodu.gecersiz_ulke": "Choose a country other than Turkey for an international account.",
  "hata_kodu.tip_sec": "Choose a customer type.",
  "fiyat.temsili": "Indicative price",
  "fiyat.temsili_aciklama": "Generated for display because the source has no price.",
  "fiyat.kdv_dahil": "incl. VAT",
  "fiyat.kdv_haric": "excl. VAT",
  "fiyat.ikincil": "≈ {tutar} (excl. VAT)",
  "fiyat.kur_satiri": "Rate: 1 € = {kur} · {tarih} CBRT selling",
  "fiyat.kur_bayat": "rate is outdated",
  "katalog.ana_baslik": "Industrial robots and spare parts",
  "katalog.ana_alt": "Tested used robots, controllers and spare parts, delivered in Turkey and abroad.",
  "katalog.kategoriler": "Categories",
  "katalog.urun_sayisi": "{adet} products",
  "katalog.one_cikanlar": "Featured products",
  "katalog.robot_teklif_baslik": "Get a quote for robots",
  "katalog.robot_teklif_metin": "Industrial robots and items above €15,000 are sold by quotation. Tell us what you need and our sales team will get back to you.",
  "katalog.robot_teklif_dugme": "Request a quote",
  "katalog.guven_test_baslik": "Tested used equipment",
  "katalog.guven_test_metin": "The test status of used items is shown on the product page.",
  "katalog.guven_ihracat_baslik": "Export",
  "katalog.guven_ihracat_metin": "VAT exemption and DAP delivery for international orders.",
  "katalog.guven_destek_baslik": "Technical support",
  "katalog.guven_destek_metin": "Expert support for robots and controllers.",
  "katalog.iz": "Breadcrumb",
  "katalog.arama": "Search",
  "katalog.arama_baslik": "Results for “{q}”",
  "katalog.arama_bos": "Type a product name, SKU or manufacturer code to search.",
  "katalog.sonuc_sayisi": "{toplam} products",
  "katalog.filtreler": "Filters",
  "katalog.filtre_stokta": "In stock only",
  "katalog.filtre_fiyat": "Price range",
  "katalog.filtre_fmin": "Min (€)",
  "katalog.filtre_fmax": "Max (€)",
  "katalog.filtre_fiyat_not": "Net EUR, excl. VAT",
  "katalog.siralama": "Sort by",
  "katalog.sira_ad": "Name",
  "katalog.sira_fiyat_artan": "Price (low to high)",
  "katalog.sira_fiyat_azalan": "Price (high to low)",
  "katalog.uygula": "Apply",
  "katalog.temizle": "Clear filters",
  "katalog.bos_sonuc": "No products match these criteria.",
  "katalog.bos_oneri_filtre": "Try removing the filters",
  "katalog.bos_oneri_teklif": "Can't find it? Request a quote",
  "katalog.bos_oneri_kategori": "Or browse a category:",
  "katalog.sayfalama": "Pages",
  "katalog.onceki": "Previous",
  "katalog.sonraki": "Next",
  "katalog.sayfa_n": "Page {n}",
  "urun.sku": "SKU",
  "urun.uretici_kodu": "Manufacturer code",
  "urun.kategori": "Category",
  "urun.ornek": "sample",
  "urun.stokta": "In stock: {adet} pcs",
  "urun.stokta_kisa": "In stock",
  "urun.tedarik_gun": "Lead time: {gun} days",
  "urun.tedarik_teyit": "Lead time will be confirmed after the order",
  "urun.teklif_ile": "Sold by quotation",
  "urun.teklif_aciklama": "This item cannot be added to the cart; request a quote for price and delivery.",
  "urun.teklif_iste": "Request a quote",
  "urun.adet": "Quantity",
  "urun.sepete_ekle": "Add to cart",
  "urun.teslim_baslik": "Delivery and returns",
  "urun.teslim_ozet": "Shipping within Turkey €15 + VAT (indicative). Factory pick-up is free. International: DAP; freight is quoted separately.",
  "urun.iade_ozet": "Consumers have a 14-day right of withdrawal; business purchases are returned under the contract terms.",
  "urun.iade_bag": "Returns and withdrawal",
  "urun.garanti_bag": "Warranty",
  "durum.yeni": "New",
  "durum.ikinci_el_test_edildi": "Used – tested",
  "durum.ikinci_el_oldugu_gibi": "Used – as is",
  "hesap.kayit_baslik": "Create account",
  "hesap.demo_parola_uyarisi": "This is a demo and the connection is not encrypted: do not use your real password or real customer data.",
  "hesap.form_hatali": "Some fields need to be corrected:",
  "hesap.tip_baslik": "Customer type",
  "hesap.tip_bireysel": "Individual",
  "hesap.tip_bireysel_aciklama": "Personal purchase in Turkey",
  "hesap.tip_kurumsal": "Business (Turkey)",
  "hesap.tip_kurumsal_aciklama": "Company registered for tax in Turkey",
  "hesap.tip_yurtdisi": "International",
  "hesap.tip_yurtdisi_aciklama": "Buyer outside Turkey",
  "hesap.ad": "Name / company name",
  "hesap.eposta": "E-mail",
  "hesap.parola": "Password",
  "hesap.parola_ipucu": "At least 10 characters.",
  "hesap.ulke": "Country",
  "hesap.vkn": "Tax number (VKN or TCKN)",
  "hesap.vkn_ipucu": "10-digit VKN for companies, 11-digit TCKN for sole proprietorships.",
  "hesap.vergi_dairesi": "Tax office",
  "hesap.vat_id": "VAT ID (optional)",
  "hesap.yalniz_kurumsal": "business only",
  "hesap.yalniz_yurtdisi": "international only",
  "hesap.yalniz_bireysel": "individual only",
  "hesap.kvkk_onay": "I have read the notice on the processing of personal data.",
  "hesap.kvkk_bag": "Privacy notice",
  "hesap.iys_onay": "I would like to receive marketing messages (IYS).",
  "hesap.kayit_ol": "Create account",
  "hesap.zaten_uye": "Already have an account?",
  "hesap.giris_baslik": "Sign in",
  "hesap.giris_yap": "Sign in",
  "hesap.uye_degil": "No account yet?",
  "hesap.hatali_giris": "Incorrect e-mail or password.",
  "hesap.cok_deneme": "Too many attempts. Please try again in a minute.",
  "hesap.hesabim_baslik": "My account",
  "hesap.hos_geldin": "Welcome, {ad}",
  "hesap.musteri_tipi": "Customer type: {tip}",
  "hesap.siparislerim": "My orders",
  "hesap.tekliflerim": "My quotes",
  "hesap.siparis_yok": "You have no orders yet.",
  "hesap.teklif_yok": "You have no quote requests yet.",
  "hesap.sutun_no": "No.",
  "hesap.sutun_tarih": "Date",
  "hesap.sutun_durum": "Status",
  "hesap.sutun_toplam": "Total",
  "hesap.sutun_urun": "Product",
  "hesap.sutun_adet": "Qty",
  "hesap.genel_teklif": "General quote",
  "hesap.sepet_birlesti": "{adet} items from your guest cart were merged into your account cart.",
  "hesap.kayit_tamam": "Your account has been created.",
  "hesap.giris_tamam": "Signed in.",
  "hesap.cikis_yapildi": "You have signed out.",
  "siparis_durum.odeme_bekliyor": "Awaiting payment",
  "siparis_durum.odendi": "Paid",
  "siparis_durum.hazirlaniyor": "Preparing",
  "siparis_durum.kargoda": "Shipped",
  "siparis_durum.teslim": "Delivered",
  "siparis_durum.iptal": "Cancelled",
  "teklif_durum.yeni": "New",
  "teklif_durum.inceleniyor": "Under review",
  "teklif_durum.teklif_verildi": "Quoted",
  "teklif_durum.kapandi": "Closed"
}
```

- [ ] **Step 7: `app/web/guvenlik.py`**

```python
"""Güvenlik başlıkları, açık yönlendirme engeli, hız sınırı, oturum ve CSRF yardımcıları."""
from __future__ import annotations

import secrets
import sqlite3
import threading
from collections import deque
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.hesap.servis import Musteri, musteri_getir

GUVENLIK_BASLIKLARI = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' https://www.ceylanrobot.com data:; style-src 'self'; script-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Robots-Tag": "noindex, nofollow",
}


class BaslikMiddleware:
    """Saf ASGI middleware: her HTTP yanıtına GUVENLIK_BASLIKLARI'nı yazar (statik dosyalar dahil)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def gonder(message: Message) -> None:
            if message["type"] == "http.response.start":
                basliklar = MutableHeaders(scope=message)
                for anahtar, deger in GUVENLIK_BASLIKLARI.items():
                    basliklar[anahtar] = deger
            await send(message)

        await self.app(scope, receive, gonder)


def guvenli_sonraki(deger: str | None, varsayilan: str = "/") -> str:
    if not deger or not isinstance(deger, str):
        return varsayilan
    if not deger.startswith("/") or deger.startswith("//") or "\\" in deger:
        return varsayilan
    if any(ord(c) < 32 or ord(c) == 127 for c in deger):
        return varsayilan
    parca = urlsplit(deger)
    if parca.scheme or parca.netloc:
        return varsayilan
    return deger


class HizSiniri:
    """Kayan pencere: `pencere` saniyede anahtar başına en fazla `limit` izin. Reddedilen deneme sayılmaz."""

    def __init__(self, limit: int = 10, pencere: float = 60.0) -> None:
        self.limit = limit
        self.pencere = pencere
        self._kayit: dict[str, deque[float]] = {}
        self._kilit = threading.Lock()

    def izin(self, anahtar: str, simdi: float) -> bool:
        with self._kilit:
            kuyruk = self._kayit.setdefault(anahtar, deque())
            sinir = simdi - self.pencere
            while kuyruk and kuyruk[0] <= sinir:
                kuyruk.popleft()
            if len(kuyruk) >= self.limit:
                return False
            kuyruk.append(simdi)
            if len(self._kayit) > 10_000:
                for k in [k for k, v in self._kayit.items() if not v]:
                    del self._kayit[k]
            return True


def oturum_kimligi(request: Request) -> str:
    oid = request.session.get("oid")
    if not isinstance(oid, str) or not oid:
        oid = secrets.token_urlsafe(16)
        request.session["oid"] = oid
    return oid


def csrf_jetonu(request: Request) -> str:
    jeton = request.session.get("csrf")
    if not isinstance(jeton, str) or len(jeton) < 20:
        jeton = secrets.token_urlsafe(32)
        request.session["csrf"] = jeton
    return jeton


async def csrf_dogrula(request: Request) -> None:
    beklenen = request.session.get("csrf")
    try:
        form = await request.form()
    except Exception:  # bozuk gövde
        raise HTTPException(status_code=403) from None
    gelen = form.get("csrf")
    if not isinstance(beklenen, str) or not isinstance(gelen, str) or not secrets.compare_digest(gelen, beklenen):
        raise HTTPException(status_code=403)


def aktif_musteri(request: Request, con: sqlite3.Connection) -> Musteri | None:
    if "session" not in request.scope:
        return None
    mid = request.session.get("mid")
    if mid is None:
        return None
    if type(mid) is not int:
        request.session.pop("mid", None)
        return None
    musteri = musteri_getir(con, mid)
    if musteri is None:
        request.session.pop("mid", None)
    return musteri
```

- [ ] **Step 8: `app/web/baglam.py`**

```python
"""Fiyat bağlamı, şablon ortak değişkenleri, biçimleyiciler ve hata sayfası."""
from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from app.db import baglan
from app.fiyat.kur import kur_bayat_mi, son_kur
from app.fiyat.kurallar import Baglam, MusteriTipi, birim_fiyat_gosterimi, kdv_uygulanir
from app.hesap.servis import Musteri
from app.metin import normalize
from app.para import d, yuvarla
from app.sepet.servis import adet_toplam
from app.web.dil import DILLER
from app.web.guvenlik import GUVENLIK_BASLIKLARI, aktif_musteri, csrf_jetonu, oturum_kimligi

log = logging.getLogger("cr_shop.web")

TR_SAAT = timezone(timedelta(hours=3))  # Türkiye 2016'dan beri sabit UTC+3
ULKELER = ("TR", "DE", "AT", "NL", "FR", "IT", "PL", "GB", "US", "AZ", "SA", "AE")
PARA_SEMBOLU = {"TRY": "₺", "EUR": "€"}
YASAL_SAYFALAR = (
    "on-bilgilendirme", "mesafeli-satis", "iade", "garanti", "kvkk",
    "acik-riza", "cerez", "gizlilik", "kullanim", "kunye",
)


def simdi() -> datetime:
    return datetime.now(UTC)


def _sayi(x: Decimal, hane: int, dil: str) -> str:
    metin = f"{abs(x):,.{hane}f}"
    if dil == "tr":
        metin = metin.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return metin


def para_bicimle(tutar: Decimal, para: str, dil: str) -> str:
    q = yuvarla(d(tutar))
    isaret = "-" if q < 0 else ""
    sembol = PARA_SEMBOLU.get(para, para)
    sayi = _sayi(q, 2, dil)
    return f"{isaret}{sayi} {sembol}" if dil == "tr" else f"{isaret}{sembol}{sayi}"


def kur_bicimle(kur: Decimal, dil: str) -> str:
    q = d(kur).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    sayi = _sayi(q, 4, dil)
    return f"{sayi} ₺" if dil == "tr" else f"₺{sayi}"


def tarih_bicimle(z: date | datetime, dil: str) -> str:
    if isinstance(z, datetime):
        if z.tzinfo is None:
            z = z.replace(tzinfo=UTC)
        z = z.astimezone(TR_SAAT)
        return z.strftime("%d.%m.%Y %H:%M") if dil == "tr" else z.strftime("%Y-%m-%d %H:%M")
    return z.strftime("%d.%m.%Y") if dil == "tr" else z.strftime("%Y-%m-%d")


def _oturum(request: Request) -> dict:
    return request.session if "session" in request.scope else {}


def dil_bul(request: Request) -> str:
    dil = request.path_params.get("dil")
    if dil in DILLER:
        return dil
    parca = request.url.path.strip("/").split("/", 1)[0]
    return parca if parca in DILLER else "tr"  # dil öneksiz yollar (yönetim, /geri-bildirim) Türkçe — K9


def ulke_tercihi(request: Request) -> str:
    ulke = _oturum(request).get("ulke") or request.cookies.get("ulke") or "TR"
    return ulke if ulke in ULKELER else "TR"


def fiyat_baglami(request: Request, musteri: Musteri | None) -> Baglam:
    if musteri is not None:
        return Baglam(musteri_tipi=musteri.tip, teslimat_ulkesi=(musteri.ulke or "TR").upper())
    ulke = ulke_tercihi(request)
    tip = MusteriTipi.BIREYSEL if ulke == "TR" else MusteriTipi.YURTDISI
    return Baglam(musteri_tipi=tip, teslimat_ulkesi=ulke)


def mevcut_sepet_id(con: sqlite3.Connection, request: Request, musteri: Musteri | None) -> int | None:
    """Sepet OLUŞTURMADAN mevcut sepetin id'si (üye sepeti ya da oturum sepeti)."""
    if musteri is not None:
        satir = con.execute("SELECT id FROM sepet WHERE musteri_id = ?", (musteri.id,)).fetchone()
    else:
        oid = _oturum(request).get("oid")
        if not oid:
            return None
        satir = con.execute("SELECT id FROM sepet WHERE oturum_id = ?", (oid,)).fetchone()
    return int(satir[0]) if satir else None


def bildir(request: Request, anahtar: str, **degerler) -> None:
    """Bir sonraki sayfada bir kez gösterilecek bilgi mesajı (çeviri anahtarı + değerler)."""
    request.session.setdefault("bildirimler", []).append([anahtar, degerler])


def yer_tutucu(kok_kategori_ad: str | None) -> str:
    n = normalize(kok_kategori_ad or "")
    if "robot" in n or "pozisyoner" in n:
        ad = "robot"
    elif "elektrik" in n or "elektronik" in n or "guc" in n:
        ad = "elektrik"
    elif "mekanik" in n or "reduktor" in n or "slider" in n:
        ad = "mekanik"
    else:
        ad = "genel"
    return f"/statik/yer-tutucu/{ad}.svg"


def gorsel_adresi(urun, gorsel_kok: str) -> str:
    url = (getattr(urun, "gorsel_url", None) or "").strip()
    if not url:
        return yer_tutucu(urun.kok_kategori_ad)
    if url.startswith("https://"):
        return url
    if url.startswith("/"):
        return gorsel_kok.rstrip("/") + url
    return gorsel_kok.rstrip("/") + "/" + url


def _ortak(request: Request) -> dict[str, Any]:
    durum = request.app.state
    ceviri = durum.ceviri
    dil = dil_bul(request)
    oturum_var = "session" in request.scope
    if oturum_var:
        oturum_kimligi(request)
    con = getattr(request.state, "con", None)
    musteri = None
    sepet_adet = 0
    kur = None
    if con is not None:
        musteri = aktif_musteri(request, con)
        sid = mevcut_sepet_id(con, request, musteri)
        if sid is not None:
            sepet_adet = adet_toplam(con, sid)
        kur = son_kur(con)
    fb = fiyat_baglami(request, musteri)
    kur_degeri = kur.eur_satis if kur is not None else None
    gorsel_kok = durum.ayarlar.gorsel_kok

    def t(anahtar: str, **k) -> str:
        return ceviri.t(dil, anahtar, **k)

    def para(tutar: Decimal, para_birimi: str) -> str:
        return para_bicimle(tutar, para_birimi, dil)

    def fiyat_goster(urun):
        return birim_fiyat_gosterimi(urun.net_fiyat_eur, urun.kdv_orani, fb, kur_degeri)

    bildirimler = []
    if oturum_var:
        for anahtar, degerler in request.session.pop("bildirimler", []):
            bildirimler.append(ceviri.t(dil, anahtar, **(degerler or {})))
    yol = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    return {
        "dil": dil,
        "diller": DILLER,
        "t": t,
        "csrf": csrf_jetonu(request) if oturum_var else "",
        "musteri": musteri,
        "sepet_adet": sepet_adet,
        "ulke": ulke_tercihi(request),
        "ulkeler": ULKELER,
        "para": para,
        "fiyat_goster": fiyat_goster,
        "kdv_var": kdv_uygulanir(fb),
        "kur": kur,
        "kur_metni": kur_bicimle(kur.eur_satis, dil) if kur is not None else "",
        "kur_tarihi": tarih_bicimle(kur.tarih, dil) if kur is not None else "",
        "kur_bayat": kur is not None and kur_bayat_mi(kur, simdi().date()),
        "istek_yolu": yol[:500],
        "yasal_sayfalar": YASAL_SAYFALAR,
        "cerez_onay": request.cookies.get("cerez_onay") == "1",
        "yer_tutucu": yer_tutucu,
        "gorsel_adresi": lambda u: gorsel_adresi(u, gorsel_kok),
        "tarih": lambda z: tarih_bicimle(z, dil),
        "bildirimler": bildirimler,
        "arama_q": "",
    }


def sablon(request: Request, ad: str, baglam: dict, durum: int = 200) -> HTMLResponse:
    ctx = _ortak(request)
    ctx.update(baglam)
    return request.app.state.sablonlar.TemplateResponse(request, ad, ctx, status_code=durum)


def hata_yaniti(
    request: Request, durum: int, kimlik: str | None = None, db: bool = True, basliklar: dict | None = None
) -> Response:
    """hata.html'i üretir. 500 yanıtı ServerErrorMiddleware'den çıktığı için güvenlik başlıkları burada da yazılır."""
    ceviri = request.app.state.ceviri
    dil = dil_bul(request)
    b = f"hata.baslik_{durum}" if ceviri.var(f"hata.baslik_{durum}") else "hata.baslik_genel"
    a = f"hata.aciklama_{durum}" if ceviri.var(f"hata.aciklama_{durum}") else "hata.aciklama_genel"
    baglam = {"durum": durum, "baslik": ceviri.t(dil, b), "aciklama": ceviri.t(dil, a), "hata_kimligi": kimlik}
    con = None
    try:
        if db:
            try:
                con = baglan(request.app.state.ayarlar.db_yolu)
            except Exception:  # noqa: BLE001
                con = None
        request.state.con = con
        yanit: Response = sablon(request, "hata.html", baglam, durum=durum)
    except Exception:  # noqa: BLE001
        log.exception("hata sayfası üretilemedi")
        yanit = PlainTextResponse(f"{durum}" + (f" – {kimlik}" if kimlik else ""), status_code=durum)
    finally:
        request.state.con = None
        if con is not None:
            con.close()
    for anahtar, deger in GUVENLIK_BASLIKLARI.items():
        yanit.headers[anahtar] = deger
    for anahtar, deger in (basliklar or {}).items():
        yanit.headers[anahtar] = deger
    return yanit
```

- [ ] **Step 9: `app/web/bagimlilik.py`, `app/web/uygulama.py` ve `app/web/rotalar/genel.py`**

`app/web/bagimlilik.py` (rota modülleri bağımlılığı buradan alır; döngüsel import yok — K9):

```python
"""İstek başına veritabanı bağlantısı."""
from __future__ import annotations

import sqlite3
from typing import Iterator

from fastapi import Request

from app.db import baglan


def db_bagimliligi(request: Request) -> Iterator[sqlite3.Connection]:
    con = baglan(request.app.state.ayarlar.db_yolu)
    request.state.con = con  # sablon() ortak bağlamı müşteri/sepet/kur için buradan okur
    try:
        yield con
    finally:
        request.state.con = None
        con.close()
```

`app/web/uygulama.py`:

```python
"""FastAPI uygulaması: middleware, statik dosyalar, rotalar, hata işleyicileri."""
from __future__ import annotations

import importlib
import logging
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.ayarlar import Ayarlar
from app.db import baglan, gecisleri_uygula
from app.fiyat.kurallar import bantlari_oku
from app.web.bagimlilik import db_bagimliligi  # noqa: F401  (yeniden dışa aktarım)
from app.web.baglam import hata_yaniti
from app.web.dil import Ceviri
from app.web.guvenlik import BaslikMiddleware, HizSiniri

WEB = Path(__file__).parent
ROTA_SIRASI = ("genel", "yonetim", "yasal", "katalog", "hesap", "sepet_odeme", "teklif_gb")
log = logging.getLogger("cr_shop.web")


def _rotalari_ekle(app: FastAPI) -> None:
    for ad in ROTA_SIRASI:
        modul_adi = f"app.web.rotalar.{ad}"
        try:
            modul = importlib.import_module(modul_adi)
        except ModuleNotFoundError as e:
            if e.name == modul_adi:
                log.info("rota modülü henüz yok: %s", modul_adi)
                continue
            raise
        app.include_router(modul.router)


async def _http_hatasi(request: Request, exc: StarletteHTTPException):
    return hata_yaniti(request, exc.status_code, basliklar=getattr(exc, "headers", None))


async def _dogrulama_hatasi(request: Request, exc: RequestValidationError):
    return hata_yaniti(request, 400)


async def _beklenmeyen_hata(request: Request, exc: Exception):
    kimlik = secrets.token_hex(4).upper()
    log.error("beklenmeyen hata kimlik=%s yol=%s", kimlik, request.url.path, exc_info=exc)
    return hata_yaniti(request, 500, kimlik=kimlik, db=False)


def uygulama_olustur(ayarlar: Ayarlar) -> FastAPI:
    ayarlar.db_yolu.parent.mkdir(parents=True, exist_ok=True)
    con = baglan(ayarlar.db_yolu)
    try:
        gecisleri_uygula(con)
    finally:
        con.close()

    app = FastAPI(title="Ceylan Robot demo mağaza", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ayarlar = ayarlar
    app.state.ceviri = Ceviri(WEB / "dil")
    app.state.sablonlar = Jinja2Templates(directory=str(WEB / "sablonlar"))
    app.state.bantlar = bantlari_oku(ayarlar.bantlar_yolu)
    app.state.hiz = HizSiniri()

    app.add_middleware(
        SessionMiddleware,
        secret_key=ayarlar.gizli_anahtar,
        session_cookie="cr_oturum",
        max_age=14 * 24 * 3600,
        same_site="lax",
        https_only=False,
    )
    app.add_middleware(BaslikMiddleware)  # en dışta: oturum çerezli yanıtlara da başlık yazar
    app.mount("/statik", StaticFiles(directory=str(WEB / "statik")), name="statik")
    _rotalari_ekle(app)
    app.add_exception_handler(StarletteHTTPException, _http_hatasi)
    app.add_exception_handler(RequestValidationError, _dogrulama_hatasi)
    app.add_exception_handler(Exception, _beklenmeyen_hata)
    return app
```

`app/web/rotalar/genel.py`:

```python
"""Kök yönlendirme, sağlık kontrolü, dil/ülke tercihi."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app.esitleme.esitle import son_basarili_esitleme
from app.web.baglam import ULKELER
from app.web.dil import DILLER
from app.web.guvenlik import csrf_dogrula, guvenli_sonraki
from app.web.bagimlilik import db_bagimliligi

router = APIRouter()
BIR_YIL = 365 * 24 * 3600


@router.get("/")
def kok(request: Request):
    dil = request.cookies.get("dil")
    if dil not in DILLER:
        dil = "tr"
    return RedirectResponse(f"/{dil}/", status_code=302)


@router.get("/saglik")
def saglik(con=Depends(db_bagimliligi)):
    son = son_basarili_esitleme(con)
    adet = con.execute("SELECT COUNT(*) FROM urun WHERE aktif = 1").fetchone()[0]
    return {"durum": "ok", "son_esitleme": son.isoformat() if son else None, "urun": adet}


@router.post("/tercih", dependencies=[Depends(csrf_dogrula)])
def tercih(request: Request, dil: str = Form(""), ulke: str = Form(""), sonraki: str = Form("/")):
    hedef = guvenli_sonraki(sonraki, "/")
    yeni_dil = dil if dil in DILLER else None
    if yeni_dil:
        yol, ayrac, sorgu = hedef.partition("?")
        parcalar = yol.split("/")
        if len(parcalar) > 1 and parcalar[1] in DILLER:
            parcalar[1] = yeni_dil
            hedef = "/".join(parcalar) + ayrac + sorgu
        elif yol == "/":
            hedef = f"/{yeni_dil}/"
    ulke = (ulke or "").strip().upper()
    yeni_ulke = ulke if ulke in ULKELER else None
    if yeni_ulke:
        request.session["ulke"] = yeni_ulke
    yanit = RedirectResponse(hedef, status_code=303)
    if yeni_dil:
        yanit.set_cookie("dil", yeni_dil, max_age=BIR_YIL, httponly=True, samesite="lax")
    if yeni_ulke:
        yanit.set_cookie("ulke", yeni_ulke, max_age=BIR_YIL, httponly=True, samesite="lax")
    return yanit
```

- [ ] **Step 10: Şablonlar — `taban.html`, `_makrolar.html`, `hata.html`**

`app/web/sablonlar/taban.html`:

```html
<!doctype html>
<html lang="{{ dil }}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{% block baslik %}{{ t('genel.site_adi') }}{% endblock %} · CEYLAN ROBOT</title>
<link rel="stylesheet" href="/statik/site.css">
<script src="/statik/site.js" defer></script>
</head>
<body>
<a class="atla" href="#icerik">{{ t('genel.icerige_atla') }}</a>
<div class="demo-bandi" role="note">{{ t('genel.demo_bandi') }}</div>
<header class="ust">
  <div class="ust-ic">
    <a class="logo" href="/{{ dil }}/">CEYLAN ROBOT</a>
    <form class="arama" action="/{{ dil }}/ara" method="get" role="search">
      <label for="ust-arama" class="gizli">{{ t('nav.ara_etiket') }}</label>
      <input id="ust-arama" type="search" name="q" value="{{ arama_q }}" placeholder="{{ t('nav.ara_ipucu') }}" maxlength="100">
      <button type="submit">{{ t('nav.ara') }}</button>
    </form>
    <form class="tercih" action="/tercih" method="post" data-otomatik>
      <input type="hidden" name="csrf" value="{{ csrf }}">
      <input type="hidden" name="sonraki" value="{{ istek_yolu }}">
      <label for="sec-dil">{{ t('nav.dil') }}</label>
      <select id="sec-dil" name="dil">
        {% for d in diller %}<option value="{{ d }}"{% if d == dil %} selected{% endif %}>{{ t('dil.' ~ d) }}</option>{% endfor %}
      </select>
      <label for="sec-ulke">{{ t('nav.ulke') }}</label>
      <select id="sec-ulke" name="ulke">
        {% for u in ulkeler %}<option value="{{ u }}"{% if u == ulke %} selected{% endif %}>{{ t('ulke.' ~ u) }}</option>{% endfor %}
      </select>
      <button type="submit" class="js-gizle">{{ t('nav.uygula') }}</button>
    </form>
    <nav class="hesap-nav" aria-label="{{ t('nav.hesabim') }}">
      {% if musteri %}
        <a href="/{{ dil }}/hesabim">{{ musteri.ad }}</a>
        <form method="post" action="/{{ dil }}/cikis">
          <input type="hidden" name="csrf" value="{{ csrf }}">
          <button type="submit" class="bag" data-e2e="cikis">{{ t('nav.cikis') }}</button>
        </form>
      {% else %}
        <a href="/{{ dil }}/giris">{{ t('nav.giris') }}</a>
        <a href="/{{ dil }}/kayit">{{ t('nav.kayit') }}</a>
      {% endif %}
      <a class="sepet-bag" href="/{{ dil }}/sepet">{{ t('nav.sepet') }} <span class="sayac" aria-label="{{ t('nav.sepet_adet', adet=sepet_adet) }}">{{ sepet_adet }}</span></a>
    </nav>
  </div>
</header>
{% if bildirimler %}
<div class="bildirimler" role="status">
  {% for b in bildirimler %}<p class="bildirim">{{ b }}</p>{% endfor %}
</div>
{% endif %}
<main id="icerik" class="sayfa">
{% block icerik %}{% endblock %}
</main>
<footer class="alt">
  <div class="alt-ic">
    <h2 class="alt-baslik">{{ t('alt.yasal_baslik') }}</h2>
    <ul>
      {% for s in yasal_sayfalar %}<li><a href="/{{ dil }}/yasal/{{ s }}">{{ t('alt.yasal_' ~ s|replace('-', '_')) }}</a></li>{% endfor %}
    </ul>
    <p>{{ t('alt.not') }}</p>
    <p class="logo-alt">CEYLAN ROBOT</p>
  </div>
</footer>
<button id="gb-dugme" type="button" aria-haspopup="dialog" aria-controls="gb-pencere">{{ t('gb.dugme') }}</button>
<dialog id="gb-pencere" aria-labelledby="gb-baslik">
  <form id="gb-form" method="post" action="/geri-bildirim" data-tamam="{{ t('gb.tamam') }}" data-hata="{{ t('gb.hata') }}">
    <h2 id="gb-baslik">{{ t('gb.baslik') }}</h2>
    <p class="alan-ipucu">{{ t('gb.aciklama') }}</p>
    <input type="hidden" name="csrf" value="{{ csrf }}">
    <input type="hidden" name="sayfa" value="{{ istek_yolu }}">
    <div class="alan">
      <label for="gb-isim">{{ t('gb.isim') }}</label>
      <input id="gb-isim" name="isim" maxlength="100" autocomplete="name">
    </div>
    <div class="alan">
      <label for="gb-metin">{{ t('gb.metin') }}</label>
      <textarea id="gb-metin" name="metin" rows="5" maxlength="2000" required></textarea>
    </div>
    <p class="gb-durum" role="status" aria-live="polite" hidden></p>
    <div class="dugmeler">
      <button type="submit" class="dugme">{{ t('gb.gonder') }}</button>
      <button type="button" class="dugme ikincil" data-kapat>{{ t('gb.kapat') }}</button>
    </div>
  </form>
</dialog>
{% if not cerez_onay %}
<div id="cerez-bandi" class="cerez-bandi" role="region" aria-label="{{ t('cerez.politika') }}">
  <p>{{ t('cerez.metin') }} <a href="/{{ dil }}/yasal/cerez">{{ t('cerez.politika') }}</a></p>
  <button type="button" class="dugme" id="cerez-kabul">{{ t('cerez.kabul') }}</button>
</div>
{% endif %}
</body>
</html>
```

`app/web/sablonlar/_makrolar.html` (Görev 12 ve 13 bu dosyanın sonuna makro ekler; şablonlarda `{% from "_makrolar.html" import ... with context %}` ile alınır):

```html
{# Fiyat bloğu: sözleşmedeki fiyat(urun, gosterim). t, para, kur* bağlamdan gelir.
   K3: kdv_dahil ise "KDV dahil"; değilse ana para TRY değilken ya da kur yokken "KDV hariç" açıkça yazılır. #}
{% macro fiyat(urun, gosterim) -%}
<div class="fiyat-blok">
  <p class="fiyat-ana" data-e2e="fiyat-ana" data-para="{{ gosterim.ana_para }}" data-kdv="{{ 'dahil' if gosterim.kdv_dahil else 'haric' }}"><span class="tutar">{{ para(gosterim.ana_tutar, gosterim.ana_para) }}</span>
  {%- if gosterim.kdv_dahil %} <span class="fiyat-kdv">{{ t('fiyat.kdv_dahil') }}</span>
  {%- elif gosterim.ana_para != 'TRY' or not kur %} <span class="fiyat-kdv">{{ t('fiyat.kdv_haric') }}</span>{% endif %}</p>
  {%- if gosterim.ikincil_tutar is not none %}
  <p class="fiyat-ikincil" data-e2e="fiyat-ikincil">{{ t('fiyat.ikincil', tutar=para(gosterim.ikincil_tutar, gosterim.ikincil_para)) }}</p>
  {%- endif %}
  {%- if urun.fiyat_temsili %}
  <p class="fiyat-rozetler"><span class="rozet rozet-temsili" title="{{ t('fiyat.temsili_aciklama') }}">{{ t('fiyat.temsili') }}</span></p>
  {%- endif %}
  {%- if kur and (gosterim.ana_para == 'TRY' or gosterim.ikincil_para == 'TRY') %}
  <p class="kur-satiri{% if kur_bayat %} kur-bayat{% endif %}">{{ t('fiyat.kur_satiri', kur=kur_metni, tarih=kur_tarihi) }}{% if kur_bayat %} · {{ t('fiyat.kur_bayat') }}{% endif %}</p>
  {%- endif %}
</div>
{%- endmacro %}
```

`app/web/sablonlar/hata.html`:

```html
{% extends "taban.html" %}
{% block baslik %}{{ baslik }}{% endblock %}
{% block icerik %}
<section class="hata-sayfa">
  <p class="hata-kodu">{{ durum }}</p>
  <h1>{{ baslik }}</h1>
  <p>{{ aciklama }}</p>
  {% if hata_kimligi %}
  <p>{{ t('hata.kimlik') }}: <code class="hata-kimligi">{{ hata_kimligi }}</code></p>
  {% endif %}
  <p><a class="dugme" href="/{{ dil }}/">{{ t('hata.ana_sayfaya') }}</a></p>
</section>
{% endblock %}
```

- [ ] **Step 11: `app/web/statik/site.css`**

Renkler `Sunum-Temasi-ve-Renk-Paleti` ile sözleşme tokenlarından gelir. Küçük gri metin `--gri-koyu` (#566055) ile yazılır; `--gri` açık zeminde 4,5:1 eşiğinin altında kalır.

```css
/* Ceylan Robot demo mağaza — tek stil dosyası (CSP: style-src 'self', satır içi stil yok) */
:root {
  --yesil-koyu: #303a32;
  --yesil: #687860;
  --kiremit: #a83c29;
  --mavi: #267593;
  --zemin: #f4f1e9;
  --gri: #697265;
  --cizgi: #c5c8bc;
  --yazi: #1f2420;
  --gri-koyu: #566055;
  --zemin-koyu: #e9e9df;
  --yesil-acik: #c7d0bf;
  --mavi-acik: #eef5f8;
  --kiremit-acik: #f6e4df;
  --kiremit-koyu: #8e3222;
  --basari: #2f6b3a;
  --beyaz: #ffffff;
  --baslik-font: Georgia, "Times New Roman", serif;
  --govde-font: "Segoe UI", Arial, sans-serif;
  --yaricap: 6px;
  --golge: 0 1px 3px rgba(31, 36, 32, .12);
  --genislik: 1200px;
}

*, *::before, *::after { box-sizing: border-box; }
[hidden] { display: none !important; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; min-width: 320px; background: var(--zemin); color: var(--yazi); font: 16px/1.5 var(--govde-font); }
h1, h2, h3 { font-family: var(--baslik-font); font-weight: normal; color: var(--yesil-koyu); line-height: 1.2; margin: 0 0 .6em; }
h1 { font-size: 1.75rem; letter-spacing: -.2px; }
h2 { font-size: 1.35rem; }
h3 { font-size: 1.1rem; }
p { margin: 0 0 .8em; }
a { color: var(--mavi); }
a:hover { color: var(--yesil-koyu); }
img { max-width: 100%; height: auto; display: block; }
code { font-family: Consolas, "Courier New", monospace; }

/* Erişilebilir odak halkası */
:focus { outline: none; }
:focus-visible { outline: 3px solid var(--mavi); outline-offset: 2px; }
.ust :focus-visible, .alt :focus-visible, .cerez-bandi :focus-visible, .kahraman :focus-visible { outline-color: var(--zemin); }
.gizli { position: absolute !important; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
.atla { position: absolute; left: 8px; top: -60px; z-index: 100; background: var(--yesil-koyu); color: var(--beyaz); padding: 8px 12px; border-radius: var(--yaricap); }
.atla:focus { top: 8px; color: var(--beyaz); }

/* DEMO bandı */
.demo-bandi { background: var(--kiremit); color: var(--beyaz); text-align: center; font-weight: 600; font-size: .9rem; letter-spacing: .3px; padding: 6px 16px; }

/* Üst çubuk */
.ust { background: var(--yesil-koyu); color: var(--zemin); border-bottom: 3px solid var(--kiremit); }
.ust-ic { max-width: var(--genislik); margin: 0 auto; padding: 12px 16px; display: flex; flex-wrap: wrap; align-items: center; gap: 12px 20px; }
.logo { font-family: var(--baslik-font); font-size: 1.3rem; letter-spacing: 2px; color: var(--beyaz); text-decoration: none; white-space: nowrap; }
.logo:hover { color: var(--yesil-acik); }
.arama { display: flex; flex: 1 1 260px; min-width: 0; margin: 0; }
.arama input { flex: 1; min-width: 0; border: 1px solid var(--cizgi); border-right: 0; border-radius: var(--yaricap) 0 0 var(--yaricap); padding: 8px 10px; font: inherit; color: var(--yazi); background: var(--beyaz); }
.arama button { border: 0; background: var(--kiremit); color: var(--beyaz); padding: 8px 14px; border-radius: 0 var(--yaricap) var(--yaricap) 0; font: inherit; font-weight: 600; cursor: pointer; }
.arama button:hover { background: var(--kiremit-koyu); }
.tercih { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-size: .85rem; margin: 0; }
.tercih label { color: var(--yesil-acik); }
.tercih select { font: inherit; padding: 4px 6px; border-radius: 4px; border: 1px solid var(--cizgi); background: var(--beyaz); color: var(--yazi); max-width: 11rem; }
.tercih button { font: inherit; padding: 4px 10px; border-radius: 4px; border: 1px solid var(--yesil-acik); background: transparent; color: var(--beyaz); cursor: pointer; }
.js .js-gizle { display: none; }
.hesap-nav { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.hesap-nav form { margin: 0; }
.hesap-nav a, .hesap-nav .bag { color: var(--beyaz); text-decoration: none; font-size: .95rem; }
.hesap-nav a:hover, .hesap-nav .bag:hover { text-decoration: underline; color: var(--beyaz); }
.bag { background: none; border: 0; padding: 0; font: inherit; color: var(--mavi); text-decoration: underline; cursor: pointer; }
.sayac { display: inline-block; min-width: 1.6em; padding: 0 6px; border-radius: 999px; background: var(--kiremit); color: var(--beyaz); text-align: center; font-size: .8rem; font-weight: 600; }

/* Sayfa gövdesi ve bildirimler */
.sayfa { max-width: var(--genislik); margin: 0 auto; padding: 24px 16px 48px; }
.bildirimler { max-width: var(--genislik); margin: 12px auto 0; padding: 0 16px; }
.bildirim { background: var(--mavi-acik); border-left: 4px solid var(--mavi); padding: 10px 14px; margin: 0 0 8px; border-radius: var(--yaricap); }
.uyari { background: var(--kiremit-acik); border-left: 4px solid var(--kiremit); padding: 10px 14px; border-radius: var(--yaricap); margin: 0 0 16px; }

/* Düğmeler */
.dugme { display: inline-block; background: var(--kiremit); color: var(--beyaz); border: 0; border-radius: var(--yaricap); padding: 10px 18px; font: inherit; font-weight: 600; line-height: 1.2; text-decoration: none; cursor: pointer; }
.dugme:hover { background: var(--kiremit-koyu); color: var(--beyaz); }
.dugme.ikincil { background: transparent; color: var(--yesil-koyu); border: 1px solid var(--yesil); }
.dugme.ikincil:hover { background: var(--zemin-koyu); }
.dugme:disabled { opacity: .6; cursor: not-allowed; }
.dugmeler { display: flex; flex-wrap: wrap; gap: 8px; }

/* Rozetler */
.rozet { display: inline-block; font-size: .75rem; font-weight: 600; letter-spacing: .2px; padding: 2px 8px; border-radius: 999px; vertical-align: middle; }
.rozet-temsili { background: var(--mavi-acik); color: #1d5b72; border: 1px solid #9cc3d1; }
.rozet-durum { background: var(--yesil-acik); color: var(--yesil-koyu); }
.rozet-ornek { background: var(--beyaz); color: var(--gri-koyu); border: 1px dashed var(--gri); }
.rozet-teklif { background: var(--kiremit-acik); color: #7c2c1e; }

/* Fiyat */
.fiyat-blok { margin: 16px 0; padding: 14px 16px; background: var(--beyaz); border: 1px solid var(--cizgi); border-left: 4px solid var(--yesil); border-radius: var(--yaricap); }
.fiyat-ana { margin: 0; font-family: var(--baslik-font); font-size: 1.6rem; color: var(--yesil-koyu); }
.fiyat-kdv { font-family: var(--govde-font); font-size: .85rem; color: var(--gri-koyu); }
.fiyat-ikincil, .kur-satiri { margin: 4px 0 0; font-size: .85rem; color: var(--gri-koyu); }
.fiyat-rozetler { margin: 6px 0 0; }
.kur-bayat { color: var(--kiremit); font-weight: 600; }

/* Izgara ve kartlar */
.izgara { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; list-style: none; margin: 0 0 24px; padding: 0; }
.kart { height: 100%; display: flex; flex-direction: column; background: var(--beyaz); border: 1px solid var(--cizgi); border-radius: var(--yaricap); overflow: hidden; box-shadow: var(--golge); }
.kart-gorsel { width: 100%; aspect-ratio: 4 / 3; object-fit: contain; background: var(--zemin-koyu); }
.kart-govde { flex: 1; display: flex; flex-direction: column; gap: 6px; padding: 12px; }
.kart-baslik { margin: 0; font-family: var(--govde-font); font-size: .95rem; font-weight: 600; line-height: 1.35; }
.kart-baslik a { color: var(--yazi); text-decoration: none; }
.kart-baslik a:hover { color: var(--mavi); text-decoration: underline; }
.kart-sku { margin: 0; font-size: .8rem; color: var(--gri-koyu); overflow-wrap: anywhere; }
.kart-fiyat { margin: auto 0 0; }
.kart-stok { margin: 0; font-size: .85rem; color: var(--basari); }
.kok-kart { height: 100%; display: flex; flex-direction: column; background: var(--beyaz); border: 1px solid var(--cizgi); border-radius: var(--yaricap); overflow: hidden; color: var(--yazi); text-decoration: none; box-shadow: var(--golge); }
.kok-kart:hover { border-color: var(--yesil); color: var(--yazi); }
.kok-kart img { aspect-ratio: 4 / 3; object-fit: cover; }
.kok-ad { padding: 10px 12px 0; font-family: var(--baslik-font); font-size: 1.1rem; color: var(--yesil-koyu); }
.kok-kart .sayi { padding: 0 12px 12px; font-size: .85rem; color: var(--gri-koyu); }

/* Ana sayfa */
.kahraman { background: var(--yesil-koyu); color: var(--zemin); border-radius: var(--yaricap); padding: 32px 24px; margin-bottom: 32px; }
.kahraman h1 { color: var(--beyaz); font-size: 2rem; margin-bottom: 0; }
.vurgu-cubuk { width: 48px; height: 3px; background: var(--kiremit); margin: 14px 0; }
.kahraman .arama { max-width: 640px; margin-top: 16px; }
.robot-teklif { background: var(--beyaz); border: 1px solid var(--cizgi); border-left: 4px solid var(--kiremit); border-radius: var(--yaricap); padding: 20px; margin: 32px 0; }
.guven { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin: 32px 0; padding: 0; list-style: none; }
.guven li { border-top: 2px solid var(--yesil); padding-top: 10px; }
.guven h3 { margin-bottom: .3em; }

/* Liste düzeni, kategori ağacı, filtre */
.liste-duzen { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 24px; align-items: start; }
.yan { background: var(--beyaz); border: 1px solid var(--cizgi); border-radius: var(--yaricap); padding: 16px; }
.yan summary { font-family: var(--baslik-font); font-size: 1.1rem; color: var(--yesil-koyu); cursor: pointer; margin-bottom: 8px; }
.yan-baslik { font-size: 1.1rem; margin-top: 16px; }
.agac, .agac ul { list-style: none; margin: 0; padding: 0; }
.agac ul { padding-left: 12px; margin-left: 4px; border-left: 1px solid var(--cizgi); }
.agac a { display: block; padding: 3px 0; color: var(--yazi); text-decoration: none; font-size: .9rem; overflow-wrap: anywhere; }
.agac a:hover { color: var(--mavi); text-decoration: underline; }
.agac a[aria-current="page"] { color: var(--kiremit); font-weight: 600; }
.agac .sayi { color: var(--gri-koyu); font-size: .8rem; }
.filtre .ikili { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.filtre fieldset { border: 0; padding: 0; margin: 0 0 16px; }
.temizle { display: inline-block; margin-left: 10px; font-size: .9rem; }
.sonuc-sayisi { color: var(--gri-koyu); }
.bos-sonuc { background: var(--beyaz); border: 1px dashed var(--cizgi); border-radius: var(--yaricap); padding: 20px; }
.etiketler { display: flex; flex-wrap: wrap; gap: 8px; list-style: none; margin: 0; padding: 0; }
.etiketler a { display: inline-block; padding: 4px 10px; border: 1px solid var(--cizgi); border-radius: 999px; background: var(--zemin); text-decoration: none; font-size: .9rem; }

/* Konum (breadcrumb) */
.iz { font-size: .85rem; margin: 0 0 12px; }
.iz ol { list-style: none; display: flex; flex-wrap: wrap; gap: 4px; margin: 0; padding: 0; }
.iz li + li::before { content: "›"; margin-right: 4px; color: var(--gri-koyu); }

/* Sayfalama */
.sayfalama ul { list-style: none; display: flex; flex-wrap: wrap; gap: 6px; margin: 16px 0 0; padding: 0; }
.sayfalama a, .sayfalama span { display: inline-block; min-width: 2.4em; padding: 6px 10px; text-align: center; border: 1px solid var(--cizgi); border-radius: var(--yaricap); background: var(--beyaz); text-decoration: none; }
.sayfalama span[aria-current="page"] { background: var(--yesil-koyu); color: var(--beyaz); border-color: var(--yesil-koyu); }

/* Ürün detayı */
.urun-detay { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 32px; align-items: start; }
.urun-gorsel { background: var(--beyaz); border: 1px solid var(--cizgi); border-radius: var(--yaricap); padding: 12px; }
.urun-gorsel img { width: 100%; aspect-ratio: 4 / 3; object-fit: contain; }
.ozellik { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 4px 16px; margin: 12px 0; }
.ozellik dt { color: var(--gri-koyu); }
.ozellik dd { margin: 0; overflow-wrap: anywhere; }
.stok-not { font-weight: 600; color: var(--basari); }
.stok-not.stok-yok { color: var(--kiremit); }
.sepet-form { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px; margin: 16px 0; }
.sepet-form .alan { margin: 0; }
.sepet-form input[type="number"] { width: 6rem; }
.ozet-kutu { background: var(--beyaz); border: 1px solid var(--cizgi); border-radius: var(--yaricap); padding: 16px; margin-top: 24px; }

/* Formlar */
.form { background: var(--beyaz); border: 1px solid var(--cizgi); border-radius: var(--yaricap); padding: 20px; max-width: 640px; }
.alan { margin: 0 0 16px; }
.alan > label, .alan legend { display: block; font-weight: 600; margin-bottom: 4px; }
.alan input[type="text"], .alan input[type="email"], .alan input[type="password"], .alan input[type="number"],
.alan input:not([type]), .alan select, .alan textarea {
  width: 100%; padding: 9px 10px; border: 1px solid var(--gri); border-radius: 4px; font: inherit; color: var(--yazi); background: var(--beyaz);
}
.alan textarea { resize: vertical; }
.alan-ipucu { margin: 4px 0 0; font-size: .85rem; color: var(--gri-koyu); }
.alan-hata { margin: 4px 0 0; font-size: .9rem; font-weight: 600; color: var(--kiremit); }
.alan.hatali input, .alan.hatali select { border: 2px solid var(--kiremit); }
.etiket-kosul { margin-left: 6px; padding: 1px 8px; border-radius: 999px; background: var(--zemin-koyu); color: var(--gri-koyu); font-size: .75rem; font-weight: 600; }
.secim { display: flex; gap: 8px; align-items: flex-start; font-weight: normal; }
.secim input { margin-top: 4px; }
.tip-secim { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; border: 0; padding: 0; margin: 0 0 16px; }
.tip-secim legend { grid-column: 1 / -1; font-weight: 600; margin-bottom: 4px; }
.tip-secim label { display: flex; gap: 8px; align-items: flex-start; padding: 10px; border: 1px solid var(--cizgi); border-radius: var(--yaricap); cursor: pointer; font-weight: 600; }
.tip-secim label:has(input:checked) { border-color: var(--kiremit); background: var(--kiremit-acik); }
.tip-secim small { display: block; font-weight: normal; color: var(--gri-koyu); }
.form-hata-ozet { background: var(--kiremit-acik); border-left: 4px solid var(--kiremit); padding: 10px 14px; border-radius: var(--yaricap); margin: 0 0 16px; }
.form-hata-ozet ul { margin: 6px 0 0; padding-left: 20px; }

/* Tablolar */
.tablo-sar { overflow-x: auto; margin-bottom: 24px; }
.tablo { width: 100%; border-collapse: collapse; background: var(--beyaz); font-size: .95rem; }
.tablo th { text-align: left; font-size: .8rem; text-transform: uppercase; letter-spacing: .5px; color: var(--yesil); border-bottom: 2px solid var(--cizgi); padding: 8px; white-space: nowrap; }
.tablo td { border-bottom: 1px solid var(--zemin-koyu); padding: 8px; vertical-align: top; }
.tablo td.sayi, .tablo th.sayi { text-align: right; font-variant-numeric: tabular-nums; }

/* Geri bildirim düğmesi ve penceresi */
#gb-dugme { position: fixed; right: 16px; bottom: 16px; z-index: 50; padding: 10px 16px; border: 0; border-radius: 999px; background: var(--mavi); color: var(--beyaz); font: inherit; font-weight: 600; cursor: pointer; box-shadow: 0 2px 8px rgba(0, 0, 0, .25); }
#gb-dugme:hover { background: #1d5b72; }
#gb-pencere { width: min(480px, calc(100vw - 32px)); padding: 20px; border: 1px solid var(--cizgi); border-radius: var(--yaricap); background: var(--beyaz); color: var(--yazi); }
#gb-pencere::backdrop { background: rgba(31, 36, 32, .5); }
.gb-durum { font-weight: 600; }
.gb-durum.basarili { color: var(--basari); }
.gb-durum.hatali { color: var(--kiremit); }

/* Çerez bandı */
.cerez-bandi { position: fixed; left: 16px; right: 16px; bottom: 72px; z-index: 40; max-width: 720px; margin: 0 auto; display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 12px 16px; background: var(--yesil-koyu); color: var(--zemin); border-radius: var(--yaricap); box-shadow: 0 2px 10px rgba(0, 0, 0, .3); }
.cerez-bandi p { margin: 0; flex: 1 1 240px; }
.cerez-bandi a { color: var(--beyaz); }

/* Hata sayfası */
.hata-sayfa { text-align: center; padding: 48px 0; }
.hata-kodu { font-family: var(--baslik-font); font-size: 3rem; color: var(--kiremit); margin: 0; }
.hata-kimligi { background: var(--zemin-koyu); padding: 2px 6px; border-radius: 4px; }

/* Alt bilgi */
.alt { background: var(--yesil-koyu); color: var(--yesil-acik); padding: 24px 16px 88px; font-size: .9rem; }
.alt-ic { max-width: var(--genislik); margin: 0 auto; }
.alt-baslik { color: var(--beyaz); font-size: 1rem; }
.alt ul { list-style: none; display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 0 0 12px; padding: 0; }
.alt a { color: var(--beyaz); }
.logo-alt { font-family: var(--baslik-font); letter-spacing: 2px; color: var(--beyaz); }

/* Tablet */
@media (max-width: 800px) {
  .liste-duzen, .urun-detay { grid-template-columns: minmax(0, 1fr); }
  .guven { grid-template-columns: minmax(0, 1fr); }
  .tip-secim { grid-template-columns: minmax(0, 1fr); }
  .kahraman { padding: 24px 16px; }
  .kahraman h1 { font-size: 1.6rem; }
}

/* Mobil (360 px) */
@media (max-width: 480px) {
  body { font-size: 15px; }
  h1 { font-size: 1.45rem; }
  .ust-ic { gap: 10px; }
  .arama { flex-basis: 100%; order: 3; }
  .tercih { order: 4; }
  .hesap-nav { order: 2; margin-left: auto; }
  .izgara { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .kart-govde { padding: 8px; }
  .fiyat-ana { font-size: 1.35rem; }
  .form { padding: 14px; }
  .cerez-bandi { left: 8px; right: 8px; }
  #gb-dugme { right: 8px; bottom: 8px; padding: 8px 12px; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; animation: none !important; }
}
```

- [ ] **Step 12: `app/web/statik/site.js`**

```javascript
/* Ceylan Robot demo mağaza — tek JS dosyası. Satır içi script yok (CSP: script-src 'self'). */
(function () {
  'use strict';

  function hazir(fn) {
    if (document.readyState !== 'loading') { fn(); } else { document.addEventListener('DOMContentLoaded', fn); }
  }

  function herBiri(liste, fn) { Array.prototype.forEach.call(liste, fn); }

  /* Dil/ülke seçici: değişince formu gönder (JS yoksa "Uygula" düğmesi görünür). */
  function tercihFormu() {
    herBiri(document.querySelectorAll('form[data-otomatik]'), function (form) {
      herBiri(form.querySelectorAll('select'), function (secim) {
        secim.addEventListener('change', function () {
          if (typeof form.requestSubmit === 'function') { form.requestSubmit(); } else { form.submit(); }
        });
      });
    });
  }

  /* Çerez bandı: kabul çerezle saklanır, sunucu bir sonraki sayfada bandı hiç basmaz. */
  function cerezBandi() {
    var bant = document.getElementById('cerez-bandi');
    var dugme = document.getElementById('cerez-kabul');
    if (!bant || !dugme) { return; }
    dugme.addEventListener('click', function () {
      document.cookie = 'cerez_onay=1; path=/; max-age=31536000; SameSite=Lax';
      bant.parentNode.removeChild(bant);
    });
  }

  /* Geri bildirim penceresi: POST /geri-bildirim (FormData, csrf dahil), yanıt JSON {"tamam": true}. */
  function geriBildirim() {
    var dugme = document.getElementById('gb-dugme');
    var pencere = document.getElementById('gb-pencere');
    var form = document.getElementById('gb-form');
    if (!dugme || !pencere || !form) { return; }
    var durum = form.querySelector('.gb-durum');
    var sayfa = form.querySelector('input[name="sayfa"]');
    var metin = form.querySelector('textarea[name="metin"]');
    var gonder = form.querySelector('button[type="submit"]');

    function goster(mesaj, sinif) {
      durum.textContent = mesaj;
      durum.className = 'gb-durum ' + sinif;
      if (sinif === 'basarili') { durum.setAttribute('data-e2e', 'gb-tamam'); } else { durum.removeAttribute('data-e2e'); }
      durum.hidden = false;
    }
    function ac() {
      if (sayfa) { sayfa.value = window.location.pathname + window.location.search; }
      durum.hidden = true;
      if (typeof pencere.showModal === 'function') { pencere.showModal(); } else { pencere.setAttribute('open', ''); }
      metin.focus();
    }
    function kapat() {
      if (typeof pencere.close === 'function') { pencere.close(); } else { pencere.removeAttribute('open'); }
      dugme.focus();
    }

    dugme.addEventListener('click', ac);
    herBiri(pencere.querySelectorAll('[data-kapat]'), function (b) { b.addEventListener('click', kapat); });
    form.addEventListener('submit', function (olay) {
      olay.preventDefault();
      if (!metin.value.trim()) { metin.focus(); return; }
      gonder.disabled = true;
      fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' }
      })
        .then(function (yanit) {
          if (!yanit.ok) { throw new Error(String(yanit.status)); }
          return yanit.json();
        })
        .then(function (veri) {
          if (!veri || veri.tamam !== true) { throw new Error('yanit'); }
          metin.value = '';
          goster(form.getAttribute('data-tamam'), 'basarili');
        })
        .catch(function () { goster(form.getAttribute('data-hata'), 'hatali'); })
        .then(function () { gonder.disabled = false; });
    });
  }

  /* Kayıt formu: seçilen müşteri tipine ait olmayan alanları gizle (JS yoksa hepsi görünür). */
  function kayitTipi() {
    var radyolar = document.querySelectorAll('input[name="tip"]');
    if (!radyolar.length) { return; }
    var alanlar = document.querySelectorAll('[data-tipler]');
    function uygula() {
      var secili = document.querySelector('input[name="tip"]:checked');
      herBiri(alanlar, function (alan) {
        var tipler = alan.getAttribute('data-tipler').split(' ');
        alan.hidden = !!secili && tipler.indexOf(secili.value) === -1;
      });
    }
    herBiri(radyolar, function (r) { r.addEventListener('change', uygula); });
    uygula();
  }

  /* Görsel yüklenemezse kategori yer tutucusuna düş. */
  function gorselYedegi() {
    herBiri(document.querySelectorAll('img[data-yedek]'), function (img) {
      function yedege() {
        var yedek = img.getAttribute('data-yedek');
        if (yedek && img.getAttribute('src') !== yedek) { img.src = yedek; }
      }
      img.addEventListener('error', yedege);
      if (img.complete && img.naturalWidth === 0) { yedege(); }
    });
  }

  hazir(function () {
    document.documentElement.classList.add('js');
    tercihFormu();
    cerezBandi();
    geriBildirim();
    kayitTipi();
    gorselYedegi();
  });
}());
```

- [ ] **Step 13: Yer tutucu SVG'leri (`app/web/statik/yer-tutucu/`)**

`robot.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="400" height="300" role="img" aria-label="Robot">
  <rect width="400" height="300" fill="#e9e9df"/>
  <g fill="none" stroke="#687860" stroke-width="10" stroke-linecap="round" stroke-linejoin="round">
    <path d="M140 250h120"/>
    <path d="M170 250v-30h60v30"/>
    <path d="M200 220l-40-80"/>
    <path d="M160 140l90-40"/>
    <path d="M250 100l30 25"/>
    <path d="M280 125l-5 22M280 125l20 14"/>
  </g>
  <g fill="#303a32">
    <circle cx="200" cy="220" r="12"/>
    <circle cx="160" cy="140" r="12"/>
    <circle cx="250" cy="100" r="10"/>
  </g>
  <rect y="292" width="400" height="8" fill="#a83c29"/>
</svg>
```

`elektrik.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="400" height="300" role="img" aria-label="Elektrik">
  <rect width="400" height="300" fill="#e9e9df"/>
  <rect x="110" y="70" width="180" height="160" rx="10" fill="none" stroke="#687860" stroke-width="8"/>
  <g stroke="#687860" stroke-width="6" stroke-linecap="round">
    <path d="M110 110H70M110 150H70M110 190H70M290 110h40M290 150h40M290 190h40"/>
  </g>
  <path d="M212 92l-46 66h32l-14 52 52-72h-34l14-46z" fill="#a83c29"/>
  <rect y="292" width="400" height="8" fill="#a83c29"/>
</svg>
```

`mekanik.svg` (12 dişli çark; diş aralığı = 2π·70/12 ≈ 36,65):

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="400" height="300" role="img" aria-label="Mekanik">
  <rect width="400" height="300" fill="#e9e9df"/>
  <circle cx="200" cy="150" r="70" fill="none" stroke="#687860" stroke-width="26" stroke-dasharray="20 16.65"/>
  <circle cx="200" cy="150" r="52" fill="none" stroke="#687860" stroke-width="10"/>
  <circle cx="200" cy="150" r="18" fill="#303a32"/>
  <rect y="292" width="400" height="8" fill="#a83c29"/>
</svg>
```

`genel.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="400" height="300" role="img" aria-label="Ürün">
  <rect width="400" height="300" fill="#e9e9df"/>
  <g fill="none" stroke="#687860" stroke-width="8" stroke-linejoin="round">
    <path d="M200 70l100 45v100l-100 45-100-45V115z"/>
    <path d="M100 115l100 45 100-45M200 160v100"/>
  </g>
  <path d="M150 92l100 45" stroke="#a83c29" stroke-width="8" stroke-linecap="round"/>
  <rect y="292" width="400" height="8" fill="#a83c29"/>
</svg>
```

- [ ] **Step 14: Testlerin geçtiğini gör**

Run: `bash dagitim/test-vm.sh tests/test_web_cekirdek.py -q`
Expected: PASS (bütün testler yeşil).

- [ ] **Step 15: Tüm paketi çalıştır (önceki görevler bozulmadı mı)**

Run: `bash dagitim/test-vm.sh tests -q`
Expected: PASS.

- [ ] **Step 16: Commit**

```bash
git add app/web tests/conftest.py tests/test_web_cekirdek.py
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m $'feat(web): uygulama çekirdeği, güvenlik başlıkları, TR/EN, taban şablon ve tema\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

---

### Görev 12: Katalog ekranları (ana sayfa, kategori/arama listesi, ürün detayı)

**Files:**
- Create: `app/web/rotalar/katalog.py`
- Create: `app/web/sablonlar/ana.html`, `app/web/sablonlar/liste.html`, `app/web/sablonlar/urun.html`
- Modify: `app/web/sablonlar/_makrolar.html` (sonuna `fiyat_kisa`, `urun_karti`, `kategori_agaci` makroları)
- Test: `tests/test_web_katalog.py`

**Interfaces:**
- Consumes: `app.katalog.indeks.indeksi_yeniden_kur` (testte; K6), `app.katalog.depo.{ListeSorgusu, ListeSonucu, kategori_agaci, kategori_getir, kategori_yolu, urun_getir, urun_listele, one_cikanlar}`, `app.web.baglam.sablon`, `app.web.bagimlilik.db_bagimliligi`; şablon ortak değişkenleri (Görev 11). Çeviri anahtarları `katalog.*`, `urun.*`, `durum.*`, `fiyat.*` Görev 11'de eklendi.
- Produces:
  - Rotalar: `GET /{dil:dil}/`, `GET /{dil:dil}/kategori/{kategori_id:int}`, `GET /{dil:dil}/ara`, `GET /{dil:dil}/urun/{urun_id:int}`.
  - Ürün sayfasındaki sepet formu `POST /{dil}/sepet/ekle` (alanlar `csrf`, `urun_id`, `adet`) Görev 14'ün rotasına gider. Teklif bağlantısı `/{dil}/teklif?urun_id=<id>`.
  - Makrolar: `fiyat_kisa(urun, gosterim)`, `urun_karti(urun)`, `kategori_agaci(dugumler, secili_id, acik)`.
  - `data-e2e`: `urun-baglanti` (kart başlığı), `fiyat-ana`/`fiyat-ikincil` (fiyat makrosu), `sepete-ekle`, `teklif-iste`.

- [ ] **Step 1: Başarısız testleri yaz — `tests/test_web_katalog.py`**

```python
import re
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.fiyat.kur import Kur, kur_kaydet
from app.katalog.indeks import indeksi_yeniden_kur
from tests.conftest import csrf_al, istemci_db, kategori_ekle, sayfa_denetle, urun_ekle


def _fiyat_blogu(html: str) -> str:
    eslesme = re.search(r'<div class="fiyat-blok">(.*?)</div>', html, re.S)
    assert eslesme, "fiyat bloğu yok"
    return eslesme.group(1)


@pytest.fixture
def katalog(istemci):
    with istemci_db(istemci) as con:
        elk = kategori_ekle(con, kaynak_id="k10", ad="Elektrik ve Elektronik", yol="10", seviye=0)
        kontrol = kategori_ekle(con, kaynak_id="k1018", ad="KONTROL SISTEMLERI", yol="10.18", seviye=1, ust_kaynak_id="k10")
        rob = kategori_ekle(con, kaynak_id="k12", ad="Endüstriyel Robotlar", yol="12", seviye=0)
        kuka = kategori_ekle(con, kaynak_id="k1241", ad="KUKA", yol="12.41", seviye=1, ust_kaynak_id="k12")
        krc4 = kategori_ekle(con, kaynak_id="k1241243", ad="KR C4", yol="12.41.243", seviye=2, ust_kaynak_id="k1241")
        role = urun_ekle(con, sku="RL-24", ad="RÖLE MODÜLÜ 24V", kok="Elektrik ve Elektronik", fiyat="120.00",
                         kategori_id=kontrol, stok=5)
        robot = urun_ekle(con, sku="8301033800019", ad="KUKA KRC5 KR 140 R3200-2 PA", kok="Endüstriyel Robotlar",
                          fiyat="32000.00", teklif=True, kategori_id=krc4, stok=1, uretici_kodu="KRC5-140")
        stoksuz = urun_ekle(con, sku="SG-1", ad="SİGORTA KUTUSU", kok="Elektrik ve Elektronik", fiyat="40.00",
                            kategori_id=kontrol, stok=0)
        pasif = urun_ekle(con, sku="PS-1", ad="ESKİ KART", kok="Elektrik ve Elektronik", fiyat="10.00",
                          kategori_id=kontrol, aktif=False)
        kur_kaydet(con, Kur(tarih=date(2026, 10, 12), eur_alis=Decimal("35.00"), eur_satis=Decimal("35.20")),
                   datetime(2026, 10, 12, 6, 0, tzinfo=UTC))
        indeksi_yeniden_kur(con)  # K6: urun_ekle zaten indeksler; pasif ürün indeks dışı kalır
    return {"elk": elk, "kontrol": kontrol, "rob": rob, "kuka": kuka, "krc4": krc4,
            "role": role, "robot": robot, "stoksuz": stoksuz, "pasif": pasif}


def test_ana_sayfa_kok_kategoriler(istemci, katalog):
    yanit = istemci.get("/tr/")
    assert yanit.status_code == 200
    html = sayfa_denetle(yanit)
    assert "Elektrik ve Elektronik" in html and "Endüstriyel Robotlar" in html
    assert f'href="/tr/kategori/{katalog["elk"]}"' in html
    assert "Robotlar için teklif alın" in html and 'href="/tr/teklif"' in html


def test_kok_adres_ana_sayfaya_gider(istemci, katalog):
    assert istemci.get("/").status_code == 200


def test_kategori_sayfasi_alt_kategori_urunlerini_listeler(istemci, katalog):
    html = sayfa_denetle(istemci.get(f"/tr/kategori/{katalog['elk']}"))
    assert "RÖLE MODÜLÜ 24V" in html and "SİGORTA KUTUSU" in html
    assert f'<a href="/tr/urun/{katalog["role"]}" data-e2e="urun-baglanti">' in html
    assert "KUKA KRC5" not in html
    assert "ESKİ KART" not in html
    assert "KONTROL SISTEMLERI" in html  # sol ağaç


def test_kategori_konum_izi(istemci, katalog):
    html = istemci.get(f"/tr/kategori/{katalog['krc4']}").text
    iz = re.search(r'<nav class="iz".*?</nav>', html, re.S).group(0)
    assert "Endüstriyel Robotlar" in iz and "KUKA" in iz and "KR C4" in iz


def test_filtreler(istemci, katalog):
    html = istemci.get(f"/tr/kategori/{katalog['elk']}?stokta=1").text
    assert "RÖLE MODÜLÜ 24V" in html and "SİGORTA KUTUSU" not in html
    html = istemci.get(f"/tr/kategori/{katalog['elk']}?fmax=100").text
    assert "SİGORTA KUTUSU" in html and "RÖLE MODÜLÜ 24V" not in html


@pytest.mark.parametrize("q", ["role", "RÖLE", "röle", "Role", "rl-24"])
def test_arama_turkce(istemci, katalog, q):
    yanit = istemci.get("/tr/ara", params={"q": q})
    assert yanit.status_code == 200
    assert "RÖLE MODÜLÜ 24V" in sayfa_denetle(yanit)


def test_arama_sku(istemci, katalog):
    assert "KUKA KRC5 KR 140 R3200-2 PA" in istemci.get("/tr/ara", params={"q": "8301033800019"}).text


def test_bos_arama_ve_bos_sonuc_onerisi(istemci, katalog):
    yanit = istemci.get("/tr/ara", params={"q": "   "})
    assert yanit.status_code == 200
    assert "Aramak için ürün adı" in yanit.text
    yanit = istemci.get("/tr/ara", params={"q": "yokboyleurun"})
    assert yanit.status_code == 200
    assert "Bu ölçütlere uyan ürün bulunamadı." in yanit.text
    assert 'href="/tr/teklif"' in yanit.text
    assert f'href="/tr/kategori/{katalog["elk"]}"' in yanit.text


def test_urun_teklif_zorunlu_kuka(istemci, katalog):
    yanit = istemci.get(f"/tr/urun/{katalog['robot']}")
    assert yanit.status_code == 200
    html = sayfa_denetle(yanit)
    assert "8301033800019" in html and "KRC5-140" in html
    assert f'href="/tr/teklif?urun_id={katalog["robot"]}"' in html
    assert 'action="/tr/sepet/ekle"' not in html
    assert 'data-e2e="teklif-iste"' in html and 'data-e2e="sepete-ekle"' not in html
    assert "Teklif iste" in html


def test_urun_normal_sepet_formu(istemci, katalog):
    html = sayfa_denetle(istemci.get(f"/tr/urun/{katalog['role']}"))
    assert 'action="/tr/sepet/ekle"' in html
    assert 'data-e2e="sepete-ekle"' in html and 'data-e2e="teklif-iste"' not in html
    assert f'name="urun_id" value="{katalog["role"]}"' in html
    assert 'name="adet"' in html and 'name="csrf"' in html
    assert "?urun_id=" not in html
    assert "Stokta: 5 adet" in html


def test_stoksuz_urunde_tedarik_notu(istemci, katalog):
    html = istemci.get(f"/tr/urun/{katalog['stoksuz']}").text
    assert "Tedarik süresi sipariş sonrası teyit edilecek" in html
    assert 'action="/tr/sepet/ekle"' in html


def test_fiyat_tr_misafir_try_kdv_dahil(istemci, katalog):
    blok = _fiyat_blogu(istemci.get(f"/tr/urun/{katalog['role']}").text)
    assert "₺" in blok and "KDV dahil" in blok
    assert 'data-e2e="fiyat-ana" data-para="TRY" data-kdv="dahil"' in blok
    assert 'data-e2e="fiyat-ikincil"' in blok
    assert "5.068,80 ₺" in blok  # 120 € × 35,20 = 4.224,00 + %20 KDV
    assert "35,2000 ₺" in blok   # kur satırı


def test_fiyat_de_ziyaretci_eur_kdv_haric(istemci, katalog):
    csrf = csrf_al(istemci, "/tr/")
    istemci.post("/tercih", data={"csrf": csrf, "ulke": "DE", "sonraki": "/tr/"}, follow_redirects=False)
    blok = _fiyat_blogu(istemci.get(f"/tr/urun/{katalog['role']}").text)
    assert "€" in blok and "120,00 €" in blok
    assert 'data-para="EUR" data-kdv="haric"' in blok
    assert "KDV hariç" in blok and "KDV dahil" not in blok  # K3: KDV'siz EUR gösterimi açıkça yazılır
    assert "₺" not in blok and 'data-e2e="fiyat-ikincil"' not in blok


def test_temsili_rozet(istemci, katalog):
    blok = _fiyat_blogu(istemci.get(f"/tr/urun/{katalog['role']}").text)
    assert 'class="rozet rozet-temsili"' in blok and "Temsili fiyat" in blok


def test_durum_rozeti_yalniz_belirtilmisse(istemci, katalog):
    assert "rozet-durum" not in istemci.get(f"/tr/urun/{katalog['role']}").text
    with istemci_db(istemci) as con:
        con.execute("UPDATE urun SET durum_kodu = 'ikinci_el_test_edildi', durum_ornek = 1 WHERE id = ?",
                    (katalog["role"],))
    html = istemci.get(f"/tr/urun/{katalog['role']}").text
    assert '<span class="rozet rozet-durum">2. el – test edildi</span>' in html
    assert '<span class="rozet rozet-ornek">örnek</span>' in html


def test_yer_tutucu_gorsel(istemci, katalog):
    html = istemci.get(f"/tr/urun/{katalog['robot']}").text
    assert 'src="/statik/yer-tutucu/robot.svg"' in html


@pytest.mark.parametrize("yol_sablonu", [
    "/tr/urun/{pasif}", "/tr/urun/999999", "/tr/urun/abc", "/tr/kategori/999999",
    "/tr/kategori/99999999999999999999", "/tr/urun/99999999999999999999", "/de/urun/{role}",
])
def test_bulunamayanlar_404(istemci, katalog, yol_sablonu):
    yanit = istemci.get(yol_sablonu.format(**katalog))
    assert yanit.status_code == 404
    sayfa_denetle(yanit)


@pytest.mark.parametrize("sorgu", [
    "fmin=x", "fmax=abc", "fmin=-5", "fmin=NaN", "fmax=Infinity", "fmin=1e999",
    "sayfa=-1", "sayfa=abc", "sayfa=0", "sayfa=99999", "sayfa=1e3",
    "sira=zzz", "stokta=evet", "fmin=200&fmax=10",
])
def test_bozuk_sorgu_parametreleri(istemci, katalog, sorgu):
    yanit = istemci.get(f"/tr/kategori/{katalog['elk']}?{sorgu}")
    assert yanit.status_code == 200, sorgu
    sayfa_denetle(yanit)


@pytest.mark.parametrize("q", ['"', "*", "AND", "röle OR", "x" * 500, "\u0000abc", "(", "NEAR("])
def test_bozuk_arama_sorgulari(istemci, katalog, q):
    yanit = istemci.get("/tr/ara", params={"q": q, "sayfa": "-3"})
    assert yanit.status_code == 200, q


def test_en_arayuz_ingilizce(istemci, katalog):
    html = sayfa_denetle(istemci.get("/en/"))
    assert '<html lang="en">' in html
    assert "Categories" in html and "Get a quote for robots" in html
    html = istemci.get(f"/en/urun/{katalog['role']}").text
    assert "Add to cart" in html and "Indicative price" in html
    assert "RÖLE MODÜLÜ 24V" in html  # ürün adı çevrilmez
```

- [ ] **Step 2: Testlerin başarısız olduğunu gör**

Run: `bash dagitim/test-vm.sh tests/test_web_katalog.py -q`
Expected: FAIL. `/tr/`, `/tr/kategori/..`, `/tr/ara` ve `/tr/urun/..` 404 döner (`assert 404 == 200`). 404 bekleyen testler ve `test_bulunamayanlar_404` bu aşamada zaten geçebilir.

- [ ] **Step 3: `app/web/rotalar/katalog.py`**

```python
"""Ana sayfa, kategori ve arama listesi, ürün detayı."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request

from app.katalog.depo import (
    Kategori, ListeSorgusu, ListeSonucu, kategori_agaci, kategori_getir, kategori_yolu,
    one_cikanlar, urun_getir, urun_listele,
)
from app.web.baglam import sablon
from app.web.bagimlilik import db_bagimliligi

router = APIRouter()

SIRALAR = ("ad", "fiyat_artan", "fiyat_azalan")
SAYFA_UST = 10_000
FIYAT_UST = Decimal("100000000")
ARAMA_UZUNLUK = 100
EN_BUYUK_ID = 2**62  # SQLite INTEGER taşmasını önler


def _sayfa(deger: str | None) -> int:
    try:
        n = int(deger) if deger is not None else 1
    except ValueError:
        return 1
    return min(max(n, 1), SAYFA_UST)


def _tutar(deger: str | None) -> Decimal | None:
    if deger is None:
        return None
    deger = deger.strip().replace(",", ".")[:30]
    if not deger:
        return None
    try:
        x = Decimal(deger)
    except InvalidOperation:
        return None
    if not x.is_finite() or x < 0:
        return None
    return min(x, FIYAT_UST)


def _arama_metni(request: Request) -> str:
    ham = request.query_params.get("q") or ""
    temiz = "".join(c for c in ham if c.isprintable())
    return temiz.strip()[:ARAMA_UZUNLUK]


def _sorgu(request: Request, kategori_id: int | None, arama: str | None) -> ListeSorgusu:
    q = request.query_params
    sira = q.get("sira", "ad")
    fmin, fmax = _tutar(q.get("fmin")), _tutar(q.get("fmax"))
    if fmin is not None and fmax is not None and fmin > fmax:
        fmin, fmax = fmax, fmin
    return ListeSorgusu(
        kategori_id=kategori_id,
        arama=arama,
        stokta=q.get("stokta") == "1",
        fiyat_min=fmin,
        fiyat_max=fmax,
        siralama=sira if sira in SIRALAR else "ad",
        sayfa=_sayfa(q.get("sayfa")),
    )


def _url(request: Request, **degisen) -> str:
    parametreler = dict(request.query_params.items())
    for anahtar, deger in degisen.items():
        if deger is None:
            parametreler.pop(anahtar, None)
        else:
            parametreler[anahtar] = str(deger)
    return request.url.path + ("?" + urlencode(parametreler) if parametreler else "")


def _liste(request: Request, con, *, kategori: Kategori | None = None, q: str = ""):
    arama_sayfasi = kategori is None
    s = _sorgu(request, kategori.id if kategori else None, q or None)
    if arama_sayfasi and not q:
        sonuc = ListeSonucu(urunler=[], toplam=0, sayfa=1, sayfa_sayisi=1)
    else:
        sonuc = urun_listele(con, s)
    yol = kategori_yolu(con, kategori.id) if kategori else []
    ham = request.query_params
    filtre_var = s.stokta or s.fiyat_min is not None or s.fiyat_max is not None
    bas, son = max(1, sonuc.sayfa - 2), min(sonuc.sayfa_sayisi, sonuc.sayfa + 2)
    return sablon(request, "liste.html", {
        "kategori": kategori,
        "yol": yol,
        "acik": {k.id for k in yol},
        "agac": kategori_agaci(con),
        "sonuc": sonuc,
        "sorgu": s,
        "q": q,
        "arama_q": q,
        "arama_sayfasi": arama_sayfasi,
        "form": {"fmin": (ham.get("fmin") or "")[:20], "fmax": (ham.get("fmax") or "")[:20]},
        "liste_yolu": request.url.path,
        "sayfa_baglantilari": [(n, _url(request, sayfa=n)) for n in range(bas, son + 1)] if sonuc.sayfa_sayisi > 1 else [],
        "onceki_url": _url(request, sayfa=sonuc.sayfa - 1) if sonuc.sayfa > 1 else None,
        "sonraki_url": _url(request, sayfa=sonuc.sayfa + 1) if sonuc.sayfa < sonuc.sayfa_sayisi else None,
        "temizle_url": request.url.path + ("?" + urlencode({"q": q}) if q else ""),
        "filtre_var": filtre_var,
    })


@router.get("/{dil:dil}/")
def ana_sayfa(request: Request, dil: str, con=Depends(db_bagimliligi)):
    return sablon(request, "ana.html", {"kokler": kategori_agaci(con), "one_cikanlar": one_cikanlar(con, 8)})


@router.get("/{dil:dil}/kategori/{kategori_id:int}")
def kategori_sayfasi(request: Request, dil: str, kategori_id: int, con=Depends(db_bagimliligi)):
    kategori = kategori_getir(con, kategori_id) if kategori_id <= EN_BUYUK_ID else None
    if kategori is None:
        raise HTTPException(status_code=404)
    return _liste(request, con, kategori=kategori)


@router.get("/{dil:dil}/ara")
def arama_sayfasi(request: Request, dil: str, con=Depends(db_bagimliligi)):
    return _liste(request, con, q=_arama_metni(request))


@router.get("/{dil:dil}/urun/{urun_id:int}")
def urun_sayfasi(request: Request, dil: str, urun_id: int, con=Depends(db_bagimliligi)):
    urun = urun_getir(con, urun_id) if urun_id <= EN_BUYUK_ID else None
    if urun is None or not urun.aktif:
        raise HTTPException(status_code=404)
    yol = kategori_yolu(con, urun.kategori_id) if urun.kategori_id else []
    return sablon(request, "urun.html", {"urun": urun, "yol": yol})
```

- [ ] **Step 4: `_makrolar.html` sonuna katalog makrolarını ekle**

```html
{# Kart ve listelerde kısa fiyat satırı #}
{% macro fiyat_kisa(urun, gosterim) -%}
<p class="kart-fiyat"><strong>{{ para(gosterim.ana_tutar, gosterim.ana_para) }}</strong>
{%- if gosterim.kdv_dahil %} <span class="fiyat-kdv">{{ t('fiyat.kdv_dahil') }}</span>
{%- elif gosterim.ana_para != 'TRY' or not kur %} <span class="fiyat-kdv">{{ t('fiyat.kdv_haric') }}</span>{% endif %}
{%- if urun.fiyat_temsili %} <span class="rozet rozet-temsili">{{ t('fiyat.temsili') }}</span>{% endif %}</p>
{%- endmacro %}

{# Ürün kartı (ızgara öğesi) #}
{% macro urun_karti(u) -%}
<article class="kart">
  <a href="/{{ dil }}/urun/{{ u.id }}" tabindex="-1" aria-hidden="true">
    <img class="kart-gorsel" src="{{ gorsel_adresi(u) }}" data-yedek="{{ yer_tutucu(u.kok_kategori_ad) }}" alt="" width="400" height="300" loading="lazy">
  </a>
  <div class="kart-govde">
    <h3 class="kart-baslik"><a href="/{{ dil }}/urun/{{ u.id }}" data-e2e="urun-baglanti">{{ u.ad }}</a></h3>
    <p class="kart-sku">{{ t('urun.sku') }} {{ u.sku }}{% if u.uretici_kodu %} · {{ u.uretici_kodu }}{% endif %}</p>
    {{ fiyat_kisa(u, fiyat_goster(u)) }}
    {% if u.teklif_zorunlu %}<p><span class="rozet rozet-teklif">{{ t('urun.teklif_ile') }}</span></p>
    {% elif u.stok > 0 %}<p class="kart-stok">{{ t('urun.stokta_kisa') }}</p>{% endif %}
  </div>
</article>
{%- endmacro %}

{# Sol kategori ağacı: kökler her zaman, alt dallar yalnız seçili yol üzerinde açık #}
{% macro kategori_agaci(dugumler, secili_id, acik) -%}
<ul class="agac">
{%- for d in dugumler recursive %}
  <li><a href="/{{ dil }}/kategori/{{ d.kategori.id }}"{% if d.kategori.id == secili_id %} aria-current="page"{% endif %}>{{ d.kategori.ad }} <span class="sayi">({{ d.urun_sayisi }})</span></a>
  {%- if d.cocuklar and d.kategori.id in acik %}<ul>{{ loop(d.cocuklar) }}</ul>{% endif %}</li>
{%- endfor %}
</ul>
{%- endmacro %}
```

- [ ] **Step 5: `app/web/sablonlar/ana.html`**

```html
{% extends "taban.html" %}
{% from "_makrolar.html" import urun_karti with context %}
{% block icerik %}
<section class="kahraman">
  <h1>{{ t('katalog.ana_baslik') }}</h1>
  <div class="vurgu-cubuk"></div>
  <p>{{ t('katalog.ana_alt') }}</p>
  <form class="arama" action="/{{ dil }}/ara" method="get" role="search">
    <label for="ana-arama" class="gizli">{{ t('nav.ara_etiket') }}</label>
    <input id="ana-arama" type="search" name="q" placeholder="{{ t('nav.ara_ipucu') }}" maxlength="100">
    <button type="submit">{{ t('nav.ara') }}</button>
  </form>
</section>

<section aria-labelledby="b-kategoriler">
  <h2 id="b-kategoriler">{{ t('katalog.kategoriler') }}</h2>
  <ul class="izgara">
    {% for d in kokler %}
    <li>
      <a class="kok-kart" href="/{{ dil }}/kategori/{{ d.kategori.id }}">
        <img src="{{ yer_tutucu(d.kategori.ad) }}" alt="" width="400" height="300">
        <span class="kok-ad">{{ d.kategori.ad }}</span>
        <span class="sayi">{{ t('katalog.urun_sayisi', adet=d.urun_sayisi) }}</span>
      </a>
    </li>
    {% endfor %}
  </ul>
</section>

<section class="robot-teklif" aria-labelledby="b-robot">
  <h2 id="b-robot">{{ t('katalog.robot_teklif_baslik') }}</h2>
  <p>{{ t('katalog.robot_teklif_metin') }}</p>
  <a class="dugme" href="/{{ dil }}/teklif">{{ t('katalog.robot_teklif_dugme') }}</a>
</section>

<ul class="guven">
  <li><h3>{{ t('katalog.guven_test_baslik') }}</h3><p>{{ t('katalog.guven_test_metin') }}</p></li>
  <li><h3>{{ t('katalog.guven_ihracat_baslik') }}</h3><p>{{ t('katalog.guven_ihracat_metin') }}</p></li>
  <li><h3>{{ t('katalog.guven_destek_baslik') }}</h3><p>{{ t('katalog.guven_destek_metin') }}</p></li>
</ul>

{% if one_cikanlar %}
<section aria-labelledby="b-one">
  <h2 id="b-one">{{ t('katalog.one_cikanlar') }}</h2>
  <ul class="izgara">
    {% for u in one_cikanlar %}<li>{{ urun_karti(u) }}</li>{% endfor %}
  </ul>
</section>
{% endif %}
{% endblock %}
```

- [ ] **Step 6: `app/web/sablonlar/liste.html` (kategori ve arama ortak)**

```html
{% extends "taban.html" %}
{% from "_makrolar.html" import urun_karti, kategori_agaci with context %}
{% block baslik %}{% if kategori %}{{ kategori.ad }}{% elif q %}{{ t('katalog.arama_baslik', q=q) }}{% else %}{{ t('katalog.arama') }}{% endif %}{% endblock %}
{% block icerik %}
<nav class="iz" aria-label="{{ t('katalog.iz') }}">
  <ol>
    <li><a href="/{{ dil }}/">{{ t('genel.ana_sayfa') }}</a></li>
    {% for k in yol %}
    <li>{% if loop.last %}<span aria-current="page">{{ k.ad }}</span>{% else %}<a href="/{{ dil }}/kategori/{{ k.id }}">{{ k.ad }}</a>{% endif %}</li>
    {% endfor %}
    {% if arama_sayfasi %}<li><span aria-current="page">{{ t('katalog.arama') }}</span></li>{% endif %}
  </ol>
</nav>

<div class="liste-duzen">
  <aside class="yan">
    <details open>
      <summary>{{ t('katalog.kategoriler') }}</summary>
      {{ kategori_agaci(agac, kategori.id if kategori else none, acik) }}
    </details>
    <form class="filtre" method="get" action="{{ liste_yolu }}">
      {% if q %}<input type="hidden" name="q" value="{{ q }}">{% endif %}
      <h2 class="yan-baslik">{{ t('katalog.filtreler') }}</h2>
      <div class="alan">
        <label class="secim"><input type="checkbox" name="stokta" value="1"{% if sorgu.stokta %} checked{% endif %}> {{ t('katalog.filtre_stokta') }}</label>
      </div>
      <fieldset class="alan">
        <legend>{{ t('katalog.filtre_fiyat') }}</legend>
        <div class="ikili">
          <div>
            <label for="fmin">{{ t('katalog.filtre_fmin') }}</label>
            <input id="fmin" name="fmin" type="text" inputmode="decimal" maxlength="20" value="{{ form.fmin }}">
          </div>
          <div>
            <label for="fmax">{{ t('katalog.filtre_fmax') }}</label>
            <input id="fmax" name="fmax" type="text" inputmode="decimal" maxlength="20" value="{{ form.fmax }}">
          </div>
        </div>
        <p class="alan-ipucu">{{ t('katalog.filtre_fiyat_not') }}</p>
      </fieldset>
      <div class="alan">
        <label for="sira">{{ t('katalog.siralama') }}</label>
        <select id="sira" name="sira">
          {% for s in ('ad', 'fiyat_artan', 'fiyat_azalan') %}<option value="{{ s }}"{% if sorgu.siralama == s %} selected{% endif %}>{{ t('katalog.sira_' ~ s) }}</option>{% endfor %}
        </select>
      </div>
      <button class="dugme" type="submit">{{ t('katalog.uygula') }}</button>
      {% if filtre_var %}<a class="temizle" href="{{ temizle_url }}">{{ t('katalog.temizle') }}</a>{% endif %}
    </form>
  </aside>

  <section>
    <h1>{% if kategori %}{{ kategori.ad }}{% elif q %}{{ t('katalog.arama_baslik', q=q) }}{% else %}{{ t('katalog.arama') }}{% endif %}</h1>
    {% if arama_sayfasi and not q %}
      <p>{{ t('katalog.arama_bos') }}</p>
    {% elif sonuc.urunler %}
      <p class="sonuc-sayisi">{{ t('katalog.sonuc_sayisi', toplam=sonuc.toplam) }}</p>
      <ul class="izgara">
        {% for u in sonuc.urunler %}<li>{{ urun_karti(u) }}</li>{% endfor %}
      </ul>
      {% if sonuc.sayfa_sayisi > 1 %}
      <nav class="sayfalama" aria-label="{{ t('katalog.sayfalama') }}">
        <ul>
          {% if onceki_url %}<li><a href="{{ onceki_url }}" rel="prev">{{ t('katalog.onceki') }}</a></li>{% endif %}
          {% for n, url in sayfa_baglantilari %}
          <li>{% if n == sonuc.sayfa %}<span aria-current="page">{{ n }}</span>{% else %}<a href="{{ url }}" aria-label="{{ t('katalog.sayfa_n', n=n) }}">{{ n }}</a>{% endif %}</li>
          {% endfor %}
          {% if sonraki_url %}<li><a href="{{ sonraki_url }}" rel="next">{{ t('katalog.sonraki') }}</a></li>{% endif %}
        </ul>
      </nav>
      {% endif %}
    {% else %}
      <div class="bos-sonuc">
        <p><strong>{{ t('katalog.bos_sonuc') }}</strong></p>
        <ul>
          {% if filtre_var %}<li><a href="{{ temizle_url }}">{{ t('katalog.bos_oneri_filtre') }}</a></li>{% endif %}
          <li><a href="/{{ dil }}/teklif">{{ t('katalog.bos_oneri_teklif') }}</a></li>
        </ul>
        <p>{{ t('katalog.bos_oneri_kategori') }}</p>
        <ul class="etiketler">
          {% for d in agac %}<li><a href="/{{ dil }}/kategori/{{ d.kategori.id }}">{{ d.kategori.ad }}</a></li>{% endfor %}
        </ul>
      </div>
    {% endif %}
  </section>
</div>
{% endblock %}
```

- [ ] **Step 7: `app/web/sablonlar/urun.html`**

```html
{% extends "taban.html" %}
{% from "_makrolar.html" import fiyat with context %}
{% block baslik %}{{ urun.ad }}{% endblock %}
{% block icerik %}
<nav class="iz" aria-label="{{ t('katalog.iz') }}">
  <ol>
    <li><a href="/{{ dil }}/">{{ t('genel.ana_sayfa') }}</a></li>
    {% for k in yol %}<li><a href="/{{ dil }}/kategori/{{ k.id }}">{{ k.ad }}</a></li>{% endfor %}
    <li><span aria-current="page">{{ urun.ad }}</span></li>
  </ol>
</nav>

<article class="urun-detay">
  <div class="urun-gorsel">
    <img src="{{ gorsel_adresi(urun) }}" data-yedek="{{ yer_tutucu(urun.kok_kategori_ad) }}" alt="{{ urun.ad }}" width="400" height="300">
  </div>
  <div class="urun-bilgi">
    <h1>{{ urun.ad }}</h1>
    {% if urun.durum_kodu != 'belirtilmemis' %}
    <p><span class="rozet rozet-durum">{{ t('durum.' ~ urun.durum_kodu) }}</span>{% if urun.durum_ornek %} <span class="rozet rozet-ornek">{{ t('urun.ornek') }}</span>{% endif %}</p>
    {% endif %}
    <dl class="ozellik">
      <dt>{{ t('urun.sku') }}</dt><dd>{{ urun.sku }}</dd>
      {% if urun.uretici_kodu %}<dt>{{ t('urun.uretici_kodu') }}</dt><dd>{{ urun.uretici_kodu }}</dd>{% endif %}
      {% if yol %}<dt>{{ t('urun.kategori') }}</dt><dd>{{ yol | map(attribute='ad') | join(' › ') }}</dd>{% endif %}
    </dl>

    {{ fiyat(urun, fiyat_goster(urun)) }}

    {% if urun.stok > 0 %}
      <p class="stok-not">{{ t('urun.stokta', adet=urun.stok) }}</p>
    {% elif urun.tedarik_suresi_gun %}
      <p class="stok-not stok-yok">{{ t('urun.tedarik_gun', gun=urun.tedarik_suresi_gun) }}</p>
    {% else %}
      <p class="stok-not stok-yok">{{ t('urun.tedarik_teyit') }}</p>
    {% endif %}

    {% if urun.teklif_zorunlu %}
      <p>{{ t('urun.teklif_aciklama') }}</p>
      <a class="dugme" href="/{{ dil }}/teklif?urun_id={{ urun.id }}" data-e2e="teklif-iste">{{ t('urun.teklif_iste') }}</a>
    {% else %}
      <form class="sepet-form" method="post" action="/{{ dil }}/sepet/ekle">
        <input type="hidden" name="csrf" value="{{ csrf }}">
        <input type="hidden" name="urun_id" value="{{ urun.id }}">
        <div class="alan">
          <label for="adet">{{ t('urun.adet') }}</label>
          <input id="adet" name="adet" type="number" min="1" max="99" value="1" inputmode="numeric" required>
        </div>
        <button class="dugme" type="submit" data-e2e="sepete-ekle">{{ t('urun.sepete_ekle') }}</button>
      </form>
    {% endif %}

    <section class="ozet-kutu" aria-labelledby="b-teslim">
      <h2 id="b-teslim">{{ t('urun.teslim_baslik') }}</h2>
      <p>{{ t('urun.teslim_ozet') }}</p>
      <p>{{ t('urun.iade_ozet') }}</p>
      <p><a href="/{{ dil }}/yasal/iade">{{ t('urun.iade_bag') }}</a> · <a href="/{{ dil }}/yasal/garanti">{{ t('urun.garanti_bag') }}</a></p>
    </section>
  </div>
</article>
{% endblock %}
```

- [ ] **Step 8: Testlerin geçtiğini gör**

Run: `bash dagitim/test-vm.sh tests/test_web_katalog.py tests/test_web_cekirdek.py -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/web/rotalar/katalog.py app/web/sablonlar/ana.html app/web/sablonlar/liste.html app/web/sablonlar/urun.html app/web/sablonlar/_makrolar.html tests/test_web_katalog.py
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m $'feat(web): ana sayfa, kategori/arama listesi ve ürün detayı\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

---

### Görev 13: Hesap ekranları (kayıt, giriş, çıkış, hesabım)

**Files:**
- Create: `app/web/rotalar/hesap.py`
- Create: `app/web/sablonlar/kayit.html`, `app/web/sablonlar/giris.html`, `app/web/sablonlar/hesabim.html`
- Modify: `app/web/sablonlar/_makrolar.html` (sonuna `metin_alani` makrosu)
- Test: `tests/test_web_hesap.py`

**Interfaces:**
- Consumes: `app.hesap.servis.{KayitGirdisi, KayitHatasi(.alan, .kod), Musteri, giris, kayit_ol}`, `app.fiyat.kurallar.MusteriTipi`, `app.sepet.servis.{sepet_bul, birlestir}`, `app.siparis.servis.musteri_siparisleri`, `app.teklif.servis.teklifler`, `app.web.baglam.{ULKELER, bildir, mevcut_sepet_id, sablon, simdi}`, `app.web.guvenlik.{aktif_musteri, csrf_dogrula, guvenli_sonraki}`, `app.state.hiz` (HizSiniri).
- Produces:
  - Rotalar: `GET/POST /{dil:dil}/kayit` (`?tip=`, `?sonraki=`; kayıt otomatik giriş yapar, misafir sepetini birleştirir ve `sonraki`'ye ya da `/hesabim`'a 303 ile gider — K12), `GET/POST /{dil:dil}/giris` (`?sonraki=`), `POST /{dil:dil}/cikis`, `GET /{dil:dil}/hesabim`.
  - `oturum_ac(request, con, musteri) -> None`: `session["mid"]` yazar, misafir sepetini üyeninkiyle birleştirir ve birleşmeyi `bildir` ile duyurur. Görev 14 ödeme adımında girişe yönlendirirken bu fonksiyonu yeniden kullanabilir.
  - Form alanları (K12): kayıt `tip, ad, eposta, parola, ulke, vergi_kimlik_no, vergi_dairesi, vat_id, kvkk_onay, iys_onay, sonraki, csrf`; giriş `eposta, parola, sonraki, csrf`. `data-e2e="kayit-gonder"`, başlıkta `data-e2e="cikis"`.
  - Hata metinleri `hata_kodu.<kod>` (K14/K17); bu görev Görev 7 kodlarına ek olarak yalnız `tip_sec` ve `gecersiz_ulke` kodlarını kullanır (Görev 11 JSON'unda).
  - Hız sınırı anahtarı `"giris:<ip>"`. Yönetici girişi kendi önekini kullanmalı (ör. `"yonetim:<ip>"`).
  - Girişsiz `/hesabim` isteği `303 /{dil}/giris?sonraki=%2F{dil}%2Fhesabim` ile yönlendirilir.

- [ ] **Step 1: Başarısız testleri yaz — `tests/test_web_hesap.py`**

```python
import re

import pytest

from app.sepet.servis import adet_toplam, ekle, sepet_bul
from app.teklif.servis import TeklifGirdisi, teklif_olustur
from tests.conftest import csrf_al, istemci_db, oturum_oku, sayfa_denetle, urun_ekle

PAROLA = "demo-parola-123"
EPOSTA = "qatestuser+bireysel@example.com"


def _kayit(istemci, dil="tr", **ek):
    csrf = csrf_al(istemci, f"/{dil}/kayit")
    veri = {"csrf": csrf, "tip": "bireysel", "ad": "QA Test Kullanıcı", "eposta": EPOSTA,
            "parola": PAROLA, "kvkk_onay": "1", "ulke": "DE"}
    veri.update(ek)
    return istemci.post(f"/{dil}/kayit", data=veri, follow_redirects=False)


def _cikis(istemci):
    csrf = csrf_al(istemci, "/tr/giris")
    return istemci.post("/tr/cikis", data={"csrf": csrf}, follow_redirects=False)


def _giris(istemci, eposta=EPOSTA, parola=PAROLA, sonraki=None):
    csrf = csrf_al(istemci, "/tr/giris")
    veri = {"csrf": csrf, "eposta": eposta, "parola": parola}
    if sonraki is not None:
        veri["sonraki"] = sonraki
    return istemci.post("/tr/giris", data=veri, follow_redirects=False)


def _musteri(istemci, eposta):
    with istemci_db(istemci) as con:
        return con.execute("SELECT * FROM musteri WHERE eposta = ?", (eposta,)).fetchone()


def test_kayit_sayfasi(istemci):
    html = sayfa_denetle(istemci.get("/tr/kayit"))
    assert 'data-e2e="kayit-gonder"' in html
    for tip in ("bireysel", "kurumsal", "yurtdisi"):
        assert f'name="tip" value="{tip}"' in html
    assert 'href="/tr/yasal/kvkk"' in html
    assert "gerçek parolanızı" in html
    assert 'data-tipler="kurumsal"' in html and "yalnız kurumsal" in html
    iys = re.search(r'<input[^>]*name="iys_onay"[^>]*>', html).group(0)
    assert "checked" not in iys
    assert 'name="vergi_kimlik_no"' in html and 'name="vat_id"' in html  # JS olmadan da tüm alanlar var


def test_kayit_tip_ve_sonraki_parametresi(istemci):
    html = istemci.get("/tr/kayit", params={"tip": "kurumsal", "sonraki": "/tr/sepet"}).text
    assert re.search(r'name="tip" value="kurumsal"[^>]*checked', html)
    assert '<input type="hidden" name="sonraki" value="/tr/sepet">' in html
    html = istemci.get("/tr/kayit", params={"sonraki": "https://evil.com"}).text
    assert '<input type="hidden" name="sonraki" value="">' in html


def test_kayit_sonrasi_sonraki_adrese_gider(istemci):
    yanit = _kayit(istemci, sonraki="/tr/sepet")
    assert yanit.status_code == 303 and yanit.headers["location"] == "/tr/sepet"
    assert "mid" in oturum_oku(istemci)  # otomatik giriş
    _cikis(istemci)
    yanit = _kayit(istemci, eposta="qatestuser+evil@example.com", sonraki="https://evil.com")
    assert yanit.headers["location"] == "/"


def test_misafir_sepeti_kayitta_birlesir(istemci, simdi):
    csrf_al(istemci, "/tr/kayit")
    oid = oturum_oku(istemci)["oid"]
    with istemci_db(istemci) as con:
        uid = urun_ekle(con, sku="KB-1", ad="KAYIT ÜRÜNÜ")
        ekle(con, sepet_bul(con, oid, None, simdi), uid, 2)
    assert _kayit(istemci).status_code == 303
    html = istemci.get("/tr/hesabim").text
    assert "Misafir sepetinizdeki 1 kalem hesabınızın sepetiyle birleştirildi." in html
    with istemci_db(istemci) as con:
        mid = con.execute("SELECT id FROM musteri WHERE eposta = ?", (EPOSTA,)).fetchone()[0]
        uye = con.execute("SELECT id FROM sepet WHERE musteri_id = ?", (mid,)).fetchone()[0]
        assert adet_toplam(con, uye) == 2


def test_kayit_sayfasi_en(istemci):
    html = istemci.get("/en/kayit").text
    assert "Create account" in html and 'href="/en/yasal/kvkk"' in html


def test_kayit_bireysel(istemci):
    yanit = _kayit(istemci)
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/tr/hesabim"
    m = _musteri(istemci, EPOSTA)
    assert m["tip"] == "bireysel" and m["ulke"] == "TR" and m["iys_onay"] == 0
    html = sayfa_denetle(istemci.get("/tr/hesabim"))
    assert "QA Test Kullanıcı" in html and "Hesabınız oluşturuldu." in html


def test_kayit_kurumsal_gecerli_vkn(istemci):
    eposta = "qatestuser+kurumsal@example.com"
    yanit = _kayit(istemci, tip="kurumsal", ad="QA Test Makina AS", eposta=eposta,
                   vergi_kimlik_no="1234567890", vergi_dairesi="Kadıköy", iys_onay="1")
    assert yanit.status_code == 303
    m = _musteri(istemci, eposta)
    assert m["tip"] == "kurumsal" and m["vergi_kimlik_no"] == "1234567890"
    assert m["vergi_dairesi"] == "Kadıköy" and m["ulke"] == "TR" and m["iys_onay"] == 0


def test_kayit_yurtdisi(istemci):
    eposta = "qatestuser+yurtdisi@example.com"
    yanit = _kayit(istemci, tip="yurtdisi", ad="QA Test GmbH", eposta=eposta, ulke="DE",
                   vat_id="DE123456789", iys_onay="1", vergi_kimlik_no="1234567890")
    assert yanit.status_code == 303
    m = _musteri(istemci, eposta)
    assert m["tip"] == "yurtdisi" and m["ulke"] == "DE" and m["vat_id"] == "DE123456789"
    assert m["iys_onay"] == 0 and m["vergi_kimlik_no"] is None


def test_kayit_yurtdisi_turkiye_secilemez(istemci):
    yanit = _kayit(istemci, tip="yurtdisi", eposta="qatestuser+yd2@example.com", ulke="TR")
    assert yanit.status_code == 400
    assert 'id="h-ulke"' in yanit.text


def test_hatali_vkn_alaninda_gosterilir_veri_korunur(istemci):
    yanit = _kayit(istemci, tip="kurumsal", ad="QA Test Makina AS", eposta="qatestuser+vkn@example.com",
                   parola="gizli-parola-123", vergi_kimlik_no="4728136593", vergi_dairesi="Kadıköy")
    assert yanit.status_code == 400
    html = sayfa_denetle(yanit)
    assert '<p class="alan-hata" id="h-vergi_kimlik_no">Vergi kimlik numarası geçersiz' in html
    assert 'aria-invalid="true"' in html
    assert 'value="QA Test Makina AS"' in html
    assert 'value="qatestuser+vkn@example.com"' in html
    assert 'value="4728136593"' in html
    assert 'value="Kadıköy"' in html
    assert "gizli-parola-123" not in html
    assert re.search(r'name="tip" value="kurumsal"[^>]*checked', html)
    assert _musteri(istemci, "qatestuser+vkn@example.com") is None


def test_tip_secilmeden_kayit(istemci):
    yanit = _kayit(istemci, tip="")
    assert yanit.status_code == 400
    assert "Müşteri tipini seçin." in yanit.text


def test_eposta_tekrar(istemci):
    assert _kayit(istemci).status_code == 303
    _cikis(istemci)
    yanit = _kayit(istemci, ad="Başka Kişi")
    assert yanit.status_code == 400
    assert "Bu e-posta adresiyle zaten bir hesap var." in yanit.text
    assert 'value="Başka Kişi"' in yanit.text


def test_giris_cikis(istemci):
    _kayit(istemci)
    yanit = _cikis(istemci)
    assert yanit.status_code == 303 and yanit.headers["location"] == "/tr/"
    assert "mid" not in oturum_oku(istemci)
    assert istemci.get("/tr/hesabim", follow_redirects=False).status_code == 303
    yanit = _giris(istemci)
    assert yanit.status_code == 303 and yanit.headers["location"] == "/tr/hesabim"
    assert "QA Test Kullanıcı" in istemci.get("/tr/hesabim").text


def test_yanlis_parola(istemci):
    _kayit(istemci)
    _cikis(istemci)
    yanit = _giris(istemci, parola="yanlis-parola-99")
    assert yanit.status_code == 400
    html = sayfa_denetle(yanit)
    assert "E-posta veya parola hatalı." in html
    assert f'value="{EPOSTA}"' in html
    assert "yanlis-parola-99" not in html


def test_onbirinci_denemede_429(istemci):
    _kayit(istemci)
    _cikis(istemci)
    for _ in range(10):
        assert _giris(istemci, parola="yanlis-parola-99").status_code == 400
    yanit = _giris(istemci)  # doğru parola bile olsa sınır aşıldı
    assert yanit.status_code == 429
    assert "Çok fazla deneme" in yanit.text


def test_sonraki_acik_yonlendirme_engeli(istemci):
    _kayit(istemci)
    _cikis(istemci)
    yanit = _giris(istemci, sonraki="https://evil.com")
    assert yanit.status_code == 303 and yanit.headers["location"] == "/"
    _cikis(istemci)
    yanit = _giris(istemci, sonraki="/tr/sepet")
    assert yanit.headers["location"] == "/tr/sepet"


def test_giris_formu_sonraki_tasir(istemci):
    html = istemci.get("/tr/giris", params={"sonraki": "/tr/odeme"}).text
    assert 'name="sonraki" value="/tr/odeme"' in html
    html = istemci.get("/tr/giris", params={"sonraki": "//evil.com"}).text
    assert '<input type="hidden" name="sonraki" value="">' in html
    assert 'value="//evil.com"' not in html


def test_misafir_sepeti_giriste_birlesir(istemci, simdi):
    assert _kayit(istemci).status_code == 303  # kayıt aynı zamanda giriş yapar
    _cikis(istemci)
    csrf_al(istemci, "/tr/giris")  # yeni misafir oturumu (oid) oluşur
    oid = oturum_oku(istemci)["oid"]
    with istemci_db(istemci) as con:
        uid = urun_ekle(con, sku="BR-1", ad="BİRLEŞME ÜRÜNÜ")
        mid = con.execute("SELECT id FROM musteri WHERE eposta = ?", (EPOSTA,)).fetchone()[0]
        uye = sepet_bul(con, None, mid, simdi)
        ekle(con, uye, uid, 1)
        misafir = sepet_bul(con, oid, None, simdi)
        ekle(con, misafir, uid, 2)
    assert _giris(istemci).status_code == 303
    html = istemci.get("/tr/hesabim").text
    assert "Misafir sepetinizdeki 1 kalem hesabınızın sepetiyle birleştirildi." in html
    assert '<span class="sayac"' in html and ">3</span>" in html
    with istemci_db(istemci) as con:
        assert adet_toplam(con, uye) == 3
        assert con.execute("SELECT COUNT(*) FROM sepet WHERE oturum_id = ?", (oid,)).fetchone()[0] == 0


def test_hesabim_girissiz_yonlendirir(istemci):
    yanit = istemci.get("/tr/hesabim", follow_redirects=False)
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/tr/giris?sonraki=%2Ftr%2Fhesabim"


def test_hesabim_teklifleri_ve_bos_siparisleri_listeler(istemci, simdi):
    _kayit(istemci)
    with istemci_db(istemci) as con:
        mid = con.execute("SELECT id FROM musteri WHERE eposta = ?", (EPOSTA,)).fetchone()[0]
        tk = teklif_olustur(con, TeklifGirdisi(ad="QA Test", eposta=EPOSTA, ulke="TR",
                                               mesaj="Robot için fiyat rica ederim", musteri_id=mid), simdi)
    html = sayfa_denetle(istemci.get("/tr/hesabim"))
    assert tk.no in html and "Yeni" in html
    assert "Henüz siparişiniz yok." in html


def test_cikis_csrfsiz_403(istemci):
    _kayit(istemci)
    assert istemci.post("/tr/cikis", data={}, follow_redirects=False).status_code == 403
```

- [ ] **Step 2: Testlerin başarısız olduğunu gör**

Run: `bash dagitim/test-vm.sh tests/test_web_hesap.py -q`
Expected: FAIL. `/tr/kayit` 404 döndüğü için `csrf_al` "sayfasında csrf alanı yok" hatası vermez; ancak `POST /tr/kayit` 404 döner (`assert 404 == 303`).

- [ ] **Step 3: `app/web/rotalar/hesap.py`**

```python
"""Kayıt, giriş, çıkış ve hesabım."""
from __future__ import annotations

import sqlite3
import time
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app.fiyat.kurallar import MusteriTipi
from app.hesap.servis import KayitGirdisi, KayitHatasi, Musteri, giris, kayit_ol
from app.sepet.servis import birlestir, sepet_bul
from app.siparis.servis import musteri_siparisleri
from app.teklif.servis import teklifler
from app.web.baglam import ULKELER, bildir, mevcut_sepet_id, sablon, simdi
from app.web.guvenlik import aktif_musteri, csrf_dogrula, guvenli_sonraki
from app.web.bagimlilik import db_bagimliligi

router = APIRouter()

TIPLER = tuple(t.value for t in MusteriTipi)
UZUNLUK = 200
PAROLA_UST = 200


def _kirp(deger: str | None) -> str:
    return (deger or "").strip()[:UZUNLUK]


def oturum_ac(request: Request, con: sqlite3.Connection, musteri: Musteri) -> None:
    """Oturumu müşteriye bağlar; misafir sepeti varsa üye sepetiyle birleştirir ve bildirir."""
    misafir = mevcut_sepet_id(con, request, None)
    request.session["mid"] = musteri.id
    if misafir is not None:
        uye = sepet_bul(con, None, musteri.id, simdi())
        if uye != misafir:
            adet = birlestir(con, misafir, uye)
            if adet:
                bildir(request, "hesap.sepet_birlesti", adet=adet)


def _bos_deger(tip: str = "") -> dict:
    return {"tip": tip, "ad": "", "eposta": "", "ulke": "DE", "vergi_kimlik_no": "",
            "vergi_dairesi": "", "vat_id": "", "iys_onay": False, "kvkk_onay": False}


def _hata_metni(request: Request, dil: str, kod: str) -> str:
    ceviri = request.app.state.ceviri
    anahtar = f"hata_kodu.{kod}"  # K14/K17: Görev 7 kodları (zorunlu, gecersiz, gecersiz_vkn, parola_kisa, kvkk_onay_yok, eposta_kayitli)
    return ceviri.t(dil, anahtar if ceviri.var(anahtar) else "hata_kodu.gecersiz")


def _kayit_formu(request: Request, deger: dict, hatalar: dict, durum: int = 200, sonraki: str = ""):
    return sablon(request, "kayit.html", {"deger": deger, "hatalar": hatalar, "sonraki": sonraki}, durum=durum)


@router.get("/{dil:dil}/kayit")
def kayit_sayfasi(request: Request, dil: str, con=Depends(db_bagimliligi)):
    if aktif_musteri(request, con) is not None:
        return RedirectResponse(f"/{dil}/hesabim", status_code=303)
    tip = request.query_params.get("tip", "")
    sonraki = guvenli_sonraki(request.query_params.get("sonraki"), "")
    return _kayit_formu(request, _bos_deger(tip if tip in TIPLER else ""), {}, sonraki=sonraki)


@router.post("/{dil:dil}/kayit", dependencies=[Depends(csrf_dogrula)])
def kayit_gonder(
    request: Request,
    dil: str,
    tip: str = Form(""),
    ad: str = Form(""),
    eposta: str = Form(""),
    parola: str = Form(""),
    ulke: str = Form(""),
    vergi_kimlik_no: str = Form(""),
    vergi_dairesi: str = Form(""),
    vat_id: str = Form(""),
    kvkk_onay: str = Form(""),
    iys_onay: str = Form(""),
    sonraki: str = Form(""),
    con=Depends(db_bagimliligi),
):
    form_sonraki = guvenli_sonraki(sonraki, "")
    deger = {
        "tip": tip if tip in TIPLER else "",
        "ad": _kirp(ad),
        "eposta": _kirp(eposta),
        "ulke": _kirp(ulke).upper(),
        "vergi_kimlik_no": _kirp(vergi_kimlik_no).replace(" ", ""),
        "vergi_dairesi": _kirp(vergi_dairesi),
        "vat_id": _kirp(vat_id),
        "iys_onay": iys_onay == "1",
        "kvkk_onay": kvkk_onay == "1",
    }
    if not deger["tip"]:
        return _kayit_formu(request, deger, {"tip": _hata_metni(request, dil, "tip_sec")}, 400, form_sonraki)
    if len(parola) > PAROLA_UST:
        return _kayit_formu(request, deger, {"parola": _hata_metni(request, dil, "gecersiz")}, 400, form_sonraki)
    musteri_tipi = MusteriTipi(deger["tip"])
    kurumsal = musteri_tipi is MusteriTipi.KURUMSAL
    yurtdisi = musteri_tipi is MusteriTipi.YURTDISI
    if yurtdisi and (deger["ulke"] not in ULKELER or deger["ulke"] == "TR"):
        return _kayit_formu(request, deger, {"ulke": _hata_metni(request, dil, "gecersiz_ulke")}, 400, form_sonraki)
    girdi = KayitGirdisi(
        tip=musteri_tipi,
        ad=deger["ad"],
        eposta=deger["eposta"],
        parola=parola,
        ulke=deger["ulke"] if yurtdisi else "TR",
        kvkk_onay=deger["kvkk_onay"],
        iys_onay=deger["iys_onay"] if musteri_tipi is MusteriTipi.BIREYSEL else False,
        vergi_kimlik_no=(deger["vergi_kimlik_no"] or None) if kurumsal else None,
        vergi_dairesi=(deger["vergi_dairesi"] or None) if kurumsal else None,
        vat_id=(deger["vat_id"] or None) if yurtdisi else None,
    )
    try:
        with con:
            musteri = kayit_ol(con, girdi, simdi())
            oturum_ac(request, con, musteri)
    except KayitHatasi as hata:
        return _kayit_formu(request, deger, {hata.alan: _hata_metni(request, dil, hata.kod)}, 400, form_sonraki)
    bildir(request, "hesap.kayit_tamam")
    hedef = guvenli_sonraki(sonraki) if sonraki else f"/{dil}/hesabim"  # K12: otomatik giriş + sonraki
    return RedirectResponse(hedef, status_code=303)


@router.get("/{dil:dil}/giris")
def giris_sayfasi(request: Request, dil: str, con=Depends(db_bagimliligi)):
    sonraki = guvenli_sonraki(request.query_params.get("sonraki"), "")
    if aktif_musteri(request, con) is not None:
        return RedirectResponse(sonraki or f"/{dil}/hesabim", status_code=303)
    return sablon(request, "giris.html", {"eposta": "", "sonraki": sonraki, "hata_anahtar": None})


@router.post("/{dil:dil}/giris", dependencies=[Depends(csrf_dogrula)])
def giris_gonder(
    request: Request,
    dil: str,
    eposta: str = Form(""),
    parola: str = Form(""),
    sonraki: str = Form(""),
    con=Depends(db_bagimliligi),
):
    eposta = _kirp(eposta)
    form_sonraki = guvenli_sonraki(sonraki, "")
    ip = request.client.host if request.client else "bilinmiyor"
    if not request.app.state.hiz.izin(f"giris:{ip}", time.monotonic()):
        return sablon(request, "giris.html",
                      {"eposta": eposta, "sonraki": form_sonraki, "hata_anahtar": "hesap.cok_deneme"}, durum=429)
    musteri = giris(con, eposta, parola[:PAROLA_UST]) if eposta and parola else None
    if musteri is None:
        return sablon(request, "giris.html",
                      {"eposta": eposta, "sonraki": form_sonraki, "hata_anahtar": "hesap.hatali_giris"}, durum=400)
    with con:
        oturum_ac(request, con, musteri)
    bildir(request, "hesap.giris_tamam")
    hedef = guvenli_sonraki(sonraki) if sonraki else f"/{dil}/hesabim"
    return RedirectResponse(hedef, status_code=303)


@router.post("/{dil:dil}/cikis", dependencies=[Depends(csrf_dogrula)])
def cikis(request: Request, dil: str):
    request.session.pop("mid", None)
    request.session.pop("oid", None)  # misafir sepeti yeni oturumla sıfırdan başlar
    bildir(request, "hesap.cikis_yapildi")
    return RedirectResponse(f"/{dil}/", status_code=303)


@router.get("/{dil:dil}/hesabim")
def hesabim(request: Request, dil: str, con=Depends(db_bagimliligi)):
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return RedirectResponse(f"/{dil}/giris?sonraki=" + quote(f"/{dil}/hesabim", safe=""), status_code=303)
    with con:  # musteri_siparisleri zaman aşımı uygular (yazma)
        siparisler = musteri_siparisleri(con, musteri.id, simdi())
    return sablon(request, "hesabim.html", {
        "musteri": musteri,
        "siparisler": siparisler,
        "teklifler": teklifler(con, musteri_id=musteri.id),
    })
```

- [ ] **Step 4: `_makrolar.html` sonuna form alanı makrosunu ekle**

```html
{# Etiketli metin alanı; hata ve ipucu aria-describedby ile bağlanır. tipler: JS ile gizlenecek tipler (boşlukla ayrılmış). #}
{% macro metin_alani(ad, etiket, deger='', hata=none, tur='text', kosul=none, ipucu=none, otomatik='off', zorunlu=false, tipler=none, uzunluk=200) -%}
<div class="alan{% if hata %} hatali{% endif %}"{% if tipler %} data-tipler="{{ tipler }}"{% endif %}>
  <label for="a-{{ ad }}">{{ etiket }}{% if kosul %} <span class="etiket-kosul">{{ kosul }}</span>{% endif %}</label>
  <input id="a-{{ ad }}" name="{{ ad }}" type="{{ tur }}" value="{{ deger }}" autocomplete="{{ otomatik }}" maxlength="{{ uzunluk }}"
    {%- if zorunlu %} required{% endif %}
    {%- if hata or ipucu %} aria-describedby="{% if ipucu %}i-{{ ad }}{% endif %}{% if hata %} h-{{ ad }}{% endif %}"{% endif %}
    {%- if hata %} aria-invalid="true"{% endif %}>
  {%- if ipucu %}<p class="alan-ipucu" id="i-{{ ad }}">{{ ipucu }}</p>{% endif %}
  {%- if hata %}<p class="alan-hata" id="h-{{ ad }}">{{ hata }}</p>{% endif %}
</div>
{%- endmacro %}
```

- [ ] **Step 5: `app/web/sablonlar/kayit.html`**

Bütün alanlar JS olmadan görünür; tipe özel alanlar `data-tipler` ve "yalnız …" etiketi taşır. `site.js` seçili tipe göre ilgisiz alanları gizler. Sunucu, ilgisiz alanları zaten yok sayar.

```html
{% extends "taban.html" %}
{% from "_makrolar.html" import metin_alani with context %}
{% block baslik %}{{ t('hesap.kayit_baslik') }}{% endblock %}
{% block icerik %}
<h1>{{ t('hesap.kayit_baslik') }}</h1>
<p class="uyari" role="note">{{ t('hesap.demo_parola_uyarisi') }}</p>
{% if hatalar %}
<div class="form-hata-ozet" role="alert">
  <p>{{ t('hesap.form_hatali') }}</p>
  <ul>{% for alan, metin in hatalar.items() %}<li>{{ metin }}</li>{% endfor %}</ul>
</div>
{% endif %}
<form class="form" method="post" action="/{{ dil }}/kayit" novalidate>
  <input type="hidden" name="csrf" value="{{ csrf }}">
  <input type="hidden" name="sonraki" value="{{ sonraki }}">

  <fieldset class="tip-secim{% if hatalar.tip %} hatali{% endif %}">
    <legend>{{ t('hesap.tip_baslik') }}</legend>
    {% for tip in ('bireysel', 'kurumsal', 'yurtdisi') %}
    <label><input type="radio" name="tip" value="{{ tip }}"{% if deger.tip == tip %} checked{% endif %} required>
      <span>{{ t('hesap.tip_' ~ tip) }}<small>{{ t('hesap.tip_' ~ tip ~ '_aciklama') }}</small></span></label>
    {% endfor %}
  </fieldset>
  {% if hatalar.tip %}<p class="alan-hata" id="h-tip">{{ hatalar.tip }}</p>{% endif %}

  {{ metin_alani('ad', t('hesap.ad'), deger=deger.ad, hata=hatalar.ad, otomatik='name', zorunlu=true) }}
  {{ metin_alani('eposta', t('hesap.eposta'), deger=deger.eposta, hata=hatalar.eposta, tur='email', otomatik='email', zorunlu=true) }}
  {{ metin_alani('parola', t('hesap.parola'), hata=hatalar.parola, tur='password', ipucu=t('hesap.parola_ipucu'), otomatik='new-password', zorunlu=true) }}

  {{ metin_alani('vergi_kimlik_no', t('hesap.vkn'), deger=deger.vergi_kimlik_no, hata=hatalar.vergi_kimlik_no, kosul=t('hesap.yalniz_kurumsal'), ipucu=t('hesap.vkn_ipucu'), tipler='kurumsal', uzunluk=11) }}
  {{ metin_alani('vergi_dairesi', t('hesap.vergi_dairesi'), deger=deger.vergi_dairesi, hata=hatalar.vergi_dairesi, kosul=t('hesap.yalniz_kurumsal'), tipler='kurumsal') }}

  <div class="alan{% if hatalar.ulke %} hatali{% endif %}" data-tipler="yurtdisi">
    <label for="a-ulke">{{ t('hesap.ulke') }} <span class="etiket-kosul">{{ t('hesap.yalniz_yurtdisi') }}</span></label>
    <select id="a-ulke" name="ulke" autocomplete="country"{% if hatalar.ulke %} aria-invalid="true" aria-describedby="h-ulke"{% endif %}>
      {% for u in ulkeler %}{% if u != 'TR' %}<option value="{{ u }}"{% if deger.ulke == u %} selected{% endif %}>{{ t('ulke.' ~ u) }}</option>{% endif %}{% endfor %}
    </select>
    {% if hatalar.ulke %}<p class="alan-hata" id="h-ulke">{{ hatalar.ulke }}</p>{% endif %}
  </div>
  {{ metin_alani('vat_id', t('hesap.vat_id'), deger=deger.vat_id, hata=hatalar.vat_id, kosul=t('hesap.yalniz_yurtdisi'), tipler='yurtdisi', uzunluk=30) }}

  <div class="alan{% if hatalar.kvkk_onay %} hatali{% endif %}">
    <label class="secim"><input type="checkbox" name="kvkk_onay" value="1"{% if deger.kvkk_onay %} checked{% endif %} required> {{ t('hesap.kvkk_onay') }}</label>
    <p class="alan-ipucu"><a href="/{{ dil }}/yasal/kvkk">{{ t('hesap.kvkk_bag') }}</a></p>
    {% if hatalar.kvkk_onay %}<p class="alan-hata" id="h-kvkk_onay">{{ hatalar.kvkk_onay }}</p>{% endif %}
  </div>
  <div class="alan" data-tipler="bireysel">
    <label class="secim"><input type="checkbox" name="iys_onay" value="1"{% if deger.iys_onay %} checked{% endif %}> {{ t('hesap.iys_onay') }} <span class="etiket-kosul">{{ t('hesap.yalniz_bireysel') }}</span></label>
  </div>

  <button class="dugme" type="submit" data-e2e="kayit-gonder">{{ t('hesap.kayit_ol') }}</button>
  <p>{{ t('hesap.zaten_uye') }} <a href="/{{ dil }}/giris">{{ t('hesap.giris_yap') }}</a></p>
</form>
{% endblock %}
```

- [ ] **Step 6: `app/web/sablonlar/giris.html`**

```html
{% extends "taban.html" %}
{% from "_makrolar.html" import metin_alani with context %}
{% block baslik %}{{ t('hesap.giris_baslik') }}{% endblock %}
{% block icerik %}
<h1>{{ t('hesap.giris_baslik') }}</h1>
{% if hata_anahtar %}<p class="form-hata-ozet" role="alert">{{ t(hata_anahtar) }}</p>{% endif %}
<form class="form" method="post" action="/{{ dil }}/giris">
  <input type="hidden" name="csrf" value="{{ csrf }}">
  <input type="hidden" name="sonraki" value="{{ sonraki }}">
  {{ metin_alani('eposta', t('hesap.eposta'), deger=eposta, tur='email', otomatik='username', zorunlu=true) }}
  {{ metin_alani('parola', t('hesap.parola'), tur='password', otomatik='current-password', zorunlu=true) }}
  <button class="dugme" type="submit">{{ t('hesap.giris_yap') }}</button>
  <p>{{ t('hesap.uye_degil') }} <a href="/{{ dil }}/kayit">{{ t('nav.kayit') }}</a></p>
</form>
{% endblock %}
```

- [ ] **Step 7: `app/web/sablonlar/hesabim.html`**

```html
{% extends "taban.html" %}
{% block baslik %}{{ t('hesap.hesabim_baslik') }}{% endblock %}
{% block icerik %}
<h1>{{ t('hesap.hesabim_baslik') }}</h1>
<p>{{ t('hesap.hos_geldin', ad=musteri.ad) }} · {{ t('hesap.musteri_tipi', tip=t('hesap.tip_' ~ musteri.tip.value)) }}</p>

<section aria-labelledby="b-siparis">
  <h2 id="b-siparis">{{ t('hesap.siparislerim') }}</h2>
  {% if siparisler %}
  <div class="tablo-sar">
    <table class="tablo">
      <thead><tr>
        <th scope="col">{{ t('hesap.sutun_no') }}</th>
        <th scope="col">{{ t('hesap.sutun_tarih') }}</th>
        <th scope="col">{{ t('hesap.sutun_durum') }}</th>
        <th scope="col" class="sayi">{{ t('hesap.sutun_toplam') }}</th>
      </tr></thead>
      <tbody>
      {% for s in siparisler %}
        <tr>
          <td><a href="/{{ dil }}/siparis/{{ s.no }}">{{ s.no }}</a></td>
          <td>{{ tarih(s.olusturma) }}</td>
          <td>{{ t('siparis_durum.' ~ s.durum.value) }}</td>
          <td class="sayi">{{ para(s.toplam, s.para_birimi) }}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <p>{{ t('hesap.siparis_yok') }}</p>
  {% endif %}
</section>

<section aria-labelledby="b-teklif">
  <h2 id="b-teklif">{{ t('hesap.tekliflerim') }}</h2>
  {% if teklifler %}
  <div class="tablo-sar">
    <table class="tablo">
      <thead><tr>
        <th scope="col">{{ t('hesap.sutun_no') }}</th>
        <th scope="col">{{ t('hesap.sutun_tarih') }}</th>
        <th scope="col">{{ t('hesap.sutun_urun') }}</th>
        <th scope="col" class="sayi">{{ t('hesap.sutun_adet') }}</th>
        <th scope="col">{{ t('hesap.sutun_durum') }}</th>
      </tr></thead>
      <tbody>
      {% for tk in teklifler %}
        <tr>
          <td>{{ tk.no }}</td>
          <td>{{ tarih(tk.olusturma) }}</td>
          <td>{% if tk.urun_id %}<a href="/{{ dil }}/urun/{{ tk.urun_id }}">{{ tk.urun_ad }}</a>{% else %}{{ t('hesap.genel_teklif') }}{% endif %}</td>
          <td class="sayi">{{ tk.adet }}</td>
          <td>{{ t('teklif_durum.' ~ tk.durum) }}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <p>{{ t('hesap.teklif_yok') }}</p>
  {% endif %}
</section>
{% endblock %}
```

- [ ] **Step 8: Testlerin geçtiğini gör**

Run: `bash dagitim/test-vm.sh tests/test_web_hesap.py tests/test_web_katalog.py tests/test_web_cekirdek.py -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/web/rotalar/hesap.py app/web/sablonlar/kayit.html app/web/sablonlar/giris.html app/web/sablonlar/hesabim.html app/web/sablonlar/_makrolar.html tests/test_web_hesap.py
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m $'feat(web): kayıt, giriş/çıkış, hesabım ve misafir sepeti birleştirme\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
```

---

## Entegrasyon durumu

- K3: fiyat makrosu `data-e2e="fiyat-ana"` + `data-para` + `data-kdv`; `kdv_dahil` değilken ana TRY değilse ya da kur yoksa "KDV hariç" yazar (DE testi buna göre).
- K6: katalog testleri `urun_ekle(uretici_kodu=...)` ve `indeksi_yeniden_kur` kullanır; yerel FTS yardımcısı yok.
- K7: testler `from tests.conftest import ...`.
- K8: `check_same_thread` adımı ve testi Görev 11'den çıkarıldı (Görev 1).
- K9: `db_bagimliligi` `app/web/bagimlilik.py`'de; `ROTA_SIRASI` birebir; `/{dil:dil}/`; dil öneksiz yolda `"tr"`; `{% block baslik %}`; yönetim şablonları `taban.html`'i genişletir.
- K10: `uretim_uygulamasi` kaldırıldı; fabrika `app/web/asgi.py` (Görev 17).
- K11: 403 metni "Oturum süresi doldu, sayfayı yenileyip tekrar deneyin" (testli).
- K12: kayıt `?tip=`/`?sonraki=`, otomatik giriş, kayıtta sepet birleşmesi (testli); Görev 18 `data-e2e` öznitelikleri (`urun-baglanti`, `fiyat-ana`, `fiyat-ikincil`, `sepete-ekle`, `teklif-iste`, `cikis`, `kayit-gonder`, `gb-tamam`) eklendi.
- K14: `siparis_durum.*`, `teklif_durum.*` Görev 11 JSON'unda; form hata metinleri `hata_kodu.<kod>`.
- K16: geçersiz VKN testi `4728136593`.
- K17: kayıt hata metinleri Görev 7 kodlarına (`zorunlu`, `gecersiz`, `gecersiz_vkn`, `parola_kisa`, `kvkk_onay_yok`, `eposta_kayitli`) eşlendi.
- K18: `/saglik` → `{"durum","son_esitleme","urun"}` (aktif ürün sayısı).

---

### Görev 14: Sepet ve ödeme ekranları

Sepet, ödeme formu (adres, fatura, teslim yöntemi, sözleşme onayları, kur fark onayı), kart formu, sahte 3D Secure ekranı ve sipariş onay sayfası. §11 senaryo 1 (bireysel TR) ve senaryo 2 (kurumsal TR) servis + web seviyesinde uçtan uca test edilir. Entegrasyon kararları (`03-entegrasyon-kararlari.md`) K4, K5, K7, K9, K11, K12, K13, K14, K21 uygulanmıştır.

**Files:**
- Create: `app/web/rotalar/sepet_odeme.py`
- Create: `app/web/sablonlar/sepet.html`, `app/web/sablonlar/odeme.html`, `app/web/sablonlar/kart.html`, `app/web/sablonlar/uc_d.html`, `app/web/sablonlar/siparis.html`, `app/web/sablonlar/_tutar_ozeti.html`
- Modify: `app/web/dil/tr.json`, `app/web/dil/en.json` (anahtar ekleme)
- Modify: `app/web/statik/site.css` (sona ekleme), `app/web/statik/site.js` (sona ekleme)
- Test: `tests/test_web_sepet_odeme.py`

(`app/web/uygulama.py` değişmez: Görev 11'in `ROTA_SIRASI` listesi `sepet_odeme` modülünü zaten yükler — K9.)

**Interfaces:**
- Consumes:
  - `app.sepet.servis`: `sepet_bul(con, oturum_id, musteri_id, simdi) -> int`, `ekle(con, sepet_id, urun_id, adet)`, `adet_ayarla(con, sepet_id, urun_id, adet)`, `kaldir(con, sepet_id, urun_id)`, `kalemler(con, sepet_id) -> tuple[list[Kalem], list[str]]`, `TeklifZorunlu`, `UrunYok`
  - `app.fiyat.kurallar`: `Baglam`, `Kalem`, `KurYok` (K5), `MusteriTipi`, `TeslimYontemi`, `SepetTutari`, `sepet_hesapla(kalemler, b, teslim, kur_eur_try) -> SepetTutari`, `birim_fiyat_gosterimi(net_eur, kdv_orani, b, kur_eur_try) -> FiyatGosterim`, `gosterim_kdv_dahil(b) -> bool`
  - `app.fiyat.kur`: `Kur`, `son_kur(con) -> Kur | None`, `kur_kaydet(con, kur, simdi)` (testte)
  - `app.hesap.servis`: `Musteri`, `Adres`, `adres_kaydet(con, musteri_id, tur, a) -> int`, `adres_son(con, musteri_id, tur) -> Adres | None`; testte `kayit_ol`, `KayitGirdisi`
  - `app.katalog.depo.urun_getir(con, urun_id) -> Urun | None`
  - `app.siparis.servis`: `Siparis`, `SiparisDurumu`, `SepetBos`, `siparis_olustur(con, musteri, sepet_id, teslim, teslimat, fatura, kur, simdi) -> Siparis`, `siparis_no_ile(con, no, simdi) -> Siparis | None`
  - `app.siparis.odeme_sim`: `BASARILI_KART`, `RET_KARTI`, `SMS_KODU`, `OdemeSonucu`, `odeme_baslat(...)`, `sms_dogrula(...)`, `deneme_getir(con, islem_anahtari) -> sqlite3.Row | None` (K13)
  - `app.web.bagimlilik.db_bagimliligi(request)` (K9)
  - `app.web.baglam`: `sablon(request, ad, baglam, durum=200)`, `fiyat_baglami(request, musteri) -> Baglam`; şablon ortak bağlamından `t`, `para(tutar, para_birimi)`, `csrf`, `dil`, `kur`, `kur_metni`, `kur_tarihi`, `kur_bayat`, `musteri` (K9)
  - `app.web.guvenlik`: `aktif_musteri(request, con)`, `csrf_dogrula(request)` (async; hatada 403 + hata sayfası — K11), `oturum_kimligi(request) -> str`
  - Dil dönüştürücüsü `{dil:dil}` (Görev 11, `app.web.dil`)
  - Şablonlar: `taban.html` (`{% block baslik %}`, `{% block icerik %}`), `_makrolar.html` `fiyat(urun, gosterim)`
  - i18n (Görev 11): `siparis_durum.<durum>`, `form_hata.zorunlu` (K14)
  - Testte: `tests.conftest` → `istemci` fixture'ı, `csrf_al(istemci, yol) -> str`, `urun_ekle(con, **)` (K7); `POST /{dil}/giris` (`eposta`, `parola`, `csrf`; 303; misafir sepetini birleştirir — K12); `GET /{dil}/hesabim` sipariş numarasını listeler
- Produces:
  - `app/web/rotalar/sepet_odeme.py`: `router: APIRouter` — `GET /{dil}/sepet`, `POST /{dil}/sepet/ekle|adet|kaldir`, `GET/POST /{dil}/odeme`, `GET/POST /{dil}/odeme/{no}/kart`, `GET/POST /{dil}/odeme/{no}/3d?a=`, `GET /{dil}/siparis/{no}?hata=`
  - Form alan adları (K12): sepet `urun_id`, `adet`, `csrf`; ödeme `teslimat_ad_soyad, teslimat_satir1, teslimat_satir2, teslimat_sehir, teslimat_posta_kodu, teslimat_ulke, teslimat_telefon`, aynıları `fatura_` önekiyle, `fatura_ayni`, `teslim` (`kargo`/`fabrika`/`yurtdisi_dap`), `on_bilgi_onay`, `mesafeli_onay` (yalnız bireysel), `kosullar_onay` (kurumsal/yurt dışı), `gosterilen_toplam`, `gosterilen_kur`, `islem` (`odeme` | `hesapla`); kart `islem_anahtari`, `kart_no` (son kullanma `#kart_skt` ve CVC `#kart_cvc` alanlarının `name`'i yoktur, sunucuya gitmez); 3D `a`, `sms_kodu`
  - `data-e2e` öznitelikleri (Görev 18 tablosu): `sepet-kalemi`, `odemeye-gec`, `teklif-iste` (409 sayfası), `satir-kdv`, `satir-ihracat`, `not-dap` (sepet, ödeme, kart, sipariş), `odeme-gonder`, `kart-gonder`, `sms-gonder`, `odeme-hata` + `data-kod` (`gecersiz_kart`, `ret`, `sms_hatali`), `siparis-durum` + `data-durum`
  - Ret / hatalı SMS sonrası akış (K12): 3D adımı `/{dil}/siparis/{no}?hata=<kod>` adresine döner; sipariş sayfası `[data-e2e="odeme-hata"][data-kod="<kod>"]` ve `/{dil}/odeme/{no}/kart` "Ödemeyi tekrar dene" bağlantısını gösterir.
  - i18n anahtarları: `sepet.*`, `tutar.*`, `odeme.*`, `kart.*`, `uc_d.*`, `siparis.*` ve bu görevin hata kodları `hata_kodu.{kur_yok, ulke_kodu, cok_uzun, teslim_secilmedi, teslim_yurtdisi, teslim_yurtici, onay_yok, gecersiz_kart, ret, sms_hatali}` (K14)
  - Şablon parçası `_tutar_ozeti.html` (değişkenler: `tutar: SepetTutari`, `teslim`)

- [ ] **Step 1: Başarısız testleri yaz**

`tests/test_web_sepet_odeme.py`:

```python
"""Görev 14 — sepet, ödeme, kart, 3D ve sipariş sayfası (TestClient ile)."""
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.db import baglan, gecisleri_uygula
from app.fiyat.kur import Kur, kur_kaydet
from app.fiyat.kurallar import MusteriTipi
from app.hesap.servis import KayitGirdisi, kayit_ol
from app.para import d
from tests.conftest import csrf_al, urun_ekle

PAROLA = "demo-parola-123"
GECERLI_VKN = "1234567890"   # K16


# ---------- yardımcılar ----------

@pytest.fixture
def db(istemci):
    """Uygulamanın kullandığı veritabanına ayrı bir bağlantı (test verisi kurmak ve sonucu okumak için)."""
    con = baglan(istemci.app.state.ayarlar.db_yolu)
    gecisleri_uygula(con)
    yield con
    con.close()


def _kur(db, tarih=date(2026, 10, 12), satis="35.0000"):
    with db:
        kur_kaydet(db, Kur(tarih=tarih, eur_alis=d(satis) - d("0.1000"), eur_satis=d(satis)), datetime.now(UTC))


def _urun(db, **ek):
    with db:
        return urun_ekle(db, **ek)


def _musteri(db, tip=MusteriTipi.BIREYSEL, eposta="bireysel@ornek.test", ulke="TR", **ek):
    with db:
        return kayit_ol(db, KayitGirdisi(tip=tip, ad=f"QATestUser {tip.value}", eposta=eposta, parola=PAROLA,
                                         ulke=ulke, kvkk_onay=True, **ek), datetime.now(UTC))


def _giris(istemci, eposta, dil="tr"):
    csrf = csrf_al(istemci, f"/{dil}/giris")
    r = istemci.post(f"/{dil}/giris", data={"eposta": eposta, "parola": PAROLA, "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 303, r.text


def _sepete_ekle(istemci, urun_id, dil="tr", adet="1"):
    csrf = csrf_al(istemci, f"/{dil}/sepet")
    return istemci.post(f"/{dil}/sepet/ekle", data={"urun_id": str(urun_id), "adet": adet, "csrf": csrf},
                        follow_redirects=False)


def _gizli(html, ad):
    m = re.search(rf'name="{ad}" value="([^"]*)"', html)
    assert m, f"gizli alan yok: {ad}"
    return m.group(1)


def _adres_formu(ulke="TR", teslim="kargo", **ek):
    form = {
        "teslimat_ad_soyad": "QATestUser Alıcı", "teslimat_satir1": "Test Mah. Deneme Sk. No: 1",
        "teslimat_satir2": "", "teslimat_sehir": "Konya" if ulke == "TR" else "Berlin",
        "teslimat_posta_kodu": "42250", "teslimat_ulke": ulke, "teslimat_telefon": "",
        "fatura_ayni": "1", "teslim": teslim,
        "on_bilgi_onay": "1", "mesafeli_onay": "1", "kosullar_onay": "1", "islem": "odeme",
    }
    form.update(ek)
    return form


def _odeme_gonder(istemci, dil="tr", sayfa_html=None, **form_ek):
    if sayfa_html is None:
        sayfa = istemci.get(f"/{dil}/odeme")
        assert sayfa.status_code == 200, sayfa.text
        sayfa_html = sayfa.text
    form = _adres_formu(**form_ek)
    for ad in ("csrf", "gosterilen_toplam", "gosterilen_kur"):
        form[ad] = _gizli(sayfa_html, ad)
    return istemci.post(f"/{dil}/odeme", data=form, follow_redirects=False)


def _siparis_no(konum):
    m = re.search(r"/odeme/(CR-DEMO-\d{8}-\d{4})/kart$", konum)
    assert m, konum
    return m.group(1)


def _kart_ode(istemci, no, kart, dil="tr"):
    sayfa = istemci.get(f"/{dil}/odeme/{no}/kart")
    assert sayfa.status_code == 200, sayfa.text
    form = {"csrf": _gizli(sayfa.text, "csrf"), "islem_anahtari": _gizli(sayfa.text, "islem_anahtari"),
            "kart_no": kart}
    return istemci.post(f"/{dil}/odeme/{no}/kart", data=form, follow_redirects=False), form


def _sms(istemci, no, konum, kod="000000", dil="tr"):
    anahtar = parse_qs(urlparse(konum).query)["a"][0]
    sayfa = istemci.get(konum)
    assert sayfa.status_code == 200, sayfa.text
    return istemci.post(f"/{dil}/odeme/{no}/3d",
                        data={"csrf": _gizli(sayfa.text, "csrf"), "a": anahtar, "sms_kodu": kod},
                        follow_redirects=False), sayfa


def _say(db, sql, *p):
    return db.execute(sql, p).fetchone()[0]


def _db_dokumu(db):
    parcalar = []
    for (tablo,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        for satir in db.execute(f'SELECT * FROM "{tablo}"').fetchall():
            parcalar.append("|".join(str(x) for x in satir))
    return "\n".join(parcalar)


def _siparis_hazirla(istemci, db, eposta="bireysel@ornek.test"):
    """Giriş yapmış bireysel müşteri + 100 € ürün + kur 35 -> odeme_bekliyor sipariş no'su."""
    _kur(db)
    uid = _urun(db, sku="S-HAZIR", ad="Hazır Ürün", fiyat="100.00")
    _musteri(db, eposta=eposta)
    _giris(istemci, eposta)
    assert _sepete_ekle(istemci, uid).status_code == 303
    r = _odeme_gonder(istemci)
    assert r.status_code == 303, r.text
    return _siparis_no(r.headers["location"])


# ---------- §11 senaryo 1: bireysel TR ----------

def test_senaryo1_bireysel_tr_siparis(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-ROLE", ad="Test Röle", fiyat="100.00")

    # misafir sepete ekler; fiyat TRY ve KDV dahil (100 € × 35 = 3.500 ₺ + %20 KDV = 4.200 ₺)
    assert _sepete_ekle(istemci, uid).status_code == 303
    sepet = istemci.get("/tr/sepet")
    assert sepet.status_code == 200
    assert "Test Röle" in sepet.text
    assert "4.200,00 ₺" in sepet.text
    assert "KDV dahil" in sepet.text
    assert 'data-e2e="sepet-kalemi"' in sepet.text and 'data-e2e="odemeye-gec"' in sepet.text

    # misafir ödemeye geçemez
    r = istemci.get("/tr/odeme", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/tr/giris?sonraki=/tr/odeme"

    # kayıtlı müşteri girer, misafir sepeti üye sepetine geçer
    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    odeme = istemci.get("/tr/odeme")
    assert odeme.status_code == 200
    assert "Test Röle" in odeme.text
    # 3.500 + 700 KDV + 525 kargo + 105 kargo KDV = 4.830 ₺
    assert "4.830,00 ₺" in odeme.text
    assert "/tr/yasal/on-bilgilendirme" in odeme.text
    assert "/tr/yasal/mesafeli-satis" in odeme.text
    assert 'name="on_bilgi_onay"' in odeme.text and 'name="mesafeli_onay"' in odeme.text
    assert 'data-e2e="odeme-gonder"' in odeme.text and 'data-e2e="satir-kdv"' in odeme.text
    assert re.search(r'<input[^>]*name="fatura_ayni"[^>]*checked', odeme.text)

    r = _odeme_gonder(istemci, sayfa_html=odeme.text)
    assert r.status_code == 303, r.text
    no = _siparis_no(r.headers["location"])

    r, _ = _kart_ode(istemci, no, "4111 1111 1111 1111")
    assert r.status_code == 303
    assert r.headers["location"].startswith(f"/tr/odeme/{no}/3d?a=")

    r, uc_d = _sms(istemci, no, r.headers["location"])
    assert 'data-e2e="sms-gonder"' in uc_d.text
    assert r.status_code == 303
    assert r.headers["location"] == f"/tr/siparis/{no}"

    onay = istemci.get(f"/tr/siparis/{no}")
    assert onay.status_code == 200
    assert re.search(r'data-e2e="siparis-durum"[^>]*data-durum="odendi"', onay.text)
    assert "4.830,00 ₺" in onay.text
    assert "**** 1111" in onay.text
    assert 'data-e2e="odeme-hata"' not in onay.text

    satir = db.execute("SELECT * FROM siparis WHERE no = ?", (no,)).fetchone()
    assert satir["durum"] == "odendi"
    assert satir["para_birimi"] == "TRY"
    assert Decimal(satir["toplam"]) == Decimal("4830.00")
    assert Decimal(satir["kdv"]) == Decimal("805.00")
    assert satir["kart_son4"] == "1111"
    assert satir["ihracat_istisnasi"] == 0

    assert no in istemci.get("/tr/hesabim").text
    assert "Sepetiniz boş" in istemci.get("/tr/sepet").text


def test_bireysel_sozlesme_onayi_zorunlu(istemci, db):
    _kur(db)
    uid = _urun(db, fiyat="100.00")
    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    _sepete_ekle(istemci, uid)
    r = _odeme_gonder(istemci, mesafeli_onay="")
    assert r.status_code == 400
    assert 'id="hata-mesafeli_onay"' in r.text
    assert _say(db, "SELECT COUNT(*) FROM siparis") == 0


# ---------- §11 senaryo 2: kurumsal TR ----------

def test_senaryo2_kurumsal_ret_sonra_basarili(istemci, db):
    _kur(db)
    uid = _urun(db, sku="S-KONT", ad="Test Kontaktör", fiyat="100.00")
    m = _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="kurumsal@ornek.test",
                 vergi_kimlik_no=GECERLI_VKN, vergi_dairesi="Selçuk")
    _giris(istemci, "kurumsal@ornek.test")
    assert _sepete_ekle(istemci, uid).status_code == 303

    sepet = istemci.get("/tr/sepet")
    assert "100,00 €" in sepet.text          # EUR, KDV hariç birim fiyat
    assert "3.500,00 ₺" in sepet.text        # TRY karşılığı (net)
    assert "KDV hariç" in sepet.text

    odeme = istemci.get("/tr/odeme")
    assert 'name="kosullar_onay"' in odeme.text
    assert 'name="mesafeli_onay"' not in odeme.text
    r = _odeme_gonder(istemci, sayfa_html=odeme.text, on_bilgi_onay="", mesafeli_onay="")
    assert r.status_code == 303, r.text
    no = _siparis_no(r.headers["location"])

    # ret kartı: banka reddi -> sipariş sayfası, odeme-hata[data-kod=ret] + tekrar dene bağlantısı
    r, _ = _kart_ode(istemci, no, "4000000000000002")
    assert r.status_code == 303
    r, _ = _sms(istemci, no, r.headers["location"])
    assert r.status_code == 303
    assert r.headers["location"] == f"/tr/siparis/{no}?hata=ret"
    hata = istemci.get(r.headers["location"])
    assert re.search(r'data-e2e="odeme-hata"[^>]*data-kod="ret"', hata.text)
    assert "reddedildi" in hata.text
    assert f'href="/tr/odeme/{no}/kart"' in hata.text
    assert db.execute("SELECT durum FROM siparis WHERE no = ?", (no,)).fetchone()[0] == "odeme_bekliyor"

    # aynı siparişle başarılı kart
    r, _ = _kart_ode(istemci, no, "4111111111111111")
    r, _ = _sms(istemci, no, r.headers["location"])
    assert r.headers["location"] == f"/tr/siparis/{no}"

    satir = db.execute("SELECT * FROM siparis WHERE no = ?", (no,)).fetchone()
    assert satir["durum"] == "odendi"
    assert satir["musteri_id"] == m.id
    assert satir["para_birimi"] == "TRY"
    assert Decimal(satir["toplam"]) == Decimal("4830.00")
    assert _say(db, "SELECT COUNT(*) FROM siparis") == 1
    assert _say(db, "SELECT COUNT(*) FROM odeme_denemesi WHERE siparis_id = ?", satir["id"]) == 2


# ---------- yurt dışı teslim ----------

def test_yurtdisi_musteri_dap_ve_ihracat_istisnasi(istemci, db):
    uid = _urun(db, sku="S-EXP", ad="Export Item", fiyat="100.00")
    _musteri(db, tip=MusteriTipi.YURTDISI, eposta="export@ornek.test", ulke="DE")
    _giris(istemci, "export@ornek.test", dil="en")
    assert _sepete_ekle(istemci, uid, dil="en").status_code == 303

    odeme = istemci.get("/en/odeme")
    assert odeme.status_code == 200
    assert "Export – VAT exemption" in odeme.text
    assert 'data-e2e="satir-ihracat"' in odeme.text and 'data-e2e="not-dap"' in odeme.text
    assert "borne by the buyer" in odeme.text
    assert 'value="yurtdisi_dap"' in odeme.text and 'value="fabrika"' in odeme.text   # K4
    assert 'value="kargo"' not in odeme.text

    r = _odeme_gonder(istemci, dil="en", sayfa_html=odeme.text, ulke="DE", teslim="yurtdisi_dap",
                      on_bilgi_onay="", mesafeli_onay="")
    assert r.status_code == 303, r.text
    satir = db.execute("SELECT * FROM siparis").fetchone()
    assert satir["para_birimi"] == "EUR"
    assert satir["ihracat_istisnasi"] == 1
    assert Decimal(satir["kdv"]) == Decimal("0")
    assert Decimal(satir["kargo"]) == Decimal("0")
    assert Decimal(satir["toplam"]) == Decimal("100.00")
    assert satir["teslim_yontemi"] == "yurtdisi_dap"


def test_tr_disi_teslimatta_kargo_secilemez(istemci, db):
    _kur(db)
    uid = _urun(db, fiyat="100.00")
    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    _sepete_ekle(istemci, uid)

    r = _odeme_gonder(istemci, ulke="DE", teslim="kargo")
    assert r.status_code == 400
    assert 'id="hata-teslim"' in r.text
    assert 'value="kargo"' not in r.text
    assert 'value="yurtdisi_dap"' in r.text and 'value="fabrika"' in r.text
    assert _say(db, "SELECT COUNT(*) FROM siparis") == 0

    # bireysel müşteri, yurt dışı teslim: TRY, KDV yerine ihracat istisnası satırı ve DAP notu
    hesap = _odeme_gonder(istemci, ulke="DE", teslim="yurtdisi_dap", islem="hesapla")
    assert hesap.status_code == 200
    assert "İhracat – KDV istisnası" in hesap.text
    assert "alıcıya aittir" in hesap.text
    assert "3.500,00 ₺" in hesap.text
    r = _odeme_gonder(istemci, sayfa_html=hesap.text, ulke="DE", teslim="yurtdisi_dap")
    assert r.status_code == 303, r.text
    satir = db.execute("SELECT * FROM siparis").fetchone()
    assert satir["para_birimi"] == "TRY"
    assert satir["ihracat_istisnasi"] == 1
    assert Decimal(satir["toplam"]) == Decimal("3500.00")


# ---------- sepet ----------

def test_teklif_zorunlu_urun_409(istemci, db):
    uid = _urun(db, sku="8301033800019", ad="KUKA KRC5 KR 140 R3200-2 PA", kok="Endüstriyel Robotlar",
                fiyat="20000.00", teklif=True)
    r = _sepete_ekle(istemci, uid)
    assert r.status_code == 409
    assert re.search(rf'href="/tr/teklif\?urun_id={uid}"[^>]*data-e2e="teklif-iste"', r.text)
    assert _say(db, "SELECT COUNT(*) FROM sepet_kalemi") == 0


def test_olmayan_urun_404_bozuk_adet_400(istemci, db):
    assert _sepete_ekle(istemci, 999999).status_code == 404
    uid = _urun(db, fiyat="10.00")
    assert _sepete_ekle(istemci, uid, adet="abc").status_code == 400
    assert _sepete_ekle(istemci, uid, adet="1000").status_code == 303
    assert _say(db, "SELECT adet FROM sepet_kalemi WHERE urun_id = ?", uid) == 99


def test_adet_guncelle_ve_kaldir(istemci, db):
    _kur(db)
    uid = _urun(db, fiyat="10.00")
    _sepete_ekle(istemci, uid)
    csrf = csrf_al(istemci, "/tr/sepet")
    r = istemci.post("/tr/sepet/adet", data={"urun_id": str(uid), "adet": "3", "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 303
    assert _say(db, "SELECT adet FROM sepet_kalemi WHERE urun_id = ?", uid) == 3
    r = istemci.post("/tr/sepet/kaldir", data={"urun_id": str(uid), "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303
    assert _say(db, "SELECT COUNT(*) FROM sepet_kalemi") == 0


def test_urunlu_sepet_sayfasi_render(istemci, db):
    # _makrolar.html'deki fiyat makrosu bağlamdaki t/para/kur'a ihtiyaç duyar ("with context" olmadan UndefinedError)
    _kur(db)
    uid = _urun(db, fiyat="10.00")
    _sepete_ekle(istemci, uid)
    r = istemci.get("/tr/sepet")
    assert r.status_code == 200
    assert 'data-e2e="sepet-kalemi"' in r.text


def test_sepet_csrf_yoksa_403(istemci, db):
    uid = _urun(db, fiyat="10.00")
    istemci.get("/tr/sepet")
    r = istemci.post("/tr/sepet/ekle", data={"urun_id": str(uid), "adet": "1"}, follow_redirects=False)
    assert r.status_code == 403
    assert _say(db, "SELECT COUNT(*) FROM sepet_kalemi") == 0


# ---------- ödeme ----------

def test_girissiz_odeme_yonlendirir(istemci):
    r = istemci.get("/tr/odeme", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/tr/giris?sonraki=/tr/odeme"
    r = istemci.get("/en/odeme", follow_redirects=False)
    assert r.headers["location"] == "/en/giris?sonraki=/en/odeme"


def test_odemede_dusen_urun_bildirilir(istemci, db):
    _kur(db)
    kalan = _urun(db, sku="S-KALAN", ad="Kalan Ürün", fiyat="10.00")
    dusen = _urun(db, sku="S-DUSEN", ad="Pasifleşen Ürün", fiyat="10.00")
    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    _sepete_ekle(istemci, kalan)
    _sepete_ekle(istemci, dusen)
    sayfa = istemci.get("/tr/odeme")                       # kullanıcı formu açtı
    with db:
        db.execute("UPDATE urun SET aktif = 0 WHERE id = ?", (dusen,))

    # K21: POST'ta siparis_olustur'dan önce kalemler() çağrılır, düşen ürün adıyla bildirilir
    r = _odeme_gonder(istemci, sayfa_html=sayfa.text)
    assert r.status_code == 409
    assert "sepetinizden çıkarıldı" in r.text and "Pasifleşen Ürün" in r.text
    assert _say(db, "SELECT COUNT(*) FROM siparis") == 0
    assert _say(db, "SELECT COUNT(*) FROM sepet_kalemi WHERE urun_id = ?", dusen) == 0

    r = _odeme_gonder(istemci, sayfa_html=r.text)          # yeni tutarla onay
    assert r.status_code == 303, r.text


def test_kur_yoksa_anlasilir_hata(istemci, db):
    uid = _urun(db, fiyat="100.00")
    _sepete_ekle(istemci, uid)
    sepet = istemci.get("/tr/sepet")
    assert sepet.status_code == 200
    assert "kuru alınamadığı" in sepet.text

    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    odeme = istemci.get("/tr/odeme")
    assert odeme.status_code == 200
    assert "kuru alınamadığı" in odeme.text
    r = _odeme_gonder(istemci, sayfa_html=odeme.text)
    assert r.status_code == 503
    assert _say(db, "SELECT COUNT(*) FROM siparis") == 0


def test_kur_degisince_fark_onayi(istemci, db):
    _kur(db, satis="35.0000")
    uid = _urun(db, fiyat="100.00")
    _musteri(db)
    _giris(istemci, "bireysel@ornek.test")
    _sepete_ekle(istemci, uid)
    eski = istemci.get("/tr/odeme")
    assert _gizli(eski.text, "gosterilen_toplam") == "4830.00"
    assert _gizli(eski.text, "gosterilen_kur") == "35.0000"

    _kur(db, tarih=date(2026, 10, 13), satis="36.0000")      # kullanıcı formdayken kur değişti
    r = _odeme_gonder(istemci, sayfa_html=eski.text)
    assert r.status_code == 409
    assert "Tutar güncellendi" in r.text
    assert "4.968,00 ₺" in r.text                              # 3.600 + 720 + 540 + 108
    assert _gizli(r.text, "gosterilen_toplam") == "4968.00"
    assert _say(db, "SELECT COUNT(*) FROM siparis") == 0

    r = _odeme_gonder(istemci, sayfa_html=r.text)               # yeni tutar onaylandı
    assert r.status_code == 303
    assert Decimal(db.execute("SELECT toplam FROM siparis").fetchone()[0]) == Decimal("4968.00")


# ---------- kart, 3D, güvenlik ----------

def test_kart_formu_skt_cvc_gonderilmez(istemci, db):
    no = _siparis_hazirla(istemci, db)
    sayfa = istemci.get(f"/tr/odeme/{no}/kart")
    assert sayfa.status_code == 200
    assert "DEMO: yalnız test kartları" in sayfa.text
    assert "4111 1111 1111 1111" in sayfa.text and "4000 0000 0000 0002" in sayfa.text
    for kimlik in ("kart_skt", "kart_cvc"):
        etiket = re.search(rf'<input[^>]*id="{kimlik}"[^>]*>', sayfa.text).group(0)
        assert "name=" not in etiket
    assert re.search(r'<input[^>]*name="kart_no"', sayfa.text)
    assert 'data-e2e="kart-gonder"' in sayfa.text and 'data-e2e="satir-kdv"' in sayfa.text
    assert len(_gizli(sayfa.text, "islem_anahtari")) >= 16


def test_cift_post_ayni_anahtar_tek_sonuc(istemci, db):
    no = _siparis_hazirla(istemci, db)
    r1, form = _kart_ode(istemci, no, "4111111111111111")
    r2 = istemci.post(f"/tr/odeme/{no}/kart", data=form, follow_redirects=False)
    assert r1.status_code == r2.status_code == 303
    assert r1.headers["location"] == r2.headers["location"]
    assert _say(db, "SELECT COUNT(*) FROM odeme_denemesi") == 1


def test_baska_musterinin_siparisi_404(istemci, db):
    no = _siparis_hazirla(istemci, db, eposta="a@ornek.test")
    _musteri(db, eposta="b@ornek.test")
    with TestClient(istemci.app) as baska:
        _giris(baska, "b@ornek.test")
        assert baska.get(f"/tr/siparis/{no}").status_code == 404
        assert baska.get(f"/tr/odeme/{no}/kart").status_code == 404
        assert baska.get(f"/tr/odeme/{no}/3d?a=xxxxxxxxxxxxxxxxxxxx").status_code == 404
    with TestClient(istemci.app) as misafir:
        r = misafir.get(f"/tr/siparis/{no}", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"].startswith("/tr/giris?sonraki=")


def test_gecersiz_kart_mesaji_ve_numara_saklanmaz(istemci, db):
    no = _siparis_hazirla(istemci, db)
    r, _ = _kart_ode(istemci, no, "5555 4444 3333 1111")
    assert r.status_code == 400
    assert re.search(r'data-e2e="odeme-hata"[^>]*data-kod="gecersiz_kart"', r.text)
    assert "Demo: yalnız test kartları kabul edilir" in r.text
    assert "5555444433331111" not in r.text and "5555 4444 3333 1111" not in r.text
    assert db.execute("SELECT durum FROM odeme_denemesi").fetchone()[0] == "gecersiz_kart"
    assert "5555444433331111" not in _db_dokumu(db)
    assert db.execute("SELECT durum FROM siparis WHERE no = ?", (no,)).fetchone()[0] == "odeme_bekliyor"


def test_tam_kart_numarasi_yanitta_ve_dbde_yok(istemci, db):
    no = _siparis_hazirla(istemci, db)
    r, _ = _kart_ode(istemci, no, "4111111111111111")
    r, uc_d = _sms(istemci, no, r.headers["location"])
    onay = istemci.get(r.headers["location"])
    for html in (uc_d.text, onay.text):
        assert "4111111111111111" not in html
        assert "4111 1111 1111 1111" not in html
    assert "1111" in uc_d.text
    assert "4111111111111111" not in _db_dokumu(db)


def test_hatali_sms_siparis_sayfasina_doner(istemci, db):
    no = _siparis_hazirla(istemci, db)
    r, _ = _kart_ode(istemci, no, "4111111111111111")
    r, _ = _sms(istemci, no, r.headers["location"], kod="123456")
    assert r.headers["location"] == f"/tr/siparis/{no}?hata=sms_hatali"
    sayfa = istemci.get(r.headers["location"])
    assert re.search(r'data-e2e="odeme-hata"[^>]*data-kod="sms_hatali"', sayfa.text)
    assert "SMS kodu hatalı" in sayfa.text
    assert db.execute("SELECT durum FROM siparis WHERE no = ?", (no,)).fetchone()[0] == "odeme_bekliyor"
```

- [ ] **Step 2: Testleri çalıştır, başarısız olduklarını gör**

Run: `bash dagitim/test-vm.sh tests/test_web_sepet_odeme.py -q`
Expected: FAIL — `/tr/sepet` ve diğer rotalar 404 döner (ör. `assert 404 == 303`); `app/web/rotalar/sepet_odeme.py` henüz yok.

- [ ] **Step 3: i18n anahtarlarını iki dile birlikte ekle**

`app/web/dil/tr.json` nesnesine (mevcut anahtarlara dokunmadan, düz `"bolum.anahtar"` biçiminde) ekle. `siparis_durum.*` ve `form_hata.zorunlu` Görev 11'indir, burada tanımlanmaz (K14):

```json
  "sepet.baslik": "Sepetim",
  "sepet.urun": "Ürün",
  "sepet.birim_fiyat": "Birim fiyat",
  "sepet.adet": "Adet",
  "sepet.tutar_kdv_dahil": "Tutar (KDV dahil)",
  "sepet.tutar_kdv_haric": "Tutar (KDV hariç)",
  "sepet.guncelle": "Güncelle",
  "sepet.kaldir": "Kaldır",
  "sepet.bos": "Sepetiniz boş.",
  "sepet.alisverise_don": "Alışverişe dön",
  "sepet.odemeye_gec": "Ödemeye geç",
  "sepet.eklendi": "Ürün sepete eklendi.",
  "sepet.teklif_zorunlu": "Bu ürün sepete eklenemez: robotlar, pozisyonerler ve 15.000 € (KDV hariç) üzerindeki ürünler teklifle satılır.",
  "sepet.teklif_iste": "Bu ürün için teklif iste",
  "sepet.dusen_urunler": "Şu ürünler artık satışta olmadığı ya da teklif gerektirdiği için sepetinizden çıkarıldı: {adlar}",
  "sepet.tedarik_teyit": "Tedarik süresi sipariş sonrası teyit edilecek.",
  "sepet.kargo_notu": "Teslim yöntemi ve kargo tutarı ödeme adımında, teslimat ülkesine göre kesinleşir.",
  "tutar.ara_toplam": "Ara toplam",
  "tutar.kargo": "Kargo",
  "tutar.kdv": "KDV",
  "tutar.ihracat_istisnasi": "İhracat – KDV istisnası",
  "tutar.toplam": "Genel toplam",
  "tutar.dap_notu": "Teslim DAP (Incoterms 2020): gümrük vergileri, ithalat vergileri ve masrafları alıcıya aittir.",
  "tutar.navlun_notu": "Navlun ayrıca teklif edilecektir.",
  "tutar.kur": "Kur: 1 € = {kur} ₺ (TCMB döviz satış, {tarih})",
  "odeme.baslik": "Ödeme",
  "odeme.gercek_veri_uyari": "Demo ortamı: gerçek ad, adres ve telefon bilgisi girmeyin.",
  "odeme.teslimat_adresi": "Teslimat adresi",
  "odeme.fatura_adresi": "Fatura adresi",
  "odeme.fatura_ayni": "Fatura adresim teslimat adresiyle aynı",
  "odeme.ad_soyad": "Ad soyad / unvan",
  "odeme.adres_satir1": "Adres",
  "odeme.adres_satir2": "Adres (devam)",
  "odeme.sehir": "Şehir",
  "odeme.posta_kodu": "Posta kodu",
  "odeme.ulke": "Ülke kodu (ör. TR, DE)",
  "odeme.telefon": "Telefon",
  "odeme.teslim_yontemi": "Teslim yöntemi",
  "odeme.teslim.kargo": "Kargo (Türkiye içi)",
  "odeme.teslim.fabrika": "Fabrikadan teslim (Konya)",
  "odeme.teslim.yurtdisi_dap": "Yurt dışı teslim – DAP",
  "odeme.teslim_ulke_notu": "Türkiye dışındaki adreslere DAP teslim yapılır ya da ürün fabrikadan teslim alınır. Ülkeyi değiştirdiyseniz \"Tutarı yeniden hesapla\" düğmesine basın.",
  "odeme.ozet": "Sipariş özeti",
  "odeme.onaylar": "Onaylar",
  "odeme.onay_on_bilgi": "Ön Bilgilendirme Formu'nu okudum, onaylıyorum.",
  "odeme.onay_mesafeli": "Mesafeli Satış Sözleşmesi'ni okudum, onaylıyorum.",
  "odeme.onay_kosullar": "Kurumsal satış koşullarını, iade ve garanti koşullarını okudum, kabul ediyorum.",
  "odeme.belge.on_bilgilendirme": "Ön Bilgilendirme Formu",
  "odeme.belge.mesafeli_satis": "Mesafeli Satış Sözleşmesi",
  "odeme.belge.kullanim": "Kullanım ve satış koşulları",
  "odeme.belge.iade": "İade ve cayma",
  "odeme.belge.garanti": "Garanti koşulları",
  "odeme.yeniden_hesapla": "Tutarı yeniden hesapla",
  "odeme.odemeye_gec": "Siparişi oluştur ve karta geç",
  "odeme.sepete_don": "Sepete dön",
  "odeme.tutar_guncellendi": "Tutar güncellendi: döviz kuru, teslimat bilgisi ya da sepet değiştiği için toplam yeniden hesaplandı. Yeni tutarı kontrol edip onaylayın.",
  "kart.baslik": "Kartla ödeme",
  "kart.demo_uyari": "DEMO: yalnız test kartları kabul edilir. Gerçek kart bilgisi girmeyin.",
  "kart.siparis": "Sipariş {no}",
  "kart.kart_no": "Kart numarası",
  "kart.son_kullanma": "Son kullanma tarihi",
  "kart.skt_ornek": "AA/YY",
  "kart.cvc": "Güvenlik kodu (CVC)",
  "kart.skt_cvc_notu": "Son kullanma tarihi ve güvenlik kodu sunucuya gönderilmez.",
  "kart.ode": "Öde",
  "kart.sure_notu": "Ödenmeyen siparişler 30 dakika sonra iptal edilir; sepetiniz korunur.",
  "kart.test_kartlari": "Test kartları",
  "kart.test_basarili": "başarılı ödeme",
  "kart.test_ret": "banka reddi",
  "kart.test_sms": "3D Secure SMS kodu: {kod}",
  "uc_d.baslik": "3D Secure doğrulama",
  "uc_d.demo_uyari": "DEMO BANKASI – bu ekran gerçek bir banka sayfası değildir.",
  "uc_d.aciklama": "Sonu {son4} ile biten kartınızdan {tutar} tutarındaki ödemeyi onaylamak için telefonunuza gönderilen kodu girin.",
  "uc_d.sms_kodu": "SMS kodu",
  "uc_d.ipucu": "Demo kodu: {kod}",
  "uc_d.onayla": "Onayla",
  "siparis.baslik": "Sipariş {no}",
  "siparis.tesekkur": "Teşekkürler, ödemeniz alındı.",
  "siparis.durum_etiket": "Durum",
  "siparis.iptal_notu": "Bu sipariş 30 dakika içinde ödenmediği için iptal edildi; sepetiniz korunuyor.",
  "siparis.odemeye_don": "Ödemeyi tamamla",
  "siparis.tekrar_dene": "Ödemeyi tekrar dene",
  "siparis.kart": "Kart: **** {son4}",
  "siparis.sku": "SKU",
  "siparis.net": "Net",
  "siparis.kdv": "KDV",
  "siparis.brut": "Tutar",
  "siparis.kur": "Siparişte sabitlenen kur: 1 € = {kur} ₺ ({tarih})",
  "siparis.teslim_yontemi": "Teslim yöntemi",
  "siparis.teslimat": "Teslimat adresi",
  "siparis.fatura": "Fatura adresi",
  "siparis.hesabim": "Hesabım'a git",
  "hata_kodu.kur_yok": "Güncel döviz kuru alınamadığı için TL tutar şu an hesaplanamıyor. Lütfen biraz sonra yeniden deneyin.",
  "hata_kodu.ulke_kodu": "İki harfli ülke kodu girin (ör. TR).",
  "hata_kodu.cok_uzun": "Girilen metin çok uzun.",
  "hata_kodu.teslim_secilmedi": "Bir teslim yöntemi seçin.",
  "hata_kodu.teslim_yurtdisi": "Türkiye dışındaki adreslere kargo seçilemez; \"Yurt dışı teslim – DAP\" ya da \"Fabrikadan teslim\" seçin.",
  "hata_kodu.teslim_yurtici": "Türkiye içindeki adresler için kargo ya da fabrikadan teslim seçin.",
  "hata_kodu.onay_yok": "Devam etmek için bu metni onaylamanız gerekir.",
  "hata_kodu.gecersiz_kart": "Demo: yalnız test kartları kabul edilir. Girdiğiniz kart işlenmedi ve saklanmadı.",
  "hata_kodu.ret": "Ödeme banka tarafından reddedildi. Siparişiniz korunuyor; başka bir kartla yeniden deneyebilirsiniz.",
  "hata_kodu.sms_hatali": "SMS kodu hatalı olduğu için doğrulama başarısız oldu. Ödemeyi yeniden başlatabilirsiniz."
```

`app/web/dil/en.json` nesnesine aynı anahtarları ekle:

```json
  "sepet.baslik": "Your cart",
  "sepet.urun": "Product",
  "sepet.birim_fiyat": "Unit price",
  "sepet.adet": "Quantity",
  "sepet.tutar_kdv_dahil": "Amount (VAT incl.)",
  "sepet.tutar_kdv_haric": "Amount (excl. VAT)",
  "sepet.guncelle": "Update",
  "sepet.kaldir": "Remove",
  "sepet.bos": "Your cart is empty.",
  "sepet.alisverise_don": "Continue shopping",
  "sepet.odemeye_gec": "Proceed to checkout",
  "sepet.eklendi": "Item added to your cart.",
  "sepet.teklif_zorunlu": "This item cannot be added to the cart: robots, positioners and items above €15,000 (excl. VAT) are sold on quotation.",
  "sepet.teklif_iste": "Request a quote for this item",
  "sepet.dusen_urunler": "The following items were removed from your cart because they are no longer available or now require a quote: {adlar}",
  "sepet.tedarik_teyit": "Lead time will be confirmed after the order.",
  "sepet.kargo_notu": "Delivery method and shipping cost are finalised at checkout, based on the delivery country.",
  "tutar.ara_toplam": "Subtotal",
  "tutar.kargo": "Shipping",
  "tutar.kdv": "VAT",
  "tutar.ihracat_istisnasi": "Export – VAT exemption",
  "tutar.toplam": "Total",
  "tutar.dap_notu": "Delivery DAP (Incoterms 2020): customs duties, import taxes and charges are borne by the buyer.",
  "tutar.navlun_notu": "Freight will be quoted separately.",
  "tutar.kur": "Exchange rate: €1 = ₺{kur} (CBRT selling rate, {tarih})",
  "odeme.baslik": "Checkout",
  "odeme.gercek_veri_uyari": "Demo environment: do not enter real names, addresses or phone numbers.",
  "odeme.teslimat_adresi": "Delivery address",
  "odeme.fatura_adresi": "Billing address",
  "odeme.fatura_ayni": "My billing address is the same as the delivery address",
  "odeme.ad_soyad": "Full name / company",
  "odeme.adres_satir1": "Address",
  "odeme.adres_satir2": "Address line 2",
  "odeme.sehir": "City",
  "odeme.posta_kodu": "Postcode",
  "odeme.ulke": "Country code (e.g. TR, DE)",
  "odeme.telefon": "Phone",
  "odeme.teslim_yontemi": "Delivery method",
  "odeme.teslim.kargo": "Courier (within Türkiye)",
  "odeme.teslim.fabrika": "Collection from our plant (Konya)",
  "odeme.teslim.yurtdisi_dap": "International delivery – DAP",
  "odeme.teslim_ulke_notu": "Addresses outside Türkiye are delivered DAP or collected from our plant. If you changed the country, press \"Recalculate\".",
  "odeme.ozet": "Order summary",
  "odeme.onaylar": "Agreements",
  "odeme.onay_on_bilgi": "I have read and accept the Pre-Contractual Information Form.",
  "odeme.onay_mesafeli": "I have read and accept the Distance Sales Agreement.",
  "odeme.onay_kosullar": "I have read and accept the business terms of sale, the returns policy and the warranty terms.",
  "odeme.belge.on_bilgilendirme": "Pre-Contractual Information Form",
  "odeme.belge.mesafeli_satis": "Distance Sales Agreement",
  "odeme.belge.kullanim": "Terms of use and sale",
  "odeme.belge.iade": "Returns and withdrawal",
  "odeme.belge.garanti": "Warranty terms",
  "odeme.yeniden_hesapla": "Recalculate",
  "odeme.odemeye_gec": "Place order and continue to card payment",
  "odeme.sepete_don": "Back to cart",
  "odeme.tutar_guncellendi": "Amount updated: the total was recalculated because the exchange rate, delivery details or cart changed. Please check and confirm the new amount.",
  "kart.baslik": "Card payment",
  "kart.demo_uyari": "DEMO: only test cards are accepted. Do not enter real card details.",
  "kart.siparis": "Order {no}",
  "kart.kart_no": "Card number",
  "kart.son_kullanma": "Expiry date",
  "kart.skt_ornek": "MM/YY",
  "kart.cvc": "Security code (CVC)",
  "kart.skt_cvc_notu": "The expiry date and security code are never sent to the server.",
  "kart.ode": "Pay",
  "kart.sure_notu": "Unpaid orders are cancelled after 30 minutes; your cart is kept.",
  "kart.test_kartlari": "Test cards",
  "kart.test_basarili": "successful payment",
  "kart.test_ret": "declined by bank",
  "kart.test_sms": "3D Secure SMS code: {kod}",
  "uc_d.baslik": "3D Secure verification",
  "uc_d.demo_uyari": "DEMO BANK – this is not a real bank page.",
  "uc_d.aciklama": "Enter the code sent to your phone to approve the payment of {tutar} from your card ending in {son4}.",
  "uc_d.sms_kodu": "SMS code",
  "uc_d.ipucu": "Demo code: {kod}",
  "uc_d.onayla": "Confirm",
  "siparis.baslik": "Order {no}",
  "siparis.tesekkur": "Thank you, your payment has been received.",
  "siparis.durum_etiket": "Status",
  "siparis.iptal_notu": "This order was cancelled because it was not paid within 30 minutes; your cart is kept.",
  "siparis.odemeye_don": "Complete payment",
  "siparis.tekrar_dene": "Try the payment again",
  "siparis.kart": "Card: **** {son4}",
  "siparis.sku": "SKU",
  "siparis.net": "Net",
  "siparis.kdv": "VAT",
  "siparis.brut": "Amount",
  "siparis.kur": "Exchange rate fixed for this order: €1 = ₺{kur} ({tarih})",
  "siparis.teslim_yontemi": "Delivery method",
  "siparis.teslimat": "Delivery address",
  "siparis.fatura": "Billing address",
  "siparis.hesabim": "Go to My account",
  "hata_kodu.kur_yok": "The TRY amount cannot be calculated because the current exchange rate is unavailable. Please try again shortly.",
  "hata_kodu.ulke_kodu": "Enter a two-letter country code (e.g. TR).",
  "hata_kodu.cok_uzun": "The text is too long.",
  "hata_kodu.teslim_secilmedi": "Choose a delivery method.",
  "hata_kodu.teslim_yurtdisi": "Courier delivery is not available outside Türkiye; choose \"International delivery – DAP\" or \"Collection from our plant\".",
  "hata_kodu.teslim_yurtici": "For addresses in Türkiye choose courier or collection from our plant.",
  "hata_kodu.onay_yok": "You must accept this text to continue.",
  "hata_kodu.gecersiz_kart": "Demo: only test cards are accepted. The card you entered was not processed or stored.",
  "hata_kodu.ret": "The payment was declined by the bank. Your order is kept; you can try again with another card.",
  "hata_kodu.sms_hatali": "Verification failed because the SMS code was wrong. You can start the payment again."
```

JSON geçerliliğini kontrol et: `python -m json.tool app/web/dil/tr.json > /dev/null && python -m json.tool app/web/dil/en.json > /dev/null` — çıktı yok, çıkış kodu 0.

- [ ] **Step 4: Rota modülünü yaz**

`app/web/rotalar/sepet_odeme.py`:

```python
"""Sepet, ödeme, kart, sahte 3D Secure ve sipariş onayı rotaları (Görev 14)."""
from __future__ import annotations

import re
import secrets
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Mapping
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.fiyat.kur import Kur, son_kur
from app.fiyat.kurallar import (Baglam, Kalem, KurYok, MusteriTipi, SepetTutari, TeslimYontemi,
                                birim_fiyat_gosterimi, gosterim_kdv_dahil, sepet_hesapla)
from app.hesap.servis import Adres, Musteri, adres_kaydet, adres_son
from app.katalog.depo import urun_getir
from app.sepet import servis as sepet_servis
from app.siparis.odeme_sim import (BASARILI_KART, RET_KARTI, SMS_KODU, OdemeSonucu, deneme_getir,
                                   odeme_baslat, sms_dogrula)
from app.siparis.servis import SepetBos, Siparis, SiparisDurumu, siparis_no_ile, siparis_olustur
from app.web.bagimlilik import db_bagimliligi
from app.web.baglam import fiyat_baglami, sablon
from app.web.guvenlik import aktif_musteri, csrf_dogrula, oturum_kimligi

router = APIRouter()

ADRES_ALANLARI = ("ad_soyad", "satir1", "satir2", "sehir", "posta_kodu", "ulke", "telefon")
ZORUNLU_ADRES = ("ad_soyad", "satir1", "sehir", "ulke")
ONEKLER = ("teslimat", "fatura")
EK_ALANLAR = ("fatura_ayni", "teslim", "on_bilgi_onay", "mesafeli_onay", "kosullar_onay",
              "gosterilen_toplam", "gosterilen_kur")
FORM_ALANLARI = tuple(f"{o}_{a}" for o in ONEKLER for a in ADRES_ALANLARI) + EK_ALANLAR
ULKE_DESENI = re.compile(r"[A-Z]{2}")
ANAHTAR_DESENI = re.compile(r"[A-Za-z0-9_-]{16,64}")
ODEME_HATALARI = frozenset({"gecersiz_kart", "ret", "sms_hatali"})
AZAMI_UZUNLUK = 200


# ---------- ortak yardımcılar ----------

def _simdi() -> datetime:
    return datetime.now(UTC)


def _tamsayi(deger: object) -> int | None:
    try:
        return int(str(deger).strip())
    except (TypeError, ValueError):
        return None


def _giris_yonlendir(dil: str, sonraki: str) -> RedirectResponse:
    return RedirectResponse(f"/{dil}/giris?sonraki={quote(sonraki, safe='/')}", status_code=303)


def _sepet_id(request: Request, con: sqlite3.Connection, musteri: Musteri | None) -> int:
    with con:
        return sepet_servis.sepet_bul(con, oturum_kimligi(request), musteri.id if musteri else None, _simdi())


def _kalemler(con: sqlite3.Connection, sepet_id: int) -> tuple[list[Kalem], list[str]]:
    with con:  # düşen ürünler sepetten silinir; silme kalıcı olsun
        return sepet_servis.kalemler(con, sepet_id)


def _teslim_secenekleri(ulke: str) -> list[TeslimYontemi]:
    """K4: TR -> kargo, fabrika ; TR dışı -> yurtdisi_dap, fabrika."""
    if ulke == "TR":
        return [TeslimYontemi.KARGO, TeslimYontemi.FABRIKA]
    return [TeslimYontemi.YURTDISI_DAP, TeslimYontemi.FABRIKA]


def _teslim_coz(deger: str | None, ulke: str) -> TeslimYontemi:
    secenekler = _teslim_secenekleri(ulke)
    try:
        teslim = TeslimYontemi(deger or "")
    except ValueError:
        return secenekler[0]
    return teslim if teslim in secenekler else secenekler[0]


def _hesapla(kalemler, baglam: Baglam, teslim: TeslimYontemi,
             kur: Kur | None) -> tuple[SepetTutari | None, str | None]:
    try:
        return sepet_hesapla(kalemler, baglam, teslim, kur.eur_satis if kur else None), None
    except KurYok:  # K5
        return None, "kur_yok"


def _kur_metni(tutar: SepetTutari | None) -> str:
    return str(tutar.kur) if tutar is not None and tutar.kur is not None else ""


# ---------- sepet ----------

def _sepet_sayfasi(request: Request, con: sqlite3.Connection, *, uyari: str | None = None,
                   teklif_urun_id: int | None = None, durum: int = 200) -> Response:
    musteri = aktif_musteri(request, con)
    kalemler, dusenler = _kalemler(con, _sepet_id(request, con, musteri))
    baglam = fiyat_baglami(request, musteri)
    kur = son_kur(con)
    kur_eur = kur.eur_satis if kur else None
    teslim = _teslim_secenekleri(baglam.teslimat_ulkesi)[0]
    tutar, hata = _hesapla(kalemler, baglam, teslim, kur) if kalemler else (None, None)
    satirlar = [{"kalem": k, "urun": urun_getir(con, k.urun_id),
                 "gosterim": birim_fiyat_gosterimi(k.birim_net_eur, k.kdv_orani, baglam, kur_eur),
                 "tutar": None} for k in kalemler]
    if tutar is not None:
        for satir, satir_tutari in zip(satirlar, tutar.satirlar):
            satir["tutar"] = satir_tutari
    return sablon(request, "sepet.html", {
        "satirlar": satirlar, "tutar": tutar, "hata": hata, "dusenler": dusenler,
        "uyari": uyari, "teklif_urun_id": teklif_urun_id, "teslim": teslim,
        "kdv_dahil": gosterim_kdv_dahil(baglam), "eklendi": request.query_params.get("eklendi") == "1",
    }, durum)


@router.get("/{dil:dil}/sepet")
def sepet_goster(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    return _sepet_sayfasi(request, con)


@router.post("/{dil:dil}/sepet/ekle")
async def sepet_ekle(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    await csrf_dogrula(request)
    form = await request.form()
    urun_id, adet = _tamsayi(form.get("urun_id")), _tamsayi(form.get("adet", "1"))
    if urun_id is None or adet is None:
        raise HTTPException(status_code=400)
    sepet_id = _sepet_id(request, con, aktif_musteri(request, con))
    try:
        with con:
            sepet_servis.ekle(con, sepet_id, urun_id, adet)
    except sepet_servis.UrunYok:
        raise HTTPException(status_code=404) from None
    except sepet_servis.TeklifZorunlu:
        return _sepet_sayfasi(request, con, uyari="sepet.teklif_zorunlu", teklif_urun_id=urun_id, durum=409)
    return RedirectResponse(f"/{dil}/sepet?eklendi=1", status_code=303)


@router.post("/{dil:dil}/sepet/adet")
async def sepet_adet(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    await csrf_dogrula(request)
    form = await request.form()
    urun_id, adet = _tamsayi(form.get("urun_id")), _tamsayi(form.get("adet"))
    if urun_id is None or adet is None:
        raise HTTPException(status_code=400)
    sepet_id = _sepet_id(request, con, aktif_musteri(request, con))
    with con:
        sepet_servis.adet_ayarla(con, sepet_id, urun_id, adet)
    return RedirectResponse(f"/{dil}/sepet", status_code=303)


@router.post("/{dil:dil}/sepet/kaldir")
async def sepet_kaldir(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    await csrf_dogrula(request)
    form = await request.form()
    urun_id = _tamsayi(form.get("urun_id"))
    if urun_id is None:
        raise HTTPException(status_code=400)
    sepet_id = _sepet_id(request, con, aktif_musteri(request, con))
    with con:
        sepet_servis.kaldir(con, sepet_id, urun_id)
    return RedirectResponse(f"/{dil}/sepet", status_code=303)


# ---------- ödeme formu ----------

def _bos_alanlar() -> dict[str, str]:
    return {ad: "" for ad in FORM_ALANLARI}


def _adresten(onek: str, adres: Adres | None) -> dict[str, str]:
    if adres is None:
        return {}
    return {f"{onek}_{ad}": getattr(adres, ad) or "" for ad in ADRES_ALANLARI}


def _baslangic_alanlari(con: sqlite3.Connection, musteri: Musteri) -> dict[str, str]:
    alanlar = _bos_alanlar()
    alanlar.update(teslimat_ad_soyad=musteri.ad, teslimat_ulke=musteri.ulke)
    teslimat = adres_son(con, musteri.id, "teslimat")
    fatura = adres_son(con, musteri.id, "fatura")
    alanlar.update(_adresten("teslimat", teslimat))
    alanlar.update(_adresten("fatura", fatura))
    alanlar["fatura_ayni"] = "1" if fatura is None or fatura == teslimat else ""
    alanlar["teslim"] = _teslim_secenekleri(alanlar["teslimat_ulke"])[0].value
    return alanlar


def _formdan(form: Mapping) -> dict[str, str]:
    alanlar = {ad: str(form.get(ad, "")).strip() for ad in FORM_ALANLARI}
    for onek in ONEKLER:
        alanlar[f"{onek}_ulke"] = alanlar[f"{onek}_ulke"].upper()
    if alanlar["fatura_ayni"]:
        for ad in ADRES_ALANLARI:
            alanlar[f"fatura_{ad}"] = alanlar[f"teslimat_{ad}"]
    return alanlar


def _dogrula(alanlar: dict[str, str], musteri: Musteri) -> dict[str, str]:
    """Alan adı -> i18n hata anahtarı (K14: `form_hata.zorunlu`, `hata_kodu.<kod>`)."""
    hatalar: dict[str, str] = {}
    for ad, deger in alanlar.items():
        if len(deger) > AZAMI_UZUNLUK:
            hatalar[ad] = "hata_kodu.cok_uzun"
    for onek in ONEKLER:
        for ad in ZORUNLU_ADRES:
            if not alanlar[f"{onek}_{ad}"]:
                hatalar[f"{onek}_{ad}"] = "form_hata.zorunlu"
        ulke = alanlar[f"{onek}_ulke"]
        if ulke and not ULKE_DESENI.fullmatch(ulke):
            hatalar[f"{onek}_ulke"] = "hata_kodu.ulke_kodu"
    try:
        teslim = TeslimYontemi(alanlar["teslim"])
    except ValueError:
        hatalar["teslim"] = "hata_kodu.teslim_secilmedi"
    else:
        if "teslimat_ulke" not in hatalar:
            if alanlar["teslimat_ulke"] != "TR" and teslim == TeslimYontemi.KARGO:
                hatalar["teslim"] = "hata_kodu.teslim_yurtdisi"
            elif alanlar["teslimat_ulke"] == "TR" and teslim == TeslimYontemi.YURTDISI_DAP:
                hatalar["teslim"] = "hata_kodu.teslim_yurtici"
    if musteri.tip == MusteriTipi.BIREYSEL:
        onaylar = ("on_bilgi_onay", "mesafeli_onay")
    else:
        onaylar = ("kosullar_onay",)
    for ad in onaylar:
        if not alanlar[ad]:
            hatalar[ad] = "hata_kodu.onay_yok"
    return hatalar


def _adres(alanlar: dict[str, str], onek: str) -> Adres:
    def bos_ise_none(ad: str) -> str | None:
        return alanlar[f"{onek}_{ad}"] or None
    return Adres(ad_soyad=alanlar[f"{onek}_ad_soyad"], satir1=alanlar[f"{onek}_satir1"],
                 sehir=alanlar[f"{onek}_sehir"], ulke=alanlar[f"{onek}_ulke"],
                 satir2=bos_ise_none("satir2"), posta_kodu=bos_ise_none("posta_kodu"),
                 telefon=bos_ise_none("telefon"))


def _ayni_tutar(alanlar: dict[str, str], tutar: SepetTutari) -> bool:
    try:
        gosterilen = Decimal(alanlar["gosterilen_toplam"])
    except (InvalidOperation, ValueError):
        return False
    return gosterilen == tutar.toplam and alanlar["gosterilen_kur"] == _kur_metni(tutar)


def _odeme_sayfasi(request: Request, con: sqlite3.Connection, musteri: Musteri,
                   alanlar: dict[str, str], kalemler: list[Kalem], dusenler: list[str], *,
                   hatalar: dict[str, str] | None = None, mesaj: str | None = None,
                   durum: int = 200) -> Response:
    ulke = alanlar["teslimat_ulke"] if ULKE_DESENI.fullmatch(alanlar["teslimat_ulke"]) else musteri.ulke
    teslim = _teslim_coz(alanlar["teslim"], ulke)
    alanlar = {**alanlar, "teslim": teslim.value}
    tutar, hata = _hesapla(kalemler, Baglam(musteri.tip, ulke), teslim, son_kur(con)) if kalemler else (None, None)
    return sablon(request, "odeme.html", {
        "alanlar": alanlar, "hatalar": hatalar or {}, "mesaj": mesaj, "hata": hata,
        "dusenler": dusenler, "kalemler": kalemler, "tutar": tutar, "teslim": teslim,
        "teslim_secenekleri": _teslim_secenekleri(ulke),
        "bireysel": musteri.tip == MusteriTipi.BIREYSEL,
        "gosterilen_toplam": str(tutar.toplam) if tutar is not None else "",
        "gosterilen_kur": _kur_metni(tutar),
    }, durum)


@router.get("/{dil:dil}/odeme")
def odeme_formu(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return _giris_yonlendir(dil, f"/{dil}/odeme")
    kalemler, dusenler = _kalemler(con, _sepet_id(request, con, musteri))
    if not kalemler and not dusenler:
        return RedirectResponse(f"/{dil}/sepet", status_code=303)
    return _odeme_sayfasi(request, con, musteri, _baslangic_alanlari(con, musteri), kalemler, dusenler)


@router.post("/{dil:dil}/odeme")
async def odeme_gonder(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    await csrf_dogrula(request)
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return _giris_yonlendir(dil, f"/{dil}/odeme")
    form = await request.form()
    alanlar = _formdan(form)
    sepet_id = _sepet_id(request, con, musteri)
    kalemler, dusenler = _kalemler(con, sepet_id)          # K21: siparis_olustur'dan önce
    if not kalemler and not dusenler:
        return RedirectResponse(f"/{dil}/sepet", status_code=303)

    def sayfa(**ek) -> Response:
        return _odeme_sayfasi(request, con, musteri, alanlar, kalemler, dusenler, **ek)

    if form.get("islem") == "hesapla":                     # yalnız yeniden hesapla, sipariş yok
        return sayfa()
    hatalar = _dogrula(alanlar, musteri)
    if hatalar:
        return sayfa(hatalar=hatalar, durum=400)
    if dusenler or not kalemler:                           # sepet değişti: kullanıcı yeni tutarı görsün
        return sayfa(mesaj="odeme.tutar_guncellendi", durum=409)
    teslim = TeslimYontemi(alanlar["teslim"])
    kur = son_kur(con)
    tutar, hata = _hesapla(kalemler, Baglam(musteri.tip, alanlar["teslimat_ulke"]), teslim, kur)
    if hata is not None:
        return sayfa(durum=503)
    if not _ayni_tutar(alanlar, tutar):
        return sayfa(mesaj="odeme.tutar_guncellendi", durum=409)
    teslimat, fatura = _adres(alanlar, "teslimat"), _adres(alanlar, "fatura")
    try:
        with con:
            adres_kaydet(con, musteri.id, "teslimat", teslimat)
            adres_kaydet(con, musteri.id, "fatura", fatura)
            siparis = siparis_olustur(con, musteri, sepet_id, teslim, teslimat, fatura, kur, _simdi())
    except SepetBos:
        return RedirectResponse(f"/{dil}/sepet", status_code=303)
    return RedirectResponse(f"/{dil}/odeme/{siparis.no}/kart", status_code=303)


# ---------- kart, 3D, sipariş ----------

def _sahip_siparis(con: sqlite3.Connection, no: str, musteri: Musteri) -> Siparis:
    with con:  # siparis_no_ile zaman aşımını uygular (yazabilir)
        siparis = siparis_no_ile(con, no, _simdi())
    if siparis is None or siparis.musteri_id != musteri.id:
        raise HTTPException(status_code=404)
    return siparis


def _deneme(con: sqlite3.Connection, anahtar: str, siparis: Siparis) -> sqlite3.Row:
    """K13: deneme_getir ile okunur; anahtar biçimsiz, yok ya da başka siparişe aitse 404."""
    deneme = deneme_getir(con, anahtar) if ANAHTAR_DESENI.fullmatch(anahtar) else None
    if deneme is None or deneme["siparis_id"] != siparis.id:
        raise HTTPException(status_code=404)
    return deneme


def _bosluklu(kart: str) -> str:
    return " ".join(kart[i:i + 4] for i in range(0, len(kart), 4))


def _kart_sayfasi(request: Request, siparis: Siparis, hata_kodu: str | None = None,
                  durum: int = 200) -> Response:
    return sablon(request, "kart.html", {
        "siparis": siparis, "islem_anahtari": secrets.token_urlsafe(24), "hata_kodu": hata_kodu,
        "test_kartlari": [(_bosluklu(BASARILI_KART), "kart.test_basarili"),
                          (_bosluklu(RET_KARTI), "kart.test_ret")],
        "sms_kodu": SMS_KODU,
    }, durum)


def _siparise(dil: str, siparis: Siparis, hata_kodu: str | None = None) -> RedirectResponse:
    hedef = f"/{dil}/siparis/{siparis.no}"
    if hata_kodu in ODEME_HATALARI:
        hedef += f"?hata={hata_kodu}"
    return RedirectResponse(hedef, status_code=303)


@router.get("/{dil:dil}/odeme/{no}/kart")
def kart_formu(dil: str, no: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return _giris_yonlendir(dil, f"/{dil}/odeme/{no}/kart")
    siparis = _sahip_siparis(con, no, musteri)
    if siparis.durum != SiparisDurumu.ODEME_BEKLIYOR:
        return _siparise(dil, siparis)
    return _kart_sayfasi(request, siparis)


@router.post("/{dil:dil}/odeme/{no}/kart")
async def kart_gonder(dil: str, no: str, request: Request,
                      con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    await csrf_dogrula(request)
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return _giris_yonlendir(dil, f"/{dil}/odeme/{no}/kart")
    siparis = _sahip_siparis(con, no, musteri)
    form = await request.form()
    anahtar = str(form.get("islem_anahtari", ""))
    if not ANAHTAR_DESENI.fullmatch(anahtar):
        raise HTTPException(status_code=400)
    with con:
        sonuc = odeme_baslat(con, siparis.id, anahtar, str(form.get("kart_no", "")), _simdi())
    if sonuc == OdemeSonucu.SMS_BEKLIYOR:
        return RedirectResponse(f"/{dil}/odeme/{siparis.no}/3d?a={anahtar}", status_code=303)
    if sonuc == OdemeSonucu.GECERSIZ_KART:
        return _kart_sayfasi(request, siparis, sonuc.value, 400)
    return _siparise(dil, siparis, sonuc.value)   # BASARILI, ZATEN_ODENDI, SIPARIS_GECERSIZ, aynı anahtarla RET/SMS_HATALI


@router.get("/{dil:dil}/odeme/{no}/3d")
def uc_d_formu(dil: str, no: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return _giris_yonlendir(dil, f"/{dil}/odeme/{no}/kart")
    siparis = _sahip_siparis(con, no, musteri)
    anahtar = request.query_params.get("a", "")
    deneme = _deneme(con, anahtar, siparis)
    if deneme["durum"] != "sms_bekliyor":
        return _siparise(dil, siparis, deneme["durum"])
    return sablon(request, "uc_d.html", {"siparis": siparis, "anahtar": anahtar,
                                         "kart_son4": deneme["kart_son4"], "sms_kodu": SMS_KODU})


@router.post("/{dil:dil}/odeme/{no}/3d")
async def uc_d_gonder(dil: str, no: str, request: Request,
                      con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    await csrf_dogrula(request)
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return _giris_yonlendir(dil, f"/{dil}/odeme/{no}/kart")
    siparis = _sahip_siparis(con, no, musteri)
    form = await request.form()
    anahtar = str(form.get("a", ""))
    _deneme(con, anahtar, siparis)
    with con:
        sonuc = sms_dogrula(con, anahtar, str(form.get("sms_kodu", "")).strip(), _simdi())
    if sonuc == OdemeSonucu.SMS_BEKLIYOR:
        return RedirectResponse(f"/{dil}/odeme/{siparis.no}/3d?a={anahtar}", status_code=303)
    return _siparise(dil, siparis, sonuc.value)   # BASARILI -> hatasız; RET / SMS_HATALI -> ?hata=<kod> (K12)


@router.get("/{dil:dil}/siparis/{no}")
def siparis_goster(dil: str, no: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    musteri = aktif_musteri(request, con)
    if musteri is None:
        return _giris_yonlendir(dil, f"/{dil}/siparis/{no}")
    siparis = _sahip_siparis(con, no, musteri)
    hata_kodu = request.query_params.get("hata")
    if hata_kodu not in ODEME_HATALARI or siparis.durum != SiparisDurumu.ODEME_BEKLIYOR:
        hata_kodu = None
    return sablon(request, "siparis.html", {"siparis": siparis, "hata_kodu": hata_kodu})
```

- [ ] **Step 5: Ortak tutar özeti parçasını yaz**

`app/web/sablonlar/_tutar_ozeti.html` (ortak bağlamdaki `kur_metni`, `kur_tarihi`, `kur_bayat` kullanılır — K9):

```html
<dl class="tutar-ozeti">
  <dt>{{ t('tutar.ara_toplam') }}</dt><dd>{{ para(tutar.ara_toplam, tutar.para_birimi) }}</dd>
  <dt>{{ t('tutar.kargo') }}</dt><dd>{{ para(tutar.kargo_net, tutar.para_birimi) }}</dd>
  {% if tutar.ihracat_istisnasi %}
  <dt data-e2e="satir-ihracat">{{ t('tutar.ihracat_istisnasi') }}</dt><dd>{{ para(tutar.kdv, tutar.para_birimi) }}</dd>
  {% else %}
  <dt data-e2e="satir-kdv">{{ t('tutar.kdv') }}</dt><dd>{{ para(tutar.kdv, tutar.para_birimi) }}</dd>
  {% endif %}
  <dt class="toplam">{{ t('tutar.toplam') }}</dt><dd class="toplam">{{ para(tutar.toplam, tutar.para_birimi) }}</dd>
</dl>
{% if teslim == 'yurtdisi_dap' %}
<p class="not" data-e2e="not-dap">{{ t('tutar.dap_notu') }}</p>
<p class="not">{{ t('tutar.navlun_notu') }}</p>
{% endif %}
{% if tutar.kur %}
<p class="kur-satiri{% if kur_bayat %} kur-bayat{% endif %}">{{ t('tutar.kur', kur=kur_metni, tarih=kur_tarihi) }}</p>
{% endif %}
```

- [ ] **Step 6: Sepet şablonunu yaz**

`app/web/sablonlar/sepet.html`:

```html
{% extends "taban.html" %}
{% from "_makrolar.html" import fiyat with context %}
{% block baslik %}{{ t('sepet.baslik') }}{% endblock %}
{% block icerik %}
<section class="sepet">
  <h1>{{ t('sepet.baslik') }}</h1>
  {% if eklendi %}<p class="basari" role="status">{{ t('sepet.eklendi') }}</p>{% endif %}
  {% if uyari %}
  <div class="uyari" role="alert">
    <p>{{ t(uyari) }}</p>
    {% if teklif_urun_id %}<p><a class="dugme" href="/{{ dil }}/teklif?urun_id={{ teklif_urun_id }}" data-e2e="teklif-iste">{{ t('sepet.teklif_iste') }}</a></p>{% endif %}
  </div>
  {% endif %}
  {% if dusenler %}<div class="uyari" role="alert">{{ t('sepet.dusen_urunler', adlar=dusenler|join(', ')) }}</div>{% endif %}
  {% if not satirlar %}
  <p>{{ t('sepet.bos') }}</p>
  <p><a href="/{{ dil }}/">{{ t('sepet.alisverise_don') }}</a></p>
  {% else %}
  {% if hata %}<div class="uyari" role="alert">{{ t('hata_kodu.' ~ hata) }}</div>{% endif %}
  <table class="sepet-tablo">
    <thead>
      <tr>
        <th scope="col">{{ t('sepet.urun') }}</th>
        <th scope="col">{{ t('sepet.birim_fiyat') }}</th>
        <th scope="col">{{ t('sepet.adet') }}</th>
        <th scope="col">{{ t('sepet.tutar_kdv_dahil') if kdv_dahil else t('sepet.tutar_kdv_haric') }}</th>
        <th scope="col"><span class="gizli-etiket">{{ t('sepet.kaldir') }}</span></th>
      </tr>
    </thead>
    <tbody>
      {% for s in satirlar %}
      <tr data-e2e="sepet-kalemi">
        <td>
          <a href="/{{ dil }}/urun/{{ s.kalem.urun_id }}">{{ s.kalem.ad }}</a><br><small>{{ s.kalem.sku }}</small>
          {% if s.kalem.tedarik_teyit %}<br><small class="not">{{ t('sepet.tedarik_teyit') }}</small>{% endif %}
        </td>
        <td>{% if s.urun %}{{ fiyat(s.urun, s.gosterim) }}{% endif %}</td>
        <td>
          <form method="post" action="/{{ dil }}/sepet/adet" class="satir-formu">
            <input type="hidden" name="csrf" value="{{ csrf }}">
            <input type="hidden" name="urun_id" value="{{ s.kalem.urun_id }}">
            <label class="gizli-etiket" for="adet-{{ s.kalem.urun_id }}">{{ t('sepet.adet') }}</label>
            <input id="adet-{{ s.kalem.urun_id }}" type="number" name="adet" min="1" max="99" value="{{ s.kalem.adet }}">
            <button type="submit">{{ t('sepet.guncelle') }}</button>
          </form>
        </td>
        <td>{% if s.tutar %}{{ para(s.tutar.brut if kdv_dahil else s.tutar.net, tutar.para_birimi) }}{% endif %}</td>
        <td>
          <form method="post" action="/{{ dil }}/sepet/kaldir">
            <input type="hidden" name="csrf" value="{{ csrf }}">
            <input type="hidden" name="urun_id" value="{{ s.kalem.urun_id }}">
            <button type="submit" class="dugme-ikincil">{{ t('sepet.kaldir') }}</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% if tutar %}{% include "_tutar_ozeti.html" %}{% endif %}
  <p class="not">{{ t('sepet.kargo_notu') }}</p>
  <p class="sepet-dugmeler">
    <a href="/{{ dil }}/">{{ t('sepet.alisverise_don') }}</a>
    <a class="dugme" href="/{{ dil }}/odeme" data-e2e="odemeye-gec">{{ t('sepet.odemeye_gec') }}</a>
  </p>
  {% endif %}
</section>
{% endblock %}
```

- [ ] **Step 7: Ödeme şablonunu yaz**

`app/web/sablonlar/odeme.html`:

```html
{% extends "taban.html" %}
{% block baslik %}{{ t('odeme.baslik') }}{% endblock %}
{% block icerik %}
{% macro alan(ad, etiket, tip="text", zorunlu=True, ek="") %}
<p class="form-alan">
  <label for="{{ ad }}">{{ t(etiket) }}{% if zorunlu %} *{% endif %}</label>
  <input id="{{ ad }}" name="{{ ad }}" type="{{ tip }}" value="{{ alanlar[ad] }}" maxlength="200"{% if ek %} {{ ek|safe }}{% endif %}{% if hatalar.get(ad) %} aria-invalid="true" aria-describedby="hata-{{ ad }}"{% endif %}>
  {% if hatalar.get(ad) %}<span class="alan-hata" id="hata-{{ ad }}">{{ t(hatalar[ad]) }}</span>{% endif %}
</p>
{% endmacro %}
{% macro onay(ad, etiket, belgeler) %}
<p class="onay-kutusu">
  <label><input type="checkbox" name="{{ ad }}" value="1"{% if alanlar[ad] %} checked{% endif %}{% if hatalar.get(ad) %} aria-invalid="true" aria-describedby="hata-{{ ad }}"{% endif %}> {{ t(etiket) }}</label>
  {% for sayfa, belge in belgeler %}<a href="/{{ dil }}/yasal/{{ sayfa }}" target="_blank" rel="noopener">{{ t(belge) }}</a> {% endfor %}
  {% if hatalar.get(ad) %}<span class="alan-hata" id="hata-{{ ad }}">{{ t(hatalar[ad]) }}</span>{% endif %}
</p>
{% endmacro %}
<section class="odeme">
  <h1>{{ t('odeme.baslik') }}</h1>
  <p class="demo-uyari" role="note">{{ t('odeme.gercek_veri_uyari') }}</p>
  {% if dusenler %}<div class="uyari" role="alert">{{ t('sepet.dusen_urunler', adlar=dusenler|join(', ')) }}</div>{% endif %}
  {% if mesaj %}<div class="uyari" role="alert">{{ t(mesaj) }}</div>{% endif %}
  {% if hata %}<div class="uyari" role="alert">{{ t('hata_kodu.' ~ hata) }}</div>{% endif %}
  {% if not kalemler %}
  <p>{{ t('sepet.bos') }} <a href="/{{ dil }}/sepet">{{ t('odeme.sepete_don') }}</a></p>
  {% else %}
  <form method="post" action="/{{ dil }}/odeme" class="odeme-formu" novalidate>
    <input type="hidden" name="csrf" value="{{ csrf }}">
    <input type="hidden" name="gosterilen_toplam" value="{{ gosterilen_toplam }}">
    <input type="hidden" name="gosterilen_kur" value="{{ gosterilen_kur }}">

    <fieldset>
      <legend>{{ t('odeme.teslimat_adresi') }}</legend>
      {{ alan('teslimat_ad_soyad', 'odeme.ad_soyad', ek='autocomplete="name"') }}
      {{ alan('teslimat_satir1', 'odeme.adres_satir1', ek='autocomplete="address-line1"') }}
      {{ alan('teslimat_satir2', 'odeme.adres_satir2', zorunlu=False, ek='autocomplete="address-line2"') }}
      {{ alan('teslimat_sehir', 'odeme.sehir', ek='autocomplete="address-level2"') }}
      {{ alan('teslimat_posta_kodu', 'odeme.posta_kodu', zorunlu=False, ek='autocomplete="postal-code"') }}
      {{ alan('teslimat_ulke', 'odeme.ulke', ek='autocomplete="country" pattern="[A-Za-z]{2}"') }}
      {{ alan('teslimat_telefon', 'odeme.telefon', tip='tel', zorunlu=False, ek='autocomplete="tel"') }}
    </fieldset>

    <p class="onay-kutusu">
      <label><input type="checkbox" id="fatura_ayni" name="fatura_ayni" value="1"{% if alanlar.fatura_ayni %} checked{% endif %}> {{ t('odeme.fatura_ayni') }}</label>
    </p>
    <fieldset class="fatura-adresi">
      <legend>{{ t('odeme.fatura_adresi') }}</legend>
      {{ alan('fatura_ad_soyad', 'odeme.ad_soyad') }}
      {{ alan('fatura_satir1', 'odeme.adres_satir1') }}
      {{ alan('fatura_satir2', 'odeme.adres_satir2', zorunlu=False) }}
      {{ alan('fatura_sehir', 'odeme.sehir') }}
      {{ alan('fatura_posta_kodu', 'odeme.posta_kodu', zorunlu=False) }}
      {{ alan('fatura_ulke', 'odeme.ulke') }}
      {{ alan('fatura_telefon', 'odeme.telefon', tip='tel', zorunlu=False) }}
    </fieldset>

    <fieldset>
      <legend>{{ t('odeme.teslim_yontemi') }}</legend>
      {% for y in teslim_secenekleri %}
      <p><label><input type="radio" name="teslim" value="{{ y }}"{% if y == teslim %} checked{% endif %}> {{ t('odeme.teslim.' ~ y) }}</label></p>
      {% endfor %}
      {% if hatalar.get('teslim') %}<span class="alan-hata" id="hata-teslim">{{ t(hatalar['teslim']) }}</span>{% endif %}
      <p class="not">{{ t('odeme.teslim_ulke_notu') }}</p>
    </fieldset>

    <h2>{{ t('odeme.ozet') }}</h2>
    <ul class="odeme-kalemleri">
      {% for k in kalemler %}
      <li>{{ k.adet }} × {{ k.ad }} <small>({{ k.sku }})</small>{% if k.tedarik_teyit %} — <small class="not">{{ t('sepet.tedarik_teyit') }}</small>{% endif %}</li>
      {% endfor %}
    </ul>
    {% if tutar %}{% include "_tutar_ozeti.html" %}{% endif %}

    <fieldset>
      <legend>{{ t('odeme.onaylar') }}</legend>
      {% if bireysel %}
      {{ onay('on_bilgi_onay', 'odeme.onay_on_bilgi', [('on-bilgilendirme', 'odeme.belge.on_bilgilendirme')]) }}
      {{ onay('mesafeli_onay', 'odeme.onay_mesafeli', [('mesafeli-satis', 'odeme.belge.mesafeli_satis')]) }}
      {% else %}
      {{ onay('kosullar_onay', 'odeme.onay_kosullar', [('kullanim', 'odeme.belge.kullanim'), ('iade', 'odeme.belge.iade'), ('garanti', 'odeme.belge.garanti')]) }}
      {% endif %}
    </fieldset>

    <p class="odeme-dugmeler">
      <button type="submit" name="islem" value="odeme" class="dugme" data-e2e="odeme-gonder">{{ t('odeme.odemeye_gec') }}</button>
      <button type="submit" name="islem" value="hesapla" class="dugme-ikincil">{{ t('odeme.yeniden_hesapla') }}</button>
    </p>
  </form>
  {% endif %}
</section>
{% endblock %}
```

- [ ] **Step 8: Kart, 3D ve sipariş şablonlarını yaz**

`app/web/sablonlar/kart.html` (sipariş tutarı özeti, Görev 18 tablosundaki `satir-kdv`/`satir-ihracat`/`not-dap` öznitelikleriyle):

```html
{% extends "taban.html" %}
{% block baslik %}{{ t('kart.baslik') }}{% endblock %}
{% block icerik %}
<section class="kart-odeme">
  <h1>{{ t('kart.baslik') }}</h1>
  <p class="demo-uyari" role="note"><strong>{{ t('kart.demo_uyari') }}</strong></p>
  {% if hata_kodu %}<div class="uyari" role="alert" data-e2e="odeme-hata" data-kod="{{ hata_kodu }}">{{ t('hata_kodu.' ~ hata_kodu) }}</div>{% endif %}
  <p>{{ t('kart.siparis', no=siparis.no) }}</p>
  <dl class="tutar-ozeti">
    <dt>{{ t('tutar.ara_toplam') }}</dt><dd>{{ para(siparis.ara_toplam, siparis.para_birimi) }}</dd>
    <dt>{{ t('tutar.kargo') }}</dt><dd>{{ para(siparis.kargo, siparis.para_birimi) }}</dd>
    {% if siparis.ihracat_istisnasi %}
    <dt data-e2e="satir-ihracat">{{ t('tutar.ihracat_istisnasi') }}</dt><dd>{{ para(siparis.kdv, siparis.para_birimi) }}</dd>
    {% else %}
    <dt data-e2e="satir-kdv">{{ t('tutar.kdv') }}</dt><dd>{{ para(siparis.kdv, siparis.para_birimi) }}</dd>
    {% endif %}
    <dt class="toplam">{{ t('tutar.toplam') }}</dt><dd class="toplam">{{ para(siparis.toplam, siparis.para_birimi) }}</dd>
  </dl>
  {% if siparis.teslim_yontemi == 'yurtdisi_dap' %}<p class="not" data-e2e="not-dap">{{ t('tutar.dap_notu') }}</p>{% endif %}
  <form method="post" action="/{{ dil }}/odeme/{{ siparis.no }}/kart" autocomplete="off">
    <input type="hidden" name="csrf" value="{{ csrf }}">
    <input type="hidden" name="islem_anahtari" value="{{ islem_anahtari }}">
    <p class="form-alan">
      <label for="kart_no">{{ t('kart.kart_no') }}</label>
      <input id="kart_no" name="kart_no" type="text" inputmode="numeric" autocomplete="off" maxlength="23" required>
    </p>
    <p class="form-alan">
      <label for="kart_skt">{{ t('kart.son_kullanma') }}</label>
      <input id="kart_skt" type="text" inputmode="numeric" autocomplete="off" maxlength="5" placeholder="{{ t('kart.skt_ornek') }}">
    </p>
    <p class="form-alan">
      <label for="kart_cvc">{{ t('kart.cvc') }}</label>
      <input id="kart_cvc" type="password" inputmode="numeric" autocomplete="off" maxlength="4">
    </p>
    <p class="not">{{ t('kart.skt_cvc_notu') }}</p>
    <p class="not">{{ t('kart.sure_notu') }}</p>
    <button type="submit" class="dugme" data-e2e="kart-gonder">{{ t('kart.ode') }}</button>
  </form>
  <aside class="test-kartlari" aria-labelledby="test-kartlari-baslik">
    <h2 id="test-kartlari-baslik">{{ t('kart.test_kartlari') }}</h2>
    <ul>
      {% for numara, anahtar in test_kartlari %}<li><code>{{ numara }}</code> — {{ t(anahtar) }}</li>{% endfor %}
      <li>{{ t('kart.test_sms', kod=sms_kodu) }}</li>
    </ul>
  </aside>
</section>
{% endblock %}
```

`app/web/sablonlar/uc_d.html`:

```html
{% extends "taban.html" %}
{% block baslik %}{{ t('uc_d.baslik') }}{% endblock %}
{% block icerik %}
<section class="uc-d">
  <h1>{{ t('uc_d.baslik') }}</h1>
  <p class="demo-uyari" role="note"><strong>{{ t('uc_d.demo_uyari') }}</strong></p>
  <p>{{ t('uc_d.aciklama', son4=kart_son4, tutar=para(siparis.toplam, siparis.para_birimi)) }}</p>
  <form method="post" action="/{{ dil }}/odeme/{{ siparis.no }}/3d" autocomplete="off">
    <input type="hidden" name="csrf" value="{{ csrf }}">
    <input type="hidden" name="a" value="{{ anahtar }}">
    <p class="form-alan">
      <label for="sms_kodu">{{ t('uc_d.sms_kodu') }}</label>
      <input id="sms_kodu" name="sms_kodu" type="text" inputmode="numeric" maxlength="6" autocomplete="one-time-code" required>
    </p>
    <p class="not">{{ t('uc_d.ipucu', kod=sms_kodu) }}</p>
    <button type="submit" class="dugme" data-e2e="sms-gonder">{{ t('uc_d.onayla') }}</button>
  </form>
</section>
{% endblock %}
```

`app/web/sablonlar/siparis.html`:

```html
{% extends "taban.html" %}
{% block baslik %}{{ t('siparis.baslik', no=siparis.no) }}{% endblock %}
{% block icerik %}
{% macro adres(a) %}
<address>{{ a.ad_soyad }}<br>{{ a.satir1 }}{% if a.satir2 %}<br>{{ a.satir2 }}{% endif %}<br>{% if a.posta_kodu %}{{ a.posta_kodu }} {% endif %}{{ a.sehir }} / {{ a.ulke }}{% if a.telefon %}<br>{{ a.telefon }}{% endif %}</address>
{% endmacro %}
<section class="siparis">
  <h1>{{ t('siparis.baslik', no=siparis.no) }}</h1>
  {% if hata_kodu %}
  <div class="uyari" role="alert" data-e2e="odeme-hata" data-kod="{{ hata_kodu }}">
    <p>{{ t('hata_kodu.' ~ hata_kodu) }}</p>
    <p><a class="dugme" href="/{{ dil }}/odeme/{{ siparis.no }}/kart">{{ t('siparis.tekrar_dene') }}</a></p>
  </div>
  {% endif %}
  {% if siparis.durum == 'odendi' %}<p class="basari" role="status">{{ t('siparis.tesekkur') }}</p>{% endif %}
  {% if siparis.durum == 'iptal' %}<p class="uyari" role="alert">{{ t('siparis.iptal_notu') }}</p>{% endif %}
  <p>{{ t('siparis.durum_etiket') }}: <strong class="durum durum-{{ siparis.durum }}" data-e2e="siparis-durum" data-durum="{{ siparis.durum }}">{{ t('siparis_durum.' ~ siparis.durum) }}</strong></p>
  {% if siparis.durum == 'odeme_bekliyor' and not hata_kodu %}<p><a class="dugme" href="/{{ dil }}/odeme/{{ siparis.no }}/kart">{{ t('siparis.odemeye_don') }}</a></p>{% endif %}
  {% if siparis.kart_son4 %}<p>{{ t('siparis.kart', son4=siparis.kart_son4) }}</p>{% endif %}
  <table class="sepet-tablo">
    <thead>
      <tr>
        <th scope="col">{{ t('sepet.urun') }}</th><th scope="col">{{ t('siparis.sku') }}</th>
        <th scope="col">{{ t('sepet.adet') }}</th><th scope="col">{{ t('siparis.net') }}</th>
        <th scope="col">{{ t('siparis.kdv') }}</th><th scope="col">{{ t('siparis.brut') }}</th>
      </tr>
    </thead>
    <tbody>
      {% for k in siparis.kalemler %}
      <tr>
        <td>{{ k.ad }}{% if k.tedarik_teyit %}<br><small class="not">{{ t('sepet.tedarik_teyit') }}</small>{% endif %}</td>
        <td>{{ k.sku }}</td><td>{{ k.adet }}</td>
        <td>{{ para(k.net, siparis.para_birimi) }}</td><td>{{ para(k.kdv, siparis.para_birimi) }}</td>
        <td>{{ para(k.brut, siparis.para_birimi) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  <dl class="tutar-ozeti">
    <dt>{{ t('tutar.ara_toplam') }}</dt><dd>{{ para(siparis.ara_toplam, siparis.para_birimi) }}</dd>
    <dt>{{ t('tutar.kargo') }}</dt><dd>{{ para(siparis.kargo, siparis.para_birimi) }}</dd>
    {% if siparis.ihracat_istisnasi %}
    <dt data-e2e="satir-ihracat">{{ t('tutar.ihracat_istisnasi') }}</dt><dd>{{ para(siparis.kdv, siparis.para_birimi) }}</dd>
    {% else %}
    <dt data-e2e="satir-kdv">{{ t('tutar.kdv') }}</dt><dd>{{ para(siparis.kdv, siparis.para_birimi) }}</dd>
    {% endif %}
    <dt class="toplam">{{ t('tutar.toplam') }}</dt><dd class="toplam">{{ para(siparis.toplam, siparis.para_birimi) }}</dd>
  </dl>
  {% if siparis.kur %}<p class="kur-satiri">{{ t('siparis.kur', kur=siparis.kur, tarih=tarih(siparis.kur_tarihi) if siparis.kur_tarihi else '') }}</p>{% endif %}
  {% if siparis.teslim_yontemi == 'yurtdisi_dap' %}
  <p class="not" data-e2e="not-dap">{{ t('tutar.dap_notu') }}</p>
  <p class="not">{{ t('tutar.navlun_notu') }}</p>
  {% endif %}
  <h2>{{ t('siparis.teslim_yontemi') }}</h2>
  <p>{{ t('odeme.teslim.' ~ siparis.teslim_yontemi) }}</p>
  <div class="adresler">
    <div><h2>{{ t('siparis.teslimat') }}</h2>{{ adres(siparis.teslimat_adresi) }}</div>
    <div><h2>{{ t('siparis.fatura') }}</h2>{{ adres(siparis.fatura_adresi) }}</div>
  </div>
  <p><a href="/{{ dil }}/hesabim">{{ t('siparis.hesabim') }}</a></p>
</section>
{% endblock %}
```

- [ ] **Step 9: CSS ve JS eklerini yaz**

`app/web/statik/site.css` dosyasının sonuna ekle:

```css
/* --- Görev 14: sepet ve ödeme --- */
.uyari { border-left: 4px solid var(--kiremit); background: #fff; padding: .75rem 1rem; margin: 1rem 0; }
.basari { border-left: 4px solid var(--yesil); background: #fff; padding: .75rem 1rem; margin: 1rem 0; }
.demo-uyari { background: var(--kiremit); color: #fff; padding: .5rem 1rem; }
.not { color: var(--gri); font-size: .9rem; }
.alan-hata { display: block; color: var(--kiremit); font-size: .9rem; }
.gizli-etiket { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.sepet-tablo { width: 100%; border-collapse: collapse; }
.sepet-tablo th, .sepet-tablo td { border-bottom: 1px solid var(--cizgi); padding: .5rem; text-align: left; vertical-align: top; }
.sepet-tablo input[type=number] { width: 4.5rem; }
.tutar-ozeti { display: grid; grid-template-columns: 1fr auto; gap: .25rem 1rem; max-width: 26rem; margin: 1rem 0 1rem auto; }
.tutar-ozeti dd { margin: 0; text-align: right; }
.tutar-ozeti .toplam { font-weight: 700; border-top: 1px solid var(--cizgi); padding-top: .25rem; }
.kur-satiri { font-size: .85rem; color: var(--gri); text-align: right; }
.kur-satiri.kur-bayat { color: var(--kiremit); }
.form-alan { display: flex; flex-direction: column; gap: .25rem; margin: .5rem 0; }
.form-alan input { padding: .5rem; border: 1px solid var(--cizgi); max-width: 30rem; }
.form-alan input[aria-invalid=true] { border-color: var(--kiremit); }
.odeme fieldset { border: 1px solid var(--cizgi); margin: 1rem 0; padding: .5rem 1rem; }
.onay-kutusu a { margin-left: .5rem; }
.odeme-dugmeler, .sepet-dugmeler { display: flex; flex-wrap: wrap; gap: 1rem; align-items: center; }
.dugme-ikincil { background: transparent; border: 1px solid var(--yesil-koyu); color: var(--yesil-koyu); padding: .5rem 1rem; cursor: pointer; }
.test-kartlari { border: 1px dashed var(--mavi); padding: .5rem 1rem; margin-top: 1.5rem; }
.adresler { display: grid; grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr)); gap: 1rem; }
@media (max-width: 600px) {
  .sepet-tablo thead { display: none; }
  .sepet-tablo tr { display: block; border-bottom: 1px solid var(--cizgi); padding: .5rem 0; }
  .sepet-tablo td { display: block; border: 0; padding: .25rem 0; }
  .tutar-ozeti { margin-left: 0; }
}
```

`app/web/statik/site.js` dosyasının sonuna ekle:

```javascript
/* --- Görev 14: ödeme formu --- */
(function () {
  function faturaGuncelle() {
    var kutu = document.getElementById("fatura_ayni");
    var alan = document.querySelector(".fatura-adresi");
    if (kutu && alan) { alan.hidden = kutu.checked; }
  }
  document.addEventListener("change", function (olay) {
    var hedef = olay.target;
    if (!hedef) { return; }
    if (hedef.id === "fatura_ayni") { faturaGuncelle(); }
    if (hedef.id === "teslimat_ulke") {
      var dugme = document.querySelector('button[name="islem"][value="hesapla"]');
      if (dugme) { dugme.click(); }
    }
  });
  document.addEventListener("DOMContentLoaded", faturaGuncelle);
})();
```

- [ ] **Step 10: Testleri çalıştır, geçtiklerini gör**

Run: `bash dagitim/test-vm.sh tests/test_web_sepet_odeme.py -q`
Expected: PASS (19 passed)

- [ ] **Step 11: Tüm test takımını çalıştır (eksik çeviri anahtarı dahil)**

Run: `bash dagitim/test-vm.sh tests -q`
Expected: PASS — `eksik_anahtarlar` testi dahil hiçbir test kırmızı değil.

- [ ] **Step 12: Commit**

```bash
git add app/web/rotalar/sepet_odeme.py app/web/sablonlar/sepet.html app/web/sablonlar/odeme.html \
  app/web/sablonlar/kart.html app/web/sablonlar/uc_d.html app/web/sablonlar/siparis.html \
  app/web/sablonlar/_tutar_ozeti.html app/web/dil/tr.json app/web/dil/en.json \
  app/web/statik/site.css app/web/statik/site.js tests/test_web_sepet_odeme.py
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m "feat: sepet, odeme, kart, sahte 3D ve siparis onayi ekranlari

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Görev 15: Teklif, geri bildirim ve yönetim paneli

Teklif formu (misafir ve üye, ürün ön seçili), geri bildirim JSON uç noktası, tek yöneticili yönetim paneli (giriş + hız sınırı, pano, siparişler, teklifler, geri bildirimler, durum değiştirme). Entegrasyon kararları K7, K9, K11, K12, K14, K17 uygulanmıştır.

**Files:**
- Create: `app/web/rotalar/teklif_gb.py`, `app/web/rotalar/yonetim.py`
- Create: `app/web/sablonlar/teklif.html`, `app/web/sablonlar/teklif_tamam.html`
- Create: `app/web/sablonlar/yonetim/_menu.html`, `yonetim/giris.html`, `yonetim/pano.html`, `yonetim/siparisler.html`, `yonetim/teklifler.html`, `yonetim/geri_bildirimler.html` (hepsi `app/web/sablonlar/` altında)
- Modify: `app/web/dil/tr.json`, `app/web/dil/en.json`, `app/web/statik/site.css`

(`app/web/uygulama.py` değişmez: `ROTA_SIRASI` `yonetim`'i dil rotalarından önce, `teklif_gb`'yi sonda yükler — K9.)
- Test: `tests/test_web_teklif_yonetim.py`

**Interfaces:**
- Consumes:
  - `app.teklif.servis`: `TeklifGirdisi`, `TeklifHatasi` (`.alan`, `.kod`), `teklif_olustur(con, g, simdi) -> Teklif`, `teklifler(con, musteri_id=None) -> list[Teklif]`, `teklif_durum_degistir(con, teklif_id, yeni) -> Teklif` (izinsiz -> `GecersizGecis`, yok -> `LookupError`), `TEKLIF_GECISLERI`
  - `app.geribildirim.servis`: `DURUMLAR`, `kaydet(con, sayfa, metin, isim, simdi) -> int` (`ValueError`), `listele(con, durum=None) -> list[sqlite3.Row]`, `durum_degistir(con, gb_id, durum)` (yok -> `LookupError`)
  - `app.siparis.servis`: `IZINLI_GECISLER`, `GecersizGecis`, `SiparisDurumu`, `siparis_getir(con, siparis_id, simdi)`, `tum_siparisler(con, simdi)`, `durum_degistir(con, siparis_id, yeni, simdi)` (izinsiz -> `GecersizGecis`, yok -> `LookupError` — K17); testte `siparis_olustur`
  - `app.esitleme.esitle`: `son_basarili_esitleme(con) -> datetime | None`, `son_esitleme(con) -> sqlite3.Row | None`
  - `app.fiyat.kur`: `son_kur`, `kur_bayat_mi`; `app.hesap.servis.parola_dogru`; `app.katalog.depo.urun_getir`
  - `app.web.guvenlik`: `csrf_dogrula`, `aktif_musteri`; `request.app.state.hiz: HizSiniri` (`izin(anahtar, simdi: float) -> bool`), `request.app.state.ayarlar: Ayarlar`
  - `app.web.bagimlilik.db_bagimliligi` (K9); `app.web.baglam.sablon` ve ortak bağlamdaki `t`, `para(tutar, para_birimi)`, `csrf`, `dil` (dil öneksiz yollarda `"tr"`)
  - Dil dönüştürücüsü `{dil:dil}` (Görev 11); i18n (Görev 11): `siparis_durum.<durum>`, `teklif_durum.<durum>`, `form_hata.zorunlu` (K14)
  - Testte `tests.conftest` → `istemci`, `csrf_al`, `urun_ekle` (K7)
  - Görev 14: i18n `odeme.gercek_veri_uyari`, `siparis.hesabim`, `hata_kodu.cok_uzun`, `hata_kodu.ulke_kodu`; CSS sınıfları `.uyari`, `.basari`, `.alan-hata`, `.sepet-tablo`, `.form-alan`, `.gizli-etiket`, `.dugme-ikincil`, `.demo-uyari`
- Produces:
  - `teklif_gb.router`: `GET/POST /{dil}/teklif`, `GET /{dil}/teklif/tamam?no=`, `POST /geri-bildirim` (form: `sayfa`, `metin`, `isim`, `csrf` → `{"tamam": true}` | 400 `{"tamam": false, "hata": "gecersiz"}` | 403)
  - Teklif form alanları: `ad`, `firma`, `eposta`, `telefon`, `ulke`, `urun_id`, `adet`, `mesaj`, `csrf`
  - `yonetim.router` (`prefix="/yonetim"`): `GET/POST /yonetim/giris` (alanlar `kullanici`, `parola`, `csrf`), `POST /yonetim/cikis`, `GET /yonetim`, `GET /yonetim/siparisler`, `POST /yonetim/siparis/{id}/durum` (alan `durum`), `GET /yonetim/teklifler`, `POST /yonetim/teklif/{id}/durum`, `GET /yonetim/geri-bildirimler?durum=`, `POST /yonetim/geri-bildirim/{id}/durum`
  - `yonetim.ESITLEME_UYARI_SURESI = timedelta(hours=36)`
  - i18n: `teklif.*`, `yonetim.*` ve bu görevin hata kodları `hata_kodu.gecersiz`, `hata_kodu.adet_araligi`. `teklif_durum.*`/`siparis_durum.*` burada tanımlanmaz (K14).
  - `data-e2e` öznitelikleri (Görev 18 tablosu): `teklif-gonder`, `teklif-no`, `yonetim-giris`, `son-esitleme`

- [ ] **Step 1: Başarısız testleri yaz**

`tests/test_web_teklif_yonetim.py`:

```python
"""Görev 15 — teklif formu, geri bildirim ve yönetim paneli (TestClient ile)."""
import re
from datetime import UTC, date, datetime, timedelta

import pytest

from app.db import baglan, gecisleri_uygula
from app.fiyat.kur import Kur, kur_kaydet, son_kur
from app.fiyat.kurallar import MusteriTipi, TeslimYontemi
from app.hesap.servis import Adres, KayitGirdisi, kayit_ol
from app.para import d
from app.sepet.servis import ekle, sepet_bul
from app.siparis.servis import siparis_olustur
from tests.conftest import csrf_al, urun_ekle

PAROLA = "demo-parola-123"
YONETICI_PAROLA = "yonetici-parola-123"
MESAJ = "KUKA robot için teslim süresi ve fiyat bilgisi rica ederim."
GB_METNI = "Teklif formunda telefon alanı daha görünür olsun."


@pytest.fixture
def db(istemci):
    con = baglan(istemci.app.state.ayarlar.db_yolu)
    gecisleri_uygula(con)
    yield con
    con.close()


def _musteri(db, tip=MusteriTipi.BIREYSEL, eposta="bireysel@ornek.test", ulke="TR", **ek):
    with db:
        return kayit_ol(db, KayitGirdisi(tip=tip, ad=f"QATestUser {tip.value}", eposta=eposta, parola=PAROLA,
                                         ulke=ulke, kvkk_onay=True, **ek), datetime.now(UTC))


def _giris(istemci, eposta, dil="tr"):
    csrf = csrf_al(istemci, f"/{dil}/giris")
    r = istemci.post(f"/{dil}/giris", data={"eposta": eposta, "parola": PAROLA, "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 303, r.text


def _yonetici_giris(istemci):
    csrf = csrf_al(istemci, "/yonetim/giris")
    r = istemci.post("/yonetim/giris", data={"kullanici": "yonetici", "parola": YONETICI_PAROLA, "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/yonetim", r.text


def _robot(db):
    with db:
        return urun_ekle(db, sku="8301033800019", ad="KUKA KRC5 KR 140 R3200-2 PA", kok="Endüstriyel Robotlar",
                         fiyat="20000.00", teklif=True)


def _teklif_gonder(istemci, dil="tr", **ek):
    form = {"ad": "QATestUser Misafir", "firma": "Deneme Otomasyon Ltd.", "eposta": "misafir@ornek.test",
            "telefon": "", "ulke": "TR", "adet": "1", "mesaj": MESAJ}
    form.update(ek)
    form["csrf"] = csrf_al(istemci, f"/{dil}/teklif")
    return istemci.post(f"/{dil}/teklif", data=form, follow_redirects=False)


def _gb_gonder(istemci, metin=GB_METNI, csrf=True):
    veri = {"sayfa": "/tr/teklif", "metin": metin, "isim": "QATestUser"}
    if csrf:
        veri["csrf"] = csrf_al(istemci, "/tr/teklif")
    else:
        istemci.get("/tr/teklif")
    return istemci.post("/geri-bildirim", data=veri)


def _siparis(db):
    simdi = datetime.now(UTC)
    with db:
        m = kayit_ol(db, KayitGirdisi(tip=MusteriTipi.BIREYSEL, ad="QATestUser Yönetim", eposta="yonetim-test@ornek.test",
                                      parola=PAROLA, ulke="TR", kvkk_onay=True), simdi)
        uid = urun_ekle(db, sku="Y-1", ad="Yönetim Test Ürünü", fiyat="100.00")
        kur_kaydet(db, Kur(tarih=date(2026, 10, 12), eur_alis=d("34.9000"), eur_satis=d("35.0000")), simdi)
        sepet_id = sepet_bul(db, None, m.id, simdi)
        ekle(db, sepet_id, uid, 1)
        adres = Adres(ad_soyad="QATestUser Alıcı", satir1="Test Mah. Deneme Sk. No: 1", sehir="Konya", ulke="TR")
        return siparis_olustur(db, m, sepet_id, TeslimYontemi.KARGO, adres, adres, son_kur(db), simdi)


def _esitleme_kaydi(db, saat_once, durum="tam"):
    bitis = datetime.now(UTC) - timedelta(hours=saat_once)
    with db:
        db.execute("INSERT INTO esitleme_gunlugu (basla, bitis, durum, api_toplam, cekilen, eklenen, guncellenen, "
                   "pasiflenen) VALUES (?, ?, ?, 4449, 4449, 0, 4449, 0)",
                   ((bitis - timedelta(minutes=5)).isoformat(), bitis.isoformat(), durum))


def _say(db, sql, *p):
    return db.execute(sql, p).fetchone()[0]


# ---------- teklif ----------

def test_teklif_formu_urun_on_secili_misafir(istemci, db):
    uid = _robot(db)
    sayfa = istemci.get(f"/tr/teklif?urun_id={uid}")
    assert sayfa.status_code == 200
    assert f'name="urun_id" value="{uid}"' in sayfa.text
    assert "KUKA KRC5 KR 140 R3200-2 PA" in sayfa.text
    assert 'data-e2e="teklif-gonder"' in sayfa.text

    r = _teklif_gonder(istemci, urun_id=str(uid))
    assert r.status_code == 303
    assert re.fullmatch(r"/tr/teklif/tamam\?no=CR-TKL-\d{8}-\d{4}", r.headers["location"])
    no = r.headers["location"].split("no=")[1]
    tamam = istemci.get(r.headers["location"])
    assert tamam.status_code == 200
    assert re.search(rf'data-e2e="teklif-no"[^>]*>{no}<', tamam.text)
    satir = db.execute("SELECT * FROM teklif WHERE no = ?", (no,)).fetchone()
    assert satir["urun_id"] == uid
    assert satir["musteri_id"] is None
    assert satir["durum"] == "yeni"


def test_teklif_bozuk_urun_id_yok_sayilir(istemci):
    assert istemci.get("/tr/teklif?urun_id=abc").status_code == 200
    r = istemci.get("/tr/teklif?urun_id=999999")
    assert r.status_code == 200
    assert 'name="urun_id" value="999999"' not in r.text


def test_teklif_uye_otomatik_doldurma(istemci, db):
    m = _musteri(db, tip=MusteriTipi.KURUMSAL, eposta="kurumsal@ornek.test",
                 vergi_kimlik_no="1234567890", vergi_dairesi="Selçuk")
    _giris(istemci, "kurumsal@ornek.test")
    sayfa = istemci.get("/tr/teklif")
    assert 'value="QATestUser kurumsal"' in sayfa.text
    assert 'value="kurumsal@ornek.test"' in sayfa.text
    r = _teklif_gonder(istemci, ad="QATestUser kurumsal", eposta="kurumsal@ornek.test")
    assert r.status_code == 303
    assert _say(db, "SELECT musteri_id FROM teklif") == m.id


def test_teklif_hatali_form_alan_hatasi(istemci, db):
    r = _teklif_gonder(istemci, ad="")
    assert r.status_code == 400
    assert 'id="hata-ad"' in r.text
    assert MESAJ in r.text                       # girilen veri korunur
    r = _teklif_gonder(istemci, adet="abc")
    assert r.status_code == 400 and 'id="hata-adet"' in r.text
    r = _teklif_gonder(istemci, ulke="Türkiye")
    assert r.status_code == 400 and 'id="hata-ulke"' in r.text
    assert _say(db, "SELECT COUNT(*) FROM teklif") == 0


def test_teklif_yonetimde_gorunur_ve_durum_degisir(istemci, db):
    assert _teklif_gonder(istemci).status_code == 303
    tid, no = db.execute("SELECT id, no FROM teklif").fetchone()
    _yonetici_giris(istemci)
    liste = istemci.get("/yonetim/teklifler")
    assert liste.status_code == 200
    assert no in liste.text and "QATestUser Misafir" in liste.text

    csrf = csrf_al(istemci, "/yonetim/teklifler")
    r = istemci.post(f"/yonetim/teklif/{tid}/durum", data={"durum": "inceleniyor", "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 303
    assert _say(db, "SELECT durum FROM teklif WHERE id = ?", tid) == "inceleniyor"

    r = istemci.post(f"/yonetim/teklif/{tid}/durum", data={"durum": "yeni", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 409
    assert "izin verilmiyor" in r.text
    assert _say(db, "SELECT durum FROM teklif WHERE id = ?", tid) == "inceleniyor"

    r = istemci.post(f"/yonetim/teklif/{tid}/durum", data={"durum": "uctu", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 400


# ---------- geri bildirim ----------

def test_geri_bildirim_json_tamam(istemci, db):
    r = _gb_gonder(istemci)
    assert r.status_code == 200
    assert r.json() == {"tamam": True}
    satir = db.execute("SELECT sayfa, metin, isim, durum FROM geri_bildirim").fetchone()
    assert tuple(satir) == ("/tr/teklif", GB_METNI, "QATestUser", "yeni")


def test_geri_bildirim_csrf_yok_403(istemci, db):
    r = _gb_gonder(istemci, csrf=False)
    assert r.status_code == 403
    assert _say(db, "SELECT COUNT(*) FROM geri_bildirim") == 0


def test_geri_bildirim_bos_metin_400(istemci, db):
    r = _gb_gonder(istemci, metin="   ")
    assert r.status_code == 400
    assert r.json()["tamam"] is False
    assert _say(db, "SELECT COUNT(*) FROM geri_bildirim") == 0


def test_geri_bildirim_yonetimde_gorunur_ve_durum_degisir(istemci, db):
    assert _gb_gonder(istemci).status_code == 200
    gid = _say(db, "SELECT id FROM geri_bildirim")
    _yonetici_giris(istemci)
    sayfa = istemci.get("/yonetim/geri-bildirimler")
    assert sayfa.status_code == 200 and GB_METNI in sayfa.text

    csrf = csrf_al(istemci, "/yonetim/geri-bildirimler")
    r = istemci.post(f"/yonetim/geri-bildirim/{gid}/durum", data={"durum": "okundu", "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 303
    assert _say(db, "SELECT durum FROM geri_bildirim WHERE id = ?", gid) == "okundu"
    assert GB_METNI not in istemci.get("/yonetim/geri-bildirimler?durum=yeni").text
    assert GB_METNI in istemci.get("/yonetim/geri-bildirimler?durum=okundu").text

    r = istemci.post(f"/yonetim/geri-bildirim/{gid}/durum", data={"durum": "sil", "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 400
    r = istemci.post("/yonetim/geri-bildirim/999999/durum", data={"durum": "okundu", "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 404


# ---------- yönetim girişi ----------

@pytest.mark.parametrize("yol", ["/yonetim", "/yonetim/siparisler", "/yonetim/teklifler", "/yonetim/geri-bildirimler"])
def test_yonetim_girissiz_yonlendirir(istemci, yol):
    r = istemci.get(yol, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/yonetim/giris"


def test_yonetim_girissiz_post_yonlendirir(istemci):
    csrf = csrf_al(istemci, "/yonetim/giris")
    r = istemci.post("/yonetim/siparis/1/durum", data={"durum": "odendi", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/yonetim/giris"


def test_yonetim_yanlis_parola(istemci):
    giris = istemci.get("/yonetim/giris")
    assert 'name="kullanici"' in giris.text and 'name="parola"' in giris.text
    assert 'data-e2e="yonetim-giris"' in giris.text
    csrf = csrf_al(istemci, "/yonetim/giris")
    r = istemci.post("/yonetim/giris", data={"kullanici": "yonetici", "parola": "yanlis-parola", "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 401
    assert "hatalı" in r.text
    r = istemci.post("/yonetim/giris", data={"kullanici": "baska", "parola": YONETICI_PAROLA, "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 401
    assert istemci.get("/yonetim", follow_redirects=False).status_code == 303


def test_yonetim_11_deneme_429(istemci):
    csrf = csrf_al(istemci, "/yonetim/giris")
    for _ in range(10):
        r = istemci.post("/yonetim/giris", data={"kullanici": "yonetici", "parola": "yanlis", "csrf": csrf},
                         follow_redirects=False)
        assert r.status_code == 401
    r = istemci.post("/yonetim/giris", data={"kullanici": "yonetici", "parola": YONETICI_PAROLA, "csrf": csrf},
                     follow_redirects=False)
    assert r.status_code == 429
    assert "Çok fazla deneme" in r.text
    assert istemci.get("/yonetim", follow_redirects=False).status_code == 303


def test_yonetim_cikis(istemci):
    _yonetici_giris(istemci)
    assert istemci.get("/yonetim").status_code == 200
    csrf = csrf_al(istemci, "/yonetim")
    r = istemci.post("/yonetim/cikis", data={"csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303
    assert istemci.get("/yonetim", follow_redirects=False).status_code == 303


# ---------- sipariş durumu ----------

def test_siparis_durum_izinli_ve_izinsiz(istemci, db):
    s = _siparis(db)
    _yonetici_giris(istemci)
    liste = istemci.get("/yonetim/siparisler")
    assert liste.status_code == 200 and s.no in liste.text

    csrf = csrf_al(istemci, "/yonetim/siparisler")
    r = istemci.post(f"/yonetim/siparis/{s.id}/durum", data={"durum": "odendi", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/yonetim/siparisler"
    assert _say(db, "SELECT durum FROM siparis WHERE id = ?", s.id) == "odendi"

    r = istemci.post(f"/yonetim/siparis/{s.id}/durum", data={"durum": "teslim", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 409
    assert "izin verilmiyor" in r.text
    assert _say(db, "SELECT durum FROM siparis WHERE id = ?", s.id) == "odendi"

    r = istemci.post(f"/yonetim/siparis/{s.id}/durum", data={"durum": "uctu", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 400
    r = istemci.post("/yonetim/siparis/999999/durum", data={"durum": "odendi", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 404


# ---------- pano ----------

def test_pano_esitleme_uyarisi_36_saat(istemci, db):
    _esitleme_kaydi(db, 40, "tam")
    _esitleme_kaydi(db, 1, "eksik")          # sonraki eksik tur uyarıyı kaldırmaz
    _yonetici_giris(istemci)
    pano = istemci.get("/yonetim")
    assert pano.status_code == 200
    assert "uyari-esitleme" in pano.text
    assert "36 saatten eski" in pano.text
    assert 'data-e2e="son-esitleme"' in pano.text
    assert (datetime.now(UTC) - timedelta(hours=40)).strftime("%d.%m.%Y") in pano.text
    assert "Eksik" in pano.text


def test_pano_taze_esitlemede_uyari_yok(istemci, db):
    _esitleme_kaydi(db, 2, "tam")
    with db:
        kur_kaydet(db, Kur(tarih=date(2026, 10, 12), eur_alis=d("34.9000"), eur_satis=d("35.0000")),
                   datetime.now(UTC))
    _yonetici_giris(istemci)
    pano = istemci.get("/yonetim")
    assert "uyari-esitleme" not in pano.text
    assert "35.0000" in pano.text and "12.10.2026" in pano.text


def test_pano_hic_esitleme_yoksa_uyari(istemci):
    _yonetici_giris(istemci)
    pano = istemci.get("/yonetim")
    assert "uyari-esitleme" in pano.text
    assert "henüz başarılı" in pano.text
    assert "Kayıtlı kur yok" in pano.text
```

- [ ] **Step 2: Testleri çalıştır, başarısız olduklarını gör**

Run: `bash dagitim/test-vm.sh tests/test_web_teklif_yonetim.py -q`
Expected: FAIL — `/tr/teklif`, `/geri-bildirim` ve `/yonetim/...` rotaları henüz yok (404).

- [ ] **Step 3: i18n anahtarlarını iki dile birlikte ekle**

`app/web/dil/tr.json` nesnesine ekle (`teklif_durum.*`, `siparis_durum.*`, `form_hata.zorunlu` Görev 11'indir — K14):

```json
  "teklif.baslik": "Teklif iste",
  "teklif.aciklama": "Robotlar, pozisyonerler ve 15.000 € (KDV hariç) üzerindeki ürünler için fiyat teklifi hazırlıyoruz. Formu doldurun, satış ekibimiz size dönsün.",
  "teklif.urun": "Ürün",
  "teklif.ad": "Ad soyad",
  "teklif.firma": "Firma",
  "teklif.eposta": "E-posta",
  "teklif.telefon": "Telefon",
  "teklif.ulke": "Ülke kodu (ör. TR, DE)",
  "teklif.adet": "Adet",
  "teklif.mesaj": "Mesajınız",
  "teklif.gonder": "Teklif isteğini gönder",
  "teklif.tamam_baslik": "Teklif isteğiniz alındı",
  "teklif.tamam_metin": "Talep numaranız: {no}. Satış ekibimiz en kısa sürede sizinle iletişime geçecek.",
  "teklif.tamam_numarasiz": "Talebiniz kaydedildi.",
  "teklif.ana_sayfa": "Ana sayfaya dön",
  "hata_kodu.gecersiz": "Geçersiz değer.",
  "hata_kodu.adet_araligi": "1 ile 9999 arasında bir adet girin.",
  "yonetim.baslik": "Yönetim paneli",
  "yonetim.giris_baslik": "Yönetim girişi",
  "yonetim.kullanici": "Kullanıcı adı",
  "yonetim.parola": "Parola",
  "yonetim.giris": "Giriş yap",
  "yonetim.cikis": "Çıkış",
  "yonetim.hatali_giris": "Kullanıcı adı veya parola hatalı.",
  "yonetim.cok_deneme": "Çok fazla deneme yapıldı. Bir dakika sonra yeniden deneyin.",
  "yonetim.menu.pano": "Özet",
  "yonetim.menu.siparisler": "Siparişler",
  "yonetim.menu.teklifler": "Teklifler",
  "yonetim.menu.geri_bildirimler": "Geri bildirimler",
  "yonetim.esitleme": "Katalog eşitleme",
  "yonetim.son_tam_esitleme": "Son başarılı (tam) eşitleme",
  "yonetim.son_esitleme": "Son çalışma",
  "yonetim.esitleme_durum.tam": "Tam",
  "yonetim.esitleme_durum.eksik": "Eksik",
  "yonetim.esitleme_durum.hata": "Hata",
  "yonetim.esitleme_durum.calisiyor": "Çalışıyor",
  "yonetim.esitleme_uyari": "Uyarı: son başarılı katalog eşitlemesi 36 saatten eski. Eşitleme günlüğünü ve zamanlayıcıyı kontrol edin.",
  "yonetim.esitleme_yok": "Uyarı: henüz başarılı (tam) bir katalog eşitlemesi yok.",
  "yonetim.esitleme_sayilar": "API toplamı {api}, çekilen {cekilen}, eklenen {eklenen}, güncellenen {guncellenen}, pasiflenen {pasiflenen}, atlanan bozuk kayıt {bozuk}",
  "yonetim.hata_metni": "Hata: {hata}",
  "yonetim.kur": "Döviz kuru",
  "yonetim.kur_degeri": "EUR satış {satis} ₺, alış {alis} ₺ — {tarih}",
  "yonetim.kur_bayat": "Kur 3 günden eski; kur zamanlayıcısını kontrol edin.",
  "yonetim.kur_yok": "Kayıtlı kur yok.",
  "yonetim.sayilar": "Sayılar",
  "yonetim.sayi.urun": "Aktif ürün",
  "yonetim.sayi.siparis": "Sipariş",
  "yonetim.sayi.odeme_bekleyen": "Ödeme bekleyen sipariş",
  "yonetim.sayi.teklif_yeni": "Yeni teklif isteği",
  "yonetim.sayi.gb_yeni": "Yeni geri bildirim",
  "yonetim.no": "No",
  "yonetim.musteri": "Müşteri",
  "yonetim.tarih": "Tarih",
  "yonetim.tutar": "Tutar",
  "yonetim.durum": "Durum",
  "yonetim.islem": "İşlem",
  "yonetim.degistir": "Değiştir",
  "yonetim.gecis_yok": "Son durum",
  "yonetim.liste_bos": "Kayıt yok.",
  "yonetim.gecis_izinsiz": "{no}: bu durum geçişine izin verilmiyor ({eski} → {yeni}). Durum değişmedi.",
  "yonetim.urun": "Ürün",
  "yonetim.iletisim": "İletişim",
  "yonetim.mesaj": "Mesaj",
  "yonetim.sayfa": "Sayfa",
  "yonetim.metin": "Metin",
  "yonetim.isim": "İsim",
  "yonetim.filtre": "Süz",
  "yonetim.filtre_tumu": "Tümü",
  "yonetim.gb_durum.yeni": "Yeni",
  "yonetim.gb_durum.okundu": "Okundu",
  "yonetim.gb_durum.yapildi": "Yapıldı"
```

`app/web/dil/en.json` nesnesine ekle:

```json
  "teklif.baslik": "Request a quote",
  "teklif.aciklama": "We prepare quotations for robots, positioners and items above €15,000 (excl. VAT). Fill in the form and our sales team will get back to you.",
  "teklif.urun": "Product",
  "teklif.ad": "Full name",
  "teklif.firma": "Company",
  "teklif.eposta": "E-mail",
  "teklif.telefon": "Phone",
  "teklif.ulke": "Country code (e.g. TR, DE)",
  "teklif.adet": "Quantity",
  "teklif.mesaj": "Your message",
  "teklif.gonder": "Send quote request",
  "teklif.tamam_baslik": "Your quote request has been received",
  "teklif.tamam_metin": "Your reference number is {no}. Our sales team will contact you shortly.",
  "teklif.tamam_numarasiz": "Your request has been recorded.",
  "teklif.ana_sayfa": "Back to home",
  "hata_kodu.gecersiz": "Invalid value.",
  "hata_kodu.adet_araligi": "Enter a quantity between 1 and 9999.",
  "yonetim.baslik": "Admin panel",
  "yonetim.giris_baslik": "Admin sign-in",
  "yonetim.kullanici": "Username",
  "yonetim.parola": "Password",
  "yonetim.giris": "Sign in",
  "yonetim.cikis": "Sign out",
  "yonetim.hatali_giris": "Wrong username or password.",
  "yonetim.cok_deneme": "Too many attempts. Try again in a minute.",
  "yonetim.menu.pano": "Overview",
  "yonetim.menu.siparisler": "Orders",
  "yonetim.menu.teklifler": "Quotes",
  "yonetim.menu.geri_bildirimler": "Feedback",
  "yonetim.esitleme": "Catalogue sync",
  "yonetim.son_tam_esitleme": "Last successful (full) sync",
  "yonetim.son_esitleme": "Last run",
  "yonetim.esitleme_durum.tam": "Complete",
  "yonetim.esitleme_durum.eksik": "Partial",
  "yonetim.esitleme_durum.hata": "Error",
  "yonetim.esitleme_durum.calisiyor": "Running",
  "yonetim.esitleme_uyari": "Warning: the last successful catalogue sync is older than 36 hours. Check the sync log and the timer.",
  "yonetim.esitleme_yok": "Warning: there has been no successful (full) catalogue sync yet.",
  "yonetim.esitleme_sayilar": "API total {api}, fetched {cekilen}, added {eklenen}, updated {guncellenen}, deactivated {pasiflenen}, skipped malformed {bozuk}",
  "yonetim.hata_metni": "Error: {hata}",
  "yonetim.kur": "Exchange rate",
  "yonetim.kur_degeri": "EUR selling ₺{satis}, buying ₺{alis} — {tarih}",
  "yonetim.kur_bayat": "Rate is older than 3 days; check the rate timer.",
  "yonetim.kur_yok": "No exchange rate stored.",
  "yonetim.sayilar": "Counts",
  "yonetim.sayi.urun": "Active products",
  "yonetim.sayi.siparis": "Orders",
  "yonetim.sayi.odeme_bekleyen": "Orders awaiting payment",
  "yonetim.sayi.teklif_yeni": "New quote requests",
  "yonetim.sayi.gb_yeni": "New feedback",
  "yonetim.no": "No.",
  "yonetim.musteri": "Customer",
  "yonetim.tarih": "Date",
  "yonetim.tutar": "Amount",
  "yonetim.durum": "Status",
  "yonetim.islem": "Action",
  "yonetim.degistir": "Change",
  "yonetim.gecis_yok": "Final status",
  "yonetim.liste_bos": "No records.",
  "yonetim.gecis_izinsiz": "{no}: this status change is not allowed ({eski} → {yeni}). Status unchanged.",
  "yonetim.urun": "Product",
  "yonetim.iletisim": "Contact",
  "yonetim.mesaj": "Message",
  "yonetim.sayfa": "Page",
  "yonetim.metin": "Text",
  "yonetim.isim": "Name",
  "yonetim.filtre": "Filter",
  "yonetim.filtre_tumu": "All",
  "yonetim.gb_durum.yeni": "New",
  "yonetim.gb_durum.okundu": "Read",
  "yonetim.gb_durum.yapildi": "Done"
```

JSON geçerliliği: `python -m json.tool app/web/dil/tr.json > /dev/null && python -m json.tool app/web/dil/en.json > /dev/null` — çıkış kodu 0.

- [ ] **Step 4: Teklif ve geri bildirim rotalarını yaz**

`app/web/rotalar/teklif_gb.py`:

```python
"""Teklif formu ve geri bildirim uç noktası (Görev 15)."""
from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.fiyat.kurallar import MusteriTipi
from app.geribildirim import servis as gb_servis
from app.katalog.depo import Urun, urun_getir
from app.teklif.servis import TeklifGirdisi, TeklifHatasi, teklif_olustur
from app.web.bagimlilik import db_bagimliligi
from app.web.baglam import sablon
from app.web.guvenlik import aktif_musteri, csrf_dogrula

router = APIRouter()

TEKLIF_ALANLARI = ("ad", "firma", "eposta", "telefon", "ulke", "urun_id", "adet", "mesaj")
AZAMI_UZUNLUK = {"ad": 200, "firma": 200, "eposta": 200, "telefon": 50}
ULKE_DESENI = re.compile(r"[A-Z]{2}")
TEKLIF_NO_DESENI = re.compile(r"CR-TKL-\d{8}-\d{4}")
ADET_AZAMI = 9999


def _simdi() -> datetime:
    return datetime.now(UTC)


def _hata_anahtari(kod: str) -> str:
    """K14: servis hata kodu -> i18n anahtarı."""
    return "form_hata.zorunlu" if kod == "zorunlu" else f"hata_kodu.{kod}"


def _tamsayi(deger: object) -> int | None:
    try:
        return int(str(deger).strip())
    except (TypeError, ValueError):
        return None


def _urun(con: sqlite3.Connection, deger: object) -> Urun | None:
    urun_id = _tamsayi(deger)
    if urun_id is None:
        return None
    urun = urun_getir(con, urun_id)
    return urun if urun is not None and urun.aktif else None


def _teklif_sayfasi(request: Request, alanlar: dict[str, str], urun: Urun | None,
                    hatalar: dict[str, str], durum: int = 200) -> Response:
    return sablon(request, "teklif.html", {"alanlar": alanlar, "urun": urun, "hatalar": hatalar}, durum)


@router.get("/{dil:dil}/teklif")
def teklif_formu(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    musteri = aktif_musteri(request, con)
    alanlar = {ad: "" for ad in TEKLIF_ALANLARI}
    alanlar["adet"] = "1"
    if musteri is not None:
        alanlar.update(ad=musteri.ad, eposta=musteri.eposta, ulke=musteri.ulke,
                       firma=musteri.ad if musteri.tip == MusteriTipi.KURUMSAL else "")
    else:
        alanlar["ulke"] = str(request.session.get("ulke", "TR"))
    urun = _urun(con, request.query_params.get("urun_id"))
    if urun is not None:
        alanlar["urun_id"] = str(urun.id)
    return _teklif_sayfasi(request, alanlar, urun, {})


@router.post("/{dil:dil}/teklif")
async def teklif_gonder(dil: str, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    await csrf_dogrula(request)
    musteri = aktif_musteri(request, con)
    form = await request.form()
    alanlar = {ad: str(form.get(ad, "")).strip() for ad in TEKLIF_ALANLARI}
    alanlar["ulke"] = alanlar["ulke"].upper()
    urun = _urun(con, alanlar["urun_id"])
    alanlar["urun_id"] = str(urun.id) if urun is not None else ""

    hatalar: dict[str, str] = {}
    for ad, sinir in AZAMI_UZUNLUK.items():
        if len(alanlar[ad]) > sinir:
            hatalar[ad] = "hata_kodu.cok_uzun"
    adet = _tamsayi(alanlar["adet"] or "1")
    if adet is None or not 1 <= adet <= ADET_AZAMI:
        hatalar["adet"] = "hata_kodu.adet_araligi"
    if not ULKE_DESENI.fullmatch(alanlar["ulke"]):
        hatalar["ulke"] = "hata_kodu.ulke_kodu"
    if hatalar:
        return _teklif_sayfasi(request, alanlar, urun, hatalar, 400)

    girdi = TeklifGirdisi(ad=alanlar["ad"], eposta=alanlar["eposta"], ulke=alanlar["ulke"], mesaj=alanlar["mesaj"],
                          firma=alanlar["firma"] or None, telefon=alanlar["telefon"] or None,
                          urun_id=urun.id if urun is not None else None, adet=adet,
                          musteri_id=musteri.id if musteri is not None else None)
    try:
        with con:
            teklif = teklif_olustur(con, girdi, _simdi())
    except TeklifHatasi as hata:
        return _teklif_sayfasi(request, alanlar, urun, {hata.alan: _hata_anahtari(hata.kod)}, 400)
    return RedirectResponse(f"/{dil}/teklif/tamam?no={quote(teklif.no)}", status_code=303)


@router.get("/{dil:dil}/teklif/tamam")
def teklif_tamam(dil: str, request: Request) -> Response:
    no = request.query_params.get("no", "")
    return sablon(request, "teklif_tamam.html", {"no": no if TEKLIF_NO_DESENI.fullmatch(no) else None})


@router.post("/geri-bildirim")
async def geri_bildirim(request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    await csrf_dogrula(request)
    form = await request.form()
    metin = str(form.get("metin", "")).strip()
    sayfa = str(form.get("sayfa", "")).strip()[:500] or "/"
    isim = str(form.get("isim", "")).strip()[:100] or None
    try:
        with con:
            gb_servis.kaydet(con, sayfa, metin, isim, _simdi())
    except ValueError:
        return JSONResponse({"tamam": False, "hata": "gecersiz"}, status_code=400)
    return JSONResponse({"tamam": True})
```

- [ ] **Step 5: Yönetim rotalarını yaz**

`app/web/rotalar/yonetim.py`:

```python
"""Yönetim paneli (Görev 15): giriş, pano, siparişler, teklifler, geri bildirimler."""
from __future__ import annotations

import secrets
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.esitleme.esitle import son_basarili_esitleme, son_esitleme
from app.fiyat.kur import kur_bayat_mi, son_kur
from app.geribildirim import servis as gb_servis
from app.hesap.servis import parola_dogru
from app.siparis.servis import (IZINLI_GECISLER, GecersizGecis, SiparisDurumu, durum_degistir,
                                siparis_getir, tum_siparisler)
from app.teklif.servis import TEKLIF_GECISLERI, teklif_durum_degistir, teklifler
from app.web.bagimlilik import db_bagimliligi
from app.web.baglam import sablon
from app.web.guvenlik import csrf_dogrula

router = APIRouter(prefix="/yonetim")

GIRIS_YOLU = "/yonetim/giris"
ESITLEME_UYARI_SURESI = timedelta(hours=36)
SAYI_SORGULARI = {
    "urun": "SELECT COUNT(*) FROM urun WHERE aktif = 1",
    "siparis": "SELECT COUNT(*) FROM siparis",
    "odeme_bekleyen": "SELECT COUNT(*) FROM siparis WHERE durum = 'odeme_bekliyor'",
    "teklif_yeni": "SELECT COUNT(*) FROM teklif WHERE durum = 'yeni'",
    "gb_yeni": "SELECT COUNT(*) FROM geri_bildirim WHERE durum = 'yeni'",
}


def _simdi() -> datetime:
    return datetime.now(UTC)


def _yetkisiz(request: Request) -> RedirectResponse | None:
    if request.session.get("yonetici") is True:
        return None
    return RedirectResponse(GIRIS_YOLU, status_code=303)


# ---------- giriş / çıkış ----------

@router.get("/giris")
def giris_formu(request: Request) -> Response:
    if request.session.get("yonetici") is True:
        return RedirectResponse("/yonetim", status_code=303)
    return sablon(request, "yonetim/giris.html", {"hata": None, "kullanici": ""})


@router.post("/giris")
async def giris_gonder(request: Request) -> Response:
    await csrf_dogrula(request)
    ip = request.client.host if request.client else "bilinmiyor"
    if not request.app.state.hiz.izin(f"yonetim:{ip}", time.monotonic()):
        return sablon(request, "yonetim/giris.html", {"hata": "yonetim.cok_deneme", "kullanici": ""}, 429)
    form = await request.form()
    kullanici = str(form.get("kullanici", "")).strip()
    parola = str(form.get("parola", ""))
    ayarlar = request.app.state.ayarlar
    ad_dogru = secrets.compare_digest(kullanici.encode(), ayarlar.yonetici_kullanici.encode())
    parola_tamam = parola_dogru(parola, ayarlar.yonetici_parola_ozeti)
    if not (ad_dogru and parola_tamam):
        return sablon(request, "yonetim/giris.html", {"hata": "yonetim.hatali_giris", "kullanici": kullanici}, 401)
    request.session["yonetici"] = True
    return RedirectResponse("/yonetim", status_code=303)


@router.post("/cikis")
async def cikis(request: Request) -> Response:
    await csrf_dogrula(request)
    request.session.pop("yonetici", None)
    return RedirectResponse(GIRIS_YOLU, status_code=303)


# ---------- pano ----------

@router.get("")
def pano(request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    if (yonlendir := _yetkisiz(request)) is not None:
        return yonlendir
    simdi = _simdi()
    son_tam = son_basarili_esitleme(con)
    if son_tam is not None and son_tam.tzinfo is None:
        son_tam = son_tam.replace(tzinfo=UTC)
    kur = son_kur(con)
    return sablon(request, "yonetim/pano.html", {
        "son": son_esitleme(con), "son_tam": son_tam,
        "esitleme_uyari": son_tam is None or simdi - son_tam > ESITLEME_UYARI_SURESI,
        "kur": kur, "kur_bayat": kur is not None and kur_bayat_mi(kur, simdi.date()),
        "sayilar": {ad: con.execute(sql).fetchone()[0] for ad, sql in SAYI_SORGULARI.items()},
    })


# ---------- siparişler ----------

def _siparisler_sayfasi(request: Request, con: sqlite3.Connection, hata: dict | None = None,
                        durum: int = 200) -> Response:
    with con:  # tum_siparisler zaman aşımını uygular (yazabilir)
        liste = tum_siparisler(con, _simdi())
    return sablon(request, "yonetim/siparisler.html", {
        "siparisler": liste, "gecisler": {s.id: sorted(IZINLI_GECISLER[s.durum]) for s in liste},
        "hata": hata,
    }, durum)


@router.get("/siparisler")
def siparisler(request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    if (yonlendir := _yetkisiz(request)) is not None:
        return yonlendir
    return _siparisler_sayfasi(request, con)


@router.post("/siparis/{siparis_id}/durum")
async def siparis_durum(siparis_id: int, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    if (yonlendir := _yetkisiz(request)) is not None:
        return yonlendir
    await csrf_dogrula(request)
    form = await request.form()
    try:
        yeni = SiparisDurumu(str(form.get("durum", "")))
    except ValueError:
        raise HTTPException(status_code=400) from None
    try:
        with con:
            durum_degistir(con, siparis_id, yeni, _simdi())
    except LookupError:                                   # K17
        raise HTTPException(status_code=404) from None
    except GecersizGecis:
        with con:
            mevcut = siparis_getir(con, siparis_id, _simdi())
        hata = {"no": mevcut.no, "eski": mevcut.durum.value, "yeni": yeni.value}
        return _siparisler_sayfasi(request, con, hata=hata, durum=409)
    return RedirectResponse("/yonetim/siparisler", status_code=303)


# ---------- teklifler ----------

def _teklifler_sayfasi(request: Request, con: sqlite3.Connection, hata: dict | None = None,
                       durum: int = 200) -> Response:
    liste = teklifler(con)
    return sablon(request, "yonetim/teklifler.html", {
        "teklifler": liste, "gecisler": {tk.id: sorted(TEKLIF_GECISLERI[tk.durum]) for tk in liste},
        "hata": hata,
    }, durum)


@router.get("/teklifler")
def teklif_listesi(request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    if (yonlendir := _yetkisiz(request)) is not None:
        return yonlendir
    return _teklifler_sayfasi(request, con)


@router.post("/teklif/{teklif_id}/durum")
async def teklif_durum(teklif_id: int, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    if (yonlendir := _yetkisiz(request)) is not None:
        return yonlendir
    await csrf_dogrula(request)
    form = await request.form()
    yeni = str(form.get("durum", ""))
    if yeni not in TEKLIF_GECISLERI:
        raise HTTPException(status_code=400)
    try:
        with con:
            teklif_durum_degistir(con, teklif_id, yeni)
    except LookupError:                                   # K17
        raise HTTPException(status_code=404) from None
    except GecersizGecis:
        mevcut = next(tk for tk in teklifler(con) if tk.id == teklif_id)
        hata = {"no": mevcut.no, "eski": mevcut.durum, "yeni": yeni}
        return _teklifler_sayfasi(request, con, hata=hata, durum=409)
    return RedirectResponse("/yonetim/teklifler", status_code=303)


# ---------- geri bildirimler ----------

@router.get("/geri-bildirimler")
def geri_bildirimler(request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    if (yonlendir := _yetkisiz(request)) is not None:
        return yonlendir
    filtre = request.query_params.get("durum")
    if filtre not in gb_servis.DURUMLAR:
        filtre = None
    return sablon(request, "yonetim/geri_bildirimler.html", {
        "kayitlar": gb_servis.listele(con, filtre), "filtre": filtre, "durumlar": gb_servis.DURUMLAR,
    })


@router.post("/geri-bildirim/{gb_id}/durum")
async def geri_bildirim_durum(gb_id: int, request: Request, con: sqlite3.Connection = Depends(db_bagimliligi)) -> Response:
    if (yonlendir := _yetkisiz(request)) is not None:
        return yonlendir
    await csrf_dogrula(request)
    form = await request.form()
    yeni = str(form.get("durum", ""))
    if yeni not in gb_servis.DURUMLAR:
        raise HTTPException(status_code=400)
    try:
        with con:
            gb_servis.durum_degistir(con, gb_id, yeni)
    except LookupError:                                   # K17
        raise HTTPException(status_code=404) from None
    return RedirectResponse("/yonetim/geri-bildirimler", status_code=303)
```

- [ ] **Step 6: Teklif şablonlarını yaz**

`app/web/sablonlar/teklif.html`:

```html
{% extends "taban.html" %}
{% block baslik %}{{ t('teklif.baslik') }}{% endblock %}
{% block icerik %}
{% macro alan(ad, etiket, tip="text", zorunlu=False, ek="") %}
<p class="form-alan">
  <label for="{{ ad }}">{{ t(etiket) }}{% if zorunlu %} *{% endif %}</label>
  <input id="{{ ad }}" name="{{ ad }}" type="{{ tip }}" value="{{ alanlar[ad] }}"{% if zorunlu %} required{% endif %}{% if ek %} {{ ek|safe }}{% endif %}{% if hatalar.get(ad) %} aria-invalid="true" aria-describedby="hata-{{ ad }}"{% endif %}>
  {% if hatalar.get(ad) %}<span class="alan-hata" id="hata-{{ ad }}">{{ t(hatalar[ad]) }}</span>{% endif %}
</p>
{% endmacro %}
<section class="teklif">
  <h1>{{ t('teklif.baslik') }}</h1>
  <p>{{ t('teklif.aciklama') }}</p>
  <p class="demo-uyari" role="note">{{ t('odeme.gercek_veri_uyari') }}</p>
  <form method="post" action="/{{ dil }}/teklif" novalidate>
    <input type="hidden" name="csrf" value="{{ csrf }}">
    {% if urun %}
    <input type="hidden" name="urun_id" value="{{ urun.id }}">
    <p class="teklif-urun"><strong>{{ t('teklif.urun') }}:</strong> <a href="/{{ dil }}/urun/{{ urun.id }}">{{ urun.ad }}</a> <small>({{ urun.sku }})</small></p>
    {% endif %}
    {{ alan('ad', 'teklif.ad', zorunlu=True, ek='maxlength="200" autocomplete="name"') }}
    {{ alan('firma', 'teklif.firma', ek='maxlength="200" autocomplete="organization"') }}
    {{ alan('eposta', 'teklif.eposta', tip='email', zorunlu=True, ek='maxlength="200" autocomplete="email"') }}
    {{ alan('telefon', 'teklif.telefon', tip='tel', ek='maxlength="50" autocomplete="tel"') }}
    {{ alan('ulke', 'teklif.ulke', zorunlu=True, ek='maxlength="2" autocomplete="country"') }}
    {{ alan('adet', 'teklif.adet', tip='number', zorunlu=True, ek='min="1" max="9999"') }}
    <p class="form-alan">
      <label for="mesaj">{{ t('teklif.mesaj') }} *</label>
      <textarea id="mesaj" name="mesaj" rows="6" maxlength="2000" required{% if hatalar.get('mesaj') %} aria-invalid="true" aria-describedby="hata-mesaj"{% endif %}>{{ alanlar.mesaj }}</textarea>
      {% if hatalar.get('mesaj') %}<span class="alan-hata" id="hata-mesaj">{{ t(hatalar['mesaj']) }}</span>{% endif %}
    </p>
    <button type="submit" class="dugme" data-e2e="teklif-gonder">{{ t('teklif.gonder') }}</button>
  </form>
</section>
{% endblock %}
```

`app/web/sablonlar/teklif_tamam.html`:

```html
{% extends "taban.html" %}
{% block baslik %}{{ t('teklif.tamam_baslik') }}{% endblock %}
{% block icerik %}
<section class="teklif-tamam">
  <h1>{{ t('teklif.tamam_baslik') }}</h1>
  <p class="basari" role="status">{% if no %}{{ t('teklif.tamam_metin', no=no) }} <strong data-e2e="teklif-no">{{ no }}</strong>{% else %}{{ t('teklif.tamam_numarasiz') }}{% endif %}</p>
  <p>
    <a href="/{{ dil }}/">{{ t('teklif.ana_sayfa') }}</a>
    {% if musteri %} · <a href="/{{ dil }}/hesabim">{{ t('siparis.hesabim') }}</a>{% endif %}
  </p>
</section>
{% endblock %}
```

- [ ] **Step 7: Yönetim şablonlarını yaz**

`app/web/sablonlar/yonetim/_menu.html`:

```html
<nav class="yonetim-menu" aria-label="{{ t('yonetim.baslik') }}">
  <a href="/yonetim">{{ t('yonetim.menu.pano') }}</a>
  <a href="/yonetim/siparisler">{{ t('yonetim.menu.siparisler') }}</a>
  <a href="/yonetim/teklifler">{{ t('yonetim.menu.teklifler') }}</a>
  <a href="/yonetim/geri-bildirimler">{{ t('yonetim.menu.geri_bildirimler') }}</a>
  <form method="post" action="/yonetim/cikis" class="satir-formu">
    <input type="hidden" name="csrf" value="{{ csrf }}">
    <button type="submit" class="dugme-ikincil">{{ t('yonetim.cikis') }}</button>
  </form>
</nav>
```

`app/web/sablonlar/yonetim/giris.html`:

```html
{% extends "taban.html" %}
{% block baslik %}{{ t('yonetim.giris_baslik') }}{% endblock %}
{% block icerik %}
<section class="yonetim-giris">
  <h1>{{ t('yonetim.giris_baslik') }}</h1>
  {% if hata %}<div class="uyari" role="alert">{{ t(hata) }}</div>{% endif %}
  <form method="post" action="/yonetim/giris">
    <input type="hidden" name="csrf" value="{{ csrf }}">
    <p class="form-alan">
      <label for="kullanici">{{ t('yonetim.kullanici') }}</label>
      <input id="kullanici" name="kullanici" type="text" value="{{ kullanici }}" autocomplete="username" required>
    </p>
    <p class="form-alan">
      <label for="parola">{{ t('yonetim.parola') }}</label>
      <input id="parola" name="parola" type="password" autocomplete="current-password" required>
    </p>
    <button type="submit" class="dugme" data-e2e="yonetim-giris">{{ t('yonetim.giris') }}</button>
  </form>
</section>
{% endblock %}
```

`app/web/sablonlar/yonetim/pano.html`:

```html
{% extends "taban.html" %}
{% block baslik %}{{ t('yonetim.baslik') }}{% endblock %}
{% block icerik %}
<section class="yonetim">
  <h1>{{ t('yonetim.baslik') }}</h1>
  {% include "yonetim/_menu.html" %}
  {% if esitleme_uyari %}
  <div class="uyari uyari-esitleme" role="alert">{{ t('yonetim.esitleme_yok') if son_tam is none else t('yonetim.esitleme_uyari') }}</div>
  {% endif %}

  <h2>{{ t('yonetim.esitleme') }}</h2>
  <dl class="yonetim-ozet">
    <dt>{{ t('yonetim.son_tam_esitleme') }}</dt>
    <dd data-e2e="son-esitleme">{% if son_tam %}{{ son_tam.strftime('%d.%m.%Y %H:%M') }} UTC{% else %}—{% endif %}</dd>
    <dt>{{ t('yonetim.son_esitleme') }}</dt>
    <dd>
      {% if son %}
      {{ son['basla'][:16]|replace('T', ' ') }} — <strong>{{ t('yonetim.esitleme_durum.' ~ son['durum']) }}</strong><br>
      <small>{{ t('yonetim.esitleme_sayilar', api=son['api_toplam'] if son['api_toplam'] is not none else '—', cekilen=son['cekilen'], eklenen=son['eklenen'], guncellenen=son['guncellenen'], pasiflenen=son['pasiflenen'], bozuk=son['bozuk']) }}</small>
      {% if son['hata'] %}<br><small class="alan-hata">{{ t('yonetim.hata_metni', hata=son['hata']) }}</small>{% endif %}
      {% else %}—{% endif %}
    </dd>
  </dl>

  <h2>{{ t('yonetim.kur') }}</h2>
  {% if kur %}
  <p class="{% if kur_bayat %}kur-bayat{% endif %}">{{ t('yonetim.kur_degeri', satis=kur.eur_satis, alis=kur.eur_alis, tarih=kur.tarih.strftime('%d.%m.%Y')) }}{% if kur_bayat %} — {{ t('yonetim.kur_bayat') }}{% endif %}</p>
  {% else %}
  <p class="uyari">{{ t('yonetim.kur_yok') }}</p>
  {% endif %}

  <h2>{{ t('yonetim.sayilar') }}</h2>
  <dl class="yonetim-ozet">
    {% for ad, deger in sayilar.items() %}<dt>{{ t('yonetim.sayi.' ~ ad) }}</dt><dd>{{ deger }}</dd>{% endfor %}
  </dl>
</section>
{% endblock %}
```

`app/web/sablonlar/yonetim/siparisler.html`:

```html
{% extends "taban.html" %}
{% block baslik %}{{ t('yonetim.menu.siparisler') }}{% endblock %}
{% block icerik %}
<section class="yonetim">
  <h1>{{ t('yonetim.menu.siparisler') }}</h1>
  {% include "yonetim/_menu.html" %}
  {% if hata %}<div class="uyari" role="alert">{{ t('yonetim.gecis_izinsiz', no=hata.no, eski=t('siparis_durum.' ~ hata.eski), yeni=t('siparis_durum.' ~ hata.yeni)) }}</div>{% endif %}
  {% if not siparisler %}
  <p>{{ t('yonetim.liste_bos') }}</p>
  {% else %}
  <table class="sepet-tablo yonetim-tablo">
    <thead>
      <tr>
        <th scope="col">{{ t('yonetim.no') }}</th><th scope="col">{{ t('yonetim.musteri') }}</th>
        <th scope="col">{{ t('yonetim.tarih') }}</th><th scope="col">{{ t('yonetim.tutar') }}</th>
        <th scope="col">{{ t('yonetim.durum') }}</th><th scope="col">{{ t('yonetim.islem') }}</th>
      </tr>
    </thead>
    <tbody>
      {% for s in siparisler %}
      <tr>
        <td>{{ s.no }}</td>
        <td>{{ s.fatura_adresi.ad_soyad }} <small>(#{{ s.musteri_id }})</small></td>
        <td>{{ s.olusturma.strftime('%d.%m.%Y %H:%M') }}</td>
        <td>{{ para(s.toplam, s.para_birimi) }}</td>
        <td>{{ t('siparis_durum.' ~ s.durum) }}</td>
        <td>
          {% if gecisler[s.id] %}
          <form method="post" action="/yonetim/siparis/{{ s.id }}/durum" class="satir-formu">
            <input type="hidden" name="csrf" value="{{ csrf }}">
            <label class="gizli-etiket" for="durum-{{ s.id }}">{{ t('yonetim.durum') }}</label>
            <select id="durum-{{ s.id }}" name="durum">
              {% for g in gecisler[s.id] %}<option value="{{ g }}">{{ t('siparis_durum.' ~ g) }}</option>{% endfor %}
            </select>
            <button type="submit">{{ t('yonetim.degistir') }}</button>
          </form>
          {% else %}{{ t('yonetim.gecis_yok') }}{% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
</section>
{% endblock %}
```

`app/web/sablonlar/yonetim/teklifler.html`:

```html
{% extends "taban.html" %}
{% block baslik %}{{ t('yonetim.menu.teklifler') }}{% endblock %}
{% block icerik %}
<section class="yonetim">
  <h1>{{ t('yonetim.menu.teklifler') }}</h1>
  {% include "yonetim/_menu.html" %}
  {% if hata %}<div class="uyari" role="alert">{{ t('yonetim.gecis_izinsiz', no=hata.no, eski=t('teklif_durum.' ~ hata.eski), yeni=t('teklif_durum.' ~ hata.yeni)) }}</div>{% endif %}
  {% if not teklifler %}
  <p>{{ t('yonetim.liste_bos') }}</p>
  {% else %}
  <table class="sepet-tablo yonetim-tablo">
    <thead>
      <tr>
        <th scope="col">{{ t('yonetim.no') }}</th><th scope="col">{{ t('yonetim.tarih') }}</th>
        <th scope="col">{{ t('yonetim.musteri') }}</th><th scope="col">{{ t('yonetim.iletisim') }}</th>
        <th scope="col">{{ t('yonetim.urun') }}</th><th scope="col">{{ t('yonetim.mesaj') }}</th>
        <th scope="col">{{ t('yonetim.durum') }}</th><th scope="col">{{ t('yonetim.islem') }}</th>
      </tr>
    </thead>
    <tbody>
      {% for tk in teklifler %}
      <tr>
        <td>{{ tk.no }}</td>
        <td>{{ tk.olusturma.strftime('%d.%m.%Y %H:%M') }}</td>
        <td>{{ tk.ad }}{% if tk.firma %}<br><small>{{ tk.firma }}</small>{% endif %}{% if tk.musteri_id %}<br><small>#{{ tk.musteri_id }}</small>{% endif %}</td>
        <td>{{ tk.eposta }}{% if tk.telefon %}<br>{{ tk.telefon }}{% endif %}<br><small>{{ tk.ulke }}</small></td>
        <td>{% if tk.urun_ad %}{{ tk.urun_ad }}{% else %}—{% endif %} × {{ tk.adet }}</td>
        <td>{{ tk.mesaj }}</td>
        <td>{{ t('teklif_durum.' ~ tk.durum) }}</td>
        <td>
          {% if gecisler[tk.id] %}
          <form method="post" action="/yonetim/teklif/{{ tk.id }}/durum" class="satir-formu">
            <input type="hidden" name="csrf" value="{{ csrf }}">
            <label class="gizli-etiket" for="tdurum-{{ tk.id }}">{{ t('yonetim.durum') }}</label>
            <select id="tdurum-{{ tk.id }}" name="durum">
              {% for g in gecisler[tk.id] %}<option value="{{ g }}">{{ t('teklif_durum.' ~ g) }}</option>{% endfor %}
            </select>
            <button type="submit">{{ t('yonetim.degistir') }}</button>
          </form>
          {% else %}{{ t('yonetim.gecis_yok') }}{% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
</section>
{% endblock %}
```

`app/web/sablonlar/yonetim/geri_bildirimler.html`:

```html
{% extends "taban.html" %}
{% block baslik %}{{ t('yonetim.menu.geri_bildirimler') }}{% endblock %}
{% block icerik %}
<section class="yonetim">
  <h1>{{ t('yonetim.menu.geri_bildirimler') }}</h1>
  {% include "yonetim/_menu.html" %}
  <form method="get" action="/yonetim/geri-bildirimler" class="satir-formu">
    <label for="filtre-durum">{{ t('yonetim.durum') }}</label>
    <select id="filtre-durum" name="durum">
      <option value="">{{ t('yonetim.filtre_tumu') }}</option>
      {% for d in durumlar %}<option value="{{ d }}"{% if d == filtre %} selected{% endif %}>{{ t('yonetim.gb_durum.' ~ d) }}</option>{% endfor %}
    </select>
    <button type="submit">{{ t('yonetim.filtre') }}</button>
  </form>
  {% if not kayitlar %}
  <p>{{ t('yonetim.liste_bos') }}</p>
  {% else %}
  <table class="sepet-tablo yonetim-tablo">
    <thead>
      <tr>
        <th scope="col">{{ t('yonetim.tarih') }}</th><th scope="col">{{ t('yonetim.sayfa') }}</th>
        <th scope="col">{{ t('yonetim.metin') }}</th><th scope="col">{{ t('yonetim.isim') }}</th>
        <th scope="col">{{ t('yonetim.durum') }}</th><th scope="col">{{ t('yonetim.islem') }}</th>
      </tr>
    </thead>
    <tbody>
      {% for k in kayitlar %}
      <tr>
        <td>{{ k['olusturma'][:16]|replace('T', ' ') }}</td>
        <td>{% if k['sayfa'].startswith('/') and not k['sayfa'].startswith('//') %}<a href="{{ k['sayfa'] }}">{{ k['sayfa'] }}</a>{% else %}{{ k['sayfa'] }}{% endif %}</td>
        <td>{{ k['metin'] }}</td>
        <td>{{ k['isim'] or '—' }}</td>
        <td>{{ t('yonetim.gb_durum.' ~ k['durum']) }}</td>
        <td>
          <form method="post" action="/yonetim/geri-bildirim/{{ k['id'] }}/durum" class="satir-formu">
            <input type="hidden" name="csrf" value="{{ csrf }}">
            <label class="gizli-etiket" for="gdurum-{{ k['id'] }}">{{ t('yonetim.durum') }}</label>
            <select id="gdurum-{{ k['id'] }}" name="durum">
              {% for d in durumlar %}<option value="{{ d }}"{% if d == k['durum'] %} selected{% endif %}>{{ t('yonetim.gb_durum.' ~ d) }}</option>{% endfor %}
            </select>
            <button type="submit">{{ t('yonetim.degistir') }}</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
</section>
{% endblock %}
```

- [ ] **Step 8: CSS ekini yaz**

`app/web/statik/site.css` sonuna ekle:

```css
/* --- Görev 15: teklif ve yönetim --- */
.teklif textarea { padding: .5rem; border: 1px solid var(--cizgi); max-width: 40rem; font: inherit; }
.teklif-urun { background: #fff; border: 1px solid var(--cizgi); padding: .5rem 1rem; }
.yonetim-menu { display: flex; flex-wrap: wrap; gap: 1rem; align-items: center; border-bottom: 2px solid var(--yesil-koyu); padding: .5rem 0; margin-bottom: 1rem; }
.yonetim-ozet { display: grid; grid-template-columns: max-content 1fr; gap: .25rem 1.5rem; }
.yonetim-ozet dd { margin: 0; }
.yonetim-tablo td { font-size: .9rem; }
.satir-formu { display: inline-flex; flex-wrap: wrap; gap: .25rem; align-items: center; }
.uyari-esitleme { font-weight: 700; }
```

- [ ] **Step 9: Testleri çalıştır, geçtiklerini gör**

Run: `bash dagitim/test-vm.sh tests/test_web_teklif_yonetim.py -q`
Expected: PASS (20 passed)

- [ ] **Step 10: Tüm test takımı**

Run: `bash dagitim/test-vm.sh tests -q`
Expected: PASS — Görev 14 testleri ve `eksik_anahtarlar` testi dahil.

- [ ] **Step 11: Commit**

```bash
git add app/web/rotalar/teklif_gb.py app/web/rotalar/yonetim.py app/web/sablonlar/teklif.html \
  app/web/sablonlar/teklif_tamam.html app/web/sablonlar/yonetim/ app/web/dil/tr.json app/web/dil/en.json \
  app/web/statik/site.css tests/test_web_teklif_yonetim.py
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m "feat: teklif formu, geri bildirim ucu ve yonetim paneli

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Görev 16: Yasal sayfalar (TR/EN taslak metinler)

10 yasal sayfa × 2 dil. Her sayfanın başında "TASLAK – hukuki onay bekliyor (SY Hukuk)" bandı. Metinler 6502 sayılı Kanun, Mesafeli Sözleşmeler Yönetmeliği (RG 27.11.2014/29188; 24.05.2025 RG 32909 değişikliği), TBK/TTK, KVKK, GDPR m.3(2), 6563 sayılı Kanun ve İYS esas alınarak yazılmış **taslaktır**; şirket kimlik bilgilerinden yalnız unvan ve adres doldurulur, diğerleri "[doldurulacak]" kalır.

**Files:**
- Create: `app/web/rotalar/yasal.py`
- Create: `app/web/sablonlar/yasal/_taban.html`
- Create: `app/web/sablonlar/yasal/tr/{on-bilgilendirme,mesafeli-satis,iade,garanti,kvkk,acik-riza,cerez,gizlilik,kullanim,kunye}.html`
- Create: `app/web/sablonlar/yasal/en/{on-bilgilendirme,mesafeli-satis,iade,garanti,kvkk,acik-riza,cerez,gizlilik,kullanim,kunye}.html`
- Modify: `app/web/dil/tr.json`, `app/web/dil/en.json`, `app/web/statik/site.css`

(`app/web/uygulama.py` değişmez: `ROTA_SIRASI` `yasal` modülünü yükler — K9.)
- Test: `tests/test_web_yasal.py`

**Interfaces:**
- Consumes: `app.web.baglam.sablon`; dil dönüştürücüsü `{dil:dil}` (Görev 11, K9 — yalnız `tr|en` eşleşir); `taban.html` (`{% block icerik %}`, alt bilgide `/{dil}/yasal/<sayfa>` bağlantıları); Görev 12'nin kayıt sayfası (`/{dil}/kayit`) KVKK bağlantısını `/{dil}/yasal/kvkk` olarak verir; testte `istemci` fixture'ı.
- Produces:
  - `app.web.rotalar.yasal.router` — `GET /{dil}/yasal/{sayfa}`; `SAYFALAR: tuple[str, ...]` (10 sayfa adı, URL sözleşmesindeki sırayla)
  - Şablon `yasal/_taban.html` (`{% block metin %}`); CSS sınıfları `.taslak-bandi`, `.yasal`, `.kunye`
  - i18n: `yasal_metin.taslak_bandi`, `yasal_metin.surum`, `yasal_metin.ceviri_notu`, `yasal_metin.kunye`
  - Ödeme ekranı (Görev 14) `on-bilgilendirme`, `mesafeli-satis`, `kullanim`, `iade`, `garanti` sayfalarına bağlanır; kurumsal/yurt dışı "satış koşulları" `kullanim` sayfasının B bölümüdür.

- [ ] **Step 1: Başarısız testleri yaz**

`tests/test_web_yasal.py`:

```python
"""Görev 16 — yasal sayfalar (TestClient ile)."""
import re

import pytest

from app.web.rotalar.yasal import SAYFALAR

BANT = {"tr": "TASLAK – hukuki onay bekliyor (SY Hukuk)", "en": "DRAFT – pending legal approval (SY Hukuk)"}


def test_on_sayfa_tanimli():
    assert SAYFALAR == ("on-bilgilendirme", "mesafeli-satis", "iade", "garanti", "kvkk",
                        "acik-riza", "cerez", "gizlilik", "kullanim", "kunye")


@pytest.mark.parametrize("dil", ["tr", "en"])
@pytest.mark.parametrize("sayfa", SAYFALAR)
def test_yasal_sayfa_200_ve_taslak_bandi(istemci, dil, sayfa):
    r = istemci.get(f"/{dil}/yasal/{sayfa}")
    assert r.status_code == 200
    assert 'class="taslak-bandi"' in r.text
    assert BANT[dil] in r.text
    assert re.search(r"<h1[^>]*>[^<]{4,}</h1>", r.text)
    assert len(re.findall(r"<h2", r.text)) >= 3          # madde başlıkları var


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_kunye_doldurulacak(istemci, dil):
    r = istemci.get(f"/{dil}/yasal/kunye")
    assert "[doldurulacak]" in r.text
    assert "MUSTAFA CEYLAN ENDÜSTRİ A.Ş." in r.text
    assert "K.O.S.B. 3. Sk., No: 7, 42250 Selçuklu / Konya" in r.text
    for terim in ("MERSİS", "KEP", "ETBİS"):
        assert terim in r.text


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_iade_ve_garanti_b2c_b2b_ayrimi(istemci, dil):
    iade = istemci.get(f"/{dil}/yasal/iade").text
    garanti = istemci.get(f"/{dil}/yasal/garanti").text
    if dil == "tr":
        assert "14 gün" in iade and "cayma hakkı uygulanmaz" in iade
        assert "test edildi" in garanti and "olduğu gibi" in garanti and "TBK m.221" in garanti
    else:
        assert "14 days" in iade and "no right of withdrawal" in iade
        assert "tested" in garanti and "as is" in garanti and "Article 221" in garanti


@pytest.mark.parametrize("yol", ["/tr/yasal/yok", "/en/yasal/bilinmeyen", "/de/yasal/kvkk",
                                 "/tr/yasal/KVKK", "/tr/yasal/_taban"])
def test_bilinmeyen_sayfa_404(istemci, yol):
    assert istemci.get(yol).status_code == 404


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_alt_bilgi_ve_metin_ici_yasal_baglantilar_calisir(istemci, dil):
    sayfa = istemci.get(f"/{dil}/yasal/kunye")
    alt_bilgiler = re.findall(r"<footer.*?</footer>", sayfa.text, re.S)
    assert alt_bilgiler, "sayfada <footer> yok"
    alt_bilgi = alt_bilgiler[-1]                      # taban.html'in alt bilgisi sayfadaki son <footer>
    assert re.findall(rf'href="/{dil}/yasal/', alt_bilgi), "alt bilgide yasal bağlantı yok"
    baglantilar = set(re.findall(r'href="(/(?:tr|en)/yasal/[^"#?]+)"', sayfa.text))
    assert baglantilar, "yasal bağlantı bulunamadı"
    for sayfa_adi in SAYFALAR:      # metin içi çapraz bağlantılar dahil bütün yasal sayfalar
        r = istemci.get(f"/{dil}/yasal/{sayfa_adi}")
        baglantilar |= set(re.findall(r'href="(/(?:tr|en)/yasal/[^"#?]+)"', r.text))
    for yol in sorted(baglantilar):
        assert istemci.get(yol).status_code == 200, yol


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_kayit_sayfasindaki_kvkk_baglantisi(istemci, dil):
    kayit = istemci.get(f"/{dil}/kayit")
    assert kayit.status_code == 200
    assert f'href="/{dil}/yasal/kvkk"' in kayit.text
    assert istemci.get(f"/{dil}/yasal/kvkk").status_code == 200
```

- [ ] **Step 2: Testleri çalıştır, başarısız olduklarını gör**

Run: `bash dagitim/test-vm.sh tests/test_web_yasal.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.web.rotalar.yasal'` (toplama hatası).

- [ ] **Step 3: i18n anahtarlarını iki dile birlikte ekle**

`app/web/dil/tr.json` nesnesine ekle:

```json
  "yasal_metin.taslak_bandi": "TASLAK – hukuki onay bekliyor (SY Hukuk). Bu metin henüz bağlayıcı değildir.",
  "yasal_metin.surum": "Taslak sürüm: 12.10.2026",
  "yasal_metin.ceviri_notu": "Türkçe metin esastır; İngilizce metin bilgi amaçlı çeviridir.",
  "yasal_metin.kunye": "Künye"
```

`app/web/dil/en.json` nesnesine ekle:

```json
  "yasal_metin.taslak_bandi": "DRAFT – pending legal approval (SY Hukuk). This text is not yet binding.",
  "yasal_metin.surum": "Draft version: 12 October 2026",
  "yasal_metin.ceviri_notu": "The Turkish text prevails; the English text is a translation for information.",
  "yasal_metin.kunye": "Legal notice"
```

- [ ] **Step 4: Rota modülünü yaz**

`app/web/rotalar/yasal.py`:

```python
"""Yasal sayfa taslakları (Görev 16)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.web.baglam import sablon
from app.web.bagimlilik import db_bagimliligi

router = APIRouter()

SAYFALAR = ("on-bilgilendirme", "mesafeli-satis", "iade", "garanti", "kvkk",
            "acik-riza", "cerez", "gizlilik", "kullanim", "kunye")


@router.get("/{dil:dil}/yasal/{sayfa}")
def yasal_sayfa(dil: str, sayfa: str, request: Request, con=Depends(db_bagimliligi)) -> Response:  # başlıkta oturum/sepet doğru görünsün
    if sayfa not in SAYFALAR:   # beyaz liste: şablon yolu kullanıcı girdisinden türetilmez
        raise HTTPException(status_code=404)
    return sablon(request, f"yasal/{dil}/{sayfa}.html", {"yasal_sayfa": sayfa})
```

- [ ] **Step 5: Ortak yasal taban şablonu ve CSS**

`app/web/sablonlar/yasal/_taban.html`:

```html
{% extends "taban.html" %}
{% block icerik %}
<article class="yasal" lang="{{ dil }}">
  <div class="taslak-bandi" role="note">{{ t('yasal_metin.taslak_bandi') }}</div>
  {% block metin %}{% endblock %}
  <footer class="yasal-dipnot">
    <p>{{ t('yasal_metin.surum') }} · <a href="/{{ dil }}/yasal/kunye">{{ t('yasal_metin.kunye') }}</a></p>
    <p>{{ t('yasal_metin.ceviri_notu') }}</p>
  </footer>
</article>
{% endblock %}
```

`app/web/statik/site.css` sonuna ekle:

```css
/* --- Görev 16: yasal sayfalar --- */
.taslak-bandi { background: #fff4d6; border: 2px solid var(--kiremit); color: var(--yazi); font-weight: 700; padding: .5rem 1rem; margin: 1rem 0; }
.yasal { max-width: 52rem; line-height: 1.6; }
.yasal h1 { font-family: Georgia, serif; color: var(--yesil-koyu); }
.yasal h2 { font-family: Georgia, serif; color: var(--yesil-koyu); margin-top: 1.75rem; font-size: 1.2rem; }
.yasal h3 { font-size: 1rem; margin-top: 1.25rem; }
.yasal table { border-collapse: collapse; width: 100%; }
.yasal th, .yasal td { border: 1px solid var(--cizgi); padding: .4rem .6rem; text-align: left; vertical-align: top; }
.yasal .yasal-ozet { background: #fff; border-left: 4px solid var(--mavi); padding: .5rem 1rem; }
.yasal-dipnot { border-top: 1px solid var(--cizgi); margin-top: 2rem; color: var(--gri); font-size: .9rem; }
.kunye { display: grid; grid-template-columns: minmax(10rem, max-content) 1fr; gap: .4rem 1.5rem; }
.kunye dd { margin: 0; }
@media (max-width: 600px) { .kunye { grid-template-columns: 1fr; } .kunye dd { margin-bottom: .5rem; } .yasal table { font-size: .85rem; } }
```

- [ ] **Step 6: Türkçe yasal metinleri yaz**

`app/web/sablonlar/yasal/tr/on-bilgilendirme.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}Ön Bilgilendirme Formu{% endblock %}
{% block metin %}
<h1>Ön Bilgilendirme Formu</h1>
<p class="yasal-ozet">Bu form, 6502 sayılı Tüketicinin Korunması Hakkında Kanun ve Mesafeli Sözleşmeler Yönetmeliği uyarınca <strong>tüketici (bireysel) siparişlerinde</strong> sözleşme kurulmadan önce alıcıya sunulur. Kurumsal ve yurt dışı alıcılar için <a href="/tr/yasal/kullanim">Kullanım ve Satış Koşulları</a> geçerlidir.</p>

<h2>1. Satıcı</h2>
<p>MUSTAFA CEYLAN ENDÜSTRİ A.Ş. (Ceylan Robot), K.O.S.B. 3. Sk., No: 7, 42250 Selçuklu / Konya. MERSİS numarası, telefon, e-posta ve KEP adresi <a href="/tr/yasal/kunye">Künye</a> sayfasında yer alır.</p>

<h2>2. Ürünün temel nitelikleri</h2>
<p>Ürünün adı, stok kodu (SKU), üretici kodu, adedi ve durumu (yeni, ikinci el – test edildi, ikinci el – olduğu gibi) ürün sayfasında ve ödeme adımındaki sipariş özetinde gösterilir. İkinci el ürünlerde durum tanımları <a href="/tr/yasal/garanti">Garanti Koşulları</a> sayfasındadır. Ürün sayfasında açıkça belirtilen kusurlar ve kullanım izleri ürünün niteliğinin parçasıdır.</p>

<h2>3. Fiyat ve ödeme</h2>
<p>Satış fiyatı Türk lirası olarak ve KDV dahil gösterilir. Euro bazlı ürünlerde TL tutar, Türkiye Cumhuriyet Merkez Bankası (TCMB) döviz satış kuruyla hesaplanır ve ödeme adımında sabitlenir. Kur değişirse yeni tutar ödemeden önce onayınıza sunulur. Kargo bedeli sipariş özetinde ayrı satırda gösterilir.</p>
<p>Ödeme, 3D Secure doğrulamalı banka veya kredi kartıyla peşin alınır. Kart bilgileri satıcı tarafından saklanmaz; sipariş kaydında yalnızca kartın son dört hanesi tutulur. Ödemesi 30 dakika içinde tamamlanmayan sipariş kendiliğinden iptal olur.</p>

<h2>4. Teslimat</h2>
<p>Ürün, bildirdiğiniz Türkiye içindeki adrese kargoyla gönderilir ya da Konya'daki tesisimizden teslim alınır. Teslim süresi sipariş tarihinden itibaren en geç 30 gündür. Stokta bulunmayan ürünlerde tedarik süresi siparişten sonra size bildirilir. 30 günlük süre aşılacaksa sözleşmeyi feshedebilirsiniz; ödediğiniz bedel 14 gün içinde iade edilir.</p>

<h2>5. Cayma hakkı</h2>
<p>Ürünü teslim aldığınız günden itibaren 14 gün içinde hiçbir gerekçe göstermeden ve cezai şart ödemeden sözleşmeden cayabilirsiniz. Ayrı ayrı teslim edilen ürünlerde süre son ürünün teslimiyle başlar. Cayma bildirimini süre içinde yazılı olarak veya e-posta gibi kalıcı bir veri saklayıcısıyla iletmeniz yeterlidir.</p>
<p>Cayma halinde, teslim masrafları dahil tahsil edilen tüm bedel bildirimin bize ulaştığı tarihten itibaren 14 gün içinde, ödemede kullandığınız araçla iade edilir. Ürünü cayma bildiriminden itibaren 10 gün içinde geri göndermeniz gerekir. Anlaşmalı kargo şirketimizle yapılan iadelerde gönderim masrafı sizden alınmaz. Ayrıntılar <a href="/tr/yasal/iade">İade ve Cayma</a> sayfasındadır.</p>

<h2>6. Cayma hakkının kullanılamayacağı durumlar</h2>
<ul>
  <li>İsteğiniz doğrultusunda özel olarak hazırlanan, programlanan veya birleştirilen ürünler (örneğin size özel parametrelenmiş kontrol ünitesi veya robot hücresi),</li>
  <li>Teslimden sonra niteliği gereği başka ürünlerle ayrılmaz biçimde karışan ürünler,</li>
  <li>Ambalajı açılmış yazılım lisansları ve dijital içerikler.</li>
</ul>
<p>Ürünün olağan kontrolün ötesinde kullanılması veya kurulması nedeniyle değerinde oluşan azalmadan alıcı sorumludur.</p>

<h2>7. Ayıplı ürün ve şikâyetler</h2>
<p>Ayıplı üründe 6502 sayılı Kanun'un 11. maddesindeki seçimlik haklarınızı (sözleşmeden dönme, bedel indirimi, ücretsiz onarım, ayıpsız misliyle değişim) kullanabilirsiniz. Bu haklar ikinci el ürünlerde de geçerlidir; ancak satıştan önce ürün sayfasında açıkça bildirilen kusurlar ve ürünün yaşına uygun olağan aşınma ayıp sayılmaz. Şikâyet ve talepleriniz için Künye'deki iletişim kanallarını kullanabilirsiniz.</p>

<h2>8. Uyuşmazlık çözümü</h2>
<p>Şikâyet ve itirazlarınızı, Ticaret Bakanlığınca her yıl ilan edilen parasal sınırlar içinde yerleşim yerinizdeki veya işlemin yapıldığı yerdeki tüketici hakem heyetine, bu sınırları aşan uyuşmazlıklarda tüketici mahkemesine iletebilirsiniz. Mevzuatta öngörülen hallerde dava açmadan önce arabulucuya başvurmak zorunludur.</p>

<h2>9. Onay</h2>
<p>Ödeme adımındaki onay kutusunu işaretleyerek bu formu okuduğunuzu ve sözleşme kurulmadan önce yukarıdaki bilgileri edindiğinizi kabul edersiniz. Form ve sipariş bilgileri sipariş onayıyla birlikte size kalıcı veri saklayıcısıyla iletilir.</p>
{% endblock %}
```

`app/web/sablonlar/yasal/tr/mesafeli-satis.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}Mesafeli Satış Sözleşmesi{% endblock %}
{% block metin %}
<h1>Mesafeli Satış Sözleşmesi</h1>
<p class="yasal-ozet">Bu sözleşme yalnızca ürünü ticari veya mesleki olmayan amaçlarla satın alan <strong>tüketiciler</strong> için geçerlidir. Kurumsal ve yurt dışı alıcılar <a href="/tr/yasal/kullanim">Kullanım ve Satış Koşulları</a>'na tabidir.</p>

<h2>Madde 1 – Taraflar</h2>
<p><strong>Satıcı:</strong> MUSTAFA CEYLAN ENDÜSTRİ A.Ş., K.O.S.B. 3. Sk., No: 7, 42250 Selçuklu / Konya. Diğer kimlik ve iletişim bilgileri <a href="/tr/yasal/kunye">Künye</a>'de yer alır.</p>
<p><strong>Alıcı:</strong> Sipariş sırasında kayıtlı hesap bilgileriyle tanımlanan gerçek kişi.</p>

<h2>Madde 2 – Konu</h2>
<p>Bu sözleşmenin konusu, alıcının internet sitesi üzerinden elektronik ortamda sipariş verdiği, nitelikleri ve satış fiyatı sipariş özetinde belirtilen ürünün satışı ve teslimidir. Taraflar, 6502 sayılı Tüketicinin Korunması Hakkında Kanun ve Mesafeli Sözleşmeler Yönetmeliği hükümleri uyarınca hak ve yükümlülüklerini düzenler.</p>

<h2>Madde 3 – Ürün, fiyat ve ödeme</h2>
<p>Ürün bilgileri, adet, KDV dahil satış fiyatı, kargo bedeli ve toplam tutar sipariş özetinde ve sipariş onayında yer alır; bu bilgiler sözleşmenin ayrılmaz parçasıdır. Euro bazlı ürünlerde ödeme anında sabitlenen TCMB döviz satış kuru uygulanır ve siparişe kaydedilir. Ödeme 3D Secure doğrulamalı kartla peşin yapılır. Ödeme 30 dakika içinde tamamlanmazsa sipariş kendiliğinden iptal olur ve sözleşme kurulmamış sayılır.</p>

<h2>Madde 4 – Teslimat</h2>
<p>Ürün, sipariş tarihinden itibaren en geç 30 gün içinde alıcının bildirdiği adrese veya alıcının gösterdiği kişiye teslim edilir. Fabrikadan teslim seçildiğinde teslim alma günü taraflarca belirlenir. Alıcı, teslim sırasında ambalajı kontrol eder; hasarlı pakette kargo görevlisine tutanak tutturur. Ürün alıcıya teslim edilene kadar oluşan hasardan satıcı sorumludur.</p>

<h2>Madde 5 – Satıcının yükümlülükleri</h2>
<ul>
  <li>Ürünü siparişte belirtilen niteliklere, ikinci el ürünlerde ilan edilen durum tanımına uygun ve eksiksiz teslim etmek,</li>
  <li>Varsa kullanım kılavuzunu, test kaydını ve garanti belgesini ürünle birlikte vermek,</li>
  <li>Faturayı düzenleyip alıcıya iletmek,</li>
  <li>Ürünün tedarik edilemeyeceğinin anlaşılması halinde alıcıyı 3 gün içinde bilgilendirmek ve tahsil edilen bedeli 14 gün içinde iade etmek.</li>
</ul>

<h2>Madde 6 – Alıcının yükümlülükleri</h2>
<ul>
  <li>Teslimat ve fatura bilgilerini doğru ve güncel vermek,</li>
  <li>Ürünü kılavuzuna ve güvenlik talimatlarına uygun kullanmak; endüstriyel ekipmanın kurulumunu yetkin kişilere yaptırmak,</li>
  <li>Hesap ve şifre güvenliğini sağlamak.</li>
</ul>

<h2>Madde 7 – Cayma hakkı</h2>
<p>Alıcı, ürünü teslim aldığı günden itibaren 14 gün içinde gerekçe göstermeksizin ve cezai şart ödemeksizin sözleşmeden cayabilir. Cayma bildirimi bu süre içinde yazılı olarak veya kalıcı veri saklayıcısıyla satıcıya yöneltilir. Satıcı, bildirimin ulaşmasından itibaren 14 gün içinde teslim masrafları dahil tüm bedeli iade eder; alıcı ürünü 10 gün içinde geri gönderir. Cayma hakkının kullanılamayacağı durumlar ve iade adımları <a href="/tr/yasal/iade">İade ve Cayma</a> sayfasında sayılmıştır.</p>

<h2>Madde 8 – Ayıplı ürün</h2>
<p>Ayıplı üründe alıcı, 6502 sayılı Kanun'un 11. maddesindeki seçimlik haklarını kullanabilir. Ayıptan doğan sorumluluk, ayıp daha sonra ortaya çıksa bile teslimden itibaren iki yıllık zamanaşımına tabidir; ayıbın satıcının ağır kusuru veya hilesiyle gizlenmesi hali saklıdır. İkinci el ürünlerde satıştan önce açıkça bildirilen kusurlar ayıp sayılmaz. Garanti ayrıntıları <a href="/tr/yasal/garanti">Garanti Koşulları</a>'ndadır.</p>

<h2>Madde 9 – Kişisel veriler</h2>
<p>Alıcının kişisel verileri <a href="/tr/yasal/kvkk">KVKK Aydınlatma Metni</a>'nde açıklanan amaçlarla ve hukuki sebeplerle işlenir.</p>

<h2>Madde 10 – Uyuşmazlık ve yürürlük</h2>
<p>Uyuşmazlıklarda, Ticaret Bakanlığınca ilan edilen parasal sınırlar içinde tüketici hakem heyetleri, bu sınırların üzerinde tüketici mahkemeleri yetkilidir. Sözleşme, alıcının ödeme adımında Ön Bilgilendirme Formu'nu ve bu sözleşmeyi onaylayıp ödemeyi tamamlamasıyla kurulur. Sözleşme metni ve sipariş bilgileri alıcıya kalıcı veri saklayıcısıyla iletilir ve satıcı tarafından mevzuatta öngörülen süre boyunca saklanır.</p>
{% endblock %}
```

`app/web/sablonlar/yasal/tr/iade.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}İade ve Cayma Koşulları{% endblock %}
{% block metin %}
<h1>İade ve Cayma Koşulları</h1>
<p class="yasal-ozet">Bireysel alıcılar 14 gün içinde cayma hakkına sahiptir. Kurumsal (ticari) alımlarda cayma hakkı uygulanmaz; iade yalnızca aşağıdaki sözleşmesel koşullarla mümkündür.</p>

<h2>A. Bireysel (tüketici) alıcılar</h2>
<h3>1. 14 günlük cayma hakkı</h3>
<p>Ürünü teslim aldığınız günden itibaren 14 gün içinde gerekçe göstermeden sözleşmeden cayabilirsiniz. Birden fazla ürünün ayrı teslim edildiği siparişlerde süre son ürünün teslimiyle başlar.</p>
<h3>2. Cayma hakkı nasıl kullanılır</h3>
<ol>
  <li>Sipariş numaranızı ve iade etmek istediğiniz ürünü belirterek Künye'deki e-posta adresine ya da yazılı olarak bildirimde bulunun. Gerekçe yazmanız gerekmez.</li>
  <li>Ürünü bildiriminizden itibaren 10 gün içinde, mümkünse orijinal ambalajı, aksesuarları ve belgeleriyle birlikte size bildirilen anlaşmalı kargo şirketiyle gönderin.</li>
  <li>Teslim masrafları dahil ödediğiniz tüm bedel, bildiriminizin bize ulaşmasından itibaren 14 gün içinde ödemede kullandığınız karta iade edilir. Ürün bize ulaşana veya gönderdiğinizi belgeleyene kadar iade bekletilebilir.</li>
</ol>
<h3>3. İade masrafı</h3>
<p>Anlaşmalı kargo şirketiyle yapılan iadelerde gönderim masrafı sizden alınmaz. Başka bir taşıyıcı seçerseniz masraf size aittir. Ağır ve hacimli ürünlerde (ör. robot, pozisyoner) iade taşıması satıcıyla birlikte planlanır.</p>
<h3>4. Cayma hakkının kullanılamayacağı ürünler</h3>
<ul>
  <li>İsteğiniz doğrultusunda özel olarak hazırlanan, programlanan veya birleştirilen ürünler,</li>
  <li>Ambalajı açılmış yazılım lisansları ve dijital içerikler,</li>
  <li>Teslimden sonra niteliği gereği başka ürünlerle ayrılmaz biçimde karışan ürünler.</li>
</ul>
<h3>5. Ayıplı ürün iadesi</h3>
<p>Ayıplı ürünlerde cayma süresinden bağımsız olarak 6502 sayılı Kanun'daki seçimlik haklarınız (iade, değişim, onarım, indirim) iki yıl boyunca geçerlidir. Ayıplı ürünün iade taşıma masrafı satıcıya aittir.</p>

<h2>B. Kurumsal alıcılar (B2B)</h2>
<p>Ticari veya mesleki amaçla yapılan alımlarda 6502 sayılı Kanun ve cayma hakkı uygulanmaz. İlişki, 6098 sayılı Türk Borçlar Kanunu (TBK) ve 6102 sayılı Türk Ticaret Kanunu (TTK) ile <a href="/tr/yasal/kullanim">Kullanım ve Satış Koşulları</a>'na tabidir.</p>
<ul>
  <li><strong>Muayene ve ihbar:</strong> Ürünü teslim aldığınızda muayene etmeniz gerekir (TBK m.223, TTK m.23). Açıkça belli olan ayıpları teslimden itibaren 2 gün içinde, açıkça belli olmayan ayıpları 8 gün içinde yapacağınız muayene sonucunda, olağan muayeneyle ortaya çıkarılamayan gizli ayıpları ise ortaya çıktıkları anda yazılı olarak bildirmelisiniz. Süresinde bildirilmeyen ayıplar için ürün kabul edilmiş sayılır.</li>
  <li><strong>Yanlış veya eksik teslim:</strong> Siparişe uymayan ürün ücretsiz olarak değiştirilir ya da bedeli iade edilir; taşıma masrafı satıcıya aittir.</li>
  <li><strong>Sözleşmesel iade:</strong> Bunun dışındaki iadeler satıcının yazılı onayına bağlıdır. Onay verilirse ambalajı açılmamış ve kullanılmamış standart ürünler, onay sırasında bildirilecek bir yeniden stoklama kesintisiyle iade alınabilir.</li>
  <li><strong>İade edilmeyen ürünler:</strong> Alıcıya özel konfigüre edilmiş, programlanmış veya üretilmiş ürünler ile "ikinci el – olduğu gibi" satılan ürünler.</li>
</ul>

<h2>C. Yurt dışı alıcılar</h2>
<p>Yurt dışı teslimatlar DAP (Incoterms 2020) koşuluyla yapılır; varış ülkesindeki gümrük vergileri, ithalat vergileri ve masrafları alıcıya aittir. Ayıp bildirimi B bölümündeki sürelerle yapılır. Satıcı kaynaklı bir hata yoksa iade navlunu, ihracat ve ithalat formaliteleri alıcıya aittir. Varış ülkesinde ödenen vergi ve harçlar satıcı tarafından iade edilmez.</p>

<h2>D. İkinci el ürünler</h2>
<p>"İkinci el – test edildi" ve "ikinci el – olduğu gibi" tanımları ile bu ürünlere özgü garanti koşulları <a href="/tr/yasal/garanti">Garanti Koşulları</a> sayfasındadır. Tüketicilerin cayma ve ayıplı mal hakları ikinci el ürünlerde de saklıdır.</p>
{% endblock %}
```

`app/web/sablonlar/yasal/tr/garanti.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}Garanti Koşulları{% endblock %}
{% block metin %}
<h1>Garanti Koşulları</h1>
<p class="yasal-ozet">Garanti kapsamı ürünün durumuna (yeni / ikinci el – test edildi / ikinci el – olduğu gibi) ve alıcının tüketici mi tacir mi olduğuna göre değişir. Ürünün durumu ürün sayfasında rozet olarak gösterilir.</p>

<h2>1. Ürün durumu tanımları</h2>
<dl>
  <dt><strong>Yeni</strong></dt>
  <dd>Kullanılmamış, orijinal ambalajında ürün. Üretici garantisi geçerlidir.</dd>
  <dt><strong>İkinci el – test edildi</strong></dt>
  <dd>Daha önce kullanılmış; sevkiyattan önce Ceylan Robot atölyesinde görsel kontrol, enerji verme ve temel fonksiyon testlerinden geçirilmiş ürün. Test kapsamı ve sonucu ürün sayfasında ve ürünle birlikte verilen test kaydında yazılır. Kozmetik kullanım izleri bulunabilir.</dd>
  <dt><strong>İkinci el – olduğu gibi</strong></dt>
  <dd>Daha önce kullanılmış; fonksiyon testi yapılmamış veya yalnızca kısmen yapılmış, bulunduğu haliyle satılan ürün. Bilinen kusurlar ürün sayfasında yazılır. Yedek parça veya onarım amaçlı alımlar için uygundur.</dd>
  <dt><strong>Belirtilmemiş</strong></dt>
  <dd>Durum bilgisi henüz girilmemiş ürün. Sipariş vermeden önce satış ekibinden durum teyidi alınmalıdır.</dd>
</dl>

<h2>2. Bireysel (tüketici) alıcılar</h2>
<ul>
  <li>Yeni ürünlerde üretici garantisi geçerlidir; garanti belgesiyle satılması zorunlu ürünlerde garanti süresi en az iki yıldır.</li>
  <li>İkinci el dahil tüm ürünlerde 6502 sayılı Kanun'un ayıplı mal hükümleri saklıdır; ayıptan sorumluluk teslimden itibaren iki yıllık zamanaşımına tabidir.</li>
  <li>"Olduğu gibi" ibaresi tüketicinin yasal haklarını kaldırmaz. Ancak satıştan önce ürün sayfasında açıkça bildirilen kusurlar ve ürünün yaşına uygun olağan aşınma ayıp sayılmaz.</li>
  <li>"İkinci el – test edildi" ürünlerde satıcı ayrıca teslimden itibaren 6 ay süreyle, test kaydında listelenen fonksiyonların çalışacağını taahhüt eder. Bu süre hukuki ve ticari onay sürecinde kesinleştirilecektir.</li>
  <li>Garanti kapsamındaki onarım süresi en fazla 20 iş günüdür.</li>
</ul>

<h2>3. Kurumsal alıcılar (B2B)</h2>
<ul>
  <li><strong>Yeni:</strong> Satıcının sorumluluğu üretici garantisinin koşulları ve süresiyle sınırlıdır.</li>
  <li><strong>İkinci el – test edildi:</strong> Teslimden itibaren 6 ay fonksiyon garantisi. Satıcının yükümlülüğü önce onarım veya değişimle, bunlar mümkün değilse bedel iadesiyle sınırlıdır.</li>
  <li><strong>İkinci el – olduğu gibi:</strong> Satıcının ayıptan sorumluluğu sözleşmeyle kaldırılmıştır. Alıcı ürünü bulunduğu haliyle, muayene imkânı tanınarak satın aldığını kabul eder. Satıcının ayıbı alıcıdan hileyle gizlemesi veya ağır kusuru hali bu sınırlamanın dışındadır (TBK m.221).</li>
  <li><strong>Dolaylı zararlar:</strong> Üretim kaybı, kâr kaybı ve duruş maliyeti gibi dolaylı zararlardan satıcı, kast ve ağır ihmal halleri dışında sorumlu değildir (TBK m.115).</li>
  <li><strong>Muayene ve ihbar:</strong> TTK m.23'teki süreler uygulanır; ayrıntılar <a href="/tr/yasal/iade">İade ve Cayma</a> sayfasındadır.</li>
</ul>

<h2>4. Garanti kapsamı dışındaki durumlar</h2>
<ul>
  <li>Yetkisiz kişilerce yapılan kurulum, onarım veya müdahale,</li>
  <li>Kılavuza aykırı kullanım, aşırı yükleme, çarpışma, uygun olmayan elektrik beslemesi veya ortam koşulları,</li>
  <li>Sarf malzemeleri ve aşınan parçalar (kablo, kayış, pil, conta, filtre, fırça vb.),</li>
  <li>Alıcının yaptığı yazılım, parametre veya programlama değişiklikleri,</li>
  <li>Teslimden sonra alıcı kaynaklı taşıma ve depolama hasarları.</li>
</ul>

<h2>5. Garanti başvurusu</h2>
<p>Sipariş numarası, ürünün seri numarası, arızanın tanımı ve mümkünse fotoğraf veya video ile teknik destek birimimize başvurabilirsiniz (iletişim bilgileri <a href="/tr/yasal/kunye">Künye</a>'de). Arıza tespiti uzaktan ya da atölyemizde yapılır. Garanti kapsamındaki işlerde taşıma masrafı satıcıya, kapsam dışındaki işlerde alıcıya aittir; kapsam dışı onarım için önce fiyat teklifi verilir.</p>
{% endblock %}
```

`app/web/sablonlar/yasal/tr/kvkk.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}KVKK Aydınlatma Metni{% endblock %}
{% block metin %}
<h1>Kişisel Verilerin Korunması Aydınlatma Metni</h1>
<p class="yasal-ozet">Bu metin, 6698 sayılı Kişisel Verilerin Korunması Kanunu (KVKK) m.10 ve Aydınlatma Yükümlülüğünün Yerine Getirilmesinde Uyulacak Usul ve Esaslar Hakkında Tebliğ uyarınca hazırlanmıştır.</p>

<h2>1. Veri sorumlusu</h2>
<p>MUSTAFA CEYLAN ENDÜSTRİ A.Ş., K.O.S.B. 3. Sk., No: 7, 42250 Selçuklu / Konya. İletişim ve KEP bilgileri <a href="/tr/yasal/kunye">Künye</a>'dedir.</p>

<h2>2. İşlenen kişisel veriler</h2>
<ul>
  <li><strong>Kimlik:</strong> ad soyad; kurumsal hesaplarda şahıs şirketi için T.C. kimlik numarası.</li>
  <li><strong>İletişim:</strong> e-posta, telefon, teslimat ve fatura adresi.</li>
  <li><strong>Müşteri işlem:</strong> sipariş, sepet, teklif talebi ve geri bildirim kayıtları.</li>
  <li><strong>Finans:</strong> fatura bilgileri, vergi dairesi ve numarası, ödeme sonucu ve kartın son dört hanesi (tam kart numarası saklanmaz).</li>
  <li><strong>İşlem güvenliği:</strong> IP adresi, oturum çerezi, giriş denemesi kayıtları.</li>
  <li><strong>Pazarlama:</strong> yalnızca onay verdiyseniz ticari elektronik ileti tercihleri.</li>
</ul>

<h2>3. İşleme amaçları ve hukuki sebepler</h2>
<table>
  <thead><tr><th>Amaç</th><th>Hukuki sebep (KVKK m.5)</th></tr></thead>
  <tbody>
    <tr><td>Üyelik, sipariş, ödeme, teslimat ve teklif süreçlerinin yürütülmesi</td><td>Sözleşmenin kurulması ve ifası (m.5/2-c)</td></tr>
    <tr><td>Fatura düzenlenmesi, ticari defter ve vergi kayıtlarının tutulması</td><td>Hukuki yükümlülük (m.5/2-ç)</td></tr>
    <tr><td>Bilgi güvenliği, kötüye kullanımın ve dolandırıcılığın önlenmesi</td><td>Meşru menfaat (m.5/2-f), hukuki yükümlülük (m.5/2-ç)</td></tr>
    <tr><td>Talep, şikâyet ve geri bildirimlerin değerlendirilmesi</td><td>Meşru menfaat (m.5/2-f)</td></tr>
    <tr><td>Hukuki uyuşmazlıklarda hakların korunması</td><td>Bir hakkın tesisi, kullanılması veya korunması (m.5/2-e)</td></tr>
    <tr><td>Kampanya ve ürün duyuruları</td><td>Açık rıza (m.5/1) ve 6563 sayılı Kanun kapsamında ticari ileti onayı</td></tr>
  </tbody>
</table>

<h2>4. Toplama yöntemi</h2>
<p>Veriler; internet sitesindeki kayıt, sipariş, teklif ve geri bildirim formları ile çerezler aracılığıyla elektronik ortamda otomatik yollarla toplanır.</p>

<h2>5. Aktarım</h2>
<p>Veriler, amaçla sınırlı olarak kargo ve lojistik şirketlerine, ödeme kuruluşu ve bankalara, mali müşavir ve denetçilere, bilgi teknolojileri hizmet sağlayıcılarına ve talep halinde yetkili kamu kurum ve kuruluşlarına aktarılabilir. Yurt dışına aktarım, KVKK m.9'da öngörülen yeterlilik kararı veya standart sözleşme gibi uygun güvencelere dayanılarak yapılır. Yurt dışı teslimatlarda verilerin varış ülkesindeki taşıyıcı ve gümrük müşavirine aktarılması sözleşmenin ifası için zorunludur (m.9/6-b). Bu güvencelerin bulunmadığı diğer arızi hallerde <a href="/tr/yasal/acik-riza">açık rızanız</a> istenir.</p>

<h2>6. Saklama süreleri</h2>
<ul>
  <li>Fatura, sipariş ve ticari kayıtlar: ilgili yılın sonundan itibaren 10 yıl (TTK m.82, VUK m.253).</li>
  <li>Üyelik bilgileri: hesap kapatılana kadar ve ardından zamanaşımı süreleri boyunca.</li>
  <li>İşlem güvenliği kayıtları: 5651 sayılı Kanun ve ilgili mevzuatta öngörülen süre.</li>
  <li>Pazarlama onayı: onay geri alınana kadar; ret kaydı İYS'de tutulur.</li>
</ul>
<p>Süresi dolan veriler silinir, yok edilir veya anonim hale getirilir.</p>

<h2>7. Haklarınız (KVKK m.11)</h2>
<p>Verilerinizin işlenip işlenmediğini öğrenme, işlenmişse bilgi talep etme, işlenme amacını ve amaca uygun kullanılıp kullanılmadığını öğrenme, aktarıldığı üçüncü kişileri bilme, eksik veya yanlış işlenmişse düzeltilmesini, KVKK m.7 çerçevesinde silinmesini veya yok edilmesini isteme, bu işlemlerin aktarılan üçüncü kişilere bildirilmesini isteme, münhasıran otomatik sistemlerle analiz sonucu aleyhinize bir sonuç çıkmasına itiraz etme ve kanuna aykırı işleme nedeniyle zarara uğramanız halinde zararın giderilmesini talep etme haklarına sahipsiniz.</p>

<h2>8. Başvuru</h2>
<p>Taleplerinizi Veri Sorumlusuna Başvuru Usul ve Esasları Hakkında Tebliğ'e uygun olarak yazılı şekilde Künye'deki adrese, KEP adresimize veya sistemimizde kayıtlı e-posta adresinizden e-posta adresimize iletebilirsiniz. Başvurular en geç 30 gün içinde ücretsiz sonuçlandırılır; işlemin ayrıca bir maliyet gerektirmesi halinde Kurul'ca belirlenen tarife uygulanabilir.</p>
{% endblock %}
```

`app/web/sablonlar/yasal/tr/acik-riza.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}Açık Rıza Metni{% endblock %}
{% block metin %}
<h1>Açık Rıza Metni</h1>
<p class="yasal-ozet">Bu metin, <a href="/tr/yasal/kvkk">KVKK Aydınlatma Metni</a>'nde açıklanan işlemlerden yalnızca hukuki sebebi açık rıza olanlar içindir. Açık rıza vermek zorunlu değildir; vermemeniz alışveriş yapmanızı veya teklif istemenizi engellemez.</p>

<h2>1. Kampanya ve ürün duyuruları</h2>
<p>Kayıt formunda veya hesap ayarlarında ilgili kutuyu işaretlemeniz halinde ad, e-posta, telefon ve sipariş geçmişiniz; size uygun ürün, kampanya ve ikinci el stok duyurularının hazırlanması ve gönderilmesi amacıyla işlenir. Kutu varsayılan olarak işaretsizdir.</p>

<h2>2. Ticari elektronik ileti onayı (6563 sayılı Kanun ve İYS)</h2>
<p>Tüketicilere e-posta, SMS veya arama yoluyla ticari elektronik ileti ancak önceden alınmış onayla gönderilir. Onayınız İleti Yönetim Sistemi'ne (İYS) kaydedilir. Her iletide yer alan bağlantıdan, İYS üzerinden veya bize yazarak ücretsiz olarak ret hakkınızı kullanabilirsiniz; ret bildiriminiz üç iş günü içinde işleme alınır. Tacir ve esnaflara, mevzuatın izin verdiği durumlarda önceden onay alınmadan ileti gönderilebilir; bu durumda da ret hakkı saklıdır.</p>

<h2>3. Yurt dışına aktarım</h2>
<p>Yurt dışında bulunan e-posta, barındırma ve bulut hizmet sağlayıcılarına aktarım öncelikle KVKK m.9'daki yeterlilik kararı veya standart sözleşme gibi uygun güvencelere dayanır. Bu güvencelerin bulunmadığı ve aktarımın arızi olduğu hallerde, aktarımın muhtemel riskleri hakkında bilgilendirilerek açık rızanız istenir.</p>

<h2>4. Rızanın geri alınması</h2>
<p>Verdiğiniz açık rızayı dilediğiniz zaman hesap ayarlarınızdan veya <a href="/tr/yasal/kunye">Künye</a>'deki iletişim kanallarından geri alabilirsiniz. Geri alma, o tarihe kadar rızaya dayanılarak yapılan işlemlerin hukuka uygunluğunu etkilemez.</p>

<h2>5. Beyan</h2>
<p>İlgili kutuyu işaretleyerek, KVKK Aydınlatma Metni'ni okuduğumu; yukarıda belirtilen amaçlarla kişisel verilerimin işlenmesine özgür irademle, belirli bir konuya ilişkin ve bilgilendirilmiş olarak rıza gösterdiğimi kabul ederim.</p>
{% endblock %}
```

`app/web/sablonlar/yasal/tr/cerez.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}Çerez Politikası{% endblock %}
{% block metin %}
<h1>Çerez Politikası</h1>
<p class="yasal-ozet">Bu sitede yalnızca sitenin çalışması için zorunlu birinci taraf çerezler kullanılır. Analitik, reklam veya üçüncü taraf takip çerezi kullanılmaz.</p>

<h2>1. Çerez nedir?</h2>
<p>Çerez, ziyaret ettiğiniz internet sitesi tarafından tarayıcınıza kaydedilen küçük bir metin dosyasıdır. Çerezler oturumunuzun açık kalması, sepetinizin hatırlanması ve formların güvenle gönderilmesi gibi işlevler için kullanılır.</p>

<h2>2. Kullandığımız çerezler</h2>
<table>
  <thead><tr><th>Çerez</th><th>Tür</th><th>Amaç</th><th>Süre</th></tr></thead>
  <tbody>
    <tr><td><code>cr_oturum</code></td><td>Zorunlu, birinci taraf</td><td>Oturum, sepet, form güvenlik jetonu (CSRF), seçilen ülke ve giriş durumu</td><td>14 gün</td></tr>
    <tr><td>Dil tercihi çerezi</td><td>Zorunlu (işlevsel), birinci taraf</td><td>Seçtiğiniz arayüz dilinin (TR/EN) hatırlanması</td><td>En fazla 1 yıl</td></tr>
    <tr><td>Çerez bandı tercihi</td><td>Zorunlu, birinci taraf</td><td>Çerez bilgilendirmesini gördüğünüzün hatırlanması</td><td>En fazla 1 yıl</td></tr>
  </tbody>
</table>

<h2>3. Hukuki dayanak</h2>
<p>Zorunlu çerezler, talep ettiğiniz hizmetin sunulması için gereklidir ve KVKK m.5/2-c (sözleşmenin ifası) ile m.5/2-f (meşru menfaat) kapsamında, açık rıza aranmaksızın kullanılır. Kişisel Verileri Koruma Kurumu'nun Çerez Uygulamaları Hakkında Rehberi dikkate alınmıştır. İleride analitik veya pazarlama çerezi kullanılması halinde bu çerezler yalnızca açık rızanızla etkinleştirilecek ve bu politika güncellenecektir.</p>

<h2>4. Ürün görselleri</h2>
<p>Ürün görselleri şirketimize ait www.ceylanrobot.com adresinden yüklenir. Bu sırada tarayıcınız teknik olarak IP adresinizi o sunucuya iletir; bu sunucu çerez yerleştirmez.</p>

<h2>5. Çerezleri yönetme</h2>
<p>Tarayıcınızın ayarlarından çerezleri silebilir veya engelleyebilirsiniz. Zorunlu çerezleri engellemeniz halinde giriş, sepet ve ödeme işlemleri çalışmaz. Kişisel verilerinizle ilgili haklarınız için <a href="/tr/yasal/kvkk">KVKK Aydınlatma Metni</a>'ne bakınız.</p>
{% endblock %}
```

`app/web/sablonlar/yasal/tr/gizlilik.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}Gizlilik Politikası (GDPR){% endblock %}
{% block metin %}
<h1>Gizlilik Politikası (AB Genel Veri Koruma Tüzüğü – GDPR)</h1>
<p class="yasal-ozet">Avrupa Birliği ve Avrupa Ekonomik Alanı'ndaki kişilere ürün sunduğumuz için bu kişilere ait verilerin işlenmesinde GDPR m.3(2)(a) uyarınca Tüzük de uygulanır. Türkiye'deki kullanıcılar için ayrıca <a href="/tr/yasal/kvkk">KVKK Aydınlatma Metni</a> geçerlidir.</p>

<h2>1. Veri sorumlusu</h2>
<p>MUSTAFA CEYLAN ENDÜSTRİ A.Ş., K.O.S.B. 3. Sk., No: 7, 42250 Selçuklu / Konya, Türkiye. İletişim bilgileri <a href="/tr/yasal/kunye">Künye</a>'dedir.</p>

<h2>2. AB temsilcisi</h2>
<p>GDPR m.27 uyarınca AB'de bir temsilci atanması değerlendirilmektedir. Temsilci atandığında iletişim bilgileri bu bölümde yayımlanacaktır.</p>

<h2>3. İşlenen veriler ve hukuki dayanaklar</h2>
<table>
  <thead><tr><th>Amaç</th><th>Veriler</th><th>Hukuki dayanak</th></tr></thead>
  <tbody>
    <tr><td>Hesap, sipariş, ödeme ve teslimat</td><td>Ad, firma, e-posta, telefon, adresler, KDV (VAT) numarası, sipariş kayıtları, kartın son dört hanesi</td><td>Sözleşmenin ifası – m.6(1)(b)</td></tr>
    <tr><td>Fatura, ihracat ve gümrük belgeleri</td><td>Fatura ve teslimat bilgileri</td><td>Hukuki yükümlülük – m.6(1)(c)</td></tr>
    <tr><td>Teklif talepleri ve B2B iletişim</td><td>İletişim bilgileri, talep içeriği</td><td>Sözleşme öncesi adımlar – m.6(1)(b); meşru menfaat – m.6(1)(f)</td></tr>
    <tr><td>Güvenlik ve kötüye kullanımın önlenmesi</td><td>IP adresi, oturum ve giriş kayıtları</td><td>Meşru menfaat – m.6(1)(f)</td></tr>
    <tr><td>Pazarlama iletileri</td><td>E-posta, tercihler</td><td>Rıza – m.6(1)(a)</td></tr>
  </tbody>
</table>

<h2>4. Alıcılar</h2>
<p>Lojistik şirketleri ve gümrük müşavirleri, ödeme kuruluşları ve bankalar, mali müşavir, bilgi teknolojileri hizmet sağlayıcıları ve yetkili kamu makamları.</p>

<h2>5. AB/AEA dışına aktarım</h2>
<p>Veri sorumlusu Türkiye'de yerleşiktir; Türkiye hakkında Avrupa Komisyonu'nun yeterlilik kararı bulunmamaktadır. Verileriniz sözleşmenin ifası için zorunlu olduğu ölçüde (m.49(1)(b)) Türkiye'ye aktarılır; hizmet sağlayıcılarla yapılan aktarımlarda Komisyon'un standart sözleşme maddeleri (2021/914) kullanılır.</p>

<h2>6. Saklama süresi</h2>
<p>Ticari ve vergi kayıtları yasal saklama süreleri boyunca (Türk hukukuna göre 10 yıla kadar), hesap verileri hesap kapatılana kadar, pazarlama verileri rıza geri alınana kadar saklanır.</p>

<h2>7. Haklarınız</h2>
<p>Erişim (m.15), düzeltme (m.16), silme (m.17), işlemeyi kısıtlama (m.18), veri taşınabilirliği (m.20) ve itiraz (m.21) haklarına sahipsiniz. Rızaya dayanan işlemlerde rızanızı dilediğiniz zaman geri alabilirsiniz. Yaşadığınız veya çalıştığınız üye devletteki denetim makamına şikâyette bulunabilirsiniz. Hakkınızda yalnızca otomatik işlemeye dayalı bir karar verilmez (m.22).</p>

<h2>8. İletişim</h2>
<p>Talepleriniz için Künye'deki e-posta adresine yazabilirsiniz. Talepler en geç bir ay içinde yanıtlanır.</p>
{% endblock %}
```

`app/web/sablonlar/yasal/tr/kullanim.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}Kullanım ve Satış Koşulları{% endblock %}
{% block metin %}
<h1>Kullanım ve Satış Koşulları</h1>
<p class="yasal-ozet">A bölümü sitenin tüm kullanıcıları için geçerlidir. B bölümü kurumsal (tacir, kamu kurumu) ve yurt dışı alıcılara yapılan satışların koşullarıdır; tüketici siparişlerinde <a href="/tr/yasal/mesafeli-satis">Mesafeli Satış Sözleşmesi</a> uygulanır.</p>

<h2>A. Sitenin kullanımı</h2>
<h3>1. Kapsam</h3>
<p>Bu site MUSTAFA CEYLAN ENDÜSTRİ A.Ş. tarafından işletilir. Siteyi kullanarak bu koşulları kabul etmiş olursunuz.</p>
<h3>2. Hesap</h3>
<p>Kayıt sırasında verdiğiniz bilgilerin doğru olmasından ve parolanızın gizliliğinden siz sorumlusunuz. Hesabınızın yetkisiz kullanıldığını fark ederseniz bize hemen bildirin.</p>
<h3>3. Ürün bilgileri ve fiyat hataları</h3>
<p>Ürün bilgileri ERP kayıtlarımızdan aktarılır. Ürün adlarında geçen marka ve modeller sahiplerine aittir ve yalnızca ürünü tanımlamak için kullanılır. Açık ve bariz bir fiyat veya bilgi hatası halinde satıcı, siparişi ödeme iadesiyle iptal etme hakkını saklı tutar; alıcıya derhal bilgi verilir.</p>
<h3>4. Yasak kullanımlar</h3>
<p>Siteden otomatik araçlarla toplu veri çekmek, güvenlik önlemlerini aşmaya çalışmak, başkası adına sipariş vermek ve siteyi hukuka aykırı amaçlarla kullanmak yasaktır.</p>
<h3>5. Fikri mülkiyet</h3>
<p>Sitenin tasarımı, metinleri ve görselleri satıcıya veya lisans verenlerine aittir; izinsiz çoğaltılamaz.</p>

<h2>B. Kurumsal ve yurt dışı satış koşulları</h2>
<h3>1. Uygulama alanı</h3>
<p>Bu koşullar, ticari veya mesleki amaçla satın alan alıcılar ile Türkiye dışına teslim edilen siparişler için geçerlidir. Bu alımlarda cayma hakkı yoktur; TBK ve TTK hükümleri uygulanır.</p>
<h3>2. Siparişin kabulü</h3>
<p>Alıcının siparişi bir icaptır; sözleşme ödemenin onaylanmasıyla kurulur. Robotlar, pozisyonerler ve 15.000 € (KDV hariç) üzerindeki ürünler yalnızca yazılı teklifle satılır; teklifte yazan koşullar bu koşullardan önce gelir.</p>
<h3>3. Fiyat ve ödeme</h3>
<p>Fiyatlar euro cinsinden ve KDV hariç gösterilir. Türkiye'ye teslimatta KDV ayrıca eklenir ve tahsilat Türk lirası ile yapılır; çevrimde ödeme anındaki TCMB döviz satış kuru kullanılır ve siparişe kaydedilir. Türkiye dışına teslimatta KDV Kanunu m.11/1-a kapsamında ihracat istisnası uygulanır ve tahsilat euro ile yapılır.</p>
<h3>4. Teslim ve hasarın geçişi</h3>
<p>Türkiye içinde kargo ile teslimde hasar, ürünün alıcıya tesliminde; fabrikadan teslimde, ürünün Konya tesisimizde alıcıya veya taşıyıcısına tesliminde geçer. Yurt dışı teslimatlar DAP (Incoterms 2020) koşuluyla yapılır: gümrük vergileri, ithalat vergileri, harçlar ve ithalat formaliteleri alıcıya aittir. Navlun ayrıca teklif edilir.</p>
<h3>5. Muayene ve ihbar</h3>
<p>Alıcı ürünü teslimde muayene eder ve ayıpları TTK m.23'te öngörülen sürelerde yazılı olarak bildirir; ayrıntılar <a href="/tr/yasal/iade">İade ve Cayma</a> sayfasındadır.</p>
<h3>6. Garanti</h3>
<p>Garanti kapsamı ve ikinci el ürünlerdeki sınırlamalar <a href="/tr/yasal/garanti">Garanti Koşulları</a>'nda düzenlenmiştir.</p>
<h3>7. Sorumluluğun sınırlandırılması</h3>
<p>Satıcının bir siparişten doğan toplam sorumluluğu o siparişin bedeliyle sınırlıdır. Bu sınırlama kast ve ağır ihmal hallerinde uygulanmaz (TBK m.115).</p>
<h3>8. İhracat kontrolü ve yaptırımlar</h3>
<p>Alıcı, ürünleri uluslararası yaptırım listelerindeki kişi, kuruluş veya ülkelere ve askeri son kullanıma devretmeyeceğini, ihracat ve yeniden ihracat mevzuatına uyacağını taahhüt eder. Satıcı, bu konuda şüphe doğuran siparişleri reddedebilir.</p>
<h3>9. Mücbir sebep</h3>
<p>Doğal afet, salgın, savaş, grev, enerji kesintisi, tedarik zinciri kesintisi ve resmi makam kararları gibi tarafların kontrolü dışındaki olaylar süresince yükümlülükler askıya alınır.</p>
<h3>10. Uygulanacak hukuk ve yetki</h3>
<p>Bu koşullara Türk hukuku uygulanır; uyuşmazlıklarda Konya mahkemeleri ve icra daireleri yetkilidir. Yurt dışı satışlarda Milletlerarası Mal Satımına İlişkin Sözleşmeler Hakkında Birleşmiş Milletler Antlaşması'nın (CISG) uygulanıp uygulanmayacağı hukuki onay sürecinde kesinleştirilecektir.</p>
{% endblock %}
```

`app/web/sablonlar/yasal/tr/kunye.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}Künye{% endblock %}
{% block metin %}
<h1>Künye</h1>
<p class="yasal-ozet">6563 sayılı Elektronik Ticaretin Düzenlenmesi Hakkında Kanun m.3 ve Elektronik Ticarette Hizmet Sağlayıcı ve Aracı Hizmet Sağlayıcılar Hakkında Yönetmelik uyarınca hizmet sağlayıcı bilgileri.</p>

<h2>Hizmet sağlayıcı</h2>
<dl class="kunye">
  <dt>Ticaret unvanı</dt><dd>MUSTAFA CEYLAN ENDÜSTRİ A.Ş.</dd>
  <dt>Marka</dt><dd>Ceylan Robot</dd>
  <dt>Merkez adresi</dt><dd>K.O.S.B. 3. Sk., No: 7, 42250 Selçuklu / Konya</dd>
  <dt>MERSİS numarası</dt><dd>[doldurulacak]</dd>
  <dt>Ticaret sicil müdürlüğü ve sicil numarası</dt><dd>[doldurulacak]</dd>
  <dt>Vergi dairesi ve vergi kimlik numarası</dt><dd>[doldurulacak]</dd>
</dl>

<h2>İletişim</h2>
<dl class="kunye">
  <dt>Telefon</dt><dd>[doldurulacak]</dd>
  <dt>E-posta</dt><dd>[doldurulacak]</dd>
  <dt>KEP adresi</dt><dd>[doldurulacak]</dd>
</dl>

<h2>Kayıt ve üyelikler</h2>
<dl class="kunye">
  <dt>ETBİS kayıt bilgisi</dt><dd>[doldurulacak]</dd>
  <dt>Üyesi olunan meslek kuruluşu</dt><dd>[doldurulacak]</dd>
  <dt>VERBİS kayıt durumu</dt><dd>[doldurulacak]</dd>
  <dt>Barındırma (yer sağlayıcı)</dt><dd>[doldurulacak]</dd>
</dl>

<h2>Açıklama</h2>
<p>Bu sayfadaki "[doldurulacak]" olarak işaretli bilgiler, gerçek site yayına alınmadan önce şirket kayıtlarından doldurulacaktır. ETBİS kaydı tamamlandığında kayıt doğrulama karekodu bu sayfada yayımlanacaktır. Yasal metinler: <a href="/tr/yasal/kvkk">KVKK Aydınlatma Metni</a>, <a href="/tr/yasal/cerez">Çerez Politikası</a>, <a href="/tr/yasal/kullanim">Kullanım ve Satış Koşulları</a>.</p>
{% endblock %}
```

- [ ] **Step 7: İngilizce yasal metinleri yaz**

`app/web/sablonlar/yasal/en/on-bilgilendirme.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}Pre-Contractual Information Form{% endblock %}
{% block metin %}
<h1>Pre-Contractual Information Form</h1>
<p class="yasal-ozet">This form is provided to <strong>consumers (individual buyers)</strong> before the contract is concluded, under Turkish Consumer Protection Law No. 6502 and the Distance Contracts Regulation. Business and international buyers are subject to the <a href="/en/yasal/kullanim">Terms of Use and Sale</a>.</p>

<h2>1. Seller</h2>
<p>MUSTAFA CEYLAN ENDÜSTRİ A.Ş. (Ceylan Robot), K.O.S.B. 3. Sk., No: 7, 42250 Selçuklu / Konya, Türkiye. Registration number, phone, e-mail and registered e-mail (KEP) address are listed in the <a href="/en/yasal/kunye">Legal Notice</a>.</p>

<h2>2. Main characteristics of the goods</h2>
<p>The product name, stock code (SKU), manufacturer code, quantity and condition (new, used – tested, used – as is) are shown on the product page and in the order summary at checkout. Condition definitions for used goods are given in the <a href="/en/yasal/garanti">Warranty Terms</a>. Defects and signs of use expressly stated on the product page form part of the description of the goods.</p>

<h2>3. Price and payment</h2>
<p>Prices are shown in Turkish lira including VAT. For euro-based items the lira amount is calculated with the Central Bank of the Republic of Türkiye (CBRT) selling rate and fixed at checkout; if the rate changes, the new amount is presented for your approval before payment. Shipping is shown as a separate line.</p>
<p>Payment is taken in advance by debit or credit card with 3D Secure. Card details are not stored by the seller; only the last four digits are kept with the order. Orders not paid within 30 minutes are cancelled automatically.</p>

<h2>4. Delivery</h2>
<p>Goods are shipped to your address in Türkiye or collected from our plant in Konya. Delivery takes place within 30 days of the order at the latest. Lead times for items not in stock are confirmed after the order; if the 30-day period would be exceeded you may terminate the contract and the amount paid is refunded within 14 days.</p>

<h2>5. Right of withdrawal</h2>
<p>You may withdraw from the contract within 14 days of receiving the goods without giving any reason and without penalty. For goods delivered separately, the period starts with delivery of the last item. A written notice or a notice on a durable medium such as e-mail within this period is sufficient.</p>
<p>All payments, including delivery costs, are refunded within 14 days of receipt of your notice using the original payment method. You must return the goods within 10 days of your notice. Returns made with our contracted carrier are free of charge. See <a href="/en/yasal/iade">Returns and Withdrawal</a> for details.</p>

<h2>6. Exceptions to the right of withdrawal</h2>
<ul>
  <li>Goods made, programmed or assembled to your specifications (for example a controller or robot cell configured for you),</li>
  <li>Goods which, by their nature, are inseparably mixed with other items after delivery,</li>
  <li>Software licences and digital content once unsealed.</li>
</ul>
<p>The buyer is liable for any diminished value resulting from handling or installation beyond what is necessary to establish the nature of the goods.</p>

<h2>7. Defective goods and complaints</h2>
<p>For defective goods you may exercise your statutory rights under Article 11 of Law No. 6502 (withdrawal, price reduction, free repair or replacement). These rights also apply to used goods; however, defects expressly disclosed before the sale and normal wear appropriate to the age of the item are not defects.</p>

<h2>8. Dispute resolution</h2>
<p>Complaints may be submitted to the consumer arbitration committee within the monetary limits announced annually by the Ministry of Trade, and to consumer courts above those limits. Where required by law, mediation must be attempted before filing a lawsuit.</p>

<h2>9. Acceptance</h2>
<p>By ticking the box at checkout you confirm that you have read this form and received the above information before concluding the contract. The form and order details are sent to you on a durable medium with the order confirmation.</p>
{% endblock %}
```

`app/web/sablonlar/yasal/en/mesafeli-satis.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}Distance Sales Agreement{% endblock %}
{% block metin %}
<h1>Distance Sales Agreement</h1>
<p class="yasal-ozet">This agreement applies only to <strong>consumers</strong> buying for non-commercial purposes. Business and international buyers are subject to the <a href="/en/yasal/kullanim">Terms of Use and Sale</a>.</p>

<h2>Article 1 – Parties</h2>
<p><strong>Seller:</strong> MUSTAFA CEYLAN ENDÜSTRİ A.Ş., K.O.S.B. 3. Sk., No: 7, 42250 Selçuklu / Konya, Türkiye. Further details are given in the <a href="/en/yasal/kunye">Legal Notice</a>.</p>
<p><strong>Buyer:</strong> The individual identified by the registered account details at the time of the order.</p>

<h2>Article 2 – Subject</h2>
<p>The subject of this agreement is the sale and delivery of the goods ordered electronically on the website, whose characteristics and price are stated in the order summary, in accordance with Law No. 6502 and the Distance Contracts Regulation.</p>

<h2>Article 3 – Goods, price and payment</h2>
<p>Product details, quantity, VAT-inclusive price, shipping cost and total are stated in the order summary and confirmation and form an integral part of this agreement. For euro-based items the CBRT selling rate fixed at payment is applied and recorded with the order. Payment is made in advance by card with 3D Secure. If payment is not completed within 30 minutes, the order is cancelled and no contract is formed.</p>

<h2>Article 4 – Delivery</h2>
<p>Goods are delivered to the buyer or a person designated by the buyer within 30 days of the order at the latest. For collection from our plant the date is agreed between the parties. The buyer checks the packaging on delivery and has a damage report drawn up by the carrier if the parcel is damaged. The seller bears the risk until delivery to the buyer.</p>

<h2>Article 5 – Seller's obligations</h2>
<ul>
  <li>To deliver goods that match the order and, for used goods, the stated condition definition,</li>
  <li>To supply the manual, test record and warranty certificate where applicable,</li>
  <li>To issue and send the invoice,</li>
  <li>If the goods cannot be supplied, to inform the buyer within 3 days and refund the amount within 14 days.</li>
</ul>

<h2>Article 6 – Buyer's obligations</h2>
<ul>
  <li>To provide accurate delivery and billing details,</li>
  <li>To use the goods in line with the manual and safety instructions and have industrial equipment installed by competent persons,</li>
  <li>To keep account credentials secure.</li>
</ul>

<h2>Article 7 – Right of withdrawal</h2>
<p>The buyer may withdraw within 14 days of delivery without giving reasons and without penalty, by written notice or notice on a durable medium. The seller refunds all payments including delivery costs within 14 days of receiving the notice; the buyer returns the goods within 10 days. Exceptions and the return procedure are listed under <a href="/en/yasal/iade">Returns and Withdrawal</a>.</p>

<h2>Article 8 – Defective goods</h2>
<p>For defective goods the buyer may exercise the rights under Article 11 of Law No. 6502. Liability for defects is subject to a two-year limitation period from delivery, even if the defect appears later, except where the seller concealed the defect through gross fault or fraud. Defects expressly disclosed before the sale of used goods are not defects. See the <a href="/en/yasal/garanti">Warranty Terms</a>.</p>

<h2>Article 9 – Personal data</h2>
<p>Personal data are processed as described in the <a href="/en/yasal/kvkk">Personal Data Protection Notice</a> and the <a href="/en/yasal/gizlilik">Privacy Policy</a>.</p>

<h2>Article 10 – Disputes and entry into force</h2>
<p>Consumer arbitration committees within the monetary limits, and consumer courts above them, have jurisdiction. The agreement is concluded when the buyer accepts the Pre-Contractual Information Form and this agreement at checkout and completes payment. The text and order details are sent to the buyer on a durable medium and kept by the seller for the period required by law.</p>
{% endblock %}
```

`app/web/sablonlar/yasal/en/iade.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}Returns and Withdrawal{% endblock %}
{% block metin %}
<h1>Returns and Right of Withdrawal</h1>
<p class="yasal-ozet">Individual consumers have a 14-day right of withdrawal. Business (commercial) purchases carry no right of withdrawal; returns are possible only under the contractual terms below.</p>

<h2>A. Individual (consumer) buyers</h2>
<h3>1. 14-day right of withdrawal</h3>
<p>You may withdraw within 14 days of receiving the goods without giving reasons. For goods delivered separately, the period starts with delivery of the last item.</p>
<h3>2. How to withdraw</h3>
<ol>
  <li>Notify us in writing or by e-mail (see the Legal Notice), stating your order number and the item. No reason is required.</li>
  <li>Return the goods within 10 days of your notice, if possible with original packaging, accessories and documents, using the contracted carrier we name.</li>
  <li>All payments including delivery costs are refunded to your card within 14 days of receipt of your notice. The refund may be withheld until the goods are received or proof of dispatch is provided.</li>
</ol>
<h3>3. Return costs</h3>
<p>Returns with our contracted carrier are free of charge; if you choose another carrier, the cost is yours. For heavy or bulky items (e.g. robots, positioners) return transport is arranged together with the seller.</p>
<h3>4. Exceptions</h3>
<ul>
  <li>Goods made, programmed or assembled to your specifications,</li>
  <li>Unsealed software licences and digital content,</li>
  <li>Goods inseparably mixed with other items after delivery.</li>
</ul>
<h3>5. Defective goods</h3>
<p>Independently of the withdrawal period, your statutory rights for defective goods under Law No. 6502 apply for two years. Return transport of defective goods is paid by the seller.</p>

<h2>B. Business buyers (B2B)</h2>
<p>For purchases made for commercial or professional purposes, Law No. 6502 does not apply and there is <strong>no right of withdrawal</strong>. The relationship is governed by the Turkish Code of Obligations (TBK), the Turkish Commercial Code (TTK) and the <a href="/en/yasal/kullanim">Terms of Use and Sale</a>.</p>
<ul>
  <li><strong>Inspection and notice:</strong> The buyer must inspect the goods on delivery (TBK Article 223, TTK Article 23). Obvious defects must be notified in writing within 2 days of delivery, defects that are not obvious within 8 days following inspection, and hidden defects that cannot be found by ordinary inspection as soon as they appear. Goods are deemed accepted for defects not notified in time.</li>
  <li><strong>Wrong or short delivery:</strong> Items not matching the order are replaced or refunded free of charge, including transport.</li>
  <li><strong>Contractual returns:</strong> Any other return requires the seller's written approval. If approved, unopened and unused standard items may be returned subject to a restocking deduction stated at approval.</li>
  <li><strong>Non-returnable:</strong> items configured, programmed or manufactured for the buyer and items sold "used – as is".</li>
</ul>

<h2>C. International buyers</h2>
<p>International deliveries are made DAP (Incoterms 2020); customs duties, import taxes and charges in the destination country are borne by the buyer. Defects must be notified within the periods in section B. Unless the seller is at fault, return freight and export/import formalities are borne by the buyer. Taxes and duties paid in the destination country are not refunded by the seller.</p>

<h2>D. Used goods</h2>
<p>The definitions "used – tested" and "used – as is" and the related warranty terms are given in the <a href="/en/yasal/garanti">Warranty Terms</a>. Consumers' withdrawal and statutory defect rights also apply to used goods.</p>
{% endblock %}
```

`app/web/sablonlar/yasal/en/garanti.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}Warranty Terms{% endblock %}
{% block metin %}
<h1>Warranty Terms</h1>
<p class="yasal-ozet">Warranty coverage depends on the condition of the item (new / used – tested / used – as is) and on whether the buyer is a consumer or a business. The condition is shown as a badge on the product page.</p>

<h2>1. Condition definitions</h2>
<dl>
  <dt><strong>New</strong></dt>
  <dd>Unused item in original packaging. The manufacturer's warranty applies.</dd>
  <dt><strong>Used – tested</strong></dt>
  <dd>Previously used item that passed visual inspection, power-up and basic function tests in the Ceylan Robot workshop before dispatch. The test scope and result are stated on the product page and in the test record supplied with the item. Cosmetic signs of use may be present.</dd>
  <dt><strong>Used – as is</strong></dt>
  <dd>Previously used item sold in its current condition, without or with only partial function testing. Known defects are stated on the product page. Suitable for spare-part or repair purposes.</dd>
  <dt><strong>Not specified</strong></dt>
  <dd>Condition not yet recorded; please confirm with our sales team before ordering.</dd>
</dl>

<h2>2. Individual (consumer) buyers</h2>
<ul>
  <li>New items carry the manufacturer's warranty; for goods that must be sold with a warranty certificate, the period is at least two years.</li>
  <li>For all items, including used ones, the statutory defect provisions of Law No. 6502 apply, with a two-year limitation period from delivery.</li>
  <li>The words "as is" do not remove a consumer's statutory rights; however, defects expressly disclosed on the product page before the sale and normal wear appropriate to the item's age are not defects.</li>
  <li>For "used – tested" items the seller additionally undertakes for 6 months from delivery that the functions listed in the test record will work. This period will be confirmed in the legal and commercial approval process.</li>
  <li>Repairs under warranty are completed within 20 working days at most.</li>
</ul>

<h2>3. Business buyers (B2B)</h2>
<ul>
  <li><strong>New:</strong> The seller's liability is limited to the terms and duration of the manufacturer's warranty.</li>
  <li><strong>Used – tested:</strong> 6-month function warranty from delivery, limited to repair or replacement and, where neither is possible, a refund.</li>
  <li><strong>Used – as is:</strong> The seller's liability for defects is excluded by contract. The buyer accepts the item in its current condition, having been given the opportunity to inspect it. The exclusion does not apply where the seller fraudulently concealed a defect or acted with gross fault (Turkish Code of Obligations, Article 221).</li>
  <li><strong>Indirect loss:</strong> The seller is not liable for indirect loss such as lost production, lost profit or downtime, except in cases of intent or gross negligence (TBK Article 115).</li>
  <li><strong>Inspection and notice:</strong> The periods of TTK Article 23 apply; see <a href="/en/yasal/iade">Returns and Withdrawal</a>.</li>
</ul>

<h2>4. Exclusions</h2>
<ul>
  <li>Installation, repair or interference by unauthorised persons,</li>
  <li>Use contrary to the manual, overload, collision, unsuitable power supply or environment,</li>
  <li>Consumables and wear parts (cables, belts, batteries, seals, filters, brushes, etc.),</li>
  <li>Software, parameter or programming changes made by the buyer,</li>
  <li>Damage from transport or storage by the buyer after delivery.</li>
</ul>

<h2>5. Making a claim</h2>
<p>Contact our technical support with the order number, serial number, a description of the fault and, if possible, photos or video (contact details in the <a href="/en/yasal/kunye">Legal Notice</a>). Diagnosis is carried out remotely or in our workshop. Transport is paid by the seller for warranty work and by the buyer otherwise; a quotation is given before any non-warranty repair.</p>
{% endblock %}
```

`app/web/sablonlar/yasal/en/kvkk.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}Personal Data Protection Notice{% endblock %}
{% block metin %}
<h1>Personal Data Protection Notice (KVKK)</h1>
<p class="yasal-ozet">This notice is provided under Article 10 of the Turkish Personal Data Protection Law No. 6698 (KVKK). Buyers in the EU/EEA should also read our <a href="/en/yasal/gizlilik">Privacy Policy (GDPR)</a>.</p>

<h2>1. Data controller</h2>
<p>MUSTAFA CEYLAN ENDÜSTRİ A.Ş., K.O.S.B. 3. Sk., No: 7, 42250 Selçuklu / Konya, Türkiye. Contact details are in the <a href="/en/yasal/kunye">Legal Notice</a>.</p>

<h2>2. Data we process</h2>
<ul>
  <li><strong>Identity:</strong> name; for sole proprietorships, the Turkish ID number used as tax number.</li>
  <li><strong>Contact:</strong> e-mail, phone, delivery and billing address.</li>
  <li><strong>Customer transactions:</strong> orders, cart, quote requests and feedback.</li>
  <li><strong>Financial:</strong> invoice details, tax office and number, VAT ID, payment result and the last four card digits (the full card number is never stored).</li>
  <li><strong>Security:</strong> IP address, session cookie, sign-in attempts.</li>
  <li><strong>Marketing:</strong> commercial message preferences, only if you consented.</li>
</ul>

<h2>3. Purposes and legal grounds</h2>
<table>
  <thead><tr><th>Purpose</th><th>Legal ground (KVKK Article 5)</th></tr></thead>
  <tbody>
    <tr><td>Account, order, payment, delivery and quotation processes</td><td>Performance of a contract (5/2-c)</td></tr>
    <tr><td>Invoicing, commercial books and tax records</td><td>Legal obligation (5/2-ç)</td></tr>
    <tr><td>Information security and fraud prevention</td><td>Legitimate interest (5/2-f), legal obligation (5/2-ç)</td></tr>
    <tr><td>Handling requests, complaints and feedback</td><td>Legitimate interest (5/2-f)</td></tr>
    <tr><td>Establishing, exercising or defending legal claims</td><td>Article 5/2-e</td></tr>
    <tr><td>Campaign and product announcements</td><td>Explicit consent (5/1) and commercial message consent under Law No. 6563</td></tr>
  </tbody>
</table>

<h2>4. Collection method</h2>
<p>Data are collected electronically through the registration, order, quotation and feedback forms on the website and through cookies.</p>

<h2>5. Transfers</h2>
<p>Data may be transferred, limited to these purposes, to carriers and logistics providers, payment institutions and banks, financial advisers and auditors, IT service providers and, on request, competent public authorities. Transfers abroad rely on an adequacy decision or appropriate safeguards such as standard contracts under KVKK Article 9; transfers to carriers and customs brokers in the destination country are necessary to perform the contract (Article 9/6-b). In other occasional cases without such safeguards, your <a href="/en/yasal/acik-riza">explicit consent</a> is requested.</p>

<h2>6. Retention</h2>
<ul>
  <li>Invoices, orders and commercial records: 10 years from the end of the relevant year (TTK Article 82, Tax Procedure Law Article 253).</li>
  <li>Account data: until the account is closed, then for applicable limitation periods.</li>
  <li>Security logs: for the period required under Law No. 5651 and related legislation.</li>
  <li>Marketing consent: until withdrawn; opt-outs are recorded in the Message Management System (İYS).</li>
</ul>

<h2>7. Your rights (KVKK Article 11)</h2>
<p>You may ask whether your data are processed and request information, learn the purpose and whether data are used accordingly, know the third parties to whom data are transferred, request rectification, erasure or destruction under Article 7 and notification of these to recipients, object to adverse results arising solely from automated analysis, and claim compensation for damage caused by unlawful processing.</p>

<h2>8. Applications</h2>
<p>Send your request in writing to our address, to our registered e-mail (KEP) address, or by e-mail from the address registered with us, in accordance with the Communiqué on the Procedures and Principles of Applications to the Data Controller. Requests are answered free of charge within 30 days; where the action entails an additional cost, the fee set by the Board may apply.</p>
{% endblock %}
```

`app/web/sablonlar/yasal/en/acik-riza.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}Explicit Consent{% endblock %}
{% block metin %}
<h1>Explicit Consent Text</h1>
<p class="yasal-ozet">This text covers only the processing described in the <a href="/en/yasal/kvkk">Personal Data Protection Notice</a> whose legal ground is explicit consent. Giving consent is optional; refusing it does not prevent you from buying or requesting a quote.</p>

<h2>1. Campaign and product announcements</h2>
<p>If you tick the relevant box at registration or in your account settings, your name, e-mail, phone and order history are processed to prepare and send relevant product, campaign and used-stock announcements. The box is unticked by default.</p>

<h2>2. Commercial electronic messages (Law No. 6563 and İYS)</h2>
<p>Commercial e-mails, text messages or calls are sent to consumers only with prior consent, which is recorded in the Turkish Message Management System (İYS). You can opt out free of charge via the link in every message, through İYS or by writing to us; opt-outs are processed within three working days. Messages to merchants and tradespeople may be sent without prior consent where the law allows; the right to opt out still applies.</p>

<h2>3. Transfers abroad</h2>
<p>Transfers to e-mail, hosting and cloud providers abroad rely primarily on an adequacy decision or appropriate safeguards such as standard contracts under KVKK Article 9. Where no such safeguard exists and the transfer is occasional, your explicit consent is requested after you are informed of the possible risks.</p>

<h2>4. Withdrawing consent</h2>
<p>You may withdraw your consent at any time in your account settings or via the contact channels in the <a href="/en/yasal/kunye">Legal Notice</a>. Withdrawal does not affect the lawfulness of processing carried out before it.</p>

<h2>5. Declaration</h2>
<p>By ticking the relevant box I confirm that I have read the Personal Data Protection Notice and that I give my consent freely, specifically and on an informed basis to the processing of my personal data for the purposes stated above.</p>
{% endblock %}
```

`app/web/sablonlar/yasal/en/cerez.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}Cookie Policy{% endblock %}
{% block metin %}
<h1>Cookie Policy</h1>
<p class="yasal-ozet">This website uses only first-party cookies that are strictly necessary for it to work. No analytics, advertising or third-party tracking cookies are used.</p>

<h2>1. What is a cookie?</h2>
<p>A cookie is a small text file saved in your browser by a website. Cookies keep you signed in, remember your cart and protect forms against misuse.</p>

<h2>2. Cookies we use</h2>
<table>
  <thead><tr><th>Cookie</th><th>Type</th><th>Purpose</th><th>Duration</th></tr></thead>
  <tbody>
    <tr><td><code>cr_oturum</code></td><td>Strictly necessary, first-party</td><td>Session, cart, form security token (CSRF), selected country and sign-in state</td><td>14 days</td></tr>
    <tr><td>Language preference cookie</td><td>Strictly necessary (functional), first-party</td><td>Remembering your interface language (TR/EN)</td><td>Up to 1 year</td></tr>
    <tr><td>Cookie banner preference</td><td>Strictly necessary, first-party</td><td>Remembering that you have seen the cookie notice</td><td>Up to 1 year</td></tr>
  </tbody>
</table>

<h2>3. Legal basis</h2>
<p>Strictly necessary cookies are required to provide the service you request and are used without consent on the grounds of contract performance and legitimate interest (KVKK Article 5/2-c and 5/2-f; GDPR Article 6(1)(b) and (f), in line with Article 5(3) of the ePrivacy Directive). The Turkish Data Protection Authority's guidance on cookies has been taken into account. Should analytics or marketing cookies be introduced, they will be activated only with your consent and this policy will be updated.</p>

<h2>4. Product images</h2>
<p>Product images are loaded from our company website www.ceylanrobot.com. Your browser technically transmits your IP address to that server; it does not set cookies.</p>

<h2>5. Managing cookies</h2>
<p>You can delete or block cookies in your browser settings. If you block strictly necessary cookies, sign-in, cart and checkout will not work. For your data protection rights see the <a href="/en/yasal/kvkk">Personal Data Protection Notice</a> and the <a href="/en/yasal/gizlilik">Privacy Policy</a>.</p>
{% endblock %}
```

`app/web/sablonlar/yasal/en/gizlilik.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}Privacy Policy (GDPR){% endblock %}
{% block metin %}
<h1>Privacy Policy (EU General Data Protection Regulation – GDPR)</h1>
<p class="yasal-ozet">Because we offer goods to people in the European Union and the European Economic Area, the GDPR applies to the processing of their data under Article 3(2)(a). Users in Türkiye should also read the <a href="/en/yasal/kvkk">Personal Data Protection Notice</a>.</p>

<h2>1. Controller</h2>
<p>MUSTAFA CEYLAN ENDÜSTRİ A.Ş., K.O.S.B. 3. Sk., No: 7, 42250 Selçuklu / Konya, Türkiye. Contact details are in the <a href="/en/yasal/kunye">Legal Notice</a>.</p>

<h2>2. EU representative</h2>
<p>The appointment of a representative in the Union under Article 27 GDPR is being assessed. Once appointed, the representative's contact details will be published in this section.</p>

<h2>3. Data and legal bases</h2>
<table>
  <thead><tr><th>Purpose</th><th>Data</th><th>Legal basis</th></tr></thead>
  <tbody>
    <tr><td>Account, order, payment and delivery</td><td>Name, company, e-mail, phone, addresses, VAT ID, order records, last four card digits</td><td>Contract – Art. 6(1)(b)</td></tr>
    <tr><td>Invoicing, export and customs documents</td><td>Billing and delivery details</td><td>Legal obligation – Art. 6(1)(c)</td></tr>
    <tr><td>Quote requests and B2B communication</td><td>Contact details, request content</td><td>Pre-contractual steps – Art. 6(1)(b); legitimate interest – Art. 6(1)(f)</td></tr>
    <tr><td>Security and abuse prevention</td><td>IP address, session and sign-in logs</td><td>Legitimate interest – Art. 6(1)(f)</td></tr>
    <tr><td>Marketing messages</td><td>E-mail, preferences</td><td>Consent – Art. 6(1)(a)</td></tr>
  </tbody>
</table>

<h2>4. Recipients</h2>
<p>Carriers and customs brokers, payment institutions and banks, our financial adviser, IT service providers and competent public authorities.</p>

<h2>5. Transfers outside the EU/EEA</h2>
<p>The controller is established in Türkiye, for which no European Commission adequacy decision exists. Your data are transferred to Türkiye to the extent necessary to perform the contract (Art. 49(1)(b)); transfers involving service providers use the Commission's standard contractual clauses (2021/914).</p>

<h2>6. Retention</h2>
<p>Commercial and tax records are kept for the statutory periods (up to 10 years under Turkish law), account data until the account is closed, and marketing data until consent is withdrawn.</p>

<h2>7. Your rights</h2>
<p>You have the rights of access (Art. 15), rectification (Art. 16), erasure (Art. 17), restriction (Art. 18), data portability (Art. 20) and objection (Art. 21). Where processing is based on consent you may withdraw it at any time. You may lodge a complaint with the supervisory authority of the Member State where you live or work. No decisions based solely on automated processing are taken about you (Art. 22).</p>

<h2>8. Contact</h2>
<p>Send requests to the e-mail address in the Legal Notice. We respond within one month.</p>
{% endblock %}
```

`app/web/sablonlar/yasal/en/kullanim.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}Terms of Use and Sale{% endblock %}
{% block metin %}
<h1>Terms of Use and Sale</h1>
<p class="yasal-ozet">Part A applies to all users of the website. Part B sets out the terms for sales to business buyers (merchants, public bodies) and international buyers; consumer orders are governed by the <a href="/en/yasal/mesafeli-satis">Distance Sales Agreement</a>.</p>

<h2>A. Use of the website</h2>
<h3>1. Scope</h3>
<p>This website is operated by MUSTAFA CEYLAN ENDÜSTRİ A.Ş. By using it you accept these terms.</p>
<h3>2. Account</h3>
<p>You are responsible for the accuracy of your registration details and for keeping your password confidential. Inform us immediately of any unauthorised use.</p>
<h3>3. Product information and pricing errors</h3>
<p>Product data are taken from our ERP records. Brands and models in product names belong to their owners and are used only to identify the product. In the event of an obvious pricing or information error, the seller may cancel the order with a full refund and will inform the buyer without delay.</p>
<h3>4. Prohibited use</h3>
<p>Automated bulk data extraction, attempts to bypass security measures, ordering in another person's name and any unlawful use are prohibited.</p>
<h3>5. Intellectual property</h3>
<p>The design, texts and images of the website belong to the seller or its licensors and may not be reproduced without permission.</p>

<h2>B. Business and international terms of sale</h2>
<h3>1. Scope</h3>
<p>These terms apply to purchases for commercial or professional purposes and to orders delivered outside Türkiye. There is no right of withdrawal for these purchases; the Turkish Code of Obligations (TBK) and Turkish Commercial Code (TTK) apply.</p>
<h3>2. Acceptance of orders</h3>
<p>The buyer's order is an offer; the contract is formed when payment is confirmed. Robots, positioners and items above €15,000 (excl. VAT) are sold only on written quotation, whose terms take precedence over these terms.</p>
<h3>3. Price and payment</h3>
<p>Prices are shown in euro excluding VAT. For delivery in Türkiye VAT is added and payment is collected in Turkish lira, converted at the CBRT selling rate fixed at payment and recorded with the order. For delivery outside Türkiye the export VAT exemption (Turkish VAT Law Article 11/1-a) applies and payment is collected in euro.</p>
<h3>4. Delivery and passing of risk</h3>
<p>For courier delivery in Türkiye risk passes on delivery to the buyer; for collection, when the goods are handed over to the buyer or its carrier at our plant in Konya. International deliveries are made DAP (Incoterms 2020): customs duties, import taxes, charges and import formalities are borne by the buyer. Freight is quoted separately.</p>
<h3>5. Inspection and notice</h3>
<p>The buyer inspects the goods on delivery and notifies defects in writing within the periods of TTK Article 23; see <a href="/en/yasal/iade">Returns and Withdrawal</a>.</p>
<h3>6. Warranty</h3>
<p>Warranty coverage and the limitations for used goods are set out in the <a href="/en/yasal/garanti">Warranty Terms</a>.</p>
<h3>7. Limitation of liability</h3>
<p>The seller's total liability arising from an order is limited to the price of that order. This limitation does not apply in cases of intent or gross negligence (TBK Article 115).</p>
<h3>8. Export control and sanctions</h3>
<p>The buyer undertakes not to transfer the goods to persons, entities or countries on international sanctions lists or for military end use, and to comply with export and re-export regulations. The seller may refuse orders that raise concerns in this respect.</p>
<h3>9. Force majeure</h3>
<p>Obligations are suspended for the duration of events beyond the parties' control, such as natural disasters, epidemics, war, strikes, power outages, supply chain disruptions and decisions of authorities.</p>
<h3>10. Governing law and jurisdiction</h3>
<p>These terms are governed by Turkish law; the courts and enforcement offices of Konya have jurisdiction. Whether the UN Convention on Contracts for the International Sale of Goods (CISG) applies to international sales will be settled in the legal approval process.</p>
{% endblock %}
```

`app/web/sablonlar/yasal/en/kunye.html`:

```html
{% extends "yasal/_taban.html" %}
{% block baslik %}Legal Notice{% endblock %}
{% block metin %}
<h1>Legal Notice (Imprint)</h1>
<p class="yasal-ozet">Service provider information under Article 3 of the Turkish Law No. 6563 on the Regulation of Electronic Commerce and the related regulation on service providers.</p>

<h2>Service provider</h2>
<dl class="kunye">
  <dt>Trade name</dt><dd>MUSTAFA CEYLAN ENDÜSTRİ A.Ş.</dd>
  <dt>Brand</dt><dd>Ceylan Robot</dd>
  <dt>Registered address</dt><dd>K.O.S.B. 3. Sk., No: 7, 42250 Selçuklu / Konya, Türkiye</dd>
  <dt>Central Registration System (MERSİS) number</dt><dd>[doldurulacak] (to be completed)</dd>
  <dt>Trade registry office and number</dt><dd>[doldurulacak] (to be completed)</dd>
  <dt>Tax office and tax number</dt><dd>[doldurulacak] (to be completed)</dd>
</dl>

<h2>Contact</h2>
<dl class="kunye">
  <dt>Phone</dt><dd>[doldurulacak] (to be completed)</dd>
  <dt>E-mail</dt><dd>[doldurulacak] (to be completed)</dd>
  <dt>Registered e-mail (KEP)</dt><dd>[doldurulacak] (to be completed)</dd>
</dl>

<h2>Registrations and memberships</h2>
<dl class="kunye">
  <dt>E-commerce information system (ETBİS) registration</dt><dd>[doldurulacak] (to be completed)</dd>
  <dt>Professional chamber</dt><dd>[doldurulacak] (to be completed)</dd>
  <dt>Data controllers' registry (VERBİS) status</dt><dd>[doldurulacak] (to be completed)</dd>
  <dt>Hosting provider</dt><dd>[doldurulacak] (to be completed)</dd>
</dl>

<h2>Note</h2>
<p>Fields marked "[doldurulacak]" will be completed from company records before the live site is launched. Once ETBİS registration is complete, its verification QR code will be published on this page. Legal texts: <a href="/en/yasal/kvkk">Personal Data Protection Notice</a>, <a href="/en/yasal/cerez">Cookie Policy</a>, <a href="/en/yasal/kullanim">Terms of Use and Sale</a>.</p>
{% endblock %}
```

- [ ] **Step 8: Testleri çalıştır, geçtiklerini gör**

Run: `bash dagitim/test-vm.sh tests/test_web_yasal.py -q`
Expected: PASS (34 passed — 1 + 20 sayfa + 2 künye + 2 iade/garanti + 5 bilinmeyen + 2 bağlantı + 2 kayıt)

- [ ] **Step 9: Tüm test takımı**

Run: `bash dagitim/test-vm.sh tests -q`
Expected: PASS — `eksik_anahtarlar` dahil.

- [ ] **Step 10: Commit**

```bash
git add app/web/rotalar/yasal.py app/web/sablonlar/yasal/ app/web/dil/tr.json app/web/dil/en.json \
  app/web/statik/site.css tests/test_web_yasal.py
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m "feat: TR/EN yasal sayfa taslaklari ve yasal rota

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Entegrasyon durumu

`03-entegrasyon-kararlari.md` kararları bu dosyaya uygulandı:

- K4: Teslimat TR değilse ödeme formu yalnız `yurtdisi_dap` ve `fabrika` sunar; TR dışına `kargo` 400 + `hata_kodu.teslim_yurtdisi`.
- K5: `KurYok` yakalanır (`hata_kodu.kur_yok`, POST'ta 503); metin karşılaştırması yok.
- K7: Testler `from tests.conftest import csrf_al, urun_ekle` kullanır.
- K9: Rotalar `db_bagimliligi`'yi `app.web.bagimlilik`'ten alır, `/{dil:dil}/` dönüştürücüsü kullanılır; `uygulama.py` düzenlemesi yok (`ROTA_SIRASI`); şablonlar ortak `para(tutar, para_birimi)` kullanır; yönetim şablonları `taban.html`'i genişletir.
- K11: CSRF hatası `csrf_dogrula` ile 403 (testlerde doğrulanır).
- K12: Ödeme alanları `teslimat_*`/`fatura_*`, `fatura_ayni`, `teslim`, `on_bilgi_onay`, `mesafeli_onay`; müşteri girişi 303; yönetim girişi `kullanici`/`parola`; ret ve hatalı SMS sonrası `/siparis/{no}?hata=<kod>` + `[data-e2e="odeme-hata"][data-kod]` + tekrar dene bağlantısı; Görev 18 tablosundaki `sepet-kalemi`, `odemeye-gec`, `teklif-iste`, `satir-kdv`, `satir-ihracat`, `not-dap`, `odeme-gonder`, `kart-gonder`, `sms-gonder`, `odeme-hata`, `siparis-durum`, `teklif-gonder`, `teklif-no`, `yonetim-giris`, `son-esitleme` öznitelikleri eklendi. Kart son kullanma (`#kart_skt`) ve CVC (`#kart_cvc`) alanlarına bilerek `name` verilmedi; e2e bunları `id` ile doldurmalı.
- K13: 3D rotası `odeme_sim.deneme_getir` kullanır; doğrudan SQL yok.
- K14: `siparis.durum.*`/`teklif.durum.*` tanımları kaldırıldı, `siparis_durum.*`/`teklif_durum.*` kullanılır; hata metinleri `form_hata.zorunlu` ve `hata_kodu.<kod>` altında.
- K17: Yönetimde sipariş, teklif ve geri bildirim `durum_degistir` için `LookupError` 404'e çevrilir; doğrudan SQL ile varlık kontrolü yok.
- K21: Ödeme POST'u `siparis_olustur`'dan önce `kalemler()` çağırır; düşen ürünler adıyla bildirilir (409, sipariş oluşmaz).

---

### Görev 17: İşletme dosyaları — betikler, systemd birimleri, VM kurulumu ve dağıtım

**Files:**
- Create: `betikler/__init__.py` (boş; `python -m betikler.X` ve testlerden import için)
- Create: `betikler/esitle.py`
- Create: `betikler/kur_al.py`
- Create: `betikler/yedek.sh`
- Create: `betikler/yonetici_ozet.py`
- Create: `app/gecis_calistir.py`
- Create: `app/web/asgi.py`
- Create: `dagitim/systemd/cr-shop-demo.service`
- Create: `dagitim/systemd/cr-shop-esitle.service`, `dagitim/systemd/cr-shop-esitle.timer`
- Create: `dagitim/systemd/cr-shop-yedek.service`, `dagitim/systemd/cr-shop-yedek.timer`
- Create: `dagitim/systemd/cr-shop-kur.service`, `dagitim/systemd/cr-shop-kur.timer`
- Create: `dagitim/ortam.ornek`
- Create: `dagitim/kurulum-vm.sh`
- Create: `dagitim/deploy.sh` (laptopta çalışır)
- Create: `dagitim/uzak-yayinla.sh` (deploy.sh'nin VM'de, release içinden çalıştırdığı kısım)
- Kontrol (değiştirilmez, Görev 1'in): `.gitattributes` (`* text=auto eol=lf`)
- Test: `tests/test_isletme.py`

**Interfaces:**
- Consumes:
  - `app.ayarlar.ayarlari_oku(ortam: Mapping[str, str] = os.environ) -> Ayarlar` (alanlar: `db_yolu`, `kaynak_api`, `bantlar_yolu`)
  - `app.db.baglan(yol: Path) -> sqlite3.Connection`, `app.db.gecisleri_uygula(con) -> list[str]`
  - `app.esitleme.kaynak.KaynakIstemci(http: httpx.Client, taban: str, bekleme: float = 1.0, uyku: Callable[[float], None] = time.sleep)`
  - `app.esitleme.esitle.esitle(con, kaynak, bantlar, simdi: Callable[[], datetime]) -> TurSonucu` (`durum`, `api_toplam`, `cekilen`, `eklenen`, `guncellenen`, `pasiflenen`, `hata`)
  - `app.fiyat.kurallar.bantlari_oku(yol: Path) -> Bantlar`
  - `app.fiyat.kur.kur_al(con, http: httpx.Client, simdi: datetime) -> Kur`, `son_kur(con) -> Kur | None`, `kur_kaydet(con, kur, simdi)`, `Kur(tarih, eur_alis, eur_satis)`
  - `app.hesap.servis.parola_ozeti(parola: str) -> str`, `parola_dogru(parola, ozet) -> bool`
  - `app.web.uygulama.uygulama_olustur(ayarlar: Ayarlar) -> FastAPI`; `GET /saglik -> {"durum":"ok","son_esitleme":...,"urun":n}`
- Produces:
  - `betikler.esitle.calistir(ortam=os.environ, *, transport=None, uyku=time.sleep, simdi=..., cikti=sys.stdout) -> int` ve `http_istemcisi(transport=None) -> httpx.Client` (timeout 30 sn, `User-Agent: cr-shop-demo-esitleme/1.0`)
  - `betikler.kur_al.calistir(ortam=os.environ, *, transport=None, simdi=None, cikti=sys.stdout) -> int`
  - `betikler.yonetici_ozet.calistir(giris=sys.stdin, cikti=sys.stdout, hata=sys.stderr) -> int`
  - `app.gecis_calistir.calistir(ortam_dosyasi=Path("/opt/cr-shop-demo/ortam"), release=None, cikti=sys.stdout) -> int`, `ortam_dosyasi_oku(yol: Path) -> dict[str, str]`
  - `app.web.asgi.uygulama() -> FastAPI` (uvicorn `--factory app.web.asgi:uygulama`)
  - systemd birimleri: `cr-shop-demo.service`, `cr-shop-esitle.{service,timer}`, `cr-shop-yedek.{service,timer}`, `cr-shop-kur.{service,timer}`
  - sudoers (kurulum-vm.sh üretir), `crwebdemo` için parolasız YALNIZ: `/usr/bin/systemctl restart cr-shop-demo`, `/usr/bin/systemctl start cr-shop-esitle`, crshop olarak `/opt/cr-shop-demo/releases/<release>/venv/bin/python -m app.gecis_calistir`
  - Betik çıktısı: stdout'a tek satır JSON; `esitle` durumu `hata` ise ya da `kur_al` başarısızsa çıkış kodu 1

Notlar (uygulayıcı için):
- Betikler release kökünden **modül olarak** çalışır (`venv/bin/python -m betikler.esitle`). systemd'de `WorkingDirectory=/opt/cr-shop-demo/current` olduğundan `app` paketi bulunur.
- Testler Görev 0'da kurulan geliştirme ortamında depo kökünden çalışır: `python -m pytest tests/test_isletme.py -v`. Dağıtımda aynı testler VM'de, release'in kendi venv'inde çalışır.
- Laptopta `core.autocrlf=true`. Görev 1'in `.gitattributes` dosyası (`* text=auto eol=lf`) olmazsa `git archive` CRLF üretir ve VM'de bash `$'\r'` hatası verir; Adım 3 bunu kontrol eder.

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/test_isletme.py`:

```python
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
    yol.write_text(f"# yorum\n\nSHOP_DB='{db}'\nSHOP_GIZLI_ANAHTAR='abc$def'\nSHOP_YONETICI=yonetici\n",
                   encoding="utf-8")
    return yol


def test_ortam_dosyasi_tirnaklari_ve_yorumlari_isler(tmp_path):
    from app.gecis_calistir import ortam_dosyasi_oku

    db = tmp_path / "shop.db"
    assert ortam_dosyasi_oku(_ortam_dosyasi(tmp_path, db)) == {
        "SHOP_DB": str(db), "SHOP_GIZLI_ANAHTAR": "abc$def", "SHOP_YONETICI": "yonetici"}


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
```

- [ ] **Adım 2: Testleri çalıştır, başarısız olduklarını gör**

Run: `python -m pytest tests/test_isletme.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'betikler'` / `'app.gecis_calistir'` / `'app.web.asgi'` ve systemd testlerinde `FileNotFoundError` (birim dosyaları henüz yok).

- [ ] **Adım 3: `betikler/__init__.py` oluştur ve LF kuralını kontrol et**

`.gitattributes` dosyasını Görev 1 oluşturur (`* text=auto eol=lf`, K19). Bu görev dosyayı değiştirmez, yalnız kontrol eder.

Run: `touch betikler/__init__.py && grep -x '\* text=auto eol=lf' .gitattributes && git check-attr eol -- dagitim/deploy.sh betikler/yedek.sh dagitim/systemd/cr-shop-demo.service`
Expected: `* text=auto eol=lf` ve üç dosya için `eol: lf`. Dosya yoksa ya da satır eksikse dur ve Görev 1'in eksiğini bildir.

- [ ] **Adım 4: `betikler/esitle.py` yaz**

```python
"""Katalog eşitleme betiği — cr-shop-esitle.service (02:30) çalıştırır.

Çalıştırma (release kökünden): venv/bin/python -m betikler.esitle
Çıktı: stdout'a tek satır JSON (TurSonucu alanları). Durum 'hata' ise çıkış kodu 1.
'eksik' tur çıkış 0 döner: veri tutarlı kalır, günlükte ve yönetim panelinde görünür.
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import TextIO

import httpx

from app.ayarlar import ayarlari_oku
from app.db import baglan
from app.esitleme.esitle import esitle
from app.esitleme.ornek import ornek_durumlari_ata
from app.esitleme.kaynak import KaynakIstemci
from app.fiyat.kurallar import bantlari_oku

KULLANICI_AJANI = "cr-shop-demo-esitleme/1.0"
ZAMAN_ASIMI_SN = 30


def http_istemcisi(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(timeout=ZAMAN_ASIMI_SN, headers={"User-Agent": KULLANICI_AJANI}, transport=transport)


def _simdi() -> datetime:
    return datetime.now(UTC)


def calistir(
    ortam: Mapping[str, str] = os.environ,
    *,
    transport: httpx.BaseTransport | None = None,
    uyku: Callable[[float], None] = time.sleep,
    simdi: Callable[[], datetime] = _simdi,
    cikti: TextIO = sys.stdout,
) -> int:
    ayarlar = ayarlari_oku(ortam)
    bantlar = bantlari_oku(ayarlar.bantlar_yolu)
    con = baglan(ayarlar.db_yolu)
    try:
        with http_istemcisi(transport) as http:
            kaynak = KaynakIstemci(http, ayarlar.kaynak_api, uyku=uyku)
            sonuc = esitle(con, kaynak, bantlar, simdi)
        if sonuc.durum != "hata":
            with con:
                ornek_durumlari_ata(con)   # Görev 5A; idempotent
    finally:
        con.close()
    print(json.dumps(dataclasses.asdict(sonuc), ensure_ascii=False), file=cikti, flush=True)
    return 1 if sonuc.durum == "hata" else 0


if __name__ == "__main__":
    sys.exit(calistir())
```

- [ ] **Adım 5: `betikler/kur_al.py` yaz**

```python
"""TCMB EUR kuru — cr-shop-kur.service (06:00) çalıştırır.

Çalıştırma (release kökünden): venv/bin/python -m betikler.kur_al
Başarı: {"durum":"tamam",...} ve çıkış 0. Hata: {"durum":"hata",...} ve çıkış 1.
Hata durumunda veritabanına yazılmaz; site son kuru kullanmaya devam eder (kur tarihi kırmızı).
"""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TextIO

import httpx

from app.ayarlar import ayarlari_oku
from app.db import baglan
from app.fiyat.kur import kur_al, son_kur

KULLANICI_AJANI = "cr-shop-demo-kur/1.0"
ZAMAN_ASIMI_SN = 30


def calistir(
    ortam: Mapping[str, str] = os.environ,
    *,
    transport: httpx.BaseTransport | None = None,
    simdi: datetime | None = None,
    cikti: TextIO = sys.stdout,
) -> int:
    ayarlar = ayarlari_oku(ortam)
    an = simdi or datetime.now(UTC)
    con = baglan(ayarlar.db_yolu)
    try:
        try:
            with httpx.Client(timeout=ZAMAN_ASIMI_SN, headers={"User-Agent": KULLANICI_AJANI},
                              transport=transport) as http:
                with con:
                    kur = kur_al(con, http, an)
        except Exception as hata:  # ağ, HTTP durum, ayrıştırma — hepsi aynı sonuç: son kur korunur
            son = son_kur(con)
            print(json.dumps({
                "durum": "hata",
                "hata": f"{type(hata).__name__}: {hata}",
                "son_kur_tarihi": son.tarih.isoformat() if son else None,
                "son_kur_eur_satis": str(son.eur_satis) if son else None,
            }, ensure_ascii=False), file=cikti, flush=True)
            return 1
    finally:
        con.close()
    print(json.dumps({
        "durum": "tamam",
        "tarih": kur.tarih.isoformat(),
        "eur_alis": str(kur.eur_alis),
        "eur_satis": str(kur.eur_satis),
    }, ensure_ascii=False), file=cikti, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(calistir())
```

- [ ] **Adım 6: `betikler/yonetici_ozet.py` yaz**

```python
"""Yönetici parolasından SHOP_YONETICI_OZET değerini üretir (ortam dosyası için).

Kullanım (release ya da araç kopyası kökünden): venv/bin/python -m betikler.yonetici_ozet
  - Terminalde: parolayı iki kez sorar, ekranda göstermez.
  - Boru ile: stdin'in ilk satırını parola olarak okur (ör. kimlik Excel'inden okuyan betikten).
Çıktı: yalnız özet ("scrypt$..."), tek satır. Parola hiçbir yere yazılmaz.
"""
from __future__ import annotations

import getpass
import sys
from typing import TextIO

from app.hesap.servis import parola_ozeti

EN_AZ_UZUNLUK = 12


def parola_al(giris: TextIO) -> str:
    if giris.isatty():
        birinci = getpass.getpass("Yönetici parolası: ")
        ikinci = getpass.getpass("Tekrar: ")
        if birinci != ikinci:
            raise ValueError("parolalar_uyusmuyor")
        return birinci
    return giris.readline().rstrip("\r\n")


def calistir(giris: TextIO = sys.stdin, cikti: TextIO = sys.stdout, hata: TextIO = sys.stderr) -> int:
    try:
        parola = parola_al(giris)
    except ValueError:
        print("HATA: parolalar uyuşmuyor.", file=hata)
        return 1
    if len(parola) < EN_AZ_UZUNLUK:
        print(f"HATA: parola en az {EN_AZ_UZUNLUK} karakter olmalı.", file=hata)
        return 1
    print(parola_ozeti(parola), file=cikti)
    return 0


if __name__ == "__main__":
    sys.exit(calistir())
```

- [ ] **Adım 7: `betikler/yedek.sh` yaz**

```bash
#!/usr/bin/env bash
# Gece SQLite yedeği — cr-shop-yedek.service (03:00).
# Tutarlı kopya: sqlite3 ".backup" (varsa) ya da Python sqlite3 con.backup().
# Ortam: SHOP_DB (zorunlu), SHOP_YEDEK_DIZIN, SHOP_YEDEK_GUN (7), SHOP_YEDEK_ARAC (otomatik|sqlite3|python), SHOP_PYTHON (python3)
set -euo pipefail

DB="${SHOP_DB:?SHOP_DB tanımlı değil}"
YEDEK_DIZIN="${SHOP_YEDEK_DIZIN:-/opt/cr-shop-demo/yedek}"
TUTULAN_GUN="${SHOP_YEDEK_GUN:-7}"
ARAC="${SHOP_YEDEK_ARAC:-otomatik}"
PYTHON="${SHOP_PYTHON:-python3}"

if [ ! -f "$DB" ]; then
  echo "HATA: veritabanı yok: $DB" >&2
  exit 1
fi
mkdir -p "$YEDEK_DIZIN"
HEDEF="$YEDEK_DIZIN/shop-$(date +%Y%m%d).db"
GECICI="$HEDEF.yarim"
rm -f "$GECICI"

if [ "$ARAC" = "otomatik" ]; then
  if command -v sqlite3 >/dev/null 2>&1; then ARAC=sqlite3; else ARAC=python; fi
fi

case "$ARAC" in
  sqlite3)
    sqlite3 "$DB" ".backup '$GECICI'"
    ;;
  python)
    "$PYTHON" - "$DB" "$GECICI" <<'PY'
import sqlite3
import sys

kaynak = sqlite3.connect(sys.argv[1])
hedef = sqlite3.connect(sys.argv[2])
try:
    kaynak.backup(hedef)
finally:
    hedef.close()
    kaynak.close()
PY
    ;;
  *)
    echo "HATA: bilinmeyen SHOP_YEDEK_ARAC: $ARAC" >&2
    exit 1
    ;;
esac

BUTUNLUK="$("$PYTHON" -c 'import sqlite3, sys; c = sqlite3.connect(sys.argv[1]); print(c.execute("PRAGMA integrity_check").fetchone()[0]); c.close()' "$GECICI")"
if [ "$BUTUNLUK" != "ok" ]; then
  rm -f "$GECICI"
  echo "HATA: yedek bütünlük kontrolü başarısız: $BUTUNLUK" >&2
  exit 1
fi
mv -f "$GECICI" "$HEDEF"

# 7 günden eski yedekleri sil (-mtime +6: en az 7 tam gün önce değişmiş)
find "$YEDEK_DIZIN" -maxdepth 1 -type f -name 'shop-[0-9]*.db' -mtime "+$((TUTULAN_GUN - 1))" -print -delete \
  | sed 's/^/silindi: /'

echo "yedek: $HEDEF ($(du -h "$HEDEF" | cut -f1)) via $ARAC"
```

- [ ] **Adım 8: `app/gecis_calistir.py` yaz**

```python
"""Dağıtım adımı: canlı veritabanını yedekler, sonra geçişleri uygular (crshop olarak).

dagitim/uzak-yayinla.sh, release kökünden çağırır:
    sudo -n -u crshop /opt/cr-shop-demo/releases/<release>/venv/bin/python -m app.gecis_calistir
sudo ortamı sıfırladığı için SHOP_DB ortam dosyasından okunur. Yedek adı release klasöründen türetilir:
    <SHOP_DB klasörü>/shop-onceki-<release>.db   (son 3 tutulur)
Çıktı: tek satır JSON. SHOP_DB yoksa çıkış 1.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import TextIO

from app.db import baglan, gecisleri_uygula

ORTAM_DOSYASI = Path("/opt/cr-shop-demo/ortam")
TUTULAN_YEDEK = 3


def ortam_dosyasi_oku(yol: Path) -> dict[str, str]:
    """systemd EnvironmentFile biçimi: ANAHTAR=deger, '#' yorum, değer tek/çift tırnaklı olabilir."""
    sonuc: dict[str, str] = {}
    for satir in yol.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if not satir or satir.startswith(("#", ";")) or "=" not in satir:
            continue
        anahtar, deger = satir.split("=", 1)
        deger = deger.strip()
        if len(deger) >= 2 and deger[0] == deger[-1] and deger[0] in "'\"":
            deger = deger[1:-1]
        sonuc[anahtar.strip()] = deger
    return sonuc


def release_adi() -> str:
    return Path(__file__).resolve().parents[1].name


def yedekle(db: Path, hedef: Path) -> None:
    kaynak = sqlite3.connect(db)
    try:
        hedef_con = sqlite3.connect(hedef)
        try:
            kaynak.backup(hedef_con)
        finally:
            hedef_con.close()
    finally:
        kaynak.close()


def eski_yedekleri_sil(klasor: Path, tutulan: int = TUTULAN_YEDEK) -> list[str]:
    yedekler = sorted(klasor.glob("shop-onceki-*.db"), key=lambda p: p.name)
    silinecek = yedekler[:-tutulan] if len(yedekler) > tutulan else []
    for yol in silinecek:
        yol.unlink()
    return [yol.name for yol in silinecek]


def calistir(ortam_dosyasi: Path = ORTAM_DOSYASI, release: str | None = None, cikti: TextIO = sys.stdout) -> int:
    ortam = ortam_dosyasi_oku(ortam_dosyasi)
    if not ortam.get("SHOP_DB"):
        print(json.dumps({"durum": "hata", "hata": f"SHOP_DB yok: {ortam_dosyasi}"}, ensure_ascii=False),
              file=cikti, flush=True)
        return 1
    db = Path(ortam["SHOP_DB"])
    release = release or release_adi()
    yedek: Path | None = None
    if db.exists():
        yedek = db.parent / f"shop-onceki-{release}.db"
        yedekle(db, yedek)
    con = baglan(db)
    try:
        uygulanan = gecisleri_uygula(con)
    finally:
        con.close()
    silinen = eski_yedekleri_sil(db.parent)
    print(json.dumps({"durum": "tamam", "release": release, "yedek": str(yedek) if yedek else None,
                      "uygulanan": uygulanan, "silinen_yedek": silinen}, ensure_ascii=False),
          file=cikti, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(calistir())
```

- [ ] **Adım 9: `app/web/asgi.py` yaz**

```python
"""uvicorn giriş noktası: uvicorn --factory app.web.asgi:uygulama

Ayarlar ortamdan (systemd EnvironmentFile=/opt/cr-shop-demo/ortam) okunur.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.ayarlar import ayarlari_oku
from app.web.uygulama import uygulama_olustur


def uygulama() -> FastAPI:
    return uygulama_olustur(ayarlari_oku())
```

- [ ] **Adım 10: systemd birimlerini yaz**

`dagitim/systemd/cr-shop-demo.service`:

```ini
[Unit]
Description=Ceylan Robot satış sitesi mockup'ı (FastAPI, port 3030)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=crshop
Group=crshop
EnvironmentFile=/opt/cr-shop-demo/ortam
Environment=PYTHONDONTWRITEBYTECODE=1
WorkingDirectory=/opt/cr-shop-demo/current
ExecStart=/opt/cr-shop-demo/current/venv/bin/uvicorn --factory app.web.asgi:uygulama --host 0.0.0.0 --port 3030 --workers 1
Restart=always
RestartSec=3
MemoryMax=600M
UMask=0027
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/cr-shop-demo/veri /opt/cr-shop-demo/yedek
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true

[Install]
WantedBy=multi-user.target
```

`dagitim/systemd/cr-shop-esitle.service`:

```ini
[Unit]
Description=cr-shop-demo katalog eşitlemesi (ceylanrobot.com public API, salt okuma)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=crshop
Group=crshop
EnvironmentFile=/opt/cr-shop-demo/ortam
Environment=PYTHONDONTWRITEBYTECODE=1
WorkingDirectory=/opt/cr-shop-demo/current
ExecStart=/opt/cr-shop-demo/current/venv/bin/python -m betikler.esitle
MemoryMax=400M
TimeoutStartSec=30min
Nice=10
UMask=0027
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/cr-shop-demo/veri /opt/cr-shop-demo/yedek
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
```

`dagitim/systemd/cr-shop-esitle.timer`:

```ini
[Unit]
Description=cr-shop-demo katalog eşitlemesi her gece 02:30

[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true
Unit=cr-shop-esitle.service

[Install]
WantedBy=timers.target
```

`dagitim/systemd/cr-shop-yedek.service`:

```ini
[Unit]
Description=cr-shop-demo SQLite yedeği (7 gün tutulur)

[Service]
Type=oneshot
User=crshop
Group=crshop
EnvironmentFile=/opt/cr-shop-demo/ortam
Environment=SHOP_YEDEK_DIZIN=/opt/cr-shop-demo/yedek
Environment=SHOP_YEDEK_GUN=7
WorkingDirectory=/opt/cr-shop-demo/current
ExecStart=/usr/bin/bash /opt/cr-shop-demo/current/betikler/yedek.sh
MemoryMax=200M
TimeoutStartSec=10min
Nice=10
UMask=0027
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/cr-shop-demo/veri /opt/cr-shop-demo/yedek
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
```

`dagitim/systemd/cr-shop-yedek.timer`:

```ini
[Unit]
Description=cr-shop-demo SQLite yedeği her gece 03:00

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true
Unit=cr-shop-yedek.service

[Install]
WantedBy=timers.target
```

`dagitim/systemd/cr-shop-kur.service`:

```ini
[Unit]
Description=cr-shop-demo TCMB EUR kuru
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=crshop
Group=crshop
EnvironmentFile=/opt/cr-shop-demo/ortam
Environment=PYTHONDONTWRITEBYTECODE=1
WorkingDirectory=/opt/cr-shop-demo/current
ExecStart=/opt/cr-shop-demo/current/venv/bin/python -m betikler.kur_al
MemoryMax=200M
TimeoutStartSec=5min
UMask=0027
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/cr-shop-demo/veri /opt/cr-shop-demo/yedek
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
```

`dagitim/systemd/cr-shop-kur.timer`:

```ini
[Unit]
Description=cr-shop-demo TCMB EUR kuru her gün 06:00

[Timer]
OnCalendar=*-*-* 06:00:00
Persistent=true
Unit=cr-shop-kur.service

[Install]
WantedBy=timers.target
```

- [ ] **Adım 11: `dagitim/ortam.ornek` yaz**

```bash
# /opt/cr-shop-demo/ortam — sahibi crshop:crshop, izin 600. Depoya GERÇEK değer yazılmaz.
# systemd EnvironmentFile biçimi. Değerler TEK TIRNAK içinde yazılır: parola özetindeki "$" işaretleri olduğu gibi kalır.
#
# SHOP_GIZLI_ANAHTAR üretimi : python3 -c "import secrets;print(secrets.token_urlsafe(48))"
# SHOP_YONETICI_OZET üretimi : venv/bin/python -m betikler.yonetici_ozet   (parola kimlik Excel'inde, "Sunucular" sayfası)
SHOP_DB='/opt/cr-shop-demo/veri/shop.db'
SHOP_GIZLI_ANAHTAR='ornek-degil-uretilecek'
SHOP_YONETICI='yonetici'
SHOP_YONETICI_OZET='scrypt$16384$8$1$ornek$ornek'
# İsteğe bağlı (varsayılan https://www.ceylanrobot.com):
# SHOP_KAYNAK_API='https://www.ceylanrobot.com'
```

- [ ] **Adım 12: `dagitim/kurulum-vm.sh` yaz**

```bash
#!/usr/bin/env bash
# cr-shop-demo VM ön koşulları. BİR KEZ çalıştırılır; yeniden çalıştırmak güvenlidir (idempotent).
# systemd birim dosyaları değiştiğinde de yeniden çalıştırılır (deploy.sh birimleri güncellemez).
# Kullanım (VM'de, depo kopyasının kökünden): sudo bash dagitim/kurulum-vm.sh
set -euo pipefail

KAYNAK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KOK=/opt/cr-shop-demo
DAGITICI="${CR_SHOP_DAGITICI:-crwebdemo}"
SERVIS_KULLANICISI=crshop
PORT=3030
AGLAR=(192.168.2.0/24 192.168.5.0/24 192.168.11.0/24 192.168.12.0/24)
SUDOERS=/etc/sudoers.d/cr-shop-demo
BIRIMLER=(cr-shop-demo.service cr-shop-esitle.service cr-shop-esitle.timer cr-shop-yedek.service
          cr-shop-yedek.timer cr-shop-kur.service cr-shop-kur.timer)
ZAMANLAYICILAR=(cr-shop-esitle.timer cr-shop-yedek.timer cr-shop-kur.timer)

if [ "$(id -u)" -ne 0 ]; then
  echo "HATA: sudo ile çalıştırın: sudo bash $0" >&2
  exit 1
fi
if ! id "$DAGITICI" >/dev/null 2>&1; then
  echo "HATA: dağıtıcı kullanıcı yok: $DAGITICI" >&2
  exit 1
fi
for birim in "${BIRIMLER[@]}"; do
  if [ ! -f "$KAYNAK/systemd/$birim" ]; then
    echo "HATA: eksik birim dosyası: $KAYNAK/systemd/$birim" >&2
    exit 1
  fi
done

cat <<EOF
cr-shop-demo kurulumu şunları yapacak:
  1. apt: apt-get update + python3-venv ve sqlite3 paketleri
  2. Sistem kullanıcısı: $SERVIS_KULLANICISI (giriş kabuğu yok, ev klasörü yok)
  3. Klasörler: $KOK ve $KOK/releases (sahibi $DAGITICI, 755);
               $KOK/veri ve $KOK/yedek (sahibi $SERVIS_KULLANICISI, 750)
  4. Ortam dosyası: $KOK/ortam yoksa boş oluşturulur; sahibi $SERVIS_KULLANICISI, izin 600 (içeriğe dokunulmaz)
  5. sudoers ($SUDOERS): $DAGITICI parolasız YALNIZ şunları çalıştırabilir:
       /usr/bin/systemctl restart cr-shop-demo
       /usr/bin/systemctl start cr-shop-esitle
       ($SERVIS_KULLANICISI olarak) $KOK/releases/<release>/venv/bin/python -m app.gecis_calistir
  6. systemd: ${BIRIMLER[*]}
     -> /etc/systemd/system, daemon-reload, cr-shop-demo.service enable (başlatılmaz; ilk deploy başlatır),
     zamanlayıcılar enable --now
  7. ufw: $PORT/tcp yalnız ${AGLAR[*]}
Port 80 (web-demo) ve 3027 (aic-demo) servislerine dokunulmaz.
EOF
read -r -p "devam? (e/h) " CEVAP
if [ "$CEVAP" != "e" ]; then
  echo "İptal edildi."
  exit 1
fi

echo "[1/7] paketler"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3-venv sqlite3

echo "[2/7] servis kullanıcısı"
if id "$SERVIS_KULLANICISI" >/dev/null 2>&1; then
  echo "  $SERVIS_KULLANICISI zaten var"
else
  useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin --user-group "$SERVIS_KULLANICISI"
fi

echo "[3/7] klasörler"
install -d -o "$DAGITICI" -g "$DAGITICI" -m 755 "$KOK" "$KOK/releases"
install -d -o "$SERVIS_KULLANICISI" -g "$SERVIS_KULLANICISI" -m 750 "$KOK/veri" "$KOK/yedek"

echo "[4/7] ortam dosyası"
if [ ! -e "$KOK/ortam" ]; then
  install -o "$SERVIS_KULLANICISI" -g "$SERVIS_KULLANICISI" -m 600 /dev/null "$KOK/ortam"
  echo "  boş $KOK/ortam oluşturuldu (doldurulması gerekiyor)"
fi
chown "$SERVIS_KULLANICISI:$SERVIS_KULLANICISI" "$KOK/ortam"
chmod 600 "$KOK/ortam"

echo "[5/7] sudoers"
GECICI_SUDOERS="$(mktemp)"
trap 'rm -f "$GECICI_SUDOERS"' EXIT
cat > "$GECICI_SUDOERS" <<EOF
# cr-shop-demo: deploy'un parolasız çalıştırabildiği komutlar (yalnız bunlar).
# Bu dosyayı dagitim/kurulum-vm.sh üretir; elle değiştirmeyin.
Cmnd_Alias CR_SHOP_SERVIS = /usr/bin/systemctl restart cr-shop-demo, /usr/bin/systemctl start cr-shop-esitle
Cmnd_Alias CR_SHOP_GECIS = $KOK/releases/[0-9]*-[0-9]*/venv/bin/python -m app.gecis_calistir
$DAGITICI ALL=(root) NOPASSWD: CR_SHOP_SERVIS
$DAGITICI ALL=($SERVIS_KULLANICISI) NOPASSWD: CR_SHOP_GECIS
EOF
visudo -cf "$GECICI_SUDOERS"
install -o root -g root -m 440 "$GECICI_SUDOERS" "$SUDOERS"
visudo -c

echo "[6/7] systemd birimleri"
for birim in "${BIRIMLER[@]}"; do
  install -o root -g root -m 644 "$KAYNAK/systemd/$birim" "/etc/systemd/system/$birim"
done
systemctl daemon-reload
systemctl enable cr-shop-demo.service
systemctl enable --now "${ZAMANLAYICILAR[@]}"

echo "[7/7] ufw"
UFW_DURUM="$(ufw status)"
case "$UFW_DURUM" in
  "Status: active"*) ;;
  *) echo "UYARI: ufw etkin değil; kurallar yine de eklenecek." >&2 ;;
esac
for ag in "${AGLAR[@]}"; do
  ufw allow proto tcp from "$ag" to any port "$PORT" comment "cr-shop-demo"
done

echo "Özet:"
id "$SERVIS_KULLANICISI"
ls -ld "$KOK" "$KOK/releases" "$KOK/veri" "$KOK/yedek" "$KOK/ortam"
systemctl list-timers --all --no-pager 'cr-shop-*'
ufw status | grep -E "^$PORT/tcp" || true
echo "TAMAM. Sıradaki: $KOK/ortam dosyasını doldurun, sonra laptopta: bash dagitim/deploy.sh"
```

- [ ] **Adım 13: `dagitim/deploy.sh` (laptop) ve `dagitim/uzak-yayinla.sh` (VM) yaz**

`dagitim/deploy.sh`:

```bash
#!/usr/bin/env bash
# cr-shop-demo dağıtımı — laptopta (Git Bash), depo kökünden: bash dagitim/deploy.sh
# Adımlar: temiz ağaç kontrolü -> git archive HEAD -> VM'de yeni release -> dagitim/uzak-yayinla.sh
# (venv + pip, pytest, yedek + geçiş, current, restart, /saglik, gerekirse geri alma, eski release temizliği)
set -euo pipefail

HEDEF="${CR_SHOP_HEDEF:-cr-web-demo}"
KOK=/opt/cr-shop-demo

cd "$(git rev-parse --show-toplevel)"

if [ -n "$(git status --porcelain)" ]; then
  echo "HATA: çalışma ağacı temiz değil; önce commit edin." >&2
  git status --short >&2
  exit 1
fi

RELEASE="$(date +%Y%m%d-%H%M)"
SURUM="$(git rev-parse --short HEAD)"
REL="$KOK/releases/$RELEASE"
echo "Release $RELEASE (commit $SURUM) -> $HEDEF:$REL"

if ! ssh "$HEDEF" "test -d $KOK/releases && test ! -e $REL && mkdir $REL"; then
  echo "HATA: $KOK/releases yok (kurulum-vm.sh çalıştı mı?) ya da $RELEASE zaten var (1 dk bekleyip tekrar deneyin)." >&2
  exit 1
fi

if ! git archive --format=tar HEAD | ssh "$HEDEF" "tar -x -C $REL && echo $SURUM > $REL/SURUM"; then
  echo "HATA: arşiv aktarılamadı; yarım release siliniyor." >&2
  ssh "$HEDEF" "rm -rf $REL"
  exit 1
fi

ssh "$HEDEF" "bash $REL/dagitim/uzak-yayinla.sh $RELEASE"
```

`dagitim/uzak-yayinla.sh`:

```bash
#!/usr/bin/env bash
# deploy.sh'nin VM tarafı. crwebdemo olarak, yeni release'in içinden çalışır:
#   bash /opt/cr-shop-demo/releases/<release>/dagitim/uzak-yayinla.sh <release>
# sudo yalnız /etc/sudoers.d/cr-shop-demo'daki parolasız komutlarla (-n) kullanılır.
set -euo pipefail

RELEASE="${1:?release adı gerekli}"
KOK=/opt/cr-shop-demo
REL="$KOK/releases/$RELEASE"
SAGLIK_URL=http://127.0.0.1:3030/saglik

release_sil_ve_dur() {
  echo "HATA: $1 — release siliniyor, current değişmedi." >&2
  cd "$KOK"
  rm -rf "${REL:?}"
  exit 1
}

current_ayarla() {
  ln -sfn "releases/$1" "$KOK/current.yeni"
  mv -Tf "$KOK/current.yeni" "$KOK/current"
}

saglikli_mi() {
  local deneme kod
  for deneme in 1 2 3 4 5 6 7 8 9 10; do
    kod="$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$SAGLIK_URL" || true)"
    if [ "$kod" = "200" ]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

cd "$REL"

echo "[1/6] venv + bağımlılıklar"
python3 -m venv venv </dev/null || release_sil_ve_dur "venv kurulamadı (python3-venv kurulu mu?)"
venv/bin/pip install --quiet --disable-pip-version-check -r requirements.txt "pytest==8.*" </dev/null \
  || release_sil_ve_dur "pip install başarısız"

echo "[2/6] testler (release venv'inde; her test geçici veritabanı kullanır)"
venv/bin/python -m pytest -q -p no:cacheprovider tests </dev/null || release_sil_ve_dur "testler geçmedi"

echo "[3/6] veritabanı yedeği + geçişler (crshop)"
sudo -n -u crshop "$REL/venv/bin/python" -m app.gecis_calistir </dev/null \
  || release_sil_ve_dur "yedek/geçiş başarısız (yedek: $KOK/veri/shop-onceki-$RELEASE.db)"

echo "[4/6] current -> $RELEASE ve yeniden başlatma"
ONCEKI=""
if [ -L "$KOK/current" ]; then
  ONCEKI="$(basename "$(readlink -f "$KOK/current")")"
fi
current_ayarla "$RELEASE"
sudo -n /usr/bin/systemctl restart cr-shop-demo

echo "[5/6] sağlık kontrolü (en fazla 10 sn)"
if ! saglikli_mi; then
  echo "HATA: $SAGLIK_URL 10 sn içinde 200 dönmedi." >&2
  journalctl -u cr-shop-demo -n 30 --no-pager >&2 || true
  if [ -n "$ONCEKI" ] && [ "$ONCEKI" != "$RELEASE" ] && [ -d "$KOK/releases/$ONCEKI" ]; then
    current_ayarla "$ONCEKI"
    sudo -n /usr/bin/systemctl restart cr-shop-demo
    echo "GERİ ALINDI: current -> $ONCEKI. Hatalı release incelemek için duruyor: $REL" >&2
    echo "Veritabanı gerekirse elle geri yüklenir: $KOK/veri/shop-onceki-$RELEASE.db" >&2
  else
    echo "Önceki release yok; geri alınacak sürüm bulunamadı." >&2
  fi
  exit 1
fi

echo "[6/6] eski release'ler (son 3 tutulur)"
GUNCEL="$(basename "$(readlink -f "$KOK/current")")"
for eski in $(ls -1 "$KOK/releases" | sort -r | tail -n +4); do
  if [ "$eski" = "$GUNCEL" ]; then
    continue
  fi
  rm -rf "${KOK:?}/releases/${eski:?}"
  echo "  silindi: $eski"
done

echo "TAMAM: $RELEASE yayında (commit $(cat "$REL/SURUM")); önceki: ${ONCEKI:-yok}"
```

- [ ] **Adım 14: Testleri çalıştır, geçtiklerini gör**

Run: `python -m pytest tests/test_isletme.py -v`
Expected: PASS — 24 test (yedek.sh testleri Linux'ta çalışır; Windows'ta 2 SKIP).

Run: `python -m pytest -q`
Expected: tüm test takımı PASS (önceki görevlerin testleri bozulmadı).

- [ ] **Adım 15: Kabuk betiklerinin sözdizimini doğrula (laptop, Git Bash)**

Run: `bash -n dagitim/deploy.sh && bash -n dagitim/uzak-yayinla.sh && bash -n dagitim/kurulum-vm.sh && bash -n betikler/yedek.sh && echo SOZDIZIMI_TAMAM`
Expected: `SOZDIZIMI_TAMAM` (başka çıktı yok).

Run: `grep -c $'\r' dagitim/*.sh betikler/yedek.sh dagitim/systemd/* || true`
Expected: her dosya için `:0` (CRLF yok).

- [ ] **Adım 16: systemd birimlerini VM'de doğrula (kopyalamadan, dosya yoluyla)**

Birimler henüz yüklü değil ve `/opt/cr-shop-demo/current` yok. `systemd-analyze verify` ExecStart ikililerinin varlığını da denetlediği için, geçici kopyada yalnız ikili yolları sistemde var olan yollara çevrilir. Bu adım sudo gerektirmez.

Run:
```bash
tar -C dagitim/systemd -cf - . | ssh cr-web-demo '
  rm -rf ~/cr-shop-systemd-dogrula && mkdir ~/cr-shop-systemd-dogrula && cd ~/cr-shop-systemd-dogrula && tar -xf - &&
  sed -i "s#/opt/cr-shop-demo/current/venv/bin/uvicorn#/usr/bin/true#; s#/opt/cr-shop-demo/current/venv/bin/python#/usr/bin/python3#" *.service &&
  systemd-analyze verify ./*.service ./*.timer; echo "cikis=$?"; cd ~ && rm -rf ~/cr-shop-systemd-dogrula'
```
Expected: son satır `cikis=0`; öncesinde `Unknown key`, `Invalid` ya da `Failed to` içeren satır yok. Böyle bir satır varsa ilgili birim düzeltilir ve adım tekrarlanır.

- [ ] **Adım 17: Commit**

```bash
git add betikler/ app/gecis_calistir.py app/web/asgi.py dagitim/ tests/test_isletme.py
git update-index --chmod=+x dagitim/deploy.sh dagitim/uzak-yayinla.sh dagitim/kurulum-vm.sh betikler/yedek.sh
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m "feat: isletme betikleri, systemd birimleri, VM kurulumu ve dagitim

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Görev 18: İlk kurulum, ilk eşitleme ve kabul

**Files:**
- Create: `e2e/conftest.py`
- Create: `e2e/test_kabul.py`
- Modify (yoksa Create): `.gitignore` (`e2e/ekranlar/`)
- Create: `docs/kabul/kabul-kaydi.md`
- Create: `docs/kullanici-testi.md`
- Depo dışı (commit edilmez): laptopta `~/.cr-shop/kimlik_oku.py`; hive `C:\Users\lbell\hive\hosts\machines.md` (Modify); Vault `C:\Users\lbell\Documents\Vault-CR\08-Website\Satis-Sitesi-Mockup.md` (Create)

**Interfaces:**
- Consumes: Görev 17'nin bütün çıktıları (`dagitim/kurulum-vm.sh`, `dagitim/deploy.sh`, `betikler.yonetici_ozet`, birimler, sudoers komutları); rotalar ve şablon sözleşmesi ("Ortak arayüz sözleşmesi" → "URL'ler", "Şablon sözleşmesi"); aşağıdaki **E2E seçici sözleşmesi** (ekran görevleri uygular; ayrıca "Entegrasyon kararları" K12).
- Produces: `http://192.168.5.30:3030` üzerinde çalışan staging, ilk tam eşitleme, kur kaydı, kabul kaydı, bağımsız değerlendirme puanı ≥ 8,5, kullanıcı testi yönergesi, hive/Vault kayıtları.

**E2E seçici sözleşmesi** (şablonlarda bulunmalı; testler yalnız bunlara dayanır):

| Yer | Seçici / alan |
|---|---|
| Liste ve arama sonuçlarında ürün bağlantısı | `a[data-e2e="urun-baglanti"]` |
| Ürün detayı ana fiyat | `[data-e2e="fiyat-ana"]` + `data-para="TRY\|EUR"` + `data-kdv="dahil\|haric"` |
| Ürün detayı ikincil fiyat | `[data-e2e="fiyat-ikincil"]` |
| Sepete ekle düğmesi / Teklif iste bağlantısı | `[data-e2e="sepete-ekle"]` / `[data-e2e="teklif-iste"]` |
| Sepet kalemi, ödemeye geç | `[data-e2e="sepet-kalemi"]`, `[data-e2e="odemeye-gec"]` |
| Tutar özeti satırları (sepet, ödeme, kart sayfası) | `[data-e2e="satir-kdv"]`, `[data-e2e="satir-ihracat"]`, `[data-e2e="not-dap"]` |
| Oturum açıkken başlıktaki çıkış düğmesi | `[data-e2e="cikis"]` |
| Kayıt formu | alanlar `tip`, `ad`, `eposta`, `parola`, `ulke`, `vergi_kimlik_no`, `vergi_dairesi`, `vat_id`, `kvkk_onay`, `iys_onay`; gönder `[data-e2e="kayit-gonder"]`; `?tip=` ve `?sonraki=` parametrelerini kabul eder |
| Ödeme formu | `teslimat_ad_soyad`, `teslimat_satir1`, `teslimat_sehir`, `teslimat_posta_kodu`, `teslimat_ulke`, `teslimat_telefon`, `fatura_ayni` (onay kutusu, varsayılan işaretli), `teslim` (radyo: `kargo`/`fabrika`/`yurtdisi_dap`), `on_bilgi_onay`, `mesafeli_onay` (yalnız bireysel), `kosullar_onay` (yalnız kurumsal/yurt dışı); gönder `[data-e2e="odeme-gonder"]` |
| Kart / 3D | `kart_no` (+ varsa `kart_ad`, `kart_skt`, `kart_cvc`), `[data-e2e="kart-gonder"]`; `sms_kodu`, `[data-e2e="sms-gonder"]` |
| Ödeme hatası | `[data-e2e="odeme-hata"]` + `data-kod` = `OdemeSonucu` değeri (`gecersiz_kart`, `ret`, `sms_hatali`) |
| Sipariş sayfası durumu | `[data-e2e="siparis-durum"]` + `data-durum` = `SiparisDurumu` değeri |
| Teklif formu / sonucu | alanlar `ad`, `firma`, `eposta`, `telefon`, `ulke`, `adet`, `mesaj`; gönder `[data-e2e="teklif-gonder"]`; tamam sayfasında `[data-e2e="teklif-no"]` |
| Geri bildirim | `#gb-dugme`, `#gb-pencere` içinde `[name="metin"]`, `[name="isim"]`, `[type="submit"]`; başarıda `[data-e2e="gb-tamam"]` |
| Tercih formu (taban) | `form[action="/tercih"]` içinde `select[name="dil"]`, `select[name="ulke"]`, `[type="submit"]` |
| Yönetim | giriş alanları `kullanici`, `parola`, gönder `[data-e2e="yonetim-giris"]`; `/yonetim` panelinde `[data-e2e="son-esitleme"]` |

- [ ] **Adım 1: Ön ölçüm — diğer demolar ve VM kaynakları (sudo yok)**

Run:
```bash
for u in http://192.168.5.30/ http://192.168.5.30:3027/; do printf '%s %s\n' "$u" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$u")"; done
ssh cr-web-demo 'free -m; df -h /opt; systemctl is-active web-demo aic-demo; ss -ltnp | grep -E ":(80|3027|3030) " || true; id'
```
Expected: iki adres `200`; `web-demo` ve `aic-demo` `active`; 3030 dinlenmiyor; `/opt` altında ≥ 1 GB boş; `id` çıktısında `sudo` grubu (ve journal okumak için `adm`). Çıktıyı Adım 16'daki kabul kaydı için sakla.

Laptop ön koşulu (aynı adımda): `python -c "import openpyxl, playwright, pytest"` hata vermemeli. Hata verirse dur ve kullanıcıya bildir; laptopa paket kurma kararı kullanıcının (disk dar).

- [ ] **Adım 2: Kimlik okuyucuyu laptopa hazırla (depo dışı, parola ekrana yazılmaz)**

`~/.cr-shop/kimlik_oku.py` (Git Bash'te `mkdir -p ~/.cr-shop`):

```python
"""Kimlik Excel'inden (Sunucular sayfası) bir satırın parolasını STDOUT'a yazar — yalnız boruya verilir.

Kullanım: python ~/.cr-shop/kimlik_oku.py <satırda geçen metin>     örn. cr-web-demo
Parolayı ekrana basmayın; çıktıyı yalnız `|` ile ssh/sudo'ya verin.
"""
import sys
from pathlib import Path

import openpyxl

DOSYA = Path(r"C:\Users\lbell\Documents\Vault-CR\06-Uygulama\CR-Sunucular-Kimlik-Ozet.xlsx")
PAROLA_BASLIKLARI = ("parola", "şifre", "sifre", "password")

anahtar = sys.argv[1].casefold()
kitap = openpyxl.load_workbook(DOSYA, read_only=True, data_only=True)
satirlar = [tuple("" if h is None else str(h).strip() for h in s) for s in kitap["Sunucular"].iter_rows(values_only=True)]

baslik_no = next((i for i, s in enumerate(satirlar)
                  if any(b in h.casefold() for h in s for b in PAROLA_BASLIKLARI)), None)
if baslik_no is None:
    sys.exit("başlık satırı (Parola/Şifre) bulunamadı")
sutun = next(j for j, h in enumerate(satirlar[baslik_no]) if any(b in h.casefold() for b in PAROLA_BASLIKLARI))

for satir in satirlar[baslik_no + 1:]:
    if any(anahtar in h.casefold() for h in satir):
        if not satir[sutun]:
            sys.exit(f"'{anahtar}' satırında parola hücresi boş")
        sys.stdout.write(satir[sutun] + "\n")
        break
else:
    sys.exit(f"'{anahtar}' satırı bulunamadı")
```

Run: `python -c "import openpyxl" && python ~/.cr-shop/kimlik_oku.py cr-web-demo | wc -c`
Expected: 1'den büyük bir sayı (parola + satır sonu uzunluğu); parola görünmez. `openpyxl` yoksa ya da satır bulunamazsa: sudo gerektiren adımları kullanıcı kendi terminalinde `! ssh -t cr-web-demo "<komut>"` biçiminde, parolayı kendisi yazarak çalıştırır. Yeni paket kurulmaz.

- [ ] **Adım 3: Depo kopyasını VM'e aktar (sudo yok; araç venv'i `python3-venv` gerektirdiği için Adım 7'de kurulur)**

Run:
```bash
git status --porcelain | grep -q . && { echo "önce commit"; exit 1; }
git archive --format=tar HEAD | ssh cr-web-demo 'rm -rf ~/cr-shop-araclar && mkdir ~/cr-shop-araclar && tar -x -C ~/cr-shop-araclar && ls ~/cr-shop-araclar/dagitim'
```
Expected: `deploy.sh  kurulum-vm.sh  ortam.ornek  systemd  uzak-yayinla.sh`

- [ ] **Adım 4: KULLANICIYA GÖSTER VE ONAY AL — kurulum-vm.sh (sudo)**

Kullanıcıya şunları göster: `dagitim/kurulum-vm.sh`'nin tam içeriği (Görev 17 Adım 12), betiğin yazdırdığı 7 maddelik özet ve çalıştırılacak komut:
`{ python ~/.cr-shop/kimlik_oku.py cr-web-demo; echo e; } | ssh cr-web-demo "sudo -S -p '' bash ~/cr-shop-araclar/dagitim/kurulum-vm.sh"`.
Özellikle sudoers satırlarını ve ufw ağlarını vurgula. Açık "evet" gelmeden Adım 5'e geçme.

- [ ] **Adım 5: Kurulumu çalıştır ve doğrula**

Run: `{ python ~/.cr-shop/kimlik_oku.py cr-web-demo; echo e; } | ssh cr-web-demo "sudo -S -p '' bash ~/cr-shop-araclar/dagitim/kurulum-vm.sh"`
Expected: `[1/7]` … `[7/7]` satırları, `visudo` çıktısında `parsed OK`, son satır `TAMAM. Sıradaki: ...`. `ls -ld` çıktısında `/opt/cr-shop-demo` ve `releases` için `crwebdemo`, `veri` ve `yedek` için `drwxr-x--- crshop`, `ortam` için `-rw------- crshop`.

Run: `ssh cr-web-demo 'sudo -n -l | grep -A3 cr-shop || sudo -n -l'`
Expected: `(root) NOPASSWD: /usr/bin/systemctl restart cr-shop-demo, /usr/bin/systemctl start cr-shop-esitle` ve `(crshop) NOPASSWD: /opt/cr-shop-demo/releases/[0-9]*-[0-9]*/venv/bin/python -m app.gecis_calistir`. Başka NOPASSWD kuralı eklenmemiş olmalı.

Run: `for u in http://192.168.5.30/ http://192.168.5.30:3027/; do curl -s -o /dev/null -w "%{http_code} $u\n" "$u"; done`
Expected: iki satır da `200` (kurulum diğer demoları etkilemedi).

- [ ] **Adım 6: Yönetici parolasını kimlik Excel'ine kaydet (kullanıcı)**

Kullanıcıdan iste: `CR-Sunucular-Kimlik-Ozet.xlsx` "Sunucular" sayfasına yeni satır — sunucu/hizmet sütununa `cr-shop-demo yönetim (http://192.168.5.30:3030/yonetim)`, kullanıcı `yonetici`, parola en az 12 karakter, kullanıcının kendi belirlediği değer. Parola sohbete yazılmaz. Dosya kaydedilip kapatılır.

Run: `python ~/.cr-shop/kimlik_oku.py cr-shop-demo | wc -c`
Expected: 13 ya da daha büyük (≥ 12 karakter + satır sonu).

- [ ] **Adım 7: Araç venv'i ile yönetici özetini üret, ortam dosyasını hazırla (sudo yok)**

Run:
```bash
ssh cr-web-demo 'cd ~/cr-shop-araclar && python3 -m venv venv && venv/bin/pip install --quiet --disable-pip-version-check -r requirements.txt && echo VENV_TAMAM'
OZET="$(python ~/.cr-shop/kimlik_oku.py cr-shop-demo | ssh cr-web-demo 'cd ~/cr-shop-araclar && venv/bin/python -m betikler.yonetici_ozet')"
GIZLI="$(python -c "import secrets;print(secrets.token_urlsafe(48))")"
case "$OZET" in scrypt\$*) ;; *) echo "HATA: özet üretilemedi"; exit 1;; esac
ssh cr-web-demo 'umask 077; cat > ~/ortam.yeni' <<EOF
SHOP_DB='/opt/cr-shop-demo/veri/shop.db'
SHOP_GIZLI_ANAHTAR='$GIZLI'
SHOP_YONETICI='yonetici'
SHOP_YONETICI_OZET='$OZET'
EOF
ssh cr-web-demo 'stat -c "%a %U %n" ~/ortam.yeni; cut -d= -f1 ~/ortam.yeni'
```
Expected: `VENV_TAMAM`; `600 crwebdemo /home/crwebdemo/ortam.yeni`; anahtar adları `SHOP_DB SHOP_GIZLI_ANAHTAR SHOP_YONETICI SHOP_YONETICI_OZET`. Değerler ekrana basılmaz.

- [ ] **Adım 8: KULLANICIYA GÖSTER VE ONAY AL — ortam dosyasını yerine koy (sudo)**

Göster: `{ python ~/.cr-shop/kimlik_oku.py cr-web-demo; } | ssh cr-web-demo "sudo -S -p '' install -o crshop -g crshop -m 600 ~/ortam.yeni /opt/cr-shop-demo/ortam && shred -u ~/ortam.yeni"` — ne yaptığı: hazırlanan dosyayı crshop sahipliğinde, 600 izinle kopyalar; geçici kopyayı siler. Onay gelmeden çalıştırma.

Run: (yukarıdaki komut), ardından `ssh cr-web-demo 'ls -l /opt/cr-shop-demo/ortam; test ! -e ~/ortam.yeni && echo GECICI_SILINDI'`
Expected: `-rw------- 1 crshop crshop ... /opt/cr-shop-demo/ortam` ve `GECICI_SILINDI`.

- [ ] **Adım 9: İlk dağıtım**

Run: `bash dagitim/deploy.sh`
Expected (sırayla): `[1/6] venv + bağımlılıklar` → `[2/6] testler` (pytest özeti `N passed`) → `[3/6]` (JSON `"durum": "tamam"`, `"yedek": null`, `uygulanan` içinde `001_baslangic`) → `[4/6]` → `[5/6]` → `[6/6]` → `TAMAM: <release> yayında (commit <kısa-hash>); önceki: yok`.
Başarısızsa: çıktıdaki ilk `HATA:` satırına göre düzelt, commit et, yeniden çalıştır. `sudo -n` "a password is required" derse Adım 5'teki `sudo -n -l` çıktısını komutla birebir karşılaştır.

Run: `curl -s http://192.168.5.30:3030/saglik; echo; curl -s -o /dev/null -w '%{http_code}\n' http://192.168.5.30:3030/tr/`
Expected: `{"durum":"ok","son_esitleme":null,"urun":0}` ve `200`.

- [ ] **Adım 10: KULLANICIYA GÖSTER VE ONAY AL — ilk eşitleme (sudo, parolasız kural)**

Göster: `ssh cr-web-demo 'sudo -n /usr/bin/systemctl start cr-shop-esitle'` — ceylanrobot.com public API'sinden ~4.449 ürünü sayfa başına 20 kayıt, 1 sn arayla çeker (~4–5 dk); canlı siteye yük düşük. Onay gelmeden çalıştırma.

- [ ] **Adım 11: Eşitlemeyi başlat ve izle (MemoryPeak < 400 MB, kullanılan bellek < 1.500 MB)**

Başlat (Bash aracında `run_in_background: true`; servis bitene kadar döner):
`ssh cr-web-demo 'sudo -n /usr/bin/systemctl start cr-shop-esitle; echo "start_cikis=$?"'`

İzle (ön planda; `MemoryPeak` servis bittikten sonra sıfırlanabildiği için çalışırken örneklenir):
```bash
ssh cr-web-demo 'bash -s' <<'IZLE'
for i in $(seq 1 30); do
  durum="$(systemctl show -p ActiveState --value cr-shop-esitle)"
  [ "$durum" = "activating" ] || [ "$durum" = "active" ] && break
  sleep 1
done
tepe=0; kullanilan_en_fazla=0
while :; do
  durum="$(systemctl show -p ActiveState --value cr-shop-esitle)"
  p="$(systemctl show -p MemoryPeak --value cr-shop-esitle)"
  k="$(free -m | awk '/^Mem:/{print $3}')"
  if [[ "$p" =~ ^[0-9]+$ ]] && (( p > tepe )); then tepe=$p; fi
  if (( k > kullanilan_en_fazla )); then kullanilan_en_fazla=$k; fi
  if [ "$durum" != "activating" ] && [ "$durum" != "active" ]; then break; fi
  sleep 10
done
echo "MemoryPeak_MB=$(( tepe / 1048576 )) free_kullanilan_en_fazla_MB=$kullanilan_en_fazla son_durum=$durum"
systemctl show -p Result --value cr-shop-esitle
journalctl -u cr-shop-esitle -n 15 --no-pager
IZLE
```
Expected: `MemoryPeak_MB` < 400; `free_kullanilan_en_fazla_MB` < 1500; `Result` = `success`; journal'da betiğin JSON satırı `{"durum": "tam", "api_toplam": 4449, "cekilen": 4449, "bozuk": 0, ...}` (tam koşulu K1: benzersiz SKU + bozuk = api_toplam) (sayı o günkü API toplamıdır) ve systemd'nin `Consumed ... memory peak` satırı (iki ölçüm birbirini doğrular). Arka plandaki komut `start_cikis=0` ile biter. Durum `eksik` ise Adım 10–11 bir kez tekrarlanır; `hata` ise journal'daki `hata` alanına göre düzeltilir.

- [ ] **Adım 12: KULLANICIYA GÖSTER VE ONAY AL, sonra kuru al (sudo)**

Göster: `{ python ~/.cr-shop/kimlik_oku.py cr-web-demo; } | ssh cr-web-demo "sudo -S -p '' /usr/bin/systemctl start cr-shop-kur"` — TCMB `today.xml`'den EUR kuru alır. Onaydan sonra çalıştır.

Run: (yukarıdaki komut), ardından `ssh cr-web-demo 'journalctl -u cr-shop-kur -n 5 --no-pager'`
Expected: `{"durum": "tamam", "tarih": "<bugün ya da son iş günü>", "eur_alis": "...", "eur_satis": "..."}`. Hafta sonu/bayramda TCMB son iş gününün kurunu verir; bu beklenen durumdur.

- [ ] **Adım 13: Duman testi, kurulu birimlerin doğrulanması, diğer demolar**

Run:
```bash
T=http://192.168.5.30:3030
curl -s "$T/saglik"; echo
URUN="$(curl -s "$T/tr/ara?q=ABB" | grep -oE '/tr/urun/[0-9]+' | head -1)"
for y in /saglik /tr/ "$URUN" /tr/sepet /en/; do printf '%s %s\n' "$(curl -s -o /dev/null -w '%{http_code}' "$T$y")" "$y"; done
for u in http://192.168.5.30/ http://192.168.5.30:3027/; do printf '%s %s\n' "$(curl -s -o /dev/null -w '%{http_code}' "$u")" "$u"; done
ssh cr-web-demo 'systemd-analyze verify /etc/systemd/system/cr-shop-*.service /etc/systemd/system/cr-shop-*.timer; echo "verify_cikis=$?"; systemctl list-timers --all --no-pager "cr-shop-*"'
```
Expected: `/saglik` → `"urun"` > 4000 ve `son_esitleme` dolu; yollar ve iki diğer demo `200`; `verify_cikis=0`; üç zamanlayıcının `NEXT` sütunu dolu (02:30, 03:00, 06:00).

- [ ] **Adım 14: Uçtan uca testleri yaz (laptop)**

`.gitignore` dosyasına (yoksa oluştur) ekle:

Run: `grep -qx 'e2e/ekranlar/' .gitignore 2>/dev/null || echo 'e2e/ekranlar/' >> .gitignore`

`e2e/conftest.py`:

```python
"""Uçtan uca kabul testleri — laptopta, staging'e karşı. Çalıştırma: python -m pytest e2e -q

Ortam: CR_SHOP_TABAN (varsayılan http://192.168.5.30:3030),
       CR_SHOP_YONETICI / CR_SHOP_YONETICI_PAROLA (yönetim paneli kontrolleri için).
VM'deki release venv'inde Playwright yoktur; o durumda bu klasör hiç toplanmaz.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # VM: Playwright yok -> e2e toplanmaz
    collect_ignore_glob = ["*.py"]
else:
    TABAN = os.environ.get("CR_SHOP_TABAN", "http://192.168.5.30:3030").rstrip("/")
    TABAN_HOST = urlparse(TABAN).hostname
    EKRANLAR = Path(__file__).parent / "ekranlar"
    # Form doğrulama yanıtları (400/409/422) Chrome'da "Failed to load resource" olarak loglanır; bunlar beklenen akıştır.
    BEKLENEN_DURUM = re.compile(r"status of (400|409|422)")

    def _kabul_edilebilir(metin: str, konum: str) -> bool:
        if not metin.startswith("Failed to load resource"):
            return False
        yer = urlparse(konum)
        if yer.hostname == "www.ceylanrobot.com":  # görsel 404 -> yer tutucu (beklenen)
            return True
        return yer.hostname == TABAN_HOST and not yer.path.startswith("/statik/") and bool(BEKLENEN_DURUM.search(metin))

    @pytest.fixture(scope="session")
    def tarayici():
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            yield b
            b.close()

    def _yeni_sayfa(tarayici, **secenekler):
        baglam = tarayici.new_context(base_url=TABAN, locale="tr-TR", **secenekler)
        sayfa = baglam.new_page()
        hatalar: list[str] = []

        def konsol(mesaj):
            if mesaj.type != "error":
                return
            konum = (mesaj.location or {}).get("url", "")
            if not _kabul_edilebilir(mesaj.text, konum):
                hatalar.append(f"{mesaj.text} @ {konum}")

        sayfa.on("console", konsol)
        sayfa.on("pageerror", lambda hata: hatalar.append(f"pageerror: {hata}"))
        return baglam, sayfa, hatalar

    @pytest.fixture
    def sayfa(tarayici):
        """Her test için yeni bağlam (çerez/oturum paylaşılmaz); sonunda konsol hatası olmamalı."""
        baglam, s, hatalar = _yeni_sayfa(tarayici, viewport={"width": 1366, "height": 900})
        yield s
        baglam.close()
        assert hatalar == [], "JS konsol hataları:\n" + "\n".join(hatalar)

    @pytest.fixture
    def mobil_sayfa(tarayici):
        baglam, s, hatalar = _yeni_sayfa(tarayici, viewport={"width": 360, "height": 780},
                                        device_scale_factor=2, is_mobile=True, has_touch=True)
        yield s
        baglam.close()
        assert hatalar == [], "JS konsol hataları (mobil):\n" + "\n".join(hatalar)

    @pytest.fixture(scope="session")
    def ekran_klasoru() -> Path:
        EKRANLAR.mkdir(exist_ok=True)
        return EKRANLAR

    @pytest.fixture(scope="session")
    def yonetici() -> tuple[str, str]:
        kullanici = os.environ.get("CR_SHOP_YONETICI", "yonetici")
        parola = os.environ.get("CR_SHOP_YONETICI_PAROLA")
        if not parola:
            pytest.fail("CR_SHOP_YONETICI_PAROLA tanımlı değil (kimlik Excel'i, 'cr-shop-demo' satırı)")
        return kullanici, parola
```

`e2e/test_kabul.py`:

```python
"""§11 kabul senaryoları 1–4, geri bildirim/yönetim (5), güvenlik (7), TR/EN ve 360 px mobil.

Sahte veri: ad "QATestUser", e-posta her çalışmada benzersiz (zaman damgası).
"""
from __future__ import annotations

import re
import time

import pytest
from playwright.sync_api import Page, expect

KUKA_SKU = "8301033800019"
BASARILI_KART = "4111 1111 1111 1111"
RET_KARTI = "4000 0000 0000 0002"
GECERSIZ_KART = "5555 5555 5555 4444"
SMS_KODU = "000000"
TEST_VKN = "1234567890"          # GİB algoritmasına göre geçerli test VKN'si
PAROLA = "QATest-Parola-2026"
ARAMA_TERIMLERI = ("ABB", "KABLO", "MOTOR", "RÖLE", "SÜRÜCÜ")
SIPARIS_NO = re.compile(r"CR-DEMO-\d{8}-\d{4}")
TEKLIF_NO = re.compile(r"CR-TKL-\d{8}-\d{4}")
KONTROL_SAYFALARI = ["/tr/", "/tr/ara?q=ABB", "/tr/sepet", "/tr/kayit", "/tr/giris", "/tr/teklif",
                     "/tr/yasal/kvkk", "/en/", "/en/kayit"]


# ---------- yardımcılar ----------

def benzersiz_eposta(etiket: str) -> str:
    return f"qatestuser+{etiket}-{time.strftime('%Y%m%d%H%M%S')}-{time.perf_counter_ns() % 100000}@example.com"


def e2e(sayfa: Page, ad: str):
    return sayfa.locator(f'[data-e2e="{ad}"]')


def alan(sayfa: Page, ad: str):
    # name'i olmayan kart son kullanma/CVC alanları id ile bulunur (Görev 14: sunucuya gönderilmezler)
    return sayfa.locator(f'[name="{ad}"], #{ad}')


def doldur(sayfa: Page, ad: str, deger: str | bool) -> bool:
    """Alan varsa türüne göre doldurur; yoksa ya da gizliyse False döner."""
    loc = alan(sayfa, ad)
    if loc.count() == 0:
        return False
    tur = loc.first.evaluate("e => e.tagName === 'SELECT' ? 'select' : (e.type || 'text')")
    if tur == "hidden":
        return False
    if tur == "radio":
        sayfa.locator(f'[name="{ad}"][value="{deger}"]').check()
        return True
    if not loc.first.is_visible():
        return False
    if tur == "select":
        loc.first.select_option(str(deger))
    elif tur == "checkbox":
        loc.first.check() if deger else loc.first.uncheck()
    else:
        loc.first.fill(str(deger))
    return True


def zorunlu(sayfa: Page, ad: str, deger: str | bool) -> None:
    assert doldur(sayfa, ad, deger), f"form alanı bulunamadı: {ad} ({sayfa.url})"


def oturum_acik(sayfa: Page) -> None:
    expect(e2e(sayfa, "cikis")).to_have_count(1)


def kayit_ol(sayfa: Page, dil: str, tip: str, eposta: str, *, ulke: str = "TR", vkn: str | None = None,
             vergi_dairesi: str | None = None, vat_id: str | None = None, sonraki: str | None = None) -> None:
    yol = f"/{dil}/kayit?tip={tip}" + (f"&sonraki={sonraki}" if sonraki else "")
    sayfa.goto(yol)
    doldur(sayfa, "tip", tip)
    zorunlu(sayfa, "ad", "QATestUser")
    zorunlu(sayfa, "eposta", eposta)
    zorunlu(sayfa, "parola", PAROLA)
    doldur(sayfa, "ulke", ulke)
    if vkn:
        zorunlu(sayfa, "vergi_kimlik_no", vkn)
        zorunlu(sayfa, "vergi_dairesi", vergi_dairesi or "Pendik")
    if vat_id:
        doldur(sayfa, "vat_id", vat_id)
    zorunlu(sayfa, "kvkk_onay", True)
    e2e(sayfa, "kayit-gonder").click()
    sayfa.wait_for_load_state()
    assert "/kayit" not in sayfa.url, f"kayıt başarısız: {sayfa.url}"
    oturum_acik(sayfa)


def sepete_eklenebilir_urun_ac(sayfa: Page, dil: str) -> str:
    """Arama ile (kabul §11.1: 'ürün aranır') sepete eklenebilen ilk ürünü açar; yolunu döner."""
    for terim in ARAMA_TERIMLERI:
        sayfa.goto(f"/{dil}/ara?q={terim}")
        baglantilar = [a.get_attribute("href") for a in e2e(sayfa, "urun-baglanti").all()[:12]]
        for href in baglantilar:
            sayfa.goto(href)
            if e2e(sayfa, "sepete-ekle").count() > 0:
                return href
    pytest.fail(f"sepete eklenebilir ürün bulunamadı: {ARAMA_TERIMLERI}")


def sepete_ekle_ve_sepete_git(sayfa: Page, dil: str) -> None:
    e2e(sayfa, "sepete-ekle").first.click()
    sayfa.wait_for_load_state("networkidle")
    sayfa.goto(f"/{dil}/sepet")
    expect(e2e(sayfa, "sepet-kalemi").first).to_be_visible()


def odeme_formu(sayfa: Page, *, ulke: str, teslim: str) -> None:
    tr = ulke == "TR"
    zorunlu(sayfa, "teslimat_ad_soyad", "QATestUser Teslim")
    zorunlu(sayfa, "teslimat_satir1", "Test Mah. Demo Sok. No:1" if tr else "Teststrasse 1")
    zorunlu(sayfa, "teslimat_sehir", "İstanbul" if tr else "Berlin")
    doldur(sayfa, "teslimat_posta_kodu", "34906" if tr else "10115")
    zorunlu(sayfa, "teslimat_ulke", ulke)
    doldur(sayfa, "teslimat_telefon", "+90 555 000 00 00" if tr else "+49 30 000000")
    doldur(sayfa, "fatura_ayni", True)
    zorunlu(sayfa, "teslim", teslim)
    doldur(sayfa, "on_bilgi_onay", True)
    doldur(sayfa, "mesafeli_onay", True)
    doldur(sayfa, "kosullar_onay", True)   # kurumsal / yurt dışı (Görev 14)


def odemeye_gec_ve_siparis_ac(sayfa: Page, dil: str, *, ulke: str, teslim: str) -> str:
    sayfa.goto(f"/{dil}/odeme")
    odeme_formu(sayfa, ulke=ulke, teslim=teslim)
    e2e(sayfa, "odeme-gonder").click()
    sayfa.wait_for_url(re.compile(rf"/{dil}/odeme/CR-DEMO-\d{{8}}-\d{{4}}/kart"))
    return SIPARIS_NO.search(sayfa.url).group(0)


def kart_gir(sayfa: Page, kart: str) -> None:
    zorunlu(sayfa, "kart_no", kart)
    doldur(sayfa, "kart_ad", "QATestUser")
    doldur(sayfa, "kart_skt", "12/30")
    doldur(sayfa, "kart_cvc", "123")
    e2e(sayfa, "kart-gonder").click()
    sayfa.wait_for_load_state()


def sms_gir(sayfa: Page) -> None:
    sayfa.wait_for_url(re.compile(r"/odeme/CR-DEMO-\d{8}-\d{4}/3d"))
    zorunlu(sayfa, "sms_kodu", SMS_KODU)
    e2e(sayfa, "sms-gonder").click()
    sayfa.wait_for_load_state()


def basarili_ode(sayfa: Page, dil: str, no: str) -> None:
    if f"/odeme/{no}/kart" not in sayfa.url:
        sayfa.goto(f"/{dil}/odeme/{no}/kart")
    kart_gir(sayfa, BASARILI_KART)
    sms_gir(sayfa)
    sayfa.wait_for_url(re.compile(rf"/{dil}/siparis/{no}"))
    expect(e2e(sayfa, "siparis-durum")).to_have_attribute("data-durum", "odendi")


def hesabimda_gorunur(sayfa: Page, dil: str, no: str) -> None:
    sayfa.goto(f"/{dil}/hesabim")
    expect(sayfa.get_by_text(no).first).to_be_visible()


def yonetime_gir(sayfa: Page, yonetici: tuple[str, str]) -> None:
    sayfa.goto("/yonetim/giris")
    zorunlu(sayfa, "kullanici", yonetici[0])
    zorunlu(sayfa, "parola", yonetici[1])
    e2e(sayfa, "yonetim-giris").click()
    sayfa.wait_for_load_state()
    assert "/yonetim/giris" not in sayfa.url, "yönetici girişi başarısız"


def tercih_sec(sayfa: Page, ad: str, deger: str, beklenen_url: re.Pattern) -> None:
    form = sayfa.locator('form[action="/tercih"]').first
    form.locator(f'select[name="{ad}"]').select_option(deger)
    try:
        sayfa.wait_for_url(beklenen_url, timeout=2000)   # JS seçimde formu kendisi gönderiyorsa
    except Exception:
        form.locator('[type="submit"]').first.click()
        sayfa.wait_for_url(beklenen_url)


# ---------- §11.1 Bireysel TR siparişi ----------

def test_senaryo1_bireysel_tr_siparisi(sayfa: Page):
    sepete_eklenebilir_urun_ac(sayfa, "tr")
    fiyat = e2e(sayfa, "fiyat-ana").first
    expect(fiyat).to_have_attribute("data-para", "TRY")
    expect(fiyat).to_have_attribute("data-kdv", "dahil")
    expect(fiyat).to_contain_text("₺")
    expect(sayfa.locator(".rozet-temsili").first).to_be_visible()
    sepete_ekle_ve_sepete_git(sayfa, "tr")

    e2e(sayfa, "odemeye-gec").click()
    sayfa.wait_for_url(re.compile(r"/tr/giris"))   # misafir ödemesi yok
    kayit_ol(sayfa, "tr", "bireysel", benzersiz_eposta("bireysel"), sonraki="/tr/odeme")

    sayfa.goto("/tr/sepet")                            # misafir sepeti üye sepetine geçti
    expect(e2e(sayfa, "sepet-kalemi").first).to_be_visible()
    no = odemeye_gec_ve_siparis_ac(sayfa, "tr", ulke="TR", teslim="kargo")
    expect(e2e(sayfa, "satir-kdv").first).to_be_visible()
    basarili_ode(sayfa, "tr", no)
    hesabimda_gorunur(sayfa, "tr", no)


# ---------- §11.2 Kurumsal TR siparişi (+ §11.7 test dışı kart reddi) ----------

def test_senaryo2_kurumsal_tr_ret_sonra_basari(sayfa: Page):
    kayit_ol(sayfa, "tr", "kurumsal", benzersiz_eposta("kurumsal"), vkn=TEST_VKN, vergi_dairesi="Pendik",
             sonraki="/tr/")
    sepete_eklenebilir_urun_ac(sayfa, "tr")
    fiyat = e2e(sayfa, "fiyat-ana").first
    expect(fiyat).to_have_attribute("data-para", "EUR")
    expect(fiyat).to_have_attribute("data-kdv", "haric")
    expect(e2e(sayfa, "fiyat-ikincil").first).to_contain_text("₺")
    sepete_ekle_ve_sepete_git(sayfa, "tr")
    expect(e2e(sayfa, "satir-kdv").first).to_be_visible()   # KDV sepette ayrı satır

    no = odemeye_gec_ve_siparis_ac(sayfa, "tr", ulke="TR", teslim="kargo")

    kart_gir(sayfa, GECERSIZ_KART)                             # test kartı değil -> sunucu reddeder
    expect(sayfa.locator('[data-e2e="odeme-hata"][data-kod="gecersiz_kart"]')).to_be_visible()
    assert "/3d" not in sayfa.url

    sayfa.goto(f"/tr/odeme/{no}/kart")
    kart_gir(sayfa, RET_KARTI)
    sms_gir(sayfa)
    expect(sayfa.locator('[data-e2e="odeme-hata"][data-kod="ret"]')).to_be_visible()

    basarili_ode(sayfa, "tr", no)                              # aynı sipariş, yeni sipariş açılmaz
    hesabimda_gorunur(sayfa, "tr", no)


# ---------- §11.3 Yurt dışı siparişi (EN) ----------

def test_senaryo3_yurtdisi_en_ihracat_istisnasi(sayfa: Page):
    kayit_ol(sayfa, "en", "yurtdisi", benzersiz_eposta("yurtdisi"), ulke="DE", vat_id="DE123456789",
             sonraki="/en/")
    expect(sayfa.locator("html")).to_have_attribute("lang", "en")
    sepete_eklenebilir_urun_ac(sayfa, "en")
    fiyat = e2e(sayfa, "fiyat-ana").first
    expect(fiyat).to_have_attribute("data-para", "EUR")
    expect(fiyat).to_have_attribute("data-kdv", "haric")
    sepete_ekle_ve_sepete_git(sayfa, "en")

    no = odemeye_gec_ve_siparis_ac(sayfa, "en", ulke="DE", teslim="yurtdisi_dap")
    expect(e2e(sayfa, "satir-ihracat").first).to_be_visible()
    expect(e2e(sayfa, "not-dap").first).to_be_visible()
    expect(e2e(sayfa, "satir-kdv")).to_have_count(0)
    basarili_ode(sayfa, "en", no)
    expect(e2e(sayfa, "satir-ihracat").first).to_be_visible()
    hesabimda_gorunur(sayfa, "en", no)


# ---------- §11.4 Teklif (KUKA) ----------

def test_senaryo4_kuka_teklif_yonetimde_listelenir(sayfa: Page, yonetici):
    sayfa.goto(f"/tr/ara?q={KUKA_SKU}")
    e2e(sayfa, "urun-baglanti").first.click()
    sayfa.wait_for_url(re.compile(r"/tr/urun/\d+"))
    expect(sayfa.get_by_text("KUKA KRC5 KR 140 R3200-2 PA").first).to_be_visible()
    expect(e2e(sayfa, "sepete-ekle")).to_have_count(0)
    e2e(sayfa, "teklif-iste").first.click()
    sayfa.wait_for_url(re.compile(r"/tr/teklif"))

    zorunlu(sayfa, "ad", "QATestUser")
    doldur(sayfa, "firma", "QATest Otomasyon A.Ş.")
    zorunlu(sayfa, "eposta", benzersiz_eposta("teklif"))
    doldur(sayfa, "telefon", "+90 555 000 00 00")
    doldur(sayfa, "ulke", "TR")
    doldur(sayfa, "adet", "1")
    zorunlu(sayfa, "mesaj", "QATest: KUKA KRC5 için fiyat ve teslim süresi rica ederiz.")
    e2e(sayfa, "teklif-gonder").click()
    sayfa.wait_for_url(re.compile(r"/tr/teklif/tamam"))
    no = TEKLIF_NO.search(e2e(sayfa, "teklif-no").inner_text()).group(0)

    yonetime_gir(sayfa, yonetici)
    sayfa.goto("/yonetim/teklifler")
    expect(sayfa.get_by_text(no).first).to_be_visible()


# ---------- §11.5 Geri bildirim ve son eşitleme yönetimde ----------

def test_geri_bildirim_yonetimde_gorunur_ve_son_esitleme(sayfa: Page, yonetici):
    metin = f"QATest geri bildirim {time.strftime('%Y%m%d%H%M%S')}"
    sayfa.goto("/tr/")
    sayfa.locator("#gb-dugme").click()
    pencere = sayfa.locator("#gb-pencere")
    expect(pencere).to_be_visible()
    pencere.locator('[name="metin"]').fill(metin)
    pencere.locator('[name="isim"]').fill("QATestUser")
    pencere.locator('[type="submit"]').click()
    expect(e2e(sayfa, "gb-tamam")).to_be_visible()

    yonetime_gir(sayfa, yonetici)
    sayfa.goto("/yonetim")
    expect(e2e(sayfa, "son-esitleme")).to_have_text(re.compile(r"\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2}"))
    sayfa.goto("/yonetim/geri-bildirimler")
    expect(sayfa.get_by_text(metin).first).to_be_visible()


# ---------- TR/EN geçişi ----------

def test_tr_en_gecisi_yolu_ve_tr_fiyatini_korur(sayfa: Page):
    yol = sepete_eklenebilir_urun_ac(sayfa, "tr")
    urun_kimligi = re.search(r"/urun/(\d+)", yol).group(1)
    tercih_sec(sayfa, "dil", "en", re.compile(rf"/en/urun/{urun_kimligi}"))
    expect(sayfa.locator("html")).to_have_attribute("lang", "en")
    # Ülke dilden bağımsız: EN arayüzdeki Türkiye ziyaretçisi yine TRY ve KDV dahil görür
    expect(e2e(sayfa, "fiyat-ana").first).to_have_attribute("data-para", "TRY")
    tercih_sec(sayfa, "dil", "tr", re.compile(rf"/tr/urun/{urun_kimligi}"))
    expect(sayfa.locator("html")).to_have_attribute("lang", "tr")


# ---------- §11.7 güvenlik: CSP, satır içi script/stil yok, demo bandı ----------

@pytest.mark.parametrize("yol", KONTROL_SAYFALARI)
def test_guvenlik_basliklari_ve_satir_ici_kod_yok(sayfa: Page, yol: str):
    yanit = sayfa.goto(yol)
    assert yanit is not None and yanit.status == 200, f"{yol}: {yanit and yanit.status}"
    basliklar = yanit.all_headers()
    assert "script-src 'self'" in basliklar.get("content-security-policy", "")
    assert basliklar.get("x-robots-tag") == "noindex, nofollow"
    assert sayfa.evaluate("() => [...document.scripts].filter(s => !s.src).length") == 0, "satır içi <script> var"
    assert sayfa.evaluate("() => document.querySelectorAll('[style]').length") == 0, "style=\"\" özniteliği var"
    expect(sayfa.locator(".demo-bandi")).to_be_visible()


# ---------- 360 px mobil ekran görüntüleri ----------

@pytest.mark.parametrize("yol", KONTROL_SAYFALARI)
def test_mobil_360_ekran_goruntusu_ve_yatay_tasma_yok(mobil_sayfa: Page, ekran_klasoru, yol: str):
    yanit = mobil_sayfa.goto(yol)
    assert yanit is not None and yanit.status == 200
    mobil_sayfa.wait_for_load_state("networkidle")
    ad = re.sub(r"[^a-z0-9]+", "-", yol.lower()).strip("-") or "kok"
    mobil_sayfa.screenshot(path=str(ekran_klasoru / f"{ad}-360.png"), full_page=True)
    genislik = mobil_sayfa.evaluate("() => document.documentElement.scrollWidth")
    assert genislik <= 360, f"{yol}: yatay taşma ({genislik}px)"


def test_mobil_360_urun_ve_sepet(mobil_sayfa: Page, ekran_klasoru):
    sepete_eklenebilir_urun_ac(mobil_sayfa, "tr")
    mobil_sayfa.screenshot(path=str(ekran_klasoru / "urun-360.png"), full_page=True)
    assert mobil_sayfa.evaluate("() => document.documentElement.scrollWidth") <= 360
    sepete_ekle_ve_sepete_git(mobil_sayfa, "tr")
    mobil_sayfa.screenshot(path=str(ekran_klasoru / "sepet-360.png"), full_page=True)
    assert mobil_sayfa.evaluate("() => document.documentElement.scrollWidth") <= 360
```

- [ ] **Adım 15: Uçtan uca testleri çalıştır (laptop, mevcut Playwright; yeni paket kurulmaz)**

Run: `python -c "import openpyxl, playwright, pytest; print('hazir')"` (Adım 1 ile aynı ön koşul)
Expected: `hazir`. (`pytest` yoksa kullanıcıya bildir ve dur; paket kurma.)

Run:
```bash
CR_SHOP_YONETICI=yonetici CR_SHOP_YONETICI_PAROLA="$(python ~/.cr-shop/kimlik_oku.py cr-shop-demo)" python -m pytest e2e -q
```
Expected: `25 passed` (4 senaryo + 1 geri bildirim/yönetim + 1 TR/EN + 9 güvenlik + 9 mobil + 1 mobil ürün/sepet; FAIL/ERROR yok) ve `e2e/ekranlar/` altında `*-360.png` dosyaları.
Başarısız test varsa: önce seçicinin E2E sözleşmesine uyup uymadığına bak. Şablon eksikse ilgili ekran görevinin dosyasını düzelt (TDD: önce TestClient testi). Testi gevşetme. Düzeltme → commit → `bash dagitim/deploy.sh` → testleri yeniden çalıştır.

Ekran görüntülerine Read aracıyla bak: 360 px'te metin taşması, üst üste binen öğe, okunmayan kontrast olmamalı.

- [ ] **Adım 16: Kabul 5–7 ölçümleri (sudo gerektirenler için önce onay)**

Sudo gerektirmeyenler:

Run:
```bash
curl -sI http://192.168.5.30:3030/tr/ | grep -iE '^(content-security-policy|x-robots-tag|x-frame-options|x-content-type-options|referrer-policy):'
ssh cr-web-demo 'echo "web_MemoryPeak_MB=$(( $(systemctl show -p MemoryPeak --value cr-shop-demo) / 1048576 ))"; systemctl show -p NRestarts --value cr-shop-demo'
for u in http://192.168.5.30/ http://192.168.5.30:3027/; do printf '%s %s\n' "$(curl -s -o /dev/null -w '%{http_code}' "$u")" "$u"; done
```
Expected: beş başlık da var (CSP `default-src 'self'; img-src 'self' https://www.ceylanrobot.com data:; ...`); `web_MemoryPeak_MB` < 600 (uçtan uca testlerden sonra); `NRestarts` 0; iki demo `200`.

**KULLANICIYA GÖSTER VE ONAY AL** — şu iki sudo komutu: (a) crshop olarak salt okunur sayım, (b) `ufw status`. Onaydan sonra:

Run:
```bash
ssh cr-web-demo 'cat > /tmp/cr-kabul-sayim.py' <<'PY'
import sqlite3
c = sqlite3.connect("file:/opt/cr-shop-demo/veri/shop.db?mode=ro", uri=True)
tur = c.execute("SELECT id, bitis, api_toplam, bozuk FROM esitleme_gunlugu WHERE durum = 'tam' ORDER BY id DESC LIMIT 1").fetchone()
aktif = c.execute("SELECT COUNT(*) FROM urun WHERE aktif = 1").fetchone()[0]
beklenen = tur[2] - tur[3]   # spec §11.5: aktif = api_toplam - bozuk
print(f"son_tam_tur={tur[0]} bitis={tur[1]} api_toplam={tur[2]} bozuk={tur[3]} aktif={aktif} -> {'ESIT' if beklenen == aktif else 'FARKLI'}")
c.close()
PY
python ~/.cr-shop/kimlik_oku.py cr-web-demo | ssh cr-web-demo "sudo -S -p '' -u crshop /usr/bin/python3 /tmp/cr-kabul-sayim.py; rm -f /tmp/cr-kabul-sayim.py"
python ~/.cr-shop/kimlik_oku.py cr-web-demo | ssh cr-web-demo "sudo -S -p '' ufw status | grep -E '^(3030|80|3027)'"
```
Expected: `... -> ESIT`; ufw'de `3030/tcp ALLOW 192.168.2.0/24`, `5.0/24`, `11.0/24`, `12.0/24` (4 satır, `comment cr-shop-demo`); 80 ve 3027 satırları kurulumdan önceki gibi.

- [ ] **Adım 17: Yedek ve geri alma tatbikatı (sudo için önce onay)**

**KULLANICIYA GÖSTER VE ONAY AL**: `{ python ~/.cr-shop/kimlik_oku.py cr-web-demo; } | ssh cr-web-demo "sudo -S -p '' /usr/bin/systemctl start cr-shop-yedek"` (gece yedeğini bir kez elle çalıştırır).

Run: (yukarıdaki komut), ardından `ssh cr-web-demo 'journalctl -u cr-shop-yedek -n 3 --no-pager'`
Expected: `yedek: /opt/cr-shop-demo/yedek/shop-<bugün>.db (<boyut>) via sqlite3`.

Geri alma tatbikatı (sudo yalnız parolasız kuraldan; ikinci release gerektirir):

Run:
```bash
bash dagitim/deploy.sh
ssh cr-web-demo 'cd /opt/cr-shop-demo && ls -1 releases && readlink current'
```
Expected: `TAMAM: <yeni> yayında ...; önceki: <ilk>`; `releases` altında iki klasör; `current` → `releases/<yeni>`.

Run (önceki release'e dön, sağlığı gör, sonra ileri al):
```bash
ssh cr-web-demo 'set -e; cd /opt/cr-shop-demo
  ONCEKI=$(ls -1 releases | sort | tail -n 2 | head -n 1); YENI=$(ls -1 releases | sort | tail -n 1)
  ln -sfn "releases/$ONCEKI" current.yeni && mv -Tf current.yeni current && sudo -n /usr/bin/systemctl restart cr-shop-demo
  sleep 3; echo "geri: $(readlink current) $(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3030/saglik)"
  ln -sfn "releases/$YENI" current.yeni && mv -Tf current.yeni current && sudo -n /usr/bin/systemctl restart cr-shop-demo
  sleep 3; echo "ileri: $(readlink current) $(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3030/saglik)"'
```
Expected: `geri: releases/<ilk> 200` ve `ileri: releases/<yeni> 200`.

- [ ] **Adım 18: Kabul kaydını yaz**

`docs/kabul/kabul-kaydi.md` dosyasını oluştur; her satıra o adımda alınan **gerçek** çıktıyı yaz (komut + değer + tarih/saat):

```markdown
# Satış sitesi mockup'ı — kabul kaydı

Staging: http://192.168.5.30:3030 · VM cr-web-demo · release ve commit: `deploy.sh` son satırından

| § | Ölçüt | Komut / test | Sonuç |
|---|---|---|---|
| 11.1–11.4 | Kabul senaryoları | `python -m pytest e2e -q` (Adım 15) | passed/failed sayısı |
| 11.5 | aktif ürün = son tam turun api_toplam'ı | Adım 16 sayım | `api_toplam=… aktif=… ESIT` |
| 11.5 | Son başarılı eşitleme yönetimde | `test_geri_bildirim_yonetimde_gorunur_ve_son_esitleme` | PASS |
| 11.5 | Geri bildirim yönetimde | aynı test | PASS |
| 11.6 | 80 ve 3027 önce/sonra 200 | Adım 1, 5, 13, 16 | 4 ölçüm |
| 11.6 | cr-shop-esitle MemoryPeak < 400 MB | Adım 11 | `MemoryPeak_MB=…` + journal "memory peak" |
| 11.6 | Eşitleme sırasında kullanılan bellek < 1.500 MB | Adım 11 | `free_kullanilan_en_fazla_MB=…` |
| 11.6 | cr-shop-demo MemoryPeak < 600 MB | Adım 16 | `web_MemoryPeak_MB=…` |
| 11.7 | CSP ve diğer başlıklar | Adım 16 `curl -I` | başlık satırları |
| 11.7 | Satır içi script yok | `test_guvenlik_basliklari_ve_satir_ici_kod_yok` | PASS (9 sayfa) |
| 11.7 | Test dışı kart reddi | `test_senaryo2_...` | PASS |
| 8 | Yedek | Adım 17 | yedek dosyası |
| 8 | Geri alma | Adım 17 tatbikat | geri 200 / ileri 200 |
| 8 | ufw | Adım 16 | 4 kural |
| 11.8 | Bağımsız değerlendirme | Adım 19 | puan |
```

- [ ] **Adım 19: Bağımsız değerlendirme (≥ 8,5/10)**

Ayrı bir ajan başlat (Agent aracı, genel amaçlı, en yetenekli model). Ajan **değişiklik yapmaz**, yalnız okur ve ölçer. İstem:

```text
Ceylan Robot satış sitesi mockup'ını bağımsız olarak değerlendir. Hiçbir dosyayı değiştirme, VM'de sudo kullanma.
Kaynaklar: depo C:\Users\lbell\dev\cr-satis-sitesi (spec docs/specs/2026-10-12-satis-sitesi-mockup-design.md,
özellikle §5, §8, §9, §11), kabul kaydı docs/kabul/kabul-kaydi.md, ekran görüntüleri e2e/ekranlar/*.png,
canlı staging http://192.168.5.30:3030 (Playwright ile gezebilirsin; yeni paket kurma).
Kendin doğrula: 4 kabul senaryosunu tarayıcıda baştan sona yürüt; en az 5 iş kuralını (KDV/kur/teklif eşiği/
yuvarlama/ihracat) kodda ve birim testlerinde kontrol et; §9'daki hata durumlarından en az 4'ünü dene
(bozuk adet, kurcalanmış sonraki=, test dışı kart, var olmayan ürün); 360 px görüntüleri ve TR/EN geçişini incele;
dagitim/ ve betikler/ altındaki geri alma, yedek, eşitleme günlüğü akışlarını oku.
Rubrik (spec §11.8), her eksene 0–10 puan ve gerekçe:
  Kabul senaryoları (1–4) eksiksiz çalışıyor  %25
  İş kuralları doğru (fiyat/KDV/kur/teklif; birim testleri dahil)  %20
  Görsel kalite ve tutarlılık (kurumsal tema, mobil 360 px)  %15
  Kullanılabilirlik (gezinme, hata mesajları, TR/EN)  %15
  Güvenlik ve sağlamlık (§5.5, §9)  %15
  İşletme (dağıtım, geri dönüş, yedek, eşitleme günlüğü)  %10
Çıktı: eksen tablosu, ağırlıklı ortalama (2 hane), puanı en çok düşüren bulguların önem sırasına göre listesi
(her biri: dosya/sayfa, gözlem, beklenen, önerilen düzeltme).
```

Sonuç ≥ 8,50 ise puanı ve eksen tablosunu `docs/kabul/kabul-kaydi.md`'nin "11.8" satırına ve dosya sonuna ekle.
Sonuç < 8,50 ise: bulguları önem sırasıyla düzelt (her biri için önce başarısız test, sonra düzeltme, ilgili görevin dosyalarında), commit, `bash dagitim/deploy.sh`, `python -m pytest e2e -q`, sonra **yeni** bir değerlendirme ajanıyla (öncekinin bulgularını vermeden) tekrar değerlendir. Puan ≥ 8,50 olana kadar tekrarla; her turun puanını kabul kaydına ekle.

- [ ] **Adım 20: Satış ekibi kullanıcı testi yönergesini yaz**

`docs/kullanici-testi.md`:

```markdown
# Satış sitesi mockup'ı — kullanıcı testi yönergesi

**Adres:** http://192.168.5.30:3030 (yalnız şirket iç ağından; Wi-Fi misafir ağından açılmaz)
**Amaç:** Siteyi yardım almadan kullanabiliyor muyuz, nerede takılıyoruz? Test edilen site, kişi değil.

## Başlamadan önce
- Bu bir **demo**: gerçek satış ve ödeme yapılmaz, fiyatlar temsilidir.
- Gerçek kişi, müşteri veya kart bilgisi **girmeyin**. Ad olarak `QATestUser`, e-posta olarak
  `qatestuser+<adınız>-<sayı>@example.com` kullanın. Parola olarak işte kullandığınız bir parolayı **kullanmayın**.
- Test kartları: başarılı `4111 1111 1111 1111`, banka reddi `4000 0000 0000 0002`, SMS kodu `000000`.
  Son kullanma tarihi ve güvenlik kodu için herhangi bir değer yazabilirsiniz.

## Senaryolar (her biri en fazla 10 dakika)
1. **Bireysel sipariş (Türkiye):** Bir ürünü arayarak bulun, sepete ekleyin. Bireysel müşteri olarak kayıt olun,
   sözleşmeleri onaylayın, başarılı test kartıyla ödeyin. Siparişi "Hesabım"da bulun.
2. **Kurumsal sipariş (Türkiye):** Kurumsal müşteri olarak kayıt olun (VKN: `1234567890`, vergi dairesi: herhangi).
   Bir ürünü sepete ekleyin. Önce **ret kartıyla** ödemeyi deneyin, sonra aynı siparişi başarılı kartla tamamlayın.
3. **Yurt dışı sipariş:** Sitenin dilini İngilizceye çevirin. Yurt dışı müşteri olarak (ör. Almanya) kayıt olun,
   bir ürünü yurt dışı teslimle sipariş edin. Tutarlarda KDV yerine ne yazdığına dikkat edin.
4. **Robot için teklif:** `8301033800019` kodlu KUKA robotunu bulun ve bu ürün için teklif isteyin.

## Gözlemci kuralları
- Kullanıcının yanında oturun ama **ipucu vermeyin**: "şuraya tıkla", "aşağıda" demeyin. Sorulursa
  "Siz ne yapardınız?" deyin.
- Süreyi tutun. 10 dakikada bitmeyen ya da kullanıcının vazgeçtiği senaryo **bulgu** olarak yazılır; kullanıcının hatası sayılmaz.
- Takılınan yeri (sayfa ve ne aranıyordu), kullanıcının yüksek sesle söylediklerini ve süreyi not edin.
- Kullanıcı başka bir senaryoya geçmeden önce aynı tarayıcıda **çıkış yapsın** ya da gizli pencere açsın.

## Geri bildirim
- Her sayfanın sağ altında **"Geri bildirim"** düğmesi var. Gördüğünüz sorunu ya da öneriyi o sayfadayken yazın;
  sayfa adresi otomatik eklenir. "Kaydedildi" mesajını görünce gönderilmiştir.
- Gözlemci notları test bitince aynı düğmeyle ya da BT birimine iletilir.
```

- [ ] **Adım 21: Hive ve Vault kaydı**

`C:\Users\lbell\hive\hosts\machines.md` — cr-web-demo satırında (Edit):
- old: ``AIC Otomotiv 2027 demosu **http://192.168.5.30:3027/** (`aic-demo.service`); yalnız VLAN 2/5/11/12``
- new: ``AIC Otomotiv 2027 demosu **http://192.168.5.30:3027/** (`aic-demo.service`), satış sitesi mockup'ı **http://192.168.5.30:3030/** (`cr-shop-demo.service`, kullanıcı `crshop`, `/opt/cr-shop-demo`, zamanlayıcılar 02:30 eşitleme / 03:00 yedek / 06:00 kur; ayrıntı Vault 08-Website/Satis-Sitesi-Mockup.md); yalnız VLAN 2/5/11/12``

Run: `git -C /c/Users/lbell/hive add hosts/machines.md && git -C /c/Users/lbell/hive -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m "hosts: cr-web-demo uzerinde satis sitesi mockup'i (3030)"`
Expected: `1 file changed`. (Push oturum sonu hook'uyla yapılır.)

`C:\Users\lbell\Documents\Vault-CR\08-Website\Satis-Sitesi-Mockup.md` (Create). `<...>` ile işaretli yerlere Adım 9, 11, 16 ve 19'un gerçek değerleri yazılır:

~~~markdown
# Satış sitesi mockup'ı (staging)

Tıklanabilir e-ticaret prototipi: Netsis kaynaklı gerçek ürünler (ceylanrobot.com public API'sinden gece eşitleme),
TR/EN, bireysel/kurumsal/yurt dışı, simüle ödeme, teklif akışı. Depo: `C:\Users\lbell\dev\cr-satis-sitesi`;
spec `docs/specs/2026-10-12-satis-sitesi-mockup-design.md`; kabul kaydı `docs/kabul/kabul-kaydi.md`.

## Erişim
- Adres: **http://192.168.5.30:3030** (cr-web-demo VM; 80 mustafaceylan demosu, 3027 AIC demosu — bağımsız).
- Yönetim: `/yonetim`, kullanıcı `yonetici`; parola kimlik Excel'inde ("Sunucular", "cr-shop-demo yönetim" satırı).
- ufw: 3030/tcp yalnız 192.168.2.0/24, 192.168.5.0/24, 192.168.11.0/24, 192.168.12.0/24.
- Kullanıcı testi yönergesi: depo `docs/kullanici-testi.md`.

## Kurulum
- Kurulum tarihi: <Adım 9 tarihi>; ilk release: <release adı, commit>.
- Klasör `/opt/cr-shop-demo`: `releases/<YYYYMMDD-HHMM>/` (her biri kendi `venv/`), `current` → etkin release,
  `veri/shop.db` (+ `shop-onceki-<release>.db`, son 3), `yedek/shop-YYYYMMDD.db` (7 gün), `ortam` (600, crshop).
- Servis kullanıcısı `crshop` (sistem, kabuk yok). Dağıtıcı `crwebdemo`; parolasız sudo yalnız
  `/etc/sudoers.d/cr-shop-demo`'daki üç komut için.
- systemd: `cr-shop-demo.service` (uvicorn, 1 worker, MemoryMax 600M, Restart=always);
  `cr-shop-esitle.timer` 02:30 (MemoryMax 400M, 30 dk); `cr-shop-yedek.timer` 03:00; `cr-shop-kur.timer` 06:00.
- İlk ölçümler: eşitleme <api_toplam> ürün, MemoryPeak <…> MB; web MemoryPeak <…> MB;
  bağımsız değerlendirme <puan>/10.

## İşletme
- Dağıtım (laptop, depo kökü, temiz ağaç): `bash dagitim/deploy.sh` — VM'de test, yedek, geçiş, sağlık kontrolü;
  başarısızsa otomatik geri döner.
- Günlükler: `journalctl -u cr-shop-demo`, `-u cr-shop-esitle`, `-u cr-shop-yedek`, `-u cr-shop-kur`.
- Elle eşitleme: `sudo systemctl start cr-shop-esitle` (parolasız kural var).
- birim dosyaları değişirse: depo kopyasıyla `sudo bash dagitim/kurulum-vm.sh` yeniden çalıştırılır.

## Geri alma
```bash
cd /opt/cr-shop-demo && ls -1 releases            # önceki release'i seç
ln -sfn releases/<önceki> current.yeni && mv -Tf current.yeni current
sudo systemctl restart cr-shop-demo && curl -s http://127.0.0.1:3030/saglik
# Veritabanı gerekirse (servis durdurulmuşken): crshop olarak veri/shop-onceki-<release>.db -> veri/shop.db
```

## Tamamen kaldırma
```bash
sudo systemctl disable --now cr-shop-demo.service cr-shop-esitle.timer cr-shop-yedek.timer cr-shop-kur.timer
sudo rm -f /etc/systemd/system/cr-shop-*.service /etc/systemd/system/cr-shop-*.timer /etc/sudoers.d/cr-shop-demo
sudo systemctl daemon-reload
for ag in 192.168.2.0/24 192.168.5.0/24 192.168.11.0/24 192.168.12.0/24; do sudo ufw delete allow proto tcp from "$ag" to any port 3030; done
sudo rm -rf /opt/cr-shop-demo
sudo userdel crshop
```
Kimlik Excel'indeki "cr-shop-demo yönetim" satırı silinir; hive `hosts/machines.md` güncellenir.
~~~

Not: Vault notunda kişi adı geçmez; roller kullanılır (BT birimi, satış ekibi).

- [ ] **Adım 22: VM'deki geçici araç kopyasını temizle (sudo yok)**

Run: `ssh cr-web-demo 'rm -rf ~/cr-shop-araclar ~/cr-shop-systemd-dogrula && ls ~ | grep -c cr-shop || true'`
Expected: `0`. (Yönetici özeti yeniden gerekirse Adım 3 ve 7 tekrarlanır.)

- [ ] **Adım 23: Commit**

```bash
git add .gitignore e2e/conftest.py e2e/test_kabul.py docs/kabul/kabul-kaydi.md docs/kullanici-testi.md
git status --short   # e2e/ekranlar/ listede OLMAMALI
git -c user.name="Sami Yilmaz" -c user.email=samiyilmaz@ceylanrobot.com commit -m "test: uctan uca kabul testleri, kabul kaydi ve kullanici testi yonergesi

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Entegrasyon durumu

- K1: `esitle.py` JSON'u `TurSonucu`'nun tüm alanlarını (`bozuk` dahil) basar; `hata` → çıkış 1, `tam`/`eksik` → 0; eksik tur testi eklendi.
- K7: testler depo kökünden `python -m pytest`; `tests/test_isletme.py` conftest'ten import yapmaz.
- K10: `app/web/asgi.py` `uygulama()` + `uvicorn --factory app.web.asgi:uygulama` (Görev 17).
- K12: Görev 18'deki `data-e2e`/form alanı tablosu bağlayıcı, değiştirilmedi; e2e yalnız ona dayanır.
- K16: e2e ve kullanıcı testi kurumsal kayıtta VKN `1234567890` kullanır.
- K18: duman testi `/saglik` `urun` alanını aktif ürün sayısı olarak okur.
- K19: betikler `python -m betikler.*`; `betikler/__init__.py`, `app/gecis_calistir.py`, `dagitim/uzak-yayinla.sh` Görev 17'de; `.gitattributes` Görev 1'in, burada yalnız kontrol.
- Spec §11.6: `cr-shop-esitle` MemoryPeak çalışırken örneklenir + journal "memory peak" satırı.

---

