import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const page = (name: string) => readFileSync(resolve(process.cwd(), `src/pages/${name}.tsx`), 'utf8')

describe('React Doctor batch 1 page regressions', () => {
  it.each(['ExecutionRecords', 'LeadsInbox', 'ReplyRecords', 'ReplyTasks'])('%s gives every native button an explicit type', (name) => {
    expect(page(name)).not.toMatch(/<button(?![^>]*\btype=)/)
  })

  it('labels search and status controls that previously relied on placeholders', () => {
    expect(page('ExecutionRecords')).toContain('htmlFor="execution-search"')
    expect(page('ExecutionRecords')).toContain('htmlFor="execution-status"')
    expect(page('LeadsInbox')).toContain('htmlFor="lead-search"')
    expect(page('ReplyRecords')).toContain('htmlFor="reply-record-search"')
  })

  it('uses semantic controls for expandable content and dismissible overlays', () => {
    expect(page('ReplyTasks')).toContain('aria-expanded={expanded}')
    expect(page('ExecutionRecords')).toContain('aria-label="关闭执行详情" className="fixed inset-0')
    expect(page('ReplyRecords')).toContain('aria-label="关闭回复记录详情" className="fixed inset-0')
    expect(page('ReplyTasks')).toContain('aria-label="关闭回复计划详情" className="fixed inset-0')
  })

  it('keeps memo dependencies stable and avoids index-only log keys', () => {
    expect(page('ExecutionRecords')).toContain('data?.items ?? EMPTY_EXECUTIONS')
    expect(page('ReplyRecords')).toContain('data?.items ?? EMPTY_REPLY_RECORDS')
    expect(page('ReplyTasks')).toContain('allCandidatesPage?.items ?? EMPTY_REPLY_CANDIDATES')
    expect(page('ExecutionRecords')).not.toContain("key={`${item.source || 'log'}-${index}`}")
  })
})
