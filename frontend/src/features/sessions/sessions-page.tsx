import { App, Card, DatePicker, Select, Space, Statistic } from 'antd'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'
import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { DEFAULT_PAGE_SIZE } from '@/core/constants/ui-constants'
import { useErrorMessage } from '@/core/i18n/use-error-message'
import { HISTORY_DEFAULT_SPAN_DAYS, HISTORY_MAX_SPAN_DAYS } from '@/features/history/use-history-queries'
import { ClockSuspectBanner } from '@/features/system/clock-suspect-banner'
import { useCameraOptionsQuery, useSlotOptionsQuery } from '@/shared/hooks/use-parking-filter-options'
import { SessionsTable } from './sessions-table'
import { formatDurationSeconds } from './sessions-table-columns'
import { useSessionsQuery } from './use-sessions-queries'

const { RangePicker } = DatePicker

/**
 * Derived parking sessions for the selected range.
 *
 * Rendered as the "Sessions" tab inside `history-page.tsx` rather than its
 * own route - `route-definitions.tsx` is out of this phase's file ownership
 * and already wires exactly `/history`, `/statistics`, `/alerts`, `/system`.
 */
export default function SessionsPage(): ReactNode {
  const { t } = useTranslation(['history', 'common'])
  const { message } = App.useApp()
  const toMessage = useErrorMessage()
  const { data: cameras } = useCameraOptionsQuery()
  const { data: slots } = useSlotOptionsQuery()

  const [range, setRange] = useState<[Dayjs, Dayjs]>([
    dayjs().subtract(HISTORY_DEFAULT_SPAN_DAYS, 'day'),
    dayjs(),
  ])
  const [cameraCode, setCameraCode] = useState<string | undefined>(undefined)
  const [slotId, setSlotId] = useState<number | undefined>(undefined)
  const [page, setPage] = useState(1)

  const filters = useMemo(
    () => ({
      from: range[0].toISOString(),
      to: range[1].toISOString(),
      cameraCode,
      slotId,
      limit: DEFAULT_PAGE_SIZE,
      offset: (page - 1) * DEFAULT_PAGE_SIZE,
    }),
    [range, cameraCode, slotId, page],
  )

  const { data, isLoading, error } = useSessionsQuery(filters)
  if (error) void message.error(toMessage(error))

  const items = data?.items ?? []
  // Duration statistics exclude ongoing (no final duration yet) and
  // clock_suspect (timestamp not trustworthy) sessions - see the state
  // machine docstring in session_derivation_service.py. Only this page's
  // loaded rows are summarised, not the full filtered set.
  const included = items.filter((session) => !session.ongoing && !session.clock_suspect)
  const excludedCount = items.length - included.length
  const averageSeconds = included.length
    ? included.reduce((sum, session) => sum + (session.duration_seconds ?? 0), 0) / included.length
    : 0

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <ClockSuspectBanner count={items.filter((session) => session.clock_suspect).length} />
      <Space wrap>
        <RangePicker
          value={range}
          allowClear={false}
          disabledDate={(current) =>
            current.isAfter(dayjs().endOf('day')) ||
            Math.abs(current.diff(range[0], 'day')) > HISTORY_MAX_SPAN_DAYS
          }
          onChange={(next) => {
            if (next?.[0] && next[1]) {
              setRange([next[0], next[1]])
              setPage(1)
            }
          }}
        />
        <Select
          allowClear
          placeholder={t('history:filterCamera')}
          style={{ width: 180 }}
          value={cameraCode}
          onChange={(value: string | undefined) => {
            setCameraCode(value)
            setPage(1)
          }}
          options={(cameras?.items ?? []).map((camera) => ({ value: camera.code, label: camera.code }))}
        />
        <Select
          allowClear
          placeholder={t('history:filterSlot')}
          style={{ width: 160 }}
          value={slotId}
          onChange={(value: number | undefined) => {
            setSlotId(value)
            setPage(1)
          }}
          options={(slots?.items ?? []).map((slot) => ({ value: slot.id, label: `${slot.code} (${slot.floor})` }))}
        />
      </Space>
      <Space size="large">
        <Statistic title={t('history:totalSessions')} value={data?.total ?? 0} />
        <Statistic
          title={t('history:averageDuration')}
          value={formatDurationSeconds(Math.round(averageSeconds))}
        />
        <Statistic title={t('history:excludedFromStats')} value={excludedCount} />
      </Space>
      <Card>
        <SessionsTable
          data={items}
          total={data?.total ?? 0}
          loading={isLoading}
          page={page}
          onPageChange={setPage}
        />
      </Card>
    </Space>
  )
}
