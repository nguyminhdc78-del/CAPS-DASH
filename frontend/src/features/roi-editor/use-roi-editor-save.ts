import { useMemo, useState } from 'react'
import { App } from 'antd'
import { useTranslation } from 'react-i18next'

import { useErrorMessage } from '@/core/i18n/use-error-message'
import type { FrameSize } from './coordinate-transform'
import { validateAll } from './polygon-validation'
import { diffSlots } from './roi-slot-diff'
import type { SlotMapDiff } from './roi-slot-diff'
import { buildSlotMapPayload } from './slot-map-payload'
import { useSaveSlotMapMutation } from './use-roi-editor-queries'
import type { RoiEditorApi } from './use-roi-editor-state'

/**
 * Save flow: validate -> diff vs baseline -> confirm dialog -> PUT ->
 * MARK_SAVED -> warm-up banner. See phase-11 plan "Save flow".
 *
 * `allow_delete` is set ONLY when the diff has removed codes AND the
 * operator confirms - never speculatively. The backend refuses a map that
 * would silently drop codes, because deleting a `parking_slots` row cascades
 * its `slot_state_history` away (slot_map_service.py docstring).
 */
export function useRoiEditorSave(cameraId: number, editor: RoiEditorApi, snapshotFrame: FrameSize | null) {
  const { t } = useTranslation(['roi'])
  const { message } = App.useApp()
  const toMessage = useErrorMessage()
  const saveMutation = useSaveSlotMapMutation(cameraId)

  const [confirmOpen, setConfirmOpen] = useState(false)
  const [diff, setDiff] = useState<SlotMapDiff | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [warmupBannerOpen, setWarmupBannerOpen] = useState(false)

  const validation = useMemo(() => validateAll(editor.state.slots), [editor.state.slots])

  function requestSave(): void {
    if (validation.errors.length > 0 || !snapshotFrame) return
    setSaveError(null)
    setDiff(diffSlots(editor.state.baseline, editor.state.slots))
    setConfirmOpen(true)
  }

  async function confirmSave(): Promise<void> {
    if (!diff || !snapshotFrame) return
    const payload = buildSlotMapPayload(editor.state.slots, snapshotFrame, diff.removed.length > 0)
    try {
      await saveMutation.mutateAsync(payload)
      editor.markSaved()
      setConfirmOpen(false)
      setWarmupBannerOpen(true)
      void message.success(t('roi:saveSuccess'))
    } catch (caught) {
      setSaveError(toMessage(caught))
    }
  }

  return {
    validation,
    confirmOpen,
    diff,
    saveError,
    warmupBannerOpen,
    saving: saveMutation.isPending,
    requestSave,
    confirmSave: () => void confirmSave(),
    cancelConfirm: () => setConfirmOpen(false),
    dismissWarmupBanner: () => setWarmupBannerOpen(false),
  }
}

export type RoiEditorSaveApi = ReturnType<typeof useRoiEditorSave>
