import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Button, Form, Input } from 'antd'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useErrorMessage } from '@/core/i18n/use-error-message'

interface LoginFormValues {
  username: string
  password: string
}

export function LoginForm({
  onSubmit,
}: {
  onSubmit: (username: string, password: string) => Promise<void>
}): ReactNode {
  const { t } = useTranslation(['auth', 'common'])
  const toMessage = useErrorMessage()
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleFinish = async (values: LoginFormValues): Promise<void> => {
    setSubmitting(true)
    setError(null)
    try {
      await onSubmit(values.username, values.password)
    } catch (caught) {
      // The backend answers identically for an unknown username and a wrong
      // password, on purpose. Do not try to be more specific here.
      setError(toMessage(caught))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Form<LoginFormValues>
      layout="vertical"
      onFinish={(values) => void handleFinish(values)}
      requiredMark={false}
      autoComplete="on"
    >
      {error !== null && (
        <Form.Item>
          <Alert type="error" message={error} showIcon />
        </Form.Item>
      )}

      <Form.Item
        name="username"
        label={t('auth:username')}
        rules={[{ required: true, message: t('auth:usernameRequired') }]}
      >
        <Input prefix={<UserOutlined />} size="large" autoComplete="username" autoFocus />
      </Form.Item>

      <Form.Item
        name="password"
        label={t('auth:password')}
        rules={[{ required: true, message: t('auth:passwordRequired') }]}
      >
        <Input.Password
          prefix={<LockOutlined />}
          size="large"
          autoComplete="current-password"
        />
      </Form.Item>

      <Form.Item>
        <Button type="primary" htmlType="submit" size="large" block loading={submitting}>
          {submitting ? t('auth:signingIn') : t('auth:signIn')}
        </Button>
      </Form.Item>
    </Form>
  )
}
