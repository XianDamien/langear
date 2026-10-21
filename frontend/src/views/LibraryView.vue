<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import DeckTreeItem from '@/components/library/DeckTreeItem.vue'
import LibraryCardsDialog from '@/components/library/LibraryCardsDialog.vue'
import { toView, useDecksStore } from '@/stores/decks'
import { fetchLibraryDeckTree, importLibraryDeck, resourceError } from '@/services/content'
import type { DeckView } from '@/stores/decks'

const decksStore = useDecksStore()
const libraryTree = ref<DeckView[]>([])
const loading = ref(false)
const importing = ref(false)
const error = ref<string | null>(null)
const coreError = ref('')
const cardsDialog = ref<InstanceType<typeof LibraryCardsDialog>>()

function findDeck(nodes: DeckView[], deckId: string): DeckView | undefined {
  for (const node of nodes) {
    if (node.id === deckId) return node
    const child = findDeck(node.children, deckId)
    if (child) return child
  }
  return undefined
}

function handlePreview(deckId: string) {
  const deck = findDeck(libraryTree.value, deckId)
  if (deck) cardsDialog.value?.show(deck)
}

async function load() {
  coreError.value = ''
  loading.value = true
  try {
    const data = await fetchLibraryDeckTree()
    libraryTree.value = data.tree.map(toView)
    error.value = null
  } catch (cause) {
    coreError.value = resourceError(cause)
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function handleToggleMembership(deckId: string) {
  if (importing.value) return
  importing.value = true
  coreError.value = ''
  try {
    const { data } = await importLibraryDeck(deckId)
    await Promise.all([load(), decksStore.load()])
    const added = data.created.cards
    const kept = data.existing.cards
    ElMessage.success(
      added
        ? `已加入我的课程：新增 ${added} 张卡片，保留 ${kept} 张已有卡片`
        : '课程已在“我的课程”中，没有需要新增的内容',
    )
    const moved = data.skipped_cards.filter(card => card.reason === 'CARD_ALREADY_IN_ANOTHER_DECK').length
    const changedType = data.skipped_cards.filter(card => card.reason === 'NOTE_TYPE_CHANGED').length
    if (moved) {
      ElMessage.warning(
        `${moved} 张卡片已被你移到其他牌组，未重复导入`,
      )
    }
    if (changedType) ElMessage.warning(`${changedType} 张卡片对应的笔记类型已更改，未重复导入`)
  } catch (cause) {
    coreError.value = resourceError(cause)
  } finally {
    importing.value = false
  }
}
</script>

<template>
  <div class="animate-fadeIn">
    <header class="mb-6 flex flex-wrap items-center justify-between gap-4">
      <h2 class="text-3xl font-bold uppercase text-brand-accent">
        题库资源
      </h2>
      <p class="text-sm text-slate-500">
        浏览共享课程内容；加入时会复制整套子课程，学习记录从零开始。
      </p>
    </header>

    <div
      v-if="coreError || error"
      role="alert"
      class="mb-4 text-amber-700"
    >
      {{ coreError || error }}
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
      v-else-if="!libraryTree.length"
      class="border-2 border-dashed border-slate-200 p-8 text-center text-slate-500"
    >
      共享题库暂时没有课程。
    </div>

    <div
      v-else
      class="space-y-2"
    >
      <DeckTreeItem
        v-for="deck in libraryTree"
        :key="deck.id"
        :deck="deck"
        mode="library"
        :selection-disabled="importing"
        :depth="0"
        @toggle-membership="handleToggleMembership"
        @preview-deck="handlePreview"
      />
    </div>
    <LibraryCardsDialog ref="cardsDialog" />
  </div>
</template>
