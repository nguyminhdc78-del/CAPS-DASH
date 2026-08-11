import { CheckCircleOutlined, CloseCircleOutlined, KeyOutlined } from '@ant-design/icons'
import { Button, Popconfirm, Space, Tag, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'

import type { Role } from '@/core/auth/role-ranking'
import type { UserAccount } from './use-users-queries'

dayjs.extend(relativeTime)

/**
 * Two explicit signatures instead of one with an optional second parameter -
 * i18next's real `TFunction` type does not structurally match a plain
 * `(key, options?) => string` under `exactOptionalPropertyTypes`, so this
 * function-builder accepts the shape i18next's `t` actually satisfies.
 */
type Translate = {
  (key: string): string
  (key: string, options: Record<string, unknown>): string
}

const ROLE_LABEL_KEYS: Record<Role, string> = {
  resident: 'auth:roleResident',
  security: 'auth:roleSecurity',
  admin: 'auth:roleAdmin',
}

export interface UsersColumnActions {
  onEdit: (user: UserAccount) => void
  onResetPassword: (user: UserAccount) => void
  onToggleActive: (user: UserAccount) => void
}

/**
 * Column defs kept out of `users-table.tsx` so that file stays a thin
 * wrapper - this is where the actual per-column rendering logic lives.
 */
export function buildUsersColumns(
  t: Translate,
  actions: UsersColumnActions,
): ColumnsType<UserAccount> {
  return [
    { title: t('auth:username'), dataIndex: 'username' },
    { title: t('user:displayName'), dataIndex: 'display_name' },
    {
      title: t('auth:role'),
      dataIndex: 'role',
      render: (role: Role) => <Tag>{t(ROLE_LABEL_KEYS[role])}</Tag>,
    },
    {
      title: t('user:active'),
      dataIndex: 'is_active',
      // State is never colour-only: the tag pairs an icon and a text label
      // with the colour, so it still reads correctly to someone who cannot
      // distinguish the colours at a glance.
      render: (isActive: boolean) =>
        isActive ? (
          <Tag color="success" icon={<CheckCircleOutlined />}>
            {t('user:active')}
          </Tag>
        ) : (
          <Tag color="default" icon={<CloseCircleOutlined />}>
            {t('user:inactive')}
          </Tag>
        ),
    },
    {
      title: t('user:lastLogin'),
      dataIndex: 'last_login_at',
      render: (value: string | null) =>
        value ? (
          <Tooltip title={dayjs(value).format('YYYY-MM-DD HH:mm')}>{dayjs(value).fromNow()}</Tooltip>
        ) : (
          t('user:lastLoginNever')
        ),
    },
    {
      title: t('common:actions'),
      key: 'actions',
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => actions.onEdit(record)}>
            {t('common:edit')}
          </Button>
          <Button
            size="small"
            icon={<KeyOutlined />}
            onClick={() => actions.onResetPassword(record)}
            aria-label={t('user:resetPassword')}
          >
            {t('user:resetPassword')}
          </Button>
          <Popconfirm
            title={
              record.is_active ? t('user:confirmDeactivateTitle') : t('user:confirmActivateTitle')
            }
            description={record.is_active ? t('user:confirmDeactivateContent') : undefined}
            onConfirm={() => actions.onToggleActive(record)}
            okText={t('common:confirm')}
            cancelText={t('common:cancel')}
          >
            <Button size="small" danger={record.is_active}>
              {record.is_active ? t('user:deactivate') : t('user:activate')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]
}
