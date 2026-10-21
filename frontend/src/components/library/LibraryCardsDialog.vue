<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import RetroButton from '@/components/ui/RetroButton.vue'
import { fetchLibraryCards, resourceError, templateLabels, type ResourceCard } from '@/services/content'
import type { DeckView } from '@/stores/decks'

const pageSize = 30
const open = ref(false)
const deckId = ref('')
const deckName = ref('')
const cards = ref<ResourceCard[]>([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const error = ref('')
let requestId = 0

const rows = computed(() => cards.value.map(card => ({
  id: card.id,
  label: templateLabels[card.card_template_key] || card.card_template_key,
  title: card.back.english || card.front.english || card.back.word || card.front.word || '无文字内容',
  detail: card.front.chinese || card.back.chinese || card.front.meaning || card.back.meaning || '',
})))

async function load(nextOffset: number) {
  const current = ++requestId
  loading.value = true
  error.value = ''
  try {
    const { data } = await fetchLibraryCards(deckId.value, {
      includeDescendants: true,
      limit: pageSize,
      offset: nextOffset,
    })
    if (current !== requestId) return
    cards.value = data.cards
    total.value = data.total
    offset.value = nextOffset
  } catch (cause) {
    if (current === requestId) error.value = resourceError(cause)
  } finally {
    if (current === requestId) loading.value = false
  }
}

function show(deck: DeckView) {
  deckId.value = deck.id
  deckName.value = deck.name
  cards.value = []
  total.value = 0
  offset.value = 0
  open.value = true
  void load(0)
}

function close() {
  requestId++
  open.value = false
}

function updateOpen(value: boolean) {
  if (!value) close()
}

defineExpose({ show })
</script>

<template>
  <el-dialog
    :model-value="open"
    :title="deckName"
    width="min(720px, 94vw)"
    class="resource-dialog"
    append-to-body
    :before-close="close"
    @update:model-value="updateOpen"
  >
    <p class="mb-4 text-sm text-slate-500">
      {{ total }} 张卡片
    </p>
    <p
      v-if="error"
      role="alert"
      class="mb-4 text-sm text-amber-700"
    >
      {{ error }}
      <button
        type="button"
        class="underline"
        @click="load(offset)"
      >
        重试
      </button>
    </p>
    <div
      v-if="loading"
      role="status"
      class="py-8 text-center text-slate-500"
    >
      加载中...
    </div>
    <div
      v-else-if="!rows.length && !error"
      class="py-8 text-center text-slate-500"
    >
      这个牌组还没有卡片。
    </div>
    <div
      v-else
      class="max-h-[55vh] overflow-y-auto border-y border-slate-200"
    >
      <div
        v-for="row in rows"
        :key="row.id"
        class="border-b border-slate-100 py-3 last:border-b-0"
      >
        <div class="mb-1 text-xs text-slate-500">
          {{ row.label }}
        </div>
        <div class="break-words font-medium text-slate-900">
          {{ row.title }}
        </div>
        <div
          v-if="row.detail"
          class="mt-1 break-words text-sm text-slate-600"
        >
          {{ row.detail }}
        </div>
      </div>
    </div>
    <div
      v-if="total > pageSize"
      class="mt-4 flex items-center justify-between gap-3"
    >
      <RetroButton
        variant="secondary"
        size="sm"
        :icon="ChevronLeft"
        :disabled="loading || offset === 0"
        title="上一页"
        aria-label="上一页"
        @click="load(Math.max(0, offset - pageSize))"
      />
      <span class="text-sm text-slate-500">
        {{ offset + 1 }}–{{ Math.min(offset + pageSize, total) }} / {{ total }}
      </span>
      <RetroButton
        variant="secondary"
        size="sm"
        :icon="ChevronRight"
        :disabled="loading || offset + pageSize >= total"
        title="下一页"
        aria-label="下一页"
        @click="load(offset + pageSize)"
      />
    </div>
  </el-dialog>
</template>
