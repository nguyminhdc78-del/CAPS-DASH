import type { ReactNode } from 'react'
import { Text } from 'react-konva'

import type { Point } from './coordinate-transform'

/** Slot code, centred on the polygon's centroid. `listening={false}` so the
 * label never steals a click meant for the polygon body underneath it. */
export function RoiSlotLabel({
  points,
  code,
  scale,
}: {
  points: Point[]
  code: string
  scale: number
}): ReactNode {
  const centroid = points.reduce(
    (acc, point) => ({ x: acc.x + point.x / points.length, y: acc.y + point.y / points.length }),
    { x: 0, y: 0 },
  )
  const fontSize = 13 / scale

  return (
    <Text
      x={centroid.x}
      y={centroid.y}
      text={code}
      fontSize={fontSize}
      fill="#ffffff"
      shadowColor="#000000"
      shadowBlur={3}
      shadowOpacity={0.8}
      // Rough horizontal centring without a text-measurement pass: good
      // enough for a short slot code, not pixel-perfect typography.
      offsetX={(code.length * fontSize) / 3.6}
      offsetY={fontSize / 2}
      listening={false}
    />
  )
}
