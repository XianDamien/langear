<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import DeckTreeItem from '@/components/library/DeckTreeItem.vue'
import RetroButton from '@/components/ui/RetroButton.vue'
import { useDecksStore } from '@/stores/decks'
import { resourceError } from '@/services/content'

const route = useRoute()
const router = useRouter()
const decksStore = useDecksStore()
const { myCourses, loading } = storeToRefs(decksStore)
const error = ref('')

const notice = computed(() => {
  switch (route.query.notice) {
    case 'legacy-link-invalid':
      return '旧链接已失效，已返回我的课程。'
    case 'invalid-deck':
      return '该课程链接无效。'
    case 'invalid-card':
      return '该卡片链接无效。'
    default:
      return ''
  }
})

async function load() {
  error.value = ''
  try {
    await decksStore.load()
  } catch (cause) {
    error.value = resourceError(cause)
  }
}

onMounted(load)

function handlePlayDeck(deckId: string) {
  void router.push({ name: 'DeckReview', params: { deckId } })
}

function handleEditDeckSettings(deckId: string) {
  void router.push({ name: 'Settings', query: { deck_id: deckId } })
}
</script>

<template>
  <div class="animate-fadeIn">
    <h2 class="mb-6 text-3xl font-bold uppercase text-brand-accent">
      我的课程
    </h2>

    <p
      v-if="notice"
      role="status"
      class="mb-4 border border-slate-200 bg-white p-3 text-sm text-slate-600"
    >
      {{ notice }}
    </p>
    <div
      v-if="error"
      role="alert"
      class="mb-4 text-amber-700"
    >
      {{ error }}
      <button
        type="button"
        class="underline"
        @click="load"
      >
        重试
      </button>
    </div>
    <div
      v-if="loading"
      class="py-20 text-center text-slate-500"
    >
      加载中...
    </div>

    <div
      v-else-if="!myCourses.length && !error"
      class="border-2 border-dashed border-slate-200 p-8 text-center"
    >
      <p class="mb-4 text-slate-500">
        你还没有加入任何课程。去题库资源挑选一些牌组吧。
      </p>
      <RetroButton
        variant="primary"
        size="sm"
        @click="router.push('/library')"
      >
        去题库资源添加课程
      </RetroButton>
    </div>

    <div
      v-else
      class="space-y-2"
    >
      <DeckTreeItem
        v-for="deck in myCourses"
        :key="deck.id"
        :deck="deck"
        mode="my-courses"
        :depth="0"
        @play-deck="handlePlayDeck"
        @edit-deck-settings="handleEditDeckSettings"
      />
    </div>
  </div>
</template>
