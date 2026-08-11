import { Table } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { buildUsersColumns } from './users-table-columns'
import type { UsersColumnActions } from './users-table-columns'
import type { UserAccount } from './use-users-queries'

export function UsersTable({
  data,
  loading,
  ...actions
}: UsersColumnActions & { data: UserAccount[]; loading: boolean }): ReactNode {
  const { t } = useTranslation(['user', 'auth', 'common'])
  const columns = buildUsersColumns(t, actions)

  return (
    <Table<UserAccount>
      rowKey="id"
      columns={columns}
      dataSource={data}
      loading={loading}
      scroll={{ x: 'max-content' }}
      pagination={{ pageSize: 20, showSizeChanger: false }}
    />
  )
}
