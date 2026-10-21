import { coreHttp, extractApiError } from './coreApi'

export interface DeckStats {
  total_cards: number
  note_count: number
  selected_cards: number
  new_cards: number
  learning_cards: number
  review_cards: number
  completed_cards: number
  due_cards: number
}

export interface ResourceDeck {
  id: string
  name: string
  parent_id: string | null
  kind: 'standard' | 'filtered'
  deck_guid?: string | null
  in_my_courses: boolean
  scheduling_config?: Record<string, unknown>
  source_metadata?: Record<string, unknown>
}

export interface DeckTreeRow extends ResourceDeck {
  depth: number
  path: string[]
  stats: DeckStats
}

export interface DeckTreeNode extends ResourceDeck {
  stats: DeckStats
  children: DeckTreeNode[]
}

export interface DeckTree {
  decks: DeckTreeRow[]
  tree: DeckTreeNode[]
}

export interface ResourceTemplate {
  id?: string
  key: string
  ord?: number
  required_fields: string[]
  q_format?: string[]
  a_format?: string[]
  input_type?: string
}

export interface ResourceField {
  key: string
  kind: 'text' | 'audio' | 'image'
  required: boolean
  ord: number
  help?: string
}

export interface ResourceNoteType {
  id?: string
  key: string
  display_name: string
  fields: ResourceField[]
  card_templates: ResourceTemplate[]
}

export interface ResourceCard {
  id: string
  note_id: string
  deck_id: string
  card_template_key: string
  template_ord?: number
  note_revision?: number
  card_schedule_revision: number
  front: Record<string, string>
  back: Record<string, string>
  answer?: Record<string, string | null>
  input_requirement?: { type: string; required: boolean }
  renderable?: boolean
  missing_fields?: string[]
  queue?: string
  due_at?: string | null
  due_day?: number | null
  fsrs_state?: string
  reps?: number
  lapses?: number
}

export interface ResourceMedia {
  id: string
  kind: 'audio' | 'image'
  name: string
}

export interface MyCourseDeck {
  id: string
  name: string
  parent_id: string | null
  deck_guid?: string | null
  stats: DeckStats
}

export interface DashboardLeaderboardEntry {
  rank: number
  name: string
  points: number
  is_user?: boolean
}

export interface DashboardResponse {
  stats: {
    points: number
    reviewsPending: number
    streakDays: number
    dailyGoal: number
    dailyDone: number
    todayNew: number
    todayReview: number
    todayDone: number
    newDue?: number
    reviewDue?: number
    learningDue?: number
    localDate?: string
  }
  weeklyTrend: { name: string; sentences: number }[]
  heatmap: { date: string; count: number }[]
  leaderboard: DashboardLeaderboardEntry[]
}

const RESOURCE_MESSAGES: Record<string, string> = {
  ACCOUNT_NOT_IMPORTED: '此账号尚未接入内容编辑，请联系管理员。',
  UNAUTHENTICATED: '登录已过期，请重新登录。',
  RESOURCE_CONFLICT: '名称已存在，请换一个名字。',
  NOTE_FIELDS_INVALID: '请检查必填内容。',
  INVALID_CREDENTIALS: '用户名、邮箱或密码不正确。',
  RATE_LIMITED: '操作过于频繁，请稍后重试。',
  CSRF_INVALID: '登录状态已更新，请刷新页面后重试。',
  DECK_SCOPE_INVALID: '默认牌组范围只能包含你拥有的牌组。',
  DECK_HIERARCHY_CYCLE: '牌组不能成为自己的上级。',
}

export function resourceError(error: unknown): string {
  const apiError = extractApiError(error)
  return RESOURCE_MESSAGES[apiError.code] || apiError.message || '操作未完成，请检查网络后重试。'
}

export const templateLabels: Record<string, string> = {
  vocabulary_english_to_chinese: '英译中',
  vocabulary_chinese_to_english: '中译英',
  sentence_retelling: '复述',
  sentence_translation: '翻译',
  sentence_dictation: '听写',
}

export const fieldLabels: Record<string, string> = {
  word: '单词',
  meaning: '释义',
  phonetic: '音标',
  mnemonic: '助记',
  note: '笔记',
  english: '英文',
  chinese: '中文',
  reference_audio: '参考音频',
  image: '图片',
}

/** Follow a paginated list until the server returns a short page. */
export async function allResources<T>(
  path: string,
  key: string,
  params: Record<string, unknown> = {},
): Promise<T[]> {
  const rows: T[] = []
  for (let offset = 0; ; offset += 500) {
    const { data } = await coreHttp.get<Record<string, T[]>>(path, {
      params: { ...params, limit: 500, offset },
    })
    const page = data[key] || []
    rows.push(...page)
    if (page.length < 500) return rows
  }
}

export async function fetchDeckTree() {
  const { data } = await coreHttp.get<DeckTree>('/decks/tree')
  return data
}

export function fetchDeck(deckId: string) {
  return coreHttp.get<ResourceDeck>(`/decks/${deckId}`)
}

export function createDeck(name: string, parentId?: string | null) {
  return coreHttp.post<ResourceDeck>('/decks', {
    name,
    ...(parentId ? { parent_id: parentId } : {}),
  })
}

export function updateDeck(deckId: string, name: string, parentId?: string | null) {
  return coreHttp.put<ResourceDeck>(`/decks/${deckId}`, {
    name,
    ...(parentId ? { parent_id: parentId } : {}),
  })
}

export function setDeckMembership(deckId: string, joined: boolean) {
  return coreHttp.put<ResourceDeck>(`/decks/${deckId}/membership`, { joined })
}

export function fetchStudySelection(deckId: string) {
  return coreHttp.get<{ card_ids: string[] | null }>(`/decks/${deckId}/study-selection`)
}

export function saveStudySelection(deckId: string, cardIds: string[] | null) {
  return coreHttp.put<{ card_ids: string[] | null; joined: boolean }>(
    `/decks/${deckId}/study-selection`,
    { card_ids: cardIds },
  )
}

export function fetchCards(params: { deckId?: string; excludeImported?: boolean } = {}) {
  return allResources<ResourceCard>('/cards', 'cards', {
    ...(params.deckId ? { deck_id: params.deckId } : {}),
    ...(params.excludeImported ? { exclude_imported: true } : {}),
  })
}

export function fetchCard(cardId: string) {
  return coreHttp.get<ResourceCard>(`/cards/${cardId}`)
}

export async function fetchNoteTypes() {
  const { data } = await coreHttp.get<{ note_types: ResourceNoteType[] }>('/note-types')
  return data.note_types
}

export function fetchMediaAssets() {
  return allResources<ResourceMedia>('/media-assets', 'media_assets')
}

export function createNote(payload: {
  deckId: string
  noteTypeKey: string
  cardTemplateKey: string
  fields: Record<string, string>
  tags: string[]
}) {
  return coreHttp.post<{
    id: string
    cards: ResourceCard[]
    cards_created: string[]
    skipped_templates: string[]
  }>('/notes', {
    deck_id: payload.deckId,
    note_type_key: payload.noteTypeKey,
    card_template_key: payload.cardTemplateKey,
    fields: payload.fields,
    tags: payload.tags,
  })
}

export async function fetchMyCourses() {
  const { data } = await coreHttp.get<{ decks: MyCourseDeck[] }>('/my-courses')
  return data.decks
}

export async function fetchDashboard() {
  const { data } = await coreHttp.get<DashboardResponse>('/dashboard')
  return data
}
