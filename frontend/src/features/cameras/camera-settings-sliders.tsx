import { Slider, Space, Typography } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useDebouncedSettingField } from './use-camera-settings-queries'
import type { MutateSettingsChanges, NumericSettingField } from './use-camera-settings-queries'

/** The four numeric sensor fields exposed as sliders. `framesize` is
 * reported in the diagnostics header but not adjustable here - the drawer's
 * brief only asks for these four plus the switches below it. */
interface SliderField {
  field: NumericSettingField
  labelKey: string
  hintKey?: string
  min: number
  max: number
}

const FIELDS: SliderField[] = [
  { field: 'brightness', labelKey: 'camera:settingsBrightness', min: -2, max: 2 },
  { field: 'contrast', labelKey: 'camera:settingsContrast', min: -2, max: 2 },
  { field: 'saturation', labelKey: 'camera:settingsSaturation', min: -2, max: 2 },
  // Range mirrors SETTING_RANGES['quality'] in camera_control_service.py.
  // Counter-intuitive on the device (lower number = higher quality, more
  // bytes per frame), so the hint is not optional decoration.
  { field: 'quality', labelKey: 'camera:settingsQuality', hintKey: 'camera:settingsQualityHint', min: 4, max: 63 },
]

function readNumber(settings: Record<string, unknown>, key: string, fallback: number): number {
  const value = settings[key]
  return typeof value === 'number' ? value : fallback
}

function SettingSlider({
  config,
  serverValue,
  disabled,
  mutate,
}: {
  config: SliderField
  serverValue: number
  disabled: boolean
  mutate: MutateSettingsChanges
}): ReactNode {
  const { t } = useTranslation('camera')
  const { displayValue, setDisplayValue } = useDebouncedSettingField(
    config.field,
    serverValue,
    disabled,
    mutate,
  )

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Typography.Text>{t(config.labelKey)}</Typography.Text>
      {config.hintKey !== undefined && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {t(config.hintKey)}
        </Typography.Text>
      )}
      <Slider
        min={config.min}
        max={config.max}
        value={displayValue}
        disabled={disabled}
        onChange={(next) => setDisplayValue(next as number)}
        tooltip={{ formatter: (v) => String(v ?? 0) }}
      />
    </Space>
  )
}

/**
 * Brightness / contrast / saturation / quality, each its own debounced
 * slider (see `useDebouncedSettingField`) so dragging one never floods the
 * device with a request per pixel of pointer movement.
 */
export function CameraSettingsSliders({
  settings,
  disabled,
  mutate,
}: {
  settings: Record<string, unknown>
  disabled: boolean
  mutate: MutateSettingsChanges
}): ReactNode {
  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      {FIELDS.map((config) => (
        <SettingSlider
          key={config.field}
          config={config}
          serverValue={readNumber(settings, config.field, 0)}
          disabled={disabled}
          mutate={mutate}
        />
      ))}
    </Space>
  )
}
