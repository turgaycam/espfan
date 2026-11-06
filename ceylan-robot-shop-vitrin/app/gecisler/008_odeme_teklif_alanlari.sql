-- G3e madde 15: sipariş ödeme yöntemi (kart: mevcut akış, 30 dk zaman aşımı; havale: proforma ile havale/EFT,
-- yalnız kurumsal ve yurt dışı müşteri; "ödeme bekleniyor" durumunda kalır, zaman aşımı uygulanmaz).
ALTER TABLE siparis ADD COLUMN odeme_yontemi TEXT NOT NULL DEFAULT 'kart' CHECK (odeme_yontemi IN ('kart','havale'));
-- G3e madde 17: teklif formunun isteğe bağlı yeni alanları (girişli kurumsalda VKN/vergi dairesi profilden gelir).
ALTER TABLE teklif ADD COLUMN vkn TEXT;
ALTER TABLE teklif ADD COLUMN vergi_dairesi TEXT;
ALTER TABLE teklif ADD COLUMN istenen_tarih TEXT;   -- YYYY-MM-DD
ALTER TABLE teklif ADD COLUMN hedef_fiyat TEXT;     -- serbest metin: hedef fiyat / iskonto notu
ALTER TABLE teklif ADD COLUMN parca_kodu TEXT;      -- ürünsüz formda ya da hızlı talepte aranan parça kodu
