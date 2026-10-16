<script setup lang="ts">
import type { FsrsRating } from '@/types/domain'

defineProps<{
  disabled?: boolean
}>()

const emit = defineEmits<{
  grade: [rating: FsrsRating]
}>()

const buttons: {
  rating: FsrsRating
  label: string
  interval: string
  color: string
}[] = [
  { rating: 1, label: '再来', interval: '1m', color: 'bg-red-500' },
  { rating: 2, label: '困难', interval: '6m', color: 'bg-amber-500' },
  { rating: 3, label: '良好', interval: '10m', color: 'bg-emerald-600' },
  { rating: 4, label: '轻松', interval: '4d', color: 'bg-sky-600' },
]
</script>

<template>
  <div class="grid grid-cols-2 gap-2 md:grid-cols-4">
    <button
      v-for="btn in buttons"
      :key="btn.rating"
      type="button"
      class="rounded-md px-2 py-2 text-white shadow-mech-sm transition-all hover:brightness-95 active:translate-y-0.5 active:shadow-none disabled:cursor-not-allowed disabled:opacity-50"
      :class="btn.color"
      :disabled="disabled"
      @click="emit('grade', btn.rating)"
    >
      <div class="flex min-w-0 flex-col items-center leading-tight">
        <span class="text-sm font-bold">{{ btn.label }}</span>
        <span class="text-xs font-medium opacity-90">{{ btn.interval }}</span>
      </div>
    </button>
  </div>
</template>
