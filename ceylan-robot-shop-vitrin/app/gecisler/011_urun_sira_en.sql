-- G3f düzeltme turu 1 (M-2): /en listede "ada göre" sıralama görünen EN ada göre. sira_anahtari_en = geçerli EN
-- çevirinin normalize hâli, yoksa TR sira_anahtari. indeksi_yeniden_kur (eşitleme her turda) ve ceviri_yukle doldurur;
-- NULL kalan satırda sorgu TR anahtarına düşer.
ALTER TABLE urun ADD COLUMN sira_anahtari_en TEXT;
CREATE INDEX ix_urun_sira_en ON urun(sira_anahtari_en, id);
