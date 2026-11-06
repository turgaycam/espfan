-- G3g madde 2: çok kalemli teklif (sepeti teklif olarak gönder). Tekli ürün teklifi teklif.urun_id/adet ile kalır;
-- sepetten gelen teklifte kalemler burada, teklif.urun_id NULL ve teklif.adet kalemlerin toplamıdır.
CREATE TABLE teklif_kalem (
  teklif_id INTEGER NOT NULL REFERENCES teklif(id),
  urun_id INTEGER NOT NULL REFERENCES urun(id),
  adet INTEGER NOT NULL CHECK (adet BETWEEN 1 AND 9999)
);
CREATE INDEX ix_teklif_kalem ON teklif_kalem(teklif_id);
-- G3g madde 4: havale siparişinin ödeme son tarihi (oluşturma + SHOP_HAVALE_GUN iş günü). Tarih geçince sipariş
-- "süresi doldu" sayılır ve stok ayırmaz (app/stok.py); yönetim yeniden açınca yeni son tarih yazılır.
-- Eski havale siparişlerine yaklaşık değer (oluşturma + 3 takvim günü) yazılır; kart siparişinde NULL (30 dk kuralı).
ALTER TABLE siparis ADD COLUMN odeme_son_tarih TEXT;
UPDATE siparis SET odeme_son_tarih = strftime('%Y-%m-%dT%H:%M:%S+00:00', olusturma, '+3 days')
  WHERE odeme_yontemi = 'havale';
