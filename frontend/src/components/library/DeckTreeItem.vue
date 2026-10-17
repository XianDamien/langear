<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChevronDown, ChevronRight, Check, Play, Plus, Settings } from 'lucide-vue-next'
import RetroButton from '@/components/ui/RetroButton.vue'
import type { Deck } from '@/types/domain'
import {
  collectLessonIds,
  getNodeSelectionStatus,
  getSelectedLessonCount,
} from '@/utils/deckSelection'

const props = defineProps<{
  deck: Deck
  mode: 'library' | 'my-courses'
  selectedLessonIdSet: Set<number>
  depth?: number
  selectedCoreDeckIds?: Set<string>
  selectionDisabled?: boolean
}>()

const emit = defineEmits<{
  selectLesson: [lessonId: string]
  toggleDeckSelection: [deckId: string]
  playDeck: [deckId: string]
  editDeckSettings: [deckId: string]
}>()

const expanded = ref(props.depth === 0)

const isCore = computed(() => props.deck.origin === 'core')
const lessonIds = computed(() => isCore.value ? [] : collectLessonIds(props.deck))
const totalLessonCount = computed(() => lessonIds.value.length)
const selectedLessonCount = computed(() =>
  getSelectedLessonCount(props.deck, props.selectedLessonIdSet),
)
const selectionStatus = computed(() =>
  isCore.value ? (props.selectedCoreDeckIds?.has(props.deck.id) ? 'full' : 'none') : getNodeSelectionStatus(props.deck, props.selectedLessonIdSet),
)

function toggle() {
  if (props.deck.children?.length) {
    expanded.value = !expanded.value
  }
}

function handleChevronClick() {
  toggle()
}

function handleRowClick() {
  if (props.mode === 'library') {
    toggle()
    return
  }

  if (props.deck.type === 'lesson') {
    emit('selectLesson', props.deck.id)
    return
  }

  if (props.mode === 'my-courses') {
    emit('playDeck', props.deck.id)
    return
  }

  toggle()
}

function handlePlayClick() {
  if (props.deck.type === 'lesson') {
    emit('selectLesson', props.deck.id)
    return
  }

  emit('playDeck', props.deck.id)
}
</script>

<template>
  <div :style="{ paddingLeft: `${(depth ?? 0) * 16}px` }">
    <div
      :class="[
        'mb-2 flex min-h-[70px] items-center justify-between border border-slate-200 p-3 transition-colors',
        mode === 'library' && !deck.children?.length ? 'cursor-default' : 'cursor-pointer',
        deck.type === 'lesson'
          ? 'bg-white hover:border-brand-accent'
          : 'bg-slate-50 hover:bg-slate-100',
      ]"
      @click="handleRowClick"
    >
      <div class="flex min-w-0 items-center gap-2">
        <template v-if="deck.children?.length">
          <ChevronDown
            v-if="expanded"
            :size="16"
            class="text-slate-400"
            @click.stop="handleChevronClick"
          />
          <ChevronRight
            v-else
            :size="16"
            class="text-slate-400"
            @click.stop="handleChevronClick"
          />
        </template>
        <div
          v-else
          class="w-4 shrink-0"
        />

        <div class="min-w-0">
          <button
            type="button"
            :disabled="mode === 'library' && !deck.children?.length"
            class="block max-w-full truncate text-left font-bold"
            :class="deck.type === 'lesson' ? 'text-base leading-6' : 'text-lg leading-7'"
            @click.stop="handleRowClick"
          >
            {{ deck.name }}
          </button>

          <div
            class="min-h-4 text-slate-500"
            :class="deck.type === 'lesson' ? 'text-sm leading-5' : 'text-xs leading-4'"
          >
            <template v-if="isCore">
              {{ deck.totalCards }} 张卡片
            </template>
            <template v-else-if="deck.type === 'lesson'">
              <span class="font-pixel text-brand-accent">新 {{ deck.newCards }}</span> ·
              <span class="font-pixel text-brand-accent">复习 {{ deck.reviewCards }}</span> ·
              <span class="text-green-600">完成 {{ deck.completedCards }}</span>
            </template>
            <template v-else-if="mode === 'library' && selectionStatus !== 'none'">
              {{ selectionStatus === 'full' ? '已选' : '' }}{{ selectedLessonCount }}/{{ totalLessonCount }}
            </template>
            <template v-else-if="mode === 'my-courses'">
              {{ totalLessonCount }} 节
            </template>
          </div>
        </div>
      </div>

      <div class="ml-3 flex shrink-0 items-center gap-2">
        <button
          v-if="mode === 'my-courses'"
          type="button"
          class="flex items-center justify-center rounded-md border border-slate-200 p-1.5 text-slate-400 transition hover:border-brand-accent hover:text-brand-accent"
          :title="`${deck.name} 设置`"
          :aria-label="`${deck.name} 设置`"
          @click.stop="emit('editDeckSettings', deck.id)"
        >
          <Settings :size="16" />
        </button>
        <template v-if="mode === 'library'">
          <RetroButton
            :variant="selectionStatus === 'full' ? 'primary' : 'secondary'"
            :disabled="selectionDisabled"
            size="sm"
            :icon="selectionStatus === 'full' ? Check : Plus"
            @click.stop="emit('toggleDeckSelection', deck.id)"
          >
            {{ selectionStatus === 'full' ? '已加入' : '加入' }}
          </RetroButton>
        </template>
        <template v-else>
          <RetroButton
            variant="primary"
            size="sm"
            :icon="Play"
            @click.stop="handlePlayClick"
          >
            开始
          </RetroButton>
        </template>
      </div>
    </div>

    <template v-if="expanded && deck.children?.length">
      <DeckTreeItem
        v-for="child in deck.children"
        :key="child.id"
        :deck="child"
        :mode="mode"
        :selected-lesson-id-set="selectedLessonIdSet"
        :selected-core-deck-ids="selectedCoreDeckIds"
        :selection-disabled="selectionDisabled"
        :depth="(depth ?? 0) + 1"
        @select-lesson="emit('selectLesson', $event)"
        @toggle-deck-selection="emit('toggleDeckSelection', $event)"
        @play-deck="emit('playDeck', $event)"
        @edit-deck-settings="emit('editDeckSettings', $event)"
      />
    </template>
  </div>
</template>
