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
      <div class="flex min-h-[16rem] items-center justify-center px-4 py-6">
        <div
          v-if="!isFlipped"
          class="w-full"
          data-testid="card-front-container"
        >
          <slot name="front" />
        </div>
        <div
          v-else
          class="flex w-full flex-col gap-4 text-left"
          data-testid="card-back-container"
        >
          <slot name="back" />
        </div>
      </div>
      <div class="border-t border-slate-200 px-2 py-3 sm:px-4">
        <slot name="actions" />
      </div>
    </div>
  </RetroCard>
</template>
