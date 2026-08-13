import { EnvironmentOutlined, VideoCameraOutlined, WarningOutlined } from '@ant-design/icons'
import { Card, Flex, Space, Tag, Tooltip, Typography } from 'antd'
import dayjs from 'dayjs'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { formatPlateForDisplay } from './format-plate-for-display'
import type { PlateMatch } from './use-plate-search-query'

/**
 * A reading below this is shown as a lead to check rather than an answer.
 *
 * The floor the backend enforces is 0.30; between there and here a reading is
 * real often enough to be worth walking to and wrong often enough that a
 * guard should look at the plate themselves before telling a resident their
 * car is in B12.
 */
const SHAKY_CONFIDENCE = 0.6

/**
 * One match: which bay, and how much to trust it.
 *
 * The bay is the answer to the guard's question, so it is the largest thing
 * on the card. Everything else - camera, time, confidence - is there to let
 * them judge the answer instead of taking it on faith.
 */
export function PlateMatchCard({ match }: { match: PlateMatch }): ReactNode {
  const { t } = useTranslation(['plate', 'common'])
  const shaky = match.confidence < SHAKY_CONFIDENCE
  const vacated = match.slot_state !== 'OCCUPIED'

  return (
    <Card size="small">
      <Flex justify="space-between" align="flex-start" wrap gap={12}>
        <Space direction="vertical" size={2}>
          <Typography.Text type="secondary">{t('plate:foundAt')}</Typography.Text>
          <Space align="baseline" size={8}>
            <EnvironmentOutlined />
            <Typography.Title level={3} style={{ margin: 0 }}>
              {match.slot_code}
            </Typography.Title>
            <Typography.Text type="secondary">{match.floor}</Typography.Text>
          </Space>
          <Typography.Text strong style={{ letterSpacing: 1 }}>
            {formatPlateForDisplay(match.plate)}
          </Typography.Text>
        </Space>

        <Space direction="vertical" size={4} align="end">
          {vacated ? (
            <Tooltip title={t('plate:vacatedHint')}>
              <Tag color="warning" icon={<WarningOutlined />}>
                {t('plate:vacated')}
              </Tag>
            </Tooltip>
          ) : null}
          {shaky ? (
            <Tooltip title={t('plate:shakyHint')}>
              <Tag color="orange">{t('plate:shaky')}</Tag>
            </Tooltip>
          ) : null}
          {/* The numbers behind the badge above, so a guard can tell a 62 px
              guess from a 150 px reading rather than seeing both as "found". */}
          <Tooltip title={t('plate:provenance', { width: match.plate_width_px })}>
            <Typography.Text type="secondary">
              {t('plate:confidence', { value: Math.round(match.confidence * 100) })}
            </Typography.Text>
          </Tooltip>
          <Typography.Text type="secondary">
            {dayjs(match.read_at).format('YYYY-MM-DD HH:mm:ss')}
          </Typography.Text>
          {/* Straight to the live view of the camera that saw it: the fastest
              way to confirm the car is still there without walking down. */}
          <Link to={`/cameras/${match.camera_code}/live`}>
            <Space size={4}>
              <VideoCameraOutlined />
              {match.camera_code}
            </Space>
          </Link>
        </Space>
      </Flex>
    </Card>
  )
}
