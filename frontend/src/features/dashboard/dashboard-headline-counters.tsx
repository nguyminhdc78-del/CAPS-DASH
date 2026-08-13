import { AppstoreOutlined, CarOutlined, CheckCircleOutlined, QuestionOutlined } from '@ant-design/icons'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { OccupancySummary } from '@/features/slots/use-slots-queries'
import { useCountUp } from './use-count-up'

type StatVariant = 'primary' | 'success' | 'danger' | 'neutral'

/**
 * One Droom-style gradient stat tile: an icon in a translucent square beside a
 * large count-up number and its label. Loading shows an em-dash rather than a
 * skeleton so the coloured tile never flashes empty white.
 */
function StatTile({
  label,
  value,
  variant,
  icon,
  loading,
}: {
  label: string
  value: number
  variant: StatVariant
  icon: ReactNode
  loading: boolean
}): ReactNode {
  const display = useCountUp(value)

  return (
    <div className={`droom-stat droom-stat--${variant}`} role="group" aria-label={label}>
      <div className="droom-stat__icon" aria-hidden>
        {icon}
      </div>
      <div className="droom-stat__body">
        <div className="droom-stat__value">{loading ? '—' : display}</div>
        <div className="droom-stat__label">{label}</div>
      </div>
    </div>
  )
}

/**
 * Total / free / occupied / unknown - four independent numbers, large, with
 * a count-up animation on change (`useCountUp`).
 *
 * `unknown` gets its own tile and a neutral slate gradient (`--neutral`),
 * never summed into `free` and never rendered green. See
 * `use-slots-queries.ts::OccupancySummary`'s docstring: a slot the detector
 * cannot currently classify (camera offline, still warming up, occluded) is
 * a different fact from an empty one, and folding the two together would let
 * a stalled camera silently report itself as free parking.
 */
export function DashboardHeadlineCounters({
  summary,
  loading,
}: {
  summary: OccupancySummary | null
  loading: boolean
}): ReactNode {
  const { t } = useTranslation('slot')

  return (
    <div className="droom-stat-grid">
      <StatTile
        label={t('slot:total')}
        value={summary?.total ?? 0}
        variant="primary"
        icon={<AppstoreOutlined />}
        loading={loading}
      />
      <StatTile
        label={t('slot:free')}
        value={summary?.free ?? 0}
        variant="success"
        icon={<CheckCircleOutlined />}
        loading={loading}
      />
      <StatTile
        label={t('slot:occupied')}
        value={summary?.occupied ?? 0}
        variant="danger"
        icon={<CarOutlined />}
        loading={loading}
      />
      <StatTile
        label={t('slot:unknown')}
        value={summary?.unknown ?? 0}
        variant="neutral"
        icon={<QuestionOutlined />}
        loading={loading}
      />
    </div>
  )
}
