<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  value: number
  max: number
  label?: string
}>()

const percentage = computed(() =>
  Math.min(100, Math.max(0, (props.value / props.max) * 100)),
)
</script>

<template>
  <div class="w-full">
    <div class="flex justify-between text-sm mb-1 uppercase text-slate-500">
      <span>{{ label }}</span>
      <span class="font-pixel text-base font-bold tabular-nums text-slate-900">{{ value }} / {{ max }}</span>
    </div>
    <div class="h-4 bg-slate-100 border border-slate-200 relative">
      <div
        class="h-full transition-all duration-300 relative overflow-hidden"
        :style="{
          width: `${percentage}%`,
          backgroundImage: 'linear-gradient(90deg, #ff4d2d 0%, #ff7a45 100%)',
        }"
      >
        <div
          class="absolute inset-0 w-full h-full"
          :style="{
            backgroundImage:
              'linear-gradient(45deg,rgba(255,255,255,.25) 25%,transparent 25%,transparent 50%,rgba(255,255,255,.25) 50%,rgba(255,255,255,.25) 75%,transparent 75%,transparent)',
            backgroundSize: '1rem 1rem',
          }"
        />
      </div>
    </div>
  </div>
</template>
