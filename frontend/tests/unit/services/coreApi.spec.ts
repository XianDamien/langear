import { AxiosError, AxiosHeaders, type AxiosRequestConfig, type AxiosResponse } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearCsrfToken,
  coreHttp,
  externalHttp,
  setUnauthorizedHandler,
} from '@/services/coreApi'

let csrfCounter = 0
let seen: AxiosRequestConfig[] = []
let onUnauthorized = vi.fn()

function reply(config: AxiosRequestConfig, data: unknown, status = 200): AxiosResponse {
  return {
    data,
    status,
    statusText: String(status),
    headers: {},
    config: config as never,
    request: {},
  }
}

function fail(config: AxiosRequestConfig, status: number, code: string) {
  return new AxiosError(
    code,
    'ERR_BAD_REQUEST',
    config as never,
    null,
    {
      data: { error: { code, message: code, request_id: 'request' } },
      status,
      statusText: String(status),
      headers: {},
      config: config as never,
    },
  )
}

beforeEach(() => {
  csrfCounter = 0
  seen = []
  onUnauthorized = vi.fn()
  clearCsrfToken()
  setUnauthorizedHandler(onUnauthorized)
  coreHttp.defaults.adapter = async (config) => {
    seen.push(config)
    if (config.url === '/auth/csrf') {
      csrfCounter += 1
      return reply(config, { csrf_token: `csrf-${csrfCounter}` })
    }
    if (config.url === '/needs-csrf' && config.headers?.['X-CSRF-Token'] === 'csrf-1') {
      return reply(config, { ok: true })
    }
    if (config.url === '/retry-csrf' && !config.csrfRetried) {
      throw fail(config, 403, 'CSRF_INVALID')
    }
    if (config.url === '/expired') throw fail(config, 401, 'UNAUTHENTICATED')
    if (config.url === '/read') return reply(config, { ok: true })
    return reply(config, { ok: true })
  }
})

describe('single core HTTP client', () => {
  it('sends GET requests without a CSRF token', async () => {
    await coreHttp.get('/read')
    expect(seen.map(request => request.url)).toEqual(['/read'])
    expect(seen[0]!.headers?.['X-CSRF-Token']).toBeUndefined()
  })

  it('fetches CSRF once and attaches it to unsafe writes', async () => {
    await coreHttp.post('/needs-csrf', {})
    expect(seen.map(request => request.url)).toEqual(['/auth/csrf', '/needs-csrf'])
    expect(seen[1]!.headers?.['X-CSRF-Token']).toBe('csrf-1')
  })

  it('refreshes the token and replays once after CSRF_INVALID', async () => {
    await coreHttp.post('/retry-csrf', {})
    expect(seen.map(request => request.url)).toEqual(['/auth/csrf', '/retry-csrf', '/auth/csrf', '/retry-csrf'])
    expect(seen[1]!.headers?.['X-CSRF-Token']).toBe('csrf-1')
    expect(seen[3]!.headers?.['X-CSRF-Token']).toBe('csrf-2')
    expect(csrfCounter).toBe(2)
  })

  it('ends the session when a request returns 401', async () => {
    await expect(coreHttp.get('/expired')).rejects.toBeTruthy()
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('lets the route guard handle an explicit skipAuthRedirect request', async () => {
    await expect(coreHttp.get('/expired', { skipAuthRedirect: true } as never)).rejects.toBeTruthy()
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('keeps cookies off third-party uploads', () => {
    expect(externalHttp.defaults.withCredentials).toBe(false)
    expect((externalHttp.defaults.headers as AxiosHeaders)['X-CSRF-Token']).toBeUndefined()
  })
})
