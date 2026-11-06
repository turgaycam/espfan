-- G3a: arama/filtre/hız. Türetilmiş ürün alanları (Python'da hesaplanır: app/katalog/indeks.py
-- turetilmisleri_doldur; eşitleme indeksi_yeniden_kur ile her turda yeniler, mevcut veriyi
-- app/db.py bu geçişten hemen sonra doldurur):
--   sira_anahtari: normalize(ad) — ada göre sıralama (tr_sira UDF'si yerine, indeksli)
--   kod_birlesik:  SKU ve üretici kodunun ayraçsız (tire/boşluk/nokta/eğik çizgi) küçük harf biçimleri
--   marka:         app/katalog/marka.py izin listesinden (yoksa NULL) — marka faseti
ALTER TABLE urun ADD COLUMN sira_anahtari TEXT NOT NULL DEFAULT '';
ALTER TABLE urun ADD COLUMN kod_birlesik TEXT NOT NULL DEFAULT '';
ALTER TABLE urun ADD COLUMN marka TEXT;
CREATE INDEX ix_urun_sira ON urun(sira_anahtari, id);
CREATE INDEX ix_urun_marka ON urun(marka);
-- FTS5 tablosuna sütun eklenemez: yeniden kurulur (içerik geçiş sonrası Python ile doldurulur)
DROP TABLE urun_ara;
CREATE VIRTUAL TABLE urun_ara USING fts5(metin, kod_birlesik, urun_id UNINDEXED, tokenize='unicode61 remove_diacritics 2');
