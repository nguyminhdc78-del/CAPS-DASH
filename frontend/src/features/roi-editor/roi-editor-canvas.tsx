import type Konva from 'konva'
import type { KonvaEventObject } from 'konva/lib/Node'
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Image as KonvaImage, Layer, Stage } from 'react-konva'

import type { FrameSize } from './coordinate-transform'
import { clampToFrame, displayToSource } from './coordinate-transform'
import { RoiDraftPolygon } from './roi-draft-polygon'
import { RoiSlotPolygon } from './roi-slot-polygon'
import type { EditorMode } from './roi-editor-types'
import type { CanvasViewportApi } from './use-canvas-viewport'
import type { RoiEditorApi } from './use-roi-editor-state'

/**
 * `<Stage><Layer>` composition: the snapshot image, every committed polygon,
 * and the in-progress draft, all inside the viewport's zoom/pan transform.
 * Owns pointer-to-coordinate conversion at the Konva boundary ONLY - every
 * point that leaves this file into the reducer is already in source pixels.
 */
export function RoiEditorCanvas({
  image,
  sourceFrame,
  mode,
  editor,
  viewportApi,
  statusBySlotKey,
  onContainerResize,
}: {
  image: HTMLImageElement
  sourceFrame: FrameSize
  mode: EditorMode
  editor: RoiEditorApi
  viewportApi: CanvasViewportApi
  statusBySlotKey: Map<string, 'valid' | 'invalid' | 'warning'>
  onContainerResize: (size: FrameSize) => void
}): ReactNode {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<Konva.Stage>(null)
  const [containerSize, setContainerSize] = useState<FrameSize>({ width: 0, height: 0 })
  const [spacePanning, setSpacePanning] = useState(false)
  const [middlePanning, setMiddlePanning] = useState(false)
  const { displayFrame, viewport, zoomAtPointer, setPan } = viewportApi

  useEffect(() => {
    const el = wrapperRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return
      const size = { width: entry.contentRect.width, height: entry.contentRect.height }
      setContainerSize(size)
      onContainerResize(size)
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [onContainerResize])

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent): void {
      if (e.code === 'Space' && !(document.activeElement instanceof HTMLInputElement)) setSpacePanning(true)
    }
    function onKeyUp(e: KeyboardEvent): void {
      if (e.code === 'Space') setSpacePanning(false)
    }
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
    }
  }, [])

  if (!displayFrame || containerSize.width === 0) {
    return <div ref={wrapperRef} style={{ width: '100%', height: '100%', minHeight: 480 }} />
  }

  const panning = mode === 'pan' || spacePanning || middlePanning

  function handleWheel(e: KonvaEventObject<WheelEvent>): void {
    e.evt.preventDefault()
    const stage = e.target.getStage()
    const pointer = stage?.getPointerPosition()
    if (!stage || !pointer) return
    const factor = e.evt.deltaY > 0 ? 1 / 1.08 : 1.08
    zoomAtPointer(pointer, viewport.scale * factor)
  }

  function handleStageClick(e: KonvaEventObject<MouseEvent>): void {
    if (mode !== 'draw' || panning) return
    const stage = e.target.getStage()
    const pointer = stage?.getRelativePointerPosition()
    if (!stage || !pointer || !displayFrame) return
    const sourcePoint = clampToFrame(displayToSource(pointer, sourceFrame, displayFrame), sourceFrame)
    editor.addVertex(sourcePoint)
  }

  return (
    <div ref={wrapperRef} style={{ width: '100%', height: '100%', minHeight: 480, overflow: 'hidden' }}>
      <Stage
        ref={stageRef}
        width={containerSize.width}
        height={containerSize.height}
        scaleX={viewport.scale}
        scaleY={viewport.scale}
        x={viewport.x}
        y={viewport.y}
        draggable={panning}
        style={{ cursor: panning ? 'grab' : mode === 'draw' ? 'crosshair' : 'default' }}
        onWheel={handleWheel}
        onClick={handleStageClick}
        onDblClick={() => mode === 'draw' && editor.closeDraft()}
        onMouseDown={(e) => {
          if (e.evt.button === 1) setMiddlePanning(true)
        }}
        onMouseUp={(e) => {
          if (e.evt.button === 1) setMiddlePanning(false)
        }}
        onDragMove={(e) => {
          if (e.target !== e.target.getStage()) return
          setPan(e.target.x(), e.target.y())
        }}
      >
        <Layer>
          <KonvaImage image={image} width={displayFrame.width} height={displayFrame.height} listening={false} />

          {editor.state.slots.map((slot) => (
            <RoiSlotPolygon
              key={slot.key}
              slot={slot}
              sourceFrame={sourceFrame}
              displayFrame={displayFrame}
              scale={viewport.scale}
              mode={mode}
              selected={editor.state.selection?.slotKey === slot.key}
              selectedVertex={
                editor.state.selection?.slotKey === slot.key ? editor.state.selection.vertexIndex : null
              }
              status={statusBySlotKey.get(slot.key) ?? 'valid'}
              onSelectPolygon={() => editor.select({ slotKey: slot.key, vertexIndex: null })}
              onSelectVertex={(index) => editor.select({ slotKey: slot.key, vertexIndex: index })}
              onBeginDrag={() => editor.beginDrag()}
              onMoveVertex={(index, point) => editor.moveVertex(slot.key, index, point)}
              onMovePolygon={(dx, dy) => editor.movePolygon(slot.key, dx, dy)}
              onInsertVertex={(afterIndex, point) => editor.insertVertex(slot.key, afterIndex, point)}
              onDeleteVertex={(index) => editor.deleteVertex(slot.key, index)}
            />
          ))}

          {editor.state.draft && (
            <RoiDraftPolygon
              draft={editor.state.draft}
              sourceFrame={sourceFrame}
              displayFrame={displayFrame}
              scale={viewport.scale}
              onCloseAtFirstVertex={() => editor.closeDraft()}
            />
          )}
        </Layer>
      </Stage>
    </div>
  )
}
