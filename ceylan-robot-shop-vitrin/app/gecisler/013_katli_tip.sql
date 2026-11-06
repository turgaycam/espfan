-- G3h: arama ve ürün tipi için türetilmiş alanlar (Python'da hesaplanır: app/katalog/indeks.py turetilmisleri_doldur;
-- eşitleme indeksi_yeniden_kur ile her turda yeniler, mevcut veriyi app/db.py bu geçişten hemen sonra doldurur):
--   katli_metin: ad | SKU | üretici kodu, her biri büyük/küçük harf, boşluk, tire, nokta, eğik çizgi olmadan
--                ("ABB DSQC 626 A GÜÇ KAYNAĞI" -> "abbdsqc626agucka..."); bitişik kod araması alt dize eşleşmesiyle
--   teknik_var:  teknik özellik verisi var mı (Önerilen sıralama)
--   tip:         ürün tipi (app/katalog/tip.yaml; ad, yoksa kategori yolu) — "Ürün tipi" faseti ve arama alakası
ALTER TABLE urun ADD COLUMN katli_metin TEXT NOT NULL DEFAULT '';
ALTER TABLE urun ADD COLUMN tip TEXT NOT NULL DEFAULT 'diger';
-- teknik_var: urun_teknik'te en az bir teknik özellik satırı var (1/0) — "Önerilen" sıralama puanı (G3h inceleme M-6:
-- istek sırasında satır başına JSON alt sorgusu yerine eşitlemede bir kez)
ALTER TABLE urun ADD COLUMN teknik_var INTEGER NOT NULL DEFAULT 0;
CREATE INDEX ix_urun_tip ON urun(tip);
-- Arama indeksine kategori (yaprak kategori adı) ve açıklama (TR, urun_aciklama) sütunları: alaka sırasında
-- bm25 ağırlıkları ad > kategori > açıklama. FTS5 tablosuna sütun eklenemez: yeniden kurulur, içerik geçiş sonrası
-- Python adımıyla (indeksi_yeniden_kur) doldurulur.
DROP TABLE urun_ara;
CREATE VIRTUAL TABLE urun_ara USING fts5(metin, kod_birlesik, ad_en, kategori, aciklama, urun_id UNINDEXED,
                                         tokenize='unicode61 remove_diacritics 2');
