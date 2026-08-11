import type { ReactNode } from 'react'
import { Circle } from 'react-konva'

import type { Point } from './coordinate-transform'

const BASE_RADIUS = 4
const HIT_PADDING = 10

/** Sits on the midpoint of an edge; a click there inserts a new vertex. */
export function RoiMidpointHandle({
  a,
  b,
  scale,
  onClick,
}: {
  a: Point
  b: Point
  scale: number
  onClick: (midpoint: Point) => void
}): ReactNode {
  const midpoint = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }

  return (
    <Circle
      x={midpoint.x}
      y={midpoint.y}
      radius={BASE_RADIUS / scale}
      hitStrokeWidth={HIT_PADDING / scale}
      fill="#ffffff"
      stroke="#8c8c8c"
      strokeWidth={1.5 / scale}
      dash={[2 / scale, 2 / scale]}
      onMouseEnter={(e) => {
        const stage = e.target.getStage()
        if (stage) stage.container().style.cursor = 'copy'
      }}
      onMouseLeave={(e) => {
        const stage = e.target.getStage()
        if (stage) stage.container().style.cursor = 'default'
      }}
      onClick={(e) => {
        e.cancelBubble = true
        onClick(midpoint)
      }}
    />
  )
}
