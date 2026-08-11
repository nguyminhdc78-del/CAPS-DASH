import { Form, Input } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { CameraSourceType } from './use-cameras-queries'

/**
 * Swaps the `source_url` field's label, help text and validation based on
 * `source_type`. FAKE renders nothing: `camera_validation.py` ignores
 * `source_url` entirely for that type, so showing an editable field for it
 * would invite a value that gets silently discarded server-side.
 */
export function CameraSourceFields({
  sourceType,
  isEditing,
}: {
  sourceType: CameraSourceType
  isEditing: boolean
}): ReactNode {
  const { t } = useTranslation('camera')

  if (sourceType === 'fake') return null

  const isUrl = sourceType === 'esp32cam_http'

  return (
    <Form.Item
      name="source_url"
      label={isUrl ? t('camera:sourceUrl') : t('camera:sourcePath')}
      // On edit, the field starts blank: the API returns source_url with any
      // credentials stripped, so round-tripping that value back into a save
      // would silently drop the real credential. Leaving it blank keeps
      // whatever is already stored.
      extra={isEditing ? t('camera:sourceUrlLeaveBlank') : undefined}
      rules={
        isUrl
          ? [
              {
                validator: (_rule, value: string | undefined) => {
                  if (!value) return Promise.resolve()
                  return /^https?:\/\/.+/i.test(value)
                    ? Promise.resolve()
                    : Promise.reject(new Error(t('camera:sourceUrlRequiredHttp')))
                },
              },
            ]
          : []
      }
    >
      <Input autoComplete="off" />
    </Form.Item>
  )
}
