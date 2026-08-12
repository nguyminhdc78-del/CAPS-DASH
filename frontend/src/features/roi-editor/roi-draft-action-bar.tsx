import { CheckOutlined, CloseOutlined, DeleteOutlined, RollbackOutlined } from '@ant-design/icons'
import { Alert, Button, Space } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { MIN_SLOT_VERTICES } from './roi-editor-reducer-helpers'

/**
 * The actions that used to exist only as key presses and gestures.
 *
 * Finishing a polygon was double-click / Enter / clicking the first vertex;
 * abandoning one was Escape; deleting a slot was Del. All of them are real,
 * all of them were invisible, and none of them exist at all on a tablet with
 * no keyboard - which is a device this dashboard is meant to be used from.
 * They are buttons now. The shortcuts still work.
 *
 * Rendered directly under the canvas so it sits where the operator is already
 * looking, not up in the toolbar.
 */
export function RoiDraftActionBar({
  draftLength,
  hasSelection,
  selectionIsVertex,
  onFinish,
  onRemoveLastPoint,
  onCancelDraft,
  onDeleteSelected,
}: {
  draftLength: number
  hasSelection: boolean
  selectionIsVertex: boolean
  onFinish: () => void
  onRemoveLastPoint: () => void
  onCancelDraft: () => void
  onDeleteSelected: () => void
}): ReactNode {
  const { t } = useTranslation(['roi', 'common'])
  const drawing = draftLength > 0
  const canFinish = draftLength >= MIN_SLOT_VERTICES

  if (!drawing && !hasSelection) return null

  return (
    <Space wrap>
      {drawing && (
        <>
          <Button type="primary" icon={<CheckOutlined />} disabled={!canFinish} onClick={onFinish}>
            {t('roi:finishPolygon')}
          </Button>
          <Button icon={<RollbackOutlined />} onClick={onRemoveLastPoint}>
            {t('roi:removeLastPoint')}
          </Button>
          <Button icon={<CloseOutlined />} onClick={onCancelDraft}>
            {t('roi:cancelDraft')}
          </Button>
          <Alert
            type={canFinish ? 'success' : 'info'}
            showIcon
            style={{ padding: '2px 10px' }}
            message={
              canFinish
                ? t('roi:draftReady', { count: draftLength })
                : t('roi:draftNeedsMore', { count: draftLength, min: MIN_SLOT_VERTICES })
            }
          />
        </>
      )}

      {!drawing && hasSelection && (
        <Button danger icon={<DeleteOutlined />} onClick={onDeleteSelected}>
          {selectionIsVertex ? t('roi:deleteVertex') : t('roi:deleteSlot')}
        </Button>
      )}
    </Space>
  )
}
