<script setup lang="ts">
import { computed, ref } from 'vue'
import RetroButton from '@/components/ui/RetroButton.vue'
import {
  fetchAllLibraryCards,
  fetchLibrarySelection,
  importLibraryDeck,
  resourceError,
  templateLabels,
  type ResourceCard,
} from '@/services/content'
import type { DeckView } from '@/stores/decks'

interface Choice {
  id: string
  english: string
  chinese: string
  cardCount: number
  label: string
}

const emit = defineEmits<{ saved: [] }>()
const open = ref(false)
const source = ref<DeckView>()
const choices = ref<Choice[]>([])
const selected = ref<string[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
let generation = 0

const selectedIds = computed(() => new Set(selected.value))
const selectedCardCount = computed(() =>
  choices.value
    .filter(row => selectedIds.value.has(row.id))
    .reduce((total, row) => total + row.cardCount, 0),
)
const allSelected = computed(() => choices.value.length > 0 && selected.value.length === choices.value.length)

function groupCards(cards: ResourceCard[]): Choice[] {
  const notes = new Map<string, Choice>()
  for (const card of cards) {
    const id = card.note_guid || card.note_id
    let row = notes.get(id)
    if (!row) {
      row = {
        id,
        english: card.back.english || card.back.word || card.front.word || '',
        chinese: card.back.chinese || card.front.chinese || card.back.meaning || card.front.meaning || '',
        cardCount: 0,
        label: '',
      }
      notes.set(id, row)
    }
    row.cardCount += 1
    const label = templateLabels[card.card_template_key] || card.card_template_key
    if (!row.label.split(' · ').includes(label)) {
      row.label = [row.label, label].filter(Boolean).join(' · ')
    }
  }
  return [...notes.values()]
}

async function show(deck: DeckView) {
  const request = ++generation
  source.value = deck
  choices.value = []
  selected.value = []
  error.value = ''
  open.value = true
  loading.value = true
  try {
    const [cards, response] = await Promise.all([
      fetchAllLibraryCards(deck.id),
      fetchLibrarySelection(deck.id),
    ])
    if (request !== generation) return
    const rows = groupCards(cards)
    choices.value = rows
    const scope = response.data.note_guids
    const ids = scope === null ? null : new Set(scope)
    selected.value = rows
      .filter(row => ids === null || ids.has(row.id))
      .map(row => row.id)
  } catch (cause) {
    if (request === generation) error.value = resourceError(cause)
  } finally {
    if (request === generation) loading.value = false
  }
}

function close() {
  if (!saving.value) {
    generation++
    open.value = false
  }
}

function updateOpen(value: boolean) {
  if (!value) close()
}

function toggleAll() {
  selected.value = allSelected.value ? [] : choices.value.map(row => row.id)
}

async function save(whole = false) {
  const deck = source.value
  if (!deck || saving.value || loading.value) return
  if (!whole && !selected.value.length) return
  const noteGuids = whole ? null : selected.value
  saving.value = true
  error.value = ''
  try {
    await importLibraryDeck(deck.id, noteGuids)
    open.value = false
    emit('saved')
  } catch (cause) {
    error.value = resourceError(cause)
  } finally {
    saving.value = false
  }
}

defineExpose({ show, close })
</script>

<template>
  <el-dialog
    :model-value="open"
    :title="`${source?.name || ''} · 选择句子`"
    width="min(760px, 94vw)"
    class="resource-dialog"
    append-to-body
    top="6vh"
    :close-on-click-modal="!saving"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    :before-close="close"
    @update:model-value="updateOpen"
  >
    <p class="mb-4 text-sm text-slate-500">
      勾选本课程要练习的句子；同一条内容的多张卡片会一起加入。选择会同步课程到「我的课程」。
    </p>
    <p
      v-if="loading"
      role="status"
      class="py-6 text-slate-500"
    >
      正在加载可选内容…
    </p>
    <div v-else-if="choices.length">
      <div class="mb-3 flex items-center justify-between gap-3">
        <span class="text-sm text-slate-500">已选 {{ selected.length }} / {{ choices.length }} 条内容 · {{ selectedCardCount }} 张卡片</span>
        <RetroButton
          variant="secondary"
          size="sm"
          :disabled="saving"
          @click="toggleAll"
        >
          {{ allSelected ? '取消全选' : '全选' }}
        </RetroButton>
      </div>
      <div class="max-h-[38vh] space-y-2 overflow-y-auto">
        <label
          v-for="(note, index) in choices"
          :key="note.id"
          class="flex cursor-pointer items-start gap-3 border border-slate-200 bg-slate-50 p-3 hover:border-brand-accent"
        >
          <input
            v-model="selected"
            type="checkbox"
            :value="note.id"
            :disabled="saving"
            :aria-label="`选择第 ${index + 1} 条`"
            class="mt-1 h-4 w-4 shrink-0 accent-red-500"
          >
          <div class="min-w-0 text-sm">
            <p class="whitespace-pre-wrap break-words font-semibold text-slate-900">
              {{ index + 1 }}. {{ note.english || note.chinese }}
            </p>
            <p
              v-if="note.english && note.chinese"
              class="mt-1 whitespace-pre-wrap text-slate-500"
            >
              {{ note.chinese }}
            </p>
            <p
              v-if="note.label"
              class="mt-1 text-xs text-slate-400"
            >
              {{ note.label }}
            </p>
          </div>
        </label>
      </div>
    </div>
    <p
      v-else-if="!error"
      class="py-6 text-slate-500"
    >
      此范围还没有可选择的卡片。
    </p>
    <p
      v-if="error"
      role="alert"
      class="mt-4 text-sm text-amber-700"
    >
      {{ error }}
      <button
        v-if="source && !saving"
        type="button"
        class="underline"
        @click="show(source)"
      >
        重新加载
      </button>
    </p>
    <footer class="mt-5 flex flex-wrap justify-end gap-3 border-t border-slate-200 pt-4">
      <RetroButton
        variant="secondary"
        :disabled="saving"
        @click="close"
      >
        取消
      </RetroButton>
      <RetroButton
        variant="secondary"
        :disabled="loading || saving || !choices.length"
        @click="save(true)"
      >
        整组加入
      </RetroButton>
      <RetroButton
        :disabled="loading || saving || !selected.length"
        @click="save(false)"
      >
        {{ saving ? '保存中…' : `加入所选内容（${selectedCardCount} 张卡片）` }}
      </RetroButton>
    </footer>
  </el-dialog>
</template>
