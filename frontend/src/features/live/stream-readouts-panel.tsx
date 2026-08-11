import { Space, Typography } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { StreamStatus } from './camera-stream-manager'
import type { StreamMetricsSummary } from './use-stream-metrics'
import type { FrameHeader } from './frame-header-types'
import { StreamStatusBadge } from './stream-status-badge'

/** fps / process time / confidence / viewers / age of last frame / connection state. */
export function StreamReadoutsPanel({
  header,
  metrics,
  status,
  viewerCount,
}: {
  header: FrameHeader | null
  metrics: StreamMetricsSummary
  status: StreamStatus
  viewerCount: number | null
}): ReactNode {
  const { t } = useTranslation('live')

  const frameAgeLabel =
    metrics.lastFrameAgeMs === null
      ? t('noFrameYet')
      : t('frameAgeSeconds', { seconds: Math.round(metrics.lastFrameAgeMs / 1000) })

  return (
    <Space size="large" wrap style={{ marginBottom: 16 }}>
      <StatItem label={t('connectionStatus')} value={<StreamStatusBadge status={status} />} />
      <StatItem label={t('fps')} value={metrics.fps.toFixed(1)} />
      <StatItem label={t('processMs')} value={header ? header.process_ms.toFixed(0) : '—'} />
      <StatItem label={t('camera:confidence')} value={header ? header.confidence.toFixed(2) : '—'} />
      <StatItem label={t('viewers')} value={viewerCount ?? '—'} />
      <StatItem label={t('frameAge')} value={frameAgeLabel} />
    </Space>
  )
}

function StatItem({ label, value }: { label: string; value: ReactNode }): ReactNode {
  return (
    <div style={{ minWidth: 96 }}>
      <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
        {label}
      </Typography.Text>
      <Typography.Text strong>{value}</Typography.Text>
    </div>
  )
}
