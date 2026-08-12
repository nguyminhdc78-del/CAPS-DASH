import { Card, Empty, Flex, Skeleton } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { CameraRecord } from '@/features/cameras/use-cameras-queries'
import { compareSlotCodes } from '@/features/slots/sort-slot-codes'
import { DashboardCameraHealthTile } from './dashboard-camera-health-tile'

/**
 * One compact tile per camera. This is what makes the page look like a real
 * running system rather than a mockup: every camera's live worker counters,
 * refreshed on `DASHBOARD_CAMERA_HEALTH_POLL_MS`.
 */
export function DashboardCameraHealthStrip({
  cameras,
  loading,
}: {
  cameras: CameraRecord[]
  loading: boolean
}): ReactNode {
  const { t } = useTranslation('dashboard')
  const sorted = [...cameras].sort(
    (a, b) => compareSlotCodes(a.floor, b.floor) || compareSlotCodes(a.code, b.code),
  )

  return (
    <Card title={t('dashboard:cameraHealthTitle')}>
      {loading ? (
        <Skeleton active paragraph={{ rows: 2 }} />
      ) : sorted.length === 0 ? (
        <Empty description={t('dashboard:cameraHealthEmpty')} />
      ) : (
        <Flex gap={12} wrap>
          {sorted.map((camera) => (
            <DashboardCameraHealthTile key={camera.id} camera={camera} />
          ))}
        </Flex>
      )}
    </Card>
  )
}
