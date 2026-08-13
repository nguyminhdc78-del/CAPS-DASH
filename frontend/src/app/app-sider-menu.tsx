import { Menu } from 'antd'
import { useMemo } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router'

import { hasAtLeastRole } from '@/core/auth/role-ranking'
import { useAuth } from '@/core/auth/use-auth'
import { APP_ROUTES } from './route-definitions'

export function AppSiderMenu(): ReactNode {
  const { user } = useAuth()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()

  // Built from the same array the router guards with, filtered by the same
  // rank comparison - a visible item is always one the user can actually open.
  const items = useMemo(
    () =>
      APP_ROUTES.filter(
        (route) => route.labelKey !== undefined && hasAtLeastRole(user?.role, route.minRole),
      ).map((route) => ({
        key: route.path,
        icon: route.icon,
        label: t(route.labelKey as string),
      })),
    [user?.role, t],
  )

  const selected = useMemo(() => {
    // Longest matching prefix, so /cameras/01/live keeps /cameras highlighted.
    const match = APP_ROUTES.filter(
      (route) => route.path !== '/' && location.pathname.startsWith(route.path),
    ).sort((a, b) => b.path.length - a.path.length)[0]
    return [match?.path ?? '/']
  }, [location.pathname])

  return (
    <>
      <div className="droom-brand">
        <span className="droom-brand__mark" aria-hidden>
          C
        </span>
        <span className="droom-brand__word">CAPS</span>
      </div>
      <Menu
        theme="dark"
        mode="inline"
        items={items}
        selectedKeys={selected}
        onClick={({ key }) => void navigate(key)}
      />
    </>
  )
}
