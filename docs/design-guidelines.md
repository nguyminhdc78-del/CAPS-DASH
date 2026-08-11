# Design Guidelines

Frontend standards for visual consistency, accessibility, and bilingual usability.

## Component Library: Ant Design v6

All UI components sourced from Ant Design (antd v6). Do not reinvent buttons, forms, or modals.

### Token Overrides
Place custom tokens in the theme provider. Avoid inline style props except for layout (margins, padding).

```typescript
// Example: theme configuration
const theme = {
  token: {
    colorPrimary: '#1890ff',
    borderRadius: 6,
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto',
  },
  components: {
    Button: { primaryColor: '#1890ff' },
  },
}
```

### Components in Use
- **Layout**: Layout (header, sider, content), Menu, Breadcrumb.
- **Forms**: Form, Input, Select, DatePicker, TimePicker, InputNumber.
- **Data display**: Table, List, Card, Statistic, Progress.
- **Feedback**: Modal, Drawer, Notification, Message, Spin, Alert.
- **Navigation**: Tabs, Pagination, Steps.
- **Data entry**: Checkbox, Radio, Switch, Upload.
- **Other**: Tree (for hierarchy), Tooltip, Popover, Divider.

## Slot State Colors

Three states, three distinct colors. **UNKNOWN must never be green.**

| State | Color | Usage | Rule |
|-------|-------|-------|------|
| UNKNOWN | Gray (`#9CA3AF`) | Before vote filter consensus | Never green; never folded into FREE count |
| FREE | Green (`#10B981`) | Slot is empty | Safe to park |
| OCCUPIED | Red (`#EF4444`) | Slot has a car | Not available |

**Examples**:
```typescript
// state-tag.tsx
const colorMap: Record<SlotState, string> = {
  [SlotState.UNKNOWN]: 'warning', // Gray in antd
  [SlotState.FREE]: 'success',    // Green
  [SlotState.OCCUPIED]: 'error',  // Red
};
```

**Live view overlay**: Draw detected boxes in red; confirmed slots in green; unconfirmed in gray.

**Dashboard counts**: Never add UNKNOWN to FREE. Show three separate counts: "X free • Y occupied • Z unknown".

## Bilingual UI (VI/EN)

### Locale Files
All UI strings stored in `src/i18n/locales/`:
```
src/i18n/
├── locales/
│   ├── vi.json
│   ├── en.json
```

### Key Naming Convention
Hierarchical with colons:
```json
{
  "common:login": "Đăng nhập",
  "common:logout": "Đăng xuất",
  "camera:title": "Camera",
  "camera:add": "Thêm Camera",
  "alert:camera_offline": "Camera ngoại tuyến"
}
```

### Rules
1. **Vietnamese is the default locale.** App boots with VI unless user explicitly chooses EN.
2. **Every string in both files.** If a key exists in VI, it must exist in EN with the equivalent translation.
3. **No partial translations.** A missing EN entry breaks the build (test assertion).
4. **No hardcoded strings.** Even error messages come from locale files (or service/exception message if dynamic).

### Example Usage
```typescript
import { useTranslation } from 'react-i18next';

export function CameraPage() {
  const { t } = useTranslation();
  return <h1>{t('camera:title')}</h1>;
}
```

### Copy Guidelines

#### Vietnamese (VI)
- **Formal tone** for admin/security features (create, delete, configure).
- **Clear and direct** for resident features (kiosk display).
- **Action verbs**: "Thêm", "Sửa", "Xóa", "Lưu", "Hủy".

#### English (EN)
- Match VI tone exactly (not simpler, not marketing-speak).
- Complete sentences in help text; fragments in buttons.

#### Consistency
- "Camera" in both (no "Máy ảnh" in VI, stick to English term for the device).
- "Slot" in both (no "Vị trí" variation; use the term consistently).

## Layout & Responsiveness

### Kiosk View (Lobby Dashboard)
- **Screen**: 1080p or smaller, often landscape on a tablet.
- **Text size**: Large (18px+), visible from 2 meters away.
- **Touch targets**: Buttons ≥ 48px high for finger accuracy.
- **Refresh**: Every 5 s, no animation flicker (CSS transitions only, not JS blinks).

### Desktop / Admin Pages
- **Sidebar**: Fixed left (optional hamburger on mobile).
- **Main content**: Responsive grid; single column on mobile.
- **Tables**: Scroll horizontally if needed; no truncation of data.

### Mobile (Web)
- **Full width**: No fixed sidebar; use a drawer.
- **Touch-friendly**: Tap targets ≥ 44px (iOS minimum).
- **Lazy load**: ROI editor (Konva) only loads when the page is visited.

## Accessibility

### Minimum Requirements (WCAG 2.1 AA)

#### Contrast
- **Text on background**: 4.5:1 for normal text, 3:1 for large text (18px+).
- **UI components**: 3:1 for focus indicators, borders, icons.
- **Tool**: Use WebAIM contrast checker or axe DevTools.

#### Keyboard Navigation
- **Tab order**: Logical (left-to-right, top-to-bottom).
- **Focus visible**: Every interactive element has a focus ring (outline or underline).
- **Escape closes**: Modals and drawers close on Escape.

#### Screen Reader Support
- **Semantic HTML**: Use `<button>`, `<nav>`, `<main>`, `<table>` (not divs).
- **Labels**: `<label htmlFor="input-id">` for form fields.
- **Images**: `alt` text for informational images (skip decorative images with `alt=""`).
- **Icon-only buttons**: `aria-label` or visible text.
- **ARIA**: Use `aria-label`, `aria-describedby`, `aria-live` only when semantic HTML is insufficient.

#### Example
```typescript
// Icon-only button with aria-label
<Tooltip title={t('common:delete')}>
  <Button
    icon={<DeleteOutlined />}
    aria-label={t('common:delete')}
    onClick={handleDelete}
  />
</Tooltip>

// Form field with proper label
<Form.Item label={t('camera:name')}>
  <Input placeholder={t('camera:name_placeholder')} />
</Form.Item>
```

### Testing
- **Manual**: Use keyboard to navigate every page; turn off mouse.
- **Screen reader**: Test with NVDA (free, Windows) or VoiceOver (built-in Mac).
- **Axe DevTools**: Chrome extension; run on every page, zero critical issues.

## Color Palette (Light & Dark Modes)

### Neutral
| Use | Light | Dark |
|-----|-------|------|
| Text primary | #000000 | #ffffff |
| Text secondary | #666666 | #cccccc |
| Background | #ffffff | #1a1a1a |
| Border | #e0e0e0 | #333333 |

### Status (Separate from Slot State)
| Status | Color | Use |
|--------|-------|-----|
| Success (OK) | #10B981 | Form validation, heartbeat |
| Warning (Caution) | #F59E0B | Config mismatch, disk low |
| Error (Alert) | #EF4444 | Failed login, offline camera |
| Info (Notice) | #3B82F6 | New data, tips |

### Slot State (see earlier section)
- **UNKNOWN**: Gray
- **FREE**: Green
- **OCCUPIED**: Red

## Typography

### Font Stack
```css
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
  'Helvetica Neue', Arial, sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji';
```

### Sizes & Weights
- **Hero (kiosk)**: 32px, weight 600 (bold).
- **Heading**: 24px, weight 600.
- **Subheading**: 16px, weight 500 (semibold).
- **Body**: 14px, weight 400 (normal).
- **Small**: 12px, weight 400.

### Line Height
- **Headings**: 1.3
- **Body**: 1.5
- **Dense UI**: 1.4

## State & Data Binding

### React Query (Queries)
- **Caching**: Stale time 5 min for occupancy data; disable for real-time (live stream).
- **Refetch**: On window focus if data > 5 min old.
- **Retry**: 3 times with exponential backoff for transient failures.

### Form State
- Use Ant Design `Form` component; let it manage state (vs. useState per field).

### Real-time (WebSocket)
- Subscriber connects on component mount; disconnects on unmount.
- Messages update component state; re-renders automatically.

## Performance

### Bundle Size
- **Target**: Main app < 500 KB (gzip).
- **Lazy load**: Konva (ROI editor) is a large dependency; load only on `/cameras/:id/roi`.

### Rendering
- **Memoization**: Memoize components that re-render frequently (slot lists, history table).
- **Virtual scrolling**: Use for large tables (e.g., 30-day history with 1000+ rows).

### API Calls
- **Debounce**: Search inputs (300 ms).
- **Throttle**: Scroll handlers (100 ms).
- **Request batching**: Combine multiple slot updates into one API call where possible.

## Error Handling

### User-Facing Errors
- **Notification**: Show at top of page with clear action ("Retry", "Dismiss", "Contact admin").
- **Toast lifespan**: 5 seconds for info/success, 10 seconds for errors (user decides to dismiss).
- **Message quality**: No stack traces; use human language.

### Example
```typescript
// Bad: "TypeError: Cannot read property 'id' of undefined"
// Good: "Camera not found. Please refresh and try again."

try {
  await api.updateCamera(cameraId, data);
  notification.success({ message: t('common:saved') });
} catch (err) {
  notification.error({
    message: t('common:error'),
    description: t('camera:update_failed'),
  });
}
```

## Dark Mode Support

- **Ant Design theme provider**: Accepts `algorithm: `dark`` or `algorithm: defaultAlgorithm`.
- **CSS variables**: Theme tokens cascade; no inline color values.
- **Test both**: Ensure every page is readable in light and dark.

## Icons

### Ant Design Icons
All icons from `@ant-design/icons`. Size: 16px (small), 20px (normal), 24px (large).

```typescript
import { DeleteOutlined, SaveOutlined, LoadingOutlined } from '@ant-design/icons';

<Button icon={<SaveOutlined />}>{t('common:save')}</Button>
```

### Semantic Use
- **Actions**: Use an icon that immediately communicates the action (edit = pencil, delete = trash, add = plus).
- **Status**: Use colour + icon (not colour alone).
- **Decorative**: Rarely; prefer text.

## Animations

### Keep It Fast
- **Transition duration**: 300 ms max; 150 ms for hovers.
- **No delays**: Transitions should feel responsive.
- **Disable on kiosk**: For full-screen dashboard, disable animations (motion reduces distraction).

### CSS Transitions (Preferred)
```css
button {
  transition: background-color 150ms ease, transform 150ms ease;
}
button:hover {
  background-color: #f0f0f0;
  transform: scale(1.02);
}
```

### Avoid
- Parallax scrolling (confusing on mobile).
- Auto-playing videos (auto-muted or avoid).
- Infinite spinners (use a progress bar if duration is known).

## RTL (Right-to-Left) Considerations

Currently out of scope (Vietnamese and English are LTR). If Arabic or Hebrew support is added:
- Ant Design supports RTL out of the box via `direction="rtl"` in ConfigProvider.
- Test layout; mirrors should work automatically.

## Colour Blindness

- **Red/green**: Don't rely on colour alone (use icon + label + colour).
- **Blue/yellow**: Avoid low-contrast combinations.
- **Tool**: Use Color Blind Simulator in browser DevTools.

### Test
- Occupancy: "3 free (green circle) • 2 occupied (red square) • 1 unknown (gray dash)".
- Alerts: "Warning (yellow triangle) Camera offline" (not just a yellow box).

## Code Style (Frontend)

### File Organization
```
src/
├── app/                          # Route definitions, layout
├── core/                         # Queries, auth, hooks
├── features/                     # Pages + sub-components
│   ├── dashboard/
│   │   ├── dashboard-page.tsx    # Page component
│   │   ├── occupancy-summary.tsx # Child component
│   │   └── dashboard-page.test.tsx
│   ├── cameras/
│   └── ...
├── shared/                       # Shared UI atoms
│   ├── components/
│   │   ├── state-tag.tsx
│   │   └── state-tag.test.tsx
│   └── hooks/
├── i18n/                         # Localization
│   └── locales/
│       ├── vi.json
│       └── en.json
└── index.tsx                     # Root
```

### Import Aliases
```typescript
// tsconfig.json
{
  "compilerOptions": {
    "baseUrl": "./src",
    "paths": {
      "@/*": ["./*"]
    }
  }
}

// Usage in components
import { getCameraById } from '@/core/cameras/camera-queries';
```

### Naming
- **Components**: PascalCase, end with "Page", "Card", "Form", etc. (`CameraPage.tsx`, not `camera-page.tsx`).
- **Utilities/hooks**: camelCase (`useCameraQuery.ts`, `formatOccupancy.ts`).
- **Types**: PascalCase (`Camera.ts`, `CameraRequest.ts`).

## Handoff to QA / Design Review

When a feature is complete:
1. **Screenshot**: Light mode + dark mode.
2. **Responsive**: Desktop (1920px), tablet (768px), mobile (375px).
3. **Accessibility**: Run axe DevTools; zero critical/serious issues.
4. **Bilingual**: VI and EN, consistency check.
5. **Keyboard**: Tab through every interactive element; Escape closes modals.

Include in the PR description.
