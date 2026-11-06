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
