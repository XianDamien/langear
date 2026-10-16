<script setup lang="ts">
import { computed } from 'vue'
import RetroCard from '@/components/ui/RetroCard.vue'

const props = defineProps<{
  isFlipped: boolean
}>()

const cardClass = computed(() =>
  props.isFlipped
    ? 'flex h-full min-h-0 flex-col p-4 sm:p-5'
    : 'flex h-full min-h-0 flex-col items-center justify-center p-4 text-center sm:p-5',
)
</script>

<template>
  <RetroCard :title="isFlipped ? 'Answer' : 'Question'" :class="cardClass">
    <div
      v-if="!isFlipped"
      class="flex max-h-full w-full flex-col items-center overflow-y-auto overscroll-contain"
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
  </RetroCard>
</template>
