import axios from 'axios'

export const contentCoreEnabled = import.meta.env.VITE_CONTENT_CORE === 'true'
export interface ResourceDeck { id: string; name: string; parent_id: string | null; kind: 'standard' | 'filtered' }
export interface ResourceTemplate { key: string; required_fields: string[] }
export interface ResourceField { key: string; kind: 'text' | 'audio' | 'image'; required: boolean; ord: number }
export interface ResourceNoteType { key: string; display_name: string; fields: ResourceField[]; card_templates: ResourceTemplate[] }
export interface ResourceCard { id: string; note_id: string; deck_id: string; card_template_key: string; front: Record<string,string>; back: Record<string,string> }
export interface ResourceMedia { id: string; kind: 'audio' | 'image'; name: string }
export interface CoreIdentity { user: { id: string; email: string | null; username?: string | null }; collection: { id: string }; csrf_token?: string }

export const coreHttp = axios.create({ baseURL: '/api/v1', withCredentials: true, timeout: 30000 })
let csrfToken = ''
let csrfRequest: Promise<string> | null = null
export function setCoreCsrf(value: string) { csrfToken = value }
coreHttp.interceptors.request.use(async config => {
  if (!['get', 'head', 'options'].includes(config.method || 'get') && !['/auth/login', '/auth/register'].includes(config.url || '')) {
    if (!csrfToken) {
      csrfRequest ??= coreHttp.get<{csrf_token: string}>('/auth/csrf').then(r => r.data.csrf_token).finally(() => { csrfRequest = null })
      csrfToken = await csrfRequest
    }
    config.headers['X-CSRF-Token'] = csrfToken
  }
  return config
})
export function resourceError(error: unknown): string {
  const code = axios.isAxiosError(error) ? error.response?.data?.error?.code : undefined
  const messages: Record<string,string> = { RESOURCE_CONFLICT: '名称已存在，请换一个名字。', UNAUTHENTICATED: '登录已过期，请重新登录。', NOTE_FIELDS_INVALID: '请检查必填内容。', INVALID_CREDENTIALS: '用户名、邮箱或密码不正确。', RATE_LIMITED: '操作过于频繁，请稍后重试。', CSRF_INVALID: '登录状态已更新，请刷新页面后重试。' }
  return messages[code] || '操作未完成，请检查网络后重试。'
}
export async function allResources<T>(path: string, key: string): Promise<T[]> {
  const rows: T[] = []
  for (let offset = 0; ; offset += 500) {
    const { data } = await coreHttp.get<Record<string,T[]>>(path, { params: { limit: 500, offset } })
    const page = data[key] || []
    rows.push(...page)
    if (page.length < 500) return rows
  }
}
export const templateLabels: Record<string,string> = {
  vocabulary_english_to_chinese: '英译中', vocabulary_chinese_to_english: '中译英',
  sentence_retelling: '复述', sentence_translation: '翻译', sentence_dictation: '听写',
}
export const fieldLabels: Record<string,string> = { word: '单词', meaning: '释义', phonetic: '音标', note: '笔记', english: '英文', chinese: '中文', reference_audio: '参考音频', image: '图片' }
