import { Card, List } from 'antd'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { AlertSeverityTag } from '@/features/alerts/alert-severity-tag'
import { localizeAlertMessage } from '@/features/alerts/alerts-table-columns'
import { useAlertsQuery } from '@/features/alerts/use-alerts-queries'

dayjs.extend(relativeTime)

const DASHBOARD_ALERTS_LIMIT = 5

/**
 * Newest few OPEN alerts, with severity and a link through to the full
 * alerts page.
 *
 * Renders nothing at all - not a loading skeleton, not an empty-state card -
 * until there is a confirmed non-empty result. An empty "no alerts" card on
 * the highest-value screen in the app is wasted space, not reassurance, and
 * a skeleton that resolves into "nothing" a moment later is worse: a block
 * appearing and then vanishing reads as a layout glitch, exactly what the
 * loading-skeleton craft guidance elsewhere on this page exists to avoid.
 * `dashboard-page.tsx`'s grid tolerates this cell collapsing to nothing.
 */
export function DashboardAlertsPanel(): ReactNode {
  const { t } = useTranslation(['dashboard', 'alert'])
  const { data, isLoading } = useAlertsQuery({
    acknowledged: false,
    limit: DASHBOARD_ALERTS_LIMIT,
    offset: 0,
  })

  if (isLoading || !data || data.items.length === 0) return null

  return (
    <Card title={t('alert:title')} extra={<Link to="/alerts">{t('dashboard:alertsViewAll')}</Link>}>
      <List
        dataSource={data.items}
        renderItem={(alert) => (
          <List.Item>
            <List.Item.Meta
              avatar={<AlertSeverityTag severity={alert.severity} />}
              title={localizeAlertMessage(t, alert)}
              description={dayjs(alert.created_at).fromNow()}
            />
          </List.Item>
        )}
      />
    </Card>
  )
}
