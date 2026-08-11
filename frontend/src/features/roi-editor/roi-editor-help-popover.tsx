import { QuestionCircleOutlined } from '@ant-design/icons'
import { Button, Popover, Typography } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

const SHORTCUT_KEYS = [
  'shortcutDrawClick',
  'shortcutCloseDraft',
  'shortcutCancelDraft',
  'shortcutInsertVertex',
  'shortcutDeleteVertex',
  'shortcutUndo',
  'shortcutRedo',
  'shortcutPan',
  'shortcutZoom',
] as const

/** Keeps the on-screen shortcut list next to the code that reads the keys
 * (use-roi-keyboard-shortcuts.ts), so the two cannot silently drift apart. */
export function RoiEditorHelpPopover(): ReactNode {
  const { t } = useTranslation(['roi', 'common'])

  return (
    <Popover
      trigger="click"
      title={t('roi:helpTitle')}
      content={
        <div style={{ maxWidth: 320 }}>
          <Typography.Paragraph>
            <ul style={{ paddingInlineStart: 20, margin: 0 }}>
              {SHORTCUT_KEYS.map((key) => (
                <li key={key}>{t(`roi:${key}`)}</li>
              ))}
            </ul>
          </Typography.Paragraph>
        </div>
      }
    >
      <Button icon={<QuestionCircleOutlined />} aria-label={t('roi:helpTitle')} />
    </Popover>
  )
}
