import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import { StreamOverlayCanvas } from './stream-overlay-canvas'
import { computeContainedRect } from './overlay-geometry'
import type { DisplayRect } from './overlay-geometry'
import type { FrameHeader } from './frame-header-types'

/** `<img>` + a transparent canvas stack, kept aligned as the box resizes. */
export function CameraStreamView({
  jpegUrl,
  header,
}: {
  jpegUrl: string | null
  header: FrameHeader | null
}): ReactNode {
  const containerRef = useRef<HTMLDivElement>(null)
  const imgRef = useRef<HTMLImageElement>(null)
  const [rect, setRect] = useState<DisplayRect | null>(null)

  const recomputeRect = (): void => {
    const container = containerRef.current
    const img = imgRef.current
    if (!container || !img || img.naturalWidth === 0 || img.naturalHeight === 0) {
      setRect(null)
      return
    }
    setRect(
      computeContainedRect(container.clientWidth, container.clientHeight, img.naturalWidth, img.naturalHeight),
    )
  }

  useEffect(() => {
    const container = containerRef.current
    // jsdom (unit tests) has no ResizeObserver; the component still renders
    // fine without live resize handling there, only real browsers need it.
    if (!container || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(recomputeRect)
    observer.observe(container)
    return () => observer.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div
      ref={containerRef}
      style={{ position: 'relative', width: '100%', aspectRatio: '16 / 9', background: '#000' }}
    >
      {jpegUrl && (
        <img
          ref={imgRef}
          src={jpegUrl}
          onLoad={recomputeRect}
          alt=""
          style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
        />
      )}
      <StreamOverlayCanvas header={header} rect={rect} showPolygons showBoxes showLabels />
    </div>
  )
}
