import http from '../http'
import { libraryContent } from '@/services/libraryContent'
import type { BackendSettingsData, SettingsData } from '@/types/api'

function parsePositiveIntegers(value: string, label: string): number[] {
  if (!value.trim()) return []
  const parts = value.split(',').map(item => item.trim())
  if (parts.some(item => !/^\d+$/.test(item) || !Number.isSafeInteger(Number(item)) || Number(item) <= 0)) {
    throw new Error(label + '请填写用英文逗号分隔的正整数')
  }
  return parts.map(Number)
}

function toFrontendSettings(data: BackendSettingsData): SettingsData {
  return {
    desiredRetention: data.desired_retention,
    learningSteps: data.learning_steps.join(','),
    relearningSteps: data.relearning_steps.join(','),
    maximumInterval: data.maximum_interval,
    defaultSourceScope: (data.default_source_scope ?? []).join(','),
    ...(data.deck_id === undefined ? {} : {
      deckId: data.deck_id, deckTitle: data.deck_title,
      schedulingEnabled: data.scheduling_enabled,
      dailyNewLimit: data.daily_new_limit, dailyReviewLimit: data.daily_review_limit,
    }),
  }
}

function toBackendSettings(data: SettingsData): BackendSettingsData {
  if (!Number.isFinite(data.desiredRetention) || data.desiredRetention <= 0 || data.desiredRetention >= 1) {
    throw new Error('目标保留率必须大于 0% 且小于 100%')
  }
  if (!Number.isSafeInteger(data.maximumInterval) || data.maximumInterval <= 0) {
    throw new Error('最大复习间隔必须为正整数')
  }
  const scoped = data.deckId !== undefined
  if (scoped && data.maximumInterval > 36500) {
    throw new Error('最大复习间隔不能超过 36500 天')
  }
  if (scoped && [data.dailyNewLimit, data.dailyReviewLimit].some(value =>
    !Number.isSafeInteger(value) || value === undefined || value < 0 || value > 10000)) {
    throw new Error('每日数量必须为 0 至 10000 的整数')
  }
  return {
    desired_retention: data.desiredRetention,
    learning_steps: parsePositiveIntegers(data.learningSteps, '学习步长'),
    relearning_steps: parsePositiveIntegers(data.relearningSteps, '重学步长'),
    maximum_interval: data.maximumInterval,
    ...(scoped ? {
      daily_new_limit: data.dailyNewLimit, daily_review_limit: data.dailyReviewLimit,
    } : { default_source_scope: parsePositiveIntegers(data.defaultSourceScope, '默认教材范围') }),
  }
}

export async function fetchSettings(deckId?: number | string) {
  const path = settingsPath(deckId)
  const client = typeof deckId === 'string' ? libraryContent : http
  const response = await client.get<BackendSettingsData>(path)
  return { ...response, data: toFrontendSettings(response.data) }
}

export async function saveSettings(data: SettingsData) {
  const path = settingsPath(data.deckId)
  const client = typeof data.deckId === 'string' ? libraryContent : http
  const response = await client.put<BackendSettingsData>(path, toBackendSettings(data))
  return { ...response, data: toFrontendSettings(response.data) }
}

function settingsPath(deckId?: number | string) {
  if (deckId === undefined) return '/settings'
  if (typeof deckId === 'string') {
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(deckId)) throw new Error('无效的牌组')
    return `/decks/${deckId}/settings`
  }
  if (!Number.isSafeInteger(deckId) || deckId <= 0 || deckId > 2147483647) throw new Error('无效的课程')
  return '/settings?deck_id=' + deckId
}
