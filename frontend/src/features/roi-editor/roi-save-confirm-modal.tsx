import { Alert, Modal, Tag, Typography } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { SlotMapDiff } from './roi-slot-diff'

/** Lists added/modified/removed codes before every save, per phase-11 plan
 * "Save flow" - the operator confirms exactly what changes, every time, not
 * only when a deletion is involved. */
export function RoiSaveConfirmModal({
  open,
  diff,
  saveError,
  saving,
  onConfirm,
  onCancel,
}: {
  open: boolean
  diff: SlotMapDiff | null
  saveError: string | null
  saving: boolean
  onConfirm: () => void
  onCancel: () => void
}): ReactNode {
  const { t } = useTranslation(['roi', 'common'])

  return (
    <Modal
      title={t('roi:saveConfirmTitle')}
      open={open}
      onOk={onConfirm}
      onCancel={onCancel}
      okText={t('common:confirm')}
      cancelText={t('common:cancel')}
      confirmLoading={saving}
      okButtonProps={{ danger: (diff?.removed.length ?? 0) > 0 }}
    >
      {saveError !== null && <Alert type="error" showIcon message={saveError} style={{ marginBottom: 12 }} />}

      {diff && diff.removed.length > 0 && (
        <Alert
          type="warning"
          showIcon
          message={t('roi:saveConfirmRemovedWarning')}
          style={{ marginBottom: 12 }}
        />
      )}

      <DiffSection title={t('roi:saveConfirmAdded')} codes={diff?.added ?? []} color="success" />
      <DiffSection title={t('roi:saveConfirmModified')} codes={diff?.modified ?? []} color="processing" />
      <DiffSection title={t('roi:saveConfirmRemoved')} codes={diff?.removed ?? []} color="error" />

      {diff && diff.added.length === 0 && diff.modified.length === 0 && diff.removed.length === 0 && (
        <Typography.Text type="secondary">{t('roi:saveConfirmNoChanges')}</Typography.Text>
      )}
    </Modal>
  )
}

function DiffSection({
  title,
  codes,
  color,
}: {
  title: string
  codes: string[]
  color: 'success' | 'processing' | 'error'
}): ReactNode {
  if (codes.length === 0) return null
  return (
    <div style={{ marginBottom: 8 }}>
      <Typography.Text strong>{title}</Typography.Text>
      <div style={{ marginTop: 4 }}>
        {codes.map((code) => (
          <Tag key={code} color={color} style={{ marginBottom: 4 }}>
            {code}
          </Tag>
        ))}
      </div>
    </div>
  )
}
