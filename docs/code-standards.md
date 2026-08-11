# Code Standards & Conventions

Developer standards in force across phases 01–14. Deviations from language norms are documented here; follow ecosystem defaults otherwise.

## Identifiers & Naming

### General Rule
All identifiers (variables, functions, modules, classes) written in **English**, even in a Vietnamese-default UI (Vietnamese strings live in locale files only).

### Python: `snake_case` (PEP 8)
```python
def get_camera_by_id(camera_id: int) -> Camera: ...
variable_name = "value"
class CameraContext: ...
```

### JavaScript/TypeScript: `kebab-case` (files), `camelCase` (identifiers)
```typescript
// Filenames
export function getCameraById(cameraId: number): Camera { ... }
const variableName = "value";
export class CameraService { ... }

// File: camera-service.ts
// NOT: cameraService.ts or camera_service.ts
```

### Exception: `*.config.js` files
Keep the `.config.js` pattern (not `.config.ts` or `.config.kebab.js`):
```
vite.config.ts
tailwind.config.js
```

## File Size Management

**Target: ≤ 200 lines per file** (including docstrings and imports).

When a file approaches 200 LOC:
- **Split by logical module**: Separate domain, services, routes, schemas.
- **Extract helpers**: Move utility functions to a dedicated `*-utils.py` or `-helpers.ts`.
- **Lazy load**: For frontend, lazy-load large dependencies (Konva in ROI editor).

**Example**: Phase 07 split REST routes into separate files per entity (camera_routes, user_routes, etc.) rather than one massive router.

## Sync vs. Async

### Rule: Sync by Default
- **REST handlers**: Always `def`, not `async def`. The event loop is available for workers and WebSocket tasks.
- **Database access**: Sync SQLAlchemy 2.0 exclusively. No async ORM.
- **File I/O**: Sync, run in threadpool if necessary (e.g., CSV export).

### Exceptions: `async def` Only
1. **WebSocket endpoints** (`/ws/*`): Must be `async` (socket I/O is inherently async).
2. **Camera worker supervisor**: Must be `async` to manage concurrent camera loops.

**Rationale**: The board's CPU is shared. Sync handlers let the event loop time-slice between cameras and WebSocket tasks without preemption overhead.

## Error Handling & Contracts

### Error Envelope
Every error response follows this contract:
```json
{
  "detail": {
    "code": "CAMERA_NOT_FOUND",
    "message": "Camera 42 does not exist",
    "context": { "camera_id": 42 }
  }
}
```

- **code**: Immutable identifier (never renamed or reused). Once a code is assigned, it is permanent for backward-compatibility with clients.
- **message**: Human-readable detail; can change.
- **context**: Optional structured data for debugging.

### Error Codes Registry
Defined in `backend/caps_dash/errors/codes.py`. New errors:
1. Assign a unique code name (CAMERA_NOT_FOUND, USER_DISABLED, etc.).
2. Add it to the `ErrorCode` enum.
3. Document the status code and trigger condition in a docstring.
4. Never delete or rename an existing code.

### Example
```python
# backend/caps_dash/errors/codes.py
class ErrorCode(StrEnum):
    CAMERA_NOT_FOUND = "CAMERA_NOT_FOUND"
    # 404: Camera with this ID does not exist
```

## Module Structure & Purity

### `domain/` — Pure Python
- **Constraint**: No third-party imports outside the standard library.
- **Purpose**: Geometry algorithms, voting logic, state machines — portable, testable without hardware.
- **Files**: `geometry.py`, `vote_filter.py`, `states.py`, `slot_map.py`, `assignment.py`.

**Example**: `vote_filter.py` takes raw detections (list of bounding boxes) and returns a set of consensus detections. No camera or database knowledge.

### `vision/` — Detector & Source Abstractions
- **Constraint**: Each detector (ONNX, ultralytics, fake) is a separate backend module.
- **Pattern**: `Detector` ABC with `detect(frame: np.ndarray) -> list[Detection]`.
- **Frame sources**: ESP32CAM, ImageFolder, VideoFile, Fake — each is a separate module.

### `services/` — Business Logic
- **Constraint**: Services are thin; they glue domain logic to ORM models and API concerns.
- **Pattern**: One service class per entity (CameraService, UserService, HistoryService).
- **No module-level state**: All dependencies injected; state lives in `AppState`.

### `api/` — Request Handlers
- **Pattern**: Routers organized by entity; one file per resource type.
- **Sync handlers**: `def`, not `async def`, unless it's a WebSocket.
- **Schemas**: Request/response schemas in a separate `schemas/` subpackage, not inline.

## No Module-Global Mutable State

**Anti-pattern**:
```python
# WRONG
detector = None

def get_detector():
    global detector
    if detector is None:
        detector = load_model()
    return detector
```

**Correct**:
```python
# Lifespan creates it once; state.services holds it.
state.services["detector"] = Detector(...)

# Handlers access via request.app.state.caps.services["detector"]
```

**Rationale**: Module-level state makes tests interact (can't run two tests with different detector configs in one process) and hides dependencies.

## Threading & Concurrency

### Rules
1. **Never share a detector between threads**. Each inference-pool worker gets its own model instance or uses a thread-safe ONNX session.
2. **One DB-writer thread**: All SQLite writes serialized through a single executor to prevent lock contention.
3. **Event loop coordination**: Workers post work to the event loop via `loop.call_soon_threadsafe()` for state changes.

### Example
```python
# lifespan.py
inference_pool = ThreadPoolExecutor(max_workers=1)  # One detector, no sharing
db_pool = ThreadPoolExecutor(max_workers=1)  # One SQLite writer
```

## Reload & Shutdown Signals

### Reload (ROI polygon changes)
1. Admin updates a polygon in the UI.
2. Backend persists to database.
3. **After commit**, `reload_signals.send(camera_id)` is called.
4. Camera loop wakes, reads the new polygon, applies it mid-flight.

**Critical**: Signal sent AFTER commit, not before. Uncommitted data would be lost if the loop restarts.

### Shutdown (SIGTERM)
1. SIGTERM received.
2. Lifespan calls `supervisor.stop(timeout=10)`.
3. Supervisor cancels all camera tasks; waits up to 10 s.
4. Executor threads shutdown with `cancel_futures=True`.
5. Engine disposed; logger closed.
6. Process exits.

## Type Annotations

### Python
- **Rule**: Strict mypy (`strict = true` in pyproject.toml).
- **No `# type: ignore`**: Every ignore requires a comment explaining why and an issue tracker reference if human error.
- **Generics**: Use `list[T]`, `dict[K, V]` (Python 3.9+); not `List[T]`, `Dict[K, V]`.

### TypeScript
- **Rule**: Strict mode (`strict: true` in tsconfig.json).
- **No `any`**: Use `unknown` if type is truly unknown; narrow with type guards.
- **React**: Use `FC<Props>` or function component with explicit return type.

## Testing & Coverage

### Coverage Gates (Phase 14)
- **`caps_dash.vision.domain`**: 100% (pure logic, high-value target).
- **`caps_dash.security`**: ≥90% (auth, RBAC, rate limiting).
- **Backend overall**: ≥80%.
- **Frontend**: ≥60%.

### Fixture Patterns
- **Temp DB per test**: Use pytest fixtures; no shared state.
- **Fake detector**: Non-blocking, predictable; default for integration tests.
- **Synthetic history**: Fixture to generate 30-day history without querying a real table.

### Markers
- `@pytest.mark.unit` — domain, codec, geometry (fast, no DB).
- `@pytest.mark.integration` — API + temp DB.
- `@pytest.mark.worker` — camera loop end-to-end.
- `@pytest.mark.e2e` — smoke test (login → camera → WS → clean exit).

## Documentation & Comments

### Docstrings
- **Every module, class, function** has a docstring.
- **Format**: Plain English, not reStructuredText or Sphinx.
- **Example**:
```python
def vote_filter(detections: list[Detection], window: int, threshold: int) -> set[Detection]:
    """Suppress transient detections via N-of-M voting.
    
    Returns detections that appear in at least `threshold` of the last `window`
    frames. Fewer than `window` frames have not yet been seen.
    """
```

### Inline Comments
- **Explain why, not what.** The code shows what; a comment should explain design decisions, gotchas, or tradeoffs.
- **Bad**: `x = x + 1  # add one`
- **Good**: `x += 1  # increment to match 1-indexed frame numbering in the protocol`

### Phase Provenance
Files list their originating phase in a module docstring:
```python
"""Camera worker loop.

Owns one asyncio task per enabled camera. Loop runs on the event loop;
inference and DB writes run in executor pools to keep the loop responsive.

Created in phase 06. Refined in phases 12 (snapshot cache) and 14 (graceful
shutdown hardening).
"""
```

## Git Workflow & Commits

### Conventional Commits
Format: `<type>(<scope>): <subject>`

```
feat(vision): add vote filter for noise suppression
fix(auth): prevent token expiry race in refresh endpoint
docs(deployment): clarify single-worker constraint in systemd unit
test(domain): add 100% coverage to geometry module
chore(deps): pin onnxruntime to 1.28 LTS
```

**Types**: feat, fix, docs, test, chore, refactor, perf, style.

### No AI References
- Do not mention "Claude", "ChatGPT", "AI assistant" in commit messages.
- Describe the work, not the tooling used.

## Secrets & Configuration

### Never in Source Code
- API keys, credentials, SECRET_KEY → environment variables only.
- `.env` is never committed (`.env.example` is the template).
- Migrations never hardcode admin passwords or tokens.

### Configuration Validation
- `settings.py` validates everything at startup.
- Invalid config fails with a clear error message before the app starts.
- No silent defaults for production settings (e.g., SECRET_KEY must be set).

## Licencing

### Runtime Dependencies
- **Apache-2.0**: onnxruntime (vehicle detection at runtime).
- **MIT**: FastAPI, Pydantic, SQLAlchemy, React, Ant Design.
- **Other**: Locked in pyproject.toml; audit in CI.

### Development-Only Dependencies
- **AGPL-3.0**: ultralytics (used only to export ONNX model; never deployed).
- Installed via `pip install -e ".[vision-dev]"` on dev machine only.
- CI asserts no AGPL code in the production image.

## Accessibility & i18n

### Accessibility (Frontend)
- **Never colour alone**: Use text + icon + colour for status tags.
- **Icon-only buttons**: Require `aria-label`.
- **Form labels**: Associated via `htmlFor`.
- **WCAG 2.1 AA target**: Contrast ratios, focus indicators, keyboard navigation.

### Bilingual (VI/EN)
- **Locale files**: `src/i18n/locales/{vi,en}.json`.
- **No hardcoded strings**: All UI strings keyed in locale files.
- **Consistency**: Keys mirrored exactly between VI and EN (same count, same structure).
- **Namespace pattern**: `namespace:key` (e.g., `camera:title`, `alert:online`).

## Performance Considerations

### No Premature Optimization
- Ship correct code first; measure on the board; optimize only if needed.
- Performance numbers measured on Arduino UNO Q are the only ones that matter.

### Known Expensive Operations
- Full occupancy history query (capped at 92 days, max 100k rows).
- Hourly aggregation (runs every 10 min in background, not on request).
- Image encoding (never done by server; JPEG passed through).

### Polling Defaults
- Camera poll interval: 3 s (tunable per camera).
- Aggregation job: 10 min.
- Retention purge: daily.
- Rate-limit sweep: hourly.

Shorter intervals increase CPU load on the board; longer intervals reduce responsiveness. Tuned per site, not hardcoded.
