-- G3e düzeltme turu 3: ödeme zamanı (kart başarısı ya da yönetimin "ödendi" işareti). Ödenmiş siparişin stok
-- ayırması yalnız bu zaman son başarılı tam eşitlemenin bitişinden sonraysa sürer (app/stok.py).
-- Eski ödenmiş siparişlerde NULL: ayırma hesabı olusturma zamanını kullanır.
ALTER TABLE siparis ADD COLUMN odeme_zamani TEXT;
