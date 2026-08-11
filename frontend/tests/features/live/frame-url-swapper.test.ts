import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createFrameUrlSwapper } from '@/features/live/frame-url-swapper'

/** Fires `onload` synchronously the moment `src` is assigned - deterministic,
 *  no need to await a real image decode in a unit test. */
class InstantLoadImage {
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  private currentSrc = ''
  set src(value: string) {
    this.currentSrc = value
    this.onload?.()
  }
  get src(): string {
    return this.currentSrc
  }
}

class NeverLoadsImage {
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  src = ''
}

describe('createFrameUrlSwapper', () => {
  let created: string[]
  let revoked: string[]
  let counter: number

  beforeEach(() => {
    created = []
    revoked = []
    counter = 0
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => {
        const url = `blob:frame-${++counter}`
        created.push(url)
        return url
      }),
      revokeObjectURL: vi.fn((url: string) => {
        revoked.push(url)
      }),
    })
  })

  it('revokes N-1 urls after N frames while mounted, and the last one on dispose', () => {
    vi.stubGlobal('Image', InstantLoadImage)
    const shown: string[] = []
    const swapper = createFrameUrlSwapper<number>((url) => shown.push(url))
    const blob = new Blob(['frame'])

    for (let i = 0; i < 5; i++) swapper.showFrame(blob, i)

    expect(created).toHaveLength(5)
    expect(revoked).toHaveLength(4)
    expect(revoked).toEqual(created.slice(0, 4)) // every url but the current one
    expect(shown).toEqual(created) // onSwap fired once per frame, in order

    swapper.dispose()

    expect(revoked).toHaveLength(5)
    expect(revoked.at(-1)).toBe(created.at(-1))
  })

  it('never revokes a url before its replacement has finished loading', () => {
    vi.stubGlobal('Image', NeverLoadsImage)
    const swapper = createFrameUrlSwapper<null>(() => {})

    swapper.showFrame(new Blob(['a']), null)
    swapper.showFrame(new Blob(['b']), null)

    expect(created).toHaveLength(2)
    expect(revoked).toHaveLength(0) // neither preload ever fired load/error
  })

  it('dispose is a no-op when nothing was ever shown', () => {
    vi.stubGlobal('Image', InstantLoadImage)
    const swapper = createFrameUrlSwapper<null>(() => {})
    expect(() => swapper.dispose()).not.toThrow()
    expect(revoked).toHaveLength(0)
  })
})
