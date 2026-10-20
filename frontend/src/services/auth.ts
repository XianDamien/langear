import { coreHttp, extractApiError, setCsrfToken } from './coreApi'

export interface CoreUser {
  id: string
  email: string | null
  username: string | null
}

export interface CoreCollection {
  id: string
  timezone?: string
  kind?: string
}

export interface CoreIdentity {
  user: CoreUser
  collection: CoreCollection
  csrf_token?: string
}

const AUTH_MESSAGES: Record<string, string> = {
  INVALID_CREDENTIALS: '用户名、邮箱或密码不正确。',
  EMAIL_CONFLICT: '该邮箱已注册。',
  USERNAME_CONFLICT: '该用户名已被使用。',
  INVITATION_REQUIRED: '请填写邀请码。',
  INVITATION_INVALID: '邀请码无效。',
  INVITATION_DISABLED: '邀请码已停用。',
  INVITATION_EXPIRED: '邀请码已过期。',
  INVITATION_EXHAUSTED: '邀请码使用次数已耗尽。',
  RATE_LIMITED: '尝试次数过多，请稍后再试。',
  VALIDATION_ERROR: '请检查填写内容。',
  ORIGIN_FORBIDDEN: '当前页面来源不受信任，请刷新后重试。',
  UNAUTHENTICATED: '登录已过期，请重新登录。',
}

export function authError(error: unknown): string {
  const apiError = extractApiError(error)
  return AUTH_MESSAGES[apiError.code] || apiError.message || '操作未完成，请重试。'
}

function acceptSession(data: CoreIdentity): CoreIdentity {
  setCsrfToken(data.csrf_token)
  return data
}

export async function login(identifier: string, password: string) {
  // Core keeps `email` as the wire key: it accepts a username or an email.
  const { data } = await coreHttp.post<CoreIdentity>('/auth/login', {
    email: identifier.trim(),
    password,
  }, { skipAuthRedirect: true, skipErrorMessage: true })
  return acceptSession(data)
}

export async function register(payload: {
  username?: string
  email?: string
  password: string
  invitationCode?: string
  timezone?: string
}) {
  const { data } = await coreHttp.post<CoreIdentity>('/auth/register', {
    ...(payload.username?.trim() ? { username: payload.username.trim() } : {}),
    ...(payload.email?.trim() ? { email: payload.email.trim() } : {}),
    password: payload.password,
    ...(payload.invitationCode?.trim() ? { invitation_code: payload.invitationCode.trim() } : {}),
    timezone: payload.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Shanghai',
  }, { skipAuthRedirect: true, skipErrorMessage: true })
  return acceptSession(data)
}

export async function fetchCurrentUser() {
  const { data } = await coreHttp.get<CoreIdentity>('/auth/me', {
    skipErrorMessage: true,
    skipAuthRedirect: true,
  })
  return data
}

export async function logout() {
  await coreHttp.post('/auth/logout')
  setCsrfToken('')
}
