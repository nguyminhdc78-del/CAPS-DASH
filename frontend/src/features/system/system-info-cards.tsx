import { Card, Col, Progress, Row, Statistic } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { SystemInfo } from './use-system-queries'

function formatBytes(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`
}

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86_400)
  const hours = Math.floor((seconds % 86_400) / 3_600)
  const minutes = Math.floor((seconds % 3_600) / 60)
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

/** `/system/info` at a glance: disk headroom, table sizes, schema revision,
 * process uptime. Read-only - `backup-panel.tsx` and `purge-panel.tsx` are
 * the actions this data motivates. */
export function SystemInfoCards({ info }: { info: SystemInfo }): ReactNode {
  const { t } = useTranslation('system')
  const usedPercent = info.disk_total_bytes
    ? Math.round(((info.disk_total_bytes - info.disk_free_bytes) / info.disk_total_bytes) * 100)
    : 0

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} md={8}>
        <Card title={t('disk')}>
          <Progress percent={usedPercent} status={usedPercent > 90 ? 'exception' : 'normal'} />
          <Statistic
            title={t('diskFree')}
            value={`${formatBytes(info.disk_free_bytes)} / ${formatBytes(info.disk_total_bytes)}`}
          />
        </Card>
      </Col>
      <Col xs={24} md={8}>
        <Card title={t('records')}>
          <Row gutter={[8, 8]}>
            {Object.entries(info.table_row_counts).map(([table, count]) => (
              <Col span={12} key={table}>
                <Statistic title={t(`table_${table}`, { defaultValue: table })} value={count} />
              </Col>
            ))}
          </Row>
        </Card>
      </Col>
      <Col xs={24} md={8}>
        <Card title={t('status')}>
          <Statistic title={t('schemaVersion')} value={info.schema_revision || t('schemaUnknown')} />
          <Statistic title={t('uptime')} value={formatUptime(info.uptime_seconds)} />
        </Card>
      </Col>
    </Row>
  )
}
