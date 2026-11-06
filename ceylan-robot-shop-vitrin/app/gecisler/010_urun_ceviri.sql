-- G3f: EN ürün adı ve teknik özellik çevirisi (LLM taslak ya da kaynak). Yalnız betikler.ceviri_yukle yazar;
-- eşitleme bu tabloya YAZMAZ/SİLMEZ. kaynak_ozet = TR ad + teknik satırlarının (urun_teknik.ozellikler) sha256'sının
-- ilk 16 hex'i (app/katalog/urun_ceviri.py kaynak_ozeti). Eşitleme adı/teknik veriyi değiştirirse özet tutmaz ve çeviri
-- gösterilmez (bayat çeviri asla gösterilmez). teknik_json: [[anahtar_en, deger_en], ...], TR satırlarıyla aynı sıra
-- ve sayı; NULL = yalnız ad çevrildi.
CREATE TABLE urun_ceviri (
  urun_id INTEGER NOT NULL REFERENCES urun(id),
  dil TEXT NOT NULL CHECK (dil = 'en'),
  ad TEXT NOT NULL,
  teknik_json TEXT,
  kaynak TEXT NOT NULL CHECK (kaynak IN ('llm-taslak', 'kaynak')),
  model TEXT,
  kaynak_ozet TEXT NOT NULL,
  uretildi TEXT NOT NULL,
  PRIMARY KEY (urun_id, dil)
);
-- Arama: EN ad FTS'e ayrı sütun (ad_en) olarak girer. FTS5 tablosuna sütun eklenemez: mevcut içerik taşınarak yeniden
-- kurulur. ad_en'i yükleme betiği (yazdığı ürünler) ve indeksi_yeniden_kur (geçerli çeviriler) doldurur.
CREATE TEMP TABLE _urun_ara_eski AS SELECT metin, kod_birlesik, urun_id FROM urun_ara;
DROP TABLE urun_ara;
CREATE VIRTUAL TABLE urun_ara USING fts5(metin, kod_birlesik, ad_en, urun_id UNINDEXED, tokenize='unicode61 remove_diacritics 2');
INSERT INTO urun_ara (metin, kod_birlesik, urun_id) SELECT metin, kod_birlesik, urun_id FROM _urun_ara_eski;
DROP TABLE _urun_ara_eski;
