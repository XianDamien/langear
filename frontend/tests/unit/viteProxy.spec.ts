import { describe, expect, it } from 'vitest'
import { contentProxyOptions } from '../../viteProxy'

describe('content proxy options', () => {
  it('preserves the content prefix when both proxies use the release origin', () => {
    const proxy = contentProxyOptions('http://127.0.0.1:18004', 'http://127.0.0.1:18004')

    expect(proxy.target).toBe('http://127.0.0.1:18004')
    expect(proxy.rewrite).toBeUndefined()
    expect(proxy.cookiePathRewrite).toBeUndefined()
  })

  it('rewrites the content prefix for a separate direct core origin', () => {
    const proxy = contentProxyOptions('http://127.0.0.1:18005', 'http://127.0.0.1:18004')

    expect(proxy.target).toBe('http://127.0.0.1:18005')
    expect(proxy.rewrite?.('/api/content/v1/auth/legacy')).toBe('/api/v1/auth/legacy')
    expect(proxy.cookiePathRewrite).toEqual({ '/api/v1': '/api/content/v1' })
  })
})
