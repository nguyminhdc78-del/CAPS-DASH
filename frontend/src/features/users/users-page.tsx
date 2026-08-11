import { PlusOutlined } from '@ant-design/icons'
import { App, Button, Card } from 'antd'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useErrorMessage } from '@/core/i18n/use-error-message'
import { ResetPasswordModal } from './reset-password-modal'
import { UserFormDrawer } from './user-form-drawer'
import { useUpdateUserMutation, useUsersQuery } from './use-users-queries'
import type { UserAccount } from './use-users-queries'
import { UsersTable } from './users-table'

export default function UsersPage(): ReactNode {
  const { t } = useTranslation(['user', 'system', 'common'])
  const { message } = App.useApp()
  const toMessage = useErrorMessage()

  const { data, isLoading } = useUsersQuery()
  const toggleActive = useUpdateUserMutation()

  const [editingUser, setEditingUser] = useState<UserAccount | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [resetTarget, setResetTarget] = useState<UserAccount | null>(null)

  const handleAdd = (): void => {
    setEditingUser(null)
    setDrawerOpen(true)
  }

  const handleEdit = (user: UserAccount): void => {
    setEditingUser(user)
    setDrawerOpen(true)
  }

  const handleToggleActive = async (user: UserAccount): Promise<void> => {
    try {
      await toggleActive.mutateAsync({ id: user.id, is_active: !user.is_active })
      void message.success(t('common:saved'))
    } catch (caught) {
      // USER_LAST_ADMIN lands here as a readable sentence, not a generic
      // failure - useErrorMessage keys off the code, and errors.json has a
      // dedicated entry explaining exactly why the change was refused.
      void message.error(toMessage(caught))
    }
  }

  return (
    <Card
      title={t('system:users')}
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
          {t('user:addUser')}
        </Button>
      }
    >
      <UsersTable
        data={data ?? []}
        loading={isLoading}
        onEdit={handleEdit}
        onResetPassword={setResetTarget}
        onToggleActive={(user) => void handleToggleActive(user)}
      />

      <UserFormDrawer open={drawerOpen} user={editingUser} onClose={() => setDrawerOpen(false)} />

      <ResetPasswordModal user={resetTarget} onClose={() => setResetTarget(null)} />
    </Card>
  )
}
