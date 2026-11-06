-- G3c madde 21 + G3a endişesi: teklifte e-posta ya da telefondan biri yeterli (telefonla gelen hızlı talepte e-posta
-- artık boş metin değil NULL); isteğe bağlı VAT ID ve misafir KVKK aydınlatma onayı zamanı.
-- SQLite NOT NULL kaldıramaz: tablo yeniden kurulur (teklif tablosuna başvuran yabancı anahtar yok).
CREATE TABLE teklif_yeni (
  id INTEGER PRIMARY KEY, no TEXT NOT NULL UNIQUE, musteri_id INTEGER REFERENCES musteri(id),
  ad TEXT NOT NULL, firma TEXT, eposta TEXT, telefon TEXT, ulke TEXT NOT NULL,
  urun_id INTEGER REFERENCES urun(id), adet INTEGER NOT NULL DEFAULT 1, mesaj TEXT NOT NULL,
  durum TEXT NOT NULL DEFAULT 'yeni' CHECK (durum IN ('yeni','inceleniyor','teklif_verildi','kapandi')),
  olusturma TEXT NOT NULL,
  vat_id TEXT,
  kvkk_onay TEXT,                   -- misafir gönderimde aydınlatma onayı zamanı (ISO); üyede NULL (kayıtta onaylı)
  CHECK (eposta IS NOT NULL OR telefon IS NOT NULL)
);
INSERT INTO teklif_yeni (id, no, musteri_id, ad, firma, eposta, telefon, ulke, urun_id, adet, mesaj, durum, olusturma)
  SELECT id, no, musteri_id, ad, firma,
         CASE WHEN NULLIF(eposta, '') IS NULL AND NULLIF(telefon, '') IS NULL THEN eposta ELSE NULLIF(eposta, '') END,
         NULLIF(telefon, ''), ulke, urun_id, adet, mesaj, durum,
         olusturma
  FROM teklif;
DROP TABLE teklif;
ALTER TABLE teklif_yeni RENAME TO teklif;
