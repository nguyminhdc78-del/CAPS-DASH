import { WarningOutlined } from '@ant-design/icons'
import { Tag, Tooltip } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * Marks one row's timestamp as untrustworthy.
 *
 * The board has no battery-backed clock (`db/clock_guard.py` on the
 * backend), so a row written between a power-cut boot and the next NTP sync
 * can carry a wrong `changed_at`. Rather than hide those rows, every list
 * that can contain one (history, sessions, hourly stats) tags them with this
 * badge and excludes them from totals - see `clock-suspect-banner.tsx` for
 * the page-level count. Text + icon, not colour alone, so the flag still
 * reads for a colour-blind operator.
 */
export function SuspectBadge(): ReactNode {
  const { t } = useTranslation('common')

  return (
    <Tooltip title={t('clockSuspectTooltip')}>
      <Tag color="warning" icon={<WarningOutlined />}>
        {t('clockSuspect')}
      </Tag>
    </Tooltip>
  )
}
