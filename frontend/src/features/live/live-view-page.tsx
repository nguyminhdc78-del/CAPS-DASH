import { Card, Empty } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * Placeholder. The real page is built in phase 12.
 *
 * It exists now so the route table, the sidebar and the role guards are
 * complete and testable from phase 09 onward - a menu entry pointing at a
 * missing module fails at runtime, not at build time.
 */
export default function LiveViewPage(): ReactNode {
  const { t } = useTranslation(['camera', 'common'])

  return (
    <Card title={t('camera:liveView')}>
      <Empty description={t('common:noData')} />
    </Card>
  )
}
