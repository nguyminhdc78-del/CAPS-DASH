/*
 * WS2812B status ring - colour, layout, and the watchdog that keeps it honest.
 *
 * WHY THESE COLOURS, and not "red" and "green" out of the box.
 *
 * The ring has to be readable with the sun on it, and in daylight the only
 * things that survive are (a) maximum drive and (b) saturation. Washing a hue
 * out towards white - the instinctive way to make an LED "brighter" - is
 * exactly wrong: against a sunlit background a desaturated colour reads as
 * "lamp is on" and nothing more, and the whole point is the colour.
 *
 * The eye is not equally sensitive to the two dies. Photopic sensitivity peaks
 * at 555 nm; the WS2812B green die sits at ~525 nm (V(l) ~ 0.79) and the red
 * die at ~625 nm (V(l) ~ 0.27). Typical parts bear that out - roughly
 * 1100-1400 mcd green against 550-700 mcd red at the same 20 mA. So:
 *
 *   - RED IS THE LIMITING CHANNEL. It is driven flat out at 255 because there
 *     is nothing above it. A hint of green (12/255) buys about 9% more
 *     luminance for a hue shift too small to see - still unmistakably red.
 *     If the ring is still not readable in direct sun, the fix is a hood or a
 *     larger ring, not a bigger number; this is already the maximum.
 *   - GREEN IS HELD BACK to 200, not 255. At 255 it is roughly twice the red's
 *     luminance, which makes the red look broken by comparison and blinds
 *     anyone standing near it at night. 200 still clears the red comfortably.
 *   - The touch of blue in the green pushes it toward the blue-green traffic
 *     signals use deliberately: red/green is the worst possible pair for the
 *     ~8% of men with a red-green deficiency, and that shift is the cheapest
 *     thing that helps. It costs no visibility - blue adds a little luminance
 *     rather than removing any.
 *
 * UNKNOWN IS NOT GREEN, and the same rule that governs the dashboard governs
 * the lamp: a bay nobody has resolved yet must never show as free, because
 * green sends a driver to it. It breathes amber instead, and so does a ring
 * whose server has gone quiet - a lamp still confidently showing the last
 * answer it heard twenty minutes ago is worse than one admitting it is lost.
 *
 * THREE DISPLAYS, in priority order:
 *
 *   no push for 90 s   whole ring breathes amber, slow and deep (2.0 s)
 *   every bay occupied whole ring pulses red, fast and shallow  (1.4 s)
 *   otherwise          one arc per bay, red / green / amber
 *
 * The middle one is a distance signal. Arcs answer "which bay is free" for
 * somebody standing under the camera; they cannot answer "is it worth driving
 * down this aisle at all" from the far end, where the whole ring is one red
 * smudge and the gaps between arcs are invisible. So a full row stops being a
 * row of segments and becomes a single moving object instead.
 */

#include "slot-ring-led.h"

#include <Adafruit_NeoPixel.h>

// GPIO 14 is HS2_CLK, one of the SD-card pins. This sketch never mounts the
// card, so the pin is free - but do not add SD logging later without moving
// the ring first. It is not a strapping pin, so holding it low or high at
// reset is harmless.
static const uint8_t RING_DATA_PIN = 14;

// The ring actually fitted on this node. 12, 16 and 24 are the common sizes;
// everything below divides this by the slot count at runtime.
//
// 12 across the three bays this camera watches divides exactly: 4 LEDs per
// bay, 3 lit and 1 dark as the separator, nothing left over. A count that does
// not divide evenly is not an error - the remainder simply stays dark rather
// than being padded into the last arc, which would make one bay look wider
// than the rest - but an exact division reads best.
static const uint16_t RING_LED_COUNT = 12;

// Full output, because daylight is the design case. Lower it to ~64 for an
// indoor bay unless you enjoy being stared at.
//
// POWER: one lit LED on a single channel draws ~20 mA, so a 12-LED ring is
// ~240 mA on top of the camera's own ~250 mA peak. Feed the ring from the
// module's 5V pin and give the whole node a supply with real headroom - a
// 500 mA phone charger will brown the ESP32 out mid-WiFi-transmit, which
// looks exactly like a flaky camera. Never take the ring off the 3V3 pin.
static const uint8_t RING_BRIGHTNESS = 255;

// One dark LED between neighbouring arcs, so two adjacent occupied bays do
// not read as one long red arc.
static const uint8_t SLOT_GAP_LEDS = 1;

// More bays than this on one ring and each arc is a single LED - unreadable
// from across a car park. Mirrored by MAX_SLOTS in the backend's
// slot_led_service, which refuses to push a longer string.
static const uint8_t MAX_SLOTS = 8;

// How long a pushed state stays believable. The backend re-sends at least
// every 15 s even when nothing changed, and its own detector is forced to run
// at least every 30 s, so 90 s is roughly three missed refreshes - long enough
// not to flicker on one dropped packet, short enough that a dead link is
// visible while the driver is still in the car park.
static const uint32_t RING_STALE_MS = 90000UL;

// Repaint cadence while something on the ring is animating.
static const uint32_t RING_FRAME_MS = 40;

static Adafruit_NeoPixel ring(RING_LED_COUNT, RING_DATA_PIN, NEO_GRB + NEO_KHZ800);

static const uint32_t COLOUR_OCCUPIED = Adafruit_NeoPixel::Color(255, 12, 0);
static const uint32_t COLOUR_FREE = Adafruit_NeoPixel::Color(0, 200, 40);
static const uint32_t COLOUR_UNKNOWN = Adafruit_NeoPixel::Color(255, 96, 0);

static char slotChars[MAX_SLOTS + 1] = {0};
static uint8_t slotCount = 0;
static uint32_t lastApplyMs = 0;
static bool haveState = false;

static uint32_t lastFrameMs = 0;
static bool needsRepaint = true;

// ------------------------------------------------------------------ helpers

static uint32_t colourFor(char state) {
  if (state == '1') return COLOUR_OCCUPIED;
  if (state == '0') return COLOUR_FREE;
  return COLOUR_UNKNOWN;
}

/** Scale a packed colour by 0..255, for the unknown breath. */
static uint32_t dim(uint32_t colour, uint8_t level) {
  const uint8_t r = (uint8_t)((colour >> 16) & 0xFF);
  const uint8_t g = (uint8_t)((colour >> 8) & 0xFF);
  const uint8_t b = (uint8_t)(colour & 0xFF);
  return Adafruit_NeoPixel::Color((r * level) / 255, (g * level) / 255,
                                  (b * level) / 255);
}

/**
 * Triangle wave, 0..255 over ~2 s. A triangle rather than a sine because the
 * only thing that matters is that it visibly moves, and this costs no FPU.
 */
static uint8_t breathLevel() {
  const uint32_t phase = millis() % 2000;
  const uint32_t up = phase < 1000 ? phase : 2000 - phase;
  return (uint8_t)(40 + (up * 215) / 1000);  // never fully off - 40..255
}

/**
 * The "no free bay" pulse: 150..255 over ~1.4 s, faster and far shallower
 * than `breathLevel`.
 *
 * Shallow because this is the daylight case. A pulse that dips to near-black
 * halves the average output, and the reason the ring is readable in sun is
 * that it is never dim; the floor sits at 150 so the darkest phase still
 * carries. Motion is the strongest attention cue there is, which is why a
 * full car park moves at all - "every bay taken" has to be readable from the
 * end of the aisle, where individual arcs are just a red smudge.
 */
static uint8_t fullPulseLevel() {
  const uint32_t phase = millis() % 1400;
  const uint32_t up = phase < 700 ? phase : 1400 - phase;
  return (uint8_t)(150 + (up * 105) / 700);
}

/** True when every bay this ring covers is occupied - nowhere left to park. */
static bool noFreeBay() {
  if (slotCount == 0) return false;
  for (uint8_t i = 0; i < slotCount; i++) {
    if (slotChars[i] != '1') return false;
  }
  return true;
}

static bool stale() {
  return !haveState || (millis() - lastApplyMs) > RING_STALE_MS;
}

/** Paint the whole ring from the current state. One code path, always. */
static void render() {
  ring.clear();

  if (stale()) {
    // No server, or none for a long time. The whole ring breathes amber -
    // deliberately different from any per-slot pattern, so "I have lost the
    // server" cannot be mistaken for "these bays are unresolved".
    const uint32_t colour = dim(COLOUR_UNKNOWN, breathLevel());
    for (uint16_t i = 0; i < RING_LED_COUNT; i++) ring.setPixelColor(i, colour);
    ring.show();
    return;
  }

  if (noFreeBay()) {
    // Every bay taken. Deliberately NOT drawn as arcs: with all of them red
    // the gaps carry no information anyway, and a driver at the end of the
    // aisle needs one unmistakable answer - "do not come down here" - rather
    // than a row of identical red segments to count. Solid and pulsing, so it
    // cannot be confused with the amber breath, which is a different colour
    // and a different, slower rhythm.
    const uint32_t colour = dim(COLOUR_OCCUPIED, fullPulseLevel());
    for (uint16_t i = 0; i < RING_LED_COUNT; i++) ring.setPixelColor(i, colour);
    ring.show();
    return;
  }

  const uint16_t span = RING_LED_COUNT / slotCount;
  const uint16_t gap = slotCount > 1 ? SLOT_GAP_LEDS : 0;
  const uint16_t lit = span > gap ? span - gap : span;

  for (uint8_t slot = 0; slot < slotCount; slot++) {
    uint32_t colour = colourFor(slotChars[slot]);
    if (slotChars[slot] != '1' && slotChars[slot] != '0') {
      colour = dim(colour, breathLevel());
    }
    const uint16_t start = slot * span;
    for (uint16_t i = 0; i < lit; i++) {
      ring.setPixelColor(start + i, colour);
    }
  }
  // Any LEDs left over by the division stay dark rather than being padded
  // into the last arc, which would make one bay look wider than the rest.
  ring.show();
}

/** True while any part of the ring is animating and needs a repaint per frame. */
static bool animating() {
  if (stale() || noFreeBay()) return true;
  for (uint8_t i = 0; i < slotCount; i++) {
    if (slotChars[i] != '1' && slotChars[i] != '0') return true;
  }
  return false;
}

// --------------------------------------------------------------------- API

void ringBegin() {
  ring.begin();
  ring.setBrightness(RING_BRIGHTNESS);
  ring.clear();
  ring.show();

  // Wiring self-test: red, then green, then the amber the ring rests on until
  // the first push. If the first step comes up green, the strip is RGB rather
  // than GRB - change NEO_GRB above. If nothing lights at all, check that the
  // ring's 5V comes from the 5V pin and not 3V3.
  const uint32_t steps[] = {COLOUR_OCCUPIED, COLOUR_FREE, COLOUR_UNKNOWN};
  for (uint8_t step = 0; step < 3; step++) {
    for (uint16_t i = 0; i < RING_LED_COUNT; i++) ring.setPixelColor(i, steps[step]);
    ring.show();
    delay(250);
  }
  needsRepaint = true;
}

bool ringApply(const String &slots) {
  const int count = slots.length();
  if (count <= 0 || count > MAX_SLOTS || count > RING_LED_COUNT) return false;

  char parsed[MAX_SLOTS + 1] = {0};
  for (int i = 0; i < count; i++) {
    const char c = slots[i];
    if (c == '1' || c == '0') {
      parsed[i] = c;
    } else if (c == 'u' || c == 'U' || c == '?') {
      parsed[i] = 'u';
    } else {
      // Reject the whole push rather than guessing at one character. A
      // half-understood string would light bays with somebody else's state.
      return false;
    }
  }

  needsRepaint = needsRepaint || slotCount != count ||
                 strncmp(parsed, slotChars, count) != 0 || stale();
  memcpy(slotChars, parsed, count);
  slotChars[count] = 0;
  slotCount = (uint8_t)count;
  lastApplyMs = millis();
  haveState = true;
  return true;
}

void ringLoop() {
  const uint32_t now = millis();
  if (!needsRepaint && !animating()) return;
  if (now - lastFrameMs < RING_FRAME_MS) return;
  lastFrameMs = now;
  needsRepaint = false;
  render();
}

String ringState() {
  return haveState ? String(slotChars) : String("");
}

long ringAgeSeconds() {
  if (!haveState) return -1;
  return (long)((millis() - lastApplyMs) / 1000UL);
}
