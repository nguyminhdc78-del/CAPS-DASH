import { Table } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { buildCamerasColumns } from './cameras-table-columns'
import type { CamerasColumnActions } from './cameras-table-columns'
import type { CameraRecord } from './use-cameras-queries'

export function CamerasTable({
  data,
  loading,
  ...actions
}: CamerasColumnActions & { data: CameraRecord[]; loading: boolean }): ReactNode {
  const { t } = useTranslation(['camera', 'common'])
  const columns = buildCamerasColumns(t, actions)

  return (
    <Table<CameraRecord>
      rowKey="id"
      columns={columns}
      dataSource={data}
      loading={loading}
      scroll={{ x: 'max-content' }}
      pagination={{ pageSize: 20, showSizeChanger: false }}
    />
  )
}
