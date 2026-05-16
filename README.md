# ESP32-S2 Fan Control

## Klasor Yapisi

- `src/main.cpp`: Ana uygulama akisi, web arayuzu, Telegram komutlari ve fan kontrol mantigi.
- `include/config/PinConfig.h`: ESP32 pin eslesmeleri.
- `include/config/RelayConfig.h`: Role aktif/pasif cikis seviyesi.
- `include/config/WiFiConfig.h`: Web portu, AP, varsayilan WiFi ve kurtarma hotspot ayarlari.
- `include/config/TelegramConfig.h`: Telegram bot varsayilanlari ve polling sureleri.
- `include/config/EnergyConfig.h`: Fan gucu, elektrik birim ucreti ve enerji kayit araliklari.
- `include/config/TimeConfig.h`: NTP ve varsayilan otomatik calisma saatleri.

Bu proje ESP32-S2 tabanli fan kontrol sistemi icindir.

## Ag Ayarlari

- Varsayilan/kurtarma Wi-Fi: `test`
- Varsayilan/kurtarma sifre: `12345678`
- Cihazin kendi AP agi: `FanControlAP`
- AP sifresi: `fan12345`
- AP panel adresi: `http://192.168.4.1`
- mDNS adresi: `http://ceylan-robot.local`

Cihaz `WIFI_AP_STA` modunda calisir. Kendi `FanControlAP` agini acik tutarken kayitli Wi-Fi profillerine baglanmayi dener. Kayitli aglar yoksa veya ulasilamazsa telefon hotspotu icin `test / 12345678` agini son care olarak dener.

## Ozellikler

- Web panelinden fan acma/kapatma
- Web panelinden ayarlanabilir otomatik calisma saatleri
- Telegram komutlari
- Enerji tuketimi ve maliyet hesabi
- Wi-Fi tarama ve ayar sayfasi
- DHCP ile dinamik IP ve AP fallback

## Telegram Komutlari

- `/fan_ac` - fani acar
- `/fan_kapat` - fani kapatir
- `/durum` - fan durumunu gosterir
- `/wifi_info` - Wi-Fi bilgisini gonderir
- `/auto` - otomatik moda doner
- `/help` - komut listesini gonderir

## PlatformIO

Derleme:

```bash
pio run
```

Yukleme:

```bash
pio run -t upload --upload-port COM7
```
