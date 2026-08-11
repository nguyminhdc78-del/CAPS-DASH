import { Table } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { buildSlotsColumns } from './slots-table-columns'
import type { SlotsColumnActions } from './slots-table-columns'
import type { SlotRecord } from './use-slots-queries'

export function SlotsTable({
  data,
  loading,
  ...actions
}: SlotsColumnActions & { data: SlotRecord[]; loading: boolean }): ReactNode {
  const { t } = useTranslation(['slot', 'common'])
  const columns = buildSlotsColumns(t, actions)

  return (
    <Table<SlotRecord>
      rowKey="id"
      columns={columns}
      dataSource={data}
      loading={loading}
      scroll={{ x: 'max-content' }}
      pagination={{ pageSize: 50, showSizeChanger: false }}
      onRow={(record) => ({
        onClick: () => actions.onViewDetail(record),
        style: { cursor: 'pointer' },
      })}
    />
  )
}
