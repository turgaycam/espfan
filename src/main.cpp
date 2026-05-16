#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ESPmDNS.h>
#include <ArduinoJson.h>
#include <time.h>

#define FAN_PIN 4
#define LED_PIN 2
#define WEB_PORT 80
#define TELEGRAM_POLL_MS 10000
#define TELEGRAM_HTTP_TIMEOUT_MS 3000
#define WIFI_RETRY_MS 30000
#define ENERGY_SAVE_MS 60000
#define FAN_POWER_WATTS 150.0  // Fan güç tüketimi (Watt)
#define ELECTRICITY_RATE 4.0  // Elektrik ücreti (TL/kWh)

WebServer server(WEB_PORT);
Preferences prefs;
WiFiClientSecure secureClient;

String wifiSsid;
String wifiPassword;
String wifiSsid2;      // İkinci WiFi profili
String wifiPassword2;  // İkinci WiFi şifresi
String telegramToken;
String telegramChatId;
String customIp;
int timezoneOffset = 3;
bool dstEnabled = false;

bool autoMode = true;
bool fanState = false;
unsigned long lastTelegramPoll = 0;
unsigned long lastWifiRetry = 0;
unsigned long lastEnergySave = 0;
long telegramOffset = 0;

// Enerji hesaplaması için değişkenler
unsigned long fanOnTimeStart = 0;  // Fan açılma zamanı
unsigned long totalFanOnTimeMs = 0;  // Toplam açık kalma süresi (ms)
float totalEnergyKwh = 0.0;  // Toplam tüketilen enerji (kWh)
float totalCost = 0.0;  // Toplam maliyet (TL)
String energyMonthKey;

const char* defaultWifiSsid = "CEYLAN-ROBOT";
const char* defaultWifiPassword = "Mahfer123.";
const char* deviceHostname = "ceylan-robot";
const char* defaultTelegramToken = "8846209399:AAH8z9siKOf8LKWubTKHuGHhXdovCSZeZnU";
const char* defaultTelegramChatId = "8618416869";
const char* botUsername = "faniyilikderBot";
const char* apSsid = "FanControlAP";
const char* apPassword = "fan12345";
const char* ntpServer = "pool.ntp.org";
IPAddress staticLocalIp(192, 168, 5, 170);
IPAddress staticGateway(192, 168, 5, 1);
IPAddress staticSubnet(255, 255, 255, 0);
IPAddress staticDns1(8, 8, 8, 8);      // Google DNS
IPAddress staticDns2(8, 8, 4, 4);      // Google DNS 2

String htmlHeader(const String& title) {
  return String("<!DOCTYPE html><html lang=\"tr\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\"><meta http-equiv=\"refresh\" content=\"20\"><title>") + title + "</title><style>"
    ":root{color-scheme:dark;--bg:#071118;--panel:#101c24;--panel2:#132834;--line:#254452;--text:#eef7f8;--muted:#9db2ba;--green:#26d07c;--red:#ff5d5d;--cyan:#35d0e6;--amber:#f6b84b;--blue:#5ba7ff;}"
    "*{box-sizing:border-box}body{font-family:Arial,Helvetica,sans-serif;background:radial-gradient(circle at top left,#173647 0,#071118 38%,#05090d 100%);color:var(--text);margin:0;min-height:100vh;}"
    "header{padding:18px 22px;border-bottom:1px solid rgba(255,255,255,.08);background:rgba(5,12,18,.78);position:sticky;top:0;z-index:5;backdrop-filter:blur(10px)}"
    ".topbar{max-width:1120px;margin:auto;display:flex;justify-content:space-between;gap:14px;align-items:center}.brand h1{font-size:1.35rem;margin:0}.brand p{margin:4px 0 0;color:var(--muted);font-size:.92rem}"
    "main{max-width:1120px;margin:auto;padding:18px 18px 28px}.grid{display:grid;grid-template-columns:1.05fr .95fr;gap:16px}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:16px}"
    ".card,.metric{background:linear-gradient(180deg,rgba(19,40,52,.94),rgba(10,20,27,.96));border:1px solid var(--line);border-radius:8px;padding:16px;box-shadow:0 18px 38px rgba(0,0,0,.25)}"
    ".metric span{display:block;color:var(--muted);font-size:.82rem;margin-bottom:8px}.metric strong{font-size:1.25rem}.card h2{margin:0 0 14px;font-size:1.15rem}.status{font-size:1rem;margin:9px 0;line-height:1.45}.small{color:var(--muted);font-size:.92rem;line-height:1.45}"
    ".hero{display:grid;grid-template-columns:210px 1fr;gap:18px;align-items:center}.fanbox{height:210px;display:grid;place-items:center}.fan{width:170px;height:170px;border-radius:50%;position:relative;background:radial-gradient(circle,#142833 0 16%,#0b151c 17% 21%,#203f4d 22% 24%,#101b23 25%);border:8px solid #1d3e4b;box-shadow:inset 0 0 28px rgba(0,0,0,.5),0 0 35px rgba(53,208,230,.16)}"
    ".fan:before{content:\"\";position:absolute;inset:18px;border-radius:50%;background:conic-gradient(from 0deg,transparent 0 18deg,rgba(53,208,230,.92) 18deg 54deg,transparent 54deg 120deg,rgba(38,208,124,.85) 120deg 156deg,transparent 156deg 240deg,rgba(91,167,255,.86) 240deg 276deg,transparent 276deg 360deg);filter:drop-shadow(0 0 8px rgba(53,208,230,.28))}"
    ".fan.on:before{animation:spin .8s linear infinite}.fan.off:before{opacity:.35}.hub{position:absolute;inset:63px;border-radius:50%;background:#e8f8fb;border:8px solid #274c5a;box-shadow:0 0 18px rgba(255,255,255,.16)}@keyframes spin{to{transform:rotate(360deg)}}"
    ".pill{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:999px;padding:8px 12px;color:var(--muted);background:#0c1a22}.dot{width:9px;height:9px;border-radius:50%;background:var(--red)}.dot.on{background:var(--green);box-shadow:0 0 12px var(--green)}"
    ".actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px}.button{display:inline-flex;align-items:center;justify-content:center;min-height:42px;padding:11px 15px;border:none;border-radius:8px;color:#061015;text-decoration:none;font-weight:700;cursor:pointer}.button-primary{background:var(--blue)}.button-accent{background:var(--cyan)}.button-danger{background:var(--red);color:#fff}.button-success{background:var(--green)}"
    ".form-row{margin-bottom:14px}label{display:block;margin-bottom:6px;font-weight:700}input,select,textarea{width:100%;padding:12px;border-radius:8px;border:1px solid var(--line);background:#07151c;color:var(--text)}"
    "@media(max-width:860px){.grid,.hero{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.fanbox{height:190px}}@media(max-width:520px){.metrics{grid-template-columns:1fr}.topbar{align-items:flex-start;flex-direction:column}.actions .button{width:100%}}"
    "</style></head><body><header><div class=\"topbar\"><div class=\"brand\"><h1>ESP32-S2 Fan Kontrol</h1><p>CEYLAN-ROBOT akilli fan paneli</p></div><div class=\"pill\">Yerel: 192.168.5.170</div></div></header><main>";
}

String htmlFooter() {
  return String("</main></body></html>");
}

String getTimeString() {
  time_t nowUtc = time(nullptr);
  if (nowUtc < 100000) return "Senkronizasyon bekleniyor...";
  long offsetSeconds = timezoneOffset * 3600 + (dstEnabled ? 3600 : 0);
  time_t localTime = nowUtc + offsetSeconds;
  struct tm tm;
  localtime_r(&localTime, &tm);
  char buf[64];
  strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", &tm);
  return String(buf);
}

bool isTimeInWindow(int h, int m, int startH, int startM, int endH, int endM) {
  int minutes = h * 60 + m;
  int start = startH * 60 + startM;
  int end = endH * 60 + endM;
  return minutes >= start && minutes < end;
}

void updateEnergyConsumption();

String getMonthKey() {
  time_t nowUtc = time(nullptr);
  if (nowUtc < 100000) return energyMonthKey;

  long offsetSeconds = timezoneOffset * 3600 + (dstEnabled ? 3600 : 0);
  time_t localTime = nowUtc + offsetSeconds;
  struct tm tm;
  localtime_r(&localTime, &tm);

  char buf[8];
  strftime(buf, sizeof(buf), "%Y-%m", &tm);
  return String(buf);
}

unsigned long getCurrentFanOnTimeMs() {
  if (fanState && fanOnTimeStart > 0) {
    return totalFanOnTimeMs + (millis() - fanOnTimeStart);
  }
  return totalFanOnTimeMs;
}

String formatDuration(unsigned long ms) {
  unsigned long totalSeconds = ms / 1000;
  unsigned long hours = totalSeconds / 3600;
  unsigned long minutes = (totalSeconds % 3600) / 60;
  unsigned long seconds = totalSeconds % 60;

  return String(hours) + " sa " + String(minutes) + " dk " + String(seconds) + " sn";
}

void saveEnergyStats() {
  prefs.putULong("fanTime", totalFanOnTimeMs);
  prefs.putFloat("energy", totalEnergyKwh);
  prefs.putFloat("cost", totalCost);
  prefs.putString("energyMonth", energyMonthKey);
}

void resetMonthlyEnergyIfNeeded() {
  String currentMonth = getMonthKey();
  if (currentMonth.length() == 0) return;

  if (energyMonthKey.length() == 0) {
    energyMonthKey = currentMonth;
    saveEnergyStats();
    return;
  }

  if (energyMonthKey != currentMonth) {
    totalFanOnTimeMs = 0;
    totalEnergyKwh = 0.0;
    totalCost = 0.0;
    fanOnTimeStart = fanState ? millis() : 0;
    energyMonthKey = currentMonth;
    saveEnergyStats();
  }
}

void setFan(bool on) {
  if (fanState == on) {
    digitalWrite(FAN_PIN, on ? HIGH : LOW);
    return;
  }

  fanState = on;
  digitalWrite(FAN_PIN, on ? HIGH : LOW);

  // Enerji hesaplaması
  if (on) {
    fanOnTimeStart = millis();
  } else if (fanOnTimeStart > 0) {
    unsigned long onDuration = millis() - fanOnTimeStart;
    totalFanOnTimeMs += onDuration;
    fanOnTimeStart = 0;
    updateEnergyConsumption();
    saveEnergyStats();
  }
}

void updateEnergyConsumption() {
  resetMonthlyEnergyIfNeeded();

  float hours = getCurrentFanOnTimeMs() / 3600000.0;
  totalEnergyKwh = (FAN_POWER_WATTS * hours) / 1000.0;
  totalCost = totalEnergyKwh * ELECTRICITY_RATE;

  if (millis() - lastEnergySave > ENERGY_SAVE_MS) {
    lastEnergySave = millis();
    if (!fanState) {
      saveEnergyStats();
    } else {
      prefs.putFloat("energy", totalEnergyKwh);
      prefs.putFloat("cost", totalCost);
      prefs.putString("energyMonth", energyMonthKey);
    }
  }
}

String getEnergyPage() {
  updateEnergyConsumption();

  String page = htmlHeader("Aylik Enerji");
  page += "<section class=\"metrics\">";
  page += "<div class=\"metric\"><span>Aylik Donem</span><strong>" + String(energyMonthKey.length() ? energyMonthKey : "Bekleniyor") + "</strong></div>";
  page += "<div class=\"metric\"><span>Calisma Suresi</span><strong>" + formatDuration(getCurrentFanOnTimeMs()) + "</strong></div>";
  page += "<div class=\"metric\"><span>Tuketim</span><strong>" + String(totalEnergyKwh, 4) + " kWh</strong></div>";
  page += "<div class=\"metric\"><span>Maliyet</span><strong>" + String(totalCost, 2) + " TL</strong></div>";
  page += "</section>";

  page += "<section class=\"grid\">";
  page += "<div class=\"card\"><h2>Aylik Enerji Takibi</h2>";
  page += "<p class=\"status\"><strong>Fan gucu:</strong> " + String(FAN_POWER_WATTS, 0) + " Watt</p>";
  page += "<p class=\"status\"><strong>Elektrik tarifi:</strong> " + String(ELECTRICITY_RATE, 2) + " TL/kWh</p>";
  page += "<p class=\"status\"><strong>Hesap:</strong> kWh x 4 TL olarak aylik maliyet tutulur.</p>";
  page += "<p class=\"small\">Ay degistiginde saya� otomatik sifirlanir. Fan calisirken sure ve maliyet anlik guncellenir.</p>";
  page += "<div class=\"actions\"><a class=\"button button-primary\" href=\"/\">Ana Sayfa</a><a class=\"button button-danger\" href=\"/energy/reset\">Bu Ayi Sifirla</a></div>";
  page += "</div>";

  page += "<div class=\"card hero\"><div class=\"fanbox\"><div class=\"fan " + String(fanState ? "on" : "off") + "\"><div class=\"hub\"></div></div></div>";
  page += "<div><h2>Canli Fan</h2><p class=\"pill\"><span class=\"dot " + String(fanState ? "on" : "") + "\"></span>" + String(fanState ? "Enerji tuketiyor" : "Tuketim durdu") + "</p>";
  page += "<p class=\"status\"><strong>Saat:</strong> " + getTimeString() + "</p></div></div>";
  page += "</section>";
  page += htmlFooter();
  return page;
}
void saveSettings() {
  prefs.putString("ssid", wifiSsid);
  prefs.putString("pass", wifiPassword);
  prefs.putString("ssid2", wifiSsid2);
  prefs.putString("pass2", wifiPassword2);
  prefs.putString("customIp", customIp);
  prefs.putString("gateway", prefs.getString("gateway", "192.168.5.1"));
  prefs.putString("subnet", prefs.getString("subnet", "255.255.255.0"));
  prefs.putString("dns1", prefs.getString("dns1", "8.8.8.8"));
  prefs.putString("dns2", prefs.getString("dns2", "8.8.4.4"));
  prefs.putString("token", telegramToken);
  prefs.putString("chatid", telegramChatId);
  prefs.putInt("tz", timezoneOffset);
  prefs.putBool("dst", dstEnabled);
  prefs.putULong("fanTime", totalFanOnTimeMs);
  prefs.putFloat("energy", totalEnergyKwh);
  prefs.putFloat("cost", totalCost);
  prefs.putString("energyMonth", energyMonthKey);
}

void loadSettings() {
  wifiSsid = prefs.getString("ssid", defaultWifiSsid);
  wifiPassword = prefs.getString("pass", defaultWifiPassword);
  wifiSsid2 = prefs.getString("ssid2", "");
  wifiPassword2 = prefs.getString("pass2", "");
  telegramToken = prefs.getString("token", defaultTelegramToken);
  telegramChatId = prefs.getString("chatid", defaultTelegramChatId);
  customIp = prefs.getString("customIp", "");
  timezoneOffset = prefs.getInt("tz", 3);
  dstEnabled = prefs.getBool("dst", false);
  telegramOffset = prefs.getLong("tgoffset", 0);
  totalFanOnTimeMs = prefs.getULong("fanTime", 0);
  totalEnergyKwh = prefs.getFloat("energy", 0.0);
  totalCost = prefs.getFloat("cost", 0.0);
  energyMonthKey = prefs.getString("energyMonth", "");
}

void connectWiFi() {
  if (wifiSsid.length() == 0) {
    Serial.println("Wi-Fi bilgisi yok, AP modu başlatılıyor.");
    return;
  }

  WiFi.mode(WIFI_AP_STA);
  WiFi.setHostname(deviceHostname);
  
  // IP ayarlarını yükle
  String ipStr = prefs.getString("customIp", "");
  String gatewayStr = prefs.getString("gateway", "192.168.5.1");
  String subnetStr = prefs.getString("subnet", "255.255.255.0");
  String dns1Str = prefs.getString("dns1", "8.8.8.8");
  String dns2Str = prefs.getString("dns2", "8.8.4.4");
  
  // String'ten IPAddress'e dönüştür
  IPAddress customLocalIp;
  IPAddress customGateway;
  IPAddress customSubnet;
  IPAddress customDns1;
  IPAddress customDns2;
  
  if (ipStr.length() > 0) {
    customLocalIp.fromString(ipStr);
    customGateway.fromString(gatewayStr);
    customSubnet.fromString(subnetStr);
    customDns1.fromString(dns1Str);
    customDns2.fromString(dns2Str);
    
    if (!WiFi.config(customLocalIp, customGateway, customSubnet, customDns1, customDns2)) {
      Serial.println("Statik IP ayarlanamadi, DHCP deneniyor.");
    } else {
      Serial.println("Statik IP ayarlandi: " + ipStr);
    }
  } else {
    Serial.println("DHCP ile IP alınacak (Statik IP ayarlanmamış).");
  }
  
  WiFi.disconnect(false);
  delay(100);
  WiFi.begin(wifiSsid.c_str(), wifiPassword.c_str());
  Serial.print("Wi-Fi baglaniyor (1. profil): ");
  Serial.println(wifiSsid);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    delay(500);
    Serial.print('.');
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.print("Baglandi. IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("DNS: ");
    Serial.print(WiFi.dnsIP(0));
    Serial.print(" / ");
    Serial.println(WiFi.dnsIP(1));
  } else {
    Serial.println();
    
    // İkinci WiFi profili varsa dene
    if (wifiSsid2.length() > 0) {
      Serial.println("1. profil basarisiz, 2. profili deniyor...");
      WiFi.disconnect(false);
      delay(100);
      WiFi.begin(wifiSsid2.c_str(), wifiPassword2.c_str());
      Serial.print("Wi-Fi baglaniyor (2. profil): ");
      Serial.println(wifiSsid2);
      
      start = millis();
      while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
        delay(500);
        Serial.print('.');
      }
      
      if (WiFi.status() == WL_CONNECTED) {
        Serial.println();
        Serial.println("2. profil WiFi'ya baglandi!");
        Serial.print("IP: ");
        Serial.println(WiFi.localIP());
      } else {
        Serial.println();
        Serial.println("Her iki WiFi de basarisiz, AP modu baslatilacak.");
      }
    } else {
      Serial.println("2. profil WiFi tanimlanbmadi, AP modu baslatilacak.");
    }
  }
}

void startAccessPoint() {
  WiFi.mode(WIFI_AP_STA);
  if (!WiFi.softAP(apSsid, apPassword)) {
    Serial.println("AP modu baslatilamadi.");
    return;
  }
  IPAddress ip = WiFi.softAPIP();
  Serial.print("AP modunda IP: ");
  Serial.println(ip);
}

void retryWiFiIfNeeded() {
  if (WiFi.status() == WL_CONNECTED) return;
  if (millis() - lastWifiRetry < WIFI_RETRY_MS) return;

  lastWifiRetry = millis();
  Serial.println("Wi-Fi bagli degil, tekrar deneniyor.");
  connectWiFi();
}
String getScheduleStatus() {
  return String("Sabah 07:00 - 08:30 ve öğleden sonra 16:00 - 17:30 arası otomatik çalışır.");
}

String getNetworkInfo() {
  if (WiFi.status() == WL_CONNECTED) {
    return String("Wi-Fi bagli: ") + wifiSsid + " - Yerel IP: " + WiFi.localIP().toString() + " - AP IP: " + WiFi.softAPIP().toString();
  }
  if (WiFi.getMode() == WIFI_AP || WiFi.getMode() == WIFI_AP_STA) {
    return String("AP modu etkin: ") + apSsid + " - AP IP: " + WiFi.softAPIP().toString() + " - Router baglantisi bekleniyor";
  }
  return String("Agda bagli degil.");
}

String getScanResultsHtml() {
  String result = "";
  int n = WiFi.scanNetworks(false, true);
  if (n <= 0) {
    result = "<div class=\"card\"><h2>Wi-Fi Tarama Sonuçları</h2><p class=\"small\">Çevrede Wi-Fi ağı bulunamadı ya da tarama başarısız oldu.</p></div>";
  } else {
    result = "<div class=\"card\"><h2>Bulunan Wi-Fi Ağları</h2>";
    for (int i = 0; i < n; ++i) {
      result += "<p class=\"status\"><strong>" + WiFi.SSID(i) + "</strong> (" + String(WiFi.RSSI(i)) + " dBm)";
      result += "</p>";
    }
    result += "</div>";
  }
  WiFi.scanDelete();
  return result;
}

String getRootPage() {
  updateEnergyConsumption();

  String page = htmlHeader("Kontrol Paneli");
  page += "<section class=\"metrics\">";
  page += "<div class=\"metric\"><span>Fan Durumu</span><strong>" + String(fanState ? "Acik" : "Kapali") + "</strong></div>";
  page += "<div class=\"metric\"><span>Calisma Modu</span><strong>" + String(autoMode ? "Otomatik" : "Manuel") + "</strong></div>";
  page += "<div class=\"metric\"><span>Bu Ay Enerji</span><strong>" + String(totalEnergyKwh, 3) + " kWh</strong></div>";
  page += "<div class=\"metric\"><span>Bu Ay Maliyet</span><strong>" + String(totalCost, 2) + " TL</strong></div>";
  page += "</section>";

  page += "<section class=\"grid\">";
  page += "<div class=\"card hero\"><div class=\"fanbox\"><div class=\"fan " + String(fanState ? "on" : "off") + "\"><div class=\"hub\"></div></div></div>";
  page += "<div><h2>Fan Simulasyonu</h2>";
  page += "<p class=\"pill\"><span class=\"dot " + String(fanState ? "on" : "") + "\"></span>" + String(fanState ? "Fan calisiyor" : "Fan beklemede") + "</p>";
  page += "<p class=\"status\"><strong>Saat:</strong> " + getTimeString() + "</p>";
  page += "<p class=\"status\"><strong>Aylik sure:</strong> " + formatDuration(getCurrentFanOnTimeMs()) + "</p>";
  page += "<p class=\"status\"><strong>Tarife:</strong> " + String(ELECTRICITY_RATE, 2) + " TL/kWh, fan gucu " + String(FAN_POWER_WATTS, 0) + " W</p>";
  page += "<div class=\"actions\"><a class=\"button button-success\" href=\"/toggleFan?state=1\">Fan Ac</a><a class=\"button button-danger\" href=\"/toggleFan?state=0\">Fan Kapat</a><a class=\"button button-primary\" href=\"/autoMode\">Otomatik Mod</a></div>";
  page += "</div></div>";

  page += "<div class=\"card\"><h2>Baglanti ve Plan</h2>";
  page += "<p class=\"status\"><strong>Ag:</strong> " + getNetworkInfo() + "</p>";
  page += "<p class=\"status\"><strong>Yerel adres:</strong> http://ceylan-robot.local</p>";
  page += "<p class=\"status\"><strong>Ay:</strong> " + String(energyMonthKey.length() ? energyMonthKey : "Senkron bekleniyor") + "</p>";
  page += "<p class=\"small\">" + getScheduleStatus() + "</p>";
  page += "<div class=\"actions\"><a class=\"button button-accent\" href=\"/wifi\">Wi-Fi</a><a class=\"button button-primary\" href=\"/settings\">Telegram / Saat</a><a class=\"button button-success\" href=\"/energy\">Enerji</a></div>";
  page += "</div>";
  page += "</section>";
  page += htmlFooter();
  return page;
}
String getWifiPage(const String& scanResults = "") {
  String page = htmlHeader("Wi-Fi Ayarları");
  page += "<div class=\"card\"><h2>WiFi Bağlantı Ayarları</h2>";
  page += "<p class=\"status\"><strong>Mevcut Ağ:</strong> " + getNetworkInfo() + "</p>";
  page += "<form action=\"/saveWifi\" method=\"post\">";
  
  // Birinci WiFi
  page += "<h3 style=\"margin-top:20px;color:#35d0e6;margin-bottom:10px;\">Birinci WiFi Ağı</h3>";
  page += "<div class=\"form-row\"><label>WiFi Ağı Adı (SSID)</label><input type=\"text\" name=\"ssid\" value=\"" + wifiSsid + "\" placeholder=\"Örn: CEYLAN-ROBOT\" required></div>";
  page += "<div class=\"form-row\"><label>WiFi Şifresi</label><input type=\"password\" name=\"pass\" value=\"" + wifiPassword + "\" placeholder=\"WiFi şifresini girin\" required></div>";
  
  // İkinci WiFi
  page += "<h3 style=\"margin-top:20px;color:#35d0e6;margin-bottom:10px;\">İkinci WiFi Ağı (İsteğe Bağlı)</h3>";
  page += "<div class=\"form-row\"><label>WiFi Ağı Adı (SSID)</label><input type=\"text\" name=\"ssid2\" value=\"" + wifiSsid2 + "\" placeholder=\"İkinci WiFi (boş bırakabilirsiniz)\"></div>";
  page += "<div class=\"form-row\"><label>WiFi Şifresi</label><input type=\"password\" name=\"pass2\" value=\"" + wifiPassword2 + "\" placeholder=\"İkinci WiFi şifresi (boş bırakabilirsiniz)\"></div>";
  
  // IP Ayarları
  page += "<h3 style=\"margin-top:20px;color:#35d0e6;margin-bottom:10px;\">IP Ayarları (İsteğe Bağlı)</h3>";
  page += "<p class=\"small\">Boş bırakırsanız DHCP ile otomatik IP alır.</p>";
  page += "<div class=\"form-row\"><label>IP Adresi</label><input type=\"text\" name=\"ip\" value=\"" + customIp + "\" placeholder=\"192.168.5.170\"></div>";
  page += "<div class=\"form-row\"><label>Gateway</label><input type=\"text\" name=\"gateway\" value=\"" + prefs.getString("gateway", "192.168.5.1") + "\" placeholder=\"192.168.5.1\"></div>";
  page += "<div class=\"form-row\"><label>Subnet Mask</label><input type=\"text\" name=\"subnet\" value=\"" + prefs.getString("subnet", "255.255.255.0") + "\" placeholder=\"255.255.255.0\"></div>";
  page += "<div class=\"form-row\"><label>DNS 1 (İsteğe Bağlı)</label><input type=\"text\" name=\"dns1\" value=\"" + prefs.getString("dns1", "8.8.8.8") + "\" placeholder=\"8.8.8.8\"></div>";
  page += "<div class=\"form-row\"><label>DNS 2 (İsteğe Bağlı)</label><input type=\"text\" name=\"dns2\" value=\"" + prefs.getString("dns2", "8.8.4.4") + "\" placeholder=\"8.8.4.4\"></div>";
  
  page += "<div class=\"form-row\"><button class=\"button button-success\" type=\"submit\">Kaydet ve Bağlan</button> ";
  page += "<a class=\"button button-accent\" href=\"/wifiScan\">Wi-Fi Ağlarını Tara</a></div>";
  page += "</form>";
  page += "<p class=\"small\"><strong>ℹ️ İpucu:</strong> İkinci WiFi, birinci bağlantı başarısız olunca otomatik denenir.</p>";
  page += "<p class=\"small\">AP modu: <strong>" + String(apSsid) + " / " + String(apPassword) + "</strong></p>";
  if (scanResults.length() > 0) {
    page += scanResults;
  }
  page += "</div>";
  page += htmlFooter();
  return page;
}

String getSettingsPage() {
  String page = htmlHeader("Ayarlar");
  page += "<div class=\"card\"><h2>Telegram ve Zaman Dilimi</h2>";
  page += "<form action=\"/saveSettings\" method=\"post\">";
  page += "<div class=\"form-row\"><label>Telegram Bot Token</label><input type=\"text\" name=\"token\" value=\"" + telegramToken + "\"></div>";
  page += "<div class=\"form-row\"><label>Telegram Chat ID</label><input type=\"text\" name=\"chatid\" value=\"" + telegramChatId + "\"></div>";
  page += "<div class=\"form-row\"><label>Zaman Dilimi</label><select name=\"tz\">";
  page += "<option value=\"-2\"" + String(timezoneOffset == -2 ? " selected" : "") + ">UTC-2</option>";
  page += "<option value=\"0\"" + String(timezoneOffset == 0 ? " selected" : "") + ">UTC+0</option>";
  page += "<option value=\"1\"" + String(timezoneOffset == 1 ? " selected" : "") + ">UTC+1</option>";
  page += "<option value=\"2\"" + String(timezoneOffset == 2 ? " selected" : "") + ">UTC+2</option>";
  page += "<option value=\"3\"" + String(timezoneOffset == 3 ? " selected" : "") + ">Istanbul (UTC+3)</option>";
  page += "<option value=\"5\"" + String(timezoneOffset == 5 ? " selected" : "") + ">UTC+5</option>";
  page += "</select></div>";
  page += "<div class=\"form-row\"><label>Ek IP Adresi</label><input type=\"text\" name=\"customIp\" value=\"" + customIp + "\"></div>";
  page += "<div class=\"form-row\"><label><input type=\"checkbox\" name=\"dst\"" + String(dstEnabled ? " checked" : "") + "> Yaz saati uygulaması</label></div>";
  page += "<button class=\"button button-success\" type=\"submit\">Kaydet</button>";
  page += "</form>";
  page += "<p class=\"small\">Telegram komutları: <strong>/fan_ac, /fan_kapat, /durum, /wifi_info, /help</strong></p>";
  page += "</div>";
  page += htmlFooter();
  return page;
}

String urlEncode(const String& txt) {
  String encoded = "";
  char c;
  for (unsigned int i = 0; i < txt.length(); i++) {
    c = txt[i];
    if (('a' <= c && c <= 'z') || ('A' <= c && c <= 'Z') || ('0' <= c && c <= '9') || c == '-' || c == '_' || c == '.' || c == '~') {
      encoded += c;
    } else if (c == ' ') {
      encoded += "+";
    } else {
      encoded += "%";
      char buf[3];
      sprintf(buf, "%02X", c);
      encoded += buf;
    }
  }
  return encoded;
}

String telegramUrl(const String& method) {
  return String("https://api.telegram.org/bot") + telegramToken + "/" + method;
}

String jsonIdToString(JsonVariantConst value) {
  int64_t id = value.as<int64_t>();
  char buf[24];
  snprintf(buf, sizeof(buf), "%lld", (long long)id);
  return String(buf);
}

void sendTelegramMessage(const String& text) {
  if (telegramToken.length() == 0) {
    Serial.println("Telegram: Token yok, mesaj gonderilemiyor");
    return;
  }
  if (telegramChatId.length() == 0) {
    Serial.println("Telegram: Chat ID yok, mesaj gonderilemiyor");
    return;
  }

  HTTPClient tgHttp;
  String url = telegramUrl("sendMessage") + "?chat_id=" + urlEncode(telegramChatId) + "&text=" + urlEncode(text);
  tgHttp.setTimeout(TELEGRAM_HTTP_TIMEOUT_MS);
  tgHttp.begin(secureClient, url);
  int code = tgHttp.GET();
  
  Serial.println("Telegram mesaj gonderildi (kod=" + String(code) + "): " + text.substring(0, 50));
  
  if (code != HTTP_CODE_OK) {
    Serial.printf("Telegram gonderim hatasi: %d\n", code);
    if (code == 401) {
      Serial.println("  -> Hatali Token!");
    } else if (code == 400) {
      Serial.println("  -> Hatali Chat ID veya mesaj!");
    }
  }
  tgHttp.end();
}
void handleTelegram() {
  if (telegramToken.length() == 0) {
    Serial.println("Telegram: Token yok");
    return;
  }
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Telegram: WiFi bagli degil, durum=" + String(WiFi.status()));
    return;
  }

  Serial.println("Telegram: WiFi bagli (RSSI=" + String(WiFi.RSSI()) + " dBm)");
  
  String url = telegramUrl("getUpdates") + "?offset=" + String(telegramOffset + 1) + "&timeout=0";
  Serial.println("Telegram URL: " + url.substring(0, 60) + "...");
  
  HTTPClient tgHttp;
  tgHttp.setTimeout(TELEGRAM_HTTP_TIMEOUT_MS);
  tgHttp.begin(secureClient, url);
  int code = tgHttp.GET();
  
  Serial.println("Telegram: getUpdates gonderi, kod=" + String(code));
  
  if (code == -1) {
    Serial.println("  ERROR: Baglanti hatasi, olasi sebep: DNS, SSL, yada internet yok");
    tgHttp.end();
    return;
  }
  
  if (code == HTTP_CODE_OK) {
    String body = tgHttp.getString();
    Serial.println("Telegram yanit uzunlugu: " + String(body.length()));
    
    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, body);
    
    if (error) {
      Serial.println("JSON hatasi: " + String(error.c_str()));
      tgHttp.end();
      return;
    }
    
    if (!doc["ok"].as<bool>()) {
      Serial.println("Telegram API hatasi: ok=false");
      Serial.println("Yanit: " + body.substring(0, 200));
      tgHttp.end();
      return;
    }
    
    JsonArray results = doc["result"].as<JsonArray>();
    Serial.println("Telegram: " + String(results.size()) + " mesaj alindi");
    
    for (JsonObject update : results) {
      long updateId = update["update_id"].as<long>();
      telegramOffset = updateId;
      prefs.putLong("tgoffset", telegramOffset);
      
      JsonObject message = update["message"].as<JsonObject>();
      if (message.isNull()) {
        Serial.println("  - Message null, skipleniyot");
        continue;
      }
      
      String chatId = jsonIdToString(message["chat"]["id"].as<JsonVariantConst>());
      String text = message["text"].as<String>();
      String sender = message["from"]["first_name"].as<String>();
      
      Serial.println("  - Chat ID: " + chatId + ", Gonderen: " + sender);
      Serial.println("    Komut: " + text);
      
      // Ilk kez chat ID kaydediliyor
      if (telegramChatId.length() == 0) {
        telegramChatId = chatId;
        prefs.putString("chatid", telegramChatId);
        Serial.println("*** YENI CHAT ID KAYDEDILDI: " + telegramChatId);
        sendTelegramMessage("Bot baglandi! Chat ID kaydedildi. /help yazin.");
      }
      
      // Chat ID eslesmiyorsa skipleniyot
      if (chatId != telegramChatId) {
        Serial.println("    Chat ID eslesmedi! Beklenen: " + telegramChatId);
        continue;
      }
      
      text.trim();
      if (text.length() == 0) continue;
      
      Serial.println("    Komut isleniyor...");
      
      if (text.equalsIgnoreCase("/fan_ac") || text.equalsIgnoreCase("/ac") || text.equalsIgnoreCase("fan ac")) {
        autoMode = false;
        setFan(true);
        sendTelegramMessage("Fan acildi. Manuel moda gecildi.");
        Serial.println("    -> Fan acildi");
      } else if (text.equalsIgnoreCase("/fan_kapat") || text.equalsIgnoreCase("/kapat") || text.equalsIgnoreCase("fan kapat")) {
        autoMode = false;
        setFan(false);
        sendTelegramMessage("Fan kapatildi. Manuel moda gecildi.");
        Serial.println("    -> Fan kapatildi");
      } else if (text.equalsIgnoreCase("/durum") || text.equalsIgnoreCase("/status")) {
        updateEnergyConsumption();
        String status = "Fan: " + String(fanState ? "Acik" : "Kapali") + "\nMod: " + String(autoMode ? "Otomatik" : "Manuel") + "\nSaat: " + getTimeString() + "\nAylik enerji: " + String(totalEnergyKwh, 3) + " kWh\nAylik maliyet: " + String(totalCost, 2) + " TL\nIP: " + WiFi.localIP().toString();
        sendTelegramMessage(status);
        Serial.println("    -> Durum gonderildi");
      } else if (text.equalsIgnoreCase("/start")) {
        sendTelegramMessage("Fan bot hazir. Komutlar: /durum, /fan_ac, /fan_kapat, /auto, /wifi_info");
        Serial.println("    -> Start mesaji gonderildi");
      } else if (text.equalsIgnoreCase("/wifi_info") || text.equalsIgnoreCase("/wifi_bilgi")) {
        String info = "Wi-Fi SSID: " + wifiSsid + "\nWi-Fi sifre: " + wifiPassword;
        sendTelegramMessage(info);
        Serial.println("    -> WiFi info gonderildi");
      } else if (text.equalsIgnoreCase("/auto")) {
        autoMode = true;
        sendTelegramMessage("Otomatik moda geri donuldu.");
        Serial.println("    -> Otomatik mod baslatildi");
      } else if (text.equalsIgnoreCase("/help")) {
        sendTelegramMessage("Komutlar: /fan_ac, /fan_kapat, /durum, /wifi_info, /auto, /help");
        Serial.println("    -> Help gonderildi");
      } else {
        Serial.println("    -> Bilinmeyen komut");
      }
    }
  } else {
    Serial.println("Telegram HTTP hatasi: " + String(code));
  }
  tgHttp.end();
}

void checkSchedule() {
  if (!autoMode) return;
  time_t nowUtc = time(nullptr);
  if (nowUtc < 100000) return;
  long offsetSeconds = timezoneOffset * 3600 + (dstEnabled ? 3600 : 0);
  time_t localTime = nowUtc + offsetSeconds;
  struct tm tm;
  localtime_r(&localTime, &tm);
  bool running = isTimeInWindow(tm.tm_hour, tm.tm_min, 7, 0, 8, 30) || isTimeInWindow(tm.tm_hour, tm.tm_min, 16, 0, 17, 30);
  setFan(running);
}

void handleRoot() { server.send(200, "text/html", getRootPage()); }

void handleWifiPage() { server.send(200, "text/html", getWifiPage()); }

void handleWifiScan() { server.send(200, "text/html", getWifiPage(getScanResultsHtml())); }

void handleSettingsPage() { server.send(200, "text/html", getSettingsPage()); }

void handleSaveWifi() {
  if (server.method() == HTTP_POST) {
    wifiSsid = server.arg("ssid");
    wifiPassword = server.arg("pass");
    wifiSsid2 = server.arg("ssid2");
    wifiPassword2 = server.arg("pass2");
    customIp = server.arg("ip");
    
    // IP ayarlarını kaydet
    prefs.putString("ssid", wifiSsid);
    prefs.putString("pass", wifiPassword);
    prefs.putString("ssid2", wifiSsid2);
    prefs.putString("pass2", wifiPassword2);
    prefs.putString("customIp", customIp);
    prefs.putString("gateway", server.arg("gateway"));
    prefs.putString("subnet", server.arg("subnet"));
    prefs.putString("dns1", server.arg("dns1"));
    prefs.putString("dns2", server.arg("dns2"));
    
    saveSettings();
    server.send(200, "text/html", htmlHeader("Kaydedildi") + "<div class=\"card\"><h2>Wi-Fi ayarları kaydedildi.</h2><p>ESP yeniden bağlanıyor...</p><a class=\"button button-primary\" href=\"/\">Geri Dön</a></div>" + htmlFooter());
    connectWiFi();
    return;
  }
  server.send(400, "text/plain", "Geçersiz istek");
}

void handleSaveSettings() {
  if (server.method() == HTTP_POST) {
    telegramToken = server.arg("token");
    telegramChatId = server.arg("chatid");
    customIp = server.arg("customIp");
    timezoneOffset = server.arg("tz").toInt();
    dstEnabled = server.hasArg("dst");
    saveSettings();
    server.send(200, "text/html", htmlHeader("Kaydedildi") + "<div class=\"card\"><h2>Ayarlar kaydedildi.</h2><p>Telegram bot ve zaman dilimi güncellendi.</p><a class=\"button button-primary\" href=\"/\">Geri Dön</a></div>" + htmlFooter());
    return;
  }
  server.send(400, "text/plain", "Geçersiz istek");
}

void handleToggleFan() {
  if (!server.hasArg("state")) {
    server.send(400, "text/plain", "state parametresi gerekli");
    return;
  }
  bool newState = server.arg("state") == "1";
  autoMode = false;
  setFan(newState);
  server.sendHeader("Location", "/");
  server.send(303);
}

void handleAutoMode() {
  autoMode = true;
  server.sendHeader("Location", "/");
  server.send(303);
}

void handleEnergyPage() { server.send(200, "text/html", getEnergyPage()); }

void handleEnergyReset() {
  totalFanOnTimeMs = 0;
  totalEnergyKwh = 0.0;
  totalCost = 0.0;
  fanOnTimeStart = fanState ? millis() : 0;
  energyMonthKey = getMonthKey();
  saveEnergyStats();
  server.sendHeader("Location", "/energy");
  server.send(303);
}

void setupServer() {
  server.on("/", HTTP_GET, handleRoot);
  server.on("/wifi", HTTP_GET, handleWifiPage);
  server.on("/wifiScan", HTTP_GET, handleWifiScan);
  server.on("/settings", HTTP_GET, handleSettingsPage);
  server.on("/energy", HTTP_GET, handleEnergyPage);
  server.on("/saveWifi", HTTP_POST, handleSaveWifi);
  server.on("/saveSettings", HTTP_POST, handleSaveSettings);
  server.on("/toggleFan", HTTP_GET, handleToggleFan);
  server.on("/autoMode", HTTP_GET, handleAutoMode);
  server.on("/energy/reset", HTTP_GET, handleEnergyReset);
  server.onNotFound([](){ server.send(404, "text/plain", "Sayfa bulunamadı"); });
}

void setup() {
  pinMode(FAN_PIN, OUTPUT);
  digitalWrite(FAN_PIN, LOW);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  Serial.begin(115200);
  delay(100);

  prefs.begin("fanctrl", false);
  loadSettings();
  
  // Telegram konfigürasyonu kontrol et
  Serial.println("\n=== Telegram Bot Konfigürasyonu ===");
  Serial.println("Bot Adı: @" + String(botUsername));
  Serial.println(String("Token: ") + (telegramToken.length() > 0 ? "YÜKLÜ" : "BOŞ"));
  Serial.println(String("Chat ID: ") + (telegramChatId.length() > 0 ? telegramChatId : "BOŞ"));
  Serial.println("Offset: " + String(telegramOffset));
  Serial.println("===================================\n");
  
  secureClient.setInsecure();
  configTime(0, 0, ntpServer);
  startAccessPoint();
  connectWiFi();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi baglantisi basarisiz, AP acik kalacak ve tekrar denenecek.");
  } else {
    Serial.println("WiFi'ya baglandi.");
    Serial.println("DNS Sunuculari:");
    Serial.print("  1: ");
    Serial.println(WiFi.dnsIP(0));
    Serial.print("  2: ");
    Serial.println(WiFi.dnsIP(1));
  }
  
  Serial.println("\n=== Baglanti Bilgileri ===");
  Serial.print("AP SSID: ");
  Serial.println(apSsid);
  Serial.print("AP Pass: ");
  Serial.println(apPassword);
  Serial.println("=====================\n");

  if (MDNS.begin(deviceHostname)) {
    Serial.println("mDNS hazır: http://ceylan-robot.local");
  } else {
    Serial.println("mDNS başlatılamadı.");
  }

  setupServer();
  server.begin();
  Serial.println("Web sunucu başlatıldı.");
  Serial.println("Erisim: http://192.168.4.1 (AP) veya http://192.168.5.170 (CEYLAN-ROBOT)");
}

void loop() {
  server.handleClient();
  retryWiFiIfNeeded();
  updateEnergyConsumption();  // Enerji tüketimini sürekli güncelle
  if (WiFi.status() == WL_CONNECTED) {
    if (millis() - lastTelegramPoll > TELEGRAM_POLL_MS) {
      lastTelegramPoll = millis();
      handleTelegram();
    }
    checkSchedule();
  }
  digitalWrite(LED_PIN, fanState ? HIGH : LOW);
}
