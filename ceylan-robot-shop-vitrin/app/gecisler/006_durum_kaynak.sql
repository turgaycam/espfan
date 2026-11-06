-- G3b düzeltme turu 1: durumun kaynağı ve genel "2. el" kodu.
--   durum_kaynak = 'cikarim': eşitleme kaynak metninden çıkardı (her turda yeniden hesaplanır; çıkarım kalkarsa
--   'belirtilmemis'e döner). NULL: varsayılan, örnek (durum_ornek=1) ya da elle girilmiş değer (eşitleme dokunmaz).
--   durum_kodu 'ikinci_el' (genel 2. el) yeni bir değerdir; TEXT sütun, tablo değişmez.
ALTER TABLE urun ADD COLUMN durum_kaynak TEXT;
-- 005 ile çıkarılmış durumlar işaretlenir: 005'ten önce örnek dışı (durum_ornek=0) belirtilmiş durum yazan tek yol
-- eşitleme çıkarımıdır (yönetim panelinde durum düzenleme yok). Eski kural "ikinci el" kaydını 'ikinci_el_oldugu_gibi'
-- yazıyordu: genel koda çevrilir. Kalan eski çıkarımlar (ör. "new"/"sıfır" -> 'yeni') bir sonraki eşitlemede yeni
-- kuralla yeniden hesaplanır (çıkarım yoksa 'belirtilmemis').
UPDATE urun SET durum_kaynak = 'cikarim' WHERE durum_ornek = 0 AND durum_kodu != 'belirtilmemis';
UPDATE urun SET durum_kodu = 'ikinci_el' WHERE durum_kaynak = 'cikarim' AND durum_kodu = 'ikinci_el_oldugu_gibi';
