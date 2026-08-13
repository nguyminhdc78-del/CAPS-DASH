import { Flex, Tag, Typography } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { SLOT_STATE_COLORS } from '@/core/theme/use-theme-config'
import { compareSlotCodes } from '@/features/slots/sort-slot-codes'

/**
 * One floor's FREE bay codes, as tags a customer can read at 2m.
 *
 * Text + colour, never colour alone (`code-standards.md:282`): each tag
 * carries the code itself, the FREE colour is reinforcement, not the only
 * signal. Only FREE codes ever reach this component - an empty bay holds no
 * car, so a code here identifies a space, not a vehicle (see
 * `kiosk-floor-panel.tsx`'s docstring for the fuller rationale).
 */
export function KioskFreeCodes({
  codes,
  freeCount,
}: {
  codes: string[]
  /** The floor's actual FREE count, which may exceed `codes.length` once the
   * backend's 40/floor cap kicks in. */
  freeCount: number
}): ReactNode {
  const { t } = useTranslation('kiosk')

  // The `0` counter above already says "no free bays" - a title with an
  // empty tag row under it would just be noise.
  if (codes.length === 0) return null

  const sorted = [...codes].sort(compareSlotCodes)
  // Truncation must stay visible: a floor with more free bays than the
  // backend's per-floor cap sent must never read as fully listed.
  const truncated = codes.length < freeCount

  return (
    <Flex vertical gap={8} align="center">
      <Typography.Text style={{ fontSize: 'clamp(18px, 1.6vw, 28px)' }}>
        {t('kiosk:freeCodesTitle')}
      </Typography.Text>
      {/* These codes are the one thing a driver acts on - the bay to steer
          for - so they scale with the screen like the counts above them
          rather than staying at reading-distance size on a lobby wall. */}
      <Flex gap={8} wrap justify="center">
        {sorted.map((code) => (
          <Tag
            key={code}
            color={SLOT_STATE_COLORS.FREE}
            style={{ fontSize: 'clamp(18px, 2vw, 36px)', padding: '6px 16px', lineHeight: 1.4 }}
          >
            {code}
          </Tag>
        ))}
      </Flex>
      {truncated && (
        <Typography.Text type="secondary" style={{ fontSize: 'clamp(18px, 1.6vw, 28px)' }}>
          {t('kiosk:freeCodesTruncated', { count: codes.length })}
        </Typography.Text>
      )}
    </Flex>
  )
}
