import { BulbOutlined, GlobalOutlined, LogoutOutlined, UserOutlined } from '@ant-design/icons'
import { Avatar, Button, Dropdown, Flex, Tooltip, Typography } from 'antd'
import { useContext } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'

import { LocaleContext } from '@/core/i18n/locale-provider'
import { useAuth } from '@/core/auth/use-auth'
import { useThemeMode } from '@/core/theme/use-theme-config'

import { AppAlertBadge } from './app-alert-badge'

const ROLE_LABEL_KEYS: Record<string, string> = {
  resident: 'auth:roleResident',
  security: 'auth:roleSecurity',
  admin: 'auth:roleAdmin',
}

export function AppHeaderBar(): ReactNode {
  const { t } = useTranslation()
  const { user, logout } = useAuth()
  const locale = useContext(LocaleContext)
  const { mode, toggle } = useThemeMode()
  const navigate = useNavigate()

  const handleLogout = async (): Promise<void> => {
    await logout()
    void navigate('/login', { replace: true })
  }

  return (
    <Flex align="center" justify="space-between" style={{ height: '100%' }}>
      <Typography.Text strong style={{ fontSize: 16 }}>
        {t('common:appSubtitle')}
      </Typography.Text>

      <Flex align="center" gap={8}>
        <AppAlertBadge />

        <Tooltip title={t('common:language')}>
          <Button
            type="text"
            icon={<GlobalOutlined />}
            onClick={() => locale?.setLanguage(locale.language === 'vi' ? 'en' : 'vi')}
          >
            {locale?.language.toUpperCase()}
          </Button>
        </Tooltip>

        <Tooltip title={mode === 'dark' ? t('common:themeLight') : t('common:themeDark')}>
          <Button type="text" icon={<BulbOutlined />} onClick={toggle} />
        </Tooltip>

        <Dropdown
          menu={{
            items: [
              {
                key: 'role',
                disabled: true,
                label: t(ROLE_LABEL_KEYS[user?.role ?? 'resident'] ?? 'auth:roleResident'),
              },
              { type: 'divider' },
              {
                key: 'logout',
                icon: <LogoutOutlined />,
                label: t('auth:signOut'),
                onClick: () => void handleLogout(),
              },
            ],
          }}
        >
          <Button type="text">
            <Avatar size="small" icon={<UserOutlined />} />
            <span style={{ marginLeft: 8 }}>{user?.display_name || user?.username}</span>
          </Button>
        </Dropdown>
      </Flex>
    </Flex>
  )
}
