<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Undo2 } from 'lucide-vue-next'
import ReviewRatingButtons from '@/components/review/ReviewRatingButtons.vue'
import RetroButton from '@/components/ui/RetroButton.vue'
import ReviewPracticeCard from '@/components/review/ReviewPracticeCard.vue'
import ReviewCardFront from '@/components/review/ReviewCardFront.vue'
import ReviewCardBack from '@/components/review/ReviewCardBack.vue'
import FlashcardContainer from '@/components/study/modules/FlashcardContainer.vue'
import PracticeFields from '@/components/study/modules/PracticeFields.vue'
import { contentResources, libraryContent } from '@/services/libraryContent'
import { resourceError, templateLabels, type ResourceCard, type ResourceDeck } from '@/services/contentCore'

const route = useRoute()
const router = useRouter()
const deck = ref<ResourceDeck>()
const cards = ref<ResourceCard[]>([])
const index = ref(0)
const flipped = ref(false)
const finished = ref(false)
const wordBackUsed = ref(false)
const loading = ref(true)
const error = ref('')
const current = computed(() => cards.value[index.value])
const isVocabulary = computed(() => current.value?.card_template_key.startsWith('vocabulary_'))
const wordAnswer = computed(() => ({
  english: current.value?.back.word || '', chinese: current.value?.back.meaning,
  mnemonic: current.value?.back.mnemonic,
  phonetic: current.value?.back.phonetic, note: current.value?.back.note,
}))
const wordMedia = computed(() => Object.fromEntries(Object.entries(current.value?.back || {}).filter(([key]) => key === 'reference_audio' || key === 'image')))
const previousWordIndex = computed(() => {
  if (wordBackUsed.value) return -1
  for (let i = index.value - 1; i >= 0; i--) {
    if (cards.value[i]?.card_template_key.startsWith('vocabulary_')) return i
  }
  return -1
})
function previousWord() {
  if (previousWordIndex.value < 0) return
  index.value = previousWordIndex.value
  wordBackUsed.value = true
  flipped.value = false
}
let generation = 0
async function load() {
  const request = ++generation
  const id = String(route.params.deckId)
  loading.value = true
  error.value = ''
  deck.value = undefined
  cards.value = []
  index.value = 0
  flipped.value = false
  finished.value = false
  wordBackUsed.value = false
  try {
    const [response, rows] = await Promise.all([
      libraryContent.get<ResourceDeck>(`/decks/${id}`),
      contentResources<ResourceCard>('/cards', 'cards', { deck_id: id, exclude_imported: true }),
    ])
    if (request !== generation) return
    deck.value = response.data
    cards.value = rows
  } catch (cause) {
    if (request === generation) error.value = resourceError(cause)
  } finally { if (request === generation) loading.value = false }
}
function next() {
  if (!flipped.value) return
  if (index.value + 1 === cards.value.length) finished.value = true
  else index.value++
  flipped.value = false
}
function previous() { if (index.value > 0) { index.value--; flipped.value = false } }
function restart() { index.value = 0; flipped.value = false; finished.value = false; wordBackUsed.value = false }
watch(() => route.params.deckId, load, { immediate: true })
onBeforeUnmount(() => { generation++ })
</script>

<template>
  <div
    class="flex min-h-screen flex-col bg-brand-dark text-slate-900"
    data-testid="deck-review"
  >
    <header class="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-slate-200 bg-brand-panel px-4 py-3 shadow-mech-sm">
      <div class="flex min-w-0 items-center gap-3">
        <RetroButton
          variant="ghost"
          size="sm"
          :icon="ArrowLeft"
          class="shrink-0 whitespace-nowrap"
          @click="router.push('/library')"
        >
          返回题库
        </RetroButton>
        <h1 class="truncate text-lg font-bold text-slate-900">
          {{ deck?.name || '复习' }}
        </h1>
        <span
          v-if="cards.length && !finished"
          class="shrink-0 text-xs text-slate-500"
        >{{ index + 1 }} / {{ cards.length }}</span>
      </div>
      <RetroButton
        variant="secondary"
        size="sm"
        :icon="Undo2"
        disabled
        title="评分功能尚未启用"
      >
        撤销评分
      </RetroButton>
    </header>
    <main class="mx-auto flex w-full flex-1 flex-col items-center justify-center px-4 py-6 sm:max-w-3xl">
      <p class="mb-4 text-center text-xs text-slate-500">
        翻卡练习 · 暂不记录评分和复习进度
      </p>
      <p
        v-if="loading"
        role="status"
        class="py-20 text-center text-slate-500"
      >
        正在加载卡片…
      </p>
      <div
        v-else-if="error"
        role="alert"
        class="space-y-4 py-20 text-center"
      >
        <p>{{ error }}</p>
        <RetroButton
          class="mx-auto"
          @click="load"
        >
          重试
        </RetroButton>
      </div>
      <div
        v-else-if="!cards.length"
        class="py-20 text-center text-slate-500"
      >
        这个牌组还没有卡片。请返回题库添加卡片。
      </div>
      <div
        v-else-if="finished"
        class="space-y-6 py-20 text-center"
        role="status"
      >
        <h2 class="text-2xl font-bold">
          本轮翻卡完成
        </h2>
        <p class="text-slate-500">
          已查看 {{ cards.length }} 张卡片
        </p>
        <RetroButton
          class="mx-auto"
          @click="restart"
        >
          再练一遍
        </RetroButton>
      </div>
      <div
        v-else-if="current"
        class="flex w-full flex-1 flex-col items-center justify-center py-4"
      >
        <p class="mb-3 text-center text-sm font-bold text-brand-accent">
          {{ templateLabels[current.card_template_key] }}
        </p>
        <component
          :is="isVocabulary ? ReviewPracticeCard : FlashcardContainer"
          :key="current.id"
          :is-flipped="flipped"
          :class="isVocabulary ? '' : 'min-h-80 w-full flex-1'"
        >
          <template #front>
            <ReviewCardFront
              v-if="isVocabulary"
              :card="current"
            />
            <PracticeFields
              v-else
              :key="`${current.id}-front`"
              :fields="current.front"
            />
          </template>
          <template #back>
            <template v-if="isVocabulary">
              <ReviewCardBack :back-snapshot="wordAnswer" />
              <PracticeFields
                v-if="Object.keys(wordMedia).length"
                :fields="wordMedia"
              />
            </template>
            <PracticeFields
              v-else
              :key="`${current.id}-back`"
              :fields="current.back"
            />
          </template>
          <template #actions>
            <template v-if="isVocabulary">
              <button
                v-if="!flipped"
                type="button"
                class="w-full rounded-md bg-brand-accent px-2 py-2 font-bold uppercase text-white shadow-mech-sm transition-all hover:brightness-95 active:translate-y-0.5"
                @click="flipped = true"
              >
                显示答案
              </button>
              <ReviewRatingButtons v-else />
            </template>
            <footer
              v-else
              class="flex flex-wrap justify-center gap-3"
            >
              <RetroButton
                variant="secondary"
                :disabled="index === 0"
                @click="previous"
              >
                上一张
              </RetroButton>
              <RetroButton
                v-if="!flipped"
                @click="flipped = true"
              >
                显示答案
              </RetroButton>
              <template v-else>
                <RetroButton
                  variant="secondary"
                  @click="flipped = false"
                >
                  查看题面
                </RetroButton>
                <RetroButton @click="next">
                  {{ index + 1 === cards.length ? '完成本轮' : '下一张' }}
                </RetroButton>
              </template>
            </footer>
          </template>
        </component>
        <div
          v-if="isVocabulary"
          class="mt-4 w-full max-w-xl text-center"
        >
          <p
            v-if="flipped"
            class="mb-3 text-xs text-slate-500"
          >
            评分尚未启用，当前仅支持翻卡练习。
          </p>
          <nav
            v-if="previousWordIndex >= 0"
            aria-label="单词回退"
            class="text-sm text-slate-500"
          >
            <button
              type="button"
              class="hover:text-brand-accent"
              @click="previousWord"
            >
              上一张
            </button>
          </nav>
        </div>
      </div>
    </main>
  </div>
</template>
