import axios from 'axios'
import type { PollingResponseCompleted } from '@/types/api'
import { coreHttp, errorCode, externalHttp } from './coreApi'
import { resourceError, type ResourceCard } from './content'

export const reviewHttp = coreHttp
export type SentenceTemplate = 'sentence_retelling' | 'sentence_translation' | 'sentence_dictation'
export type ReviewTemplate = SentenceTemplate | 'vocabulary_english_to_chinese' | 'vocabulary_chinese_to_english'
export const sentenceTemplates: SentenceTemplate[] = ['sentence_retelling', 'sentence_translation', 'sentence_dictation']
export interface PracticeOption { key: ReviewTemplate; count: number }

export async function fetchPracticeOptions(deckId: string): Promise<PracticeOption[]> {
  const { data } = await reviewHttp.get<{ templates: PracticeOption[] }>(`/decks/${deckId}/practice-options`)
  return data.templates.filter(option => option.count > 0)
}
export interface PendingReview { deck_id: string; deck_name: string; card_template_key: string }
export type Rating = 'again' | 'hard' | 'good' | 'easy'
export type ReviewInput = { type: 'none' } | { type: 'text'; text: string } | { type: 'audio'; temporary_media_asset_id: string; realtime_session_id?: string }
export type PracticeInput = { type: 'none' } | { type: 'text'; text: string } | { type: 'audio'; blob: Blob; realtimeSessionId?: string }
export interface RatingOption { rating: Rating; display_interval: string }
export interface DictationResult {
  kind: 'dictation_text_diff'; exact_match: boolean
  normalized_expected: string; normalized_actual: string
  differences: { category: string; expected: string; actual: string; expected_range: { start: number; end: number }; actual_range: { start: number; end: number } }[]
}
export interface ReviewAttempt {
  id: string; card_id: string; review_token: string
  front_snapshot: Record<string, string>; back_snapshot: Record<string, string>
  input_snapshot: ReviewInput; media_asset_id: string | null; rating: Rating | null
  asr_status: string; asr_result: { text?: string } | null
  ai_status: string; ai_feedback: (Partial<PollingResponseCompleted['feedback']> & { summary?: string }) | null
  deterministic_result: DictationResult | null
}
export interface FlippedReview { attempt: ReviewAttempt; card_schedule_revision: number; rating_options: RatingOption[] }
export interface QueueCounts {
  new_remaining: number; learning_remaining: number; review_remaining: number
  can_undo: boolean; next_due_at: string | null; empty_reason: 'no_cards' | 'waiting' | 'done_today' | null
}
export interface ReviewNext extends QueueCounts {
  queue_id: string; review_token: string | null
  card: (Omit<ResourceCard, 'back'> & { card_schedule_revision: number; input_requirement: { type: ReviewInput['type']; required: boolean } }) | null
  attempt?: ReviewAttempt; card_schedule_revision?: number; rating_options?: RatingOption[]
}
export interface ReviewQueue extends QueueCounts { queue_id: string; current: ReviewNext | null }

// RFC 9562 UUIDv7: 48-bit millisecond timestamp plus cryptographic randomness.
export function reviewKey(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  let millis = Date.now()
  for (let i = 5; i >= 0; i--) { bytes[i] = millis % 256; millis = Math.floor(millis / 256) }
  bytes[6] = (bytes[6]! & 0x0f) | 0x70
  bytes[8] = (bytes[8]! & 0x3f) | 0x80
  const hex = Array.from(bytes, n => n.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
export function reviewErrorCode(error: unknown): string | undefined {
  return errorCode(error)
}
export function reviewError(error: unknown): string {
  const code = reviewErrorCode(error)
  const messages: Record<string, string> = {
    LEGACY_LESSON_NOT_IMPORTED: '该课程尚未迁入复习牌组，请先在题库中选择已迁移的课程。',
    PENDING_REVIEW_OUTSIDE_SCOPE: '另一个课程或练习类型有尚未评分的作答，请先完成该作答。',
    QUEUE_EXPIRED: '复习队列已更新，请恢复队列后继续。',
    CARD_SCHEDULE_CONFLICT: '这张卡片的进度已变化，请恢复队列后继续。',
    RATING_ALREADY_SET: '评分已保存，请恢复队列查看当前进度。',
    REVIEW_TOKEN_INVALID: '当前卡片已变化，请恢复队列后继续。',
    REVIEW_TOKEN_REUSED: '这次作答已保存，请恢复队列查看。',
    DAILY_LIMIT_REACHED: '今日学习额度已用完，请恢复队列。',
    UNDO_NOT_AVAILABLE: '当前无法撤销，可能已开始下一次作答。',
    FILTERED_DECK_NOT_READY: '筛选牌组尚未开放复习，请选择普通牌组。',
    MEDIA_UNAVAILABLE: '录音存储暂时不可用，请稍后重试。',
    MEDIA_NOT_UPLOADED: '录音尚未上传完成，请重试。',
    MEDIA_UPLOAD_INVALID: '录音格式或大小不正确，请重新录音。',
  }
  return (code && messages[code]) || (error instanceof Error && !axios.isAxiosError(error) ? error.message : resourceError(error))
}

export async function uploadReviewAudio(blob: Blob, progress: (percent: number) => void): Promise<string> {
  if (!blob.size || blob.size > 25 * 1024 * 1024) throw new Error('录音不能为空，且不能超过 25 MB')
  const { data } = await reviewHttp.post<{ media_asset_id: string; upload_url: string; headers: Record<string, string> }>('/media-assets/audio-uploads', {
    content_type: 'audio/webm', size_bytes: blob.size,
  })
  // A separate client keeps application cookies and CSRF off OSS.
  await externalHttp.put(data.upload_url, blob, {
    headers: data.headers,
    onUploadProgress: event => progress(Math.round(event.loaded * 100 / (event.total || blob.size))),
  })
  await reviewHttp.post(`/media-assets/${data.media_asset_id}/confirm-upload`)
  progress(100)
  return data.media_asset_id
}
