<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChevronDown, ChevronRight, Check, Play, Plus, Settings, ListChecks } from 'lucide-vue-next'
import RetroButton from '@/components/ui/RetroButton.vue'
import type { DeckView } from '@/stores/decks'

const props = defineProps<{
  deck: DeckView
  mode: 'library' | 'my-courses'
  selectionDisabled?: boolean
  depth?: number
}>()

const emit = defineEmits<{
  toggleMembership: [deckId: string]
  playDeck: [deckId: string]
  editDeckSettings: [deckId: string]
  selectCards: [deckId: string]
}>()

const expanded = ref((props.depth ?? 0) === 0)
const hasChildren = computed(() => props.deck.children.length > 0)

function toggle() {
  if (hasChildren.value) expanded.value = !expanded.value
}

function handleRowClick() {
  if (props.mode === 'library') {
    toggle()
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
        mode === 'library' && !hasChildren ? 'cursor-default' : 'cursor-pointer',
        hasChildren ? 'bg-slate-50 hover:bg-slate-100' : 'bg-white hover:border-brand-accent',
      ]"
      @click="handleRowClick"
    >
      <div class="flex min-w-0 items-center gap-2">
        <template v-if="hasChildren">
          <ChevronDown
            v-if="expanded"
            :size="16"
            class="text-slate-400"
            @click.stop="toggle"
          />
          <ChevronRight
            v-else
            :size="16"
            class="text-slate-400"
            @click.stop="toggle"
          />
        </template>
        <div
          v-else
          class="w-4 shrink-0"
        />

        <div class="min-w-0">
          <button
            type="button"
            class="block max-w-full truncate text-left font-bold"
            :class="hasChildren ? 'text-lg leading-7' : 'text-base leading-6'"
            @click.stop="handleRowClick"
          >
            {{ deck.name }}
          </button>

          <div
            class="min-h-4 text-slate-500"
            :class="hasChildren ? 'text-xs leading-4' : 'text-sm leading-5'"
          >
            {{ deck.sentenceCount }} 句
          </div>
        </div>
      </div>

      <div class="ml-3 flex shrink-0 items-center gap-2">
        <template v-if="mode === 'my-courses'">
          <button
            type="button"
            class="flex items-center justify-center rounded-md border border-slate-200 p-1.5 text-slate-400 transition hover:border-brand-accent hover:text-brand-accent"
            :title="`${deck.name} 设置`"
            :aria-label="`${deck.name} 设置`"
            @click.stop="emit('editDeckSettings', deck.id)"
          >
            <Settings :size="16" />
          </button>
          <RetroButton
            variant="primary"
            size="sm"
            :icon="Play"
            @click.stop="emit('playDeck', deck.id)"
          >
            开始
          </RetroButton>
        </template>
        <template v-else>
          <button
            type="button"
            class="flex items-center justify-center rounded-md border border-slate-200 p-1.5 text-slate-400 transition hover:border-brand-accent hover:text-brand-accent disabled:opacity-40"
            :disabled="selectionDisabled"
            :title="`${deck.name} 选择卡片`"
            :aria-label="`${deck.name} 选择卡片`"
            @click.stop="emit('selectCards', deck.id)"
          >
            <ListChecks :size="16" />
          </button>
          <RetroButton
            :variant="deck.inMyCourses ? 'primary' : 'secondary'"
            :disabled="selectionDisabled"
            size="sm"
            :icon="deck.inMyCourses ? Check : Plus"
            @click.stop="emit('toggleMembership', deck.id)"
          >
            {{ deck.inMyCourses ? '已加入' : '加入' }}
          </RetroButton>
        </template>
      </div>
    </div>

    <template v-if="expanded && hasChildren">
      <DeckTreeItem
        v-for="child in deck.children"
        :key="child.id"
        :deck="child"
        :mode="mode"
        :selection-disabled="selectionDisabled"
        :depth="(depth ?? 0) + 1"
        @toggle-membership="emit('toggleMembership', $event)"
        @play-deck="emit('playDeck', $event)"
        @edit-deck-settings="emit('editDeckSettings', $event)"
        @select-cards="emit('selectCards', $event)"
      />
    </template>
  </div>
</template>
