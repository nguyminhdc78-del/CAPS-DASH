import { Button, Result } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'

export function NotFoundPage(): ReactNode {
  const { t } = useTranslation('common')
  const navigate = useNavigate()

  return (
    <Result
      status="404"
      title="404"
      subTitle={t('notFoundTitle')}
      extra={
        <Button type="primary" onClick={() => void navigate('/')}>
          {t('back')}
        </Button>
      }
    />
  )
}
