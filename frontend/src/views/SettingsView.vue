<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useSettingsStore } from '@/stores/settings'
import { useDashboardStore } from '@/stores/dashboard'
import RetroCard from '@/components/ui/RetroCard.vue'
import RetroButton from '@/components/ui/RetroButton.vue'

const settingsStore = useSettingsStore()
const dashboardStore = useDashboardStore()
const {
  desiredRetention,
  learningSteps,
  relearningSteps,
  maximumInterval,
  defaultSourceScope,
  saving,
  loading,
} =
  storeToRefs(settingsStore)

onMounted(() => {
  settingsStore.load()
})

async function handleSave() {
  await settingsStore.save()
  await dashboardStore.load()
}
</script>

<template>
  <div class="animate-fadeIn max-w-xl mx-auto">
    <h2 class="text-3xl font-bold mb-6 text-brand-accent uppercase">
      设置
    </h2>

    <div
      v-if="loading"
      class="text-center text-slate-500 py-20"
    >
      加载中...
    </div>

    <template v-else>
      <RetroCard class="space-y-6">
        <div>
          <label class="block text-sm font-bold uppercase text-slate-500 mb-2">
            目标记忆率
          </label>
          <input
            v-model.number="desiredRetention"
            type="number"
            min="0.5"
            max="0.99"
            step="0.01"
            class="w-full border border-slate-200 p-2 text-slate-900 font-sans focus:border-brand-accent outline-none"
          >
        </div>

        <div>
          <label class="block text-sm font-bold uppercase text-slate-500 mb-2">
            学习步长
          </label>
          <input
            v-model.trim="learningSteps"
            type="text"
            placeholder="单位：分钟，例如 15 或 15,1440"
            class="w-full border border-slate-200 p-2 text-slate-900 font-sans focus:border-brand-accent outline-none"
          >
        </div>

        <div>
          <label class="block text-sm font-bold uppercase text-slate-500 mb-2">
            重学步长
          </label>
          <input
            v-model.trim="relearningSteps"
            type="text"
            placeholder="单位：分钟，例如 15"
            class="w-full border border-slate-200 p-2 text-slate-900 font-sans focus:border-brand-accent outline-none"
          >
        </div>

        <div>
          <label class="block text-sm font-bold uppercase text-slate-500 mb-2">
            最大间隔
          </label>
          <input
            v-model.number="maximumInterval"
            type="number"
            min="1"
            class="w-full border border-slate-200 p-2 text-slate-900 font-sans focus:border-brand-accent outline-none"
          >
        </div>

        <div>
          <label class="block text-sm font-bold uppercase text-slate-500 mb-2">
            默认教材范围
          </label>
          <input
            v-model.trim="defaultSourceScope"
            type="text"
            placeholder="留空表示全部，或填写 source ID，逗号分隔"
            class="w-full border border-slate-200 p-2 text-slate-900 font-sans focus:border-brand-accent outline-none bg-white"
          >
        </div>

        <RetroButton
          variant="primary"
          class="w-full"
          :disabled="saving"
          @click="handleSave"
        >
          {{ saving ? '保存中...' : '保存设置' }}
        </RetroButton>
      </RetroCard>
    </template>
  </div>
</template>
