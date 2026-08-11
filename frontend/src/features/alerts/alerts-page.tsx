import { App, Card, Select, Space } from 'antd'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { DEFAULT_PAGE_SIZE } from '@/core/constants/ui-constants'
import { useErrorMessage } from '@/core/i18n/use-error-message'
import { AlertsTable } from './alerts-table'
import { useAlertsQuery } from './use-alerts-queries'

const ALERT_TYPES = ['camera_offline', 'overstay', 'disk_low', 'slot_overlap', 'clock_unsynced']
const SEVERITIES = ['info', 'warning', 'critical']

/** Unacknowledged-first, filterable by acknowledged/type/severity. Ordering
 * itself is the server's (see `alert_repository.build_list_query`); this
 * page only manages filters, pagination and the acknowledge action. */
export default function AlertsPage(): ReactNode {
  const { t } = useTranslation(['alert', 'common'])
  const { message } = App.useApp()
  const toMessage = useErrorMessage()

  const [acknowledged, setAcknowledged] = useState<boolean | undefined>(false)
  const [alertType, setAlertType] = useState<string | undefined>(undefined)
  const [severity, setSeverity] = useState<string | undefined>(undefined)
  const [page, setPage] = useState(1)

  const filters = {
    acknowledged,
    type: alertType,
    severity,
    limit: DEFAULT_PAGE_SIZE,
    offset: (page - 1) * DEFAULT_PAGE_SIZE,
  }
  const { data, isLoading, error } = useAlertsQuery(filters)
  if (error) void message.error(toMessage(error))

  return (
    <Card title={t('alert:title')}>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select
          allowClear
          placeholder={t('alert:filterStatus')}
          style={{ width: 160 }}
          value={acknowledged}
          onChange={(value: boolean | undefined) => {
            setAcknowledged(value)
            setPage(1)
          }}
          options={[
            { value: false, label: t('alert:open') },
            { value: true, label: t('alert:acknowledged') },
          ]}
        />
        <Select
          allowClear
          placeholder={t('alert:type')}
          style={{ width: 180 }}
          value={alertType}
          onChange={(value: string | undefined) => {
            setAlertType(value)
            setPage(1)
          }}
          options={ALERT_TYPES.map((type) => ({ value: type, label: t(`alert:${toCamel(type)}`) }))}
        />
        <Select
          allowClear
          placeholder={t('alert:severity')}
          style={{ width: 140 }}
          value={severity}
          onChange={(value: string | undefined) => {
            setSeverity(value)
            setPage(1)
          }}
          options={SEVERITIES.map((value) => ({ value, label: t(`alert:severity${capitalize(value)}`) }))}
        />
      </Space>
      <AlertsTable
        data={data?.items ?? []}
        total={data?.total ?? 0}
        loading={isLoading}
        page={page}
        onPageChange={setPage}
        onAcknowledgeError={(msg) => void message.error(msg)}
      />
    </Card>
  )
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

/** `disk_low` -> `diskLow`, matching the keys already in `alert.json`. */
function toCamel(value: string): string {
  return value.replace(/_([a-z])/g, (_, char: string) => char.toUpperCase())
}
