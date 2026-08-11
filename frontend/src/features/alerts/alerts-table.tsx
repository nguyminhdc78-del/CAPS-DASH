import { Table } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { DEFAULT_PAGE_SIZE } from '@/core/constants/ui-constants'
import { buildAlertsColumns } from './alerts-table-columns'
import type { AlertsColumnActions } from './alerts-table-columns'
import type { AlertRecord } from './use-alerts-queries'

interface AlertsTableProps extends AlertsColumnActions {
  data: AlertRecord[]
  total: number
  loading: boolean
  page: number
  onPageChange: (page: number) => void
}

/** Open-first, newest-first - `/alerts` already returns rows in that order
 * (see alert_repository.build_list_query), no client-side sort applied. */
export function AlertsTable({ data, total, loading, page, onPageChange, ...actions }: AlertsTableProps): ReactNode {
  const { t } = useTranslation(['alert', 'common'])
  const columns = buildAlertsColumns(t, actions)

  return (
    <Table<AlertRecord>
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
