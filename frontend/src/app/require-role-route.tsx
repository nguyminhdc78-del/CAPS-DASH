import { Result, Spin } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, useLocation } from 'react-router'

import { hasAtLeastRole } from '@/core/auth/role-ranking'
import type { Role } from '@/core/auth/role-ranking'
import { useAuth } from '@/core/auth/use-auth'

/**
 * Route guard.
 *
 * Two distinct failures, handled differently on purpose:
 *   not signed in    -> redirect to /login, remembering where they meant to go
 *   signed in, wrong role -> show 403 in place
 *
 * Redirecting the second case to /login would bounce an already-authenticated
 * user into a form they do not need, which then sends them back here: a loop
 * with no explanation.
 */
export function RequireRoleRoute({
  minRole,
  children,
}: {
  minRole: Role
  children: ReactNode
}): ReactNode {
  const { user, status } = useAuth()
  const location = useLocation()
  const { t } = useTranslation(['common'])

  if (status === 'booting') {
    // The cold-load token exchange is still running. Rendering the login page
    // now would flash it at a user who is in fact signed in.
    return (
      <div style={{ display: 'grid', placeItems: 'center', minHeight: '60vh' }}>
        <Spin size="large" tip={t('common:loading')} />
      </div>
    )
  }

  if (status === 'anonymous' || user === null) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  if (!hasAtLeastRole(user.role, minRole)) {
    return (
      <Result
        status="403"
        title={t('common:forbiddenTitle')}
        subTitle={t('common:forbiddenDetail')}
      />
    )
  }

  return children
}
