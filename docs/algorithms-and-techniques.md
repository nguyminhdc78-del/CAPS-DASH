# Mô tả kỹ thuật — Thuật toán & kỹ thuật trong CAPS-DASH

Tổng hợp mọi thuật toán, kỹ thuật và quyết định kỹ thuật đang chạy thật trong
mã nguồn. Mỗi mục ghi: **làm gì → thuật toán → tham số → độ phức tạp → tại sao
chọn thế**. Không mô tả tính năng chưa cài (xem `project-roadmap.md`).

Bổ trợ: `system-architecture.md` (luồng vật lý, process model),
`code-standards.md` (quy ước), `deployment-guide.md` (vận hành).

---

## 0. Bảng tổng hợp nhanh

| # | Kỹ thuật | Vị trí | Loại |
|---|----------|--------|------|
| 1 | Polling snapshot HTTP + RTSP fallback | `vision/sources/` | I/O |
| 2 | Frame Change Gate (MAD trên mặt nạ ROI) | `vision/frame_change_gate.py` | Lọc tính toán |
| 3 | Letterbox / un-letterbox | `vision/detectors/box_utils.py` | Tiền/hậu xử lý |
| 4 | YOLO ONNX decode 2 layout (classic / end-to-end) | `vision/detectors/onnx_decode.py` | Suy luận |
| 5 | NMS tham lam theo lớp | `vision/detectors/box_utils.py` | Hậu xử lý |
| 6 | Ground point + ray casting + AABB reject | `vision/domain/{geometry,assignment}.py` | Hình học |
| 7 | Bottom-band grid sampling (fallback gán ô) | `vision/domain/assignment.py` | Hình học |
| 8 | ROI-as-filter + 1 xe/ô + IoU khử trùng lặp chéo lớp | `vision/domain/slot_detections.py` | Khử nhiễu |
| 9 | Vote filter N-of-M (cửa sổ trượt) | `vision/domain/vote_filter.py` | Ổn định thời gian |
| 10 | Hoà giải gate ↔ vote (`needs_more_observations`) | `workers/camera_tick_policy.py` | Điều phối |
| 11 | Inference scheduler 1-in-flight + generation | `workers/inference_scheduler.py` | Đồng thời |
| 12 | Stagger khởi động camera | `workers/camera_start_stagger.py` | Lập lịch |
| 13 | ALPR kích hoạt theo sự kiện + crop theo polygon | `vision/plate_reader.py` | Suy luận |
| 14 | Bầu chọn biển số theo đa số (mode → conf → recency) | `services/plate_search_service.py` | Thống kê |
| 15 | Khung nhị phân tự mô tả (header + JPEG) | `realtime/frame_protocol.py` | Giao thức |
| 16 | Backpressure latest-wins hàng đợi 1 khe | `realtime/subscriber.py` | Đồng thời |
| 17 | Encode-once fan-out + cached still có tuổi | `realtime/broadcast_hub.py` | Hiệu năng |
| 18 | Auth sau khi kết nối WS (token không nằm ở URL) | `realtime/ws_auth.py` | Bảo mật |
| 19 | Ghi lịch sử chỉ khi đổi trạng thái + seeding | `workers/state_tracker.py` | Dữ liệu |
| 20 | Máy trạng thái suy ra phiên đỗ | `services/session_derivation_service.py` | Dữ liệu |
| 21 | Gộp thống kê theo giờ (timeline giây, upsert idempotent) | `services/hourly_aggregation_service.py` | Dữ liệu |
| 22 | Clock guard (bo không có RTC) | `db/clock_guard.py` | Toàn vẹn |
| 23 | SQLite online backup API | `services/backup_service.py` | Toàn vẹn |
| 24 | argon2id + dummy-hash chống dò tài khoản qua thời gian | `security/password_hasher.py` | Bảo mật |
| 25 | JWT HS256 access/refresh + `typ` + `token_version` | `security/jwt_tokens.py` | Bảo mật |
| 26 | Sliding-window rate limiter (`try_acquire` nguyên tử) | `security/rate_limiter.py` | Bảo mật |
| 27 | RBAC theo thứ hạng vai trò | `security/rbac.py` | Bảo mật |
| 28 | Hot reload qua `call_soon_threadsafe` | `workers/reload_signals.py` | Đồng thời |
| 29 | Object-URL swap có cổng preload | `features/live/frame-url-swapper.ts` | Frontend |
| 30 | Backoff mũ + jitter ±25% | `features/live/reconnect-backoff.ts` | Frontend |
| 31 | Reducer thuần + undo theo đơn vị thao tác | `features/roi-editor/roi-editor-reducer.ts` | Frontend |

---

## 1. Mô hình xử lý (process & concurrency)

**Một tiến trình, một uvicorn worker.** Không phải mặc định — là ràng buộc
đúng đắn: N worker ⇒ N vòng lặp camera trên cùng một camera, N vote filter bất
đồng ý về cùng một ô, N tiến trình ghi tranh chấp một file SQLite. Ràng buộc
được mã hoá 4 nơi: CLI, `Dockerfile CMD`, `systemd ExecStart`, và guard runtime
từ chối khởi động nếu `WEB_CONCURRENCY > 1` ở prod.

Bên trong một tiến trình, công việc được phân theo bản chất:

```
Loại công việc          Đặc tính              Chạy ở đâu
─────────────────────────────────────────────────────────────
Lấy frame               I/O mạng, chậm        event loop (async)
Decode + inference      CPU-bound, blocking   inference pool (1 thread)
Gán ô + bỏ phiếu        vài chục µs, thuần    inline trên event loop
Ghi DB                  sqlite3 blocking      db-write pool (1 thread)
REST handler            ORM đồng bộ           FastAPI threadpool
```

Bất biến: **không có gì blocking chạy trên event loop**. Một camera treo không
làm chậm camera khác; API vẫn trả lời khi inference đang bận.

**Pool inference = 1 worker** (`INFERENCE_POOL_SIZE=1`, ràng buộc bắt buộc): mô
hình ONNX không được ghi nhận là thread-safe, và bo 4 nhân không có dư CPU để
chạy 2 phiên suy luận song song — 2 worker chỉ làm cả hai chậm gấp đôi.

**Pool ghi DB = 1 thread**: tuần tự hoá mọi thao tác ghi SQLite. Không cần khoá
ứng dụng, không có `database is locked`.

---

## 2. Pipeline thị giác — tổng thể

```
JPEG (camera)
   │
   ├─ 2a. decode → BGR ndarray
   │
   ├─ 2b. FRAME CHANGE GATE ──── không đổi ──▶ BỎ QUA (0 ms inference)
   │        │ đổi / heartbeat / settling
   │        ▼
   ├─ 2c. letterbox 640×640, /255, NCHW float32
   │        ▼
   ├─ 2d. ONNX session.run  ← ~616 ms trên bo (đo thật)
   │        ▼
   ├─ 2e. decode head → lọc conf → lọc lớp xe → NMS/lớp → un-letterbox
   │        ▼
   ├─ 2f. fit slot-map vào kích thước frame (scale x, y ĐỘC LẬP)
   │        ▼
   ├─ 2g. gán detection → ô (ground point → ray cast → band fallback)
   │        ▼
   ├─ 2h. ROI-as-filter + 1 xe/ô (best-of)
   │        ▼
   ├─ 2i. VOTE FILTER N-of-M   → {UNKNOWN | FREE | OCCUPIED}
   │        ▼
   ├─ 2j. diff với trạng thái đã biết → chỉ ghi phần đổi
   │        ▼
   └─ 2k. nếu FREE→OCCUPIED: đọc biển số (crop theo ô)
```

### 2b. Frame Change Gate — bỏ suy luận khi cảnh không đổi

**Vấn đề**: xe đã đỗ thì không di chuyển. Giữa hai lượt xe vào, mọi frame là
cùng một bức ảnh; chạy YOLO trên từng frame tiêu ~616 ms/lượt để suy lại một
câu trả lời không đổi.

**Thuật toán**: MAD (mean absolute difference) trên ảnh xám hạ mẫu.

```
sample   = resize(gray(frame), 64×48, INTER_AREA).astype(int16)
diff     = mean(|sample − reference|[roi_mask])
infer    = diff ≥ threshold  OR  elapsed ≥ force_interval  OR  first_frame
```

Chi phí: **2,7 ms** ≈ 0,4 % một lần inference. Trả xong vốn ngay lần đầu nói
"bỏ qua".

Ba luật, mỗi luật vá một chế độ hỏng đã gặp thật:

1. **Chỉ nhìn bên trong các ô đỗ.** Trước đây lấy trung bình toàn khung → sai
   cả hai chiều: người đi ngang mép khung kích hoạt suy luận vô nghĩa; xe vào 1
   ô trong 20 ô bị 19 ô tĩnh pha loãng và không bao giờ vượt ngưỡng. Mặt nạ ROI
   dựng bằng `cv2.fillPoly` trên lưới 64×48 rồi **dilate 3×3** — 1 ô lưới ≈ 10
   pixel gốc, để phản ứng lúc xe *đang tới* chứ không đợi xe đỗ xong. Camera
   chưa vẽ ô ⇒ mặt nạ `None` ⇒ so cả khung (nếu không, "không chỗ nào quan
   trọng" sẽ thành "không bao giờ suy luận").
2. **So với frame ĐÃ SUY LUẬN gần nhất, không phải frame trước.** Xe vào chậm
   qua 10 frame, mỗi frame đổi rất ít; đo frame-với-frame thì không bao giờ
   vượt ngưỡng. Đo với mốc suy luận cuối thì sai khác tích luỹ đến khi vượt.
3. **Heartbeat**: dù gì cũng suy luận mỗi `motion_force_interval_s` (mặc định
   30 s). Trôi chậm (hoàng hôn, bật đèn, auto-exposure của cảm biến) có thể đẩy
   cả bức ảnh dịch dần dưới ngưỡng. Heartbeat chặn trên thời gian hệ thống được
   phép sai.

Chi tiết cài đặt đáng lưu: hạ mẫu về **`int16`, không phải `uint8`** — hiệu của
hai mảng uint8 bị wrap, |20−30| ra 246, và một khung tối dần sẽ đọc thành thay
đổi khổng lồ.

Ngưỡng mặc định `motion_change_threshold = 8.0`, đặt trên sàn nhiễu đo được
(~0,5 MAD, xấu nhất 1,2 trên cảnh rất tối) với biên rộng.

### 2c–2e. Suy luận YOLO

**Letterbox** (`box_utils.letterbox`): resize giữ tỉ lệ vào ô vuông 640×640,
đệm màu xám YOLO `(114,114,114)`, trả về `(ảnh, scale, (pad_left, pad_top))`.
Ở đây **một hệ số scale chung là đúng** (hai trục của cùng một ảnh co cùng
nhau) — khác hẳn trường hợp scale polygon ở §2f.

**Un-letterbox**: trừ pad *trước*, chia scale *sau* (ngược thứ tự letterbox),
rồi `clip` về biên khung gốc.

**Decode 2 layout head** — chỗ dễ sai nhất của pipeline:

| Layout | Shape | Nội dung | Xử lý |
|--------|-------|----------|-------|
| Classic (YOLOv8/11) | `[1, 4+C, N]` hoặc `[1, N, 4+C]` | `cxcywh` + điểm từng lớp, **chưa NMS** | argmax lớp → lọc conf → lọc lớp xe → cxcywh→xyxy → NMS/lớp |
| End-to-end (YOLO26) | `[1, 300, 6]` | `x1,y1,x2,y2,score,class_id`, **đã NMS trong graph** | chỉ lọc conf + lớp |

Phân biệt bằng **kiểm tra tường minh số cột = 6**, không đoán. Nếu đưa output
end-to-end vào nhánh classic: không có exception nào được ném, hệ thống chỉ đơn
giản đọc `class_id = 59` thành `confidence = 59.0` và bãi xe ngừng thấy xe.
Heuristic "trục ngắn hơn là kênh" cũng được chặn trước bởi kiểm tra này, vì một
output `(3, 6)` trên khung vắng sẽ bị transpose thành 6 detection giả.

**Lọc lớp**: mô hình là COCO 80 lớp gốc, chỉ giữ `{2: car, 3: motorcycle,
5: bus, 7: truck}` — lọc lúc decode thay vì huấn luyện lại.

**NMS tham lam thuần numpy**, chạy **riêng từng lớp** (`_nms_per_class`), IoU
ngưỡng 0,45. Vector hoá: mỗi vòng lặp tính IoU của hộp điểm cao nhất với toàn
bộ phần còn lại một lần bằng numpy → O(k·n) thực tế thay vì O(n²) Python thuần.
Trước NMS chặn `MAX_CANDIDATES_BEFORE_NMS = 100` (NMS là O(n²) trên lý thuyết;
một khung đầy dương tính giả không được phép làm nghẽn bo aarch64).

### 2f. Khớp slot-map vào khung — hai hệ số scale ĐỘC LẬP

Slot map được vẽ trên một ảnh tĩnh kích thước A, đem so với frame trực tiếp
kích thước B, và hai tỉ lệ khung hình hiếm khi trùng (vẽ trên 16:9, frame về
10:7). `scale_polygon` nhân `x` và `y` bằng **hai hệ số riêng**.

Gộp thành một hệ số chung là thảm hoạ im lặng: mọi ô báo FREE vĩnh viễn, không
exception nào được ném, hệ thống trông khoẻ mạnh trong khi sai toàn bộ. Có test
hồi quy ghim hành vi này.

### 2g. Gán detection → ô đỗ

Không có AI ở tầng này. Detector chỉ nói "có xe tại toạ độ này"; biến thành "ô
A2 có xe" là hình học thuần — và tách bạch như vậy là điều cho phép đổi mô
hình, hoặc lắp ở toà nhà mới, mà không cần huấn luyện lại gì.

**Bước 1 — ground point.** Điểm đại diện một xe là **trung điểm cạnh ĐÁY** của
bbox: `((x1+x2)/2, y2)` — nơi bánh chạm sàn. Cố ý *không* dùng tâm bbox:
camera gắn trần nhìn xiên xuống, tâm hộp của xe cao rơi vào ô **phía sau** nó.
Mô phỏng trên dự án tham chiếu cho tỉ lệ gán đúng **0 %** với một số hình học
camera khi dùng tâm.

**Bước 2 — point-in-polygon bằng ray casting.** Bắn tia ngang, đếm số cạnh cắt;
lẻ ⇒ bên trong. Hoạt động với polygon lõm (ô vẽ tay thường lõm). Trước ray
casting có **AABB reject** (`_within` trên bounding box đã tiền tính của ô), nên
ray casting O(V) chỉ chạy cho ô sống sót.

Nhiều ô cùng chứa điểm ⇒ chọn ô có **diện tích nhỏ nhất** (công thức shoelace,
`polygon_area`), vì ô nhỏ hơn là ô cụ thể hơn.

**Bước 3 — fallback lấy mẫu dải đáy.** Nếu ground point không rơi vào ô nào
(polygon vẽ hụt vài pixel), lấy lưới **5×5 = 25 điểm** trên **30 % dải đáy** của
bbox, đếm tỉ lệ điểm nằm trong từng ô, chọn ô có phủ cao nhất **nếu ≥
`MIN_BAND_COVERAGE = 0,40`**.

Chỉ dải đáy, không bao giờ cả hộp: phần trên là nóc và thân xe, nhô sang hàng
phía sau dưới góc nhìn xiên — lấy mẫu cả hộp sẽ giao xe cho ô sau lưng nó, đúng
lỗi mà ground point sinh ra để tránh.

Ngưỡng 0,40 dung thứ ô vẽ hụt ~20 % chiều cao xe, nhưng vẫn từ chối xe chỉ chạm
mép. 0,60 khiến gần như không ô nào đạt; 0,20 bắt đầu cướp xe của ô bên cạnh.

Độ phức tạp: O(D · S) với D = số detection (≤ vài chục), S = số ô mỗi camera —
đơn vị micro giây, chạy inline trên event loop.

### 2h. Rút gọn về một xe mỗi ô

Hai luật, cả hai tồn tại vì mô hình COCO gốc chĩa vào bãi xe là một dụng cụ ồn:

1. **ROI là bộ lọc.** Hộp không thuộc ô nào bị vứt. Trên giàn tham chiếu, một
   con chuột máy tính trên bàn phía sau các ô được chấm là "xe" ở hầu hết frame.
2. **Một ô một xe.** Hộp thừa trong cùng ô là chính chiếc xe đó được mô tả lại —
   ở lớp khác hoặc thang khác — nên ô giữ hộp điểm cao nhất, phần còn lại bỏ.
   Tie-break bằng **diện tích lớn hơn**: camera chạy sát sàn confidence (chỗ mà
   mô hình gốc buộc phải đứng để nhìn thấy xe) tạo ra hoà điểm thường xuyên, và
   thiếu khoá thứ hai thì hộp thắng đảo qua lại giữa hai frame liên tiếp, làm
   overlay giật trong khi không có gì trong ô nhúc nhích.

Hai luật này **không** đổi được ô nào đang bị chiếm (5 hộp hay 1 hộp đều là
occupied); chúng đổi lượng nhiễu mà mọi tầng phía sau phải gánh — nên chúng
chạy **trước** vote filter, overlay và bộ đọc biển, thay vì lặp lại ở từng nơi.

**Chẩn đoán lúc lắp đặt** (`count_detections_per_slot`): đếm số xe **khác nhau**
trong một ô bằng khử trùng lặp tham lam theo IoU (`SAME_VEHICLE_IOU = 0,50`),
chạy **chéo lớp** — đúng trường hợp mà NMS theo-lớp của detector không thấy
được (một xe trả về vừa là `car` vừa là `truck`). ≥ 2 xe trong một ô ⇒ cảnh báo
"polygon vẽ chồng sang hàng sau", bắt lỗi khi thợ còn đang đứng trên thang.
Trước khi sửa sang đếm-xe-khác-nhau, cảnh báo này bắn 25 lần trong 45 phút trên
giàn có 3 xe và trở thành nhiễu — chế độ hỏng tệ nhất với một công cụ chẩn đoán.

### 2i. Vote filter N-of-M — ổn định hoá theo thời gian

**Vấn đề**: phán xét từng frame độc lập làm trạng thái nhấp nháy. Ai đó đi
ngang giữa camera và xe nửa giây, ô đọc thành FREE, dashboard mời chỗ, tài xế
đi hết bãi và thấy chỗ đã có xe. Niềm tin mất và không quay lại.

**Thuật toán**: mỗi ô giữ một `deque(maxlen=window)` các phiếu boolean.

```
window = 5, threshold = 4   (mặc định; override theo từng camera trong DB)

len(votes) < window            → giữ nguyên state  (chưa đủ mẫu, UNKNOWN)
occupied_votes ≥ threshold     → OCCUPIED
free_votes     ≥ threshold     → FREE
không bên nào đạt ngưỡng       → GIỮ trạng thái cũ   ← nhánh hấp thụ che khuất
```

Chi phí O(1) mỗi ô mỗi frame, bộ nhớ 5 bit/ô.

**UNKNOWN là một câu trả lời thật, không phải chỗ trống cho FREE.** Trước khi
lấp đầy cửa sổ, hệ thống chưa xác lập được trong ô có gì; nói "trống" là gửi
tài xế tới một chỗ chưa ai thực sự nhìn. Quy tắc bất di bất dịch: **không bao
giờ cộng UNKNOWN vào FREE**; UI luôn hiện 3 số riêng.

`build_filter()` là cách duy nhất được phép tạo filter, để "luôn dựng filter
mới sau khi sửa slot map" là một lời gọi duy nhất tại chỗ dùng — dùng lại filter
qua một lần sửa sẽ cho ô mới vẽ thừa kế phiếu của ô trùng id, sai và hoàn toàn
im lặng.

Cấu hình mặc định 3,0 s × 4 phiếu ≈ **12 giây** để một ô chốt trạng thái. Ghi
chú cấu hình của dự án tham chiếu cho thấy 1,0 s × 3 phiếu nhấp nháy liên tục,
vì confidence của detector dao động quanh ngưỡng chấp nhận.

### 2j. Hoà giải: change gate ↔ vote filter

Hai cơ chế trên muốn hai điều trái ngược. Gate bỏ qua vì "kết quả trước vẫn mô
tả đúng frame này". Filter chỉ đổi ý sau khi `threshold` trong `window` quan
sát đồng thuận. Nên đúng hai dịp filter có việc phải làm, gate lại sai chính xác:

- **Khởi động (warm-up)**: ô đang UNKNOWN không có "kết quả trước", nên giấy
  phép của gate không áp dụng. Đo thật: **2 phút UNKNOWN** sau mỗi lần khởi
  động lại hoặc vẽ lại ROI, vì bãi xe tĩnh không đổi gì và chỉ heartbeat nuôi
  filter — 1 quan sát mỗi 30 s.
- **Xe vào/ra**: tệ hơn, vì trông giống câu trả lời sai chứ không phải câu trả
  lời thiếu. Lấy xe ra làm cảnh đổi **một lần**: gate bắn, 1 phiếu FREE rơi
  xuống, rồi cảnh tĩnh trở lại nên gate bỏ qua — ô tiếp tục báo OCCUPIED cho
  đến khi 4 heartbeat trôi qua. Phản hồi từ hiện trường: *"Tôi lấy xe ra, đợi
  gần một phút, vẫn báo có xe."*

Cả hai là **cùng một điều kiện**: quan sát mới nhất mâu thuẫn với trạng thái
đang báo. `needs_more_observations()` phát hiện điều đó và ép suy luận với lý
do `settling`, tốn thêm vài lần inference, **một lần**, đúng lúc câu trả lời
đang bị nghi ngờ. `_disagreeing_slots()` tính mâu thuẫn đó sau mỗi kết quả và
đặt cờ `votes_settled`.

Chốt chặn: camera **chưa vẽ ô nào ⇒ trả `False`**. Trả `True` ở đó từng là lỗi
thật: một camera thứ hai chưa cấu hình chạy inference trên **mọi tick vĩnh
viễn**, bão hoà worker inference dùng chung (2 × 1,5 s công việc trên mỗi tick
3 s) và bỏ đói camera đã cấu hình — đo được 11 lần suy luận/phút trên camera
rỗng, 0 trên camera thật.

**Sàn tốc độ** (`too_soon_to_infer`): chỉ chặn suy luận do `changed`.
`first_frame` không có kết quả trước để phát thay, `heartbeat` chính là chặn
trên thời gian được phép sai — chặn cả hai là đổi một giới hạn đã biết lấy một
giới hạn vô hạn. Khi bị chặn, mốc tham chiếu của gate **cố ý không** cập nhật,
để gate tiếp tục nói "changed" và bắn ngay khi sàn hết hiệu lực.

---

## 3. Đồng thời & lập lịch

### 3.1. Inference scheduler — tách suy luận khỏi đường tới hạn của tick

Trước đây phát frame *sau* lệnh `await` inference, nên mọi frame người xem nhận
đã già thêm trọn một lần suy luận (~616 ms, và N × 616 ms khi N camera xếp hàng
sau worker dùng chung). Chỗ nghẽn đó rơi đúng nơi dễ thấy nhất: cảnh không đổi
thì bỏ qua suy luận nên hình mượt lúc chẳng có gì xảy ra, và giật đúng lúc xe
di chuyển — thời điểm duy nhất có người đang nhìn.

Nay một tick **phát frame rồi khởi động** một lần suy luận và đi tiếp, không
bao giờ đợi. Hai luật giữ điều đó trung thực:

- **Tối đa một suy luận đang bay mỗi camera.** Pool có một worker dùng chung
  nên khởi động cái thứ hai không làm nó xong sớm hơn; chỉ xếp hàng một kết quả
  mô tả frame đã trôi qua và làm chậm kết quả còn quan trọng. Tick thấy detector
  bận thì phát frame và đi tiếp. (Kiểm tra `busy` đặt **trước** change gate —
  detector đang chạy thì câu trả lời không dùng được, so sánh 2,7 ms để quyết
  định một việc không làm là lãng phí.)
- **Reload huỷ kết quả đang chạy.** Bộ đếm `generation` tăng khi reload; kết
  quả về với generation cũ bị bỏ. Chấm điểm kết quả tính trên slot map cũ vào
  map mới sẽ gán detection cho các polygon đã bị vẽ lại — im lặng, và không cách
  nào phát hiện về sau.

`drain()` lúc shutdown **await** thay vì cancel: cancel task không dừng được
thread pool đang chạy mô hình, nên đằng nào cũng phải đợi — đợi ở đây, nơi nhìn
thấy được, thay vì đợi trong executor shutdown. Chặn trên: một lần inference.

### 3.2. Stagger khởi động camera

Mỗi tick tự đo từ điểm bắt đầu của chính nó, nên N camera sinh cùng một
mili-giây sẽ bắn cùng một mili-giây mãi mãi — rồi ném N lần suy luận vào pool
một worker cùng lúc, và cái cuối đợi (N−1) × 616 ms.

```
offset(camera_i) = index_i × poll_interval_s(camera_i) / fleet_size
```

Chia cho **toàn đội hình** (kể cả camera đang chạy), không chia cho số camera
đang khởi động: 2 camera thêm vào đội 3 camera phải giãn 1/3 chu kỳ, không phải
1/2. Đội 1 camera ⇒ 0,0, hành xử y như trước khi có staggering. Giãn cách theo
chu kỳ **riêng của từng camera** vì `poll_interval_s` là per-camera.

Hàm số học thuần trên tập id ⇒ test được không cần event loop.

### 3.3. Hot reload không khởi động lại tiến trình

REST handler là hàm `def` đồng bộ chạy trong threadpool của FastAPI; vòng lặp
camera là task asyncio trên event loop. `asyncio.Event.set()` **không**
thread-safe — handler gọi thẳng là một race chạy tốt khi test và thỉnh thoảng
hỏng ở production. Mọi tín hiệu reload đi qua **`loop.call_soon_threadsafe`**.

Khi tick nhận tín hiệu: dựng lại context (slot map mới + vote filter **mới
tinh**), `scheduler.invalidate()`, `change_gate.reset()` (mốc tham chiếu cũ mô
tả một bố cục không còn áp dụng), và xoá kết quả đã phát.

---

## 4. ALPR — đọc biển số

**Vì sao đủ rẻ để chạy**, gói trong một phép đo: dò + đọc biển trên toàn khung
640×480 tốn **2642 ms** trên bo, so với 1477 ms mà detector xe đã tiêu mỗi
tick. Chạy mỗi tick là bất khả thi. **Nó không chạy mỗi tick**: biển số chỉ cần
tại đúng khoảnh khắc một ô chuyển sang OCCUPIED — điều mà vote filter đã công
bố — nên chi phí ở trạng thái ổn định là **0**.

Kích hoạt theo sự kiện còn trả lời thứ hai: khi ô chuyển trạng thái thì polygon
của nó đã biết, nên khung được **crop về đúng ô** trước, biển số chiếm phần lớn
hơn hẳn của đầu vào — đó là điều cho phép mô hình 384-pixel rẻ hơn làm được việc.

| Tham số | Giá trị | Lý do |
|---------|---------|-------|
| `DETECTOR_MODEL` | `yolo-v9-t-384-license-plate-end2end` | 1067 ms; chạy trên crop nên đủ |
| `OCR_MODEL` | `cct-s-v1-global-model` | biển chỉ có chữ Latin + số |
| `CROP_MARGIN` | 0,25 | biển nằm ở mũi/đuôi xe, thường ngoài ô vẽ |
| `MIN_PLATE_WIDTH_PX` | 60 | đo thật: đọc tốt từ 60 px, hỏng ở 40 px |

Mô hình lưu **thread-local** (`threading.local`), cùng lý do với detector xe:
đối tượng mô hình không được ghi nhận thread-safe, và bản dùng chung hỏng im
lặng chứ không hỏng ồn ào. Với pool 1 worker ⇒ đúng một bản trong bộ nhớ.

`import fast_alpr` đặt **trong hàm**, không ở module scope: mô hình biển số là
năng lực tuỳ chọn, một triển khai không có nó vẫn phải khởi động và đếm xe được.
Mọi lỗi đọc biển bị nuốt thành `None` + log warning — đếm chỗ là sản phẩm, biển
số là phần thêm.

Nhiều biển trong một crop ⇒ **biển rộng nhất thắng** (xe bên cạnh lấn vào lề
margin thì biển gần hơn là biển to hơn).

`looks_like_plate()` cố ý **không** là bộ kiểm định format: 6–10 ký tự và có ít
nhất một chữ số. Từ chối một biển thật vì không khớp regex ai đó viết theo trí
nhớ còn tệ hơn lưu một biển trông lạ mà bảo vệ nhìn là biết sai.

---

## 5. Tìm xe theo biển số — bầu chọn theo đa số

Câu hỏi cần trả lời là câu hỏi của bảo vệ: cư dân quên đỗ ở đâu. Nên câu trả
lời là **một Ô**, không phải danh sách lần nhìn thấy — điều đó định hình truy
vấn nhiều hơn tưởng.

**Một ô một xe ⇒ một ô một biển. Quyết bằng ĐỒNG THUẬN, không bằng độ mới.**
Lấy bản đọc mới nhất trông có vẻ đúng nhưng không: đo trên bo, ô A1 được đọc là
`98A83355` chín lần liên tiếp ở 0,61–0,91 confidence, rồi một lần `88C27999` ở
0,54 — và bản đọc sai đơn lẻ đó trở thành câu trả lời của ô, nên tìm biển thật
không ra gì. Lỗi OCR ngẫu nhiên riêng lẻ, hiếm khi trùng nhau.

```
ứng viên = readings trong 12 h, ô còn OCCUPIED, ô active
        → thu hẹp về readings kể từ slot.state_since   (xe hiện tại)
        → lọc confidence ≥ 0.60                        (nếu lọc sạch thì bỏ lọc)
best_plate = argmax( count, max(confidence), max(read_at) )   ← 3 tie-break
```

Ba luật phái sinh:

1. **Bản đọc detector không chắc không phải bằng chứng**: dưới 0,60 bị loại
   trước khi bầu. Đo trên bo: 55/59 bản đọc ở ≥ 0,6, và **cả hai** lần đọc sai
   quan sát được (0,54 và 0,45) nằm dưới ngưỡng. Nhưng ngưỡng **không chặn câu
   trả lời**: ô chỉ từng được đọc ở 0,31 vẫn báo biển đó kèm confidence, vì với
   bảo vệ một bản đọc kém là manh mối để kiểm tra, còn hơn không có gì.
2. **Ô chỉ được tính khi còn OCCUPIED.** Bản đọc từ ô nay đã FREE mô tả chiếc
   xe đã đi. Chỉ bảo vệ tới đó còn tệ hơn im lặng, vì họ sẽ tin và đi thật.
3. **Fallback 12 giờ**: khởi động lại làm `state_since` reset về thời điểm boot
   nên không bản đọc nào mới hơn nó. Không có fallback thì tìm kiếm trắng sau
   mỗi lần deploy.

Chuẩn hoá truy vấn: `30H-832.31` và `30h 832 31` là cùng một tìm kiếm — bỏ mọi
ký tự không alphanumeric, viết hoa. Query < 3 ký tự bị từ chối (gần như mọi biển
đều khớp ⇒ hết là tìm kiếm), trả lỗi có lý do thay vì cắt ngắn im lặng. Trần 50
kết quả.

Rút gọn chạy trong Python chứ không trong SQL vì "nhiều nhất → chắc nhất → mới
nhất" là ba tầng tie-break và đọc như nhiễu trong một window function; tập dòng
đã bị chặn hai lần (sàn confidence + cửa sổ 12 h) nên vẫn nhỏ.

---

## 6. Realtime — giao thức và backpressure

### 6.1. Khung nhị phân tự mô tả

```
[4 byte big-endian uint32 = N][N byte JSON UTF-8][JPEG bytes]
```

Một message mang **cả frame lẫn trạng thái mô tả nó** — đó là toàn bộ mục đích.
Hai message riêng vẫn tới đúng thứ tự, nhưng một lần rớt do backpressure có thể
bỏ cái này giữ cái kia, để lại các polygon vẽ chồng lên một frame chúng không mô
tả. Một message thì không thể lệch pha.

Base64 bị loại: hơn 1/3 số byte và một bước decode mỗi frame, đổi lại không gì.
`MAX_HEADER_BYTES = 64 KB` — header vài trăm byte; lớn hơn là bug hoặc thù địch,
phải từ chối **trước khi** cấp phát cho nó.

### 6.2. Fan-out: encode một lần

JPEG phát đi là **byte nguyên bản camera gửi**; server không bao giờ vẽ lên
frame và không bao giờ encode lại, vì overlay được vẽ ở client từ JSON header.
Fan-out vì thế là một bản sao tham chiếu mỗi subscriber, bất kể kích thước frame.

`publish()` **đồng bộ và không blocking**: vòng lặp camera gọi nó trên đường
nóng và không được đợi socket. Tập subscriber được snapshot (`tuple(...)`) trước
khi duyệt, vì một người xem ngắt kết nối trên event loop giữa chừng sẽ mutate
tập đang đi.

**Cached still có dấu thời gian**: client vừa kết nối thấy hình ngay thay vì
nhìn ô trống tới 3 giây (đọc như trang hỏng). Có dấu thời gian vì camera loop
chỉ publish khi có người xem — không kiểm tra tuổi thì frame cuối trước khi mọi
người rời đi sẽ được phục vụ nhiều giờ sau như thể đang trực tiếp, tệ hơn không
hiện gì.

### 6.3. Backpressure — hàng đợi 1 khe, latest-wins

Luật: **publish không bao giờ await một socket.** Fan-out ngây thơ
(`for client in clients: await client.send_bytes(...)`) khiến mọi người xem chờ
người chậm nhất, và đặt cái chờ đó lên đường nóng của camera loop.

Mỗi người xem sở hữu `asyncio.Queue(maxsize=1)` và một task riêng rút hàng đợi
vào socket. `offer()` không bao giờ block/await/raise: hàng đầy ⇒ vứt frame cũ
chưa lấy, thay bằng frame mới, `dropped += 1`.

Hàng đợi giữ **đúng một** message có chủ đích: người đang xem camera muốn
*bây giờ*; một backlog frame cũ còn tệ hơn vô dụng, vì người xem sẽ tụt lại xa
hơn sau mỗi tick và không bao giờ đuổi kịp.

Giới hạn: 4 người xem/camera, 16 tổng.

### 6.4. Xác thực WebSocket sau khi kết nối

**Token không bao giờ nằm trong URL.** `?token=` rơi vào access log của uvicorn,
vào log mọi proxy giữa trình duyệt và bo, và vào lịch sử trình duyệt — ba nơi
một bearer credential không được xuất hiện. Trình duyệt cũng không đặt được
header trên handshake WebSocket. Nên: accept → chờ message `{"type":"auth",
"token":...}` **có deadline** → kiểm tra → chỉ khi đó mới gửi gì đi.

RBAC tại đây dùng `assert_role()` — hàm thuần, không phải FastAPI dependency, để
tầng WS áp **đúng cùng một luật** với REST.

Heartbeat ping/pong `ws_heartbeat_s = 20` phát hiện socket chết mà TCP chưa báo.
Close code phân loại (`close_codes.py`) để client biết cái nào nên thử lại.

### 6.5. Phía client

- **Bộ đếm generation**: `close()` là bất đồng bộ, nên socket đã đóng lúc cleanup
  vẫn có thể giao một `onmessage`/`onclose` muộn. Mọi handler so generation đã
  chụp với generation hiện tại và bỏ callback cũ. Đây cũng là thứ làm cho vũ
  điệu mount → cleanup → mount của React 19 StrictMode an toàn.
- **Object-URL swap có cổng preload**: tạo objectURL mới mỗi frame, nhưng chỉ
  revoke URL **trước đó** sau khi trình duyệt đã load xong bản thay thế (dùng
  một `Image()` bỏ đi làm cổng). Revoke sớm hơn có nguy cơ nháy trắng, vì vài
  engine re-resolve `src` của `<img>` còn hiển thị khi repaint. Decode chạy đồng
  thời và có thể xong sai thứ tự ⇒ có bộ đếm `issued`/`shown` để frame cũ không
  giành lại màn hình. `onJpegUrl` và `onFrame` bắn từ **cùng một swap**, nên
  overlay và ảnh nó vẽ lên không bao giờ lệch nhau một frame.
- **Backoff mũ + jitter**: 1 s → 8 s, jitter ±25 %. Jitter không phải trang trí:
  thiếu nó, mọi người xem bị ngắt bởi cùng một lần restart server sẽ kết nối lại
  đúng cùng thời điểm — biến "bo đã trở lại" thành một thundering herd nhắm vào
  chính cái bo vừa trở lại. `attempt` reset khi **decode được một frame thật**,
  không phải khi socket mở (socket mở rồi bị policy-close ngay không phải thành
  công).
- **Tạm dừng theo `visibilitychange`**: tab ẩn ⇒ đóng socket, giải phóng một
  slot người xem; cờ `pausedForVisibility` riêng để resume không vô tình huỷ một
  lần đóng dứt khoát (ví dụ `forbidden`).

---

## 7. Dữ liệu, thời gian, thống kê

### 7.1. Chỉ ghi lịch sử khi trạng thái đổi

Ghi mọi lần quét cho bãi 100 ô ở 1 s/lần là **8,6 triệu dòng/ngày** — đầy đĩa và
mòn flash mà bo boot từ đó, trong khi không thêm thông tin nào mà các dòng
"đổi trạng thái" chưa mang.

`StateTracker.diff()` trả về đúng các ô khác lần trước. UNKNOWN **không bao giờ
vào lịch sử**: filter chỉ trả UNKNOWN trước khi đủ cửa sổ, nên "trở thành
unknown" luôn nghĩa là "tiến trình vừa khởi động", không bao giờ là "có gì đó
xảy ra trong bãi".

**Seeding** (`seed()`): nạp trạng thái đã lưu trong DB trước khi chạy. Thiếu nó,
mỗi lần khởi động lại ghi một dòng ma `UNKNOWN → FREE` cho **mỗi ô**. Khởi động
lại tiến trình không phải một sự kiện đỗ xe. Có seeding, warm-up trùng trạng
thái DB thì không sinh gì, còn xe vào/ra lúc tiến trình chết vẫn sinh **đúng
một** dòng — đúng thay đổi đã thực sự xảy ra.

### 7.2. Suy ra phiên đỗ — máy trạng thái, không có bảng riêng

Cố ý **không có bảng `parking_session`**: một phiên là hai dòng liên tiếp
OCCUPIED rồi FREE của cùng một ô. `derive_sessions()` là hàm thuần đi qua các
dòng đã sắp thứ tự.

```
* → OCCUPIED (chưa mở)      : MỞ phiên
OCCUPIED → FREE             : ĐÓNG phiên
OCCUPIED → UNKNOWN          : KHÔNG đóng, đánh dấu had_gap=True
OCCUPIED → OCCUPIED (đã mở) : bỏ qua (restart quan sát lại cùng trạng thái)
FREE/UNKNOWN khi chưa mở    : bỏ qua (dòng mở nằm trước cửa sổ truy vấn)
còn mở khi hết dòng         : ongoing=True, ended_at=None
```

Camera offline giữa phiên **không phải** "xe đã đi" — nhưng phải nhìn thấy được,
nên `had_gap` đánh dấu phiên có thời lượng bắc qua một khoảng không quan sát.

`itertools.groupby` chỉ gom các đoạn **liền kề**, nên thứ tự
`(slot_id, changed_at, id)` là điều kiện tiên quyết — sai thứ tự sẽ im lặng sinh
ra một "phiên" vỡ cho mỗi ô. Cửa sổ thời gian bắt buộc và có trần (dùng chung
`history_service.resolve_range` với `/history`) vì hàm này đọc **mọi** dòng
trong cửa sổ.

### 7.3. Gộp thống kê theo giờ

Tính lại báo cáo từ lịch sử thô trên CPU của bo quá chậm để dùng được; job này
cuộn một lần cho mỗi giờ đã đóng, và báo cáo đọc từ `hourly_stats`.

- **Chỉ giờ đã đóng**: giờ đang chạy không bao giờ được gộp, vì
  `unknown/free/occupied_seconds` của nó còn đang tăng.
- **Timeline theo giây**: seed trạng thái ngay trước mốc giờ + các sự kiện trong
  giờ → tích luỹ số giây ở mỗi trạng thái cho từng ô.
- **Ba scope**: SLOT → FLOOR → SITE. Dòng SITE ghi **cuối cùng** và đóng vai
  con dấu hoàn thành (`latest_aggregated_hour`).
- **Upsert idempotent** ⇒ `rebuild-stats` chạy lại an toàn bất cứ lúc nào (ví dụ
  sau khi sửa bug trong chính module này).
- **Trần `MAX_HOURS_PER_RUN = 24`**: không có trần thì một lần deploy mới hoặc
  một sự cố nhiều ngày biến lần chạy **đầu tiên** thành một transaction dài
  tranh CPU với inference; các tick sau dọn nốt hàng tồn.
- Giờ mà **mọi** sự kiện đều `clock_suspect` ⇒ **bỏ qua**, không gộp rác vào một
  dòng vĩnh viễn.
- `hourly_stats` **không bao giờ** bị purge: nó tồn tại chính để xu hướng dài
  hạn sống sót sau khi `slot_state_history` bị xoá theo `retention_months`.

### 7.4. Thời gian & toàn vẹn

**Clock guard** — phần cứng đích không có RTC nuôi pin. Sau mất điện, bo boot
tin rằng đang ở một ngày trong quá khứ, và mọi dòng ghi trước khi NTP đuổi kịp
mang timestamp sai. Thay vì đếm sai im lặng, các dòng đó được **gắn cờ**
`clock_suspect`: `now < 2026-01-01` hoặc `now > 2031-01-01` ⇒ nghi ngờ. Báo cáo
có thể loại chúng ra **và nói rõ**, điều đó trung thực; lặng lẽ trộn vào trung
bình thì không.

**`UtcDateTime`** — SQLite không có kiểu timestamp và trả về datetime naive.
Input naive bị **từ chối** chứ không được ngầm hiểu là UTC: đoán ở đây là cách
một hệ thống kết thúc với hỗn hợp dòng local và UTC mà về sau không ai gỡ được.
`utc_now()` là lời gọi đồng hồ duy nhất được phép.

**Backup bằng SQLite online backup API** — copy file khi WAL đang hoạt động có
thể chộp một lần ghi dở giữa transaction và phục hồi thành dữ liệu hỏng (nghi
là bug của dự án tham chiếu). `sqlite3.Connection.backup()` copy theo trang dưới
bảo đảm nhất quán của chính SQLite, database vẫn sống, writer không bị chặn. Tên
file có **micro giây** — hai lần backup cách nhau tích tắc (click lặp, vòng test
nhanh) sẽ trùng tên ở độ phân giải giây và ghi đè im lặng.

### 7.5. Job nền (5 job)

| Job | Chu kỳ | Kỹ thuật |
|-----|--------|----------|
| Gộp theo giờ | 1 h | §7.3 |
| Cảnh báo quá hạn đỗ | 5 phút | so `state_since` với `OVERSTAY_HOURS`; **khử trùng** qua `create_deduplicated` — ô kẹt một tuần sinh 1 cảnh báo, không phải 1 mỗi tick |
| Cảnh báo hết đĩa | 5 phút | `DISK_LOW_PERCENT` |
| Purge theo retention | 24 h | xoá `slot_state_history` + alerts quá `RETENTION_MONTHS`; có dry-run; luôn audit |
| Quét rate-limiter + session | 10 phút | `sweep_idle()` bỏ key hết hạn; xoá `refresh_sessions` hết hạn |

---

## 8. Bảo mật

**Băm mật khẩu: argon2id** (argon2-cffi trực tiếp, không qua passlib — passlib
không còn được bảo trì và backend bcrypt của nó vỡ với bcrypt 4.x). argon2id cố
ý chậm và tốn bộ nhớ: crack offline một database bị đánh cắp tốn hàng năm thay
vì hàng giờ. **Hash nhanh ở đây là bug, không phải tối ưu.**

**Chống dò tài khoản qua thời gian**: username không tồn tại vẫn được verify
với `DUMMY_HASH`, nên một lần đăng nhập tốn CPU như nhau ở cả hai đường. Thiếu
nó, "không có user này" trả về **đo được** nhanh hơn "sai mật khẩu".

`needs_rehash()` cho phép nâng tham số chi phí về sau mà không khoá ai ra ngoài:
lần đăng nhập thành công kế tiếp âm thầm nâng cấp hash đã lưu.

**JWT HS256** (đối xứng đúng ở đây: một tiến trình vừa phát vừa xác minh, không
có bên thứ hai cần public key).

- `typ` là claim **bắt buộc** và `expected_type` **không** tuỳ chọn. Chấp nhận
  cả hai loại sẽ cho phép replay một refresh token sống lâu như bearer
  credential — lỗi token-confusion kinh điển.
- `tv` (`token_version`) cho phép **thu hồi tức thì** toàn bộ token của một user
  (đổi mật khẩu, khoá tài khoản) mà không cần blacklist.
- Refresh token lưu `jti`, đối chiếu với bảng `refresh_sessions` ⇒ thu hồi từng
  phiên. Refresh đi qua **HttpOnly cookie**, access token giữ trong bộ nhớ JS.
- Client có **single-flight refresh** (`refresh-single-flight.ts`): N request
  401 đồng thời chỉ tạo một lần refresh.

**Rate limiter cửa sổ trượt** — `deque` timestamp mỗi key, prune theo cutoff.
In-process là đúng chứ không phải đi tắt: app chạy đúng một worker theo thiết
kế, nên không có tiến trình thứ hai cần chia sẻ bộ đếm; thêm Redis vào một máy
trong phòng bảo vệ là thêm một dịch vụ phải cài, giám sát và khởi động lại.

`try_acquire()` gộp check+record trong **một** lần giữ khoá. Tách hai bước thì N
thread có thể cùng qua check trước khi thread nào kịp record — vượt hạn mức khi
có burst, và trên tìm kiếm biển số công khai điều đó bào mòn cái chặn duy nhất
giữa một người gọi ẩn danh và cơ sở dữ liệu biển số. (Đăng nhập vẫn giữ
check/record/reset tách rời, vì đăng nhập **thành công** gọi `reset()` chứ không
`record()`.)

`sweep_idle()` bắt buộc: thiếu nó, dict tăng một entry mỗi username hoặc IP từng
thử — không chặn trên và do kẻ tấn công điều khiển.

**RBAC theo thứ hạng**, không bao giờ so bằng: `resident(1) < security(2) <
admin(3)`. Admin làm được mọi việc của guard mà không route nào phải liệt kê cả
hai vai trò — và ngay khi route bắt đầu liệt kê vai trò, sẽ có một route bị quên
lúc thêm vai trò mới. Vai trò lạ xếp hạng 0 ⇒ không với tới gì.

**Kiosk công khai**: không đăng nhập, nhưng sau rate limit theo IP **và** một
kill-switch. Mọi lần tìm kiếm được audit kèm IP client. Đây là đánh đổi riêng tư
có chủ ý và được ghi trong `project-overview-pdr.md#privacy-position`.

**Riêng tư ảnh**: ảnh camera được xử lý rồi **huỷ tại chỗ**; không ảnh nào rời
khỏi toà nhà. Không lưu frame lên đĩa.

---

## 9. Frontend

- **React Query** với `query-keys.ts` tập trung — invalidation theo cây khoá,
  không có chuỗi khoá rải rác.
- **ROI editor**: reducer **thuần** (không import Konva) ⇒ unit test được toàn
  bộ logic vẽ. Kỷ luật undo: hầu hết mutation đẩy một entry lịch sử mỗi dispatch,
  **kéo là ngoại lệ có chủ ý** — `BEGIN_DRAG` chụp một lần lúc bắt đầu, các
  `MOVE_VERTEX`/`MOVE_POLYGON` áp dụng theo từng pointer-move mà **không** đẩy
  lịch sử, vì đơn vị undo thật của người vận hành là "cả thao tác kéo", không
  phải "một khung hình của nó". Canvas dựng bằng Konva; `coordinate-transform.ts`
  quy đổi giữa toạ độ hiển thị và toạ độ frame gốc.
- **Overlay trực tiếp**: `stream-overlay-canvas.tsx` vẽ box + polygon từ JSON
  header ở client — server không bao giờ vẽ lên ảnh (§6.2).
- **TypeScript strict** + `api-schema.d.ts` sinh từ OpenAPI ⇒ hợp đồng API được
  kiểm tra lúc biên dịch.
- **Song ngữ** VI (mặc định) / EN.

---

## 10. Kiểm thử & CI

Phân tầng theo thứ mỗi tầng có thể chứng minh:

| Tầng | Kiểm chứng | Ngưỡng coverage |
|------|-----------|-----------------|
| `vision/domain/` | hình học, bỏ phiếu, gán ô — **không import gì ngoài stdlib** ⇒ test không cần phần cứng | **100 %** |
| `security/` | JWT, RBAC, rate limit, hash | ≥ 90 % |
| backend còn lại | API + SQLite tạm | ≥ 80 % |
| frontend | Vitest | ≥ 60 % |

Luật then chốt: **`vision/domain/` không import gì ngoài thư viện chuẩn.** Đó
chính là thứ làm nó test được không cần phần cứng và port được sang thiết bị
hạn chế. `numpy`/`cv2` sống ở `vision/detectors/`, cách một thư mục.

CI: `ruff` → `mypy` → `pytest --cov` → `npm ci` → `tsc` → `oxlint` → `vitest` →
`npm run build` → `docker build` (đa kiến trúc, arm64). Kiểm định bổ sung: không
có `ultralytics` trong `pip freeze` production (AGPL chỉ dùng để export ONNX
trên máy dev), không có `.onnx` bị track trong git, config prod từ chối CORS
wildcard.

---

## 11. Tham số mặc định

| Tham số | Mặc định | Ghi chú |
|---------|----------|---------|
| `DEFAULT_POLL_INTERVAL_S` | 3,0 | vừa là nhịp suy luận vừa là FPS live view |
| `DEFAULT_VOTE_WINDOW / THRESHOLD` | 5 / 4 | ≈ 12 s để một ô chốt |
| `DETECTOR_CONFIDENCE` | 0,25 | clamp vào [0,01 – 0,95] |
| `NMS_IOU_THRESHOLD` | 0,45 | mặc định YOLO |
| `SAME_VEHICLE_IOU` | 0,50 | lỏng hơn NMS: các hộp này đã qua NMS |
| `MIN_BAND_COVERAGE` | 0,40 | dải đáy 30 %, lưới 5×5 |
| `motion_change_threshold` | 8,0 | sàn nhiễu đo được ~0,5 (xấu nhất 1,2) |
| `motion_force_interval_s` | 30,0 | heartbeat |
| `min_inference_interval_s` | 0,0 | sàn tốc độ, tắt mặc định |
| `MIN_PLATE_CONFIDENCE` | 0,60 | 55/59 bản đọc ở trên mức này |
| `MIN_PLATE_WIDTH_PX` | 60 | đọc tốt từ 60, hỏng ở 40 |
| `ws_heartbeat_s` | 20,0 | ping/pong |
| `ws_max_viewers_per_camera` | 4 | tổng 16 |
| `INFERENCE_POOL_SIZE` | 1 | **ràng buộc đúng đắn, không phải tuning** |
| `RETENTION_MONTHS` | 6 | `hourly_stats` không bị purge |

**Hiệu năng đo trên bo** (Arduino UNO Q, aarch64, 4 nhân): trung vị **616 ms**
mỗi lần suy luận ở 640×640. Suy luận tuần tự ⇒ nhịp 3 s đỡ được ~3 camera có dư
địa; 6 camera cần nhịp 5 s. Đọc biển toàn khung 640×480: 2642 ms (nên mới kích
hoạt theo sự kiện). Change gate: 2,7 ms.

---

## 12. Câu hỏi chưa giải đáp

1. **Chưa có số đo độ chính xác** (precision/recall gán ô) trên hiện trường
   thật — mọi tham số hình học hiện dựa trên mô phỏng + giàn tham chiếu.
2. **Chưa chạy soak test đầu-cuối**: chưa biết mức tăng bộ nhớ 8 h, CPU nền,
   tốc độ tăng dung lượng đĩa, độ trễ đầu-cuối (frame → trạng thái hiển thị).
3. `min_inference_interval_s` mặc định 0 (tắt) — chưa xác định giá trị nên bật ở
   hiện trường có nhiều camera.
4. Stagger **không** căn pha camera thêm vào muộn so với camera đang chạy (cần
   một epoch chung mà các loop không có). Cold start thì chính xác; thêm lẻ thì
   không. Chưa rõ có đáng làm không.
5. Ngưỡng `motion_change_threshold = 8,0` đo trên **một** camera tham chiếu ở
   cảnh tối; camera sáng hơn ồn hơn và có thể cần cao hơn — chưa có quy trình
   hiệu chỉnh tự động.
