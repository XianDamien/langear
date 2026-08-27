import http from '../http'
import type { SettingsData } from '@/types/api'

interface BackendSettingsData {
  desired_retention?: number
  learning_steps?: unknown
  relearning_steps?: unknown
  maximum_interval?: number
  default_source_scope?: unknown
}

function parseStepList(value: string): number[] {
  const normalized = value.trim()
  if (!normalized) return []

  return normalized
    .split(',')
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isInteger(item) && item > 0)
}

function parseDefaultSourceScope(value: string): number[] {
  const normalized = value.trim()
  if (!normalized) return []

  return normalized
    .split(',')
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isInteger(item) && item > 0)
}

function toFrontendSettings(data: BackendSettingsData): SettingsData {
  return {
    desiredRetention: typeof data.desired_retention === 'number' ? data.desired_retention : 0.9,
    learningSteps: Array.isArray(data.learning_steps)
      ? data.learning_steps.join(',')
      : '15',
    relearningSteps: Array.isArray(data.relearning_steps)
      ? data.relearning_steps.join(',')
      : '15',
    maximumInterval: typeof data.maximum_interval === 'number' ? data.maximum_interval : 36500,
    defaultSourceScope: Array.isArray(data.default_source_scope)
      ? data.default_source_scope.join(',')
      : '',
  }
}

function toBackendSettings(data: SettingsData): BackendSettingsData {
  return {
    desired_retention: data.desiredRetention,
    learning_steps: parseStepList(data.learningSteps),
    relearning_steps: parseStepList(data.relearningSteps),
    maximum_interval: data.maximumInterval,
    default_source_scope: parseDefaultSourceScope(data.defaultSourceScope),
  }
}

export async function fetchSettings() {
  const response = await http.get<BackendSettingsData>('/settings')
  return {
    ...response,
    data: toFrontendSettings(response.data),
  }
}

export async function saveSettings(data: SettingsData) {
  const response = await http.put<BackendSettingsData>('/settings', toBackendSettings(data))
  return {
    ...response,
    data: toFrontendSettings(response.data),
  }
}
