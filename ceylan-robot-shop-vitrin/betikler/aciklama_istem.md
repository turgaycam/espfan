# Ürün açıklaması üretim istemi (G3d)

Görev: Verilen her ürün satırı için bir Türkçe (`tr`) ve bir İngilizce (`en`) açıklama yaz. Girdi: `betikler.aciklama_disa`
satırları (JSON). Çıktı: JSONL; her ürün için tam iki satır:

    {"urun_id": 123, "dil": "tr", "metin": "..."}
    {"urun_id": 123, "dil": "en", "metin": "..."}

Başka hiçbir şey yazma (açıklama, kod bloğu, boş satır yok). Metinler `betikler.aciklama_yukle` ile otomatik
denetlenir; kurala uymayan metin reddedilir ve TR/EN çiftinden biri reddedilirse ürünün İKİ metni de yayınlanmaz.

## Kurallar (TR ve EN için aynı)
1. YALNIZ satırdaki alanlardan yaz: `ad`, `uretici_kodu`, `marka`, `kategori`/`kategori_en`,
   `kok_kategori`/`kok_kategori_en`, `durum_kodu`, `stok_durumu`, `teknik`, `kaynak_aciklama`.
2. Sayı, kod, ölçü, teknik değer UYDURMA. Metindeki her sayı/kod satırda aynen bulunmalı (parça kodunu ayraçlı ya da
   ayraçsız yazabilirsin). Yıl, ağırlık, uyumlu model, seri numarası, voltaj/tork/yük/erişim: satırda yoksa yazma.
   Tek izinli genel sayılar: "12 ay" (garanti), "14 gün" (iade), "2. el".
3. ÇIKARIM YASAK. Satırda yazmayanı sonuç çıkararak ekleme. Örnekler: teknik değer "3 × AC 380 V" ise "üç fazlı" deme
   (yalnız "3 × AC 380 V"); "sürücü", "pano", "robot" gibi bir bağlamı yalnız `teknik`/`kaynak_aciklama` söylüyorsa kullan;
   "sinyali yeniler", "aşırı gerilimi korur", "kablo teması olmadan" gibi işlev cümleleri yazma.
4. Bilinmeyeni yazma; eksik bilgiyi doldurmaya çalışma, atla.
5. Ad ile teknik alanlar çelişiyorsa (örn. ad "akım filtresi" ama özellikler direnç/güç/Ω gösteriyor) ürünün işlevini
   KESİN söyleme: yalnız ürün adını ve teknik değerleri aktar, işlev cümlesi yazma. (Bu tür ürünler normalde dışa aktarmada
   ayrılır; yine de çelişki görürsen bu kuralı uygula.)
6. "Yetkili satıcı/distribütör", "authorized dealer/distributor", "orijinal garanti", "fabrika garantisi", "en ucuz",
   "%100", rakip satıcı adları, e-posta, web adresi, telefon YASAK. Fiyat vaadi verme.
7. Durum YALNIZ `durum_kodu`'ndan: `yeni` = yeni/sıfır; `yenilenmis` = yenilenmiş; `ikinci_el` = ikinci el;
   `ikinci_el_test_edildi` = ikinci el, test edilmiş; `ikinci_el_oldugu_gibi` = ikinci el, olduğu gibi (test edilmemiş);
   `belirtilmemis` = durumdan hiç söz etme ("yeni", "sıfır", "test edilmiş", "yenilenmiş" yok). `yeni` değilse "yeni/sıfır/new"
   sözcüğünü hiç kullanma.
8. Marka: yalnız satırdaki `marka`yı an (boşsa marka anma); başka üretici markası yazma (uyumluluk iddiası olarak bile).
9. SKU'yu ve `sku` alanını metne ASLA yazma; ürünü yalnız `uretici_kodu` (varsa) ile an. "ile listelenmektedir" ya da
   "listed under/with code" kalıbını kullanma (yapay).
10. Düz metin: HTML, markdown, madde işareti, başlık, tırnaklı kod yok. Paragraflar arası boş satır (`\n\n`).
    `<` ve `>` karakterlerini HİÇ kullanma (karşılaştırma için TR "altında/üstünde", EN "below/above" yaz).
11. Toplam uzunluk 300–900 karakter, tam 3 kısa paragraf. TR metin Türkçe, EN metin İngilizce yazılır (EN'de Türkçe
    sözcük ve ğ ş ı İ harfleri yok: kademe, normal tip gibi sözcükleri çevir; `kategori_en` yoksa kategoriyi çevirmeden anma).
12. Sayıları rakamla ve satırdaki değeriyle yaz; sayıyı yazıyla yazma ("iki yıl", "beş kilogram" yasak). Birim sözcüğünü
    çevirirken sayı değişmez ("1 saniye" = "1 second"). Süre/garanti bilgisi verme; "garanti" sözcüğü yalnız durum
    `ikinci_el_test_edildi` ya da `yenilenmis` ise ve yalnız "12 ay" biçiminde geçebilir (diğer durumlarda "garanti kapsamı
    dışında" gibi olumsuz cümle de reddedilir: hiç anma). "not only ..." gibi olumsuzlama kalıplarıyla durum ifadesi kurma.
13. EN biçim: yüzde "87%" yazılır (TR kaynakta "%87" olsa bile); birimler A, W, V simgeleriyle ("Amper", "Watt" yazma;
    ya da "amperes / watts"); Türkçe sözcük bırakma.

## Paragraf yapısı
Teknik tablo sayfada zaten ayrıca gösterilir: özelliklerin listesini TEKRARLAMA.
1. Tek ya da iki cümle. Kullanım/uygulama cümlesini YALNIZ `teknik` ya da `kaynak_aciklama` içinde bir uygulama alanı
   açıkça geçiyorsa yaz ("genellikle ... sistemlerinde kullanılır" / "generally used in ... systems"). Aksi halde tek
   cümle: ürünü, markasını (varsa) ve `uretici_kodu`'nu tanıt. Adın dışına çıkan işlev yazma ("hareketli sistemler",
   "sinyali yeniler", "kablo teması olmadan" gibi).
2. En çok 3 KARAR DEĞERİ: alıcının parça seçerken bakacağı 2-3 değer (akım, gerilim, güç, montaj, boyut); teknik
   tablonun ilk satırlarını değil, karar için en yararlı olanları seç; tabloda geçen her değeri yazma. Değerleri satırdaki
   gibi, birimiyle aynen kopyala (V, A, W, kg, mm, °C). Özellik yoksa bu paragraf "parça numarasından uyumluluğu doğrulayın"
   türü tek cümle olur.
3. Durum + stok, son cümle teklif/ihracat. Stok cümlesi SABİT şablon:
   - `stokta` -> TR "Stokta bulunmaktadır." / EN "It is in stock."
   - `stok_yok` -> TR "Şu anda stokta görünmemektedir; temin için teklif isteyebilirsiniz." /
     EN "It is currently out of stock; you can request a quote for availability."
   - `tedarik_suresi_var` -> stok cümlesi yazma.
   Son cümle: "Fiyat ve ihracat koşulları için teklif isteyebilirsiniz." / "You can request a quote for price and export terms."

## Açılış çeşitliliği
Komşu ürünlerin metinleri birbirinin kopyası olmasın (kopya içerik). Paragraf 1 için 3-4 açılış kalıbından sırayla
dön (ürün sırasına göre), bağlaç ve cümle kuruluşunu değiştir; örnek açılışlar:
(a) "<Marka> <ad> ..." ile başla, (b) "<Ürün türü>, <uretici_kodu> koduyla ..." ile başla, (c) kategoriden başla
("<Kategori> grubunda yer alan ..."), (d) durumdan başla ("<Durum> olarak sunulan ..."). Aynı açılışı arka arkaya iki ürüne verme.

## Doğal geçirilecek terimler (kategoriye uygun 1-2 tanesi, zorlamadan; yalnız konuya uyuyorsa)
Kaynak: seo/oneriler.md bölüm 3. Marka terimi yalnız ürünün gerçek markası içindir.

| Kategori | TR | EN |
|---|---|---|
| Robot kolu / manipülatör | ikinci el robot, endüstriyel robot, robot yedek parça | used industrial robot, robot arm, spare parts |
| Kontrol kabini / kontrolcü | kontrol ünitesi, robot kontrolcü, yedek parça | controller, control cabinet, spare parts |
| Teach pendant | teach pendant, kontrol paneli | teach pendant, pendant |
| Servo motor | servo motor, eksen motoru, robot yedek parça | servo motor, axis motor, replacement |
| Servo sürücü / amplifikatör | servo sürücü, sürücü, güç modülü | servo drive, drive, power module |
| Kart / elektronik modül | elektronik kart, kart, bilgisayar kartı | board, module, spare parts |
| Kablo / kablo demeti | kablo, kablo demeti, robot kablosu | cable, cable harness, robot cable |
| Mekanik / redüktör / bilek | redüktör, dişli kutusu, robot bileği | gearbox, wrist, mechanical parts |
| Güç kaynağı | güç kaynağı, otomasyon yedek parça | power supply, spare parts |
| Sensör / otomasyon parçaları | sensör, sürücü, otomasyon yedek parça | sensor, drive, automation parts |

Genel: "parça numarası / part number", "ihracat / export", "teklif / quote". Terim doldurma yapma; aynı terimi tekrarlama.
