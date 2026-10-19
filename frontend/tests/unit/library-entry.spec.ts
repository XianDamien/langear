import { loadEnv } from 'vite'
import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => { vi.unstubAllEnvs(); vi.resetModules() })

describe('course-tree application entry', () => {
  it.each(['development', 'staging', 'production'])('keeps the existing library and content editor in %s', mode => {
    const env = loadEnv(mode, process.cwd(), 'VITE_')
    expect(env.VITE_CONTENT_CORE).toBe('false')
    expect(env.VITE_LIBRARY_CONTENT_EDITOR).toBe('true')
  })

  it.each([
    { core: 'false', base: '/api/content/v1', expected: '/api/content/v1/dialogue/sessions/session/ws' },
    { core: 'true', base: '/api/v1', expected: '/api/v1/dialogue/sessions/session/ws' },
  ])('keeps dialogue transport on the selected review backend ($core)', async ({ core, base, expected }) => {
    vi.resetModules()
    vi.stubEnv('VITE_CONTENT_CORE', core)
    vi.stubEnv('VITE_CONTENT_API_BASE_URL', base)
    const { dialogueSocketUrl } = await import('@/services/dialogue')
    const url = new URL(dialogueSocketUrl('session'))
    expect(url.pathname).toBe(expected)
    expect(url.protocol).toBe(window.location.protocol === 'https:' ? 'wss:' : 'ws:')
  })
})
