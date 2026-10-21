import { coreHttp } from '@/services/coreApi'
import type { BackendSettingsData, CollectionSettingsData, DeckSettingsData, SettingsData } from '@/types/api'

export const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function isUuid(value: string | undefined | null): value is string {
  return Boolean(value && UUID_PATTERN.test(value))
}

function parsePositiveIntegers(value: string, label: string): number[] {
  if (!value.trim()) return []
  const parts = value.split(',').map(item => item.trim())
  if (parts.some(item => !/^\d+$/.test(item) || !Number.isSafeInteger(Number(item)) || Number(item) <= 0)) {
    throw new Error(label + '请填写用英文逗号分隔的正整数')
  }
  return parts.map(Number)
}

function parseUuids(value: string, label: string): string[] {
  if (!value.trim()) return []
  const parts = value.split(',').map(item => item.trim()).filter(Boolean)
  if (parts.some(item => !isUuid(item))) {
    throw new Error(label + '请填写用英文逗号分隔的牌组 UUID')
  }
  return [...new Set(parts)]
}

function collectionToFrontend(data: CollectionSettingsData): SettingsData {
  return {
    dailyNewLimit: data.new_limit,
    desiredRetention: data.desired_retention,
    learningSteps: data.learning_steps.join(','),
    relearningSteps: data.relearning_steps.join(','),
    maximumInterval: data.maximum_review_interval,
    defaultDeckScope: (data.default_deck_scope ?? []).join(','),
  }
}

function deckToFrontend(data: DeckSettingsData): SettingsData {
  return {
    deckId: data.deck_id,
    deckTitle: data.deck_title,
    schedulingEnabled: data.scheduling_enabled,
    dailyNewLimit: data.daily_new_limit,
    dailyReviewLimit: data.daily_review_limit,
    newCardGatherOrder: data.new_card_order_overrides?.new_card_gather_order,
    newCardSortOrder: data.new_card_order_overrides?.new_card_sort_order,
    effectiveNewCardGatherOrder: data.new_card_gather_order ?? undefined,
    effectiveNewCardSortOrder: data.new_card_sort_order ?? undefined,
    desiredRetention: data.desired_retention,
    learningSteps: data.learning_steps.join(','),
    relearningSteps: data.relearning_steps.join(','),
    maximumInterval: data.maximum_interval,
    defaultDeckScope: '',
  }
}

function validateCommon(data: SettingsData) {
  if (!Number.isFinite(data.desiredRetention) || data.desiredRetention <= 0 || data.desiredRetention >= 1) {
    throw new Error('目标保留率必须大于 0% 且小于 100%')
  }
  if (!Number.isSafeInteger(data.maximumInterval) || data.maximumInterval <= 0) {
    throw new Error('最大复习间隔必须为正整数')
  }
}

function collectionPayload(data: SettingsData): BackendSettingsData {
  validateCommon(data)
  const newLimit = data.dailyNewLimit
  if (newLimit === undefined || !Number.isSafeInteger(newLimit) || newLimit < 0 || newLimit > 10000) {
    throw new Error('每日新学数量必须为 0 至 10000 的整数')
  }
  if (data.maximumInterval > 36500) throw new Error('最大复习间隔不能超过 36500 天')
  return {
    new_limit: newLimit,
    desired_retention: data.desiredRetention,
    learning_steps: parsePositiveIntegers(data.learningSteps, '学习步长'),
    relearning_steps: parsePositiveIntegers(data.relearningSteps, '重学步长'),
    maximum_review_interval: data.maximumInterval,
    default_deck_scope: parseUuids(data.defaultDeckScope, '默认牌组范围'),
  }
}

function deckPayload(data: SettingsData): BackendSettingsData {
  validateCommon(data)
  if (data.maximumInterval > 36500) throw new Error('最大复习间隔不能超过 36500 天')
  if ([data.dailyNewLimit, data.dailyReviewLimit].some(value =>
    !Number.isSafeInteger(value) || value === undefined || value < 0 || value > 10000)) {
    throw new Error('每日数量必须为 0 至 10000 的整数')
  }
  return {
    desired_retention: data.desiredRetention,
    learning_steps: parsePositiveIntegers(data.learningSteps, '学习步长'),
    relearning_steps: parsePositiveIntegers(data.relearningSteps, '重学步长'),
    maximum_interval: data.maximumInterval,
    daily_new_limit: data.dailyNewLimit,
    daily_review_limit: data.dailyReviewLimit,
    ...(data.newCardGatherOrder === undefined ? {} : { new_card_gather_order: data.newCardGatherOrder }),
    ...(data.newCardSortOrder === undefined ? {} : { new_card_sort_order: data.newCardSortOrder }),
  }
}

export function settingsPath(deckId?: string) {
  if (deckId === undefined) return '/settings'
  if (!isUuid(deckId)) throw new Error('无效的牌组')
  return `/decks/${deckId}/settings`
}

export async function fetchSettings(deckId?: string) {
  const path = settingsPath(deckId)
  if (deckId === undefined) {
    const { data } = await coreHttp.get<CollectionSettingsData>(path)
    return { data: collectionToFrontend(data) }
  }
  const { data } = await coreHttp.get<DeckSettingsData>(path)
  if (data.deck_id !== deckId) throw new Error('牌组设置未正确返回')
  return { data: deckToFrontend(data) }
}

export async function saveSettings(data: SettingsData) {
  const path = settingsPath(data.deckId)
  if (data.deckId === undefined) {
    const { data: saved } = await coreHttp.put<CollectionSettingsData>(path, collectionPayload(data))
    return { data: collectionToFrontend(saved) }
  }
  const { data: saved } = await coreHttp.put<DeckSettingsData>(path, deckPayload(data))
  if (saved.deck_id !== data.deckId) throw new Error('保存结果与当前牌组不匹配，请重试')
  return { data: deckToFrontend(saved) }
}
