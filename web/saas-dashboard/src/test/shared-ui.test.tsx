import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ConfirmModal from '../components/ui/ConfirmModal'
import MetricCard from '../components/ui/MetricCard'
import SafetyAlert from '../components/ui/SafetyAlert'
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

  it('labels confirmation dialogs and their close controls', () => {
    const onCancel = vi.fn()
    render(<ConfirmModal open title="删除项目" description="此操作无法撤销" onConfirm={() => {}} onCancel={onCancel} />)

    expect(screen.getByRole('alertdialog', { name: '删除项目', description: '此操作无法撤销' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '关闭' })).toHaveAttribute('type', 'button')
    fireEvent.click(screen.getByRole('button', { name: '关闭确认对话框' }))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('provides accessible safety alert actions and sparkline names', () => {
    const onViewSettings = vi.fn()
    const { rerender } = render(<SafetyAlert onViewSettings={onViewSettings} />)

    fireEvent.click(screen.getByRole('button', { name: '查看安全设置' }))
    expect(onViewSettings).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: '关闭安全提示' }))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()

    rerender(<MetricCard label="回复率" value="25%" sparkline={[1, 2, 3]} />)
    expect(screen.getByRole('img', { name: '回复率趋势图' })).toBeInTheDocument()
  })
})
