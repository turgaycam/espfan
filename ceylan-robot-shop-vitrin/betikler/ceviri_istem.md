# Ürün adı ve teknik özellik çeviri istemi (G3f)

Görev: Verilen her ürün satırının Türkçe ürün adını (`ad`) ve teknik özelliklerini (`teknik`) İngilizceye çevir.
Girdi: `betikler.ceviri_disa` satırları (JSON):

    {"urun_id": 123, "ad": "...", "marka": "KUKA", "kategori_en": "POWER SYSTEMS", "teknik": [["anahtar", "değer"], ...]}

(`--yalniz-ad` ile dışa aktarılan satırlarda `teknik` yoktur.) Çıktı: JSONL; her ürün için tam bir satır:

    {"urun_id": 123, "ad_en": "...", "teknik_en": [["key", "value"], ...]}

Satırda `teknik` yoksa `"teknik_en": null` yaz. `teknik` boş liste ise `"teknik_en": []`. Başka hiçbir şey yazma
(açıklama, kod bloğu, boş satır yok). Çıktı `betikler.ceviri_yukle` ile otomatik denetlenir; kurala uymayan satır
reddedilir ve sitede Türkçe ad gösterilmeye devam eder.

## Kurallar
1. YALNIZ çeviri. Açıklama, yorum, ek bilgi, parantez içi not, uyumluluk ya da işlev ekleme; bir şeyi çıkarma.
2. AYNEN kalır (harfi harfine, ayraçlarıyla): kodlar, parça numaraları, model ve seri adları (KRC2, IRB 2400,
   6ES7 307-1EA00-0AA0, 00-109-802, 27V-NT), sayılar, birim sembolleri (V, kV, A, mA, W, kW, Hz, mm, kg, Nm, °C, IP65),
   marka adları (KUKA, ABB, FANUC, Yaskawa, Siemens ...). Marka adını büyük/küçük harfiyle kaynaktaki gibi yaz.
   Kaynakta olmayan markayı ekleme; kaynaktaki markayı atma.
3. Sayılar değişmez. Yalnız ondalık virgül noktaya çevrilir: `0,72 kV` → `0.72 kV`, `3,5 kg` → `3.5 kg`.
   Yüzde işareti İngilizce yerine taşınabilir: `%15` → `15%`. Rakamı yazıyla yazma, sayı ekleme/çıkarma.
   İşaret ve karşılaştırma aynen: `-20 °C` eksi kalır, `<5 ms` `<` kalır, `±10%` `±` kalır; kesir `1/2"` aynen.
   Binlik ayraç: sayı binlik ayraçlıysa (`1.000 W`, `10.000.000`) ayraçsız yaz (`1000 W`) ya da aynen bırak;
   `.` ile `,` arasında dönüştürme YAPMA (TR `1,500` = 1,5'tir; İngilizcede `1,500` bin beş yüz okunur).
   Birim sembolü büyük/küçük harfiyle ve akım türü aynen: `kV` `V` olmaz, `MW` `mW` olmaz, `kg` `lb` olmaz, `AC` `DC`
   olmaz; birim dönüştürme yapma. Kontak tipleri aynen ve aynı sayıda: `NO`, `NC`, `COM` (TR `NA` → `NO`, `NK` → `NC`).
   Kesin binlik ayraçlı sayı (`1.000`, `10.000.000`) İngilizcede noktalı KALAMAZ: `1000` ya da `1,000` yaz.
4. Teknik satırlar: `teknik_en` girdideki `teknik` ile AYNI SAYIDA ve AYNI SIRADA olmalı. Her satır
   `[anahtar_en, değer_en]`; anahtar ve değer ayrı ayrı çevrilir, satırlar birleştirilmez/bölünmez. Bir satırdaki
   sayı ve kodlar yalnız o satırda kalır. Çevrilecek sözcük yoksa (yalnız kod/sayı) değeri aynen yaz. Boş bırakma.
5. Sözlük (ortak terimler, tutarlı kullan):
   - GÜÇ KAYNAĞI → Power Supply
   - SERVO MOTOR → Servo Motor
   - SÜRÜCÜ → Drive (SERVO SÜRÜCÜ → Servo Drive)
   - KABLO → Cable
   - KART → Board
   - REDÜKTÖR → Gearbox
   - VALF → Valve
   - SENSÖR → Sensor
   - RÖLE → Relay
   - KONTAKTÖR → Contactor
   - SİGORTA → Fuse
   - TRAFO / TRANSFORMATÖR → Transformer
   - FİLTRE → Filter
   - MOTOR → Motor; FREN → Brake; ENKODER → Encoder; FAN → Fan; AKÜ / PİL → Battery
   - KONTROL ÜNİTESİ → Control Unit; KONTROL KABİNİ → Control Cabinet; EL TERMİNALİ → Teach Pendant
   - ROBOT KOLU → Robot Arm; MODÜL → Module; KONNEKTÖR → Connector; ŞALTER → Switch; PANO → Panel
   - Giriş → Input; Çıkış → Output; Gerilim / Voltaj → Voltage; Akım → Current; Güç → Power; Ağırlık → Weight;
     Boyut / Ölçü → Dimensions; Sıcaklık → Temperature; Basınç → Pressure; Frekans → Frequency; Tip → Type;
     Adet → pcs; Uzunluk → Length; Koruma Sınıfı → Protection Class
6. Durum ifadeleri: "2. EL" / "İKİNCİ EL" → "Used"; "SIFIR" → "New"; "YENİLENMİŞ" → "Refurbished".
7. Biçim: tamamı BÜYÜK HARF Türkçe ad İngilizcede Title Case yazılır ("KUKA KRC2 GÜÇ KAYNAĞI" → "KUKA KRC2 Power
   Supply"); kodlar, model adları ve kısaltmalar (PLC, CNC, I/O, LED) büyük harf kalır; bağlaçlar küçük (and, of, for,
   with). Kaynakta karışık harfli ad varsa harf düzenini koru.
8. Çıktıda Türkçe sözcük ya da ğ ş ı İ ç ö ü harfi kalmasın (kod/model jetonları ve marka adları hariç). "ve", "ile",
   "için", "arası", "yaklaşık", "adet" gibi sözcükleri çevir ("and", "with", "for", "between", "approx.", "pcs").
9. Uzunluk: `ad_en` 3–200 karakter ve Türkçe adın 0,5–2,5 katı arasında olmalı.
10. Emin olmadığın terimi uydurma: en yakın genel İngilizce teknik terimi kullan; kodları asla "düzeltme".

## Örnek
Girdi:

    {"urun_id": 7, "ad": "KUKA 00-109-802 KRC2 GÜÇ KAYNAĞI 27V-NT", "marka": "KUKA", "kategori_en": "POWER SYSTEMS", "teknik": [["Giriş Voltajı (Input)", "0,72 kV"], ["Ağırlık", "yaklaşık 3,5 kg"]]}

Çıktı:

    {"urun_id": 7, "ad_en": "KUKA 00-109-802 KRC2 Power Supply 27V-NT", "teknik_en": [["Input Voltage (Input)", "0.72 kV"], ["Weight", "approx. 3.5 kg"]]}
