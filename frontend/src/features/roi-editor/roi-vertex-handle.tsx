import type { KonvaEventObject } from 'konva/lib/Node'
import type { ReactNode } from 'react'
import { Circle } from 'react-konva'

import type { Point } from './coordinate-transform'

/** Base sizes in SCREEN pixels. Divided by the Stage's zoom scale so a
 * handle stays the same visible size (and stays grabbable) at any zoom
 * level, per phase-11 plan risk "Vertex handles unclickable at low zoom". */
const BASE_RADIUS = 6
const HIT_PADDING = 10

export function RoiVertexHandle({
  point,
  scale,
  active,
  onDragStart,
  onDragMove,
  onDragEnd,
  onClick,
  onDelete,
}: {
  point: Point
  scale: number
  active: boolean
  onDragStart: () => void
  /** Display-space point, straight from the Konva node - the caller converts. */
  onDragMove: (point: Point) => void
  onDragEnd: () => void
  onClick: () => void
  onDelete: () => void
}): ReactNode {
  return (
    <Circle
      x={point.x}
      y={point.y}
      radius={BASE_RADIUS / scale}
      hitStrokeWidth={HIT_PADDING / scale}
      fill={active ? '#1677ff' : '#ffffff'}
      stroke="#1677ff"
      strokeWidth={2 / scale}
      draggable
      onMouseEnter={(e) => setCursor(e, 'grab')}
      onMouseLeave={(e) => setCursor(e, 'default')}
      onDragStart={(e) => {
        e.cancelBubble = true
        onDragStart()
      }}
      onDragMove={(e) => {
        e.cancelBubble = true
        onDragMove({ x: e.target.x(), y: e.target.y() })
      }}
      onDragEnd={(e) => {
        e.cancelBubble = true
        onDragEnd()
      }}
      onClick={(e) => {
        e.cancelBubble = true
        onClick()
      }}
      onContextMenu={(e) => {
        e.evt.preventDefault()
        e.cancelBubble = true
        onDelete()
      }}
    />
  )
}

function setCursor(event: KonvaEventObject<MouseEvent>, cursor: string): void {
  const stage = event.target.getStage()
  if (stage) stage.container().style.cursor = cursor
}
