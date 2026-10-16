<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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
const loading = ref(true)
const error = ref('')
const current = computed(() => cards.value[index.value])
const isVocabulary = computed(() => current.value?.card_template_key.startsWith('vocabulary_'))
const wordAnswer = computed(() => ({
  english: current.value?.back.word || '', chinese: current.value?.back.meaning,
  phonetic: current.value?.back.phonetic, note: current.value?.back.note,
}))
const wordMedia = computed(() => Object.fromEntries(Object.entries(current.value?.back || {}).filter(([key]) => key === 'reference_audio' || key === 'image')))
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
function restart() { index.value = 0; flipped.value = false; finished.value = false }
watch(() => route.params.deckId, load, { immediate: true })
onBeforeUnmount(() => { generation++ })
</script>

<template>
  <div
    class="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 py-4 sm:px-6 sm:py-6"
    data-testid="deck-review"
  >
    <header class="mb-6 flex items-center justify-between gap-3">
      <RetroButton
        variant="ghost"
        size="sm"
        class="shrink-0 whitespace-nowrap"
        @click="router.push('/library')"
      >
        返回题库
      </RetroButton>
      <h1 class="min-w-0 break-words text-center text-lg font-bold text-brand-accent">
        {{ deck?.name || '翻卡练习' }}
      </h1>
      <span
        v-if="cards.length && !finished"
        class="shrink-0 text-sm text-slate-500"
      >{{ index + 1 }} / {{ cards.length }}</span>
    </header>
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
      class="flex flex-1 flex-col items-center justify-center py-4"
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
          <footer class="flex flex-wrap justify-center gap-3">
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
    </div>
  </div>
</template>
