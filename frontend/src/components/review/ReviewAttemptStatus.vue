<script setup lang="ts">
import { computed } from 'vue'
import type { ReviewAttempt } from '@/services/review'
const props = defineProps<{ attempt: ReviewAttempt }>()
const statuses: Record<string, string> = { pending: '等待处理', processing: '处理中', succeeded: '已完成', completed: '已完成', failed: '处理失败' }
const feedback = computed(() => Object.entries(props.attempt.ai_feedback || {}).filter(([key, value]) =>
  ['pronunciation', 'completeness', 'fluency', 'summary'].includes(key) && typeof value === 'string'))
const labels: Record<string, string> = { pronunciation: '发音', completeness: '完整度', fluency: '流利度', summary: '反馈' }
</script>
<template>
  <section
    v-if="attempt.asr_status !== 'skipped' || attempt.ai_status !== 'skipped'"
    class="space-y-2 rounded-md border border-slate-200 bg-white p-3 text-sm"
    aria-label="作答处理状态"
  >
    <p
      v-if="attempt.asr_status !== 'skipped'"
      role="status"
    >
      转写：{{ statuses[attempt.asr_status] || attempt.asr_status }}
    </p>
    <p
      v-if="attempt.asr_result?.text"
      class="whitespace-pre-wrap"
    >
      {{ attempt.asr_result.text }}
    </p>
    <p
      v-if="attempt.ai_status !== 'skipped'"
      role="status"
    >
      AI 反馈：{{ statuses[attempt.ai_status] || attempt.ai_status }}
    </p>
    <p
      v-for="[key, text] in feedback"
      :key="key"
      class="whitespace-pre-wrap"
    >
      <strong>{{ labels[key] }}</strong> {{ text }}
    </p>
    <p
      v-if="['pending', 'processing'].includes(attempt.asr_status) || ['pending', 'processing'].includes(attempt.ai_status)"
      class="text-xs text-slate-500"
    >
      作答已保存，可以先评分；转写和反馈不影响复习进度。
    </p>
    <p
      v-if="attempt.asr_status === 'failed' || attempt.ai_status === 'failed'"
      class="text-xs text-amber-700"
    >
      作答和录音已保留，评分仍可正常保存。
    </p>
  </section>
</template>
