import { reviewHttp, reviewError } from './review'

export interface DialogueSource { attempt_id: string; card_id: string }
export interface DialogueScenario {
  title: string; setup_zh: string; learner_role: string; agent_role: string
  goals: { id: string; description_zh: string }[]
  target_expressions: { english: string; meaning_zh: string; source: DialogueSource }[]
}
export interface DialogueTurn { id: string; role: 'user' | 'assistant'; text: string }
export interface DialogueSession {
  id: string; deck_id: string; scenario: DialogueScenario; status: string; finish_reason: string | null
  user_turns: number; max_user_turns: number; turns: DialogueTurn[]
}
export interface DialogueEntry { deck_id: string; review_queue_id: string; entry_key: string; attempt_ids: string[] }
export const dialogueApi = {
  available: async () => (await reviewHttp.get<{ enabled: boolean }>('/dialogue/availability')).data.enabled,
  create: async (entry: DialogueEntry) => (await reviewHttp.post<DialogueSession>('/dialogue/sessions', entry)).data,
  get: async (id: string) => (await reviewHttp.get<DialogueSession>(`/dialogue/sessions/${id}`)).data,
  finish: async (id: string) => (await reviewHttp.post<DialogueSession>(`/dialogue/sessions/${id}/finish`)).data,
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
