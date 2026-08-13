import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  // Deliberately NOT vi.unstubAllGlobals(): several suites install a global
  // once at module scope (e.g. `vi.stubGlobal('WebSocket', FakeWebSocket)` in
  // tests/features/live/), and tearing that down after the first test in the
  // file leaves the rest of the file running against the real global. Suites
  // that stub per-test re-stub per test, so they do not need the teardown.
})

// antd components query matchMedia for responsive behaviour; jsdom has no
// implementation, so without this every render throws.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
})
