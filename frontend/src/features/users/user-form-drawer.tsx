import { Alert, Button, Drawer, Form, Input, Select, Space } from 'antd'
import type { FormInstance } from 'antd'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '@/core/api/api-error'
import { ROLES } from '@/core/auth/role-ranking'
import type { Role } from '@/core/auth/role-ranking'
import {
  USER_PASSWORD_MAX_LENGTH,
  USER_PASSWORD_MIN_LENGTH,
  USER_USERNAME_MAX_LENGTH,
  USER_USERNAME_MIN_LENGTH,
} from '@/core/constants/ui-constants'
import { useErrorMessage } from '@/core/i18n/use-error-message'
import { useCreateUserMutation, useUpdateUserMutation } from './use-users-queries'
import type { UserAccount } from './use-users-queries'

interface FormValues {
  username: string
  password: string
  display_name: string
  role: Role
}

const ROLE_LABEL_KEYS: Record<Role, string> = {
  resident: 'auth:roleResident',
  security: 'auth:roleSecurity',
  admin: 'auth:roleAdmin',
}

const USERNAME_PATTERN = /^[A-Za-z0-9._-]+$/

/**
 * The backend's 422 handler ships per-field pydantic messages as
 * `details.fields`, e.g. `{ username: "String should match pattern..." }`.
 * There is no error CODE per field - only pydantic's own text - so unlike
 * the top-level alert below, this is the one place a raw backend message
 * reaches the screen. Returns true when it found something to attach, so
 * the caller knows whether a generic alert is still needed.
 */
function applyFieldErrors(form: FormInstance, error: unknown): boolean {
  if (!(error instanceof ApiError) || error.code !== 'VALIDATION_FAILED') return false
  const fields = error.details['fields']
  if (typeof fields !== 'object' || fields === null) return false
  const entries = Object.entries(fields as Record<string, unknown>).filter(
    (entry): entry is [string, string] => typeof entry[1] === 'string',
  )
  if (entries.length === 0) return false
  form.setFields(entries.map(([name, message]) => ({ name, errors: [message] })))
  return true
}

export function UserFormDrawer({
  open,
  user,
  onClose,
}: {
  open: boolean
  user: UserAccount | null
  onClose: () => void
}): ReactNode {
  const { t } = useTranslation(['user', 'auth', 'common'])
  const toMessage = useErrorMessage()
  const [form] = Form.useForm<FormValues>()
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const isEditing = user !== null
  const createUser = useCreateUserMutation()
  const updateUser = useUpdateUserMutation()

  useEffect(() => {
    if (!open) return
    setSubmitError(null)
    form.resetFields()
    if (user) {
      form.setFieldsValue({ username: user.username, display_name: user.display_name, role: user.role })
    }
  }, [open, user, form])

  const handleFinish = async (values: FormValues): Promise<void> => {
    setSubmitting(true)
    setSubmitError(null)
    try {
      if (user) {
        await updateUser.mutateAsync({
          id: user.id,
          display_name: values.display_name,
          role: values.role,
        })
      } else {
        await createUser.mutateAsync(values)
      }
      onClose()
    } catch (caught) {
      if (!applyFieldErrors(form, caught)) setSubmitError(toMessage(caught))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Drawer
      title={isEditing ? t('user:editUser') : t('user:addUser')}
      open={open}
      onClose={onClose}
      destroyOnHidden
      width={420}
      extra={
        <Space>
          <Button onClick={onClose}>{t('common:cancel')}</Button>
          <Button type="primary" loading={submitting} onClick={() => void form.submit()}>
            {t('common:save')}
          </Button>
        </Space>
      }
    >
      {submitError !== null && (
        <Alert type="error" showIcon message={submitError} style={{ marginBottom: 16 }} />
      )}

      <Form<FormValues> form={form} layout="vertical" onFinish={(v) => void handleFinish(v)}>
        <Form.Item
          name="username"
          label={t('auth:username')}
          rules={[
            { required: true, message: t('user:usernameRequired') },
            {
              min: USER_USERNAME_MIN_LENGTH,
              max: USER_USERNAME_MAX_LENGTH,
              message: t('user:usernameLength'),
            },
            { pattern: USERNAME_PATTERN, message: t('user:usernamePattern') },
          ]}
        >
          <Input disabled={isEditing} autoComplete="off" />
        </Form.Item>

        {!isEditing && (
          <Form.Item
            name="password"
            label={t('auth:password')}
            rules={[
              { required: true, message: t('user:passwordRequired') },
              {
                min: USER_PASSWORD_MIN_LENGTH,
                max: USER_PASSWORD_MAX_LENGTH,
                message: t('user:passwordLength'),
              },
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        )}

        <Form.Item
          name="display_name"
          label={t('user:displayName')}
          rules={[{ max: 120, message: t('user:displayNameLength') }]}
        >
          <Input autoComplete="off" />
        </Form.Item>

        <Form.Item
          name="role"
          label={t('auth:role')}
          initialValue="resident"
          rules={[{ required: true }]}
        >
          <Select options={ROLES.map((role) => ({ value: role, label: t(ROLE_LABEL_KEYS[role]) }))} />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
