<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import DialogueModal from '@/components/dialogue/DialogueModal.vue'
import { dialogueApi, type DialogueEntry } from '@/services/dialogue'
import { ArrowLeft, Undo2 } from 'lucide-vue-next'
import ReviewRatingButtons from '@/components/review/ReviewRatingButtons.vue'
import ReviewQueueCounts from '@/components/review/ReviewQueueCounts.vue'
import ReviewCardActions from '@/components/review/ReviewCardActions.vue'
import ReviewPausedCards from '@/components/review/ReviewPausedCards.vue'
import ReviewAttemptStatus from '@/components/review/ReviewAttemptStatus.vue'
import RetroButton from '@/components/ui/RetroButton.vue'
import ReviewPracticeCard from '@/components/review/ReviewPracticeCard.vue'
import ReviewCardFront from '@/components/review/ReviewCardFront.vue'
import ReviewCardBack from '@/components/review/ReviewCardBack.vue'
import SentencePracticeCard from '@/components/review/SentencePracticeCard.vue'
import PracticeFields from '@/components/study/modules/PracticeFields.vue'
import PracticeOptionsModal from '@/components/review/PracticeOptionsModal.vue'
import { useReviewSession } from '@/composables/useReviewSession'
import { templateLabels, type ResourceDeck } from '@/services/content'
import { reviewHttp, type ReviewTemplate } from '@/services/review'
import { isUuid } from '@/services/api/settings'

const showPaused = ref(false)
const showPracticeOptions = ref(false)
const practiceDeck = ref<{ id: string; name: string }>()
const dialogueAvailable = ref(false)
const dialogueEntry = ref<DialogueEntry>()
void dialogueApi.available().then(value => { dialogueAvailable.value = value === true }).catch(() => {})
const route = useRoute()
const router = useRouter()
const { completedRound, deck, state, card: current, flipped, loading, busy, actionStatus, error, needsRecovery, pendingReview, practiceTemplate, uploadProgress, load, flip, rate, undo, schedule, retry, retryProcessing } = useReviewSession()
const isVocabulary = computed(() => current.value?.card_template_key.startsWith('vocabulary_'))
const wordAnswer = computed(() => ({
  english: current.value?.back.word || '', chinese: current.value?.back.meaning,
  mnemonic: current.value?.back.mnemonic, phonetic: current.value?.back.phonetic, note: current.value?.back.note,
}))
const wordMedia = computed(() => Object.fromEntries(Object.entries(current.value?.back || {}).filter(([key]) => key === 'reference_audio' || key === 'image')))
const dueLabel = computed(() => state.value?.next_due_at ? new Date(state.value.next_due_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '')

function practiceSelection(): ReviewTemplate | undefined {
  const key = String(route.query.template || '')
  return Object.hasOwn(templateLabels, key) ? key as ReviewTemplate : undefined
}

function hasPracticeSelection(): boolean {
  return Boolean(route.query.practice || route.query.template)
}

function loadEntry() {
  const deckId = String(route.params.deckId || '')
  if (!isUuid(deckId)) {
    void router.replace({ name: 'MyCourses' })
    return Promise.resolve()
  }
  return load(deckId, { template: practiceSelection() })
}

function confirmPracticeOptions(value: { template: ReviewTemplate }) {
  const query: Record<string, string> = { ...(route.query as Record<string, string>), practice: '1', template: value.template }
  delete query.templates
  delete query.limit
  void router.replace({ path: route.path, query })
}

async function openPracticeOptions() {
  showPracticeOptions.value = true
  const deckId = String(route.params.deckId || '')
  if (!isUuid(deckId) || practiceDeck.value?.id === deckId) return
  try {
    const { data } = await reviewHttp.get<ResourceDeck>(`/decks/${deckId}`)
    practiceDeck.value = { id: deckId, name: data.name }
  } catch {
    // The modal can still show a generic title.
  }
}

function closePracticeOptions() {
  showPracticeOptions.value = false
  if (!state.value) void router.push('/my-courses')
}

watch(
  () => [route.params.deckId, route.query.template, route.query.practice],
  () => {
    dialogueEntry.value = undefined
    if (!hasPracticeSelection()) {
      void openPracticeOptions()
      return
    }
    showPracticeOptions.value = false
    return loadEntry()
  },
  { immediate: true },
)
watch([completedRound, dialogueAvailable, busy, error], ([round, available, working, failure]) => {
  if (round && available && !working && !failure) dialogueEntry.value = round
})
</script>

<template>
  <div
    class="flex flex-col bg-brand-dark text-slate-900"
    :class="isVocabulary || !current ? 'min-h-screen' : 'h-[100dvh] overflow-hidden'"
    data-testid="deck-review"
  >
    <header class="sticky top-0 z-10 flex shrink-0 flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-slate-200 bg-brand-panel px-4 py-3">
      <div class="flex min-w-0 flex-1 items-center gap-3">
        <RetroButton
          variant="ghost"
          size="sm"
          :icon="ArrowLeft"
          class="shrink-0 whitespace-nowrap text-slate-500"
          :disabled="busy"
          @click="router.push('/library')"
        >
          返回题库
        </RetroButton>
        <h1 class="truncate text-sm font-semibold text-slate-800 sm:text-base">
          {{ deck?.name || '复习' }}
        </h1>
      </div>
      <div class="flex shrink-0 items-center gap-3 sm:order-3">
        <button
          type="button"
          class="text-xs text-slate-500 transition-colors hover:text-slate-800"
          :disabled="busy || loading"
          data-testid="practice-options-open"
          @click="openPracticeOptions"
        >
          练习设置
        </button>
        <button
          type="button"
          class="text-xs text-slate-500 transition-colors hover:text-slate-800"
          :disabled="busy || loading"
          @click="showPaused = true"
        >
          暂停/跳过
        </button>
        <RetroButton
          v-if="!current"
          variant="ghost"
          size="sm"
          :icon="Undo2"
          class="whitespace-nowrap"
          aria-label="撤回上一张"
          :disabled="busy || loading || !state?.can_undo || !!error"
          @click="undo"
        >
          <span class="hidden sm:inline">撤回上一张</span>
        </RetroButton>
      </div>
      <ReviewQueueCounts
        v-if="state"
        class="sm:order-2 sm:w-auto sm:shrink-0"
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
        <p>{{ error }}</p>
        <RouterLink
          v-if="pendingReview"
          :to="{ path: `/review/${pendingReview.deck_id}`, query: { template: pendingReview.card_template_key } }"
          class="mt-2 inline-block underline"
        >
          继续 {{ pendingReview.deck_name }} · {{ templateLabels[pendingReview.card_template_key] }} 的未评分作答
        </RouterLink>
        <button
          v-else
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
      <p
        v-else-if="actionStatus && !error && !loading"
        role="status"
        aria-live="polite"
        data-testid="review-action-status"
        class="mb-3 shrink-0 text-sm text-slate-500"
      >
        {{ actionStatus }}
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
          @click="loadEntry"
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
          <template #toolbar>
            <ReviewCardActions
              v-if="!flipped"
              :busy="busy || !!error"
              :can-undo="!!state?.can_undo"
              :can-schedule="!state?.attempt"
              @undo="undo"
              @schedule="schedule"
            />
          </template>
          <template #feedback>
            <ReviewAttemptStatus
              v-if="state?.attempt"
              :attempt="state.attempt"
              :retrying="busy"
              @retry="retryProcessing"
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
          <template #toolbar>
            <ReviewCardActions
              v-if="!flipped"
              :busy="busy || !!error"
              :can-undo="!!state?.can_undo"
              :can-schedule="!state?.attempt"
              @undo="undo"
              @schedule="schedule"
            />
          </template>
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
    <DialogueModal
      v-if="dialogueEntry"
      :key="dialogueEntry.entry_key"
      :entry="dialogueEntry"
      @close="dialogueEntry = undefined"
    />
    <ReviewPausedCards
      v-if="showPaused && deck"
      :deck-id="deck!.id"
      @close="showPaused = false"
      @changed="loadEntry"
    />
    <PracticeOptionsModal
      :open="showPracticeOptions"
      :deck-id="String(route.params.deckId || '')"
      :deck-name="deck?.name || practiceDeck?.name"
      :initial-template="practiceTemplate"
      @close="closePracticeOptions"
      @confirm="confirmPracticeOptions"
    />
  </div>
</template>
