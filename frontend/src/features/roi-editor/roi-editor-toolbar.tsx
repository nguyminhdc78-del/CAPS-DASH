import {
  AimOutlined,
  DragOutlined,
  EditOutlined,
  ExpandOutlined,
  RedoOutlined,
  SaveOutlined,
  UndoOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
} from '@ant-design/icons'
import { Button, Popconfirm, Segmented, Space, Tooltip, Typography } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { RoiEditorHelpPopover } from './roi-editor-help-popover'
import type { EditorMode } from './roi-editor-types'

/** Toolbar strip above the canvas: mode, zoom, undo/redo, save/discard, help.
 * Pure presentation - every action is a callback prop, kept in sync by
 * roi-editor-page.tsx. */
export function RoiEditorToolbar({
  mode,
  onModeChange,
  zoomPercent,
  onZoomIn,
  onZoomOut,
  onFitToView,
  onZoomTo100,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  dirty,
  onDiscard,
  onSave,
  saveDisabledReason,
  saving,
}: {
  mode: EditorMode
  onModeChange: (mode: EditorMode) => void
  zoomPercent: number
  onZoomIn: () => void
  onZoomOut: () => void
  onFitToView: () => void
  onZoomTo100: () => void
  canUndo: boolean
  canRedo: boolean
  onUndo: () => void
  onRedo: () => void
  dirty: boolean
  onDiscard: () => void
  onSave: () => void
  saveDisabledReason: string | null
  saving: boolean
}): ReactNode {
  const { t } = useTranslation(['roi', 'common'])

  return (
    <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
      <Space wrap>
        <Segmented
          value={mode}
          onChange={(value) => onModeChange(value as EditorMode)}
          options={[
            { value: 'select', icon: <AimOutlined />, label: t('roi:modeSelect') },
            { value: 'draw', icon: <EditOutlined />, label: t('roi:modeDraw') },
            { value: 'pan', icon: <DragOutlined />, label: t('roi:modePan') },
          ]}
        />
        <Space.Compact>
          <Tooltip title={t('roi:zoomOut')}>
            <Button icon={<ZoomOutOutlined />} onClick={onZoomOut} />
          </Tooltip>
          <Button disabled style={{ minWidth: 64 }}>
            {zoomPercent}%
          </Button>
          <Tooltip title={t('roi:zoomIn')}>
            <Button icon={<ZoomInOutlined />} onClick={onZoomIn} />
          </Tooltip>
        </Space.Compact>
        <Button icon={<ExpandOutlined />} onClick={onFitToView}>
          {t('roi:fitToView')}
        </Button>
        <Button onClick={onZoomTo100}>{t('roi:zoom100')}</Button>
        <Space.Compact>
          <Tooltip title={t('roi:undo')}>
            <Button icon={<UndoOutlined />} disabled={!canUndo} onClick={onUndo} />
          </Tooltip>
          <Tooltip title={t('roi:redo')}>
            <Button icon={<RedoOutlined />} disabled={!canRedo} onClick={onRedo} />
          </Tooltip>
        </Space.Compact>
      </Space>

      <Space>
        {dirty && <Typography.Text type="warning">{t('roi:unsavedChanges')}</Typography.Text>}
        <Popconfirm
          title={t('roi:discardConfirmTitle')}
          onConfirm={onDiscard}
          okText={t('common:confirm')}
          cancelText={t('common:cancel')}
          disabled={!dirty}
        >
          <Button disabled={!dirty}>{t('common:cancel')}</Button>
        </Popconfirm>
        <Tooltip title={saveDisabledReason ?? ''}>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={saving}
            disabled={saveDisabledReason !== null}
            onClick={onSave}
          >
            {t('common:save')}
          </Button>
        </Tooltip>
        <RoiEditorHelpPopover />
      </Space>
    </Space>
  )
}
