import type { ReactNode } from 'react'
import { Circle, Line } from 'react-konva'

import type { FrameSize, Point } from './coordinate-transform'
import { sourceToDisplay } from './coordinate-transform'

const FIRST_VERTEX_RADIUS = 7

/**
 * The polygon currently being drawn (draw mode, before it is closed into a
 * committed slot). Rendered separately from `roi-slot-polygon.tsx` because a
 * draft has no `code`/`floor` yet and a fundamentally different interaction:
 * clicking the FIRST vertex closes it (same as double-click / Enter),
 * everything else here is display-only.
 */
export function RoiDraftPolygon({
  draft,
  sourceFrame,
  displayFrame,
  scale,
  onCloseAtFirstVertex,
}: {
  draft: Point[]
  sourceFrame: FrameSize
  displayFrame: FrameSize
  scale: number
  onCloseAtFirstVertex: () => void
}): ReactNode {
  const displayPoints = draft.map((point) => sourceToDisplay(point, sourceFrame, displayFrame))
  const flat = displayPoints.flatMap((point) => [point.x, point.y])
  const canClose = displayPoints.length >= 3

  return (
    <>
      <Line points={flat} stroke="#1677ff" strokeWidth={2 / scale} dash={[6 / scale, 4 / scale]} />
      {displayPoints.map((point, index) => (
        <Circle
          key={index}
          x={point.x}
          y={point.y}
          radius={(index === 0 && canClose ? FIRST_VERTEX_RADIUS : 5) / scale}
          fill={index === 0 && canClose ? '#1677ff' : '#ffffff'}
          stroke="#1677ff"
          strokeWidth={2 / scale}
          onMouseEnter={(e) => {
            if (index !== 0 || !canClose) return
            const stage = e.target.getStage()
            if (stage) stage.container().style.cursor = 'pointer'
          }}
          onMouseLeave={(e) => {
            const stage = e.target.getStage()
            if (stage) stage.container().style.cursor = 'default'
          }}
          onClick={(e) => {
            if (index !== 0 || !canClose) return
            e.cancelBubble = true
            onCloseAtFirstVertex()
          }}
        />
      ))}
    </>
  )
}
