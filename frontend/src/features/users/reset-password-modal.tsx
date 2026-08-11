import { CopyOutlined } from '@ant-design/icons'
import { Alert, App, Button, Input, Modal, Space, Typography } from 'antd'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useErrorMessage } from '@/core/i18n/use-error-message'
import { copyText } from '@/shared/utils/copy-text'
import { useResetPasswordMutation } from './use-users-queries'
import type { UserAccount } from './use-users-queries'

/**
 * 16 characters from a mixed alphabet, generated with `crypto.getRandomValues`
 * rather than `Math.random` - this value becomes an account's password, so it
 * needs to be unguessable, not merely different each time.
 */
function generatePassword(): string {
  const charset = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%^&*'
  const bytes = new Uint32Array(16)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (n) => charset[n % charset.length]).join('')
}

/**
 * Generates a password client-side, submits it, and shows it exactly once.
 *
 * The backend takes the new password as input rather than generating one
 * itself (`ResetPasswordRequest.new_password`), so this modal is the only
 * place a generated password exists. It is held only in component state -
 * never written to storage, never logged - and the field clears the moment
 * the modal closes.
 */
export function ResetPasswordModal({
  user,
  onClose,
}: {
  user: UserAccount | null
  onClose: () => void
}): ReactNode {
  const { t } = useTranslation(['user', 'common'])
  const { message } = App.useApp()
  const toMessage = useErrorMessage()
  const resetPassword = useResetPasswordMutation()

  const [password, setPassword] = useState('')
  const [revealed, setRevealed] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (user) {
      setPassword(generatePassword())
      setRevealed(false)
      setError(null)
    }
  }, [user])

  if (user === null) return null

  const handleConfirm = async (): Promise<void> => {
    setSubmitting(true)
    setError(null)
    try {
      await resetPassword.mutateAsync({ id: user.id, newPassword: password })
      setRevealed(true)
    } catch (caught) {
      setError(toMessage(caught))
    } finally {
      setSubmitting(false)
    }
  }

  const handleCopy = async (): Promise<void> => {
    if (await copyText(password)) {
      void message.success(t('common:copied'))
      return
    }
    // Never claim a copy that did not happen: this password is shown once,
    // and an operator who trusts a false "copied" loses it entirely.
    void message.warning(t('common:copyFailed'))
  }

  const handleClose = (): void => {
    setPassword('')
    setRevealed(false)
    onClose()
  }

  return (
    <Modal
      title={t('user:resetPasswordFor', { username: user.username })}
      open
      onCancel={handleClose}
      footer={
        revealed ? (
          <Button type="primary" onClick={handleClose}>
            {t('common:close')}
          </Button>
        ) : (
          <Space>
            <Button onClick={handleClose}>{t('common:cancel')}</Button>
            <Button type="primary" loading={submitting} onClick={() => void handleConfirm()}>
              {t('common:confirm')}
            </Button>
          </Space>
        )
      }
    >
      {error !== null && (
        <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />
      )}

      {revealed ? (
        <>
          <Alert
            type="warning"
            showIcon
            message={t('user:passwordShownOnce')}
            style={{ marginBottom: 12 }}
          />
          <Space.Compact style={{ width: '100%' }}>
            <Input readOnly value={password} />
            <Button
              icon={<CopyOutlined />}
              onClick={() => void handleCopy()}
              aria-label={t('common:copy')}
            />
          </Space.Compact>
        </>
      ) : (
        <Typography.Paragraph>{t('user:resetPasswordConfirm')}</Typography.Paragraph>
      )}
    </Modal>
  )
}
