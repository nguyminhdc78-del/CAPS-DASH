import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

import { SLOT_STATE_COLORS } from '@/core/theme/use-theme-config'
import type { DisplayRect } from './overlay-geometry'
import { scaleFactorsFor } from './overlay-geometry'
import type { DetectionBox, FrameHeader, SlotOverlay } from './frame-header-types'

const POLYGON_FILL_ALPHA = 0.25
const BOX_STROKE_COLOR = '#faad14' // antd's warning-gold, distinct from every slot-state color
const LABEL_FONT = '12px sans-serif'

/**
 * Draws slot polygons and detection boxes over the last frame's rendered
 * rectangle. Redraws in a plain effect keyed on the header/rect/toggles - no
 * requestAnimationFrame loop, because frames arrive at the camera's poll
 * interval (seconds), not at video frame rate; scheduling a 60Hz loop for a
 * value that changes a few times a minute would be pure overhead.
 */
export function StreamOverlayCanvas({
  header,
  rect,
  showPolygons,
  showBoxes,
  showLabels,
}: {
  header: FrameHeader | null
  rect: DisplayRect | null
  showPolygons: boolean
  showBoxes: boolean
  showLabels: boolean
}): ReactNode {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d') ?? null
    if (!canvas || !ctx) return

    ctx.clearRect(0, 0, canvas.width, canvas.height)
    if (!header || !rect) return

    const { x: scaleX, y: scaleY } = scaleFactorsFor(rect, header.frame_w, header.frame_h)

    if (showPolygons) {
      for (const slot of header.slots) drawPolygon(ctx, slot, scaleX, scaleY, showLabels)
    }
    if (showBoxes) {
      for (const detection of header.detections) drawDetection(ctx, detection, scaleX, scaleY, showLabels)
    }
  }, [header, rect, showPolygons, showBoxes, showLabels])

  if (!rect) return null

  return (
    <canvas
      ref={canvasRef}
      width={rect.width}
      height={rect.height}
      style={{ position: 'absolute', left: rect.left, top: rect.top, pointerEvents: 'none' }}
    />
  )
}

function drawPolygon(
  ctx: CanvasRenderingContext2D,
  slot: SlotOverlay,
  scaleX: number,
  scaleY: number,
  showLabels: boolean,
): void {
  const first = slot.polygon[0]
  if (!first) return

  // UNKNOWN must render grey, never a shade of green - the same rule
  // state-tag.tsx enforces for the slot table, so this is the same lookup.
  const color = SLOT_STATE_COLORS[slot.state]

  ctx.beginPath()
  slot.polygon.forEach(([x, y], index) => {
    const px = x * scaleX
    const py = y * scaleY
    if (index === 0) ctx.moveTo(px, py)
    else ctx.lineTo(px, py)
  })
  ctx.closePath()
  ctx.fillStyle = withAlpha(color, POLYGON_FILL_ALPHA)
  ctx.fill()
  ctx.strokeStyle = color
  ctx.lineWidth = 2
  ctx.stroke()

  if (showLabels) {
    ctx.fillStyle = color
    ctx.font = LABEL_FONT
    ctx.fillText(slot.code, first[0] * scaleX, first[1] * scaleY - 4)
  }
}

function drawDetection(
  ctx: CanvasRenderingContext2D,
  detection: DetectionBox,
  scaleX: number,
  scaleY: number,
  showLabels: boolean,
): void {
  const x = detection.x1 * scaleX
  const y = detection.y1 * scaleY
  const width = (detection.x2 - detection.x1) * scaleX
  const height = (detection.y2 - detection.y1) * scaleY

  ctx.strokeStyle = BOX_STROKE_COLOR
  ctx.lineWidth = 2
  ctx.strokeRect(x, y, width, height)

  if (showLabels) {
    ctx.fillStyle = BOX_STROKE_COLOR
    ctx.font = LABEL_FONT
    ctx.fillText(`${detection.label} ${Math.round(detection.confidence * 100)}%`, x, y - 4)
  }
}

function withAlpha(hexColor: string, alpha: number): string {
  const r = parseInt(hexColor.slice(1, 3), 16)
  const g = parseInt(hexColor.slice(3, 5), 16)
  const b = parseInt(hexColor.slice(5, 7), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}
