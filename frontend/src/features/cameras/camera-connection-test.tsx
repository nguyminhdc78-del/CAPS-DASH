import { CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import { Alert, Button, Descriptions, Space } from 'antd'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { api } from '@/core/api/api-client'
import { ApiError } from '@/core/api/api-error'
import { useErrorMessage } from '@/core/i18n/use-error-message'
import type { CameraSourceType } from './use-cameras-queries'

interface TestConnectionResult {
  ok: boolean
  latency_ms: number
  frame_width: number
  frame_height: number
  error: string
  error_code: string
}

/**
 * Runs the backend's connection probe and renders the result inline.
 *
 * `POST /cameras/test-connection` (unsaved draft) or
 * `POST /cameras/{id}/test-connection` (saved camera) both answer HTTP 200
 * with `{ ok: false, error_code, ... }` for a genuine connection failure -
 * that is a normal diagnostic outcome, not an exception. Treating it as one
 * would crash this drawer every time an installer tests a camera that is
 * not plugged in yet, which is precisely when this button gets used most.
 * A thrown error here means the REQUEST itself failed (network, auth, 500),
 * which is a different, separately rendered case.
 */
export function CameraConnectionTest({
  cameraId,
  sourceType,
  sourceUrl,
}: {
  cameraId: number | null
  sourceType: CameraSourceType
  sourceUrl: string
}): ReactNode {
  const { t } = useTranslation(['camera', 'common'])
  const toMessage = useErrorMessage()
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<TestConnectionResult | null>(null)
  const [requestFailed, setRequestFailed] = useState<string | null>(null)

  const handleTest = async (): Promise<void> => {
    setTesting(true)
    setResult(null)
    setRequestFailed(null)
    try {
      const response =
        cameraId === null
          ? await api.post<TestConnectionResult>('/cameras/test-connection', {
              source_type: sourceType,
              source_url: sourceUrl,
            })
          : await api.post<TestConnectionResult>(`/cameras/${cameraId}/test-connection`)
      setResult(response)
    } catch (caught) {
      setRequestFailed(toMessage(caught))
    } finally {
      setTesting(false)
    }
  }

  return (
    <Space direction="vertical" style={{ width: '100%', marginBottom: 16 }}>
      <Button onClick={() => void handleTest()} loading={testing} disabled={testing}>
        {t('camera:testConnection')}
      </Button>

      {requestFailed !== null && <Alert type="error" showIcon message={requestFailed} />}

      {result !== null && result.ok && (
        <Alert
          type="success"
          showIcon
          icon={<CheckCircleOutlined />}
          message={t('camera:testConnectionOk')}
          description={
            <Descriptions size="small" column={1}>
              <Descriptions.Item label={t('camera:testConnectionLatency')}>
                {result.latency_ms.toFixed(0)} ms
              </Descriptions.Item>
              <Descriptions.Item label={t('camera:testConnectionFrameSize')}>
                {result.frame_width} x {result.frame_height}
              </Descriptions.Item>
            </Descriptions>
          }
        />
      )}

      {result !== null && !result.ok && (
        <Alert
          type="error"
          showIcon
          icon={<CloseCircleOutlined />}
          message={t('camera:testConnectionFailed')}
          // Reuses the same code -> localized-message pipeline as every other
          // error in the app, rather than showing the probe's raw dev text.
          description={toMessage(
            new ApiError({ code: result.error_code || 'INTERNAL_ERROR', message: result.error, status: 200 }),
          )}
        />
      )}
    </Space>
  )
}
