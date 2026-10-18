<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Undo2 } from 'lucide-vue-next'
import ReviewRatingButtons from '@/components/review/ReviewRatingButtons.vue'
import ReviewQueueCounts from '@/components/review/ReviewQueueCounts.vue'
import ReviewPausedCards from '@/components/review/ReviewPausedCards.vue'
import ReviewAttemptStatus from '@/components/review/ReviewAttemptStatus.vue'
import RetroButton from '@/components/ui/RetroButton.vue'
import ReviewPracticeCard from '@/components/review/ReviewPracticeCard.vue'
import ReviewCardFront from '@/components/review/ReviewCardFront.vue'
import ReviewCardBack from '@/components/review/ReviewCardBack.vue'
import SentencePracticeCard from '@/components/review/SentencePracticeCard.vue'
import PracticeFields from '@/components/study/modules/PracticeFields.vue'
import { useReviewSession } from '@/composables/useReviewSession'
import { templateLabels } from '@/services/contentCore'

const showPaused = ref(false)
const route = useRoute()
const router = useRouter()
const { deck, state, card: current, loading, busy, error, needsRecovery, uploadProgress, load, flip, rate, undo, schedule, retry } = useReviewSession()
const flipped = computed(() => !!state.value?.attempt)
const isVocabulary = computed(() => current.value?.card_template_key.startsWith('vocabulary_'))
const wordAnswer = computed(() => ({
  english: current.value?.back.word || '', chinese: current.value?.back.meaning,
  mnemonic: current.value?.back.mnemonic, phonetic: current.value?.back.phonetic, note: current.value?.back.note,
}))
const wordMedia = computed(() => Object.fromEntries(Object.entries(current.value?.back || {}).filter(([key]) => key === 'reference_audio' || key === 'image')))
const dueLabel = computed(() => state.value?.next_due_at ? new Date(state.value.next_due_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '')
watch(() => route.params.deckId, id => load(String(id)), { immediate: true })
</script>

<template>
  <div
    class="flex flex-col bg-brand-dark text-slate-900"
    :class="isVocabulary || !current ? 'min-h-screen' : 'h-[100dvh] overflow-hidden'"
    data-testid="deck-review"
  >
    <header class="sticky top-0 z-10 flex shrink-0 flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-slate-200 bg-brand-panel px-4 py-3 shadow-mech-sm">
      <div class="flex min-w-0 flex-1 items-center gap-3">
        <RetroButton
          variant="ghost"
          size="sm"
          :icon="ArrowLeft"
          class="shrink-0 whitespace-nowrap"
          :disabled="busy"
          @click="router.push('/library')"
        >
          返回题库
        </RetroButton>
        <h1 class="truncate text-lg font-bold">
          {{ deck?.name || '复习' }}
        </h1>
      </div>
      <div class="flex shrink-0 items-center gap-3">
        <button
          type="button"
          class="text-xs text-slate-500 underline"
          :disabled="busy || loading"
          @click="showPaused = true"
        >
          暂停/跳过
        </button>
        <RetroButton
          variant="secondary"
          size="sm"
          :icon="Undo2"
          class="whitespace-nowrap"
          aria-label="撤销评分"
          :disabled="busy || loading || !state?.can_undo || !!error"
          @click="undo"
        >
          <span class="hidden sm:inline">撤销评分</span>
        </RetroButton>
      </div>
      <ReviewQueueCounts
        v-if="state"
        :new-remaining="state.new_remaining"
        :learning-remaining="state.learning_remaining"
        :review-remaining="state.review_remaining"
      />
    </header>
    <main
      class="mx-auto flex w-full flex-1 flex-col items-center px-4 py-4"
      :class="isVocabulary || !current ? 'justify-center sm:max-w-3xl' : 'min-h-0 max-w-6xl'"
    >
      <p
        v-if="loading"
        role="status"
        class="py-20 text-slate-500"
      >
        正在恢复复习队列…
      </p>
      <div
        v-if="error"
        role="alert"
        class="mb-3 w-full shrink-0 rounded border border-amber-300 bg-amber-50 p-3 text-center text-sm"
      >
        <p>{{ error }}</p><button
          type="button"
          class="mt-2 underline"
          :disabled="busy || loading"
          @click="retry"
        >
          {{ needsRecovery ? '恢复队列' : '重试' }}
        </button>
      </div>
      <p
        v-if="uploadProgress !== null"
        role="status"
        class="mb-3 text-sm"
      >
        正在保存录音 {{ uploadProgress }}%
      </p>
      <div
        v-if="!loading && !current && state"
        class="space-y-4 py-16 text-center text-slate-500"
        data-testid="review-empty"
      >
        <p v-if="state.empty_reason === 'no_cards'">
          这个牌组没有选中的可学卡片，请返回题库选择卡片。
        </p>
        <p v-else-if="state.empty_reason === 'waiting'">
          当前卡片已完成，下一张将在 {{ dueLabel }} 到期。
        </p>
        <p v-else>
          今日暂无可学卡片。已评分的进度已保存。
        </p>
        <RetroButton
          class="mx-auto"
          :disabled="busy || !!error"
          @click="load(String(route.params.deckId))"
        >
          检查到期卡片
        </RetroButton>
      </div>
      <div
        v-else-if="!loading && current"
        class="flex w-full flex-1 flex-col items-center"
        :class="isVocabulary ? 'justify-center py-4' : 'min-h-0'"
      >
        <div class="mb-3 flex w-full shrink-0 items-center justify-center gap-4 text-sm">
          <span class="font-bold text-brand-accent">{{ templateLabels[current.card_template_key] }}</span>
          <template v-if="!flipped">
            <button
              type="button"
              class="text-xs text-slate-500 underline"
              :disabled="busy || !!error"
              @click="schedule('bury')"
            >
              今日跳过
            </button>
            <button
              type="button"
              class="text-xs text-slate-500 underline"
              :disabled="busy || !!error"
              @click="schedule('suspend')"
            >
              暂停此卡
            </button>
          </template>
        </div>
        <SentencePracticeCard
          v-if="!isVocabulary"
          :key="state?.review_token || current.id"
          :card="current"
          :is-flipped="flipped"
          :busy="busy || !!error"
          :attempt="state?.attempt"
          @flip="flip"
        >
          <template #feedback>
            <ReviewAttemptStatus
              v-if="state?.attempt"
              :attempt="state.attempt"
            />
          </template>
          <template #rating>
            <ReviewRatingButtons
              :options="state?.rating_options"
              :disabled="busy || !!error"
              @rate="rate"
            />
          </template>
        </SentencePracticeCard>
        <ReviewPracticeCard
          v-else
          :key="state?.review_token || current.id"
          :is-flipped="flipped"
        >
          <template #front>
            <ReviewCardFront :card="current" />
          </template>
          <template #back>
            <template v-if="flipped">
              <ReviewCardBack :back-snapshot="wordAnswer" />
              <PracticeFields
                v-if="Object.keys(wordMedia).length"
                :fields="wordMedia"
              />
            </template>
          </template>
          <template #actions>
            <RetroButton
              v-if="!flipped"
              class="w-full rounded-md"
              :disabled="busy || !!error"
              @click="flip()"
            >
              {{ busy ? '保存中…' : '显示答案' }}
            </RetroButton>
            <ReviewRatingButtons
              v-else
              :options="state?.rating_options"
              :disabled="busy || !!error"
              @rate="rate"
            />
          </template>
        </ReviewPracticeCard>
      </div>
    </main>
    <ReviewPausedCards
      v-if="showPaused"
      :deck-id="String(route.params.deckId)"
      @close="showPaused = false"
      @changed="load(String(route.params.deckId))"
    />
  </div>
</template>
