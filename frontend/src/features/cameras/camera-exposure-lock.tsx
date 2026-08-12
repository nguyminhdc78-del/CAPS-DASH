import { Alert, Space, Switch, Tag, Typography } from 'antd'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { MutateSettingsChanges } from './use-camera-settings-queries'

/** 0/1 as the firmware reports it, or `null` when this camera's driver does
 * not report the flag at all. */
function readBit(settings: Record<string, unknown>, key: string): 0 | 1 | null {
  const value = settings[key]
  return value === 0 || value === 1 ? value : null
}

function FlagTag({ label, bit }: { label: string; bit: 0 | 1 | null }): ReactNode {
  const { t } = useTranslation('camera')
  if (bit === null) return <Tag>{`${label}: ${t('camera:settingsFlagUnknown')}`}</Tag>
  return (
    <Tag color={bit === 0 ? 'success' : 'warning'}>
      {`${label}: ${bit === 0 ? t('camera:settingsFlagLocked') : t('camera:settingsFlagAuto')}`}
    </Tag>
  )
}

/**
 * The most important control on this panel.
 *
 * Left on automatic, `aec`/`agc`/`awb` hunt continuously and the whole frame
 * shifts brightness between shots - the detection pipeline's change filter
 * reads that shift as motion. Measured on the reference camera this is the
 * difference between YOLO running on 11% of frames and on all of them; it is
 * what keeps the board from saturating, not a cosmetic toggle. The switch
 * sends `lock_exposure`, which the backend expands into the three flags shown
 * read-only beneath it, so an operator can see what actually changed on the
 * device rather than trusting the switch's own memory of what it clicked.
 */
export function CameraExposureLock({
  settings,
  disabled,
  mutate,
}: {
  settings: Record<string, unknown>
  disabled: boolean
  mutate: MutateSettingsChanges
}): ReactNode {
  const { t } = useTranslation('camera')
  const [pending, setPending] = useState(false)

  const aec = readBit(settings, 'aec')
  const agc = readBit(settings, 'agc')
  const awb = readBit(settings, 'awb')
  const locked = aec === 0 && agc === 0 && awb === 0

  const handleToggle = (checked: boolean): void => {
    setPending(true)
    mutate(
      { lock_exposure: checked },
      {
        onSuccess: () => setPending(false),
        onError: () => setPending(false),
      },
    )
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="small">
      <Space align="center">
        <Switch
          checked={locked}
          loading={pending}
          disabled={disabled}
          onChange={handleToggle}
          aria-label={t('camera:settingsExposureLockTitle')}
        />
        <Typography.Text strong>{t('camera:settingsExposureLockTitle')}</Typography.Text>
      </Space>
      <Alert type="info" showIcon message={t('camera:settingsExposureLockExplanation')} />
      <Space wrap>
        <FlagTag label={t('camera:settingsFlagAec')} bit={aec} />
        <FlagTag label={t('camera:settingsFlagAgc')} bit={agc} />
        <FlagTag label={t('camera:settingsFlagAwb')} bit={awb} />
      </Space>
    </Space>
  )
}
