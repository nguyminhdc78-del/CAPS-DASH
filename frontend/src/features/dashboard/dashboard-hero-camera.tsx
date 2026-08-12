import { Card, Empty, Select, Skeleton } from 'antd'
import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { CameraRecord } from '@/features/cameras/use-cameras-queries'
import { CameraStreamView } from '@/features/live/camera-stream-view'
import { StreamStatusBadge } from '@/features/live/stream-status-badge'
import { useCameraStream } from '@/features/live/use-camera-stream'
import { compareSlotCodes } from '@/features/slots/sort-slot-codes'
import { DashboardHeroCameraFallback } from './dashboard-hero-camera-fallback'
import { DashboardInferencePanel } from './dashboard-inference-panel'

/**
 * The centrepiece: one live camera tile with the YOLO detection overlay,
 * beside the headline counters - proof the system genuinely works, not just
 * a report of numbers it produced. Reuses `use-camera-stream` and
 * `CameraStreamView` exactly as `features/live` does; nothing about the
 * streaming protocol is reimplemented here.
 *
 * Exactly one `useCameraStream` call happens on this whole page - this is
 * that one call site. The backend caps viewers at 4 per camera and 16 total,
 * and every open socket is CPU the board is also spending on YOLO26, so a
 * camera *chooser* (swap which single socket is open) replaces what would
 * otherwise be a tempting wall of live tiles when more than one camera exists.
 */
export function DashboardHeroCamera({
  cameras,
  camerasLoading,
}: {
  cameras: CameraRecord[]
  camerasLoading: boolean
}): ReactNode {
  const { t } = useTranslation('dashboard')
  const sorted = useMemo(
    () => [...cameras].sort((a, b) => compareSlotCodes(a.floor, b.floor) || compareSlotCodes(a.code, b.code)),
    [cameras],
  )
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const activeCamera = sorted.find((camera) => camera.id === selectedId) ?? sorted[0] ?? null

  const stream = useCameraStream(activeCamera?.id ?? null)

  if (camerasLoading) {
    return (
      <Card title={t('dashboard:heroTitle')}>
        <Skeleton.Image active style={{ width: '100%', aspectRatio: '16 / 9' }} />
      </Card>
    )
  }

  if (activeCamera === null) {
    return (
      <Card title={t('dashboard:heroTitle')}>
        <Empty description={t('dashboard:heroEmptyNoCamera')} />
      </Card>
    )
  }

  return (
    <Card
      title={t('dashboard:heroTitle')}
      extra={
        sorted.length > 1 ? (
          <Select
            size="small"
            value={activeCamera.id}
            style={{ minWidth: 140 }}
            onChange={(value: number) => setSelectedId(value)}
            options={sorted.map((camera) => ({ value: camera.id, label: camera.code }))}
            aria-label={t('dashboard:heroCameraSelectLabel')}
          />
        ) : null
      }
    >
      {stream.jpegUrl ? (
        <>
          <CameraStreamView jpegUrl={stream.jpegUrl} header={stream.header} />
          <div style={{ marginTop: 8 }}>
            <StreamStatusBadge status={stream.status} />
          </div>
          <DashboardInferencePanel header={stream.header} />
        </>
      ) : (
        <DashboardHeroCameraFallback cameraId={activeCamera.id} status={stream.status} />
      )}
    </Card>
  )
}
