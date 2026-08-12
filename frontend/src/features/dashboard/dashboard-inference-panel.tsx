import { Progress, Tooltip, Typography } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { FrameHeader } from '@/features/live/frame-header-types'
import { useInferenceStats } from './use-inference-stats'

const { Text } = Typography

/**
 * What the detector is doing, right now, under the live tile.
 *
 * The headline is the skip ratio, because that is the whole reason this
 * system runs on the board at all: parked cars do not move, so comparing each
 * frame against the last one YOLO actually looked at lets the detector sleep
 * through most of them. Measured on the reference camera that took the loop
 * from 0.33 fps to 7.78 and the board's load average from 3.77 to 0.29.
 * Every number here comes out of frame headers the socket already sends -
 * this panel adds no load to the thing it is measuring.
 */
export function DashboardInferencePanel({ header }: { header: FrameHeader | null }): ReactNode {
  const { t } = useTranslation('dashboard')
  const stats = useInferenceStats(header)

  if (header === null || stats.frames === 0) return null

  const savedPercent = Math.round(stats.skipRatio * 100)
  const vehicles = header.detections.length

  return (
    <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {t('dashboard:inferenceSavedLabel')}
        </Text>
        <Text style={{ fontSize: 12 }}>
          {stats.gateUnknown ? '—' : t('dashboard:inferenceSavedValue', { percent: savedPercent })}
        </Text>
      </div>

      {/* Deliberately not `percent={savedPercent}` alone: the bar reads as
          "how much of the work was avoided", so it must sit at 0 while the
          gate's behaviour is still unknown rather than imply 0% saved. */}
      <Tooltip title={t('dashboard:inferenceSavedHint')}>
        <Progress
          percent={stats.gateUnknown ? 0 : savedPercent}
          size="small"
          showInfo={false}
          strokeColor="#52c41a"
          aria-label={t('dashboard:inferenceSavedLabel')}
        />
      </Tooltip>

      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {stats.medianProcessMs === null
            ? t('dashboard:inferenceIdle')
            : t('dashboard:inferenceLatency', { ms: Math.round(stats.medianProcessMs) })}
        </Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {/* `n`, not `count`: `count` would switch i18next into plural-key
              lookup (`_one`/`_other`), which no locale here defines. */}
          {t('dashboard:inferenceVehicles', { n: vehicles })}
        </Text>
      </div>
    </div>
  )
}
