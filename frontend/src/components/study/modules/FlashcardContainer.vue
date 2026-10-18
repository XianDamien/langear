<script setup lang="ts">
import { computed, useSlots } from 'vue'
import RetroCard from '@/components/ui/RetroCard.vue'

const props = defineProps<{
  isFlipped: boolean
}>()
const slots = useSlots()

const cardClass = computed(() =>
  props.isFlipped
    ? 'flex h-full min-h-0 flex-col p-4 sm:p-5'
    : `flex h-full min-h-0 flex-col items-center ${slots.toolbar ? 'justify-start' : 'justify-center'} p-4 text-center sm:p-5`,
)
</script>

<template>
  <RetroCard
    :title="isFlipped ? 'Answer' : 'Question'"
    :class="cardClass"
  >
    <slot name="toolbar" />
    <div
      v-if="!isFlipped"
      class="flex max-h-full w-full flex-col items-center overflow-y-auto overscroll-contain"
      :class="$slots.toolbar ? 'min-h-0 flex-1 justify-center' : ''"
      data-testid="card-front-container"
    >
      <slot name="front" />
    </div>
    <div
      v-else
      class="flex h-full min-h-0 w-full flex-col text-left"
      data-testid="card-back-container"
    >
      <slot name="back" />
    </div>
    <div
      v-if="$slots.actions"
      class="mt-6 w-full shrink-0 border-t border-slate-200 pt-4"
    >
      <slot name="actions" />
    </div>
  </RetroCard>
</template>
