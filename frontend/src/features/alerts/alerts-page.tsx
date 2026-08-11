import { Card, Empty } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * Placeholder. The real page is built in phase 13.
 *
 * It exists now so the route table, the sidebar and the role guards are
 * complete and testable from phase 09 onward - a menu entry pointing at a
 * missing module fails at runtime, not at build time.
 */
export default function AlertsPage(): ReactNode {
  const { t } = useTranslation(['alert', 'common'])

  return (
    <Card title={t('alert:title')}>
      <Empty description={t('common:noData')} />
    </Card>
  )
}
