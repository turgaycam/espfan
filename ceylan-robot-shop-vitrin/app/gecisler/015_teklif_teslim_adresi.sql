-- G3j madde 16: teklif formunda isteğe bağlı teslim adresi / posta kodu (DAP navlun teklifi için; serbest metin, en çok
-- 200 karakter, web katmanı denetler). Eski satırlarda NULL.
ALTER TABLE teklif ADD COLUMN teslim_adresi TEXT;
