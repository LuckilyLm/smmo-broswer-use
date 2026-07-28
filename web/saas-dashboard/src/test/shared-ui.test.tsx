import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import StatusBadge from '../components/ui/StatusBadge'
import StickySaveBar from '../components/ui/StickySaveBar'

describe('shared interaction components', () => {
  it('renders the localized status label instead of the raw enum', () => {
    render(<StatusBadge status="paused" label="已暂停" />)
    expect(screen.getByText('已暂停')).toBeInTheDocument()
    expect(screen.queryByText('paused')).not.toBeInTheDocument()
  })

  it('only renders the save bar for dirty or success state', () => {
    const { rerender } = render(<StickySaveBar dirty={false} state="idle" onCancel={() => {}} onSave={() => {}} />)
    expect(screen.queryByTestId('sticky-save-bar')).not.toBeInTheDocument()

    rerender(<StickySaveBar dirty state="idle" onCancel={() => {}} onSave={() => {}} />)
    expect(screen.getByTestId('sticky-save-bar')).toBeInTheDocument()
    expect(screen.getByText('有未保存的更改')).toBeInTheDocument()
  })
})
