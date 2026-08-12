import { Alert, Button, Drawer, Form, Input, Select, Space, Switch } from 'antd'
import type { FormInstance } from 'antd'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '@/core/api/api-error'
import { useErrorMessage } from '@/core/i18n/use-error-message'
import { CameraConnectionTest } from './camera-connection-test'
import { CameraSourceFields } from './camera-source-fields'
import { CameraTuningFields } from './camera-tuning-fields'
import { useCreateCameraMutation, useUpdateCameraMutation } from './use-cameras-queries'
import type { CameraRecord, CreateCameraInput, CameraSourceType } from './use-cameras-queries'

type FormValues = CreateCameraInput

const SOURCE_TYPES: CameraSourceType[] = [
  'esp32cam_http',
  'esp32cam_stream',
  'rtsp',
  'image_folder',
  'video_file',
  'fake',
]
const SOURCE_TYPE_LABEL_KEYS: Record<CameraSourceType, string> = {
  esp32cam_http: 'camera:sourceTypeEsp32camHttp',
  esp32cam_stream: 'camera:sourceTypeEsp32camStream',
  rtsp: 'camera:sourceTypeRtsp',
  image_folder: 'camera:sourceTypeImageFolder',
  video_file: 'camera:sourceTypeVideoFile',
  fake: 'camera:sourceTypeFake',
}

/** See `user-form-drawer.tsx` for why this reads `details.fields` directly. */
function applyFieldErrors(form: FormInstance, error: unknown): boolean {
  if (!(error instanceof ApiError) || error.code !== 'VALIDATION_FAILED') return false
  const fields = error.details['fields']
  if (typeof fields !== 'object' || fields === null) return false
  const entries = Object.entries(fields as Record<string, unknown>).filter(
    (entry): entry is [string, string] => typeof entry[1] === 'string',
  )
  if (entries.length === 0) return false
  form.setFields(entries.map(([name, message]) => ({ name, errors: [message] })))
  return true
}

export function CameraFormDrawer({
  open,
  camera,
  onClose,
}: {
  open: boolean
  camera: CameraRecord | null
  onClose: () => void
}): ReactNode {
  const { t } = useTranslation(['camera', 'common'])
  const toMessage = useErrorMessage()
  const [form] = Form.useForm<FormValues>()
  const sourceType = Form.useWatch('source_type', form) ?? 'esp32cam_http'
  const sourceUrl = Form.useWatch('source_url', form) ?? ''

  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const isEditing = camera !== null
  const createCamera = useCreateCameraMutation()
  const updateCamera = useUpdateCameraMutation()

  useEffect(() => {
    if (!open) return
    setSubmitError(null)
    form.resetFields()
    if (camera) {
      form.setFieldsValue({
        code: camera.code,
        name: camera.name,
        floor: camera.floor,
        source_type: camera.source_type,
        source_url: '', // never round-trip a possible credential back into the field
        poll_interval_s: camera.poll_interval_s,
        vote_window: camera.vote_window,
        vote_threshold: camera.vote_threshold,
        is_enabled: camera.is_enabled,
      })
    }
  }, [open, camera, form])

  const handleFinish = async (values: FormValues): Promise<void> => {
    setSubmitting(true)
    setSubmitError(null)
    try {
      if (camera) {
        const { name, floor, source_type, poll_interval_s, vote_window, vote_threshold, is_enabled, source_url } =
          values
        await updateCamera.mutateAsync({
          id: camera.id,
          name,
          floor,
          source_type,
          poll_interval_s,
          vote_window,
          vote_threshold,
          is_enabled,
          // Omitted entirely when left blank, so the credential-bearing
          // value already saved on the server is left untouched.
          ...(source_url ? { source_url } : {}),
        })
      } else {
        await createCamera.mutateAsync(values)
      }
      onClose()
    } catch (caught) {
      if (!applyFieldErrors(form, caught)) setSubmitError(toMessage(caught))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Drawer
      title={isEditing ? t('camera:editCamera') : t('camera:addCamera')}
      open={open}
      onClose={onClose}
      destroyOnHidden
      width={480}
      extra={
        <Space>
          <Button onClick={onClose}>{t('common:cancel')}</Button>
          <Button type="primary" loading={submitting} onClick={() => void form.submit()}>
            {t('common:save')}
          </Button>
        </Space>
      }
    >
      {submitError !== null && (
        <Alert type="error" showIcon message={submitError} style={{ marginBottom: 16 }} />
      )}

      <Form<FormValues>
        form={form}
        layout="vertical"
        onFinish={(v) => void handleFinish(v)}
        initialValues={{
          floor: 'B1',
          source_type: 'esp32cam_http',
          poll_interval_s: 3,
          vote_window: 5,
          vote_threshold: 4,
          confidence: 0.25,
          is_enabled: true,
        }}
      >
        <Form.Item
          name="code"
          label={t('camera:code')}
          rules={[
            { required: true, message: t('camera:codeRequired') },
            { max: 16, pattern: /^[A-Za-z0-9._-]+$/, message: t('camera:codePattern') },
          ]}
        >
          <Input disabled={isEditing} autoComplete="off" />
        </Form.Item>

        <Form.Item name="name" label={t('camera:name')} rules={[{ max: 120, message: t('camera:nameLength') }]}>
          <Input autoComplete="off" />
        </Form.Item>

        <Form.Item name="floor" label={t('camera:floor')} rules={[{ max: 16 }]}>
          <Input />
        </Form.Item>

        <Form.Item name="source_type" label={t('camera:sourceType')} rules={[{ required: true }]}>
          <Select
            options={SOURCE_TYPES.map((type) => ({ value: type, label: t(SOURCE_TYPE_LABEL_KEYS[type]) }))}
          />
        </Form.Item>

        <CameraSourceFields sourceType={sourceType} isEditing={isEditing} />

        <CameraConnectionTest
          cameraId={isEditing ? camera.id : null}
          sourceType={sourceType}
          sourceUrl={sourceUrl}
        />

        <CameraTuningFields isEditing={isEditing} />

        <Form.Item name="is_enabled" label={t('camera:enabled')} valuePropName="checked">
          <Switch />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
