import { Button, Card, Result, Spin } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'

import { CameraStreamView } from './camera-stream-view'
import { StreamReadoutsPanel } from './stream-readouts-panel'
import { useCameraByCode } from './use-camera-by-code'
import { useCameraStream } from './use-camera-stream'
import { useStreamErrorMessage } from './stream-close-reason-messages'

/**
 * Route shell for `/cameras/:code/live`.
 *
 * Security role or above is enforced by `RequireRoleRoute` around every
 * route in `route-definitions.tsx` (this camera's `minRole: 'security'`) and,
 * independently and authoritatively, by the WS handshake itself
 * (`ws_auth.py::assert_role`) - a resident cannot reach this page, and even if
 * they somehow forced the socket open, the server refuses it. Nothing more is
 * needed here.
 */
export default function LiveViewPage(): ReactNode {
  const { t } = useTranslation(['live', 'camera', 'common'])
  const { code } = useParams<{ code: string }>()
  const { camera, isLoading } = useCameraByCode(code)
  const stream = useCameraStream(camera?.id ?? null)
  const toStreamMessage = useStreamErrorMessage()

  if (isLoading) {
    return (
      <div style={{ display: 'grid', placeItems: 'center', minHeight: '40vh' }}>
        <Spin size="large" tip={t('common:loading')} />
      </div>
    )
  }

  if (!camera) {
    return (
      <Result
        status="404"
        title={t('cameraNotFound')}
        extra={
          <Link to="/cameras">
            <Button type="primary">{t('common:back')}</Button>
          </Link>
        }
      />
    )
  }

  return (
    <Card title={`${t('camera:liveView')} — ${camera.code}`}>
      <StreamReadoutsPanel
        header={stream.header}
        metrics={stream.metrics}
        status={stream.status}
        viewerCount={camera.health?.viewers ?? null}
      />

      {stream.error && (
        <Result
          status="warning"
          title={toStreamMessage(stream.error.code)}
          extra={
            <Button type="primary" onClick={stream.reconnect}>
              {t('common:retry')}
            </Button>
          }
        />
      )}

      <CameraStreamView jpegUrl={stream.jpegUrl} header={stream.header} />
    </Card>
  )
}
