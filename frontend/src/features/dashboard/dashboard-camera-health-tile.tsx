import { Badge, Flex, Tooltip, Typography } from 'antd'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { CameraRecord } from '@/features/cameras/use-cameras-queries'

dayjs.extend(relativeTime)

type OnlineState = 'online' | 'offline' | 'unknown'

const BADGE_STATUS: Record<OnlineState, 'success' | 'error' | 'default'> = {
  online: 'success',
  offline: 'error',
  unknown: 'default',
}

const LABEL_KEY: Record<OnlineState, string> = {
  online: 'camera:online',
  offline: 'camera:offline',
  unknown: 'camera:noWorkerData',
}

/**
 * One camera's health at a glance: online dot, process time, slot count,
 * last seen. This is the one place on the overview that makes a dead camera
 * visible - today it silently turns every one of its slots UNKNOWN with
 * nothing on this page explaining why.
 *
 * `camera.health === null` (no worker running - disabled, or never polled)
 * is deliberately a third, visibly distinct state, not folded into
 * "offline" - see `CameraWithHealth`'s docstring in `camera_schemas.py`:
 * conflating "we know it's down" with "we have no data" hides the
 * difference between a camera that failed and one nobody ever started. The
 * colour dot is never the only signal either way - the state also renders
 * as text right below it.
 */
export function DashboardCameraHealthTile({ camera }: { camera: CameraRecord }): ReactNode {
  const { t } = useTranslation('camera')
  const state: OnlineState = camera.health === null ? 'unknown' : camera.health.online ? 'online' : 'offline'
  const lastSeenText = camera.last_seen_at ? dayjs(camera.last_seen_at).fromNow() : t('camera:lastSeenNever')

  return (
    <div
      role="group"
      aria-label={`${camera.code} — ${t(LABEL_KEY[state])}`}
      style={{
        border: '1px solid var(--ant-color-border-secondary, #d9d9d9)',
        borderRadius: 8,
        padding: 12,
        minWidth: 168,
      }}
    >
      <Flex align="center" gap={8}>
        <Badge status={BADGE_STATUS[state]} />
        <Typography.Text strong>{camera.code}</Typography.Text>
      </Flex>
      <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
        {t(LABEL_KEY[state])}
      </Typography.Text>
      <Typography.Text style={{ fontSize: 12, display: 'block' }}>
        {t('camera:processMs')}: {camera.health ? camera.health.process_ms.toFixed(0) : '—'}
      </Typography.Text>
      <Typography.Text style={{ fontSize: 12, display: 'block' }}>
        {t('camera:slotCount')}: {camera.slot_count}
      </Typography.Text>
      <Tooltip title={camera.last_seen_at ? dayjs(camera.last_seen_at).format('YYYY-MM-DD HH:mm') : undefined}>
        <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
          {t('camera:lastSeen')}: {lastSeenText}
        </Typography.Text>
      </Tooltip>
    </div>
  )
}
