/*
 * Copy this file to `wifi-credentials.h` (same directory) and fill it in.
 *
 *   cp wifi-credentials.example.h wifi-credentials.h
 *
 * `wifi-credentials.h` is gitignored. The example is not - it is the contract,
 * the same way `.env.example` is for the server.
 *
 * Both the Arduino IDE and PlatformIO compile every file in this directory, so
 * nothing else needs configuring; `esp32cam-caps.ino` picks these up through
 * `__has_include` and falls back to a password that cannot associate when the
 * file is absent. A build with no credentials therefore fails to join the
 * network loudly rather than looking like a hardware fault.
 */

#pragma once

#define CAPS_WIFI_SSID "Meomeo"
#define CAPS_WIFI_PASSWORD "put-the-hotspot-password-here"
