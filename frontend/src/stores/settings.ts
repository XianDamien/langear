import { ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchSettings, saveSettings } from '@/services/api/settings'
import type { SettingsData } from '@/types/api'
import { ElMessage } from 'element-plus'

export const useSettingsStore = defineStore('settings', () => {
  const desiredRetention = ref(0.9)
  const learningSteps = ref('15')
  const relearningSteps = ref('15')
  const maximumInterval = ref(36500)
  const defaultSourceScope = ref('')
  const deckId = ref<number | undefined>()
  const deckTitle = ref('')
  const dailyNewLimit = ref<number | undefined>()
  const dailyReviewLimit = ref<number | undefined>()
  let loadVersion = 0
  const saving = ref(false)
  const loading = ref(false)
  const loadError = ref<string | null>(null)
  const saveError = ref<string | null>(null)

  function apply(data: SettingsData) {
    deckId.value = data.deckId
    deckTitle.value = data.deckTitle ?? ''
    dailyNewLimit.value = data.dailyNewLimit
    dailyReviewLimit.value = data.dailyReviewLimit
    desiredRetention.value = data.desiredRetention
    learningSteps.value = data.learningSteps
    relearningSteps.value = data.relearningSteps
    maximumInterval.value = data.maximumInterval
    defaultSourceScope.value = data.defaultSourceScope
  }

  async function load(requestedDeckId?: number) {
    const version = ++loadVersion
    loading.value = true
    loadError.value = null
    saveError.value = null
    try {
      const { data } = await fetchSettings(requestedDeckId)
      if (version !== loadVersion) return
      if (requestedDeckId !== undefined && data.deckId !== requestedDeckId) {
        throw new Error('牌组设置未正确返回')
      }
      apply(data)
    } catch {
      if (version === loadVersion) loadError.value = '设置加载失败，请确认课程已加入我的课程后重试'
    } finally {
      if (version === loadVersion) loading.value = false
    }
  }

  async function save(): Promise<boolean> {
    if (loading.value || loadError.value || saving.value) return false
    saving.value = true
    saveError.value = null
    const version = loadVersion
    const requestedDeckId = deckId.value
    try {
      const { data } = await saveSettings({
        desiredRetention: desiredRetention.value,
        learningSteps: learningSteps.value,
        relearningSteps: relearningSteps.value,
        maximumInterval: maximumInterval.value,
        defaultSourceScope: defaultSourceScope.value,
        ...(deckId.value === undefined ? {} : {
          deckId: deckId.value, dailyNewLimit: dailyNewLimit.value, dailyReviewLimit: dailyReviewLimit.value,
        }),
      })
      if (data.deckId !== requestedDeckId) throw new Error('保存结果与当前牌组不匹配，请重试')
      if (version === loadVersion) apply(data)
      ElMessage.success('设置已保存')
      return true
    } catch (error) {
      if (version === loadVersion) saveError.value = error instanceof Error ? error.message : '保存失败，请重试'
      return false
    } finally {
      saving.value = false
    }
  }

  return {
    desiredRetention, learningSteps, relearningSteps, maximumInterval,
    deckId, deckTitle, dailyNewLimit, dailyReviewLimit,
    defaultSourceScope, saving, loading, loadError, saveError, load, save,
  }
})
