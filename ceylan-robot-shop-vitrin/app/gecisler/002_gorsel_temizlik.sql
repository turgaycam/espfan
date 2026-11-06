-- G1: eski eşitlemelerde gorsel_url alanına yazılan base64 (uzun) değerleri temizle;
-- sonraki eşitleme gerçek görsel adreslerini yazar. esitleme_ara geçici bir tablodur.
UPDATE urun SET gorsel_url = NULL WHERE LENGTH(gorsel_url) > 500;
DELETE FROM esitleme_ara;
