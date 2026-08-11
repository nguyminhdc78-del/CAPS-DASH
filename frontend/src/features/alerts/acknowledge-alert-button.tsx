import { CheckOutlined } from '@ant-design/icons'
import { Button, Tag } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useErrorMessage } from '@/core/i18n/use-error-message'
import { useAcknowledgeAlertMutation } from './use-alerts-queries'
import type { AlertRecord } from './use-alerts-queries'

interface AcknowledgeAlertButtonProps {
  alert: AlertRecord
  onError: (message: string) => void
}

/** `POST /alerts/{id}/acknowledge` is idempotent server-side (see
 * `alert_service.acknowledge`'s docstring), so a double-click here is
 * harmless - the button just disables itself once acknowledged. */
export function AcknowledgeAlertButton({ alert, onError }: AcknowledgeAlertButtonProps): ReactNode {
  const { t } = useTranslation('alert')
  const toMessage = useErrorMessage()
  const acknowledge = useAcknowledgeAlertMutation()

  if (alert.acknowledged_at) {
    return <Tag color="success">{t('acknowledged')}</Tag>
  }

  return (
    <Button
      size="small"
      icon={<CheckOutlined />}
      loading={acknowledge.isPending}
      onClick={() =>
        acknowledge.mutate(alert.id, { onError: (caught) => onError(toMessage(caught)) })
      }
    >
      {t('acknowledge')}
    </Button>
  )
}
