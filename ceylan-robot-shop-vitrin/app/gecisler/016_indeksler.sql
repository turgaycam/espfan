-- Son inceleme M-11: sıcak sorgular için indeksler (yalnız ekleme; geri uyumlu, ikinci kez uygulanabilir).
-- siparis_kalemi(siparis_id): sipariş ayrıntısı / listeleri her siparişin kalemlerini siparis_id ile okur.
-- siparis(durum): ayrilan_adetler her katalog isteğinde açık siparişleri durumla süzer.
CREATE INDEX IF NOT EXISTS ix_siparis_kalemi_siparis ON siparis_kalemi(siparis_id);
CREATE INDEX IF NOT EXISTS ix_siparis_durum ON siparis(durum);
