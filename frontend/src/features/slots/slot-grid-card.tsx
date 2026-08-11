import { Flex, Typography } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { StateTag } from '@/shared/components/state-tag'
import type { SlotRecord } from './use-slots-queries'

const STATE_LABEL_KEY = {
  FREE: 'slot:stateFree',
  OCCUPIED: 'slot:stateOccupied',
  UNKNOWN: 'slot:stateUnknown',
} as const

/**
 * One slot, as a card. `role="button"` + `tabIndex=0` + an Enter/Space
 * handler make it a keyboard-operable control even though it renders as a
 * `div` (a real `<button>` would fight antd's `Card` padding and the
 * `StateTag` layout for no benefit) - every card must be reachable and
 * activatable without a mouse, per this phase's accessibility requirement.
 */
export function SlotGridCard({
  slot,
  onSelect,
}: {
  slot: SlotRecord
  onSelect: (slot: SlotRecord) => void
}): ReactNode {
  const { t } = useTranslation('slot')

  const activate = (): void => onSelect(slot)

  return (
    <Flex
      vertical
      align="center"
      justify="center"
      gap={6}
      role="button"
      tabIndex={0}
      aria-label={t('slot:cardAriaLabel', { code: slot.code, state: t(STATE_LABEL_KEY[slot.current_state]) })}
      onClick={activate}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          activate()
        }
      }}
      style={{
        border: '1px solid var(--ant-color-border, #d9d9d9)',
        borderRadius: 8,
        padding: '16px 8px',
        cursor: 'pointer',
        minHeight: 88,
      }}
    >
      <Typography.Text strong>{slot.code}</Typography.Text>
      <StateTag state={slot.current_state} />
    </Flex>
  )
}
