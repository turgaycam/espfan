-- G3i madde 6: müşterinin satın alma (PO) numarası (isteğe bağlı, en çok 40 karakter; web katmanı denetler).
ALTER TABLE siparis ADD COLUMN musteri_po TEXT;
ALTER TABLE teklif ADD COLUMN musteri_po TEXT;
-- G3i inceleme I-1: alıcı kimliğinin sipariş anındaki anlık görüntüsü (proforma, onay, Hesabım ayrıntısı). Hesapta
-- "Fatura bilgilerim" sonradan değişse de eski siparişin belgeleri değişmez. Eski satırlarda NULL kalır (yedek:
-- unvan için fatura adresindeki ad, vergi bilgileri için hesaptaki değer — yalnız NULL iken).
ALTER TABLE siparis ADD COLUMN alici_unvan TEXT;
ALTER TABLE siparis ADD COLUMN alici_tip TEXT;
ALTER TABLE siparis ADD COLUMN alici_vkn TEXT;
ALTER TABLE siparis ADD COLUMN alici_vergi_dairesi TEXT;
ALTER TABLE siparis ADD COLUMN alici_vat_id TEXT;
-- G3i madde 16: hızlı talepte aciliyet ('acil' | 'bu_hafta' | 'planli'; seçilmezse NULL) ve robot/kontrolör modeli
-- (isteğe bağlı). Yönetim listesinde acil talepler üstte.
ALTER TABLE teklif ADD COLUMN aciliyet TEXT;
ALTER TABLE teklif ADD COLUMN model TEXT;
