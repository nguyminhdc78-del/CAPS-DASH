import { Empty } from 'antd'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { SLOT_GRID_BREAKPOINTS } from '@/core/constants/ui-constants'
import { SlotGridCard } from './slot-grid-card'
import type { SlotRecord } from './use-slots-queries'

const WIDE_QUERY = '(min-width: 1200px)'
const MEDIUM_QUERY = '(min-width: 700px)'

function computeColumns(): number {
  if (typeof window === 'undefined') return SLOT_GRID_BREAKPOINTS.narrow
  if (window.matchMedia(WIDE_QUERY).matches) return SLOT_GRID_BREAKPOINTS.wide
  if (window.matchMedia(MEDIUM_QUERY).matches) return SLOT_GRID_BREAKPOINTS.medium
  return SLOT_GRID_BREAKPOINTS.narrow
}

/**
 * Wide -> medium -> narrow column count, tracked with `matchMedia` listeners
 * rather than a resize observer or a CSS file: this codebase has no CSS
 * files at all (everything is inline style / antd tokens, see
 * `theme-provider.tsx` for the same `matchMedia` pattern), and the
 * breakpoints only need to change on an actual viewport-class crossing, not
 * on every pixel of a resize.
 */
function useResponsiveColumnCount(): number {
  const [columns, setColumns] = useState(computeColumns)

  useEffect(() => {
    const wide = window.matchMedia(WIDE_QUERY)
    const medium = window.matchMedia(MEDIUM_QUERY)
    const update = (): void => setColumns(computeColumns())
    wide.addEventListener('change', update)
    medium.addEventListener('change', update)
    return () => {
      wide.removeEventListener('change', update)
      medium.removeEventListener('change', update)
    }
  }, [])

  return columns
}

export function SlotGrid({
  slots,
  onSelect,
}: {
  slots: readonly SlotRecord[]
  onSelect: (slot: SlotRecord) => void
}): ReactNode {
  const { t } = useTranslation('common')
  const columns = useResponsiveColumnCount()

  if (slots.length === 0) return <Empty description={t('common:noData')} />

  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${columns}, 1fr)`, gap: 12 }}>
      {slots.map((slot) => (
        <SlotGridCard key={slot.id} slot={slot} onSelect={onSelect} />
      ))}
    </div>
  )
}
