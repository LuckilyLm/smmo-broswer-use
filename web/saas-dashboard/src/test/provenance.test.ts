import { describe, expect, it } from 'vitest'

import { isDemoData } from '../utils/provenance'

describe('demo provenance', () => {
  it('recognizes execution snapshot and inherited API markers', () => {
    expect(isDemoData({ config_snapshot: { demo_seed: true } })).toBe(true)
    expect(isDemoData({ config_snapshot: { provenance: 'demo' } })).toBe(true)
    expect(isDemoData({ provenance: 'demo' })).toBe(true)
  })

  it('does not label unmarked live records as demo', () => {
    expect(isDemoData({ config_snapshot: {} })).toBe(false)
    expect(isDemoData({ provenance: 'live' })).toBe(false)
    expect(isDemoData(null)).toBe(false)
  })
})
