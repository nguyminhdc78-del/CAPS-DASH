import { Alert, App, Divider, Drawer, Empty, Space, Spin } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '@/core/api/api-error'
import { hasAtLeastRole } from '@/core/auth/role-ranking'
import { useAuth } from '@/core/auth/use-auth'
import { useErrorMessage } from '@/core/i18n/use-error-message'
import { CameraExposureLock } from './camera-exposure-lock'
import { CameraRingTest } from './camera-ring-test'
import { CameraSettingsSliders } from './camera-settings-sliders'
import { CameraSettingsDiagnostics, CameraSettingsToggles } from './camera-settings-toggles'
import { useCameraSettingsQuery, useUpdateCameraSettingsMutation } from './use-camera-settings-queries'
import type { MutateSettingsChanges } from './use-camera-settings-queries'
import type { CameraRecord } from './use-cameras-queries'

/**
 * Sensor-settings panel for one camera, opened from a row action on
 * `cameras-table-columns.tsx`.
 *
 * Reading (`GET .../settings`) works for security role and above; writing
 * (`PATCH`) is admin-only server-side. A non-admin viewer therefore still
 * sees the live values but every control is disabled with a stated reason
 * here, rather than offering a control that would 403 on submit.
 */
export function CameraSettingsDrawer({
  open,
  camera,
  onClose,
}: {
  open: boolean
  camera: CameraRecord | null
  onClose: () => void
}): ReactNode {
  const { t } = useTranslation(['camera', 'common'])
  const { message } = App.useApp()
  const toMessage = useErrorMessage()
  const { user } = useAuth()
  const isAdmin = hasAtLeastRole(user?.role, 'admin')

  const cameraId = camera?.id ?? null
  const settingsQuery = useCameraSettingsQuery(open ? cameraId : null)
  const updateMutation = useUpdateCameraSettingsMutation(cameraId)

  // Every control below (sliders, switches, the exposure lock) commits
  // through this one function, so they all share the drawer's single
  // mutation instance - that instance is what carries `applied` after a
  // write, and a toast here covers request-level failures (network, auth)
  // distinct from a per-field rejection the device itself reports as `false`.
  const mutate: MutateSettingsChanges = (changes, callbacks) => {
    updateMutation.mutate(changes, {
      onSuccess: () => callbacks.onSuccess(),
      onError: (caught) => {
        message.error(toMessage(caught))
        callbacks.onError()
      },
    })
  }

  const isSourceInvalid =
    settingsQuery.error instanceof ApiError && settingsQuery.error.code === 'CAMERA_SOURCE_INVALID'

  const applied = updateMutation.data?.applied ?? null
  const rejected = applied
    ? Object.entries(applied)
        .filter(([, ok]) => !ok)
        .map(([field]) => field)
    : []

  return (
    <Drawer
      title={t('camera:settingsTitle', { code: camera?.code ?? '' })}
      open={open}
      onClose={onClose}
      destroyOnHidden
      width={420}
    >
      {camera === null ? null : (
        <Space direction="vertical" style={{ width: '100%' }} size="large">
          {renderSensorPanel()}

          {/* Outside the sensor panel deliberately. The ring is a separate
              device on a separate endpoint, so a camera whose sensor cannot be
              read - a source with no controllable sensor, or one that is not
              answering at all - must not take the ring test down with it. That
              is precisely when somebody needs it: an installer standing at a
              half-working node, trying to work out which part is wrong. */}
          <Divider style={{ margin: 0 }} />
          <CameraRingTest cameraId={cameraId} disabled={!isAdmin} />
        </Space>
      )}
    </Drawer>
  )

  function renderSensorPanel(): ReactNode {
    if (settingsQuery.isLoading) return <Spin />
    if (isSourceInvalid) return <Empty description={t('camera:settingsSourceHasNoSensor')} />
    if (settingsQuery.isError) {
      return <Alert type="error" showIcon message={toMessage(settingsQuery.error)} />
    }
    if (!settingsQuery.data) return null

    return (
      <Space direction="vertical" style={{ width: '100%' }} size="large">
        {!isAdmin && <Alert type="info" showIcon message={t('camera:settingsReadOnlyReason')} />}

        {applied !== null &&
          (rejected.length === 0 ? (
            <Alert type="success" showIcon message={t('camera:settingsAppliedAllOk')} />
          ) : (
            <Alert
              type="warning"
              showIcon
              message={t('camera:settingsAppliedPartial', { fields: rejected.join(', ') })}
            />
          ))}

        <CameraSettingsDiagnostics settings={settingsQuery.data.settings} />

        <CameraExposureLock
          settings={settingsQuery.data.settings}
          disabled={!isAdmin}
          mutate={mutate}
        />

        <CameraSettingsSliders
          settings={settingsQuery.data.settings}
          disabled={!isAdmin}
          mutate={mutate}
        />

        <CameraSettingsToggles
          settings={settingsQuery.data.settings}
          disabled={!isAdmin}
          mutate={mutate}
        />
      </Space>
    )
  }
}
