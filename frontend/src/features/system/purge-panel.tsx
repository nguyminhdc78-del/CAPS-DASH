import { DeleteOutlined } from '@ant-design/icons'
import { App, Button, Card, Descriptions, Input, InputNumber, Space, Typography } from 'antd'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useErrorMessage } from '@/core/i18n/use-error-message'
import { usePurgeMutation } from './use-system-queries'
import type { PurgeResult } from './use-system-queries'

/**
 * Destructive operations get friction: preview (dry run) first, then a
 * typed word before the real delete fires.
 *
 * `PurgeRequestInput.dry_run` defaults `true` server-side, but this panel
 * always sends it explicitly - relying on a server default for the branch
 * that decides whether data is actually deleted is exactly the kind of gap
 * that turns "preview" into "oops" on a future refactor. The preview result
 * is invalidated whenever the retention window changes or a real purge
 * completes, so a stale preview can never be confirmed against different
 * parameters than what it showed.
 */
export function PurgePanel(): ReactNode {
  const { t } = useTranslation('system')
  const { message } = App.useApp()
  const toMessage = useErrorMessage()
  const purge = usePurgeMutation()

  const [olderThanMonths, setOlderThanMonths] = useState<number | null>(null)
  const [preview, setPreview] = useState<PurgeResult | null>(null)
  const [confirmText, setConfirmText] = useState('')

  const confirmWord = t('purgeConfirmWord')

  const runPreview = async (): Promise<void> => {
    setConfirmText('')
    try {
      const result = await purge.mutateAsync({
        older_than_months: olderThanMonths ?? undefined,
        dry_run: true,
      })
      setPreview(result)
    } catch (caught) {
      void message.error(toMessage(caught))
    }
  }

  const runPurge = async (): Promise<void> => {
    try {
      const result = await purge.mutateAsync({
        older_than_months: olderThanMonths ?? undefined,
        dry_run: false,
      })
      void message.success(t('purgeSucceeded'))
      setPreview(result)
      setConfirmText('')
    } catch (caught) {
      void message.error(toMessage(caught))
    }
  }

  return (
    <Card title={t('purge')}>
      <Typography.Paragraph type="secondary">{t('purgeDescription')}</Typography.Paragraph>
      <Space wrap style={{ marginBottom: 12 }}>
        <InputNumber
          min={1}
          max={60}
          placeholder={t('retentionMonths')}
          value={olderThanMonths}
          onChange={(value) => {
            setOlderThanMonths(typeof value === 'number' ? value : null)
            setPreview(null)
            setConfirmText('')
          }}
        />
        <Button onClick={() => void runPreview()} loading={purge.isPending}>
          {t('purgePreview')}
        </Button>
      </Space>

      {preview && (
        <>
          <Descriptions size="small" bordered column={1} style={{ marginBottom: 12 }}>
            <Descriptions.Item label={t('purgeHistoryRows')}>
              {preview.deleted_history_rows}
            </Descriptions.Item>
            <Descriptions.Item label={t('purgeAlertRows')}>
              {preview.deleted_alert_rows}
            </Descriptions.Item>
          </Descriptions>

          <Typography.Paragraph>{t('purgeTypeToConfirm', { word: confirmWord })}</Typography.Paragraph>
          <Space>
            <Input
              value={confirmText}
              onChange={(event) => setConfirmText(event.target.value)}
              placeholder={confirmWord}
              style={{ width: 160 }}
              aria-label={t('purgeConfirmInputLabel')}
            />
            <Button
              danger
              icon={<DeleteOutlined />}
              disabled={confirmText !== confirmWord}
              loading={purge.isPending}
              onClick={() => void runPurge()}
            >
              {t('purgeNow')}
            </Button>
          </Space>
        </>
      )}
    </Card>
  )
}
