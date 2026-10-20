import { loadEnv } from 'vite'
import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => { vi.unstubAllEnvs(); vi.resetModules() })

describe('core-only application entry', () => {
  it.each(['development', 'staging', 'production'])('declares one core API base in %s', mode => {
    const env = loadEnv(mode, process.cwd(), 'VITE_')
    expect(env.VITE_API_BASE_URL).toBe('/api/content/v1')
    expect(env.VITE_CONTENT_CORE).toBeUndefined()
    expect(env.VITE_LIBRARY_CONTENT_EDITOR).toBeUndefined()
    expect(env.VITE_CONTENT_API_BASE_URL).toBeUndefined()
  })

  it('keeps dialogue transport on the single core backend', async () => {
    vi.resetModules()
    vi.stubEnv('VITE_API_BASE_URL', '/api/content/v1')
    const { dialogueSocketUrl } = await import('@/services/dialogue')
    const url = new URL(dialogueSocketUrl('session'))
    expect(url.pathname).toBe('/api/content/v1/dialogue/sessions/session/ws')
    expect(url.protocol).toBe(window.location.protocol === 'https:' ? 'wss:' : 'ws:')
  })
})
