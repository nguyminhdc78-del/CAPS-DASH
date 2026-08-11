import { CloudUploadOutlined } from '@ant-design/icons'
import { App, Button, Card, Typography } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useErrorMessage } from '@/core/i18n/use-error-message'
import { useCreateBackupMutation } from './use-system-queries'
import type { BackupResult } from './use-system-queries'

/** Triggers `POST /system/backup` (a `sqlite3.Connection.backup()` copy, run
 * off the request thread server-side - see `backup_service.py`) and shows
 * the resulting file name and size once it lands. */
export function BackupPanel(): ReactNode {
  const { t } = useTranslation('system')
  const { message } = App.useApp()
  const toMessage = useErrorMessage()
  const createBackup = useCreateBackupMutation()
  const [lastBackup, setLastBackup] = useState<BackupResult | null>(null)

  const handleBackup = async (): Promise<void> => {
    try {
      const result = await createBackup.mutateAsync()
      setLastBackup(result)
      void message.success(t('backupSucceeded'))
    } catch (caught) {
      void message.error(toMessage(caught))
    }
  }

  return (
    <Card title={t('backup')}>
      <Typography.Paragraph type="secondary">{t('backupDescription')}</Typography.Paragraph>
      <Button
        type="primary"
        icon={<CloudUploadOutlined />}
        loading={createBackup.isPending}
        onClick={() => void handleBackup()}
      >
        {t('backupNow')}
      </Button>
      {lastBackup && (
        <Typography.Paragraph style={{ marginTop: 12 }}>
          {t('backupLastResult', {
            path: lastBackup.backup_path,
            size: (lastBackup.size_bytes / (1024 * 1024)).toFixed(1),
            time: dayjs(lastBackup.created_at).format('YYYY-MM-DD HH:mm:ss'),
          })}
        </Typography.Paragraph>
      )}
    </Card>
  )
}
