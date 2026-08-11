import { Table } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { DEFAULT_PAGE_SIZE } from '@/core/constants/ui-constants'
import { buildHistoryColumns } from './history-table-columns'
import type { SlotStateChangeRecord } from './use-history-queries'

interface HistoryTableProps {
  data: SlotStateChangeRecord[]
  total: number
  loading: boolean
  page: number
  onPageChange: (page: number) => void
}

/** Newest-first, server-paginated - `/history` already returns rows in that
 * order (see history_repository), so no client-side sort is applied here. */
export function HistoryTable({ data, total, loading, page, onPageChange }: HistoryTableProps): ReactNode {
  const { t } = useTranslation(['history', 'common'])
  const columns = buildHistoryColumns(t)

  return (
    <Table<SlotStateChangeRecord>
      rowKey="id"
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
