import { Flex, Typography } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { StateTag } from './state-tag'
import type { SlotState } from './state-tag'

const ALL_STATES: SlotState[] = ['FREE', 'OCCUPIED', 'UNKNOWN']

/**
 * Legend strip pairing each state tag with a short explanation.
 *
 * Built specifically so UNKNOWN never has to be inferred from a bare grey
 * tag - the API contract explicitly warns consumers not to fold unknown
 * into free, and this is where that promise is spelled out for a human
 * looking at the screen instead of the response body.
 */
export function SlotStateLegend(): ReactNode {
  const { t } = useTranslation('slot')

  return (
    <Flex gap={16} wrap align="center">
      {ALL_STATES.map((state) => (
        <Flex key={state} gap={6} align="center">
          <StateTag state={state} />
          {state === 'UNKNOWN' && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('slot:unknownNotFree')}
            </Typography.Text>
          )}
        </Flex>
      ))}
    </Flex>
  )
}
