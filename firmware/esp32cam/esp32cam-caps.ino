/*
 * CAPS-DASH ESP32-CAM node.
 *
 * Serves one JPEG still per request at `GET /anh`, which is exactly what
 * `Esp32CamHttpSource` on the server polls. Nothing streams: the server asks
 * for a frame every few seconds, so a permanent MJPEG stream would burn WiFi
 * airtime and camera power for frames nobody looks at.
 *
 * Board: AI-Thinker ESP32-CAM (the common OV2640 module).
 * Arduino IDE: Tools > Board > "AI Thinker ESP32-CAM", Partition "Huge APP".
 *
 * Flashing needs IO0 pulled to GND at reset (most USB-serial carrier boards
 * have a button for this); remove it before running.
 */

#include <WiFi.h>
#include <WebServer.h>
#include <esp_camera.h>
#include <esp_task_wdt.h>

// ---------------------------------------------------------------- settings

static const char *WIFI_SSID = "CHANGE_ME";
static const char *WIFI_PASSWORD = "CHANGE_ME";

// Shown in the server's camera list and in logs. Give each node a distinct
// one; it is the only way to tell two identical modules apart on the network.
static const char *CAMERA_CODE = "cam-01";

// The server treats a body under 512 bytes as a failed read, so a frame size
// that produces tiny JPEGs would look like a broken camera rather than a
// misconfiguration. SVGA is a good balance for a ceiling-mounted view.
static const framesize_t FRAME_SIZE = FRAMESIZE_SVGA;  // 800x600
static const int JPEG_QUALITY = 12;                    // 10..63, lower = better

// AI-Thinker pinout. Different carrier boards differ - check yours before
// assuming these are universal.
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
  config.frame_size = FRAME_SIZE;
  config.jpeg_quality = JPEG_QUALITY;
  config.grab_mode = CAMERA_GRAB_LATEST;

  // Two buffers in PSRAM when it exists. With one buffer the sensor and the
  // HTTP handler contend for it, which shows up as occasional torn frames -
  // and a torn JPEG is exactly what the server's decode check rejects.
  if (psramFound()) {
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
  } else {
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
    config.frame_size = FRAMESIZE_VGA;  // no PSRAM: keep the buffer affordable
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("camera init failed: 0x%x\n", err);
    return false;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  if (sensor != nullptr) {
    // Ceiling-mounted modules are usually installed upside down. Flip here
    // rather than in the server: the slot polygons are drawn against whatever
    // this camera sends, so the image must be the right way up before anyone
    // draws on it.
    sensor->set_vflip(sensor, 1);
    sensor->set_hmirror(sensor, 1);
  }
  return true;
}

// ------------------------------------------------------------------ routes

static void handleFrame() {
  camera_fb_t *frame = esp_camera_fb_get();
  if (frame == nullptr) {
    // 503, not 500: the sensor failing to produce this frame is temporary,
    // and the server's fail-streak logic treats it as a camera that did not
    // answer rather than as a bug.
    server.send(503, "text/plain", "capture failed");
    return;
  }

  server.setContentLength(frame->len);
  server.send(200, "image/jpeg", "");
  server.sendContent(reinterpret_cast<const char *>(frame->buf), frame->len);
  esp_camera_fb_return(frame);
}

static void handleStatus() {
  String body = String("{\"code\":\"") + CAMERA_CODE +
                "\",\"rssi\":" + WiFi.RSSI() +
                ",\"heap\":" + ESP.getFreeHeap() +
                ",\"uptime_s\":" + (millis() / 1000) + "}";
  server.send(200, "application/json", body);
}

// ------------------------------------------------------------------- setup

static void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // sleep adds seconds of latency to a polled request
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print('.');
  }
  Serial.printf("\nready: http://%s/anh\n", WiFi.localIP().toString().c_str());
}

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);

  if (!startCamera()) {
    // Nothing this node can do is useful without a camera. Restart rather
    // than sit answering 503 forever - a power-cycle fixes most init faults.
    delay(5000);
    ESP.restart();
  }

  connectWifi();

  server.on("/anh", HTTP_GET, handleFrame);
  server.on("/status", HTTP_GET, handleStatus);
  server.onNotFound([]() { server.send(404, "text/plain", "not found"); });
  server.begin();
}

void loop() {
  server.handleClient();

  // WiFi drops happen in a basement. Reconnect rather than requiring someone
  // to walk down and power-cycle the module.
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("wifi lost, reconnecting");
    WiFi.disconnect();
    connectWifi();
  }
}
