#pragma once

// Varsayilan ve kurtarma WiFi ayarlari
constexpr int WEB_PORT = 80;
constexpr int WIFI_RETRY_MS = 30000;
constexpr int WIFI_CONNECT_TIMEOUT_MS = 25000;
constexpr int PREFERRED_WIFI_ATTEMPTS = 3;

const char* const defaultWifiSsid = "test";
const char* const defaultWifiPassword = "12345678";
const char* const fallbackWifiSsid = "test";
const char* const fallbackWifiPassword = "12345678";
const char* const deviceHostname = "ceylan-robot";
const char* const apSsid = "FanControlAP";
const char* const apPassword = "fan12345";

