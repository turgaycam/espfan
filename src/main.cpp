#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ESPmDNS.h>
#include <ArduinoJson.h>
#include <time.h>

#include "config/EnergyConfig.h"
#include "config/PinConfig.h"
#include "config/RelayConfig.h"
#include "config/TelegramConfig.h"
#include "config/TimeConfig.h"
#include "config/WiFiConfig.h"

WebServer server(WEB_PORT);
Preferences prefs;
WiFiClientSecure secureClient;

String wifiSsid;
String wifiPassword;
String connectedWifiSsid;
String wifiSsid2;      // İkinci WiFi profili
String wifiPassword2;  // İkinci WiFi şifresi
String telegramToken;
String telegramChatId;
String customIp;
int timezoneOffset = DEFAULT_TIMEZONE_OFFSET;
bool dstEnabled = false;
int schedule1StartH = DEFAULT_SCHEDULE1_START_H;
int schedule1StartM = DEFAULT_SCHEDULE1_START_M;
int schedule1EndH = DEFAULT_SCHEDULE1_END_H;
int schedule1EndM = DEFAULT_SCHEDULE1_END_M;
int schedule2StartH = DEFAULT_SCHEDULE2_START_H;
int schedule2StartM = DEFAULT_SCHEDULE2_START_M;
int schedule2EndH = DEFAULT_SCHEDULE2_END_H;
int schedule2EndM = DEFAULT_SCHEDULE2_END_M;
bool schedule2Enabled = DEFAULT_SCHEDULE2_ENABLED;

bool autoMode = true;
bool fanState = false;
unsigned long lastTelegramPoll = 0;
unsigned long lastWifiRetry = 0;
unsigned long lastEnergySave = 0;
unsigned long lastFanRuntimeSave = 0;
long telegramOffset = 0;

// Enerji hesaplaması için değişkenler
unsigned long fanOnTimeStart = 0;  // Fan açılma zamanı
unsigned long totalFanOnTimeMs = 0;  // Toplam açık kalma süresi (ms)
float totalEnergyKwh = 0.0;  // Toplam tüketilen enerji (kWh)
float totalCost = 0.0;  // Toplam maliyet (TL)
String energyMonthKey;

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
    "</style></head><body><header><div class=\"topbar\"><div class=\"brand\"><h1>ESP32-S2 Fan Kontrol</h1><p>CEYLAN-ROBOT akilli fan paneli</p></div><div class=\"pill\">DHCP / ceylan-robot.local</div></div></header><main>";
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
  if (start == end) return false;
  if (start < end) return minutes >= start && minutes < end;
  return minutes >= start || minutes < end;
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

String formatTimeValue(int h, int m) {
  char buf[6];
  snprintf(buf, sizeof(buf), "%02d:%02d", h, m);
  return String(buf);
}

void parseTimeValue(const String& value, int& h, int& m) {
  if (value.length() < 5 || value.charAt(2) != ':') return;
  int parsedH = value.substring(0, 2).toInt();
  int parsedM = value.substring(3, 5).toInt();
  if (parsedH < 0 || parsedH > 23 || parsedM < 0 || parsedM > 59) return;
  h = parsedH;
  m = parsedM;
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
    digitalWrite(FAN_PIN, on ? RELAY_ON_LEVEL : RELAY_OFF_LEVEL);
    return;
  }

  fanState = on;
  digitalWrite(FAN_PIN, on ? RELAY_ON_LEVEL : RELAY_OFF_LEVEL);

  // Enerji hesaplaması
  if (on) {
    fanOnTimeStart = millis();
    lastFanRuntimeSave = millis();
  } else if (fanOnTimeStart > 0) {
    unsigned long onDuration = millis() - fanOnTimeStart;
    totalFanOnTimeMs += onDuration;
    fanOnTimeStart = 0;
    updateEnergyConsumption();
    saveEnergyStats();
  }
}

void updateEnergyConsumption() {
  if (fanState && fanOnTimeStart > 0 && millis() - lastFanRuntimeSave > FAN_RUNTIME_SAVE_MS) {
    unsigned long onDuration = millis() - fanOnTimeStart;
    totalFanOnTimeMs += onDuration;
    fanOnTimeStart = millis();
    lastFanRuntimeSave = millis();
    saveEnergyStats();
  }

  float hours = getCurrentFanOnTimeMs() / 3600000.0;
  totalEnergyKwh = (CONFIG_FAN_POWER_WATTS * hours) / 1000.0;
  totalCost = totalEnergyKwh * CONFIG_ELECTRICITY_RATE;

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

  String page = htmlHeader("Toplam Enerji");
  page += "<section class=\"metrics\">";
  page += "<div class=\"metric\"><span>Toplam Calisma</span><strong>" + formatDuration(getCurrentFanOnTimeMs()) + "</strong></div>";
  page += "<div class=\"metric\"><span>Anlik Durum</span><strong>" + String(fanState ? "Fan acik" : "Fan kapali") + "</strong></div>";
  page += "<div class=\"metric\"><span>Toplam Tuketim</span><strong>" + String(totalEnergyKwh, 4) + " kWh</strong></div>";
  page += "<div class=\"metric\"><span>Toplam Maliyet</span><strong>" + String(totalCost, 2) + " TL</strong></div>";
  page += "</section>";

  page += "<section class=\"grid\">";
  page += "<div class=\"card\"><h2>Toplam Enerji Takibi</h2>";
  page += "<p class=\"status\"><strong>Fan gucu:</strong> " + String(CONFIG_FAN_POWER_WATTS, 0) + " Watt</p>";
  page += "<p class=\"status\"><strong>Elektrik tarifi:</strong> " + String(CONFIG_ELECTRICITY_RATE, 2) + " TL/kWh</p>";
  page += "<p class=\"status\"><strong>Hesap:</strong> Fan acik kaldigi toplam sure uzerinden kWh ve TL hesaplanir.</p>";
  page += "<p class=\"small\">Ay degistiginde saya� otomatik sifirlanir. Fan calisirken sure ve maliyet anlik guncellenir.</p>";
  page += "<div class=\"actions\"><a class=\"button button-primary\" href=\"/\">Ana Sayfa</a><a class=\"button button-danger\" href=\"/energy/reset/confirm\">Toplami Sifirla</a></div>";
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
  prefs.putString("customIp", "");
  prefs.putString("gateway", "");
  prefs.putString("subnet", "");
  prefs.putString("dns1", "");
  prefs.putString("dns2", "");
  prefs.putString("token", telegramToken);
  prefs.putString("chatid", telegramChatId);
  prefs.putInt("tz", timezoneOffset);
  prefs.putBool("dst", dstEnabled);
  prefs.putInt("s1sh", schedule1StartH);
  prefs.putInt("s1sm", schedule1StartM);
  prefs.putInt("s1eh", schedule1EndH);
  prefs.putInt("s1em", schedule1EndM);
  prefs.putInt("s2sh", schedule2StartH);
  prefs.putInt("s2sm", schedule2StartM);
  prefs.putInt("s2eh", schedule2EndH);
  prefs.putInt("s2em", schedule2EndM);
  prefs.putBool("s2en", schedule2Enabled);
  prefs.putULong("fanTime", totalFanOnTimeMs);
  prefs.putFloat("energy", totalEnergyKwh);
  prefs.putFloat("cost", totalCost);
  prefs.putString("energyMonth", energyMonthKey);
}

void loadSettings() {
  wifiSsid = prefs.getString("ssid", defaultWifiSsid);
  wifiPassword = prefs.getString("pass", defaultWifiPassword);
  if (wifiSsid == "CEYLAN-ROBOT" && wifiPassword == "Mahfer123.") {
    wifiSsid = defaultWifiSsid;
    wifiPassword = defaultWifiPassword;
    prefs.putString("ssid", wifiSsid);
    prefs.putString("pass", wifiPassword);
  }
  wifiSsid2 = prefs.getString("ssid2", "");
  wifiPassword2 = prefs.getString("pass2", "");
  telegramToken = prefs.getString("token", defaultTelegramToken);
  telegramChatId = prefs.getString("chatid", defaultTelegramChatId);
  customIp = "";
  timezoneOffset = prefs.getInt("tz", DEFAULT_TIMEZONE_OFFSET);
  dstEnabled = prefs.getBool("dst", false);
  schedule1StartH = prefs.getInt("s1sh", DEFAULT_SCHEDULE1_START_H);
  schedule1StartM = prefs.getInt("s1sm", DEFAULT_SCHEDULE1_START_M);
  schedule1EndH = prefs.getInt("s1eh", DEFAULT_SCHEDULE1_END_H);
  schedule1EndM = prefs.getInt("s1em", DEFAULT_SCHEDULE1_END_M);
  schedule2StartH = prefs.getInt("s2sh", DEFAULT_SCHEDULE2_START_H);
  schedule2StartM = prefs.getInt("s2sm", DEFAULT_SCHEDULE2_START_M);
  schedule2EndH = prefs.getInt("s2eh", DEFAULT_SCHEDULE2_END_H);
  schedule2EndM = prefs.getInt("s2em", DEFAULT_SCHEDULE2_END_M);
  schedule2Enabled = prefs.getBool("s2en", DEFAULT_SCHEDULE2_ENABLED);
  telegramOffset = prefs.getLong("tgoffset", 0);
  totalFanOnTimeMs = prefs.getULong("fanTime", 0);
  totalEnergyKwh = prefs.getFloat("energy", 0.0);
  totalCost = prefs.getFloat("cost", 0.0);
  energyMonthKey = prefs.getString("energyMonth", "");
  Serial.println("Kayitli WiFi 1: " + wifiSsid);
  Serial.println("Kayitli WiFi 2: " + String(wifiSsid2.length() > 0 ? wifiSsid2 : "(bos)"));
}

void applyIpSettings() {
  WiFi.config(INADDR_NONE, INADDR_NONE, INADDR_NONE, INADDR_NONE);
  Serial.println("DHCP ile IP alinacak.");
}

String wifiStatusText(wl_status_t status) {
  switch (status) {
    case WL_IDLE_STATUS: return "IDLE";
    case WL_NO_SSID_AVAIL: return "SSID bulunamadi";
    case WL_SCAN_COMPLETED: return "Tarama tamamlandi";
    case WL_CONNECTED: return "Bagli";
    case WL_CONNECT_FAILED: return "Baglanti basarisiz";
    case WL_CONNECTION_LOST: return "Baglanti koptu";
    case WL_DISCONNECTED: return "Bagli degil";
    default: return "Bilinmeyen durum: " + String((int)status);
  }
}

bool connectToProfile(const String& ssid, const String& password, const String& label) {
  if (ssid.length() == 0) return false;

  WiFi.disconnect(false);
  delay(200);
  applyIpSettings();
  WiFi.begin(ssid.c_str(), password.c_str());
  Serial.print("Wi-Fi baglaniyor (");
  Serial.print(label);
  Serial.print("): ");
  Serial.println(ssid);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_CONNECT_TIMEOUT_MS) {
    delay(500);
    Serial.print('.');
  }

  Serial.println();
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println(label + " basarisiz. Durum: " + wifiStatusText(WiFi.status()));
    return false;
  }

  connectedWifiSsid = ssid;
  Serial.println(label + " baglandi.");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());
  Serial.print("DNS: ");
  Serial.print(WiFi.dnsIP(0));
  Serial.print(" / ");
  Serial.println(WiFi.dnsIP(1));
  return true;
}

void connectWiFiFixed() {
  WiFi.mode(WIFI_AP_STA);
  WiFi.setHostname(deviceHostname);
  connectedWifiSsid = "";

  bool hasPreferredWifi = wifiSsid.length() > 0 && wifiSsid != fallbackWifiSsid;
  int attempts = hasPreferredWifi ? PREFERRED_WIFI_ATTEMPTS : 1;

  for (int attempt = 1; attempt <= attempts; attempt++) {
    if (attempts > 1) {
      Serial.println("Kayitli WiFi denemesi " + String(attempt) + "/" + String(attempts));
    }
    if (connectToProfile(wifiSsid, wifiPassword, "1. profil")) return;
    if (attempt < attempts) delay(3000);
  }

  if (wifiSsid2.length() > 0) {
    Serial.println("1. profil basarisiz, 2. profili deniyor...");
    if (connectToProfile(wifiSsid2, wifiPassword2, "2. profil")) return;
  } else {
    Serial.println("2. profil WiFi tanimlanmadi.");
  }

  if (wifiSsid != fallbackWifiSsid && wifiSsid2 != fallbackWifiSsid) {
    Serial.println("Kayitli profiller basarisiz, test hotspot deneniyor...");
    if (connectToProfile(fallbackWifiSsid, fallbackWifiPassword, "test hotspot")) return;
  }

  WiFi.disconnect(false);
  connectedWifiSsid = "";
  Serial.println("WiFi basarisiz, AP acik kalacak.");
}

void connectWiFi() {
  connectWiFiFixed();
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

void retryPreferredWiFiIfNeeded() {
  if (WiFi.status() != WL_CONNECTED) return;
  if (connectedWifiSsid != fallbackWifiSsid) return;
  if (wifiSsid == fallbackWifiSsid && wifiSsid2.length() == 0) return;
  if (millis() - lastWifiRetry < WIFI_RETRY_MS) return;

  lastWifiRetry = millis();
  Serial.println("Test hotspot uzerinde, kayitli WiFi tekrar deneniyor.");
  connectWiFi();
}
String getScheduleStatus() {
  String status = "Otomatik: " + formatTimeValue(schedule1StartH, schedule1StartM) + " - " + formatTimeValue(schedule1EndH, schedule1EndM);
  if (schedule2Enabled) {
    status += " ve " + formatTimeValue(schedule2StartH, schedule2StartM) + " - " + formatTimeValue(schedule2EndH, schedule2EndM);
  }
  status += " arasi calisir.";
  return status;
}

String getNetworkInfo() {
  if (WiFi.status() == WL_CONNECTED) {
    return String("Wi-Fi bagli: ") + connectedWifiSsid + " - Yerel IP: " + WiFi.localIP().toString() + " - AP IP: " + WiFi.softAPIP().toString();
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
  page += "<div class=\"metric\"><span>Toplam Enerji</span><strong>" + String(totalEnergyKwh, 3) + " kWh</strong></div>";
  page += "<div class=\"metric\"><span>Toplam Maliyet</span><strong>" + String(totalCost, 2) + " TL</strong></div>";
  page += "</section>";

  page += "<section class=\"grid\">";
  page += "<div class=\"card hero\"><div class=\"fanbox\"><div class=\"fan " + String(fanState ? "on" : "off") + "\"><div class=\"hub\"></div></div></div>";
  page += "<div><h2>Fan Simulasyonu</h2>";
  page += "<p class=\"pill\"><span class=\"dot " + String(fanState ? "on" : "") + "\"></span>" + String(fanState ? "Fan calisiyor" : "Fan beklemede") + "</p>";
  page += "<p class=\"status\"><strong>Saat:</strong> " + getTimeString() + "</p>";
  page += "<p class=\"status\"><strong>Toplam sure:</strong> " + formatDuration(getCurrentFanOnTimeMs()) + "</p>";
  page += "<p class=\"status\"><strong>Tarife:</strong> " + String(CONFIG_ELECTRICITY_RATE, 2) + " TL/kWh, fan gucu " + String(CONFIG_FAN_POWER_WATTS, 0) + " W</p>";
  page += "<div class=\"actions\"><a class=\"button button-success\" href=\"/toggleFan?state=1\">Fan Ac</a><a class=\"button button-danger\" href=\"/toggleFan?state=0\">Fan Kapat</a><a class=\"button button-primary\" href=\"/autoMode\">Otomatik Mod</a><a class=\"button button-danger\" href=\"/energy/reset/confirm\">Sayaci Sifirla</a></div>";
  page += "</div></div>";

  page += "<div class=\"card\"><h2>Baglanti ve Plan</h2>";
  page += "<p class=\"status\"><strong>Ag:</strong> " + getNetworkInfo() + "</p>";
  page += "<p class=\"status\"><strong>Yerel adres:</strong> http://ceylan-robot.local</p>";
  page += "<p class=\"status\"><strong>Program:</strong> " + getScheduleStatus() + "</p>";
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
  
  page += "<p class=\"small\">IP adresi router tarafindan DHCP ile otomatik alinir. Guncel IP Telegram /durum veya /wifi_info komutuyla gorulebilir.</p>";
  
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
  page += "<div class=\"form-row\"><label><input type=\"checkbox\" name=\"dst\"" + String(dstEnabled ? " checked" : "") + "> Yaz saati uygulaması</label></div>";
  page += "<h2>Otomatik Fan Saatleri</h2>";
  page += "<div class=\"form-row\"><label>1. Baslangic</label><input type=\"time\" name=\"s1start\" value=\"" + formatTimeValue(schedule1StartH, schedule1StartM) + "\"></div>";
  page += "<div class=\"form-row\"><label>1. Bitis</label><input type=\"time\" name=\"s1end\" value=\"" + formatTimeValue(schedule1EndH, schedule1EndM) + "\"></div>";
  page += "<div class=\"form-row\"><label><input type=\"checkbox\" name=\"s2enabled\"" + String(schedule2Enabled ? " checked" : "") + "> 2. zaman araligi aktif</label></div>";
  page += "<div class=\"form-row\"><label>2. Baslangic</label><input type=\"time\" name=\"s2start\" value=\"" + formatTimeValue(schedule2StartH, schedule2StartM) + "\"></div>";
  page += "<div class=\"form-row\"><label>2. Bitis</label><input type=\"time\" name=\"s2end\" value=\"" + formatTimeValue(schedule2EndH, schedule2EndM) + "\"></div>";
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
        String status = "Fan: " + String(fanState ? "Acik" : "Kapali") + "\nMod: " + String(autoMode ? "Otomatik" : "Manuel") + "\nSaat: " + getTimeString() + "\nToplam sure: " + formatDuration(getCurrentFanOnTimeMs()) + "\nToplam enerji: " + String(totalEnergyKwh, 3) + " kWh\nToplam maliyet: " + String(totalCost, 2) + " TL\nProgram: " + getScheduleStatus() + "\nIP: " + WiFi.localIP().toString();
        sendTelegramMessage(status);
        Serial.println("    -> Durum gonderildi");
      } else if (text.equalsIgnoreCase("/start")) {
        sendTelegramMessage("Fan bot hazir. Komutlar: /durum, /fan_ac, /fan_kapat, /auto, /wifi_info");
        Serial.println("    -> Start mesaji gonderildi");
      } else if (text.equalsIgnoreCase("/wifi_info") || text.equalsIgnoreCase("/wifi_bilgi")) {
        String info = "Wi-Fi SSID: " + connectedWifiSsid + "\nIP: " + WiFi.localIP().toString() + "\nAP IP: " + WiFi.softAPIP().toString() + "\nMod: DHCP";
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
  bool running = isTimeInWindow(tm.tm_hour, tm.tm_min, schedule1StartH, schedule1StartM, schedule1EndH, schedule1EndM);
  if (schedule2Enabled) {
    running = running || isTimeInWindow(tm.tm_hour, tm.tm_min, schedule2StartH, schedule2StartM, schedule2EndH, schedule2EndM);
  }
  setFan(running);
}

void handleRoot() { server.send(200, "text/html", getRootPage()); }

void handleWifiPage() { server.send(200, "text/html", getWifiPage()); }

void handleWifiScan() { server.send(200, "text/html", getWifiPage(getScanResultsHtml())); }

void handleSettingsPage() { server.send(200, "text/html", getSettingsPage()); }

String getTrimmedArg(const String& name) {
  String value = server.arg(name);
  value.trim();
  return value;
}

void handleSaveWifi() {
  if (server.method() == HTTP_POST) {
    wifiSsid = getTrimmedArg("ssid");
    wifiPassword = server.arg("pass");
    wifiSsid2 = getTrimmedArg("ssid2");
    wifiPassword2 = server.arg("pass2");
    customIp = "";
    
    prefs.putString("ssid", wifiSsid);
    prefs.putString("pass", wifiPassword);
    prefs.putString("ssid2", wifiSsid2);
    prefs.putString("pass2", wifiPassword2);
    prefs.putString("customIp", "");
    prefs.putString("gateway", "");
    prefs.putString("subnet", "");
    prefs.putString("dns1", "");
    prefs.putString("dns2", "");
    
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
    customIp = "";
    timezoneOffset = server.arg("tz").toInt();
    dstEnabled = server.hasArg("dst");
    parseTimeValue(server.arg("s1start"), schedule1StartH, schedule1StartM);
    parseTimeValue(server.arg("s1end"), schedule1EndH, schedule1EndM);
    parseTimeValue(server.arg("s2start"), schedule2StartH, schedule2StartM);
    parseTimeValue(server.arg("s2end"), schedule2EndH, schedule2EndM);
    schedule2Enabled = server.hasArg("s2enabled");
    saveSettings();
    Serial.println("Genel ayarlar kaydedildi.");
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

void handleEnergyResetConfirm() {
  String page = htmlHeader("Sayac Sifirla");
  page += "<div class=\"card\"><h2>Enerji sayaci sifirlansin mi?</h2>";
  page += "<p class=\"status\"><strong>Toplam sure:</strong> " + formatDuration(getCurrentFanOnTimeMs()) + "</p>";
  page += "<p class=\"status\"><strong>Toplam enerji:</strong> " + String(totalEnergyKwh, 4) + " kWh</p>";
  page += "<p class=\"status\"><strong>Toplam maliyet:</strong> " + String(totalCost, 2) + " TL</p>";
  page += "<p class=\"small\">Bu islem sadece enerji/sure sayacini sifirlar. Wi-Fi, Telegram ve saat ayarlarina dokunmaz.</p>";
  page += "<div class=\"actions\"><a class=\"button button-danger\" href=\"/energy/reset\">Evet, Sifirla</a><a class=\"button button-primary\" href=\"/energy\">Vazgec</a></div>";
  page += "</div>";
  page += htmlFooter();
  server.send(200, "text/html", page);
}

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
  server.on("/energy/reset/confirm", HTTP_GET, handleEnergyResetConfirm);
  server.on("/energy/reset", HTTP_GET, handleEnergyReset);
  server.onNotFound([](){ server.send(404, "text/plain", "Sayfa bulunamadı"); });
}

void setup() {
  pinMode(FAN_PIN, OUTPUT);
  digitalWrite(FAN_PIN, RELAY_OFF_LEVEL);
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
  Serial.println("Erisim: http://192.168.4.1 (AP), http://ceylan-robot.local veya Telegram /wifi_info");
}

void loop() {
  server.handleClient();
  retryWiFiIfNeeded();
  retryPreferredWiFiIfNeeded();
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
