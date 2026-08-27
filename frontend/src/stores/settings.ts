import { ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchSettings, saveSettings } from '@/services/api/settings'
import { ElMessage } from 'element-plus'

export const useSettingsStore = defineStore('settings', () => {
  const desiredRetention = ref(0.9)
  const learningSteps = ref('15')
  const relearningSteps = ref('15')
  const maximumInterval = ref(36500)
  const defaultSourceScope = ref('')
  const saving = ref(false)
  const loading = ref(false)

  async function load() {
    loading.value = true
    try {
      const { data } = await fetchSettings()
      desiredRetention.value = data.desiredRetention
      learningSteps.value = data.learningSteps
      relearningSteps.value = data.relearningSteps
      maximumInterval.value = data.maximumInterval
      defaultSourceScope.value = data.defaultSourceScope
    } finally {
      loading.value = false
    }
  }

  async function save() {
    saving.value = true
    try {
      await saveSettings({
        desiredRetention: desiredRetention.value,
        learningSteps: learningSteps.value,
        relearningSteps: relearningSteps.value,
        maximumInterval: maximumInterval.value,
        defaultSourceScope: defaultSourceScope.value,
      })
      ElMessage.success('设置已保存')
    } catch {
      ElMessage.error('保存失败，请重试')
    } finally {
      saving.value = false
    }
  }

  return {
    desiredRetention,
    learningSteps,
    relearningSteps,
    maximumInterval,
    defaultSourceScope,
    saving,
    loading,
    load,
    save,
  }
})
