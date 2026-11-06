-- G3b: ürün teknik özellikleri. Eşitleme API techSpecs / descriptionSections alanlarını güvenli düz metne çevirip
-- (app/esitleme/teknik.py: HTML etiketleri ve base64 atılır) ürün başına tek JSON olarak yazar (en çok 8 KB):
--   {"ozellikler": [[etiket, değer], ...], "bolumler": [[başlık, metin], ...]}
-- Kaynakta alan boşalırsa satır silinir. Durum çıkarımı (urun.durum_kodu) aynı turda yapılır; yeni sütun gerekmez.
CREATE TABLE urun_teknik (
  urun_id INTEGER PRIMARY KEY REFERENCES urun(id),
  veri TEXT NOT NULL CHECK (length(CAST(veri AS BLOB)) <= 8192)
);
