<script setup lang="ts">
import { computed } from 'vue'
import type { PollingResponseCompleted, FeedbackSuggestion, FeedbackIssue } from '@/types/api'
import { Headphones } from 'lucide-vue-next'

const props = defineProps<{
  feedback: Pick<PollingResponseCompleted, 'feedback'> | null
  loading: boolean
  errorCode?: string | null
  errorMessage?: string | null
}>()

const emit = defineEmits<{
  timestampClick: [timestamp: number]
}>()

const isV3 = computed(() => {
  return !!props.feedback?.feedback?.overall_rating
})

function handleSuggestionClick(suggestion: FeedbackSuggestion) {
  if (suggestion.timestamp != null) {
    emit('timestampClick', suggestion.timestamp)
  }
}

function handleIssueClick(issue: FeedbackIssue) {
  if (issue.timestamp != null) {
    emit('timestampClick', issue.timestamp)
  }
}

const alternativePhrases = computed(() => {
  if (!props.feedback?.feedback) return []
  // Handle key with spaces from API
  return props.feedback.feedback['alternative phrases and sentences'] || []
})
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
      <!-- V3 Structure (New) -->
      <div v-if="isV3" class="space-y-3">
        <!-- Overall Rating -->
        <div class="rounded-md bg-slate-50 p-3 border border-slate-100">
          <p class="text-sm leading-relaxed text-slate-700">
            {{ feedback.feedback.overall_rating }}
          </p>
        </div>

        <!-- Issue Analysis -->
        <div v-if="feedback.feedback.issues.length > 0" class="space-y-3">
          <h4 class="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-1">
            改进细节
          </h4>
          <div
            v-for="(issue, idx) in feedback.feedback.issues"
            :key="idx"
            class="group relative flex flex-col rounded-xl border border-slate-100 bg-white p-4 transition-all hover:border-brand-accent/30 hover:shadow-sm"
            :class="issue.timestamp != null ? 'cursor-pointer' : ''"
            @click="handleIssueClick(issue)"
          >
            <div class="mb-1 flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="text-sm font-bold text-brand-accent">
                  {{ issue.target_word || '表达点' }}
                </span>
                <span v-if="issue.ipa" class="text-xs font-mono text-slate-400">
                  {{ issue.ipa }}
                </span>
              </div>
              <Headphones
                v-if="issue.timestamp != null"
                class="text-slate-300 transition-colors group-hover:text-brand-accent"
                :size="14"
              />
            </div>
            
            <p class="text-xs font-semibold text-slate-800 mb-1">
              {{ issue.problem }}
            </p>
            <p v-if="issue.suggestion" class="text-xs text-slate-500 leading-relaxed">
              💡 {{ issue.suggestion }}
            </p>
          </div>
        </div>

        <!-- Alternative Phrases -->
        <div v-if="alternativePhrases.length > 0" class="space-y-3">
          <h4 class="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-1">
            地道表达
          </h4>
          <div class="rounded-xl border border-dashed border-slate-200 p-3 space-y-2">
            <div
              v-for="(phrase, idx) in alternativePhrases"
              :key="idx"
              class="text-xs text-slate-600 flex gap-2"
            >
              <span class="text-slate-300">•</span>
              {{ phrase }}
            </div>
          </div>
        </div>
      </div>

      <!-- V2 Structure (Legacy Compatibility) -->
      <div v-else class="mx-auto max-w-2xl space-y-3 text-sm">
        <div class="mb-4 grid grid-cols-1 gap-4 md:grid-cols-3">
          <div class="rounded bg-slate-50 p-3">
            <div class="mb-1 text-xs uppercase text-slate-500">发音</div>
            <p class="text-slate-900">{{ feedback.feedback.pronunciation }}</p>
          </div>
          <div class="rounded bg-slate-50 p-3">
            <div class="mb-1 text-xs uppercase text-slate-500">完整度</div>
            <p class="text-slate-900">{{ feedback.feedback.completeness }}</p>
          </div>
          <div class="rounded bg-slate-50 p-3">
            <div class="mb-1 text-xs uppercase text-slate-500">流畅度</div>
            <p class="text-slate-900">{{ feedback.feedback.fluency }}</p>
          </div>
        </div>

        <!-- Suggestions (V2) -->
        <div
          v-if="feedback.feedback.suggestions && feedback.feedback.suggestions.length > 0"
          class="rounded border-l-4 border-amber-400 bg-amber-50 p-3"
        >
          <p class="mb-2 text-sm font-semibold text-amber-900">改进建议:</p>
          <ul class="list-inside list-disc space-y-1">
            <li
              v-for="(suggestion, idx) in feedback.feedback.suggestions"
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

        <!-- Issues (V2) -->
        <div
          v-if="feedback.feedback.issues.length > 0"
          class="rounded border-l-4 border-rose-400 bg-rose-50 p-3"
        >
          <p class="mb-2 text-sm font-semibold text-rose-900">问题点:</p>
          <ul class="list-inside list-disc space-y-1">
            <li
              v-for="(issue, idx) in feedback.feedback.issues"
              :key="idx"
              :class="[
                'text-sm text-rose-900',
                issue.timestamp != null && 'cursor-pointer hover:text-brand-accent hover:underline'
              ]"
              @click="handleIssueClick(issue)"
            >
              {{ issue.problem }}
            </li>
          </ul>
        </div>
      </div>
    </template>

    <!-- Empty State -->
    <span v-else class="block text-center text-slate-500 py-4">暂无反馈</span>
  </div>
</template>
