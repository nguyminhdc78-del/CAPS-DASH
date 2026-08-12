import { Descriptions, Space, Switch, Typography } from 'antd'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { MutateSettingsChanges } from './use-camera-settings-queries'

interface ToggleField {
  field: 'hmirror' | 'vflip' | 'led'
  labelKey: string
}

const TOGGLES: ToggleField[] = [
  { field: 'hmirror', labelKey: 'camera:settingsHmirror' },
  { field: 'vflip', labelKey: 'camera:settingsVflip' },
  { field: 'led', labelKey: 'camera:settingsLed' },
]

function readBit(settings: Record<string, unknown>, key: string): boolean {
  return settings[key] === 1
}

/** A single discrete on/off flag. No debounce needed - a click is one event,
 * unlike a slider drag - but the switch still waits for the device to
 * confirm before the invalidated query re-renders it, rather than flipping
 * ahead of what was actually applied. */
function ToggleSwitch({
  config,
  serverValue,
  disabled,
  mutate,
}: {
  config: ToggleField
  serverValue: boolean
  disabled: boolean
  mutate: MutateSettingsChanges
}): ReactNode {
  const { t } = useTranslation('camera')
  const [pending, setPending] = useState(false)

  const handleChange = (checked: boolean): void => {
    setPending(true)
    mutate(
      { [config.field]: checked ? 1 : 0 },
      { onSuccess: () => setPending(false), onError: () => setPending(false) },
    )
  }

  return (
    <Space>
      <Switch
        checked={serverValue}
        loading={pending}
        disabled={disabled}
        onChange={handleChange}
        aria-label={t(config.labelKey)}
      />
      <Typography.Text>{t(config.labelKey)}</Typography.Text>
    </Space>
  )
}

export function CameraSettingsToggles({
  settings,
  disabled,
  mutate,
}: {
  settings: Record<string, unknown>
  disabled: boolean
  mutate: MutateSettingsChanges
}): ReactNode {
  return (
    <Space direction="vertical" size="small">
      {TOGGLES.map((config) => (
        <ToggleSwitch
          key={config.field}
          config={config}
          serverValue={readBit(settings, config.field)}
          disabled={disabled}
          mutate={mutate}
        />
      ))}
    </Space>
  )
}

/** Candidate diagnostic keys, rendered only when the device actually
 * reported them - the firmware's own status payload decides what shows up,
 * this is not a fixed schema. */
const DIAGNOSTIC_LABEL_KEYS: Record<string, string> = {
  rssi: 'camera:settingsDiagnosticsRssi',
  framesize: 'camera:settingsDiagnosticsFramesize',
  heap: 'camera:settingsDiagnosticsHeap',
  uptime_s: 'camera:settingsDiagnosticsUptime',
}

function formatDiagnostic(key: string, value: unknown): string {
  if (typeof value !== 'number' && typeof value !== 'string') return String(value)
  switch (key) {
    case 'rssi':
      return `${value} dBm`
    case 'heap':
      return `${value} B`
    case 'uptime_s':
      return `${value} s`
    default:
      return String(value)
  }
}

export function CameraSettingsDiagnostics({ settings }: { settings: Record<string, unknown> }): ReactNode {
  const { t } = useTranslation('camera')
  const present = Object.keys(DIAGNOSTIC_LABEL_KEYS).filter((key) => settings[key] !== undefined)
  if (present.length === 0) return null

  return (
    <Descriptions size="small" column={2} bordered={false}>
      {present.map((key) => (
        <Descriptions.Item key={key} label={t(DIAGNOSTIC_LABEL_KEYS[key] ?? '')}>
          {formatDiagnostic(key, settings[key])}
        </Descriptions.Item>
      ))}
    </Descriptions>
  )
}
