import { EnvironmentOutlined } from '@ant-design/icons'
import { Card, Flex, Space, Typography } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { formatPlateForDisplay } from '@/features/plates/format-plate-for-display'
import type { PublicPlateMatch } from './use-kiosk-plate-search'

/**
 * One match, sized for a customer reading it from ~2m away.
 *
 * Deliberately NOT `PlateMatchCard` (`features/plates/plate-match-card.tsx`):
 * that component renders `confidence` and a `<Link>` to the camera's live
 * view, both of which assume a staff viewer who can judge or act on that
 * information. Neither exists in `PublicPlateMatch` in the first place, so
 * reusing that card is not even possible without either breaking on the
 * missing fields or fabricating them - this component exists so nobody is
 * tempted to try.
 *
 * The bay code is the answer to the only question a public visitor is
 * asking ("where is my car"), so it is the largest thing on screen - larger
 * than the app's normal 32px hero (`design-guidelines.md:206`), because this
 * is read at kiosk distance, not desk distance.
 */
export function KioskPlateResult({ match }: { match: PublicPlateMatch }): ReactNode {
  const { t } = useTranslation('kiosk')

  return (
    <Card size="small">
      <Space direction="vertical" size={4}>
        <Typography.Text style={{ fontSize: 18 }} type="secondary">
          {t('kiosk:foundAt')}
        </Typography.Text>
        <Flex align="baseline" gap={12}>
          <EnvironmentOutlined style={{ fontSize: 32 }} />
          <Typography.Title level={1} style={{ margin: 0, fontSize: 48, fontWeight: 700 }}>
            {match.slot_code}
          </Typography.Title>
          <Typography.Text style={{ fontSize: 18 }} type="secondary">
            {match.floor}
          </Typography.Text>
        </Flex>
        <Typography.Text style={{ fontSize: 18, letterSpacing: 1 }} strong>
          {formatPlateForDisplay(match.plate)}
        </Typography.Text>
      </Space>
    </Card>
  )
}
