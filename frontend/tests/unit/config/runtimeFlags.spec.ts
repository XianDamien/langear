import { describe, expect, it, vi } from 'vitest'
import { getUseMockMode, resolveUseMockMode } from '@/config/runtimeFlags'

describe('explicit mock mode', () => {
  it('requires an explicit startup flag', () => {
    expect(resolveUseMockMode('true')).toBe(true)
    expect(resolveUseMockMode('false')).toBe(false)
    expect(resolveUseMockMode(undefined)).toBe(false)
  })
  it('ignores stale mock preferences and URL overrides during normal startup', () => {
    vi.stubEnv('VITE_USE_MOCK', 'false')
    window.localStorage.setItem('langear-use-mock', 'true')
    window.history.replaceState({}, '', '/?mock=true')
    try { expect(getUseMockMode()).toBe(false) }
    finally { window.history.replaceState({}, '', '/'); vi.unstubAllEnvs() }
  })
})
