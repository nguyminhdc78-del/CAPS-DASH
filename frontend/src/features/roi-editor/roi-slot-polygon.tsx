import type { ReactNode } from 'react'
import { Group, Line } from 'react-konva'

import type { FrameSize, Point } from './coordinate-transform'
import { clampToFrame, displayToSource, sourceToDisplay } from './coordinate-transform'
import { RoiMidpointHandle } from './roi-midpoint-handle'
import { RoiSlotLabel } from './roi-slot-label'
import { RoiVertexHandle } from './roi-vertex-handle'
import type { EditorMode, EditorSlot } from './roi-editor-types'

const COLORS = {
  invalid: { fill: 'rgba(245,34,45,0.25)', stroke: '#f5222d' },
  warning: { fill: 'rgba(250,173,20,0.22)', stroke: '#faad14' },
  selected: { fill: 'rgba(22,119,255,0.30)', stroke: '#1677ff' },
  normal: { fill: 'rgba(82,196,26,0.18)', stroke: '#52c41a' },
}

export function RoiSlotPolygon({
  slot,
  sourceFrame,
  displayFrame,
  scale,
  mode,
  selected,
  selectedVertex,
  status,
  onSelectPolygon,
  onSelectVertex,
  onBeginDrag,
  onMoveVertex,
  onMovePolygon,
  onInsertVertex,
  onDeleteVertex,
}: {
  slot: EditorSlot
  sourceFrame: FrameSize
  displayFrame: FrameSize
  scale: number
  mode: EditorMode
  selected: boolean
  selectedVertex: number | null
  status: 'valid' | 'invalid' | 'warning'
  onSelectPolygon: () => void
  onSelectVertex: (index: number) => void
  onBeginDrag: () => void
  onMoveVertex: (index: number, point: Point) => void
  onMovePolygon: (dx: number, dy: number) => void
  onInsertVertex: (afterIndex: number, point: Point) => void
  onDeleteVertex: (index: number) => void
}): ReactNode {
  const displayPoints = slot.points.map((point) => sourceToDisplay(point, sourceFrame, displayFrame))
  const flat = displayPoints.flatMap((point) => [point.x, point.y])
  const colors =
    status === 'invalid'
      ? COLORS.invalid
      : selected
        ? COLORS.selected
        : status === 'warning'
          ? COLORS.warning
          : COLORS.normal

  return (
    <Group
      draggable={mode === 'select'}
      onDragStart={(e) => {
        e.cancelBubble = true
        onBeginDrag()
      }}
      onDragEnd={(e) => {
        e.cancelBubble = true
        const node = e.target
        // The Group's own x/y is the drag delta in DISPLAY pixels; convert
        // once (displayToSource is a pure per-axis scale with no translation
        // term, so it doubles correctly as a delta transform), feed it to
        // the reducer as a source-pixel delta, then zero the node - the
        // reducer's `points` become the single source of truth again on the
        // very next render, not a leftover Konva transform.
        const deltaDisplay = { x: node.x(), y: node.y() }
        node.position({ x: 0, y: 0 })
        const deltaSource = displayToSource(deltaDisplay, sourceFrame, displayFrame)
        onMovePolygon(deltaSource.x, deltaSource.y)
      }}
    >
      <Line
        points={flat}
        closed
        fill={colors.fill}
        stroke={colors.stroke}
        strokeWidth={(selected ? 2.5 : 1.5) / scale}
        onClick={(e) => {
          e.cancelBubble = true
          onSelectPolygon()
        }}
      />

      {mode === 'select' &&
        displayPoints.map((point, index) => (
          <RoiVertexHandle
            key={index}
            point={point}
            scale={scale}
            active={selected && selectedVertex === index}
            onDragStart={onBeginDrag}
            onDragMove={(displayPoint) => {
              const sourcePoint = clampToFrame(
                displayToSource(displayPoint, sourceFrame, displayFrame),
                sourceFrame,
              )
              onMoveVertex(index, sourcePoint)
            }}
            onDragEnd={() => undefined}
            onClick={() => onSelectVertex(index)}
            onDelete={() => onDeleteVertex(index)}
          />
        ))}

      {mode === 'select' &&
        selected &&
        displayPoints.map((point, index) => {
          const next = displayPoints[(index + 1) % displayPoints.length]
          if (!next) return null
          return (
            <RoiMidpointHandle
              key={`mid-${index}`}
              a={point}
              b={next}
              scale={scale}
              onClick={(midDisplay) =>
                onInsertVertex(index, displayToSource(midDisplay, sourceFrame, displayFrame))
              }
            />
          )
        })}

      <RoiSlotLabel points={displayPoints} code={slot.code} scale={scale} />
    </Group>
  )
}
