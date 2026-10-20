<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import RetroCard from '@/components/ui/RetroCard.vue'
import RetroButton from '@/components/ui/RetroButton.vue'
import { fetchCard, resourceError, templateLabels, type ResourceCard } from '@/services/content'

const route = useRoute()
const router = useRouter()
const card = ref<ResourceCard | null>(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await fetchCard(String(route.params.cardId))
    card.value = data
  } catch (cause) {
    error.value = resourceError(cause)
  } finally {
    loading.value = false
  }
}

onMounted(load)

function fieldEntries(value: Record<string, string> | undefined) {
  return Object.entries(value || {}).filter(([, text]) => Boolean(text))
}
</script>

<template>
  <div class="animate-fadeIn max-w-2xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-3xl font-bold text-brand-accent uppercase">
        卡片详情
      </h2>
      <RetroButton
        variant="ghost"
        size="sm"
        @click="router.back()"
      >
        返回
      </RetroButton>
    </div>

    <div
      v-if="loading"
      role="status"
      class="text-center text-slate-500 py-20"
    >
      加载中...
    </div>
    <div
      v-else-if="error"
      role="alert"
      class="border border-amber-400 p-4"
    >
      <p>{{ error }}</p>
      <button
        type="button"
        class="mt-3 underline"
        @click="load"
      >
        重试
      </button>
    </div>
    <div
      v-else-if="card"
      class="space-y-4"
    >
      <RetroCard :title="templateLabels[card.card_template_key] || '卡片'">
        <dl class="space-y-3">
          <div
            v-for="[key, text] in fieldEntries(card.front)"
            :key="`front-${key}`"
          >
            <dt class="text-xs font-bold uppercase text-slate-500">
              {{ key }}
            </dt>
            <dd class="whitespace-pre-wrap break-words text-slate-900">
              {{ text }}
            </dd>
          </div>
        </dl>
      </RetroCard>

      <RetroCard title="答案">
        <dl class="space-y-3">
          <div
            v-for="[key, text] in fieldEntries(card.back)"
            :key="`back-${key}`"
          >
            <dt class="text-xs font-bold uppercase text-slate-500">
              {{ key }}
            </dt>
            <dd class="whitespace-pre-wrap break-words text-slate-900">
              {{ text }}
            </dd>
          </div>
        </dl>
      </RetroCard>

      <p class="text-sm text-slate-500">
        AI 反馈与练习证据保存在对应复习记录中。
      </p>
    </div>
  </div>
</template>
