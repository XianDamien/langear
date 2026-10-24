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
    <div class="flex items-baseline justify-between mb-1">
      <span class="text-sm uppercase text-slate-500">{{ label }}</span>
      <span class="flex items-baseline gap-1 text-slate-900">
        <span class="dashboard-number text-4xl">{{ value }}</span>
        <span class="dashboard-number text-base text-slate-600">/ {{ max }}</span>
      </span>
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
