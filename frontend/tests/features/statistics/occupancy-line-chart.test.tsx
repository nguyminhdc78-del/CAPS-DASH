import '@/core/i18n/i18n-config'
// Side-effect import: registers the `stats:` namespace at runtime - see the
// docstring in `use-stats-queries.ts` for why it is not in `i18n-config.ts`
// yet. The chart component itself never imports this hook module (data
// arrives via props), so a standalone render of the chart needs this here.
import '@/features/statistics/use-stats-queries'

import { render } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import i18n from '@/core/i18n/i18n-config'
import { OccupancyLineChart } from '@/features/statistics/occupancy-line-chart'
import { toOccupancySeries } from '@/features/statistics/use-stats-queries'
import type { HourlyStatRecord } from '@/features/statistics/use-stats-queries'

function makeRow(overrides: Partial<HourlyStatRecord>): HourlyStatRecord {
  return {
    scope_type: 'site',
    scope_key: '',
    hour_start: '2026-01-01T00:00:00Z',
    occupied_seconds: 0,
    free_seconds: 3600,
    unknown_seconds: 0,
    change_count: 0,
    peak_occupied: 0,
    slot_count: 10,
    clock_suspect: false,
    ...overrides,
  }
}

// Recharts' `ResponsiveContainer` measures its parent via `ResizeObserver`
// and only draws once it sees a positive size - jsdom has neither by
// default. Stubbed here (module scope, this file only) so the smoke test
// below exercises a real render instead of an empty 0x0 container.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
window.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver
HTMLElement.prototype.getBoundingClientRect = () =>
  ({ width: 600, height: 280, top: 0, left: 0, right: 600, bottom: 280, x: 0, y: 0, toJSON() {} }) as DOMRect

/**
 * `toOccupancySeries` is the load-bearing part - `/stats/hourly` stores
 * seconds, never percentages (see that schema's docstring), so converting
 * for display is a division this component must get right, including the
 * zero-slots-configured edge case that would otherwise divide by zero.
 */
describe('toOccupancySeries', () => {
  it('converts seconds to a percentage and sorts chronologically', () => {
    const rows: HourlyStatRecord[] = [
      makeRow({ hour_start: '2026-01-01T02:00:00Z', occupied_seconds: 1800, free_seconds: 1800 }),
      makeRow({ hour_start: '2026-01-01T01:00:00Z', occupied_seconds: 3600, free_seconds: 0 }),
    ]

    const series = toOccupancySeries(rows)

    expect(series.map((point) => point.hour)).toEqual([
      '2026-01-01T01:00:00Z',
      '2026-01-01T02:00:00Z',
    ])
    expect(series[0]?.occupiedPercent).toBe(100)
    expect(series[1]?.occupiedPercent).toBe(50)
  })

  it('reports 0%, not NaN, for an hour with no observed seconds at all', () => {
    const rows: HourlyStatRecord[] = [
      makeRow({ occupied_seconds: 0, free_seconds: 0, unknown_seconds: 0 }),
    ]

    expect(toOccupancySeries(rows)[0]?.occupiedPercent).toBe(0)
  })
})

describe('OccupancyLineChart', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('renders a chart surface for a typical series without crashing', () => {
    const rows: HourlyStatRecord[] = [
      makeRow({ hour_start: '2026-01-01T00:00:00Z', occupied_seconds: 900, free_seconds: 2700 }),
      makeRow({ hour_start: '2026-01-01T01:00:00Z', occupied_seconds: 1800, free_seconds: 1800 }),
    ]

    const { container } = render(<OccupancyLineChart data={toOccupancySeries(rows)} />)

    expect(container.querySelector('.recharts-surface')).not.toBeNull()
    expect(container.querySelector('.recharts-line-curve')).not.toBeNull()
  })
})
