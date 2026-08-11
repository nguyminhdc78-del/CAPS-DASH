import { App, Card, Space, Tabs } from 'antd'
import dayjs from 'dayjs'
import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { DEFAULT_PAGE_SIZE } from '@/core/constants/ui-constants'
import { useErrorMessage } from '@/core/i18n/use-error-message'
import SessionsPage from '@/features/sessions/sessions-page'
import { ClockSuspectBanner } from '@/features/system/clock-suspect-banner'
import { ExportHistoryButton } from './export-history-button'
import { HistoryFilters } from './history-filters'
import type { HistoryFilterValues } from './history-filters'
import { HistoryTable } from './history-table'
import { HISTORY_DEFAULT_SPAN_DAYS, useHistoryQuery } from './use-history-queries'

function defaultFilters(): HistoryFilterValues {
  return {
    range: [dayjs().subtract(HISTORY_DEFAULT_SPAN_DAYS, 'day'), dayjs()],
    slotId: undefined,
    cameraCode: undefined,
    floor: undefined,
  }
}

/**
 * Slot state changes: filter bar, paginated table, CSV export.
 *
 * The "Sessions" tab renders `features/sessions/sessions-page.tsx` in place
 * rather than being a second route - `/sessions` has no entry in
 * `route-definitions.tsx` (out of this phase's file ownership; see the
 * phase's own "Sessions page (or tab)" wording), so this page is where it
 * becomes reachable.
 */
export default function HistoryPage(): ReactNode {
  const { t } = useTranslation(['history', 'common'])
  const { message } = App.useApp()
  const toMessage = useErrorMessage()

  const [filters, setFilters] = useState<HistoryFilterValues>(defaultFilters)
  const [page, setPage] = useState(1)

  const handleFiltersChange = (next: HistoryFilterValues): void => {
    setFilters(next)
    setPage(1)
  }

  const queryFilters = useMemo(
    () => ({
      from: filters.range[0].toISOString(),
      to: filters.range[1].toISOString(),
      slotId: filters.slotId,
      cameraCode: filters.cameraCode,
      floor: filters.floor,
      limit: DEFAULT_PAGE_SIZE,
      offset: (page - 1) * DEFAULT_PAGE_SIZE,
    }),
    [filters, page],
  )

  const { data, isLoading, error } = useHistoryQuery(queryFilters)
  // A range wider than the server's cap (or any other request failure)
  // surfaces here as a translated message, never a crash - `RANGE_TOO_WIDE`
  // and `RANGE_INVALID` are both already mapped in locales/*/errors.json.
  if (error) void message.error(toMessage(error))

  const items = data?.items ?? []
  const suspectCount = items.filter((row) => row.clock_suspect).length

  const historyTab = (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <ClockSuspectBanner count={suspectCount} />
      <Card
        extra={<ExportHistoryButton filters={queryFilters} onError={(msg) => void message.error(msg)} />}
      >
        <HistoryFilters value={filters} onChange={handleFiltersChange} />
        <HistoryTable data={items} total={data?.total ?? 0} loading={isLoading} page={page} onPageChange={setPage} />
      </Card>
    </Space>
  )

  return (
    <Tabs
      defaultActiveKey="history"
      items={[
        { key: 'history', label: t('history:title'), children: historyTab },
        { key: 'sessions', label: t('history:sessionsTab'), children: <SessionsPage /> },
      ]}
    />
  )
}
