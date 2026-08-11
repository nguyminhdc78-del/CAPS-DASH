import { Form, InputNumber } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import {
  CAMERA_POLL_INTERVAL_MAX_S,
  CAMERA_POLL_INTERVAL_MIN_S,
  CAMERA_VOTE_THRESHOLD_MAX,
  CAMERA_VOTE_WINDOW_MAX,
} from '@/core/constants/ui-constants'

/**
 * The vote-filter and polling fields, split out of `camera-form-drawer.tsx`
 * to keep that file under the 200-line cap.
 *
 * `confidence` only renders at creation - after that it is tuned live via
 * `camera-confidence-slider.tsx` (`PATCH .../runtime`, no worker restart)
 * rather than through this full-update form, which may restart the worker.
 */
export function CameraTuningFields({ isEditing }: { isEditing: boolean }): ReactNode {
  const { t } = useTranslation('camera')

  return (
    <>
      <Form.Item name="poll_interval_s" label={t('camera:pollInterval')} rules={[{ required: true }]}>
        <InputNumber
          min={CAMERA_POLL_INTERVAL_MIN_S}
          max={CAMERA_POLL_INTERVAL_MAX_S}
          step={0.5}
          style={{ width: '100%' }}
        />
      </Form.Item>

      <Form.Item name="vote_window" label={t('camera:voteWindow')} rules={[{ required: true }]}>
        <InputNumber min={1} max={CAMERA_VOTE_WINDOW_MAX} style={{ width: '100%' }} />
      </Form.Item>

      <Form.Item name="vote_threshold" label={t('camera:voteThreshold')} rules={[{ required: true }]}>
        <InputNumber min={1} max={CAMERA_VOTE_THRESHOLD_MAX} style={{ width: '100%' }} />
      </Form.Item>

      {!isEditing && (
        <Form.Item name="confidence" label={t('camera:confidence')} rules={[{ required: true }]}>
          <InputNumber min={0.01} max={0.99} step={0.01} style={{ width: '100%' }} />
        </Form.Item>
      )}
    </>
  )
}
