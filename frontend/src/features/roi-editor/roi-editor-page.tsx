import { Alert, Card, Modal, Space } from 'antd'
import { useCallback, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router'

import type { FrameSize } from './coordinate-transform'
import { RoiEditorCanvas } from './roi-editor-canvas'
import { RoiEditorEmptyState } from './roi-editor-empty-state'
import { RoiEditorToolbar } from './roi-editor-toolbar'
import type { EditorMode } from './roi-editor-types'
import { RoiSaveConfirmModal } from './roi-save-confirm-modal'
import { RoiSlotInspector } from './roi-slot-inspector'
import { useCanvasViewport } from './use-canvas-viewport'
import { useRoiEditorData } from './use-roi-editor-data'
import { useRoiEditorSave } from './use-roi-editor-save'
import { useRoiEditorState } from './use-roi-editor-state'
import { useRoiKeyboardShortcuts } from './use-roi-keyboard-shortcuts'
import { useUnsavedChangesGuard } from './use-unsaved-changes-guard'

/** Route shell: `/cameras/:cameraId/roi`, admin-only. Composes the data,
 * editor-state, viewport and save hooks; the heavy lifting lives in each of
 * those. See phase-11 plan "Architecture". */
export default function RoiEditorPage(): ReactNode {
  const { t } = useTranslation(['roi', 'common'])
  const { cameraId: cameraIdParam } = useParams<{ cameraId: string }>()
  const cameraId = Number(cameraIdParam)

  const editor = useRoiEditorState()
  const { snapshot, slotMapQuery, frameMismatch } = useRoiEditorData(cameraId, editor)
  const viewportApi = useCanvasViewport()
  const save = useRoiEditorSave(
    cameraId,
    editor,
    snapshot.image ? { width: snapshot.image.naturalWidth, height: snapshot.image.naturalHeight } : null,
  )
  const blocker = useUnsavedChangesGuard(editor.state.dirty)

  const [mode, setMode] = useState<EditorMode>('select')
  const [containerSize, setContainerSize] = useState<FrameSize>({ width: 0, height: 0 })
  const hasAutoFitted = useRef(false)

  const handleContainerResize = useCallback(
    (size: FrameSize) => {
      setContainerSize(size)
      if (!hasAutoFitted.current && snapshot.image && size.width > 0) {
        viewportApi.fitToView(size, { width: snapshot.image.naturalWidth, height: snapshot.image.naturalHeight })
        hasAutoFitted.current = true
      }
    },
    [snapshot.image, viewportApi],
  )

  useRoiKeyboardShortcuts({
    onUndo: editor.undo,
    onRedo: editor.redo,
    onDeleteSelected: () => {
      const selection = editor.state.selection
      if (selection && selection.vertexIndex !== null) editor.deleteVertex(selection.slotKey, selection.vertexIndex)
    },
    onCloseDraft: () => mode === 'draw' && editor.closeDraft(),
    onCancelDraft: () => editor.cancelDraft(),
  })

  const statusBySlotKey = useMemo(() => {
    const map = new Map<string, 'valid' | 'invalid' | 'warning'>()
    for (const error of save.validation.errors) map.set(error.slotKey, 'invalid')
    for (const warning of save.validation.warnings) if (!map.has(warning.slotKey)) map.set(warning.slotKey, 'warning')
    return map
  }, [save.validation])

  const selectedSlot = editor.state.slots.find((slot) => slot.key === editor.state.selection?.slotKey) ?? null
  const saveDisabledReason = save.validation.errors.length > 0 ? t('roi:saveBlockedInvalid') : null

  if (snapshot.status !== 'ready' || !snapshot.image || slotMapQuery.isLoading) {
    return (
      <Card title={t('roi:title', { cameraId })}>
        <RoiEditorEmptyState
          loading={snapshot.status === 'loading' || slotMapQuery.isLoading}
          error={snapshot.status === 'error' ? snapshot.error : (slotMapQuery.error ?? null)}
          onRetry={snapshot.retry}
        />
      </Card>
    )
  }

  const sourceFrame: FrameSize = { width: snapshot.image.naturalWidth, height: snapshot.image.naturalHeight }
  const zoomPercent = Math.round(viewportApi.viewport.scale * 100)
  const center = { x: containerSize.width / 2, y: containerSize.height / 2 }

  return (
    <Card title={t('roi:title', { cameraId })} styles={{ body: { padding: 12 } }}>
      <Space direction="vertical" style={{ width: '100%' }}>
        {frameMismatch && <Alert type="warning" showIcon message={t('roi:frameMismatchWarning')} />}
        {save.warmupBannerOpen && (
          <Alert
            type="info"
            showIcon
            closable
            onClose={save.dismissWarmupBanner}
            message={t('roi:saveWarmupBanner')}
          />
        )}

        <RoiEditorToolbar
          mode={mode}
          onModeChange={setMode}
          zoomPercent={zoomPercent}
          onZoomIn={() => viewportApi.zoomAtPointer(center, viewportApi.viewport.scale * 1.2)}
          onZoomOut={() => viewportApi.zoomAtPointer(center, viewportApi.viewport.scale / 1.2)}
          onFitToView={() => viewportApi.fitToView(containerSize, sourceFrame)}
          onZoomTo100={() => viewportApi.zoomTo100(containerSize, sourceFrame)}
          canUndo={editor.canUndo}
          canRedo={editor.canRedo}
          onUndo={editor.undo}
          onRedo={editor.redo}
          dirty={editor.state.dirty}
          onDiscard={() => editor.state.sourceFrame && editor.loadSlots(editor.state.baseline, editor.state.sourceFrame)}
          onSave={save.requestSave}
          saveDisabledReason={saveDisabledReason}
          saving={save.saving}
        />

        <div style={{ display: 'flex', gap: 12, height: '70vh' }}>
          <div style={{ flex: 1, minWidth: 0, border: '1px solid #d9d9d9', borderRadius: 6 }}>
            <RoiEditorCanvas
              image={snapshot.image}
              sourceFrame={sourceFrame}
              mode={mode}
              editor={editor}
              viewportApi={viewportApi}
              statusBySlotKey={statusBySlotKey}
              onContainerResize={handleContainerResize}
            />
          </div>
          {selectedSlot && (
            <RoiSlotInspector
              slot={selectedSlot}
              onRename={(patch) => editor.renameSlot(selectedSlot.key, patch)}
              onDelete={() => editor.deleteSlot(selectedSlot.key)}
            />
          )}
        </div>
      </Space>

      <RoiSaveConfirmModal
        open={save.confirmOpen}
        diff={save.diff}
        saveError={save.saveError}
        saving={save.saving}
        onConfirm={save.confirmSave}
        onCancel={save.cancelConfirm}
      />

      <Modal
        title={t('roi:unsavedChangesTitle')}
        open={blocker.state === 'blocked'}
        onOk={() => blocker.proceed?.()}
        onCancel={() => blocker.reset?.()}
        okText={t('roi:leaveAnyway')}
        cancelText={t('common:cancel')}
        okButtonProps={{ danger: true }}
      >
        {t('roi:unsavedChangesBody')}
      </Modal>
    </Card>
  )
}
