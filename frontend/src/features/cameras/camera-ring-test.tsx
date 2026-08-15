import { Alert, App, Button, Space, Typography } from 'antd'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useErrorMessage } from '@/core/i18n/use-error-message'
import { useRingTestMutation } from './use-camera-settings-queries'

/**
 * The three colours the WS2812B ring can show, and the character the firmware
 * takes for each. The swatches are the *rendered* colours from
 * `firmware/esp32cam/slot-ring-led.cpp`, so what an installer compares against
 * on screen is what the LED is being told to emit - not an approximation
 * somebody picked because it looked nice in a browser.
 */
const PATTERNS = [
  { slots: '1', labelKey: 'ringTestOccupied', swatch: 'rgb(255, 12, 0)' },
  { slots: '0', labelKey: 'ringTestFree', swatch: 'rgb(0, 200, 40)' },
  { slots: 'u', labelKey: 'ringTestUnknown', swatch: 'rgb(255, 96, 0)' },
] as const

/**
 * Commissioning check for the bay-status LED ring on a camera node.
 *
 * It answers what the dashboard alone cannot: is the ring on the right pin,
 * is it powered from 5V rather than 3V3, and is the strip GRB rather than RGB
 * - a strip that lights green when told red is the giveaway. Waiting for a
 * real car to arrive to discover that is how a ring gets installed backwards
 * and stays that way.
 *
 * One character is sent, so the whole ring becomes a single arc in that
 * colour: what is under test is the wiring and the colour, not which bay is
 * which. The camera loop takes the ring back within seconds, and that is said
 * plainly rather than papered over with a lock - a test pattern that outlived
 * the test would be a lamp showing a car that is not there.
 */
export function CameraRingTest({
  cameraId,
  disabled,
}: {
  cameraId: number | null
  disabled: boolean
}): ReactNode {
  const { t } = useTranslation('camera')
  const { message } = App.useApp()
  const toMessage = useErrorMessage()
  const testMutation = useRingTestMutation(cameraId)
  const [sending, setSending] = useState<string | null>(null)

  const handleTest = (slots: string): void => {
    setSending(slots)
    testMutation.mutate(slots, {
      onSuccess: (result) => {
        setSending(null)
        message.success(t('camera:ringTestSent', { seconds: result.reverts_within_s }))
      },
      onError: (caught) => {
        // The whole reason this endpoint raises rather than failing quietly
        // like the camera loop's own pusher: somebody is standing in front of
        // the ring waiting to see it change, and silence would not tell them
        // whether the wiring, the pin or the address is at fault.
        setSending(null)
        message.error(toMessage(caught))
      },
    })
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="small">
      <Typography.Text strong>{t('camera:ringTestTitle')}</Typography.Text>
      <Alert type="info" showIcon message={t('camera:ringTestExplanation')} />
      <Space wrap>
        {PATTERNS.map((pattern) => (
          <Button
            key={pattern.slots}
            disabled={disabled || cameraId === null}
            loading={sending === pattern.slots}
            onClick={() => handleTest(pattern.slots)}
            icon={
              <span
                aria-hidden
                style={{
                  display: 'inline-block',
                  width: 12,
                  height: 12,
                  borderRadius: '50%',
                  background: pattern.swatch,
                  boxShadow: `0 0 6px ${pattern.swatch}`,
                }}
              />
            }
          >
            {t(`camera:${pattern.labelKey}`)}
          </Button>
        ))}
      </Space>
    </Space>
  )
}
