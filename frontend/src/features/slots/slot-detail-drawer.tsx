import { Descriptions, Drawer, Empty, List, Tag, Tooltip, Typography } from 'antd'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { StateTag } from '@/shared/components/state-tag'
import { useSlotHistoryQuery } from './use-slots-queries'
import type { SlotRecord } from './use-slots-queries'

dayjs.extend(relativeTime)

/**
 * Read-only detail view for one slot: current state, when it started, a
 * link to the owning camera, and its last 10 history rows. Everything here
 * is security-tier data (slot codes, camera identity) - this drawer only
 * ever renders inside `/slots`, which is already gated at `security` and
 * above by `route-definitions.tsx`.
 */
export function SlotDetailDrawer({
  slot,
  cameraLabel,
  cameraLinkTo,
  onClose,
}: {
  slot: SlotRecord | null
  cameraLabel: string
  cameraLinkTo: string | null
  onClose: () => void
}): ReactNode {
  const { t } = useTranslation(['slot', 'common'])
  const { data: history, isLoading: historyLoading } = useSlotHistoryQuery(slot?.id ?? null)

  return (
    <Drawer title={slot ? t('slot:detailTitle', { code: slot.code }) : ''} open={slot !== null} onClose={onClose} width={420}>
      {slot && (
        <>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label={t('slot:state')}>
              <StateTag state={slot.current_state} />
            </Descriptions.Item>
            <Descriptions.Item label={t('slot:since')}>
              {slot.state_since ? (
                <Tooltip title={dayjs(slot.state_since).format('YYYY-MM-DD HH:mm:ss')}>
                  {dayjs(slot.state_since).fromNow()}
                </Tooltip>
              ) : (
                '—'
              )}
            </Descriptions.Item>
            <Descriptions.Item label={t('slot:floor')}>{slot.floor}</Descriptions.Item>
            <Descriptions.Item label={t('slot:camera')}>
              {cameraLinkTo ? <Link to={cameraLinkTo}>{cameraLabel}</Link> : cameraLabel}
            </Descriptions.Item>
          </Descriptions>

          <Typography.Title level={5} style={{ marginTop: 24 }}>
            {t('slot:recentChanges')}
          </Typography.Title>
          <List
            loading={historyLoading}
            dataSource={history ?? []}
            locale={{ emptyText: <Empty description={t('slot:noRecentChanges')} /> }}
            renderItem={(row) => (
              <List.Item>
                <List.Item.Meta
                  title={
                    <>
                      <StateTag state={row.previous_state} /> {'->'} <StateTag state={row.new_state} />
                    </>
                  }
                  description={
                    <>
                      <Tooltip title={dayjs(row.changed_at).format('YYYY-MM-DD HH:mm:ss')}>
                        {dayjs(row.changed_at).fromNow()}
                      </Tooltip>
                      {row.clock_suspect && (
                        <Tag color="warning" style={{ marginInlineStart: 8 }}>
                          {t('slot:clockSuspect')}
                        </Tag>
                      )}
                    </>
                  }
                />
              </List.Item>
            )}
          />
        </>
      )}
    </Drawer>
  )
}
