<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { Plus } from 'lucide-vue-next'
import RetroButton from '@/components/ui/RetroButton.vue'
import LibraryContentEditor from '@/components/library/LibraryContentEditor.vue'
import DeckTreeItem from '@/components/library/DeckTreeItem.vue'
import CardPickerModal from '@/components/library/CardPickerModal.vue'
import { useDecksStore } from '@/stores/decks'
import { resourceError } from '@/services/content'
import type { DeckView } from '@/stores/decks'

const decksStore = useDecksStore()
const { libraryTree, loading, saving, error } = storeToRefs(decksStore)
const coreError = ref('')
const editor = ref<InstanceType<typeof LibraryContentEditor>>()
const cardPicker = ref<InstanceType<typeof CardPickerModal>>()

async function load() {
  coreError.value = ''
  try {
    await decksStore.load()
  } catch (cause) {
    coreError.value = resourceError(cause)
  }
}

onMounted(load)

async function handleToggleMembership(deckId: string) {
  coreError.value = ''
  try {
    const joined = await decksStore.toggleMembership(deckId)
    ElMessage.success(joined ? '已加入我的课程' : '已从我的课程移除')
  } catch (cause) {
    coreError.value = resourceError(cause)
  }
}

function handleSelectCards(deckId: string) {
  const deck = findDeck(libraryTree.value, deckId)
  if (deck) cardPicker.value?.show(deck)
}

function findDeck(nodes: DeckView[], deckId: string): DeckView | undefined {
  for (const node of nodes) {
    if (node.id === deckId) return node
    const child = findDeck(node.children, deckId)
    if (child) return child
  }
  return undefined
}

async function handleCardsSaved() {
  await load()
  ElMessage.success('课程学习范围已更新')
}

async function handleCreated() {
  await load()
  ElMessage.success('题库已更新')
}
</script>

<template>
  <div class="animate-fadeIn">
    <header class="mb-6 flex flex-wrap items-center justify-between gap-4">
      <h2 class="text-3xl font-bold uppercase text-brand-accent">
        题库资源
      </h2>
      <div class="flex flex-wrap gap-3">
        <RetroButton
          variant="secondary"
          :icon="Plus"
          @click="editor?.openDeck()"
        >
          添加牌组
        </RetroButton>
        <RetroButton
          :icon="Plus"
          @click="editor?.openCard()"
        >
          添加卡片
        </RetroButton>
      </div>
    </header>

    <LibraryContentEditor
      ref="editor"
      @created="handleCreated"
    />

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
      还没有牌组，先添加一个吧。
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
        :selection-disabled="saving"
        :depth="0"
        @toggle-membership="handleToggleMembership"
        @select-cards="handleSelectCards"
      />
    </div>

    <CardPickerModal
      ref="cardPicker"
      @saved="handleCardsSaved"
    />
  </div>
</template>
