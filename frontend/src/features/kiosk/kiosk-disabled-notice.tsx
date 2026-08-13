import { Result } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * Shown when `/public/summary` 404s with `PUBLIC_KIOSK_DISABLED` - the
 * operator has not opted into the public surface. `PUBLIC_KIOSK_ENABLED`
 * defaults false on purpose (`plan.md`): a public, unauthenticated display
 * is an opt-in act, not something a deployment gets by upgrading.
 *
 * Read by an operator standing in front of the screen wondering why it is
 * blank, not by a customer, so this is allowed to be plain and technical -
 * it names the setting rather than offering a vague apology.
 */
export function KioskDisabledNotice(): ReactNode {
  const { t } = useTranslation('kiosk')

  return (
    <Result
      status="info"
      title={t('kiosk:disabledTitle')}
      subTitle={t('kiosk:disabledHint')}
    />
  )
}
