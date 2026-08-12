import '@/core/i18n/i18n-config'

import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/core/i18n/i18n-config'
import { RoiDraftActionBar } from '@/features/roi-editor/roi-draft-action-bar'

/**
 * These controls exist because every one of them used to be a key press or a
 * gesture and nothing else - invisible on a desktop, unreachable on a tablet.
 * The point of this file is that they are on screen, so assert on what the
 * operator can see and click.
 */

function renderBar(props: Partial<Parameters<typeof RoiDraftActionBar>[0]> = {}) {
  const handlers = {
    onFinish: vi.fn(),
    onRemoveLastPoint: vi.fn(),
    onCancelDraft: vi.fn(),
    onDeleteSelected: vi.fn(),
  }
  render(
    <RoiDraftActionBar
      draftLength={0}
      hasSelection={false}
      selectionIsVertex={false}
      {...handlers}
      {...props}
    />,
  )
  return handlers
}

describe('RoiDraftActionBar', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('stays out of the way when nothing is being drawn or selected', () => {
    renderBar()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('offers finish, take-back and cancel as soon as a point is placed', () => {
    renderBar({ draftLength: 1 })
    expect(screen.getByRole('button', { name: /finish slot/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /remove last point/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /cancel drawing/i })).toBeInTheDocument()
  })

  it('refuses to finish a polygon that has too few points, and says how many are needed', () => {
    renderBar({ draftLength: 2 })
    expect(screen.getByRole('button', { name: /finish slot/i })).toBeDisabled()
    expect(screen.getByText(/at least 3 needed/i)).toBeInTheDocument()
  })

  it('enables finish at three points', () => {
    const handlers = renderBar({ draftLength: 3 })
    const finish = screen.getByRole('button', { name: /finish slot/i })
    expect(finish).toBeEnabled()
    fireEvent.click(finish)
    expect(handlers.onFinish).toHaveBeenCalledOnce()
  })

  it('takes back the last point on click', () => {
    const handlers = renderBar({ draftLength: 4 })
    fireEvent.click(screen.getByRole('button', { name: /remove last point/i }))
    expect(handlers.onRemoveLastPoint).toHaveBeenCalledOnce()
  })

  it('offers to delete the whole slot when one is selected', () => {
    const handlers = renderBar({ hasSelection: true, selectionIsVertex: false })
    const remove = screen.getByRole('button', { name: /delete slot/i })
    fireEvent.click(remove)
    expect(handlers.onDeleteSelected).toHaveBeenCalledOnce()
  })

  it('names the vertex case differently, so it is clear what is about to go', () => {
    renderBar({ hasSelection: true, selectionIsVertex: true })
    expect(screen.getByRole('button', { name: /vertex/i })).toBeInTheDocument()
  })

  it('hides the delete button while drawing - the draft has its own controls', () => {
    renderBar({ draftLength: 2, hasSelection: true, selectionIsVertex: false })
    expect(screen.queryByRole('button', { name: /delete slot/i })).toBeNull()
  })

  it('renders in Vietnamese too', async () => {
    await i18n.changeLanguage('vi')
    renderBar({ draftLength: 3 })
    expect(screen.getByRole('button', { name: /hoàn tất ô/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /bớt điểm cuối/i })).toBeInTheDocument()
  })
})
