<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChevronDown, ChevronRight, Check, Play, Plus } from 'lucide-vue-next'
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
}>()

const emit = defineEmits<{
  selectLesson: [lessonId: string]
  toggleDeckSelection: [deckId: string]
  playDeck: [deckId: string]
}>()

const expanded = ref(props.depth === 0)

const lessonIds = computed(() => collectLessonIds(props.deck))
const totalLessonCount = computed(() => lessonIds.value.length)
const selectedLessonCount = computed(() =>
  getSelectedLessonCount(props.deck, props.selectedLessonIdSet),
)
const selectionStatus = computed(() =>
  getNodeSelectionStatus(props.deck, props.selectedLessonIdSet),
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
        'mb-2 flex items-center justify-between border border-slate-200 p-3 transition-colors',
        deck.type === 'lesson'
          ? 'cursor-pointer bg-white hover:border-brand-accent'
          : 'cursor-pointer bg-slate-50 hover:bg-slate-100',
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
          class="w-4"
        />

        <div class="min-w-0">
          <div
            class="truncate font-bold"
            :class="deck.type === 'lesson' ? 'text-base' : 'text-lg'"
          >
            {{ deck.name }}
          </div>

          <div
            v-if="deck.type === 'lesson'"
            class="text-sm text-slate-500"
          >
            <span class="font-pixel text-brand-accent">{{ deck.newCards }}</span> 新卡 •
            <span class="font-pixel text-brand-accent">{{ deck.reviewCards }}</span> 复习 •
            <span class="text-green-600">{{ deck.completedCards }}</span> 已完成
          </div>

          <div
            v-else
            class="text-xs text-slate-500 uppercase"
          >
            <template v-if="mode === 'library' && selectionStatus !== 'none'">
              已加入 {{ selectedLessonCount }}/{{ totalLessonCount }} lessons •
            </template>
            <template v-if="mode === 'my-courses'">
              {{ totalLessonCount }} lessons •
            </template>
            {{ deck.totalCards }} 句
          </div>
        </div>
      </div>

      <div class="ml-3 flex shrink-0 items-center gap-2">
        <template v-if="mode === 'library'">
          <RetroButton
            :variant="selectionStatus === 'full' ? 'primary' : 'secondary'"
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
        :depth="(depth ?? 0) + 1"
        @select-lesson="emit('selectLesson', $event)"
        @toggle-deck-selection="emit('toggleDeckSelection', $event)"
        @play-deck="emit('playDeck', $event)"
      />
    </template>
  </div>
</template>
