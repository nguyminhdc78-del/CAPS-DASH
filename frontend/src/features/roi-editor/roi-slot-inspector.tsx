import { DeleteOutlined } from '@ant-design/icons'
import { Button, Card, Input, Popconfirm, Space } from 'antd'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { CAMERA_CODE_MAX_LENGTH, CAMERA_FLOOR_MAX_LENGTH } from '@/core/constants/ui-constants'
import type { EditorSlot } from './roi-editor-types'

/** Inline rename panel for the selected polygon - code (required, unique)
 * and floor. Field limits mirror `SlotMapEntry` in camera_schemas.py, which
 * happen to match the camera's own code/floor limits already in
 * ui-constants.ts. */
export function RoiSlotInspector({
  slot,
  onRename,
  onDelete,
}: {
  slot: EditorSlot
  onRename: (patch: { code?: string; floor?: string }) => void
  onDelete: () => void
}): ReactNode {
  const { t } = useTranslation(['roi', 'common'])
  const [code, setCode] = useState(slot.code)
  const [floor, setFloor] = useState(slot.floor)

  useEffect(() => {
    setCode(slot.code)
    setFloor(slot.floor)
  }, [slot.key, slot.code, slot.floor])

  const commitCode = (): void => {
    if (code !== slot.code) onRename({ code })
  }
  const commitFloor = (): void => {
    if (floor !== slot.floor) onRename({ floor })
  }

  return (
    <Card size="small" title={t('roi:slotInspectorTitle')} style={{ width: 260 }}>
      <Space direction="vertical" style={{ width: '100%' }}>
        <div>
          <label htmlFor="roi-slot-code">{t('roi:slotCode')}</label>
          <Input
            id="roi-slot-code"
            value={code}
            maxLength={CAMERA_CODE_MAX_LENGTH}
            onChange={(e) => setCode(e.target.value)}
            onBlur={commitCode}
            onPressEnter={commitCode}
            status={code.trim().length === 0 ? 'error' : ''}
          />
        </div>
        <div>
          <label htmlFor="roi-slot-floor">{t('roi:slotFloor')}</label>
          <Input
            id="roi-slot-floor"
            value={floor}
            maxLength={CAMERA_FLOOR_MAX_LENGTH}
            onChange={(e) => setFloor(e.target.value)}
            onBlur={commitFloor}
            onPressEnter={commitFloor}
          />
        </div>
        <Popconfirm
          title={t('roi:deleteSlotConfirm')}
          onConfirm={onDelete}
          okText={t('common:confirm')}
          cancelText={t('common:cancel')}
        >
          <Button danger icon={<DeleteOutlined />} block>
            {t('roi:deleteSlot')}
          </Button>
        </Popconfirm>
      </Space>
    </Card>
  )
}
