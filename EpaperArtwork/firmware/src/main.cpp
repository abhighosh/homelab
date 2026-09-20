#include <Arduino.h>
#include <ArduinoJson.h>
#include <ArduinoOTA.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiManager.h>
#include <TFT_eSPI.h>

#ifndef EPAPER_ENABLE
#error "Seeed_GFX E1001 setup was not selected"
#endif

// The E1001 carrier's USB-to-UART bridge is wired to UART1, not USB CDC.
#define LOG Serial1

namespace {
constexpr int kWidth = 800;
constexpr int kHeight = 480;
constexpr size_t kFrameBytes = kWidth * kHeight / 2;
constexpr uint8_t kGreen = 3;
constexpr uint8_t kRight = 4;
constexpr uint8_t kLeft = 5;
constexpr uint32_t kPollMs = 30UL * 60UL * 1000UL;
constexpr uint32_t kSurpriseMs = 60UL * 60UL * 1000UL;
const char *kPages[] = {"portrait", "today", "map", "almanac", "constellations"};
constexpr uint8_t kSurprise = 5;

EPaper panel;
Preferences prefs;
String serverUrl;
String otaPassword;
String shownHash;
uint8_t mode = 0;
uint8_t shown = 0;
uint8_t *frame = nullptr;
uint32_t lastPoll = 0;
uint32_t lastSurprise = 0;
uint32_t lastButton = 0;
bool leftWasDown = false;
bool rightWasDown = false;
bool greenWasDown = false;

void configureNetwork() {
  WiFi.mode(WIFI_STA);
  WiFiManager manager;
  manager.setConfigPortalTimeout(300);
  manager.setConnectTimeout(20);
  WiFiManagerParameter serverParameter("server", "Artwork server URL",
                                      serverUrl.c_str(), 95);
  WiFiManagerParameter otaParameter("ota", "OTA password (set one)",
                                   "", 64);
  manager.addParameter(&serverParameter);
  manager.addParameter(&otaParameter);
  manager.setSaveConfigCallback([] { LOG.println("Configuration saved"); });
  // Holding green during power-up reopens provisioning even with saved Wi-Fi.
  const bool forcePortal = otaPassword.length() < 8 || digitalRead(kGreen) == LOW;
  while (!(forcePortal ? manager.startConfigPortal("E1001-Artwork")
                       : manager.autoConnect("E1001-Artwork"))) {
    // Keep the existing e-paper image while Wi-Fi is unavailable. The setup
    // access point is retried so the device is recoverable without USB.
    delay(1000);
  }
  String enteredServer = serverParameter.getValue();
  enteredServer.trim();
  while (enteredServer.endsWith("/")) enteredServer.remove(enteredServer.length() - 1);
  if (enteredServer.startsWith("http://") && enteredServer.length() < 96) {
    serverUrl = enteredServer;
    prefs.putString("server", serverUrl);
  }
  String enteredOta = otaParameter.getValue();
  if (enteredOta.length() >= 8) {
    otaPassword = enteredOta;
    prefs.putString("ota", otaPassword);
  }
  LOG.printf("Wi-Fi connected: %s; image server: %s\n",
                WiFi.localIP().toString().c_str(), serverUrl.c_str());
}

bool fetchManifestHash(uint8_t page, String &hash) {
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  http.setTimeout(10000);
  if (!http.begin(serverUrl + "/manifest")) return false;
  int code = http.GET();
  if (code != HTTP_CODE_OK) { http.end(); return false; }
  JsonDocument document;
  DeserializationError error = deserializeJson(document, http.getStream());
  if (!error && document[kPages[page]].is<const char *>())
    hash = document[kPages[page]].as<String>();
  http.end();
  return !error && hash.length() == 16;
}

bool fetchAndDisplay(uint8_t page, const String &hash) {
  HTTPClient http;
  http.setTimeout(30000);
  if (!http.begin(serverUrl + "/frame/" + kPages[page] + ".g4")) return false;
  int code = http.GET();
  if (code != HTTP_CODE_OK || http.getSize() != static_cast<int>(kFrameBytes)) {
    LOG.printf("Frame request failed: HTTP %d, size %d\n", code, http.getSize());
    http.end();
    return false;
  }
  size_t received = http.getStreamPtr()->readBytes(frame, kFrameBytes);
  http.end();
  if (received != kFrameBytes) {
    LOG.printf("Incomplete frame: %u bytes\n", static_cast<unsigned>(received));
    return false;
  }
  panel.pushImage(0, 0, kWidth, kHeight, reinterpret_cast<uint16_t *>(frame));
  panel.update();
  shownHash = hash;
  prefs.putString("hash", hash);
  prefs.putUChar("shown", page);
  LOG.printf("Displayed %s (%s)\n", kPages[page], hash.c_str());
  return true;
}

void refresh(bool force = false) {
  if (!frame || WiFi.status() != WL_CONNECTED) return;
  String remoteHash;
  if (!fetchManifestHash(shown, remoteHash)) return;
  if (force || shownHash != remoteHash) fetchAndDisplay(shown, remoteHash);
}

void reroll() {
  uint8_t next;
  do { next = random(0, 5); } while (next == shown);
  shown = next;
  shownHash = "";
  lastSurprise = millis();
  refresh(true);
}

void changeMode(uint8_t next) {
  mode = next;
  prefs.putUChar("mode", mode);
  if (mode == kSurprise) reroll();
  else {
    shown = mode;
    shownHash = "";
    refresh(true);
  }
}

void onButton(uint8_t pin) {
  if (millis() - lastButton < 300) return;
  lastButton = millis();
  if (pin == kGreen) {
    if (mode == kSurprise) reroll();
    else changeMode(0);
  } else if (pin == kLeft) {
    changeMode((mode + kSurprise) % (kSurprise + 1));
  } else {
    changeMode((mode + 1) % (kSurprise + 1));
  }
}
}  // namespace

void setup() {
  LOG.begin(115200, SERIAL_8N1, 44, 43);
  delay(300);
  pinMode(kGreen, INPUT_PULLUP);
  pinMode(kLeft, INPUT_PULLUP);
  pinMode(kRight, INPUT_PULLUP);
  prefs.begin("artwork", false);
  mode = prefs.getUChar("mode", 0);
  if (mode > kSurprise) mode = 0;
  shown = mode == kSurprise ? prefs.getUChar("shown", 0) : mode;
  if (shown >= kSurprise) shown = 0;
  shownHash = prefs.getString("hash", "");
  serverUrl = prefs.getString("server", "http://192.168.0.10:8765");
  otaPassword = prefs.getString("ota", "");
  frame = static_cast<uint8_t *>(ps_malloc(kFrameBytes));
  if (!frame) { LOG.println("PSRAM frame allocation failed"); return; }
  panel.begin();
  panel.initGrayMode(GRAY_LEVEL4);
  configureNetwork();
  // The bundled Arduino core already defaults to minimum modem sleep. The
  // maximum DTIM-aware setting reduces radio-on time while keeping Wi-Fi and
  // OTA reachable; unlike deep sleep it needs no special maintenance window.
  if (!WiFi.setSleep(WIFI_PS_MAX_MODEM)) LOG.println("Wi-Fi power save unavailable");
  ArduinoOTA.setHostname("e1001-artwork");
  if (otaPassword.length() >= 8) {
    ArduinoOTA.setPassword(otaPassword.c_str());
    ArduinoOTA.begin();
  } else {
    LOG.println("OTA disabled until a password is set in the setup portal");
  }
  randomSeed(esp_random());
  refresh();
  lastPoll = millis();
}

void loop() {
  if (otaPassword.length() >= 8) ArduinoOTA.handle();
  const bool leftDown = digitalRead(kLeft) == LOW;
  const bool rightDown = digitalRead(kRight) == LOW;
  const bool greenDown = digitalRead(kGreen) == LOW;
  if (leftDown && !leftWasDown) onButton(kLeft);
  else if (rightDown && !rightWasDown) onButton(kRight);
  else if (greenDown && !greenWasDown) onButton(kGreen);
  leftWasDown = leftDown;
  rightWasDown = rightDown;
  greenWasDown = greenDown;
  if (mode == kSurprise && millis() - lastSurprise >= kSurpriseMs) reroll();
  if (millis() - lastPoll >= kPollMs) {
    lastPoll = millis();
    refresh();
  }
  delay(75);
}
