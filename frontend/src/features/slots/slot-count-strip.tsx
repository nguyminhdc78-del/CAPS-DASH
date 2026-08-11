import { SyncOutlined } from '@ant-design/icons'
import { Flex, Tooltip, Typography } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { SLOT_STATE_COLORS } from '@/core/theme/use-theme-config'
import type { FloorSummary, OccupancySummary, SlotRecord } from './use-slots-queries'

interface Counts {
  total: number
  free: number
  occupied: number
  unknown: number
}

function countRows(rows: readonly SlotRecord[]): Counts {
  let free = 0
  let occupied = 0
  let unknown = 0
  for (const row of rows) {
    if (row.current_state === 'FREE') free += 1
    else if (row.current_state === 'OCCUPIED') occupied += 1
    else unknown += 1
  }
  return { total: rows.length, free, occupied, unknown }
}

/** The `/summary` slice comparable to the current floor selection. */
function targetFor(summary: OccupancySummary | undefined, floor: string | null): FloorSummary | OccupancySummary | undefined {
  if (summary === undefined) return undefined
  if (floor === null) return summary
  return summary.by_floor.find((entry) => entry.floor === floor)
}

function countsDiffer(a: Counts, b: Counts): boolean {
  return a.total !== b.total || a.free !== b.free || a.occupied !== b.occupied || a.unknown !== b.unknown
}

function CountBlock({ label, value, color, tooltip }: { label: string; value: number; color: string; tooltip?: string }): ReactNode {
  const block = (
    <Flex vertical align="center" gap={2} role="group" aria-label={label} style={{ minWidth: 88 }}>
      <Typography.Text type="secondary">{label}</Typography.Text>
      <Typography.Title level={3} style={{ margin: 0, color }}>
        {value}
      </Typography.Title>
    </Flex>
  )
  return tooltip === undefined ? block : <Tooltip title={tooltip}>{block}</Tooltip>
}

/**
 * Four independent numbers, never three.
 *
 * `unknown` is its own block with its own tooltip, not folded into `free` -
 * that promise is the entire point of this component (see the API contract
 * docstring on `OccupancySummary`). It is rendered from the fetched rows
 * (the same rows the grid/table show) and cross-checked against `/summary`;
 * a genuine disagreement between "what I just counted" and "what the
 * dedicated aggregate endpoint says" almost always means one of the two
 * queries is mid-refetch, not that either number is wrong - so this shows a
 * quiet "refreshing" hint instead of a second, conflicting set of digits
 * that would make the board look broken.
 */
export function SlotCountStrip({
  rows,
  summary,
  floor,
}: {
  rows: readonly SlotRecord[]
  summary: OccupancySummary | undefined
  floor: string | null
}): ReactNode {
  const { t } = useTranslation('slot')

  const counts = countRows(rows)
  const target = targetFor(summary, floor)
  const isRefreshing = target !== undefined && countsDiffer(counts, target)

  return (
    <Flex gap={24} wrap align="center">
      <CountBlock label={t('slot:total')} value={counts.total} color="inherit" />
      <CountBlock label={t('slot:free')} value={counts.free} color={SLOT_STATE_COLORS.FREE} />
      <CountBlock label={t('slot:occupied')} value={counts.occupied} color={SLOT_STATE_COLORS.OCCUPIED} />
      <CountBlock
        label={t('slot:unknown')}
        value={counts.unknown}
        color={SLOT_STATE_COLORS.UNKNOWN}
        tooltip={t('slot:unknownNotFree')}
      />
      {isRefreshing && (
        <Typography.Text type="secondary" aria-live="polite" style={{ fontSize: 12 }}>
          <SyncOutlined spin /> {t('slot:countsRefreshing')}
        </Typography.Text>
      )}
    </Flex>
  )
}
