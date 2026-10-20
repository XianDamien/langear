import axios, { type AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import type { ApiError } from '@/types/api'

declare module 'axios' {
  export interface AxiosRequestConfig {
    /** Suppress the global error toast; callers render the error themselves. */
    skipErrorMessage?: boolean
    /** Let the route guard handle a 401 instead of a session-expiry redirect. */
    skipAuthRedirect?: boolean
    /** Internal marker for the one CSRF retry. */
    csrfRetried?: boolean
  }
}

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const coreHttp = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

/** A client for third-party upload URLs: never sends app cookies, CSRF or auth. */
export const externalHttp = axios.create({ timeout: 120_000, withCredentials: false })

const SAFE_METHODS = new Set(['get', 'head', 'options'])
const CSRF_EXEMPT = new Set(['/auth/login', '/auth/register'])
const CSRF_RETRYABLE = new Set(['auth/csrf'])

let csrfToken = ''
let csrfRequest: Promise<string> | null = null
let unauthorizedHandler: (() => void) | null = null

export function setCsrfToken(value: string | undefined | null) {
  csrfToken = value || ''
  if (csrfToken) csrfRequest = null
}

export function clearCsrfToken() {
  csrfToken = ''
  csrfRequest = null
}

export function setUnauthorizedHandler(handler: () => void) {
  unauthorizedHandler = handler
}

export function requestPath(config: AxiosRequestConfig): string {
  return String(config.url || '').split('?')[0]!
}

async function fetchCsrfToken(): Promise<string> {
  if (csrfToken) return csrfToken
  csrfRequest ??= coreHttp
    .get<{ csrf_token: string }>('/auth/csrf', { skipAuthRedirect: true })
    .then(response => {
      csrfToken = response.data.csrf_token
      return csrfToken
    })
    .finally(() => {
      csrfRequest = null
    })
  return csrfRequest
}

coreHttp.interceptors.request.use(async config => {
  const method = (config.method || 'get').toLowerCase()
  const path = requestPath(config)
  if (!SAFE_METHODS.has(method) && !CSRF_EXEMPT.has(path) && !CSRF_RETRYABLE.has(path)) {
    config.headers['X-CSRF-Token'] = await fetchCsrfToken()
  }
  return config
})

coreHttp.interceptors.response.use(
  response => response,
  async error => {
    const config = error.config as AxiosRequestConfig | undefined
    const status = error.response?.status
    const code = error.response?.data?.error?.code

    if (code === 'CSRF_INVALID' && config && !config.csrfRetried) {
      clearCsrfToken()
      return coreHttp.request({ ...config, csrfRetried: true })
    }

    if (status === 401) {
      clearCsrfToken()
      if (!config?.skipAuthRedirect) unauthorizedHandler?.()
    }

    if (!config?.skipErrorMessage) {
      ElMessage.error(extractApiError(error).message)
    }
    return Promise.reject(error)
  },
)

export function errorCode(error: unknown): string | undefined {
  return axios.isAxiosError(error) ? error.response?.data?.error?.code : undefined
}

export function extractApiError(error: unknown): ApiError {
  const body = (error as { response?: { data?: unknown } })?.response?.data as
    | {
        error?: Partial<ApiError>
        detail?: unknown
      }
    | undefined

  const nested =
    body?.detail && typeof body.detail === 'object'
      ? (body.detail as { error?: Partial<ApiError> }).error
      : undefined
  const direct = body?.error

  return {
    code: nested?.code || direct?.code || 'UNKNOWN_ERROR',
    message:
      nested?.message ||
      direct?.message ||
      (typeof body?.detail === 'string' ? body.detail : undefined) ||
      (error as { message?: string })?.message ||
      '网络请求失败',
    request_id: nested?.request_id || direct?.request_id || 'unknown',
  }
}
