# ESP32-S2 Fan Control

Bu proje ESP32-S2 tabanli fan kontrol sistemi icindir.

## Ag Ayarlari

- Ana Wi-Fi: `CEYLAN-ROBOT`
- Sifre: `Mahfer123.`
- Router uzerindeki sabit IP: `http://192.168.5.170`
- Cihazin kendi AP agi: `FanControlAP`
- AP sifresi: `fan12345`
- AP panel adresi: `http://192.168.4.1`
- mDNS adresi: `http://ceylan-robot.local`

Cihaz `WIFI_AP_STA` modunda calisir. Yani kendi `FanControlAP` agini acik tutarken ayni anda `CEYLAN-ROBOT` agina baglanmayi dener. Router baglantisi koparsa AP paneli acik kalir ve cihaz 30 saniyede bir tekrar Wi-Fi baglantisi dener.

## Ozellikler

- Web panelinden fan acma/kapatma
- Otomatik calisma saatleri: 07:00-08:30 ve 16:00-17:30
- Telegram komutlari
- Enerji tuketimi ve maliyet hesabi
- Wi-Fi tarama ve ayar sayfasi
- Sabit yerel IP ve AP fallback

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
