<script setup lang="ts">
import type { Rating, RatingOption } from '@/services/review'
withDefaults(defineProps<{ options?: RatingOption[]; disabled?: boolean }>(), { options: () => [], disabled: false })
const emit = defineEmits<{ rate: [rating: Rating] }>()
const ratings: { value: Rating; label: string; color: string }[] = [
  { value: 'again', label: 'Again', color: 'bg-red-500' },
  { value: 'hard', label: 'Hard', color: 'bg-amber-500' },
  { value: 'good', label: 'Good', color: 'bg-emerald-600' },
  { value: 'easy', label: 'Easy', color: 'bg-sky-600' },
]
</script>
<template>
  <div
    class="grid grid-cols-4 gap-2"
    role="group"
    aria-label="复习评分"
  >
    <button
      v-for="rating in ratings"
      :key="rating.value"
      type="button"
      :data-testid="`rate-${rating.value}`"
      :disabled="disabled || !options.some(option => option.rating === rating.value)"
      :class="rating.color"
      class="rounded-md px-2 py-2 text-white shadow-mech-sm transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50"
      @click="emit('rate', rating.value)"
    >
      <span class="flex flex-col items-center leading-tight">
        <span class="text-sm font-bold uppercase">{{ rating.label }}</span>
        <span class="text-xs font-medium opacity-90">{{ options.find(option => option.rating === rating.value)?.display_interval || '—' }}</span>
      </span>
    </button>
  </div>
</template>
