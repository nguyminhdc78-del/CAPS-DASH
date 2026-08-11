import { AlertOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Badge, Button, Tooltip } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'

import { api } from '@/core/api/api-client'
import { queryKeys } from '@/core/api/query-keys'
import { hasAtLeastRole } from '@/core/auth/role-ranking'
import { useAuth } from '@/core/auth/use-auth'
import { ALERT_BADGE_POLL_MS } from '@/core/constants/ui-constants'

/**
 * Unacknowledged alert count, in the header, on every page.
 *
 * An alerting system nobody looks at is not an alerting system. A camera that
 * went offline at 2am is only useful if the next person to open the dashboard
 * sees it without navigating to a page they had no reason to visit.
 *
 * Residents never see it: they cannot read `/api/alerts` at all, so polling it
 * for them would be a guaranteed 403 every interval.
 */
export function AppAlertBadge(): ReactNode {
  const { t } = useTranslation(['alert'])
  const { user } = useAuth()
  const navigate = useNavigate()

  const canSeeAlerts = hasAtLeastRole(user?.role, 'security')

  // `limit=1` because only the envelope's `total` is wanted - the rows
  // themselves are the alerts page's job, and fetching a full page every
  // interval to render one number would be wasteful on a board this size.
  const { data } = useQuery({
    queryKey: queryKeys.alerts.list({ acknowledged: false, limit: 1 }),
    queryFn: () => api.get<{ total: number }>('/alerts?acknowledged=false&limit=1&offset=0'),
    enabled: canSeeAlerts,
    refetchInterval: ALERT_BADGE_POLL_MS,
  })

  if (!canSeeAlerts) return null

  const openCount = data?.total ?? 0
  const label = t('alert:openAlertCount', { count: openCount })

  return (
    <Tooltip title={label}>
      <Badge count={openCount} size="small" offset={[-2, 2]}>
        <Button
          type="text"
          icon={<AlertOutlined />}
          aria-label={label}
          onClick={() => void navigate('/alerts')}
        />
      </Badge>
    </Tooltip>
  )
}
