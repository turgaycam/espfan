# SY Hukuk'a sorulacak açık noktalar

Yasal sayfa taslakları (Görev 16) için hukuki onay beklenen konular.

- Yurt dışı tüketiciye satış: cayma hakkı ve ikamet ülkesinin emredici tüketici hükümleri (Roma I m.6); ihracatta hangi alıcılara hangi koşulların uygulanacağı.
- GDPR m.27: AB temsilcisinin atanması, kim olacağı ve künyede yayımlanması.
- Bariz fiyat hatasında tek taraflı iptal hakkı (Kullanım koşulları A.3): 6502 sayılı Kanun m.5 kapsamında haksız şart riski.
- Ön bilgilendirme formunda standart cayma formunun (Yönetmelik ekindeki örnek) eklenmesi gerekip gerekmediği.
- B2B garanti sınırlaması ve "ikinci el – olduğu gibi" satış: TBK m.221 ve m.223, TTK m.23; dolaylı zarar sınırlaması (TBK m.115) ve sorumluluk üst sınırının geçerliliği.
- İkinci el "test edildi" ürünlerde 6 aylık fonksiyon garantisi süresinin kesinleştirilmesi.
- CISG'nin yurt dışı satışlarda uygulanıp uygulanmayacağı; yetkili mahkeme ve uygulanacak hukuk.
- VERBİS, ETBİS ve İYS kayıt durumları ile yükümlülüklerin kapsamı.
- Künyedeki "[doldurulacak]" alanlarının (MERSİS, sicil, vergi, KEP, e-posta, meslek kuruluşu, yer sağlayıcı) şirket kayıtlarından tamamlanması.

## Ürün sayfası ihracat metni (G3b, 13.10.2026)
- **Hukuki gözden geçirme bekliyor:** ürün sayfasında TR dışı teslimde gösterilen ihracat KDV istisnası metni
  ("İhracat: KDV istisnası (KDVK md. 11) · DAP navlun teklifle" / EN "Export: exempt from Turkish VAT (VAT Law art. 11) ·
  DAP freight on quotation"; `app/web/dil/*.json` → `urun.maliyet_ihracat`, `urun.teslim_ozet_ihracat`). İstisnanın
  koşulları (gümrük beyannamesi, fiili ihraç, alıcı türü) ve DAP teslim şekli metnin doğruluğunu etkiler; yayından önce
  mali müşavir/hukuk onayı alınmalı.

## İhracat KDV ve navlun metni (G3e, 13.10.2026)
- TR dışı teslimde ürün, sepet, ödeme, kart ve sipariş sayfalarında tek satır (`app/web/dil/*.json` → `ihracat.kdv_metni`,
  şablon `_ihracat_kdv.html`): "Türkiye KDV'si uygulanmaz (ihracat, KDVK md. 11/1-a). Varış ülkesindeki ithalat KDV'si ve
  gümrük vergileri alıcıya aittir (DAP). VAT numaranız faturada yer alır." + "Ayrıntı" bağlantısı (Kullanım ve Satış
  Koşulları B.3, `#ihracat`). AB içi işlem olmadığından "reverse charge" ifadesi kullanılmaz. Yukarıdaki G3b notundaki
  koşullar (gümrük beyannamesi, fiili ihraç) için onay ihtiyacı sürer.
- DAP siparişte navlun ödeme tutarına dahil değildir; özet "Navlun: teklifle (bu ödemeye dahil değil)" ve "Mal bedeli" der.
- İade satırı müşteri tipine göre: bireysel "İade 14 gün", kurumsal/yurt dışı ticari "Ayıplı ürün: garanti kapsamında
  değişim/iade" (İade sayfası B/C bölümleriyle uyumlu), misafirde ikisi birlikte.
- Yurt dışı müşteri fabrikadan teslim seçerse DAP ibaresi kullanılmaz (`ihracat.kdv_metni_fabrika`): ithalat KDV'si,
  gümrük vergileri ve ihracat formaliteleri alıcıya aittir. Fabrikadan teslimde ihracat istisnasının koşulları
  (fiili ihraç kanıtı) ayrıca teyit edilmeli.

## Navlun, ithalat KDV'si, garanti ve havale metinleri (G3g, 13.10.2026)
- Yurt dışı DAP sepet, ödeme, kart ve proformada (`app/web/dil/*.json` → `tutar.dap_notu`, `tutar.navlun_notu`,
  `tutar.ithalat_notu`): "Teslim şekli: DAP (Incoterms 2020), varış yeri teslimat adresinizdir." + "Navlun dahil
  değildir. Teslimat adresinize göre DAP navlun teklifini 1 iş günü içinde e-postayla iletiriz (temsili); ayrıca
  faturalandırılır." + "İthalat KDV'si ve gümrük vergileri varış ülkesinde gümrükte alıcı tarafından ödenir;
  indirilebilirliği yerel mevzuatınıza bağlıdır." (EN: "Freight is not included. We e-mail a DAP freight quote to your
  delivery address within 1 business day (indicative); it is invoiced separately." / "Import VAT and duties are paid
  by the buyer at customs in the destination country; deductibility depends on your local rules."). Proformada
  "Navlun: teklifle" satırı. Yukarıdaki ihracat KDV istisnası metniyle birlikte gösterilir; "1 iş günü" sözü
  operasyonel taahhüttür, yayından önce satış ekibiyle teyit edilmeli.
- Garanti sayfasına "2. el (genel) / Used (general)" tanımı eklendi: satıştan önce fotoğraf/test raporu; garanti süresi
  teklif ve faturada belirtilir (temsili). Ürün sayfasında durum satırının yanında duruma göre tek satır garanti özeti
  (`urun.garanti_ozeti_*`) ve garanti sayfasındaki tanıma bağlantı. G3g inceleme turu 1 (kontrolcü kararı): ürün
  kartı, karşılaştırma ve ürün sayfasındaki eski güven satırı "Test edilmiştir · 12 ay garanti (temsili)" kaldırıldı;
  yerine aynı duruma göre garanti özeti ve garanti sayfası çapası geldi. Sitede artık garanti süresi yalnız garanti
  sayfasında yazar (test edildi: 6 ay fonksiyon garantisi, kesinleştirilecek); özet satırları süre vermez.
  "Yenilenmiş" durumu garanti sayfasında ayrıca tanımlı değildir; özeti "test edildi" tanımına bağlanır.
- Proformada SWIFT/BIC ve EUR IBAN satırları "(temsili)" yer tutucudur; alıcı unvanı künyedeki unvandır.
- Havale/EFT siparişinde ödeme son tarihi oluşturma + 3 iş günü (`SHOP_HAVALE_GUN`; cumartesi/pazar ve sabit tarihli
  resmî tatiller sayılmaz, dinî bayramlar ve 28 Ekim yarım günü hesaba katılmaz); süre dolunca stok ayırması kalkar. Ödeme son tarihinin ön bilgilendirme / mesafeli satış metinlerine yansıtılması gerekip gerekmediği sorulmalı.

## Fiyat gösterimi ve tedarik notu (G3i A, 13.10.2026)
- Liste ve sepette fiyat gösterim seçici "Fiyatlar: ₺ KDV dahil | € KDV hariç" (`fiyat.secici_*`). Seçim yalnız
  gösterimi değiştirir; tahsilat para birimi değişmez ve özette "Ödeme Türk lirası ile alınır; € tutarlar bilgi
  içindir" notu kalır. Tüketiciye (bireysel) € KDV hariç ana fiyat gösterilmesinin fiyat etiketi mevzuatı (KDV dahil
  satış fiyatı gösterimi) açısından yeterli olup olmadığı sorulmalı; varsayılan bireyselde ₺ KDV dahildir.
- "Tedarik süresi teklifle" kalemi için sepette ve ödeme özetinde: "Bu kalemin tedarik süresi siparişten sonra 1 iş günü
  içinde bildirilir (temsili); süreyi önce öğrenmek için teklif isteyin" (`sepet.tedarik_notu`). "1 iş günü"
  operasyonel taahhüttür; mesafeli satışta teslim süresinin (30 gün üst sınırı) ön bilgilendirmede nasıl yazılacağı
  sorulmalı.

## Proforma fatura belgesi ve fatura bilgileri (G3i B, 13.10.2026)
- Havale siparişinde `/tr/hesabim/siparis/<no>/proforma` (EN "PROFORMA INVOICE"): düzenlenme tarihi, geçerlilik (=
  havale ödeme son tarihi), satıcı unvanı/adresi (künye), satıcı VKN ve vergi dairesi `SHOP_SATICI_VKN` /
  `SHOP_SATICI_VERGI_DAIRESI` ayarlarından (boşsa "Demo: üretimde doldurulacak"), alıcı firma/VKN/VAT ID/fatura
  adresi, PO no, kalemler, TL toplamlar ve sabitlenen kurla bilgi amaçlı EUR karşılığı. Banka: TL siparişte yalnız TL
  IBAN, EUR siparişte yalnız EUR IBAN + SWIFT (temsili). Yurt dışı teslimde "Menşe ve GTİP (HS) kodu sevk
  belgelerinde bildirilir" notu (kaynakta menşe/GTİP verisi yok; uydurulmadı). Proformanın mali belge niteliği
  taşımadığı ve e-fatura/e-arşiv ile ilişkisi mali müşavirle teyit edilmeli.
- "Fatura bilgilerim": unvan, vergi dairesi, fatura adresi ve telefon müşteri tarafından değiştirilir; VKN/VAT ID
  salt okunurdur ("Değişiklik için bizimle iletişime geçin"). G3i inceleme turu 1: alıcı unvanı, tipi, VKN, vergi
  dairesi ve VAT ID sipariş anında siparişe yazılır (anlık görüntü); proforma, onay ve Hesabım sipariş ayrıntısı bunu
  gösterir, sonradan yapılan fatura bilgisi değişikliği eski siparişlerin belgelerine yansımaz. G3i öncesi siparişte
  (anlık görüntü yok) unvan fatura adresindeki ad, vergi bilgileri hesaptaki değerdir. İptal edilen siparişin
  proforması açılmaz; ödenmiş / süresi dolmuş siparişte belge üstünde "ÖDENDİ" / "SÜRESİ DOLDU" ibaresi bulunur.

## Güven metinleri (G3i C, 13.10.2026)
- **Hukuk onayı bekleyen taahhüt (temsili):** durumu belirtilmemiş ürünün satın alma kutusunda (`urun.durum_guvence`):
  "Durum belirtilmemiş: siparişten sonra 1 iş günü içinde fotoğraf/test raporunu e-postayla gönderiyoruz; uygun
  bulmazsanız siparişi ücretsiz iptal edebilirsiniz (temsili)" (EN: "Condition not specified: within 1 business day
  after the order we e-mail photos/test report; if it does not suit you, you can cancel the order free of charge
  (indicative)"). Ücretsiz iptal hakkı kurumsal (ticari) alıcıya da sözleşmesel hak olarak tanınmış olur; Kullanım ve
  Satış Koşulları'na ve mesafeli satış sözleşmesine eklenip eklenmeyeceği, iptalde ödeme iadesinin süresi ve "1 iş
  günü" operasyon taahhüdü onaylanmalı. Onaylanana kadar "(temsili)" kalır.
- Ürün sayfasında ticari alıcıya iade özeti (`urun.iade_ticari`): "Ticari alım: cayma hakkı yok; açık ayıplar
  teslimden itibaren 2 gün içinde yazılı bildirilir; garanti kapsamında değişim/iade". Gün sayısı İade sayfası B
  bölümüyle aynı sabitten gelir (`app/web/baglam.py` `ACIK_AYIP_IHBAR_GUN`); TTK m.23'teki süre değişirse tek yerden
  değişir. Misafirde bireysel ve ticari satır birlikte.
- Hızlı talep onayında "Acil talepler öncelikle aranır (temsili)" operasyonel taahhüttür; satış ekibiyle teyit edilmeli.

## Hizmet taahhütleri (G3j, 13.10.2026)
- **Hukuk ve operasyon onayı bekleyen taahhüt (temsili):** hızlı talepte aciliyet "Hat durdu – acil" seçilince telefon
  numarası zorunludur ve onay metni "Çalışma saatlerinde 1 saat içinde telefonla dönüş (temsili)" der
  (`teklif.tamam_metin_acil`; EN "We call you back within 1 hour during business hours (indicative)"). Çalışma saatleri
  alt bilgideki "Hafta içi 08:30–18:00 (TSİ, UTC+3)"tir. Satış ekibinin bu süreyi karşılayıp karşılayamayacağı ve
  mesai dışı taleplerde ne yazılacağı onaylanmalı; onaylanana kadar "(temsili)" kalır. Diğer aciliyetlerde mevcut
  "1 iş günü içinde yanıt" metni değişmedi.
- Kartla ödenmiş siparişin onay sayfasında ve Hesabım ayrıntısında "Fatura e-posta ile gönderilir (temsili)" notu
  (`siparis.fatura_eposta`). Demo sitede e-fatura/e-arşiv akışı yoktur; yayın öncesi muhasebeyle netleştirilmeli.

## Proforma ihracat KDV dayanağı ve hızlı talep KVKK bilgisi (G3k, 13.10.2026)
- **Bekleyen madde — ihracat istisnası dayanağı:** yurt dışı (ihracat istisnalı) siparişin proformasında
  "KDV: ihracat istisnası (dayanak üretimde hukukça yazılacak — temsili)" satırı var (`pb.ihracat_dayanak`; EN "VAT: export exemption
  (legal basis to be written by counsel for production — indicative)"). Dayanak cümlesi (KDV Kanunu madde ve fıkrası,
  gerekirse gümrük beyannamesi atfı) hukukça yazılana kadar bu yer tutucu kalır; site metni dayanak UYDURMAZ.
- Hızlı parça talep formunda onay kutusu yok; form altında aydınlatma metnine bağlantılı bilgi cümlesi var
  (`teklif.hizli_kvkk_bilgi`). Girişsiz talepler e-posta eşleşmesiyle hesaba bağlanmaz (doğrulanmamış e-posta); yalnız
  girişli kullanıcının talebi hesabına bağlanır. Bilgi cümlesinin aydınlatma yükümlülüğü için yeterliliği onaylanmalı.

## Ticari cayma, belirtilmemiş durum ve "olduğu gibi" satırları (G3m, 14.10.2026)
- **Hukuk onayı bekleyen taahhüt (temsili):** durumu belirtilmemiş üründe kurumsal / yurt dışı / misafir görünümünde
  ayrı güvence satırı (`urun.durum_guvence`) gösterilmez; ticari iade satırı ve "Teslimat ve iade" özeti tek cümledir
  (`urun.iade_ticari_belirtilmemis`): "Ticari alım: cayma hakkı yok. İstisna: durum belirtilmemiş ürünlerde
  fotoğraf/test raporunu uygun bulmazsanız siparişi ücretsiz iptal edebilirsiniz (temsili). Fotoğraf/test raporu
  siparişten sonra 1 iş günü içinde e-postayla gönderilir." (inceleme m1: ikinci cümle mevcut `urun.durum_guvence`
  taahhüdünden; ayrı güvence satırı kalkınca misafirde kaybolmasın). Bireysel görünüm değişmedi
  (güvence satırı kalır). Yukarıdaki G3i maddesinin (ücretsiz iptalin ticari alıcıya sözleşmesel hak olarak tanınması)
  onayı bu cümle için de geçerlidir; açık ayıp ihbar süresi bu cümlede ayrıca yazılmaz.
- "Olduğu gibi" üründe ticari satır diğer durumlarla aynı kalıptadır (`urun.iade_ticari_oldugu_gibi`, özet
  `urun.iade_ozet_ticari_oldugu_gibi`, misafir özeti `urun.iade_ozet_oldugu_gibi`): "Ticari alım: cayma hakkı yok.
  Olduğu gibi satılır: garanti yok; açık ayıplar teslimden itibaren 2 gün içinde yazılı bildirilir." (EN "… within 2
  days of delivery"; inceleme I2: başlangıç İade sayfası B ve `urun.iade_ticari` ile aynı). Gün sayısı yine `ACIK_AYIP_IHBAR_GUN`; garanti sayfası B2B "olduğu gibi" maddesiyle
  çelişmez (ayıptan sorumluluk sözleşmeyle kaldırılmıştır; ihbar süresi İade sayfası B'dekiyle aynıdır).
- Filtre ve rozet açıklaması (`durum.aciklama_ikinci_el`, `durum.aciklama_ikinci_el_test_edildi`): "2. el: kullanılmış,
  test durumu kaynakta belirtilmemiş · Test edilmiş: satıştan önce test edildi". Brief'teki "çalışır sökülmüş, test
  raporu yok" ifadesi garanti sayfasının 2. el (genel) tanımıyla çelişeceği için (sayfa "satıştan önce fotoğraf/test
  raporu paylaşılır" der; "çalışır sökülmüş" tanımda yok) garanti sayfası tanımına göre yazıldı.
- **Bekleyen madde — kurumsal / yurt dışı havale iadesi (temsili):** İade sayfası B bölümüne "Havale/EFT ile ödenen
  bedelin iadesi: Kurumsal ve yurt dışı alımlarda havale/EFT ile ödenen bedelin iadesi, ödemenin geldiği banka hesabına
  havale/EFT ile yapılır (temsili)." maddesi eklendi (EN: "Refund of bank transfer payments: … refunded by bank transfer
  to the account the payment came from (indicative)"). İade süresi ve iade transferinin banka masraflarını kimin
  karşılayacağı yazılmadı (süre uydurulmaz); hukuk ve muhasebe onayıyla eklenmeli.
- **Bekleyen madde — banka masrafı talimatı (temsili):** yurt dışı müşterinin ödeme adımında havale açıklamasında ve
  EUR havale siparişinin onay sayfası / proformasında "Banka masrafları: gönderen öder (OUR) (temsili)"
  (`odeme.banka_masraf`; EN "Bank charges: paid by the sender (OUR) (indicative)"). Yurt dışı müşteride havale
  (proforma) ilk ve varsayılan seçenektir; izinli ödeme yöntemleri değişmedi. OUR talimatının sözleşmeye / proforma
  şartlarına girmesi ve muhabir banka masraflarının durumu muhasebeyle onaylanmalı.

## Yurt dışı misafirde iade satırları (G3n fix turu 1, 14.10.2026)
- **Bekleyen madde — "site kime açık" kararı:** sitenin yalnız ticari alıcılara (B2B) mı, yoksa yurt dışındaki
  tüketicilere de mi açık olduğu henüz karara bağlanmadı. Karar verilene kadar yurt dışı ülke seçmiş misafir de Türkiye
  misafiri gibi iki satır görür: tüketici satırı `urun.iade_bireysel_satir` ("Bireysel alım: 14 gün cayma hakkı
  (temsili)" / "Consumer purchase: 14-day right of withdrawal (indicative)") ve durumuna göre ticari satır. Girişli
  kurumsal ve yurt dışı (VAT ID'li) hesap yalnız ticari satırı görür.
- Site yurt dışındaki tüketicilere açıksa AB tüketicisinin cayma hakkı (2011/83/AB; Roma I md. 6 uyarınca tüketicinin
  mutad meskeni hukuku) uygulanır; cayma süresi, bildirim yolu ve iade masrafları yasal metinlerde (İade ve cayma, Ön
  bilgilendirme, Mesafeli satış) yazılmalı. Site yalnız B2B ise bu dayanak (ör. yurt dışı siparişte VAT ID zorunluluğu)
  metinlerde açıkça söylenmeli ve tüketici satırı yurt dışı görünümden kaldırılabilir.
