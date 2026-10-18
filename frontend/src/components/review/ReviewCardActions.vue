<script setup lang="ts">
import { Pause, SkipForward, Undo2 } from 'lucide-vue-next'

defineProps<{ busy?: boolean; canUndo: boolean; canSchedule: boolean }>()
const emit = defineEmits<{ undo: []; schedule: [action: 'bury' | 'suspend'] }>()
</script>

<template>
  <div
    class="mb-4 flex w-full flex-wrap items-center justify-between gap-2 text-xs text-slate-500"
    role="group"
    aria-label="卡片操作"
  >
    <button
      type="button"
      class="inline-flex items-center gap-1.5 py-1 transition hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
      :disabled="busy || !canUndo"
      @click="emit('undo')"
    >
      <Undo2 :size="14" />撤回上一张
    </button>
    <div class="flex items-center gap-3">
      <button
        type="button"
        class="inline-flex items-center gap-1 py-1 transition hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
        title="搁置到下一个学习日"
        :disabled="busy || !canSchedule"
        @click="emit('schedule', 'bury')"
      >
        <SkipForward :size="14" />今日跳过
      </button>
      <button
        type="button"
        class="inline-flex items-center gap-1 py-1 transition hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
        :disabled="busy || !canSchedule"
        @click="emit('schedule', 'suspend')"
      >
        <Pause :size="14" />暂停此卡
      </button>
    </div>
  </div>
</template>
