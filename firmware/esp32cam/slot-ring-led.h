/*
 * WS2812B status ring for a CAPS-DASH camera node.
 *
 * The ring shows what the SERVER decided, not what the camera saw. An
 * ESP32-CAM has no idea whether a bay holds a car - YOLO and the vote filter
 * run on the backend - so the state arrives over HTTP and this module owns
 * only the pixels and the "is that answer still fresh?" question.
 *
 * Wiring (matches the module's screen-printed ring header):
 *   ring 5V  -> ESP32-CAM 5V      ring GND -> GND      ring D -> GPIO 14
 *   ring DO  -> not connected
 */

#pragma once

#include <Arduino.h>

/** Bring the ring up and run the wiring self-test. Call once from setup(). */
void ringBegin();

/**
 * Adopt one state character per slot, in slot-code order.
 *
 *   '1' occupied   '0' free   'u' or '?' unknown
 *
 * Returns false - and changes nothing - if the string is empty, longer than
 * the ring can divide, or holds a character that is not one of those.
 */
bool ringApply(const String &slots);

/** Drive animations and the staleness watchdog. Call every loop(). */
void ringLoop();

/** The last string accepted by `ringApply`, for /status. */
String ringState();

/** Seconds since the last accepted push, or -1 if there has never been one. */
long ringAgeSeconds();
