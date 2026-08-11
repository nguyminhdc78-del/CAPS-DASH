import { Table } from 'antd'
import dayjs from 'dayjs'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { DEFAULT_PAGE_SIZE } from '@/core/constants/ui-constants'
import { buildSessionsColumns } from './sessions-table-columns'
import type { ParkingSessionRecord } from './use-sessions-queries'

interface SessionsTableProps {
  data: ParkingSessionRecord[]
  total: number
  loading: boolean
  page: number
  onPageChange: (page: number) => void
}

/** Table only ticks its own clock while at least one row is ongoing - no
 * point re-rendering every second for a page of entirely closed sessions. */
export function SessionsTable({ data, total, loading, page, onPageChange }: SessionsTableProps): ReactNode {
  const { t } = useTranslation(['history', 'common'])
  const [now, setNow] = useState(() => dayjs())
  const hasOngoing = data.some((row) => row.ongoing)

  useEffect(() => {
    if (!hasOngoing) return undefined
    const timer = setInterval(() => setNow(dayjs()), 1_000)
    return () => clearInterval(timer)
  }, [hasOngoing])

  const columns = buildSessionsColumns(t, now)

  return (
    <Table<ParkingSessionRecord>
      rowKey={(record) => `${record.slot_id}-${record.started_at}`}
      columns={columns}
      dataSource={data}
      loading={loading}
      scroll={{ x: 'max-content' }}
      pagination={{
        current: page,
        pageSize: DEFAULT_PAGE_SIZE,
        total,
        showSizeChanger: false,
        onChange: onPageChange,
      }}
    />
  )
}
