import { Card, Typography } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, useLocation, useNavigate } from 'react-router'

import { CenteredLayout } from '@/app/app-layout'
import { useAuth } from '@/core/auth/use-auth'
import { LoginForm } from './login-form'

interface LocationState {
  from?: string
}

export default function LoginPage(): ReactNode {
  const { t } = useTranslation(['auth', 'common'])
  const { login, status } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const from = (location.state as LocationState | null)?.from ?? '/'

  // Already signed in - send them where they were headed rather than showing
  // a form that would immediately redirect anyway.
  if (status === 'authenticated') return <Navigate to={from} replace />

  const handleSubmit = async (username: string, password: string): Promise<void> => {
    await login(username, password)
    void navigate(from, { replace: true })
  }

  return (
    <CenteredLayout className="droom-auth">
      <Card className="droom-auth-card" style={{ width: 400 }} styles={{ body: { padding: 32 } }}>
        <div className="droom-auth-mark" aria-hidden>
          C
        </div>
        <Typography.Title level={3} style={{ textAlign: 'center', marginBottom: 4 }}>
          {t('common:appName')}
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ textAlign: 'center' }}>
          {t('auth:welcome')}
        </Typography.Paragraph>
        <LoginForm onSubmit={handleSubmit} />
      </Card>
    </CenteredLayout>
  )
}
