import { CarOutlined, CheckCircleOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import { Tag } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { SLOT_STATE_COLORS } from '@/core/theme/use-theme-config'

/**
 * The three states a slot can be in, mirroring the backend's `SlotState`.
 *
 * Defined here rather than in a generated types file: this component is the
 * one place in the frontend allowed to turn a state into a colour, and
 * keeping the type next to that mapping is what stops them from drifting
 * apart as the app grows.
 */
export type SlotState = 'FREE' | 'OCCUPIED' | 'UNKNOWN'

const STATE_ICON: Record<SlotState, ReactNode> = {
  FREE: <CheckCircleOutlined />,
  OCCUPIED: <CarOutlined />,
  UNKNOWN: <QuestionCircleOutlined />,
}

const STATE_LABEL_KEY: Record<SlotState, string> = {
  FREE: 'slot:stateFree',
  OCCUPIED: 'slot:stateOccupied',
  UNKNOWN: 'slot:stateUnknown',
}

/**
 * `SlotState` -> colour + icon + localized label, and nowhere else.
 *
 * UNKNOWN renders grey with a question mark, never a shade of green. Until
 * the vote filter has seen a full window of frames the system has not
 * established what is in that slot, and colouring it like FREE would send a
 * driver toward a space nobody has actually looked at - worse than showing
 * nothing at all. Every other component that needs to show a slot's state
 * renders this instead of touching `SLOT_STATE_COLORS` itself.
 */
export function StateTag({ state }: { state: SlotState }): ReactNode {
  const { t } = useTranslation('slot')

  return (
    <Tag icon={STATE_ICON[state]} color={SLOT_STATE_COLORS[state]} style={{ marginInlineEnd: 0 }}>
      {t(STATE_LABEL_KEY[state])}
    </Tag>
  )
}
