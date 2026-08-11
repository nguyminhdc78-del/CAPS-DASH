import { useState } from 'react'

import type { FrameSize, Point } from './coordinate-transform'

/**
 * Owns the Konva Stage's zoom/pan transform PLUS the "display box" size that
 * coordinate-transform.ts converts against.
 *
 * These are deliberately two different scales, and conflating them is the
 * mistake this whole module exists to avoid:
 *   - `displayFrame` sizes the box the snapshot is laid out in so it keeps
 *     the source's aspect ratio (computed by `fitToView`/`zoomTo100`, only
 *     changed when the container or the loaded snapshot changes). This is
 *     what sourceToDisplay/displayToSource convert against, always with
 *     independent x/y factors.
 *   - `viewport.scale` is the Stage's uniform zoom ON TOP of that box: it
 *     stretches the whole already-aspect-correct scene (image AND polygons
 *     together) equally, so a single shared factor here is fine - it is not
 *     converting between two differently-proportioned coordinate systems,
 *     it is zooming a picture that is already correctly proportioned.
 */

export interface Viewport {
  scale: number
  x: number
  y: number
}

export const MIN_SCALE = 0.2
export const MAX_SCALE = 8

export function clampScale(scale: number): number {
  return Math.min(Math.max(scale, MIN_SCALE), MAX_SCALE)
}

function boxPreservingAspect(container: FrameSize, source: FrameSize): FrameSize {
  const containerAspect = container.width / container.height
  const sourceAspect = source.width / source.height
  // The one legitimate single-ratio use in this hook: sizing the on-screen
  // BOX so it preserves the source's aspect ratio inside the container. This
  // decides how big to draw the box before any point is converted into it -
  // it is not the point-conversion transform itself.
  return sourceAspect > containerAspect
    ? { width: container.width, height: container.width / sourceAspect }
    : { width: container.height * sourceAspect, height: container.height }
}

export function useCanvasViewport() {
  const [displayFrame, setDisplayFrame] = useState<FrameSize | null>(null)
  const [viewport, setViewport] = useState<Viewport>({ scale: 1, x: 0, y: 0 })

  function fitToView(container: FrameSize, source: FrameSize): void {
    const box = boxPreservingAspect(container, source)
    setDisplayFrame(box)
    setViewport({ scale: 1, x: (container.width - box.width) / 2, y: (container.height - box.height) / 2 })
  }

  function zoomTo100(container: FrameSize, source: FrameSize): void {
    const box = displayFrame ?? boxPreservingAspect(container, source)
    const nativeScale = box.width > 0 ? clampScale(source.width / box.width) : 1
    setDisplayFrame(box)
    setViewport({
      scale: nativeScale,
      x: (container.width - box.width * nativeScale) / 2,
      y: (container.height - box.height * nativeScale) / 2,
    })
  }

  function zoomAtPointer(pointer: Point, nextScale: number): void {
    setViewport((prev) => {
      const clamped = clampScale(nextScale)
      const ratio = clamped / prev.scale
      // Anchors the point under the cursor: it should stay under the cursor
      // after the zoom, not drift toward the canvas origin.
      return {
        scale: clamped,
        x: pointer.x - (pointer.x - prev.x) * ratio,
        y: pointer.y - (pointer.y - prev.y) * ratio,
      }
    })
  }

  function setPan(x: number, y: number): void {
    setViewport((prev) => ({ ...prev, x, y }))
  }

  return { displayFrame, viewport, fitToView, zoomTo100, zoomAtPointer, setPan }
}

export type CanvasViewportApi = ReturnType<typeof useCanvasViewport>
