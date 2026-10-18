<script setup lang="ts">
defineProps<{ newRemaining: number; learningRemaining: number; reviewRemaining: number }>()
</script>

<template>
  <dl
    class="flex w-full items-center justify-end gap-4 text-xs leading-5 sm:gap-5"
    aria-label="剩余卡片"
    role="status"
    aria-live="polite"
    aria-atomic="true"
  >
    <div class="flex items-baseline gap-1.5">
      <dt class="text-slate-500">未学习</dt>
      <dd class="text-sm font-semibold tabular-nums text-blue-600">{{ newRemaining }}</dd>
    </div>
    <div class="flex items-baseline gap-1.5">
      <dt class="text-slate-500">学习中</dt>
      <dd class="text-sm font-semibold tabular-nums text-amber-600">{{ learningRemaining }}</dd>
    </div>
    <div class="flex items-baseline gap-1.5">
      <dt class="text-slate-500">待复习</dt>
      <dd class="text-sm font-semibold tabular-nums text-emerald-600">{{ reviewRemaining }}</dd>
    </div>
  </dl>
</template>
