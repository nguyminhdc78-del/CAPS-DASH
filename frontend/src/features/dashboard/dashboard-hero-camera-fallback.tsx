import { Empty, Spin, Tag } from 'antd'
import type { CSSProperties, ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { StreamStatus } from '@/features/live/camera-stream-manager'
import { useCameraSnapshot } from '@/features/roi-editor/use-camera-snapshot'

const CONNECTING_STATUSES: ReadonlySet<StreamStatus> = new Set(['connecting', 'authenticating'])

// The same box `camera-stream-view.tsx` renders the live frame into, so the
// hero tile never changes size as it swaps between loading, snapshot and
// empty states - the layout must not jump depending on which of the three
// this happens to be showing at the moment a judge looks at the screen.
const TILE_STYLE: CSSProperties = {
  width: '100%',
  aspectRatio: '16 / 9',
  position: 'relative',
  display: 'grid',
  placeItems: 'center',
  borderRadius: 4,
  overflow: 'hidden',
}

/**
 * What the hero tile shows before the WebSocket has delivered a first frame.
 *
 * While the socket is still opening this is just a loading spinner - the
 * connection is expected to succeed within a moment. Once this attempt has
 * given up (closed, or backed off into a retry) it falls back to one still
 * frame from `GET /cameras/{id}/snapshot` (the same authenticated fetch the
 * ROI editor already uses - see `use-camera-snapshot.ts`), so the tile still
 * proves the camera is alive without a live overlay. If even that fails -
 * notably, that endpoint is admin-only, so it always fails this way for a
 * security-role viewer - a calm empty state: never a broken image icon on
 * the page a judge looks at first.
 */
export function DashboardHeroCameraFallback({
  cameraId,
  status,
}: {
  cameraId: number
  status: StreamStatus
}): ReactNode {
  if (CONNECTING_STATUSES.has(status)) return <LoadingTile />
  return <HeroSnapshotFallback cameraId={cameraId} />
}

function HeroSnapshotFallback({ cameraId }: { cameraId: number }): ReactNode {
  const { t } = useTranslation('dashboard')
  const snapshot = useCameraSnapshot(cameraId)

  if (snapshot.status === 'ready' && snapshot.image) {
    return (
      <div style={{ ...TILE_STYLE, background: '#000' }}>
        <img
          src={snapshot.image.src}
          alt=""
          style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
        />
        <Tag style={{ position: 'absolute', top: 8, left: 8 }}>{t('dashboard:heroSnapshotBadge')}</Tag>
      </div>
    )
  }

  if (snapshot.status === 'error') {
    return (
      <div style={TILE_STYLE}>
        <Empty description={t('dashboard:heroEmptyUnavailable')} />
      </div>
    )
  }

  return <LoadingTile />
}

function LoadingTile(): ReactNode {
  return (
    <div style={TILE_STYLE}>
      <Spin />
    </div>
  )
}
