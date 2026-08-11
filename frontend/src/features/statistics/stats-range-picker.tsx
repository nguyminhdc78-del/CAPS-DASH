import { DatePicker } from 'antd'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'
import type { ReactNode } from 'react'

import { HISTORY_MAX_SPAN_DAYS } from '@/features/history/use-history-queries'

const { RangePicker } = DatePicker

interface StatsRangePickerProps {
  value: [Dayjs, Dayjs]
  onChange: (value: [Dayjs, Dayjs]) => void
}

/**
 * Shared by all three charts on the statistics page - one range, three
 * views of it, rather than each chart picking its own window.
 *
 * `/stats/hourly` reuses `history_service.resolve_range` server-side (same
 * mandatory-and-capped range as `/history`), so the same
 * `HISTORY_MAX_SPAN_DAYS` soft cap applies here via `disabledDate`.
 */
export function StatsRangePicker({ value, onChange }: StatsRangePickerProps): ReactNode {
  return (
    <RangePicker
      value={value}
      allowClear={false}
      disabledDate={(current) =>
        current.isAfter(dayjs().endOf('day')) || Math.abs(current.diff(value[0], 'day')) > HISTORY_MAX_SPAN_DAYS
      }
      onChange={(next) => {
        if (next?.[0] && next[1]) onChange([next[0], next[1]])
      }}
    />
  )
}
