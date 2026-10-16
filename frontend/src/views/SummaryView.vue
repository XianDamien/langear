<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useSummaryStore } from '@/stores/summary'
import RetroCard from '@/components/ui/RetroCard.vue'
import RetroButton from '@/components/ui/RetroButton.vue'

import { computed } from 'vue'

const route = useRoute()
const router = useRouter()
const summaryStore = useSummaryStore()
const { summaryData, loading, error } = storeToRefs(summaryStore)

const lessonId = computed(() => route.params.lessonId as string)

onMounted(() => {
  summaryStore.load(lessonId.value)
})

function retry() {
  summaryStore.load(lessonId.value)
}
</script>

<template>
  <div class="animate-fadeIn max-w-2xl mx-auto">
    <h2 class="text-3xl font-bold mb-6 text-brand-accent uppercase">
      课级总结
    </h2>

    <div
      v-if="loading"
      class="text-center text-slate-500 py-20"
    >
      AI 总结生成中...
    </div>

    <div
      v-else-if="error"
      class="text-center py-20"
    >
      <p class="text-brand-alert mb-4">
        总结加载失败
      </p>
      <RetroButton
        variant="primary"
        @click="retry"
      >
        重试生成
      </RetroButton>
    </div>

    <template v-else-if="summaryData">
      <div class="space-y-4">
        <RetroCard title="总评">
          <div class="flex items-center gap-4">
            <div class="text-4xl font-bold font-pixel text-brand-accent">
              {{ summaryData.overallScore }}
            </div>
            <p class="text-slate-700">
              {{ summaryData.overallComment }}
            </p>
          </div>
        </RetroCard>

        <RetroCard title="高频问题">
          <ul class="list-disc list-inside space-y-1">
            <li
              v-for="(issue, i) in summaryData.frequentIssues"
              :key="i"
              class="text-slate-700"
            >
              {{ issue }}
            </li>
          </ul>
        </RetroCard>

        <RetroCard title="改进建议">
          <ul class="list-disc list-inside space-y-1">
            <li
              v-for="(imp, i) in summaryData.improvements"
              :key="i"
              class="text-slate-700"
            >
              {{ imp }}
            </li>
          </ul>
        </RetroCard>

        <RetroCard title="各句表现">
          <div
            v-for="cr in summaryData.cardResults"
            :key="cr.cardId"
            class="flex justify-between items-center py-2 border-b border-slate-100 last:border-0 cursor-pointer hover:bg-slate-50"
            @click="router.push(`/cards/${cr.cardId}`)"
          >
            <span class="text-slate-700">{{ cr.feedback }}</span>
            <span class="font-pixel text-brand-accent">{{ cr.score }}</span>
          </div>
        </RetroCard>

        <div class="flex gap-4 mt-6">
          <RetroButton
            variant="secondary"
            @click="router.push('/library')"
          >
            返回题库资源
          </RetroButton>
          <RetroButton
            variant="primary"
            @click="router.push('/dashboard')"
          >
            回到首页
          </RetroButton>
        </div>
      </div>
    </template>
  </div>
</template>
