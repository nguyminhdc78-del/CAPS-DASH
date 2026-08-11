import { Col, Row, Skeleton } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { BackupPanel } from './backup-panel'
import { ClockSuspectBanner } from './clock-suspect-banner'
import { PurgePanel } from './purge-panel'
import { SystemInfoCards } from './system-info-cards'
import { useSystemInfoQuery } from './use-system-queries'

/** Admin-only operational console: status snapshot, backup, purge.
 * `route-definitions.tsx` already gates this route at `minRole: 'admin'`. */
export default function SystemPage(): ReactNode {
  const { t } = useTranslation('system')
  const { data, isLoading } = useSystemInfoQuery()

  return (
    <Row gutter={[16, 16]}>
      <Col span={24}>
        <h2>{t('title')}</h2>
      </Col>
      {data && (
        <Col span={24}>
          <ClockSuspectBanner active={data.clock_suspect} />
        </Col>
      )}
      <Col span={24}>{isLoading || !data ? <Skeleton active /> : <SystemInfoCards info={data} />}</Col>
      <Col xs={24} md={12}>
        <BackupPanel />
      </Col>
      <Col xs={24} md={12}>
        <PurgePanel />
      </Col>
    </Row>
  )
}
