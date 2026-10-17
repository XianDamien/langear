<script setup lang="ts">
import RetroCard from '@/components/ui/RetroCard.vue'

defineProps<{ isFlipped: boolean }>()
</script>

<template>
  <RetroCard
    :title="isFlipped ? 'Answer' : 'Question'"
    class="w-full max-w-xl"
  >
    <div class="flex flex-col">
      <div class="h-[22rem] w-full overflow-y-auto overscroll-contain px-4 py-6 sm:px-6">
        <div
          v-if="!isFlipped"
          class="flex h-full w-full items-start justify-start text-left"
          data-testid="card-front-container"
        >
          <slot name="front" />
        </div>
        <div
          v-else
          class="flex min-h-full w-full flex-col items-start justify-start gap-4 text-left"
          data-testid="card-back-container"
        >
          <slot name="back" />
        </div>
      </div>
      <div class="border-t border-slate-200 px-4 py-3">
        <slot name="actions" />
      </div>
    </div>
  </RetroCard>
</template>
