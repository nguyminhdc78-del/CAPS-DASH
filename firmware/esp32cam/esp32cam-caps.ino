/*
 * CAPS-DASH ESP32-CAM node.
 *
 * Three endpoints:
 *   GET /anh                    one JPEG still  (compatible with the old firmware)
 *   GET /stream                 continuous MJPEG
 *   GET /control?var=X&val=N    sensor settings
 *   GET /status                 current settings + link quality, as JSON
 *
 * WHY A STREAM AS WELL AS A STILL, measured on the real hardware:
 * one still costs ~74 ms end to end - 8 ms TCP handshake, 37 ms sensor
 * capture plus JPEG encode, 28 ms to move 12.8 KB over WiFi - which caps
 * polling at about 13 fps. Those three run strictly in sequence per request.
 * A stream removes the handshake entirely and lets the sensor capture the
 * next frame while the current one is still going out, so the ceiling
 * becomes roughly the slower of capture and transfer rather than their sum.
 *
 * The cost is real and worth stating: streaming keeps the sensor and the
 * radio busy continuously, so the module draws more power and runs warmer,
 * and this WebServer is single-threaded - while a stream is open, a second
 * client asking for /anh waits. The CAPS-DASH backend is meant to be the
 * only consumer; everything else reads frames from the backend.
 *
 * Board: AI-Thinker ESP32-CAM (OV2640).
 * Arduino IDE: Tools > Board "AI Thinker ESP32-CAM", Partition "Huge APP".
 * Flashing needs IO0 pulled to GND at reset; remove it before running.
 */

#include <WiFi.h>
#include <WebServer.h>
#include <esp_camera.h>

// ---------------------------------------------------------------- settings

static const char *WIFI_SSID = "CHANGE_ME";
static const char *WIFI_PASSWORD = "CHANGE_ME";

// A fixed address, because the camera's URL is stored in the CAPS-DASH
// database. A DHCP lease that moves after a power cut would leave every
// camera row pointing at nothing, and the failure looks like a dead camera
// rather than a changed address. Set USE_STATIC_IP to false to let DHCP
// assign one anyway.
static const bool USE_STATIC_IP = true;
static const IPAddress STATIC_IP(192, 168, 137, 50);
static const IPAddress GATEWAY(192, 168, 137, 1);
static const IPAddress SUBNET(255, 255, 255, 0);
static const IPAddress DNS_SERVER(192, 168, 137, 1);

// Shown in /status. Give each module a distinct one - it is the only way to
// tell two identical boards apart on the network.
static const char *CAMERA_CODE = "cam-01";

// VGA is what the slot polygons were drawn against. Lower it (QVGA) for a
// markedly faster stream; the ROI editor rescales polygons for a changed
// frame size, so this is safe to change - but redraw-quality suffers.
static const framesize_t DEFAULT_FRAME_SIZE = FRAMESIZE_VGA;  // 640x480
static const int DEFAULT_JPEG_QUALITY = 12;                   // 10..63, lower = better

// AI-Thinker pinout. Other carrier boards differ - check before assuming.
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

#define FLASH_GPIO_NUM 4

static const char *STREAM_BOUNDARY = "capsframe";

static WebServer server(80);

// ------------------------------------------------------------------ camera

static bool startCamera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = DEFAULT_FRAME_SIZE;
  config.jpeg_quality = DEFAULT_JPEG_QUALITY;
  config.grab_mode = CAMERA_GRAB_LATEST;

  // Two buffers in PSRAM is what makes the stream faster than polling: the
  // sensor fills one while the other is being sent. With a single buffer the
  // two serialise again and the stream is worth little.
  if (psramFound()) {
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
  } else {
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
    config.frame_size = FRAMESIZE_QVGA;  // no PSRAM: keep the buffer affordable
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("camera init failed: 0x%x\n", err);
    return false;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  if (sensor != nullptr) {
    // Ceiling-mounted modules are usually installed upside down. Flipping
    // here rather than server-side matters: slot polygons are drawn against
    // whatever this camera sends, so the image must be the right way up
    // before anybody draws on it.
    sensor->set_vflip(sensor, 1);
    sensor->set_hmirror(sensor, 1);
  }
  return true;
}

// ------------------------------------------------------------------ routes

static void handleStill() {
  if (server.hasArg("den")) {
    digitalWrite(FLASH_GPIO_NUM, HIGH);
    delay(120);  // let exposure settle before the capture
  }

  camera_fb_t *frame = esp_camera_fb_get();
  digitalWrite(FLASH_GPIO_NUM, LOW);

  if (frame == nullptr) {
    // 503, not 500: failing to produce this one frame is temporary, and the
    // server treats it as a camera that did not answer rather than a bug.
    server.send(503, "text/plain", "capture failed");
    return;
  }

  server.setContentLength(frame->len);
  server.send(200, "image/jpeg", "");
  server.sendContent(reinterpret_cast<const char *>(frame->buf), frame->len);
  esp_camera_fb_return(frame);
}

static void handleStream() {
  WiFiClient client = server.client();
  client.print(String("HTTP/1.1 200 OK\r\n") +
               "Content-Type: multipart/x-mixed-replace; boundary=" + STREAM_BOUNDARY +
               "\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n");

  while (client.connected()) {
    camera_fb_t *frame = esp_camera_fb_get();
    if (frame == nullptr) {
      // Skip this frame rather than ending the stream: a single failed
      // capture must not force the backend into a reconnect cycle.
      delay(50);
      continue;
    }

    client.print(String("--") + STREAM_BOUNDARY + "\r\nContent-Type: image/jpeg\r\n" +
                 "Content-Length: " + frame->len + "\r\n\r\n");
    client.write(frame->buf, frame->len);
    client.print("\r\n");
    esp_camera_fb_return(frame);

    // Yield so /control and /status still answer while a stream is running.
    server.handleClient();
  }
}

/** One sensor setting per call, mirroring the esp32-camera driver's own names. */
static void handleControl() {
  sensor_t *sensor = esp_camera_sensor_get();
  if (sensor == nullptr) {
    server.send(503, "text/plain", "no sensor");
    return;
  }

  const String var = server.arg("var");
  const int val = server.arg("val").toInt();
  int result = -1;

  if (var == "framesize") result = sensor->set_framesize(sensor, (framesize_t)val);
  else if (var == "quality") result = sensor->set_quality(sensor, val);
  else if (var == "brightness") result = sensor->set_brightness(sensor, val);
  else if (var == "contrast") result = sensor->set_contrast(sensor, val);
  else if (var == "saturation") result = sensor->set_saturation(sensor, val);
  else if (var == "gainceiling") result = sensor->set_gainceiling(sensor, (gainceiling_t)val);
  else if (var == "colorbar") result = sensor->set_colorbar(sensor, val);
  else if (var == "awb") result = sensor->set_whitebal(sensor, val);
  else if (var == "agc") result = sensor->set_gain_ctrl(sensor, val);
  else if (var == "aec") result = sensor->set_exposure_ctrl(sensor, val);
  else if (var == "aec_value") result = sensor->set_aec_value(sensor, val);
  else if (var == "agc_gain") result = sensor->set_agc_gain(sensor, val);
  else if (var == "hmirror") result = sensor->set_hmirror(sensor, val);
  else if (var == "vflip") result = sensor->set_vflip(sensor, val);
  else if (var == "lenc") result = sensor->set_lenc(sensor, val);
  else if (var == "wb_mode") result = sensor->set_wb_mode(sensor, val);
  else if (var == "led") { digitalWrite(FLASH_GPIO_NUM, val ? HIGH : LOW); result = 0; }
  else {
    server.send(404, "text/plain", "unknown var");
    return;
  }

  server.send(result == 0 ? 200 : 400, "application/json",
              String("{\"var\":\"") + var + "\",\"val\":" + val + ",\"ok\":" +
                  (result == 0 ? "true" : "false") + "}");
}

static void handleStatus() {
  sensor_t *s = esp_camera_sensor_get();
  String body = String("{\"code\":\"") + CAMERA_CODE + "\",\"rssi\":" + WiFi.RSSI() +
                ",\"heap\":" + ESP.getFreeHeap() + ",\"psram\":" + (psramFound() ? "true" : "false") +
                ",\"uptime_s\":" + (millis() / 1000);
  if (s != nullptr) {
    body += String(",\"framesize\":") + s->status.framesize +
            ",\"quality\":" + s->status.quality +
            ",\"brightness\":" + s->status.brightness +
            ",\"contrast\":" + s->status.contrast +
            ",\"saturation\":" + s->status.saturation +
            ",\"awb\":" + s->status.awb + ",\"agc\":" + s->status.agc +
            ",\"aec\":" + s->status.aec + ",\"vflip\":" + s->status.vflip +
            ",\"hmirror\":" + s->status.hmirror;
  }
  server.send(200, "application/json", body + "}");
}

// ------------------------------------------------------------------- setup

static void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // power save adds hundreds of ms to a polled request

  if (USE_STATIC_IP && !WiFi.config(STATIC_IP, GATEWAY, SUBNET, DNS_SERVER)) {
    // Say so and carry on: a DHCP address still works, it just moves. Silent
    // failure here would be worse - the module would look fine until the
    // address changed and every stored camera URL stopped resolving.
    Serial.println("static IP config failed; falling back to DHCP");
  }

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print('.');
  }
  Serial.printf("\nstill  : http://%s/anh\n", WiFi.localIP().toString().c_str());
  Serial.printf("stream : http://%s/stream\n", WiFi.localIP().toString().c_str());
  Serial.printf("rssi   : %d dBm\n", WiFi.RSSI());
}

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);
  pinMode(FLASH_GPIO_NUM, OUTPUT);
  digitalWrite(FLASH_GPIO_NUM, LOW);

  if (!startCamera()) {
    // Nothing this node does is useful without a camera, and a power cycle
    // fixes most init faults - better than answering 503 forever.
    delay(5000);
    ESP.restart();
  }

  connectWifi();

  server.on("/anh", HTTP_GET, handleStill);
  server.on("/stream", HTTP_GET, handleStream);
  server.on("/control", HTTP_GET, handleControl);
  server.on("/status", HTTP_GET, handleStatus);
  server.onNotFound([]() { server.send(404, "text/plain", "not found"); });
  server.begin();
}

void loop() {
  server.handleClient();

  // WiFi drops happen in a basement. Reconnect rather than requiring somebody
  // to walk down and power-cycle the module.
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("wifi lost, reconnecting");
    WiFi.disconnect();
    connectWifi();
  }
}
