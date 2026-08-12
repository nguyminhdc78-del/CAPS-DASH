import { Form, Input } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { CameraSourceType } from './use-cameras-queries'

/**
 * Which source types take a URL, and which scheme each one requires. Mirrors
 * `_SCHEMES_BY_SOURCE` in `camera_validation.py`; a type absent from here
 * takes a filesystem path instead. Keeping it a table rather than a chain of
 * comparisons is what stops a newly added source type silently falling into
 * the "no validation" branch.
 */
const URL_SCHEMES: Partial<
  Record<CameraSourceType, { pattern: RegExp; errorKey: string }>
> = {
  esp32cam_http: { pattern: /^https?:\/\/.+/i, errorKey: 'camera:sourceUrlRequiredHttp' },
  esp32cam_stream: { pattern: /^https?:\/\/.+/i, errorKey: 'camera:sourceUrlRequiredHttp' },
  rtsp: { pattern: /^rtsps?:\/\/.+/i, errorKey: 'camera:sourceUrlRequiredRtsp' },
}

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

  const scheme = URL_SCHEMES[sourceType]
  const isUrl = scheme !== undefined

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
        scheme
          ? [
              {
                validator: (_rule, value: string | undefined) => {
                  if (!value) return Promise.resolve()
                  return scheme.pattern.test(value)
                    ? Promise.resolve()
                    : Promise.reject(new Error(t(scheme.errorKey)))
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
