import axios from 'axios'
import { getUseMockMode } from '@/config/runtimeFlags'
import { getAccessToken } from '@/services/authToken'
import type { CoreIdentity } from '@/services/contentCore'

export const libraryEditorEnabled = import.meta.env.VITE_LIBRARY_CONTENT_EDITOR === 'true' && !getUseMockMode()

// The original app keeps its legacy session; content writes use a mapped core session.
export const libraryContent = axios.create({ baseURL: '/api/content/v1', withCredentials: true, timeout: 15000 })
let csrfToken = ''
let authenticatedToken: string | null = null
let sessionRequest: Promise<void> | null = null

export async function ensureContentSession() {
  const token = getAccessToken()
  if (!token) throw new Error('请先登录')
  if (authenticatedToken === token && csrfToken) return
  sessionRequest ??= libraryContent.post<CoreIdentity>('/auth/legacy', {}, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(({ data }) => {
    csrfToken = data.csrf_token || ''
    authenticatedToken = token
  }).finally(() => { sessionRequest = null })
  await sessionRequest
  if (getAccessToken() !== token) throw new Error('登录状态已变化，请重试')
}

libraryContent.interceptors.request.use(async config => {
  if (config.url === '/auth/legacy') return config
  await ensureContentSession()
  if (!['get', 'head', 'options'].includes(config.method || 'get')) {
    config.headers['X-CSRF-Token'] = csrfToken
  }
  return config
})
libraryContent.interceptors.response.use(response => response, error => {
  if (error.response?.status === 401 || error.response?.data?.error?.code === 'CSRF_INVALID') {
    authenticatedToken = null
    csrfToken = ''
  }
  return Promise.reject(error)
})

export async function contentResources<T>(path: string, key: string, params: Record<string, unknown> = {}): Promise<T[]> {
  const rows: T[] = []
  for (let offset = 0; ; offset += 500) {
    const { data } = await libraryContent.get<Record<string, T[]>>(path, { params: { ...params, limit: 500, offset } })
    const page = data[key] || []
    rows.push(...page)
    if (page.length < 500) return rows
  }
}

export async function logoutLibraryContent() {
  if (!libraryEditorEnabled) return
  try {
    const { data } = await axios.get<{csrf_token: string}>('/api/content/v1/auth/csrf', { withCredentials: true, timeout: 5000 })
    await axios.post('/api/content/v1/auth/logout', {}, {
      withCredentials: true, timeout: 5000, headers: { 'X-CSRF-Token': data.csrf_token },
    })
  } catch (error) {
    if (!axios.isAxiosError(error) || error.response?.status !== 401) throw error
  }
  authenticatedToken = null
  csrfToken = ''
}
