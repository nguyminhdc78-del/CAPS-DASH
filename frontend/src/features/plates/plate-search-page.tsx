import { App, Alert, Card, Checkbox, Empty, Flex, Input, Space, Spin, Typography } from 'antd'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useErrorMessage } from '@/core/i18n/use-error-message'
import { PlateMatchCard } from './plate-match-card'
import { MIN_PLATE_QUERY_LENGTH, usePlateSearchQuery } from './use-plate-search-query'

/**
 * "Where did they park?" - asked by a guard, about a resident who cannot
 * remember.
 *
 * One box and one answer. The guard is usually standing at a desk with
 * somebody waiting in front of them, so the page opens focused on the input
 * and the bay is the biggest thing in the result.
 *
 * Search happens on submit, never as-you-type: each request is written to the
 * audit log, and a plate identifies a vehicle and through it a person. Eight
 * audit rows for one question would make the log useless as a record of who
 * looked for what.
 */
export default function PlateSearchPage(): ReactNode {
  const { t } = useTranslation(['plate', 'common'])
  const { message } = App.useApp()
  const toMessage = useErrorMessage()

  const [typed, setTyped] = useState('')
  const [submitted, setSubmitted] = useState('')
  const [includeVacated, setIncludeVacated] = useState(false)

  const { data, isFetching, error } = usePlateSearchQuery(submitted, includeVacated)
  if (error) void message.error(toMessage(error))

  const tooShort = typed.trim().length > 0 && typed.trim().length < MIN_PLATE_QUERY_LENGTH
  const searched = submitted.trim().length >= MIN_PLATE_QUERY_LENGTH
  const matches = data?.matches ?? []

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Card>
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          <Input.Search
            autoFocus
            size="large"
            allowClear
            value={typed}
            placeholder={t('plate:searchPlaceholder')}
            enterButton={t('plate:search')}
            aria-label={t('plate:searchAriaLabel')}
            onChange={(event) => setTyped(event.target.value)}
            onSearch={(value) => setSubmitted(value)}
          />
          <Flex justify="space-between" align="center" wrap gap={8}>
            <Typography.Text type="secondary">
              {tooShort ? t('plate:tooShort', { min: MIN_PLATE_QUERY_LENGTH }) : t('plate:searchHint')}
            </Typography.Text>
            {/* Off by default. The usual question is where a car IS; a bay the
                car has left is an answer to a different and rarer question,
                and offering it unasked sends a guard walking to an empty
                space they will trust. */}
            <Checkbox
              checked={includeVacated}
              onChange={(event) => setIncludeVacated(event.target.checked)}
            >
              {t('plate:includeVacated')}
            </Checkbox>
          </Flex>
        </Space>
      </Card>

      {isFetching ? (
        <Flex justify="center" style={{ padding: 32 }}>
          <Spin />
        </Flex>
      ) : null}

      {!isFetching && searched && matches.length === 0 ? (
        <Card>
          <Empty description={t('plate:noMatches', { query: data?.query ?? submitted })} />
          {/* The commonest reason for nothing, and it is not a broken search:
              a plate is only recorded when the camera could read one, and a
              car parked tail-in behind a pillar never offers a plate to read.
              Saying so stops a guard concluding the car is not in the
              building. */}
          <Alert type="info" showIcon message={t('plate:noMatchesHint')} style={{ marginTop: 12 }} />
        </Card>
      ) : null}

      {!isFetching && matches.length > 0 ? (
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          {matches.map((match) => (
            <PlateMatchCard key={`${match.slot_code}-${match.read_at}`} match={match} />
          ))}
        </Space>
      ) : null}
    </Space>
  )
}
