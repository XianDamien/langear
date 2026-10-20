<script setup lang="ts">
import { computed } from 'vue'
import type { PollingResponseCompleted, FeedbackSuggestion, FeedbackDimension } from '@/types/api'

const props = defineProps<{
  feedback: Pick<PollingResponseCompleted, 'feedback'> | null
  loading: boolean
  errorCode?: string | null
  errorMessage?: string | null
}>()

const emit = defineEmits<{
  timestampClick: [timestamp: number]
}>()

const DIMENSION_LABELS: { key: FeedbackDimension; label: string }[] = [
  { key: 'pronunciation', label: '发音' },
  { key: 'completeness', label: '完整度' },
  { key: 'fluency', label: '流利度' },
]

function handleSuggestionClick(suggestion: FeedbackSuggestion) {
  if (suggestion.timestamp != null) {
    emit('timestampClick', suggestion.timestamp)
  }
}

// Legacy feedback stored only `issues` with an inline suggestion; keep it readable.
const allSuggestions = computed<FeedbackSuggestion[]>(() => {
  const value = props.feedback?.feedback
  if (!value) return []
  if (value.suggestions?.length) return value.suggestions
  return (value.issues || []).flatMap(issue => 'suggestion' in issue && issue.suggestion
    ? [{ text: issue.suggestion, target_word: 'target_word' in issue ? issue.target_word || null : null, timestamp: issue.timestamp }]
    : [])
})

const dimensionSections = computed(() => {
  const value = props.feedback?.feedback
  if (!value) return []
  return DIMENSION_LABELS.map(meta => ({
    key: meta.key,
    label: meta.label,
    evaluation: (value[meta.key] || '').trim(),
    suggestions: allSuggestions.value.filter(item => item.dimension === meta.key),
  })).filter(section => section.evaluation || section.suggestions.length > 0)
})

const generalSuggestions = computed(() => allSuggestions.value.filter(item => !item.dimension))

const hasContent = computed(
  () => dimensionSections.value.length > 0 || generalSuggestions.value.length > 0,
)
</script>

<template>
  <div
    class="rounded-md border border-slate-200 bg-white p-3 sm:p-4"
    data-testid="feedback-panel"
  >
    <h3 class="mb-3 text-xs font-bold uppercase text-slate-500">
      AI 评测反馈
    </h3>

    <!-- Loading State -->
    <div
      v-if="loading"
      class="animate-pulse space-y-4"
      data-testid="feedback-processing"
    >
      <div class="h-20 rounded-xl bg-slate-100" />
      <div class="space-y-2">
        <div class="h-4 w-3/4 rounded bg-slate-100" />
        <div class="h-4 w-1/2 rounded bg-slate-100" />
      </div>
      <span class="text-xs text-slate-400">AI 分析中...</span>
    </div>

    <!-- Error State -->
    <div
      v-else-if="errorCode || errorMessage"
      class="rounded-xl border-l-4 border-rose-400 bg-rose-50 p-4 text-sm"
    >
      <p class="font-semibold text-rose-900">
        {{ errorCode || 'SUBMISSION_FAILED' }}
      </p>
      <p class="mt-2 text-rose-800">
        {{ errorMessage || '提交失败，请重试' }}
      </p>
    </div>

    <!-- Feedback Content -->
    <template v-else-if="feedback">
      <div v-if="hasContent" class="mx-auto max-w-2xl space-y-2 text-sm">
        <div
          v-for="section in dimensionSections"
          :key="section.key"
          class="rounded border border-slate-100 bg-slate-50 p-3"
          data-testid="feedback-dimension"
        >
          <div class="flex items-baseline gap-2">
            <span class="shrink-0 text-xs font-bold text-slate-500">
              {{ section.label }}
            </span>
            <p class="text-sm leading-relaxed text-slate-800">
              {{ section.evaluation || '这一项没有明显问题。' }}
            </p>
          </div>
          <ul
            v-if="section.suggestions.length > 0"
            class="mt-2 space-y-1 border-t border-slate-200 pt-2"
          >
            <li
              v-for="(suggestion, idx) in section.suggestions"
              :key="idx"
              :class="[
                'text-sm text-amber-900',
                suggestion.timestamp != null && 'cursor-pointer hover:text-brand-accent hover:underline'
              ]"
              @click="handleSuggestionClick(suggestion)"
            >
              改进建议：{{ suggestion.text }}
              <span v-if="suggestion.target_word" class="font-semibold text-brand-accent">
                ({{ suggestion.target_word }})
              </span>
            </li>
          </ul>
        </div>

        <div
          v-if="generalSuggestions.length > 0"
          class="rounded border-l-4 border-amber-400 bg-amber-50 p-3"
        >
          <p class="mb-2 text-sm font-semibold text-amber-900">改进建议</p>
          <ul class="list-inside list-disc space-y-1">
            <li
              v-for="(suggestion, idx) in generalSuggestions"
              :key="idx"
              :class="[
                'text-sm text-amber-900',
                suggestion.timestamp != null && 'cursor-pointer hover:text-brand-accent hover:underline'
              ]"
              @click="handleSuggestionClick(suggestion)"
            >
              {{ suggestion.text }}
              <span v-if="suggestion.target_word" class="font-semibold text-brand-accent">
                ({{ suggestion.target_word }})
              </span>
            </li>
          </ul>
        </div>
      </div>
      <p v-else class="text-center text-sm text-slate-500">
        这次没有明确需要调整的地方，继续保持。
      </p>
    </template>

    <!-- Empty State -->
    <span v-else class="block text-center text-slate-500 py-4">暂无反馈</span>
  </div>
</template>
