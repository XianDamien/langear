import { reviewHttp, reviewError } from './review'

export interface DialogueSource { attempt_id: string; card_id: string }
export interface DialogueScenario {
  title: string; setup_en?: string; setup_zh: string; learner_role: string; agent_role: string
  goals: { id: string; description_en?: string; description_zh: string }[]
  target_expressions: { english: string; meaning_zh: string; source: DialogueSource }[]
}
export interface DialogueTurn { id: string; role: 'user' | 'assistant'; text: string; translation_zh?: string | null }
export interface DialogueReview {
  summary_en?: string
  summary_zh: string
  goals: { goal_id: string; completed: boolean; evidence_turn_ids: string[] }[]
  used_expressions: { english: string; evidence_turn_ids: string[] }[]
  practice_points: { advice_en?: string; advice_zh: string; source: DialogueSource }[]
}
export interface DialogueSession {
  id: string; deck_id: string; scenario: DialogueScenario; status: string; finish_reason: string | null
  user_turns: number; time_limit_seconds: number; turns: DialogueTurn[]; review: DialogueReview | null
}
export interface DialogueEntry { deck_id: string; review_queue_id: string; entry_key: string; attempt_ids: string[] }
export interface DialogueHistoryItem {
  id: string
  deck_id: string
  deck_name: string
  title: string | null
  status: string
  user_turns: number
  created_at: string
  has_review: boolean
}
export const dialogueApi = {
  available: async () => (await reviewHttp.get<{ enabled: boolean }>('/dialogue/availability')).data.enabled,
  list: async () => (await reviewHttp.get<{ sessions: DialogueHistoryItem[] }>('/dialogue/sessions')).data.sessions,
  remove: async (id: string) => { await reviewHttp.delete(`/dialogue/sessions/${id}`) },
  create: async (entry: DialogueEntry) => (await reviewHttp.post<DialogueSession>('/dialogue/sessions', entry, { timeout: 110000 })).data,
  get: async (id: string) => (await reviewHttp.get<DialogueSession>(`/dialogue/sessions/${id}`)).data,
  finish: async (id: string) => (await reviewHttp.post<DialogueSession>(`/dialogue/sessions/${id}/finish`)).data,
  review: async (id: string) => (await reviewHttp.post<DialogueSession>(`/dialogue/sessions/${id}/review`, {}, { timeout: 110000 })).data,
  translate: async (id: string, turn: string) => (await reviewHttp.post<{ chinese: string }>(`/dialogue/sessions/${id}/turns/${turn}/translation`, {}, { timeout: 65000 })).data.chinese,
}
export function dialogueSocketUrl(id: string): string {
  const url = new URL(`${reviewHttp.defaults.baseURL}/dialogue/sessions/${id}/ws`, window.location.origin)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}
export function dialogueError(error: unknown): string {
  const fallback = reviewError(error)
  return fallback === '操作未完成，请检查网络后重试。' ? '对话暂时不可用，请重试。练习进度已保存。' : fallback
}
