import { ReloadOutlined } from '@ant-design/icons'
import { Button, Empty } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useErrorMessage } from '@/core/i18n/use-error-message'

/** No snapshot -> a clear empty state with retry, never a blank canvas
 * (phase-11 plan requirement). Shown for both the loading and error cases so
 * the operator is never staring at nothing while a camera is unreachable. */
export function RoiEditorEmptyState({
  loading,
  error,
  onRetry,
}: {
  loading: boolean
  error: unknown
  onRetry: () => void
}): ReactNode {
  const { t } = useTranslation(['roi', 'common'])
  const toMessage = useErrorMessage()

  return (
    <Empty
      style={{ padding: '64px 0' }}
      description={
        loading
          ? t('roi:snapshotLoading')
          : error !== null
            ? toMessage(error)
            : t('roi:snapshotUnavailable')
      }
    >
      {!loading && (
        <Button icon={<ReloadOutlined />} onClick={onRetry}>
          {t('common:retry')}
        </Button>
      )}
    </Empty>
  )
}
