import { DownloadOutlined } from '@ant-design/icons'
import { Button } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { HistoryRangeFilters } from '@/core/api/query-keys'
import { useErrorMessage } from '@/core/i18n/use-error-message'
import { downloadHistoryCsv } from './use-history-queries'

interface ExportHistoryButtonProps {
  filters: Omit<HistoryRangeFilters, 'limit' | 'offset'>
  onError: (message: string) => void
}

/**
 * Downloads `/exports/history.csv` for the currently applied filters.
 *
 * The blob never touches component state - it is turned into an object URL,
 * clicked via a detached `<a download>`, and immediately revoked, so nothing
 * keeps a multi-megabyte export alive in memory longer than the download
 * itself takes to start.
 */
export function ExportHistoryButton({ filters, onError }: ExportHistoryButtonProps): ReactNode {
  const { t } = useTranslation('history')
  const toMessage = useErrorMessage()
  const [downloading, setDownloading] = useState(false)

  const handleClick = async (): Promise<void> => {
    setDownloading(true)
    try {
      const blob = await downloadHistoryCsv(filters)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `history-export-${dayjs().format('YYYYMMDD-HHmmss')}.csv`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (caught) {
      onError(toMessage(caught))
    } finally {
      setDownloading(false)
    }
  }

  return (
    <Button icon={<DownloadOutlined />} loading={downloading} onClick={() => void handleClick()}>
      {t('exportCsv')}
    </Button>
  )
}
