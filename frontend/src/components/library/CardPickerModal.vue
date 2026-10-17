<script setup lang="ts">
import { computed, ref } from 'vue'
import RetroButton from '@/components/ui/RetroButton.vue'
import { contentResources, libraryContent } from '@/services/libraryContent'
import { fetchMyCourseCards, updateMyCourseCards, fetchLessonCards } from '@/services/api/decks'
import { resourceError, templateLabels, type ResourceCard } from '@/services/contentCore'
import type { Deck } from '@/types/domain'

interface Choice { id: string; english: string; chinese: string; cardIds: string[]; label?: string }
const emit = defineEmits<{ saved: [] }>()
const open = ref(false)
const source = ref<Deck>()
const choices = ref<Choice[]>([])
const selected = ref<string[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
let generation = 0
const selectedIds = computed(() => new Set(selected.value))
const selectedCards = computed(() => choices.value.filter(row => selectedIds.value.has(row.id)).flatMap(row => row.cardIds))
const allSelected = computed(() => choices.value.length > 0 && selected.value.length === choices.value.length)
async function show(deck: Deck) {
  const request = ++generation
  source.value = deck
  choices.value = []
  selected.value = []
  error.value = ''
  open.value = true
  loading.value = true
  try {
    let rows: Choice[]
    let scope: string[] | null
    if (deck.origin === 'core') {
      const [cards, response] = await Promise.all([
        contentResources<ResourceCard>('/cards', 'cards', { deck_id: deck.id }),
        libraryContent.get<{ card_ids: string[] | null }>(`/decks/${deck.id}/study-selection`),
      ])
      const notes = new Map<string, Choice>()
      for (const card of cards) {
        let row = notes.get(card.note_id)
        if (!row) {
          row = { id: card.note_id, english: card.back.english || card.back.word || card.front.word || '',
            chinese: card.back.chinese || card.front.chinese || card.back.meaning || card.front.meaning || '', cardIds: [], label: '' }
          notes.set(card.note_id, row)
        }
        row.cardIds.push(card.id)
        row.label = [row.label, templateLabels[card.card_template_key]].filter(Boolean).join(' · ')
      }
      rows = [...notes.values()]
      scope = response.data.card_ids
    } else {
      const [response, selection] = await Promise.all([fetchLessonCards(deck.id), fetchMyCourseCards(deck.id)])
      rows = response.data.cards.map(card => ({ id: String(card.id), english: card.front_text || '', chinese: card.back_text || '', cardIds: [String(card.id)] }))
      scope = selection.data.card_ids?.map(String) ?? null
    }
    if (request !== generation) return
    choices.value = rows
    const ids = scope === null ? null : new Set(scope)
    selected.value = rows.filter(row => ids === null || row.cardIds.every(id => ids.has(id))).map(row => row.id)
  } catch (cause) { if (request === generation) error.value = resourceError(cause) }
  finally { if (request === generation) loading.value = false }
}
function close() { if (!saving.value) { generation++; open.value = false } }
function toggleAll() { selected.value = allSelected.value ? [] : choices.value.map(row => row.id) }
async function save(whole = false) {
  const deck = source.value
  if (!deck || saving.value || loading.value) return
  saving.value = true
  error.value = ''
  try {
    const ids = whole ? null : selectedCards.value
    if (deck.origin === 'core') await libraryContent.put(`/decks/${deck.id}/study-selection`, { card_ids: ids })
    else await updateMyCourseCards(deck.id, ids?.map(Number) ?? null)
    open.value = false
    emit('saved')
  } catch (cause) { error.value = resourceError(cause) }
  finally { saving.value = false }
}
defineExpose({ show, close })
</script>

<template>
  <el-dialog
    :model-value="open"
    :title="`${source?.name || ''} · 选择内容`"
    width="760px"
    class="resource-dialog"
    append-to-body
    top="6vh"
    :close-on-click-modal="false"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    :before-close="close"
  >
    <p class="mb-4 text-sm text-slate-500">勾选本课程要练习的内容，保留原课程和已有学习进度。整组加入会包含后续新增的内容。</p>
    <p v-if="loading" role="status" class="py-6 text-slate-500">正在加载可选内容…</p>
    <div v-else-if="choices.length">
      <div class="mb-3 flex items-center justify-between gap-3">
        <span class="text-sm text-slate-500">已选 {{ selected.length }} / {{ choices.length }} 条内容 · {{ selectedCards.length }} 张卡片</span>
        <RetroButton variant="secondary" size="sm" :disabled="saving" @click="toggleAll">{{ allSelected ? '取消全选' : '全选' }}</RetroButton>
      </div>
      <div class="max-h-[38vh] space-y-2 overflow-y-auto">
        <label v-for="(note, index) in choices" :key="note.id" class="flex cursor-pointer items-start gap-3 border border-slate-200 bg-slate-50 p-3 hover:border-brand-accent">
          <input v-model="selected" type="checkbox" :value="note.id" :disabled="saving" :aria-label="`选择第 ${index + 1} 条`" class="mt-1 h-4 w-4 shrink-0 accent-red-500">
          <div class="min-w-0 text-sm">
            <p class="whitespace-pre-wrap break-words font-semibold text-slate-900">{{ index + 1 }}. {{ note.english || note.chinese }}</p>
            <p v-if="note.english && note.chinese" class="mt-1 whitespace-pre-wrap text-slate-500">{{ note.chinese }}</p>
            <p v-if="note.label" class="mt-1 text-xs text-slate-400">{{ note.label }}</p>
          </div>
        </label>
      </div>
    </div>
    <p v-else-if="!error" class="py-6 text-slate-500">此范围还没有可选择的卡片。</p>
    <p v-if="error" role="alert" class="mt-4 text-sm text-amber-700">{{ error }} <button v-if="source && !saving" type="button" class="underline" @click="show(source)">重新加载</button></p>
    <footer class="mt-5 flex flex-wrap justify-end gap-3 border-t border-slate-200 pt-4">
      <RetroButton variant="secondary" :disabled="saving" @click="close">取消</RetroButton>
      <RetroButton variant="secondary" :disabled="loading || saving || !choices.length" @click="save(true)">整组加入</RetroButton>
      <RetroButton :disabled="loading || saving || !choices.length" @click="save(false)">{{ saving ? '保存中…' : selectedCards.length ? '加入所选内容' : '移除本课程' }}</RetroButton>
    </footer>
  </el-dialog>
</template>
